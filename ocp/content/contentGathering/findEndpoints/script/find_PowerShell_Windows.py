"""PowerShell detection library for Windows.

Functions:
  queryWindows : entry point; run queries against Windows endpoint
  queryOperatingSystem : query Win32_OperatingSystem
  queryBios : query Win32_BIOS
  queryComputerSystem : query Win32_ComputerSystem
  queryForIps : query Win32_NetworkAdapterConfiguration
  getDictValue : normalize empty strings to Python None type
  parseListFormatToDict : Convert Format-List to Python dictionary
  createObjects : create objects and links in the results

"""
import sys
import traceback
import re

## From openContentPlatform
from utilities import addObject, addIp, addLink
from utilities import getInstanceParameters, setInstanceParameters


def createObjects(runtime, osType, osAttrDict, biosAttrDict, csAttrDict, ipAddresses, ipDict, endpoint, protocolReference):
	"""Create objects and links in our results."""
	protocolId = None
	try:
		## Log when the 'printDebug' parameter is set
		runtime.logger.report('osAttrDict  : {osAttrDict!r}', osAttrDict=osAttrDict)
		runtime.logger.report('biosAttrDict: {biosAttrDict!r}', biosAttrDict=biosAttrDict)
		runtime.logger.report('csAttrDict  : {csAttrDict!r}', csAttrDict=csAttrDict)
		runtime.logger.report('ipAddresses : {ipAddresses!r}', ipAddresses=ipAddresses)

		## First create the node
		domain = csAttrDict.get('Domain')
		hostname = csAttrDict.get('Name')
		vendor = osAttrDict.get('Manufacturer')
		platform = osAttrDict.get('Caption')
		version = osAttrDict.get('Version')
		hw_provider = csAttrDict.get('Manufacturer')
		if domain is None:
			nodeId, exists = addObject(runtime, osType, hostname=hostname, vendor=vendor, platform=platform, version=version, hardware_provider=hw_provider)
		else:
			nodeId, exists = addObject(runtime, osType, hostname=hostname, domain=domain, vendor=vendor, platform=platform, version=version, hardware_provider=hw_provider)

		## Establish an FQDN string for local IP addresses (loopback)
		realm = runtime.jobMetaData.get('realm', 'NA')
		FQDN = 'NA'
		if hostname is not None:
			FQDN = hostname
			if (domain is not None and domain not in hostname):
				FQDN = '{}.{}'.format(hostname, domain)

		## Now create the IPs
		trackedZones = {}
		for ip in ipAddresses:
			ipId = None
			if (ip in ['127.0.0.1', '::1', '0:0:0:0:0:0:0:1']):
				## Override realm setting for two reasons: we do not want these
				## IPs in endpoint query results, and we want one per node
				ipId, exists = runtime.results.addIp(address=ip, realm=FQDN)
			else:
				ipId, exists = runtime.results.addIp(address=ip, realm=realm)

				## Add any DNS records found
				if ip in ipDict:
					for entry in ipDict[ip]:
						(domainName, recordData) = entry
						## Create the zone if necessary
						if domainName not in trackedZones:
							## Add the zone onto the result set
							zoneId, exists = addObject(runtime, 'Domain', name=domainName)
							trackedZones[domainName] = zoneId
						zoneId = trackedZones[domainName]
						## Create the DNS record
						recordId, exists = addObject(runtime, 'NameRecord', name=recordData, value=ip)
						addLink(runtime, 'Enclosed', zoneId, recordId)

			addLink(runtime, 'Usage', nodeId, ipId)
		## In case the IP we've connected in on isn't in the IP table list:
		if endpoint not in ipAddresses:
			ipId, exists = addIp(runtime, address=endpoint)
			addLink(runtime, 'Usage', nodeId, ipId)

		## Now create the PowerShell object
		protocolId, exists = addObject(runtime, 'PowerShell', container=nodeId, ipaddress=endpoint, protocol_reference=protocolReference, realm=realm, node_type=osType)
		addLink(runtime, 'Enclosed', nodeId, protocolId)

		## Now create the hardware
		serial_number = biosAttrDict.get('SerialNumber')
		bios_info = biosAttrDict.get('Caption')
		model = csAttrDict.get('Model')
		manufacturer = csAttrDict.get('Manufacturer')
		hardwareId, exists = addObject(runtime, 'HardwareNode', serial_number=serial_number, bios_info=bios_info, model=model, vendor=manufacturer)
		addLink(runtime, 'Usage', nodeId, hardwareId)

		## Update the runtime status to success
		runtime.status(1)

	except:
		runtime.setError(__name__)

	## end createObjects
	return protocolId


