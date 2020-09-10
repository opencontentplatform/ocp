"""Gather running processes on OS types.

Entry function:
  getProcesses : standard module entry point

OS agnostic functions:
  gatherInitialProcesses : get initial process - wrapper for OS types
  filterInitialProcesses : filter processes returned in 'list' format
  updateAllProcesses : update all process at once - wrapper for OS types
  isValidProcessAndIsNotTopOsProcess : whether we should follow this process
  isValidProcessAndIsNotTopOsProcessWithList : same with list style results
  buildProcessHierarchy : find all processes in the stack (tree)
  setFingerprintAttributes : track attributes for process fingerprint object
  snipLongProcessStrings : retain only 2400 chars of long process args
  needToTrackThisProcess : determine whether this process is worth keeping
  parseParams : parse process args to find valuable context
  parseJavaParams : parse Java process args to find main entry point
  getFullyQualifiedProcessName : lookup process path given a PID
  cleanUnixProcessCommand : clean up any UX style process line
  uxResolveSymbolicLink : follow one UX symbolic link to the destination file
  uxResolveSymbolicLinks : follow all UX symbolic links to the destination files
  uxGetProcessPath : split out path from process name on UX style line

OS specific functions:
  windowsGetProcess : parse Windows Process in List format
  windowsGetFullyQualifiedProcessName : get fully qualified process name
  windowsUpdateProcessResolvedPath : translate an 8dot3 Windows path
  windowsUpdateAllProcesses : update all Windows processes
  windowsUpdateThisProcess : update a single Windows process
  linuxGetProcess : parse Linux Processes
  linuxGetFullyQualifiedProcessName : fully qualified process name from /proc
  linuxGetCurrentWorkingDir : cwd from the /proc filesystem
  linuxParseProcFilesystem : use /proc filesystem to update path attributes
  linuxUpdateAllProcesses : update all Linux processes
  linuxUpdateThisProcess : Update details on a single Linux process


Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Mar 3, 2018

"""
import sys
import traceback
import os
import re
from contextlib import suppress

## From openContentPlatform content/contentGathering/shared/script
from utilities import updateCommand, verifyOutputLines, loadJsonIgnoringComments
from utilities import concatenate, resolve8dot3Name, compareFilter


def getProcesses(runtime, client, nodeId, trackResults=False, resultList=None, discoverPaths=True, discoverVirtualChildProcs=False, includeFilteredProcesses=False):
	"""Standard entry point for osProcesses when gathering all procs at once.

	Note: the dynamic discovery jobs use a modified version of this since they
	need to gather all processes and filter out known instances, before
	surgically going after just those that are new. So they only want to run
	additional commands to update attributes (like path) for the new ones.

	This function returns a dictionary of processes found. And when the caller
	function requests to trackResults (meaning add objects onto the results
	object), this function adds all the created instances onto runtime's results
	so the caller function doesn't need to code that logic.
	"""
	resultDictionary = {}
	rawProcessOutput = None
	if resultList is None:
		resultList = []
	try:
		osType = runtime.endpoint.get('data').get('node_type')

		## Gather initial process listing from the supported OS types.
		rawProcessOutput = gatherInitialProcesses(runtime, client, osType)
		if rawProcessOutput is None:
			return resultDictionary
		runtime.logger.report('Process results:\n {rawProcessOutput!r}', rawProcessOutput=rawProcessOutput)

		## Get values and set defaults for the filters, before going through
		## the processes; it's unnecessary overhead to do this per process
		filters = {}
		getFilterParameters(runtime, osType, filters)
		excludedProcessList = []
		processIgnoreList = []
		filterInitialProcesses(runtime, osType, nodeId, rawProcessOutput, resultList, excludedProcessList, filters)
		buildProcessDictionary(runtime, nodeId, resultList, resultDictionary, False, osType, True, includeFilteredProcesses=True, excludedProcessList=excludedProcessList, processIgnoreList=filters.get('processIgnoreList'))

		## Go through each process that wasn't filtered out
		for pid in resultDictionary:
			(processData, processPpid, objectId) = resultDictionary[pid]
			runtime.logger.report('looking at process {pid!r}: {processData!r}', pid=pid, processData=processData)
			## Qualify and update this process of interest, before analysis
			updateThisProcess(runtime, processData, client, osType, pid)


		runtime.logger.report('Process count after attributes updated: {processCount!r}', processCount=len(resultList))

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error(' Failure in getProcesses: {stacktrace!r}', stacktrace=stacktrace)

	## Abort if no process data returned; error already logged
	if ((rawProcessOutput is None) or (len(resultList) == 0)):
		runtime.logger.report('Failed to discover processes on {osType!r}', osType=osType)
		## Prevent calling script from thinking everything is fine
		raise EnvironmentError('Failed to discover processes')

	## end getProcesses
	return resultDictionary


###############################################################################
###########################  BEGIN GENERAL SECTION  ###########################
###############################################################################

def gatherInitialProcesses(runtime, client, osType):
	"""Gather initial process listing from the supported OS types."""
	runtime.logger.report('Gathering {osType!r} Processes', osType=osType)

	psCmd = None
	if (osType == 'Windows'):
		psCmd = 'Get-WmiObject Win32_Process | %{Try{$A=$_.CommandLine; if ($A.length -gt 2416) {$B=$A.Substring(0,1200); $C=$A.Substring($A.length-1200); $A=$B+\'...[snip]...\'+$C}; $_.Name,$_.handle,$_.ParentProcessId,$_.ExecutablePath,$A,$_.getowner().user -Join \':==:\'}Catch{}}'
		## Eventually I want to cut over to a more managable object like JSON,
		## especially since ConvertTo-Json cmdlet improved in PowerShell version
		## 4 (fixed quoting) and then in 6 (fixed newline encapulation issues):
		## 'Get-WmiObject Win32_Process | Select-Object Name,@{n=\'PID\';e={$_.handle}},@{n=\'PPID\';e={$_.ParentProcessId}},ExecutablePath,@{n=\'Owner\';e={$_.GetOwner().User}},CommandLine | ConvertTo-Json'
	elif (osType == 'Linux'):
		psCmd = updateCommand(runtime, 'ps -e -o user -o pid -o ppid -o command --cols 10000')
		## Eventually if planning to enable PowerShell to Linux and others, will
		## want to use similar command syntax on that shell type... of course
		## as of v6.1 the get-process cmdlet doesn't have command line and the
		## PPID(SessionId or SI) is sometimes the same as PID(Id), or zero:
		## get-process -IncludeUserName  | select-object ProcessName,Id,SessionId,Path,UserName | ConvertTo-Json
	elif (osType == 'HPUX'):
		psCmd = updateCommand(runtime, 'ps -ef')
	elif (osType == 'Solaris'):
		psCmd = updateCommand(runtime, 'ps_bsd -awwxl')
	elif (osType == 'AIX'):
		psCmd = updateCommand(runtime, 'ps -e -o \'user,pid,ppid,args\'')
		psCmd = 'export COLUMNS=10000; ' + psCmd
	(rawProcessOutput, stdError, hitProblem) = client.run(psCmd, 120)

	if (rawProcessOutput is None or len(rawProcessOutput) <= 0):
		runtime.logger.report('No processes returned from process query')
		if stdError is not None:
			runtime.logger.report('  Process error: {stdError!r}', stdError=stdError)
	if hitProblem:
		runtime.logger.info('Operating system returned error in gatherInitialProcesses: {rawProcessOutput!r}. Check your operating system parameters for process command paths and permissions.', rawProcessOutput=rawProcessOutput[:256])
		raise EnvironmentError('Error gathering processes; bad exit status.')

	## end gatherInitialProcesses
	return rawProcessOutput


def getFilterParameters(runtime, osType, filters):
	"""Get filters from the shell parameters."""
	## Get the shell interpreters in list format
	filters['interpreterList'] = runtime.endpoint.get('data').get('parameters').get('interpreters', [])
	## Get the exclusion list of processes
	filters['processFilterIncludeCompare'] = runtime.endpoint.get('data').get('parameters').get('processFilterIncludeCompare', '==')
	filters['processFilterExcludeCompare'] = runtime.endpoint.get('data').get('parameters').get('processFilterExcludeCompare', '==')
	filters['processFilterExcludeList'] = runtime.endpoint.get('data').get('parameters').get('processFilterExcludeList', [])
	filters['processFilterExcludeOsCompare'] = runtime.endpoint.get('data').get('parameters').get('processFilterExcludeOsCompare', '==')
	filters['processFilterExcludeOsList'] = runtime.endpoint.get('data').get('parameters').get('processFilterExcludeOsList', [])
	filters['processIgnoreList'] = runtime.endpoint.get('data').get('parameters').get('processIgnoreList', [])

	filters['processFilterFlag'] = True
	if (len(filters['processFilterExcludeList']) <= 0 and len(filters['processFilterExcludeOsList']) <= 0):
		filters['processFilterFlag'] = False
		runtime.logger.report(' No processes listed in the exclusion parameters inside osParameters.json for {osType!r} (or settings are intentionally overwritten); returning all processes.', osType=osType)

	## end getFilterParameters
	return


