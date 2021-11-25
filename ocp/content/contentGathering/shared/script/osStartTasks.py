"""Gather start tasks (services/daemons) on OS types.

Entry function:
  getStartTasks : standard module entry point

OS agnostic functions:
  queryForStartTasks : start task data (services/daemons)
  parseAndFilterStartTasks : Parse and filter initial set
  buildStartTaskDictionary : Create requested CIs and relationships
  getFilterParameters : Get filters from the runtime shell parameters
  compareFilter : Conditionally use equal vs regEx compare methods
  inFilteredStartTaskList : Determine whether start task is in the list to return
  setAttribute : Helper to set attributes only when they are valid values

OS specific functions:
  windowsGetStartTasks : Get Windows Services
  windowsFilterStartTasks : Parse the Services and filter out undesirables

"""
import sys
import traceback
import os
import re
from contextlib import suppress

## From openContentPlatform content/contentGathering/shared/script
from utilities import updateCommand, loadJsonIgnoringComments, compareFilter
from utilities import resolve8dot3Name, splitAndCleanList, delimitedStringToIterableObject


def getStartTasks(runtime, client, nodeId, trackResults=False):
	"""Standard entry function for osStartTasks.

	This function returns a dictionary with all start task objects. And when
	the caller function requests to trackResults (meaning add objects onto the
	results object), this function adds all the created start tasks onto
	runtime's results so the caller function doesn't need to code that logic.
	"""
	startTasks = {}
	try:
		osType = runtime.endpoint.get('data').get('node_type')

		## Gather start tasks
		allStartTasks = queryForStartTasks(runtime, client, osType)
		## Parse and filter the initial raw listing
		parseAndFilterStartTasks(runtime, startTasks, allStartTasks, client, osType)
		## Build requested CIs and relationships
		buildStartTaskDictionary(runtime, osType, startTasks, nodeId, trackResults)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error(' Failure in getStartTasks: {stacktrace!r}', stacktrace=stacktrace)

	## end getStartTasks
	return startTasks


###############################################################################
###########################  BEGIN GENERAL SECTION  ###########################
###############################################################################

def queryForStartTasks(runtime, client, osType):
	"""Gather start task data (services/daemons); this is a wrapper for OS types."""
	allStartTasks = {}

	runtime.logger.report('Gathering {osType!r} StartTasks', osType=osType)
	if (osType == 'Windows'):
		(allStartTasks, stdError, hitProblem) = windowsGetStartTasks(runtime, client)
	elif (osType == 'Linux'):
		(allStartTasks, stdError, hitProblem) = linuxGetStartTasks(runtime, client)
	else:
		raise NotImplementedError('Start task (daemon) solution is not yet implemented on {}'.format(osType))

	## end queryForStartTasks
	return allStartTasks


def parseAndFilterStartTasks(runtime, startTasks, allStartTasks, client, osType):
	"""Parse and filter initial set; this is a wrapper for OS types."""
	try:
		runtime.logger.report('Parsing {osType!r} StartTasks', osType=osType)
		if (osType == 'Windows'):
			windowsFilterStartTasks(runtime, client, startTasks, allStartTasks)
		elif (osType == 'Linux'):
			linuxFilterStartTasks(runtime, client, startTasks, allStartTasks)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error(' Failure in parseAndFilterStartTasks: {stacktrace!r}', stacktrace=stacktrace)

	## end parseAndFilterStartTasks
	return startTasks


def buildStartTaskDictionary(runtime, osType, startTasks, nodeId, trackResults):
	"""Create requested CIs and relationships."""
	runtime.logger.report('Building start task dictionary on {osType!r}', osType=osType)
	filters = {}
	getFilterParameters(runtime, osType, filters)

	for entry,attributes in list(startTasks.items()):
		try:
			runtime.logger.report(' Looking at entry {name!r}', name=entry)
			## Ensure it's not supposed to be filtered out
			if (not filters['startTaskFilterFlag'] or (inFilteredStartTaskList(runtime, attributes, filters))):
				if trackResults:
					## Create the software and link it to the node
					startTaskId, exists = runtime.results.addObject('OsStartTask', **attributes)
					runtime.results.addLink('Enclosed', nodeId, startTaskId)
			else:
				runtime.logger.report(' Filtering out start task {name!r} with attributes {attributes!r}', name=entry, attributes=attributes)
				startTasks.pop(entry)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error(' Exception with creating {osType!r} startTask in buildStartTaskDictionary: {stacktrace!r}', osType=osType, stacktrace=stacktrace)

	## end buildStartTaskDictionary
	return


