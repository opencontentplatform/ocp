"""External utility to work with PowerShell connections.

Externally referenced function:
  |  setCredential  : called by protocolWrapperPowerShell to construct credential


The intention with an external wrapper, is to move responsibility of protecting
sensitive data away from the open-source platform. From a modular perspective,
this module would be best coded as a single Python class. However, doing that
provides easier access to internals and so we intentionally avoid encapsulation
with individual functions.

"""
import utils
externalProtocolHandler = utils.loadExternalLibrary('externalProtocolHandler')

def setCredential(protoWrapper):
	"""Extract user & password from protocol and create PSCredential on shell"""
	protocol = externalProtocolHandler.extractProtocol(protoWrapper.runtime, protoWrapper.protocol)
	user = protocol['user']
	password = protocol['password']
	prep = '$a="{}";$b="{}";$sp=Convertto-SecureString -String $b -AsPlainText -force;$ocpc=New-object System.Management.Automation.PSCredential $a, $sp'.format(user, password)
	return protoWrapper.send(prep, skipStatusCheck=True)