def queryForNameRecords(client, runtime, ipAddresses, ipDict):
	try:
		## Only run lookup commands on our IPs, if we have a lookup utility.
		## If the utilities become more numerous, move this to osParameters.
		lookupCmds = [{
			'lookupTest': 'nslookup 127.0.0.1',
			'lookupCommand': 'nslookup',
			'regExParser': '^\s*[Nn]ame:\s*(\S+)\s*$'
		}]
		## Sample nslookup output:
		##  Server:  192.168.121.142
		##  Address:  192.168.121.142
		##
		##  Name:    revelation.local.net
		##  Address:  192.168.121.190
		lookup = None
		for entry in lookupCmds:
			(stdout, stderr, hitProblem) = client.run(entry['lookupTest'])
			if not hitProblem:
				lookup = entry
				break
		if lookup is None:
			## No utility available to issue a local DNS lookup of the IP
			return

		for ipAddress in ipAddresses:
			command = '{} {}'.format(lookup['lookupCommand'], ipAddress)
			(stdout, stderr, hitProblem) = client.run(command)
			runtime.logger.report(' {command!r}: {stdout!r}, {stderr!r}, {hitProblem!r}', command=command, stdout=stdout, stderr=stderr, hitProblem=hitProblem)
			if not hitProblem and stdout is not None and len(stdout.strip()) > 0:
				for line in stdout.splitlines():
					try:
						m = re.search(lookup['regExParser'], line)
						if m:
							recordData = m.group(1)
							domainName = '.'.join(recordData.split('.')[1:])
							if domainName is None or len(domainName) <= 0:
								## Exclude entries without domain extensions
								continue
							if ipAddress not in ipDict:
								ipDict[ipAddress] = []
							ipDict[ipAddress].append((domainName, recordData))
							runtime.logger.report('  resolved name: {valueString!r}', valueString=recordData)
					except:
						stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
						runtime.logger.error('queryForNameRecords: {exception!r}', exception=stacktrace)

	except:
		runtime.setError(__name__)

	## end queryForNameRecords
	return


def queryForIps(client, runtime, ipAddresses):
	"""Query and parse IPs from Win32_NetworkAdapterConfiguration."""
	try:
		## Query Win32_NetworkAdapterConfiguration
		results = client.run('Get-WmiObject -Query "SELECT IPAddress FROM Win32_NetworkAdapterConfiguration WHERE IPEnabled = \'True\'" | select-object IPAddress |fl')
		runtime.logger.report('queryForIps result: {results!r}', results=results)

		for line in results[0].split('\n'):
			try:
				if (line is not None and len(line.strip()) > 0):
					## Samples. First if only IPv4 is enabled on an interface:
					##   ipaddress : {192.168.121.230}
					## Next when both IPv4 and IPv6 are enabled:
					##   ipaddress : {192.168.121.230, fe80::9c8e:e405:771d:197}
					runtime.logger.report('line: {line!r}', line=line)
					m = re.search('^\s*IPAddress\s*:\s*{(.*)}\s*$', line, re.I)
					line = m.group(1)
					for entry in line.split(','):
						ipAddress = entry.strip()
						ipAddresses.append(ipAddress)
			except:
				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				runtime.logger.error('queryForIps Exception: {exception!r}', exception=stacktrace)

	except:
		runtime.setError(__name__)

	## end queryForIps
	return


def queryComputerSystem(client, runtime, attrDict):
	"""Query and parse Win32_ComputerSystem attributes."""
	try:
		## Query Win32_ComputerSystem
		results = client.run('Get-WmiObject -Class Win32_ComputerSystem | select-object DNSHostName,Domain,Manufacturer,Model,Name,PrimaryOwnerName |fl')
		runtime.logger.report('Win32_ComputerSystem result: {results!r}', results=results)
		tmpDict = {}
		parseListFormatToDict(runtime, results[0], tmpDict)
		for keyName in ['DNSHostName', 'Domain', 'Manufacturer', 'Model', 'Name', 'PrimaryOwnerName']:
			attrDict[keyName] = getDictValue(tmpDict, keyName)

	except:
		runtime.setError(__name__)

	## end queryComputerSystem
	return


