"""Client side framework for the Open Content Platform.

This script spins up an instance of the desired client.

Functions:
  * :func:`clientWrapper` : entry point
  * :func:`setupLogging` : setup requested log handlers
  * :func:`basicSetup` : resolve dependencies and pre-reqs for client startup
  * :func:`spinUpTheClient` : load client libraries and start the process
  * :func:`clientLoop` : monitor active client process

"""
import sys
import traceback
import os
import platform
import time
import logging, logging.handlers
import multiprocessing
from contextlib import suppress

## Add openContentPlatform directories onto the sys path
import env
path = os.path.dirname(os.path.abspath(__file__))
env.addClientPath()
env.addLibPath()
os.chdir(path)

## From openContentPlatform
import utils
from twisted.internet import reactor, task, ssl
from twisted.python.filepath import FilePath

## Global section
osType = platform.system()


def spinUpTheClient(logger, clientType, settings, shutdownEvent, canceledEvent, watcherPID):
	"""Load the appropriate client library and start the process."""
	thisClient = None
	ClientEntryPoint = None
	## Construct the client
	if clientType.lower() == 'contentgathering':
		from contentGatheringClient import ContentGatheringClient as ClientEntryPoint
	elif clientType.lower() == 'universaljob':
		from universalJobClient import UniversalJobClient as ClientEntryPoint
	elif clientType.lower() == 'resultprocessing':
		from resultProcessingClient import ResultProcessingClient as ClientEntryPoint
	thisClient = ClientEntryPoint(shutdownEvent, canceledEvent, settings)
	## Start the client as a separate process
	thisClient.start()
	logger.info('Starting child process...')
	logger.info('  Main client watcher process running on PID {}'.format(watcherPID))
	logger.info('  client {} running on child process with PID {}'.format(thisClient.name, thisClient.pid))

	## end spinUpTheClient
	return thisClient


