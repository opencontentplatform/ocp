"""Wrapper for accessing the Simple Network Management Protocol (SNMP).

Classes:
  |  Snmp : wrapper class for SNMP

"""
## Using an externally provided library defined in globalSettings and located
## in '<install_path>/external'.
import utils
externalProtocolLibrary = utils.loadExternalLibrary('externalProtocolSnmp')

## Pysnmp is used in the external library:
##   from pysnmp.hlapi import *
## To call these functions:
##   getCmd(SnmpEngine(), CommunityData(communityString),
##          UdpTransportTarget((endpoint, port)), ContextData(),
##          ObjectType(ObjectIdentity(oid)))
##   nextCmd(SnmpEngine(), CommunityData(communityString),
##          UdpTransportTarget((endpoint, port)), ContextData(),
##          ObjectType(ObjectIdentity(oid)), lexicographicMode=False)


class Snmp:
	"""Wrapper class for SNMP."""
	def __init__(self, runtime, logger, endpoint, reference, protocol):
		## Get a handle on the provided protocol context
		self.runtime = runtime
		self.logger = logger
		self.endpoint = endpoint
		self.reference = reference
		self.protocol = protocol
		self.client = None

	def open(self):
		## There isn't a stateful connection here
		pass

	def close(self):
		## There isn't a stateful connection here
		pass

	def getId(self):
		return self.reference

	def get(self, oid, response):
		"""Return the output from a single OID."""
		## Extract communityString/port from protocol and return the following:
		##   getCmd(SnmpEngine(), CommunityData(communityString),
		##          UdpTransportTarget((endpoint, port)), ContextData(),
		##          ObjectType(ObjectIdentity(oid)))
		errorIndication, errorStatus, errorIndex, varBinds = next(externalProtocolLibrary.snmpGetCmd(self.runtime, self.protocol, self.endpoint, oid))

		if errorIndication:
			self.logger.error('{errorIndication!r}', errorIndication=errorIndication)
		elif errorStatus:
			self.logger.error('{errorStatus!r} at {errorIndex!r}', errorStatus=errorStatus.prettyPrint(), errorIndex=errorIndex)
		else:
			for varBind in varBinds:
				response[str(varBind[0])] = str(varBind[1])

		## end get
		return


	def getNext(self, oid, response):
		"""Return the output from the OID tree.

		The lexicographicMode ensures it stays within the OID context instead of
		walking past it. Please note that this is a getNext instrumentation, not
		a getBulk. As such it's recommended for targeted/light queries only.
		"""
		## Extract communityString/port from protocol and return the following:
		##   nextCmd(SnmpEngine(), CommunityData(communityString),
		##          UdpTransportTarget((endpoint, port)), ContextData(),
		##          ObjectType(ObjectIdentity(oid)), lexicographicMode=False)
		for (errorIndication, errorStatus, errorIndex, varBinds) in externalProtocolLibrary.snmpNextCmd(self.runtime, self.protocol, self.endpoint, oid):
			if errorIndication:
				self.logger.error('{errorIndication!r}', errorIndication=errorIndication)
				break
			elif errorStatus:
				self.logger.error('{errorStatus!r} at {errorIndex!r}', errorStatus=errorStatus.prettyPrint(), errorIndex=errorIndex)
				break
			else:
				for varBind in varBinds:
					response[str(varBind[0])] = str(varBind[1])

		## end getNext
		return