def getFilterParameters(runtime, osType, filters):
	"""Get filters from the shell parameters."""
	shellParameters = runtime.endpoint.get('data').get('parameters')

	filters['startTaskFilterFlag'] = shellParameters.get('startTaskFilterFlag', False)
	if (not filters['startTaskFilterFlag']):
		runtime.logger.report(' Returning all software since \'startTaskFilterFlag\' for {osType!r} is not set to true in the shell parameters.', osType=osType)
	else:
		filters['startTaskFilterByName'] = shellParameters.get('startTaskFilterByName', False)
		filters['startTaskFilterByDisplayName'] = shellParameters.get('startTaskFilterByDisplayName', False)
		filters['startTaskFilterByStartName'] = shellParameters.get('startTaskFilterByStartName', False)
		filters['startTaskFilterByActiveState'] = shellParameters.get('startTaskFilterByActiveState', True)
		filters['startTaskFilterPathExcludeList'] = runtime.endpoint.get('data').get('parameters').get('startTaskFilterPathExcludeList', ['system32\\\\+svchost\\.exe'])
		filters['startTaskFilterPathExcludeCompare'] = runtime.endpoint.get('data').get('parameters').get('startTaskFilterPathExcludeCompare', 'regex')
		filters['startTaskFilterExcludeCompare'] = runtime.endpoint.get('data').get('parameters').get('startTaskFilterExcludeCompare', '==')
		filters['startTaskFilterExcludeList'] = runtime.endpoint.get('data').get('parameters').get('startTaskFilterExcludeList', [])
		filters['startTaskFilterIncludeCompare'] = runtime.endpoint.get('data').get('parameters').get('startTaskFilterIncludeCompare', '==')
		filters['startTaskFilterIncludeList'] = runtime.endpoint.get('data').get('parameters').get('startTaskFilterIncludeList', [])
		if (len(filters['startTaskFilterIncludeList']) <= 0 and len(filters['startTaskFilterExcludeList']) <= 0):
			runtime.logger.report(' No entries listed in either \'startTaskFilterIncludeList\' or \'startTaskFilterExcludeList\' for {osType!r} in the shell parameters.', osType=osType)

	## end getFilterParameters
	return


def inFilteredStartTaskList(runtime, attributes, filters):
	"""Determine whether start task is in the list to return."""
	## First check the general exclude list
	if (len(filters['startTaskFilterExcludeList']) >= 0):
		runtime.logger.report('startTaskFilterExcludeList - got path:  {path!r}', path=attributes['path'])
		for matchContext in filters['startTaskFilterExcludeList']:
			try:
				if (matchContext is None or len(matchContext) <= 0):
					continue
				searchString = matchContext.strip().lower()
				if (filters['startTaskFilterByName'] and
					attributes['name'] and
					compareFilter(filters['startTaskFilterExcludeCompare'], searchString, attributes['name'].lower())):
					return False
				if (filters['startTaskFilterByDisplayName'] and
					attributes['display_name'] and
					compareFilter(filters['startTaskFilterExcludeCompare'], searchString, attributes['display_name'].lower())):
					return False
				if (filters['startTaskFilterByStartName'] and
					attributes['user'] and
					compareFilter(filters['startTaskFilterExcludeCompare'], searchString, attributes['user'].lower())):
					return False
				if (filters['startTaskFilterByActiveState'] and
					attributes['state'] and
					attributes['state'].lower() == 'stopped'):
					return False
			except:
				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				runtime.logger.error('Exception in inFilteredStartTaskList: on searchString {searchString!r}:  {stacktrace!r}', searchString=searchString, stacktrace=stacktrace)

		## Next check the path-based exclude list
		if (len(filters['startTaskFilterPathExcludeList']) >= 0):
			runtime.logger.report('startTaskFilterPathExcludeList - got path:  {path!r}', path=attributes['path'])
			for matchContext in filters['startTaskFilterPathExcludeList']:
				try:
					runtime.logger.report('startTaskFilterPathExcludeList - looking at filter:  {matchContext!r}', matchContext=matchContext)
					if (matchContext is None or len(matchContext) <= 0):
						continue
					searchString = matchContext.strip()
					if (attributes['path'] and
						compareFilter(filters['startTaskFilterPathExcludeCompare'], matchContext, attributes['path'])):
						return False
				except:
					stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					runtime.logger.error('Exception in inFilteredStartTaskList: on searchString {searchString!r}:  {stacktrace!r}', searchString=searchString, stacktrace=stacktrace)

		## Exclusion rules have precidence over inclusion rules. If the exclude
		## list had content but nothing matched, go ahead and include in results
		return True

	## Now check the include list
	for matchContext in filters['startTaskFilterIncludeList']:
		try:
			if (matchContext is None or len(matchContext) <= 0):
				continue
			searchString = matchContext.strip().lower()
			if (filters['startTaskFilterByName'] and
				attributes['name'] and
				compareFilter(filters['startTaskFilterIncludeCompare'], searchString, attributes['name'].lower())):
				return True
			if (filters['startTaskFilterByDisplayName'] and
				attributes['display_name'] and
				compareFilter(filters['startTaskFilterIncludeCompare'], searchString, attributes['display_name'].lower())):
				return True
			if (filters['startTaskFilterByStartName'] and
				attributes['user'] and
				compareFilter(filters['startTaskFilterIncludeCompare'], searchString, attributes['user'].lower())):
				return True
			if (filters['startTaskFilterByActiveState'] and
				attributes['state'] and
				attributes['state'].lower() != 'stopped'):
				return True
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in inFilteredStartTaskList: on searchString {searchString!r}:  {stacktrace!r}', searchString=searchString, stacktrace=stacktrace)

	## end inFilteredStartTaskList
	return False


