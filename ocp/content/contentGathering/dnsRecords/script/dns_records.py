"""Import a custom CSV according to a descriptor file.

Functions:
  startJob : Standard job entry point
  normalizeEmptyParameters : Helper to normalize empty JSON parameters to 'None'
  processCsvFile : Open the CSV and action on each row
  parseCsvRecord : Parse and validate a row in the CSV
  createCIsForThisRecord: Create and relate objects
"""
import sys
import traceback
import os
import json
import re
import socket
from time import time
from contextlib import suppress

## From openContentPlatform
from protocolWrapper import getClient
from utilities import addObject, addIp, addLink
from utilities import verifyJobRuntimePath, cleanupJobRuntimePath
from utilities import getApiQueryResultsInChunks
from utilities import RealmUtility


def createNewIp(runtime, trackedIPs, thisIP):
	"""Reduce the number of times we lookup an IP and add to the results."""
	if thisIP in trackedIPs:
		return trackedIPs.get(thisIP)
	ipId, exists = addIp(runtime, address=thisIP)
	trackedIPs[thisIP] = ipId

	## end createNewIp
	return ipId


def createObjects(runtime, realmUtil, trackedZones, trackedIPs, recordData, domainName, ownerName, trackEveryIpInDNS, trackEveryIpInDB, trackIPsInRealm, ipAddrToIdDict):
	"""Conditionally create IPs and link in the records."""
	recordId = None
	ipId = None
	## If we are told to create all DNS content, do not check values
	if not trackEveryIpInDNS:
		## Otherwise, we have two more conditions to check...
		## if told to create DNS for all IPs already resident in the DB
		if trackEveryIpInDB:
			if recordData in ipAddrToIdDict:
				ipId = ipAddrToIdDict[recordData]
				runtime.logger.report('   trackedByDB using id: {ipId!r}', ipId=ipId)
				addObject(runtime, 'IpAddress', uniqueId=ipId)
			elif trackIPsInRealm:
				if not realmUtil.isIpInRealm(recordData):
					runtime.logger.report('   ... skipping IP {recordData!r} because it is neither in the DB nor in the realm configuration', recordData=recordData)
					return recordId
			else:
				runtime.logger.report('   ... skipping IP {recordData!r} because it is not in the DB', recordData=recordData)
				return recordId
		elif trackIPsInRealm:
			if not realmUtil.isIpInRealm(recordData):
				runtime.logger.report('   ... skipping IP {recordData!r} because it is not in the realm configuration', recordData=recordData)
				return recordId

	## Create the IP first (if not using a handle from the DB)
	if ipId is None:
		try:
			ipId = createNewIp(runtime, trackedIPs, recordData)
		except ValueError:
			runtime.logger.report('ValueError in getThisIp: {valueError!r}', valueError=str(sys.exc_info()[1]))
			return recordId

	## Create the zone if necessary
	if domainName not in trackedZones.keys():
		## Add the zone onto (or back onto) the result set
		zoneId, exists = addObject(runtime, 'Domain', name=domainName)
		trackedZones[domainName] = zoneId
	zoneId = trackedZones[domainName]

	## Create the DNS record
	recordId, exists = addObject(runtime, 'NameRecord', name=ownerName, value=recordData)
	addLink(runtime, 'Enclosed', zoneId, recordId)
	addLink(runtime, 'Usage', ipId, recordId)

	## end createObjects
	return recordId


def resolveIntoIPs(runtime, name):
	"""Helper function for the DNS lookup."""
	ipaddrlist = []
	try:
		(hostname, aliaslist, ipaddrlist) = socket.gethostbyname_ex(name)
	except:
		runtime.logger.report('  unable to resolve an IP for {name!r}', name=name)

	## end resolveIntoIPs
	return ipaddrlist