def filterInitialProcesses(runtime, osType, nodeId, outputString, resultList, excludedProcessList, filters, processFilterIncludeList=None, processFilterPidList=None):
	"""Inital parsing for processes returned in 'List' format."""
	if (outputString is None or len(outputString) <= 0 or len(outputString.strip()) <= 0):
		runtime.logger.error('No {osType!r} processes returned', osType=osType)
		return

	## Solaris doesn't have a native sudo, so it's possible it's not there
	if (re.search('sudo[:]*\s*not\s*found', outputString, re.I)):
		runtime.logger.error('Sudo not found on {osType!r}; no processes returned', osType=osType)
		return

	errorCount = 1  ## set to 1 to avoid zero division in the calculation below
	outputLines = verifyOutputLines(runtime, outputString)

	## Parse process output (stored in List)
	for line in outputLines:
		try:
			## Ignore blank lines and bad entries
			if not line:
				continue
			line = line.strip()
			if (line is None or len(line.strip()) <= 0):
				continue
			if line.find('<defunct>') != -1:
				continue

			## OS Specific parsing
			if (osType == 'Windows'):
				newSeparator = ':==:'
				errorCount = windowsGetProcess(runtime, osType, nodeId, line, errorCount, resultList, excludedProcessList, filters, processFilterIncludeList, processFilterPidList, newSeparator)
			elif (osType == 'Linux'):
				errorCount = linuxGetProcess(runtime, osType, nodeId, line, errorCount, resultList, excludedProcessList, filters, processFilterIncludeList, processFilterPidList)
			elif (osType == 'HPUX'):
				#errorCount = hpuxGetProcess(runtime, osType, nodeId, line, errorCount, resultList, processFilterIncludeList, processFilterPidList, excludedProcessList)
				pass
			elif (osType == 'Solaris'):
				#errorCount = solarisGetProcess(runtime, osType, nodeId, line, errorCount, resultList, processFilterIncludeList, processFilterPidList, excludedProcessList)
				pass
			elif (osType == 'AIX'):
				#errorCount = aixGetProcess(runtime, osType, nodeId, line, errorCount, resultList, processFilterIncludeList, processFilterPidList, excludedProcessList)
				pass

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception parsing {osType!r} process line {line!r}: {stacktrace!r}', osType=osType, line=line, stacktrace=stacktrace)
			errorCount = errorCount + 1

	## If most the lines returned with unparsable values - say something
	if (errorCount / (len(outputLines)) > .75):
		runtime.logger.report(' Number of {osType!r} processes {outputLines!r}; number of parsing errors {errorCount!r}.', osType=osType, outputLines=len(outputLines), errorCount=errorCount)
		if (osType == 'Windows'):
			runtime.logger.report('Process list for {osType!r} returned over 75% of unusuable data; this suggests either limited access or output variance on a different OS version.', osType=osType)
		else:
			runtime.logger.report('Process list for {osType!r} returned over 75% of unusuable data; this suggests either limited access or output variance on a different OS version.  Ensure \'Use_SUDO_for_PS\' and \'ps_Cmd\' are configured properly in the {osType2!r} Parameters section.', osType=osType, osType2=osType)
		## Don't just warn; abort the run
		raise EnvironmentError('Process list for ' + osType + ' returned over 75% of unusuable data; this suggests either limited access or output variance on a different OS version')

	## end filterInitialProcesses
	return


def cleanUnixProcessCommand(runtime, commAndPath, processArgs, interpreters):
	"""Clean up Unix style processes."""
	commandLine = commAndPath
	if processArgs:
		## Avoid appending 'None' to the cmdline if we have no arguments
		commandLine = commAndPath + ' ' + processArgs

	## Clean process cmdlines returned in square brackets; not only do I remove
	## the brakets, but I also remove anything with slash content. That means
	## '[crypto/0]' and '[crypto/1]' merge into the same 'crypto' process.
	m = re.search('^\s*\[\s*(.[^\]/]+)', commAndPath)
	if (m):
		commAndPath = m.group(1)

	## Check for process names with preceeding paths
	m1 = re.search('^\s*(/.+)/([^/]+)', commAndPath)
	m2 = re.search('^\s*(\./(?:.*/)?)([^/]+)', commAndPath)
	cleanCommand = commAndPath
	cleanPath = None
	parsedArgs = None

	## Second thought; keep the paths on the qualified process so there isn't
	## so much magic around how you put the process name back on, when the
	## object is a symbolic link to another location and the process name has
	## been changed by the calling program (e.g. db2wdog instead of db2sysc)
	## Split out fully qualified paths
	if (m1):
		cleanCommand = m1.group(2)
		cleanPath = commAndPath

	## Split out relative paths
	if (m2):
		## Relative paths are not useful
		#cleanPath = m2.group(1)
		cleanCommand = m2.group(2)

	## Clean process names ending in a colon
	m = re.search('^\s*(.*):\s*$', cleanCommand)
	if (m):
		cleanCommand = m.group(1)

	## Clean process paths that start with @, e.g.:
	##   @usr/sbin/plymouthd --mode=boot --pid-file...
	m = re.search('^\s*@(.*)\s*$', cleanCommand)
	if (m):
		tmpCommand = m.group(1)
		## If the @ sign replaced the first slash in a path... reconstruct:
		## Note: leaving the process name alone; just modifying the path here,
		## to enable other jobs to find the same raw process name.
		if re.search('[/]', tmpCommand):
			cleanPath = '/{}'.format(tmpCommand)

	## Special formatting for shell script invocation; need to retain visibility
	## to the actual script names from the args, since resolving ownership from
	## shell interpreters (bash/sh/tcsh/ksh/perl) actually works against this
	## type of dyanamic discovery.  For example, the following hierarchy...
	##    ['hpbsm_opr-backend', 'sh', 'sh', 'nannyManager', 'wrapper']
	## would stop at 'sh', and resolve to 'GNU Bourne Shell' for /bin/sh,
	## which would actually only track the following hierarchy:
	##    ['sh', 'sh', 'nannyManager', 'wrapper']
	## when we need it to resolve either at the HP components, or not at all.
	## And if we choose not at all, then we should have a better qualified
	## hierarchy value in the process fingerprint CI; something like the
	## following is much more helpful:
	##    ['sh:opr-backend_run', 'sh:service_manager.sh', 'nannyManager', 'wrapper']
	## This allows the user to pattern-match interpreter scripts.
	runtime.logger.report('  cleanUnixProcessCommand: processArgs: {processArgs!r}', processArgs=processArgs)
	if processArgs:
		try:
			## Sample interpreters: sh, bash, tcsh, ksh, zsh, fish, perl
			for interpreter in interpreters:
				## If the first parameter after the interpreter is a path or
				## alphabetical character (specifically not a dash or slash
				## option), assume it's worth retaining (e.g. a script name)
				#m = re.search(interpreter, cleanCommand)
				m = re.search(r'^\s*('+interpreter+')\s*$', cleanCommand)
				if m:
					interpreterMatch = m.group(1)
					runtime.logger.report('  cleanUnixProcessCommand: found interpreter: {interpreterMatch!r}', interpreterMatch=interpreterMatch)
					runtime.logger.report('  cleanUnixProcessCommand: looking at processArgs: {processArgs!r}', processArgs=processArgs)
					## If the first parameter after the interpreter is a path or
					## alphabetical character (specifically not a dash or slash
					## option), assume it's worth retaining (e.g. a script name)
					m = re.search('^\s*([\./a-zA-Z]\S+)', processArgs)
					if (m):
						script = m.group(1)
						runtime.logger.report('  cleanUnixProcessCommand: found arg: {script!r}', script=script)
						m1 = re.search('^\s*(/.+)/([^/]+)', script)
						m2 = re.search('^\s*(\./(?:.*/)?)([^/]+)', script)
						## Check for script names with preceeding paths
						if (m1):
							script = m1.group(2)
						## Split out relative paths
						if (m2):
							script = m2.group(2)
						parsedArgs = script[:256]
						runtime.logger.report('  cleanUnixProcessCommand: clean arg: {parsedArgs!r}', parsedArgs=parsedArgs)
					break
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in cleanUnixProcessCommand in adding script name: {stacktrace!r}', stacktrace=stacktrace)

	## end cleanUnixProcessCommand
	return (cleanCommand, cleanPath, commandLine, parsedArgs)


def updateAllProcesses(runtime, client, osType, resultList, defaultContainerId, discoverPaths, discoverVirtualChildProcs, resultListMutable=None):
	"""Update desired process details on a list of processes.

	This enables parsing for each OS type to manipulate existing listings; add
	new attributes, translate existing attributes, switch the node for a process
	CI, etc. Overwriting resultList since the list changes pointer addresses.
	"""
	runtime.logger.report('Updating {osType!r} Processes', osType=osType)
	try:
		if (resultListMutable is None):
			resultListMutable = []

		if (osType == 'Windows'):
			resultList = windowsUpdateAllProcesses(runtime, client, osType, resultList, defaultContainerId, discoverPaths, resultListMutable)
		if (osType == 'Linux'):
			resultList = linuxUpdateAllProcesses(runtime, client, osType, resultList, defaultContainerId, discoverPaths, resultListMutable)
		if (osType == 'HPUX'):
			#resultList = hpuxUpdateProcesses(runtime, client, osType, resultList, defaultContainerId, discoverPaths, resultListMutable)
			pass
		if (osType == 'Solaris'):
			#resultList = solarisUpdateProcesses(runtime, client, osType, resultList, defaultContainerId, discoverPaths, discoverVirtualChildProcs, results, resultListMutable)
			pass
		if (osType == 'AIX'):
			#resultList = aixUpdateProcesses(runtime, client, osType, resultList, defaultContainerId, discoverPaths, resultListMutable)
			pass
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception updating {osType!r} processes: {stacktrace!r}', osType=osType, stacktrace=stacktrace)

	## end updateAllProcesses
	return


def updateThisProcess(runtime, processData, client, osType, pid, objectId=None):
	"""Update attributes on a single process (like Path).

	This enables parsing for each OS type to manipulate existing listings; add
	new attributes, translate existing attributes, switch the node for a process
	CI, etc. Overwriting resultList since the list changes pointer addresses.
	"""
	runtime.logger.report('Updating {osType!r} Process', osType=osType)
	try:
		if (osType == 'Windows'):
			windowsUpdateThisProcess(runtime, processData, client, objectId)
		if (osType == 'Linux'):
			linuxUpdateThisProcess(runtime, processData, client, pid, objectId)
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in updateThisProcess for {osType!r}: {stacktrace!r}', osType=osType, stacktrace=stacktrace)

	## end updateThisProcess
	return


