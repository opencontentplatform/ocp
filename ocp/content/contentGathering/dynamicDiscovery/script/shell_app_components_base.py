"""Dynamic discovery for Base Application Components.

Both dynamic discovery jobs for Application Components ('Base' & 'Vocal') use
a common library with the same functions and code paths - once a process is
selected. However, the method for selecting a process is different. The 'Base'
job selects processes at the bottom of the process tree (those without any
spawned children), while the 'Vocal' job selects processes using the network.
Those two methods reveal different types of application components, and each
has proven extremely useful for automated mapping and modeling techniques.

Functions:
  startJob : standard job entry point
  baseAppComponents : find processes without children and start investigation
  standardBaseSetup : setup required on all OS types for 'Base' discovery

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Jun 25, 2018

"""
import sys
import traceback
from contextlib import suppress

## From openContentPlatform
from protocolWrapper import getClient
## From this package
import osSoftwarePackages
import osStartTasks
import shellAppComponentsUtils


def standardBaseSetup(runtime, data):
	"""Setup required on all OS types for 'Base' Application Components.

	Arguments:
	  runtime (dict)             : object used for providing I/O for jobs and
	                               tracking the job thread through its runtime
	  data (dataContainer)       : holds variables used across functions
	"""
	## Get the startTask and software filter parameters once, and use many times
	osStartTasks.getFilterParameters(runtime, data.osType, data.startTaskFilters)
	osSoftwarePackages.getFilterParameters(runtime, data.osType, data.softwareFilters)

	## Get Processes
	runtime.logger.report(' retrieving Processes...')
	runtime.logger.setFlag(False)
	shellAppComponentsUtils.getRawProcesses(runtime, data)
	runtime.logger.setFlag(data.savedPrintDebug)

	## end standardBaseSetup
	return


def baseAppComponents(runtime, data):
	"""Find processes without children and start investigation.

	Arguments:
	  runtime (dict)             : object used for providing I/O for jobs and
	                               tracking the job thread through its runtime
	  data (dataContainer)       : holds variables used across functions
	"""
	try:
		runtime.logger.report('Starting Base Application Component discovery on {nodeName!r} ({protocolIp!r})', nodeName=data.nodeName, protocolIp=data.protocolIp)
		## Setup required for all OS types
		standardBaseSetup(runtime, data)
		if len(data.processDictionary) <= 0:
			runtime.logger.report('All processes were filtered out; nothing to analyze.')

		## Go through each process that wasn't filtered out
		for pid in data.processDictionary:
			(processData, processPpid, objectId) = data.processDictionary[pid]
			runtime.logger.report('looking at process {pid!r}: {processData!r}', pid=pid, processData=processData)
			## Look to see if any other process lists this PID as its parent;
			## if not, then it becomes an entry point for investigation. I use
			## the dictionary here since it has all processes (filtered or not)
			usedAsParent = False
			for thisPid in data.processDictionary.keys():
				with suppress(Exception):
					(thisData, thisPpid, thisId) = data.processDictionary[thisPid]
					if (pid == thisPpid):
						usedAsParent = True
						break
			if usedAsParent:
				runtime.logger.report(' skipping process with pid {processId!r}, since it has children: {processData!r} ', processId=pid, processData=processData)
				continue
			## Now I'm dealing with a process with no children, which is where
			## I start investigation for the 'Base' discovery.

			## Determine if we are looking at a process we need to ignore and
			## instead look one level higher in the process tree (if it exists)
			(pid, processData, objectId) = shellAppComponentsUtils.translateIgnoredProcess(runtime, data, pid, processData, processPpid, objectId)
			if processData is None:
				continue

			## Determine if process already exists or if we otherwise skip it
			(skipProcess, processIdentifier) = shellAppComponentsUtils.shouldWeSkipThisProcess(runtime, processData, data)
			if skipProcess or processIdentifier is not None:
				continue

			## Run the osSpecificSetup before looking at the first process; this
			## is down here instead of at the start of the flow because unless a
			## new process is found, we won't need to ask this of the endpoint.
			if not data.osSpecificSetupComplete:
				shellAppComponentsUtils.osSpecificSetup(runtime, data)
				data.osSpecificSetupComplete = True

			## Call walkPIDtree for the remaining work; note this returns two
			## variables (processFingerprintId, softwareFingerprintId), but I
			## don't need their handles for Base discovery
			shellAppComponentsUtils.walkPIDtree(runtime, data, pid, processData, objectId)

		## OS cleanup; currently just the HPUX inventory temp file removal
		shellAppComponentsUtils.osSpecificCleanup(runtime, data)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in baseAppComponents for {nodeName!r}: {stacktrace!r}', nodeName=data.nodeName, stacktrace=stacktrace)

	## end baseAppComponents
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing I/O for jobs and tracking
	                     the job thread through its runtime
	"""
	client = None
	try:
		## Configure shell client
		client = getClient(runtime, commandTimeout=30)
		if client is not None:
			## Get a handle on our Node in order to link objects in this job
			nodeId = runtime.endpoint.get('data').get('container')
			runtime.results.addObject('Node', uniqueId=nodeId)

			## Initialize data container used to pass I/O between functions
			data = shellAppComponentsUtils.dataContainer(runtime, nodeId, client, getIpList=False)

			## Open client session before starting the work
			client.open()

			## Do the work
			baseAppComponents(runtime, data)

			## Good house keeping; though I force this after the exception below
			client.close()

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