def setAttribute(attributes, name, value, maxLength=None):
	"""Helper to set attributes only when they are valid values."""
	if (value is not None and value != 'null' and len(str(value)) > 0):
		attributes[name] = value
		if maxLength:
			attributes[name] = value[:maxLength]

	## end setAttribute
	return

###############################################################################
############################  END GENERAL SECTION  ############################
###############################################################################


###############################################################################
###########################  BEGIN WINDOWS SECTION  ###########################
###############################################################################

def windowsGetStartTasks(runtime, client):
	"""Get Windows Services."""
	iterableObject = {}
	stdError = None
	hitProblem = None
	try:
		delimiter = ':==:'
		wmiServicesQuery = 'Get-WmiObject -q "Select * from Win32_Service" | foreach {$_.DisplayName,$_.Name,$_.StartName,$_.State,$_.PathName,$_.ProcessId,$_.StartMode,$_.Description -Join "'+ delimiter + '"}'
		(rawOutput, stdError, hitProblem) = client.run(wmiServicesQuery, 20)
		iterableObject = delimitedStringToIterableObject(rawOutput, delimiter)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in windowsGetStartTasks: {stacktrace!r}', stacktrace=stacktrace)

	## end windowsGetStartTasks
	return (iterableObject, stdError, hitProblem)


