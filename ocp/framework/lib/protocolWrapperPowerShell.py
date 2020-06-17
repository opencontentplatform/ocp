"""Wrapper for accessing Windows PowerShell.

Classes:
  |  PowerShell : wrapper class for PowerShell

.. hidden::
	
	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Jan 3, 2018

"""
from contextlib import suppress
import sys
import os
import subprocess

import utils
from protocolWrapperShell import Shell, NonBlockingStreamReader
## Using an externally provided library defined in globalSettings and located
## in '<install_path>/external'.
externalProtocolLibrary = utils.loadExternalLibrary('externalProtocolPowerShell')


class PowerShell(Shell):
	"""Wrapper class for PowerShell."""
	def __init__(self, runtime, logger, endpoint, reference, protocol, **kwargs):
		if ('shellExecutable' not in kwargs or kwargs['shellExecutable'] is None):
			## Static v1.0 path still valid on v5.1, however relative paths work 
			## best with different environments setup through user preferences
			#kwargs['shellExecutable'] = 'C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe'
			kwargs['shellExecutable'] = 'powershell.exe'
		self.exitStatusPassRegEx = '^True$'
		self.exitStatusFailRegEx = '^False$'
		super().__init__(runtime, logger, endpoint, protocol, **kwargs)
		self.reference = reference
		self.session = None
		self.process = None
		self.stream = None
		self.streamErr = None
		self.kwargs = kwargs
		self.connected = False
		self.log('init {}'.format(__name__))


	def open(self):
		'''Initialize shell and establish session connection into endpoint.

		Capture all problems with the PSSession command; avoid silent failure
		messages and prevent false positives - thinking we have a connection.

		This calls subprocess.Popen to start a local powershell process. Then we
		interact with the process using its internal pipes; we send commands in
		by writing to STDIN and read results by reading/buffering from STDOUT
		and STDERR. I don't use the subprocess.communicate() method because that
		cleans up and shuts down after a single command (or set of commands that
		must be provided up front). At this point in the job, we have no idea
		what types of commands or even the number that need sent to the remote
		endpoint. All we can do here is establish that remote connection, which
		is accomplished by establishing a remote PowerShell session off a local
		PowerShell subprocess call.
		'''
		self.log('open: Popen starting')
		## Avoid using the 'shell' option if we don't need to.
		#self.process = subprocess.Popen(self.shellExecutable, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
		self.process = subprocess.Popen([self.shellExecutable], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
		self.log('open: Popen finished')
		
		## Note: We may need to change this from a PIPE (with a character limit
		## of 65,536) to using a tempfile (tempfile.TemporaryFile()), like so:
		#self.process = subprocess.Popen([self.shellExecutable], stdin=subprocess.PIPE, stdout=tempfile.TemporaryFile(), stderr=tempfile.TemporaryFile(), shell=False)
		## Right now we are using a PIPE with a NonBlockingStreamReader function
		## to move data from the PIPE over to a QUEUE for processing; this works
		## with large datasets, but was not tested on GB streams of data.		

		self.log('open: wrapping pipes with NonBlockingStreamReader')
		self.stream = NonBlockingStreamReader(self.process.stdout)
		self.streamErr = NonBlockingStreamReader(self.process.stderr)
		
		versionInfo = '$PSVersionTable.PSVersion | ConvertTo-Json'
		(stdout, stderr, hitProblem) = self.send(versionInfo, skipStatusCheck=True)
		self.log('open: PSVersionTable output: {}. stderr: {}. hitProblem: {}'.format(stdout, stderr, hitProblem))
		
		## Extract user/password from protocol and use self.send to create a
		## PSCredential object assigned to a target $ocpc PowerShell variable:
		##   setCredential = '$a="{}";$b="{}";$sp=Convertto-SecureString -String $b -AsPlainText -force;$ocpc=New-object System.Management.Automation.PSCredential $a, $sp'.format(user, password)
		##   self.send(setCredential, skipStatusCheck=True)
		(stdout, stderr, hitProblem) = externalProtocolLibrary.setCredential(self)
		self.log('open: PSCredential output: {}. stderr: {}. hitProblem: {}'.format(stdout, stderr, hitProblem))
		
		sessionWrapper = '$s = New-PSSession -ComputerName "{}" -Credential $ocpc; $?'.format(self.endpoint)
		self.log('open: PSSession starting')
		(strResult, strErrors, hitProblem) = self.send(sessionWrapper)
		self.log('open: PSSession result: {}. stderr: {}. hitProblem: {}'.format(stdout, stderr, hitProblem))
		if hitProblem:
			raise EnvironmentError(strErrors)
		self.connected = True
		return strResult


	def run(self, cmd, timeout=None, skipStatusCheck=False):
		'''Entry point for executing commands.'''
		if self.abort:
			self.logger.error('Error occured on session; unable to send additional commands in. Please close the session.')
			return
		## Wrap the command with start/stop markers
		cmdToExecute = None
		if skipStatusCheck:
			cmdToExecute = self._wrapCommand('Invoke-Command -Session $s -ScriptBlock {' + cmd + ' | out-string -width 16000 -stream}')
		else:
			cmdToExecute = self._wrapCommand('Invoke-Command -Session $s -ScriptBlock {' + cmd + ' | out-string -width 16000 -stream; $?}')

		## Send the command (in string form) into the process' STDIN
		self.process.stdin.write(cmdToExecute)
		self.process.stdin.flush()
		## Accumulate and return the results of the command
		cmdTimeout = self.commandTimeout
		if timeout and str(timeout).isdigit():
			cmdTimeout = int(timeout)
		return self._processResults(cmdTimeout, skipStatusCheck)


	def close(self):
		'''Stop the shell process.'''
		self.log('close protocolWrapperPowerShell')
		## The checks for connected and process are there mainly so we can code
		## the close function outside the __del__(destructor) call. So in cases
		## where the developer of a job doesn't close the connection, the intent
		## is for the destructor to handle that. But we obviously only want the
		## destructor to attempt this if it hasn't yet been explicitely closed.
		if self.connected:
			result = self.send('if ($s -ne $null) {Remove-PSSession $s}')
			self.connected = False
		if self.process:
			self.process.terminate()
			self.process.wait()
		with suppress(Exception):
			del self.stream
		with suppress(Exception):
			del self.streamErr
		## We shouldn't have to manually close the pipes, but just in case:
		with suppress(Exception):
			self.process.stdin.close()
		with suppress(Exception):
			self.process.stdout.close()
		with suppress(Exception):
			self.process.stderr.close()
		self.process = None


	def __del__(self):
		self.close()

	def getId(self):
		return self.reference



## Unit test section
def queryOperatingSystem(client, logger, attrDict):
	try:
		results = client.run('Get-WmiObject -Class Win32_OperatingSystem | select-object Manufacturer,Version,Name,Caption |fl')
		logger.debug('Win32_OperatingSystem result: {results!r}', results=results)
		tmpDict = {}
		parseListFormatToDict(logger, results[0], tmpDict)
		for keyName in ['Manufacturer', 'Version', 'Name', 'Caption']:
			attrDict[keyName] = getDictValue(tmpDict, keyName)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in queryOperatingSystem: {stacktrace!r}', stacktrace=stacktrace)
	return

def getDictValue(attrDict, keyName):
	value = None
	if keyName in attrDict:
		value = attrDict[keyName]
		if value is not None and len(value.strip()) > 0:
			value = None
	return value

def parseListFormatToDict(logger, output, data):

	for line in output.split('\n'):
		try:
			if (line and len(line.strip()) > 0):
				lineAsList = line.split(':', 1)
				logger.debug('lineAsList: {lineAsList!r}', lineAsList=lineAsList)
				key = lineAsList[0].strip()
				value = lineAsList[1].strip()
				data[key] = value
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			logger.debug('parseListFormatToDict Exception: {exception!r}', exception=stacktrace)
	return data


def powerShell():
	import sys
	import traceback
	import os
	import re
	try:
		## Add openContentPlatform directories onto the sys path
		thisPath = os.path.dirname(os.path.abspath(__file__))
		basePath = os.path.abspath(os.path.join(thisPath, '..'))
		if basePath not in sys.path:
			sys.path.append(basePath)
		import env
		env.addLibPath()
		env.addDatabasePath()
		env.addExternalPath()

		## Setup requested log handlers
		globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))
		logEntity = 'Protocols'
		logger = utils.setupLogger(logEntity, env, 'logSettingsCore.json')
		logger.info('Starting protocolWrapperPowershell...')

		import twisted.logger
		logFiles = utils.setupLogFile('JobDetail', env, globalSettings['fileContainingContentGatheringLogSettings'], directoryName='client')
		logObserver  = utils.setupObservers(logFiles, 'JobDetail', env, globalSettings['fileContainingContentGatheringLogSettings'])
		logger = twisted.logger.Logger(observer=logObserver, namespace='JobDetail')

		from remoteRuntime import Runtime
		runtime = Runtime(logger, env, 'TestPkg', 'TestJob', 'endpoint', {}, None, {}, None, {}, None)

		## Manual creation of a protocol via protocolHandler
		externalProtocolHandler = utils.loadExternalLibrary('externalProtocolHandler', env, globalSettings)
		protocolHandler = externalProtocolHandler.ProtocolHandler(None, globalSettings, env, logger)
		protocolType = 'ProtocolPowerShell'
		protocolData = {'user': 'Me', 'password': 'Something'}
		protocolHandler.createManual(runtime, protocolType, protocolData)
		protocol = externalProtocolHandler.getProtocolObject(runtime, 1)
		print('protocol to use: {}'.format(protocol))
		print('protocols: {}'.format(externalProtocolHandler.getProtocolObjects(runtime)))

		endpoint = '192.168.1.100'
		client = PowerShell(runtime, logger, endpoint, 1, protocol)
		client.open()

		osAttrDict = {}
		queryOperatingSystem(client, logger, osAttrDict)
		logger.debug('osAttrDict: {osAttrDict!r}', osAttrDict=osAttrDict)
		client.close()

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		msg = str(sys.exc_info()[1])
		## Cleanup message when we know what it is:
		## "<x_wmi: The RPC server is unavailable.  (-2147023174, 'The RPC server is unavailable. ', (0, None, 'The RPC server is unavailable. ', None, None, -2147023174), None)>"
		if re.search('The client cannot connect to the destination specified in the request', msg, re.I):
			## Remove the rest of the fluff
			msg = 'The client cannot connect to the destination specified in the request. Verify that the service on the destination is running and is accepting requests.'
			logger.debug('Main Exception: {exception!r}', exception=msg)
		else:
			logger.debug('Main Exception: {exception!r}', exception=stacktrace)

if __name__ == '__main__':
	sys.exit(powerShell())
