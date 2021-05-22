"""SNMP detection job.

Functions:
  startJob : standard job entry point
  detectSNMP : attempt to connect to the endpoint via SNMP
  parseNameForDomain : split SNMP sysName into name/domain
  querySystemTable : query base system table
  queryEntityTable : query the physical entity table
  queryHrDeviceDescr : query host device table
  queryIpTable : query ip table
  queryInternalStorageTable : query system device table
  createObjects : create objects and links 

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Oct 9, 2018

"""
import sys
import re
import socket
from contextlib import suppress

## From openContentPlatform
from protocolWrapper import findClients
from utilities import addObject, addIp, addLink


def createObjects(runtime, shortname, domain, description, deviceOID, location, firmware, serialNumber, model, assetId, endpoint, ips, protocolId):
	"""Create objects and links in our results."""
	try:
		## First create the node
		nodeId, exists = addObject(runtime, 'Node', hostname=shortname, domain=domain, description=description, snmp_oid=deviceOID, location=location)
		
		## Now create the hardware
		if serialNumber is not None:
			hardwareId, exists = addObject(runtime, 'HardwareNode', serial_number=serialNumber, bios_info=firmware, model=model, asset_tag=assetId)
			addLink(runtime, 'Usage', nodeId, hardwareId)

		## Now create the IPs
		for ip in ips:
			with suppress(ValueError):
				ipId, exists = addIp(runtime, address=ip)
				addLink(runtime, 'Usage', nodeId, ipId)
		## In case the IP we've connected in on isn't in the IP table list:
		if endpoint not in ips:
			with suppress(ValueError):
				ipId, exists = addIp(runtime, address=endpoint)
				addLink(runtime, 'Usage', nodeId, ipId)

		## Now create the SNMP object
		realm = runtime.jobMetaData.get('realm')
		snmpId, exists = addObject(runtime, 'SNMP', container=nodeId, ipaddress=endpoint, protocol_reference=protocolId, realm=realm, node_type='Unknown')
		addLink(runtime, 'Enclosed', nodeId, snmpId)

		## Update the runtime status to success
		runtime.status(1)

	except:
		runtime.setError(__name__)

	## end createObjects
	return

def queryEntityTable(client, runtime, description):
	"""Query and parse the entity table."""
	## OID dot notation: 1.3.6.1.2.1.47.1.1.1.1
	## .iso.org.dod.internet.mgmt.mib-2.entityMIB == .1.3.6.1.2.1.47
	##    .entityMIBObjects.entityPhysical == .1.1
	##    .entPhysicalTable.entPhysicalEntry == .1.1
	entityOid = '1.3.6.1.2.1.47.1.1.1.1'
	physicalDescription = '1.3.6.1.2.1.47.1.1.1.1.2'
	physicalFirmwareRev = '1.3.6.1.2.1.47.1.1.1.1.9'
	physicalSerialNum   = '1.3.6.1.2.1.47.1.1.1.1.11'
	physicalModelName   = '1.3.6.1.2.1.47.1.1.1.1.13'
	physicalAssetID     = '1.3.6.1.2.1.47.1.1.1.1.15'
	## Query the entityMIB
	snmpResponse = {}
	client.getNext(entityOid, snmpResponse)
	firmware = None
	serialNumber = None
	model = None
	assetId = None

	## Parse response from the 'entity' table
	if len(snmpResponse) > 0:
		newDescription = snmpResponse.get(physicalDescription, None)
		runtime.logger.debug('description: {description!r}', description=newDescription)
		if newDescription is not None:
			runtime.logger.info('Changing description from {description!r} to {newDescription!r}', description=description, newDescription=newDescription)
			description = newDescription
		firmware = snmpResponse.get(physicalFirmwareRev, None)
		runtime.logger.debug('firmware: {firmware!r}', firmware=firmware)
		serialNumber = snmpResponse.get(physicalSerialNum, None)
		runtime.logger.debug('serialNumber: {serialNumber!r}', serialNumber=serialNumber)
		model = snmpResponse.get(physicalModelName, None)
		runtime.logger.debug('model: {model!r}', model=model)
		assetId = snmpResponse.get(physicalAssetID, None)
		runtime.logger.debug('assetId: {assetId!r}', assetId=assetId)
		for oid, value in snmpResponse.items():
			runtime.logger.debug('queryEntityTable SNMP response:  {oid!r} = {value!r}', oid=oid, value=value)

	## end queryEntityTable
	return (description, firmware, serialNumber, model, assetId)


