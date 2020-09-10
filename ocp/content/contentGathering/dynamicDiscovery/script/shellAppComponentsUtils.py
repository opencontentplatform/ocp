"""Shared utilities for Application Component discovery jobs.

Both dynamic discovery jobs for Application Components ('Base' & 'Vocal') use
this library for common functions and code paths.


Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Jun 27, 2018

"""
import sys
import traceback
import re
from contextlib import suppress

## From openContentPlatform
import osProcesses
import osSoftwarePackages
import osStartTasks
import utilities


def walkPIDtree(runtime, data, processId, processData, objectId):
	"""Walk the PID tree looking for a process or parent with context.

	This function is handed the context of a single running process; with that
	particular process stack in focus, it works through the data sets multiple
	times, leveraging multiple techniques, to find higher-level ownership type
	context about that running process.

	This is the core flow behind the dynamic discovery jobs. It determines as
	much as possible about a running process, without any hints or manual input.
	"""
	processFingerprintId = None
	softwareFingerprintId = None
	try:
		## Need to have a qualified process object or none of this will work
		if (processData is None or processData.get('name') is None):
			return None
		processName = processData.get('name')
		processTree = processData.get('process_hierarchy')
		## Also need to have a process tree
		if (processTree is None or processTree == 'Unknown'):
			return None

		## Analyze this process and see if we can find high level context. This
		## is the main goal of application components, but I want to accomodate
		## jobs that may only need process and IP:port context.
		if (runtime.parameters.get('createSignatureObjects', True)):

			## Qualify and update this process of interest, before analysis
			osProcesses.updateThisProcess(runtime, processData, data.client, data.osType, processId)

			## ===============================================================
			## Level 1: Loop through processes in this process stack, looking
			## for a PID being managed by an OS "start task" (Service/Daemon).
			## ===============================================================
			runtime.logger.report(' Starting walkPIDtree level 1 analysis on tree {processTree!r} by calling findStartTask', processTree=processTree)
			(processFingerprintId, softwareFingerprintId, trackThisComponent) = findStartTask(runtime, data, processId, processName, processData, processTree)
			if (softwareFingerprintId != None or not trackThisComponent):
				runtime.logger.report(' Level 1 mapped processTree {processTree!r} to Application Component {softwareFingerprintId!r}', processTree=processTree, softwareFingerprintId=softwareFingerprintId)
				return (processFingerprintId, softwareFingerprintId)

			## ===============================================================
			## Level 2: look for a previously created context
			## ===============================================================
			runtime.logger.report(' Starting walkPIDtree level 2 analysis on tree {processTree!r} by calling matchPreviousApplicationComponent', processTree=processTree)
			(processFingerprintId, softwareFingerprintId) = findPreviousApplicationComponent(runtime, data, processData)
			if (softwareFingerprintId != None):
				runtime.logger.report(' Level 2 mapped processTree {processTree!r} to Application Component {softwareFingerprintId!r}', processTree=processTree, softwareFingerprintId=softwareFingerprintId)
				return (processFingerprintId, softwareFingerprintId)

			## ===============================================================
			## Level 3: loop through processes in this stack/tree; use
			## investigative analysis to pull meaning from the runtime.
			## ===============================================================
			runtime.logger.report(' Starting walkPIDtree level 3 analysis on tree {processTree!r} by calling findNewApplicationComponentL1', processTree=processTree)
			(processFingerprintId, softwareFingerprintId, trackThisComponent) = findNewApplicationComponentL1(runtime, data, processId, processName, processData, processTree)
			if (softwareFingerprintId != None or not trackThisComponent):
				runtime.logger.report(' Level 3 mapped processTree {processTree!r} to Application Component {softwareFingerprintId!r}', processTree=processTree, softwareFingerprintId=softwareFingerprintId)
				return (processFingerprintId, softwareFingerprintId)

			runtime.logger.report(' Starting walkPIDtree level 4 analysis on tree {processTree!r} by calling findNewApplicationComponentL2', processTree=processTree)
			(processFingerprintId, softwareFingerprintId, trackThisComponent) = findNewApplicationComponentL2(runtime, data, processId, processName, processData, processTree)
			if (softwareFingerprintId != None or not trackThisComponent):
				runtime.logger.report(' Level 4 mapped processTree {processTree!r} to Application Component {softwareFingerprintId!r}', processTree=processTree, softwareFingerprintId=softwareFingerprintId)
				return (processFingerprintId, softwareFingerprintId)

			## ===============================================================
			## Final level: Create the unqualified mapping for later analysis
			## ===============================================================
			runtime.logger.report(' Starting walkPIDtree level 5 (unknown stub) on tree {processTree!r} by calling stubUnknownApplicationComponent', processTree=processTree)
			(processFingerprintData, ppid, processFingerprintId) = data.processDictionary[int(processId)]
			if processFingerprintId is None:
				(processFingerprintId, pfAlreadyCreated) = runtime.results.addObject('ProcessFingerprint', **processFingerprintData)
				if not pfAlreadyCreated:
					runtime.results.addLink('Enclosed', data.nodeId, processFingerprintId)
			runtime.logger.report(' Level 5 mapped processTree {processTree!r} without context.', processTree=processTree)

		else:
			## Create only the ProcessFingerprint
			(processFingerprintId, pfAlreadyCreated) = runtime.results.addObject('ProcessFingerprint', **processData)
			if not pfAlreadyCreated:
				runtime.results.addLink('Enclosed', data.nodeId, processFingerprintId)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in walkPIDtree: {stacktrace!r}', stacktrace=stacktrace)

	## end walkPIDtree
	return (processFingerprintId, softwareFingerprintId)


###############################################################################
###########################  BEGIN GENERAL SECTION  ###########################
###############################################################################
class dataContainer:
	"""Container to hold variables used across functions.

	The purpose here is simply to reduce the required parameter lists between
	function calls. Many functions required more than 20 arguments passed in,
	even though most of the variables were not used directly in each function.
	"""
	def __init__(self, runtime, nodeId, client, getIpList=True):
		self.nodeId = nodeId
		self.client = client
		## Initialize these from our runtime object passed in
		self.protocolIp = runtime.endpoint.get('data').get('ipaddress')
		self.osType = runtime.endpoint.get('data').get('node_type')
		self.savedPrintDebug = runtime.parameters.get('printDebug', False)
		## This pulls the Node name related to the shell (and there will
		## only be one since the max/min on the endpoint query is 1)
		thisNode = runtime.endpoint.get('children').get('Node')[0]
		self.nodeName = thisNode.get('data', {}).get('hostname')
		self.nodeDomain = thisNode.get('data', {}).get('domain')
		## This pulls in the previously created processFingerprints
		self.previousProcesses = []
		for processFingerprint in thisNode.get('children').get('ProcessFingerprint'):
			processIdentifier = processFingerprint.get('identifier')
			processName = processFingerprint.get('data').get('name')
			processOwner = processFingerprint.get('data').get('process_owner')
			processPath = processFingerprint.get('data').get('path_from_process')
			processHierarchy = processFingerprint.get('data').get('process_hierarchy')
			processArgs = processFingerprint.get('data').get('process_args')
			self.previousProcesses.append((processIdentifier, processName, processPath, processOwner, processHierarchy, processArgs))
		## This pulls the list of IPs related to the Node (i.e. local IPs)
		self.ipList = []
		if getIpList:
			for ipObject in thisNode.get('children').get('IpAddress'):
				thisAddress = ipObject.get('data').get('address')
				is_ipv4 = ipObject.get('data').get('is_ipv4')
				if thisAddress is not None:
					self.ipList.append((thisAddress, is_ipv4))
		self.interpreters = runtime.endpoint.get('data').get('parameters').get('interpreters', [])
		self.osSpecificSetupComplete = False
		## The rest of these will be used after initial construction
		self.trackedIPs = {}
		self.serverPorts = {}
		self.clientPorts = {}
		self.pidTracking = {}
		self.fqProcessTracking = {}
		self.fqProcessFails = {}
		## The following allow jobs to wait & optimize process cmds
		self.filteredProcessList = []
		self.excludedProcessList = []
		self.processIgnoreList = []
		self.processFilters = {}
		self.processList = []
		self.processDictionary = {}
		self.softwareList = None
		self.softwareDictionary = {}
		self.startTaskDictionary = {}
		self.softwareFingerprints = []
		self.swlistFileDataFile = None
		self.swlistProductDataFile = None
		self.startTaskFilters = {}
		self.softwareFilters = {}
		self.udpListenerList = None
		self.tcpListenerList = None
		self.tcpEstablishedList = None
		## Need to validate the next three
		self.zoneTranslator = None
		self.IPdictWithHostIds = None
		self.HostArrayWithSoftwareElements = None

def getAttribute(attribute, maxLength=False):
	"""Normalize an attribute."""
	value = None
	if (attribute is not None):
		attribute = attribute.strip()
		if (len(attribute) > 0 and attribute != 'None' and attribute != 'null'):
			value = attribute
			if maxLength:
				value = attribute[:maxLength]
	return value

def getRequiredAttribute(attribute, maxLength=False):
	"""Normalize a required attribute and set a default value."""
	normalizedValue = getAttribute(attribute, maxLength)
	if normalizedValue is not None:
		return normalizedValue
	return 'Unknown'

def setRequiredAttribute(attributes, name, value, maxLength=False):
	"""Helper to get a required attribute and drop it into the dictionary."""
	attributes[name] = getRequiredAttribute(value, maxLength)

def setOptionalAttribute(attributes, name, value, maxLength=False):
	"""Helper to get an optional attribute and drop it in the dictionary."""
	normalizedValue = getAttribute(value, maxLength)
	if normalizedValue is not None:
		attributes[name] = normalizedValue


def resetConfigGroupSettings(runtime, savedSettings):
	"""Reset shell config and parameter settings to original values.

	Arguments:
	  runtime (dict)       : object used for providing I/O for jobs and tracking
	                         the job thread through its runtime
	  savedSettings (dict) : original shell config group settings
	"""
	for name,value in savedSettings.items():
		runtime.endpoint.get('data').get('parameters', {})[name] = value

	## end resetConfigGroupSettings
	return