def adhearToChunks(runtime, sizeThreshold, trackedZones, trackedIPs):
	if (runtime.results.size() > sizeThreshold):
		runtime.logger.report('   result to send: {result!r}', result=runtime.results.getJson())
		runtime.sendToKafka()
		trackedZones.clear()
		trackedIPs.clear()

	## end adhearToChunks
	return


def createAndMapAliases(runtime, targetId, targetName, targetDomain, trackedZones, domainDict, knownCnames):
	"""Create and link associated aliases."""
	try:
		runtime.logger.report('    Looking for aliases of {targetName!r}', targetName=targetName)
		## Map through aliases if any exist
		if targetDomain in domainDict.keys():
			domainCnameDict = domainDict[targetDomain]
			if targetName in domainCnameDict.keys():
				(sourceName, sourceDomain) = domainCnameDict[targetName]
				runtime.logger.report('      {targetName!r} has related alias {sourceName!r}', targetName=targetName, sourceName=sourceName)
				knownCnames[targetName] = 1

				## Create the zone if necessary
				if sourceDomain not in trackedZones.keys():
					## Add the zone onto (or back onto) the result set
					zoneId, exists = addObject(runtime, 'Domain', name=sourceDomain)
					trackedZones[sourceDomain] = zoneId
				zoneId = trackedZones[sourceDomain]

				## Create the record
				sourceId, exists = addObject(runtime, 'NameRecord', name=sourceName, value=targetName)
				addLink(runtime, 'Enclosed', zoneId, sourceId)
				addLink(runtime, 'Route', sourceId, targetId)

				## See if there are aliases for this alias
				createAndMapAliases(runtime, sourceId, sourceName, sourceDomain, trackedZones, domainDict, knownCnames)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in createAndMapAliases: {stacktrace!r}', stacktrace=stacktrace)

	## end createAndMapAliases
	return


def resolveUnknownCNAMEs(runtime, domains, realmUtil, trackedZones, trackedIPs, domainDict, knownCnames, chunkSize, ipAddrToIdDict, trackEveryIpInDNS, trackEveryIpInDB, trackIPsInRealm):
	"""Handly any CNAMEs that were not previously correlated"""
	try:
		runtime.logger.report(' -------------- resolveUnknownCNAMEs')
		## Map through aliases if any exist
		for thisDomain in domainDict.keys():
			domainCnameDict = domainDict[thisDomain]
			for thisName in domainCnameDict.keys():
				if thisName not in knownCnames.keys():
					## Process unresolved CNAME record

					## Let users know when they should add more domains to
					## the zone transfer list for future job executions:
					if thisDomain not in domains:
						runtime.logger.error('CNAME refers to zone that was not discovered: {thisDomain!r}', thisDomain=thisDomain)

					runtime.logger.report('  Looking up unknown alias {aliasName!r}', aliasName=thisName)
					ips = resolveIntoIPs(runtime, thisName)
					if len(ips) <= 0:
						continue

					for thisIp in ips:
						runtime.logger.report('   --> found IP {thisIp!r}', thisIp=thisIp)
						## Create IP, DNS record, zone, and relationships
						recordId = createObjects(runtime, realmUtil, trackedZones, trackedIPs, thisIp, thisDomain, thisName, trackEveryIpInDNS, trackEveryIpInDB, trackIPsInRealm, ipAddrToIdDict)
						if recordId is None:
							continue
						knownCnames[thisName] = 1
						(sourceName, sourceDomain) = domainCnameDict[thisName]
						runtime.logger.report('      --> Following alias: {sourceName!r}', sourceName=sourceName)
						createAndMapAliases(runtime, recordId, sourceName, sourceDomain, trackedZones, domainDict, knownCnames)

					## Adhear to the chunk size request
					adhearToChunks(runtime, chunkSize, trackedZones, trackedIPs)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in resolveUnknownCNAMEs: {stacktrace!r}', stacktrace=stacktrace)

	## Send back remaining set
	adhearToChunks(runtime, 0, trackedZones, trackedIPs)

	## end resolveUnknownCNAMEs
	return


