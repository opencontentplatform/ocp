"""Detect Microsoft SQL Server databases.

Discover the existence of MSSQL instances via shell. This dynamically goes after
instance names and port numbers, instead of trying TCP ports that were assigned
in through governance with the Internet Assigned Numbers Authority (IANA).


Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Oct 23, 2020

"""
import sys
import traceback
import re
from contextlib import suppress

## From openContentPlatform
from protocolWrapper import getClient
from utilities import addObject, addLink


def getIpAllEntry(runtime, client, instanceName, protocol, tcpPath, tcpEntry):
	"""Get the shared configuration when not explicitely set per IP."""
	tcpPortAll = 0
	tcpDynamicPortAll = 0
	try:
		path = r'{}\{}'.format(tcpPath, tcpEntry)
		command = 'Get-ItemProperty -Path "' + path + '" | %{$_.TcpPort,$_.TcpDynamicPorts -Join ":==:"}'
		(stdOut, stdError, hitProblem) = client.run(command, 5)
		## Sample output:
		## ===================================
		## 1433:==:
		## ===================================
		runtime.logger.report('   getIpAllEntry: {}'.format(stdOut))
		if len(stdOut) > 0:
			(tcpPortAll, tcpDynamicPortAll) = stdOut.split(':==:')
			runtime.logger.report('     ====> : {}'.format(stdOut.split(':==:')))
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error(' Failure in getProcesses: {stacktrace!r}', stacktrace=stacktrace)

	## end getIpAllEntry
	return (tcpPortAll, tcpDynamicPortAll)


def normalizePort(attributes, tcpPortAll, tcpDynamicPortAll):
	"""Selects the port configuration.

	Order of precedence:
	  1) static port is directly assigned (not null and not 0)
	  2) when static port is 0, use static port assigned on ipAll
	  3) dynamic port is directly assigned (not null and not 0)
	  4) when dynamic port is 0, use dynamic port assigned on ipAll
	"""
	staticPort = attributes.pop('port')
	dynamicPort = attributes.pop('dynamicPort')

	if staticPort is not None and len(staticPort) > 0:
		if staticPort != '0':
			attributes['port'] = int(staticPort)
		else:
			attributes['port'] = int(tcpPortAll)
		return
	if dynamicPort is not None and len(dynamicPort) > 0:
		if dynamicPort != '0':
			attributes['port'] = int(dynamicPort)
		else:
			attributes['port'] = int(tcpDynamicPortAll)

	## end normalizePort
	return


def getTcpIpEntry(runtime, client, instanceName, protocol, hostname, tcpPath, tcpEntry, tcpIpEntries):
	"""Get a single TCP/IP entry from the SuperSocketNetLib list."""
	try:
		path = r'{}\{}'.format(tcpPath, tcpEntry)
		command = 'Get-ItemProperty -Path "' + path + '" | %{$_.IpAddress,$_.Enabled,$_.Active,$_.TcpPort,$_.TcpDynamicPorts -Join ":==:"}'
		(stdOut, stdError, hitProblem) = client.run(command, 5)
		## Sample output:
		## ===================================
		## 192.168.121.230:==:0:==:1:==:1433:==:
		## ===================================
		runtime.logger.report('   getTcpIpEntry: {}'.format(stdOut))
		if len(stdOut) > 0:
			(ipAddress, enabled, active, port, dynamicPort) = stdOut.split(':==:')
			## Ignore any Windows assigned link-local types (169.254.x.x)
			if re.search('^169[.]254[.]\d{1,3}[.]\d{1,3}', ipAddress):
				return
			attributes = {}
			attributes['name'] = instanceName
			attributes['protocol'] = protocol
			attributes['ip_address'] = ipAddress
			attributes['db_type'] = 'SqlServer'
			attributes['source'] = 'Local'
			attributes['hostname'] = hostname
			attributes['port'] = port
			attributes['dynamicPort'] = dynamicPort
			tcpIpEntries.append(attributes)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error(' Failure in getProcesses: {stacktrace!r}', stacktrace=stacktrace)

	## end getTcpIpEntry
	return


