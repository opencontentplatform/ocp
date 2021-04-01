"""Sends Node-->ProcessFingerprint-->SoftwareFingerprint mappings to ServiceNow.

Functions:
  startJob : Standard job entry point
  doThreadedWork : Create and link associated objects
  getFullDataSet : Gather full dataset from ITDM
  getDeltaDataSet : Gather partial dataset from ITDM (based on time of last run)

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created July 17, 2019

"""
import sys
import traceback
import os
import json
import time
import arrow
from queue import Queue
from queue import Empty as Queue_Empty
from queue import Full as Queue_Full
from contextlib import suppress

## From openContentPlatform
import fingerprintUtils
from workerThread import WorkerThread
from utilities import getApiQueryResultsFull, getApiQueryResultsInChunks


def getDeltaDataSet(runtime, jobPath, query, fullQuery, previousRuntimeStatistics, deltaSyncExpirationInDays):
	"""Pull partial/delta dataset from ITDM, based on last successful run."""
	## First check the previous runtime stats to direct the type of job. The job
	## params asked for delta, but if we didn't have a successful in the past,
	## then this needs to redirect to a full sync instead.
	runtime.logger.report('SNOW JOB Stats: {stats!r}', stats=previousRuntimeStatistics)
	lastSuccess = previousRuntimeStatistics.get('date_last_success')
	lastSuccessDate = None
	redirectToFull = False
	if lastSuccess is None:
		redirectToFull = True
		runtime.logger.info('Redirecting this delta-sync to full-sync; previous runtime statistics do not hold a value for date_last_success.')
	else:
		## The deltaSyncExpirationInDays variable holds the number of days since
		## the last successful delta sync, before the job redirects to full sync
		#lastSuccessDate = datetime.datetime.strptime(lastSuccess, '%Y-%m-%d %H:%M:%S')
		lastSuccessDate = arrow.get(lastSuccess, 'YYYY-MM-DD HH:mm:ss')
		expirationDate = arrow.utcnow().shift(days=-(deltaSyncExpirationInDays)).datetime
		if expirationDate > lastSuccessDate:
			redirectToFull = True
			runtime.logger.info('Redirecting this delta-sync to full-sync; value for \'date_last_success\'={lastSuccess!r} is past the number of days allowed in the user provided parameter \'deltaSyncExpirationInDays\'={deltaSyncExpirationInDays!r}.', lastSuccess=lastSuccess, deltaSyncExpirationInDays=deltaSyncExpirationInDays)

	if redirectToFull or lastSuccessDate is None:
		runtime.logger.info('Redirecting Delta sync to Full sync')
		return(getFullDataSet(runtime, jobPath, fullQuery))

	## Load the file containing the query
	queryFile = os.path.join(jobPath, 'input', query + '.json')
	if not os.path.isfile(queryFile):
		raise EnvironmentError('JSON query file does not exist: {}'.format(queryFile))
	queryContent = None
	with open(queryFile, 'r') as fp:
		queryContent = fp.read()
	## Replace the <VALUE1> and <VALUE2> placeholders in the in betweendate
	## operation, with the proper formats:
	##   VALUE1 = the last successful runtime of the job, which should be in UTC
	##   VALUE2 = current UTC time sent in the expected string format
	utcNow = arrow.utcnow().format('YYYY-MM-DD HH:mm:ss')
	runtime.logger.info('Using this time comparison for deta-sync query:  time_created is between {lastSuccess!r} and {utcNow!r}...', lastSuccess=lastSuccess, utcNow=utcNow)
	# lastSuccess = "2019-07-26 09:39:00"
	# utcNow = "2019-07-10 09:39:00"
	queryContent = queryContent.replace('<VALUE1>', '"{} UTC"'.format(lastSuccess))
	queryContent = queryContent.replace('<VALUE2>', '"{} UTC"'.format(utcNow))

	queryResults = getApiQueryResultsFull(runtime, queryContent, resultsFormat='Nested-Simple', headers={'removeEmptyAttributes': False})
	if queryResults is None or len(queryResults) <= 0:
		raise EnvironmentError('No results found from database; nothing to send.')

	## end getDeltaDataSet
	return queryResults


