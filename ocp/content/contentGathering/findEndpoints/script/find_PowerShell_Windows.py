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

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  0.1 : (CS) Created Jan 24, 2018
  1.0 : (CS) Instrumented shell parameters and config groups, Jun 18, 2018

"""
import sys
import traceback
import re

## From openContentPlatform
from utilities import addObject, addIp, addLink
from utilities import getInstanceParameters, setInstanceParameters


def createObjects(runtime, osType, osAttrDict, biosAttrDict, csAttrDict, ipAddresses, endpoint, protocolReference):
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
		for ip in ipAddresses:
			ipId = None
			if (ip in ['127.0.0.1', '::1', '0:0:0:0:0:0:0:1']):
				## Override realm setting for two reasons: we do not want these
				## IPs in endpoint query results, and we want one per node
				ipId, exists = runtime.results.addIp(address=ip, realm=FQDN)
			else:
				ipId, exists = runtime.results.addIp(address=ip, realm=realm)
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
			runtime.jobStatus == 'SUCCESS'

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

			## Create the objects
			protocolId = createObjects(runtime, osType, osAttrDict, biosAttrDict, csAttrDict, ipAddresses, endpoint, protocolReference)
			setInstanceParameters(runtime, protocolId, shellParameters)
			#runtime.logger.report('shell parameters: {shellParameters!r}', shellParameters=runtime.results.getObject(protocolId).get('shellConfig'))

	except:
		runtime.setError(__name__)

	## end queryWindows
	return
