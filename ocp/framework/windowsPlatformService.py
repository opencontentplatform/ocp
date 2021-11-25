"""Manages the server side framework as a Windows Service.

Usage::

  $ python windowsPlatformService.py --startup delayed install
  $ python windowsPlatformService.py start
  $ python windowsPlatformService.py stop
  $ python windowsPlatformService.py remove

"""
import sys
import traceback
import os
import time
import multiprocessing
from contextlib import suppress
import logging
## Concurrent-log-handler's version
try:
	from concurrent_log_handler import ConcurrentRotatingFileHandler as RFHandler
except ImportError:
	from warnings import warn
	warn("concurrent_log_handler package not installed. Using builtin log handler")
	## Python's version
	from logging.handlers import RotatingFileHandler as RFHandler

import socket
import win32serviceutil
import servicemanager
import win32event
import win32service


## Add openContentPlatform directories onto the sys path
import env
path = os.path.dirname(os.path.abspath(__file__))
env.addServicePath()
env.addLibPath()
os.chdir(path)

## From openContentPlatform
from transportService import TransportService
from contentGatheringService import ContentGatheringService
from resultProcessingService import ResultProcessingService
from queryService import QueryService
from universalJobService import UniversalJobService
from logCollectionService import LogCollectionService
from apiService import ApiService
from serverSideService import ServerSideService
import utils


class ItdmService(win32serviceutil.ServiceFramework):
	_svc_name_ = 'ITDM_Server'
	_svc_display_name_ = 'ITDM Server'
	_svc_description_ = 'Server component for IT Discovery Machine (ITDM). ITDM is a content gathering and integration framework for CMS solutions, made by CMS Construct (cmsconstruct.com).'

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
		self.servicePlatform()
		print('SvcDoRun stop')


	def serviceLoop(self, settings, logger):
		"""Monitor service managers.

		Starts up the managers and then actively monitor their status.

		Arguments:
		  settings (json) : global settings
		"""
		activeServices = []
		watcherWaitCycle = int(settings['statusReportingInterval'])
		serviceWaitCycle = int(settings['waitSecondsBeforeStartingNextService'])
		exitWaitCycle = int(settings['waitSecondsBeforeExiting'])
		shutdownEvent = multiprocessing.Event()

		## Construct each Service
		transportService = TransportService(shutdownEvent, settings)
		apiService = ApiService(shutdownEvent, settings)
		contentGatheringService = ContentGatheringService(shutdownEvent, settings)
		resultProcessingService = ResultProcessingService(shutdownEvent, settings)
		queryService = QueryService(shutdownEvent, settings)
		universalJobService = UniversalJobService(shutdownEvent, settings)
		logCollectionService = LogCollectionService(shutdownEvent, settings)

		## Add to the list of services
		activeServices.append(transportService)
		activeServices.append(apiService)
		activeServices.append(contentGatheringService)
		activeServices.append(resultProcessingService)
		activeServices.append(queryService)
		activeServices.append(universalJobService)
		activeServices.append(logCollectionService)

		## Conditionally start/add the local service (ServerSideService)
		if settings['startServerSideService']:
			serverSideService = ServerSideService(shutdownEvent, settings)
			activeServices.append(serverSideService)

		## Start the services as separate processes
		for thisService in activeServices:
			thisService.start()
			logger.info('Started {} with PID {}'.format(thisService.name, thisService.pid))
			## Default 2 second sleep between service starts
			time.sleep(serviceWaitCycle)

		logger.info('Status of services:')
		for thisService in activeServices:
			if not thisService.is_alive():
				logger.error('   {}: stopped with exit code [{}]'.format(thisService.name, thisService.exitcode))
			else:
				logger.info('   {}: running'.format(thisService.name))

		## Wait loop
		logger.info('Starting main loop - {}'.format(time.strftime('%X %x')))
		while True:
			try:
				if self.stopFlag:
					raise KeyboardInterrupt()
				## Message on any failing services
				for thisService in activeServices:
					if not thisService.is_alive():
						logger.error('   {}: stopped with exit code [{}]'.format(thisService.name, thisService.exitcode))

				## Avoiding join() with the processes (from the multiprocessing
				## internals), since we're not waiting for them to finish. They
				## will always be running, so this loop is just for monitoring
				## and messaging. Any interrupt signals will be sent to the sub-
				## processes, and intentional shutdown requests are handled here.
				win32event.WaitForSingleObject(self.eventFlag, 10000)

			except (KeyboardInterrupt, SystemExit):
				print('Interrrupt received; notifying services to stop...')
				logger.debug('Interrrupt received; notifying services to stop...')
				shutdownEvent.set()
				## Wait for threads to finish graceful shutdown
				time.sleep(exitWaitCycle)
				break
			except:
				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				logger.debug('Exception in watcher loop: {}'.format(stacktrace))
				logger.debug('Notifying services to stop...')
				shutdownEvent.set()
				time.sleep(exitWaitCycle)
				break

		## end serviceLoop
		return


	def setupLogging(self, globalSettings):
		"""Logger for the parent process."""
		logFiles = setupLogFile('Main', env, globalSettings['fileContainingServiceLogSettings'])
		logObserver  = setupObservers(logFiles, 'Main', env, globalSettings['fileContainingServiceLogSettings'])
		logger = twisted.logger.Logger(observer=logObserver, namespace='Main')
		if not os.path.exists(env.logPath):
			os.makedirs(env.logPath)
		logger.info('Starting Open Content Platform.')
		logger.info(' Main-process identifier (PID): {}.'.format(os.getpid()))
		logger.info(' Started on the command line; press Ctrl+C to exit.')
	
		## end setupLogging
		return logger


	def servicePlatform(self):
		"""Main entry point for the service platform.

		This function loads global settings, sets up logging, calls the service
		flows, waits for completion, and then cleans up.
		"""
		try:
			print('Starting Open Content Platform.\nTo stop, you can use the Services console or invoke the command directly: python {}\windowsPlatformService.py stop'.format(path))
			if not os.path.exists(env.logPath):
				os.makedirs(env.logPath)
			startTime = time.time()

			## Parse global settings
			globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))

			## Setup logging
			logger = self.setupLogging(globalSettings)
			logger.info('Starting Open Content Platform.')
			logger.info(' Main-process identifier (PID): {}'.format(os.getpid()))
			logger.info(' Started from a service; use the Services console to stop, or invoke the command directly:  python {}\windowsPlatformService.py stop'.format(path))

			## Create and monitor the service processes
			self.serviceLoop(globalSettings, logger)

			## Finish up
			endTime = time.time()
			runTime = utils.prettyRunTime(startTime, endTime)
			logger.warning('Open Content Platform stopped. Total runtime was {}'.format(runTime))
			print('Open Content Platform stopped. Total runtime was {}'.format(runTime))

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			## The basic print is here for a console message in case we weren't able
			## to connect the logging mechanism before encountering a failure.
			print('Exception in servicePlatform: {}'.format(stacktrace))
			with suppress(Exception):
				logger.debug(stacktrace)

		## end servicePlatform
		return



if __name__ == '__main__':
	if len(sys.argv) == 1:
		print('initializing')
		servicemanager.Initialize()
		print('2')
		servicemanager.PrepareToHostSingle(ItdmService)
		print('3')
		servicemanager.StartServiceCtrlDispatcher()
		print('4')
	else:
		print('5')
		win32serviceutil.HandleCommandLine(ItdmService)
		print('6')