def getFingerprintAttributes(runtime, resultList, entry, osType, attributes, excludedProcessList, processIgnoreList, resultDictionary, logContext=""):
	"""Get the process hierarchy and then set attributes."""
	(nodeId, user, pid, name, ppid, commandLine, pathFromProcess, pathFromAnalysis, pathFromFilesystem, args, parsedArgs) = entry
	runtime.logger.report('  {osType!r} process: {pid!r}, {ppid!r}, {name!r}, {user!r}, {pathFromProcess!r}, {parsedArgs!r}, {commandLine!r}', osType=osType, pid=pid, ppid=ppid, name=name, user=user, pathFromProcess=pathFromProcess, parsedArgs=parsedArgs, commandLine=commandLine[:256])
	## Establish the parsedArgs. Note, this may already be set from the initial
	## process parsing by pulling off the interpretor script name.
	parsedArgContext = parsedArgs
	if parsedArgContext is None:
		## If not, attempt other parsing (e.g. java class name)
		parsedArgContext = parseParams(runtime, name, args)
	## Establish process tree named heirarchy
	processHierarchy = None
	try:
		processHierarchy = buildProcessHierarchy(runtime, pid, osType, resultList, excludedProcessList, processIgnoreList)
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception with building processHierarchy in getFingerprintAttributes: {stacktrace!r}', stacktrace=stacktrace)
	runtime.logger.report('    --> {logContext!r} Process has processHierarchy: {processHierarchy!r}', logContext=str(logContext), processHierarchy=processHierarchy)
	setFingerprintAttributes(attributes, nodeId, name, user, processHierarchy, pathFromProcess, pathFromAnalysis, pathFromFilesystem, parsedArgContext)
	return (nodeId, pid, ppid)


def getValuableFingerprints(runtime, nodeId, resultList, resultDictionary, trackResults, osType, discoverPaths, excludedProcessList=None, processIgnoreList=[]):
	"""Track attributes for processes considered interesting/valuable thus far."""
	runtime.logger.report('Creating valuable fingerprints for {osType!r} processes', osType=osType)
	for entry in resultList:
		try:
			attributes = {}
			(nodeId, pid, ppid) = getFingerprintAttributes(runtime, resultList, entry, osType, attributes, excludedProcessList, processIgnoreList, resultDictionary)
			if trackResults:
				processFingerprintId, exists = runtime.results.addObject('ProcessFingerprint', **attributes)
				resultDictionary[pid] = (attributes, ppid, processFingerprintId)
				## Using the nodeId from the process, since we could be dealing
				## with a single Host that has multiple containers/zones/nodes
				## running under the process listing; link in the correct Node.
				runtime.results.addLink('Enclosed', nodeId, processFingerprintId)
			else:
				resultDictionary[pid] = (attributes, ppid, None)
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in getValuableFingerprints: {stacktrace!r}', stacktrace=stacktrace)

	## end getValuableFingerprints
	return


def getFilteredFingerprints(runtime, nodeId, resultList, resultDictionary, osType, discoverPaths, excludedProcessList, processIgnoreList):
	"""Track attributes for processes already filtered out.

	Some packages need the full heirarchy/tree and not just the flat list, even
	when they were "filtered out"; I need to be able to follow the trail.
	"""
	runtime.logger.report('Creating filtered fingerprints for {osType!r} processes', osType=osType)
	for entry in excludedProcessList:
		try:
			attributes = {}
			(nodeId, pid, ppid) = getFingerprintAttributes(runtime, resultList, entry, osType, attributes, excludedProcessList, processIgnoreList, resultDictionary, "Filtered ")
			resultDictionary[pid] = (attributes, ppid, None)
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in getFilteredFingerprints: {stacktrace!r}', stacktrace=stacktrace)

	## end getFilteredFingerprints
	return


def buildProcessDictionary(runtime, nodeId, resultList, resultDictionary, trackResults, osType, discoverPaths, includeFilteredProcesses=False, excludedProcessList=None, processIgnoreList=[]):
	"""Construct a result dictionary out of process fingerprints."""
	runtime.logger.report('Building process dictionary')
	## Track attributes from a process considered interesting thus far
	getValuableFingerprints(runtime, nodeId, resultList, resultDictionary, trackResults, osType, discoverPaths, excludedProcessList, processIgnoreList)
	## Track attributes for all processes already filtered out
	if includeFilteredProcesses:
		getFilteredFingerprints(runtime, nodeId, resultList, resultDictionary, osType, discoverPaths, excludedProcessList, processIgnoreList)

	## end buildProcessDictionary
	return


def needToTrackThisProcess(runtime, osType, name, filters=None, processFilterPidList=None, processId=None, processFilterIncludeList=None, processFilterIncludeCompare='=='):
	"""Determine whether this process is worth keeping.

	Similar to Software discovery, we can have both include and exclude filters.
	The include filters may be provided when invoked from scripts that are only
	concerned with certain types of processes (eg. I only want processes with
	certain text in the command line). If an inclusion string is not provided,
	we fall back to the exclude list. And it basically includes everything that
	is standard OS issued, or that the customer adds to the list as something
	unimportant (e.g. I don't want to track backup or log monitor processes).

	Priority of parsing:
	  1. PID list. This parsing is used by jobs that look for PIDs on demand
	     (e.g. DB or dynamic remote); allows the script to track based on PIDs.
	  2. Include list. This parsing is used by by 1-to-1 technology-specific
	     jobs that need to look at processes of a certain type (e.g. all apache
	     or IIS processes or all jboss processes); allows the script to track
	     based on a provided list of named processes.
	  3. Exclude lists. This is the standard parsing method; allows the script
	     to track anything that isn't filtered out by whatever is believed to
	     be un-interesting. There are multiple exclude lists: a) the manually
	     defined list per OS (regex), and b) the automatically constructed list
	     created for the config group (==).
	"""
	## Ensure this isn't a kernel or OS level process
	if (isTopLevelProcess(runtime, osType, processId, name)):
		return False

	## First priority is to use PIDs instead of names
	if processFilterPidList is not None and len(processFilterPidList) > 0:
		for thisPID in processFilterPidList:
			if str(processId) == str(thisPID):
				return True
		return False

	## Second priority is to use an include list
	if processFilterIncludeList is not None and len(processFilterIncludeList) > 0:
		for matchExp in processFilterIncludeList:
			if (matchExp is None or len(matchExp) <= 0):
				continue
			## Enable regEx instead of just exact matches
			searchString = matchExp.strip()
			if compareFilter(processFilterIncludeCompare, searchString, name):
				runtime.logger.report('  process {processName!r} matched processFilterIncludeList search string {searchString!r}', processName=name, searchString=searchString)
				return True
		return False

	## Third priority is to use exclusion lists, which is the standard usage
	if filters is None:
		runtime.logger.report(' The function osProcess.needToTrackThisProcess was not provided filters; tracking all processes...')
		return True
	if not filters.get('processFilterFlag', False):
		runtime.logger.report(' processFilterFlag is False; tracking all processes...')
		return True
	## Exclusion list constructed by config group (compare operator is '==')
	for avoidProcess in filters['processFilterExcludeList']:
		if (avoidProcess is None or len(avoidProcess) <= 0):
			continue
		if compareFilter(filters['processFilterExcludeCompare'], avoidProcess, name):
			runtime.logger.report('  process {processName!r} matched processFilterExcludeList search string {avoidProcess!r}', processName=name, avoidProcess=avoidProcess)
			return False
	## Exclusion list defined per OS (compare operator is normally 'regex')
	for avoidProcess in filters['processFilterExcludeOsList']:
		if (avoidProcess is None or len(avoidProcess) <= 0):
			continue
		if compareFilter(filters['processFilterExcludeOsCompare'], avoidProcess, name):
			runtime.logger.report('  process {processName!r} matched processFilterExcludeOsList search string {avoidProcess!r}', processName=name, avoidProcess=avoidProcess)
			return False

	## end needToTrackThisProcess
	return True


def isTopLevelProcess(runtime, osType, pid, name):
	"""Ensure this isn't a 'top level process'.

	Processes that fall into that category are those at the kernel level, the
	daemon or service-level, or an OS manager level (like the Windows system
	explorer or a Linux gnome shell). When we hit those, we want to stop
	tracking and/or accumulating the process tree.
	"""
	if (pid is not None):
		if (pid == 0 or pid == 1 or pid == 4):
			runtime.logger.report('   Process is a top level process ({processName!r} [PID: {pid!r}]).', processName=name, pid=pid)
			return True
	if (name is not None):
		## Samples of topLevelProcess; defined in osParameters:
		##   Windows: ["explorer.exe", "services.exe", "wininit.exe", "system"]
		##   Linux: ["init", "sshd", "gnome-shell"]
		if name.lower() in runtime.endpoint.get('data').get('parameters').get('topLevelProcess', []):
			runtime.logger.report('   Process is a top level process ({processName!r} [PID: {pid!r}]).', processName=name, pid=pid)
			return True

	## end isTopLevelProcess
	return False


def isValidProcessAndIsNotTopOsProcess(runtime, targetPID, targetName, processDictionary, pidTrackingList, osType):
	"""Find out if we should follow this process; uses dictionary format."""
	## Make sure we want to pursue this process (or parent)
	if (targetPID is None):
		runtime.logger.report(' Process PID is None')
		return False

	## Ensure this isn't a kernel or OS level process
	if (isTopLevelProcess(runtime, osType, targetPID, targetName)):
		return False

	## Check if the process is on the dictionary sent in
	if (not int(targetPID) in processDictionary.keys()):
		runtime.logger.report(' Process not found for PID ({pid!r}) with name ({processName!r}); it may have just terminated.', pid=targetPID, processName=targetName)
		runtime.logger.report('    for reference: PID keys: {processPIDs!r}', processPIDs=processDictionary.keys())
		return False

	## OS can have the same parent process ID as the child (sad but true)
	if ((len(pidTrackingList) > 0) and (targetPID in pidTrackingList)):
		runtime.logger.report('  Process ({processName!r} with PID {pid!r}) has a circular dependency (same parent/child PID). Do not continue \'up the process tree\'.', processName=targetName, pid=targetPID)
		return False
	else:
		## Track previously processed PIDs; in some cases a process can
		## have the same PID as PPID, which obviously would cause an
		## infinite loop. Solaris does this seemingly by design, perhaps
		## due to zones, but I've seen it on Linux and Windows as well.
		pidTrackingList.append(targetPID)

	## end isValidProcessAndIsNotTopOsProcess
	return True