def querySystemTable(client, runtime):
	"""Query and parse the base system table."""
	## RFC1213-MIB
	## .iso.org.dod.internet.mgmt.mib-2.system == .1.3.6.1.2.1.1
	systemOid   = '1.3.6.1.2.1.1'
	sysDescr    = '1.3.6.1.2.1.1.1.0'
	sysObjectID = '1.3.6.1.2.1.1.2.0'
	sysName     = '1.3.6.1.2.1.1.5.0'
	sysLocation = '1.3.6.1.2.1.1.6.0'
	description = None
	deviceOID = None
	name = None
	location = None
	
	## Query the 'system' table
	snmpResponse = {}
	client.getNext(systemOid, snmpResponse)

	## Parse response from the 'system' table
	if len(snmpResponse) > 0:
		description = snmpResponse.get(sysDescr, None)
		runtime.logger.debug('description: {description!r}', description=description)
		name = snmpResponse.get(sysName, None)
		runtime.logger.debug('name: {name!r}', name=name)
		deviceOID = snmpResponse.get(sysObjectID, None)
		runtime.logger.debug('deviceOID: {deviceOID!r}', deviceOID=deviceOID)
		location = snmpResponse.get(sysLocation, None)
		runtime.logger.debug('location: {location!r}', location=location)
		for oid, value in snmpResponse.items():
			runtime.logger.debug('querySystemTable SNMP response:  {oid!r} = {value!r}', oid=oid, value=value)

	## end querySystemTable
	return (name, description, deviceOID, location)


def queryHrDeviceDescr(client, runtime, description):
	"""Query a specific entry from the host table."""
	## HOST-RESOURCES-MIB
	## .iso.org.dod.internet.mgmt.mib-2.host == .1.3.6.1.2.1.25
	##    .hrDevice.hrDeviceTable.hrDeviceEntry.hrDeviceDescr == .3.2.1.3
	hrDeviceDescr = '1.3.6.1.2.1.25.3.2.1.3'
	try:
		## Query the 'host' table
		snmpResponse = {}
		client.getNext(hrDeviceDescr, snmpResponse)

		## Parse response from the 'host' table
		count = len(list(snmpResponse.keys()))
		if count >= 0 and count <= 2:
			runtime.logger.debug('queryHrDeviceDescr has length of {count!r} : {snmpResponse!r}', count=count, snmpResponse=snmpResponse)
			if count == 2 and '1.3.6.1.2.1.25.3.2.1.3' in snmpResponse:
				## Remove the base OID, which won't have a value
				del(snmpResponse['1.3.6.1.2.1.25.3.2.1.3'])
				count = len(list(snmpResponse.keys()))
				runtime.logger.report('queryHrDeviceDescr has length of {} : {}'.format(count, snmpResponse))
			if count == 1:
				## Server type endpoints will have many entries in this table,
				## but specialty device types may have just one. The specialty
				## types are being targeted in this code block. Sampling some
				## devices, I noticed an office printer had just one entry...
				## that was more descriptive about itself than the sysDescr. The
				## sysDescr returns "HP ETHERNET MULTI-ENVIRONMENT" whereas this
				## table returns "OfficeJet Pro 7740 Wide Format All-in-One".
				for oid, value in snmpResponse.items():
					runtime.logger.debug('queryHrDeviceDescr SNMP response:  {oid!r} = {value!r}', oid=oid, value=value)
					## Get first/only value from the dictionary, regardless of oid
					newDescr = value
					break

				runtime.logger.info('Changing description from {description!r} to {newDescr!r}', description=description, newDescr=newDescr)
				description = newDescr

	except:
		runtime.setError(__name__)

	## end queryHrDeviceDescr
	return description


def queryIpTable(client, runtime, ips):
	"""Query and parse the ip table."""
	## RFC1213-MIB
	## .iso.org.dod.internet.mgmt.mib-2.ip == .1.3.6.1.2.1.4
	##    .ipAddrTable.ipAddrEntry.ipAdEntAddr == .20.1.1
	ipAddrEntryOid = '1.3.6.1.2.1.4.20.1.1'
	try:
		## Query the 'ip' table
		snmpResponse = {}
		client.getNext(ipAddrEntryOid, snmpResponse)

		## Parse response from the 'ip' table
		for oid, value in snmpResponse.items():
			runtime.logger.debug('queryIpTable SNMP response:  {oid!r} = {value!r}', oid=oid, value=value)
			ipIgnoreList = ['127.0.0.1', '0.0.0.0', '::1', '::0']
			## Special parsing since the IP Address is added to the end of OID
			## and unfortunately is not instead within the value of the OID:
			matchString = '^' + ipAddrEntryOid + '\.(.+)$'
			m = re.search(matchString, oid)
			if m and m.group(1):
				value = m.group(1)
				if value in ipIgnoreList:
					continue
				## Validate IP with Python's library when creating at the top
				ips.append(value)

	except:
		runtime.setError(__name__)

	## end queryIpTable
	return


