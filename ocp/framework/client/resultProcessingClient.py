"""Result Processing Client.

This module receives direction from the :mod:`service.resultProcessingService`,
and runtime data (streams of objects to put into the database) from Kafka. The
entry class is :class:`.ResultProcessingClient`, which inherits from the shared
:mod:`.sharedClient` module. And it is invoked from the command line through
:mod:`openContentClient`, or wrapped by a corresponding service/daemon.

The main purpose of this client is to process JSON results sitting out on the
Kafka topics/queues. A sample of expected JSON format follows; notice it has a
list of objects and links.  Both contain a "class_name" key, which holds the
case sensitive name of the Python class for the database object. In addition to
the class_name, each object should contain a unique numerical "identifier" (that
is able to be referenced in the links section) along with a "data" key, which is
a dictionary of attributes for the object. The "data" section must contain all
the unique constraints required by that DB class, or it will be dropped. The
links hold the class_name, followed by "first_id" and "second_id" that should
match numerical identifiers in the objects section.

Sample JSON::

	{
		"source": "jobXYZ",
		"objects": [
			{
				"class_name": "IpAddress",
				"identifier": "1",
				"data": {
					"address": "192.168.121.45",
					"realm": "default"
				}
			},
			{
				"class_name": "NameRecord",
				"identifier": "2",
				"data": {
					"name": "192.168.121.45",
					"value": "server5.lab.cmsconstruct.com"
				}
			},
			{
				"class_name": "Domain",
				"identifier": "426e86b90d5a4a2d87089c947ab4462b",
				"data": {
					"name": "WORKGROUP"
				}
			}
		],
		"links": [{
				"class_name": "Usage",
				"first_id": "1",
				"second_id": "2"
			},
			{
				"class_name": "Enclosed",
				"first_id": "426e86b90d5a4a2d87089c947ab4462b",
				"second_id": "2"
			}
		]
	}

When the client tries to insert or update database objects based on the JSON
result, it does so in an ordered way. First it checks to see if the object
exists in the special caches (constraint and reference caches). If not found,
check the production database for the object. If the object is found, it knows
the primary key (object_id) to use with an update. If the object is not found,
it is inserted into the production database.

The architecture for this ResultProcessingClient allows any number of instances
to work in parallel with a horizontally scaling, multi-process architecture. So
if you want faster processing of results flowing through Kafka, just spin up
additional instances of this client.

Classes:
  * :class:`.ResultProcessingClient` :entry class for this client
  * :class:`.ResultProcessingClientFactory` : Twisted factory for this client
  * :class:`.ResultProcessingClientListener` : Twisted protocol for this client

.. hidden::

  Author: Chris Satterthwaite (CS)
  Contributors: Madhusudan Sridharan (MS)
  Version info:
    1.0 : (CS) Created Nov 22, 2017
    1.1 : (CS) Refactored to use the same startup process controls as the service
          managers. Mar 6, 2019.

"""
import os, sys
import traceback
import json
import time
import datetime
from twisted.internet import reactor, task, defer, threads, ssl
from twisted.internet.protocol import ReconnectingClientFactory
import twisted.logger
from contextlib import suppress
from sqlalchemy.orm import noload
from sqlalchemy import and_, inspect, exc

## Add openContentPlatform directories onto the sys path
thisPath = os.path.dirname(os.path.abspath(__file__))
basePath = os.path.abspath(os.path.join(thisPath, '..'))
if basePath not in sys.path:
	sys.path.append(basePath)
import env
env.addLibPath()

## From openContentPlatform
import utils
import sharedClient
from database.connectionPool import DatabaseClient
from resultProcessing import ResultProcessing
from objectCache import ObjectCache


class ResultProcessingClientListener(sharedClient.ServiceClientProtocol):
	"""Receives and sends data through protocol of choice"""

	def doPartitionCountResponse(self, content):
		"""Sending kafka partition count as response for server request"""
		self.factory.logger.info('Received kafkapartition count request from server')
		content = dict()
		content['action'] = 'kafkaHealth'
		content['KafkaPartitionCount'] = self.factory.partitionCount
		self.constructAndSendData('kafkaHealth', content)