def windowsFilterStartTasks(runtime, client, startTasks, output):
	"""Parse the Services and filter out undesirables.

	Sample output from WMI Win32_Service for attributes DisplayName,Name,StartName,State,PathName,ProcessId,StartMode,Description
	===================================================================
	DisplayName                                 Name                 StartName                     State    PathName                                                                                                      ProcessId  StartMode  Description
	Norton Security                             NortonSecurity       LocalSystem                   Running  "C:\\Program Files\\Norton Security with Backup\\Engine\\22.12.1.15\\NortonSecurity.exe" /s "NortonSecurity"  2944       Auto       Norton Security
	Remote Access Auto Connection Manager       RasAuto              localSystem                   Stopped  C:\WINDOWS\System32\svchost.exe -k netsvcs -p                                                                 0          Manual     Creates a connection to a remote network whenever a program references a remote DNS or NetBIOS name or address
	postgresql-x64-9.6 - PostgreSQL Server 9.6  postgresql-x64-9.6   NT AUTHORITY\\NetworkService  Running  "C:\Program Files\PostgreSQL\9.6\bin\pg_ctl.exe" runservice -N "postgresql-x64-9.6" -w                        2956       Auto       Provides relational database storage.
	UCMDB Probe                                 UCMDB_Probe          LocalSystem                   Stopped  E:\\hp\\UCMDB\\DataFlowProbe\\bin\\wrapper.exe -s E:\\hp\\UCMDB\\DataFlowProbe\\bin\\WrapperGateway.conf      0          Manual     UCMDB Data Flow Probe
	Windows Update                              wuauserv             LocalSystem                   Running  C:\WINDOWS\system32\svchost.exe -k netsvcs                                                                    3064       Manual     Enables the detection, download, and installation of updates for Windows and other programs.
	===================================================================
	"""
	while output.next():
		try:
			attributes = {}
			setAttribute(attributes, 'display_name', output.getString(1), 256)
			setAttribute(attributes, 'name', output.getString(2), 256)
			setAttribute(attributes, 'user', output.getString(3), 64)
			setAttribute(attributes, 'state', output.getString(4), 64)
			setAttribute(attributes, 'path', output.getString(5), 512)
			setAttribute(attributes, 'process_id', output.getInt(6))
			setAttribute(attributes, 'start_mode', output.getString(7), 64)
			setAttribute(attributes, 'description', output.getString(8), 1024)

			## Debug print
			runtime.logger.report('  Win32_Service DisplayName: {display_name!r}, Name: {name!r}, StartName: {user!r}, State: {state!r}, PathName: {path!r}, PID: {process_id!r}, StartMode: {start_mode!r}, Description: {description!r}', display_name=attributes.get('display_name'), name=attributes.get('name'), user=attributes.get('user'), state=attributes.get('state'), path=attributes.get('path'), process_id=attributes.get('process_id'), start_mode=attributes.get('start_mode'), description=attributes.get('description'))
			name=attributes.get('name')
			if (name is None or name == 'null' or len(name.strip()) <= 0):
				runtime.logger.report('   cannot proceed with empty name in Windows Service:  DisplayName: {display_name!r}, Name: {name!r}, StartName: {user!r}, State: {state!r}, PathName: {path!r}, PID: {process_id!r}, StartMode: {start_mode!r}, Description: {description!r}', display_name=attributes.get('display_name'), name=attributes.get('name'), user=attributes.get('user'), state=attributes.get('state'), path=attributes.get('path'), process_id=attributes.get('process_id'), start_mode=attributes.get('start_mode'), description=attributes.get('description'))
				continue

			## Need to resolve 8dot3 names (short names) for path matching
			path=attributes.get('path')
			if (path is not None and path != "null" and re.search('\~', path)):
				(updatedPath, stdError, hitProblem) = resolve8dot3Name(log, client, path)
				if updatedPath is not None:
					runtime.logger.report('   Conversion returned path: {resolvedPath!r}', resolvedPath=updatedPath.encode('unicode-escape'))
					if updatedPath != path and not hitProblem:
						runtime.logger.report('     ---> new install: {productName!r}, Package: {packageName!r}.  Old value: {path!r}.  New value: {updatedPath!r}', productName=productName, packageName=packageName, path=path, updatedPath=updatedPath)
						attributes['path'] = updatedPath

			## Add to the start task list
			startTasks[attributes.get('name')] = attributes
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in windowsFilterStartTasks: {stacktrace!r}', stacktrace=stacktrace)

	## end windowsFilterStartTasks
	return

###############################################################################
############################  END WINDOWS SECTION  ############################
###############################################################################


###############################################################################
############################  BEGIN LINUX SECTION  ############################
###############################################################################

def linuxGetStartTaskDetails(runtime, client, serviceName, attributes):
	try:
		command = 'systemctl show {} | grep "Id\|Description\|MainPID\|User\|Type\|Names\|ActiveState\|SubState\|Environment\|ExecStart"'.format(serviceName)
		command = updateCommand(runtime, command)
		(rawOutput, stdError, hitProblem) = client.run(command, 20)
		runtime.logger.report('service {serviceName!r}:\n {rawOutput!r}', serviceName=serviceName, rawOutput=rawOutput)

		## Sample output
		#################################################
		## Type=forking
		## GuessMainPID=yes
		## MainPID=455947
		## ExecMainPID=455947
		## ExecStartPre={ path=/usr/bin/postgresql-check-db-dir ; argv[]=/usr/bin/postgresql-check-db-dir ${PGDATA} ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }
		## ExecStart={ path=/usr/bin/pg_ctl ; argv[]=/usr/bin/pg_ctl start -D ${PGDATA} -s -o -p ${PGPORT} -w -t 300 ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }
		## Environment=PGPORT=5432 PGDATA=/var/lib/pgsql/data
		## User=postgres
		## Id=postgresql.service
		## Names=postgresql.service
		## Description=PostgreSQL database server
		## ActiveState=active
		## SubState=running
		#################################################
		for line in rawOutput.split('\n'):
			if (len(line) <= 0 or len(line.strip()) <= 0):
				continue
			m = re.search('^(\S+)\s*=\s*(\S.*)$', line)
			if not m:
				runtime.logger.report('Failed to parse service {serviceName!r} detail line: {line!r}', serviceName=serviceName, line=line)
				continue
			attrName = m.group(1)
			attrValue = m.group(2)
			attrMapping = {'Id': {'name': 'name', 'maxSize': 256},
						   'Description': {'name': 'description', 'maxSize': 1024},
						   'MainPID': {'name': 'process_id'},
						   'User': {'name': 'user', 'maxSize': 64},
						   'Names': {'name': 'display_name', 'maxSize': 256},
						   'Type': {'name': 'start_type', 'maxSize': 64},
						   'Environment': {'name': 'environment', 'maxSize': 512},
						   'ActiveState': {'name': 'start_mode', 'maxSize': 64},
						   'SubState': {'name': 'state', 'maxSize': 64},
						   'ExecStart': {'name': 'command_line', 'maxSize': 512}}
			if attrName in attrMapping:
				attrDef = attrMapping.get(attrName)
				## Special parsing for particular entries:
				## Pull the path out of ExecStart
				if attrName == 'ExecStart':
					m = re.search('path=(\S[^\s;]+)', attrValue)
					if m:
						setAttribute(attributes, 'path', m.group(1), 512)
				## General section:
				thisAttrName = attrDef.get('name')
				thisAttrMaxSize = attrDef.get('maxSize', 0)
				if thisAttrMaxSize:
					setAttribute(attributes, thisAttrName, attrValue, thisAttrMaxSize)
				else:
					setAttribute(attributes, thisAttrName, attrValue)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in linuxGetStartTaskDetails: {stacktrace!r}', stacktrace=stacktrace)

	## end linuxGetStartTaskDetails
	return