def queryInternalStorageTable(client, runtime, storage):
	"""Query and parse hrStorage data."""
	## RFC1213-MIB
	## .iso.org.dod.internet.mgmt.mib-2.host == .1.3.6.1.2.1.25
	##    .hrDevice.hrDeviceTable.hrDeviceEntry.hrDeviceDescr == .3.2.1.3
	ipAddrEntryOid = '.1.3.6.1.2.1.25.2.3.1.3'
	try:
		## Query the 'ip' table
		snmpResponse = {}
		client.getNext(ipAddrEntryOid, snmpResponse)

		## Parse response from the 'ip' table
		for oid, value in snmpResponse.items():
			runtime.logger.debug('queryInternalStorageTable SNMP response:  {oid!r} = {value!r}', oid=oid, value=value)
			storage.append(value)

	except:
		runtime.setError(__name__)

	## end queryInternalStorageTable
	return


def parseNameForDomain(runtime, name, endpoint):
	"""Split SNMP sysName into name/domain. Alternatively, use a lookup."""
	shortName = None
	domain = None
	try:
		## Get a handle on a required input parameter
		queryForFQDN = runtime.parameters.get('queryForFQDN', True)
		runtime.logger.debug('queryForFQDN = {queryForFQDN!r}', queryForFQDN=queryForFQDN)

		## Prefer to pull domain off the name, when it exists as an FQDN;
		## alternatively we can pull from a DNS/socket lookup when missing:
		m = re.search('^([^.]+)(\.(.*))?$', name)
		shortName = m.group(1)
		domain = m.group(3) or None

		if domain is None and queryForFQDN is True:
			try:
				runtime.logger.error('Attempting socket lookup...')
				socketResponse = socket.getfqdn(endpoint)
				runtime.logger.error('   socket lookup returned {socketResponse!r}', socketResponse=socketResponse)
				m = re.search('^([^.]+)(\.(.*))?$', socketResponse)
				## Don't override the shortName if we came up empty with DNS
				if not m.group(1).isdigit():
					shortName = m.group(1)
					domain = m.group(3) or None

			except:
				runtime.setError(__name__)
	except:
		runtime.setError(__name__)

	## end parseNameForDomain
	return (shortName, domain)


def querySNMP(runtime, client, endpoint, protocolId):
	"""Run queries against the endpoint.

	Arguments:
	  runtime (dict)    : object used for providing input into jobs and tracking
	                      the job thread through the life of its runtime
	"""
	try:
		## Query the base system table (in RFC1213-MIB)
		(name, description, deviceOID, location) = querySystemTable(client, runtime)

		## Only continue if the first query was successful
		if name is not None:
			## If connections failed before succeeding, remove false negatives
			runtime.clearMessages()

			## Query the entity table
			(description, firmware, serialNumber, model, assetId) = queryEntityTable(client, runtime, description)
			
			## Query a specific entry from the host table (in HOST-RESOURCES-MIB)
			description = queryHrDeviceDescr(client, runtime, description)

			## Query the ip table (in RFC1213-MIB)
			ips = []
			queryIpTable(client, runtime, ips)

			## Split the sysName into a short name with domain, if/when possible
			## since the primary constraints for the Node are hostname & domain.
			(shortname, domain) = parseNameForDomain(runtime, name, endpoint)

			## Update the runtime status to success
			runtime.status(1)

			## Create the objects
			protocolId = client.getId()
			createObjects(runtime, shortname, domain, description, deviceOID, location, firmware, serialNumber, model, assetId, endpoint, ips, protocolId)

	except:
		runtime.setError(__name__)

	## end querySNMP
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

		## Go through SNMP protocol entries and attempt a connection
		clients = findClients(runtime, 'ProtocolSnmp')
		for client in clients:
			protocolId = None
			try:
				protocolId = client.getId()
				client.open()

			except:
				msg = str(sys.exc_info()[1])
				## Add search/replacements to cleanup messages if needed...
				runtime.logger.error('Exception with {name!r} trying {endpoint!r} with protocol ID {protocolId!r}: {msg!r}', name=__name__, endpoint=endpointString, protocolId=protocolId, msg=msg)
				runtime.status(3)
				runtime.message(msg)
				continue

			## Do the work
			querySNMP(runtime, client, endpointString, protocolId)

			## If we connected and ran queries, break out of the detection loop
			if runtime.jobStatus == 'SUCCESS':
				break

	except:
		runtime.setError(__name__)

	## end startJob
	return
