"""Shared code for clients that invoke remote jobs.

This provides common code used by contentGathering and universalJob services,
which invoke and manage remote jobs.

Classes:
  * :class:`.RemoteClientListener` : Twisted protocol to talk to remote services
  * :class:`.RemoteClientFactory` : Twisted factory class for this client

.. hidden::

  Author: Chris Satterthwaite (CS)
  Contributors: Madhusudan Sridharan (MS)
  Version info:
    1.0 : (CS) Created Dec, 2017
    1.1 : (CS) Improved capability for clients to reconnect when the server side
          is unavailable. Mar 25, 2019.

"""
import os, sys
import traceback
import re
import shutil
import json
import time
import datetime
import hashlib
from twisted.internet import task, threads
import twisted.logger
from contextlib import suppress
from queue import Queue
from queue import Empty as Queue_Empty
from queue import Full as Queue_Full

## Add openContentPlatform directories onto the sys path
thisPath = os.path.dirname(os.path.abspath(__file__))
basePath = os.path.abspath(os.path.join(thisPath, '..'))
if basePath not in sys.path:
	sys.path.append(basePath)
import env
env.addLibPath()
env.addLibThirdPartyPath()
env.addExternalPath()
env.addContentGatheringSharedScriptPath()

## From openContentPlatform
import utils
## Using an externally provided library defined in globalSettings and located
## in '<install_path>/external'.
externalProtocolHandler = utils.loadExternalLibrary('externalProtocolHandler')
import sharedClient
from remoteThread import RemoteThread


class RemoteClientListener(sharedClient.ServiceClientProtocol):
	"""Receives and sends data through protocol of choice"""

	def doPrepareJob(self, content):
		self.factory.doPrepareJob(content)

	def doJobEndpoints(self, content):
		self.factory.doJobEndpoints(content)

	def doRemoveJob(self, content):
		self.factory.logger.info('Received a doRemoveJob')
		self.factory.doRemoveJob(content)

	def doHealthRequest(self, content):
		""" """
		self.factory.logger.info('Responding to health request')
		self.constructAndSendData('healthResponse', self.factory.health)

	def doModuleSnapshots(self, content):
		self.factory.logger.info('Received a doModuleSnapshots')
		self.factory.doModuleSnapshots(content)

	def doModuleFile(self, content):
		self.factory.logger.info('Received a doModuleFile')
		self.factory.doModuleFile(content)

	def doModuleComplete(self, content):
		self.factory.logger.info('Received a doModuleComplete')
		self.factory.doModuleComplete(content)

	def requestAuthorization(self):
		"""Custom entry for content gathering client; redirects to checkModules."""
		self.factory.logger.debug('Requesting connection --> redirect to checkModules')
		content = {}
		content['endpointName'] = self.factory.endpointName
		content['endpointToken'] = self.factory.endpointToken
		self.constructAndSendData('checkModules', content)

	def requestAuthorization2(self):
		"""Once check modules is finished, this does the connection request."""
		self.factory.logger.debug('Requesting connection authorization')
		content = self.factory.platformDetails
		content['endpointName'] = self.factory.endpointName
		content['endpointToken'] = self.factory.endpointToken
		self.constructAndSendData('connectionRequest', content)

	def rawDataReceived(self, data):
		try:
			self.factory.logger.debug('rawDataReceived size {fileSize!r}', fileSize=len(data))
			self.factory.logger.debug('rawDataReceived data: {data!r}', data=str(data))
			fileName = self.factory.moduleFileContext['fileName']
			fileLength = self.factory.moduleFileContext['contentLength']
			streamSize = 0
			delimiterSize = len(self.delimiter)
			currentSize = len(self.factory.moduleFileContext['partialContent'])
			remainingSize = fileLength - currentSize
			transferComplete = False
			if currentSize <= 0:
				self.factory.moduleFileContext['md5Hash'] = hashlib.md5()
			self.factory.logger.debug('rawDataReceived: ... ... ...')

			## First check if we received the separator without data first, which
			## would mean we did not receive and contents for this file.
			if (data[:delimiterSize] == self.delimiter):
				if fileLength == 0:
					self.factory.logger.debug('rawDataReceived: File {fileName!r} was empty, but this was expected.', fileName=fileName)
				else:
					self.factory.logger.error('rawDataReceived: End of stream for file {fileName!r}. Expected transfer size of {fileLength!r} but only received {remainingSize!r}', fileName=fileName, fileLength=fileLength, remainingSize=remainingSize)
				streamSize = delimiterSize
				## Remove the delimiter
				data = data[delimiterSize:]
				transferComplete = True

			## Received a partial chunk of the file; retain in memory
			elif len(data) <= remainingSize:
				remainingSize = remainingSize - len(data)
				self.factory.logger.error('rawDataReceived: fileName part: {data!r}', data=data)
				self.factory.logger.debug('rawDataReceived: File {fileName!r} chunk received. Length of chunk: {dataSize!r}.  Remaining needed: {remainingSize!r}', fileName=fileName, dataSize=len(data), remainingSize=remainingSize)
				## Store the updated file hash and contents
				self.factory.moduleFileContext['md5Hash'].update(data)
				self.factory.moduleFileContext['partialContent'].extend(data)


			## Received the full file
			elif len(data) > remainingSize:
				filePart = data[:remainingSize]
				self.factory.logger.error('rawDataReceived: fileName last part: {filePart!r}', filePart=filePart)
				## Ensure the delimiter is at the end of the stream; if not, we have
				## received communication/noise during the file download!
				self.factory.logger.error('rawDataReceived: blah {blah!r}', blah=data[remainingSize:delimiterSize+remainingSize])
				if data[remainingSize:remainingSize+delimiterSize] != self.delimiter:
					self.factory.logger.error('rawDataReceived: Problem downloading file {fileName!r}; length of data was NOT followed by the expected delimiter.', fileName=fileName)
					## Reset the client (pause/re-initialize)
					self.cleanup()

				else:
					## Store the updated file hash and contents
					self.factory.moduleFileContext['md5Hash'].update(data[:remainingSize])
					self.factory.moduleFileContext['partialContent'].extend(data[:remainingSize])
					## Remove the file part and delimiter off data
					data = data[remainingSize + delimiterSize:]
					transferComplete = True

			## After receiving the full file transfer
			if transferComplete:
				self.factory.logger.debug('---> setting mode to Line Mode ')
				## Flip back to line mode, and send any remaining stream
				if len(data) > 0:
					self.setLineMode(data)
					self.factory.logger.debug('  ---> forward the remaining data for line mode processing: {data!r}', data=data)
				else:
					self.setLineMode()
					self.factory.logger.debug('  ---> no remaining data to forward back to line mode')
				## Write the file
				filePath = os.path.join(self.factory.moduleFileContext['filePath'], self.factory.moduleFileContext['fileName'])
				self.factory.logger.debug('rawDataReceived: creating file handle for {filePath!r}', filePath=filePath)
				with open(filePath, 'wb') as fh:
					fh.write(self.factory.moduleFileContext['partialContent'])
				self.factory.moduleFileContext['partialContent'] = bytearray()

				## Let the service know we received the file
				self.factory.logger.debug('Let the service know we received the file {fileName!r}', fileName=fileName)
				content = {}
				content['module'] = self.factory.moduleFileContext['module']
				content['snapshot'] = self.factory.moduleFileContext['snapshot']
				self.constructAndSendData('receivedFile', content)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.factory.logger.debug('Exception in rawDataReceived: {exception!r}', exception=exception)
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			self.factory.logToKafka(str(exceptionOnly))

		self.factory.logger.debug('rawDataReceived: leaving after processing {fileName!r}', fileName=fileName)
		## end rawDataReceived


