"""Wrapper for accessing SQL connections via database adapters/drivers.

Classes:
  |  SQL : wrapper class for SQL connections

"""
import sys
import traceback
import socket

## Using an externally provided library defined in globalSettings and located
## in '<install_path>/external'.
import utils
externalProtocolLibrary = utils.loadExternalLibrary('externalProtocolSqlPostgres')

## Fabric is used by the external library:
##   from fabric import Connection
## To call this function for a remote connection:
##   Connection(host, user, connect_timeout, connect_kwargs)


class SqlPostgres():
	"""Wrapper class for SQL connections."""
	def __init__(self, runtime, logger, endpoint, reference, protocol, sessionTimeout=120, commandTimeout=10, connectTimeout=10, dbname=None, port=0):
		self.runtime = runtime
		self.logger = logger
		self.endpoint = endpoint
		self.reference = reference
		self.protocol = protocol
		self.connectTimeout = int(connectTimeout)
		self.sessionTimeout = int(sessionTimeout)
		self.commandTimeout = int(commandTimeout)
		self.dbname = dbname
		self.port = port
		self.session = None
		self.cursor = None
		self.connected = False

	def open(self):
		'''Initialize database session and then a default cursor'''
		self.logger.info('Opening SQL connection')
		try:
			## Extract user/password from protocol and return the following:
			##   psycopg2.connect(**parameters)
			self.session = externalProtocolLibrary.connection(self.runtime, self.protocol, self.endpoint, self.dbname, self.port, self.connectTimeout)
			## Create a default cursor; this is used for executing PostgreSQL
			## commands in the session. This needs to expose both the session
			## and the cursor, since commit/rollback is done on the session.
			self.cursor = self.session.cursor()
			self.connected = True
		except socket.timeout:
			raise socket.timeout(str(sys.exc_info()[1]))
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Failure in SQL open: {stacktrace!r}', stacktrace=stacktrace)
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			raise EnvironmentError(exceptionOnly)
		if not self.connected:
			self.close()
			raise EnvironmentError('No connection established')
		return


	def close(self):
		'''Stop the cursor and then the session.'''
		if self.cursor is not None:
			self.cursor.close()
		if self.session is not None:
			self.session.close()

	def __del__(self):
		self.close()

	def getId(self):
		return self.reference