def getFullDataSet(runtime, jobPath, query):
	"""Pull requested dataset from ITDM."""
	## Load the file containing the query
	queryFile = os.path.join(jobPath, 'input', query + '.json')
	if not os.path.isfile(queryFile):
		raise EnvironmentError('JSON query file does not exist: {}'.format(queryFile))
	queryContent = None
	with open(queryFile) as fp:
		queryContent = json.load(fp)

	## Get chunked query results from the API; best to use when the data
	## set can be quite large, but the second version can be used if you
	## want to gather everything in one call or in a non-Flat format:
	#queryResults = getApiQueryResultsInChunks(runtime, queryContent)
	queryResults = getApiQueryResultsFull(runtime, queryContent, resultsFormat='Nested-Simple', headers={'removeEmptyAttributes': False})
	if queryResults is None or len(queryResults) <= 0:
		raise EnvironmentError('No results found from database; nothing to send.')

	## Convert the API results into a desired layout for our needs here? No,
	## we would only need to do this if using chunked/flat result format.
	#transformResultsFromApi(runtime, queryResults)

	## end getFullDataSet
	return queryResults


def doThreadedWork(runtime, scriptName, queryResults, restEndpoint, userContext, numberOfThreads):
	try:
		jobThreads = []
		jobName = runtime.jobName
		## Queue used to transfer endpoints to worker threads
		inputQueue = Queue()

		## Spin up the worker threads
		runtime.logger.info('Spinning up {numberOfJobThreads!r} threads for job {jobName!r}', numberOfJobThreads=numberOfThreads, jobName=jobName)
		for i in range(int(numberOfThreads)):
			activeThread = WorkerThread(runtime, scriptName, inputQueue, restEndpoint, userContext)
			activeThread.start()
			jobThreads.append(activeThread)

		## Load ITDM data set into a shared queue for the worker threads
		for result in queryResults:
			while True:  # loop for the Queue_Full catch
				try:
					inputQueue.put(result, True, .1)
					break
				except Queue_Full:
					## If the queue is full, wait for the workers to pull data
					## off and free up room; no need to break here. Note: this
					## is blocking; we may want to convert into asynchronous
					## thread/defered, to avoid parent control/breaks.
					continue
				except:
					runtime.setError(__name__)
					break

		## Wait for the threads
		while not inputQueue.empty():
			time.sleep(3)

		## Tell all idle threads (threads not currently running a job on
		## an endpoint) to gracefully shut down
		runtime.logger.info('Spinning down active threads for job {jobName!r}', jobName=jobName)
		for jobThread in jobThreads:
			jobThread.completed = True

		## Ensure job threads finish properly, before removing references
		runtime.logger.info('Waiting for threads to clean up...')
		while True:
			updatedJobThreads = []
			for jobThread in jobThreads:
				if (jobThread is not None and
					jobThread.is_alive()):
					updatedJobThreads.append(jobThread)
			jobThreads = updatedJobThreads
			if len(jobThreads) > 0:
				## I don't want to 'join' the threads, but should replace
				## the blocking sleep with something that can be interrupted
				time.sleep(.5)
			else:
				break
		runtime.logger.info('Threads finished.')

	except:
		runtime.setError(__name__)

	## end doThreadedWork
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	client = None
	try:
		## User defined parameters
		workerScript = runtime.parameters.get('workerScript')
		restEndpoint = runtime.parameters.get('restEndpoint')
		userDescriptor = runtime.parameters.get('userDescriptor', 'ServiceNow')
		fullQuery = runtime.parameters.get('fullQuery')
		deltaQuery = runtime.parameters.get('deltaQuery')
		runDeltaSync = runtime.parameters.get('runDeltaSync')
		numberOfThreads = int(runtime.parameters.get('numberOfThreads'))
		previousRuntimeStatistics = runtime.jobMetaData.get('previousRuntimeStatistics', {})
		deltaSyncExpirationInDays = int(runtime.parameters.get('deltaSyncExpirationInDays'))

		## Set the corresponding directories for input
		jobScriptPath = os.path.dirname(os.path.realpath(__file__))
		jobPath = os.path.abspath(os.path.join(jobScriptPath, '..'))

		## Establish a connection the the ServiceNow REST API and retrieve token
		userContext = fingerprintUtils.getUserContextMatchingDescriptor(runtime, restEndpoint, userDescriptor)
		if userContext is None:
			raise EnvironmentError('Unable to connect to ServiceNow instance: {}'.format(restEndpoint))

		## Query the ITDM Rest API for dataset
		queryResults = None
		if runDeltaSync:
			queryResults = getDeltaDataSet(runtime, jobPath, deltaQuery, fullQuery, previousRuntimeStatistics, deltaSyncExpirationInDays)
		else:
			queryResults = getFullDataSet(runtime, jobPath, fullQuery)
		runtime.logger.report('Node result sets to send into ServiceNow: {nodeCount!r}', nodeCount=len(queryResults))

		# runtime.status(3)
		# sys.exit(0)

		## Start the work
		doThreadedWork(runtime, workerScript, queryResults, restEndpoint, userContext, numberOfThreads)

		## Update the runtime status to success
		if runtime.getStatus() == 'UNKNOWN':
			runtime.status(1)

	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end startJob
	return
