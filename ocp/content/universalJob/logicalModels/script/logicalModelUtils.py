"""Shared functions in this module.

Functions:
  getQueryResults : run a query to get all matching objects
  getMetaDataResults : run a query to get all matching metadata objects

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Jul 23, 2018

"""
import sys
import traceback
import os
import json

## From openContentPlatform
from utilities import getApiQueryResultsFull


def getQueryResults(runtime, queryName, resultsFormat):
	"""Run a query to get all matching objects."""
	queryFile = os.path.join(runtime.env.universalJobPkgPath, 'logicalModels', 'input', queryName + '.json')
	if not os.path.isfile(queryFile):
		raise EnvironmentError('Missing query file specified in the parameters: {queryFile!r}', queryFile=queryFile)
	queryContent = None
	with open(queryFile) as fp:
		queryContent = json.load(fp)
	queryResults = getApiQueryResultsFull(runtime, queryContent, resultsFormat=resultsFormat)

	## end getQueryResults
	return queryResults


def getMetaDataResults(runtime, queryName):
	"""Run a query to get all matching metadata objects."""
	formattedResults = {}
	queryResults = getQueryResults(runtime, queryName, 'Flat')
	for result in queryResults.get('objects'):
		try:
			identifier = result.get('identifier')
			data = result.get('data')
			runtime.logger.report('  found metadata : {identifier!r} {data!r}', identifier=identifier, data=data)
			formattedResults[identifier] = data
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Failure in getMetaDataResults: {stacktrace!r}', stacktrace=stacktrace)

	## end getMetaDataResults
	return formattedResults
