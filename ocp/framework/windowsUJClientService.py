"""Manages the client side framework as a Windows Service.

Usage::

  $ python windowsUJClientService.py --startup delayed install
  $ python windowsUJClientService.py start
  $ python windowsUJClientService.py stop
  $ python windowsUJClientService.py remove

"""
import sys
import traceback
import os
import time
import logging, logging.handlers
import socket
import win32serviceutil
import servicemanager
import win32event
import win32service
import multiprocessing
from contextlib import suppress
from twisted.internet import reactor, task, ssl
from twisted.python.filepath import FilePath

## Add openContentPlatform directories onto the sys path
import env
env.addClientPath()
env.addLibPath()
path = os.path.dirname(os.path.abspath(__file__))
os.chdir(path)
## From openContentPlatform
import utils
from universalJobClient import UniversalJobClient
clientLabel = 'ITDM Universal Job Client'


class ItdmClientService(win32serviceutil.ServiceFramework):
	_svc_name_ = 'ITDM_UniversalJob'
	_svc_display_name_ = clientLabel
	_svc_description_ = 'Client component for IT Discovery Machine (ITDM). ITDM is a content gathering and integration framework for CMS solutions, made by CMS Construct (cmsconstruct.com).'

	def parse_command_line(cls):
		win32serviceutil.HandleCommandLine(cls)

	def __init__(self, args):
		print('initializing')
		win32serviceutil.ServiceFramework.__init__(self, args)
		self.eventFlag = win32event.CreateEvent(None, 0, 0, None)
		socket.setdefaulttimeout(60)

	def SvcStop(self):
		print('SvcStop')
		self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
		win32event.SetEvent(self.eventFlag)
		self.stopFlag = True

	def SvcDoRun(self):
		print('SvcDoRun start')
		self.stopFlag = False
		servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE, servicemanager.PYS_SERVICE_STARTED, (self._svc_name_, ''))
		self.serviceClient()
		print('SvcDoRun stop')

	def setupLogging(self, logPath, fileContainingLogSettings):
		"""Setup requested log handlers.

		Arguments:
		  logPath (str)                   : string containing path to the log directory
		  fileContainingLogSettings (str) : config file path for log settings
		"""
		## Open defined configurations
		logSettings = utils.loadSettings(fileContainingLogSettings)
		## Create if they don't exist
		thisPath = os.path.join(logPath, 'client')
		if not os.path.exists(thisPath):
			os.makedirs(thisPath)
		for entityName in ['ClientStartup', 'ClientStatus']:
			## Set each log handler as defined; no reason to wrap with exception
			## handling yet because we haven't established the logs to report it
			logEntry = logSettings.get(entityName)
			logFile = os.path.join(logPath, logEntry.get('fileName'))
			logger = logging.getLogger(entityName)
			logger.setLevel(logEntry.get('logLevel'))
			thisHandler = logging.handlers.RotatingFileHandler(logFile,
															   maxBytes=int(logEntry.get('maxSizeInBytes')),
															   backupCount=int(logEntry.get('maxRollovers')))
			fmt = logging.Formatter(logEntry.get('lineFormat'), datefmt = logEntry.get('dateFormat'))
			thisHandler.setFormatter(fmt)
			logger.addHandler(thisHandler)

		## end setupLogging
		return


	def spinUpTheClient(self, logger, settings, shutdownEvent, watcherPID):
		## Construct the client
		thisClient = UniversalJobClient(shutdownEvent, settings)
		## Start the client as a separate process
		thisClient.start()
		clientPID = thisClient.pid
		logger.info('Starting child process...')
		logger.info('  Main client watcher process running on PID {}'.format(watcherPID))
		logger.info('  client {} running on child process with PID {}'.format(thisClient.name, thisClient.pid))

		return (thisClient, clientPID)


	def clientLoop(self, settings):
		"""Startup and monitor the client.

		Arguments:
		  settings (json) : global settings
		"""
		logger = logging.getLogger('ClientStartup')
		errorCount = 0
		firstErrorTime = None
		restartThresholdMaxErrors = int(settings.get('clientRestartThresholdMaxCountInTimeframe', 5))
		restartThresholdTimeframe = int(settings.get('clientRestartThresholdTimeframeInSeconds', 600))
		watcherWaitCycle = int(settings.get('statusReportingInterval'))
		exitWaitCycle = int(settings.get('waitSecondsBeforeExiting'))
		shutdownEvent = multiprocessing.Event()
		watcherPID = os.getpid()

		## Construct and start the client
		(thisClient, clientPID) = self.spinUpTheClient(logger, settings, shutdownEvent, watcherPID)

		## Wait loop
		logger = logging.getLogger('ClientStatus')
		logger.info('Starting client watcher loop - {}'.format(time.strftime('%X %x')))
		while True:
			try:
				if self.stopFlag:
					raise KeyboardInterrupt()
				## Evaluate the running client
				if not thisClient.is_alive():
					logger.error('Status of {}: client on PID {} stopped with exit code {}.'.format(thisClient.name, clientPID, thisClient.exitcode))
					thisErrorTime = int(time.time())
					if firstErrorTime is None or ((thisErrorTime - firstErrorTime) > restartThresholdTimeframe):
						## Re-initialize if timeframe has passed w/o passing max errors
						firstErrorTime = thisErrorTime
						errorCount = 0
					errorCount += 1
					if errorCount <= restartThresholdMaxErrors:
						del thisClient
						## Restart the client
						(thisClient, clientPID) = self.spinUpTheClient(logger, settings, shutdownEvent, watcherPID)
						logger = logging.getLogger('ClientStatus')
						logger.info('Restarted client. Restart count {}.'.format(errorCount))
					else:
						raise EnvironmentError('Client stopped more than it was allowed to auto-restart in the provided timeframe. Watcher loop shutting down.')
				else:
					logger.info('Status of {}: running with PID {} and PPID {}'.format(thisClient.name, clientPID, watcherPID))

				## Avoiding join() with the processes (from the multiprocessing
				## internals), since we're not waiting for them to finish. They
				## will always be running, so this loop is just for monitoring
				## and messaging. Any interrupt signals will be sent to the sub-
				## processes, and intentional shutdown requests are handled here.
				win32event.WaitForSingleObject(self.eventFlag, 10000)

			except (KeyboardInterrupt, SystemExit):
				print('Interrrupt received; notifying services to stop...')
				logger = logging.getLogger('ClientStartup')
				logger.debug('Interrrupt received; notifying services to stop...')
				shutdownEvent.set()
				## Wait for threads to finish graceful shutdown
				time.sleep(exitWaitCycle)
				break
			except:
				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				print('Exception in watcher loop: {}'.format(stacktrace))
				logger = logging.getLogger('ClientStartup')
				logger.debug('Exception in watcher loop: {}'.format(stacktrace))
				logger.debug('Notifying services to stop...')
				shutdownEvent.set()
				time.sleep(exitWaitCycle)
				break

		## end clientLoop
		return


	def serviceClient(self):
		"""Main entry point for the service platform.

		This function loads global settings, sets up logging, calls the service
		flows, waits for completion, and then cleans up.
		"""
		try:
			print('Starting Open Content Platform.\nTo stop, you can use the Services console or invoke the command directly: python {} stop'.format(__file__))
			if not os.path.exists(env.logPath):
				os.makedirs(env.logPath)
			utils.masterLog(env, 'openContentClientMasterLog')
			## Parse global settings
			settings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))
			## Setup requested log handlers
			startTime = time.time()
			self.setupLogging(env.logPath, os.path.join(env.configPath, settings['fileContainingClientLogSettings']))
			logger = logging.getLogger('ClientStartup')
			logger.info('Starting {}'.format(clientLabel))
			logger.info(' Main-process identifier (PID): {}'.format(os.getpid()))
			logger.info(' Started from a service; use the Services console to stop, or invoke the command directly:  python {} stop'.format(__file__))
			## Create and monitor the service processes
			self.clientLoop(settings)
			## Finish up
			logger = logging.getLogger('ClientStartup')
			endTime = time.time()
			runTime = utils.prettyRunTime(startTime, endTime)
			logger.warning('Stopped {}. Total runtime was {}'.format(clientLabel, runTime))
			print('Stopped {}. Total runtime was {}'.format(clientLabel, runTime))

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			## The basic print is here for a console message in case we weren't able
			## to connect the logging mechanism before encountering a failure.
			print('Exception in serviceClient: {}'.format(stacktrace))
			with suppress(Exception):
				logger.debug(stacktrace)

		## end serviceClient
		return


if __name__ == '__main__':
	if len(sys.argv) == 1:
		servicemanager.Initialize()
		servicemanager.PrepareToHostSingle(ItdmClientService)
		servicemanager.StartServiceCtrlDispatcher()
	else:
		win32serviceutil.HandleCommandLine(ItdmClientService)
