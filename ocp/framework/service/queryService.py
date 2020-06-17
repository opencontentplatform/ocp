"""Query Service.

This module is responsible for storing and managing query results. Initially
created for chunking/paging results, but positioned for maintaining and
routinely updating required cached queries (like a view table).

Classes:

  * :class:`.QueryService` : entry class for this service
  * :class:`.QueryFactory` : Twisted factory that provides the custom
    functionality for this service

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Oct 17, 2018

"""
import os
import sys
import traceback
import json
import datetime
import time
from contextlib import suppress
import twisted.logger
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor, task, defer, threads

## Add openContentPlatform directories onto the sys path
import env
env.addLibPath()

## From openContentPlatform
import sharedService
import utils
from queryProcessing import QueryProcessing
import database.schema.platformSchema as platformSchema


## TODO: consider breaking from sharedService, which currently uses a TCP-based
## Twisted factory, and use a Thread-based factory without the socket overhead.

## TODO: force a specified max thread limit, instead of the default setting for
## our reactor. We want to chunk through the queries instead of all at once; so
## if we get 5000 simultaneously - only process a certain number at a time.

class QueryListener(LineReceiver):
	def doNothing(self, content):
		pass


class QueryFactory(sharedService.ServiceFactory):
	"""Contains custom tailored parts specific to Query result processing."""

	protocol = QueryListener

	def __init__(self, serviceName, globalSettings, canceledEvent, shutdownEvent):
		"""Constructor for the QueryFactory."""
		self.canceledEvent = canceledEvent
		self.shutdownEvent = shutdownEvent
		self.logFiles = utils.setupLogFile(serviceName, env, globalSettings['fileContainingServiceLogSettings'], directoryName='service')
		self.logObserver  = utils.setupObservers(self.logFiles, serviceName, env, globalSettings['fileContainingServiceLogSettings'])
		self.logger = twisted.logger.Logger(observer=self.logObserver, namespace=serviceName)
		self.validActions = ['connectionRequest', 'healthResponse', 'nothing']
		self.actionMethods = ['doConnectionRequest', 'doHealthResponse', 'doNothing']
		self.dbClient = None
		## Allow the dbClient to get created in the main thread, to reuse pool
		super().__init__(serviceName, globalSettings, False, True)
		self.dbClient.session.close()
		self.localSettings = utils.loadSettings(os.path.join(env.configPath, globalSettings['fileContainingQuerySettings']))
		## Initialize the Kafka consumer
		self.kafkaConsumer = self.createKafkaConsumer(globalSettings['kafkaQueryTopic'])
		self.logger.info('waitSecondsBetweenCacheCleanupJobs: {secs!r}', secs=self.localSettings['waitSecondsBetweenCacheCleanupJobs'])
		## TODO: modify looping calls to use threads.deferToThread(); avoid
		## time delays/waits from being blocking to the main reactor thread
		self.loopingCleanUpCache = task.LoopingCall(self.cleanUpCache)
		self.loopingCleanUpCache.start(self.localSettings['waitSecondsBetweenCacheCleanupJobs'])
		## If we call the main thread function from our constructor directly,
		## it becomes blocking. Same results if we use callWhenRunning or
		## deferToThread or deferToThread in a separate deferred function. But
		## it gracefully exists with callFromThread on the main function:
		reactor.callFromThread(self.processKafkaResults)
		self.logger.debug('QueryFactory: leaving constructor')


	def stopFactory(self):
		"""Manual destructor to cleanup when catching signals."""
		print(' queryService cleaning up... inside stopFactory')
		with suppress(Exception):
			self.logger.debug(' stopFactory: starting...')
		self.cleanup()
		with suppress(Exception):
			self.logger.info(' stopFactory: complete.')
		return


	def cleanup(self):
		self.logger.debug(' cleanup called in queryService')
		with suppress(Exception):
			self.loopingCleanUpCache.stop()
			self.logger.debug(' cleanup: Looping calls stopped.')
		with suppress(Exception):
			if self.kafkaConsumer is not None:
				self.kafkaConsumer.close()
				self.logger.debug(' cleanup: kafkaConsumer closed.')
		self.logger.info(' cleanup complete.')


	def cleanUpCache(self):
		try:
			self.logger.info('Cleaning up old cache entries')
			time.sleep(2)
			current_time = datetime.datetime.now()
			timeThreshold = current_time - datetime.timedelta(seconds=int(self.localSettings.get('maxSecondsForRetainingCachedQueryResult', 900)))

			dbTable = platformSchema.CachedQuery
			oldEntries = self.dbClient.session.query(dbTable).filter(dbTable.time_started < timeThreshold).all()
			self.dbClient.session.commit()
			if len(oldEntries) > 0:
				count = 0
				for entry in oldEntries:
					count += 1
					self.logger.info('Found entry: {entry!r}', entry=entry)
					queryId = entry.object_id
					chunkCount = entry.chunk_count
					self.logger.info('Found old query ID {queryId!r} with count {chunkCount!r}', queryId=queryId, chunkCount=chunkCount)

					## Remove chunk details
					chunkTable = platformSchema.CachedQueryChunk
					oldChunks = self.dbClient.session.query(chunkTable).filter(chunkTable.object_id == queryId).all()
					self.dbClient.session.commit()
					for chunk in oldChunks:
						thisId = chunk.object_id
						thisChunkId = chunk.chunk_id
						self.logger.info('Removing chunk query {thisId!r} chunk {thisChunkId!r}', thisId=thisId, thisChunkId=thisChunkId)
						self.dbClient.session.delete(chunk)
						self.dbClient.session.commit()
					## Now remove the top level entry
					self.dbClient.session.delete(entry)
					self.dbClient.session.commit()
				self.logger.info('Finished cleanUpCache... successfully cleaned up {count!r} old cached queries', count=count)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in cleanUpCache: {exception!r}', exception=exception)

		if self.dbClient is not None:
			self.dbClient.session.close()

		## end cleanUpCache
		return


	def processKafkaResults(self):
		"""Wait for kafka messages and start processing when they arrive."""
		exitMessage = 'Leaving processKafkaResults'
		while not self.shutdownEvent.is_set() and not self.canceledEvent.is_set():
			try:
				msgs = self.kafkaConsumer.consume(num_messages=int(self.localSettings['kafkaPollMaxRecords']), timeout=int(self.localSettings['kafkaPollTimeOut']))
				## Manual commit prevents message from being re-processed
				## more than once by either this consumer or another one.
				self.kafkaConsumer.commit()
				if msgs is None or len(msgs) <= 0:
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

		self.logger.debug('Ready to exit processKafkaResults... shutdownEvent: {}, canceledEvent: {}'.format(self.shutdownEvent.is_set(), self.canceledEvent.is_set()))

		## end processKafkaResults
		return


	def workOnMessage(self, message):
		"""Process the query pulled from kafka.

		Arguments:
		  message (str) : value part of message sent through kafka
		"""
		self.logger.info('Inside workOnMessage')
		try:
			self.logger.info('Inside workOnMessage... ')
			self.logger.info('       workOnMessage... message: {message!r}', message=message)
			## Get a handle on the different sections of the message
			queryId = message['queryId']
			headers = message['headers']
			content = message['content']
			apiUser = message['apiUser']
			queryName = 'dynamic'
			jobStart = datetime.datetime.now()

			## Initialize a row in the CachedQuery table
			self.logger.info('       workOnMessage... stub DB table')
			dbTable = platformSchema.CachedQuery
			thisEntry = dbTable(object_id=queryId, time_started=jobStart, object_created_by=apiUser, chunk_count=0, chunk_size_requested=int(headers.get('contentDeliverySize', 0)))
			self.dbClient.session.add(thisEntry)
			self.dbClient.session.commit()
			## Execute the query and get the results
			queryProcessing = QueryProcessing(self.logger, self.dbClient, content, utils.valueToBoolean(headers.get('removePrivateAttributes', True)), utils.valueToBoolean(headers.get('removeEmptyAttributes', True)), headers.get('resultsFormat', 'Flat'))
			queryResult = queryProcessing.runQuery()

			## Split up query and save in DB
			chunkCount = self.chunkResult(headers, queryId, queryResult)

			## Job cleanup
			jobEnd = datetime.datetime.now()
			totalSeconds = (jobEnd - jobStart).total_seconds()
			prettyRunTime = utils.prettyRunTimeBySeconds(totalSeconds)
			self.logger.info('Query {queryName!r} complete.  Started at {startDate!r}.  Runtime: {prettyRunTime!r}', queryName=queryName, startDate=str(jobStart), prettyRunTime=prettyRunTime)
			## Update our stubbed row in the CachedQuery table
			matchedEntry = self.dbClient.session.query(dbTable).filter(dbTable.object_id == queryId).first()
			if not matchedEntry:
				self.logger.error('Error updating CachedQuery entry; object_id not found: {queryId!r}', queryId=queryId)
				raise 'Error updating CachedQuery entry; object_id not found: {}'.format(queryId)
			matchedEntry.chunk_count = chunkCount
			matchedEntry.time_finished = jobEnd
			matchedEntry.time_elapsed = totalSeconds
			originalSizeInKB = 0
			with suppress(Exception):
				originalSizeInKB = int(len(str(queryResult)) / 1024)
			matchedEntry.original_size_in_kb = originalSizeInKB
			self.logger.info('Updating CachedQuery entry... had chunkCount: {chunkCount!r}, originalSizeInKB: {originalSizeInKB!r}', chunkCount=chunkCount, originalSizeInKB=originalSizeInKB)
			self.dbClient.session.merge(matchedEntry)
			self.dbClient.session.commit()

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in {queryName!r}: {exception!r}', queryName=queryName, exception=exception)

		if self.dbClient is not None:
			self.dbClient.session.close()
		self.logger.info('Leaving workOnMessage')

		## end workOnMessage
		return


	def sendChunk(self, queryId, chunkId, chunkSize, data):
		self.logger.info('       sendChunk...')
		dbTable = platformSchema.CachedQueryChunk
		thisEntry = dbTable(object_id=queryId, chunk_id=chunkId, chunk_size_in_kb=chunkSize, data=data)
		self.dbClient.session.add(thisEntry)
		self.dbClient.session.commit()


	def chunkResult(self, headers, queryId, queryResult):
		"""Split up query and store chunks in the database."""
		chunkId = 0
		try:
			contentDeliverySize = int(headers.get('contentDeliverySize', 1))
			## Assuming the provided size will be MB and not KB or Bytes:
			contentDeliverySize = contentDeliverySize * 1024
			resultSize = len(str(queryResult))
			chunkSizeInKB = 0
			with suppress(Exception):
				chunkSizeInKB = int(resultSize / 1024)
			## Split up query and save in DB
			self.logger.debug('Query result character count {queryResultSize!r}', queryResultSize=resultSize)
			self.logger.debug('  contentDeliverySize: {contentDeliverySize!r}', contentDeliverySize=contentDeliverySize)
			if contentDeliverySize > resultSize:
				## Save as a single chunk without breaking it up
				chunkId += 1
				self.sendChunk(queryId, chunkId, chunkSizeInKB, queryResult)
				self.logger.info('  Sent only one chunk')
			else:
				chunkData = {}
				lastKey = None
				for dictKey in ['objects', 'links']:
					chunkData[dictKey] = []
					for entry in queryResult.get(dictKey, []):
						chunkData[dictKey].append(entry)
						if len(str(chunkData)) > contentDeliverySize:
							chunkId += 1
							chunkSizeInKB = 0
							with suppress(Exception):
								chunkSizeInKB = int(len(str(chunkData)) / 1024)
							self.sendChunk(queryId, chunkId, chunkSizeInKB, chunkData)
							## Reinitialize JSON result with where we left off
							chunkData = {}
							chunkData[dictKey] = []
							lastKey = dictKey
				## Avoid having this trailing chunk: {'links': []}
				if len(str(chunkData)) > 0 and chunkData.get(lastKey) != []:
					chunkId += 1
					chunkSizeInKB = 0
					with suppress(Exception):
						chunkSizeInKB = int(len(str(chunkData)) / 1024)
					self.sendChunk(queryId, chunkId, chunkSizeInKB, chunkData)
				self.logger.info('  Sent number of chunks: {chunkId!r}', chunkId=chunkId)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in chunkResult: {exception!r}', exception=exception)

		## end chunkResult
		return chunkId


class QueryService(sharedService.ServiceProcess):
	"""Entry class for the queryService.

	This class leverages a common wrapper for the run method, which comes from
	the serviceProcess module. The constructor below directs the shared run
	function to use settings specific to this manager, including setting the
	factory class (self.serviceFactory) to the one above, which is customized
	for this manager.

	"""

	def __init__(self, shutdownEvent, globalSettings):
		"""Modified constructor to accept custom arguments.

		Arguments:
		  shutdownEvent : event used to control graceful shutdown
		  settings      : global settings; used to direct this manager

		"""
		self.serviceName = 'QueryService'
		self.multiProcessingLogContext = 'QueryServiceDebug'
		self.serviceFactory = QueryFactory
		self.shutdownEvent = shutdownEvent
		self.globalSettings = globalSettings
		self.listeningPort = int(globalSettings['queryServicePort'])
		super().__init__()