def overrideConfigGroupSettings(runtime, savedSettings):
	"""Backup settings and override before gathering initial data sets.

	Arguments:
	  runtime (dict)       : object used for providing I/O for jobs and tracking
	                         the job thread through its runtime
	  savedSettings (dict) : original shell config group settings

	This allows the job to gather all data necessary for qualifying something
	even if it will eventually be filtered out. Without doing this, I can't
	enable more efficient resource consumption on future discovery invocations
	by avoiding processing something previously found and qualified.
	"""
	savedSettings['softwareFilterFlag'] = runtime.endpoint.get('data').get('parameters', {})['softwareFilterFlag']
	savedSettings['startTaskFilterFlag'] = runtime.endpoint.get('data').get('parameters', {}).get('startTaskFilterFlag', True)
	savedSettings['startTaskFilterExcludeCompare'] = runtime.endpoint.get('data').get('parameters', {}).get('startTaskFilterExcludeCompare', '==')
	savedSettings['startTaskFilterExcludeList'] = runtime.endpoint.get('data').get('parameters', {}).get('startTaskFilterExcludeList', ['Stopped'])
	savedSettings['startTaskFilterByActiveState'] = runtime.endpoint.get('data').get('parameters', {}).get('startTaskFilterByActiveState', True)
	savedSettings['startTaskFilterByName'] = runtime.endpoint.get('data').get('parameters', {}).get('startTaskFilterByName', False)
	savedSettings['startTaskFilterByDisplayName'] = runtime.endpoint.get('data').get('parameters', {}).get('startTaskFilterByDisplayName', False)
	savedSettings['startTaskFilterByStartName'] = runtime.endpoint.get('data').get('parameters', {}).get('startTaskFilterByStartName', False)
	## Temporarily override parameters to get full datasets; even if we
	## normally ignore certain software/services, we may need them for this
	runtime.endpoint.get('data').get('parameters', {})['softwareFilterFlag'] = False
	runtime.endpoint.get('data').get('parameters', {})['startTaskFilterFlag'] = True
	runtime.endpoint.get('data').get('parameters', {})['startTaskFilterExcludeCompare'] = '=='
	runtime.endpoint.get('data').get('parameters', {})['startTaskFilterExcludeList'] = ['Stopped']
	runtime.endpoint.get('data').get('parameters', {})['startTaskFilterByActiveState'] = True
	runtime.endpoint.get('data').get('parameters', {})['startTaskFilterByName'] = False
	runtime.endpoint.get('data').get('parameters', {})['startTaskFilterByDisplayName'] = False
	runtime.endpoint.get('data').get('parameters', {})['startTaskFilterByStartName'] = False

	## end overrideConfigGroupSettings
	return


def osSpecificCleanup(runtime, data):
	"""OS specific cleanup.

	Arguments:
	  runtime (dict)             : object used for providing I/O for jobs and
	                               tracking the job thread through its runtime
	  client (shell)             : instance of the shell wrapper
	  osType (str)               : Operating System type
	  swlistFileDataFile (str)   : temp file on HPUX Node holding swlist file
	  swlistProductDataFile (str): temp file on HPUX Node holding swlist product
	"""
	if (data.osType == 'HPUX'):
		## Remove the local files created at the start of the run
		#destroy_tempfiles_with_software_inventory(runtime, data.client, data.swlistFileDataFile, data.swlistProductDataFile)
		pass


def osSpecificSetup(runtime, data):
	"""OS specific pre-work before running the Application Component code.

	Some OS tooling is setup to allow individual queries for a process instance
	to gather software/ownership-type context (e.g. Linux, Solaris, and AIX).
	On those OS types, I don't need to worry about gathering initial datasets.
	But other OS tooling requires you to get the entire dataset before looking
	up each process instance (e.g. Windows and HP-UX). This function gathers
	initial datasets on OS types where the tooling isn't conducive to individual
	queries per process, but rather requires gathering the full dataset first.

	Arguments:
	  runtime (dict)       : object used for providing I/O for jobs and tracking
	                         the job thread through its runtime
	  client (shell)       : instance of the shell wrapper connected to endpoint
	  nodeId (str)         : 'object_id' of the Node the client is connected to
	  savedPrintDebug (str): original setting of the printDebug job parameter
	"""
	## Save the shell configuration before overriding for initial baseline
	savedSettings = {}
	overrideConfigGroupSettings(runtime, savedSettings)

	## OS specific pre-work before starting the Application Component stuff
	if (data.osType == 'Windows'):
		## Need to collect Software & Services on Windows beforehand
		runtime.logger.report(' retrieving Software...')
		runtime.logger.setFlag(False)
		data.softwareList = osSoftwarePackages.getSoftwarePackages(runtime, data.client, data.nodeId, trackResults=False)
		runtime.logger.setFlag(data.savedPrintDebug)
		runtime.logger.report(' retrieving Services...')
		runtime.logger.setFlag(False)
		data.startTaskDictionary = osStartTasks.getStartTasks(runtime, data.client, data.nodeId, trackResults=False)
		runtime.logger.setFlag(data.savedPrintDebug)
		## Raise an exception if the variables are empty
		if (len(data.softwareList) < 1 or len(data.startTaskDictionary) < 1):
			raise OSError('Windows software/services were not gathered; cannot continue.')

	elif (data.osType == 'Linux'):
		## Need to collect Services (daemons) on Linux beforehand
		runtime.logger.report(' retrieving Services...')
		runtime.logger.setFlag(False)
		data.startTaskDictionary = osStartTasks.getStartTasks(runtime, data.client, data.nodeId, trackResults=False)
		runtime.logger.setFlag(data.savedPrintDebug)
		## Raise an exception if the variables are empty
		if (len(data.startTaskDictionary) < 1):
			#raise OSError('Linux services (daemons) were not gathered...')
			## Would like to error out, but this depends on the type of daemon
			## service in use on the Linux endpoint; we handle systemd, but if
			## it's init.d or another... this won't find anything.
			runtime.logger.report('Linux services (daemons) were not gathered...')

	elif (data.osType == 'HPUX'):
		# ## Need to create local files on HPUX for software inventory lookup
		# runtime.logger.report(' retrieving swlist-ings...')
		# runtime.logger.setFlag(False)
		# (data.swlistFileDataFile, data.swlistProductDataFile) = create_tempfiles_with_software_inventory(runtime, data.client, data.protocolIp)
		# ## Raise an exception if the files are empty
		# if (data.swlistFileDataFile is None or data.swlistProductDataFile is None):
		# 	raise OSError('HPUX software inventory files were not created; cannot continue.')
		pass

	## Reset shell config and parameter settings to original values
	resetConfigGroupSettings(runtime, savedSettings)

	## end osSpecificSetup
	return


def getRawProcesses(runtime, data):
	"""Just get and filter the processes; don't look for updates here."""
	rawProcessOutput = None
	try:
		## Gather initial process listing from the supported OS types.
		rawProcessOutput = osProcesses.gatherInitialProcesses(runtime, data.client, data.osType)
		if rawProcessOutput is None:
			return
		runtime.logger.report('Process results:\n {rawProcessOutput!r}', rawProcessOutput=rawProcessOutput)
		## Get values and set defaults for the filters, before going through
		## the processes; it's unnecessary overhead to do this per process
		osProcesses.getFilterParameters(runtime, data.osType, data.processFilters)
		## Need to save the processFilters since they are used when looking at
		## a created process hierarchy down in the
		osProcesses.filterInitialProcesses(runtime, data.osType, data.nodeId, rawProcessOutput, data.filteredProcessList, data.excludedProcessList, data.processFilters)
		osProcesses.buildProcessDictionary(runtime, data.nodeId, data.filteredProcessList, data.processDictionary, False, data.osType, True, includeFilteredProcesses=True, excludedProcessList=data.excludedProcessList, processIgnoreList=data.processFilters.get('processIgnoreList'))

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error(' Failure in getRawProcesses: {stacktrace!r}', stacktrace=stacktrace)

	## Abort if no process data returned; error already logged
	if ((rawProcessOutput is None) or (len(data.filteredProcessList) == 0)):
		runtime.logger.report('Failed to discover processes on {osType!r}', osType=data.osType)
		## Prevent calling script from thinking everything is fine
		raise EnvironmentError('Failed to discover processes')

	## end getRawProcesses
	return


def translateIgnoredProcess(runtime, data, thisPid, thisProcessData, thisProcessPpid, thisObjectId):
	"""Convert or translate an ignored process to one that is not ignored.

	If a focus process is in the ignore list (not excluded but ignored) then
	we need to change context of the starting/focus process over to the next
	one up the tree, as if the ignored one never existed.
	"""
	thisProcessName = thisProcessData.get('name')
	if (thisProcessName in data.processFilters.get('processIgnoreList')):
		if thisProcessPpid in data.processDictionary:
			(nextProcessData, nextProcessPpid, nextObjectId) = data.processDictionary[thisProcessPpid]
			runtime.logger.report('Translating ignored process; started with {thisProcessName!r}, shifting focus onto {nextProcessName!r}', thisProcessName=thisProcessName, nextProcessName=nextProcessData.get('name'))
			return(translateIgnoredProcess(runtime, data, thisProcessPpid, nextProcessData, nextProcessPpid, nextObjectId))
		else:
			runtime.logger.report('Found ignored process name {thisProcessName!r}, but no parent found for shifting focus onto... skipping.', thisProcessName=thisProcessName)
			return (None, None, None)

	## end translateIgnoredProcess
	return (thisPid, thisProcessData, thisObjectId)


def shouldWeSkipThisProcess(runtime, processData, data):
	"""Determine if process was created previously or should otherwise be dropped."""
	try:
		## See if any of the processes in the stack are meant to be ignored.
		## Since processTree is a concatenated string, recreate actual list.
		## Note: there may be a more optimal way to do this down the line;
		## I used to do it in walkPIDtree when it used recursion, but after
		## switching that function over to iteration, it needed a new home.
		## Also note that this isn't done in osProcesses; the PF's coming
		## back with the dictionary hold the tree as a string instead of a
		## linked list of processes; if a PPID was filtered out, the child
		## could still hold the parent's name attribute on their processTree
		processName = processData.get('name')
		processPath = processData.get('path_from_process')
		processOwner = processData.get('process_owner')
		processTree = processData.get('process_hierarchy')
		processArgs = processData.get('process_args')
		processTreeAsList = [entry.strip() for entry in processTree.split(',') if entry != '']
		if processTree is None or processTree == 'N/A':
			## Use the processName directly
			if (not osProcesses.needToTrackThisProcess(runtime, data.osType, processName, data.processFilters)):
				runtime.logger.report('  process {processName!r} in tree {processTree!r} was filtered out as requested via processFilterList.', processName=processName, processTree=processTree)
				return (True, None)
		else:
			## Otherwise the processName should be on the processTree
			for thisProcessName in processTreeAsList:
				if (not osProcesses.needToTrackThisProcess(runtime, data.osType, thisProcessName, data.processFilters)):
					runtime.logger.report('  process {processName!r} in tree {processTree!r} was filtered out as requested via processFilterList.', processName=processName, processTree=processTree)
					return (True, None)
		## Compare to previously tracked objects; only continue if new
		for previousProcess in data.previousProcesses:
			(thisId, thisName, thisPath, thisOwner, thisHierarchy, thisArgs) = previousProcess
			if ((processName == thisName) and
				(processPath == thisPath) and
				(processOwner == thisOwner) and
				(processTree == thisHierarchy) and
				(processArgs == thisArgs)):
				runtime.logger.report('  process {processName!r} in tree {processTree!r} was created previously. Using ID {thisId!r}', processName=processName, processTree=processTree, thisId=thisId)
				return (False, thisId)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in shouldWeSkipThisProcess: {stacktrace!r}', stacktrace=stacktrace)

	## end shouldWeSkipThisProcess
	return (False, None)


