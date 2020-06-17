"""Remove group objects in the DB that are not connected to something else.

Functions:
  startJob : standard job entry point
  getStaleResultCount : issue an API call to get the stale object count
  deleteStaleResultCount : issue an API call to delete matching stale objects
  parseResponse : helper to get the status code and JSON response

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Nov 6, 2019

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


def getEmptyGroupsCount(runtime, objectType):
	"""Issue an API call to get the object count."""
	resultCount = 0
	content = {
		"count": True,
		"objects": [
			{
				"label": "TARGET",
				"class_name": objectType,
				"attributes": ["caption"],
				"filter": [],
				"minimum": "1",
				"maximum": "",
				"linchpin": True
			}, {
				"label": "CHILD",
				"class_name": "BaseObject",
				"attributes": ["caption"],
				"filter": [],
				"minimum": "0",
				"maximum": "0"
			}
		],
		"links": [
			{
				"label": "TARGET_TO_CHILD",
				"class_name": "Contain",
				"first_id": "TARGET",
				"second_id": "CHILD"
			}
		]
	}

	apiResponse = getApiResult(runtime, 'query/this', 'get', customPayload={'content': content})
	(responseCode, responseAsJson) = parseResponse(apiResponse)
	if responseCode is not None and str(responseCode) == '200':
		queryResults = json.loads(apiResponse.text)
		resultCount = queryResults.get('Result Count')
		runtime.logger.report('Stale {objectType!r} objects found: {resultCount!r}', objectType=objectType, resultCount=resultCount)
	else:
		raise EnvironmentError('Unexpected response from API. Code: {}. Payload: {}'.format(responseCode, responseAsJson))

	## end getEmptyGroupsCount
	return resultCount


def deleteEmptyGroups(runtime, objectType):
	"""Issue an API call to delete the matching results."""
	content = {
		"objects": [
			{
				"label": "TARGET",
				"class_name": objectType,
				"attributes": ["caption"],
				"filter": [],
				"minimum": "1",
				"maximum": "",
				"linchpin": True
			}, {
				"label": "CHILD",
				"class_name": "BaseObject",
				"attributes": ["caption"],
				"filter": [],
				"minimum": "0",
				"maximum": "0"
			}
		],
		"links": [
			{
				"label": "TARGET_TO_CHILD",
				"class_name": "Contain",
				"first_id": "TARGET",
				"second_id": "CHILD"
			}
		]
	}

	apiResponse = getApiResult(runtime, 'query/this', 'delete', customPayload={'content': content})
	(responseCode, responseAsJson) = parseResponse(apiResponse)
	if responseCode is not None and str(responseCode) == '200':
		queryResults = json.loads(apiResponse.text)
		runtime.logger.report('Delete completed: {queryResults!r}', queryResults=queryResults)
	else:
		raise EnvironmentError('Unexpected response from API. Code: {}. Payload: {}'.format(responseCode, responseAsJson))

	## end deleteEmptyGroups
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		objectTypes = runtime.parameters.get('objectTypes')
		for objectType in objectTypes:
			runtime.logger.report('Attempting to cleanup {objectType!r} objects, void of any links.', objectType=objectType)
			## Don't have to do a count before delete, but it's nice for logging
			resultCount = getEmptyGroupsCount(runtime, objectType)
			if resultCount > 0:
				deleteEmptyGroups(runtime, objectType)
			else:
				## Nothing to do
				runtime.logger.debug('No objects of type {objectType!r} found for cleanup.', objectType=objectType)

		## Update the runtime status to success
		if runtime.getStatus() == 'UNKNOWN':
			runtime.status(1)

	except:
		runtime.setError(__name__)

	## end startJob
	return
