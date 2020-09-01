"""Run user-provided command on target endpoint.

Troubleshooting aid for troubled endpoint testing.

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Sep 1, 2020

"""
import sys
import traceback
from contextlib import suppress
import json
import os
import re

## From openContentPlatform
from protocolWrapper import getClient
from osProcesses import getProcesses
from osSoftwarePackages import getSoftwarePackages
from osStartTasks import getStartTasks
from utilities import loadConfigGroupFile, compareFilter, getApiResult
from utilities import getApiQueryResultsFull

## Global for ease of future change
validShellTypes = ["PowerShell", "SSH"]



def issueApiCall(runtime):
	endpoint = None
	## Get the parameters
	inputQuery = runtime.parameters.get('inputQuery')
	targetIp = runtime.parameters.get('endpointIp')

	## Corresponding directory for our input query
	jobScriptPath = os.path.dirname(os.path.realpath(__file__))
	jobPath = os.path.abspath(os.path.join(jobScriptPath, '..'))

	## Load the file containing the query
	queryFile = os.path.join(jobPath, 'input', inputQuery + '.json')
	if not os.path.isfile(queryFile):
		raise EnvironmentError('JSON query file does not exist: {}'.format(queryFile))
	queryContent = None
	with open(queryFile, 'r') as fp:
		queryContent = fp.read()

	## We do not know shell type, and in the future there may be more. So we
	## will loop through each one, trying until we find it.

	## Note: previously this was sent in by the endpoint query, but when we
	## switched over to make the IP a parameter instead... the shell details are
	## no longer sent into the job. Hence this step to request from the API.
	## The idea was to simplify user experience by adding more code.
	queryResults = None
	for shellType in validShellTypes:
		thisQuery = queryContent
		## Replace <VALUE1> and <VALUE2> placeholders:
		##   VALUE1 = the shell type: PowerShell or SSH
		##   VALUE2 = the IP address of the target endpoint you wish to template
		thisQuery = thisQuery.replace('<VALUE1>', '"{}"'.format(shellType))
		thisQuery = thisQuery.replace('<VALUE2>', '"{}"'.format(targetIp))

		queryResults = getApiQueryResultsFull(runtime, thisQuery, resultsFormat='Nested', headers={'removeEmptyAttributes': False})
		if queryResults is not None and len(queryResults[shellType]) > 0:
			break

	if queryResults is None or len(queryResults[shellType]) <= 0:
		raise EnvironmentError('Could not find endpoint {} with a correspoinding shell. Please make sure to run the corresponding "Find" job first.'.format(targetIp))

	runtime.logger.report('queryResults: {queryResults!r}...', queryResults=queryResults)
	## Set the protocol data on runtime, as though it was sent in regularly.
	## And don't use 'get'; allow exceptions here if endpoint values are missing
	endpoint = queryResults[shellType][0]
	runtime.endpoint = {
		"class_name" : endpoint["class_name"],
		"identifier" : endpoint["identifier"],
		"data" : endpoint["data"]
	}
	runtime.setParameters()

	return endpoint


def getNodeDetails(runtime):
	"""Pull attributes off the node sent in the endpoint.

	Arguments:
	  runtime (dict) : object used for providing I/O for jobs and tracking
	                   the job thread through its runtime.
	"""
	nodeDetails = {}
	endpoint = issueApiCall(runtime)

	## Node should be directly connected to the endpoint linchpin
	objectsLinkedToLinchpin = endpoint.get('children',{})
	nodeFound = False
	hostname = None
	for objectLabel, objectList in objectsLinkedToLinchpin.items():
		runtime.logger.report(' looking for Node in related objects label {objectLabel!r}...', objectLabel=objectLabel)
		for entry in objectList:
			if 'hostname' not in entry.get('data').keys():
				break
			nodeDetails['hostname'] = entry.get('data').get('hostname')
			nodeDetails['domain'] = entry.get('data').get('domain')
			nodeDetails['vendor'] = entry.get('data').get('vendor')
			nodeDetails['platform'] = entry.get('data').get('platform')
			nodeDetails['version'] = entry.get('data').get('version')
			nodeDetails['provider'] = entry.get('data').get('hardware_provider')
			runtime.logger.report(' --> found hostname {hostname!r}: {vendor!r}, {platform!r}, {version!r}, {provider!r}', hostname=nodeDetails['hostname'], vendor=nodeDetails['vendor'], platform=nodeDetails['platform'], version=nodeDetails['version'], provider=nodeDetails['provider'])
			return nodeDetails

	## end getNodeDetails
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict) : object used for providing I/O for jobs and tracking
	                   the job thread through its runtime.
	"""
	client = None
	try:
		## Issue API query for the node, and get details for creating this entry
		nodeDetails = getNodeDetails(runtime)
		if nodeDetails is None:
			raise EnvironmentError('Unable to pull node details from endpoint.')

		## Get parameters controlling the job
		commandsToTest = runtime.parameters.get('commandList', [])
		commandTimeout = runtime.parameters.get('commandTimeout', 10)

		## Configure shell client
		client = getClient(runtime)
		if client is not None:
			## Open client session before starting the work
			client.open()

			## Run commands
			for command in commandsToTest:
				runtime.logger.warn('Running command: {command!r}', command=command)
				(stdOut, stdError, hitProblem) = client.run(command, commandTimeout)
				if hitProblem:
					runtime.logger.warn(' command encountered a problem')
				else:
					runtime.logger.warn(' command successful')
				runtime.logger.warn('  stdOut: {stdOut!r}', stdOut=stdOut)
				runtime.logger.warn('  stdError: {stdError!r}', stdError=stdError)

			## Update the runtime status to success
			runtime.status(1)

	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end startJob
	return
