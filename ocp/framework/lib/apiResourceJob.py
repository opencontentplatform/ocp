"""Job resource for the IT Discovery Machine REST API.

This module defines the Application Programming Interface (API) methods for the
/<root>/job endpoint. Available resources follow::

	/<root>/job/{service}
	/<root>/job/{service}/filter
	/<root>/job/{service}/{jobName}
	/<root>/job/{service}/{jobName}/stats

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Sep 15, 2017
	  1.1 : (CS) Replaced apiUtils with Falcon middleware, Sept 2, 2019
	  1.2 : (CS) Added /{service}/{name}/stats, Sept 24, 2019

"""

import sys
import traceback
import os
from hug.types import text
from hug.types import json as hugJson
from falcon import HTTP_400
from sqlalchemy import inspect

## From openContentPlatform
from utils import customJsonDumpsConverter
from database.schema.platformSchema import ContentGatheringResults
from database.schema.platformSchema import UniversalJobResults
from apiHugWrapper import hugWrapper
from apiResourceUtils import *

@hugWrapper.get('/')
def getJobResultTypes(request, response):
	staticPayload = {'Services' : ['contentGathering', 'universalJob'],
		'/job/{service}' : {
			'methods' : {
				'GET' : 'Return a list of job names based on results tracked by the named service.'
			}
		},
		'/job/{service}/filter' : {
			'methods' : {
				'GET' : 'Return job runtime results for the service, which match the provided filter.',
				'DELETE' : 'Delete job runtime results for the service, which match the provided filter.'
			}
		},
		'/job/{service}/{jobName}' : {
			'methods' : {
				'GET' : 'Return raw runtime results for the specified job.'
			}
		},
		'/job/{service}/{jobName}/stats' : {
			'methods' : {
				'GET' : 'Return statistical analysis on the runtime results for the specified job.'
			}
		},
	}

	## end getJobResultTypes
	return staticPayload


@hugWrapper.get('/{service}')
def getJobResultByServiceList(service:text, request, response):
	"""Return a list of job names based on results tracked by the named service."""
	try:
		if service.lower() == 'contentgathering':
			getServiceJobResultList(request, response, 'contentGathering', ContentGatheringResults)
		elif service.lower() == 'universaljob':
			getServiceJobResultList(request, response, 'universalJob', UniversalJobResults)
		else:
			request.context['payload']['errors'].append('Invalid resource: ./job/{}'.format(service))
			response.status = HTTP_400
	except:
		errorMessage(request, response)

	## end getJobResultByServiceList
	return cleanPayload(request)


@hugWrapper.get('/{service}/filter')
def executeJobResultListFilter(service:text, content:hugJson, request, response):
	"""Return job runtime results for service, matching the provided filter."""
	try:
		if hasRequiredData(request, response, content, ['filter']):
			filterConditions = content.get('filter')
			countResult = content.get('count', False)
			getJobResultsFilterHelper(request, response, filterConditions, countResult, False, service)
	except:
		errorMessage(request, response)

	## end executeJobResultListFilter
	return cleanPayload(request)


@hugWrapper.delete('/{service}/filter')
def deleteJobResultListFilter(service:text, content:hugJson, request, response):
	"""Delete job runtime results for service, matching the provided filter.

	Note: this is the runtime meta data for the job, not the CIs.
	"""
	try:
		if hasRequiredData(request, response, content, ['filter']):
			filterConditions = content.get('filter')
			countResult = content.get('count', False)
			getJobResultsFilterHelper(request, response, filterConditions, countResult, True, service)

	except:
		errorMessage(request, response)

	## end deleteJobResultListFilter
	return cleanPayload(request)


@hugWrapper.get('/{service}/{name}')
def executeNamedJobResultList(service:text, name:text, request, response):
	"""Return runtime results for the specified job."""
	try:
		dbTable = None
		if service.lower() == 'contentgathering':
			dbTable = ContentGatheringResults
		elif service.lower() == 'universaljob':
			dbTable = UniversalJobResults
		else:
			request.context['payload']['errors'].append('Invalid resource: ./job/{}'.format(service))
			response.status = HTTP_400

		if dbTable is not None:
			dataHandle = request.context['dbSession'].query(dbTable).filter(dbTable.job == name).order_by(dbTable.endpoint.desc()).all()
			for item in dataHandle:
				request.context['payload'][item.endpoint] = {col:getattr(item, col) for col in inspect(item).mapper.c.keys() if col != 'job'}

	except:
		errorMessage(request, response)

	## end executeNamedJobResultList
	return cleanPayload(request)