def isValidProcessAndIsNotTopOsProcessWithList(runtime, targetPID, targetName, processList, pidTrackingList, osType):
	"""Find out if we should follow this process; uses List format."""
	## Make sure we want to pursue this process (or parent)
	if (targetPID is None):
		runtime.logger.report('   Process PID is None')
		return False

	## Ensure this isn't a kernel or OS level process
	if (isTopLevelProcess(runtime, osType, targetPID, targetName)):
		return False

	## Check if process is on the list sent in
	matched = False
	for entry in processList:
		with suppress(Exception):
			pid = None
			(hostId, user, pid, name, ppid, commandLine, pathFromProcess, pathFromAnalysis, pathFromFilesystem, args, parsedArgs) = entry
			if (targetPID == pid):
				matched = True
				break
	if (not matched):
		runtime.logger.report('   Process not found for PID ({pid!r}) with name ({processName!r}); it may have just terminated.', pid=targetPID, processName=targetName)
		return False

	## OS can have the same parent process ID as the child (sad but true)
	if ((len(pidTrackingList) > 0) and (targetPID in pidTrackingList)):
		runtime.logger.report('   Process ({processName!r} with PID {pid!r}) has a circular dependency (same parent/child PID). Do not continue \'up the process tree\'.', processName=targetName, pid=targetPID)
		return False
	else:
		## Track previously processed PIDs; in some cases a process can
		## have the same PID as PPID, which obviously would cause an
		## infinite loop. Solaris does this seemingly by design, perhaps
		## due to zones, but I've seen it on Linux and Windows as well.
		pidTrackingList.append(targetPID)

	## end isValidProcessAndIsNotTopOsProcessWithList
	return True


def buildProcessHierarchy(runtime, nextPID, osType, processList, excludedProcessList, processIgnoreList=[]):
	"""Find all named processes in this process stack."""
	processTree = []
	processTreeAsString = None
	pidTrackingList = []
	foundParent = True
	while (foundParent):
		foundParent = False
		## First look in the processes that weren't filtered out
		for entry in processList:
			try:
				(hostId, user, pid, name, ppid, commandLine, pathFromProcess, pathFromAnalysis, pathFromFilesystem, args, parsedArgs) = entry
				if (nextPID == pid):
					if (not isValidProcessAndIsNotTopOsProcessWithList(runtime, nextPID, name, processList, pidTrackingList, osType)):
						break
					## If a process in the ignoreProcessList is located in the
					## middle of the tree, we want to join the top/bottom portions,
					## which is why I continue parsing and just leave this name
					## out of the appended processTree.
					nextPID = ppid
					foundParent = True
					if (name in processIgnoreList):
						break
					labelToAdd = str(name)
					if parsedArgs is not None:
						labelToAdd = '{}:{}'.format(str(name), str(parsedArgs))
					processTree.append(labelToAdd)
					#processTree.append(str(name))
					break
			except:
				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				runtime.logger.error('Exception in buildProcessHierarchy: {stacktrace!r}', stacktrace=stacktrace)
		if foundParent or excludedProcessList is None:
			continue
		## Otherwise, see if the parent process was filtered out
		for entry in excludedProcessList:
			try:
				(hostId, user, pid, name, ppid, commandLine, pathFromProcess, pathFromAnalysis, pathFromFilesystem, args, parsedArgs) = entry
				if (nextPID == pid):
					if (not isValidProcessAndIsNotTopOsProcessWithList(runtime, nextPID, name, excludedProcessList, pidTrackingList, osType)):
						break
					nextPID = ppid
					foundParent = True
					labelToAdd = str(name)
					if parsedArgs is not None:
						labelToAdd = '{}:{}'.format(str(name), str(parsedArgs))
					processTree.append(labelToAdd)
					#processTree.append(str(name))
					break
			except:
				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				runtime.logger.error('Exception in buildProcessHierarchy: {stacktrace!r}', stacktrace=stacktrace)
	## Create a custom string right now, instead of keeping as a list/array type
	## Later I want to convert this over when I build out the ORM methods, for
	## enabling queries for 'contains' of shared processes in this attribute.
	## Need to reverse the list so that the parent appears before the child...
	processTree.reverse()
	for entry in processTree:
		if processTreeAsString is None:
			processTreeAsString = entry
		else:
			processTreeAsString = processTreeAsString + ', ' + entry

	## end buildProcessHierarchy
	return processTreeAsString


def setFingerprintAttributes(attributes, nodeId, name, user, processHierarchy, pathFromProcess=None, pathFromAnalysis=None, pathFromFilesystem=None, parsedArgContext=None):
	"""Track attributes for the ProcessFingerprint object.

	This represents a process running on a Node (OS instance). It tracks a
	particular set of attributes that helps identify the same process across
	changes in the runtime. Consider worker processes in a web server that
	spin up/down based on traffic, or processes with subtle differences in the
	runtime parameters (like the thread or process ids), or even just a simple
	restart of the server or container that changes all process ids.

	Unique Constraints for ProcessFingerprint objects:
	  container
	  name
	  process_hierarchy
	  process_owner
	  process_args
	  path_from_process
	  path_from_filesystem
	  path_from_analysis
	"""
	attributes['name'] = name
	attributes['process_owner'] = user
	## Parsed context from arguments (intentionally not fully tracked)
	if (parsedArgContext and len(parsedArgContext) > 0):
		attributes['process_args'] = parsedArgContext[:255]

	## Path from the basic/initial process listing
	if (pathFromProcess and len(pathFromProcess) > 0):
		attributes['path_from_process'] = pathFromProcess[:255]

	## Path from /proc filesystem (on Linux and Solaris)
	if (pathFromFilesystem and len(pathFromFilesystem) > 0):
		attributes['path_from_filesystem'] = pathFromFilesystem[:255]

	## Path from the resolution of 8dot3 on Windows or symbolic links on Unix
	if (pathFromAnalysis and len(pathFromAnalysis) > 0):
		attributes['path_from_analysis'] = pathFromAnalysis[:255]

	attributes['process_owner'] = 'N/A'
	if (user and len(user) > 0):
		attributes['process_owner'] = user

	attributes['process_hierarchy'] = 'N/A'
	if (processHierarchy and len(processHierarchy) > 0):
		attributes['process_hierarchy'] = processHierarchy[:511]

	## end setFingerprintAttributes
	return


def snipLongProcessStrings(var):
	"""Keep only 2400 chars of long process args.

	Some processes (e.g. java) can have extremely long command line args. Since
	the unique parts of the args are usually on the start and end, we need a
	better way than string truncation to reduce the number of characters while
	preserving process arg uniqueness.
	"""
	## For anything over 2400 characters plus our [snip] indicator string:
	if (var and len(var) > 2416):
		saveVar = var
		## Keep the first 1200 characters and the last 1200
		var = concatenate(saveVar[:1200], '...[snip]...', saveVar[-1200:])

	return var


def parseParams(runtime, name, args):
	"""Parse process args to find additional context."""
	## Currently only enabled for java processes, but could be wrapped in case
	## we need to build this out in the future to extend to other general types.
	if (re.search('java', name, re.I)):
		return (parseJavaParams(runtime, name, args))

def stripFirstSection(runtime, context):
	m = re.search('^(\s*\"[^\"]+\")(.*)', context)
	if m:
		if re.search('java(?:\.exe){0,1}\"{0,1}', m.group(1)):
			runtime.logger.report('   Java 1 removed: {group!r}', group=m.group(1))
			return m.group(2)
	m = re.search('^\s*(\S+)\s(.*)', context)
	if m:
		if re.search('java(?:\.exe){0,1}\"{0,1}', m.group(1)):
			runtime.logger.report('   Java 2 removed: {group!r}', group=m.group(1))
			return m.group(2)
	return context

def stripStandAloneSection(runtime, label, context):
	## two quotes together, followed by a space (empty value)
	m = re.search('^(\s*\"\")\s(.*)', context)
	if m:
		runtime.logger.report('   removing empty value: {label!r}: {group!r}', label=label, group=m.group(1))
		return m.group(2)
	## multiple quotes together - treat as one
	m = re.search('^(\s*\"\"+[^\"]*\")(.*)', context)
	if m:
		runtime.logger.report('   removing multiple quoted entry: {label!r}: {group!r}', label=label, group=m.group(1))
		newSection = m.group(2)
		if len(newSection) > 0 and not re.search('\s', newSection[0]):
			## found a set of quoted entries
			newSection = continueStripThruJoinChars(runtime, newSection)
		return newSection
	## single quote followed by data
	m = re.search('^(\s*\"[^\"]*\")\s(.*)', context)
	if m:
		runtime.logger.report('   removing single quoted entry: {label!r}: {group!r}', label=label, group=m.group(1))
		return m.group(2)
	## regular entry
	m = re.search('^(\s*\S+)(.*)', context)
	if m:
		runtime.logger.report('   removing entry: {label!r}: {group!r}', label=label, group=m.group(1))
		return m.group(2)
	return

def continueStripThruJoinChars(runtime, context):
	count = 0
	for char in context:
		runtime.logger.report('   continueStripThruJoinChars: looking at char [{char!r}]', char=char)
		if re.search('\s', char):
			context = context[count+1:]
			break
		elif re.search('\"', char):
			context = context[count:]
			runtime.logger.report('   continueStripThruJoinChars: calling stripInlineSection on: {context!r}', context=context)
			return stripInlineSection(runtime, "RECURSED QUOTED STRING", context)
		count += 1
	return context

