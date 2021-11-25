"""Thread management for sending data to ServiceNow.

Classes:
  WorkerThread : Wraps job invocation with a common framework

"""
import sys
import traceback
import time
import datetime
import importlib
from queue import Queue
from queue import Empty as Queue_Empty
from queue import Full as Queue_Full

## From openContentPlatform
from threadInstance import ThreadInstance
from snowRestAPI import SnowRestAPI


class WorkerThread(ThreadInstance):
	"""Wraps thread invocation with a common framework."""

	def __init__(self, runtime, scriptName, inputQueue, restEndpoint, userContext):
		"""Constructor for the WorkerThread.

		Arguments:
		  runtime (dict)     : object used for providing input into jobs and
		                       tracking job the life of its runtime
		  scriptName (str)   : worker script to multi-thread
		  inputQueue (Queue) : shard Queue for providing work to the threads

		"""
		self.runtime = runtime
		self.jobName = runtime.jobName
		self.packageName = runtime.packageName
		self.scriptName = scriptName
		self.inputQueue = inputQueue
		self.threadedFunction = self.jobWrapper

		(user, notthat, clientId, clientSecret) = userContext
		## Configure a connection to the remote endpoint
		self.webService = SnowRestAPI(runtime, restEndpoint, user, notthat, clientId, clientSecret)
		if not self.webService.connected:
			raise EnvironmentError('Unable to connect to ServiceNow instance: {}'.format(runtime.parameters.get('serviceNowRestEndpoint')))

		super().__init__(self.runtime.logger, self.jobName)


	def jobWrapper(self, *args, **kargs):
		try:
			## Dynamic import for job script
			packageModule = '{}.{}.{}'.format(self.packageName, 'script', self.scriptName)
			self.runtime.logger.report('Importing module: {packageModule!r}', packageModule=packageModule)
			startJobFunction = getattr(importlib.import_module(packageModule), 'startJob')

			## Loop for processing multiple input datasets inside this thread
			while (not self.completed and not self.canceled):
				try:
					## Allow timeout so we can continue checking self.canceled
					dataSet = self.inputQueue.get(True, .2)
					self.inputQueue.task_done()

					## Simple validation of data coming from queue
					hostname = dataSet.get('data', {}).get('hostname')
					if hostname is None:
						self.runtime.logger.error('Input data set is not valid for this job: {}'.format(dataSet))
						continue

					## Start job execution; expect updated runtime object
					self.runtime.logger.report('Processing hostname {hostname!r}', hostname=hostname)
					## Try/except prevents bad scripting from jumping out of the
					## standard flow here; expect the worst, hope for the best.
					startTime = datetime.datetime.now()
					try:
						startJobFunction(self.runtime, self.webService, dataSet)
					except:
						self.runtime.setError(__name__)

					## Job cleanup
					stopTime = datetime.datetime.now()
					totalTime = (stopTime - startTime).total_seconds()
					prettyStartTime = startTime.strftime('%Y-%m-%d %H:%M:%S.%f')
					prettyStopTime = stopTime.strftime('%Y-%m-%d %H:%M:%S.%f')
					self.runtime.logger.report('Finished dataSet {hostname!r}.  Start time: {prettyStartTime!r}.  Stop time: {prettyStopTime!r}.  Total runtime (seconds): {totalTime!r}', hostname=hostname, prettyStartTime=prettyStartTime, prettyStopTime=prettyStopTime, totalTime=totalTime)

				except Queue_Empty:
					time.sleep(.5)
					continue
				except:
					self.canceled = True
					self.exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					self.runtime.logger.error('Exception in {jobName!r} {threadName!r}: {exception!r}', jobName=self.jobName, threadName=self.threadName, exception=self.exception)

		except:
			self.exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.runtime.logger.error('Exception in {jobName!r} {threadName!r}: {exception!r}', jobName=self.jobName, threadName=self.threadName, exception=self.exception)

		## end jobWrapper
		return
