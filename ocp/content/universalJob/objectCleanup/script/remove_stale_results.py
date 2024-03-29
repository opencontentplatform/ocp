"""Remove job results that are past the desired retention period.

Functions:
  startJob : standard job entry point
  getStaleResultCount : issue an API call to get the stale result count
  deleteStaleResultCount : issue an API call to delete matching stale results
  parseResponse : helper to get the status code and JSON response

"""
import json
from contextlib import suppress

## From openContentPlatform
from utilities import getApiResult


def parseResponse(apiResponse):
	"""Simple helper to get the status code and JSON response."""
	responseCode = None
	responseAsJson = {}
	with suppress(Exception):
		responseCode = apiResponse.status_code
	with suppress(Exception):
		responseAsJson = json.loads(apiResponse.text)
	return (responseCode, responseAsJson)


def getStaleResultCount(runtime, resultType, serviceType, thresholdInHours):
	"""Issue an API call to get the object count."""
	resultCount = 0
	content = {
		'count': True,
		'filter': [{
			'negation': True,
			'condition': {
				'attribute': 'time_started',
				'operator': 'lastnumhours',
				'value': thresholdInHours
			}
		}]
	}
	apiResponse = getApiResult(runtime, 'job/{}/{}/filter'.format(resultType, serviceType), 'get', customPayload={'content': content})
	(responseCode, responseAsJson) = parseResponse(apiResponse)
	if responseCode is not None and str(responseCode) == '200':
		queryResults = json.loads(apiResponse.text)
		resultCount = queryResults.get('Result Count')
		runtime.logger.report('Stale {resultType!r} results found: {resultCount!r}', resultType=resultType, resultCount=resultCount)
	else:
		raise EnvironmentError('Unexpected response from API. Code: {}. Payload: {}'.format(responseCode, responseAsJson))

	## end getStaleResultCount
	return resultCount


def deleteStaleResultCount(runtime, resultType, serviceType, thresholdInHours):
	"""Issue an API call to delete the matching results."""
	content = {
		'filter': [{
			'negation': True,
			'condition': {
				'attribute': 'time_started',
				'operator': 'lastnumhours',
				'value': thresholdInHours
			}
		}]
	}
	apiResponse = getApiResult(runtime, 'job/{}/{}/filter'.format(resultType, serviceType), 'delete', customPayload={'content': content})
	(responseCode, responseAsJson) = parseResponse(apiResponse)
	if responseCode is not None and str(responseCode) == '200':
		queryResults = json.loads(apiResponse.text)
		runtime.logger.report('Delete completed: {queryResults!r}', queryResults=queryResults)
	else:
		raise EnvironmentError('Unexpected response from API. Code: {}. Payload: {}'.format(responseCode, responseAsJson))

	## end deleteStaleResultCount
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		serviceType = runtime.parameters.get('serviceType')
		resultType = runtime.parameters.get('resultType')
		thresholdDays = runtime.parameters.get('thresholdInNumberOfDays')
		if not isinstance(thresholdDays, int):
			raise EnvironmentError('Please change the value of thresholdInNumberOfDays in the job parameters to a valid integer.')
		thresholdInHours = thresholdDays * 24
		## Don't have to do a count before delete, but it's nice for logging
		resultCount = getStaleResultCount(runtime, resultType, serviceType, thresholdInHours)
		if resultCount > 0:
			deleteStaleResultCount(runtime, resultType, serviceType, thresholdInHours)
		else:
			## Nothing to do
			runtime.logger.debug('No stale {resultType!r}/{serviceType!r} results found for cleanup.', resultType=resultType, serviceType=serviceType)

		## Update the runtime status to success
		if runtime.getStatus() == 'UNKNOWN':
			runtime.status(1)

	except:
		runtime.setError(__name__)

	## end startJob
	return