def stripInlineSection(runtime, label, context):
	"""Parse an inline parameter section.

	Keep in mind that the parameters may not be well formatted. So we try to
	positionally parse by splitting on spaces, but fall back to string parsing.

	Consider this example on Windows, with a quoted properties file and a mix
	quoted class path (i.e. starts with a double quote, then has enclosed double
	quotes, and ends with two double quotes):

	java.exe -Xmx1G -Xms1G -server -XX:+UseG1GC -XX:MaxGCPauseMillis=20
	  -XX:InitiatingHeapOccupancyPercent=35 -XX:+ExplicitGCInvokesConcurrent
	  -Djava.awt.headless=true -Dcom.sun.management.jmxremote
	  -Dcom.sun.management.jmxremote.authenticate=false
	  -Dcom.sun.management.jmxremote.ssl=false
	  -Dkafka.logs.dir="E:\\Software\\kafka_2.12-2.3.0/logs"
	  "-Dlog4j.configuration=file:E:\\Software\\kafka_2.12-2.3.0\\bin\\windows\\../../config/log4j.properties"
	  -cp "C:\\tmp;"E:\\kafka\\libs\\activation-1.1.1.jar";"E:\\kafka\\libs\\aopalliance-repackaged-2.5.0.jar";...;"E:\\kafka\\libs\\zstd-jni-1.4.0-1.jar""
	  kafka.Kafka .\\config\\server.properties
	"""
	argv = context.split()
	if re.search('\"', argv[0]):
		## There's a quoted string; go back to string parsing
		newSection = stripStandAloneSection(runtime, label, context)
		if newSection is None:
			raise EnvironmentError('Unmatched quotes found in arg parsing at: {}'.format(context))
		return newSection
	## Otherwise it's safe to assume we can split on spaces
	argv.pop(0)
	return ' '.join(argv)

def parseJavaParams(runtime, name, argvAsString):
	"""Parse Java process args to find main entry point."""
	parsedName = None
	try:
		argvAsString = argvAsString.strip()
		argvAsString = stripFirstSection(runtime, argvAsString)

		## Look for ' -jar <jarName>'
		m3 = re.search(' -jar (\S+)', argvAsString)
		if m3:
			parsedName = m3.group(1)
			return parsedName

		## If no -jar option, look for the first positional parameter
		## To do this, we need to skip all known options
		while len(argvAsString) > 0:
			runtime.logger.report(' parseJavaParams --> argvAsString: {argvAsString!r}', argvAsString=argvAsString)
			argvAsString = argvAsString.strip()
			## Starts with a hyphen, so probably an option
			if re.search('^-.*', argvAsString):
				## These are java options space-delimited for value
				m = re.search('^-cp\s+(\S+.*)', argvAsString, re.I)
				if m:
					argvAsString = stripStandAloneSection(runtime, 'CP', m.group(1))
					continue
				m = re.search('^-classpath\s+(\S+.*)', argvAsString, re.I)
				if m:
					argvAsString = stripStandAloneSection(runtime, 'CLASSPATH', m.group(1))
					continue
				## Standard java options, single strings
				matched = False
				skipOpts = ['^-D.*', '^-X.*', '^-server', '^-verbose', '^-ea', '^-enableassertions', '^-da', '^-disableassertions', '^-esa', '^-enablesystemassertions', '^-dsa', '^-disablesystemassertions', '^-agentlib:', '^-agentpath:', '^-javaagent:', '^-splash:']
				for opt in skipOpts:
					if re.search(opt, argvAsString, re.I):
						matched = True
						argvAsString = stripInlineSection(runtime, opt, argvAsString)
						break
				if matched:
					continue
			## Starts with a quote; could be a properties file or something else
			elif re.search('^".*', argvAsString):
				## not really sure what to assume here, so skip
				argvAsString = stripStandAloneSection(runtime, 'QUOTED STRING', argvAsString)
				continue

			## If we get here, it should be the first positional parameter
			## on the command line, which should be the java class name
			argv = argvAsString.split()
			parsedName = argv[0]
			runtime.logger.report(' parseJavaParams --> parsedName {parsedName!r}', parsedName=parsedName)
			break
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in parseJavaParams: {stacktrace!r}', stacktrace=stacktrace)

	## end parseJavaParams
	return parsedName


## This is fine on Linux, but has alot of gaps on Windows with quotes being
## intermixed through parameters; so changed list parsing to string parsing.
## Leaving in as a reminder in case someone heads this direction in the future.
# def parseJavaParams(runtime, name, argvAsString):
# 	"""Parse Java process args to find main entry point."""
# 	parsedName = None
# 	try:
# 		runtime.logger.report(' parseJavaParams --> argvAsString {argvAsString!r}', argvAsString=argvAsString)
# 		argv = argvAsString.split()
# 		numberOfArgs = len(argv)
# 		argStartPosition = 0
# 		## Some OS results will not have process name in the argv
# 		if (re.search('java\"*$', argv[0], re.I) or re.search('java\.exe\"*$', argv[0], re.I)):
# 			argStartPosition += 1
#
# 		## Iterate through this twice; some Java cmd lines can have positional
# 		## arguments before a -jar jarName (e.g. solr search with a TCP port)
# 		x = argStartPosition
# 		while x < numberOfArgs:
# 			try:
# 				param = argv[x]
# 				if re.search('^-jar$', param, re.I):
# 					x += 1
# 					parsedName = argv[x]
# 					runtime.logger.report(' parseJavaParams --> parsedName {parsedName!r}', parsedName=parsedName)
# 					return parsedName
# 			except:
# 				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
# 				runtime.logger.error('Exception in parseJavaParams: {stacktrace!r}', stacktrace=stacktrace)
# 			x += 1
#
# 		## If no -jar option, look for the first positional parameter
# 		x = argStartPosition
# 		while x < numberOfArgs:
# 			found = False
# 			try:
# 				param = argv[x]
# 				## Standard java options, space delimited for value
# 				skipParams = ['^-cp', '^-classpath']
# 				for opt in skipParams:
# 					if re.search(opt, param, re.I):
# 						x += 1
# 						found = True
# 						break
# 				if found:
# 					x += 1
# 					continue
# 				## Standard java options, single strings
# 				skipOpts = ['^-D.*', '^-X.*', '^-server', '^-verbose', '^-ea', '^-enableassertions', '^-da', '^-disableassertions', '^-esa', '^-enablesystemassertions', '^-dsa', '^-disablesystemassertions', '^-agentlib:', '^-agentpath:', '^-javaagent:', '^-splash:']
# 				for opt in skipOpts:
# 					if re.search(opt, param, re.I):
# 						found = True
# 						break
# 				if found:
# 					x += 1
# 					continue
# 				## Try to account for future options?
# 				if re.search('^-.*', param):
# 					x += 1
# 					continue
# 				## If we get here, it should be the first positional parameter
# 				## on the command line, which should be the java class name
# 				parsedName = param
# 				runtime.logger.report(' parseJavaParams --> parsedName {parsedName!r}', parsedName=parsedName)
# 				break
#
# 			except:
# 				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
# 				runtime.logger.error('Exception in parseJavaParams: {stacktrace!r}', stacktrace=stacktrace)
# 				x += 1
# 	except:
# 		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
# 		runtime.logger.error('Exception in parseJavaParams: {stacktrace!r}', stacktrace=stacktrace)
#
# 	## end parseJavaParams
# 	return parsedName

## The old way of parsing for 1-to-1 matches needs redone by some learning
## algorithms that can run analytics after the fingerprints are created.
# def parseProcessArgsForProduct(productName, procOshDict, targetPID):
# 	"""Parse the process args to find a better name.
# 
# 	Obsolete. Use parseParams(name, args) instead.
# 	"""
# 	## May not have a product name if forced to create
# 	if (procOshDict[int(targetPID)].getAttribute('process_parameters')):
# 		processArgs = procOshDict[int(targetPID)].getAttribute('process_parameters').getValue().strip()
# 		if (processArgs and len(processArgs) > 0):
# 			## Blocks to pull content from process arguments
# 
# 			## Websphere java processes:
# 			websphereM1 = re.search("java.*\scom\.[.\S]+\.([^.\s]+)\s", processArgs)
# 			if websphereM1:
# 				productName = websphereM1.group(1)
# 
# 			## Weblogic java processes:
# 			## -Dbea.home=/app/weblogic/location
# 			weblogicM1 = re.search("-Dbea.home=\s*(\S+)\s", processArgs)
# 			if weblogicM1:
# 				productName = weblogicM1.group(1)
# 			## -Dweblogic.home=/app/weblogic/location
# 			weblogicM2 = re.search("-Dweblogic.home=\s*(\S+)\s", processArgs)
# 			if weblogicM2:
# 				productName = weblogicM2.group(1)
# 
# 			## Insert others as needed...
# 
# 	## parseProcessArgsForProduct
# 	return productName


def getFullyQualifiedProcessName(runtime, pid, osType, client):
	"""Lookup process path given a PID.

	This function looks up the process path from root using the operating
	system. Its required to find the path for anything that was launched
	with a relative path when the command line is inaccurate, which happens.
	It's a distinct function because looking this up for all processes is
	expensive and should be done in one place for efficiency. The default
	behavior is that Application Components will gather this information.

	NOTE - sometimes the command line is wrong - including the process name,
	which is the last element of the path. We need the correct information
	and we gather it for the path. However, the name at this point will be
	created from the command line and its wrong in some cases.
	"""

	if (osType == 'Windows'):
		fqProcessName = windowsGetFullyQualifiedProcessName(runtime, pid, client, osType)
	if (osType == 'Linux'):
		fqProcessName = linuxGetFullyQualifiedProcessName(runtime, client, pid)
	if (osType == 'HPUX'):
		pass
	if (osType == 'Solaris'):
		#fqProcessName = solarisGetFullyQualifiedProcessName(runtime, pid, client, osType)
		pass
	if (osType == 'AIX'):
		#fqProcessName = aixGetFullyQualifiedProcessName(runtime, pid, client, osType)
		pass

	## end getFullyQualifiedProcessName
	return fqProcessName


