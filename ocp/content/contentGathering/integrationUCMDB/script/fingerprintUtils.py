"""Utilities shared by the UCMDB integration send scripts.

Functions:
  transformFingerprint : transform fingerprint into expected UCMDB structure
  transformNode : transform node into expected UCMDB structure
  sendDataSet : send results and reset data structure after processing each node
  getCredentialMatchingDescriptor : wrapper to get un-managed credential type

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Jan 14, 2019

"""
import sys
import traceback
import re

## From openContentPlatform
from ucmdbRestAPI import UcmdbRestAPI

## Global mappings
objectMapping = {
	'node': {
		'Node': 'node',
		'NodeServer': 'host_node',
		'Windows': 'nt',
		'Linux': 'unix',
		'HPUX': 'unix',
		'Solaris': 'unix',
		'AIX': 'unix'
	},
	'fingerprint': {
		'ProcessFingerprint': 'process_fingerprint',
		'SoftwareFingerprint': 'software_fingerprint'
	},
	'ip': 'ip_address',
	'port': 'ip_service_endpoint'
}
attributeMapping = {
	'ProcessFingerprint': {
		'name': 'name',
		'process_owner': 'process_owner',
		'path_from_process': 'path_from_process',
		'path_from_filesystem': 'path_from_filesystem',
		'path_from_analysis': 'path_from_analysis',
		'process_hierarchy': 'process_hierarchy',
		'path_working_dir': 'path_working_dir',
		'process_args': 'process_args'
	},
	'SoftwareFingerprint': {
		'name': 'name',
		'software_version': 'software_version',
		'software_info': 'software_info',
		'software_id': 'software_id',
		'software_source': 'software_source'
	}
}


def transformFingerprint(runtime, result, data, containerId):
	"""Transform Process/Software Fingerprint into expected UCMDB structure."""
	fingerprintId = None
	try:
		objectId = result.get('identifier')
		objectClass = result.get('class_name')
		## Transform from ITDM class to UCMDB class, without a default
		thisType = objectMapping['fingerprint'][objectClass]
		objectData = result.get('data')
		## Map attributes
		thisProps = {}
		thisProps['root_container'] = containerId
		mapping = attributeMapping[objectClass]
		for prop,thisProp in mapping.items():
			value = objectData.get(prop)
			#value = objectData.get(prop, 'NA')
			thisProps[thisProp] = value
		fingerprintId = data.addObject(thisType, **thisProps)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in transformFingerprint: {stacktrace!r}', stacktrace=stacktrace)

	## end transformFingerprint
	return fingerprintId


def transformNode(runtime, result, data):
	"""Transform a Node into expected UCMDB structure."""
	nodeId = None
	nodeProps = {}
	nodeType = None
	try:
		objectId = result.get('identifier')
		objectClass = result.get('class_name')
		## Transform from ITDM class to UCMDB class, and default to node
		nodeType = objectMapping.get('node').get(objectClass, 'node')
		objectData = result.get('data')
		hostname = objectData.get('hostname')
		if hostname is not None:
			runtime.logger.report('Looking at hostname {hostname!r}', hostname=hostname)
			domain = objectData.get('domain')
			nodeProps['name'] = hostname
			if domain is not None and domain.lower() != 'workgroup':
				nodeProps['primary_dns_name'] = '{}.{}'.format(hostname, domain)
			nodeId = data.addObject(nodeType, **nodeProps)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in transformNode: {stacktrace!r}', stacktrace=stacktrace)

	## end transformNode
	return (nodeId, nodeType, nodeProps)


def transformIpAddress(runtime, ipAddress, data):
	"""Transform an IP into expected UCMDB structure."""
	ipId = None
	try:
		## Get the corresponding UCMDB class
		thisType = objectMapping['ip']
		## statically map attributes
		thisProps = {}
		thisProps['routing_domain'] = '${DefaultDomain}'
		thisProps['name'] = ipAddress
		ipId = data.addObject(thisType, **thisProps)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in transformIpAddress: {stacktrace!r}', stacktrace=stacktrace)

	## end transformIpAddress
	return ipId


def transformTcpIpPort(runtime, result, data):
	"""Transform a TCP/IP port into expected UCMDB structure."""
	portId = None
	try:
		objectId = result.get('identifier')
		objectClass = result.get('class_name')
		## Get the corresponding UCMDB class
		thisType = objectMapping['port']
		objectData = result.get('data')
		## Statically map attributes
		thisProps = {}
		thisProps['bound_to_ip_address'] = objectData.get('ip')
		thisProps['network_port_number'] = objectData.get('port')
		#thisProps['port_type'] = 'tcp'
		thisProps['port_type'] = objectData.get('port_type')
		#thisProps['name'] = objectData.get('name')

		## Create the IP first
		ipId = transformIpAddress(runtime, objectData.get('ip'), data)
		thisProps['root_container'] = ipId
		## Now create the Port
		portId = data.addObject(thisType, **thisProps)
		## And link it to the IP
		data.addLink('composition', ipId, portId)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in transformTcpIpPort: {stacktrace!r}', stacktrace=stacktrace)

	## end transformTcpIpPort
	return portId


def sendDataSet(runtime, ucmdbService, data):
	"""Send results and reset the data structure after processing each node."""
	runtime.logger.report('Data set size: {size!r}', size=data.size())
	stringResult = data.stringify()
	runtime.logger.report('Sending data: {data!r}', data=stringResult)
	ucmdbService.insertTopology(stringResult)
	data.reset()

	## end sendDataSet
	return


def getCredentialMatchingDescriptor(runtime):
	"""Simple wrapper to get un-managed credential type (REST API here).

	Note, since this is for a REST endpoint, this data isn't encrypted as it is
	for the standard managed/wrapped types.  We we actually have to supply the
	credentials in the connection attempt.
	"""
	## Read/initialize the job parameters
	ucmdbRestEndpoint = runtime.parameters.get('ucmdbRestEndpoint')
	descriptor = runtime.parameters.get('credentialDescriptor', 'UCMDB')
	protocolType = 'ProtocolRestApi'

	for protocolReference,entry in runtime.protocols.items():
		runtime.logger.report('getCredentialMatchingDescriptor: looking at protocol: {entry!r}',entry=entry)
		if (entry.get('protocolType', '').lower() == protocolType.lower()):
			runtime.logger.report('getCredentialMatchingDescriptor: found matching protocol type')
			protocolReference = entry.get('protocol_reference')
			endpointDescription = entry.get('description', '')
			runtime.logger.report('getCredentialMatchingDescriptor: using descriptor {descriptor!r} with description {endpointDescription!r}', descriptor=descriptor, endpointDescription=endpointDescription)
			if re.search(descriptor, endpointDescription, re.I):
				## Since this is for a REST endpoint, this data isn't encrypted;
				## we actually have to supply it during the connection attempt.
				runtime.logger.report(' getCredentialMatchingDescriptor: protocol type {protocolType!r} with reference {protocolReference!r}: {entry!r}', protocolType=protocolType, protocolReference=protocolReference, entry=entry)
				user = entry.get('user')
				notthat = entry.get('password')
				if user is None:
					continue
				ucmdbService = UcmdbRestAPI(runtime, ucmdbRestEndpoint, user, notthat)
				if ucmdbService.connected:
					return ucmdbService
				runtime.logger.report('Failed to connect to UCMDB REST API with user {user!r}', user=user)

	## end getCredentialMatchingDescriptor
	return None
