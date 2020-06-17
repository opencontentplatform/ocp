"""Server side framework for the Open Content Platform.

This script starts the server components; it handles spinning up the service
managers in separate processes and periodic reporting on those processes.

Functions:
  * :func:`servicePlatform` : entry point
  * :func:`setupLogging` : setup requested log handlers
  * :func:`serviceLoop` : monitor service managers

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Aug 17, 2017

"""
import sys
import traceback
import os
import platform
import time
import copy
import signal
import multiprocessing
from contextlib import suppress
import twisted.logger

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
from utils import loadSettings, setupLogFile, setupObservers, prettyRunTime

## Global section
osType = platform.system()


def signalAbort(signal, frame):
	"""After waiting for a clean exit (SIGTERM), just abort (SIGKILL)."""
	print('Signal time limit hit after waiting for clean exit. Aborting at {}'.format(time.ctime()))
	sys.exit(1)


def signalHandler(sigNum, frame):
	"""Catch signals from the OS; required for Linux."""
	message = 'Received signal {}'.format(sigNum)
	print(message)
	## Call signalAbort in 10 seconds; this isn't available on Windows
	if osType != 'Windows':
		signal.signal(signal.SIGALRM, signalAbort)
		signal.alarm(10)
	## Raise exception so the service loop properly notifies all sub-processes
	raise SystemExit(message)


def getNewEvent(shutdownEvents):
	"""Get a new shutdownEvent and add it to the managed list."""
	shutdownEvent = multiprocessing.Event()
	shutdownEvents.append(shutdownEvent)
	return shutdownEvent


def registerSignals():
	"""Register any signals that should be caught and handled.
	This is needed for Linux daemon shutdown and can be leveraged on Windows.
	Note, that only the following signals are valid on Windows:
	  SIGABRT, SIGFPE, SIGILL, SIGINT, SIGSEGV, SIGTERM, or SIGBREAK
	ValueError is raised for all other signals on Windows.
	"""
	validSignals = []
	if osType == 'Windows':
		validSignals = [signal.SIGINT, signal.SIGABRT, signal.SIGFPE,
						signal.SIGSEGV, signal.SIGTERM, signal.SIGBREAK]
	else:
		validSignals = [signal.SIGHUP, signal.SIGINT, signal.SIGQUIT,
						signal.SIGTRAP, signal.SIGABRT, signal.SIGBUS,
						signal.SIGFPE, signal.SIGUSR1, signal.SIGSEGV,
						signal.SIGUSR2, signal.SIGPIPE, signal.SIGALRM,
						signal.SIGTERM]
	for validSignal in validSignals:
		signal.signal(validSignal, signalHandler)


def serviceLoop(logger, settings):
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

	transportService = TransportService(shutdownEvent, copy.deepcopy(settings))
	apiService = ApiService(shutdownEvent, copy.deepcopy(settings))
	contentGatheringService = ContentGatheringService(shutdownEvent, copy.deepcopy(settings))
	resultProcessingService = ResultProcessingService(shutdownEvent, copy.deepcopy(settings))
	queryService = QueryService(shutdownEvent, copy.deepcopy(settings))
	universalJobService = UniversalJobService(shutdownEvent, copy.deepcopy(settings))
	logCollectionService = LogCollectionService(shutdownEvent, copy.deepcopy(settings))

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
		serverSideService = ServerSideService(shutdownEvent, copy.deepcopy(settings))
		activeServices.append(serverSideService)

	## Start the services as separate processes
	for thisService in activeServices:
		thisService.start()
		logger.info('  Started {} with PID {}'.format(thisService.name, thisService.pid))
		## Default 2 second sleep between service starts
		time.sleep(serviceWaitCycle)

	## Wait loop
	logger.info('Starting main loop - {}'.format(time.strftime('%X %x')))
	while True:
		try:
			logger.info('Status of services:')
			## Evaluate the running services
			for thisService in activeServices:
				if not thisService.is_alive():
					logger.error('   {}: stopped with exit code [{}]'.format(thisService.name, thisService.exitcode))
				else:
					logger.info('   {}: running'.format(thisService.name))

			## Avoiding join() with the processes (from the multiprocessing
			## internals), since we're not waiting for them to finish. They
			## will always be running, so this loop is just for monitoring
			## and messaging. Any interrupt signals will be sent to the sub-
			## processes, and intentional shutdown requests are handled here.
			time.sleep(watcherWaitCycle)

		except (KeyboardInterrupt, SystemExit):
			print('Interrupt received; notifying services to stop...')
			logger.debug('Interrupt received; notifying services to stop...')
			shutdownEvent.set()
			## Wait for threads to finish graceful shutdown
			time.sleep(exitWaitCycle)
			## Kill any process that is still running
			for thisService in activeServices:
				try:
					logger.debug('Evaluating {} with PID {}'.format(thisService.name, thisService.pid))
					if thisService.is_alive():
						logger.debug('Attempting to kill {} with PID {}'.format(thisService.name, thisService.pid))
						thisService.terminate()
				except:
					exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
					print('Exception in killing process in serviceLoop: {}'.format(str(exceptionOnly)))
					with suppress(Exception):
						logger.debug('Exception in killing process in clientLoop: {}'.format(str(exceptionOnly)))
			break
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			print('Exception in watcher loop: {}'.format(stacktrace))
			logger.debug('Exception in watcher loop: {}'.format(str(stacktrace)))
			logger.debug('Notifying services to stop...')
			shutdownEvent.set()
			time.sleep(exitWaitCycle)
			break

	## end serviceLoop
	return


def setupLogging(globalSettings):
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


def servicePlatform():
	"""Entry point for the Open Content Platform.

	This function loads global settings, sets up logging, calls the service
	flows, waits for completion, and then cleans up.

	Usage::
	  $ python openContentPlatform.py

	"""
	try:
		print('Starting Open Content Platform.')
		print(' Main-process identifier (PID): {}.'.format(os.getpid()))
		print(' Press Ctrl+C to exit.\n'.format(os.getpid()))
		## Parse global settings
		globalSettings = loadSettings(os.path.join(env.configPath, 'globalSettings.json'))
		startTime = time.time()
		## Setup logging
		logger = setupLogging(globalSettings)
		## Register signals
		registerSignals()
		## Create and monitor the service processes
		serviceLoop(logger, globalSettings)
		## Finish up
		endTime = time.time()
		runTime = prettyRunTime(startTime, endTime)
		logger.debug('Open Content Platform stopped. Total runtime was {}'.format(runTime))
		print('Open Content Platform stopped. Total runtime was {}'.format(runTime))

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		## The print is here for a console message in case we weren't able
		## to connect the logging mechanism before encountering a failure.
		print('Exception in servicePlatform: {}'.format(stacktrace))
		with suppress(Exception):
			logger.debug(str(stacktrace))

	## end servicePlatform
	return


if __name__ == '__main__':
	sys.exit(servicePlatform())
