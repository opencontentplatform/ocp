"""Shared code for services that invoke remote jobs.

This provides common code used by :class:`ContentGatheringService` and
:class:`UniversalJobService` services, which invoke and manage jobs.

Classes:

  * :class:`.JobServiceFactory` : Twisted factory managing connections for
    job-enabled services
  * :class:`.JobServiceListener` : Twisted protocol for the job factory

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Aug 26, 2019

"""
import os
import sys
import traceback
import json
import time
import datetime
import twisted.logger
from contextlib import suppress
from twisted.internet import reactor, threads, defer, task
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.twisted import TwistedScheduler
from sqlalchemy import and_

## Add openContentPlatform directories onto the sys path
import env
env.addLibPath()

## From openContentPlatform
import networkService
import utils
from utils import logExceptionWithSelfLogger
import database.schema.platformSchema as platformSchema
from utilities import loadConfigGroupFile


class JobServiceListener(networkService.ServiceListener):
	"""Receives and sends data through protocol of choice."""

	def doJobStatistics(self, content):
		"""Calls the doJobStatistics method in JobServiceFactory class."""
		self.factory.logger.info('Received a doJobStatistics')
		self.factory.doJobStatistics(self.clientName, content)

	def doJobFinishedOnClient(self, content):
		"""Calls the doJobFinishedOnClient method in JobServiceFactory class."""
		self.factory.logger.info('Received a doJobFinishedOnClient')
		self.factory.doJobFinishedOnClient(self.clientName, content)

	def doJobIdle(self, content):
		"""Calls the doJobIdle method in JobServiceFactory class."""
		self.factory.logger.info('Received a doJobIdle')
		self.factory.doJobIdle(self.clientName, content)

	def doClientGroups(self, content):
		"""Calls the doClientGroups method in JobServiceFactory class."""
		self.factory.logger.info('Received a doClientGroups')
		self.factory.doClientGroups(self.clientName, content)

	def doCheckModules(self, content):
		self.factory.logger.info('Received a doCheckModules')
		self.factory.doCheckModules(self, content)

	def doSendModule(self, content):
		"""Calls the doSendModule method in JobServiceFactory class."""
		self.factory.logger.info('Received a doSendModule')
		self.factory.doSendModule(self, content)

	def doReceivedFile(self, content):
		"""Calls the doReceivedFile method in JobServiceFactory class."""
		self.factory.logger.info('Received a doReceivedFile')
		self.factory.doReceivedFile(self, content)