class ResultProcessingClientFactory(sharedClient.ServiceClientFactory):
	"""Contains custom tailored parts for this module."""
	continueTrying = True
	maxDelay = 300
	initialDelay = 1
	factor = 4

	def __init__(self, serviceName, globalSettings, canceledEvent, shutdownEvent):
		"""Constructor for the ResultProcessingClientFactory.

		Arguments:
		  serviceName (str)     : class name of the client ('ResultProcessingClient')
		  globalSettings (dict) : global globalSettings
		"""
		## Add any additional custom setup
		try:
			## TODO : instrument these two events since this now is a process
			self.canceledEvent = canceledEvent
			self.shutdownEvent = shutdownEvent
			self.logFiles = utils.setupLogFile(serviceName, env, globalSettings['fileContainingClientLogSettings'], directoryName='client')
			self.logObserver = utils.setupObservers(self.logFiles, serviceName, env, globalSettings['fileContainingClientLogSettings'])
			self.logger = twisted.logger.Logger(observer=self.logObserver, namespace=serviceName)
			self.globalSettings = globalSettings
			self.localSettings = utils.loadSettings(os.path.join(env.configPath, globalSettings['fileContainingResultProcessingSettings']))
			self.canceled = False
			self.dbClient = None
			self.validActions = ['connectionResponse', 'healthRequest', 'tokenExpired', 'unauthorized', 'partitionCountResponse']
			self.actionMethods = ['doConnectionResponse', 'doHealthRequest', 'doTokenExpired', 'doUnauthorized', 'doPartitionCountResponse']
			self.kafkaErrorCount = 0
			self.kafkaErrorLimit = 5
			self.kafkaConsumer = None
			self.partitionCount = 0
			self.connectedToKafkaConsumer = False
			self.resultProcessingUtility = None
			self.maintenanceMode = True
			self.pauseKafkaProcessing = True
			super().__init__(serviceName, globalSettings)
			self.initialize(True)
			## Looping call to build objectCache and start kafka processing
			self.loopingStartProcessing = task.LoopingCall(self.startProcessing)
			self.loopingStartProcessing.start(int(self.localSettings['waitSecondsBetweenRequestingFullSyncCacheUpdates'])).addErrback(self.logger.error)
			## Looping call to delta update (in-place) the objectCache
			self.loopingDeltaSync = task.LoopingCall(self.updateObjectCache)
			self.loopingDeltaSync.start(int(self.localSettings['waitSecondsBetweenRequestingDeltaSyncCacheUpdates'])).addErrback(self.logger.error)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			print('Exception in ResultProcessingClientFactory constructor: {}'.format(str(exception)))
			with suppress(Exception):
				self.logger.error('Exception in ResultProcessingClientFactory: {exception!r}', exception=exception)
			self.canceled = True
			self.logToKafka(sys.exc_info()[1])
			reactor.stop()


	def buildProtocol(self, addr):
		self.logger.debug('Connected.')
		## Resetting reconnection delay
		self.resetDelay()
		protocol = ResultProcessingClientListener()
		protocol.factory = self
		return protocol


	def initialize(self, justStarted=False):
		self.logger.debug('called initialize in resultsProcessingClient...')
		self.getDbSession()
		self.objectCache = ObjectCache(self.logger, self.dbClient)
		super().initialize(justStarted)


	def stopFactory(self):
		"""Manual destructor to cleanup when catching signals."""
		print(' Cleaning up...')
		self.logToKafka('stopFactory called in {} instance {}'.format(self.serviceName, self.clientName))
		## Tell ReconnectingClientFactory not to reconnect on future disconnects
		print('  stopFactory: stop trying to reconnect on future disconnects')
		self.stopTrying()
		self.canceled = True
		print('  stopFactory: stopping loopingStartProcessing and loopingDeltaSync')
		with suppress(Exception):
			self.loopingStartProcessing.stop()
		with suppress(Exception):
			self.loopingDeltaSync.stop()
		self.objectCache.remove()
		self.objectCache = None
		with suppress(Exception):
			self.dbClient.close()
		print('  stopFactory: stopping kafkaConsumer')
		self.logger.debug('  stopFactory: stopping kafkaConsumer')
		with suppress(Exception):
			self.kafkaConsumer.close()
		print('  stopFactory: flush kafkaProducer')
		with suppress(Exception):
			if self.kafkaProducer is not None:
				self.kafkaProducer.flush()
				print('  stopFactory: close kafkaProducer')
				self.kafkaProducer = None
		self.connectedToKafkaConsumer = False
		## These are from the sharedClient
		print('  stopFactory: stopping loopingSystemHealth and loopingAuthenticateClient')
		with suppress(Exception):
			self.loopingSystemHealth.stop()
		with suppress(Exception):
			self.loopingAuthenticateClient.stop()
		self.resultProcessingUtility = None
		self.logObserver = None
		self.logger = None
		self.logFiles = None
		print(' Cleanup complete; stopping client.')

		## end stopFactory
		return


	def startProcessing(self):
		"""Starts kafka processessing."""
		print('Inside startProcessing...')
		threadHandle = None
		try:
			## Prepare for our maintenance work (no-op on first run)...
			self.maintenanceMode = True
			print('startProcessing: while not canceled loop')
			## Initialize the Kafka connection
			while not self.connectedToKafkaConsumer and not self.canceled:
				print('startProcessing: calling createKafkaConsumer')
				self.logger.debug('startProcessing: calling createKafkaConsumer')
				self.kafkaConsumer = self.createKafkaConsumer(self.kafkaTopic)
				## You hit an exception if this is the first time the topic is
				## used (auto.create.topics.enable=true), as no partitions exist
				with suppress(Exception):
					self.partitionCount = getKafkaPartitionCount(self.logger, self.kafkaConsumer, self.kafkaTopic)
				continue
			## Wait for the previous processKafkaResults to break out of the
			## while loop and finish, before starting routine maintenance.
			while not self.pauseKafkaProcessing and not self.canceled:
				print('startProcessing: inside maintenance wait loop for pauseKafkaProcessing')
				self.logger.info('startProcessing: inside maintenance wait loop for pauseKafkaProcessing')
				time.sleep(2)

			## Maintenance work...
			## Build objectCache from scratch instead of updating from timestamp
			print('startProcessing: build objectCache from scratch')
			self.logger.debug('startProcessing: build objectCache from scratch')
			self.objectCache.build()
			## Initialize the resultProcessingUtility
			self.logger.debug('startProcessing: initialize ResultProcessing')
			self.resultProcessingUtility = ResultProcessing(self.logger, self.dbClient, cacheData=self.objectCache.constraintCache, referenceCacheData=self.objectCache.referenceCache)
			## Set flags to (re)enable standard processKafkaResults flow
			self.maintenanceMode = False
			self.pauseKafkaProcessing = False

			## (Re)Start the result processing work...
			## Run main processing code in a separate thread
			self.logger.debug('startProcessing: calling processKafkaResults in separate thread')
			threadHandle = threads.deferToThread(self.processKafkaResults)
			threadHandle.addErrback(self.logger.error)
			threadHandle.addCallback(self.logger.info)

		except (KeyboardInterrupt, SystemExit):
			print('Interrrupt received...')
			self.canceled = True
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in startProcessing: {exception!r}', exception=exception)
			self.logToKafka(sys.exc_info()[1])
			sleep(.5)
			self.canceled = True

		print('startProcessing: exiting')
		self.logger.debug('startProcessing: exiting')

		## end startProcessing
		return


	def processKafkaResults(self):
		"""Wait for kafka results, and send into the resultProcessingUtility."""
		print('Inside processKafkaResults')
		self.logger.info('Inside {name!r}.processKafkaResults', name=__name__)
		while self.connectedToKafkaConsumer and not self.maintenanceMode and not self.canceled:
			try:

				msgs = self.kafkaConsumer.consume(num_messages=int(self.localSettings['kafkaPollMaxRecords']), timeout=int(self.localSettings['kafkaPollTimeOut']))
				## Manual commit prevents message from being re-processed
				## more than once by either this consumer or another one.
				self.kafkaConsumer.commit()
				if msgs is None or len(msgs) <= 0:
					continue
				for message in msgs:
					self.kafkaErrorCount = 0
					if message is None:
						continue
					elif message.error():
						self.logger.debug('processKafkaResults: Kafka error: {error!r}', error=msgs.error())
						continue
					thisMsg = json.loads(message.value().decode('utf-8'))
					if 'nested' not in thisMsg.keys():
						errMsg = self.resultProcessingUtility.processResult(thisMsg)
						if errMsg is not None:
							self.logToKafka('resultProcessing error: {}  ... on result: {}'.format(str(errMsg), json.dumps(thisMsg)))
					else:
						errMsg = self.resultProcessingUtility.initiateNest(thisMsg)
						if errMsg is not None:
							self.logToKafka('resultProcessing error: {}  ... on nested result: {}'.format(str(errMsg), json.dumps(thisMsg)))
					## Return underlying DBAPI connection
					self.dbClient.session.close()

			except (KeyboardInterrupt, SystemExit):
				print('Interrrupt received...')
				self.canceled = True
			except:
				print('Exception in processKafkaResults...')
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('processKafkaResults: exception in kafka wait loop: {exception}', exception=exception)
				self.logToKafka('processKafkaResults: aborted kafka wait loop')
				## The timeout_ms set in our kafkaConsumer call above, will
				## never be large enough since we can't control the size of data
				## sent here. We default the timeout to half a second or 2 secs,
				## and just wait until we hit a 'kafka.errors.CommitFailedError'
				## with the message talking about the time between subsequent
				## calls was longer than the configured session.timeout.ms.
				## That lands us here, and so our raise will be caught by the
				## deferred and it will recall this function to start again.
				self.kafkaErrorCount += 1
				try:
					if self.kafkaErrorCount < self.kafkaErrorLimit:
						print('processKafkaResults kafkaErrorCount {}'.format(self.kafkaErrorCount))
						with suppress(Exception):
							self.logger.error('processKafkaResults kafkaErrorCount {kafkaErrorCount}', kafkaErrorCount=self.kafkaErrorCount)
						time.sleep(2)
					else:
						self.canceled = True
						print('processKafkaResults kafkaErrorCount {}... exiting.'.format(self.kafkaErrorCount))
						with suppress(Exception):
							self.logger.error('processKafkaResults kafkaErrorCount {kafkaErrorCount}', kafkaErrorCount=self.kafkaErrorCount)
						reactor.stop()
				except:
					exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					print('Exception in processKafkaResults second catch: {}'.format(exception))
					reactor.stop()

		self.resultProcessingUtility = None
		print('Leaving processKafkaResults...')
		self.logger.debug('Leaving processKafkaResults...')
		print('  --> connectedToKafkaConsumer {}'.format(self.connectedToKafkaConsumer))
		self.logger.debug('  --> connectedToKafkaConsumer {connectedToKafkaConsumer!r}', connectedToKafkaConsumer=self.connectedToKafkaConsumer)
		print('  --> maintenanceMode  {}'.format(self.maintenanceMode))
		self.logger.debug('  --> maintenanceMode  {maintenanceMode!r}', maintenanceMode=self.maintenanceMode)

		## Indicate we are ready for cache full sync
		self.pauseKafkaProcessing = True
		if not self.connectedToKafkaConsumer:
			return 'processKafkaResults: not currently connected to Kafka'

		if self.maintenanceMode:
			return 'processKafkaResults: entering maintenance mode'

		## end processKafkaResults
		return 'processKafkaResults: exiting'


	def updateObjectCache(self):
		self.objectCache.update()


	def getDbSession(self):
		"""Get instance for database client from defined configuration."""
		## If the database isn't up when the client is starting... wait on it.
		self.logger.debug('Attempting to connect to database')
		while self.dbClient is None and not self.canceled:
			try:
				## Hard coding the connection pool settings for now; may want to
				## pull into a localSetting if they need to be independently set
				self.dbClient = DatabaseClient(self.logger, globalSettings=self.globalSettings, env=env, poolSize=1, maxOverflow=2, poolRecycle=900)
				if self.dbClient is None:
					self.canceled = True
					raise EnvironmentError('Failed to connect to database; unable to initialize tables.')
				self.logger.debug('Database connection successful')
			except exc.OperationalError:
				self.logger.debug('DB is not available; waiting {waitCycle!r} seconds before next retry.', waitCycle=self.globalSettings['waitSecondsBeforeRetryingDatabaseConnection'])
				self.logToKafka('DB is not available; waiting {waitCycle!r} seconds before next retry.'.format(self.globalSettings['waitSecondsBeforeRetryingDatabaseConnection']))
				time.sleep(int(self.globalSettings['waitSecondsBeforeRetryingDatabaseConnection']))
			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception in getDbSession: {exception!r}', exception=exception)
				self.canceled = True
				self.logToKafka(sys.exc_info()[1])
				break

		## end getDbSession
		return


class ResultProcessingClient(sharedClient.ClientProcess):
	"""Entry class for this client.

	This class leverages a common wrapper for the multiprocessing code, found
	in the :mod:`.sharedClient` module. The constructor below directs the
	wrapper function to use settings specific to this manager.
	"""

	def __init__(self, shutdownEvent, globalSettings):
		"""Modified constructor to accept custom arguments.

		Arguments:
		  shutdownEvent  - event used to control graceful shutdown
		  globalSettings - global settings; used to direct this manager
		"""
		self.shutdownEvent = shutdownEvent
		self.globalSettings = globalSettings
		self.clientName = 'ResultProcessingClient'
		self.clientFactory = ResultProcessingClientFactory
		self.listeningPort = int(globalSettings['resultProcessingServicePort'])
		super().__init__()
