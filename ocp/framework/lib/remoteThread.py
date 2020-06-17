"""Thread management for content gathering.

Classes:
  :class:`remoteThread.RemoteThread` : Wraps job invocation with a common
    framework

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Oct, 2017

"""
import sys
import traceback
import time
import json
import datetime
import importlib
from queue import Queue
from queue import Empty as Queue_Empty
from queue import Full as Queue_Full

## From openContentPlatform
from threadInstance import ThreadInstance
from remoteRuntime import Runtime


class RemoteThread(ThreadInstance):
	"""Wraps job invocation with a common framework."""

	def __init__(self, dStatusLogger, dDetailLogger, env, jobName, packageName, scriptName, jobMetaData, protocolType, inputParameters, protocols, shellConfig, jobEndpoints, jobStatistics, kafkaProducer, kafkaTopic):
		"""Constructor for the RemoteThread.

		Arguments:
		  dStatusLogger         : handler to a logging utility for job status
		  dDetailLogger         : handler to a logging utility for job details
		  jobName (str)         : name of the content gathering job in a package
		  packageName (str)     : name of the content gathering package
		  scriptName (str)      : name of the content gathering script to run
		  jobMetaData (dict)    : controlling information for this job, defined
		                          by the JSON file in the job folder
		  jobEndpoints (Queue)  : shared Queue holding the remote endpoints
		                          or destinations where this job is to run
		  jobStatistics (Queue) : shared Queue for passing back runtime stats
		  kafkaProducer         : reusing the same kafka producer across threads
		  kafkaTopic (str)      : name of the kafka topic/queue to send messages

		"""
		self.loggerStatus = dStatusLogger
		self.logger = dDetailLogger
		self.env = env
		self.jobName = jobName
		self.packageName = packageName
		self.scriptName = scriptName
		self.jobEndpoints = jobEndpoints
		self.jobStatistics = jobStatistics
		self.kafkaProducer = kafkaProducer
		self.kafkaTopic = kafkaTopic
		self.endpointIdColumn = jobMetaData['endpointIdColumn']
		self.jobMaxJobRunTime = int(jobMetaData['maxJobRunTime'])
		self.threadedFunction = self.jobWrapper
		self.endpoint = None
		self.runtime = None
		self.resultCount = {}
		self.protocolType = protocolType
		self.parameters = inputParameters
		self.protocols = protocols
		self.shellConfig = shellConfig
		self.jobMetaData = jobMetaData
		super().__init__(self.logger, self.jobName)


	def trackResultCount(self, jsonResult):
		"""Accumulate and track object counts.

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


	def sendToKafka(self, kafkaTopic=None, unstructuredData=None):
		"""Send results from a thread over to kafka queues/topics."""
		self.kafkaProducer.poll(0)
		if unstructuredData is not None:
			if kafkaTopic is not None:
				self.logger.debug('Sending to Kafka topic {kafkaTopic} data type {dataType!r}', kafkaTopic=kafkaTopic, dataType=type(unstructuredData))
				self.kafkaProducer.produce(kafkaTopic, value=json.dumps(unstructuredData).encode('utf-8'))
			else:
				self.logger.error('Received unstructured data for Kafka, but without a specified topic: {unstructuredData!r}', unstructuredData=unstructuredData)
		else:
			jsonResult = self.runtime.results.getJson()
			if (jsonResult is not None and len(jsonResult['objects']) > 0):
				## Accumulate and track object counts.
				self.trackResultCount(jsonResult)
				## Should we verify the type is strictly json or dict
				## before attempting the send? Or let the error return?
				self.logger.debug('Sending to Kafka {jsonResult!r}', jsonResult=jsonResult)
				if kafkaTopic is not None:
					#self.kafkaProducer.send(kafkaTopic, value=jsonResult)
					self.kafkaProducer.produce(kafkaTopic, value=json.dumps(jsonResult).encode('utf-8'))
				else:
					#self.kafkaProducer.send(self.kafkaTopic, value=jsonResult)
					self.kafkaProducer.produce(self.kafkaTopic, value=json.dumps(jsonResult).encode('utf-8'))
			self.runtime.results.clearJson()
		self.kafkaProducer.flush()


	def jobWrapper(self, *args, **kargs):
		try:
			## Dynamic import for job script
			packageModule = '{}.{}.{}'.format(self.packageName, 'script', self.scriptName)
			self.logger.debug('Importing module: {packageModule!r}', packageModule=packageModule)
			startJobFunction = getattr(importlib.import_module(packageModule), 'startJob')
			workStarted = False

			while (not self.completed and not self.canceled):
				try:
					self.endTime = None
					## Allow timeout so we can continue checking self.canceled
					endpoint = self.jobEndpoints.get(True, .2)
					self.jobEndpoints.task_done()
					workStarted = True

					## The attribute leveraged by this statistic (and
					## later used as a primary key along with the job
					## name, when updating content_gathering_results)
					## is defined by endpointIdColumn in the job's JSON
					## file. So how the statistic is tracked depends on
					## what structure the endpoint query creates, along
					## with which attribute is listed in the job file.
					endpointValue = endpoint.get(self.endpointIdColumn)
					if endpointValue is None:
						endpointValue = endpoint.get('data').get(self.endpointIdColumn)
					if endpointValue is None:
						endpointValue = endpoint
					endpointValue = str(endpointValue)[:255]
					## Track in class variable so we can see externally
					self.endpoint = endpointValue

					## Reset count if we run multiple endpoints in same thread
					self.resultCount = {}
					## Initialize runtime container
					self.runtime = Runtime(self.logger, self.env, self.packageName, self.jobName, endpoint, self.jobMetaData, self.sendToKafka, self.parameters, self.protocolType, self.protocols, self.shellConfig)
					if not self.runtime.setupComplete:
						raise EnvironmentError('Runtime was not initialized properly!')

					## Start job execution; expect updated runtime object
					self.runtime.logger.report('Running job {name!r} on endpoint {endpoint_value!r}', name=self.jobName, endpoint_value=endpoint)
					## Try/except prevents bad scripting from jumping out of the
					## standard flow here; expect the worst, hope for the best.
					try:
						self.startTime = time.time()
						startJobFunction(self.runtime)
					except:
						self.runtime.setError(__name__)
					## overload the start/end times for this job execution
					self.endTime = time.time()

					## Send any (remaining) results to Kafka
					try:
						self.sendToKafka()
					except:
						self.logger.error('Error sending results to Kafka. Exception: {exception!r}', exception=str(sys.exc_info()[1]))
						self.runtime.message(str(sys.exc_info()[1]))

					## Job cleanup
					self.runtime.setEndTime()
					self.loggerStatus.info('{runtime_repr!r}, {result_count!r}', runtime_repr=self.runtime, result_count=self.resultCount)

					## Update the job statistics from this run
					## If we hit a cancel flag, might as well submit results
					while (not self.completed):
						try:
							jobStat = {}
							jobStat['endpoint'] = endpointValue
							jobStat['status'] = self.runtime.jobStatus
							jobStat['messages'] = str(list(self.runtime.jobMessages))[:8096]
							jobStat['start'] = self.runtime.startTime.strftime('%Y-%m-%d %H:%M:%S.%f')
							jobStat['end'] = self.runtime.endTime.strftime('%Y-%m-%d %H:%M:%S.%f')
							jobStat['results'] = self.resultCount
							self.jobStatistics.put(jobStat, True, .1)
							break
						except Queue_Full:
							if self.canceled:
								break
							## If the queue is full, wait for the workers to pull
							## data off and free up room; no need to break here.
							continue
						except:
							exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
							self.logger.error('Exception in jobWrapper: {exception!r}', exception=exception)
							break
					self.endpoint = None

				except Queue_Empty:
					## If endpoints have all been worked through, exit thread
					if self.endpointsLoaded:
						self.logger.debug('{jobName!r} {threadName!r}: all endpoints worked through; exiting.', jobName=self.jobName, threadName=self.threadName)
						break
					if not workStarted:
						## May be a problem with kafka... so message out. This
						## isn't the best place, since 100 threads will message
						## the same thing individually... but it's all we got.
						self.logger.debug('{jobName!r} {threadName!r}: queue empty but endpoints are not loaded yet.', jobName=self.jobName, threadName=self.threadName)
					time.sleep(1)
					continue
				except:
					self.canceled = True
					self.exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					self.logger.error('Exception in {jobName!r} {threadName!r}: {exception!r}', jobName=self.jobName, threadName=self.threadName, exception=self.exception)

			self.logger.debug('jobWrapper: Closing job {jobName!r} {threadName!r}.  completed: {completed!r}. canceled: {canceled!r}. endpointsLoaded: {endpointsLoaded!r}', jobName=self.jobName, threadName=self.threadName, completed=self.completed, canceled=self.canceled, endpointsLoaded=self.endpointsLoaded)

		except:
			self.exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in {jobName!r} {threadName!r}: {exception!r}', jobName=self.jobName, threadName=self.threadName, exception=self.exception)

		## end jobWrapper
		return
