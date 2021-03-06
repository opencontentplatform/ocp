"""Merge nodes with same name but empty vs defined domains.

Functions:
  startJob : standard job entry point
  getNodesWithoutDomains : get the first set of nodes (less qualified)
  getNodesWithDomains : get the second set of nodes (more qualified)
  getQueryResults : get query results for the node type
  processResults : loop through weak/strong objects and look for matches
  mergeObjects : issue an API call to merge the weak/strong objects

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Jan 3, 2018
  1.1 : (CS) Changed from calling DB queries directly (when running on server
        via the ServerSideService), to using the API (when running on a client
        via the UniversalJobService). Sep 5, 2019

"""
import sys
import traceback
import re
import os
import json
from contextlib import suppress

## From openContentPlatform
from utilities import getApiQueryResultsFull, getApiResult


def mergeObjects(runtime, weakId, strongId):
	"""Issue an API call to merge the objects."""
	apiResponse = getApiResult(runtime, 'tool/mergeObject', 'post', customPayload={'weakId': weakId, 'strongId': strongId})
	responseCode = None
	responseAsJson = {}
	with suppress(Exception):
		responseCode = apiResponse.status_code
	with suppress(Exception):
		responseAsJson = json.loads(apiResponse.text)
	if responseCode is None or str(responseCode) != '200':
		raise EnvironmentError('Unexpected response from API. Code: {}. Payload: {}'.format(responseCode, responseAsJson))


def processResults(runtime, weakNodes, strongNodes):
	"""Loop through the weak/strong objects and look for matches."""
	## TODO: consider adding the client group to Node created by Identification
	## jobs, which will allow us to compare the weak/strong nodes by the client
	## group. Why? Because maybe the same named server will be found in a DMZ
	## and a Corp segment, but in different DNS zones (i.e. domain names). This
	## job will pick the first server by equal name, regardless of the domain.
	## Even though we may not know the domain, we should know if the same client
	## group created both.
	try:
		## Go through the Nodes with domains and without domains
		for weakName,weakId in weakNodes.items():
			weakNameLower = weakName.lower()
			for (strongName, strongDomain, strongId) in strongNodes:
				strongNameLower = strongName.lower()
				if weakNameLower == strongNameLower:
					runtime.logger.info('Found qualified node with same name as lesser node')
					runtime.logger.info('  qualified node: {strongName!r}, domain: {strongDomain}. id: {strongId!r}.', strongName=strongName, strongDomain=strongDomain, strongId=strongId)
					runtime.logger.info('     lesser node: {weakName!r}. id: {weakId!r}.', weakName=weakName, weakId=weakId)
					mergeObjects(runtime, weakId, strongId)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in processResults: {stacktrace!r}', stacktrace=stacktrace)

	## end processResults
	return


def getQueryResults(runtime, queryName, resultsFormat):
	"""Run a query to get all matching objects."""
	queryFile = os.path.join(runtime.env.universalJobPkgPath, 'strongObjectReference', 'input', queryName + '.json')
	if not os.path.isfile(queryFile):
		raise EnvironmentError('Missing query file specified in the parameters: {queryFile!r}', queryFile=queryFile)
	queryContent = None
	with open(queryFile) as fp:
		queryContent = json.load(fp)
	queryResults = getApiQueryResultsFull(runtime, queryContent, resultsFormat=resultsFormat, verify=runtime.ocpCertFile)

	## end getQueryResults
	return queryResults


def getNodesWithoutDomains(runtime, weakNodes):
	"""Get all nodes from the database with empty domain names."""
	foundWeakNodes = False
	try:
		weakNodesQuery = runtime.parameters.get('weakNodesQuery')
		queryResults = getQueryResults(runtime, weakNodesQuery, 'Flat')
		## Sample data:
		## {
		## 	"data": {
		## 	  "hostname": "HP885C0E"
		## 	},
		## 	"class_name": "Node",
		## 	"identifier": "1af80d8b9b3a46a1a7989ff82ca36b1e",
		## 	"label": "Node"
		##   }
		for result in queryResults.get('objects', []):
			foundWeakNodes = True
			hostname = result['data']['hostname']
			identifier = result['identifier']
			weakNodes[hostname] = identifier
			runtime.logger.report('Found weak Node: {nodeName!r}', nodeName=hostname)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in getNodesWithoutDomains: {stacktrace!r}', stacktrace=stacktrace)

	## end getNodesWithoutDomains
	return foundWeakNodes


def getNodesWithDomains(runtime, strongNodes):
	"""Get all nodes from the database that have associated domains."""
	try:
		strongNodesQuery = runtime.parameters.get('strongNodesQuery')
		queryResults = getQueryResults(runtime, strongNodesQuery, 'Flat')
		for result in queryResults.get('objects', []):
			hostname = result['data']['hostname']
			domain = result['data']['domain']
			identifier = result['identifier']
			strongNodes.append((hostname, domain, identifier))

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in getNodesWithDomains: {stacktrace!r}', stacktrace=stacktrace)

	## end getNodesWithDomains
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		## Get result set 1 (weaker nodes without domains and without ref_id)
		weakNodes = {}
		foundWeakNodes = getNodesWithoutDomains(runtime, weakNodes)
		if foundWeakNodes:
			## Get result set 2 (nodes with domains and without ref_id)
			strongNodes = []
			getNodesWithDomains(runtime, strongNodes)
			## Do the work
			processResults(runtime, weakNodes, strongNodes)
		else:
			## Nothing to do
			runtime.logger.debug("No results found for processing in job {name!r}", name=__name__)

		## Update the runtime status to success
		if runtime.getStatus() == 'UNKNOWN':
			runtime.status(1)

	except:
		runtime.setError(__name__)

	## end startJob
	return
