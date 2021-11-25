"""Protocol type wrapper for the UCMDB REST API."""
import sys
import traceback
import requests
import json

class UcmdbRestAPI():
	"""Protocol type wrapper for the UCMDB rest API."""
	def __init__(self, runtime, restEndpoint, apiUser, notthat, clientContext=1):
		"""Constructor."""
		self.runtime = runtime
		self.token = None
		self.authHeader = {}
		self.baseURL = restEndpoint
		self.apiUser = apiUser
		self.notthat = notthat
		self.clientContext = clientContext
		self.connected = False
		self.establishConnection()


	def establishConnection(self):
		"""Attempt a connection and acquire the security token."""
		try:
			urlForTokenGeneration = '{}{}'.format(self.baseURL, '/authenticate')

			## Create the payload:
			payloadAsDict = {}
			payloadAsDict['username'] = self.apiUser
			payloadAsDict['password'] = self.notthat
			payloadAsDict['clientContext'] = str(self.clientContext)

			## Convert payload Dictionary into json string format (not json)
			payloadAsString = json.dumps(payloadAsDict)
			self.runtime.logger.report('payloadAsString: {payloadAsString!r}', payloadAsString=payloadAsString)
			self.runtime.logger.report('urlForTokenGeneration: {urlForTokenGeneration!r}', urlForTokenGeneration=urlForTokenGeneration)

			## Tell the web service to use json
			headersAsDict = {}
			headersAsDict["Content-Type"] = "application/json"

			## Issue a POST call to URL for token generation
			apiResponse = requests.post(urlForTokenGeneration, data=payloadAsString, headers=headersAsDict, verify=False)
			self.runtime.logger.report('Response code: {status_code!r}', status_code=apiResponse.status_code)
			self.runtime.logger.report('Response as String: {apiResponse!r}', apiResponse=apiResponse.text)
			responseAsJson =  json.loads(apiResponse.text)
			self.token = responseAsJson.get("token")
			if self.token is not None:
				## Create the header to use for future queries
				self.authHeader['Authorization'] = '{} {}'.format('Bearer', self.token)
				self.authHeader["Content-Type"] = "application/json"
				self.connected = True

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.runtime.logger.error('Failure in UcmdbRestAPI.establishConnection: {stacktrace!r}', stacktrace=stacktrace)

		## end establishConnection
		return

	def dynamicQuery(self, payloadAsString):
		"""Request a dataset from the UCMDB."""
		try:
			urlForCiQuery = '{}{}'.format(self.baseURL, '/topologyQuery')
			## Payload is passed in as a string type
			self.runtime.logger.report('authHeader: {authHeader!r}', authHeader=self.authHeader)
			self.runtime.logger.report('payloadAsString: {payloadAsString!r}', payloadAsString=payloadAsString)

			## Issue a POST call to URL
			apiResponse = requests.post(urlForCiQuery, data=payloadAsString, headers=self.authHeader, verify=False)
			self.runtime.logger.report('Response code: {status_code!r}', status_code=apiResponse.status_code)
			self.runtime.logger.report('Response as String: {apiResponse!r}', apiResponse=apiResponse.text)
			responseAsJson =  json.loads(apiResponse.text)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.runtime.logger.error('Failure in UcmdbRestAPI.dynamicQuery: {stacktrace!r}', stacktrace=stacktrace)

		## end dynamicQuery
		return

	def insertTopology(self, payloadAsString):
		"""Insert a new topology."""
		try:
			urlForCiQuery = '{}{}'.format(self.baseURL, '/dataModel')
			## Payload is passed in as a string type
			## Issue a GET call to URL
			apiResponse = requests.post(urlForCiQuery, data=payloadAsString, headers=self.authHeader, verify=False)
			self.runtime.logger.report('Response code: {status_code!r}', status_code=apiResponse.status_code)
			self.runtime.logger.report('Response as String: {apiResponse!r}', apiResponse=apiResponse.text)
			responseAsJson =  json.loads(apiResponse.text)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.runtime.logger.error('Failure in UcmdbRestAPI.dynamicQuery: {stacktrace!r}', stacktrace=stacktrace)

		## end getCI
		return
