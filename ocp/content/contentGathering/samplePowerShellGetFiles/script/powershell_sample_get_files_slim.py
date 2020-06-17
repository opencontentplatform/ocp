import re
import sys
import traceback
from contextlib import suppress
from protocolWrapper import getClient
from utilities import addObject, addLink

def setAttribute(source, sourceKey, destination, destinationKey):
	value = source.get(sourceKey)
	if value is not None:
		destination[destinationKey] = value

def createObject(runtime, nodeId, properties):
	attributes = {}
	setAttribute(properties, 'Name', attributes, 'name')
	setAttribute(properties, 'FullName', attributes, 'path')
	setAttribute(properties, 'Extension', attributes, 'extension')
	setAttribute(properties, 'CreationTime', attributes, 'file_created')
	setAttribute(properties, 'LastWriteTime', attributes, 'file_modified')
	setAttribute(properties, 'Hash', attributes, 'md5hash')
	## Create files and link to the node
	fileId = addObject(runtime, 'FileCustom', **attributes)
	addLink(runtime, 'Enclosed', nodeId, fileId)

def parserFunction(runtime, outputString, properties):
	for line in outputString.split('\n'):
		line = line.strip()
		m = re.search('^([^:]+):(.*)', line)
		if m:
			key = m.group(1).strip()
			value = m.group(2).strip()
			properties[key] = value

def checkFiles(runtime, client, nodeId):
	try:
		filesToCheck = runtime.parameters.get('filesToCheck', [])
		runtime.results.addObject('Node', uniqueId=nodeId)
		for fileWithPath in filesToCheck:
			command = 'Test-Path "{}"'.format(fileWithPath)
			(outputString, stderr, hitProblem) = client.run(command)
			if outputString != 'True':
				continue
			command = 'Get-ItemProperty -Path "{}" | Format-list -Property FullName,Name,Extension,CreationTime,LastWriteTime'.format(fileWithPath)
			(outputString, stderr, hitProblem) = client.run(command, 3)
			if (hitProblem):
				raise OSError('Command failed {}. Error returned {}'.format(command, stderr))
			properties = {}
			parserFunction(runtime, outputString, properties)
			command = 'Get-FileHash "{}" -Algorithm MD5 | Format-list -Property Hash'.format(fileWithPath)
			(outputString, stderr, hitProblem) = client.run(command)
			if (not hitProblem and outputString is not None and len(outputString) > 0):
				parserFunction(runtime, outputString, properties)

			## Create this file object
			createObject(runtime, nodeId, properties)
			runtime.logger.report(' --> added file {fileWithPath!r}', fileWithPath=fileWithPath)
	except:
		runtime.setError(__name__)

def startJob(runtime):
	client = None
	try:
		endpointContext = runtime.endpoint.get('data')
		osType = endpointContext.get('node_type')
		nodeId = endpointContext.get('container')
		connectViaFQDN = endpointContext.get('parameters').get('connectViaFQDN', False)
		client = getClient(runtime)
		if client is not None:
			client.open()
			checkFiles(runtime, client, nodeId)
			client.close()
	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()
