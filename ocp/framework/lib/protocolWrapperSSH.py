"""Wrapper for accessing SSH shell connections.

Classes:
  |  SSH : wrapper class for SSH

"""
import sys
import traceback
from paramiko.ssh_exception import NoValidConnectionsError, AuthenticationException
import socket

## Using an externally provided library defined in globalSettings and located
## in '<install_path>/external'.
import utils
externalProtocolLibrary = utils.loadExternalLibrary('externalProtocolSsh')

## Fabric is used by the external library:
##   from fabric import Connection
## To call this function for a remote connection:
##   Connection(host, user, connect_timeout, connect_kwargs)


class SSH():
	"""Wrapper class for SSH."""
	def __init__(self, runtime, logger, endpoint, reference, protocol, sessionTimeout=120, commandTimeout=10, connectTimeout=10):
		self.runtime = runtime
		self.logger = logger
		self.endpoint = endpoint
		self.reference = reference
		self.protocol = protocol
		self.connectTimeout = int(connectTimeout)
		self.sessionTimeout = int(sessionTimeout)
		self.commandTimeout = int(commandTimeout)
		self.client = None
		self.connected = False

	def open(self):
		'''Initialize shell connection'''
		self.logger.info('Opening SSH connection')
		try:
			## Extract user/password from protocol and return the following:
			##   fabric.Connection(host=self.endpoint, user=user, connect_timeout=self.connectTimeout, connect_kwargs)
			self.client = externalProtocolLibrary.connection(self.runtime, self.protocol, self.endpoint, self.connectTimeout)
			## Send something through stdin to verify we have a connection...
			## TODO: consider making this more useful by validating something
			## like user, an environmental setting, shell type/version, etc
			self.run('hostname', timeout=3)
			self.connected = True
		except NoValidConnectionsError as e:
			raise NoValidConnectionsError(e.errors)
		except socket.timeout:
			raise socket.timeout(str(sys.exc_info()[1]))
		except AuthenticationException:
			raise AuthenticationException(str(sys.exc_info()[1]))
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Failure in SSH open: {stacktrace!r}', stacktrace=stacktrace)
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			raise EnvironmentError(exceptionOnly)
		if not self.connected:
			self.client.close()
			raise EnvironmentError('No connection established')
		return


	def run(self, cmd, timeout=None, pty=False, env=None):
		'''Entry point for executing commands.'''
		cmdTimeout = self.commandTimeout
		if timeout and str(timeout).isdigit():
			cmdTimeout = int(timeout)
		kwargs = {'warn': True, 'hide': True, 'timeout': cmdTimeout}
		if pty:
			self.logger.info('RUN setting PTY to true')
			kwargs['pty'] = True
		## If a child environment is provided... override
		if env:
			self.logger.info('RUN overriding ENV with {env!r}', env=env)
			kwargs['env'] = env
		result = self.client.run(cmd, **kwargs)
		hitProblem = not result.ok
		return (result.stdout, result.stderr, hitProblem)


	def close(self):
		'''Stop the shell process.'''
		if self.client is not None:
			self.client.close()

	def __del__(self):
		self.close()

	def getId(self):
		return self.reference
