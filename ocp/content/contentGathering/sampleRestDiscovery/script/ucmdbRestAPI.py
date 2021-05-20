"""Class for interacting with the MicroFocus UCMDB REST API.

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Apr 10, 2021

"""
import sys
import traceback
import json
from protocolWrapperREST import RestAPI


class UcmdbRestAPI(RestAPI):
	'''
	Class for UCMDB interaction.
	'''
	def __init__(self, runtime, httpType='https', endpoint=None, ports=[443,8443], restPath='/rest-api', authPath='/rest-api/authenticate', proxyServer=None, descriptor=None, requestsVerify=False, requestsDebug=False):
		## API base URL, authentication/verification URL, and possible ports
		## come from job parameters - based on API and customer configurations
		self.restPath = restPath
		self.authPath = authPath
		self.previousData = None
		self.url = None
		self.port = None
		self.reference = None
		## Normalize paths and ensure they start with a slash
		if self.restPath[0] != '/':
			self.restPath = '/{}'.format(self.restPath)
		if self.authPath[0] != '/':
			self.authPath = '/{}'.format(self.authPath)
		## Header will be specific to the vendor/product
		self.header = {}
		## Token returns from authentication
		self.token = None

		super().__init__(runtime, httpType, endpoint, ports, proxyServer=proxyServer, descriptor=descriptor, requestsVerify=requestsVerify, requestsDebug=requestsDebug)


	def connect(self):
		"""Attempt to establish a REST connection to target URL(s)."""
		if self.previousData is not None and isinstance(self.previousData, dict):
			self.reference = self.previousData.get('protocol_reference')
			self.runtime.logger.report('  connect: using previous credential: {reference!r}', reference=self.reference)
			previousCred = self.runtime.protocols[self.reference]
			user = previousCred.get('user')
			pstr = previousCred.get('password')
			if self.authenticate(user, pstr):
				self.runtime.logger.report('  connect: yes, previous credential and config still work.')
				return
		for port,baseURL in self.urls.items():
			self.runtime.logger.report('Attempt connection on URL: {url!r}', url=baseURL)
			for reference,entry in self.credentials.items():
				self.runtime.logger.report('  using credential: {reference!r}', reference=reference)
				## Don't re-run on a previous one that failed directly above
				if self.previousData is not None and self.reference == reference:
					continue
				user = entry.get('user')
				pstr = entry.get('password')
				if self.authenticate(user, pstr, '{}{}'.format(baseURL, self.authPath)):
					self.runtime.logger.report('Connected with credential: {reference!r}', reference=reference)
					## Set working values
					self.port = port
					self.reference = reference
					self.url = '{}{}'.format(baseURL, self.restPath)
					self.authUrl = '{}{}'.format(baseURL, self.authPath)
					return
		raise EnvironmentError('No valid connection found.')


	## This version uses the user/password in protocol to get the token
	def authenticate(self, user, pstr, authURL=None):
		if authURL is None:
			authURL = self.authUrl
		## Create the payload:
		payload = {}
		payload['username'] = user
		payload['password'] = pstr
		payload['clientContext'] = 1
		## Convert payload Dictionary into json string format (not json)
		payloadAsString = json.dumps(payload)

		## Contruct a temp header set
		headers = {}
		headers['Content-Type'] = 'application/json'

		## Issue a POST call to URL for token generation
		(code, response) = self.post(None, payload=payloadAsString, headers=headers, baseURL=authURL)
		if code == 200:
			self.token = response.get('token')
			if self.token is not None:
				## Create the header to use for future queries
				self.header['Authorization'] = 'Bearer {}'.format(self.token)
				self.header['Content-Type'] = 'application/json'
				return True

		## end authenticate
		return False
	

	## Request methods
	def get(self, resourcePath, payload=None, headers=None, baseURL=None, returnJSON=True):
		## Add the headers, since they have the token
		if headers is None:
			headers = self.header
		response = self.request('get', resourcePath, payload=payload, headers=headers, baseURL=baseURL)
		return self.validateResponseOrRaiseException(response, returnJSON=returnJSON)

	def post(self, resourcePath, payload=None, headers=None, baseURL=None, returnJSON=True):
		## Add the headers, since they have the token
		if headers is None:
			headers = self.header
		response = self.request('post', resourcePath, payload=payload, headers=headers, baseURL=baseURL)
		return self.validateResponseOrRaiseException(response, returnJSON=returnJSON)

	def restDetails(self):
		return (self.endpoint, self.reference, self.port, self.url, self.authUrl)