def needToTrackThisAppComponent(runtime, productName, productSummary, packageId, processTree, processData, filters, filterType):
	"""Determine whether or not to keep & create the SoftwareFingerprint object.

	Some of this is identical to osSoftware and osStartTask filtering, but there
	are a few differences. At the time of writing this, I didn't think it was
	important enough to objectify and merge the code for common paths; it would
	actually take quite a few more functions to do so. Keep in mind that the
	osSoftware library is for creating SoftwarePackage objects and likewise the
	osStartTask library is for creating OsStartTasks objects, whereas this is
	specifically for SoftwareFingerprint objects.
	"""
	## I filter out named processes in 'makePIDtree' to avoid discovery overhead
	## in parsing those undesired processes. Sometimes I know Software, Service,
	## & Libraries to avoid, without knowing correspondingly named processes. So
	## here I enable secondary filtering for an undesired named context. This
	## filter will prevent the creation of SoftwareFingerprints, but I still
	## create the SoftwareSignature group object. Why? Because I want a method
	## of continual refinement for the process filter list. So I create the
	## group objects and mark them as 'enabled' or 'disabled'. That allows data
	## queries to find process names tracked by 'disabled' SoftwareSignatures,
	## and when not also found by 'enabled' SoftwareSignatures - I can refine
	## profiling/heuristics.
	if filters is None:
		return (True, None, None)
	## The application component could have been constructed from start tasks,
	## software, libraries, or other methods. Apply filters accordingly...
	if filterType == 'software':
		runtime.logger.report('   needToTrackThisAppComponent: using software filters')
		softwareFilterFlag = filters.get('softwareFilterFlag', False)
		if (softwareFilterFlag):
			softwareFilterExcludeList = filters.get('softwareFilterExcludeList', [])
			softwareFilterExcludeCompare = filters.get('softwareFilterExcludeCompare', '==')
			for filterExp in softwareFilterExcludeList:
				if (filterExp is None or len(filterExp) <= 0):
					continue
				searchString = filterExp.strip()
				if (utilities.compareFilter(softwareFilterExcludeCompare, searchString, productName)):
					#runtime.logger.report('   needToTrackThisAppComponent: productName {productName!r} with process tree {processTree!r} was filtered out by matchString {searchString!r} in the softwareFilterExcludeList.', productName=productName, processTree=processTree, searchString=searchString)
					return (False, searchString, productName)
				if (utilities.compareFilter(softwareFilterExcludeCompare, searchString, productSummary)):
					#runtime.logger.report('   needToTrackThisAppComponent: productSummary {productSummary!r} with process tree {processTree!r} was filtered out by matchString {searchString!r} in the softwareFilterExcludeList.', productSummary=productSummary, processTree=processTree, searchString=searchString)
					return (False, searchString, productSummary)
				if (utilities.compareFilter(softwareFilterExcludeCompare, searchString, packageId)):
					#runtime.logger.report('   needToTrackThisAppComponent: packageId {packageId!r} with process tree {processTree!r} was filtered out by matchString {searchString!r} in the softwareFilterExcludeList.', packageId=packageId, processTree=processTree, searchString=searchString)
					return (False, searchString, packageId)

	elif filterType == 'starttask':
		runtime.logger.report('   needToTrackThisAppComponent: using start task filters')
		startTaskFilterFlag = filters.get('startTaskFilterFlag', False)
		if (startTaskFilterFlag):
			startTaskFilterByName = filters.get('startTaskFilterByName', True)
			## Figure out why this is flipping: 'Intel(R)' vs 'Intelr' and then
			## set this back to the default; right now I need to hard code:
			#startTaskFilterByDisplayName = filters.get('startTaskFilterByDisplayName', True)
			startTaskFilterByDisplayName = True
			startTaskFilterExcludeCompare = filters.get('startTaskFilterExcludeCompare', '==')
			startTaskFilterExcludeList = filters.get('startTaskFilterExcludeList', [])
			runtime.logger.report('   needToTrackThisAppComponent: go through startTaskFilterExcludeList: {startTaskFilterExcludeList!r}', startTaskFilterExcludeList=startTaskFilterExcludeList)
			for matchContext in startTaskFilterExcludeList:
				try:
					if (matchContext is None or len(matchContext) <= 0):
						continue
					searchString = matchContext.strip()
					#runtime.logger.report('   needToTrackThisAppComponent: searchString {searchString!r} for packageId {packageId!r} and productName {productName!r}', searchString=searchString, packageId=packageId, productName=productName)
					if (startTaskFilterByName and packageId and
						utilities.compareFilter(startTaskFilterExcludeCompare, searchString, packageId)):
						runtime.logger.report('   needToTrackThisAppComponent: packageId {packageId!r} with process tree {processTree!r} was filtered out by matchString {searchString!r} in the startTaskFilterExcludeList.', packageId=packageId, processTree=processTree, searchString=searchString)
						return (False, searchString, packageId)
					if (startTaskFilterByDisplayName and productName and
						utilities.compareFilter(startTaskFilterExcludeCompare, searchString, productName)):
						runtime.logger.report('   needToTrackThisAppComponent: productName {productName!r} with process tree {processTree!r} was filtered out by matchString {searchString!r} in the startTaskFilterExcludeList.', productName=productName, processTree=processTree, searchString=searchString)
						return (False, searchString, productName)
				except:
					stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					runtime.logger.error('Exception in inFilteredStartTaskList: on searchString {searchString!r}:  {stacktrace!r}', searchString=searchString, stacktrace=stacktrace)

			## Next check the path-based exclude list
			startTaskFilterPathExcludeList = filters.get('startTaskFilterPathExcludeList', [])
			if (len(startTaskFilterPathExcludeList) >= 0):
				runtime.logger.report('   needToTrackThisAppComponent: go through startTaskFilterPathExcludeList: {startTaskFilterPathExcludeList!r}', startTaskFilterPathExcludeList=startTaskFilterPathExcludeList)
				startTaskFilterPathExcludeCompare = filters.get('startTaskFilterPathExcludeCompare', 'regex')
				for pathAttribute in ['path_from_process', 'path_from_analysis', 'path_from_filesystem']:
					processPath = processData.get(pathAttribute)
					if processPath is None or processPath == 'N/A':
						continue
					for matchContext in startTaskFilterPathExcludeList:
						try:
							if (matchContext is None or len(matchContext) <= 0):
								continue
							searchString = matchContext.strip()
							if (utilities.compareFilter(startTaskFilterPathExcludeCompare, searchString, processPath)):
								runtime.logger.report('   needToTrackThisAppComponent: processPath {processPath!r} with process tree {processTree!r} was filtered out by matchString {searchString!r} in the startTaskFilterPathExcludeList.', processPath=processPath, processTree=processTree, searchString=searchString)
								return (False, searchString, processPath)
						except:
							stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
							runtime.logger.error('Exception in inFilteredStartTaskList: on searchString {searchString!r}:  {stacktrace!r}', searchString=searchString, stacktrace=stacktrace)

	else:
		runtime.logger.report('   needToTrackThisAppComponent: unexpected filterType: {filterType!r}', filterType=filterType)

	## end needToTrackThisAppComponent
	return (True, None, None)


def createObjects(runtime, osType, nodeId, softwareFingerprints, processData, targetProcessPid, processId, pidTrackingList, processDictionary, processShortName, productName, packageId, productVersion, productSummary, productCompany, dataSource, processTree, filters=None, filterType='software'):
	"""Create all desired signature and fingerprint objects in this flow.

	This represents a software instance running on a Node (OS instance). The
	standard operation is to create a processFingerprint for the 'interesting'
	process. 'Vocal' App Components does this for processes using the network,
	and 'Base' App Components does this for the lowest child processes. And
	the ProcessFingerprint is linked to the SoftwareFingerprint when qualified.

	Unique Constraints for SoftwareFingerprint objects:
	  container
	  name
	  software_info
	  software_version
	"""
	wasAddedOntoResults = False
	softwareFingerprintId = None
	## Set the attributes, but don't yet add to the results
	softwareFingerprintData = {}
	softwareFingerprintId = None
	createSoftwareFingerprint(softwareFingerprintData, productName, packageId, productVersion, productSummary, productCompany, dataSource)
	## Override local variables after createSoftwareFingerprint, for less typing
	productName = softwareFingerprintData.get('name')
	productSummary = softwareFingerprintData.get('software_info')
	packageId = softwareFingerprintData.get('software_id')

	## Act according to defined software/startTask filters on this OS instance
	(trackThisComponent, searchString, matchString) = needToTrackThisAppComponent(runtime, productName, productSummary, packageId, processTree, processData, filters, filterType)
	## Gather the originating process content
	(processFingerprintData, ppid, processFingerprintId) = processDictionary[int(targetProcessPid)]
	if not trackThisComponent:
		processFingerprintData['is_filtered_out'] = True
		if processFingerprintId is not None:
			runtime.results.updateObject(processFingerprintId, is_filtered_out=True)

	(processFingerprintId, pfAlreadyCreated) = runtime.results.addObject('ProcessFingerprint', **processFingerprintData)
	if pfAlreadyCreated:
		newAttrs = runtime.results.getObject(processFingerprintId).get('data', {})
		## Provide debug visibility to what will be merged objects
		runtime.logger.report('   createObjects: already created process {name!r}:', name=processShortName)
		runtime.logger.report('      Prev attrs: {prev!r}', prev=processFingerprintData)
		runtime.logger.report('       New attrs: {newAttrs!r}', newAttrs=newAttrs)

	psAlreadyCreated = False
	processSignatureId = None
	if not pfAlreadyCreated:
		## Won't get here if the process was already created in osProcesses
		runtime.results.addLink('Enclosed', nodeId, processFingerprintId)
	## Create the ProcessSignature
	(processSignatureId, psAlreadyCreated) = createProcessSignature(runtime, nodeId, processShortName, str(processTree))
	if not psAlreadyCreated:
		## Link the ProcessSignature to the ProcessFingerprint
		runtime.results.addLink('Contain', processSignatureId, processFingerprintId)
		runtime.logger.report('   createObjects: created processSignature {processShortName!r}:  {processTree!r}', processShortName=processShortName, processTree=processTree)

		## Create the SoftwareSignature
		(softwareSignatureId, ssAlreadyCreated) = createSoftwareSignature(runtime, productName, productSummary, osType, trackThisComponent, matchString, searchString)
		if (not (ssAlreadyCreated and psAlreadyCreated)):
			## Link the SoftwareSignature to the ProcessSignature
			runtime.results.addLink('Usage', softwareSignatureId, processSignatureId)
		## Create the SoftwareFingerprint if it's not filtered out
		if (trackThisComponent):
			## Create the Software Fingerprint CI
			#(sfAlreadyCreated, softwareFingerprintId) = utilities.addObjectIfNotExists(runtime, 'SoftwareFingerprint', **softwareFingerprintData)
			(softwareFingerprintId, sfAlreadyCreated) = runtime.results.addObject('SoftwareFingerprint', **softwareFingerprintData)
			if not sfAlreadyCreated:
				runtime.results.addLink('Enclosed', nodeId, softwareFingerprintId)
				wasAddedOntoResults = True
				runtime.logger.report('   createObjects: created softwareFingerprint {productName!r}:  {softwareFingerprintData!r}', productName=productName, softwareFingerprintData=softwareFingerprintData)
			if (not sfAlreadyCreated or not pfAlreadyCreated):
				## Link the Software Fingerprint to the Process Fingerprint
				runtime.results.addLink('Usage', softwareFingerprintId, processFingerprintId)
				runtime.logger.report('   createObjects: linked softwareFingerprint {productName!r} to process {processShortName!r}', productName=productName, processShortName=processShortName)
			if (not ssAlreadyCreated or not sfAlreadyCreated):
				## Link the Software Signature to the Software Fingerprint
				runtime.results.addLink('Contain', softwareSignatureId, softwareFingerprintId)
				runtime.logger.report('   createObjects: linked softwareSignature to softwareFingerprint for {productName!r}', productName=productName)
	elif (trackThisComponent):
		## Get a handle on the previously created SoftwareFingerprint object
		(softwareFingerprintId, sfAlreadyCreated) = runtime.results.addObject('SoftwareFingerprint', **softwareFingerprintData)
		if not sfAlreadyCreated:
			runtime.results.addLink('Enclosed', nodeId, softwareFingerprintId)

	## Add it to the list being tracked
	softwareFingerprints.append((processData.get('name'), processData.get('path_from_process'), processData.get('path_from_analysis'), processData.get('path_from_filesystem'), softwareFingerprintId, softwareFingerprintData, wasAddedOntoResults))

	## end createObjects
	return (processFingerprintId, softwareFingerprintId, trackThisComponent)