def getTcpIp(runtime, client, hostname, instanceName, regInstancePath, dbContextId):
	"""Find out whether TCP/IP is enabled."""
	tcpPath = r'{}\MSSQLServer\SuperSocketNetLib\TCP'.format(regInstancePath)
	command = 'Get-ItemProperty -Path "' + tcpPath + '" | %{$_.DisplayName,$_.Enabled,$_.ListenOnAllIPs,$_.KeepAlive -Join ":==:"}'
	(stdOut, stdError, hitProblem) = client.run(command, 5)
	## Sample output:
	## ===================================
	## TCP/IP:==:1:==:1:==:30000
	## ===================================
	if len(stdOut) > 0:
		(protocol, enabled, listenOnAllIPs, keepAlive) = stdOut.split(':==:')
		if enabled == '0':
			return
		runtime.logger.report('   {} enabled on instance {}:'.format(protocol, instanceName))
		runtime.logger.report('     enabled: {}'.format(enabled))
		runtime.logger.report('     listenOnAllIPs: {}'.format(listenOnAllIPs))
		runtime.logger.report('     keepAlive: {}'.format(keepAlive))

		## Get all TCP/IP settings
		command = 'Get-ChildItem -Path "' + tcpPath + '" | foreach { $_.PSChildName }'
		(stdOut, stdError, hitProblem) = client.run(command, 5)
		## Sample output:
		## ===================================
		## IP1
		## IP2
		## ...
		## IPAll
		## ===================================
		tcpIpEntries = []
		for entry in stdOut.splitlines():
			if entry.strip().lower() == 'ipall':
				(tcpPortAll, tcpDynamicPortAll) = getIpAllEntry(runtime, client, instanceName, protocol, tcpPath, entry.strip().lower())
			else:
				getTcpIpEntry(runtime, client, instanceName, protocol, hostname, tcpPath, entry.strip().lower(), tcpIpEntries)

		for entry in tcpIpEntries:
			normalizePort(entry, tcpPortAll, tcpDynamicPortAll)
			if entry['port'] > 0:
				## Create TCP/IP connection parameter and link to dbContext
				connectionParameterId, exists = addObject(runtime, 'DBConnectionParameter', **entry)
				addLink(runtime, 'Enclosed', dbContextId, connectionParameterId)

	## end getTcpIp
	return


def getSharedMemory(runtime, client, hostname, instanceName, regInstancePath, dbContextId):
	"""Find out whether Shared Memory is enabled."""
	path = r'{}\MSSQLServer\SuperSocketNetLib\Sm'.format(regInstancePath)
	command = 'Get-ItemProperty -Path "' + path + '" | %{$_.DisplayName,$_.Enabled -Join ":==:"}'
	(stdOut, stdError, hitProblem) = client.run(command, 5)
	## Sample output:
	## ===================================
	## Shared Memory:==:1
	## ===================================
	if len(stdOut) > 0:
		(protocol, enabled) = stdOut.split(':==:')
		if enabled != '0':
			attributes = {}
			attributes['name'] = instanceName
			attributes['protocol'] = protocol
			attributes['db_type'] = 'SqlServer'
			attributes['source'] = 'Local'
			attributes['hostname'] = hostname

			## Create Shared Memory connection parameter and link to dbContext
			connectionParameterId, exists = addObject(runtime, 'DBConnectionParameter', **attributes)
			addLink(runtime, 'Enclosed', dbContextId, connectionParameterId)

			## Debugging aid
			runtime.logger.report('   {} enabled on instance {}:'.format(protocol, instanceName))

	## end getSharedMemory
	return


