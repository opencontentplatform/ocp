"""Wrapper for accessing REST API endpoints.

This module is not a standard protocolWrapper module, if you're familiar with
the others (SSH, SNMP, PowerShell, SQL), and so it's not called from the base
protocolWrapper.py module or used with getClient().

The REST protocol is intentionally NOT a standard managed/wrapped type because
REST does not have a single authentication mechanism; it loosely defines and
enables many, such as: basic, digest, OAUTH, token, or custom. And the way you
pass data through varies with URL inlined parameters, base64 encoding, payload
vs headers, and even what the variables names are even called, such as username
and token. Sometimes you authenticate one set of data - to be provided another,
like providing user/password for a token.

This top level class is meant to be overloaded with each instrumentation using
REST to talk to a particular vendor/product.


Classes:
  |  REST : base class for REST connections

"""
import re
import json
from utilities import runPortTest, requestsRetrySession


class RestAPI:
	"""Base class for common code paths and encapsulation.
	
	Arguments::
	
		runtime (dict)   : object used for providing input into jobs and tracking
						   the job thread through the life of its runtime
		httpType (str)   : http or https
		endpoint (str)   : destination target; either an IP or FQDN
		ports (str|list) : single port or a list of multiple
		proxyServer (str) : name of a proxy server if using one
		reference (int)  : optional - ID of the credential to use; if provided,
						   only the provided credential will be attempted. Used
						   for recurring discovery, when previously established
		descriptor (str) : optional - regEx; if provided, only protocol entries
						   with matching description fields, will be attempted
		requestsVerify (str) : 'verify' parameter for requests library
		requestsDebug (str)  : 'debug' parameter for requests library

	"""
	def __init__(self, runtime, httpType, endpoint, ports, proxyServer=None, descriptor=None, requestsVerify=False, requestsDebug=False):
		self.runtime = runtime
		self.httpType = httpType.lower()
		self.endpoint = endpoint
		self.reference = None
		self.descriptor = descriptor
		self.requestsVerify = requestsVerify
		self.requestsDebug = requestsDebug
		self.proxy = {}
		self.ports = []
		self.credentials = {}
		self.urls = {}
		if endpoint is None:
			self.previousData = runtime.endpoint.get('data')
			if not isinstance(self.previousData, dict):
				raise ValueError('Endpoint was not passed through args, or found in the runtime; nothing to use for the connection context.')
			
		if self.previousData is None:
			## New connection; standard pre-work
			self.createRequestsProxy(proxyServer)
			self.validatePorts(ports)
			self.constructURLs()
			self.getUnManagedCredentials()
		else:
			## Override values back for the child classes
			self.reference = self.previousData.get('protocol_reference')
			self.url = self.previousData.get('base_url')
			self.authUrl = self.previousData.get('auth_url')
			self.port = self.previousData.get('port')


	def close(self):
		"""Shouldn't have to do this, but some APIs require something here."""
		raise NotImplementedError('Override in child classes')
	

	def createRequestsProxy(self, proxyServer):
		if proxyServer is not None:
			## Proxy server
			self.proxy = proxyServer
			if proxyServer[:4].lower != 'http':
				## requests lib (v2+) requires type
				self.proxy[self.httpType] = '{}://{}'.format(self.httpType, proxyServer)
			else:
				self.proxy[self.httpType] = proxyServer
			## Note: if enabling proxy user/pass, it should be similar to:
			##   {'https': 'https://user:pass@10.20.30.40:8080/'}


	def validatePorts(self, ports):
		"""Syntax checking and socket testing to construct valid port list."""
		## Validation checking on ports first; could be a single port
		## or a list of ports... get rid of any potential garbage
		portsToCheck = []
		self.runtime.logger.report('validatePorts: entry ports : {ports!r}', ports=ports)
		if isinstance(ports, int) or (isinstance(ports, str) and str(ports).isdigit()):
			portsToCheck.append(int(ports))
		elif isinstance(ports, list):
			for port in ports:
				if isinstance(port, int) or (isinstance(port, str) and str(port).isdigit()):
					portsToCheck.append(int(port))
		if len(portsToCheck) <= 0:
			raise ValueError('Not a valid port or list of ports: {}'.format(ports))
		
		## Now socket test to ensure ports are active/open; only continue
		## with ports that we know are out there listening...
		self.runtime.logger.report('validatePorts: portsToCheck: {portsToCheck!r}', portsToCheck=portsToCheck)
		## Get rid of duplicates, and test each
		for port in list(set(portsToCheck)):
			if runPortTest(self.runtime, self.endpoint, [port]):
				self.ports.append(port)
			else:
				self.runtime.logger.report('validatePorts: socket test failed on {}:{}'.format(self.endpoint, port))
		if len(self.ports) <= 0:
			raise EnvironmentError('Endpoint {} not listening on ports: {}'.format(self.endpoint, portsToCheck))


	def getUnManagedCredentials(self):
		"""Simple wrapper to get REST credential types.

		Note: with un-managed credential types, data isn't encrypted as it is
		for standard managed/wrapped types - for multiple reasons, including:
		1) we need access to credentials/tokens after the initial connection,
		2) we restrict instrumentation by putting a wrapper in the middle,
		3) the protocol has multiple ways ways of working; not one standard.
		"""
		protocolType='ProtocolRestApi'
		for protocolReference,entry in self.runtime.protocols.items():
			self.runtime.logger.report('getUnManagedCredentials: looking at protocol: {protocolReference!r}: {entry!r}', protocolReference=protocolReference, entry=entry)

			## When we only want the entry that matches the provided reference;
			## don't even need this block if we just pull from runtime.protocols
			if self.reference is not None:
				if protocolReference != self.reference:
					self.runtime.logger.report('getUnManagedCredentials: skipping reference; ID {targetReference!r} != {thisReference!r}', targetReference=self.reference, thisReference=protocolReference)
					continue
			
			if (entry.get('protocolType', '').lower() == protocolType.lower()):
				thisDescription = entry.get('description', '')
				
				## When we only want entries where descriptions match the regEx
				if self.descriptor is not None:
					if not re.search(self.descriptor, thisDescription, re.I):
						self.runtime.logger.report('getUnManagedCredentials: skipping reference {protocolReference!r}.  Descriptor {descriptor!r} mismatched description {thisDescription!r}', protocolReference=protocolReference, descriptor=self.descriptor, thisDescription=thisDescription)
						continue
				
				self.runtime.logger.report(' getUnManagedCredentials: protocol type {protocolType!r} with reference {protocolReference!r}: {entry!r}', protocolType=protocolType, protocolReference=protocolReference, entry=entry)
				## Add to the filtered protocol dictionary we send back
				self.credentials[protocolReference] = entry
		
		if len(self.credentials) <= 0:
			raise ValueError('No credentials found.')

		## end getUnManagedCredentials
		return


	def constructURLs(self):
		"""Create a URL entry per valid port."""
		urlPart = '{}://{}'.format(self.httpType, self.endpoint)
		self.runtime.logger.report('constructURLs: urlPart: {}'.format(urlPart))
		for port in self.ports:
			## Drop unnecessarily explicit port numbers
			if ((self.httpType == 'http' and port == 80) or
				(self.httpType == 'https' and port == 443)):
				self.urls[port] = urlPart
			else:
				self.urls[port] = '{}:{}'.format(urlPart, port)


	def request(self, method, resourcePath, payload=None, headers=None, baseURL=None):
		apiResponse = None
		## Normalize the resourcePath
		if resourcePath is None or len(str(resourcePath).strip()) <= 0:
			resourcePath = '/'
		elif resourcePath[0] != '/':
			resourcePath = '/{}'.format(resourcePath)
		## Construct the full URL
		if baseURL is None:
			## Use the established base URL
			url = '{}{}'.format(self.url, resourcePath)
		else:
			## And for special cases (like authentication on a different path)
			## Don't assume it has the same root - assume full path
			#url = '{}{}'.format(baseURL, resourcePath)
			url = baseURL
		
		## Request methods enabled by a retry session for network failures		
		self.runtime.logger.report(' Sending {method!r} to {url!r}', method=str(method).upper(), url=url)
		if method.lower() == 'get':
			apiResponse = requestsRetrySession().get(url, data=payload, headers=headers, proxies=self.proxy, verify=self.requestsVerify)
		elif method.lower() == 'post':
			apiResponse = requestsRetrySession().post(url, data=payload, headers=headers, proxies=self.proxy, verify=self.requestsVerify)
		elif method.lower() == 'put':
			apiResponse = requestsRetrySession().put(url, data=payload, headers=headers, proxies=self.proxy, verify=self.requestsVerify)
		elif method.lower() == 'delete':
			apiResponse = requestsRetrySession().delete(url, data=payload, headers=headers, proxies=self.proxy, verify=self.requestsVerify)
		else:
			raise NotImplementedError('request works with get/post/put/delete, but not {}'.format(method))
		return apiResponse


	def validateResponseOrRaiseException(self, response, validCodes=[200], returnJSON=True):
		responseCode = response.status_code
		responseText = response.text
		self.runtime.logger.report('Response code: {}'.format(responseCode))
		#self.runtime.logger.report('Response string: {}'.format(responseText))
		## Response codes may include others
		if responseCode not in validCodes:
			raise ValueError('Bad response code: {}. {}'.format(responseCode, responseText))
		## Conditionally convert to JSON
		if responseText is not None and returnJSON:
			responseText = json.loads(responseText)
		## Return both the code and result
		return (responseCode, responseText)
