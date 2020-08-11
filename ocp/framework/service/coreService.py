"""Core service class, used by all services.

This module provides common code paths for reuse across services (like gathering
execution environment, database initialization, kafka communication, etc). The
:class:`.CoreService` class is inherited by all services, regardless of whether
the service uses clients (i.e. micro-service and horizontally scalable) or is
contained within the app server (i.e. local).

Comments on Method Resolution Order (MRO) for the different service types:
===========================================================
Services with clients will inherit networkService.ServiceFactory, which then
inherits both this class and the twisted.internet.protocol.ServerFactory.

Services without clients simply inherit this class.

To illustrate the point:
ContentGatheringService (a horizontally scalable/micro-service) MRO:
  remoteService.RemoteServiceFactory -> networkService.ServiceFactory ->
  coreService.CoreService -> twisted.internet.protocol.ServerFactory

LogCollectionService (a local service that runs on server) MRO:
  localService.LocalService -> coreService.CoreService
===========================================================

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Split functionality out from sharedService on Aug 4, 2020

"""

import sys
import traceback
import os
import time
import datetime
import json
import platform
import psutil
import multiprocessing
from contextlib import suppress
from twisted.internet import reactor, threads, task, threads
from sqlalchemy import exc
from confluent_kafka import KafkaError

## Add openContentPlatform directories onto the sys path
import env
env.addLibPath()

## From openContentPlatform
import utils
from utils import logExceptionWithSelfLogger
from database.connectionPool import DatabaseClient


