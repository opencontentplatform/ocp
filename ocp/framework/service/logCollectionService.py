"""Log Collection Service.

This module is responsible for log collection.

Classes:

  * :class:`.LogCollectionService` : entry class for this service
  * :class:`.LogCollectionFactory` : Twisted factory that provides the custom
    functionality for this service

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  0.1 : (CS) Created Jan, 2018
	  1.0 : (CS) Wired together and brought online, Oct 25, 2018

"""
import os
import sys
import traceback
import json
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


## TODO: break this out from sharedService, which currently uses a TCP-based
## Twisted factory, and use a Thread-based factory without the socket overhead.


class LogCollectionListener(LineReceiver):
	def doNothing(self, content):
		pass


class LogCollectionFactory(sharedService.ServiceFactory):
	"""Contains custom tailored parts specific to LogCollection."""

	protocol = LogCollectionListener

	def __init__(self, serviceName, globalSettings, canceledEvent, shutdownEvent):
		"""Constructor for the LogCollectionFactory."""
		self.canceledEvent = canceledEvent
		self.shutdownEvent = shutdownEvent
		self.logFiles = utils.setupLogFile(serviceName, env, globalSettings['fileContainingServiceLogSettings'], directoryName='service')
		self.logObserver  = utils.setupObservers(self.logFiles, serviceName, env, globalSettings['fileContainingServiceLogSettings'])
		self.logger = twisted.logger.Logger(observer=self.logObserver, namespace=serviceName)
		self.validActions = ['connectionRequest', 'healthResponse', 'nothing']
		self.actionMethods = ['doConnectionRequest', 'doHealthResponse', 'doNothing']
		super().__init__(serviceName, globalSettings, False, False)
		self.localSettings = utils.loadSettings(os.path.join(env.configPath, globalSettings['fileContainingLogCollectionSettings']))
		self.kafkaConsumer = self.createKafkaConsumer(globalSettings['kafkaLogTopic'])
		## If we call the main thread function from our constructor directly,
		## it becomes blocking. Same results if we use callWhenRunning or
		## deferToThread or deferToThread in a separate deferred function. But
		## it gracefully exists with callFromThread on the main function:
		reactor.callFromThread(self.processKafkaResults)
		self.logger.debug('LogCollectionFactory: leaving constructor')


	def stopFactory(self):
		"""Manual destructor to cleanup when catching signals."""
		print(' logCollectionService cleaning up... inside stopFactory')
		with suppress(Exception):
			self.logger.debug(' stopFactory: starting...')
		self.cleanup()
		with suppress(Exception):
			self.logger.info(' stopFactory: complete.')
		return


	def cleanup(self):
		self.logger.debug(' cleanup called in logCollectionService')
		with suppress(Exception):
			if self.kafkaConsumer is not None:
				#print('  stopFactory: close kafkaConsumer')
				self.kafkaConsumer.close()
				self.logger.debug(' cleanup: kafkaConsumer closed.')
		self.logger.info(' cleanup complete.')


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
		try:
			## Get a handle on the different sections of the message
			serviceName = message['serviceName']
			endpointName = message['endpointName']
			content = message['content']
			self.logger.info('Service: {serviceName!r}  Endpoint: {endpointName!r}  Message: {content!r}', serviceName=serviceName, endpointName=endpointName, content=content)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in workOnMessage: {exception!r}', exception=exception)

		## end workOnMessage
		return


class LogCollectionService(sharedService.ServiceProcess):
	"""Entry class for the logCollectionService.

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
		self.serviceName = 'LogCollectionService'
		self.multiProcessingLogContext = 'LogCollectionServiceDebug'
		self.serviceFactory = LogCollectionFactory
		self.shutdownEvent = shutdownEvent
		self.globalSettings = globalSettings
		self.listeningPort = int(globalSettings['logCollectionServicePort'])
		super().__init__()
