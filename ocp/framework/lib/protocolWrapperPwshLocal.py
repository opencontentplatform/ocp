"""Wrapper for using a local open-source PowerShell on the client.

This PowerShell is running "local" to the client; it's not a remote session. The
reason for using this class instead subprocess.Popen() directly, is to enable
a long-standing shell environment where all commands are executed in the same
runtime. It's also a convenience wrapper implementing command timeouts, shell
resets, and data pipes.


Classes:
  |  PwshLocal : wrapper class for a local open-source PowerShell (PWSH)

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Jan 3, 2018

"""
import sys
import traceback
import os
import time
import random
from contextlib import suppress
import subprocess
from protocolWrapperShell import Shell, NonBlockingStreamReader


class PwshLocal(Shell):
	"""Wrapper class for PWSH."""
	def __init__(self, runtime, logger, **kwargs):
		if ('shellExecutable' not in kwargs or kwargs['shellExecutable'] is None):
			kwargs['shellExecutable'] = 'pwsh'
		kwargs['echoCmd'] = 'write-host'
		self.exitStatusCheck = '$?'
		self.exitStatusPassRegEx = '^True$'
		self.exitStatusFailRegEx = '^False$'
		self.joinCmd = ' ; '
		super().__init__(runtime, logger, None, None, **kwargs)
		self.kwargs = kwargs
		self.connected = False
		self.log('init {}'.format(__name__))


	def open(self):
		"""Initialize shell and establish pipes.

		Capture all problems with the PSSession command; avoid silent failure
		messages and prevent false positives - thinking we have a connection.

		This calls subprocess.Popen to start a local terminal process. It then
		interacts with the process using the internal pipes; sending commands in
		by writing to STDIN and reading results by reading/buffering from STDOUT
		and STDERR. It avoids the subprocess.communicate() method because that
		cleans up and shuts down after a single command (or set of commands that
		must be provided up front), and we have no context of number of commands
		desired by the job.
		"""
		## Random delay to avoid 100 threads starting powershell sessions at
		## the same time; more than about 10 sessions starting simultaneously
		## has caused resource restrictions and is shown to stifle additional
		## concurrent requests.
		time.sleep(random.uniform(0,2))

		self.log('open: Popen starting')
		self.process = subprocess.Popen([self.shellExecutable], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
		self.log('open: Popen finished')

		self.log('open: wrapping pipes with NonBlockingStreamReader')
		self.stream = NonBlockingStreamReader(self.process.stdout)
		self.streamErr = NonBlockingStreamReader(self.process.stderr)

		#versionInfo = '$PSVersionTable.PSVersion | ConvertTo-Json'
		testCommand = 'hostname'
		(stdout, stderr, hitProblem) = self.run(testCommand, timeout=5, skipStatusCheck=False)
		self.log('open: {} output: {}. stderr: {}. hitProblem: {}'.format(testCommand, stdout, stderr, hitProblem))

		if hitProblem:
			raise EnvironmentError(stderr)
		self.connected = True
		return stdout


	def run(self, cmd, timeout=None, skipStatusCheck=False):
		"""Entry point for executing commands."""
		if self.abort:
			self.logger.error('Error occured on session; unable to send additional commands in. Please close the session.')
			return
		## Wrap the command with start/stop markers
		cmdToExecute = None
		if skipStatusCheck:
			cmdToExecute = self._wrapCommand('Invoke-Command -ScriptBlock {' + cmd + ' | out-string -width 16000 -stream}')
		else:
			cmdToExecute = self._wrapCommand('Invoke-Command -ScriptBlock {' + cmd + ' | out-string -width 16000 -stream' + self.joinCmd + self.exitStatusCheck + '}')

		## Send the command (in string form) into the process' STDIN
		self.process.stdin.write(cmdToExecute)
		self.process.stdin.flush()
		## Accumulate and return the results of the command
		cmdTimeout = self.commandTimeout
		if timeout and str(timeout).isdigit():
			cmdTimeout = int(timeout)
		return self._processResults(cmdTimeout, skipStatusCheck)


	def close(self):
		"""Stop the shell process."""
		self.log('close PwshLocal')
		if self.connected:
			self.connected = False
		if self.process:
			self.process.terminate()
			self.process.wait()
			self.process = None
		with suppress(Exception):
			del self.stream
		with suppress(Exception):
			del self.streamErr

	def __del__(self):
		self.close()



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

def psLocalTest():
	try:
		thisPath = os.path.dirname(os.path.abspath(__file__))
		basePath = os.path.abspath(os.path.join(thisPath, '..'))
		if basePath not in sys.path:
			sys.path.append(basePath)
		import env
		env.addLibPath()
		import utils
		import twisted.logger

		## Setup requested log handlers
		globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))
		logFiles = utils.setupLogFile('JobDetail', env, globalSettings['fileContainingContentGatheringLogSettings'], directoryName='client')
		logObserver  = utils.setupObservers(logFiles, 'JobDetail', env, globalSettings['fileContainingContentGatheringLogSettings'])
		logger = twisted.logger.Logger(observer=logObserver, namespace='JobDetail')

		client = PwshLocal(logger)
		version = client.open()
		logger.debug('version: {version!r}', version=version)

		logger.debug('sleep should timeout and reinitialize shell...')
		results = client.run('sleep 5', timeout=2)
		logger.debug('sleep output: {results!r}', results=results)

		osAttrDict = {}
		queryOperatingSystem(client, logger, osAttrDict)
		logger.debug('osAttrDict: {osAttrDict!r}', osAttrDict=osAttrDict)
		client.close()

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		print('Main Exception: {}'.format(stacktrace))
		client.close()

if __name__ == '__main__':
	sys.exit(psLocalTest())
