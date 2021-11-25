"""Web page detection job.

Functions:
  startJob - Standard job entry point
  attemptWebRequest - Get a web response
  trackWebResponse - Create IP, Port, and WebEnabledEndpoint

"""
import sys, traceback
import re
import os
import json
import html
from contextlib import suppress

## From openContentPlatform
from utilities import runPortTest, requestsRetrySession, addObject, addLink



def trackCiToCreate(runtime, ipObjectId, ciSection, attributes):
	"""Create the custom CI defined by the mapping definition."""
	ciType = ciSection.get('type')
	staticAttributes = ciSection.get('staticAttributes', {})
	## Add any static attributes
	for attr,value in staticAttributes.items():
		if attr not in attributes:
			attributes[attr] = value.strip()
	runtime.logger.report('trackCiToCreate: create attributes on {} CI: {}'.format(ciType, attributes))
	## Create the object and link the IP
	objectId, exists = addObject(runtime, ciType, **attributes)
	addLink(runtime, 'Usage', objectId, ipObjectId)
	
	## end trackCiToCreate
	return


def trackWebResponse(runtime, ipAddress, ipObjectId, port, url, responseCode, responseText, title):
	"""Create the IP, Port, and WebEnabledEndpoint."""
	## Recreate the IP by the identifier
	addObject(runtime, 'IpAddress', uniqueId=ipObjectId)
	## Create TcpIpPort
	tcpIpPortId, portExists = addObject(runtime, 'TcpIpPort', name=str(port), port=int(port), ip=ipAddress, port_type='tcp', is_tcp=True)
	## Don't need to HTML encode all, but definitely double quotes for JSON
	## result object; and truncate in case the response was too large
	responseText = responseText.replace('"', '&quot;')[:4096]
	## Create WebEnabledEndpoint
	webId, certExists = addObject(runtime, 'WebEnabledEndpoint', url=url, ip=ipAddress, port=port, title=title, response_code=responseCode, response_text=responseText)
	## Links
	addLink(runtime, 'Enclosed', ipObjectId, tcpIpPortId)
	addLink(runtime, 'Enclosed', tcpIpPortId, webId)
	
	## end trackWebResponse
	return


def attemptWebRequest(runtime, protocol, ipAddress, port, context, connectTimeout, verify=False):
	"""Helper to get a web response."""
	url = '{}://{}:{}{}'.format(protocol, ipAddress, port, context)
	runtime.logger.report(' Requesting web-enabled response from {}'.format(url))
	apiResponse = requestsRetrySession().get(url, verify=verify)
	with suppress(Exception):
		return (url, apiResponse.status_code, apiResponse.text)
	
	## end attemptWebRequest
	return (None, None, None)


def checkMatch(runtime, attributes, mapping, source):
	"""Determine if the mapping section matches the provided source."""
	compareType = mapping.get('valueCompareType')
	matchString = mapping.get('valueCompareGroup')
	discoveredAttribute = mapping.get('discoveredAttribute')
	runtime.logger.report('checkMatch: trying: {}'.format(mapping))
	
	## If definition compare type is equals:
	if compareType.lower() == 'equals' and source == matchString:
		#return createMatch(Framework, printDebug, ciSection, discoveredAttribute, source, nodeOSH, nodeType, nodeId)
		runtime.logger.report('FOUND MATCH on equals: {}'.format(matchString))
		attributes[discoveredAttribute] = matchString
		return True

	## If definition compare type is regEx:
	elif compareType.lower() == 'regex':
		m = re.search(matchString, source, re.I)
		if m:
			#return createMatch(Framework, printDebug, ciSection, discoveredAttribute, m.group(1), nodeOSH, nodeType, nodeId)
			runtime.logger.report('FOUND MATCH on regex: {}'.format(m.group(1)))
			attributes[discoveredAttribute] = m.group(1).strip()
			return True

	## end checkMatch
	return False


def getHtmlTitle(responseText):
	"""Get an HTML title tag, if it exists."""
	title = None
	with suppress(Exception):
		m = re.search('<\W*title\W*(.*)</title', responseText, re.I)
		if m:
			title = m.group(1)
			## Remove any HTML encoding (e.g. &amp; to &, or &#8211; to -)
			## so any user provided regEx for matches, works as expected
			title = html.unescape(title)
	
	## end getHtmlTitle
	return title


