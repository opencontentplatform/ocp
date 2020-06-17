"""Sample script illustrating how to work from previously discovered content.

Not all software is installed via known software installers; it can be also be
copied to an endpoint. This job specifically looks for Python, but can be built
out to be more flexible. This is another sample for new developers to follow.

This script queries endpoints previously found running python scripts, and asks
for python versions from each runtime location - relative to paths found before.
This finds multiple active versions when applicable, and creates a Software
Package to represent the software.

Results are sent into two different Kafka topics, to illustrate flexibility. The
implicit/default topic will be consumed by this platform to create Software
Package objects in the database, representing the software. The second topic is
used to allow another utility/process/endpoint to consume the information for a
different reason. This illustrates how this platform can be used in an effort
for tool consolidation, removing the need for multiple tools (agent or agent-
less) with multiple accounts, or overhead of running or querying endpoints for
the same or similar data.


Functions:
  startJob : standard job entry point
  checkFiles : worker function to issue a command and check results
  parserFunction : helper function to illustrate the difference with logging


Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Mar 22, 2018

"""
import sys
import traceback
import re
from contextlib import suppress
## From openContentPlatform
from protocolWrapper import getClient
from utilities import addObject, addLink


def setAttribute(attributes, name, value, maxLength=None):
	"""Helper to set attributes only when they are valid values."""
	if (value is not None and value != 'null' and len(value) > 0):
		attributes[name] = value
		if maxLength:
			attributes[name] = value[:maxLength]

	## end setAttribute
	return


def createObjects(runtime, output, processFile, nodeId, ipaddress, hostname, domain):
	"""Grouping two different send methods in this function.

	The first method formats the content as expected for our internal database,
	and either implicitely or explicitely sends it back to the framework. The
	second method formats it in another way and sends it to a different topic
	on the bus (Kafka), to be consumed by a external endpoint.
	"""
	## Create file objects in the format for the CMS to consume; these
	## objects are implicitely sent back after the startJob function returns
	## ===================================================================
	## Map properties from commands into attributes for the CMS object
	attributes = {}
	setAttribute(attributes, 'name', 'Python')
	setAttribute(attributes, 'version', output, 256)
	#setAttribute(attributes, 'recorded_by', 'shell_qualify_python', 256)
	setAttribute(attributes, 'recorded_by', __name__, 256)
	setAttribute(attributes, 'path', processFile, 256)

	## Create the software and link it to the node
	softwareId = addObject(runtime, 'SoftwarePackage', **attributes)
	addLink(runtime, 'Enclosed', nodeId, softwareId)

	## The above results are tracked by the runtime object, and returned
	## after the job finishes. Alternatively, you can explicitely send them
	## back by calling the sendToKafka function without any arguments:
	#runtime.sendToKafka()
	## But if you do that, make sure to put the node object back on for the
	## next SoftwarePackage object to be linked to the node object again:
	#runtime.results.addObject('Node', uniqueId=nodeId)
	## ===================================================================


	## Now send explicitely to a different kafka topic, using any format you
	## wish; illustrating streaming multiple outputs for different consumers
	## ===================================================================
	customFormat = {
		'hostname' : hostname,
		'domain' : domain,
		'ipaddress' : ipaddress,
		'software' : 'Python',
		'version' : output,
		'path' : processFile
	}
	runtime.sendToKafka('security', customFormat)
	## ===================================================================
	## end createObjects


