"""Utilities shared by the ServiceNow integration send scripts.

Functions:
  transformFingerprint : transform fingerprint into expected ServiceNow structure
  transformNode : transform node into expected ServiceNow structure
  sendDataSet : send results and reset data structure after processing each node
  getCredentialMatchingDescriptor : wrapper to get un-managed credential type

If this is built on, we should generalize and wrap the transformations.

"""
import sys
import traceback
import re

## From openContentPlatform
from snowRestAPI import SnowRestAPI

## Global mappings
objectMapping = {
	'node': {
		'Node': 'cmdb_ci_hardware',
		'NodeServer': 'cmdb_ci_computer',
		'Windows': 'cmdb_ci_win_server',
		'Linux': 'cmdb_ci_linux_server',
		'HPUX': 'cmdb_ci_hpux_server',
		'Solaris': 'cmdb_ci_solaris_server',
		'AIX': 'cmdb_ci_aix_server'
	},
	'fingerprint': {
		'ProcessFingerprint': 'u_cmdb_ci_itdm_process_fingerprint',
		'SoftwareFingerprint': 'u_cmdb_ci_itdm_software_fingerprint'
	}
}
attributeMapping = {
	'Node': {
		'hostname': 'name',
		'platform': 'short_description',
		'version': 'os_version'
	},
	'ProcessFingerprint': {
		'name': 'name',
		'process_owner': 'u_process_owner',
		'path_from_process': 'u_path_from_process',
		'path_from_filesystem': 'u_path_from_filesystem',
		'path_from_analysis': 'u_path_from_analysis',
		'process_hierarchy': 'u_process_hierarchy',
		'path_working_dir': 'u_path_working_dir',
		'process_args': 'u_process_args'
	},
	'SoftwareFingerprint': {
		'name': 'name',
		'software_version': 'u_software_version',
		'software_info': 'u_software_info',
		'software_id': 'u_software_id',
		'software_source': 'u_software_source'
	}
}


def transformFingerprint(runtime, result, data):
	"""Transform Process/Software Fingerprint into expected ServiceNow structure.

	ITDM structure:
	{
	  "data": {
		"name": "postgres.exe",
		"process_owner": "NETWORK SERVICE",
		"process_hierarchy": "pg_ctl.exe, postgres.exe, postgres.exe",
		"path_from_process": "D:\\Software\\PostgreSQL\\11\\bin\\postgres.exe",
		"path_from_analysis": "D:\\Software\\PostgreSQL\\11\\bin\\postgres.exe"
	  },
	  "class_name": "ProcessFingerprint",
	  "identifier": "f7752059ec7f451599cf9c6600314982",
	  "label": "Process",
	}

	becomes ServiceNow structure:
	{
		"className": "u_cmdb_ci_itdm_process_fingerprint",
		"values": {
			"name": "postgres.exe",
			"u_process_hierarchy": "pg_ctl.exe, postgres.exe, postgres.exe",
			"u_process_owner": "NETWORK SERVICE",
			"u_path_from_process": ""D:\\Software\\PostgreSQL\\11\\bin\\postgres.exe",
			"u_path_from_analysis": ""D:\\Software\\PostgreSQL\\11\\bin\\postgres.exe",
		}
	}
	"""
	fingerprintId = None
	try:
		objectId = result.get('identifier')
		objectClass = result.get('class_name')
		## Transform from ITDM class to ServiceNow class, without a default
		thisType = objectMapping['fingerprint'][objectClass]
		objectData = result.get('data')
		## Map attributes
		thisProps = {}
		mapping = attributeMapping[objectClass]
		for sourceProp,targetProp in mapping.items():
			#value = objectData.get(sourceProp)
			value = objectData.get(sourceProp, 'None')
			if value is None:
				## in case we are looking at null; force to string to avoid dups
				## created on the ServiceNow side, due to database dialect
				value = 'None'
			thisProps[targetProp] = value
		fingerprintId = data.addObject(thisType, **thisProps)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in transformFingerprint: {stacktrace!r}', stacktrace=stacktrace)

	## end transformFingerprint
	return fingerprintId


def transformNode(runtime, result, data):
	"""Transform a Node into expected ServiceNow structure.

	ITDM structure:
	{
		"data": {
		  "hostname": "JACOB",
		  "domain": "WORKGROUP",
		  "platform": "Microsoft Windows Server 2012 R2 Standard",
		  "version": "6.3.9600"
		},
		"class_name": "Windows",
		"identifier": "180d52a5c8c44dc1bae658196737d8fd",
		"label": "Node"
	}

	becomes ServiceNow structure:
	{
		"className": "cmdb_ci_win_server",
		"values": {
			"name": "JACOB",
			"os_domain": "WORKGROUP",
			"short_description" : "Microsoft Windows Server 2012 R2 Standard",
			"os_version": "6.3.9600"
		}
	}
	"""
	nodeId = None
	nodeProps = {}
	nodeType = None
	try:
		objectId = result.get('identifier')
		objectClass = result.get('class_name')
		## Transform from ITDM class to ServiceNow class, and default to node
		nodeType = objectMapping.get('node').get(objectClass)
		objectData = result.get('data')
		hostname = objectData.get('hostname')
		if hostname is not None:
			runtime.logger.report('Looking at hostname {hostname!r}', hostname=hostname)
			mapping = attributeMapping['Node']
			#nodeProps['name'] = hostname
			for sourceProp,targetProp in mapping.items():
				value = objectData.get(sourceProp)
				#value = objectData.get(sourceProp, 'None')
				nodeProps[targetProp] = value

			domain = objectData.get('domain')
			if domain is not None:
				if domain.lower() == 'workgroup':
					## dropping WORKGROUP into the os_domain field
					nodeProps['os_domain'] = domain
				else:
					## dropping into the dns_domain field
					nodeProps['dns_domain'] = domain

			data.addObject(nodeType, **nodeProps)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in transformNode: {stacktrace!r}', stacktrace=stacktrace)

	## end transformNode
	return