def parseRecords(runtime, client, jobRuntimePath, realmUtil, domain, trackedZones, trackedIPs, domainDict, knownCnames, chunkSize, ipAddrToIdDict, trackEveryIpInDNS, trackEveryIpInDB, trackIPsInRealm):
	"""Query the A-type records from WMI."""
	count = 0
	## Open the custom domain transfer file for reading
	domainFile = os.path.join(jobRuntimePath, '{}.records'.format(domain))
	## Sample file format:
	###############################################
	## A test1server.domain.com 10.0.21.132
	## AAAA myserver.domain.com 2620:149:4:101::13a
	###############################################
	for line in open(domainFile):
		try:
			matchLine = re.search('(\S+)\s(\S+)\s(\S+.*)', line)
			if matchLine:
				recordType = matchLine.group(1)
				ownerName = matchLine.group(2).lower().strip()
				recordData = matchLine.group(3).lower().strip()
				runtime.logger.report('  {recordType!r} record {ownerName!r} -> {recordData!r}', recordType=str(recordType), ownerName=str(ownerName), recordData=str(recordData))

				## Create IP, DNS record, zone, and relationships
				recordId = createObjects(runtime, realmUtil, trackedZones, trackedIPs, recordData, domain, ownerName, trackEveryIpInDNS, trackEveryIpInDB, trackIPsInRealm, ipAddrToIdDict)
				if recordId is None:
					continue
				count = count + 1
				## Create and link any aliases
				createAndMapAliases(runtime, recordId, ownerName, domain, trackedZones, domainDict, knownCnames)

				## Adhear to the chunk size request
				adhearToChunks(runtime, chunkSize, trackedZones, trackedIPs)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in parseRecords: {stacktrace!r}', stacktrace=stacktrace)

	## Send back remaining set
	adhearToChunks(runtime, 0, trackedZones, trackedIPs)
	runtime.logger.report('    Parsed {count!r} records from domain {domain!r}', count=count, domain=domain)

	## end parseRecords
	return


def parseAliases(runtime, domainDict, jobRuntimePath):
	"""Parse CNAMES from the local cache."""
	count = 0
	## Open local file with CNAMEs for reading
	cnameFile = os.path.join(jobRuntimePath, 'cname.records')
	## Sample file format:
	###############################################
	## chris.site.leveragediscovery.com -> chris.lab.leveragediscovery.com
	###############################################
	for line in open(domainFile):
		try:
			matchLine = re.search('(\S+) -> (\S+)', line)
			if matchLine:
				aliasName = matchLine.group(1)
				recordData = matchLine.group(2)

				## Parse out the source/destination domains
				sourceDomain = None
				m = re.search('^[^.]+[.](\S+)', aliasName)
				if m:
					sourceDomain = m.group(1)
				targetDomain = None
				m = re.search('^[^.]+[.](\S+)', recordData)
				if m:
					targetDomain = str(m.group(1))

				## Add the CNAME onto the list
				if ((recordData is not None) and (len(recordData.strip()) > 0) and
					(aliasName is not None) and (len(aliasName.strip()) > 0)):

					## Create the domain if it hasn't been referenced yet:
					if targetDomain not in domainDict.keys():
						domainDict[targetDomain] = {}
					domainCnameDict = domainDict[targetDomain]
					#domainCnameDict[str(recordData)] = (str(aliasName), str(sourceDomain))
					domainCnameDict[recordData] = (aliasName, sourceDomain)
					domainDict[targetDomain] = domainCnameDict
					count = count + 1

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in parseAliases: {stacktrace!r}', stacktrace=stacktrace)

	runtime.logger.report('   Parsed {count!r} CNAMEs.', count=count)
	for thisDomain in domainDict.keys():
		runtime.logger.report('   {domainCount!r} CNAMEs in domain {thisDomain!r}.', domainCount=len(domainDict[thisDomain]), thisDomain=thisDomain)

	## end parseAliases
	return