def createSoftwareFingerprint(softwareFingerprintData, productName, packageId, productVersion, productSummary, productCompany, dataSource):
	"""Create a SoftwareFingerprint object.

	This represents a software instance running on a Node (OS instance). The
	standard operation is to create a processFingerprint for the 'interesting'
	process. 'Vocal' App Components does this for processes using the network,
	and 'Base' App Components does this for the lowest child processes. And
	the ProcessFingerprint is linked to the SoftwareFingerprint when qualified.

	Unique Constraints for SoftwareFingerprint objects:
	  container
	  name
	  software_info
	  software_version
	"""
	## Required attributes
	setRequiredAttribute(softwareFingerprintData, 'name', productName)
	setRequiredAttribute(softwareFingerprintData, 'software_version', productVersion, 256)
	setRequiredAttribute(softwareFingerprintData, 'software_info', productSummary, 256)
	## Optional attributes
	setOptionalAttribute(softwareFingerprintData, 'software_id', packageId, 64)
	setOptionalAttribute(softwareFingerprintData, 'vendor', productCompany, 64)
	setOptionalAttribute(softwareFingerprintData, 'software_source', dataSource, 32)

	## end createSoftwareFingerprint
	return softwareFingerprintData


def createSoftwareSignature(runtime, productName, productSummary, osType, trackThisComponent, matchString, searchString):
	"""Create a SoftwareSignature object.

	This is a collection object that groups all similar instances of a
	particular software across the enterprise.

	Unique Constraints for SoftwareSignature objects:
	  name
	  software_info
	  os_type
	"""
	## Set the attributes
	softwareSignatureData = {}
	setRequiredAttribute(softwareSignatureData, 'name', productName)
	setRequiredAttribute(softwareSignatureData, 'software_info', productSummary, 256)
	setRequiredAttribute(softwareSignatureData, 'os_type', osType, 8)
	## Mark whether or not it's active, using the 'notes' field
	if (trackThisComponent):
		setOptionalAttribute(softwareSignatureData, 'notes', 'Enabled')
	else:
		#setOptionalAttribute(softwareSignatureData, 'notes', 'Disabled: value [{}] matched filter [{}]'.format(matchString, searchString), 512)
		setOptionalAttribute(softwareSignatureData, 'notes', 'Disabled: matched filter [{}]'.format(searchString), 512)

	## end createSoftwareSignature
	return (runtime.results.addObject('SoftwareSignature', **softwareSignatureData))


def createProcessSignature(runtime, nodeId, processName, processHierarchy):
	"""Create a ProcessSignature object.

	This is a collection object that groups all similar instances of a
	particular process across the enterprise.

	Unique Constraints for ProcessSignature objects:
	  name
	  process_hierarchy
	"""
	## Set the attributes
	processSignatureData = {}
	setRequiredAttribute(processSignatureData, 'name', processName, 256)
	setRequiredAttribute(processSignatureData, 'process_hierarchy', processHierarchy, 512)

	## end createProcessSignature
	return (runtime.results.addObject('ProcessSignature', **processSignatureData))


def startTaskForProcess(runtime, data, processId, pidTrackingList, processName, processData, processTree, startingProcessData=None, startingProcessId=None):
	"""Look for a start task (windows service, unix daemon) for this process."""
	#if (data.osType == 'Windows' and not runtime.parameters.get('onlyMapProcessesToNetworkUsage', False)):
	if (data.osType == 'Windows'):
		return startTaskForProcessWindows(runtime, data, processId, pidTrackingList, processName, processData, processTree, startingProcessData, startingProcessId)
	elif (data.osType == 'Linux'):
		return startTaskForProcessLinux(runtime, data, processId, pidTrackingList, processName, processData, processTree, startingProcessData, startingProcessId)
	else:
		raise NotImplementedError()
	## end startTaskForProcess


def findStartTask(runtime, data, processId, processName, processData, processTree):
	"""Walk through this process stack looking for an associated OS start task."""
	nextPID = processId
	nextData = processData
	nextName = processName
	pidTrackingList = []
	spaceBuffer = '  '

	## Don't use this method if we didn't gather any start tasks
	if (len(data.startTaskDictionary.keys()) <= 0):
		runtime.logger.report(spaceBuffer + 'Skipping method 1 analysis since startTaskDictionary is empty')
		return (None, None, True)

	## Break out of loop if this is the system/init process
	while (nextPID is not None and int(nextPID) in data.processDictionary.keys()):
		try:
			runtime.logger.report(spaceBuffer + 'Inside findStartTask on process {processName!r} with PID {pid!r}', processName=nextName, pid=nextPID)
			## Code block to test for a stopping point
			if (not osProcesses.isValidProcessAndIsNotTopOsProcess(runtime, nextPID, nextName, data.processDictionary, pidTrackingList, data.osType)):
				## Break out of loop if this is the system/init process or if
				## ppid==pid, which as crazy as that sounds - yes, it actually
				## happens... so we need to avoid creating any infinite loops
				break

			## Pursuing deeper analysis
			(processFingerprintId, softwareFingerprintId, trackThisComponent) = startTaskForProcess(runtime, data, nextPID, pidTrackingList, nextName, nextData, processTree, processData, processId)
			## If found, success; send the appComponent back.
			if (processFingerprintId != None):
				return (processFingerprintId, softwareFingerprintId, trackThisComponent)
			runtime.logger.report(spaceBuffer + 'No {osType!r} daemon found for PID {pid!r}; continue up tree', osType=data.osType, pid=processId)

			## Save variables for Child process references in this iteration
			prevName = nextName
			prevPID = nextPID

			## We didn't find ownership for this process; turn our
			## attention to the parent process and continue up the tree
			(prevData, nextPID, prevId) = data.processDictionary[prevPID]
			prevName = prevData.get('name')

			## Help the log messages... that's all
			if (int(nextPID) in data.processDictionary.keys()):
				(nextData, nextPPID, nextId) = data.processDictionary[nextPID]
				nextName = nextData.get('name')
				runtime.logger.report(spaceBuffer + 'currently at process {processName!r} pid:{pid!r} --> pursuing parent process {parentProcessName!r} ppid:{ppid!r}', processName=prevName, pid=prevPID, parentProcessName=nextName, ppid=nextPID)
			else:
				runtime.logger.report(spaceBuffer + 'currently at process {processName!r} pid:{pid!r} --> pursuing parent process (Unknown ppid:{ppid!r}', processName=prevName, pid=prevPID, ppid=nextPID)
			spaceBuffer = spaceBuffer + ' '

			## Iterate/loop to the next parent process...

		except:
			## Valid exceptions when we hit processes without parents
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in findStartTask: {stacktrace!r}', stacktrace=stacktrace)
			nextPID = None

	## end findStartTask
	return (None, None, True)


def mapThisProcessFingerprintToPrevSoftwareFingerprint(runtime, wasAddedOntoResults, nodeId, softwareFingerprintId, softwareFingerprintName, processFingerprintData):
	"""If the Software Fingerprint was found previously, map the process."""
	## Currently called from findPreviousApplicationComponent; the process
	## fingerprints and corresponding links to the previously matching software
	## still need to be created after identifying that there was a match

	## Create the ProcessFingerprint (constructed in osProcesses)
	runtime.logger.report('  mapThisProcessFingerprintToPrevSoftwareFingerprint: created process {processName!r} with attributes: {processFingerprintData!r}', processName=processFingerprintData.get('name'), processFingerprintData=processFingerprintData)
	(processFingerprintId, pfAlreadyCreated) = runtime.results.addObject('ProcessFingerprint', **processFingerprintData)
	if not pfAlreadyCreated:
		runtime.results.addLink('Enclosed', nodeId, processFingerprintId)

		## We might have identified the App component CI as needing to be
		## filtered out, and so don't just blindly create the objects
		if (wasAddedOntoResults):
			## Link the SoftwareFingerprint to the ProcessFingerprint
			runtime.results.addLink('Usage', softwareFingerprintId, processFingerprintId)
			runtime.logger.report('  mapThisProcessFingerprintToPrevSoftwareFingerprint: linked softwareFingerprint {softwareFingerprintName!r} to process: {processName!r}', softwareFingerprintName=softwareFingerprintName, processName=processFingerprintData.get('name'))

	## end mapThisProcessFingerprintToPrevSoftwareFingerprint
	return processFingerprintId


def findPreviousApplicationComponent(runtime, data, targetProcessData):
	"""Determine if the SoftwareFingerprint was found previously."""
	## The SoftwareFingerprint object is considered equivelant if the following
	## attributes matched: name, info, version. But we need more granular
	## comparisons, and so look at the process data from that process. The
	## "Process Fingerprint" is considered equivelant for the related Software
	## Fingerprint when all three (3) process paths and the process name are
	## the same.  While 'user' is a primary key on the Process Fingerprint,
	## it's not needed for matching back to the Software Fingerprint.
	softwareFingerprintId = None
	processFingerprintId = None
	found = False

	## Get the attributes from this process fingerprint to use for comparison
	targetProcessName = targetProcessData.get('name')
	targetPathFromProcess = targetProcessData.get('path_from_process')
	targetPathFromAnalysis = targetProcessData.get('path_from_analysis')
	targetPathFromFilesystem = targetProcessData.get('path_from_filesystem')
	runtime.logger.report('  LOOKING TO MATCH processName {targetProcessName!r} with paths: {targetPathFromProcess!r} {targetPathFromAnalysis!r} {targetPathFromFilesystem!r}', targetProcessName=targetProcessName, targetPathFromProcess=targetPathFromProcess, targetPathFromAnalysis=targetPathFromAnalysis, targetPathFromFilesystem=targetPathFromFilesystem)

	## Go through softwareFingerprints to see if this process fingerprint
	## was already investigated for owning software in a previous iteration.
	for entry in data.softwareFingerprints:
		try:
			(processName, pathFromProcess, pathFromAnalysis, pathFromFilesystem, softwareFingerprintId, softwareFingerprintData, wasAddedOntoResults) = entry
			if ((processName == targetProcessName) and
				(pathFromProcess == targetPathFromProcess) and
				(pathFromAnalysis == targetPathFromAnalysis) and
				(pathFromFilesystem == targetPathFromFilesystem)):

				softwareFingerprintName = softwareFingerprintData.get('name')
				runtime.logger.report('  FOUND MATCHING previous Software Fingerprint {softwareFingerprintName!r} with paths: {targetPathFromProcess!r} {targetPathFromAnalysis!r} {targetPathFromFilesystem!r}', softwareFingerprintName=softwareFingerprintName, targetPathFromProcess=targetPathFromProcess, targetPathFromAnalysis=targetPathFromAnalysis, targetPathFromFilesystem=targetPathFromFilesystem)
				## Software Fingerprint was found previously; map the process
				processFingerprintId = mapThisProcessFingerprintToPrevSoftwareFingerprint(runtime, wasAddedOntoResults, data.nodeId, softwareFingerprintId, softwareFingerprintName, targetProcessData)
				found = True
				break
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in findPreviousApplicationComponent: {stacktrace!r}', stacktrace=stacktrace)

	if not found:
		softwareFingerprintId = None
		runtime.logger.report('  No {osType!r} Software Fingerprint previously found for processName {targetProcessName!r} with paths: {targetPathFromProcess!r} {targetPathFromAnalysis!r} {targetPathFromFilesystem!r}', osType=data.osType, targetProcessName=targetProcessName, targetPathFromProcess=targetPathFromProcess, targetPathFromAnalysis=targetPathFromAnalysis, targetPathFromFilesystem=targetPathFromFilesystem)

	## end findPreviousApplicationComponent
	return (processFingerprintId, softwareFingerprintId)


