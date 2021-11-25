"""Log Collection Service.

This module is responsible for taking client messages from Kafka and writing
them to a common server-side log. This is used for providing visibility to
important events occuring on the horizontally scalable client infrastructure.

Classes:

  * :class:`.LogCollectionService` : entry class for multiprocessing
  * :class:`.LogCollection` : specific functionality for this service

"""
import os
import sys
import traceback
from contextlib import suppress
import twisted.logger

## Add openContentPlatform directories onto the sys path
import env
env.addLibPath()

## From openContentPlatform
import localService
from utils import setupLogFile, setupObservers, loadSettings
from utils import logExceptionWithSelfLogger


class LogCollection(localService.LocalService):
	"""Contains custom tailored parts specific to LogCollection."""

	def __init__(self, serviceName, globalSettings, canceledEvent, shutdownEvent):
		"""Constructor for the LogCollection service."""
		self.canceledEvent = canceledEvent
		self.shutdownEvent = shutdownEvent
		self.logFiles = setupLogFile(serviceName, env, globalSettings['fileContainingServiceLogSettings'], directoryName='service')
		self.logObserver  = setupObservers(self.logFiles, serviceName, env, globalSettings['fileContainingServiceLogSettings'])
		self.logger = twisted.logger.Logger(observer=self.logObserver, namespace=serviceName)
		self.logger.info('Started logger for {serviceName!r}', serviceName=serviceName)
		super().__init__(serviceName, globalSettings)
		self.localSettings = loadSettings(os.path.join(env.configPath, globalSettings['fileContainingLogCollectionSettings']))

		## Twisted import here to avoid issues with epoll on Linux
		from twisted.internet import task

		## Make checking kafka and processing results a looping call, to give a
		## break to the main reactor thread; otherwise it blocks other looping
		## calls, like those in coreService for health and environment details:
		self.kafkaConsumer = self.createKafkaConsumer(globalSettings['kafkaLogTopic'])
		self.loopingGetKafkaResults = task.LoopingCall(self.getKafkaResults, self.kafkaConsumer)
		## Give a second break before starting the main LoopingCall
		self.loopingGetKafkaResults.start(1, now=False)
		self.logger.debug('Leaving LogCollection constructor')


	def stopFactory(self):
		try:
			#print('logCollection stopFactory start: {}'.format(str(self.__dict__)))
			self.logger.info('stopFactory called in logCollection')
			if self.loopingGetKafkaResults is not None:
				self.logger.debug(' stopFactory: stopping loopingGetKafkaResults')
				self.loopingGetKafkaResults.stop()
				self.loopingGetKafkaResults = None
			if self.kafkaConsumer is not None:
				self.logger.debug(' stopFactory closing kafkaConsumer')
				self.kafkaConsumer.close()
				self.kafkaConsumer = None
			super().stopFactory()
			self.globalSettings = None
			self.localSettings = None
			self.logger.info(' logCollection stopFactory: complete.')
			## Logger and log file handle cleanup needs to be the last step
			for label,twistedLogFile in self.logFiles.items():
				with suppress(Exception):
					del self.logger
				twistedLogFile.flush()
				twistedLogFile.close()
				del twistedLogFile
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			print('Exception in logCollection stopFactory: {}'.format(exception))
			with suppress(Exception):
				self.logger.debug('Exception: {exception!r}', exception=exception)
		#print('logCollection stopFactory complete: {}'.format(str(self.__dict__)))

		## end stopFactory
		return


	@logExceptionWithSelfLogger()
	def workOnMessage(self, message):
		"""Transcribe the message from kafka over to a server-side log.

		Arguments:
		  message (str) : value part of message sent through kafka
		"""
		## Get a handle on the different sections of the message
		serviceName = message['serviceName']
		endpointName = message['endpointName']
		content = message['content']
		self.logger.info('Service: {serviceName!r}  Endpoint: {endpointName!r}  Message: {content!r}', serviceName=serviceName, endpointName=endpointName, content=content)

		## end workOnMessage
		return


class LogCollectionService(localService.ServiceProcess):
	"""Entry class for the logCollectionService.

	This class leverages a common wrapper for the run method, which comes from
	the localService module. The constructor below directs multiprocessing
	to use settings specific to this manager, including setting the expected
	class (self.serviceClass) to the one customized for this manager.

	"""

	def __init__(self, shutdownEvent, canceledEvent, globalSettings):
		"""Modified multiprocessing.Process constructor to accept custom arguments.

		Arguments:
		  shutdownEvent  - event used by main process to shutdown this one
		  canceledEvent  - event that notifies main process to restart this one
		  globalSettings - global settings; used to direct this manager

		"""
		self.serviceName = 'LogCollectionService'
		self.serviceClass = LogCollection
		self.shutdownEvent = shutdownEvent
		self.canceledEvent = canceledEvent
		self.globalSettings = globalSettings
		super().__init__()
