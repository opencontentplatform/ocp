"""Send 'Node--> ProcessFingerprint--> SoftwareFingerprint' maps to ServiceNow.

Functions:
  startJob : Standard job entry point
  doWork : Create and link associated objects, and send to REST endpoint

Notes:
=============================================================================
The below ServiceNow documentation link:
  https://docs.servicenow.com/bundle/madrid-servicenow-platform/page/product/
			configuration-management/concept/best-practices-id-reconcile.html

Mentions the following:
  When inserting many CIs, all of which depend on the same CI, you should
  serialize your API calls. Otherwise, attempting to concurrently process
  many CIs can clog the system, significantly degrading overall system
  performance.

That means we need to send individual ProcessFingerprint --> SoftwareFingerprint
submissions.  So if a server has 100 ProcessFingerprints, that's 100 POST calls
to the REST API. So the threaded work here is bundled per server dataset, and is
broken into individual calls to adhear to the ServiceNow direction.
=============================================================================

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created July 17, 2019

"""
import sys
import traceback
import os
import json
from contextlib import suppress

## From openContentPlatform
import fingerprintUtils
from snowTopologyData import SnowTopologyData


def doWork(runtime, webService, dataToProcess):
	"""Create and link associated objects.


	"""
	data = SnowTopologyData('ITDM Fingerprints')
	try:
		runtime.logger.report('doWork: dataToProcess: {dataToProcess!r}', dataToProcess=dataToProcess)
		## First object is a Node
		fingerprintUtils.transformNode(runtime, dataToProcess, data)
		(nodeType, sysId) = fingerprintUtils.sendNodeAndGetIdentifier(runtime, webService, data)

		## Next level holds mapped processes
		processList = dataToProcess.get('children', [])
		for process in processList:
			## Add node by reference, as the first object on data to send
			nodeId = data.addObject(nodeType, uniqueId=sysId)

			processId = fingerprintUtils.transformFingerprint(runtime, process, data)
			if processId is None:
				## Make sure to clear the node back off our dataset, to
				## maintain positional integrity for the link references
				data.reset()
				continue

			## Link the process to the node
			data.addLink('Runs on::Runs', processId, nodeId)

			## Last level holds mapped software
			softwareList = process.get('children', [])
			for software in softwareList:
				softwareId = fingerprintUtils.transformFingerprint(runtime, software, data)
				if softwareId is None:
					continue

				## Link the software to the node
				data.addLink('Runs on::Runs', softwareId, nodeId)
				## Link the software to the process
				data.addLink('Depends on::Used by', processId, softwareId)

			if (data.size() > 100):
				fingerprintUtils.sendDataSet(runtime, webService, data)
				## Re-add the node back onto the JSON result
				nodeId = data.addObject(nodeType, **nodeProps)

			## Send and reset the results after processing each node
			fingerprintUtils.sendDataSet(runtime, webService, data)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in doWork: {stacktrace!r}', stacktrace=stacktrace)

	## end doWork
	return


def startJob(runtime, webService, dataToProcess):
	"""Standard job entry point.

	Arguments:
	  runtime (dict) : object used for providing input into jobs and tracking
	                   the job thread through the life of its runtime.
	  webService (class) : instance of snowRestAPI
	  dataToProcess (json) : map result set pulled from the shared Queue
	"""
	client = None
	try:
		## Start the work
		doWork(runtime, webService, dataToProcess)

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
