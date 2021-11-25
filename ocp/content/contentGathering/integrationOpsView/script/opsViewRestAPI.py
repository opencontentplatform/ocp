"""Protocol type wrapper for the OpsView REST API.

If this is built on, we should generalize and wrap the calls below.

"""
import sys
import traceback
import requests
import json

class OpsViewRestAPI():
	"""Protocol type wrapper for the UCMDB rest API."""
	def __init__(self, runtime, restEndpoint, apiUser, notthat):
		"""Constructor."""
		self.runtime = runtime
		self.token = None
		self.authHeader = {}
		self.baseURL = restEndpoint
		self.apiUser = apiUser
		self.notthat = notthat
		self.connected = False
		self.establishConnection()


	def establishConnection(self):
		"""Attempt a connection and acquire the security token."""
		try:
			urlForTokenGeneration = '{}{}'.format(self.baseURL, '/login')

			## Create the payload:
			payloadAsDict = {}
			payloadAsDict['username'] = self.apiUser
			payloadAsDict['password'] = self.notthat

			## Convert payload Dictionary into json string format (not json)
			payloadAsString = json.dumps(payloadAsDict)
			self.runtime.logger.report('payloadAsString: {payloadAsString!r}', payloadAsString=payloadAsString)
			self.runtime.logger.report('urlForTokenGeneration: {urlForTokenGeneration!r}', urlForTokenGeneration=urlForTokenGeneration)

			## Tell the web service to use json
			headersAsDict = {}
			headersAsDict['Content-Type'] = 'application/json'

			## Issue a POST call to URL for token generation
			apiResponse = requests.post(urlForTokenGeneration, data=payloadAsString, headers=headersAsDict, verify=False)
			self.runtime.logger.report('Response code: {status_code!r}', status_code=apiResponse.status_code)
			self.runtime.logger.report('Response as String: {apiResponse!r}', apiResponse=apiResponse.text)
			responseAsJson =  json.loads(apiResponse.text)
			self.token = responseAsJson.get('token')
			if self.token is not None:
				## Create the header to use for future queries
				self.authHeader['X-Opsview-Username'] = self.apiUser
				self.authHeader['X-Opsview-Token'] = self.token
				self.authHeader['Content-Type'] = 'application/json'
				self.connected = True

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.runtime.logger.error('Failure in OpsViewRestAPI.establishConnection: {stacktrace!r}', stacktrace=stacktrace)

		## end establishConnection
		return


	def getHosts(self):
		responseAsJson = None
		try:
			urlForCiQuery = '{}{}'.format(self.baseURL, '/config/host')
			## Issue a POST call to URL
			apiResponse = requests.get(urlForCiQuery, headers=self.authHeader, verify=False)
			self.runtime.logger.report('Response code: {status_code!r}', status_code=apiResponse.status_code)
			self.runtime.logger.report('Response as String: {apiResponse!r}', apiResponse=apiResponse.text)
			responseAsJson =  json.loads(apiResponse.text)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.runtime.logger.error('Failure in OpsViewRestAPI.getHosts: {stacktrace!r}', stacktrace=stacktrace)

		## end getHosts
		return responseAsJson


	def insertHost(self, payloadAsString):
		responseAsJson = None
		try:
			urlForCiQuery = '{}{}'.format(self.baseURL, '/config/host')
			## Issue a POST call to URL
			apiResponse = requests.post(urlForCiQuery, data=payloadAsString, headers=self.authHeader, verify=False)
			self.runtime.logger.report('Response code: {status_code!r}', status_code=apiResponse.status_code)
			self.runtime.logger.report('Response as String: {apiResponse!r}', apiResponse=apiResponse.text)
			responseAsJson = json.loads(apiResponse.text)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.runtime.logger.error('Failure in OpsViewRestAPI.insertHost: {stacktrace!r}', stacktrace=stacktrace)

		## end insertHost
		return responseAsJson


	def updateHost(self, hostId, payloadAsString):
		responseAsJson = None
		try:
			urlForCiQuery = '{}{}'.format(self.baseURL, '/config/host/{}'.format(hostId))
			## Issue a POST call to URL
			apiResponse = requests.put(urlForCiQuery, data=payloadAsString, headers=self.authHeader, verify=False)
			self.runtime.logger.report('Response code: {status_code!r}', status_code=apiResponse.status_code)
			self.runtime.logger.report('Response as String: {apiResponse!r}', apiResponse=apiResponse.text)
			responseAsJson =  json.loads(apiResponse.text)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.runtime.logger.error('Failure in OpsViewRestAPI.updateHost: {stacktrace!r}', stacktrace=stacktrace)

		## end updateHost
		return responseAsJson


	def getComponents(self):
		responseAsJson = None
		try:
			urlForCiQuery = '{}{}'.format(self.baseURL, '/config/bsmcomponent')
			## Issue a POST call to URL
			apiResponse = requests.get(urlForCiQuery, headers=self.authHeader, verify=False)
			self.runtime.logger.report('Response code: {status_code!r}', status_code=apiResponse.status_code)
			self.runtime.logger.report('Response as String: {apiResponse!r}', apiResponse=apiResponse.text)
			responseAsJson =  json.loads(apiResponse.text)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			#self.runtime.logger.error('Failure in OpsViewRestAPI.getHosts: {stacktrace!r}', stacktrace=stacktrace)
			print('Failure in OpsViewRestAPI.getComponents: {}'.format(stacktrace))

		## end getComponents
		return responseAsJson


	def insertComponent(self, payloadAsString):
		responseAsJson = None
		try:
			urlForCiQuery = '{}{}'.format(self.baseURL, '/config/bsmcomponent')
			## Issue a POST call to URL
			apiResponse = requests.post(urlForCiQuery, data=payloadAsString, headers=self.authHeader, verify=False)
			self.runtime.logger.report('Response code: {status_code!r}', status_code=apiResponse.status_code)
			self.runtime.logger.report('Response as String: {apiResponse!r}', apiResponse=apiResponse.text)
			responseAsJson = json.loads(apiResponse.text)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.runtime.logger.error('Failure in OpsViewRestAPI.insertHost: {stacktrace!r}', stacktrace=stacktrace)

		## end insertHost
		return responseAsJson


	def updateComponent(self, componentId, payloadAsString):
		responseAsJson = None
		try:
			urlForCiQuery = '{}{}'.format(self.baseURL, '/config/bsmcomponent/{}'.format(componentId))
			## Issue a POST call to URL
			apiResponse = requests.put(urlForCiQuery, data=payloadAsString, headers=self.authHeader, verify=False)
			self.runtime.logger.report('Response code: {status_code!r}', status_code=apiResponse.status_code)
			self.runtime.logger.report('Response as String: {apiResponse!r}', apiResponse=apiResponse.text)
			responseAsJson =  json.loads(apiResponse.text)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.runtime.logger.error('Failure in OpsViewRestAPI.updateComponent: {stacktrace!r}', stacktrace=stacktrace)

		## end updateComponent
		return responseAsJson
