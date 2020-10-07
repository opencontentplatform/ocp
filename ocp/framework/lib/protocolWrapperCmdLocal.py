"""Wrapper for using a local Windows cmd.exe terminal on the client.

This terminal is running "local" to the client; it's not a remote session. The
reason for using this class instead subprocess.Popen() directly, is to enable
a long-standing shell environment where all commands are executed in the same
runtime. It's also a convenience wrapper implementing command timeouts, shell
resets, and data pipes.


Classes:
  |  CmdLocal : wrapper class for a local cmd terminal

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


class CmdLocal(Shell):
	"""Wrapper class for local cmd terminal."""
	def __init__(self, runtime, logger, **kwargs):
		if ('shellExecutable' not in kwargs or kwargs['shellExecutable'] is None):
			#kwargs['shellExecutable'] = 'C:\\WINDOWS\\System32\\cmd.exe'
			#kwargs['shellExecutable'] = '%windir%\system32\cmd.exe'
			kwargs['shellExecutable'] = 'cmd.exe'
		kwargs['echoCmd'] = 'echo'
		self.exitStatusCheck = 'echo %errorlevel%'
		self.exitStatusPassRegEx = '^0$'
		self.exitStatusFailRegEx = '^[^0]$'
		self.joinCmd = ' && '
		super().__init__(runtime, logger, None, None, **kwargs)
		self.kwargs = kwargs
		self.connected = False
		self.log('init {}'.format(__name__))


	def open(self):
		"""Initialize terminal and establish pipes.

		This calls subprocess.Popen to start a local terminal process. It then
		interacts with the process using the internal pipes; sending commands in
		by writing to STDIN and reading results by reading/buffering from STDOUT
		and STDERR. It avoids the subprocess.communicate() method because that
		cleans up and shuts down after a single command (or set of commands that
		must be provided up front), and we have no context of number of commands
		desired by the job.
		"""
		## Random delay to avoid 100 threads starting terminals at the same time
		time.sleep(random.uniform(0,1))

		self.log('open: Popen starting')
		self.process = subprocess.Popen([self.shellExecutable], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
		self.log('open: Popen finished')

		self.log('open: wrapping pipes with NonBlockingStreamReader')
		self.stream = NonBlockingStreamReader(self.process.stdout)
		self.streamErr = NonBlockingStreamReader(self.process.stderr)

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
			cmdToExecute = self._wrapCommand(cmd)
		else:
			cmdToExecute = self._wrapCommand(cmd + self.joinCmd + self.exitStatusCheck)

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
		self.log('close protocolWrapperPowerShell')
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
		results = client.run('systeminfo')
		logger.debug('systeminfo results:\n{results!r}', results=results)
		tmpDict = {}

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in queryOperatingSystem: {stacktrace!r}', stacktrace=stacktrace)
	return


def cmdLocalTest():
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

		client = CmdLocal(logger)
		name = client.open()
		logger.debug('name: {name!r}', name=name)

		logger.debug('sleep should timeout and reinitialize shell...')
		results = client.run('timeout 5', timeout=2)
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
	sys.exit(cmdLocalTest())
