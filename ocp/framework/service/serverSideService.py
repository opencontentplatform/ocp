"""Server Side Service.

This module is responsible for managing jobs that should only run on the server
side. Jobs normally fall into either contentGathering or universalJob categories
and run on the corresponding clients. The purpose of this particular module is
to enable explicit requirements of jobs needing to run on the server instead of
on any connected client. Take caution running jobs under this service; they may
cause performance bottlenecks on the server, since they run within the thread of
the service and consume system resources (CPU/memory) on the server.

Classes:

  * :class:`.ServerSideService` : entry class for this service
  * :class:`.ServerSideFactory` : Twisted factory for this service

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Dec 9, 2017

"""
import os
import sys
import traceback
import json
import datetime
import time
import importlib
from contextlib import suppress
import twisted.logger
from twisted.protocols.basic import LineReceiver
from twisted.internet import task
from apscheduler.schedulers.background import BackgroundScheduler

## Add openContentPlatform directories onto the sys path
import env
env.addLibPath()
env.addServerSidePkgPath()
env.addContentGatheringSharedScriptPath()

## From openContentPlatform
import sharedService
import utils
import serviceThreadRuntime
import database.schema.platformSchema as platformSchema

## Using an externally provided library defined in globalSettings and located
## in '<install_path>/external'.
externalProtocolHandler = utils.loadExternalLibrary('externalProtocolHandler')


## TODO: break this out from sharedService, which currently uses a TCP-based
## Twisted factory, and use a Thread-based factory without the socket overhead.
class ServerSideListener(LineReceiver):
	def doNothing(self, content):
		pass


