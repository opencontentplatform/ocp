"""External utility to work with WMI connections.

Externally referenced function:
  |  connection  : called by protocolWrapperWmi to get make a WMI connection


The intention with an external wrapper, is to move responsibility of protecting
sensitive data away from the open-source platform. From a modular perspective,
this module would be best coded as a single Python class. However, doing that
provides easier access to internals and so we intentionally avoid encapsulation
with individual functions.

"""
import wmi
import utils
externalProtocolHandler = utils.loadExternalLibrary('externalProtocolHandler')

def connection(runtime, protocol, endpoint, namespace="root/cimv2"):
	"""Extract user & password from protocol, and call wmi.WMI()."""
	protocol = externalProtocolHandler.extractProtocol(runtime, protocol)
	user = protocol['user']
	password = protocol['password']
	return wmi.WMI(moniker=namespace, computer=endpoint, user=user, password=password)