def writeRecords(runtime, fileHandle, recordType, resultSet):
	"""Write records into a cached zone file for parsing."""
	for obj in resultSet:
		try:
			ownerName = obj.OwnerName
			recordData = obj.RecordData
			## Write the IPv4 and IPv6 A Records
			if ((ownerName is not None) and (len(ownerName.strip()) > 0) and
				(recordData is not None) and (len(recordData.strip()) > 0)):
				fileHandle.write('{} {} {}\n'.format(recordType, ownerName, recordData))
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.report('  Failure in writeRecords: {stacktrace!r}', stacktrace=stacktrace)

	## end writeRecords
	return


def doQuery(runtime, client, wmiClass, domain):
	"""Query WMI for records of requested type."""
	result = None
	try:
		## Sample: 'SELECT OwnerName,RecordData FROM MicrosoftDNS_AType WHERE ContainerName = "mydomain"'
		wmiQuery = 'SELECT OwnerName,RecordData FROM {} WHERE ContainerName = "{}"'.format(wmiClass, domain)
		result = client.query(wmiQuery)
	except:
		msg = str(sys.exc_info()[1])
		runtime.logger.error('Failed WMI query for {wmiClass!r} on domain {domain!r}: {msg!r}', wmiClass=wmiClass, domain=domain, msg=msg)
		runtime.setErrorMsg(__name__)

	## end doQuery
	return result


def getDomainRecords(runtime, client, domain, jobRuntimePath):
	"""Query and track IPv4 and IPv6 records."""
	## Prepare local file for the zone info
	domainFile = os.path.join(jobRuntimePath, '{}.records'.format(domain))
	fileHandle = open(domainFile, 'w')

	runtime.logger.report(' Query domain {domain!r}...', domain=domain)
	for recordType in ['A', 'AAAA']:
		## Time the DNS query
		startTime = time()
		resultSet = doQuery(runtime, client, 'MicrosoftDNS_{}Type'.format(recordType), domain)
		endTime = time()
		totalSecs = endTime - startTime
		runtime.logger.report('   {recordType!r} record query time in seconds: {totalSecs!r}', recordType=recordType, totalSecs=totalSecs)

		## Write records into a temporary zone file for parsing
		writeRecords(runtime, fileHandle, recordType, resultSet)

	## Close the local zone file
	if fileHandle:
		fileHandle.flush()
		fileHandle.close()

	## end getDomainRecords
	return


def queryAndParseAliases(runtime, client, domainDict, jobRuntimePath):
	"""Query and track all CNAME records."""
	## Prepare local file for all CNAMEs
	cnameFile = os.path.join(jobRuntimePath, 'cname.records')
	fileHandle = open(cnameFile, 'w')
	count = 0
	for obj in client.MicrosoftDNS_CNAMEType():
		try:
			containerName = obj.ContainerName
			aliasName = obj.OwnerName
			recordData = obj.RecordData

			## We don't want some entries (..cache, ..roothints, system data)
			if (re.search('^\.\.', containerName) or
				re.search('_msdcs\.', containerName.lower())):
				runtime.logger.report(' skipping CNAME {containerName!r}: {aliasName!r} -> {recordData!r}', containerName=containerName, aliasName=aliasName, recordData=recordData)
				continue
			runtime.logger.report(' CNAME {containerName!r}: {aliasName!r} -> {recordData!r}', containerName=containerName, aliasName=aliasName, recordData=recordData)

			## remove the trailing dot on the recordData
			m = re.search('^(.*)\.$' , recordData.strip())
			recordData = m.group(1)

			## Parse out the source/destination domains
			sourceDomain = None
			m = re.search('^[^.]+[.](\S+)', aliasName)
			if m:
				sourceDomain = m.group(1)
			targetDomain = None
			m = re.search('^[^.]+[.](\S+)', recordData)
			if m:
				targetDomain = str(m.group(1))

			## Add the CNAME onto the list
			if ((recordData is not None) and (len(recordData.strip()) > 0) and
				(aliasName is not None) and (len(aliasName.strip()) > 0)):

				fileHandle.write('{} -> {}\n'.format(aliasName, recordData))
				## Create the domain if it hasn't been referenced yet:
				if targetDomain not in domainDict.keys():
					domainDict[targetDomain] = {}
				domainCnameDict = domainDict[targetDomain]
				#domainCnameDict[str(recordData)] = (str(aliasName), str(sourceDomain))
				domainCnameDict[recordData] = (aliasName, sourceDomain)
				domainDict[targetDomain] = domainCnameDict
				count = count + 1

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in queryAndParseAliases: {stacktrace!r}', stacktrace=stacktrace)

	runtime.logger.report('   Parsed {count!r} total CNAME-type records...', count=count)
	for thisDomain in domainDict.keys():
		runtime.logger.report('   {domainCount!r} CNAMEs in domain {thisDomain!r}.', domainCount=len(domainDict[thisDomain]), thisDomain=thisDomain)

	## Close the local file
	if fileHandle:
		fileHandle.flush()
		fileHandle.close()

	## end queryAndParseAliases
	return