def mapApplicationComponentsL1(runtime, data, targetProcessId, processId, pidTrackingList, processName, processData, processTree):
	"""Branch off to the OS specific implementation for L1 analysis."""
	softwareFingerprintId = None
	processFingerprintId = None
	trackThisComponent = True
	if (data.osType == 'Windows'):
		(processFingerprintId, softwareFingerprintId, trackThisComponent) = queryLibrariesForProcessWindows(runtime, data, targetProcessId, processId, pidTrackingList, processName, processData, processTree)
	elif (data.osType == 'Linux'):
		#(processFingerprintId, softwareFingerprintId) = Linux_Query_Package_Manager_For_Process(runtime, data, processId, pidTrackingList, processName, processData, processTree)
		(processFingerprintId, softwareFingerprintId, trackThisComponent) = queryPackageManagerForProcessLinux(runtime, data, targetProcessId, processId, pidTrackingList, processName, processData, processTree)
	elif (data.osType == 'HPUX'):
		#(processFingerprintId, softwareFingerprintId) = HPUX_Query_Package_Manager_For_Process(runtime, data, processId, pidTrackingList, processName, processData, processTree)
		raise NotImplementedError('Software solution on HPUX was not (re)implemented')
	elif (data.osType == 'AIX'):
		#(processFingerprintId, softwareFingerprintId) = AIX_Query_Package_Manager_For_Process(runtime, data, processId, pidTrackingList, processName, processData, processTree)
		raise NotImplementedError('Software solution on AIX was not (re)implemented')
	elif (data.osType == 'Solaris'):
		#(processFingerprintId, softwareFingerprintId) = Solaris_Query_Package_Manager_For_Process(runtime, data, processId, pidTrackingList, processName, processData, processTree)
		raise NotImplementedError('Software solution on Solaris was not (re)implemented')

	## end mapApplicationComponentsL1
	return (processFingerprintId, softwareFingerprintId, trackThisComponent)


def findNewApplicationComponentL1(runtime, data, processId, processName, processData, processTree):
	"""Loop through process stack, pursuing L1 analysis."""
	## Save a pointer to the actual process, since we will be iterating through
	targetProcessId = processId
	nextPID = processId
	nextData = processData
	nextName = processName
	pidTrackingList = []
	spaceBuffer = '  '

	## Break out of loop if this is the system/init process
	while (nextPID is not None and int(nextPID) in data.processDictionary.keys()):
		try:
			runtime.logger.report(spaceBuffer + 'Inside findNewApplicationComponentL1 on process {nextName!r} with PID {nextPID!r}', nextName=nextName, nextPID=nextPID)
			## Code block to test for a stopping point
			if (not osProcesses.isValidProcessAndIsNotTopOsProcess(runtime, nextPID, nextName, data.processDictionary, pidTrackingList, data.osType)):
				## Break out of loop if this is the system/init process
				break

			## Pursuing deeper analysis
			(processFingerprintId, softwareFingerprintId, trackThisComponent) = mapApplicationComponentsL1(runtime, data, targetProcessId, nextPID, pidTrackingList, nextName, nextData, processTree)
			## If found, success; send the appComponent back.
			if (softwareFingerprintId != None or not trackThisComponent):
				return (processFingerprintId, softwareFingerprintId, trackThisComponent)
			runtime.logger.report(spaceBuffer + 'no {osType!r} App Component found for process {nextName!r} in tree {processTree!r} ... continue up tree', osType=data.osType, nextName=nextName, processTree=processTree)

			## Save variables for Child process references in this iteration
			prevName = nextName
			prevPID = nextPID

			## We didn't find ownership for this process; turn attention to
			## the parent process and continue recursively up the tree
			(prevData, nextPID, prevId) = data.processDictionary[prevPID]
			prevName = prevData.get('name')

			if (int(nextPID) in data.processDictionary.keys()):
				## Get a handle on the next process up the tree (parent process)
				(nextData, nextPPID, nextId) = data.processDictionary[nextPID]

				## Qualify and update this process of interest, before analysis
				runtime.logger.report(spaceBuffer + '==>running  updateThisProcess for {nextName!r}. Old data: {nextData}', nextName=nextData.get('name'), nextData=nextData)
				runtime.logger.setFlag(False)
				osProcesses.updateThisProcess(runtime, nextData, data.client, data.osType, nextPID)
				runtime.logger.setFlag(data.savedPrintDebug)
				runtime.logger.report(spaceBuffer + '==>finished updateThisProcess for {nextName!r}. New data: {nextData}', nextName=nextData.get('name'), nextData=nextData)

				nextName = nextData.get('name')
				runtime.logger.report(spaceBuffer + 'currently at process {prevName!r} (pid: {prevPID!r}) --> pursuing parent process {nextName!r} (pid: {nextPID!r})', prevName=prevName, prevPID=prevPID, nextName=nextName, nextPID=nextPID)
			else:
				runtime.logger.report(spaceBuffer + 'currently at process {prevName!r} (pid: {prevPID!r}) --> pursuing parent process Unknown (pid: {nextPID!r})', prevName=prevName, prevPID=prevPID, nextPID=nextPID)
			spaceBuffer = utilities.concatenate(spaceBuffer, ' ')

			## Iterate/loop to the next parent process...

		except:
			## Valid exceptions when we hit processes without parents; using a
			## try/except block instead of comparing all values individually
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in findNewApplicationComponentL1: {stacktrace!r}', stacktrace=stacktrace)
			nextPID = None

	## end findNewApplicationComponentL1
	return (None, None, True)


def mapApplicationComponentsL2(runtime, data, processId, pidTrackingList, processName, processData, processTree):
	"""Branch off to the OS specific implementation of L2 analysis."""
	processFingerprintId = None
	softwareFingerprintId = None
	trackThisComponent = True
	if (data.osType == 'Windows'):
		(processFingerprintId, softwareFingerprintId, trackThisComponent) = querySoftwareForProcessWindows(runtime, data, processId, pidTrackingList, processName, processData, processTree)
	else:
		## Currently only have a second method of deep analysis for Windows,
		## but if/when I have more... they will go here, following the same
		## format found in the 'mapApplicationComponentsL1' function.
		pass

	## end mapApplicationComponentsL2
	return (processFingerprintId, softwareFingerprintId, trackThisComponent)


def findNewApplicationComponentL2(runtime, data, processId, processName, processData, processTree):
	"""Loop through process stack, pursuing L2 analysis."""
	## I currently only have a second method of analysis for Windows
	if (len(data.startTaskDictionary.keys()) <= 0):
		runtime.logger.report('  Skipping method 4 analysis, since it is only enabled at this time on Windows and this OS type is {osType!r}', osType=data.osType)
		return (None, None, True)
	nextPID = processId
	nextData = processData
	nextName = processName
	pidTrackingList = []
	spaceBuffer = '  '

	## Break out of loop if this is the system/init process
	while (nextPID is not None and int(nextPID) in data.processDictionary.keys()):
		try:
			runtime.logger.report(spaceBuffer + 'Inside findNewApplicationComponentL2 on process {nextName!r} with PID {nextPID!r}', nextName=nextName, nextPID=nextPID)
			## Code block to test for a stopping point
			if (not osProcesses.isValidProcessAndIsNotTopOsProcess(runtime, nextPID, nextName, data.processDictionary, pidTrackingList, data.osType)):
				## Break out of loop if this is the system/init process
				break

			## Pursuing deeper analysis
			(processFingerprintId, softwareFingerprintId, trackThisComponent) = mapApplicationComponentsL2(runtime, data, nextPID, pidTrackingList, nextName, nextData, processTree)
			## If found, success; send the appComponent back.
			if (softwareFingerprintId != None):
				return (processFingerprintId, softwareFingerprintId, trackThisComponent)
			runtime.logger.report(spaceBuffer + 'no {osType!r} App Component found for process {nextName!r} in tree {processTree!r} ... continue up tree', osType=data.osType, nextName=nextName, processTree=processTree)

			## Save variables for Child process references in this iteration
			prevName = nextName
			prevPID = nextPID

			## We didn't find ownership for this process; turn attention to
			## the parent process and continue recursively up the tree
			(prevData, nextPID, prevId) = data.processDictionary[prevPID]
			prevName = prevData.get('name')

			if (int(nextPID) in data.processDictionary.keys()):
				## Get a handle on the next process up the tree (parent process)
				(nextData, nextPPID, nextId) = data.processDictionary[nextPID]
				nextName = nextData.get('name')
				runtime.logger.report(spaceBuffer + 'currently at process {prevName!r} (pid: {prevPID!r}) --> pursuing parent process {nextName!r} (pid: {nextPID!r})', prevName=prevName, prevPID=prevPID, nextName=nextName, nextPID=nextPID)
			else:
				runtime.logger.report(spaceBuffer + 'currently at process {prevName!r} (pid: {prevPID!r}) --> pursuing parent process Unknown (pid: {nextPID!r})', prevName=prevName, prevPID=prevPID, nextPID=nextPID)
			spaceBuffer = utilities.concatenate(spaceBuffer, ' ')

			## Iterate/loop to the next parent process...

		except:
			## Valid exceptions when we hit processes without parents; using a
			## try/except block instead of comparing all values
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in findNewApplicationComponentL2: {stacktrace!r}', stacktrace=stacktrace)
			nextPID = None

	## end findNewApplicationComponentL2
	return (None, None, True)


