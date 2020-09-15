"""Transport Service.

This module starts the tcp framework used by services; the actual functions can
be found in the serviceCommunication module.

Classes:

  * :class:`.TransportService` : class for this service

The entry class for this module is :class:`.TransportService`, which does the
setup required for API resources to be hosted through the selected technologies.


.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Mar 25, 2018

"""
import os
import sys
import traceback
from contextlib import suppress
import multiprocessing

## Different logger options
###########################################################################
## Python's base
import logging
from logging.handlers import RotatingFileHandler as RFHandler
## Twisted's version
from twisted.logger import Logger as twistedLogger
## Multiprocessing version to wrap the rotating file handler
import multiprocessing_logging
###########################################################################

## Add openContentPlatform directories onto the sys path
import env
env.addLibPath()

## From openContentPlatform
from utils import loadSettings, setupLogFile, setupObservers
from utils import pidEntryService, pidRemoveService
from database.connectionPool import DatabaseClient
import serviceCommunication


class TransportService(multiprocessing.Process):
	"""Entry class for the transportService manager."""

	def __init__(self, shutdownEvent, settings):
		"""Constructor for the TransportService.

		Arguments:
		  shutdownEvent : event used to control graceful shutdown
		  settings      : global settings; used to direct this manager

		"""
		try:
			self.serviceName = 'TransportService'
			self.multiProcessingLogContext = 'ServiceCommunication'
			self.shutdownEvent = shutdownEvent
			self.listeningPort = int(settings.get('transportServicePort'))
			self.serviceEndpoint = settings.get('transportIpAddress')
			self.useCertificates = settings.get('useCertificates', True)
			self.globalSettings = settings
			super().__init__()
		except:
			print('Exception in TransportService:')
			print(traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2]))


	def getLocalLogger(self):
		"""Setup a log handler."""
		logFiles = setupLogFile(self.serviceName, env, self.globalSettings['fileContainingServiceLogSettings'], directoryName='service')
		logObserver  = setupObservers(logFiles, 'TransportService', env, self.globalSettings['fileContainingServiceLogSettings'])
		self.logger = twistedLogger(observer=logObserver, namespace='TransportService')
		self.logger.info('Started logger for {serviceName!r}', serviceName=self.serviceName)

		## end getLocalLogger
		return


	def getSharedLogger(self):
		"""Create an asynchronous shared logger to be used by the WSGI threads."""
		## Open defined configurations
		logSettingsFileName = self.globalSettings['fileContainingServiceLogSettings']
		## Create requested shared log handler for the threads
		logSettings = loadSettings(os.path.join(env.configPath, logSettingsFileName))
		logSettings = logSettings.get(self.multiProcessingLogContext)
		logFile = os.path.join(env.logPath, 'service', logSettings.get('fileName'))
		sharedLogger = logging.getLogger(self.multiProcessingLogContext)
		sharedLogger.setLevel(logSettings.get('logLevel'))
		mainHandler = RFHandler(logFile, maxBytes=int(logSettings.get('maxSizeInBytes')), backupCount=int(logSettings.get('maxRollovers')))
		fmt = logging.Formatter(logSettings.get('lineFormat'), datefmt = logSettings.get('dateFormat'))
		mainHandler.setFormatter(fmt)
		sharedLogger.addHandler(mainHandler)

		## Setup a queue for all the threads/processes to send messages through,
		## so we are only writing to the log from the main thread
		multiprocessing_logging.install_mp_handler()

		## Initialize the log
		sharedLogger.info('Initializing log from transportService')
		self.logger.info('Initialized shared log')

		## end getSharedLogger
		return


	def getSharedDbPool(self):
		"""Create a global context for sharing a DB connection pool.

		When using a scoped_session in sqlalchemy, the code checks if there was
		a previous thread-local session created. If one already exists then
		sqlalchemy will reuse it. This shares a DB pool across connections.
		"""
		dbClient = DatabaseClient(self.logger, globalSettings=self.globalSettings, env=env, poolSize=2, maxOverflow=1, poolRecycle=1800)
		if dbClient is None:
			self.logger.error('Failed to connect to shared database pool.')
			raise EnvironmentError('Failed to connect to shared database pool.')
		dbClient.session.close()
		dbClient.session.remove()
		dbClient.close()
		self.logger.info('Created the SqlAlchemy connection pool.')

		## end getSharedDbPool
		return


	def run(self):
		"""Override Process run method to provide a custom wrapper for the API.

		This provides a continuous loop for watching the service while keeping
		an ear open to the main process from openContentPlatform, listening for
		any interrupt requests.

		"""
		## Setup requested log handler
		try:
			## Twisted imports here to avoid issues with epoll on Linux
			from twisted.internet import reactor, ssl
			from twisted.python.filepath import FilePath
			from twisted.web.server import Site
			from twisted.web.wsgi import WSGIResource
			from twisted.python.threadpool import ThreadPool

			print('Starting {}'.format(self.serviceName))
			self.getLocalLogger()
			self.logger.info('Starting {}'.format(self.serviceName))
			self.logger.info('Setting up service communication...')

			## Setup shared resources for our WSGIResource instances to use
			self.getSharedLogger()
			self.getSharedDbPool()
			## Create a PID file for system administration purposes
			pidEntryService(self.serviceName, env, self.pid)
			## Reference the magic WSGI throwable from the module using Hug
			application = serviceCommunication.__hug_wsgi__

			## Setup the WSGI to be hosted through Twisted's web server
			wsgiThreadPool = ThreadPool()
			wsgiThreadPool.start()
			## For some reason the system event wasn't working all the time,
			## so I'm adding an explicit wsgiThreadPool.stop() below as well,
			## which was needed before reactor.stop() would properly cleanup.
			reactor.addSystemEventTrigger('after', 'shutdown', wsgiThreadPool.stop)
			resource = WSGIResource(reactor, wsgiThreadPool, application)
			self.logger.info('calling listener on {}:{}.'.format(str(self.serviceEndpoint), self.listeningPort))
			if self.useCertificates:
				## Use TLS to encrypt the communication
				certData = FilePath(os.path.join(env.configPath, 'server_cert_private.pem')).getContent()
				certificate = ssl.PrivateCertificate.loadPEM(certData)
				reactor.listenSSL(self.listeningPort, Site(resource), certificate.options())
			else:
				## Plain text communication
				reactor.listenTCP(self.listeningPort, Site(resource), interface=self.serviceEndpoint)
			## Normally we'd just call reactor.run() here and let twisted handle
			## the wait loop while watching for signals. The problem is that we
			## need openContentPlatform (parent process) to manage this process.
			## So this is a bit hacky in that I'm using the reactor code, but I
			## am manually calling what would be called if I just called run():
			reactor.startRunning()
			## Start event wait loop
			while reactor._started and not self.shutdownEvent.is_set():
				try:
					## Four lines from twisted.internet.main.mainloop:
					reactor.runUntilCurrent()
					t2 = reactor.timeout()
					t = reactor.running and t2
					reactor.doIteration(t)

				except:
					exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					self.logger.error('Exception in {}: {}'.format(self.serviceName, str(exception)))
					break
			if self.shutdownEvent.is_set():
				self.logger.info('Process received shutdownEvent')
			with suppress(Exception):
				wsgiThreadPool.stop()
			with suppress(Exception):
				reactor.stop()

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in {}: {}'.format(self.serviceName, str(exception)))

		## Cleanup
		pidRemoveService(self.serviceName, env, self.pid)
		self.logger.info('Stopped {}'.format(self.serviceName))
		print('Stopped {}'.format(self.serviceName))

		## end run
		return
