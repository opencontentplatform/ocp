"""Log Collection For Jobs Service.

This module is responsible for pulling job logs on clients, back to server side.

Classes:

  * :class:`.LogCollectionForJobsService` : entry class for multiprocessing
  * :class:`.LogCollectionForJobs` : specific functionality for this service

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Aug 4, 2020

"""
import os
import sys
import traceback
import json
from contextlib import suppress
import twisted.logger
from twisted.internet import reactor, task, defer, threads

## Add openContentPlatform directories onto the sys path
import env
env.addLibPath()

## From openContentPlatform
import localService
from utils import setupLogFile, setupObservers, loadSettings
from utils import logExceptionWithSelfLogger


class LogCollectionForJobs(localService.LocalService):
	"""Contains custom tailored parts specific to LogCollectionForJobs."""

	def __init__(self, serviceName, globalSettings, canceledEvent, shutdownEvent):
		"""Constructor for the LogCollectionForJobs service."""
		self.canceledEvent = canceledEvent
		self.shutdownEvent = shutdownEvent
		self.logFiles = setupLogFile(serviceName, env, globalSettings['fileContainingServiceLogSettings'], directoryName='service')
		self.logObserver = setupObservers(self.logFiles, serviceName, env, globalSettings['fileContainingServiceLogSettings'])
		self.logger = twisted.logger.Logger(observer=self.logObserver, namespace=serviceName)
		super().__init__(serviceName, globalSettings)
		self.localSettings = loadSettings(os.path.join(env.configPath, globalSettings['fileContainingLogCollectionForJobsSettings']))

		## Make checking kafka and processing results a looping call, to give a
		## break to the main reactor thread; otherwise it blocks other looping
		## calls, like those in coreService for health and environment details:
		self.kafkaConsumer = self.createKafkaConsumer(globalSettings['kafkaLogForJobsTopic'])
		self.loopingGetKafkaResults = task.LoopingCall(self.getKafkaResults, self.kafkaConsumer)
		## Give a second break before starting the main LoopingCall
		self.loopingGetKafkaResults.start(1, now=False)
		self.logger.debug('Leaving LogCollectionForJobs constructor')


	def stopFactory(self):
		try:
			#print('logCollectionForJobs stopFactory start: {}'.format(str(self.__dict__)))
			self.logger.info('stopFactory called in logCollectionForJobs')
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
			self.logger.info(' logCollectionForJobs stopFactory: complete.')

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			print('Exception in logCollectionForJobs stopFactory: {}'.format(exception))
			with suppress(Exception):
				self.logger.debug('Exception: {exception!r}', exception=exception)
		print('logCollectionForJobs stopFactory complete: {}'.format(str(self.__dict__)))

		## end stopFactory
		return


	@logExceptionWithSelfLogger()
	def workOnMessage(self, message):
		"""Process data pulled from kafka.

		Arguments:
		  message (str) : value part of message sent through kafka
		"""
		## Get a handle on the different sections of the message
		packageName = message['package']
		jobName = message['job']
		endpoint = message['endpoint']
		content = message['content']
		self.logger.info('Received message from: {packageName!r}.{jobName!r}.{endpointName!r}',
						 packageName=packageName, jobName=jobName, endpointName=endpointName)

		## end workOnMessage
		return


class LogCollectionForJobsService(localService.ServiceProcess):
	"""Entry class for the logCollectionForJobsService.

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
		self.serviceName = 'LogCollectionForJobsService'
		self.serviceClass = LogCollectionForJobs
		self.shutdownEvent = shutdownEvent
		self.canceledEvent = canceledEvent
		self.globalSettings = globalSettings
		super().__init__()