def uxResolveSymbolicLinks(runtime, client, osType, resultList):
	"""Attempt to follow all symbolic links to their destination files."""
	updatedResultList = []
	## Go through each process entry
	for entry in resultList:
		(user, pid, name, ppid, commandLine, processPath, resolvedPath, filesystemPath, args, parsedArgs) = entry
		## Attempt to update the resolved path attribute
		resolvedPath = uxResolveSymbolicLink(runtime, client, pid, name, processPath, filesystemPath)
		updatedResultList.append((user, pid, name, ppid, commandLine, processPath, resolvedPath, filesystemPath, args, parsedArgs))

	## end uxResolveSymbolicLinks
	return updatedResultList


def uxResolveSymbolicLink(runtime, client, pid, processName, processPath, filesystemPath):
	"""Attempt to follow a single symbolic link to the destination file.

	Currently no virtual context parsed (eg. zone, domain), so default the
	node for ProcessFingerprint as the hostId sent into main function.
	"""
	resolvedPath = None
	try:
		## Get the path to resolve (prefer the filesystemPath when available)
		pathToResolve = processPath
		if (filesystemPath is not None and len(filesystemPath) > 0 and filesystemPath[0] == '/'):
			pathToResolve = filesystemPath
		if (pathToResolve is None or len(pathToResolve) <= 0 or pathToResolve[0] != '/'):
			## Nothing to do if a valid path wasn't found
			return None

		## Prefer the Perl method, which follows more than one level deep
		commandsToTransform = runtime.endpoint.get('data').get('parameters').get('commandsToTransform', {})
		if 'perl' in commandsToTransform:
			command = updateCommand(runtime, 'perl -MCwd -e \'print Cwd::realpath($ARGV[0])\' {}'.format(pathToResolve))
			(outputString, stderr, hitProblem) = client.run(command, 3)
			runtime.logger.report('Output from resolving potential symbolic link via PERL: {outputString!r}', outputString=outputString)
			if (not hitProblem and outputString is not None and len(outputString) > 0):
				try:
					outputString = outputString.strip()
					m = re.search('^\s*(/.*)\s*$', outputString)
					if (m):
						resolvedPath = m.group(1)
						runtime.logger.report(' Updating process {processName!r}:{pid!r} with starting path {processPath!r} to resolved path {resolvedPath!r} using PERL command', processName=processName, pid=pid, processPath=pathToResolve, resolvedPath=resolvedPath)
				except:
					stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					runtime.logger.error('Exception in uxResolveSymbolicLink with PERL parsing: {stacktrace!r}', stacktrace=stacktrace)

		## If that failed, try the simple directory listing method
		if (resolvedPath is None):
			command = updateCommand(runtime, 'ls -l {}'.format(pathToResolve))
			(outputString, stderr, hitProblem) = client.run(command, 5)
			runtime.logger.report('Output from resolving potential symbolic link via LS: {outputString!r}', outputString=outputString)
			if (not hitProblem and outputString is not None and len(outputString) > 0):
				try:
					outputString = outputString.strip()
					m = re.search('^\s*(/.*)\s+->\s+(\S+)\s*$', outputString)
					if (m):
						resolvedPath = m.group(2)
						if resolvedPath[0] != '/':
							## The symbolic link is pointing to a file in the
							## same directory as the link; add the path back on:
							##   lrwxrwxrwx 1 root root 2 Apr 30  2018 /usr/bin/xzcat -> xz
							## Because we want '/usr/bin/xz' and not just 'xz'
							m = re.search('^(.*/)[^/]+\s*$', pathToResolve)
							if m:
								resolvedPath = '{}{}'.format(m.group(1), resolvedPath)
						runtime.logger.report(' Updating process {processName!r}:{pid!r} with starting path {processPath!r} to resolved path {resolvedPath!r} using LS command', processName=processName, pid=pid, processPath=pathToResolve, resolvedPath=resolvedPath)
				except:
					stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					runtime.logger.error('Exception in uxResolveSymbolicLink with LS parsing: {stacktrace!r}', stacktrace=stacktrace)
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in uxResolveSymbolicLink: {stacktrace!r}', stacktrace=stacktrace)

	## end uxResolveSymbolicLink
	return resolvedPath


def uxGetProcessPath(fullyQualifiedProcessName):
	"""Split out path from process name."""
	processPath = None
	tmpObject = os.path.split(fullyQualifiedProcessName)
	tmpStr = tmpObject[0]
	if (tmpStr != None):
		os.path.normpath(tmpStr)
		seperator = '/'
		tmpPath = None
		splitString = tmpStr.split("\\") or None
		if (splitString != None):
			for piece in splitString:
				if (tmpPath == None):
					tmpPath = piece
				else:
					tmpPath = '{}{}{}'.format(tmpPath, seperator, piece)
			processPath = tmpPath

	## end uxGetProcessPath
	return processPath

###############################################################################
############################  END GENERAL SECTION  ############################
###############################################################################


###############################################################################
###########################  BEGIN WINDOWS SECTION  ###########################
###############################################################################

############################################
##  Parse Windows Process in List format  ##
############################################
def windowsGetProcess(runtime, osType, nodeId, line, errorCount, resultList, excludedProcessList, filters, processFilterIncludeList, processFilterPidList, newSeparator=None):
	"""Parse Windows Process in List format.

	Sample output...
	========================================================================
	Process name|PID|PPID|ExecutablePath|CommandLine|User
	TrustedInstaller.exe|4636|624|C:\Windows\servicing\TrustedInstaller.exe|C:\Windows\servicing\TrustedInstaller.exe|SYSTEM
	cmd.exe|5824|3224|C:\Windows\System32\cmd.exe|"C:\Windows\System32\cmd.exe" |Administrator
	jucheck.exe|6336|3288|C:\Program Files (x86)\Common Files\Java\Java Update\jucheck.exe|"C:\Program Files (x86)\Common Files\Java\Java Update\jucheck.exe" -auto -critical|Administrator
	iexplore.exe|4860|5160|C:\Program Files (x86)\Internet Explorer\iexplore.exe|"C:\Program Files (x86)\Internet Explorer\iexplore.exe" SCODEF:5160 CREDAT:145409|Administrator
	powershell.exe|4420|3224|C:\WINDOWS\system32\WindowsPowerShell\v1.0\powershell.exe|"C:\WINDOWS\system32\WindowsPowerShell\v1.0\powershell.exe" |Administrator
	========================================================================
	"""
	try:
		separator = "|"
		if newSeparator is not None:
			separator = newSeparator
		runtime.logger.report('  Windows Process to split: {line!r}', line=line)
		(name, pid, ppid, path, commandLine, user) = line.split(separator)
		args = None
		parsedArgs = None

		## Strip 'cmd /c' command prefix from the commandLine, when exists,
		## and take the Path from WMI instead of trying to interpret spaces
		m = re.search("(?:cmd(?:\s*/c)*\s)*(.*)", commandLine)
		if m:
			commandLine = m.group(1)

		## Check to see if it is part of the exclusions, to filter out
		if (needToTrackThisProcess(runtime, osType, name, filters, processFilterPidList, pid, processFilterIncludeList)):
			## Clean up this type of path: \??\C:\WINDOWS\system32\winlogon.exe
			m = re.search(r'[\\]\?\?[\\](\S.*)', path)
			if m:
				path = m.group(1)

			## Special formatting for shell script invocation; need to
			## retain visibility to the actual script names from the args,
			## since resolving ownership from shell interpreters (e.g. perl,
			## powershell, python, cygwin, mks) works against this type of
			## dyanamic discovery.  For example, the following hierarchy...
			##   ['hpbsm_opr-backend', 'sh', 'sh', 'nannyManager', 'wrapper']
			## would stop at 'sh', and resolve to 'GNU Bourne Again Shell',
			## which would actually only track the following hierarchy:
			##   ['sh', 'sh', 'nannyManager', 'wrapper']
			## when we need it to resolve either at the HP components or not
			## at all. And if we choose not at all, then we should have a
			## better qualified hierarchy value in the process fingerprint
			## object; something like the following is much more helpful:
			##   ['sh:opr-backend_run', 'sh:service_manager.sh', 'nannyManager', 'wrapper']
			## This allows the user to pattern-match interpreter scripts.
			if (commandLine is not None and len(commandLine) > 0):
				try:
					runtime.logger.report('  windowsGetProcess: commandLine: {commandLine!r}', commandLine=commandLine)
					## Sample interpreters: sh, bash, tcsh, ksh, zsh, fish, perl
					for interpreter in filters['interpreterList']:
						#if (re.search(concatenate(r'^(?:.*)', interpreter, '(?:\.exe)?(?:[\"])?\s*$'), name)):
						if (re.search(r'^(?:.*)'+interpreter+'(?:\.exe)?(?:[\"])?\s*$', name)):
							runtime.logger.report('  windowsGetProcess: found interpreter: {interpreter!r}', interpreter=interpreter)
							## If the first parameter after the interpreter is a path or
							## alphabetical character (specifically not a dash or slash
							## option), assume it's worth retaining (e.g. a script name)
							m = re.search(r'^(?:.*)('+interpreter+')(?:\.exe)?(?:[\"])?\s+(?:[\"])?(\S+)(?:[\"])?', commandLine)
							if m:
								interpreterMatch = m.group(1)
								processArg = m.group(2)
								runtime.logger.report('  windowsGetProcess: looking at args: {processArg!r}', processArg=processArg)
								m = re.search('^\s*([\.a-zA-Z]\S+)', processArg)
								if (m):
									script = m.group(1)
									runtime.logger.report('  windowsGetProcess: found arg: {script!r}', script=script)
									m1 = re.search(r'^(.*?)([^/\\]+)$', script)
									## Check for script names with preceeding paths
									if (m1):
										script = m1.group(2)
									#name = '{}:{}'.format(interpreter, script[:30])
									runtime.logger.report('Changing interpreterProcess: {name!r} --> {newName!r}', name=name, newName='{}:{}'.format(interpreterMatch, script[:30]))
									#name = '{}:{}'.format(interpreterMatch, script[:30])
									parsedArgs = script[:256]
									runtime.logger.report('  windowsGetProcess: clean arg: {parsedArgs!r}', parsedArgs=parsedArgs)

								break

				except:
					stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					runtime.logger.error('Exception in windowsGetProcess in adding script name: {stacktrace!r}', stacktrace=stacktrace)

			runtime.logger.report('  Windows process: {pid!r}, {ppid!r}, {name!r}, {user!r}, {path!r}, {commandLine!r}', pid=pid, ppid=ppid, name=name, user=user, path=path, commandLine=commandLine[:256])
			## Add this process to our result list
			resultList.append((nodeId, user, int(pid), name, int(ppid), commandLine, str(path), None, None, commandLine, parsedArgs))
		else:
			runtime.logger.report('   Filtering out process: {pid!r}, \t{ppid!r}, \t{name!r}, \t{user!r}, \t{commandLine!r}', pid=pid, ppid=ppid, name=name, user=user, commandLine=commandLine[:256])
			excludedProcessList.append((nodeId, user, int(pid), name, int(ppid), commandLine, path, None, None, commandLine, parsedArgs))

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		## The powerShell command to gather all our processes of course includes
		## the separator string in the command, which always returns an error;
		## I don't want folks to think these are real issues, hence this block:
		errorMsg = str(sys.exc_info()[1])
		if (errorMsg and not re.search('too many values to unpack', errorMsg, re.I)):
			runtime.logger.error(' Couldn\'t parse line from process listing: {line!r}', line=line)
			runtime.logger.error('    ---> exception was: {stacktrace!r}', stacktrace=stacktrace)
			errorCount = errorCount + 1

	## end windowsGetProcess
	return errorCount