def tryMappings(runtime, deviceMappings, protocol, port, ipAddress, ipObjectId, connectTimeout):
	"""Run through each webPageToNode mapping"""
	responses = {}
	
	## First attempt a query to root /
	title = None
	(url, responseCode, responseText) = attemptWebRequest(runtime, protocol, ipAddress, port, '/', connectTimeout)
	if url is not None:
		title = getHtmlTitle(responseText)
		trackWebResponse(runtime, ipAddress, ipObjectId, port, url, responseCode, responseText, title)
		## Update the runtime status to SUCCESS
		if runtime.getStatus() == 'UNKNOWN':
			runtime.status(1)
	responses['/'] = (url, title, responseCode, responseText)
	
	for key,value in deviceMappings.items():
		try:
			runtime.logger.report('tryMappings loop: entry: {}'.format(key))
			ciSection = value.get('ciToCreate')
			matchSection = value.get('webPageMatch', {})
			urlStubs = matchSection.get('urlStubs', [])
			for urlStub in urlStubs:
				attributes = {}
				## If we haven't processed this stub on this port yet
				if urlStub not in responses:
					try:
						title = None
						(url, responseCode, responseText) = attemptWebRequest(runtime, protocol, ipAddress, port, urlStub.strip(), connectTimeout)
						if url is not None:
							title = getHtmlTitle(responseText)
					except:
						stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
						runtime.logger.error('Failure in tryMappings: {}'.format(stacktrace))
					## only do this once
					responses[urlStub] = (url, title, responseCode, responseText)

				## Get the previous response
				(url, title, responseCode, responseText) = responses[urlStub]
				
				## Work on any title matching sections first
				if title is not None:
					for mapping in matchSection.get('title', {}).get('mapping', []):
						if checkMatch(runtime, attributes, mapping, title):
							runtime.logger.report('tryMappings: found TITLE match: {}'.format(mapping))
				
				## Then work on any HTML document matching sections
				if responseText is not None:
					for mapping in matchSection.get('document', {}).get('mapping', []):
						if checkMatch(runtime, attributes, mapping, responseText):
							runtime.logger.report('tryMappings: found DOCUMENT match: {}'.format(mapping))
				
				## If we have a hit, no reason to try additional urlStubs
				if len(attributes) > 0:
					trackCiToCreate(runtime, ipObjectId, ciSection, attributes)
					## Also want to track the response
					trackWebResponse(runtime, ipAddress, ipObjectId, port, url, responseCode, responseText, title)
					return

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Failure in tryMappings: {}'.format(stacktrace))
	
	## Don't want to see all the time, but when debug is turned on...
	runtime.logger.report('tryMappings: No match found on endpoint {}:{}'.format(ipAddress, port))

	## end tryMappings
	return


def tryPorts(runtime, deviceMappings, protocol, ports, portTest, endpointString, ipAddress, ipObjectId, connectTimeout):
	"""Run through ports and construct the endpoints to query."""
	for port in ports:
		continueFlag = True
		if portTest:
			portIsActive = runPortTest(runtime, endpointString, [int(port)])
			if not portIsActive:
				runtime.logger.report('Endpoint not listening on port {}'.format(port))
				continueFlag = False

		if continueFlag:
			tryMappings(runtime, deviceMappings, protocol, port, ipAddress, ipObjectId, connectTimeout)
	
	## end tryPorts
	return


def loadMappings():
	"""Load our mapping definitions from webPageToNodeMapping.json"""
	jobScriptPath = os.path.dirname(os.path.realpath(__file__))
	mappingFile = os.path.abspath(os.path.join(jobScriptPath, '..', 'conf', 'webPageToNodeMapping.json'))
	with open(mappingFile) as fp:
		deviceMapping = json.load(fp)
	
	## end loadMappings
	return deviceMapping


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		endpointString = runtime.endpoint.get('data', {}).get('address')
		runtime.logger.report('Running job {name!r} on endpoint {endpoint!r}', name=__name__, endpoint=endpointString)

		## Get our targets from our runtime object passed in
		ipAddress = runtime.endpoint.get('data').get('address')
		ipObjectId = runtime.endpoint.get('identifier')

		## Port test if user requested via parameters
		portTest = runtime.parameters.get('portTestBeforeConnectionAttempt', True)
		httpsPorts = runtime.parameters.get('httpsPortsToTest', [])
		tryHTTP = runtime.parameters.get('tryHttpPorts', False)
		httpPorts = runtime.parameters.get('httpPortsToTest', [])
		connectTimeout = int(runtime.parameters.get('connectTimeoutInSeconds', 3))
		
		## Load mappings
		deviceMappings = loadMappings()
		
		## First try HTTPS
		tryPorts(runtime, deviceMappings, 'https', httpsPorts, portTest, endpointString, ipAddress, ipObjectId, connectTimeout)
		if tryHTTP:
			## Try HTTP (applicable for printers/storage/devices)
			tryPorts(runtime, deviceMappings, 'http', httpPorts, portTest, endpointString, ipAddress, ipObjectId, connectTimeout)

		## Update the runtime status to INFO with a relevant message
		if runtime.getStatus() == 'UNKNOWN':
			runtime.setInfo('No web-enabled response found')

	except:
		runtime.setError(__name__)

	## end startJob
	return
