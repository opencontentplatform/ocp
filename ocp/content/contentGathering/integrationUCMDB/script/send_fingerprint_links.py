"""Send ITDM client/server dependencies with ProcessFingerprints to the UCMDB.

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
import re
from contextlib import suppress

## From openContentPlatform
import fingerprintUtils
from utilities import getApiQueryResultsFull
from ucmdbTopologyData import UcmdbTopologyData


def doWork(runtime, queryResults, ucmdbService, isServer=True):
	"""Create and link associated aliases.

	Eventually I'll want a descriptor language to abstract the coding and allow
	a single script to do the work, regardless of the data set or mapping. But
	for now, I'll make this specific to the data set:

	Server_Node -->
	      Server_Process -->
	            Client_Port -->
	                  Client_Process -->
	                        Client_Node
	"""
	data = UcmdbTopologyData('ITDM Fingerprints')
	try:
		for result in queryResults:
			runtime.logger.report('doWork on Node result: {result!r}', result=result)
			## First object is a Node (server side)
			(nodeId, nodeType, nodeProps) = fingerprintUtils.transformNode(runtime, result, data)
			if nodeId is None:
				continue

			## Next level holds mapped processes (server side)
			processList = result.get('children', [])
			for process in processList:
				processId = fingerprintUtils.transformFingerprint(runtime, process, data, nodeId)
				if processId is None:
					continue

				## Link the process to the node
				data.addLink('composition', nodeId, processId)

				## Next level holds TCP/IP port connection
				portList = process.get('children', [])
				for port in portList:
					# portId = fingerprintUtils.transformTcpIpPort(runtime, port, data)
					# if portId is None:
					# 	continue
					# ## Link the port to the process
					# if isServer:
					# 	data.addLink('usage', processId, portId)
					# else:
					# 	data.addLink('client_server', processId, portId, properties={"clientserver_protocol": "tcp"})

					## Next level holds mapped processes (client side)
					clientProcessList = port.get('children', [])
					for clientProcess in clientProcessList:
						## Last level holds the Node (client side)
						runtime.logger.report('clientNode list: {result!r}', result=clientProcess.get('children', []))
						clientNode = clientProcess.get('children', [])[0]
						runtime.logger.report('clientNode first: {result!r}', result=clientNode)
						(clientNodeId, clientNodeType, clientNodeProps) = fingerprintUtils.transformNode(runtime, clientNode, data)
						runtime.logger.report('clientNode data: {}  {}'.format(clientNodeId, clientNodeType))
						if clientNodeId is None:
							continue
						## Now we have the client node container, add process
						clientProcessId = fingerprintUtils.transformFingerprint(runtime, clientProcess, data, clientNodeId)

						## Links
						data.addLink('composition', clientNodeId, clientProcessId)
						## Process to process client_server links
						data.addLink('client_server', processId, clientProcessId, properties={"clientserver_protocol": "tcp"})

				if (data.size() > 100):
					fingerprintUtils.sendDataSet(runtime, ucmdbService, data)
					## Re-add the node back onto the JSON result
					nodeId = data.addObject(nodeType, **nodeProps)

			## Send and reset the results after processing each node
			if (data.size() > 1):
				## Don't need to send back a lonely node
				fingerprintUtils.sendDataSet(runtime, ucmdbService, data)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in doWork: {stacktrace!r}', stacktrace=stacktrace)

	## end doWork
	return


def getDataSet(runtime, jobPath, queryName):
	"""Pull requested dataset from ITDM."""
	queryFile = os.path.join(jobPath, 'input', queryName + '.json')
	if not os.path.isfile(queryFile):
		raise EnvironmentError('JSON query file does not exist: {}'.format(queryFile))

	## Load the file containing the query
	queryContent = None
	with open(queryFile) as fp:
		queryContent = json.load(fp)
	queryResults = getApiQueryResultsFull(runtime, queryContent, resultsFormat='Nested-Simple', headers={'removeEmptyAttributes': False})
	if queryResults is None or len(queryResults) <= 0:
		raise EnvironmentError('No IPs found from database; nothing to update.')

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

		# # Query the ITDM Rest API for the SERVER dataset
		# queryResults = getDataSet(runtime, jobPath, runtime.parameters.get('serverQuery'))
		# runtime.logger.report('Server result set to send into UCMDB: {objectCount!r}', objectCount=len(queryResults))
		# ## Process SERVER connections
		# doWork(runtime, queryResults, ucmdbService)
		#
		# ## Query the ITDM Rest API for the CLIENT dataset
		# queryResults = getDataSet(runtime, jobPath, runtime.parameters.get('clientQuery'))
		# runtime.logger.report('Client result set to send into UCMDB: {objectCount!r}', objectCount=len(queryResults))
		# ## Process CLIENT connections
		# doWork(runtime, queryResults, ucmdbService, False)

		## Query the ITDM Rest API for the dataset
		queryResults = getDataSet(runtime, jobPath, runtime.parameters.get('linksQuery'))
		runtime.logger.report('Client result set to send into UCMDB: {objectCount!r}', objectCount=len(queryResults))
		## Process connections
		doWork(runtime, queryResults, ucmdbService, False)

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
