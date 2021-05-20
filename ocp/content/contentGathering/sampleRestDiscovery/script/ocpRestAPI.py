"""Class for interacting with the Open Content Platform REST API.

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Apr 10, 2021

"""
import sys
import traceback
import json
import re
from protocolWrapperREST import RestAPI


class OcpRestAPI(RestAPI):
	'''
	Class for OCP interaction.
	'''
	def __init__(self, runtime, httpType='https', endpoint=None, ports=[52705], restPath='/ocp', proxyServer=None, descriptor=None, requestsVerify=False, requestsDebug=False):
		## API base URL, authentication/verification URL, and possible ports
		## come from job parameters - based on API and customer configurations
		self.restPath = restPath
		self.previousData = None
		self.url = None
		self.port = None
		self.reference = None
		## Normalize paths and ensure they start with a slash
		if self.restPath[0] != '/':
			self.restPath = '/{}'.format(self.restPath)
		## Header will be specific to the vendor/product
		self.header = {}

		super().__init__(runtime, httpType, endpoint, ports, proxyServer=proxyServer, descriptor=descriptor, requestsVerify=requestsVerify, requestsDebug=requestsDebug)


	def connect(self):
		"""Attempt to establish a REST connection to target URL(s)."""
		if self.previousData is not None and isinstance(self.previousData, dict):
			self.reference = self.previousData.get('protocol_reference')
			self.runtime.logger.report('  connect: using previous credential: {reference!r}', reference=self.reference)
			previousCred = self.runtime.protocols[self.reference]
			user = previousCred.get('user')
			token = previousCred.get('token')
			if self.validate(user, token):
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
				token = entry.get('token')
				if self.validate(user, token, '{}{}'.format(baseURL, self.restPath)):
					self.runtime.logger.report('Connected with credential: {reference!r}', reference=reference)
					## Set working values
					self.port = port
					self.reference = reference
					self.url = '{}{}'.format(baseURL, self.restPath)
					return
		raise EnvironmentError('No valid connection found.')


	## This version uses the user/token and does simple response validation
	def validate(self, user, token, baseURL=None):
		if baseURL is None:
			baseURL = self.url
		## Contruct a temp header set
		headers = {}
		headers['Content-Type'] = 'application/json'
		headers['apiUser'] = user
		headers['apiKey'] = token

		## Issue a GET call to the base URL for simple response validation
		(code, response) = self.get(None, headers=headers, baseURL=baseURL)
		if code == 200:
			for key,value in response.items():
				## Should just be one key showing API endpoints
				if re.search('Open Content Platform', key):
					## Create the header to use for future queries
					self.header['Content-Type'] = 'application/json'
					self.header['apiUser'] = user
					self.header['apiKey'] = token
					return True

		## end validate
		return False
	

	## Request methods
	def get(self, resourcePath, payload=None, headers=None, baseURL=None, returnJSON=True):
		## Add the headers, since they have the user/token
		if headers is None:
			headers = self.header
		response = self.request('get', resourcePath, payload=payload, headers=headers, baseURL=baseURL)
		return self.validateResponseOrRaiseException(response, returnJSON=returnJSON)

	def post(self, resourcePath, payload=None, headers=None, baseURL=None, returnJSON=True):
		## Add the headers, since they have the user/token
		if headers is None:
			headers = self.header
		response = self.request('post', resourcePath, payload=payload, headers=headers, baseURL=baseURL)
		return self.validateResponseOrRaiseException(response, returnJSON=returnJSON)

	def restDetails(self):
		return (self.endpoint, self.reference, self.port, self.url)
