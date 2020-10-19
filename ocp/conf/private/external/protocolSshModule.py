"""External utility to work with SSH connections.

Externally referenced function:
  |  connection  : called by protocolWrapperSSH to get make an SSH connection


The intention with an external wrapper, is to move responsibility of protecting
sensitive data away from the open-source platform. From a modular perspective,
this module would be best coded as a single Python class. However, doing that
provides easier access to internals and so we intentionally avoid encapsulation
with individual functions.

"""
import os
import utils
externalProtocolHandler = utils.loadExternalLibrary('externalProtocolHandler')
from fabric import Connection

def connection(runtime, protocol, endpoint, connectTimeout=3):
	"""Extract protocol and call fabric.Connection."""
	protocol = externalProtocolHandler.extractProtocol(runtime, protocol)
	user = protocol['user']
	args = {}

	useKey = protocol.get('use_key', False)
	if useKey:
		keyFileName = protocol.get('key_filename')
		passPhrase = protocol.get('key_passphrase')
		## Construct fully qualified path for keys in ./conf/private/content/keys
		keyFile = os.path.join(runtime.env.privateContentKeyPath, keyFileName)
		args['key_filename'] = keyFile
		## Handle empty pass phrases to avoid errors downstream
		if passPhrase is not None and len(passPhrase.strip()) > 0:
			args['passphrase'] = passPhrase

	else:
		password = protocol['password']
		args['password'] = password

	return Connection(host=endpoint, user=user, connect_timeout=connectTimeout, connect_kwargs=args)