def windowsUpdateThisProcess(runtime, processData, client, objectId):
	"""Update details on a single Windows process.

	This updates the processData dictionary (local version used for reference)
	along with the runtime.results object if they were previously created (which
	is possible if the parameters told the osProcesses library to create them).
	"""
	processPath = processData.get('path_from_process')
	newData = {}
	## Attempt to update the resolved path (on any 8dot3 paths)
	resolvedPath = windowsUpdateProcessResolvedPath(runtime, client, processPath)
	if resolvedPath is not None:
		processData['path_from_analysis'] = resolvedPath
		newData['path_from_analysis'] = resolvedPath

	if objectId is not None and len(newData) > 0:
		runtime.results.updateObject(objectId, **newData)

	## Not dealing with virtual platforms, but we could overwrite nodeId here.

	## end windowsUpdateThisProcess
	return


def windowsUpdateProcessResolvedPath(runtime, client, path):
	"""Update the path of a Windows process."""
	resolvedPath = path
	## Resolve any/all 8dot3 names (short names) to long format
	(updatedPath, stdError, hitProblem) = resolve8dot3Name(runtime, client, path)
	#runtime.logger.report('    conversion returned path: {resolvedPath!r}', resolvedPath=updatedPath.encode('unicode-escape'))
	runtime.logger.report('    conversion returned path: {resolvedPath!r}', resolvedPath=updatedPath)
	if updatedPath != path and updatedPath is not None and not hitProblem:
		resolvedPath = updatedPath
		runtime.logger.report('  Windows Process has updated path. Old value: {processPath!r}, New value: {resolvedPath!r}', processPath=path, resolvedPath=resolvedPath)
	return resolvedPath


def windowsUpdateAllProcesses(runtime, client, osType, resultList, defaultContainerId, discoverPaths, updatedResultList):
	"""Update Windows Processes.

	TODO: Add additional function calls to further update process attributes
	here. Currently no virtual context parsed (eg. zone, domain), so set the
	node for the ProcessFingerprint as the Node sent into the main function.
	Update processes with fully qualified PATH attributes, when neccessary.
	"""
	for entry in resultList:
		(user, pid, name, ppid, commandLine, path, resolvedPath, filesystemPath, args, parsedArgs) = entry
		if discoverPaths:
			resolvedPath = windowsUpdateProcessResolvedPath(runtime, client, path)
		## Add the process onto the updated result list
		updatedResultList.append((defaultContainerId, user, pid, name, ppid, commandLine, path, resolvedPath, filesystemPath, args, parsedArgs))

	## end windowsUpdateAllProcesses
	return updatedResultList


def windowsGetFullyQualifiedProcessName(runtime, pid, client, osType):
	"""Get fully qualified process name for Windows."""
	fullyQualifiedProcessName = None
	rawProcessOutput = client.executeWindowsProcessViaPShell(pid,5000)

	if (rawProcessOutput is not None and len(rawProcessOutput) > 0 and len(rawProcessOutput.strip()) > 0):
		(name, pid, ppid, path, commandLine, user) = rawProcessOutput.split(":==:")

		## Clean up this type of path: \??\C:\WINDOWS\system32\winlogon.exe
		## that was returned from the enhanced PowerShell context
		m = re.search(r'[\\]\?\?[\\](\S.*)', path)
		if m:
			path = m.group(1)
		runtime.logger.report('  Windows process: {pid!r}, {ppid!r}, {name!r}, {user!r}, {path!r}, {commandLine!r}', pid=pid, ppid=ppid, name=name, user=user, path=path, commandLine=commandLine[:256])

		fullyQualifiedProcessName = resolve8dot3Name(runtime, client, path)

	## end windowsGetFullyQualifiedProcessName
	return fullyQualifiedProcessName

###############################################################################
############################  END WINDOWS SECTION  ############################
###############################################################################


###############################################################################
############################  BEGIN LINUX SECTION  ############################
###############################################################################

###########################
##  Parse Linux Process  ##
###########################
def linuxGetProcess(runtime, osType, nodeId, line, errorCount, resultList, excludedProcessList, filters, processFilterIncludeList, processFilterPidList):
	"""Parse Linux Processes.

	Sample output...
	========================================================================
	rpcuser   1731     1 rpc.statd
	root      1830     1 cupsd
	ntp       1930     1 ntpd -U ntp -p /var/run/ntpd.pid
	root      1960     1 [nfsd]
	root      2088     1 smbd -D -d 3
	root      2988  2088 smbd -D -d 3
	myuser    2984  2934 ssh -l Administrator 127.0.0.1
	========================================================================
	"""
	runtime.logger.report('  Linux Process line: {line!r}', line=line)
	## RegEx to match processes with or without args
	m = re.search('^(\S+)\s+(\d+)\s+(\d+)\s+(\S+)\s*((?:\S.*)*)$', line.strip())

	## Update error count if the line doesn't match
	if (not m):
		runtime.logger.report('   could not parse line from ps: {line!r}', line=line)
		errorCount = errorCount + 1
		return errorCount

	user = m.group(1)
	pid = int(m.group(2))
	ppid = int(m.group(3))
	commAndPath = m.group(4)
	cleanArgs = m.group(5) or None

	## Clean up Unix style processes
	(cleanCommand, cleanPath, commandLine, parsedArgs) = cleanUnixProcessCommand(runtime, commAndPath, cleanArgs, filters['interpreterList'])

	## Check to see if it is part of the exclusions, to filter out
	if (needToTrackThisProcess(runtime, osType, cleanCommand, filters, processFilterPidList, pid, processFilterIncludeList)):
		## Add this process to our result list
		runtime.logger.report('  Linux process: {pid!r}, {ppid!r}, {name!r}, {user!r}, {path!r}, {commandLine!r}', pid=pid, ppid=ppid, name=cleanCommand, user=user, path=cleanPath, commandLine=commandLine[:256])
		resultList.append((nodeId, user, pid, cleanCommand, ppid, commandLine, cleanPath, None, None, cleanArgs, parsedArgs))
	else:
		runtime.logger.report('   Filtering out process: {pid!r}, {ppid!r}, {name!r}, {user!r}, {path!r}, {commandLine!r}', pid=pid, ppid=ppid, name=cleanCommand, user=user, path=cleanPath, commandLine=commandLine[:256])
		excludedProcessList.append((nodeId, user, pid, cleanCommand, ppid, commandLine, cleanPath, None, None, cleanArgs, parsedArgs))

	## end linuxGetProcess
	return errorCount


def linuxUpdateAllProcesses(runtime, client, osType, resultList, defaultContainerId, discoverPaths, updatedResultList):
	"""Update Linux processes.

	Use the /proc filesystem to update paths and resolve any symbolic links.
	"""
	if discoverPaths:
		## Use the /proc filesystem to update path attributes
		tempResultList = []
		resultList = linuxParseProcFilesystem(runtime, client, osType, resultList, defaultContainerId, discoverPaths, tempResultList)
		## Track down any and all symbolic links
		resultList = uxResolveSymbolicLinks(runtime, client, osType, resultList)

	## Generic loop to add defaultContainerId
	for entry in resultList:
		(user, pid, name, ppid, commandLine, path, resolvedPath, filesystemPath, args, parsedArgs) = entry
		updatedResultList.append((defaultContainerId, user, pid, name, ppid, commandLine, path, resolvedPath, filesystemPath, args, parsedArgs))

	## Add additional function calls to further update process attributes here

	## end linuxUpdateAllProcesses
	return updatedResultList


def linuxGetCurrentWorkingDir(runtime, client, pid, procName=None):
	"""Get the CWD, reported from the /proc filesystem."""
	cwdPath = None
	## The updateCommand should add --color=never to avoid PTY user preferences
	command = updateCommand(runtime, concatenate('ls -l /proc/', str(pid), '/cwd'))
	(stdout, stderr, hitProblem) = client.run(command, 3)
	if not hitProblem:
		if (len(stdout) > 1):
			line = stdout.strip()
			m = re.search('/proc/(\d+)/cwd\s+->\s+(\S+)\s*$', line)
			if m:
				cwdPath = m.group(2)
			else:
				if procName is not None:
					runtime.logger.report(' Unable to get CWD for {procName!r} with pid {pid!r} from /proc info: {procLine!r}', procName=procName, pid=pid, procLine=line)
				else:
					runtime.logger.report(' Unable to get CWD for process with pid {pid!r} from /proc info: {procLine!r}', pid=pid, procLine=line)
	else:
		## Only report on unexpected failures; specifically drop these two out:
		if (not re.search('cannot read symbolic link', stderr, re.I) and
			not re.search('No such file or directory', stderr, re.I)):
			runtime.logger.error(' Error with {command!r}: {stdout!r}, {stderr!r}, {hitProblem!r}', command=command, stdout=stdout, stderr=stderr, hitProblem=hitProblem)
	if cwdPath is not None:
		runtime.logger.report('  Linux Process {procName!r} {pid!r} cwd found.  Current working dir: {cwdPath!r}', procName=procName, pid=pid, cwdPath=cwdPath)

	## end linuxGetCurrentWorkingDir
	return cwdPath