def getNamedPipes(runtime, client, hostname, instanceName, regInstancePath, dbContextId):
	"""Find out whether Named Pipes are enabled."""
	path = r'{}\MSSQLServer\SuperSocketNetLib\Np'.format(regInstancePath)
	command = 'Get-ItemProperty -Path "' + path + '" | %{$_.DisplayName,$_.Enabled,$_.PipeName -Join ":==:"}'
	(stdOut, stdError, hitProblem) = client.run(command, 5)
	## Sample output:
	## ===================================
	## Named Pipes:==:0:==:\\.\pipe\sql\query
	## ===================================
	if len(stdOut) > 0:
		(protocol, enabled, pipeName) = stdOut.split(':==:')
		if enabled != '0':
			attributes = {}
			attributes['name'] = instanceName
			attributes['protocol'] = protocol
			attributes['logical_context'] = pipeName
			attributes['db_type'] = 'SqlServer'
			attributes['source'] = 'Local'
			attributes['hostname'] = hostname

			## Create Named Pipes connection parameter and link to dbContext
			connectionParameterId, exists = addObject(runtime, 'DBConnectionParameter', **attributes)
			addLink(runtime, 'Enclosed', dbContextId, connectionParameterId)

			## Debugging aid
			runtime.logger.report('   {} enabled on instance {}:'.format(protocol, instanceName))

	## end getNamedPipes
	return


def getConnectionParameters(runtime, client, instanceName, instanceData, regInstancePath, dbContextId):
	"""Look for various connection parameters.

	Specifically looking for Shared Memory, Named Pipes, and TCP."""
	try:
		## Get the hostname
		(stdOut, stdError, hitProblem) = client.run('hostname', 3)
		hostname = stdOut.strip()

		## Track the desired connection parameter types
		getNamedPipes(runtime, client, hostname, instanceName, regInstancePath, dbContextId)
		getSharedMemory(runtime, client, hostname, instanceName, regInstancePath, dbContextId)
		getTcpIp(runtime, client, hostname, instanceName, regInstancePath, dbContextId)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error(' Failure in getConnectionParameters: {stacktrace!r}', stacktrace=stacktrace)

	## end getConnectionParameters
	return


def qualifyInstance(runtime, client, instanceName, instanceData, regInstancePath, nodeId):
	"""Request details from each existing database instance."""
	dbContextId = None
	try:
		instanceId = instanceData.get('id')
		## C:\Program Files\Microsoft SQL Server\MSSQL11.TEST\Setup
		setupPath = '{}\Setup'.format(regInstancePath)
		command = 'Get-ItemProperty -Path "' + setupPath + '" | %{$_.Version,$_.PatchLevel,$_.Edition,$_.EditionType,$_.SqlProgramDir,$_.SQLPath -Join ":==:"}'
		(stdOut, stdError, hitProblem) = client.run(command, 10)
		## Sample output:
		## ===================================
		## 10.50.1600.1:==:10.50.1617.0:==:Express Edition:==:Express Edition with Advanced Services:==:c:\Program Files\Microsoft SQL Server\:==:c:\Program Files\Microsoft SQL Server\MSSQL10.SQLEXPRESS\MSSQL
		## 11.0.2100.60:==:11.0.2100.60:==:Express Edition:==:Express Edition:==:C:\Program Files\Microsoft SQL Server\:==:C:\Program Files\Microsoft SQL Server\MSSQL11.SQLEXPTRACK201\MSSQL
		## 13.2.5026.0:==:13.2.5026.0:==:Developer Edition:==:Developer Edition:==:C:\Program Files\Microsoft SQL Server\:==:C:\Program Files\Microsoft SQL Server\MSSQL13.MSSQLSERVER\MSSQL
		## ===================================

		if hitProblem:
			raise EnvironmentError('Problem gathering details on instance {}'.format(instanceId))
		if (stdOut is None or len(stdOut) <= 0):
			runtime.logger.report('No details found on instance {}'.format(instanceId))
			if stdError is not None:
				runtime.logger.report('  Error: {stdError!r}', stdError=stdError)
		else:
			(version, patchLevel, edition, editionType, sqlProgramDir, sqlPath) = stdOut.split(':==:')
			## Create the attributes to send to addObject
			attr = {}
			attr['name'] = instanceName
			attr['path'] = sqlPath
			attr['version'] = version
			attr['patch_level'] = patchLevel
			attr['edition'] = edition
			attr['edition_type'] = editionType
			attr['program_dir'] = sqlProgramDir

			## Create the DB context object and link to the Node
			dbContextId, exists = addObject(runtime, 'SqlServerContext', **attr)
			addLink(runtime, 'Enclosed', nodeId, dbContextId)

			## Debugging aid
			runtime.logger.report('Setup info on instance {}:'.format(instanceName))
			runtime.logger.report('   version: {}'.format(version))
			runtime.logger.report('   patchLevel: {}'.format(patchLevel))
			runtime.logger.report('   edition: {}'.format(edition))
			runtime.logger.report('   editionType: {}'.format(editionType))
			runtime.logger.report('   sqlProgramDir: {}'.format(sqlProgramDir))
			runtime.logger.report('   sqlPath: {}'.format(sqlPath))

	except:
		runtime.setError(__name__)

	## end qualifyInstance
	return dbContextId


