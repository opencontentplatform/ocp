"""SSH detection job.

Tested on Linux, but only stubbed for unix types.

Functions:
  startJob : standard job entry point
  getOsType: determine what OS variant we landed on
  createObjects: create objects and links

"""
import sys
import traceback
import re
import socket
from contextlib import suppress
from paramiko.ssh_exception import NoValidConnectionsError, AuthenticationException

## From openContentPlatform
from protocolWrapper import findClients
from utilities import runPortTest
import find_SSH_Linux
# import find_SSH_Solaris
# import find_SSH_HPUX
# import find_SSH_Apple
# import find_SSH_AIX


def findOsType(runtime, client, endpoint, protocolId):
	"""Find out what OS variant we landed on.

	Arguments:
	  runtime (dict)    : object used for providing input into jobs and tracking
	                      the job thread through the life of its runtime
	  client            : PowerShell client

	Note: useful link for uname context:  https://en.wikipedia.org/wiki/Uname
	"""
	## Initial check for Linux, Solaris, HP-UX, Apple
	(stdout, stderr, hitProblem) = client.run('uname -a')
	runtime.logger.report(' uname: {stdout!r}, {stderr!r}, {hitProblem!r}', stdout=stdout, stderr=stderr, hitProblem=hitProblem)
	if not hitProblem:

		## Linux
		if re.search('^\s*Linux', stdout, re.I):
			runtime.logger.report(' found Linux')
			return find_SSH_Linux.queryLinux(runtime, client, endpoint, protocolId, 'Linux', stdout)

		# ## Solaris
		# elif re.search('^\s*SunOS', stdout, re.I):
		# 	runtime.logger.report(' found Solaris')
		# 	return find_SSH_Solaris.querySolaris(runtime, client, endpoint, protocolId, 'Solaris', stdout)
		#
		# ## HP-UX
		# elif re.search('^\s*HP-UX', stdout, re.I):
		# 	runtime.logger.report(' found HPUX')
		# 	return find_SSH_HPUX.queryHPUX(runtime, client, endpoint, protocolId, 'HPUX', stdout)
		#
		# ## Apple
		# elif re.search('^\s*Darwin', stdout, re.I):
		# 	runtime.logger.report(' found Apple')
		# 	return find_SSH_Apple.queryApple(runtime, client, endpoint, protocolId, 'Apple', stdout)

		## OS not currently covered
		else:
			raise NotImplementedError(' Returned OS type that is not implemented. "uname -a" output: {}'.format(stdout))

	# else:
	# 	## Initial check for AIX
	# 	(stdout, stderr, hitProblem) = client.run('oslevel -s')
	# 	if not hitProblem:
	# 		if re.search('^\s*\d+\-\d+\-\d+', stdout):
	# 			## AIX
	# 			return find_SSH_AIX.queryAIX(runtime, client, endpoint, protocolId, 'AIX', stdout)

	raise NotImplementedError('Failed to find matching OS on endpoint {}'.format(endpoint))

	## end findOsType
	return


def attemptConnection(runtime, endpointString):
	"""Go through SSH protocol entries and attempt a connection."""
	client = None
	try:
		## Go through SSH protocol entries and attempt a connection
		clients = findClients(runtime, 'ProtocolSsh')
		for client in clients:
			protocolId = None
			try:
				protocolId = client.getId()
				client.open()

			## If we hit certain messages, may not want to continue:
			except NoValidConnectionsError:
				msg = str(sys.exc_info()[1])
				runtime.logger.error('NoValidConnectionsError with {name!r} trying {endpoint!r} with protocol ID {protocolId!r}: {msg!r}', name=__name__, endpoint=endpointString, protocolId=protocolId, msg=msg)
				runtime.status(3)
				runtime.message(msg)
				break
			except socket.timeout:
				msg = str(sys.exc_info()[1])
				runtime.logger.error('Timeout with {name!r} trying {endpoint!r} with protocol ID {protocolId!r}: {msg!r}', name=__name__, endpoint=endpointString, protocolId=protocolId, msg=msg)
				runtime.status(3)
				runtime.message(msg)
				break
			## Further wrap or control messages we expect
			except AuthenticationException:
				msg = str(sys.exc_info()[1])
				runtime.logger.error('AuthenticationException with {name!r} trying {endpoint!r} with protocol ID {protocolId!r}: {msg!r}', name=__name__, endpoint=endpointString, protocolId=protocolId, msg=msg)
				with suppress(Exception):
					client.close()
				client = None
				continue
			## For all the rest
			except:
				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				runtime.logger.report('=====> except msg: {stacktrace!r}', stacktrace=stacktrace)
				msg = str(sys.exc_info()[1])
				runtime.logger.error('Exception with {name!r} trying {endpoint!r} with protocol ID {protocolId!r}:  {msg!r}', name=__name__, endpoint=endpointString, protocolId=protocolId, msg=msg)
				runtime.setError(__name__)
				with suppress(Exception):
					client.close()
				client = None
				continue

			## Detect the OS type and then start the work
			findOsType(runtime, client, endpointString, protocolId)
			client.close()
			## If we got here, we should break even if there's a script error
			break

	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end attemptConnection
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		endpointString = runtime.endpoint.get('data', {}).get('address')
		runtime.logger.report('endpointString: {endpointString}', endpointString=endpointString)
		if runtime.jobMetaData.get('realm') is None:
			runtime.logger.warn('Skipping job {name!r} on endpoint {endpoint!r}; realm is not set in job configuration.', name=__name__, endpoint=endpointString)
			return
		runtime.logger.report('Running job {name!r} on endpoint {endpoint!r}', name=__name__, endpoint=endpointString)

		## Port test if user requested via parameters
		continueFlag = True
		portTest = runtime.parameters.get('portTestBeforeConnectionAttempt', False)
		if portTest:
			ports = runtime.parameters.get('portsToTest', [])
			portIsActive = runPortTest(runtime, endpointString, ports)
			if not portIsActive:
				runtime.setWarning('Endpoint not listening on ports {}; skipping SSH attempt.'.format(str(ports)))
				continueFlag = False

		if continueFlag:
			attemptConnection(runtime, endpointString)

	except:
		runtime.setError(__name__)

	## end startJob
	return
