"""Remove specified objects in the DB that are past the desired retention period.

Functions:
  startJob : standard job entry point
  getStaleResultCount : issue an API call to get the stale object count
  deleteStaleResultCount : issue an API call to delete matching stale objects
  parseResponse : helper to get the status code and JSON response

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Sep 6, 2019

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


def getStaleObjectCount(runtime, objectType, thresholdInHours):
	"""Issue an API call to get the object count."""
	resultCount = 0
	content = {
		'count': True,
		'objects': [
			{
				'class_name': objectType,
				'attributes': ['time_gathered', 'caption'],
				'minimum': '1',
				'maximum': '',
				'filter': [{
						'negation': True,
						'condition': {
							'attribute': 'time_gathered',
							'operator': 'lastnumhours',
							'value': thresholdInHours
						}
				}]
			}
		],
		'links': []
	}

	apiResponse = getApiResult(runtime, 'query/this', 'get', customPayload={'content': content})
	(responseCode, responseAsJson) = parseResponse(apiResponse)
	if responseCode is not None and str(responseCode) == '200':
		queryResults = json.loads(apiResponse.text)
		resultCount = queryResults.get('Result Count')
		runtime.logger.report('Stale {objectType!r} objects found: {resultCount!r}', objectType=objectType, resultCount=resultCount)
	else:
		raise EnvironmentError('Unexpected response from API. Code: {}. Payload: {}'.format(responseCode, responseAsJson))

	## end getStaleObjectCount
	return resultCount


def deleteStaleObjects(runtime, objectType, thresholdInHours):
	"""Issue an API call to delete the matching results."""
	content = {
		'objects': [
			{
				'class_name': objectType,
				'attributes': ['time_gathered', 'caption'],
				'minimum': '1',
				'maximum': '',
				'filter': [{
						'negation': True,
						'condition': {
							'attribute': 'time_gathered',
							'operator': 'lastnumhours',
							'value': thresholdInHours
						}
				}]
			}
		],
		'links': []
	}

	apiResponse = getApiResult(runtime, 'query/this', 'delete', customPayload={'content': content})
	(responseCode, responseAsJson) = parseResponse(apiResponse)
	if responseCode is not None and str(responseCode) == '200':
		queryResults = json.loads(apiResponse.text)
		runtime.logger.report('Delete completed: {queryResults!r}', queryResults=queryResults)
	else:
		raise EnvironmentError('Unexpected response from API. Code: {}. Payload: {}'.format(responseCode, responseAsJson))

	## end deleteStaleObjects
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		objectTypes = runtime.parameters.get('objectTypes')
		thresholdDays = runtime.parameters.get('thresholdInNumberOfDays')
		if not isinstance(thresholdDays, int):
			raise EnvironmentError('Please change the value of thresholdInNumberOfDays in the job parameters to a valid integer.')
		thresholdInHours = thresholdDays * 24

		for objectType in objectTypes:
			runtime.logger.report('Attempting to cleanup any stale {objectType!r} objects older than {thresholdDays!r} days.', objectType=objectType, thresholdDays=thresholdDays)
			## Don't have to do a count before delete, but it's nice for logging
			resultCount = getStaleObjectCount(runtime, objectType, thresholdInHours)
			if resultCount > 0:
				deleteStaleObjects(runtime, objectType, thresholdInHours)
			else:
				## Nothing to do
				runtime.logger.debug('No stale {objectType!r} objects found for cleanup.', objectType=objectType)

		## Update the runtime status to success
		if runtime.getStatus() == 'UNKNOWN':
			runtime.status(1)

	except:
		runtime.setError(__name__)

	## end startJob
	return
