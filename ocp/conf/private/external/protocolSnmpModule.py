"""External utility to work with SNMP queries.

Externally referenced functions:
  |  snmpGetCmd  : called by protocolWrapperSnmp to get a single result
  |  snmpNextCmd : called by protocolWrapperSnmp to get a list of results


The intention with an external wrapper, is to move responsibility of protecting
sensitive data away from the open-source platform. From a modular perspective,
this module would be best coded as a single Python class. However, doing that
provides easier access to internals and so we intentionally avoid encapsulation
with individual functions.

"""
from pysnmp.hlapi import *
import utils
externalProtocolHandler = utils.loadExternalLibrary('externalProtocolHandler')


def getValues(runtime, protocol):
	protocol = externalProtocolHandler.extractProtocol(runtime, protocol)
	communityString = protocol.get('community_string')
	port = protocol.get('port', 161)
	## Defaulting the port above, doesn't work if port has None as the value
	if port is None:
		port = 161
	return (protocol, communityString, port)


def snmpGetCmd(runtime, protocol, endpoint, oid):
	"""Extract community string & port from protocol, and call pysnmp.hlapi.getCmd()"""
	(protocol, communityString, port) = getValues(runtime, protocol)
	#version = protocol.get('version', 2)
	return getCmd(SnmpEngine(),
				  CommunityData(communityString),
				  UdpTransportTarget((endpoint, port)),
				  ContextData(),
				  ObjectType(ObjectIdentity(oid)))


def snmpNextCmd(runtime, protocol, endpoint, oid):
	"""Extract community string & port from protocol, and call pysnmp.hlapi.nextCmd()"""
	(protocol, communityString, port) = getValues(runtime, protocol)
	return nextCmd(SnmpEngine(),
				   CommunityData(communityString),
				   UdpTransportTarget((endpoint, port)),
				   ContextData(),
				   ObjectType(ObjectIdentity(oid)),
				   lexicographicMode=False)
