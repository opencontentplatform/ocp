"""Wrapper for managed client connections.

The intent is to protect the actual library methods used when interacting with
the clients. While I'm not sure exactly what this entails right now, I'm adding
a level of obfuscation for that work in the future.

Functions:
  |  getClient : simple wrapper to instantiate managed client types
  |  getFQDN : construct a fully qualified domain name for a connection

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  0.1 : (CS) Created Jan 4, 2018
	  1.0 : (CS) Updated for current protocol types, Oct 17, 2018

"""
import sys
import traceback
import platform
import socket
from contextlib import suppress

## External lib for protocol handling
from utils import loadExternalLibrary
externalProtocolHandler = loadExternalLibrary('externalProtocolHandler')

## Local shell/terminal wrappers
from protocolWrapperPowerShellLocal import PowerShellLocal
from protocolWrapperCmdLocal import CmdLocal
from protocolWrapperPwshLocal import PwshLocal

## Remote shell/terminal wrappers
from protocolWrapperSnmp import Snmp
from protocolWrapperSSH import SSH
from protocolWrapperPowerShell import PowerShell

## Remote SQL database adapter wrappers
from protocolWrapperSqlPostgres import SqlPostgres
# from protocolWrapperSqlOracle import SqlOracle
# from protocolWrapperSqlIbmDb2 import SqlIbmDb2
# from protocolWrapperSqlMicrosoft import SqlMicrosoft
# from protocolWrapperSqlMariaDb import SqlMariaDb
# from protocolWrapperSqlMySql import SqlMySql

## The Pymi wmi module is not supported on Linux, and went through a build
## change that made it unavailable for several Python builds. So don't assume
## it's there; check for it and handle appropriately...
try:
	import mi
	from protocolWrapperWmi import Wmi
except ImportError:
	## The first print will hit the master log at startup only
	print('PyMi module not found (for WMI support). Not currently supported on Linux or on some newer Python versions. See here for details: https://github.com/cloudbase/PyMI')
	## This stubbed function handles calls from active jobs
	def Wmi(logger, endpoint, three, four, **kwargs):
		## This message is for the local client's job level (if monitored)
		logger.error('Trying to use WMI, but the PyMi module is not installed. PyMi is not supported on Linux or on some newer Python versions; see here for details: https://github.com/cloudbase/PyMI.  Endpoint: {endpoint!r}', endpoint=endpoint)
		## This EnvironmentError will reflect in the returned job status.
		raise EnvironmentError('Trying to use WMI, but the PyMi module is not installed. PyMi is not supported on Linux or on some newer Python versions; see here for details: https://github.com/cloudbase/PyMI.')


## Globals for ease of update
remoteProtocolTypes = ['protocolsnmp', 'protocolwmi', 'protocolssh',
					   'protocolpowershell', 'protocolsqlpostgres',
					   'protocolsqloracle', 'protocolsqldb2',
					   'protocolsqlmicrosoft', 'protocolsqlmaria',
					   'protocolsqlmy']
clientToProtocolTable = {'snmp': 'protocolsnmp',
						 'wmi': 'protocolwmi',
						 'ssh': 'protocolssh',
						 'powershell': 'protocolpowershell',
						 'postgres': 'protocolsqlpostgres',
						 'oracle': 'protocolsqloracle',
						 'sqlserver': 'protocolsqlmicrosoft',
						 'mariadb': 'protocolsqlmaria',
						 'mysql': 'protocolsqlmy',
						 'db2': 'protocolsqldb2'}
localProtocolTypes = {'powershell': PowerShellLocal,
					  'cmd': CmdLocal,
					  'pwsh': PwshLocal}


def getClient(runtime, **kwargs):
	"""Simple wrapper to instantiate managed client types.

	Note, you can generate new protocols without requiring them to flow through
	security wrappers like this (e.g. when you need to make an API call and the
	credentials/tokens/etc need extracted and manipulated in a script).
	"""
	## Get endpoint context
	endpoint = runtime.endpoint
	clientType = endpoint.get('class_name')
	protocolType = clientToProtocolTable.get(clientType.lower())
	endpointContext = endpoint.get('data', endpoint)
	protocolReference = endpointContext.get('protocol_reference')
	endpointString = endpointContext.get('endpoint')
	if endpointString is None:
		endpointString = endpointContext.get('ipaddress')
	runtime.logger.report(' getClient: endpoint {endpointString!r} protocol type {protocolType!r} with reference {protocolReference!r}', endpointString=endpointString, protocolType=protocolType, protocolReference=protocolReference)
	client = thisClient(runtime, endpointString, protocolReference, protocolType, None, **kwargs)
	if client is None:
		raise EnvironmentError('Unable to establish connection to endpoint')

	## end getClient
	return client


def findClients(runtime, protocolType, **kwargs):
	"""Test client connections until finding a protocol entry that works."""
	connectViaFQDN = runtime.parameters.get('connectViaFQDN', False)
	## Target endpoint could be one of these:
	##   runtime.endpoint.data.ipaddress (found in protocol instances)
	##   runtime.endpoint.data.address (found in IpAddress instances)
	endpointSection = runtime.endpoint.get('data', runtime.endpoint)
	endpointString = endpointSection.get('ipaddress')
	if endpointString is None:
		endpointString = endpointSection.get('address')
	if endpointString is None:
		raise EnvironmentError('endpoint not found in runtime context')
	protocolDict = externalProtocolHandler.getProtocolObjects(runtime)

	runtime.logger.report('findClients: protocol length: {tl}. protocols {protocolDict!r}', tl=len(protocolDict), protocolDict=protocolDict)
	if len(protocolDict) <= 0:
		runtime.logger.warn('Job wants to use protocol {protocolType!r}, but there are no defined credentials for that protocol!', protocolType=protocolType)
	for protocolReference in protocolDict:
		## May want to add in something that checks for protocol types in case
		## folks want to send more than one type to a single job; this either
		## needs checked inside where the protocol is opened up (external lib),
		## or format the protocols section by protocol type, in the service.
		#if entry.get('protocolType', '').lower() == protocolType.lower():
		client = thisClient(runtime, endpointString, protocolReference, protocolType.lower(), connectViaFQDN, **kwargs)
		yield client