def stubUnknownApplicationComponent(runtime, data, processId, processName, processData, processTree):
	"""Create an 'Unknown' object to which we can connect the process.

	If we get here, it means the code was not able to find a software package,
	service, library, etc - across any process in the tree. Creating this anchor
	object allows mapping of relevant processes that were not qualified.

	I've used this in the past for reporting on components I have not been able
	to find more information on, for continual improvement over time. I'm not
	sure if I'll leave this for standard job invocations in the OCP platform...
	"""
	return createObjects(runtime, data.osType, data.nodeId, data.softwareFingerprints, processData, processId, processId, [], data.processDictionary, processName, None, 'Unknown', None, None, None, data.osType, processTree)

###############################################################################
############################  END GENERAL SECTION  ############################
###############################################################################


###############################################################################
###########################  BEGIN WINDOWS SECTION  ###########################
###############################################################################

def queryProcessForOwnershipWindows(runtime, data, fqProcessName):
	"""Attempt to retrieve data from libraries for a single path on a process.

	The lookup on Windows is equivalent to interactively right clicking on a
	file, selecting Properties, and then looking at the Details pane. This
	method is Windows specific; similar methods may be found and used with the
	linux/unix variants for binaries using more robust formats (e.g. ELF).
	"""
	version = None
	name = None
	info = None
	identifier = None
	company = None
	try:
		if (data.fqProcessTracking and fqProcessName in data.fqProcessTracking):
			## Only call this once per executable, even if multiple are running
			(name, version, identifier, info, company) = data.fqProcessTracking[fqProcessName]
			runtime.logger.report('   getProcessOwnership previous result for {fqProcessName!r}:  {result!r}', fqProcessName=fqProcessName, result=data.fqProcessTracking[fqProcessName])
		elif (data.fqProcessFails and fqProcessName in data.fqProcessFails):
			## Skip if we've tried this before and it failed
			pass
		else:
			result = None
			try:
				#query = concatenate('powershell "Invoke-Command -ScriptBlock {(Get-ItemProperty \'', fqProcessName,'\').VersionInfo |fl | out-string -width 16000}" < NUL')
				query = utilities.concatenate('(Get-ItemProperty "', fqProcessName,'").VersionInfo | fl')
				(result, stdError, hitProblem) = data.client.run(query, 5)
				runtime.logger.report('   getProcessOwnership result for {fqProcessName!r}:  {result!r}', fqProcessName=fqProcessName, result=result)
			except:
				## Not all unicode characters are able to be printed to debug;
				## and that may be the reason for the error, so try to continue
				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				runtime.logger.error('Exception in queryProcessForOwnershipWindows: {stacktrace!r}', stacktrace=stacktrace)
			if (result is not None and len(result) > 0 and (not re.search('Cannot find path', result, re.I))):
				## Parse the response from the query; samples follow:
				## ===========================================================
				## OriginalFilename : javaws.exe
				## FileDescription  : Java(TM) Web Start Launcher
				## ProductName      : Java(TM) Platform SE 7 U45
				## CompanyName      : Oracle Corporation
				## FileName         : C:\Program Files (x86)\Java\jre7\bin\javaws.exe
				## FileVersion      : 10.45.2.18
				## ProductVersion   : 7.0.450.18
				##
				## OriginalFilename : ApacheMonitor.exe
				## FileDescription  : Apache HTTP Server Monitor
				## ProductName      : Apache HTTP Server
				## CompanyName      : Apache Software Foundation
				## FileName         : C:\Program Files\Apache Software Foundation\Apache2.2\bin\ApacheMonitor.exe
				## FileVersion      : 2.2.22
				## ProductVersion   : 2.2.22
				##
				## OriginalFilename :
				## FileDescription  :
				## ProductName      :
				## Comments         :
				## CompanyName      :
				## FileName         : C:\WINDOWS\System32\drivers\etc\xCmdSvc.exe
				## FileVersion      :
				## ProductVersion   :
				##
				## OriginalFilename : HPNetworkCommunicator.exe
				## FileDescription  : HPNetworkCommunicator
				## ProductName      : HP Digital Imaging
				## CompanyName      : Hewlett-Packard Co.
				## FileName         : C:\Program Files\HP\HP Photosmart 7520 series\Bin\HPNetworkCommunicator.exe
				## FileVersion      : 28.0.1315.0
				## ProductVersion   : 028.000.1315.000
				## ===========================================================
				lines = result.split('\n')
				for line in lines:
					try:
						m1 = re.search('InternalName\s*:\s*(\S.*)\s*$', line, re.I)
						m2 = re.search('OriginalFilename\s*:\s*(\S.*)\s*$', line, re.I)
						m3 = re.search('FileVersion\s*:\s*(\S.*)\s*$', line, re.I)
						m4 = re.search('FileDescription\s*:\s*(\S.*)\s*$', line, re.I)
						m5 = re.search('Product\s*:\s*(\S.*)\s*$', line, re.I)
						m6 = re.search('ProductName\s*:\s*(\S.*)\s*$', line, re.I)
						m7 = re.search('ProductVersion\s*:\s*(\S.*)\s*$', line, re.I)
						m8 = re.search('CompanyName\s*:\s*(\S.*)\s*$', line, re.I)
						## Could also use 'FileName' for resolution without
						## the additional call for 8dot3 name resolution...
						## but the empty entries (without info) have FileName
						## and so using this entry could cause a false positive.
						if m1:
							name = m1.group(1)
						elif (m2 and name is None):
							## Prefer Internal name over Original file name
							name = m2.group(1)
						elif (m3 and version is None):
							## Prefer the Product version over File version
							version = m3.group(1)
						elif m4:
							info = m4.group(1)
						elif m5:
							identifier = m5.group(1)
						elif (m6 and (identifier is None or re.search('Microsoft.*Windows.*Operating.*System', identifier, re.I))):
							## Prefer Product over Product Name
							identifier = m6.group(1)
						elif m7:
							version = m7.group(1)
						elif m8:
							company = m8.group(1)

					except:
						stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
						runtime.logger.error('Exception in queryProcessForOwnershipWindows: {stacktrace!r}', stacktrace=stacktrace)

				## The 'Microsoftr Windowsr Operating System' label is useless;
				## so if we got it... swap the identifier and info fields
				if identifier is not None and re.search('Microsoft.*Windows.*Operating.*System', identifier, re.I) and info is not None:
					tmp = identifier
					identifier = info
					info = tmp

				## Track so we don't issue multiple lookups for the same item
				data.fqProcessTracking[fqProcessName] = (name, version, identifier, info, company)
				runtime.logger.report('   getProcessOwnership tracked details for {fqProcessName!r}: {details!r}', fqProcessName=fqProcessName, details=data.fqProcessTracking[fqProcessName] )

			## If a particular process failed to resolve before, and we have a
			## large number of instances (e.g. 1000) of it, then we certainly
			## do not want to check the same thing 1000 times.  This was found
			## happening to a DNS server when the account didn't have access
			## to look at files inside the system32 directory.  So I need to
			## keep track of the failing processes as well, to avoid retries.
			else:
				runtime.logger.report('   getProcessOwnership not able to find details for {fqProcessName!r}', fqProcessName=fqProcessName)
				data.fqProcessFails[fqProcessName] = 1
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in queryProcessForOwnershipWindows: {stacktrace!r}', stacktrace=stacktrace)

	## end queryProcessForOwnershipWindows
	return (name, version, identifier, info, company)


def queryLibrariesForProcessWindows(runtime, data, targetProcessId, processId, pidTrackingList, processName, processData, processTree):
	"""Attempt to retrieve data from libraries for all paths on this process."""
	runtime.logger.report('  Inside queryLibrariesForProcessWindows on process {processName!r} with PID {processId!r}', processName=processName, processId=processId)
	for pathAttribute in ['path_from_analysis', 'path_from_filesystem', 'path_from_process']:
		try:
			processPath = processData.get(pathAttribute)
			if processPath is None or processPath == 'N/A' or processPath == 'null' or processPath == 'None' or processPath == 'Unknown':
				continue
			## Attempt to retrieve process file data from OS Libraries. Prefer
			## this method over the next path-matching method (better accuracy)
			runtime.logger.report('  Querying OS libraries for process {processPath!r}', processPath=processPath)
			dataSource = 'Windows Libraries'
			(name, version, identifier, info, company) = queryProcessForOwnershipWindows(runtime, data, processPath)
			if (version):
				runtime.logger.report('   OS library version   : {version!r}', version=version)
			if (info):
				runtime.logger.report('   OS library info      : {info!r}', info=info)
			if (identifier):
				runtime.logger.report('   OS library identifier: {identifier!r}', identifier=identifier)
			if (company):
				runtime.logger.report('   OS library company   : {company!r}', company=company)

			if (version or info or identifier or company):
				(processFingerprintId, softwareFingerprintId, trackThisComponent) = createObjects(runtime, data.osType, data.nodeId, data.softwareFingerprints, processData, targetProcessId, processId, pidTrackingList, data.processDictionary, processName, identifier, None, version, info, company, dataSource, processTree, filters=data.softwareFilters)
				runtime.logger.report('  Created SoftwareFingerprint for process {processName!r} and softwareFingerprintId: {softwareFingerprintId!r}', processName=processName, softwareFingerprintId=softwareFingerprintId)
				return (processFingerprintId, softwareFingerprintId, trackThisComponent)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in queryLibrariesForProcessWindows: {stacktrace!r}', stacktrace=stacktrace)

	## end queryLibrariesForProcessWindows
	return (None, None, True)