def linuxGetFullyQualifiedProcessName(runtime, client, pid, procName=None, procPath=None):
	"""Get a fully qualified path, reported from the /proc filesystem."""
	fqPath = None
	## The updateCommand should add --color=never to avoid PTY user preferences
	command = updateCommand(runtime, concatenate('ls -l /proc/', str(pid), '/exe'))
	(stdout, stderr, hitProblem) = client.run(command, 3)
	if not hitProblem:
		if (len(stdout) > 1):
			line = stdout.strip()
			m = re.search('/proc/(\d+)/exe\s+->\s+(\S+)\s*$', line)
			if m:
				fqPath = m.group(2)
			else:
				if procName is not None:
					runtime.logger.report(' Unable to update process name {procName!r} with pid {pid!r} from /proc info: {procLine!r}', procName=procName, pid=pid, procLine=line)
				else:
					runtime.logger.report(' Unable to update process with pid {pid!r} from /proc info: {procLine!r}', pid=pid, procLine=line)
	else:
		## Only report on unexpected failures; specifically drop these two out:
		if (not re.search('cannot read symbolic link', stderr, re.I) and
			not re.search('No such file or directory', stderr, re.I)):
			runtime.logger.error(' Error with {command!r}: {stdout!r}, {stderr!r}, {hitProblem!r}', command=command, stdout=stdout, stderr=stderr, hitProblem=hitProblem)
	if fqPath is not None:
		runtime.logger.report('  Linux Process {procName!r} {pid!r} path found.  From ps: {procPath!r}.  From proc: {fqPath!r}', procName=procName, pid=pid, procPath=procPath, fqPath=fqPath)

	## end linuxGetFullyQualifiedProcessName
	return fqPath


def linuxUpdateThisProcess(runtime, processData, client, pid, objectId):
	"""Update details on a single Linux process.

	This updates the processData dictionary (local version used for reference)
	along with the runtime.results object if they were previously created (which
	is possible if the parameters told the osProcesses library to create them).
	"""
	newData = {}
	processName = processData.get('name')
	processPath = processData.get('path_from_process')
	## Attempt to update the filesystem path (via the /proc filesystem)
	filesystemPath = linuxGetFullyQualifiedProcessName(runtime, client, pid, processName, processPath)
	if filesystemPath is not None:
		processData['path_from_filesystem'] = filesystemPath
		newData['path_from_filesystem'] = filesystemPath
	## Attempt to update the current working dir (via the /proc filesystem)
	cwdPath = linuxGetCurrentWorkingDir(runtime, client, pid, processName)
	if cwdPath is not None:
		processData['path_working_dir'] = cwdPath
		newData['path_working_dir'] = cwdPath
	## Attempt to update the resolved path (via following symbolic links)
	resolvedPath = uxResolveSymbolicLink(runtime, client, pid, processName, processPath, filesystemPath)
	if resolvedPath is not None:
		processData['path_from_analysis'] = resolvedPath
		newData['path_from_analysis'] = resolvedPath

	if objectId is not None and len(newData) > 0:
		runtime.results.updateObject(objectId, **newData)
	## Not dealing with virtual platforms, but we could overwrite nodeId here.

	## end linuxUpdateThisProcess
	return


def linuxParseProcFilesystem(runtime, client, osType, resultList, defaultContainerId, discoverPaths, updatedResultList):
	"""Use the /proc filesystem to update path attributes for all processes.

	Sample output...
	========================================================================
	lrwxrwxrwx    1 root     root            0 Jun  9 23:05 /proc/1239/exe
	lrwxrwxrwx    1 root     root            0 Jun  9 23:05 /proc/1915/exe -> /usr/sbin/xinetd
	lrwxrwxrwx    1 nancy    humble          0 Jun  9 23:05 /proc/2984/exe -> /usr/bin/ssh
	lrwxrwxrwx    1 root     root            0 Jun  9 23:05 /proc/2988/exe -> /usr/sbin/smbd
	lrwxrwxrwx    1 root     root            0 Jun  9 23:05 /proc/2/exe
	lrwxrwxrwx    1 nancy    humble          0 Jun  9 23:05 /proc/3549/exe -> /bin/bash
	========================================================================

	Comments:
	I parse the contents of /proc to update paths; this is needed for processes
	without paths or to get the actual path when the listed file is a symbolic
	link.  In order for this to read symbolic links from /proc/$$/exe files, the
	user/service account needs to have read access to additional paths, e.g.:
	/bin, /sbin, /usr/bin, /usr/sbin

	I used to keep only the process path, and cut the name off the end; the
	problem was when applications would override the process name shown from the
	process listing; I can't piece it back together later. Example with DB2 on
	Linux: Process list shows process names like 'db2ckpwd' and 'db2wdog', which
	are not real executable names but rather spoofed or aliased from the actual
	binary. By referencing the /proc filesystem, we see it listing the binary
	as something like '/home/db2inst3/sqllib/adm/db2syscr'. So if I pull the
	'db2syscr' off the end, and re-attach it later, I get something like this:
	'/home/db2inst3/sqllib/adm/db2wdog', which does not exist.
	"""
	## Currently no virtual context parsed (eg. zone, domain), so default the
	## host container for ProcessOSH as the hostOSH sent into main function
	tempDictionary = {}

	## updateCommand should add '--color=never' to avoid PTY user preferences
	command = updateCommand(runtime, concatenate('ls -l /proc/[0-9]*/exe'))
	## Add optional commands on the front. The export turns off some terminal
	## color options resident in startup profiles, which can help with the PTY
	## color codes on different TERM settings. Extended path for link lookups.
	## Can't issue these on separate lines since the SSH client destroys/creates
	## new session pipes for each call to run(), for better handling of errors
	## and exit codes.
	command = 'export LS_OPTIONS=; export PATH=$PATH:/bin:/sbin:/usr/bin:/usr/sbin; ' + command
	(stdout, stderr, hitProblem) = client.run(command, 120)
	if hitProblem and not re.search('cannot read symbolic link', stderr):
		runtime.logger.error(' error with {command!r}: {stdout!r}, {stderr!r}, {hitProblem!r}', command=command, stdout=stdout, stderr=stderr, hitProblem=hitProblem)
		runtime.logger.error('Listing of /proc filesystem failed. Please ensure commandsToTransform section is setup properly for the OS type, and that you have elevated access rights for this query.')
		return updatedResultList

	runtime.logger.report('  /proc output: {stdout!r}', stdout=stdout)
	outputLines = verifyOutputLines(runtime, stdout)
	## Parse /proc/$$/exe symbolic links
	for line in outputLines:
		try:
			line = line.strip()
			m = re.search('/proc/(\d+)/exe\s+->\s+(\S+)\s*$', line)
			if (not m):
				## Processes that are kernel specific or without executable
				## details, will always error out; this is expected.
				runtime.logger.report('  could not parse line from /proc: {line!r}', line=line)
				continue
			myPID = int(m.group(1))
			for entry in resultList:
				## Process may have started after initial query for ps
				(user, pid, name, ppid, commandLine, processPath, resolvedPath, filesystemPath, args, parsedArgs) = entry
				if (int(myPID) != int(pid)):
					continue
				filesystemPath = m.group(2)
				runtime.logger.report('  updating process path of {name!r} {pid!r}. Old: {processPath!r} -> New:{filesystemPath!r}', name=name, pid=pid, processPath=processPath, filesystemPath=filesystemPath)
				updatedResultList.append((user, pid, name, ppid, commandLine, processPath, resolvedPath, filesystemPath, args, parsedArgs))
				tempDictionary[int(pid)] = 1
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in linuxParseProcFilesystem: {stacktrace!r}', stacktrace=stacktrace)

	## Some sudo implementations will not expand * when supplied to the shell
	## In this case, direct 1-by-1 queries into the process directories will do
	for entry in resultList:
		try:
			(user, pid, name, ppid, commandLine, processPath, resolvedPath, filesystemPath, args, parsedArgs) = entry
			if (int(pid) in tempDictionary.keys()):
				runtime.logger.report('  already updated path for {pid!r} in parsing all procs at once', pid=pid)
			else:
				newPath = linuxUpdateProcessFilesystemPath(runtime, client, pid, name, processPath)
				if newPath is not None:
					updatedResultList.append((user, pid, name, ppid, commandLine, processPath, resolvedPath, newPath, args, parsedArgs))
				else:
					updatedResultList.append((user, pid, name, ppid, commandLine, processPath, resolvedPath, filesystemPath, args, parsedArgs))
				tempDictionary[int(pid)] = 1
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in linuxParseProcFilesystem: {stacktrace!r}', stacktrace=stacktrace)

	## If limited success capturing paths report to GUI
	procCount = len(resultList)
	pathCount = len(tempDictionary.keys())
	runtime.logger.report('Number of processes: {procCount!r} and number of resolved paths: {pathCount!r}', procCount=procCount, pathCount=pathCount)
	if (float(pathCount+1) / float(procCount)) < .10:
		runtime.logger.report('Listing of /proc filesystem returned over 90% of unusuable data; this suggests either limited access or format change with a different OS version. Please ensure commandsToTransform section is setup properly for the OS type, and that you have elevated access rights for this query.')

	## end linuxParseProcFilesystem
	return updatedResultList

###############################################################################
#############################  END LINUX SECTION  #############################
###############################################################################