def thisClient(runtime, endpointString, protocolReference, protocolType, connectViaFQDN, **kwargs):
	client = None
	if protocolType not in remoteProtocolTypes:
		raise NotImplementedError('Client type not wrapped: {}'.format(protocolType))
	## Get protocol to use in the connection attempt
	protocolEntry = externalProtocolHandler.getProtocolObject(runtime, protocolReference)
	runtime.logger.report('thisClient: trying endpoint {endpoint!r} with protocol reference {protocolReference!r}', endpoint=endpointString, protocolReference=protocolReference)
	endpointString = getFQDN(runtime, endpointString, connectViaFQDN)
	
	## SNMP
	if protocolType == 'protocolsnmp':
		client = Snmp(runtime, runtime.logger, endpointString, protocolReference, protocolEntry)
	## WMI
	elif protocolType == 'protocolwmi':
		client = Wmi(runtime, runtime.logger, endpointString, protocolReference, protocolEntry, **kwargs)
	## PowerShell
	elif protocolType == 'protocolpowershell':
		client = PowerShell(runtime, runtime.logger, endpointString, protocolReference, protocolEntry, **kwargs)
	## SSH
	elif protocolType == 'protocolssh':
		client = SSH(runtime, runtime.logger, endpointString, protocolReference, protocolEntry, **kwargs)

	## SQL types
	elif protocolType == 'protocolsqlpostgres':
		client = SqlPostgres(runtime, runtime.logger, endpointString, protocolReference, protocolEntry, **kwargs)
	# elif protocolType == 'protocolsqloracle':
	# 	client = SqlOracle(runtime, runtime.logger, endpointString, protocolReference, protocolEntry, **kwargs)
	# elif protocolType == 'protocolsqldb2':
	# 	client = SqlIbmDb2(runtime, runtime.logger, endpointString, protocolReference, protocolEntry, **kwargs)
	# elif protocolType == 'protocolsqlmicrosoft':
	# 	client = SqlMicrosoft(runtime, runtime.logger, endpointString, protocolReference, protocolEntry, **kwargs)
	# elif protocolType == 'protocolsqlmaria':
	# 	client = SqlMariaDb(runtime, runtime.logger, endpointString, protocolReference, protocolEntry, **kwargs)
	# elif protocolType == 'protocolsqlmy':
	# 	client = SqlMySql(runtime, runtime.logger, endpointString, protocolReference, protocolEntry, **kwargs)

	## end thisClient
	return client


def getFQDN(runtime, endpointString, connectViaFQDN=None):
	"""Get a fully qualified domain name for the connection, when requested."""
	## See if parameters request using FQDN (hostname.domain) over ipaddress
	if connectViaFQDN is None:
		connectViaFQDN = runtime.endpoint.get('data', {}).get('parameters', {}).get('connectViaFQDN', False)
	if connectViaFQDN:
		runtime.logger.report('getFQDN: directed to use FQDN instead of IP')
		## Assuming that the Node is directly connected to the IP in the results
		objectsLinkedToLinchpin = runtime.endpoint.get('children',{})
		breakOut = False
		hostname = None
		for objectLabel, objectList in objectsLinkedToLinchpin.items():
			runtime.logger.report(' looking for Node in related objects label {objectLabel!r}...', objectLabel=objectLabel)
			for entry in objectList:
				if 'hostname' not in entry.get('data').keys():
					break
				hostname = entry.get('data').get('hostname')
				domain = entry.get('data').get('domain')
				runtime.logger.report(' found hostname {hostname!r} with domain {domain!r}', hostname=hostname, domain=domain)
				breakOut = True
				break
			if breakOut:
				break
		if hostname is not None:
			runtime.logger.report('getFQDN: looking in connected Node for FQDN...')
			endpointString = hostname
			if (domain and domain.lower() != 'workgroup' and domain not in hostname):
				endpointString = '{}.{}'.format(hostname, domain)
		else:
			runtime.logger.report('getFQDN: looking in DNS for FQDN...')
			endpointString = socket.gethostbyaddr(endpointString)[0]
			runtime.logger.report(' found FQDN from DNS lookup: {endpointString!r}', endpointString=endpointString)
		## If the node wasn't qualified and the DNS lookup also failed...
		if endpointString is None:
			raise EnvironmentError('Directed to \'connectViaFQDN\', but no hostname was found from connected node or DNS lookup.')
	else:
		runtime.logger.report('getFQDN: directed to use IP instead of FQDN')

	## end getFQDN
	return endpointString


def localClient(runtime, clientType, **kwargs):
	"""Simple wrapper to instantiate managed local client types."""
	client = None
	normalizedType = clientType.lower()
	if normalizedType not in localProtocolTypes:
		raise NotImplementedError('Local client type not available for {}'.format(clientType))
	runtime.logger.report(' localClient: type {clientType!r}', clientType=clientType)

	client = localProtocolTypes[normalizedType](runtime, runtime.logger, **kwargs)
	if client is None:
		raise EnvironmentError('Unable to establish local shell type: {}'.format(clientType))

	## end getLocalClient
	return client