def querySoftwareForProcessWindows(runtime, data, processId, pidTrackingList, processName, processData, processTree):
	"""Attempt to retrieve data from installed Products/Software entries.

	This method is less reliable, due to multiple results for the same vendor.
	For example, all Microsoft office products can match the same base install
	directory as the first result returned from the uninstall Registry location
	(e.g. 'Microsoft Office Word MUI'), even if what we're really looking at is
	'Excel' or 'Live Meeting'. But when you aren't working with a suite of
	products, it does a pretty good job matching up what wasn't found otherwise.
	Aside from being misleading with shared directories, this method works very
	well for legitamate products wrapped by non-MSI installers.
	"""
	for pathAttribute in ['path_from_analysis', 'path_from_filesystem', 'path_from_process']:
		try:
			processPath = processData.get(pathAttribute)
			if processPath is None or processPath == 'N/A' or processPath == 'null' or processPath == 'None' or processPath == 'Unknown':
				continue

			runtime.logger.report('   Going through software entries for {processPath!r}...', processPath=processPath)
			version = None
			description = None
			vendor = None
			softwareName = None
			thisType = 'Windows'
			## Go through the list of Software and search for a matching Owner
			for softwareData in data.softwareList:
				try:
					## Software Products created by OS shared job or this job
					thisType = softwareData.get('recorded_by')
					if (thisType == 'Windows Product' or
						thisType == 'Windows Product from Registry' or
						thisType == 'Windows Product from WMI'):
						## Get the software install path
						softwarePath = softwareData.get("path")
						if softwarePath is None:
							continue

						runtime.logger.report('   Going through software entries for {processPath!r}... this Software path: {softwarePath!r}', processPath=processPath, softwarePath=softwarePath)
						## Remove quotes and change backslashes, for the regEx re_match
						softwarePathValue = utilities.AlignSlashesInDirectoryPath(utilities.ReplaceCharactersInStrings(softwarePath, '"', ''), 'Windows')
						## Look for a Software Product matching the install path
						if (softwarePathValue and (processPath != 'null') and
							(len(processPath) > 1 and len(softwarePathValue) > 1) and
							(softwarePathValue == processPath[:len(softwarePathValue)])):

							runtime.logger.report('   Matching software path FOUND for process {processPath!r}...', processPath=processPath)
							## This process has a path beneath the install location
							## of a software product installation; use the package
							## details for ownership context.
							softwareName = softwareData.get('name')

							## Matching Application Component found
							version = None
							with suppress(Exception):
								version = softwareData.get('version')
								runtime.logger.report('   Software version    : {version!r}...', version=version)
							description = None
							with suppress(Exception):
								description = softwareData.get('description')
								runtime.logger.report('   Software description: {description!r}...', description=description)
							vendor = None
							with suppress(Exception):
								vendor = softwareData.get('vendor')
								runtime.logger.report('   Software vendor     : {vendor!r}...', vendor=vendor)
							if vendor is None:
								with suppress(Exception):
									vendor = softwareData.get('discovered_vendor')
									runtime.logger.report('   Software vendor     : {vendor!r}...', vendor=vendor)
							if vendor is None:
								with suppress(Exception):
									vendor = softwareData.get('TenantOwner')
									runtime.logger.report('   Software vendor     : {vendor!r}...', vendor=vendor)
							if (version or description or vendor):
								break
					else:
						runtime.logger.report('   --> Software type is not Windows Product, skipping.')
				except:
					stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					runtime.logger.error('Exception in querySoftwareForProcessWindows: {stacktrace!r}', stacktrace=stacktrace)

			(processFingerprintId, softwareFingerprintId, trackThisComponent) = createObjects(runtime, data.osType, data.nodeId, data.softwareFingerprints, processData, processId, processId, pidTrackingList, data.processDictionary, processName, softwareName, None, version, description, vendor, thisType, processTree, filters=data.softwareFilters)
			runtime.logger.report('  Created SoftwareFingerprint for process {processName!r} and softwareFingerprintId:  {softwareFingerprintId!r}', processName=processName, softwareFingerprintId=softwareFingerprintId)
			return (processFingerprintId, softwareFingerprintId, trackThisComponent)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in querySoftwareForProcessWindows: {stacktrace!r}', stacktrace=stacktrace)

	## end querySoftwareForProcessWindows
	return (None, None, True)


def startTaskForProcessWindows(runtime, data, processId, pidTrackingList, processName, processData, processTree, startingProcessData=None, startingProcessPid=None):
	"""Look for a Windows Service responsible for starting this process."""
	try:
		## Find a valid path in case we need it
		processPath = None
		for pathAttribute in ['path_from_analysis', 'path_from_filesystem', 'path_from_process']:
			processPath = processData.get(pathAttribute)
			if processPath is None or processPath == 'N/A' or processPath == 'null' or processPath == 'None' or processPath == 'Unknown':
				continue
			break

		## Go through the Services using the PID (very reliable)
		for entry in data.startTaskDictionary.keys():
			try:
				serviceData = data.startTaskDictionary[entry]
				testPID = serviceData.get('process_id')
				if testPID is None:
					## Not all services will list PIDs, even if running
					continue
				thisType = 'Windows Service'
				## Look for a Windows Service matching the PID
				if (int(testPID) != int(processId)):
					continue
				serviceName = serviceData.get('name')
				serviceDisplayName = serviceData.get('display_name')
				serviceDescription = serviceData.get('description')
				if serviceDescription is not None and len(serviceDescription) > 100:
					serviceDescription = utilities.concatenate(serviceDescription[:100], '...')

				## While the Windows Service is the best place to look for a
				## positive match of the process ID (or parent), it doesn't
				## hold enough data; we retrieve more from the OS Libraries.

				## Sometimes this will cause confusion; for example, a UCMDB
				## service would have a java wrapper.exe process and so the
				## version and vendor would be based on Java and Oracle -
				## instead of HP/HPE/MicroFocus. This is mitigated by taking
				## the data from the child process (e.g. ucmdb_server.exe)
				## instead of the parent (e.g. wrapper) that was started by
				## a Windows Service. Nevertheless, it's far more complete
				## this way; plus I note 'Windows Service and Libraries'.

				## In createObjects below, I want to use the starting/child
				## process data. But when the starting process context is
				## empty, I fall back to using the original process sent in.
				if (startingProcessPid is None):
					startingProcessPid = processId
				if (startingProcessData is None):
					startingProcessData = processData
				else:
					## Override the Name with the starting proc
					processName = startingProcessData.get('name')
					## Override the Path with the starting proc
					with suppress(Exception):
						startingProcessPath = startingProcessData.get('path_from_process')
						if (startingProcessPath and len(startingProcessPath) > 0 and startingProcessPath != 'null' and startingProcessPath != 'None' and startingProcessPath != 'Unknown' and startingProcessPath != 'N/A'):
							## Use the starting process when possible
							processPath = startingProcessPath

				runtime.logger.report('  Querying OS libraries for process {processPath!r}', processPath=processPath)
				name = None
				version = None
				identifier = None
				info = None
				company = None
				if (processPath is not None and len(processPath) > 0):
					(name, version, identifier, info, company) = queryProcessForOwnershipWindows(runtime, data, processPath)
				## Keep Name, ID, and description from the Service
				if (serviceDisplayName is None):
					serviceDisplayName = serviceName
				description = None
				if (version or info or identifier or company):
					thisType = 'Windows Service and Libraries'
					## Combine the Windows Service description with the file
					## 'info'; sometimes this is important and sometimes it
					## will be confusing, but better to retain than discard
					## in order to enable automation (not fed interactively)
					if (info):
						description = info
					elif (identifier):
						description = identifier
					if (serviceName == serviceDisplayName):
						if (identifier and serviceName != identifier):
							serviceName = identifier
						elif (name):
							serviceName = name
				elif (serviceName == None):
					serviceName = utilities.concatenate('NA: ', processName)
				if description is not None:
					if len(description) > 100:
						description = utilities.concatenate(description[:100], '...')
					if (serviceDescription):
						description = utilities.concatenate(serviceDescription, '  [along with]  ', description)
				else:
					description = serviceDescription

				(processFingerprintId, softwareFingerprintId, trackThisComponent) = createObjects(runtime, data.osType, data.nodeId, data.softwareFingerprints, startingProcessData, startingProcessPid, startingProcessPid, pidTrackingList, data.processDictionary, processName, serviceDisplayName, serviceName, version, description, company, thisType, processTree, filters=data.startTaskFilters, filterType='starttask')
				runtime.logger.report('  Created SoftwareFingerprint for process {processName!r} and softwareFingerprintId:  {softwareFingerprintId!r}', processName=processName, softwareFingerprintId=softwareFingerprintId)
				return (processFingerprintId, softwareFingerprintId, trackThisComponent)

			except:
				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				runtime.logger.error('Exception in startTaskForProcessWindows: {stacktrace!r}', stacktrace=stacktrace)
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in startTaskForProcessWindows: {stacktrace!r}', stacktrace=stacktrace)

	## end startTaskForProcessWindows
	return (None, None, True)

###############################################################################
############################  END WINDOWS SECTION  ############################
###############################################################################


###############################################################################
############################  BEGIN LINUX SECTION  ############################
###############################################################################

def queryPackageManagerForProcessLinux(runtime, data, targetProcessId, processId, pidTrackingList, processName, processData, processTree):
	"""Attempt to retrieve data from package managers using paths on this process."""
	for pathAttribute in ('path_from_filesystem', 'path_from_analysis', 'path_from_process'):
		try:
			## This won't work without a fully qualified process name
			## Get the path of this process
			processPath = processData.get(pathAttribute)
			if processPath is None or processPath == 'N/A' or processPath == 'null' or processPath == 'None' or processPath == 'Unknown':
				continue

			## Call the package manager
			softwareData = {}
			if processPath in data.softwareDictionary.keys():
				## Use a previously created entry when possible
				softwareData = data.softwareDictionary[processPath]
			else:
				## Create a new entry
				softwarePackageName = querySoftwareForProcessLinux(runtime, data, processPath)
				if softwarePackageName is not None:
					createSoftwareDataLinux(runtime, data, softwareData, softwarePackageName, processPath)
					data.softwareDictionary[processPath] = softwareData

			if len(softwareData.keys()) > 0:
				## Use software context to create fingerprint objects
				productName = softwareData.get('name')
				productID = softwareData.get('identifier')
				productVersion = softwareData.get('version')
				productSummary = softwareData.get('title')
				productVendor = None

				## Create the objects
				(processFingerprintId, softwareFingerprintId, trackThisComponent) = createObjects(runtime, data.osType, data.nodeId, data.softwareFingerprints, processData, targetProcessId, processId, pidTrackingList, data.processDictionary, processName, productName, productID, productVersion, productSummary, productVendor, 'Linux', processTree, filters=data.softwareFilters)
				runtime.logger.report('  Created SoftwareFingerprint for process {processName!r} and softwareFingerprintId:  {softwareFingerprintId!r}', processName=processName, softwareFingerprintId=softwareFingerprintId)
				return (processFingerprintId, softwareFingerprintId, trackThisComponent)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in queryPackageManagerForProcessLinux: {stacktrace!r}', stacktrace=stacktrace)

	## end queryPackageManagerForProcessLinux
	return (None, None, True)


def querySoftwareForProcessLinux(runtime, data, processPath):
	"""Find the software package responsible for deploying this process."""
	softwarePackageName = None
	try:
		whatProvides = utilities.updateCommand(runtime, utilities.concatenate('rpm -q --whatprovides ', processPath))
		(result, stdError, hitProblem) = data.client.run(whatProvides, 60)
		if (hitProblem or result is None or len(result) <= 0):
			return None
		softwarePackageName = result.strip()

		if (re.findall('no package provides', softwarePackageName)):
			## If no package found, we may have a symbolic link
			runtime.logger.report('  Did not find owning package for process file; check if this is a symbolic link: {processPath!r}', processPath=processPath)

			## Search for symbolic link instead of a hard file node.
			lastFileSize = 0
			filePropertiesCmd = utilities.updateCommand(runtime, utilities.concatenate('ls -l ', processPath))
			(result, stdError, hitProblem) = data.client.run(filePropertiesCmd)
			if (hitProblem or len(result) <= 0):
				return None
			filePropertiesStr = result.strip()
			m = re.search(utilities.concatenate(processPath, '\s*[-][>]\s*(/.*)$'), filePropertiesStr)
			if (not m):
				return None
			processPath = m.group(1)
			runtime.logger.report('  Yes, file is a symbolic link. New file location: {processPath!r}', processPath=processPath)

			## Search the package manager again for the new process name
			whatProvides = utilities.updateCommand(runtime, utilities.concatenate('rpm -q --whatprovides ', processPath))
			(result, stdError, hitProblem) = data.client.run(whatProvides, 60)
			if (hitProblem or result is None or len(result.strip()) <= 0):
				return None
			softwarePackageName = result.strip()

		if (re.findall('is not owned by any package', softwarePackageName)):
			## File was found, but not owned by a package
			runtime.logger.report('  File was found but not owned by a package: {processPath!r}', processPath=processPath)
			return None
		if (re.findall('[Nn]o package provides', softwarePackageName) or re.findall('[Nn]o such file or directory', softwarePackageName) or re.findall('[Ee]rror:', softwarePackageName)):
			runtime.logger.report('  File is not owned by a package: {processPath!r}', processPath=processPath)
			return None

		line = softwarePackageName.split()
		if (line != [] or len(line) != 0):
			softwarePackageName = line[0] or None
		runtime.logger.report('  File was found in softwarePackageName: {softwarePackageName!r}', softwarePackageName=softwarePackageName)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in querySoftwareForProcessLinux: {stacktrace!r}', stacktrace=stacktrace)

	## end querySoftwareForProcessLinux
	return softwarePackageName