class CoreService():
	"""Core service class, used by all services."""
	def __init__(self, serviceName, globalSettings, getDbClient=False):
		"""Constructor for the CoreService."""
		try:
			self.serviceName = serviceName
			self.globalSettings = globalSettings
			self.kafkaEndpoint = self.globalSettings['kafkaEndpoint']
			self.useCertsWithKafka = self.globalSettings.get('useCertificatesWithKafka')
			self.kafkaCaRootFile = os.path.join(env.configPath, self.globalSettings.get('kafkaCaRootFile'))
			self.kafkaCertFile = os.path.join(env.configPath, self.globalSettings.get('kafkaCertificateFile'))
			self.kafkaKeyFile = os.path.join(env.configPath, self.globalSettings.get('kafkaKeyFile'))
			self.dbClient = None
			if getDbClient:
				self.getDbSession()
			self.baselineEnvironment()

			#self.loopingHealthCheck = task.LoopingCall(self.healthCheck)
			self.loopingHealthCheck = task.LoopingCall(self.deferHealthCheck)
			self.loopingHealthCheck.start(self.globalSettings['waitSecondsBetweenHealthChecks'])
			#self.loopingGetExecutionEnvironment = task.LoopingCall(self.getExecutionEnvironment)
			self.loopingGetExecutionEnvironment = task.LoopingCall(self.deferGetExecutionEnvironment)
			## The initial environment check needs to wait for the service to
			## startup, since you will see a false reading if measured right at
			## process startup time, when it's establishing initial runtime.
			self.loopingGetExecutionEnvironment.start(self.globalSettings['waitSecondsBetweenExecutionEnvironmentChecks'], now=False)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception: {exception!r}', exception=exception)
		self.logger.debug('Leaving CoreService constructor')


	def cleanup(self):
		self.logger.debug('cleanup called in {}'.format(self.serviceName))
		## Probably some operation is out there lingering and needs moved into
		## the main Twisted thread, because calling reactor.stop the following
		## recommended way does not always call the stopFactory functions:
		#reactor.callFromThread(reactor.stop)

		## For now I'll force a stopFactory call here to ensure shutdown of
		## resources that may stop the reactor from doing thread cleanup (e.g.
		## database client, Kafka connections, looping calls updating class
		## state), and rely on the multiprocessing code to ensure it stops.

		## TODO: figure out why I need to manually call this...
		self.stopFactory()
		#reactor.callFromThread(self.stopFactory)
		self.logger.info(' cleanup complete.')
		reactor.callFromThread(reactor.stop)


	def stopFactory(self):
		try:
			self.logger.debug('stopFactory called in coreService:')
			if self.loopingHealthCheck is not None:
				self.logger.debug(' stopFactory: stopping loopingHealthCheck')
				self.loopingHealthCheck.stop()
				self.loopingHealthCheck = None
			if self.loopingGetExecutionEnvironment is not None:
				self.logger.debug(' stopFactory: stopping loopingGetExecutionEnvironment')
				self.loopingGetExecutionEnvironment.stop()
				self.loopingGetExecutionEnvironment = None
			self.logger.debug(' stopFactory: removing executionEnvironment details')
			self.executionEnvironment = None
			if self.dbClient is not None:
				self.logger.debug(' stopFactory: closing database connection')
				self.dbClient.session.close()
				self.dbClient.close()
				self.dbClient = None
			self.kafkaEndpoint = None
			self.useCertsWithKafka = None
			self.kafkaCaRootFile = None
			self.kafkaCertFile = None
			self.kafkaKeyFile = None
			self.logger.info(' coreService stopFactory complete.')
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			print('Exception in coreService stopFactory: {}'.format(exception))
			with suppress(Exception):
				self.logger.error('Exception: {exception!r}', exception=exception)


	@logExceptionWithSelfLogger()
	def baselineEnvironment(self):
		"""Gather initial platform details for tracking execution environment."""
		self.executionEnvironment = { 'runtime': {}}
		self.executionEnvironment['endpointName'] = platform.node()
		self.executionEnvironment['platform'] = platform.platform()
		self.executionEnvironment['python'] = platform.python_build()


	@logExceptionWithSelfLogger()
	def deferGetExecutionEnvironment(self):
		"""Call getExecutionEnvironment in a non-blocking thread."""
		d = threads.deferToThread(self.getExecutionEnvironment)
		d.addCallback(self.updateExecutionEnvironment)
		return d


	@logExceptionWithSelfLogger()
	def updateExecutionEnvironment(self, data):
		content = self.executionEnvironment['runtime']
		## Mutate in place in case of references
		content.clear()
		for key,value in data.items():
			content[key] = value
		self.logger.info('Execution Environment:  {runtime!r}', runtime=content)


	def getExecutionEnvironment(self):
		"""Get regular execution environment updates for this service."""
		data = {}
		try:
			currentTime = time.time()
			data['lastSystemStatus'] = datetime.datetime.fromtimestamp(currentTime).strftime('%Y-%m-%d %H:%M:%S')
			## Server wide CPU average (across all cores, threads, virtuals)
			data['systemCpuAvgUtilization'] = psutil.cpu_percent()
			## Server wide memory
			memory = psutil.virtual_memory()
			data['systemMemoryAproxTotal'] = utils.getGigOrMeg(memory.total)
			data['systemMemoryAproxAvailable'] = utils.getGigOrMeg(memory.available)
			data['systemMemoryPercentUsed'] = memory.percent
			## Info on this process
			data['pid'] = os.getpid()
			process = psutil.Process(data['pid'])
			data['processCpuPercent'] = process.cpu_percent()
			data['processMemory'] = process.memory_full_info().uss
			## Create time in epoc
			startTime = process.create_time()
			data['processStartTime'] = datetime.datetime.fromtimestamp(startTime).strftime('%Y-%m-%d %H:%M:%S')
			data['processRunTime'] = utils.prettyRunTime(startTime, currentTime)

		except psutil.AccessDenied:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception: {exception!r}', exception=exception)
			self.logger.error('AccessDenied errors on Windows usually mean the main process was not started as Administrator.')

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception: {exception!r}', exception=exception)

		## end getExecutionEnvironment
		return data


	@logExceptionWithSelfLogger()
	def deferHealthCheck(self):
		"""Call healthCheck in a non-blocking thread."""
		d = threads.deferToThread(self.healthCheck)
		d.addCallback(self.shutdownCheck)
		return d


	@logExceptionWithSelfLogger()
	def shutdownCheck(self, needToShutdown):
		if needToShutdown:
			self.canceledEvent.set()
			self.logger.info('Need to shutdown after health check.')
		else:
			#self.logger.debug('Health check is good.')
			pass
		self.checkEvents()


	@logExceptionWithSelfLogger()
	def healthCheck(self):
		"""Watch for shutdown events and enforce self-service restarts."""
		needToShutdown = False

		## Ensure the system status is being updated
		previousTime = self.executionEnvironment['runtime'].get('lastSystemStatus')
		## Nothing to compare against if it hasn't been set the first time;
		## Keep in mind, the first check isn't until 30 seconds in (or
		## whatever the global waitSecondsBetweenExecutionEnvironmentChecks
		## setting has been changed to), while the first health check is
		## shorter (2 seconds is default for waitSecondsBetweenHealthChecks)
		if previousTime is not None:
			currentTime = datetime.datetime.now()
			deltaTime = currentTime - datetime.datetime.strptime(previousTime, '%Y-%m-%d %H:%M:%S')
			secondsSinceLastSystemStatus = deltaTime.seconds
			## If it has been longer than expected, set the canceledEvent. Note:
			## the local maxSecondsSinceLastSystemStatus setting must be larger
			## than the global waitSecondsBetweenExecutionEnvironmentChecks, or
			## this puts the service in an infinite restart cycle. ;)
			if secondsSinceLastSystemStatus > self.localSettings['maxSecondsSinceLastSystemStatus']:
				self.logger.info('healthCheck: system status is outdated: {}; need to request service restart.'.format(previousTime))
				needToShutdown = True

			## Check memory consumption on this process
			maxMemoryThreshold = self.localSettings['maxProcessMemoryUsageThreshold']
			## User may not want to check this (if setting is empty or set to 0)
			if maxMemoryThreshold is not None and maxMemoryThreshold != 0:
				processMemory = self.executionEnvironment['runtime'].get('processMemory')
				if processMemory is None:
					self.logger.info('healthCheck: processMemory not found; execution environment runtime invalid: {}; need to request service restart.'.format(self.executionEnvironment['runtime']))
					needToShutdown = True
				elif processMemory >= maxMemoryThreshold:
					self.logger.info('healthCheck: processMemory: {} is not less than defined threshold {}; need to request service restart.'.format(processMemory, maxMemoryThreshold))
					needToShutdown = True

			## Check CPU consumption on this process
			maxCpuPercentThreshold = self.localSettings['maxProcessCpuPercentUsageThreshold']
			## User may not want to check this (if setting is empty or set to 0)
			if maxCpuPercentThreshold is not None and maxCpuPercentThreshold != 0:
				processCpuPercent = self.executionEnvironment['runtime'].get('processCpuPercent')
				if processCpuPercent is None:
					self.logger.info('healthCheck: processCpuPercent not found; execution environment runtime invalid: {}; need to request service restart.'.format(self.executionEnvironment['runtime']))
					needToShutdown = True
				elif processCpuPercent >= maxCpuPercentThreshold:
					self.logger.info('healthCheck: processCpuPercent: {} is not less than defined threshold {}; need to request service restart.'.format(processCpuPercent, maxMemoryThreshold))
					needToShutdown = True

			## Test block
			# maxRunTimeBeforeRestart = 7200
			# processStartTime = self.executionEnvironment['runtime'].get('processStartTime')
			# currentTime = datetime.datetime.now()
			# deltaTime = currentTime - datetime.datetime.strptime(processStartTime, '%Y-%m-%d %H:%M:%S')
			# runtimeInSeconds = deltaTime.seconds
			# ## If it has been longer than expected, set the canceledEvent. Note:
			# ## the local maxSecondsSinceLastSystemStatus setting must be larger
			# ## than the global waitSecondsBetweenExecutionEnvironmentChecks, or
			# ## this puts the service in an infinite restart cycle. ;)
			# if runtimeInSeconds > maxRunTimeBeforeRestart:
			# 	self.logger.info('healthCheck: process runtime: {} is longer than max {}; need to request service restart.'.format(runtimeInSeconds, maxRunTimeBeforeRestart))
			# 	needToShutdown = True

		## end healthCheck
		return needToShutdown


	def checkEvents(self):
		if self.shutdownEvent.is_set() or self.canceledEvent.is_set():
			## Reactor.stop() may have been called from the process wrapper if
			## the shutdownEvent was set. So we attempt to cleanup as much as
			## possible (DB clients, Kafka clients, loggers, etc) with a manual
			## stopFactory call, attempting to interrupt any non-reactor threads
			## that may be blocking, before the service sub-process is killed by
			## the parent process.
			if self.shutdownEvent.is_set():
				self.logger.info('checkEvents: shutdownEvent is set; need to shutdown service.')
			else:
				self.logger.info('checkEvents: canceledEvent is set; need to request service restart.')

			## Need to call reactor.stop() on the main reactor thread
			#reactor.callFromThread(reactor.stop)

			## Well, that doesn't work. The reactor.callFromThread(reactor.stop)
			## call does not invoke our stopFactory functions! So that means
			## there is likely some operation lingering on a separate thread
			## (i.e. not on the main reactor thread) that needs to be wrapped
			## with callFromThread. Stubbing a cleanup() function for now since
			## we can control from the process level instead of thread level,
			## but I'll need to come back to this later:
			self.logger.info('checkEvents: calling cleanup.')
			self.cleanup()
			reactor.stop()

		## end checkEvents
		return


	def getDbSession(self, maxAttempts=24, waitSeconds=5):
		"""Get database connection; wait number of times or abort."""
		## If the database isn't up when the client is starting... wait on it;
		## currently set to retry every 5 sec for 2 minutes, before failing.
		self.logger.debug('Attempting to connect to database')
		errorCount = 0
		while (self.dbClient is None and
			   not self.shutdownEvent.is_set() and
			   not self.canceledEvent.is_set() and
			   errorCount < maxAttempts):
			try:
				## Hard coding the connection pool settings for now; may want to
				## pull into a setting if they need to be set per service
				self.dbClient = DatabaseClient(self.logger, globalSettings=self.globalSettings, env=env, poolSize=2, maxOverflow=1, poolRecycle=900)
				if self.dbClient is None:
					self.canceledEvent.set()
					raise EnvironmentError('Failed to connect to database')
				self.logger.debug('Database connection successful')
			except exc.OperationalError:
				self.logger.debug('DB is not available; waiting {waitCycle!r} seconds before next retry.', waitCycle=waitSeconds)
				time.sleep(int(waitSeconds))
			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception: {exception!r}', exception=exception)
				self.canceledEvent.set()
				break
			errorCount += 1
		return


	def createKafkaConsumer(self, kafkaTopic, maxRetries=5, sleepBetweenRetries=0.5, useGroup=True):
		"""Connect to Kafka and initialize a consumer.

		You may need more than one consumer per client, so don't assign directly
		to a class variable like self.kafkaConsumer; return and allow each
		client to assign and manage as desired."""
		errorCount = 0
		kafkaConsumer = None
		while kafkaConsumer is None and not self.canceledEvent.is_set() and not self.shutdownEvent.is_set():
			try:
				kafkaConsumer = utils.attemptKafkaConsumerConnection(self.logger, self.kafkaEndpoint, kafkaTopic, self.useCertsWithKafka, self.kafkaCaRootFile, self.kafkaCertFile, self.kafkaKeyFile, useGroup)

			except KafkaError:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception: Kafka error: {exception!r}', exception=exception)
				if errorCount >= maxRetries:
					self.logger.error('Too many connect attempts to kafka; aborting.')
					break
				errorCount += 1
				time.sleep(sleepBetweenRetries)

			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception: {exception!r}', exception=exception)
				break

		## end createKafkaConsumer
		return kafkaConsumer


	def createKafkaProducer(self, maxRetries=5, sleepBetweenRetries=0.5):
		"""Connect to Kafka and initialize a producer.

		You may need more than one producer per client, so don't assign directly
		to a class variable like self.kafkaProducer; return and allow each
		client to assign and manage as desired."""
		errorCount = 0
		kafkaProducer = None
		while kafkaProducer is None and not self.canceledEvent.is_set() and not self.shutdownEvent.is_set():
			try:
				kafkaProducer = utils.attemptKafkaProducerConnection(self.logger, self.kafkaEndpoint, self.useCertsWithKafka, self.kafkaCaRootFile, self.kafkaCertFile, self.kafkaKeyFile)

			except KafkaError:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception: Kafka error: {exception!r}', exception=exception)
				if errorCount >= maxRetries:
					self.logger.error('Too many connect attempts to kafka; aborting.')
					break
				errorCount += 1
				time.sleep(sleepBetweenRetries)

			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception: {exception!r}', exception=exception)
				break

		## end createKafkaProducer
		return kafkaProducer


	def processKafkaResults(self, topic):
		"""Wait for kafka messages and start processing when they arrive.

		Deprecated. Looping becomes blocking; migrate to using getKafkaResults."""
		exitMessage = 'Leaving processKafkaResults'
		kafkaConsumer = self.createKafkaConsumer(topic)
		while kafkaConsumer is not None and not self.shutdownEvent.is_set() and not self.canceledEvent.is_set():
			try:
				msgs = kafkaConsumer.consume(num_messages=int(self.localSettings['kafkaPollMaxRecords']), timeout=int(self.localSettings['kafkaPollTimeOut']))
				## Manual commit prevents message from being re-processed
				## more than once by either this consumer or another one.
				kafkaConsumer.commit()
				if msgs is None or len(msgs) <= 0:
					self.logger.debug('processKafkaResults: no msg...')
					continue
				else:
					for message in msgs:
						if message is None:
							continue
						elif message.error():
							self.logger.debug('processKafkaResults: Kafka error: {error!r}', error=message.error())
							continue
						thisMsg = json.loads(message.value().decode('utf-8'))
						self.logger.debug('Data received for processing: {thisMsg!r}', thisMsg=thisMsg)
						self.workOnMessage(thisMsg)

			except:
				self.exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('{exception}', exception=self.exception)
				exitMessage = str(traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1]))
				self.logger.debug('Aborting processKafkaResults')

		if kafkaConsumer is not None:
			with suppress(Exception):
				kafkaConsumer.close()
				kafkaConsumer = None
				self.logger.debug('processKafkaResults: closed kafkaConsumer')
		self.logger.debug('Leaving processKafkaResults. shutdownEvent: {}, canceledEvent: {}'.format(self.shutdownEvent.is_set(), self.canceledEvent.is_set()))

		## end processKafkaResults
		return exitMessage


	def getKafkaResults(self, kafkaConsumer):
		"""Process kafka messages if available, timeout and return if not."""
		while kafkaConsumer is not None and not self.shutdownEvent.is_set() and not self.canceledEvent.is_set():
			try:
				msgs = kafkaConsumer.consume(num_messages=int(self.localSettings['kafkaPollMaxRecords']), timeout=int(self.localSettings['kafkaPollTimeOut']))
				## Manual commit prevents message from being re-processed
				## more than once by either this consumer or another one.
				kafkaConsumer.commit()
				if msgs is None or len(msgs) <= 0:
					#self.logger.debug('Leaving getKafkaResults. Nothing to process.')
					return

				for message in msgs:
					if message is None:
						continue
					elif message.error():
						self.logger.debug('getKafkaResults: Kafka error: {error!r}', error=message.error())
						continue
					thisMsg = json.loads(message.value().decode('utf-8'))
					self.logger.debug('Data received for processing: {thisMsg!r}', thisMsg=thisMsg)
					self.workOnMessage(thisMsg)

			except:
				self.exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('{exception}', exception=self.exception)
				exitMessage = str(traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1]))
				self.logger.debug('Aborting getKafkaResults')

		self.logger.debug('Leaving getKafkaResults. shutdownEvent: {}, canceledEvent: {}'.format(self.shutdownEvent.is_set(), self.canceledEvent.is_set()))

		## end getKafkaResults
		return exitMessage
