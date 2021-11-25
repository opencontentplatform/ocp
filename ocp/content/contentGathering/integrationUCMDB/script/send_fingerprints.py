"""Sends Node-->ProcessFingerprints-->SoftwareFingerprint mappings to the UCMDB.

Functions:
  startJob : Standard job entry point
  getDataSet : Pull requested dataset from ITDM
  doWork : Create and link associated objects via aliases

If this is built on, we should generalize and wrap the data transformations.

"""
import sys
import traceback
import os
import json
from contextlib import suppress

## From openContentPlatform
import fingerprintUtils
from utilities import getApiQueryResultsFull, getApiQueryResultsInChunks
from ucmdbTopologyData import UcmdbTopologyData


def doWork(runtime, queryResults, ucmdbService):
	"""Create and link associated aliases.

	Eventually I'll want a descriptor language to abstract the coding and allow
	a single script to do the work, regardless of the data set or mapping. But
	for now, I'll make this specific to the data set:

	Node -->
	         ProcessFingerprint -->
	                                SoftwareFingerprint
	"""
	data = UcmdbTopologyData('ITDM Fingerprints')
	try:
		for result in queryResults:
			runtime.logger.report('doWork on Node result: {result!r}', result=result)
			## First object is a Node
			(nodeId, nodeType, nodeProps) = fingerprintUtils.transformNode(runtime, result, data)
			if nodeId is None:
				continue

			## Next level holds mapped processes
			processList = result.get('children', [])
			for process in processList:
				processId = fingerprintUtils.transformFingerprint(runtime, process, data, nodeId)
				if processId is None:
					continue

				## Link the process to the node
				data.addLink('composition', nodeId, processId)

				## Last level holds mapped software
				softwareList = process.get('children', [])
				for software in softwareList:
					softwareId = fingerprintUtils.transformFingerprint(runtime, software, data, nodeId)
					if softwareId is None:
						continue

					## Link the software to the node
					data.addLink('composition', nodeId, softwareId)
					## Link the software to the process
					data.addLink('dependency', softwareId, processId)

				if (data.size() > 100):
					fingerprintUtils.sendDataSet(runtime, ucmdbService, data)
					## Re-add the node back onto the JSON result
					nodeId = data.addObject(nodeType, **nodeProps)

			## Send and reset the results after processing each node
			fingerprintUtils.sendDataSet(runtime, ucmdbService, data)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in doWork: {stacktrace!r}', stacktrace=stacktrace)

	## end doWork
	return


def getDataSet(runtime, jobPath):
	"""Pull requested dataset from ITDM."""
	targetQuery = runtime.parameters.get('targetQuery')
	queryFile = os.path.join(jobPath, 'input', targetQuery + '.json')
	if not os.path.isfile(queryFile):
		raise EnvironmentError('JSON query file does not exist: {}'.format(queryFile))

	## Load the file containing the query
	queryContent = None
	with open(queryFile) as fp:
		queryContent = json.load(fp)

	## Get chunked query results from the API; best to use when the data
	## set can be quite large, but the second version can be used if you
	## want to gather everything in one call or in a non-Flat format:
	#queryResults = getApiQueryResultsInChunks(runtime, queryContent)
	queryResults = getApiQueryResultsFull(runtime, queryContent, resultsFormat='Nested-Simple', headers={'removeEmptyAttributes': False})
	if queryResults is None or len(queryResults) <= 0:
		raise EnvironmentError('No IPs found from database; nothing to update.')

	## Convert the API results into a desired layout for our needs here? No,
	## we would only need to do this if using chunked/flat result format.
	#transformResultsFromApi(runtime, queryResults)

	## end getDataSet
	return queryResults


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	client = None
	try:
		## Set the corresponding directories for input
		jobScriptPath = os.path.dirname(os.path.realpath(__file__))
		jobPath = os.path.abspath(os.path.join(jobScriptPath, '..'))

		## Establish a connection the the UCMDB REST API and retrieve token
		ucmdbService = fingerprintUtils.getCredentialMatchingDescriptor(runtime)
		if ucmdbService is None:
			raise EnvironmentError('Unable to connect to UCMDB')

		## Query the ITDM Rest API for dataset
		queryResults = getDataSet(runtime, jobPath)
		runtime.logger.report('Node result sets to send into UCMDB: {nodeCount!r}', nodeCount=len(queryResults))

		## Start the work
		doWork(runtime, queryResults, ucmdbService)

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