def createSoftwareDataLinux(runtime, data, softwareData, softwarePackageName, processPath):
	"""Pull software details and create an object."""
	try:
		## Query for the package name
		packageInfoCmd = utilities.updateCommand(runtime, utilities.concatenate('rpm  -q -i ', softwarePackageName, ' |grep -i \"name\\\|version\\\|summary\"'))
		(result, stdError, hitProblem) = data.client.run(packageInfoCmd, 60)
		if (not hitProblem and len(result) > 0):
			if (re.findall('[Nn]o package provides', result) or re.findall('[Nn]o such file or directory', result) or re.findall('[Ee]rror:', result)):
				runtime.logger.report('  Package not found: {softwarePackageName!r}', softwarePackageName=softwarePackageName)
				return None

			productName = None
			productVersion = None
			productSummary = None
			## Parse the software package information
			lines = result.split('\n')
			runtime.logger.report('  Package information: {lines!r}', lines=lines)
			for line in lines:
				try:
					if (re.findall("[Nn]ame\s*:\s*\S*", line)):
						nameStr = re.search("[Nn]ame\s*:\s*(\S+)", line)
						productName = nameStr.group(1)
					elif (re.findall("[Vv]ersion\s*:\s*\S*", line)):
						versionStr = re.search("[Vv]ersion\s*:\s*(\S+)", line)
						productVersion = versionStr.group(1)
					elif (re.findall("[Ss]ummary\s*:\s*\S", line)):
						summaryStr = re.search("[Ss]ummary\s*:\s*(.+)$", line)
						productSummary = summaryStr.group(1).strip()
						## Clean up the Summary
						try:
							## Remove trailing period
							if (re.findall("\.$", productSummary)):
								tmpStr = re.search("(.*)\.$", productSummary)
								productSummary = tmpStr.group(1)
							## Remove "A tool " verbiage; more concise
							if (re.findall("^[Aa] tool for ", productSummary)):
								tmpStr = re.search("^[Aa] tool for (.*)", productSummary)
								productSummary = tmpStr.group(1)
							if (re.findall("^[Aa] tool to ", productSummary)):
								tmpStr = re.search("^[Aa] tool to (.*)", productSummary)
								productSummary = tmpStr.group(1)
							if (re.findall("^[Aa] tool which ", productSummary)):
								tmpStr = re.search("^[Aa] tool which (.*)", productSummary)
								productSummary = tmpStr.group(1)
							if (re.findall("^[Aa] tool that ", productSummary)):
								tmpStr = re.search("^[Aa] tool that (.*)", productSummary)
								productSummary = tmpStr.group(1)
							## Remove "The " and "A " from the start; more concise
							if (re.findall("^[Tt]he ", productSummary)):
								tmpStr = re.search("^[Tt]he (.*)", productSummary)
								productSummary = tmpStr.group(1)
							if (re.findall("^[Aa] ", productSummary)):
								tmpStr = re.search("^[Aa] (.*)", productSummary)
								productSummary = tmpStr.group(1)
							if (re.findall("^[Aa]n ", productSummary)):
								tmpStr = re.search("^[Aa]n (.*)", productSummary)
								productSummary = tmpStr.group(1)
							## Uppercase the first letter
							tmpStr = re.search("^(\S)(.*)", productSummary)
							productSummary = utilities.concatenate(tmpStr.group(1).upper(), tmpStr.group(2))
						except:
							stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
							runtime.logger.error('Exception in createSoftwareDataLinux parsing summary on package {softwarePackageName!r} for process {processPath!r}:  {stacktrace!r}', softwarePackageName=softwarePackageName, processPath=processPath, stacktrace=stacktrace)
							productSummary = summaryStr.group(1).strip()
				except:
					stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					runtime.logger.error('Exception in createSoftwareDataLinux parsing package {softwarePackageName!r} for process {processPath!r}:  {stacktrace!r}', softwarePackageName=softwarePackageName, processPath=processPath, stacktrace=stacktrace)

			osSoftwarePackages.createSoftware(runtime, data.nodeId, False, [], productName, softwarePackageName, productVersion, productSummary, 'Linux', None, None, None, None, None, None, softwareData)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in createSoftwareDataLinux: {stacktrace!r}', stacktrace=stacktrace)

	## end createSoftwareDataLinux
	return


def startTaskForProcessLinux(runtime, data, processId, pidTrackingList, processName, processData, processTree, startingProcessData=None, startingProcessPid=None):
	"""Look for a Linux Daemon responsible for starting this process."""
	try:
		## Find a valid path in case we need it
		processPath = None
		for pathAttribute in ['path_from_analysis', 'path_from_filesystem', 'path_from_process']:
			processPath = processData.get(pathAttribute)
			if processPath is None or processPath == 'N/A' or processPath == 'null' or processPath == 'None' or processPath == 'Unknown':
				continue
			break
		runtime.logger.report('  startTaskForProcessLinux: processData: {processData!r}', processData=processData)
		runtime.logger.report('  startTaskForProcessLinux: pathAttribute {pathAttribute!r} value: {processPath!r}', pathAttribute=pathAttribute, processPath=processPath)
		runtime.logger.report('  startTaskForProcessLinux: startingProcessData: {startingProcessData!r}', startingProcessData=startingProcessData)

		## Go through the Services using the PID (pretty reliable with systemd)
		for entry in data.startTaskDictionary.keys():
			try:
				serviceData = data.startTaskDictionary[entry]
				testPID = serviceData.get('process_id')
				if testPID is None:
					## Not all services will list PIDs, even if running
					continue
				thisType = 'Linux Service'
				## Look for a Service matching the PID
				if (int(testPID) != int(processId)):
					continue
				serviceName = serviceData.get('name')
				serviceDisplayName = serviceData.get('display_name')
				serviceDescription = serviceData.get('description')
				if serviceDescription is not None and len(serviceDescription) > 100:
					serviceDescription = utilities.concatenate(serviceDescription[:100], '...')
				## While the Linux Service is the best place to look for a
				## positive match of the process ID (or parent), it doesn't
				## hold enough data; we retrieve more from the OS Libraries.

				## Sometimes this will cause confusion; for example, a UCMDB
				## service is started by have a java wrapper process and the
				## version and vendor would be based on Java and Oracle, instead
				## of MicroFocus. This is mitigated by taking the data from the
				## child process (e.g. ucmdb_server) instead of the parent (e.g.
				## wrapper) that was started by a Service/Daemon. But it's more
				## context rich this way, and we note 'Service and Software'.

				## In createObjects below, I want to use the starting/child
				## process data. But when the starting process context is
				## empty, I fall back to using the original process sent in.
				if (startingProcessPid is None):
					startingProcessPid = processId
				if (startingProcessData is None):
					startingProcessData = processData
				else:
					## Override the Name with the starting proc
					processName = startingProcessData.get('name')
					## Override the Path with the starting proc
					with suppress(Exception):
						for pathAttribute in ['path_from_analysis', 'path_from_filesystem', 'path_from_process']:
							startingProcessPath = startingProcessData.get(pathAttribute)
							if (startingProcessPath and len(startingProcessPath) > 0 and startingProcessPath != 'null' and startingProcessPath != 'None' and startingProcessPath != 'Unknown' and startingProcessPath != 'N/A'):
								## Use the starting process when possible
								processPath = startingProcessPath
							break

				runtime.logger.report('  startTaskForProcessLinux: now using processPath: {processPath!r}', processPath=processPath)

				name = None
				version = None
				identifier = None
				info = None
				company = None
				if (processPath and len(processPath) > 0 and processPath != 'null' and processPath != 'None' and processPath != 'Unknown' and processPath != 'N/A'):
					## Call the package manager
					softwareData = {}
					if processPath in data.softwareDictionary.keys():
						## Use a previously created entry when possible
						softwareData = data.softwareDictionary[processPath]
					else:
						## Create a new entry
						softwarePackageName = querySoftwareForProcessLinux(runtime, data, processPath)
						if softwarePackageName is not None:
							createSoftwareDataLinux(runtime, data, softwareData, softwarePackageName, processPath)
							data.softwareDictionary[processPath] = softwareData

					if len(softwareData.keys()) > 0:
						## Use software context to create fingerprint objects
						name = softwareData.get('name')
						identifier = softwareData.get('identifier')
						version = softwareData.get('version')
						info = softwareData.get('title')

				## Keep Name, ID, and description from the Service
				if (serviceDisplayName is None):
					serviceDisplayName = serviceName
				description = None
				#if (version or info or identifier or company):
				if (version or info or identifier or name):
					thisType = 'Linux Service and Software'
					## Combine the Linux Service description with the software
					## 'info'; sometimes this is important and sometimes it
					## will be confusing, but better to retain than discard
					## in order to enable automation (not fed interactively)
					if (info):
						description = info
					elif (identifier):
						description = identifier
					if (serviceName == serviceDisplayName):
						if (identifier and serviceName != identifier):
							serviceName = identifier
						elif (name):
							serviceName = name
				elif (serviceName == None):
					serviceName = utilities.concatenate('NA: ', processName)
				if description is not None:
					if len(description) > 100:
						description = utilities.concatenate(description[:100], '...')
					if (serviceDescription):
						description = utilities.concatenate(serviceDescription, '  [along with]  ', description)
					elif (description != info):
						description = utilities.concatenate(serviceDescription, ' : ', info)
				else:
					description = serviceDescription

				(processFingerprintId, softwareFingerprintId, trackThisComponent) = createObjects(runtime, data.osType, data.nodeId, data.softwareFingerprints, startingProcessData, startingProcessPid, startingProcessPid, pidTrackingList, data.processDictionary, processName, serviceDisplayName, serviceName, version, description, company, thisType, processTree, filters=data.startTaskFilters, filterType='starttask')
				runtime.logger.report('  Created SoftwareFingerprint for process {processName!r} and softwareFingerprintId:  {softwareFingerprintId!r}', processName=processName, softwareFingerprintId=softwareFingerprintId)
				return (processFingerprintId, softwareFingerprintId, trackThisComponent)

			except:
				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				runtime.logger.error('Exception in startTaskForProcessWindows: {stacktrace!r}', stacktrace=stacktrace)
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in startTaskForProcessWindows: {stacktrace!r}', stacktrace=stacktrace)

	## end startTaskForProcessWindows
	return (None, None, True)

###############################################################################
#############################  END LINUX SECTION  #############################
###############################################################################
