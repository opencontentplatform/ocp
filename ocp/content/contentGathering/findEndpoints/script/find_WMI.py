"""WMI detection job.

Functions:
  startJob : standard job entry point
  queryOperatingSystem : query Win32_OperatingSystem
  queryBios : query Win32_BIOS
  queryComputerSystem : query Win32_ComputerSystem
  queryForIps : query Win32_NetworkAdapterConfiguration
  detectWMI : attempt to connect to the endpoint via WMI
  createObjects: Create objects and links

"""
import sys
import traceback
import time
import re
import ipaddress
from contextlib import suppress

## From openContentPlatform
from protocolWrapper import findClients
from utilities import runPortTest, addObject, addIp, addLink


def createObjects(runtime, osAttrDict, biosAttrDict, csAttrDict, ipAddresses, endpoint, protocolId):
	"""Create objects and links in our results."""
	try:
		## First create the node
		domain = csAttrDict.get('Domain', None)
		hostname = csAttrDict.get('Name', None)
		vendor = osAttrDict.get('Manufacturer', None)
		platform = osAttrDict.get('Caption', None)
		version = osAttrDict.get('Version', None)
		hw_provider = csAttrDict.get('Manufacturer', None)
		nodeId, exists = addObject(runtime, 'Node', hostname=hostname, domain=domain, vendor=vendor, platform=platform, version=version, hardware_provider=hw_provider)

		## Now create the IPs
		for ip in ipAddresses:
			with suppress(ValueError):
				ipId, exists = addIp(runtime, address=ip)
				addLink(runtime, 'Usage', nodeId, ipId)
		## In case the IP we've connected in on isn't in the IP table list:
		if endpoint not in ipAddresses:
			with suppress(ValueError):
				ipId, exists = addIp(runtime, address=endpoint)
				addLink(runtime, 'Usage', nodeId, ipId)

		## Now create the WMI object
		realm = runtime.jobMetaData.get('realm')
		snmpId, exists = addObject(runtime, 'WMI', container=nodeId, ipaddress=endpoint, protocol_reference=protocolId, realm=realm, node_type='Windows')
		addLink(runtime, 'Enclosed', nodeId, snmpId)

		## Now create the hardware
		serial_number = biosAttrDict.get('SerialNumber', None)
		bios_info = biosAttrDict.get('Caption', None)
		model = csAttrDict.get('Model', None)
		manufacturer = csAttrDict.get('Manufacturer', None)
		hardwareId, exists = addObject(runtime, 'HardwareNode', serial_number=serial_number, bios_info=bios_info, model=model, vendor=manufacturer)
		addLink(runtime, 'Usage', nodeId, hardwareId)

		## Update the runtime status to success
		runtime.status(1)

	except:
		runtime.setError(__name__)

	## end createObjects
	return


def queryForIps(client, runtime, ipAddresses):
	"""Query and parse Win32_NetworkAdapterConfiguration attributes."""
	try:
		## Query Win32_NetworkAdapterConfiguration
		for obj in client.query('SELECT IPAddress FROM Win32_NetworkAdapterConfiguration WHERE IPEnabled = \'True\''):
			## Sample: ('192.168.121.220', 'fe80::3826:b066:b6f5:f4e2')
			for entry in obj.IPAddress:
				value = str(entry).strip()
				## Validate IP with Python's library when creating at the top
				ipAddresses.append(value)
				runtime.logger.debug('Win32_NetworkAdapterConfiguration: IP = {ipAddress!r}', ipAddress=value)

	except:
		runtime.setError(__name__)

	## end queryForIps
	return


def queryComputerSystem(client, runtime, attrDict):
	"""Query and parse Win32_ComputerSystem attributes."""
	try:
		## Query Win32_ComputerSystem
		for obj in client.Win32_ComputerSystem():
			attrDict['DNSHostName'] = obj.DNSHostName
			attrDict['Domain'] = obj.Domain
			attrDict['Manufacturer'] = obj.Manufacturer
			attrDict['Model'] = obj.Model
			attrDict['Name'] = obj.Name
			attrDict['PrimaryOwnerName'] = obj.PrimaryOwnerName
			for key,value in attrDict.items():
				runtime.logger.debug('Win32_ComputerSystem: {key!r} = {value!r}', key=key, value=value)
			if len(list(attrDict.keys())) > 0:
				## We only need/want the first entry
				break

	except:
		runtime.setError(__name__)

	## end queryComputerSystem
	return


def queryBios(client, runtime, attrDict):
	"""Query and parse Win32_BIOS attributes."""
	try:
		## Query Win32_BIOS
		for obj in client.Win32_BIOS():
			attrDict['SerialNumber'] = obj.SerialNumber
			## Remove space padding on the primary key
			if attrDict['SerialNumber'] is not None:
				attrDict['SerialNumber'] = attrDict['SerialNumber'].strip()
			attrDict['Manufacturer'] = obj.Manufacturer
			attrDict['Name'] = obj.Name
			attrDict['Caption'] = obj.Caption
			attrDict['SoftwareElementID'] = obj.SoftwareElementID
			for key,value in attrDict.items():
				runtime.logger.debug('Win32_BIOS: {key!r} = {value!r}', key=key, value=value)
			if len(list(attrDict.keys())) > 0:
				## We only need/want the first entry
				break

	except:
		runtime.setError(__name__)

	## end queryBios
	return