def runCommand(runtime, client, source, command, timeout=None, keepErrorsMatchingString=None):
	"""Wrapper to report errors on shell command execution."""
	output = None
	failed = True
	(rawOutput, stdError, hitProblem) = client.run(command, timeout)

	if hitProblem:
		runtime.logger.warn(' {source!r}: command encountered a problem', source=source)
		runtime.logger.warn('  command output {output!r}', output=rawOutput)
	if keepErrorsMatchingString is not None:
		if stdError is not None and len(stdError.strip()) > 0:
			for tmpString in stdError.split('\n'):
				if re.search(keepErrorsMatchingString, tmpString):
					rawOutput = rawOutput + tmpString
		if (rawOutput is None or len(rawOutput.strip()) <= 0):
			runtime.logger.warn(' {source!r}: no output returned from command: {command!r}', source=source, command=command)
		else:
			output = rawOutput.strip()
			## The failed flag is expecting output; for commands that do not return
			## output, caller should not check this flag (as it will be misleading)
			failed = False
	else:
		if stdError is not None and len(stdError.strip()) > 0:
			runtime.logger.warn(' {source!r}: error: {stdError!r}', source=source, stdError=stdError)
		elif (rawOutput is None or len(rawOutput.strip()) <= 0):
			runtime.logger.warn(' {source!r}: no output returned from command: {command!r}', source=source, command=command)
		else:
			output = rawOutput.strip()
			## The failed flag is expecting output; for commands that do not return
			## output, caller should not check this flag (as it will be misleading)
			failed = False

	## end runCommand
	return (output, failed)


def qualifySoftware(runtime, endpoint, client, nodeId):
	"""Find and qualify the software version from the previous runtime path."""
	runtime.logger.report('qualifySoftware:  endpoint:  {endpoint!r}', endpoint=endpoint)
	endpointNode = endpoint.get('children').get('Node')[0]
	processJson = endpointNode.get('children').get('ProcessFingerprint')
	runtime.logger.report('qualifySoftware:  processJson:  {processJson!r}', processJson=processJson)
	savedPaths = []
	for thisProcess in processJson:
		thisData = thisProcess.get('data', {})
		process = thisData.get('name')
		runtime.logger.report('Attempting to qualify process {process!r}', process=process)
		path_from_process = thisData.get('path_from_process')
		path_from_filesystem = thisData.get('path_from_filesystem')
		path_from_analysis = thisData.get('path_from_analysis')
		orderedList = [path_from_analysis, path_from_filesystem, path_from_process]
		processFile = None
		for item in orderedList:
			if item is None or item == 'N/A':
				continue
			processFile = item
			break
		if processFile is None:
			continue
		runtime.logger.report('  with path {processFile!r}', processFile=processFile)
		if processFile in savedPaths:
			runtime.logger.report('... already processed this location: {processFile!r}', processFile=processFile)
			continue
		savedPaths.append(processFile)

		shellType = endpoint.get('data').get('object_type')
		command1 = 'Invoke-Expression \'& "{}" -VV\''.format(processFile)
		command2 = 'Invoke-Expression \'& "{}" -V\''.format(processFile)
		if shellType == 'ssh':
			command1 = '{} -VV'.format(processFile)
			command2 = '{} -V'.format(processFile)

		(output, failed) = runCommand(runtime, client, 'qualifySoftware', command1, 5, '^Python ')
		if failed:
			## Fall back to the standard version
			(output, failed) = runCommand(runtime, client, 'qualifySoftware', command2, 5, '^Python ')

		## Create file objects in the format for the CMS to consume; these
		## objects are implicitely sent back after the startJob function returns
		runtime.logger.report('Python version: {output!r}', output=output)
		if not failed:
			createObjects(runtime, output, processFile, nodeId,
						  endpoint.get('data').get('ipaddress'),
						  endpointNode.get('data', {}).get('hostname'),
						  endpointNode.get('data', {}).get('domain'))

	## end qualifySoftware
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	client = None
	try:
		## Configure shell client
		client = getClient(runtime)
		if client is not None:
			## Get a handle on our Node in order to link objects in this job
			nodeId = runtime.endpoint.get('data').get('container')
			runtime.results.addObject('Node', uniqueId=nodeId)

			## Open client session before starting the work
			client.open()

			## Do the work
			qualifySoftware(runtime, runtime.endpoint, client, nodeId)

			## Good house keeping; though I force this after the exception below
			client.close()

			## Update the runtime status to success
			if runtime.getStatus() == 'UNKNOWN':
				runtime.status(1)

			## Debug output
			runtime.logger.report('results: {results!r}\n\n', results=runtime.results.getJson())

	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end startJob
	return
