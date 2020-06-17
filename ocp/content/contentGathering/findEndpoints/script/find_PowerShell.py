"""PowerShell detection job.

Functions:
  startJob : standard job entry point
  getOsType: determine what OS variant we landed on
  createObjects: create objects and links

Note: When creating this, PowerShell 6.0 Core had just hit the GA release,
which only contained the framework for Linux and Apple. After this becomes
more functional and widely accepted, I need to setup a test bed for Linux
and Apple endpoints to get the associated details as I do now on Windows.

Watch here for future PowerShell open source releases:
https://github.com/PowerShell/PowerShell

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Jan 24, 2018

"""
import sys
import traceback
import re
from contextlib import suppress

## From openContentPlatform
from protocolWrapper import findClients
from utilities import runPortTest
import find_PowerShell_Windows
import find_PowerShell_Linux
import find_PowerShell_Apple


def getOsType(runtime, client):
	"""Find out what OS variant we landed on.

	PowerShell 6.0 Core had the framework for Linux & Apple as well as Windows.

	Arguments:
	  runtime (dict)    : object used for providing input into jobs and tracking
	                      the job thread through the life of its runtime
	  client            : PowerShell client
	"""
	## Non-Windows OS types are stubbed in, but not tested at this time
	getOsTypeCmds = {
		"Linux": ["$IsLinux", "True"],
		"Apple": ["$IsMacOS", "True"],
		"Windows": ["$Env:OS", "Windows_NT"]
	}
	osType = None
	for osKey in getOsTypeCmds:
		try:
			(typeCmd, typeOutput) = getOsTypeCmds[osKey]
			runtime.logger.report('  running {osType!r} command: {typeCmd!r}', osType=osKey, typeCmd=typeCmd)
			(stdOut, stdError, hitProblem) = client.run(typeCmd, 5)
			runtime.logger.report('  testCmd returned: {stdOut!r}, {stdError!r}, {hitProblem!r}', stdOut=stdOut, stdError=stdError, hitProblem=hitProblem)
			## Check shell command exit status to ensure success
			if hitProblem or stdOut is None:
				continue
			## Validate output if typeOutput was provided
			m = re.search(typeOutput, stdOut, re.I)
			if m:
				osType = osKey
				break
			runtime.logger.report('  typeOutput does NOT match {typeOutput!r}', typeOutput=typeOutput)
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in getOsType: {stacktrace!r}', stacktrace=stacktrace)

	## end getOsType
	return osType


def attemptConnection(runtime, endpointString):
	"""Go through PowerShell protocol entries and attempt a connection."""
	client = None
	try:
		## Go through PowerShell protocol entries and attempt a connection
		clients = findClients(runtime, 'ProtocolPowerShell', commandTimeout=30)
		for client in clients:
			doNotContinue = False
			protocolId = None
			try:
				protocolId = client.getId()
				runtime.logger.error('  ... attempting connection with protocolId: {protocolId!r}', protocolId=protocolId)
				client.open()

			except:
				msg = str(sys.exc_info()[1])
				## If we hit certain messages, may not want to continue:
				if re.search('The client cannot connect to the destination specified in the request. Verify that the service on the destination is running and is accepting requests.', msg, re.I):
					## This type of failure means the endpoint is unavailable
					doNotContinue = True
					runtime.logger.error('  ... doNotContinue 1: {doNotContinue!r}', doNotContinue=doNotContinue)
				runtime.logger.error('Exception with {name!r} trying {endpoint!r} with protocol ID {protocolId!r}: {msg!r}', name=__name__, endpoint=endpointString, protocolId=protocolId, msg=msg)
				runtime.status(3)
				runtime.message(msg)
				with suppress(Exception):
					client.close()
				client = None
				if doNotContinue:
					runtime.logger.error('  ... doNotContinue 2: {doNotContinue!r}', doNotContinue=doNotContinue)
					break
				continue

			## Get the OS type (PowerShell Core enabled other OS types)
			osType = getOsType(runtime, client)
			## Do the work
			if osType == 'Windows':
				find_PowerShell_Windows.queryWindows(runtime, client, endpointString, protocolId, osType)
			elif osType == 'Linux':
				find_PowerShell_Linux.queryLinux(runtime, client, endpointString, protocolId, osType)
			elif osType == 'Apple':
				find_PowerShell_Apple.queryApple(runtime, client, endpointString, protocolId, osType)
			else:
				runtime.logger.debug('OS Type not found; nothing to do on endpoint {endpointString!r}', endpointString=endpointString)
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
		## When using the endpointQuery 'ipv4addresses':
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
				runtime.setWarning('Endpoint not listening on ports {}; skipping PowerShell attempt.'.format(str(ports)))
				continueFlag = False

		if continueFlag:
			attemptConnection(runtime, endpointString)

	except:
		runtime.setError(__name__)

	## end startJob
	return