def queryBios(client, runtime, attrDict):
	"""Query and parse Win32_BIOS attributes."""
	try:
		## Query Win32_BIOS
		results = client.run('Get-WmiObject -Class Win32_BIOS | select-object SerialNumber,Manufacturer,Name,Caption,SoftwareElementID |fl')
		runtime.logger.report('Win32_BIOS result: {results!r}', results=results)
		tmpDict = {}
		parseListFormatToDict(runtime, results[0], tmpDict)
		for keyName in ['SerialNumber', 'Manufacturer', 'Name', 'Caption', 'SoftwareElementID']:
			attrDict[keyName] = getDictValue(tmpDict, keyName)
		## Remove space padding on the primary key
		if attrDict['SerialNumber'] is not None:
			attrDict['SerialNumber'] = attrDict['SerialNumber'].strip()
	except:
		runtime.setError(__name__)

	## end queryBios
	return


def queryOperatingSystem(client, runtime, attrDict):
	"""Query and parse Win32_OperatingSystem attributes."""
	try:
		## Query Win32_OperatingSystem
		results = client.run('Get-WmiObject -Class Win32_OperatingSystem | select-object Manufacturer,Version,Name,Caption |fl')
		runtime.logger.report('Win32_OperatingSystem result: {results!r}', results=results)
		tmpDict = {}
		parseListFormatToDict(runtime, results[0], tmpDict)
		for keyName in ['Manufacturer', 'Version', 'Name', 'Caption']:
			attrDict[keyName] = getDictValue(tmpDict, keyName)

	except:
		runtime.setError(__name__)

	## end queryOperatingSystem
	return


def getDictValue(attrDict, keyName):
	"""Normalize empty strings to Python None type."""
	value = None
	if keyName in attrDict:
		value = attrDict[keyName]
		if value is not None and len(value.strip()) <= 0:
			value = None

	## end getDictValue
	return value


def parseListFormatToDict(runtime, output, data):
	"""Convert PowerShell Format-List type output into Python dictionary."""
	for line in output.split('\n'):
		try:
			if (line and len(line.strip()) > 0):
				lineAsList = line.split(':', 1)
				key = lineAsList[0].strip()
				value = lineAsList[1].strip()
				data[key] = value
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('parseListFormatToDict Exception: {exception!r}', exception=stacktrace)

	## end parseListFormatToDict
	return data


def queryWindows(runtime, client, endpoint, protocolReference, osType):
	"""Run queries against a Windows endpoint.

	Arguments:
	  runtime (dict)    : object used for providing input into jobs and tracking
	                      the job thread through the life of its runtime
	  client            : PowerShell client
	  endpoint          : target endpoint for the discovery job
	  protocolReference : reference id
	"""
	try:
		## Query Win32_OperatingSystem for OS attributes
		osAttrDict = {}
		queryOperatingSystem(client, runtime, osAttrDict)
		runtime.logger.report('osAttrDict: {osAttrDict!r}', osAttrDict=osAttrDict)

		## Only continue if the first query was successful
		if len(list(osAttrDict.keys())) > 0:
			## If connections failed before succeeding, remove false negatives
			runtime.clearMessages()

			## Assign shell configuration and potential config group
			shellParameters = {}
			getInstanceParameters(runtime, client, osType, endpoint, shellParameters)
			runtime.logger.report('shell parameters: {shellParameters!r}', shellParameters=shellParameters)

			## Query Win32_BIOS for serial number and firmware
			biosAttrDict = {}
			queryBios(client, runtime, biosAttrDict)
			runtime.logger.report('biosAttrDict: {biosAttrDict!r}', biosAttrDict=biosAttrDict)

			## Query Win32_ComputerSystem for name/domain and HW details
			csAttrDict = {}
			queryComputerSystem(client, runtime, csAttrDict)
			runtime.logger.report('csAttrDict: {csAttrDict!r}', csAttrDict=csAttrDict)

			## Query Win32_NetworkAdapterConfiguration for IPs
			ipAddresses = []
			queryForIps(client, runtime, ipAddresses)
			runtime.logger.report('ipAddresses: {ipAddresses!r}', ipAddresses=ipAddresses)

			## Associate DNS names to the IPs; unless you have DNS zone discovery
			ipDict = {}
			queryForNameRecords(client, runtime, ipAddresses, ipDict)
			runtime.logger.report('ipDict: {ipDict!r}', ipDict=ipDict)

			## Update the runtime status to success
			runtime.status(1)

			## Create the objects
			protocolId = createObjects(runtime, osType, osAttrDict, biosAttrDict, csAttrDict, ipAddresses, ipDict, endpoint, protocolReference)
			setInstanceParameters(runtime, protocolId, shellParameters)
			#runtime.logger.report('shell parameters: {shellParameters!r}', shellParameters=runtime.results.getObject(protocolId).get('shellConfig'))

	except:
		runtime.setError(__name__)

	## end queryWindows
	return