@hugWrapper.get('/{service}/{name}/stats')
def executeNamedJobStatistics(service:text, name:text, request, response):
	"""Return statistical analysis on the runtime results for the specified job."""
	try:
		statusSet = {}
		timeElapsedSet = {}
		timeElapsedFull = []
		dbTable = None
		if service.lower() == 'contentgathering':
			dbTable = ContentGatheringResults
		elif service.lower() == 'universaljob':
			dbTable = UniversalJobResults
		else:
			request.context['payload']['errors'].append('Invalid resource: ./job/{}'.format(service))
			response.status = HTTP_400

		if dbTable is not None:
			dataHandle = request.context['dbSession'].query(dbTable).filter(dbTable.job == name).order_by(dbTable.endpoint.desc()).all()
			for item in dataHandle:
				uniqueId = item.endpoint
				## Don't need everything; minimal visibility is fine
				status = item.status
				runtime = item.time_elapsed
				timestamp = customJsonDumpsConverter(item.date_last_invocation)
				if status not in statusSet:
					statusSet[status] = {}
				if status not in timeElapsedSet:
					timeElapsedSet[status] = []
				statusSet[status][uniqueId] = {'time_elapsed': runtime, 'date_last_invocation': timestamp}
				timeElapsedSet[status].append(runtime)
				timeElapsedFull.append(runtime)

			## Attempt to load numpy
			statDefault = None
			try:
				import numpy
			except ModuleNotFoundError:
				statDefault = 'Need to install the numpy package for this: \'pip install numpy\''

			payload = request.context['payload']
			payload['Statistics'] = {}
			if len(timeElapsedFull) > 0:
				## Report on the full set: Overall
				payload['Statistics']['Overall'] = {}
				timeElapsedFull.sort()
				payload['Statistics']['Overall']['totalEndpoints'] = len(timeElapsedFull)
				payload['Statistics']['Overall']['shortestRuntime'] = float('{0:.4f}'.format(timeElapsedFull[0]))
				payload['Statistics']['Overall']['longestRuntime'] = float('{0:.4f}'.format(timeElapsedFull[-1]))
				payload['Statistics']['Overall']['averageRuntime'] = None
				payload['Statistics']['Overall']['standardDeviation'] = None
				if len(timeElapsedFull) > 1:
					if statDefault is None:
						totalElements = numpy.array(timeElapsedFull)
						totalMean = numpy.mean(totalElements, axis=0)
						totalStandardDeviation = numpy.std(totalElements, axis=0)
						payload['Statistics']['Overall']['averageRuntime'] = float('{0:.4f}'.format(totalMean))
						payload['Statistics']['Overall']['standardDeviation'] = float('{0:.4f}'.format(totalStandardDeviation))
					else:
						payload['Statistics']['Overall']['averageRuntime'] = statDefault
						payload['Statistics']['Overall']['standardDeviation'] = statDefault

				## Report per status type: SUCCESS, WARNING, FAILURE, UNKNOWN
				payload['Statistics']['Breakdown'] = {}
				for status in timeElapsedSet.keys():
					payload['Statistics']['Breakdown'][status] = {}
					runtimes = timeElapsedSet[status]
					runtimes.sort()
					payload['Statistics']['Breakdown'][status]['totalEndpoints'] = len(runtimes)
					payload['Statistics']['Breakdown'][status]['shortestRuntime'] = float('{0:.4f}'.format(runtimes[0]))
					payload['Statistics']['Breakdown'][status]['longestRuntime'] = float('{0:.4f}'.format(runtimes[-1]))
					payload['Statistics']['Breakdown'][status]['averageRuntime'] = None
					payload['Statistics']['Breakdown'][status]['standardDeviation'] = None
					payload['Statistics']['Breakdown'][status]['outliers'] = None
					if len(runtimes) > 1:
						if statDefault is None:
							## Using numpy for mean and standard deviation calculations
							elements = numpy.array(runtimes)
							mean = numpy.mean(elements, axis=0)
							standardDeviation = numpy.std(elements, axis=0)
							## All standard deviation values under 1 second
							## (milliseconds) are increased for comparisons
							## since we don't care about the granularity if
							## it only took 2 seconds longer than others.
							standardDeviationUsed = standardDeviation
							if standardDeviationUsed < 1:
								standardDeviationUsed = 1.0
							## Get rid of outliers by removing any runtimes that were
							## above (mean + 2*standardDeviation) and any points below
							## (mean - 2*standardDeviation):
							lowThreshold = mean - 2 * standardDeviationUsed
							highThreshold = mean + 2 * standardDeviationUsed
							reducedSet = [x for x in runtimes if (x > lowThreshold)]
							reducedSet = [x for x in reducedSet if (x < highThreshold)]
							cleanElements = numpy.array(reducedSet)
							cleanMean = numpy.mean(cleanElements, axis=0)
							payload['Statistics']['Breakdown'][status]['averageRuntime'] = float('{0:.4f}'.format(cleanMean))
							payload['Statistics']['Breakdown'][status]['standardDeviation'] = float('{0:.4f}'.format(standardDeviation))
							## We should report at least the endpoint in question
							## instead of just the runtime value.
							lowOutliers = []
							highOutliers = []
							for endpoint,entry in statusSet[status].items():
								runtime = entry.get('time_elapsed')
								timestamp = entry.get('date_last_invocation')
								if runtime < lowThreshold:
									lowOutliers.append({'endpoint': endpoint, 'timestamp': timestamp, 'runtime': float('{0:.4f}'.format(runtime))})
								elif runtime > highThreshold:
									highOutliers.append({'endpoint': endpoint, 'timestamp': timestamp, 'runtime': float('{0:.4f}'.format(runtime))})
							if len(lowOutliers) > 0 or len(highOutliers) > 0:
								payload['Statistics']['Breakdown'][status]['outliers'] = {}
								if len(lowOutliers) > 0:
									payload['Statistics']['Breakdown'][status]['outliers']['low'] = lowOutliers
								if len(highOutliers) > 0:
									payload['Statistics']['Breakdown'][status]['outliers']['high'] = highOutliers
						else:
							payload['Statistics']['Breakdown'][status]['averageRuntime'] = statDefault
							payload['Statistics']['Breakdown'][status]['standardDeviation'] = statDefault
							payload['Statistics']['Breakdown'][status]['outliers'] = statDefault
	except:
		errorMessage(request, response)

	## end executeNamedJobStatistics
	return cleanPayload(request)