class ServerSideFactory(sharedService.ServiceFactory):
	"""Contains custom tailored parts specific to ServerSide."""

	protocol = ServerSideListener

	def __init__(self, serviceName, globalSettings, canceledEvent, shutdownEvent):
		"""Constructor for the ServerSideFactory."""
		self.canceledEvent = canceledEvent
		self.shutdownEvent = shutdownEvent
		self.logFiles = utils.setupLogFile(serviceName, env, globalSettings['fileContainingServiceLogSettings'], directoryName='service')
		self.logObserver  = utils.setupObservers(self.logFiles, serviceName, env, globalSettings['fileContainingServiceLogSettings'])
		self.logger = twisted.logger.Logger(observer=self.logObserver, namespace=serviceName)
		self.validActions = ['connectionRequest', 'healthResponse', 'something']
		self.actionMethods = ['doConnectionRequest', 'doHealthResponse', 'doSomething']
		## Allow the dbClient to get created in the main thread, to reuse pool
		super().__init__(serviceName, globalSettings, False, True)
		self.dbClient.session.close()
		if self.canceledEvent.is_set() or self.shutdownEvent.is_set():
			self.logger.error('Cancelling startup of {serviceName!r}', serviceName=serviceName)
			return
		self.runtime = None
		self.resultCount = {}
		self.kafkaTopic = globalSettings['kafkaTopic']
		self.kafkaProducer = None
		self.createKafkaProducer()
		self.localSettings = utils.loadSettings(os.path.join(env.configPath, globalSettings['fileContainingServerSideSettings']))
		self.pkgPath = env.serverSidePkgPath
		self.scheduler = BackgroundScheduler({
			'apscheduler.executors.default': {
				'class': 'apscheduler.executors.pool:ThreadPoolExecutor',
				'max_workers': '10'
			},
			'apscheduler.timezone': globalSettings.get('localTimezone', 'UTC')
		})
		self.setupJobSchedules()
		self.scheduler.start()
		self.loopingCheckSchedules = task.LoopingCall(self.reportJobSchedules)
		self.loopingCheckSchedules.start(self.localSettings['waitSecondsBetweenReportingJobSchedules'])


	def stopFactory(self):
		"""Manual destructor to cleanup when catching signals."""
		with suppress(Exception):
			self.logger.info('Stopping service factory.')
		print('ServerSideService cleaning up...')
		print('  stopFactory: stopping looping calls')
		with suppress(Exception):
			self.loopingCheckSchedules.stop()
		print('  stopFactory: stopping scheduler')
		with suppress(Exception):
			self.scheduler.shutdown(wait=False)
		with suppress(Exception):
			if self.dbClient is not None:
				print('  stopFactory: closing database connection')
				self.dbClient.close()
		print(' ServerSideService cleanup complete; stopping service.')
		return


	def reportJobSchedules(self):
		## Note: this is a blocking loop
		try:
			scheduledJobs = self.scheduler.get_jobs()
			self.logger.info("Number of jobs [{activeJobs!r}]:", activeJobs=len(scheduledJobs))
			for job in scheduledJobs:
				self.logger.info("  job {job_id!r:4}: {job_name!r}", job_id=job.id, job_name=job.name)
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error(' Exception with job report loop: {stacktrace!r}', stacktrace=stacktrace)


	def handleFailure(self, failure):
		tb = failure.getTraceback()
		print('handleFailure: {}'.format(tb))
		self.logger.error('handleFailure: {traceBack!r}', traceBack = tb)
		failure.trap(RuntimeError)


	def prepareJob(self, *args, **kargs):
		"""Initialize job meta data.

		Arguments:
		  jobName (str) : (args[0]) String containing the module/job name
		  parameters    : Dicitionary containing the job parameters

		"""
		try:
			jobShortName = args[0]
			packageName = args[1]
			## We track jobs based on the full name (package and job) because
			## there is no garantee (nor should there be) of unique job names
			## from independently created modules across the ecosystem.
			jobName = '{}.{}'.format(packageName, jobShortName)
			## Build meta-data by re-parsing job file each time for user updates
			content = {}
			jobSettings = self.loadJobData(jobName, jobShortName, packageName, content)
			if len(jobSettings) <= 0:
				self.logger.error('Failed to prepare job [{jobName!r}] in package [{packageName!r}]. Skipping.', jobName=jobName, packageName=packageName)
				return
			if content['isDisabled']:
				self.logger.debug('Job currently disabled: {jobName!r}', jobName=jobName)
				return

			self.invokeJob(jobName, packageName, jobSettings)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in prepareJob: {exception!r}', exception=exception)

		## end prepareJob
		return


	def loadJobData(self, jobName, jobShortName, packageName, content):
		"""Load at runtime to pick up user changes to job configurations."""
		jobSettings = {}
		try:
			content['jobShortName'] = jobShortName
			## Open defined job configurations
			jobSettingsFile = os.path.join(self.pkgPath, packageName, 'job', '{}.json'.format(jobShortName))
			self.logger.debug('Trying to load: {jobSettingsFile!r}', jobSettingsFile=jobSettingsFile)
			jobSettings = utils.loadSettings(jobSettingsFile)

			## Set parameter defaults when not defined in the JSON file
			content['isDisabled'] = jobSettings.get('isDisabled', False)
			if content['isDisabled']:
				## Avoid additional CPU cycles for the job setup, when disabled
				return jobSettings

			## Verify required parameters are defined
			requiredParams = ['jobScript']
			for requiredParam in requiredParams:
				jobSettings[requiredParam] = jobSettings.get(requiredParam, None)
				if (jobSettings[requiredParam] is None):
					self.logger.error('JSON file for job [{jobName!r}], does not provide {requiredParam!r}; not able to run.', jobName=jobName, requiredParam=requiredParam)
					raise SystemError('JSON file for job [{}], does not provide {}; not able to run.'.format(jobName, requiredParam))

			## Pull out scheduler-specific settings before setting jobMetaData
			for entry in ('triggerType', 'triggerArgs', 'schedulerArgs'):
				jobSettings.pop(entry)

			## Add the API context so jobs can natively talk to the API
			try:
				protocolHandler = externalProtocolHandler.ProtocolHandler(self.dbClient, self.globalSettings, env, self.logger)
			except PermissionError:
				self.logger.error('Unable to create protocolHandler. Make sure your license is compliant.')
				raise
			jobSettings['apiContext'] = protocolHandler.apiContext

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in loadJobData: {exception!r}', exception=exception)
			raise

		## end loadJobData
		return jobSettings


	def invokeJob(self, jobName, packageName, jobSettings):
		try:
			## Dynamic import for job scripts
			packageModule = '{}.{}.{}'.format(packageName, 'script', jobSettings['jobScript'])
			self.logger.debug('Importing module: {packageModule!r}', packageModule=packageModule)
			startJobFunction = getattr(importlib.import_module(packageModule), 'startJob')
			jobStart = datetime.datetime.now()
			self.runtime = serviceThreadRuntime.Runtime(self.logger, jobName, jobSettings, self.dbClient, env, self.sendToKafka)

			## Start job execution; expect updated runtime object and
			## a returned JSON object that will be sent to kafka
			try:
				startJobFunction(self.runtime)
			except:
				self.runtime.setError(__name__)

			## Send any results to Kafka
			try:
				self.sendToKafka()
			except:
				self.logger.error('Error sending results to Kafka. Exception: {exception!r}', exception=str(sys.exc_info()[1]))
				self.runtime.message(str(sys.exc_info()[1]))
			jobStatus = self.runtime.jobStatus
			jobMessages = str(list(self.runtime.jobMessages))

			## Tell job (threaded by schedule) to do garbage cleanup
			del jobSettings

			## Job cleanup
			jobEnd = datetime.datetime.now()
			totalSeconds = (jobEnd - jobStart).total_seconds()
			prettyRunTime = utils.prettyRunTimeBySeconds(totalSeconds)

			## Log and send statistics back
			self.logger.info('Job {jobName!r} complete.  Started at {startDate!r}.  Runtime: {prettyRunTime!r}', jobName=jobName, startDate=jobStart, prettyRunTime=prettyRunTime)
			self.doJobStatistics(jobName, jobStatus, jobMessages, jobStart, jobEnd, totalSeconds)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in {jobName!r} {packageName!r}: {exception!r}', jobName=jobName, packageName=packageName, exception=exception)

		if self.dbClient is not None:
			self.dbClient.session.close()

		## end invokeJob
		return


	def trackResultCount(self, jsonResult):
		"""Accumulate and track object counts.

		This is duplicated from the contentGatheringClient. I am not a fan of
		code duplication, but since the clients and services cannot effectively
		inherit the same base functionality - this is what it is.

		'sendToKafka' can be called inside job scripts multiple times, which is
		recommended for sending back small, bite-sized results. And while that's
		better for the results processing backend (responsible for processing
		data from kafka), it prevents us from doing a single size check on the
		results as you would if the full bulk is returned from the job at the
		end. So the purpose of the count here is to enable a full count of the
		data set in either case, and add that as another job statistic."""
		if (len(jsonResult['objects']) > 0):
			for resultObject in jsonResult['objects']:
				objectType = resultObject.get('class_name')
				prevCount = self.resultCount.get(objectType, 0)
				self.resultCount[objectType] = prevCount + 1
		if (len(jsonResult['links']) > 0):
			for resultLink in jsonResult['links']:
				linkType = resultLink.get('class_name')
				prevCount = self.resultCount.get(linkType, 0)
				self.resultCount[linkType] = prevCount + 1


	def sendToKafka(self, kafkaTopic=None):
		"""Send results from a thread over to kafka queues/topics.

		This is similar to the version in remoteThread. I am not a fan
		of code duplication, but since clients and services cannot effectively
		inherit the same base functionality - this is what it is.
		"""
		jsonResult = self.runtime.results.getJson()
		if (jsonResult is not None and len(jsonResult['objects']) > 0):
			## Accumulate and track object counts.
			self.trackResultCount(jsonResult)
			## Should we verify the type is strictly json or dict
			## before attempting the send? Or let the error return?
			self.logger.debug('Sending to Kafka {jsonResult!r}', jsonResult=jsonResult)
			if kafkaTopic is not None:
				self.kafkaProducer.produce(kafkaTopic, value=json.dumps(jsonResult).encode('utf-8'))
			else:
				self.kafkaProducer.produce(self.kafkaTopic, value=json.dumps(jsonResult).encode('utf-8'))
			self.kafkaProducer.poll(0)
			self.kafkaProducer.flush()
		self.runtime.results.clearJson()


	def doJobStatistics(self, jobName, jobStatus, jobMessages, jobStart, jobEnd, jobRuntime):
		"""Processes statistics coming back on jobs.

		Pulls the job statistics out of the content and stores them in the
		content_gathering_results table.

		Arguments:
		  clientName : String containing the client instance detail
		  content    : Dicitionary containing the Job statistics for the client

		"""
		self.logger.debug('Received {jobName!r} statistics', jobName=jobName)
		try:
			## Run through the results and send to the database
			thisEntry = self.dbClient.session.query(platformSchema.ServerSideResults).filter(platformSchema.ServerSideResults.job == jobName).first() or None
			if thisEntry:
				## Job entry exists; pull current record and update
				setattr(thisEntry, 'status', jobStatus)
				setattr(thisEntry, 'messages', jobMessages)
				setattr(thisEntry, 'time_started', jobStart)
				setattr(thisEntry, 'time_finished', jobEnd)
				setattr(thisEntry, 'time_elapsed', jobRuntime)
				self.dbClient.session.add(thisEntry)
				self.dbClient.session.commit()
				self.logger.debug('Updated job statistics entry for job {jobName!r}', jobName=jobName)
			else:
				## Job entry does not yet exist; create new
				thisEntry = platformSchema.ServerSideResults(job=jobName, status=jobStatus, messages=jobMessages, time_started=jobStart, time_finished=jobEnd, time_elapsed=jobRuntime)
				self.dbClient.session.add(thisEntry)
				self.dbClient.session.commit()
				self.logger.debug('Created new job statistics entry for job {jobName!r}', jobName=jobName)
			## Return underlying DBAPI connection
			self.dbClient.session.close()
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			print('Exception in doJobStatistics: {}'.format(exception))
			self.logger.error('Exception in doJobStatistics: {}'.format(exception))

		## end doJobStatistics
		return


	def doJobResponse(self, topic, content):
		self.logger.warn('Add functionality in doJobResponse for {serviceName!r}', serviceName = self.serviceName)

	def doJobStatus(self, topic, content):
		self.logger.warn('Add functionality in doJobStatus for {serviceName!r}', serviceName = self.serviceName)


class ServerSideService(sharedService.ServiceProcess):
	"""Entry class for the serverSideService.

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
		self.serviceName = 'ServerSideService'
		self.multiProcessingLogContext = 'ServerSideServiceDebug'
		self.serviceFactory = ServerSideFactory
		self.shutdownEvent = shutdownEvent
		self.globalSettings = globalSettings
		## Override IP to ensure no communication until we use reactor thread?
		#self.globalSettings['serviceIpAddress'] = '127.0.0.1'
		self.listeningPort = int(globalSettings['serverSideServicePort'])
		super().__init__()