class RemoteClientFactory(sharedClient.ServiceClientFactory):
	"""Contains custom tailored parts for this module."""
	continueTrying = True
	maxDelay = 300
	initialDelay = 1
	factor = 4

	def __init__(self, serviceName, globalSettings, canceledEvent, shutdownEvent, pkgPath, clientSettings, clientLogSetup):
		"""Constructor for the RemoteClientFactory.

		Arguments:
		  serviceName (str)     : class name of the client
		  globalSettings (dict) : global globalSettings

		Initialized variables:
		Keys for all of the following dictionaries, is the job name:
		  jobMetaData (dict)    : runtimes, parameters, etc
		  jobThreads (dict)     : list of active threads for this job
		  jobEndpoints (dict)   : Queue used to transfer endpoints to threads
		  jobStatistics (dict)  : Queue used to transfer finished statistics
		                          back from threads
		  jobStatus (dict)      : (startDate, startTime, jobsCompleted) marking
		                          when 'doPrepareJob' ran for this job

		"""
		try:
			## TODO : instrument these two events since this now is a process
			self.canceledEvent = canceledEvent
			self.shutdownEvent = shutdownEvent

			self.pkgPath = pkgPath
			if self.pkgPath not in sys.path:
				sys.path.append(self.pkgPath)
			self.logFiles = utils.setupLogFile(serviceName, env, globalSettings['fileContainingClientLogSettings'], directoryName='client')
			self.logObserver  = utils.setupObservers(self.logFiles, serviceName, env, globalSettings['fileContainingClientLogSettings'])
			self.logger = twisted.logger.Logger(observer=self.logObserver, namespace=serviceName)
			self.dStatuslogFiles = utils.setupLogFile('JobStatus', env, clientLogSetup, directoryName='client')
			self.dStatuslogObserver  = utils.setupObservers(self.dStatuslogFiles,'JobStatus', env, clientLogSetup)
			self.dStatusLogger = twisted.logger.Logger(observer=self.dStatuslogObserver, namespace='JobStatus')
			self.dDetaillogFiles = utils.setupLogFile('JobDetail', env, clientLogSetup, directoryName='client')
			self.dDetaillogObserver  = utils.setupObservers(self.dDetaillogFiles, 'JobDetail', env, clientLogSetup)
			self.dDetailLogger = twisted.logger.Logger(observer=self.dDetaillogObserver, namespace='JobDetail')

			self.validActions = ['connectionResponse', 'healthRequest', 'tokenExpired', 'unauthorized', 'prepareJob', 'jobEndpoints', 'removeJob', 'moduleSnapshots', 'moduleFile', 'moduleComplete']
			self.actionMethods = ['doConnectionResponse', 'doHealthRequest', 'doTokenExpired', 'doUnauthorized', 'doPrepareJob', 'doJobEndpoints', 'doRemoveJob', 'doModuleSnapshots', 'doModuleFile', 'doModuleComplete']
			self.localSettings = utils.loadSettings(os.path.join(env.configPath, clientSettings))
			self.clientSettings = utils.loadSettings(os.path.join(env.configPath, globalSettings['fileContainingRemoteClientConfig']))
			self.clientGroups = { 'clientGroups' : self.clientSettings.get('clientGroups', []) }
			self.kafkaTopic = globalSettings['kafkaTopic']
			self.kafkaConsumerErrorLimit = self.localSettings['kafkaConsumerErrorLimit']
			self.jobThreads = {}
			self.jobEndpoints = {}
			self.jobEndpointsCount = {}
			self.jobEndpointsLoaded = {}
			self.jobStatistics = {}
			self.jobStatus = {}
			self.jobKafkaConsumer = {}
			self.moduleContext = {}
			self.moduleFileContext = {}
			self.modulesToTransfer = {}
			super().__init__(serviceName, globalSettings)
			self.loopingJobCheck = task.LoopingCall(self.enterJobsCheck)
			self.loopingJobCheck.start(int(self.globalSettings['waitSecondsBetweenReturningJobStatistics']))
			self.initialize()
			self.protocolHandler = externalProtocolHandler.ProtocolHandler(None, globalSettings, env, self.logger)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			print('Exception in RemoteClientFactory constructor: {}'.format(str(exception)))
			with suppress(Exception):
				self.logger.error('Exception in RemoteClientFactory: {exception!r}', exception=exception)
			self.canceledEvent.set()
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			self.logToKafka(str(exceptionOnly))
			## Reset the client (pause/re-initialize)
			self.cleanup()

	def buildProtocol(self, addr):
		self.logger.debug('Connected.')
		## Resetting reconnection delay
		self.resetDelay()
		protocol = RemoteClientListener()
		protocol.factory = self
		return protocol

	def initialize(self):
		self.logger.debug('called initialize in remoteClient...')
		self.logger.debug('initializing : createKafkaProducer')
		self.createKafkaProducer()
		super().initialize()


	def cleanup(self):
		"""Reset the client (pause/re-initialize)."""
		print('Reset the client (pause/re-initialize)...')
		self.logToKafka('cleanup called in {} instance {}'.format(self.serviceName, self.clientName))
		## Stop the client to avoid accepting more work from the service
		print('  cleanup: activeClient: {}'.format(self.clientName))
		self.logger.warn('  cleanup: activeClient: {clientName!r}', clientName=self.clientName)
		self.clientName = 'Unknown'
		print('  cleanup: stop remoteClient threads')
		self.logger.warn('  cleanup: stop remoteClient threads')
		self.cleanupThreads()
		print('  cleanup: waiting for threads to finish')
		self.logger.warn('  cleanup: waiting for threads to finish')
		self.waitForThreadsToFinish()
		print('  cleanup: flush kafkaProducer')
		self.logger.warn('  cleanup: flush kafkaProducer')
		with suppress(Exception):
			if self.kafkaProducer is not None:
				## Close the producer
				print('  cleanup: closing kafkaProducer...')
				self.kafkaProducer.flush()
				self.kafkaProducer = None
				print('  cleanup: closed kafkaProducer')
				self.logger.warn('  cleanup: closed kafkaProducer')
		print('  cleanup: removing the protocolHandler')
		with suppress(Exception):
			del self.protocolHandler
		print(' Cleanup complete; client is paused.')
		self.logger.warn(' Cleanup complete; client is paused.')
		if self.connectedClient is not None:
			self.connectedClient.transport.loseConnection()
			self.disconnectedOnPurpose = True

		## end cleanup
		return


	def stopFactory(self):
		"""Manual destructor to cleanup when catching signals."""
		print(' stopFactory: cleaning up...')
		self.logToKafka('stopFactory called in {} instance {}'.format(self.serviceName, self.clientName))
		## Tell ReconnectingClientFactory not to reconnect on future disconnects
		print('  stopFactory: stop trying to reconnect on future disconnects')
		self.stopTrying()
		self.canceled = True
		## Stop the client to avoid accepting more work from the service
		print('  stopFactory: activeClient: {}'.format(self.clientName))
		self.clientName = 'Unknown'
		self.activeClient = None
		print('  stopFactory: stop remoteClient threads')
		self.cleanupThreads()
		print('  stopFactory: waiting for threads to finish')
		self.waitForThreadsToFinish()
		print('  stopFactory: stopping loopingJobCheck')
		with suppress(Exception):
			self.loopingJobCheck.stop()
		print('  stopFactory: flush kafkaProducer')
		with suppress(Exception):
			if self.kafkaProducer is not None:
				## Close the producer
				print('  stopFactory: closing kafkaProducer...')
				self.kafkaProducer.flush()
				self.kafkaProducer = None
				print('  stopFactory: closed kafkaProducer')
				self.logger.warn('  cleanup: closed kafkaProducer')
		## These are from the sharedClient
		print('  stopFactory: stopping loopingSystemHealth and loopingAuthenticateClient')
		with suppress(Exception):
			self.loopingSystemHealth.stop()
		with suppress(Exception):
			self.loopingAuthenticateClient.stop()
		print(' Cleanup complete; stopping client.')

		## end stopFactory
		return


	def cleanupThreads(self):
		## Wait for threads to finish before closing kafka. When running the
		## client on Windows, Python is no longer able to see error status with
		## pipe operations (STATUS_INVALID_HANDLE / ERROR_OPERATION_ABORTED).
		## Since I can't catch the signal and stop all running jobs, I need to
		## let them flush through before finishing. Otherwise jobs get stuck
		## in trying to send results back.
		for jobName,jobThreads in self.jobThreads.items():
			try:
				## Should we try to clean off the stats queue? This will likely
				## require more time to clean off and send to the server side
				## than we will have in the time before the process dies...
				self.logger.debug('  cleanupThreads: stopping threads for job {jobName!r}...', jobName=jobName)
				for jobThread in jobThreads:
					jobThread.canceled = True
			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.debug('Exception in cleanupThreads: {exception!r}', exception=exception)
				exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
				self.logToKafka(str(exceptionOnly))


	def waitForThreadsToFinish(self):
		waitSecondsOnJobCleanupLoop = self.localSettings.get('waitSecondsOnJobCleanupLoop', 10)
		print('  waiting for threads to finish')
		self.logger.info('    waiting for threads to finish...')
		## In case this was started in a terminal window, message to the console
		print('    waiting for threads to finish...')
		while len(self.jobThreads.keys()) > 0:
			for jobName in list(self.jobThreads.keys()):
				jobThreads = self.jobThreads[jobName]
				updatedJobThreads = []
				for jobThread in jobThreads:
					if jobThread.endpoint is not None:
						self.logger.info('      {jobThread!r}  with endpoint: {endpoint!r}', jobThread=jobThread, endpoint=jobThread.endpoint)
					if (jobThread is not None and
						jobThread.is_alive()):
						updatedJobThreads.append(jobThread)
				if len(updatedJobThreads) > 0:
					self.logger.info('     {jobName!r} has {numThreads} threads', jobName=jobName, numThreads=len(updatedJobThreads))
					self.jobThreads[jobName] = updatedJobThreads
				else:
					self.jobThreads.pop(jobName, None)

			## I don't want to join the threads but I may want something better
			## than a blocking sleep call, to wait before re-checking threads
			if len(self.jobThreads.keys()) > 0:
				self.logger.info('    waiting {waitSecondsOnJobCleanupLoop!r} seconds before checking again...', waitSecondsOnJobCleanupLoop=waitSecondsOnJobCleanupLoop)
				## In case this was started in a terminal, message to the console
				print('    waiting {} seconds before checking active threads again...'.format(waitSecondsOnJobCleanupLoop))
				time.sleep(int(waitSecondsOnJobCleanupLoop))

		self.logger.info('    All jobs have finished.')
		## In case this was started in a terminal window, message to the console
		print('    All jobs have finished.')

		## end waitForThreadsToFinish
		return


	def doPrepareJob(self, content):
		"""Prepare a new job for execution.

		Parse meta-data on job, setup shared queues, spin up worker threads.
		"""
		jobName = content['jobName']
		jobShortName = content['jobShortName']
		packageName = content['packageName']
		scriptName = content['jobScript']
		jobMetaDataContent = content['jobMetaData']
		self.logger.debug('====> jobMetaData: {jobMetaDataContent!r}', jobMetaDataContent=jobMetaDataContent)

		## Resolve protocol entries before starting threads
		self.protocolHandler.open(jobMetaDataContent)

		## Pull data into variables, before calling RemoteThread
		jobMetaData = {}
		keysToMove = ['protocolType', 'inputParameters', 'protocols', 'shellConfig']
		for key,value in jobMetaDataContent.items():
			if key in keysToMove:
				continue
			jobMetaData[key] = value
		protocolType = jobMetaDataContent.get('protocolType')
		inputParameters = jobMetaDataContent.get('inputParameters', {})
		protocols = jobMetaDataContent.get('protocols', {})
		shellConfig = jobMetaDataContent.get('shellConfig', {})

		if jobName in self.jobThreads.keys():
			## It means it was active already; if we run again, we may be
			## clobbering results or causing a spiral performance problem
			self.logger.error('Job {jobName!r} still has active threads from last execution.', jobName=jobName)
			self.logger.debug('Manual cleanup of Job {jobName!r} before restart...', jobName=jobName)
			## Cleanup previously allocated resources and start fresh
			self.doRemoveJob({ 'jobName' : jobName })

		## Add the package script dir onto path to enable loading dependent libs
		pythonPackage = os.path.join(self.pkgPath, packageName, 'script')
		if pythonPackage not in sys.path:
			sys.path.append(pythonPackage)

		## Get kafka configurations:
		kafkaPollTimeout = self.localSettings['kafkaPollTimeOut']
		## Allow job to override max worker pool size (how much to queue up)
		numberOfJobThreads = jobMetaData.get('numberOfJobThreads', 1)
		kafkaPerPollJobEndpointsSize = jobMetaData.get('kafkaPerPollJobEndpointsSize', numberOfJobThreads)
		## Get queue configurations:
		queuePutTimeoutInSeconds = self.localSettings.get('queuePutTimeoutInSeconds', .1)
		## Allow job to override queue size (based on speed of job)
		endpointQueueSize = jobMetaData.get('endpointQueueSize', numberOfJobThreads)

		## Create the job memory structures
		startDate = datetime.datetime.now()
		startTime = time.time()
		self.jobStatus[jobName] = (startDate, startTime, 0, False)
		self.jobThreads[jobName] = []
		## Queue used to transfer finished statistics back to this client
		self.jobStatistics[jobName] = Queue()
		endpointPipeline = jobMetaData.get('endpointPipeline', 'service').lower()
		## Queue used to transfer endpoints to worker threads; notice we set a
		## max size, according to the defaults and overriden by the job. This
		## controls how much is pulled from kafka at once, so that the number of
		## remote clients and threads per client, can all be set independently.
		## And this enables a native load-balancing between the clients, so that
		## they only pull down evenly sized chunks at a time, and need to finish
		## those work items before pulling more.
		self.jobEndpoints[jobName] = None
		if endpointPipeline == 'kafka':
			self.jobEndpoints[jobName] = Queue(maxsize=endpointQueueSize)
		elif endpointPipeline == 'service':
			self.jobEndpoints[jobName] = Queue()
		self.jobEndpointsLoaded[jobName] = False
		self.jobEndpointsCount[jobName] = 0

		## Spin up the worker threads
		numberOfJobThreads = int(jobMetaData['numberOfJobThreads'])
		self.logger.info('Spinning up {numberOfJobThreads!r} threads for job {jobName!r}', numberOfJobThreads=numberOfJobThreads, jobName=jobName)
		for i in range(int(numberOfJobThreads)):
			activeThread = RemoteThread(self.dStatusLogger, self.dDetailLogger, env, jobShortName, packageName, scriptName, jobMetaData, protocolType, inputParameters, protocols, shellConfig, self.jobEndpoints[jobName], self.jobStatistics[jobName], self.kafkaProducer, self.kafkaTopic)
			activeThread.start()
			self.jobThreads[jobName].append(activeThread)

		## Get the endpoints for the threads to work on
		if endpointPipeline == 'kafka':
			## Call doJobEndpointsKafka in a separate non-blocking thread
			self.logger.info('Job {jobName!r} uses kafka endpoint pipeline. Calling doJobEndpointsKafka in separate thread, to pull endpoints.', jobName=jobName)
			args = (jobName, queuePutTimeoutInSeconds, kafkaPollTimeout)
			threadHandle = threads.deferToThread(self.doJobEndpointsKafka, *args)
			threadHandle.addErrback(self.logger.error)
			threadHandle.addCallback(self.logger.info)
		elif endpointPipeline == 'service':
			self.logger.info('Job {jobName!r} uses service endpoint pipeline... waiting for endpoints.', jobName=jobName)
		else:
			self.logger.error('Job {jobName!r} has unrecognized endpointPipeline setting: {endpointPipeline!r}.  Expected value to be \'service\' or \'kafka\'.', jobName=jobName, endpointPipeline=endpointPipeline)

		## end doPrepareJob
		return


	def scrubEndpoints(self, jobName):
		"""Flush the queue and kafka."""
		returnMessage = None
		self.logger.debug('scrubEndpoints on {jobName!r}', jobName=jobName)
		kafkaConsumer = self.jobKafkaConsumer.get(jobName)
		if kafkaConsumer is not None:
			self.logger.debug('scrubEndpoints on {jobName!r}: kafkaConsumer still exists', jobName=jobName)
			self.jobEndpointsLoaded[jobName] = True
			targetEndpoints = []
			kafkaIsEmpty = False
			count = 0
			## Intentionally drain the kafka topic to avoid future duplicates
			while not kafkaIsEmpty and not self.canceledEvent.is_set() and not self.shutdownEvent.is_set():
				kafkaIsEmpty = self.getEndpointsFromKafka(kafkaConsumer, targetEndpoints, jobName, 0.05)
				thisSize = len(targetEndpoints)
				count += thisSize
				self.logger.debug('scrubEndpoints on {jobName!r}: kafka data size: {size!r}', jobName=jobName, size=thisSize)
				targetEndpoints.clear()
			self.logger.debug('scrubEndpoints on {jobName!r}: total scrubbed from kafka: {count!r}', jobName=jobName, count=count)
			self.logger.debug('scrubEndpoints on {jobName!r}: stopping kafkaConsumer', jobName=jobName)
			kafkaConsumer.close()
			self.jobKafkaConsumer[jobName] = None
		returnMessage = 'Exiting scrubEndpoints for job {}.'.format(jobName)

		## end scrubEndpoints
		return returnMessage


	def doJobEndpointsKafka(self, jobName, queuePutTimeoutInSeconds, kafkaPollTimeout):
		"""Feed and monitor active job via non-blocking thread.

		Note, it would be easier to do this from the worker threads themselves,
		but that won't work with how kafka uses partitions. If kafka had 10
		partitions setup, and we spin up 11 (or 100) worker threads on a client,
		only the first 10 would connect and get work. And the problem gets worse
		since our clients can scale horizontally (10 clients with 100 threads,
		would mean 990 threads doing nothing in the same scenario with 10 total
		kafka partitions). So this allows us to work in a multi-threaded manner,
		sharing load off a Kafka Consumer that is not thread safe.

		The remote client pulls a message from kafka, containing a chunk of
		endpoints. It then feeds that chunk into the internal shared Queue used
		by the worker threads.
		"""
		returnMessage = None
		## Create a KafkaConsumer to populate the jobEndpoints[jobName] queue;
		## Not saving in a class variable since this function should run the
		## entire time we're using it... so just keep it local.
		try:
			self.logger.debug('doJobEndpointsKafka: initializing createKafkaConsumer')
			kafkaConsumer = self.createKafkaConsumer(jobName)
			self.jobKafkaConsumer[jobName] = kafkaConsumer

			targetEndpoints = []
			#while not self.canceled:
			while not self.canceledEvent.is_set() and not self.shutdownEvent.is_set():
				## Continue filling queue to its max (freed up again by workers
				## pulling endpoints off), until kafka says it has nothing more.
				kafkaIsEmpty = self.getEndpointsFromKafka(kafkaConsumer, targetEndpoints, jobName, kafkaPollTimeout)
				if kafkaIsEmpty:
					self.jobEndpointsLoaded[jobName] = True
					self.logger.debug('doJobEndpointsKafka : kafka endpoints depleted for this job; stopping kafkaConsumer')
					kafkaConsumer.close()
					self.jobKafkaConsumer[jobName] = None
					## Tell threads that everything has been loaded into their queue
					self.logger.debug('doJobEndpointsKafka : {jobName!r} telling threads that endpoints have been loaded.', jobName=jobName)
					for jobThread in self.jobThreads[jobName]:
						jobThread.endpointsLoaded = True
					break
				## Kafka query may be pulling more than one endpoint, and so we
				## may need to wait a few times to add the full set to the queue.
				for endpoint in targetEndpoints:
					self.logger.debug('doJobEndpointsKafka : {jobName!r} adding endpoint {endpoint!r} to queue', jobName=jobName, endpoint=endpoint)
					while not self.jobEndpointsLoaded[jobName] and not self.canceledEvent.is_set() and not self.shutdownEvent.is_set():
						try:
							## Put this endpoint onto the shared worker Queue
							self.jobEndpoints[jobName].put(endpoint, True, queuePutTimeoutInSeconds)
							self.jobEndpointsCount[jobName] += 1
							break
						except Queue_Full:
							## If the queue is full, wait for the workers to pull
							## data off and free up room; no need to break here.
							pass
						except:
							exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
							self.logger.error('Exception in doJobEndpointsKafka: {exception!r}', exception=exception)
							exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
							self.logToKafka(str(exceptionOnly))
							self.canceled = True
							returnMessage = 'Exited doJobEndpointsKafka for job {} with an error.'.format(jobName)
							self.logger.debug('doJobEndpointsKafka: Manual cleanup of Job {jobName!r}...', jobName=jobName)
							## Cleanup previously allocated resources
							self.doRemoveJob({ 'jobName' : jobName })
							break
				targetEndpoints.clear()
			## After kafka is drained, we wait until the worker threads have pulled
			## and processed everything from the queue, and then exit gracefully.
			returnMessage = 'Exiting doJobEndpointsKafka for job {}. Kafka has no more endpoints to add, now just waiting on current work queue to flush.'.format(jobName)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in doJobEndpointsKafka: {exception!r}', exception=exception)
			returnMessage = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])

		## end doJobEndpointsKafka
		return returnMessage


	def getEndpointsFromKafka(self, kafkaConsumer, targetEndpoints, jobName, kafkaPollTimeout):
		"""Pull data from Kafka to feed the shared queue for worker threads."""
		try:
			## Initially the service sent chunks of endpoints per kafka msg
			## (mirroring the endpointPipeline as 'service' flow), but that
			## worked against the idea of load balancing off kafka partition
			## allocation to group members. So now it's just one at a time.

			## Also, since it normally takes a few seconds for partitions to
			## be rebalanced - the kafkaPollTimeout needs to be high enough
			## so that the clients don't spin down before being added into
			## the corresponding topic. Probably want 15-30 seconds as the
			## default, but don't go over 30 unless the core kafka settings
			## are also increased.

			message = kafkaConsumer.poll(kafkaPollTimeout)
			if message is None:
				return True
			if message.error():
				self.logger.debug('getEndpointsFromKafka: Kafka error on job {jobName!r}: {error!r}', jobName=jobName, error=message.error())
				## This might be a false positive if kafka goes down
				return True
			else:
				## Manual commit prevents message from being re-processed
				## more than once by either this consumer or another one.
				kafkaConsumer.commit(message)
				thisMsg = json.loads(message.value().decode('utf-8'))
				targetEndpoints.append(thisMsg['endpoint'])
				return False

		except (KeyboardInterrupt, SystemExit):
			print('getEndpointsFromKafka: Interrrupt received...')
			self.logger.debug('getEndpointsFromKafka: Interrrupt received...')
			self.canceled = True
			return True
		except:
			print('Exception in getEndpointsFromKafka...')
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('getEndpointsFromKafka: exception in kafka wait loop: {exception}', exception=exception)
			self.logToKafka('getEndpointsFromKafka: aborted kafka wait loop for job {}'.format(jobName))
			## The timeout set in our kafkaConsumer.poll call above, will
			## never be large enough since we can't control the size of data
			## sent here. We default the timeout to half a second or 2 secs,
			## and just wait until we hit a 'kafka.errors.CommitFailedError'
			## with the message talking about the time between subsequent
			## calls was longer than the configured session.timeout.ms.
			## Allow a bit of resilience via retry logic.
			self.kafkaErrorCount += 1
			try:
				if self.kafkaErrorCount < self.kafkaConsumerErrorLimit:
					print('getEndpointsFromKafka: kafkaErrorCount {}'.format(self.kafkaErrorCount))
					self.logger.error('getEndpointsFromKafka: kafkaErrorCount {kafkaErrorCount}', kafkaErrorCount=self.kafkaErrorCount)
					time.sleep(2)
				else:
					self.canceled = True
					print('getEndpointsFromKafka: kafkaErrorCount {}... exiting.'.format(self.kafkaErrorCount))
					return True
			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Kafka error: {exception}',exception=exception)
				print('Exception in getEndpointsFromKafka: second catch: {}'.format(exception))
				return True

		## end getEndpointsFromKafka
		return True


	def doJobEndpoints(self, content):
		"""Process endpoints provided by service, and add into the shared queue.

		Arguments:
		  content : Dictionary containing the Job detail information.

		"""
		queuePutTimeoutInSeconds = self.localSettings.get('queuePutTimeoutInSeconds', .1)
		jobName = content['jobName']
		targetEndpoints = content['endpoints']
		if jobName not in self.jobEndpoints.keys():
			## This means the client received a message with an invokeJob
			## action before it received the corresponding prepareJob
			self.logger.error('Job {jobName!r} was not yet prepared.', jobName=jobName)
			return

		for endpoint in targetEndpoints:
			## Put this endpoint onto the shared worker Queue
			try:
				while not self.canceledEvent.is_set() and not self.shutdownEvent.is_set():
					try:
						self.jobEndpoints[jobName].put(endpoint, True, queuePutTimeoutInSeconds)
						self.jobEndpointsCount[jobName] += 1
						break
					except Queue_Full:
						## If the queue is full, wait for the workers to pull
						## data off and free up room; no need to break here.
						## TODO: This is blocking; we should convert this into
						## a defered to avoid interrupting other processing.
						continue
					except:
						exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
						self.logger.error('Exception in doJobEndpoints: {exception!r}', exception=exception)
						break
			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception in doJobEndpoints: {exception!r}', exception=exception)
				exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
				self.logToKafka(str(exceptionOnly))

		## Service notice that this was the last bulk
		if content.get('complete', False):
			self.jobEndpointsLoaded[jobName] = True
			## Tell threads that everything has been loaded into their queue
			self.logger.debug('doJobEndpoints : {jobName!r} telling threads that endpoints have been loaded.', jobName=jobName)
			for jobThread in self.jobThreads[jobName]:
				jobThread.endpointsLoaded = True

		## end doJobEndpoints
		return


	def enterJobsCheck(self):
		"""Looping method for checking job stats; done via non-blocking thread."""
		threadHandle = None
		try:
			threadHandle = threads.deferToThread(self.checkJobsForStats)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in enterJobsCheck: {exception!r}', exception=exception)
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			self.logToKafka(str(exceptionOnly))

		## end enterJobsCheck
		return threadHandle


	def checkJobsForStats(self):
		"""Check all active jobs to see if there are statistics to process."""
		for jobName in self.jobStatistics.copy():
			try:
				self.logger.debug('inside checkJobsForStats, looking at Job {jobName!r}.', jobName=jobName)
				self.processStatsOnJob(jobName)
			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception in checkJobsForStats: {exception!r}', exception=exception)
				exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
				self.logToKafka(str(exceptionOnly))
				return 'Exiting {}'.format(str(exceptionOnly))

		## end checkJobsForStats
		return 'Exiting checkJobsForStats'


	def checkJobThreads(self, jobName, startDate, completedCount, sentNotification):
		"""Check on the job worker threads.

		Since we switched from the server controlling the endpoint flow, to the
		clients doing this individually - we regularly check active threads.
		"""
		try:
			self.logger.debug('inside checkJobThreads...')
			if jobName in self.jobThreads:
				self.logger.debug('checkJobThreads: job {jobName!r} still has active threads.', jobName=jobName)
				numActiveThreads = 0
				for jobThread in self.jobThreads.get(jobName, []):
					if (jobThread is not None and jobThread.is_alive()):
						## Report on threads & provide visibility to the current
						## endpoints; could be problems with specific endpoints.
						threadReport = str(jobThread)
						self.logger.debug('   checkJobThreads: {jobName!r} thread info: {data!r}', jobName=jobName, data=threadReport)
						numActiveThreads += 1
						## Send any/all jobs running longer than expected, back
						## through the log service. Don't overwrite the stats
						## since the job may still complete successfully, but do
						## this to ensure some tracking on the incident.
						m = re.search('^Error: (.*)', threadReport, re.I)
						if m:
							self.logToKafka(m.group(1))

				## If no active threads remain, cleanup
				if numActiveThreads <= 0:
					content = {}
					content['jobName'] = jobName
					self.logger.debug('  checkJobThreads: removing {jobName!r}', jobName=jobName)
					## Send the remaining queued statistics back, and set the
					## checkIdle flag to false to avoid recursive calls here
					self.processStatsOnJob(jobName, checkIdle=False)
					## Remove local data on this job
					self.doRemoveJob(content)
					self.logger.debug('  checkJobThreads: notifying server that job {jobName!r} finished', jobName=jobName)

					## Tell the server side service it's finished
					if self.activeClient is not None:
						self.activeClient.constructAndSendData('jobFinishedOnClient', content)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in checkJobThreads: {exception!r}', exception=exception)
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			self.logToKafka(str(exceptionOnly))

		## end checkJobThreads
		return


	def processStatsOnJob(self, jobName, checkIdle=True):
		"""Process job statistics into chunks to send."""
		try:
			self.logger.debug('inside processStatsOnJob, looking at Job {jobName!r}.', jobName=jobName)
			## Get jobStatus information for use below
			(startDate, startTime, completedCount, sentNotification) = self.jobStatus[jobName]
			## Send any remaining statistics back to the contentGatheringService
			if jobName in self.jobStatistics and not self.jobStatistics[jobName].empty():
				self.logger.debug('inside processStatsOnJob, sending stats on Job {jobName!r}.', jobName=jobName)
				## Initially choosing an arbitrary number (10) for the throttle.
				## 31 was too many with a short error message when using the
				## default line receiver buffer size; total chars in the json
				## message was 4384 before it cut off. This makes more sense if
				## set to something like 100, but for now I'm leaving it low.
				maxResultCount = 10
				resultLines = []
				while not self.canceledEvent.is_set() and not self.shutdownEvent.is_set():
					try:
						## Pull statistics result off jobStatistics queue
						resultLine = self.jobStatistics[jobName].get(True, .2)
						self.jobStatistics[jobName].task_done()
						## Add to chunk to send back to contentGatheringService
						## to optimize result processing and avoid overwhelming
						## the server side when we have many connected clients.
						self.logger.debug('   processStatsOnJob: got line: {resultLine!r}', resultLine=resultLine)
						resultLines.append(resultLine)
						## When we hit the desired chunk size; send it back
						if len(resultLines) >= maxResultCount:
							self.sendStatsOnJob(jobName, resultLines)
							completedCount += len(resultLines)
							self.logger.debug('   processStatsOnJob: completedCount for job {jobName!r}: {completedCount!r}', jobName=jobName, completedCount=completedCount)
							resultLines = []
					except Queue_Empty:
						self.logger.debug('   processStatsOnJob: QUEUE EMPTY on job {jobName!r}', jobName=jobName)
						break
					except:
						self.exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
						print('Exception in {}: {}'.format(self.jobName, self.exception))
						self.logger.error('Exception in {jobName!r}: {exception!r}', jobName=self.jobName, exception=self.exception)
						exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
						self.logToKafka(str(exceptionOnly))
						break
				## Send remaining partial chunk
				if len(resultLines) > 0:
					self.sendStatsOnJob(jobName, resultLines)
					completedCount += len(resultLines)
					self.logger.debug('   processStatsOnJob: completedCount for job {jobName!r}: {completedCount!r}', jobName=jobName, completedCount=completedCount)
				## Update completedCount in jobStatus
				self.jobStatus[jobName] = (startDate, startTime, completedCount, sentNotification)

			if checkIdle == True:
				self.logger.debug('   processStatsOnJob: going to checkJobThreads')
				self.checkJobThreads(jobName, startDate, completedCount, sentNotification)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in processStatsOnJob: {exception!r}', exception=exception)
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			self.logToKafka(str(exceptionOnly))

		## end processStatsOnJob
		return


	def sendStatsOnJob(self, jobName, resultLines):
		"""Send chunk of statistics to the ContentGatheringService."""
		try:
			## This can happen if the client is offline/being reconnected, and
			## the looping call for stats is run during that period
			if self.activeClient is None:
				return
			self.logger.debug('inside sendStatsOnJob...')
			content = {}
			content['jobName'] = jobName
			content['statistics'] = resultLines
			self.logger.debug('sendStatsOnJob: client name: {clientName!r}', clientName=self.clientName)
			self.activeClient.constructAndSendData('jobStatistics', content)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in sendStatsOnJob: {exception!r}', exception=exception)
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			self.logToKafka(str(exceptionOnly))

		self.logger.debug('leaving sendStatsOnJob...')
		## end sendStatsOnJob
		return


	def doRemoveJob(self, content):
		"""Deactivate a job and scrub residual memory and threads."""
		jobName = content['jobName']
		self.logger.debug('doRemoveJob for job {jobName!r}', jobName=jobName)
		## For debugging purposes:
		self.logger.debug('  self.jobEndpoints.keys: {data!r}', data=self.jobEndpoints.keys())
		if jobName in self.jobEndpoints.keys():
			self.logger.debug('    self.jobEndpoints[jobName]: {data!r}', data=self.jobEndpoints[jobName])
		self.logger.debug('  self.jobStatistics.keys: {data!r}', data=self.jobStatistics.keys())
		if jobName in self.jobStatistics.keys():
			self.logger.debug('    self.jobStatistics[jobName]: {data!r}', data=self.jobStatistics[jobName])
		self.logger.debug('  self.jobThreads.keys: {data!r}', data=self.jobThreads.keys())
		if jobName in self.jobThreads.keys():
			self.logger.debug('    self.jobThreads[jobName]: {data!r}', data=self.jobThreads[jobName])
		self.logger.debug('  self.jobEndpointsLoaded.keys: {data!r}', data=self.jobEndpointsLoaded.keys())
		if jobName in self.jobEndpointsLoaded.keys():
			self.logger.debug('    self.jobEndpointsLoaded[jobName]: {data!r}', data=self.jobEndpointsLoaded[jobName])
		self.logger.debug('  self.jobEndpointsCount.keys: {data!r}', data=self.jobEndpointsCount.keys())
		if jobName in self.jobEndpointsCount.keys():
			self.logger.debug('    self.jobEndpointsCount[jobName]: {data!r}', data=self.jobEndpointsCount[jobName])

		## Gracefully close all threads via notification
		if jobName not in self.jobThreads:
			## Another event told this job to cleanup already
			self.logger.info('Job {jobName!r} has finished; duplicate cleanup request.', jobName=jobName)
			return
		self.logger.info('Job {jobName!r} has finished; cleanup...', jobName=jobName)
		try:
			self.scrubEndpoints(jobName)
			## Send the last of the queued statistics back to the service, and
			## set the checkIdle flag to false to avoid recursive calls here.
			## This is already called in normal job spin down, but for errors
			## hit in other places, we explicitely call it here
			self.processStatsOnJob(jobName, checkIdle=False)
			## Tell all idle threads (threads not currently running a job on
			## an endpoint) to gracefully shut down
			for jobThread in self.jobThreads[jobName]:
				jobThread.completed = True
			## Ensure job threads finish properly, before removing references
			#while not self.canceled:
			while not self.canceledEvent.is_set() and not self.shutdownEvent.is_set():
				updatedJobThreads = []
				for jobThread in self.jobThreads[jobName]:
					if (jobThread is not None and
						jobThread.is_alive()):
						updatedJobThreads.append(jobThread)
				self.jobThreads[jobName] = updatedJobThreads
				if len(self.jobThreads[jobName]) > 0:
					## I don't want to 'join' the threads, but should replace
					## the blocking sleep with something that can be interrupted
					time.sleep(.1)
				else:
					break
			## Report on the overall performance of job
			(startDate, startTime, completedCount, sentNotification) = self.jobStatus[jobName]
			endDate = datetime.datetime.now()
			## Math expressions on datetime values yield a timedelta type; to
			## get seconds just apply the total_seconds method:
			totalSeconds = int((endDate - startDate).total_seconds())
			prettyRunTime = utils.prettyRunTimeBySeconds(totalSeconds)
			## Remove job memory management
			self.jobStatistics.pop(jobName, None)
			self.jobEndpoints.pop(jobName, None)
			self.jobThreads.pop(jobName, None)
			self.jobEndpointsLoaded[jobName] = False
			jobCount = self.jobEndpointsCount.pop(jobName, 0)
			## TODO: client should be accumulating this information as well:
			##   Number of endpoints [{}].  Average job runtime [{}].
			##   Shortest runtime [{}].  Longest runtime [{}].
			self.logger.info('Job {jobName!r} completed {jobCount!r} executions.  Started at {startDate!r}.  Runtime: {prettyRunTime!r}', jobName=jobName, jobCount=int(jobCount), startDate=startDate.strftime('%Y-%m-%d %H:%M:%S.%f'), prettyRunTime=prettyRunTime)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in doRemoveJob: {exception!r}', exception=exception)
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			self.logToKafka(str(exceptionOnly))

		## end doRemoveJob
		return


	def removeOldModulePath(self, moduleName):
		## Remove contents within the client module directory
		modulePath = os.path.join(self.pkgPath, moduleName)
		try:
			self.logger.debug('Removing old module dir from client: {modulePath!r}', modulePath=modulePath)
			## Remove the directory itself
			utils.cleanDirectory(self.logger, modulePath)
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Cannot remove old module dir from client ({modulePath!r}): {stacktrace!r}', modulePath=modulePath, stacktrace=stacktrace)
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			self.logToKafka(str(exceptionOnly))
		with suppress(Exception):
			os.mkdir(modulePath)

		## end removeOldModulePath
		return


	def doModuleFile(self, content):
		self.moduleFileContext['module'] = content.get('module')
		self.moduleFileContext['snapshot'] = content.get('snapshot')
		self.moduleFileContext['fileName'] = content.get('fileName')
		self.moduleFileContext['fileHash'] = content.get('fileHash')
		self.moduleFileContext['fileSize'] = content.get('size')
		self.moduleFileContext['contentLength'] = content.get('contentLength')
		directory = env.basePath
		for subPath in content['pathString'].split(','):
			directory = os.path.join(directory, subPath)
			if not os.path.exists(directory):
				os.mkdir(directory)
		filePath = directory
		self.moduleFileContext['filePath'] = directory
		self.moduleFileContext['fileHandle'] = None
		self.moduleFileContext['partialContent'] = bytearray()
		self.logger.debug('---> setting mode to Raw Mode')
		self.connectedClient.setRawMode()


	def requestModuleContents(self, moduleName, moduleSnapshot):
		try:
			self.logger.debug('Requesting module: {moduleName!r}', moduleName=moduleName)
			self.moduleContext['module'] = moduleName
			self.moduleContext['snapshot'] = moduleSnapshot
			content = {}
			content['module'] = moduleName
			content['snapshot'] = moduleSnapshot
			self.logger.debug('requestModuleContents for module: {moduleName!r}', moduleName=moduleName)
			self.connectedClient.constructAndSendData('sendModule', content)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Failed creating module {moduleName!r}: {stacktrace!r}', moduleName=moduleName, stacktrace=stacktrace)
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			self.logToKafka(str(exceptionOnly))

		## end requestModuleContents
		return


	def doModuleComplete(self, content):
		try:
			moduleName = content.get('module')
			moduleSnapshot = content.get('snapshot')
			if moduleName is None:
				self.logger.debug('doModuleComplete: starting to process modules...')
			else:
				self.logger.debug('doModuleComplete: finished module {moduleName!r}.', moduleName=moduleName)
			## See if we finished all module updates
			if len(self.modulesToTransfer) <= 0:
				self.logger.debug('doModuleComplete: finished all modules; proceeding to register...')
				self.connectedClient.requestAuthorization2()
			else:
				self.logger.debug('doModuleComplete: modules remaining: {modulesToTransfer!r}', modulesToTransfer=self.modulesToTransfer)
				## Remove the next module from those tracked for needing updates
				moduleName, moduleSnapshot = self.modulesToTransfer.popitem()
				self.logger.debug('doModuleComplete: requesting next module {moduleName!r}.', moduleName=moduleName)
				self.requestModuleContents(moduleName, moduleSnapshot)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.debug('Exception in doModuleComplete: {exception!r}', exception=exception)
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			self.logToKafka(str(exceptionOnly))


	def doModuleSnapshots(self, content):
		self.logger.info(' doModuleSnapshots: {modulesToTransfer!r}', modulesToTransfer=self.modulesToTransfer)
		try:
			serverSnapshots = content['content']
			clientSnapshots = {}
			updateSnapshotsFile = False
			## Don't pursue granular file checks; trust the high-level snapshot
			snapshotFile = os.path.join(self.pkgPath, 'moduleSnapshots.json')
			if (os.path.exists(snapshotFile) and os.path.isfile(snapshotFile)):
				clientSnapshots = utils.loadSettings(snapshotFile)
			else:
				if (not os.path.exists(self.pkgPath)):
					## On startup, the content directory will not exist
					os.makedirs(self.pkgPath)

			for moduleName,serverSnapshot in serverSnapshots.items():
				if moduleName in clientSnapshots:
					## Module already present on client; check snapshot value
					clientSnapshot = clientSnapshots[moduleName]
					if clientSnapshot == serverSnapshot:
						self.logger.info(' module data is current: {moduleName!r}', moduleName=moduleName)
					else:
						self.logger.info(' module requires update: {moduleName!r}', moduleName=moduleName)
						updateSnapshotsFile = True
						self.modulesToTransfer[moduleName] = serverSnapshot
						## Remove client module directory and recreate
						self.removeOldModulePath(moduleName)
					## Remove the processed module from the remaining snapshots
					clientSnapshots.pop(moduleName)
				else:
					self.logger.info(' module requires update: {moduleName!r}', moduleName=moduleName)
					updateSnapshotsFile = True
					self.modulesToTransfer[moduleName] = serverSnapshot

			## Start the first module transfer
			self.doModuleComplete({})

			## Now go through any remaining modules on the client that were
			## not in the server listing, and remove the old/unknown content.
			## No need to track this with self.modulesToTransfer since jobs
			## can run while old modules are being removed.
			for moduleName in clientSnapshots:
				updateSnapshotsFile = True
				## Remove the client module directory
				self.removeOldModulePath(moduleName)

			## If something changed, overwrite the client-side moduleSnapshots
			if updateSnapshotsFile:
				self.logger.debug('Writing a new moduleSnapshots.json file')
				with open(snapshotFile, 'w') as fh:
					json.dump(serverSnapshots, fh, indent=4)

			## Wait on these updates to finish before activating the client; this
			## occurs after doModuleComplete() has been called enough times by the
			## service, indicating all self.modulesToTransfer are completed.
			self.logger.debug('Finished doModuleSnapshots')
			self.logger.debug('Need to wait for doModuleComplete to run through all modulesToTransfer...')

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in doModuleSnapshots: {stacktrace!r}', stacktrace=stacktrace)
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			self.logToKafka(str(exceptionOnly))
			self.cleanup()

		## end doModuleSnapshots
		return