def findInstances(runtime, client, instances):
	"""Find SQL instances on a Windows server.

	Note: querying the 'InstalledInstances' property from the following registry
	location worked back on Windows 2003 and 2008, but then stopped returning ID
	qualifiers on 2008 and beyond: 'HKLM\SOFTWARE\Microsoft\Microsoft SQL Server'
	So we use 'HKLM\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL'
	path, instead of InstalledInstances property.
	"""
	try:
		command = 'Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL" | Select-Object * -exclude PSPath,PSParentPath,PSChildName,PSProvider,PSDrive | fl'
		(stdOut, stdError, hitProblem) = client.run(command, 10)
		## Sample output:
		## ===================================
		## SQLEXPRESS : MSSQL10.SQLEXPRESS
		## SQLEXPTRACK201 : MSSQL11.SQLEXPTRACK201
		## MSSQLSERVER : MSSQL13.MSSQLSERVER
		## ===================================

		if (stdOut is None or len(stdOut) <= 0):
			runtime.logger.report('No output returned from SQL instances query')
			if stdError is not None:
				runtime.logger.report('  Error: {stdError!r}', stdError=stdError)

		else:
			#runtime.logger.report('Output returned from SQL instances query: {}'.format(stdOut))
			for line in stdOut.splitlines():
				m = re.search('^\s*(\S+)\s*[:]\s*(\S+)\s*$', line)
				if not m:
					continue
				runtime.logger.report('Instance: {}'.format(line))
				instanceName = m.group(1)
				instanceId = m.group(2)
				instances[instanceName] = { 'id': instanceId }

	except:
		runtime.setError(__name__)

	## end findInstances
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
			## Get all related IPs
			ips = {}
			for ip in runtime.endpoint.get('children', {}).get('IpAddress', []):
				ipObjectId = ip.get('identifier')
				ipAddress = ip.get('data').get('address')
				ips[ipAddress] = ipObjectId

			## Open client session before starting the work
			client.open()

			## First query for SQL instance name and IDs
			instances = {}
			findInstances(runtime, client, instances)

			## Only continue if we found SQL instances
			if len(instances) <= 0:
				## Job executed fine, but didn't find what it was looking for
				runtime.setInfo('SQL Server not found')
			else:
				addObject(runtime, 'Node', uniqueId=nodeId)
				#runtime.results.addObject('Node', uniqueId=nodeId)
				for instanceName,instanceData in instances.items():
					regInstancePath = 'HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\{}'.format(instanceData.get('id'))
					dbContextId = qualifyInstance(runtime, client, instanceName, instanceData, regInstancePath, nodeId)
					getConnectionParameters(runtime, client, instanceName, instanceData, regInstancePath, dbContextId)


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