def clientLoop(clientType, settings):
	"""Start and monitor the client.

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
	canceledEvent = multiprocessing.Event()
	watcherPID = os.getpid()
	logger = logging.getLogger('ClientStatus')

	## Construct and start the client
	thisClient = spinUpTheClient(logger, clientType, settings, shutdownEvent, canceledEvent, watcherPID)

	## Wait loop
	logger.info('Starting client watcher loop - {}'.format(time.strftime('%X %x')))
	while True:
		try:
			## Evaluate the running client
			if thisClient.is_alive() and canceledEvent is not None and canceledEvent.is_set():
				## If the child process is requesting a restart
				logger.error('  {}: still alive (PID: {}), but requested a restart'.format(thisClient.name, thisClient.pid))
				thisClient.terminate()
				canceledEvent.clear()
				del thisClient
				thisClient = spinUpTheClient(logger, clientType, settings, shutdownEvent, canceledEvent, watcherPID)
				logger.info('    Started {} with PID {}'.format(thisClient.name, thisClient.pid))

			elif not thisClient.is_alive():
				logger.error('  {}: stopped with exit code {}.'.format(thisClient.name, thisClient.exitcode))

				## If the child process is requesting a restart
				if canceledEvent is not None and canceledEvent.is_set():
					logger.info('    Client {} requested a restart'.format(thisClient.name))
					canceledEvent.clear()
					del thisClient
					thisClient = spinUpTheClient(logger, clientType, settings, shutdownEvent, canceledEvent, watcherPID)
					logger.info('    Started {} with PID {}'.format(thisClient.name, thisClient.pid))

				## If something went wrong, conditionally restart the client
				else:
					thisErrorTime = int(time.time())
					if firstErrorTime is None or ((thisErrorTime - firstErrorTime) > restartThresholdTimeframe):
						## Re-initialize if timeframe has passed w/o passing max errors
						firstErrorTime = thisErrorTime
						errorCount = 0
					errorCount += 1
					if errorCount <= restartThresholdMaxErrors:
						del thisClient
						## Restart the client
						thisClient = spinUpTheClient(logger, clientType, settings, shutdownEvent, canceledEvent, watcherPID)
						logger.info('Restarted the stopped client. Restart count {}.'.format(errorCount))
					else:
						logger.error('Too many restarts within the client restart threshold timeframe. Exiting...')
						raise EnvironmentError('Client stopped more than it was allowed to auto-restart in the provided timeframe. Watcher loop shutting down.')
			else:
				#logger.debug('Status of {}: running with PID {} and PPID {}'.format(thisClient.name, thisClient.pid, watcherPID))
				logger.debug('  {}: running'.format(thisClient.name))

			## Avoiding join() with the processes (from the multiprocessing
			## internals), since we're not waiting for them to finish. They
			## will always be running, so this loop is just for monitoring
			## and messaging. Any interrupt signals will be sent to the sub-
			## processes, and intentional shutdown requests are handled here.
			time.sleep(watcherWaitCycle)

		except (KeyboardInterrupt, SystemExit):
			logger.info('Status of {}: interrupt received... shutting down PID [{}]'.format(thisClient.name, thisClient.pid))
			print('Interrrupt received; notifying client process [{}] to stop...'.format(thisClient.pid))
			logger = logging.getLogger('ClientStartup')
			logger.error('Interrrupt received; notifying services to stop...')
			shutdownEvent.set()
			## Wait for thread to finish graceful shutdown
			time.sleep(exitWaitCycle)
			try:
				print('Checking if client process is still running')
				if thisClient.is_alive():
					print('Stopping client process in clientLoop...')
					with suppress(Exception):
						logger.debug('  process still running; stopping {} with PID {}'.format(thisClient.name, thisClient.pid))
					thisClient.terminate()
			except:
				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				print('Exception in killing process in clientLoop: {}'.format(stacktrace))
				with suppress(Exception):
					logger.debug('Exception in killing process in clientLoop: {}'.format(stacktrace))
			break
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			logger.info('Status of {}: exception hit... shutting down PID [{}]'.format(thisClient.name, thisClient.pid))
			print('Exception in watcher loop: {}'.format(stacktrace))
			print('Notifying client process [{}] to stop...'.format(thisClient.pid))
			with suppress(Exception):
				logger = logging.getLogger('ClientStartup')
				logger.error('Exception in watcher loop: {}'.format(stacktrace))
				logger.debug('Notifying services to stop...')
			shutdownEvent.set()
			time.sleep(exitWaitCycle)
			break

	## end clientLoop
	return


def setupLogging(logPath, fileContainingLogSettings):
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


def basicSetup(argv):
	"""Resolve basic dependencies and pre-reqs for client startup."""
	if not os.path.exists(env.logPath):
		os.makedirs(env.logPath)
	## Setup master Twisted catch-all log
	utils.masterLog(env, 'openContentClientMasterLog')
	## Parse global settings
	globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))
	## Setup requested log handlers
	setupLogging(env.logPath, os.path.join(env.configPath, globalSettings['fileContainingClientLogSettings']))
	logger = logging.getLogger('ClientStartup')
	## Ensure the command specified the desired client type
	if len(argv) != 2 or argv[1].lower() not in ['contentgathering', 'resultprocessing', 'universaljob']:
		print('\nPlease pass the client type as an input parameter. Usage:\n  $ python {} [contentGathering|universalJob|resultProcessing]\n'.format(__file__))
		logger.error('Please pass the client type as an input parameter.')
		raise EnvironmentError('Please pass the client type as an input parameter.')

	logger.info('Starting client {}'.format(argv[1]))
	logger.info(' Main-process identifier (PID): {}'.format(os.getpid()))
	logger.info(' Started on the command line; press Ctrl+C to exit.')

	## end basicSetup
	return globalSettings


def clientWrapper(argv):
	"""Entry point for an Open Content Platform client.

	This function loads global settings, sets up logging, calls the service
	flows, waits for completion, and then cleans up.

	Usage::

	  $ python openContentClient.py [contentGathering|universalJob|resultProcessing]

	"""
	try:
		startTime = time.time()
		globalSettings = basicSetup(argv)

		## Create and monitor the client process
		clientLoop(argv[1], globalSettings)

		logger = logging.getLogger('ClientStartup')
		endTime = time.time()
		runTime = utils.prettyRunTime(startTime, endTime)
		logger.warning('Client stopped. Total runtime was {}'.format(runTime))
		print('Client stopped. Total runtime was {}'.format(runTime))

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		## The basic print is here for a console message in case we weren't able
		## to connect the logging mechanism before encountering a failure.
		print('Exception in clientWrapper: {}'.format(stacktrace))
		with suppress(Exception):
			logger.debug(stacktrace)

	## end clientWrapper
	return


if __name__ == '__main__':
	sys.exit(clientWrapper(sys.argv))
