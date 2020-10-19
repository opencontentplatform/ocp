"""External utility to work with SSH connections.

Externally referenced function:
  |  connection  : called by protocolWrapperSSH to get make an SSH connection


The intention with an external wrapper, is to move responsibility of protecting
sensitive data away from the open-source platform. From a modular perspective,
this module would be best coded as a single Python class. However, doing that
provides easier access to internals and so we intentionally avoid encapsulation
with individual functions.

"""
from fabric import Connection
import utils
externalProtocolHandler = utils.loadExternalLibrary('externalProtocolHandler')

def connection(runtime, protocol, endpoint, connectTimeout=3):
	"""Extract user & password from protocol, and call wmi.WMI()."""
	protocol = externalProtocolHandler.extractProtocol(runtime, protocol)
	user = protocol['user']
	password = protocol['password']
	args = {}
	args['password'] = password
	return Connection(host=endpoint, user=user, connect_timeout=connectTimeout, connect_kwargs=args)
