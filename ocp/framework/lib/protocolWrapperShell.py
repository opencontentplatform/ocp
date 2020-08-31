"""Wrapper for creating a Shell protocol, inherited by SSH/PowerShell.

Classes:
  |  Shell : wrapper class for Shell

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Feb 22, 2018

"""
import sys
import subprocess
import traceback
import datetime
import re
import time
from time import sleep
from threading import Thread
from queue import Queue, Empty
from contextlib import suppress

import os


class Shell:
	'''Generic wrapper class for Shell.'''

	def __init__(self, runtime, logger, endpoint, protocol, shellExecutable, printDebug=False, sessionTimeout=120, commandTimeout=10, echoCmd='echo', startMarker='OCP:CmdStart', stopMarker='OCP:CmdStop'):
		'''Initialize parameters and start the shell process.'''
		self.runtime = runtime
		self.logger = logger
		self.printDebug = printDebug
		self.endpoint = endpoint
		self.protocol = protocol
		self.shellExecutable = shellExecutable
		self.sessionTimeout = sessionTimeout
		self.commandTimeout = commandTimeout
		self.echo = echoCmd
		self.startMarker = startMarker
		self.stopMarker = stopMarker
		self.startCmd = self.echo + ' ' + self.startMarker
		self.stopCmd  = self.echo + ' ' + self.stopMarker + '\n'
		self.abort = False
		self.process = None
		self.stream = None
		self.streamErr = None


	def log(self, msg):
		'''Mechanism to enable toggling debug logging just in the protocol wrapper.'''
		if self.printDebug:
			## twisted.logger syntax
			self.logger.debug('{msg!r}', msg=msg)


	def reinitialize(self):
		'''This function closes and reopens the shell process.

		This is used when a command times out. Since the session is sharing the
		same I/O pipes across commands, there's no way to recover from a command
		in the middle that hit a timeout. In order to continue using the shell
		for additional commands, it must be closed and re-opened.
		'''
		self.close()
		self.open()
		self.logger.info('Shell reinitialized')


	def send(self, cmd, timeout=None, skipStatusCheck=False):
		'''Entry point for executing commands.'''
		if self.abort:
			self.logger.error('Error occured on session; unable to send additional commands in. Please close the session.')
			return
		## Wrap the command with start/stop markers
		cmdToExecute = self._wrapCommand(cmd)
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
		## Right now I'm supressing error messages; may expose them later.
		self.process.terminate()
		self.process.wait()
		with suppress(Exception):
			self.process.terminate()
		with suppress(Exception):
			self.process.wait()


	def _wrapCommand(self, cmdToExecute):
		'''Wrap each command with markers noting the start and stop.

		This is needed since our shell process is streaming stdin/stdout/stderr
		on shared pipes for the full session, and so we need to capture results
		specific to each individual command.
		'''
		self.log('_wrapCommand: cmd to wrap: {}'.format(str(cmdToExecute)))
		cmdList = []
		cmdList.append(self.startCmd)
		cmdList.append(cmdToExecute)
		cmdList.append(self.stopCmd)
		self.log('_wrapCommand: cmd as list: {}'.format(cmdList))
		## Join into a single string, add line feeds, and encode to bytes
		cmdAsString = '\n'.join(cmdList).encode()
		self.log('_wrapCommand: encoded: {}'.format(cmdAsString))
		return cmdAsString


	def _processResults(self, timeout, skipStatusCheck):
		outputLines = []
		hitProblem = None
		started = False
		shellPrompt = None
		shellPromptLength = 0
		startTime = time.time()
		maxRuntime = startTime + timeout
		strErrors = None
		errorLines = []

		## First get the STDOUT
		while True:
			## Wait for output; non-blocking escape every interval (.2 seconds)
			outputLine = self.stream.readline(.2)
			if outputLine is None:
				## TODO: find STATUS_INVALID_HANDLE / ERROR_OPERATION_ABORTED
				## None of these allow me to determine whether the stream
				## was closed with a Ctrl+C event... and yet on a Ctrl+C at the
				## contentGatheringClient, all active shell protocol connections
				## stop interactive with the STDOUT streams. This seems to be
				## identified by the following bug report tracked in 2016 for
				## Windows v8 and v10 platforms:  bugs.python.org/issue26882
				## For now, we'll just have to gracefully wait for protocols to
				## disconnect and jobs to finish, before stopping the client
				## after it receives a stop event... which may take minutes.
				## ===========================================================
				#self.logger.info('dir(_stream): {stream!r}', stream=dir(self.stream._stream))
				#self.logger.info('_stream.mode: {streamMode!r}', streamMode=self.stream._stream.mode)
				#self.logger.info('_stream.closed: {streamClosed!r}', streamClosed=self.stream._stream.closed)
				#self.logger.info('At Start: _stream._checkClosed(): {checkClosed!r}', checkClosed=self.stream._stream._checkClosed())
				#self.logger.info('At Start: _stream._checkReadable(): {checkReadable!r}', checkReadable=self.stream._stream._checkReadable())
				## Check if the stream is closed (happens on a Ctrl+C event)
				#if self.stream._stream is None:
				#	self.abort = True
				#	raise('Protocol piped stream was closed; this can be caused by a Ctrl+C event.')
				## ===========================================================

				## Check if number of seconds for timeout is exceeded
				now = time.time()
				if now > maxRuntime:
					hitProblem = True
					## Make sure we connected previously, or this becomes an
					## endless connection attempt
					if self.connected:
						## Reinitialize shell connection to 'kill' prev cmd
						self.logger.info('Command timed out!')
						errorLines.append('Command timed out!')
						self.reinitialize()
					else:
						strErrors = 'Unable to connect; attempt timed out.'
					break
			else:
				try:
					outputLine = outputLine.decode('utf8', 'ignore').strip()
					if re.search('\x00', outputLine):
						outputLine = re.sub('\x00', '', outputLine)
					self.log('_processResults: outputLine: {}'.format(outputLine))
					if started:
						## If we know the command has started, watch for the
						## stop marker or for intermediate shell prompts
						if outputLine == self.stopMarker:
							self.log('_processResults: found stopMarker')
							break
						if shellPrompt:
							if shellPrompt == outputLine[:shellPromptLength]:
								## If the line starts with the shell prompt
								## string, then assume it is the echo output
								## of the requested cmd; drop from outputLines.
								continue
						outputLines.append(outputLine)
					else:
						## If the command hasn't yet started, watch for the
						## start of the wrapped command to capture the prompt
						m = re.search('^(.*)' + self.startCmd, outputLine)
						if m:
							shellPrompt = m.group(1)
							shellPromptLength = len(shellPrompt)
							self.log('_processResults: found shell prompt: {}'.format(shellPrompt))
							continue
						if outputLine.strip() == self.startMarker:
							started = True
							self.log('_processResults: found startMarker')
							continue
				except:
					self.logger.error('protocol exception: {exception!r}', exception=str(sys.exc_info()[1]))

		## Now get the STDERR
		while True:
			try:
				errorLine = self.streamErr.readline(.1)
				if errorLine is None:
					break
				errorLine = errorLine.decode('utf8', 'ignore').strip()
				if re.search('\x00', errorLine):
					errorLine = re.sub('\x00', '', errorLine)
				errorLines.append(errorLine)
				self.log('_processResults: ... error line: {}'.format(str(errorLine)))
			except:
				self.logger.debug('protocol exception: {exception!r}', exception=str(sys.exc_info()[1]))
				break

		## Finishing touches on the results...
		if len(errorLines) > 0:
			strErrors = '\n'.join(errorLines)
		## Check the last line of output for the $? exit status
		strResult = '\n'.join(outputLines)
		outputLength = len(outputLines)
		if not skipStatusCheck and outputLength > 0:
			self.log('_processResults: status check')
			lastLine = outputLines[-1]
			self.log('_processResults: last line in result: {}'.format(lastLine))
			outputLength = len(outputLines)
			if re.search(self.exitStatusFailRegEx, lastLine):
				hitProblem = True
				if outputLength > 1:
					strResult = '\n'.join(outputLines[:-1])
			elif re.search(self.exitStatusPassRegEx, lastLine):
				hitProblem = False
				if outputLength > 1:
					strResult = '\n'.join(outputLines[:-1])
			else:
				self.log('Exit status [{} or {}] not found in: [{}]'.format(self.exitStatusFailRegEx, self.exitStatusPassRegEx, lastLine))

		## May have received a passing exit status but also received errors on
		## STDERR; PS scripts vs commands vs cmdlets - work with $? differently.
		if len(errorLines) > 0:
			self.log('_processResults: forcing hitProblem since we had STDERR')
			hitProblem = True

		## end _processResults
		return (strResult, strErrors, hitProblem)


class NonBlockingStreamReader:
	'''Non-blocking stream reader class, used in shell I/O.

	This class mostly comes from the following post:
	https://gist.github.com/EyalAr/7915597

	It's modified for python v3 and to use a loop iterator instead
	of a potentially blocking readline call from the stream.
	'''
	def __init__(self, stream):
		self._stream = stream
		self._queue = Queue()
		self.quit = False

		def _populateQueue(stream, queue):
			try:
				for line in iter(stream.readline, b''):
					if line:
						queue.put(line)
					else:
						print('breaking out of _populateQueue')
						break
			except ValueError:
				## These ValueError exceptions mean we need to stop as well:
				## PyMemoryView_FromBuffer(): info->buf must not be NULL
				pass
			except:
				raise

		self._thread = Thread(target=_populateQueue, args=(self._stream, self._queue))
		self._thread.start()

	def readline(self, timeout=None):
		try:
			return self._queue.get(block=timeout is not None, timeout=timeout)
		except Empty:
			return None
