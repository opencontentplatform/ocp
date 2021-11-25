"""Protocol type wrapper for the ServiceNow REST API."""
import sys
import traceback
import requests
import json

class SnowRestAPI():
	"""Protocol type wrapper for the ServiceNow REST API."""
	def __init__(self, runtime, restEndpoint, apiUser, notthat, clientId, clientSecret):
		"""Constructor."""
		self.runtime = runtime
		self.token = None
		self.authHeader = {}
		self.baseURL = restEndpoint
		self.apiUser = apiUser
		self.notthat = notthat
		self.clientId = clientId
		self.clientSecret = clientSecret
		self.connected = False
		self.establishConnection()


	def establishConnection(self):
		"""Attempt a connection and acquire the security token."""
		try:
			urlForTokenGeneration = '{}{}'.format(self.baseURL, '/oauth_token.do')

			## Create the payload:
			payloadAsDict = {}
			payloadAsDict['grant_type'] = 'password'
			payloadAsDict['client_id'] = str(self.clientId)
			payloadAsDict['client_secret'] = str(self.clientSecret)
			payloadAsDict['username'] = self.apiUser
			payloadAsDict['password'] = self.notthat
			self.runtime.logger.report('payloadAsDict: {payloadAsDict!r}', payloadAsDict=payloadAsDict)
			self.runtime.logger.report('urlForTokenGeneration: {urlForTokenGeneration!r}', urlForTokenGeneration=urlForTokenGeneration)

			## Tell web service to use URL encoded form instead of JSON string;
			## note that the requests library uses this when passed dict value,
			## so we don't need to explicitely set it.
			headersAsDict = {}
			headersAsDict["Content-Type"] = "application/x-www-form-urlencoded"

			## Issue a POST call to URL for token generation
			apiResponse = requests.post(urlForTokenGeneration, data=payloadAsDict, headers=headersAsDict, verify=False)
			self.runtime.logger.report('Response code: {status_code!r}', status_code=apiResponse.status_code)
			self.runtime.logger.report('Response as String: {apiResponse!r}', apiResponse=apiResponse.text)
			responseAsJson =  json.loads(apiResponse.text)
			self.token = responseAsJson.get("access_token")
			if self.token is not None:
				## Create the header to use for future queries
				self.authHeader['Authorization'] = '{} {}'.format('Bearer', self.token)
				self.authHeader['Content-Type'] = 'application/json'
				self.authHeader['Accept'] = 'application/json'
				#self.authHeader['sysparm_data_source'] = 'IT Discovery Machine'
				self.connected = True

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.runtime.logger.error('Failure in SnowRestAPI.establishConnection: {stacktrace!r}', stacktrace=stacktrace)

		## end establishConnection
		return


	def get(self, url):
		"""GET request on target URL."""
		apiResponse = requests.get(url, headers=self.authHeader, verify=False)
		statusCode = apiResponse.status_code
		apiResponse = apiResponse.text
		self.runtime.logger.report('GET: Response code: {status_code!r}', status_code=statusCode)
		self.runtime.logger.report('GET: Response as string: {apiResponse!r}', apiResponse=apiResponse)
		## end get
		return (statusCode, apiResponse)


	def post(self, url, payload):
		"""POST request with payload to target URL."""
		apiResponse = requests.post('{}?sysparm_data_source=IT%20Discovery%20Machine'.format(url), data=payload, headers=self.authHeader, verify=False)
		statusCode = apiResponse.status_code
		self.runtime.logger.report('POST: Response code: {status_code!r}', status_code=statusCode)
		apiResponse = apiResponse.text
		self.runtime.logger.report('POST: Response as string: {apiResponse!r}', apiResponse=apiResponse)
		## end post
		return (statusCode, apiResponse)


	def metaQuery(self, tableName):
		"""Request a test dataset from ServiceNow."""
		statusCode = None
		metaResponse = None
		try:
			urlForCiQuery = '{}{}'.format(self.baseURL, '/api/now/cmdb/meta/{}'.format(tableName))
			self.runtime.logger.report('authHeader: {authHeader!r}', authHeader=self.authHeader)
			## Issue a GET call to URL
			(statusCode, metaResponse) = self.get(urlForCiQuery)
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.runtime.logger.error('Failure in SnowRestAPI.metaQuery: {stacktrace!r}', stacktrace=stacktrace)
			statusCode = 500

		## end metaQuery
		return (statusCode, metaResponse)


	def validateServiceNowClassSetup(self):
		"""Validate the required CMDB tables have been created (pre-requisite)."""
		requiredTables = ['u_cmdb_ci_itdm_process_fingerprint', 'u_cmdb_ci_itdm_software_fingerprint']
		for tableName in requiredTables:
			(statusCode, metaResponse) = self.metaQuery(tableName)
			if statusCode != 200:
				raise EnvironmentError('Failed to validate required ServiceNow table {}.  URL {} statusCode: {}.  Exception: {}'.format(tableName, '/api/now/table/{}'.format(tableName), statusCode, metaResponse))

		## end validateServiceNowClassSetup
		return


	def insertTopology(self, payloadAsString):
		"""Insert a new topology."""
		urlForCiQuery = '{}{}'.format(self.baseURL, '/api/now/identifyreconcile')
		## Issue a POST call to URL; payload is passed in as a string type
		(statusCode, apiResponse) = self.post(urlForCiQuery, payloadAsString)
		## If token timed out during run, get a new one and resend the request
		if statusCode == 401:
			self.connected = False
			self.establishConnection()
			(statusCode, apiResponse) = self.post(urlForCiQuery, payloadAsString)
		if statusCode != 200:
			## Should we just log, or should we abort the run?
			self.runtime.logger.error('Failure in SnowRestAPI.insertTopology.  Code: {statusCode!r}. Response: {apiResponse!r}', statusCode=statusCode, apiResponse=apiResponse)
			raise EnvironmentError('Failure in SnowRestAPI.insertTopology.  Code: {statusCode!r}. Response: {apiResponse!r}', statusCode=statusCode, apiResponse=apiResponse)
		responseAsJson = json.loads(apiResponse)

		## end insertTopology
		return responseAsJson