def queryDnsSoaViaWMI(runtime, client, domains):
	"""Get the list of zones/domains on the Microsoft DNS server."""
	for obj in client.MicrosoftDNS_Zone():
		try:
			domainName = obj.Name
			masterServers = obj.MasterServers
			## Skip reverse zones and TrustAnchors
			if (not re.search('in-addr.arpa', domainName) and domainName != 'TrustAnchors'):
				runtime.logger.report(' Found domain: {domainName!r}', domainName=domainName)
				domains.append(domainName)
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in queryDnsSoaViaWMI: {stacktrace!r}', stacktrace=stacktrace)

	## end queryDnsSoaViaWMI
	return


def doWork(runtime, client, ipAddrToIdDict, jobRuntimePath, realmUtil):
	"""Main worker function."""
	## Read/initialize parameters
	trackEveryIpInDNS = runtime.parameters.get('trackEveryIpInDNS', False)
	trackEveryIpInDB = runtime.parameters.get('trackEveryIpInDB', False)
	trackIPsInRealm = runtime.parameters.get('trackIPsInRealm', True)
	pullDnsRecordsFromCache = runtime.parameters.get('pullDnsRecordsFromCache', False)
	chunkSize = runtime.parameters.get('chunkSize', 100)
	lookupMissingRecords = runtime.parameters.get('lookupMissingRecords', True)
	domains = []

	## Get the list of zones/domains on the Microsoft DNS server.
	queryDnsSoaViaWMI(runtime, client, domains)
	if len(domains) > 0:

		## Query and track all CNAME records
		domainDict = {}
		runtime.logger.report(' Gathering CNAME-type records...')
		if not pullDnsRecordsFromCache:
			queryAndParseAliases(runtime, client, domainDict, jobRuntimePath)
		else:
			parseAliases(runtime, domainDict, jobRuntimePath)

		trackedZones = {}
		trackedIPs = {}
		knownCnames = {}
		## Dump the DNS A and AAAA-type records to files for parsing. I'm
		## not parsing in place because I want to minimize the time talking
		## to the DNS server; also it's easier to troubleshoot if we can do
		## that on cached files instead. Parsing occurs after this step.
		runtime.logger.report(' Gathering A-type records...')
		if not pullDnsRecordsFromCache:
			for domain in domains:
				getDomainRecords(runtime, client, domain, jobRuntimePath)

		## Now parse records, one zone/domain at a time
		for domain in domains:
			parseRecords(runtime, client, jobRuntimePath, realmUtil, domain, trackedZones, trackedIPs, domainDict, knownCnames, chunkSize, ipAddrToIdDict, trackEveryIpInDNS, trackEveryIpInDB, trackIPsInRealm)

		## Handle any CNAMEs that were not previously correlated
		if (lookupMissingRecords):
			resolveUnknownCNAMEs(runtime, domains, realmUtil, trackedZones, trackedIPs, domainDict, knownCnames, chunkSize, ipAddrToIdDict, trackEveryIpInDNS, trackEveryIpInDB, trackIPsInRealm)

	## end doWork
	return


