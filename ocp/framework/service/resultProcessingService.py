"""Result Processing Service.

This module manages interaction with connected clients of type
:mod:`ResultProcessingClient`. The entry class is
:class:`ResultProcessingService`, which inherits from the shared class
:class:`.networkService.ServiceProcess` that handles process creation and tear
down for all services.

Classes:

  * :class:`.ResultProcessingService` : entry class for multiprocessing
  * :class:`.ResultProcessingFactory` : Twisted factory that provides the custom
    functionality for this service
  * :class:`.ResultProcessingListener` : Twisted protocol used by the factory

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors: Madhusudan Sridharan (MS)
	Version info:
	  1.0 : (CS) Created Aug 24, 2017

"""
import os, sys
import json
import twisted.logger
import traceback
from contextlib import suppress
from twisted.internet import task

## Add openContentPlatform directories onto the sys path
import env
env.addLibPath()

## From openContentPlatform
import networkService
import utils
import database.schema.platformSchema as platformSchema

## Global section
globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))


class ResultProcessingListener(networkService.ServiceListener):
	"""Receives and sends data through protocol of choice."""

	def doKafkaHealth(self, content):
		"""Logging the received kafka partition count."""
		if len(self.factory.activeClients.keys()) > int(content['KafkaPartitionCount']):
			self.factory.logger.error('The number of clients {cCount!r} has exceeded the kafka partition count {pCount!r}. They will not be able to do anything!', cCount=len(self.factory.activeClients.keys()), pCount=content['KafkaPartitionCount'])
		elif len(self.factory.activeClients.keys()) > int(content['KafkaPartitionCount'])/2:
			self.factory.logger.warn('The number of clients {cCount!r} has exceeded 50% of the partition count {pCount!r}. Consider increasing the number of kafka partitions.', cCount=len(self.factory.activeClients.keys()), pCount=content['KafkaPartitionCount'])
		else:
			self.factory.logger.info('Kafka has a healthy partition count {cCount!r} for the number of previous clients {pCount!r}', pCount=content['KafkaPartitionCount'], cCount=len(self.factory.activeClients.keys()))


class ResultProcessingFactory(networkService.ServiceFactory):
	"""Contains custom tailored parts specific to ResultProcessing."""

	protocol = ResultProcessingListener

	def __init__(self, serviceName, globalSettings, canceledEvent, shutdownEvent):
		"""Constructor for the ResultProcessingFactory."""
		self.canceledEvent = canceledEvent
		self.shutdownEvent = shutdownEvent
		self.logFiles = utils.setupLogFile(serviceName, env, globalSettings['fileContainingServiceLogSettings'], directoryName='service')
		self.logObserver  = utils.setupObservers(self.logFiles, serviceName, env, globalSettings['fileContainingServiceLogSettings'])
		self.logger = twisted.logger.Logger(observer=self.logObserver, namespace=serviceName)
		self.logger.info('Started logger for {serviceName!r}', serviceName=serviceName)
		self.localSettings = utils.loadSettings(os.path.join(env.configPath, globalSettings['fileContainingResultProcessingSettings']))
		self.globalSettings = globalSettings
		self.clientEndpointTable = platformSchema.ServiceResultProcessingEndpoint
		self.serviceJobTable = None
		self.serviceHealthTable = platformSchema.ServiceResultProcessingHealth
		self.validActions = ['connectionRequest', 'healthResponse', 'cacheResponse', 'getKafkaPartitionCount','kafkaHealth']
		self.actionMethods = ['doConnectionRequest', 'doHealthResponse', 'doCacheResponse', 'doGetKafkaPartitionCount','doKafkaHealth']
		super().__init__(serviceName, globalSettings)
		if self.canceledEvent.is_set() or self.shutdownEvent.is_set():
			self.logger.error('Cancelling startup of {serviceName!r}', serviceName=serviceName)
			return
		self.loopingGetKafkaPartitionCount = task.LoopingCall(self.doGetKafkaPartitionCount)
		self.loopingGetKafkaPartitionCount.start(self.localSettings['waitSecondsBetweenRequestingKafkaPartitionCount'])


	def stopFactory(self):
		try:
			self.logger.info('stopFactory called in resultProcessingService')
			if self.loopingGetKafkaPartitionCount is not None:
				self.logger.debug(' stopFactory: stopping loopingGetKafkaPartitionCount')
				self.loopingGetKafkaPartitionCount.stop()
				self.loopingGetKafkaPartitionCount = None
			super().stopFactory()
			self.logger.info(' resultProcessingService stopFactory: complete.')
			## Logger and log file handle cleanup needs to be the last step
			for label,twistedLogFile in self.logFiles.items():
				with suppress(Exception):
					del self.logger
				twistedLogFile.flush()
				twistedLogFile.close()
				del twistedLogFile

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			print('Exception in networkService stopFactory: {}'.format(exception))
			with suppress(Exception):
				self.logger.debug('Exception: {exception!r}', exception=exception)

		## end stopFactory
		return


	def doGetKafkaPartitionCount(self):
		"""Sends kafkapartition count request to all clients"""
		for thisName, thisValue in self.activeClients.items():
			try:
				(thisEndpoint, thisInstanceNumber, client) = thisValue
				self.logger.info('Sending KafkaPartition count request to the client {client!r}',client=client)
				client.constructAndSendData('partitionCountResponse', {})
			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception in getKafkaPartitionCount: {exception!r}', exception = exception)


class ResultProcessingService(networkService.ServiceProcess):
	"""Entry class for the resultProcessingService.

	This class leverages a common wrapper for the run method, which comes from
	the networkService module. The constructor below directs multiprocessing
	to use settings specific to this manager, including setting the expected
	class (self.serviceFactory) to the one customized for this manager.

	"""

	def __init__(self, shutdownEvent, canceledEvent, globalSettings):
		"""Modified multiprocessing.Process constructor to accept custom arguments.

		Arguments:
		  shutdownEvent  - event used by main process to shutdown this one
		  canceledEvent  - event that notifies main process to restart this one
		  globalSettings - global settings; used to direct this manager

		"""
		self.serviceName = 'ResultProcessingService'
		self.serviceFactory = ResultProcessingFactory
		self.shutdownEvent = shutdownEvent
		self.canceledEvent = canceledEvent
		self.globalSettings = globalSettings
		self.listeningPort = int(globalSettings['resultProcessingServicePort'])
		super().__init__()