def linuxGetStartTasks(runtime, client):
	"""Get Linux Daemons from systemd.

	Attempted to do something similar with init.d (System V init) around 2010,
	using clever script parsing. Unfortunately, the lack of scripting standards
	prevented me from just going after two simple attributes: daemon name and
	the target script/command.

	Systemd offers a relatively standard syntax for describing and querying
	daemon processes.  Ideally I'd like to have access to daemon name, command,
	PID, vendor/owner, and version... but only some of those are available here.
	"""
	startTasks = {}
	stdError = None
	hitProblem = None
	try:
		## Going after active daemons; description of LOAD/ACTIVE/SUB columns:
		#################################################
		## LOAD   = Reflects whether the unit definition was properly loaded.
		## ACTIVE = The high-level unit activation state, i.e. generalization of SUB.
		## SUB    = The low-level unit activation state, values depend on unit type.
		#################################################

		command = 'systemctl --no-legend --no-pager list-units --type=service --state=running'
		(rawOutput, stdError, hitProblem) = client.run(command, 30)
		runtime.logger.report('Linux daemons: {rawOutput!r}', rawOutput=rawOutput)

		## Sample output
		#################################################
		## console-getty.service    loaded active running Console Getty
		## crond.service            loaded active running Command Scheduler
		## dbus.service             loaded active running D-Bus System Message Bus
		## firewalld.service        loaded active running firewalld - dynamic firewall daemon
		## getty@tty2.service       loaded active running Getty on tty2
		## httpd.service            loaded active running The Apache HTTP Server
		## kafka.service            loaded active running Apache Kafka - a distributed streaming platform
		## postgresql.service       loaded active running PostgreSQL database server
		## ...
		## zookeeper.service        loaded active running zookeeper.service
		#################################################
		for service in rawOutput.split('\n'):
			if (len(service) <= 0 or len(service.strip()) <= 0):
				continue
			m = re.search('^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S.*)\s*$', service)
			if not m:
				runtime.logger.report('Failed to parse service line: {service!r}', service=service)
				continue
			serviceName = m.group(1)
			serviceLoad = m.group(2)
			serviceActive = m.group(3)
			serviceSub = m.group(4)
			attributes = {}
			linuxGetStartTaskDetails(runtime, client, serviceName, attributes)
			startTasks[serviceName] = attributes
			runtime.logger.report('Found daemon: {serviceName!r}: {attributes!r}', serviceName=serviceName, attributes=attributes)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in linuxGetStartTasks: {stacktrace!r}', stacktrace=stacktrace)

	## end linuxGetStartTasks
	return (startTasks, stdError, hitProblem)


def linuxFilterStartTasks(runtime, client, startTasks, allStartTasks):
	"""Parse the Daemons and filter out undesirables."""
	for serviceName,attributes in allStartTasks.items():
		try:
			## TODO
			## What are we supposed to do here?
			## Filter out non running daemons?

			## Add to the start task list
			startTasks[serviceName] = attributes
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in linuxFilterStartTasks: {stacktrace!r}', stacktrace=stacktrace)

	## end linuxFilterStartTasks
	return

###############################################################################
#############################  END LINUX SECTION  #############################
###############################################################################