def transformIpResultsFromApi(runtime, ipAddrToIdDict, queryResults):
	"""Create a dictionary of IpAddress(key):ObjectId(value) pairs."""
	for entry in queryResults.get('objects', []):
		objectId = entry.get('identifier')
		ipAddress = entry.get('data').get('address')
		if (ipAddress in ['127.0.0.1', '::1', '0:0:0:0:0:0:0:1', '0.0.0.0', '::0', '0:0:0:0:0:0:0:0']):
			continue
		ipAddrToIdDict[ipAddress] = objectId

	## end transformIpResultsFromApi
	return


def getCurrentIps(runtime, ipAddrToIdDict):
	"""Pull IPs from the database."""
	targetQuery = runtime.parameters.get('targetQuery')
	queryFile = os.path.join(runtime.env.contentGatheringPkgPath, 'dnsRecords', 'input', targetQuery + '.json')
	if not os.path.isfile(queryFile):
		raise EnvironmentError('JSON query file does not exist: {}'.format(queryFile))

	## Load the file containing the query for IPs
	queryContent = None
	with open(queryFile) as fp:
		queryContent = json.load(fp)

	## Get chunked query results from the API; best to use when the data
	## set can be quite large, but the second version can be used if you
	## want to gather everything in one call or in a non-Flat format:
	queryResults = getApiQueryResultsInChunks(runtime, queryContent)
	if queryResults is None or len(queryResults) <= 0:
		raise EnvironmentError('No IPs found from database; nothing to update.')
	## Convert the API results into a desired layout for our needs here
	transformIpResultsFromApi(runtime, ipAddrToIdDict, queryResults)
	queryResults = None

	## end getCurrentIps
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	client = None
	try:
		## Read/initialize the job parameters
		trackEveryIpInDNS = runtime.parameters.get('trackEveryIpInDNS', False)
		retainCacheAfterJobCompletion = runtime.parameters.get('retainCacheAfterJobCompletion', False)
		ipAddrToIdDict = {}
		jobRuntimePath = verifyJobRuntimePath(__file__)
		runtime.logger.report('path jobRuntimePath: {jobRuntimePath!r}', jobRuntimePath=jobRuntimePath)

		## See if we need to query the API for current IPs
		if not trackEveryIpInDNS:
			## Pull current IPs from DB
			getCurrentIps(runtime, ipAddrToIdDict)
			runtime.logger.report('IP count found from database: {ipCount!r}', ipCount=len(ipAddrToIdDict))
			## Create a realm utility to check if IPs are within the boundary
			runtime.logger.report('realm: {runtime!r}', runtime=runtime.jobMetaData.get('realm'))
			runtime.logger.report('protocols: {runtime!r}', runtime=runtime.jobMetaData)
			realmUtil = RealmUtility(runtime)

		## Get the WMI client
		client = getClient(runtime, namespace='root/microsoftdns')
		if client is not None:
			## Open client session before starting the work
			client.open()

			## Do the work
			doWork(runtime, client.connection, ipAddrToIdDict, jobRuntimePath, realmUtil)

			## Good house keeping; though I force this after the exception below
			client.close()

			## Update the runtime status to success
			if runtime.getStatus() == 'UNKNOWN':
				runtime.status(1)

			if not retainCacheAfterJobCompletion:
				cleanupJobRuntimePath(__file__)

	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end startJob
	return
