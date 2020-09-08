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
import time
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
		self.logger.info('Started logger for {serviceName!r}', serviceName=serviceName)
		super().__init__(serviceName, globalSettings)
		self.localSettings = loadSettings(os.path.join(env.configPath, globalSettings['fileContainingLogCollectionForJobsSettings']))
		self.secondsBetweenLogCleanup = int(self.localSettings['waitHoursBetweenLogCleanupChecks']) * 60 * 60
		self.secondsToRetainLogFiles = int(self.localSettings['numberOfHoursToRetainLogFiles']) * 60 * 60

		## Make checking kafka and processing results a looping call, to give a
		## break to the main reactor thread; otherwise it blocks other looping
		## calls, like those in coreService for health and environment details:
		self.kafkaConsumer = self.createKafkaConsumer(globalSettings['kafkaLogForJobsTopic'])
		self.loopingGetKafkaResults = task.LoopingCall(self.getKafkaResults, self.kafkaConsumer)
		## Give a second break before starting the main LoopingCall
		self.loopingGetKafkaResults.start(1, now=False)
		## Regularly check logs for cleanup; avoid filling disk with old logs
		self.loopingCleanupLogs = task.LoopingCall(self.deferCleanupLogs)
		self.loopingCleanupLogs.start(self.secondsBetweenLogCleanup)
		self.logger.debug('Leaving LogCollectionForJobs constructor')


	def stopFactory(self):
		try:
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
			## Logger and log file handle cleanup needs to be the last step
			for label,twistedLogFile in self.logFiles.items():
				with suppress(Exception):
					del self.logger
				twistedLogFile.flush()
				twistedLogFile.close()
				del twistedLogFile

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
						 packageName=packageName, jobName=jobName, endpointName=endpoint)

		## Write to ./runtime/log/job/<jobName>/<endpoint>.log
		logPath = os.path.join(env.logPath, 'job', jobName)
		if not os.path.exists(logPath):
			os.makedirs(logPath)
		exectutionLogFile = os.path.join(logPath, '{}.log'.format(endpoint))
		with open(exectutionLogFile, 'w') as fh:
			fh.write(content)

		## end workOnMessage
		return


	def deferCleanupLogs(self):
		"""Looping method for cleanup logs; done via non-blocking thread."""
		threadHandle = None
		try:
			threadHandle = threads.deferToThread(self.cleanupLogs)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in deferCleanupLogs: {exception!r}', exception=exception)

		## end deferCleanupLogs
		return threadHandle


	def cleanupLogs(self):
		"""Check all active jobs to see if there are statistics to process."""
		try:
			self.logger.error('Removing job execution logs older than {hours!r}...', hours=self.localSettings['numberOfHoursToRetainLogFiles'])
			currentTime = time.time()
			thresholdTime = currentTime - self.secondsToRetainLogFiles
			logDir = os.path.join(env.logPath, 'job')
			if os.path.exists(logDir):
				for jobName in os.listdir(logDir):
					if os.path.isdir(os.path.join(logDir, jobName)):
						## For each job directory, stat the log files
						self.logger.error(' Inspecting logs for {jobName!r}', jobName=jobName)
						jobDir = os.path.join(logDir, jobName)
						removedCount = 0
						for logFile in os.listdir(jobDir):
							try:
								endpointLog = os.path.join(jobDir, logFile)
								## epoch seconds
								fileTime = os.path.getmtime(endpointLog)
								if thresholdTime > fileTime:
									self.logger.error('  removing {logFile!r}', logFile=logFile)
									os.remove(endpointLog)
									removedCount += 1
							except:
								exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
								self.logger.error('Exception on log: {logFile!r}: {exception!r}', logFile=logFile, exception=exception)
						if removedCount > 0:
							self.logger.error('  removed {removedCount!r} logs for {jobName!r}', removedCount=removedCount, jobName=jobName)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in cleanupLogs: {exception!r}', exception=exception)

		## end cleanupLogs
		return 'Exiting cleanupLogs'


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
