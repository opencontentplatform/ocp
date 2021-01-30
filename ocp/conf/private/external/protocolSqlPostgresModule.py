"""External utility to work with Postgres SQL connections.

Externally referenced function:
  |  connection  : called by protocolWrapperSqlPostgres to make a SQL connection


The intention with an external wrapper, is to move responsibility of protecting
sensitive data away from the open-source platform. From a modular perspective,
this module would be best coded as a single Python class. However, doing that
provides easier access to internals and so we intentionally avoid encapsulation
with individual functions.

"""
import os
import utils
externalProtocolHandler = utils.loadExternalLibrary('externalProtocolHandler')
## Using the following database adapter: https://www.psycopg.org/
import psycopg2


def getParameters(runtime, protocol, endpoint, dbname, port, connectTimeout, parameters):
	"""Create the connection parameters to use with our database adapter."""
	user = protocol['user']
	parameters['user'] = user
	parameters['host'] = endpoint
	parameters['dbname'] = dbname
	## Postgres default standard is to have databases named the same as the user
	## so if a dbname was not passed in, we use the user as the database name
	if dbname is None:
		parameters['dbname'] = user

	parameters['port'] = protocol.get('port', 5432)
	## Override TCP/IP port when specified
	if port != 0:
		parameters['port'] = port
	parameters['connect_timeout'] = protocol.get('ssl_mode', 10)
	## Override standard connection timeout when specified
	if connectTimeout != 0:
		parameters['connect_timeout'] = int(connectTimeout)
	## Set mode if specified (e.g. 'allow', 'prefer', 'require', 'verify-full')
	ssl_mode = protocol.get('ssl_mode')
	if ssl_mode is not None and len(ssl_mode.strip()) > 0:
		parameters['ssl_mode'] = ssl_mode.strip()
	## Provide the server side visibility into who is attempting the connection
	parameters['application_name'] = 'OpenContentPlatform'

	useCert = protocol.get('use_cert', False)
	if useCert:
		certFileName = protocol.get('cert_filename')
		## Construct fully qualified certificate in ./conf/private/content/certs
		certFile = os.path.join(runtime.env.privateContentCertPath, certFileName)

		## Conditionally handle a secret key file for the client certificate
		certKey = protocol.get('cert_key')
		if certKey is not None and len(certKey.strip()) > 0:
			## Construct fully qualified key in ./conf/private/content/certs
			certKey = os.path.join(runtime.env.privateContentCertPath, certKey)
			parameters['sslkey'] = certKey
		## Conditionally handle a password for encrypted secret keys
		parameters['sslcert'] = certFile
		certPassword = protocol.get('cert_password')
		if certPassword is not None and len(certPassword.strip()) > 0:
			parameters['sslpassword'] = certPassword

	else:
		parameters['password'] = protocol['password']


def connection(runtime, protocol, endpoint, dbname, port=0, connectTimeout=0):
	"""Attempt SQL connection to provided endpoint."""

	## Get a handle on the protocol
	protocol = externalProtocolHandler.extractProtocol(runtime, protocol)
	## Create the connection parameters
	parameters = {}
	getParameters(runtime, protocol, endpoint, dbname, port, connectTimeout, parameters)

	## Attempt connection with psycopg2, establishing a new DB session
	return psycopg2.connect(**parameters)