def sendNodeAndGetIdentifier(runtime, snowService, data):
	"""Send a single node and get the sys_id to use for related inserts.

	Sample ServiceNow output from Madrid version:
	{
	  "result": {
		"items": [
		  {
			"className": "cmdb_ci_win_server",
			"operation": "NO_CHANGE",
			"sysId": "81d55793db62330060e17b603996194f",
			"identifierEntrySysId": "556eb250c3400200d8d4bea192d3ae92",
			"identificationAttempts": [
			  {
				"identifierName": "Hardware Rule",
				"attemptResult": "SKIPPED",
				"attributes": [
				  "serial_number",
				  "serial_number_type"
				],
				"hybridEntryCiAttributes": [],
				"searchOnTable": "cmdb_serial_number"
			  },
			  {
				"identifierName": "Hardware Rule",
				"attemptResult": "SKIPPED",
				"attributes": [
				  "serial_number"
				],
				"hybridEntryCiAttributes": [],
				"searchOnTable": "cmdb_ci_hardware"
			  },
			  {
				"identifierName": "Hardware Rule",
				"attemptResult": "MATCHED",
				"attributes": [
				  "name"
				],
				"hybridEntryCiAttributes": [],
				"searchOnTable": "cmdb_ci_hardware"
			  }
			]
		  }
		],
		"relations": []
	  }
	}

	"""
	data.finalize()
	stringResult = data.stringify()
	runtime.logger.report('sendNodeAndGetIdentifier: Sending data: {data!r}', data=stringResult)
	responseAsJson = snowService.insertTopology(stringResult)
	data.reset()

	className = responseAsJson.get('result', {}).get('items')[0]['className']
	## Don't use a safe 'get' on this... let the exception raise if not found:
	#sysId = responseAsJson.get('result', {}).get('items')[0].get('sysId')
	sysId = responseAsJson.get('result', {}).get('items')[0]['sysId']
	if sysId is None:
		raise EnvironmentError('ServiceNow did not return a sysId for node: {}'.format(data))

	## end sendNodeAndGetIdentifier
	return (className, sysId)


def sendDataSet(runtime, snowService, data):
	"""Send results and reset the data structure after processing each node."""
	runtime.logger.report('Data set size: {size!r}', size=data.size())
	data.finalize()
	stringResult = data.stringify()
	runtime.logger.report('sendDataSet: Sending data: {data!r}', data=stringResult)
	snowService.insertTopology(stringResult)
	data.reset()

	## end sendDataSet
	return


def getUserContextMatchingDescriptor(runtime, restEndpoint, userDescriptor):
	"""Simple wrapper to get un-managed credential type (REST API here).

	Note, since this is for a REST endpoint, this data isn't encrypted as it is
	for the standard managed/wrapped types; we have to supply the credentials
	to the request library for a RESTful connection attempt.
	"""
	## Read/initialize the job parameters
	protocolType = 'ProtocolRestApi'
	userContext = None
	for protocolReference,entry in runtime.protocols.items():
		runtime.logger.report('getUserContextMatchingDescriptor: looking at protocol: {entry!r}',entry=entry)
		if (entry.get('protocolType', '').lower() == protocolType.lower()):
			runtime.logger.report('getUserContextMatchingDescriptor: found matching protocol type')
			protocolReference = entry.get('protocol_reference')
			endpointDescription = entry.get('description', '')
			runtime.logger.report('getUserContextMatchingDescriptor: using descriptor {descriptor!r} with description {endpointDescription!r}', descriptor=userDescriptor, endpointDescription=endpointDescription)
			if re.search(userDescriptor, endpointDescription, re.I):
				## Since this is for a REST endpoint, this data isn't encrypted;
				## we actually have to supply it during the connection attempt.
				runtime.logger.report(' getUserContextMatchingDescriptor: protocol type {protocolType!r} with reference {protocolReference!r}: {entry!r}', protocolType=protocolType, protocolReference=protocolReference, entry=entry)
				user = entry.get('user')
				notthat = entry.get('password')
				clientId = entry.get('client_id')
				clientSecret = entry.get('client_secret')
				if (user is None) or (notthat is None) or (clientId is None) or (clientSecret is None):
					continue

				## Need to verify credential and validate Class Setup
				snowService = SnowRestAPI(runtime, restEndpoint, user, notthat, clientId, clientSecret)
				if snowService.connected:
					## Ensure the required tables exist before trying to populate them
					snowService.validateServiceNowClassSetup()
					## No longer need this; threads will create their own handle
					del snowService
					## Everything good; use this user context for the threads
					userContext = (user, notthat, clientId, clientSecret)
					break
				runtime.logger.report('Unable to connect to ServiceNow REST API with user {user!r}', user=user)

	## end getUserContextMatchingDescriptor
	return userContext
