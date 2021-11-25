"""Shared functions across the merge_nodes scripts.

Functions:
  mergeObjects : issue an API call to merge the weak/strong objects
  getQueryResults : run a query to get all matching objects

"""

import json
import os
from contextlib import suppress

## From openContentPlatform
from utilities import getApiQueryResultsFull, getApiResult


def mergeObjects(runtime, weakId, strongId):
	"""Issue an API call to merge the objects."""
	apiResponse = getApiResult(runtime, 'tool/mergeObject', 'post', customPayload={'weakId': weakId, 'strongId': strongId})
	responseCode = None
	responseAsJson = {}
	with suppress(Exception):
		responseCode = apiResponse.status_code
	with suppress(Exception):
		responseAsJson = json.loads(apiResponse.text)
	if responseCode is None or str(responseCode) != '200':
		raise EnvironmentError('Unexpected response from API. Code: {}. Payload: {}'.format(responseCode, responseAsJson))


def getQueryResults(runtime, queryName, resultsFormat):
	"""Run a query to get all matching objects."""
	queryFile = os.path.join(runtime.env.universalJobPkgPath, 'strongObjectReference', 'input', queryName + '.json')
	if not os.path.isfile(queryFile):
		raise EnvironmentError('Missing query file specified in the parameters: {queryFile!r}', queryFile=queryFile)
	queryContent = None
	with open(queryFile) as fp:
		queryContent = json.load(fp)
	queryResults = getApiQueryResultsFull(runtime, queryContent, resultsFormat=resultsFormat, verify=runtime.ocpCertFile)

	## end getQueryResults
	return queryResults
