"""Web page detection job.

Functions:
  startJob - Standard job entry point
  attemptWebRequest - Get a web response
  trackWebResponse - Create IP, Port, and WebEnabledEndpoint

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Jun 18, 2021

"""
import sys, traceback
import re
import html
from contextlib import suppress

## From openContentPlatform
from utilities import runPortTest, requestsRetrySession, addObject, addLink


def trackWebResponse(runtime, ipAddress, ipObjectId, port, url, responseCode, responseText):
	"""Create the IP, Port, and WebEnabledEndpoint."""
	addObject(runtime, 'IpAddress', uniqueId=ipObjectId)
	## Create TcpIpPort
	tcpIpPortId, portExists = addObject(runtime, 'TcpIpPort', name=str(port), port=int(port), ip=ipAddress, port_type='tcp', is_tcp=True)
	
	## Get any title, if it exists
	title = None
	with suppress(Exception):
		m = re.search('<\W*title\W*(.*)</title', responseText, re.I)
		if m:
			title = m.group(1)
			## Remove any HTML encoding (e.g. &amp; to &, or &#8211; to -)
			## so any user provided regEx for matches, works as expected
			title = html.unescape(title)
	## Don't need to HTML encode all, but definitely double quotes for JSON
	## result object; and truncate in case the response was too large
	responseText = responseText.replace('"', '&quot;')[:4096]
	
	## Create WebEnabledEndpoint
	webId, certExists = addObject(runtime, 'WebEnabledEndpoint', url=url, ip=ipAddress, port=port, title=title, response_code=responseCode, response_text=responseText)
	## Links
	addLink(runtime, 'Enclosed', ipObjectId, tcpIpPortId)
	addLink(runtime, 'Enclosed', tcpIpPortId, webId)


def attemptWebRequest(runtime, ipAddress, port, connectTimeout, addHTTP, verify=False):
	"""Helper to get a web response."""
	urls = ['https://{}:{}/'.format(ipAddress, port)]
	if addHTTP:
		urls.append('http://{}:port/'.format(ipAddress, port))
	
	for url in urls:
		#apiResponse = requestsRetrySession().get(url, data=payload, headers=headers, verify=verify)
		apiResponse = requestsRetrySession().get(url, verify=verify)
		
		with suppress(Exception):
			return (url, apiResponse.status_code, apiResponse.text)
	
	return (None, None, None)


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
		portTest = runtime.parameters.get('portTestBeforeConnectionAttempt', False)
		ports = runtime.parameters.get('portsToTest', [])
		connectTimeout = int(runtime.parameters.get('connectTimeoutInSeconds', 3))
		addHTTP = runtime.parameters.get('alsoTryHTTP', False)
		for port in ports:
			continueFlag = True
			if portTest:
				portIsActive = runPortTest(runtime, endpointString, [int(port)])
				if not portIsActive:
					runtime.logger.report('Endpoint not listening on port {}'.format(port))
					continueFlag = False

			## Attempt to request a response
			if continueFlag:
				runtime.logger.report(' Requesting web-enabled response from {}:{}'.format(ipAddress, port))
				(url, responseCode, responseText) = attemptWebRequest(runtime, ipAddress, port, connectTimeout, addHTTP)
				if url is not None:
					trackWebResponse(runtime, ipAddress, ipObjectId, port, url, responseCode, responseText)
					## Update the runtime status to SUCCESS
					runtime.status(1)

		## Update the runtime status to INFO with a relevant message
		if runtime.getStatus() == 'UNKNOWN':
			runtime.setInfo('No web-enabled response found')

	except:
		runtime.setError(__name__)

	## end startJob
	return