def queryOperatingSystem(client, runtime, attrDict):
	"""Query and parse Win32_OperatingSystem attributes."""
	try:
		## Query Win32_OperatingSystem
		for obj in client.Win32_OperatingSystem():
			attrDict['Manufacturer'] = obj.Manufacturer
			attrDict['Name'] = obj.Name
			attrDict['Caption'] = obj.Caption
			attrDict['Version'] = obj.Version
			for key,value in attrDict.items():
				runtime.logger.debug('Win32_OperatingSystem: {key!r} = {value!r}', key=key, value=value)
			if len(list(attrDict.keys())) > 0:
				## We only need/want the first entry
				break

	except:
		runtime.setError(__name__)

	## end queryOperatingSystem
	return


def queryWMI(runtime, client, endpoint, protocolId):
	"""Run queries against the endpoint.

	Arguments:
	  runtime (dict)    : object used for providing input into jobs and tracking
	                      the job thread through the life of its runtime
	"""
	try:
		## Query Win32_OperatingSystem for OS attributes
		osAttrDict = {}
		queryOperatingSystem(client, runtime, osAttrDict)

		## Only continue if the first query was successful
		if len(list(osAttrDict.keys())) > 0:
			## If connections failed before succeeding, remove false negatives
			runtime.clearMessages()

			## Query Win32_BIOS for serial number and firmware
			biosAttrDict = {}
			queryBios(client, runtime, biosAttrDict)

			## Query Win32_ComputerSystem for name/domain and HW details
			csAttrDict = {}
			queryComputerSystem(client, runtime, csAttrDict)

			## Query Win32_NetworkAdapterConfiguration for IPs
			ipAddresses = []
			queryForIps(client, runtime, ipAddresses)

			## Update the runtime status to success
			runtime.status(1)

			## Create the objects
			createObjects(runtime, osAttrDict, biosAttrDict, csAttrDict, ipAddresses, endpoint, protocolId)

	except:
		runtime.setError(__name__)

	## end queryWMI
	return


def attemptConnection(runtime, endpointString):
	"""Go through WMI protocol entries and attempt a connection."""
	client = None
	try:
		clients = findClients(runtime, 'ProtocolWmi')
		for client in clients:
			doNotContinue = False
			protocolId = None
			try:
				protocolId = client.getId()
				client.open()

			except:
				msg = str(sys.exc_info()[1])
				## Cleanup message when we know what they are:
				## "<x_wmi: The RPC server is unavailable.  (-2147023174, 'The RPC server is unavailable. ', (0, None, 'The RPC server is unavailable. ', None, None, -2147023174), None)>"
				## "<x_wmi: Access is denied.  (-2147024891, \'Access is denied. \', (0, None, \'Access is denied. \', None, None, -2147024891), None)>"
				if re.search('The RPC server is unavailable', msg, re.I):
					## Remove the rest of the fluff
					msg = 'The RPC server is unavailable'
					## This type of failure means the endpoint is unavailable
					doNotContinue = True
				if re.search('Access is denied', msg, re.I):
					## Remove the rest of the fluff
					msg = 'Access is denied'
				runtime.logger.error('Exception with {name!r} trying {endpoint!r} with protocol ID {protocolId!r}: {msg!r}', name=__name__, endpoint=endpointString, protocolId=protocolId, msg=msg)
				runtime.status(3)
				runtime.message(msg)
				if doNotContinue:
					break
				continue

			## Do the work
			queryWMI(runtime, client.connection, endpointString, protocolId)

			## If we connected and ran queries, break out of the detection loop
			if runtime.jobStatus == 'SUCCESS':
				break

	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end attemptConnection
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		endpointString = runtime.endpoint.get('data', {}).get('address')
		runtime.logger.report('endpointString: {endpointString}', endpointString=endpointString)
		if runtime.jobMetaData.get('realm') is None:
			runtime.logger.warn('Skipping job {name!r} on endpoint {endpoint!r}; realm is not set in job configuration.', name=__name__, endpoint=endpointString)
			return
		runtime.logger.report('Running job {name!r} on endpoint {endpoint!r}', name=__name__, endpoint=endpointString)

		## Port test if user requested via parameters
		continueFlag = True
		portTest = runtime.parameters.get('portTestBeforeConnectionAttempt', False)
		if portTest:
			ports = runtime.parameters.get('portsToTest', [])
			portIsActive = runPortTest(runtime, endpointString, ports)
			if not portIsActive:
				runtime.setWarning('Endpoint not listening on ports {}; skipping WMI attempt.'.format(str(ports)))
				continueFlag = False

		if continueFlag:
			attemptConnection(runtime, endpointString)

	except:
		runtime.setError(__name__)

	## end startJob
	return
