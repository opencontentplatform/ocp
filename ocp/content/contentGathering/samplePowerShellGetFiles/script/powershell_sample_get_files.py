"""Sample script illustrating how to add related content to a node.

This script queries target endpoints for a list of files specified in the job's
input parameters. For each entry, if the file exists then it pulls specified
attributes and requests an MD5 hash. Those attributes are dropped on an object


Functions:
  startJob : standard job entry point
  checkFiles : worker function to issue a command and check results
  parserFunction : helper function to illustrate the difference with logging

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  0.1 : (CS) Created Oct 9, 2017
  1.0 : (CS) Retrofitted library calls and added lots of comments; intended to
        enable folks planning to create new content.  Aug 1, 2018

"""
import re
import sys
import traceback
from contextlib import suppress

## From openContentPlatform
from protocolWrapper import getClient
from utilities import addObject, addLink


def setAttribute(source, sourceKey, destination, destinationKey):
	"""Transform file property to database column.

	Arguments:
	  source (dict)      : dictionary with key:value pairs from command output
	  sourceKey (string) : name of key in the source dictionary
	  destination (dict) : dictionary with key:value pairs for database table
	  destinationKey (string) : name of key in the destination dictionary
	"""
	value = source.get(sourceKey)
	if value is not None:
		destination[destinationKey] = value


def createObject(runtime, nodeId, properties):
	"""Create the file object and link it to the node.

	Arguments:
	  runtime (dict)     : used for providing input into jobs and tracking
	                       the job thread through the life of its runtime
	  nodeId (string)    : 'object_id' of the Node that our client is connected
	                       to; not used here... just stubbed for common practice
	  properties (dict)  : dictionary with key:value pairs from command output
	"""
	try:
		attributes = {}
		setAttribute(properties, 'Name', attributes, 'name')
		setAttribute(properties, 'FullName', attributes, 'path')
		setAttribute(properties, 'Extension', attributes, 'extension')
		## In production scenario, convert string dates to datetime type before
		setAttribute(properties, 'CreationTime', attributes, 'file_created')
		setAttribute(properties, 'LastWriteTime', attributes, 'file_modified')
		setAttribute(properties, 'Hash', attributes, 'md5hash')

		## Create the file
		fileId, exists = addObject(runtime, 'FileCustom', **attributes)
		## Link it to the node
		addLink(runtime, 'Enclosed', nodeId, fileId)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error(' Failure in createObject: {stacktrace!r}', stacktrace=stacktrace)

	## end createObject
	return


def parserFunction(runtime, outputString, properties):
	"""Update dictionary with PowerShell's Format-List output of key:value pairs.

	Arguments:
	  runtime (dict)     : used for providing input into jobs and tracking
	                       the job thread through the life of its runtime
	  outputString (str) : string object evaluated in this function
	  properties (dict)  : output dictionary with key:value updated pairs
	"""
	try:
		## Sample output of Format-List coming from Get-ItemProperty
		## =====================================================================
		##   FullName      : E:\Work\openContentPlatform\framework\openContentPlatform.py
		##   Name          : openContentPlatform.py
		##   Extension     : .py
		##   CreationTime  : 8/23/2017 8:29:36 AM
		##   LastWriteTime : 9/3/2018 8:48:59 AM
		## =====================================================================
		for line in outputString.split('\n'):
			line = line.strip()
			m = re.search('^([^:]+):(.*)', line)
			if m:
				key = m.group(1).strip()
				value = m.group(2).strip()
				properties[key] = value

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error(' Failure in parserFunction: {stacktrace!r}', stacktrace=stacktrace)

	## end parserFunction
	return


def checkFiles(runtime, client, nodeId):
	"""Retrieves properties and MD5 hash on a set of files defined by the job.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	  client (shell)   : instance of the shell wrapper
	  nodeId (string)  : 'object_id' of the Node that our client is connected
	                     to; not used here... just stubbed for common practice
	"""
	try:
		filesToCheck = runtime.parameters.get('filesToCheck', [])
		nodeCreated = False
		for fileWithPath in filesToCheck:
			## Can't check and test in the same command since it would yield an
			## empty pipe sent to out-string, causing an error. So check first.
			#command = 'if (Test-Path "' + fileWithPath + '") { Get-ItemProperty -Path "' + fileWithPath + '" | Format-list -Property FullName,Name,Extension,CreationTime,LastWriteTime }'

			## See if the file exists
			command = 'Test-Path "{}"'.format(fileWithPath)
			runtime.logger.report(' --> command: {command!r}', command=command)
			(outputString, stderr, hitProblem) = client.run(command)
			if outputString != 'True':
				continue

			## Get desired properties of a file, if the file exists
			command = 'Get-ItemProperty -Path "{}" | Format-list -Property FullName,Name,Extension,CreationTime,LastWriteTime'.format(fileWithPath)
			runtime.logger.report(' --> command: {command!r}', command=command)
			(outputString, stderr, hitProblem) = client.run(command, 3)

			## If we hit an error, raise an exception and set error status
			if (hitProblem):
				raise OSError('Command failed {}. Error returned {}'.format(command, stderr))

			## If we get here, we found a file and have properties to parse
			properties = {}
			parserFunction(runtime, outputString, properties)

			## Get the md5sum as well
			command = 'Get-FileHash "{}" -Algorithm MD5 | Format-list -Property Hash'.format(fileWithPath)
			(outputString, stderr, hitProblem) = client.run(command)
			if (not hitProblem and outputString is not None and len(outputString) > 0):
				parserFunction(runtime, outputString, properties)

			## Only add the node once
			if not nodeCreated:
				runtime.results.addObject('Node', uniqueId=nodeId)
				nodeCreated = True

			## Create this file object
			createObject(runtime, nodeId, properties)
			runtime.logger.report(' --> added file {fileWithPath!r}', fileWithPath=fileWithPath)

	except:
		runtime.setError(__name__)

	## end checkFiles
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	client = None
	try:
		## Drop our input parameters into the log
		for inputParameter in runtime.parameters:
			runtime.logger.report(' --> input parameter {name!r}: {value!r}', name=inputParameter, value=runtime.parameters.get(inputParameter))

		## Configure shell client
		client = getClient(runtime)
		if client is not None:
			## Our client is configured and ready to use, but we won't establish
			## an actual connection until needed

			## Get a handle on our Node in order to attach files.
			nodeId = runtime.endpoint.get('data').get('container')

			## Open client session before starting the work
			client.open()

			## Now we do something; this just calls a function above
			checkFiles(runtime, client, nodeId)

			## Good house keeping; though I force this after the exception below
			client.close()

			## Update the runtime status to success, for job tracking and proper
			## statistics. You don't want jobs to list UNKNOWN if you know they
			## either passed or failed. Likewise, you may not want to leave them
			## tagged with FAILED if some of the previous failures can be safely
			## disregarded upon a final success criteria.
			if runtime.getStatus() == 'UNKNOWN':
				runtime.status(1)

	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end startJob
	return