class JobServiceFactory(networkService.ServiceFactory):
	"""Contains custom tailored parts specific to JobService."""

	protocol = JobServiceListener

	def __init__(self, serviceName, globalSettings, canceledEvent, shutdownEvent, moduleType, clientEndpointTable, clientResultsTable, serviceResultsTable, serviceJobTable, serviceHealthTable, pkgPath, serviceSettings, serviceLogSetup):
		"""Constructor for the JobServiceFactory."""
		self.canceledEvent = canceledEvent
		self.shutdownEvent = shutdownEvent
		self.logFiles = utils.setupLogFile(serviceName, env, serviceLogSetup, directoryName='service')
		self.logObserver  = utils.setupObservers(self.logFiles, serviceName, env, serviceLogSetup)
		self.logger = twisted.logger.Logger(observer=self.logObserver, namespace=serviceName)
		self.localSettings = utils.loadSettings(os.path.join(env.configPath, serviceSettings))
		self.clientEndpointTable = clientEndpointTable
		self.clientResultsTable = clientResultsTable
		self.serviceResultsTable = serviceResultsTable
		self.serviceJobTable = serviceJobTable
		self.serviceHealthTable = serviceHealthTable
		self.moduleType = moduleType
		self.pkgPath = pkgPath
		self.validActions = ['connectionRequest', 'healthResponse', 'reAuthorization', 'jobStatistics', 'jobFinishedOnClient', 'jobIdle', 'clientGroups', 'checkModules', 'sendModule', 'receivedFile']
		self.actionMethods = ['doConnectionRequest', 'doHealthResponse', 'doReAuthorization', 'doJobStatistics', 'doJobFinishedOnClient', 'doJobIdle', 'doClientGroups', 'doCheckModules', 'doSendModule', 'doReceivedFile']
		super().__init__(serviceName, globalSettings)
		if self.canceledEvent.is_set() or self.shutdownEvent.is_set():
			self.logger.error('Cancelling startup of {serviceName!r}', serviceName=serviceName)
			return
		self.kafkaProducer = self.createKafkaProducer()
		self.jobActiveClients = {}
		self.jobStatistics = {}
		self.clientGroups = {}
		self.moduleFilesToTransfer = []
		self.scheduler = TwistedScheduler({
			'apscheduler.timezone': globalSettings.get('localTimezone', 'UTC')
		})

		## Block on setting schedules; nothing to do without this
		self.setupJobSchedules()
		## Call the scheduler in a different thread, so we can stop it later
		reactor.callInThread(self.scheduler.start)

		## Invoke LoopingCalls to return deferred, because according to the
		## documentation on LoopingCall, "rescheduling will not take place
		## until the deferred has fired." That's important for short cycles
		## or when the main thread is blocking progress.
		self.loopingCheckSchedules = task.LoopingCall(self.deferReportJobSchedules)
		self.loopingCheckSchedules.start(self.localSettings['waitSecondsBetweenReportingJobSchedules'])
		## Watch for events on the same loop schedule as coreService.healthCheck
		self.loopingMainService = task.LoopingCall(self.deferCallMainLoop)
		self.loopingMainService.start(self.globalSettings['waitSecondsBetweenHealthChecks'])


	@logExceptionWithSelfLogger()
	def deferCallMainLoop(self):
		"""Call the main loop in a non-blocking thread."""
		return threads.deferToThread(self.callMainLoop)

	@logExceptionWithSelfLogger()
	def callMainLoop(self):
		## coreService.healthCheck uses coreService.checkEvents; we need to
		## do something similar here since the scheduler needs notified
		#self.logger.info('mainServiceLoop...')
		if self.shutdownEvent.is_set() or self.canceledEvent.is_set():
			self.logger.info('mainServiceLoop: shutting down scheduler.')
			# shutdownArgs = { 'shutdown_threadpool': False }
			# reactor.callFromThread(self.scheduler.shutdown, **shutdownArgs)
			self.scheduler.shutdown(shutdown_threadpool=False)
			self.logger.info('mainServiceLoop: finished.')


	def stopFactory(self):
		"""Manual destructor to cleanup when catching signals.

		Note: SIGTERM seems to go through here, but SIGINT uses a different path
		since it's caught by twisted.internet.base and calls reactor.close. The
		main thread's function is the APScheduler, and not our own. If we had
		our own main function, we would have a place to regularly (in a timed
		loop) check for the event variables (canceledEvent or shutdownEvent) and
		explicitely call cleanup() from there. Outside of that, we could create
		a looping call that would check the same. But looping calls are ignored
		once the twisted.internet.base calls reactor.close. If we could add a
		reactor.addSystemEventTrigger('before', 'shutdown', self.cleanup), that
		would take care of this. But calling that from init above, after the
		reactor starts, does not work... and of course 'self' (the instantiated
		Service) does not exist until after the reactor starts.
		"""
		try:
			self.logger.info('stopFactory called in jobService')
			if self.loopingMainService is not None:
				self.logger.debug(' stopFactory: stopping loopingMainService')
				self.loopingMainService.stop()
				self.loopingMainService = None
			if self.scheduler is not None:
				self.logger.debug(' stopFactory: stopping scheduler')
				#self.scheduler.shutdown(wait=False)
				self.scheduler.shutdown(shutdown_threadpool=False)
				self.scheduler = None
			if self.loopingCheckSchedules is not None:
				self.logger.debug(' stopFactory: stopping loopingCheckSchedules')
				self.loopingCheckSchedules.stop()
				self.loopingCheckSchedules = None
			if self.kafkaProducer is not None:
				self.logger.debug(' stopFactory: stopping kafka producer')
				self.kafkaProducer.flush()
				self.kafkaProducer = None
			super().stopFactory()
			self.logger.info(' jobService stopFactory: complete.')
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			print('Exception in jobService stopFactory: {}'.format(exception))
			with suppress(Exception):
				self.logger.debug('Exception: {exception!r}', exception=exception)

		## end stopFactory
		return


	@logExceptionWithSelfLogger()
	def deferReportJobSchedules(self):
		"""Call reportJobSchedules in a non-blocking thread."""
		return threads.deferToThread(self.reportJobSchedules)


	def reportJobSchedules(self):
		try:
			scheduledJobs = self.scheduler.get_jobs()
			self.logger.info("Number of jobs {activeJobs!r}:", activeJobs=len(scheduledJobs))
			for job in scheduledJobs:
				self.logger.info("  job {job_id!r:4}: {job_name!r}", job_id=job.id, job_name=job.name)
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error(' Exception with job report loop: {stacktrace!r}', stacktrace=stacktrace)


	def prepareJob(self, *args, **kargs):
		"""Initialize job meta data on all connected clients.

		Arguments:
		  jobName (str)     : (args[0]) String containing the job name
		  packageName (str) : (args[1]) Package name, of type content

		"""
		try:
			jobShortName = args[0]
			packageName = args[1]
			## We track jobs based on the full name (package and job) because
			## there is no garantee (nor should there be) of unique job names
			## from independently created modules across the ecosystem.
			jobName = '{}.{}'.format(packageName, jobShortName)
			content = {}
			## Build meta-data by re-parsing job file each time for user updates
			self.loadJobData(jobName, jobShortName, packageName, content)
			if len(content) <= 0:
				self.logger.error('Failed to prepare job {jobName!r} in package {packageName!r}. Skipping.', jobName=jobName, packageName=packageName)
				return
			if content['isDisabled']:
				self.logger.debug(' Job disabled: {jobName!r}', jobName=jobName)
				return
			self.logger.info('Prepare job: {job!r}', job=jobName)
			## Ensure we have at least one active client
			clientGroup = content.get('jobMetaData', {}).get('clientGroup')
			activeClientsInGroup = self.clientGroups.get(clientGroup, [])
			if clientGroup is None:
				activeClientsInGroup = self.activeClients.keys()
			if len(self.activeClients.keys()) <= 0:
				self.logger.error('prepareJob: No active {serviceName!r} found; unable to run job.', serviceName=self.serviceName)
				return
			elif len(activeClientsInGroup) <= 0:
				self.logger.error('prepareJob: No active {serviceName!r} found for the desired group {clientGroup!r}; unable to run job.', serviceName=self.serviceName, clientGroup=clientGroup)
				return

			## See if the job is still running from the last execution
			if jobName in self.jobActiveClients:
				self.logger.debug(' Job {jobName!r} still being worked on these clients from last execution: {activeClients!r}. The job will not re-run until the previous run has been properly cleaned up.', jobName=jobName, activeClients=self.jobActiveClients[jobName])
				return

			## If 'endpointPipeline' was 'kafka', flush kafka topic here on the
			## service before running the job. This is just a safety net in case
			## clients previously entered a bad state and were unable to follow
			## regular cleanup flow. Want to avoid duplicate work in this run...
			endpointPipeline = content.get('jobMetaData').get('endpointPipeline', 'service').lower()
			if endpointPipeline == 'kafka':
				self.scrubKafkaEndpoints(jobName)

			## Construct this version of our activeClients, with our focus group
			groupActiveClients = {}
			for clientName, clientValue in self.activeClients.items():
				if clientName not in activeClientsInGroup:
					continue
				groupActiveClients[clientName] = clientValue

			jobSettings = content['jobMetaData']
			## If job tells us to load configGroups (OS, global, config groups)
			if jobSettings.get('loadConfigGroups', False):
				shellConfig = {}
				## Load from the database...
				realm = jobSettings.get('realm')
				shellConfig['osParameters'] = self.loadPlatformSettings(platformSchema.OsParameters, realm)
				shellConfig['configDefault'] = self.loadPlatformSettings(platformSchema.ConfigDefault, realm)
				shellConfig['configGroups'] = self.loadPlatformSettings(platformSchema.ConfigGroups, realm)
				## Return underlying DBAPI connection from loadPlatformSettings
				self.dbClient.session.close()
				jobSettings['shellConfig'] = shellConfig
				self.logger.info('osParameters: {osParameters!r}', osParameters=shellConfig['osParameters'])

			## If we are running on the content gathering client(s) only, then
			## the job acts more like an integration than a discovery type job:
			clientOnlyTrigger = jobSettings.get('clientOnlyTrigger', False)
			if clientOnlyTrigger:
				clientEndpoint = jobSettings.get('clientEndpoint')
				if clientEndpoint == 'any':
					## Sending to one client (any active one will work)
					for clientName, clientValue in groupActiveClients.items():
						(endpointName, instanceNumber, client) = clientValue
						self.logger.debug('========> clientName: {clientName!r}, endpointName: {endpointName!r}, instanceNumber: {instanceNumber!r}', clientName=clientName, endpointName=endpointName, instanceNumber=instanceNumber)
						self.addJobStatsToContent(content['jobMetaData'], endpointName, jobName)
						self.logger.debug('Job {jobName!r} being sent to client {clientName!r}', jobName=jobName, clientName=clientName)
						client.constructAndSendData('prepareJob', content)
						## Transform 'any' endpoint to selected client instance
						jobSettings['clientEndpoint'] = [clientName]
						break

				elif clientEndpoint == 'all':
					## Sending to all active clients
					uniqueEndpoints = {}
					for clientName, clientValue in groupActiveClients.items():
						(endpointName, instanceNumber, client) = clientValue
						self.addJobStatsToContent(content['jobMetaData'], endpointName, jobName)
						self.logger.debug('Job {jobName!r} being sent to client {clientName!r}', jobName=jobName, clientName=clientName)
						client.constructAndSendData('prepareJob', content)
						if endpointName in uniqueEndpoints.keys():
							continue
						uniqueEndpoints[endpointName] = clientName
					## Change 'all' to one active client per endpoint; keep in
					## mind we can run multiple client instances on the same
					## server endpoint, but we only want to run the job once on
					## an endpoint, not once per client instance
					clients = []
					for thisEndpoint, thisName in uniqueEndpoints.items():
						clients.append(thisName)
					jobSettings['clientEndpoint'] = clients

				else:
					## Using a specified client
					foundEndpoint = False
					for clientName, clientValue in groupActiveClients.items():
						(endpointName, instanceNumber, client) = clientValue
						if endpointName.lower() != clientEndpoint.lower():
							continue
						foundEndpoint = True
						self.addJobStatsToContent(content['jobMetaData'], endpointName, jobName)
						self.logger.debug('Job {jobName!r} being sent to client {clientName!r}', jobName=jobName, clientName=clientName)
						client.constructAndSendData('prepareJob', content)
						## Transform specific endpoint to one client instance;
						## keep in mind we can run multiple client instances on
						## the same server endpoint, but we only want to run the
						## job once on an endpoint, not once per client instance
						jobSettings['clientEndpoint'] = [clientName]
						break
					if not foundEndpoint:
						self.logger.error('prepareJob: Specified {serviceName!r} endpoint {clientEndpoint!r} not found; unable to run job.', serviceName=self.serviceName, clientEndpoint=clientEndpoint)

				## Make sure communication is ordered/synchronized on this
				## step; namely we need to prepare the job before it can be
				## invoked. May later change this to a deffered:
				time.sleep(2)

				## Once the job is setup on the clients, begin sending the
				## lists of target endpoints for the cycle to start
				self.invokeJobOnClient(jobName, packageName, jobSettings.get('clientEndpoint'), content.get('jobMetaData'))

			## Otherwise, we plan to hit many endpoints via remote protocols
			## and therefore need to prepare all the clients for execution;
			## will want to control job flow differently via endpoint chunking:
			else:
				## Send meta-data to all active clients, for job initialization
				if len(groupActiveClients.keys()) <= 0:
					self.logger.error('prepareJob: No active {serviceName!r} found; unable to run job.', serviceName=self.serviceName)
				else:
					jobSettings['clientEndpoint'] = []
					for clientName, clientValue in groupActiveClients.items():
						try:
							(endpointName, instanceNumber, client) = clientValue
							self.logger.debug('Job {jobName!r} being sent to client {clientName!r}', jobName=jobName, clientName=clientName)
							client.constructAndSendData('prepareJob', content)
							jobSettings['clientEndpoint'].append(clientName)
						except:
							exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
							self.logger.error('Exception in prepareJob: {exception!r}', exception=exception)

					## Once the job is setup on the clients, begin sending the
					## lists of target endpoints for the cycle to start
					self.invokeJob(jobName, packageName, list(groupActiveClients.keys()), jobSettings.get('endpointQuery'), jobSettings.get('endpointScript'), content.get('jobMetaData'))

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in prepareJob: {exception!r}', exception=exception)

		## end prepareJob
		return


	def loadJobData(self, jobName, jobShortName, packageName, content):
		"""Load at runtime to pick up user changes to job configurations."""
		try:
			content['jobName'] = jobName
			content['jobShortName'] = jobShortName
			content['packageName'] = packageName

			## Open defined job configurations
			jobSettings = self.getSpecificJob(jobName)

			## Set parameter defaults when not defined in the JSON file
			content['isDisabled'] = jobSettings.get('isDisabled', False)
			if content['isDisabled']:
				## Avoid additional CPU cycles for the job setup, when disabled
				return

			## Default the realm, clientGroup, and credentialGroup
			if not 'realm' in jobSettings:
				jobSettings['realm'] = self.localSettings.get('defaultRealm', 'default')
			if not 'numberOfJobThreads' in jobSettings:
				jobSettings['numberOfJobThreads'] = self.localSettings.get('defaultNumberOfJobThreads', 30)
			## Use runtime values if defined, otherwise use local Setting defaults
			runTimeValues = jobSettings.get('runTimeValues', {})
			jobSettings['maxJobRunTime'] = runTimeValues.get('maxJobRunTime', self.localSettings.get('defaultMaxJobRunTime', 600))
			jobSettings['maxProtocolTime'] = runTimeValues.get('maxProtocolTime', self.localSettings.get('defaultMaxProtocolTime', 600))
			jobSettings['maxCommandTime'] = runTimeValues.get('maxCommandTime', self.localSettings.get('defaultMaxCommandTime', 60))

			## Verify required parameters are defined
			requiredParams = ['jobScript', 'endpointIdColumn']
			clientOnlyTrigger = jobSettings.get('clientOnlyTrigger', False)
			if clientOnlyTrigger:
				## If running on any/all/specific content gathering client(s),
				## we leverage the clientEndpoint instead of an endpointQuery
				requiredParams = ['jobScript', 'clientEndpoint']
			for requiredParam in requiredParams:
				content[requiredParam] = jobSettings.get(requiredParam, None)
				if (content[requiredParam] is None):
					self.logger.error('JSON file for job {jobName!r}, does not provide {requiredParam!r}; not able to run.', jobName=jobName, requiredParam=requiredParam)
					raise SystemError('JSON file for job {}, does not provide {}; not able to run.'.format(jobName, requiredParam))

			self.protocolHandler.create(jobSettings)

			## Pull out scheduler-specific settings before setting jobMetaData
			for entry in ('triggerType', 'triggerArgs', 'schedulerArgs'):
				jobSettings.pop(entry, None)
			## And pull out whatever was moved up a level; remove duplication
			for entry in ('jobName', 'jobScript', 'isDisabled'):
				jobSettings.pop(entry, None)
			content['jobMetaData'] = jobSettings

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in loadJobData: {exception!r}', exception=exception)
			raise

		## end loadJobData
		return


	def addJobStatsToContent(self, content, endpoint, jobName):
		self.logger.debug('addJobStatsToContent... looking for endpoint {endpoint!r}', endpoint=endpoint)
		thisEntry = self.dbClient.session.query(self.clientResultsTable).filter(and_(self.clientResultsTable.endpoint == endpoint, self.clientResultsTable.job == jobName)).first()
		statistics = {}
		if thisEntry:
			statistics['status'] = thisEntry.status
			statistics['messages'] = str(thisEntry.messages)[:8096]
			statistics['client_name'] = thisEntry.client_name
			statistics['time_started'] = utils.customJsonDumpsConverter(thisEntry.time_started)
			statistics['time_finished'] = utils.customJsonDumpsConverter(thisEntry.time_finished)
			statistics['time_elapsed'] = utils.customJsonDumpsConverter(thisEntry.time_elapsed)
			statistics['result_count'] = thisEntry.result_count
			statistics['date_last_invocation'] = utils.customJsonDumpsConverter(thisEntry.date_last_invocation)
			statistics['date_last_success'] = utils.customJsonDumpsConverter(thisEntry.date_last_success)
			statistics['consecutive_jobs_passed'] = thisEntry.consecutive_jobs_passed
			statistics['total_jobs_passed'] = thisEntry.total_jobs_passed
			statistics['date_last_failure'] = utils.customJsonDumpsConverter(thisEntry.date_last_failure)
			statistics['consecutive_jobs_failed'] = thisEntry.consecutive_jobs_failed
			statistics['total_jobs_failed'] = thisEntry.total_jobs_failed
			statistics['total_job_invocations'] = thisEntry.total_job_invocations
		content['previousRuntimeStatistics'] = statistics
		self.dbClient.session.commit()
		self.dbClient.session.close()
		self.logger.debug('addJobStatsToContent: stats: {statistics!r}', statistics=statistics)

		## addJobStatsToContent
		return


	def initializeJobStats(self, jobName, resultCount, clientEndpoints):
		## Track jobs to know when they have reported back, and enable a level
		## of statistical analysis over time:
		jobStats = {}
		jobStats['job'] = jobName
		jobStats['endpoint_count'] = resultCount
		jobStats['time_started'] = datetime.datetime.now()
		jobStats['active_client_list'] = clientEndpoints[:]
		jobStats['active_client_count'] = len(jobStats['active_client_list'])
		jobStats['completed_count'] = 0
		jobStats['job_completed'] = False
		jobStats['count_per_client'] = {}
		for clientEndpoint in clientEndpoints:
			jobStats['count_per_client'][clientEndpoint] = 0
		jobStats['count_per_status'] = {}

		## Create initial result stat in database, to be updated as job runs
		thisEntry = self.serviceResultsTable(**jobStats)
		self.dbClient.session.add(thisEntry)
		self.dbClient.session.commit()
		self.dbClient.session.close()

		## Store the stats for final processing
		self.jobStatistics[jobName] = jobStats

		## end initializeJobStats
		return


	def finalizeJobStats(self, jobName):
		jobStats = self.jobStatistics[jobName]
		jobStats['time_finished'] = datetime.datetime.now()
		jobStats['time_elapsed'] = (jobStats['time_finished'] - jobStats['time_started']).total_seconds()
		if jobStats['endpoint_count'] == jobStats['completed_count']:
			jobStats['job_completed'] = True

		## Update result entry in database
		thisEntry = self.dbClient.session.query(self.serviceResultsTable).filter(and_(self.serviceResultsTable.job == jobName, self.serviceResultsTable.time_started == jobStats['time_started'])).first()
		if thisEntry:
			setattr(thisEntry, 'time_finished', jobStats['time_finished'])
			setattr(thisEntry, 'time_elapsed', jobStats['time_elapsed'])
			setattr(thisEntry, 'job_completed', jobStats['job_completed'])
			setattr(thisEntry, 'completed_count', jobStats['completed_count'])
			self.dbClient.session.add(thisEntry)
		else:
			## This should never happen; the entry should have been created
			## when the job started, and updated regularly during runtime
			self.logger.error('Service results entry does not exist for job {jobName!r} with start time {startTime!r}', jobName=jobName, startTime=jobStats['time_started'])

		## Return underlying DBAPI connection
		self.dbClient.session.commit()
		self.dbClient.session.close()

		## end finalizeJobStats
		return


	def invokeJobOnClient(self, jobName, packageName, clientEndpoints, metaData):
		"""Sends jobs to specified client endpoint(s).

		Arguments:
		  jobName (str)     : String containing the module/job name
		  packageName (str) : Package name, of type content

		"""
		try:
			resultCount = len(clientEndpoints)
			self.initializeJobStats(jobName, resultCount, clientEndpoints)
			self.jobActiveClients[jobName] = []

			for clientEndpoint in clientEndpoints:
				(endpointName, instanceNumber, client) = self.activeClients.get(clientEndpoint)
				self.jobActiveClients[jobName].append(clientEndpoint)
				content = {}
				content['jobName'] = jobName
				content['endpoints'] = [{ "value": endpointName }]
				## Let the clients know that was the full data set
				content['complete'] = True
				self.logger.debug('Job {jobName!r} being sent to client {clientName!r}', jobName=jobName, clientName=clientEndpoint)
				client.constructAndSendData('jobEndpoints', content)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in invokeJobOnClient: {exception!r}', exception=exception)

		## end invokeJobOnClient
		return


	def invokeJob(self, jobName, packageName, clientEndpoints, endpointQuery, endpointScript, metaData):
		"""Sends job endpoints to clients in order to start content gathering.

		Arguments:
		  jobName : String containing the module/job name

		"""
		try:
			## Add the packages path in case this is the first invocation
			thisPackagePath = os.path.join(self.pkgPath, packageName)
			if self.pkgPath not in sys.path:
				sys.path.append(self.pkgPath)
			if thisPackagePath not in sys.path:
				sys.path.append(thisPackagePath)

			## Get target endpoints (via either JSON query or Python script)
			endpointList = []
			if endpointQuery is not None:
				## Prefer to use JSON Query over Python Script
				dbTable = platformSchema.EndpointQuery
				dataHandle = self.dbClient.session.query(dbTable).filter(dbTable.name == endpointQuery).first()
				if not dataHandle:
					raise EnvironmentError('Endpoint query not found: {}'.format(endpointQuery))
				queryDefinition = dataHandle.content
				utils.executeProvidedJsonQuery(self.logger, self.dbClient, queryDefinition, endpointList)
				#utils.getEndpointsFromJsonQuery(self.logger, self.dbClient, thisPackagePath, packageName, endpointQuery, endpointList)
				## Using list comprehension to remove any endpoints not matching
				## the job's realm, and doing this in place on the endpointList.
				## Important to mention that just because it has a realm, does
				## NOT mean it's actually in the realm scope. So a simple attr
				## comparison like this will not work:
				# endpointList[:] = [x for x in endpointList if (x.get('data', {}).get('realm') == metaData['realm'])]
				## Instead, we need to use the realm utility and ensure the IP
				## is included in defined scope before allowing execution
				realmUtil = utils.RealmUtility(self.dbClient)
				self.logger.debug('invokeJob: Endpoint list size before realm compare: {size!r}', size=len(endpointList))
				endpointList[:] = [x for x in endpointList if (realmUtil.isIpInRealm(x.get('data', {}).get('ipaddress', x.get('data', {}).get('address')), metaData['realm']))]
				self.logger.debug('invokeJob: Endpoint list size after realm compare: {size!r}', size=len(endpointList))
			else:
				utils.getEndpointsFromPythonScript(self.logger, self.dbClient, thisPackagePath, packageName, endpointScript, endpointList, metaData)
			## Return underlying DBAPI connection
			self.dbClient.session.close()
			resultCount = len(endpointList)

			## If there are zero target endpoints, spin the jobs back down.
			if resultCount <= 0:
				## No target endpoints returned
				self.logger.debug('No target endpoints found for job {jobName!r}', jobName=jobName)
				self.logger.info('invokeJob telling clients to remove job {jobName!r}', jobName=jobName)
				self.doJobComplete(jobName)
				return

			## If this is a single endpoint test (i.e. development testing)
			if metaData.get('singleEndpointTest', False):
				newList = []
				newList.append(endpointList[0])
				endpointList = newList
				resultCount = 1

			self.initializeJobStats(jobName, resultCount, clientEndpoints)
			self.jobActiveClients[jobName] = []

			endpointPipeline = metaData.get('endpointPipeline', 'service').lower()
			numberOfJobThreads = metaData.get('numberOfJobThreads', 1)
			endpointChunkSize = metaData.get('endpointChunkSize', numberOfJobThreads)

			## If this is set to 'kafka', then create the Kafka producer for the
			## job, and send the endpointList through. This is the recommended
			## pipeline for providing work to the client worker threads.
			##
			## This not only throttles the load for clients, but also enables an
			## organic-type of load balancing. This is because the performance
			## of worker threads is determined at runtime, based on conditions
			## of the execution environment, which change while the job runs.
			## CPU/memory/disk/network conditions are only part. Consider also
			## other jobs running... the number of threads and the type/load of
			## the job. For example, a single ETL type integration flow might
			## consume high resources for 15 minutes. Let's say that single job
			## thread is running on client1. Contrast that with client2 running
			## 200 ICMP-type job threads, and yet client2 has much lower system
			## utilization. Also, keep in mind overlapping jobs when they are
			## kicked off after the start of the previous job.
			##
			## By using a shared work queue (kafka), workers can work as fast as
			## they are able. New jobs for clients will be pulled off kafka as
			## needed, instead of being assigned a predetermined number of
			## endpoints. So new jobs invoked on client2 may show a completion
			## rate of 200 every 10 seconds, whereas the same new jobs invoked
			## on client1 (running the ETL job) may show a reduced turnaround of
			## 20 every 10 seconds. No need to proactively manage this if we let
			## clients pull work as needed... and the job will continue to be
			## balanced until it's finished.
			if endpointPipeline == 'kafka':
				self.logger.debug('Job {jobName!r} is planning to use kafka for the endpointPipeline. Active clients: {clients!r}', jobName=jobName, clients=self.activeClients.keys())
				self.logger.debug('Job {jobName!r}: {num!r} endpoints being sent to kafka', jobName=jobName, num=len(endpointList))
				## If we don't pause a few seconds before sending in endpoints,
				## the first connected client will get the brunt of the work
				self.logger.debug('Job {jobName!r}: pausing 3 seconds for kafka to rebalance all the newly connected consumer clients', jobName=jobName)
				time.sleep(3)
				self.logger.debug('Job {jobName!r}: continuing now...', jobName=jobName)
				for endpoint in endpointList:
					if not (self.canceledEvent.is_set() or self.shutdownEvent.is_set()):
						try:
							message = {'endpoint': endpoint}
							self.kafkaProducer.poll(0)
							## If we want to see each entry into kafka logged:
							self.kafkaProducer.produce(jobName, value=json.dumps(message).encode('utf-8'), callback=self.kafkaDeliveryReport)
						except:
							exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
							self.logger.error('Exception in invokeJob: {exception!r}', exception=exception)
				self.kafkaProducer.flush()
				self.logger.debug('  invokeJob: kafka producer sent and flushed jobs on topic {topic!r}...', topic=jobName)
				self.logger.debug('Job {jobName!r} finished sending endpoints into kafka.', jobName=jobName)
				## Add the clients to the active job list
				for clientEndpoint in clientEndpoints:
					self.jobActiveClients[jobName].append(clientEndpoint)

			## If this is service, then the service sends the chunks directly to
			## active clients... all at the start (not throttled).
			elif endpointPipeline == 'service':
				self.logger.debug('Job {jobName!r} is planning to use service for the endpointPipeline. Active clients: {clients!r}', jobName=jobName, clients=self.activeClients.keys())
				## Determine number of chunks
				(numberOfChunks, remainder) = divmod(resultCount, endpointChunkSize)
				if remainder > 0:
					numberOfChunks += 1
				## Now split the endpoints into requested sized chunks
				splitTargets = utils.chunk(endpointList, numberOfChunks)
				self.logger.debug('splitTargets length: {splitTargets!r}', splitTargets=len(splitTargets))
				## These targets are split up, but they are not being throttled.
				## All desired targets are sent at the start of the run. Consider
				## a client going MIA sometime during a job runtime. To leverage
				## throttling and true load balancing, you should consider using
				## the 'kafka' endpointPipeline setting instead of 'service'.

				## Make sure communication is ordered/synchronized on this step;
				## namely we need to prepare the job before it can be invoked.
				## Probably should change this to a deffered, but we prefer folks
				## use the 'kafka' method instead... so less support is on this.
				time.sleep(2)

				## May want to do a divmod on the number of chunks verses number
				## of activeClients. For example, if there are 2 clients and 5
				## chunks, we probably want to take the last chunk and split it
				## in two for the client count.
				x = 0
				while x < numberOfChunks and not (self.canceledEvent.is_set() or self.shutdownEvent.is_set()):
					## Only use clients that matched the job's client group
					#for clientName, clientValue in self.activeClients.items():
					for clientEndpoint in clientEndpoints:
						(endpointName, instanceNumber, client) = self.activeClients.get(clientEndpoint)
						if x >= numberOfChunks:
							break
						try:
							content = {}
							content['jobName'] = jobName
							targets = splitTargets[x]
							content['endpoints'] = targets
							client.constructAndSendData('jobEndpoints', content)
						except:
							exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
							self.logger.error('Exception in invokeJob: {exception!r}', exception=exception)
						x += 1
				## Let the clients know that was the full data set
				for clientEndpoint in clientEndpoints:
					(endpointName, instanceNumber, client) = self.activeClients.get(clientEndpoint)
					client.constructAndSendData('jobEndpoints', {'jobName': jobName, 'complete': True, 'endpoints': []})
					## Add the client to the active job list
					self.jobActiveClients[jobName].append(clientEndpoint)

			else:
				self.logger.error('Job {jobName!r} has unrecognized endpointPipeline setting: {endpointPipeline!r}.  Expected value to be \'service\' or \'kafka\'.', jobName=jobName, endpointPipeline=endpointPipeline)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in invokeJob: {exception!r}', exception=exception)

		## end invokeJob
		return

	def kafkaDeliveryReport(self, err, msg):
		""" Called once for each message produced to indicate delivery result.
			Triggered by poll() or flush(). """
		if err is not None:
			self.logger.error('Kafka message delivery failed: {}'.format(err))
		else:
			self.logger.debug('Kafka message delivered to {} [{}]'.format(msg.topic(), msg.partition()))

	def doJobStatistics(self, clientName, content):
		"""Processes statistics coming back on jobs.

		Pulls the job statistics out of the content and stores them in the
		content_gathering_results table.

		Arguments:
		  clientName : String containing the client instance detail
		  content    : Dicitionary containing the Job statistics for the client

		"""
		jobName = content['jobName']
		self.logger.debug('Received {jobName!r} statistics from {clientName!r}: {content!r}', jobName=jobName, clientName=clientName, content=content)
		try:
			resultLines = content['statistics']
			## Get a handle on the stats for this job
			jobStats = self.jobStatistics[jobName]
			totalCount = jobStats['endpoint_count']
			completedCount = jobStats['completed_count']
			completedCount += len(resultLines)
			jobStats['completed_count'] = completedCount

			## Process CLIENT-SIDE status results
			self.logger.info('  totalCount: {totalCount!r}, completedCount: {completedCount!r}', totalCount=totalCount, completedCount=completedCount)
			## Run through the results and update client-side stats
			for result in resultLines:
				endpoint = result['endpoint']
				jobStatus = result['status']
				jobMessages = result['messages']
				## Updating count_per_status for the service-side stats
				jobStats['count_per_status'][jobStatus] = jobStats['count_per_status'].get(jobStatus, 0) + 1

				## Pull the datetime fields out of the JSON and explicitely
				## typecast back to datetime fields so we can send to the DB
				jobStart = datetime.datetime.strptime(result['start'], '%Y-%m-%d %H:%M:%S.%f')
				jobEnd = datetime.datetime.strptime(result['end'], '%Y-%m-%d %H:%M:%S.%f')
				jobRuntime = (jobEnd - jobStart).total_seconds()
				jobResultCount = result['results']

				thisEntry = self.dbClient.session.query(self.clientResultsTable).filter(and_(self.clientResultsTable.endpoint == endpoint, self.clientResultsTable.job == jobName)).first()
				self.dbClient.session.commit()
				if thisEntry:
					prevStatus = thisEntry.status
					prevConJobPass = thisEntry.consecutive_jobs_passed
					prevConJobFail = thisEntry.consecutive_jobs_failed

					## Job entry exists; pull current record and update
					setattr(thisEntry, 'status', jobStatus)
					setattr(thisEntry, 'messages', jobMessages)
					setattr(thisEntry, 'client_name', clientName)
					setattr(thisEntry, 'time_started', jobStart)
					setattr(thisEntry, 'time_finished', jobEnd)
					setattr(thisEntry, 'time_elapsed', jobRuntime)
					setattr(thisEntry, 'result_count', jobResultCount)
					setattr(thisEntry, 'date_last_invocation', jobStart)

					## If this execution didn't outright fail (success/warning)
					if jobStatus != 'FAILURE':
						setattr(thisEntry, 'date_last_success', jobStart)
						setattr(thisEntry, 'total_jobs_passed', thisEntry.total_jobs_passed + 1)
						## If last execution failed, this is the first consecutive pass
						if prevStatus == 'FAILURE':
							prevConJobPass = 0
						setattr(thisEntry, 'consecutive_jobs_passed', prevConJobPass + 1)
					## If this execution failed
					else:
						setattr(thisEntry, 'date_last_failure', jobStart)
						setattr(thisEntry, 'total_jobs_failed', thisEntry.total_jobs_failed + 1)
						## If last execution didn't fail, this is the first consecutive fail
						if prevStatus != 'FAILURE':
							prevConJobFail = 0
						setattr(thisEntry, 'consecutive_jobs_failed', prevConJobFail + 1)

					setattr(thisEntry, 'total_job_invocations', thisEntry.total_job_invocations + 1)
					self.dbClient.session.add(thisEntry)
					self.dbClient.session.commit()
					self.logger.debug('Updated job statistics entry for job {jobName!r} endpoint {endpoint!r}', jobName=jobName, endpoint=endpoint)
				else:
					## Job entry does not yet exist; create new
					thisEntry = None
					if jobStatus != 'FAILURE':
						thisEntry = self.clientResultsTable(endpoint=endpoint, job=jobName, status=jobStatus, messages=jobMessages, client_name=clientName, time_started=jobStart, time_finished=jobEnd, time_elapsed=jobRuntime, result_count=jobResultCount, date_first_invocation=jobStart, date_last_invocation=jobStart, date_last_success=jobStart, consecutive_jobs_passed=1, total_jobs_passed=1, total_job_invocations=1)
					else:
						thisEntry = self.clientResultsTable(endpoint=endpoint, job=jobName, status=jobStatus, messages=jobMessages, client_name=clientName, time_started=jobStart, time_finished=jobEnd, time_elapsed=jobRuntime, result_count=jobResultCount, date_first_invocation=jobStart, date_last_invocation=jobStart, date_last_failure=jobStart, consecutive_jobs_failed=1, total_jobs_failed=1, total_job_invocations=1)
					self.dbClient.session.add(thisEntry)
					self.dbClient.session.commit()
					self.logger.debug('Created new job statistics entry for job {jobName!r} endpoint {endpoint!r}', jobName=jobName, endpoint=endpoint)
				## Return underlying DBAPI connection
				self.dbClient.session.close()

			## Process SERVICE-SIDE status results
			countPerClient = jobStats['count_per_client']
			countPerClient[clientName] = countPerClient.get(clientName, 0) + len(resultLines)
			self.jobStatistics[jobName] = jobStats
			## Update service-side stats
			thisEntry = self.dbClient.session.query(self.serviceResultsTable).filter(and_(self.serviceResultsTable.job == jobName, self.serviceResultsTable.time_started == jobStats['time_started'])).first()
			if thisEntry:
				setattr(thisEntry, 'completed_count', jobStats['completed_count'])
				setattr(thisEntry, 'count_per_client', jobStats['count_per_client'])
				setattr(thisEntry, 'count_per_status', jobStats['count_per_status'])
				self.dbClient.session.add(thisEntry)
				self.dbClient.session.commit()
			else:
				## This should never happen; the entry should have been created
				## when the job started, and updated regularly during runtime
				self.logger.error('Cannot update stats. Service results entry does not exist for job {jobName!r} with start time {startTime!r}', jobName=jobName, startTime=jobStats['time_started'])

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in doJobStatistics: {exception!r}', exception=exception)

		## end doJobStatistics
		return


	def removeClientFromAllActiveJobs(self, clientName):
		"""Special job cleanup when a client connects into the service.

		If a client was restarted while active, any jobs that client was running
		at the time will no longer be running... it will return to a clean state
		without any knowledge of work. So we need to mirror this state on the
		server side by scrubbing it from any active jobs being tracked.
		"""
		self.logger.info('removeClientFromAllActiveJobs: started for client {clientName!r}...', clientName=clientName)
		self.logger.info('removeClientFromAllActiveJobs: jobNames: {jobName!r}', jobName=self.jobActiveClients.keys())
		self.logger.info('removeClientFromAllActiveJobs: activeClients: {activeClients!r}', activeClients=self.jobActiveClients)
		for jobName in list(self.jobActiveClients.keys()):
			if clientName in self.jobActiveClients[jobName]:
				self.logger.info('removeClientFromAllActiveJobs: removing client {clientName!r} from job {jobName!r}', clientName=clientName, jobName=jobName)
				self.jobActiveClients[jobName].remove(clientName)
				## If all the clients reported back in, shut it down
				if len(self.jobActiveClients[jobName]) <= 0:
					self.logger.info('removeClientFromAllActiveJobs: calling doJobComplete for job {jobName!r}', jobName=jobName)
					self.doJobComplete(jobName)

		## end removeClientFromAllActiveJobs
		return


	def doJobFinishedOnClient(self, clientName, content):
		"""Regular job cleanup when things go right.

		The client tells the service it's finished, and the service pulls it out
		of active duty, and cleans the rest if it was the last remaining client.
		"""
		jobName = content['jobName']
		self.logger.info('doJobFinishedOnClient: job {jobName!r} finished on client {clientName!r}', jobName=jobName, clientName=clientName)
		if clientName in self.jobActiveClients[jobName]:
			self.jobActiveClients[jobName].remove(clientName)
		clientEndpoints = self.jobActiveClients[jobName]
		## If all the clients reported back in, shut it down:
		if len(clientEndpoints) <= 0:
			self.doJobComplete(jobName)

		## end doJobFinishedOnClient
		return


	def doJobIdle(self, clientName, content):
		"""Verify client has nothing more to do."""
		jobName = content['jobName']
		self.logger.info('inside doJobIdle for {jobName!r}--{clientName!r}', jobName=jobName, clientName=clientName)

		if jobName in self.jobStatistics:
			jobStats = self.jobStatistics[jobName]
			totalCount = jobStats['endpoint_count']
			completedCount = jobStats['completed_count']
			self.logger.info('totalCount: {totalCount!r}, completedCount: {completedCount!r}', totalCount=totalCount, completedCount=completedCount)

		## end doJobIdle
		return


	def doClientGroups(self, clientName, content):
		"""Associate client groups configured for this client."""
		try:
			clientGroups = content.get('clientGroups')
			self.logger.info('inside doClientGroups1 for {clientName!r}; found groups: {clientGroups!r}', clientName=clientName, clientGroups=clientGroups)
			for clientGroup in clientGroups:
				if clientGroup not in self.clientGroups:
					self.clientGroups[clientGroup] = [clientName]
				else:
					tmpList = self.clientGroups[clientGroup]
					if clientName not in tmpList:
						self.clientGroups[clientGroup].append(clientName)
			self.logger.info('inside doClientGroups2 for {clientName!r}; current groups: {clientGroups!r}', clientName=clientName, clientGroups=self.clientGroups)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in doClientGroups: {exception!r}', exception=exception)

		## end doClientGroups
		return


	def removeClientGroups(self, clientName):
		"""Remove client from previously configured groups."""
		try:
			self.logger.info('inside removeClientGroups1 for {clientName!r}; old groups: {clientGroups!r}', clientName=clientName, clientGroups=self.clientGroups)
			for clientGroup,clientList in self.clientGroups.items():
				with suppress(ValueError, AttributeError):
					clientList.remove(clientName)
			## Should I also remove the group key if no active clients exist?
			for clientGroup in list(self.clientGroups.keys()):
				if not len(self.clientGroups[clientGroup]):
					self.clientGroups.pop(clientGroup)
			self.logger.info('inside removeClientGroups2 for {clientName!r}; new groups: {clientGroups!r}', clientName=clientName, clientGroups=self.clientGroups)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in removeClientGroups: {exception!r}', exception=exception)

		## end removeClientGroups
		return


	def loadPlatformSettings(self, dbTable, realm):
		content = None
		dataHandle = self.dbClient.session.query(dbTable).filter(dbTable.realm==realm).first()
		self.dbClient.session.commit()
		if dataHandle is None:
			self.logger.error('loadPlatformSettings: No entry found in table {dbTable!r} for realm {realm!r}', dbTable=str(dbTable), realm=realm)
			raise EnvironmentError('loadPlatformSettings: No entry found in table {} for realm {}'.format(str(dbTable), realm))
		else:
			## Get the previous ConfigGroup contents saved in the DB
			content = dataHandle.content

		## end loadPlatformSettings
		return content


	def doCheckModules(self, client, content):
		try:
			###########################################################
			## Need to validate the token before actually activating the client,
			## in order to transfer files...
			self.logger.debug('doCheckModules: content: {content!r}', content=content)
			endpointName = content['endpointName']
			endpointToken = content['endpointToken']
			self.logger.debug('doCheckModules: received client connection from {endpointName!r}', endpointName=endpointName)
			## Checks if the endpoint is an authorized endpoint.
			if not self.validateClient(endpointName, endpointToken):
				## For clients connecting the very first time, their keys were just
				## created in the database, so we'll need to get an updated list
				self.getServiceClients()
				if not self.validateClient(endpointName, endpointToken):
					self.logger.error('doCheckModules: Did NOT authenticate client; dropping connection from {endpointName!r}', endpointName=endpointName)
					self.constructAndSendData('connectionResponse', {'Response' : 'Not authorized to use this service'})
					return
			###########################################################
			self.logger.debug('doCheckModules: ...starting work... {endpointName!r}', endpointName=endpointName)
			moduleSnapshots = {}
			modules = self.dbClient.session.query(platformSchema.ContentPackage).filter(platformSchema.ContentPackage.system==self.moduleType).all()
			self.dbClient.session.commit()
			for module in modules:
				moduleName = module.name
				snapshot = module.snapshot
				moduleSnapshots[moduleName] = snapshot

			## Ensure we also include the 'shared' package; it would have been
			## included if it was a ContentGathering client request, but other
			## clients need it too (e.g. universalJob).
			if self.moduleType != 'contentGathering':
				self.logger.debug('doCheckModules: need to add shared')
				sharedModule = self.dbClient.session.query(platformSchema.ContentPackage).filter(platformSchema.ContentPackage.name=='shared').first()
				self.dbClient.session.commit()
				if sharedModule:
					moduleName = sharedModule.name
					snapshot = sharedModule.snapshot
					moduleSnapshots[moduleName] = snapshot
					self.logger.debug('doCheckModules: added shared {}'.format(snapshot))

			## Provide the client with the current module snapshot (UUID) values
			content = {}
			content['content'] = moduleSnapshots
			client.constructAndSendData('moduleSnapshots', content)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in doCheckModules: {exception!r}', exception=exception)

		## end doCheckModules
		return


	def getFileChunk(self, targetFile, chunkSize=8192):
		## Generator function that returns chunks of
		## binary data, to be processed one at a time
		with open(targetFile, 'rb') as fh:
			while 1:
				thisChunk = fh.read(chunkSize)
				if thisChunk:
					## generator
					yield thisChunk
				else:
					break
		## end getFileChunk
		return


	def sendFile(self, client, requestedModule, requestedSnapshot):
		try:
			if len(self.moduleFilesToTransfer) <= 0:
				self.logger.debug('sendFile: package {requestedModule!r} has no files remaining for transfer', requestedModule=requestedModule)
				content = {}
				content['module'] = requestedModule
				content['snapshot'] = requestedSnapshot
				client.constructAndSendData('moduleComplete', content)
			else:
				## Popping will process files in reverse, but that's fine
				fileId = self.moduleFilesToTransfer.pop()
				self.logger.error('sendFile: looking at file ID {fileId!r}', fileId=fileId)
				moduleFile = self.dbClient.session.query(platformSchema.ContentPackageFile).filter(platformSchema.ContentPackageFile.object_id == fileId).first()
				self.dbClient.session.commit()
				## Pull this file's attributes and content
				fileName = moduleFile.name
				fileContent = moduleFile.content
				pathString = moduleFile.path
				fileHash = moduleFile.file_hash
				fileSize = moduleFile.size
				## Construct a line mode message to send the client before
				## dropping into Raw mode in order to transfer file contents
				content = {}
				content['module'] = requestedModule
				content['snapshot'] = requestedSnapshot
				content['fileName'] = fileName
				content['fileHash'] = fileHash
				content['fileSize'] = fileSize
				content['pathString'] = pathString
				content['contentLength'] = 0
				## Determine the number of chunks needed to send the file
				chunkSize = self.localSettings.get('moduleTransferChunkSize', 8192)
				dataSize = len(fileContent)
				chunkCount = int(dataSize/chunkSize)
				if (dataSize%chunkSize):
					chunkCount += 1
				content['contentLength'] = dataSize
				self.logger.debug('Client requesting file: {fileName!r}', fileName=content)
				client.constructAndSendData('moduleFile', content)
				## Change communication type to Raw before sending file
				self.logger.debug('  setting to Raw mode')
				client.setRawMode()
				## Send the file in chunks
				self.logger.debug('  sending file contents...')
				for chunkId in range(chunkCount):
					self.logger.debug('  sending chunk #{chunkId!r} of {chunkCount!r}', chunkId=chunkId+1, chunkCount=chunkCount)
					chunk = fileContent[:chunkSize]
					client.transport.write(chunk)
					with suppress(Exception):
						fileContent = fileContent[chunkSize:]
				## Mark the end of file
				client.transport.write(b':==:')
				## Set back to LineReceiver mode
				client.setLineMode()
				self.logger.debug('  resetting to LineReceiver mode')
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in sendFile: {exception!r}', exception=exception)

		## end sendFile
		return


	def doReceivedFile(self, client, content):
		try:
			self.logger.debug('inside doReceivedFile')
			requestedModule = content.get('module')
			requestedSnapshot = content.get('snapshot')
			## Send the next file
			self.sendFile(client, requestedModule, requestedSnapshot)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in doReceivedFile: {exception!r}', exception=exception)

		## end doReceivedFile
		return


	def doSendModule(self, client, content):
		try:
			self.logger.debug('inside doSendModule')
			requestedModule = content.get('module')
			requestedSnapshot = content.get('snapshot')
			self.logger.error('doSendModule: module to request: {requestedModule!r}', requestedModule=requestedModule)
			self.moduleFilesToTransfer = []
			module = self.dbClient.session.query(platformSchema.ContentPackage).filter(platformSchema.ContentPackage.name == requestedModule).first()
			self.dbClient.session.commit()
			self.logger.error('doSendModule: module: {module!r}', module=module)
			snapshot = module.snapshot

			## Use the snapshot UUID to confirm the client had knowledge enough
			## to request the data; simple but just another plug for security
			if snapshot != requestedSnapshot:
				self.logger.error('Client requested module {requestedModule!r} but the snapshot did not match; ignoring request.', requestedModule=requestedModule)
			else:
				## Construct the list of moduleFiles that need transfered
				moduleFiles = self.dbClient.session.query(platformSchema.ContentPackageFile).filter(platformSchema.ContentPackageFile.package == requestedModule).all()
				self.dbClient.session.commit()
				for moduleFile in moduleFiles:
					fileId = moduleFile.object_id
					## Some files are not used on clients, eg. jobs & endpoints
					path = moduleFile.path
					ignoreList = ['job', 'endpoint']
					if path.endswith(tuple(ignoreList)):
						continue
					self.moduleFilesToTransfer.append(fileId)
				self.logger.debug('doSendModule: finished compiling list of files: {fileList!r}', fileList=self.moduleFilesToTransfer)
				## Start the first file transfer
				self.sendFile(client, requestedModule, requestedSnapshot)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in doSendModule: {exception!r}', exception=exception)

		## end doSendModule
		return


	def getEndpointsFromKafka(self, kafkaConsumer, targetEndpoints, jobName, kafkaPollTimeout):
		"""Flush data from Kafka."""
		self.logger.info('Inside jobService.getEndpointsFromKafka')
		msgs = kafkaConsumer.consume(num_messages=1, timeout=kafkaPollTimeout)
		if msgs is None or len(msgs) <= 0:
			return True
		## Manual commit prevents message from being re-processed
		## more than once by either this consumer or another one.
		kafkaConsumer.commit()
		kafkaIsEmpty = True
		for message in msgs:
			if message is None:
				continue
			elif message.error():
				self.logger.debug('getEndpointsFromKafka: Kafka error on job {jobName!r}: {error!r}', jobName=jobName, error=message.error())
				continue
			else:
				kafkaIsEmpty = False
				thisMsg = json.loads(message.value().decode('utf-8'))
				self.logger.debug('Data received for processing: {thisMsg!r}', thisMsg=thisMsg)
				for endpoint in thisMsg['endpoints']:
					targetEndpoints.append(endpoint)

		## end getEndpointsFromKafka
		return kafkaIsEmpty


	def scrubKafkaEndpoints(self, jobName):
		"""Flush the queue and kafka."""
		returnMessage = None
		kafkaConsumer = None
		self.logger.debug('scrubKafkaEndpoints on {jobName!r}', jobName=jobName)
		try:
			kafkaConsumer = self.createKafkaConsumer(jobName)
			if kafkaConsumer is None:
				self.logger.error('scrubKafkaEndpoints not ran for {jobName!r}: unable to create kafkaConsumer!', jobName=jobName)
			else:
				targetEndpoints = []
				kafkaIsEmpty = False
				count = 0
				## Intentionally drain the kafka topic to avoid future duplicates
				while not kafkaIsEmpty and not self.canceledEvent.is_set() and not self.shutdownEvent.is_set():
					kafkaIsEmpty = self.getEndpointsFromKafka(kafkaConsumer, targetEndpoints, jobName, 0.05)
					thisSize = len(targetEndpoints)
					count += thisSize
					self.logger.debug('scrubKafkaEndpoints on {jobName!r}: kafka data size: {size!r}', jobName=jobName, size=thisSize)
					targetEndpoints.clear()
				self.logger.debug('scrubKafkaEndpoints on {jobName!r}: total scrubbed from kafka: {count!r}', jobName=jobName, count=count)
				self.logger.debug('scrubKafkaEndpoints on {jobName!r}: stopping kafkaConsumer', jobName=jobName)
			returnMessage = 'Exiting scrubKafkaEndpoints for job {}.'.format(jobName)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in scrubKafkaEndpoints: {exception!r}', exception=exception)

		## Close down and remove the consumer
		if kafkaConsumer is not None:
			try:
				self.logger.debug('scrubKafkaEndpoints on {jobName!r}: closing kafka consumer...', jobName=jobName)
				kafkaConsumer.close()
				self.logger.debug('scrubKafkaEndpoints on {jobName!r}: kafka consumer closed.', jobName=jobName)
			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception in scrubKafkaEndpoints: {exception!r}', exception=exception)

		## end scrubKafkaEndpoints
		return returnMessage


	def doJobComplete(self, jobName):
		try:
			## Tell the JobServiceClients to deactivate the job
			clientEndpoints = self.jobActiveClients.get(jobName, [])
			if len(clientEndpoints) > 0:
				for clientEndpoint in clientEndpoints:
					(endpointName, instanceNumber, client) = self.activeClients.get(clientEndpoint)
					client.constructAndSendData('removeJob', { 'jobName' : jobName })
			clientEndpoints = None
			self.jobActiveClients.pop(jobName, None)
			self.finalizeJobStats(jobName)
			self.jobStatistics.pop(jobName, None)
			## TODO: call aggregate functions to get statistics on the jobs:
			## shortest successful runtime, longest runtime, avg runtime,
			## standard deviations, and pass/fail counts

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in doJobComplete: {exception!r}', exception=exception)
