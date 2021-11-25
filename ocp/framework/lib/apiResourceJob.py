"""Job resource for the Open Content Platform REST API.

This module defines the Application Programming Interface (API) methods for the
/<root>/job endpoint. Available resources follow::

	/<root>/job/config
	/<root>/job/config/{service}
	/<root>/job/config/{service}/{jobName}
	/<root>/job/runtime
	/<root>/job/runtime/{service}
	/<root>/job/runtime/{service}/filter
	/<root>/job/runtime/{service}/{jobName}
	/<root>/job/runtime/{service}/{jobName}/stats
	/<root>/job/review
	/<root>/job/review/{service}
	/<root>/job/review/{service}/filter
	/<root>/job/review/{service}/{jobName}
	/<root>/job/log
	/<root>/job/log/{jobName}
	/<root>/job/log/{jobName}/{endpoint}

"""

import sys
import traceback
import os
import json
from hug.types import text
from hug.types import json as hugJson
from falcon import HTTP_400
from sqlalchemy import inspect

## From openContentPlatform
from utils import customJsonDumpsConverter
from database.schema.platformSchema import JobUniversal, UniversalJobResults, UniversalJobServiceResults
from database.schema.platformSchema import JobContentGathering, ContentGatheringResults, ContentGatheringServiceResults
from apiHugWrapper import hugWrapper
from apiResourceUtils import *


@hugWrapper.get('/')
def getJobResources(request, response):
	staticPayload = {
		'/job/config' : {
			'methods' : {
				'GET' : 'Show available config resources.'
			}
		},
		'/job/runtime' : {
			'methods' : {
				'GET' : 'Show available runtime resources.'
			}
		},
		'/job/review' : {
			'methods' : {
				'GET' : 'Show available review resources.'
			}
		},
		'/job/log' : {
			'methods' : {
				'GET' : 'Show available directories on the server containing (or previously containing) job execution logs.'
			}
		}
	}

	## end getJobResources
	return staticPayload


@hugWrapper.get('/config')
def getJobConfigResources(request, response):
	#staticPayload = {'Services' : ['contentGathering', 'universalJob', 'serverSide'],
	staticPayload = {'Services' : ['contentGathering', 'universalJob'],
		'/job/config/{service}' : {
			'methods' : {
				'GET' : 'Return a list of job names configured in the specified service.',
				'POST': 'Create a new job definition in the specified service.'
			}
		},
		'/job/config/{service}/{jobName}' : {
			'methods' : {
				'GET' : 'Return current configuration of the specified job.',
				'PUT' : 'Updates the configuration for the named job.',
				'DELETE' : 'Delete the specified job configuration.'
			}
		}
	}

	## end getJobConfigResources
	return staticPayload


def getConfigServiceTable(service, request, response):
	"""Helper for shared code path."""
	dbTable = None
	if service.lower() == 'contentgathering':
		dbTable = JobContentGathering
	elif service.lower() == 'universaljob':
		dbTable = JobUniversal
	elif service.lower() == 'serverside':
		dbTable = JobServerSide
	else:
		request.context['payload']['errors'].append('Invalid resource: ./job/runtime/{}'.format(service))
		response.status = HTTP_400
	return dbTable


@hugWrapper.get('/config/{service}')
def getJobConfigServiceList(service:text, request, response):
	"""Return a list of job names configured in the specified service."""
	try:
		dbTable = getConfigServiceTable(service, request, response)
		if dbTable is not None:
			dataHandle = request.context['dbSession'].query(dbTable.name).order_by(dbTable.name).all()
			jobNames = []
			for item in dataHandle:
				jobNames.append(item[0])
			request.context['payload']['Jobs'] = jobNames

	except:
		errorMessage(request, response)

	## end getJobConfigServiceList
	return cleanPayload(request)


@hugWrapper.post('/config/{service}')
def createJobConfigServiceList(service:text, content:hugJson, request, response):
	"""Insert a new job in the specified service."""
	try:
		if hasRequiredData(request, response, content, ['source', 'package', 'content']):
			dbClass = getConfigServiceTable(service, request, response)
			if dbClass is not None:
				packageName = content.get('package')
				jobDescriptor = content.get('content')
				jobShortName = jobDescriptor.get('jobName')
				jobName = '{}.{}'.format(packageName, jobShortName)

				dataHandle = request.context['dbSession'].query(dbClass).filter(dbClass.name==jobName).first()
				if dataHandle is not None:
					request.context['payload']['errors'].append('Job already exists: {name!r}'.format(name=jobName))
					response.status = HTTP_404
				else:
					attributes = {}
					attributes['name'] = jobName
					attributes['package'] = packageName
					attributes['realm'] = jobDescriptor.get('realm', 'default')
					attributes['active'] = not jobDescriptor.get('isDisabled', True)
					attributes['content'] = jobDescriptor
					## Update the source
					source = mergeUserAndSource(content, request)
					attributes['object_created_by'] = source

					thisEntry = dbClass(**attributes)
					request.context['dbSession'].add(thisEntry)
					request.context['dbSession'].commit()
					request.context['payload']['Response'] = 'Inserted job: {name}'.format(name=jobName)

	except:
		errorMessage(request, response)

	## end createJobConfigServiceList
	return cleanPayload(request)


@hugWrapper.get('/config/{service}/{name}')
def getThisJobConfig(service:text, name:text, request, response):
	"""Return configuration for the specified job."""
	try:
		dbTable = getConfigServiceTable(service, request, response)
		if dbTable is not None:
			dataHandle = request.context['dbSession'].query(dbTable).filter(dbTable.name == name).first()
			if dataHandle:
				request.context['payload'][dataHandle.name] = {col:getattr(dataHandle, col) for col in inspect(dataHandle).mapper.c.keys()}

		## Standard conversions of dates and Decimal types to string
		request.context['payload'] = json.loads(json.dumps(request.context['payload'], default=customJsonDumpsConverter))
	except:
		errorMessage(request, response)

	## end getJobConfig
	return cleanPayload(request)


@hugWrapper.put('/config/{service}/{name}')
def updateThisJobConfig(service:text, name:text, content:hugJson, request, response):
	"""Update job configuration with the provided JSON content."""
	try:
		## Don't do this for a PUT operation; the goal here is to keep it simple
		## for job activation/deactivation and parameter changes.
		#if hasRequiredData(request, response, content, ['source', 'content']):
		dbTable = getConfigServiceTable(service, request, response)
		if dbTable is not None:
			dataHandle = request.context['dbSession'].query(dbTable).filter(dbTable.name==name).first()
			if dataHandle is None:
				request.context['payload']['errors'].append('No job exists for {}. Use POST on ./job/config/<service> to create.'.format(name))
				response.status = HTTP_404
			else:
				## Get the previous contents
				contentToUpdate = dataHandle.content
				## Override any/all new settings provided
				contentToMerge = {}
				contentToMerge['name'] = name
				#dataSection = content.get('content', {})
				dataSection = content
				for key in dataSection:
					contentToUpdate[key] = dataSection.get(key)
					if key == 'realm':
						contentToMerge['realm'] = dataSection.get(key, 'default')
					if key == 'isDisabled':
						contentToMerge['active'] = not dataSection.get(key, True)
				## Update the source
				source = mergeUserAndSource(content, request)
				contentToMerge['object_updated_by'] = source
				## Get it back to JSON (not string or Python formats)
				contentToMerge['content'] = json.loads(json.dumps(contentToUpdate))
				request.context['logger'].debug('previousContent: {}'.format(contentToUpdate))
				request.context['logger'].debug('newContent: {}'.format(content))
				request.context['logger'].debug('mergedContent: {}'.format(contentToMerge))
				## Merge back to the DB object
				dataHandle = dbTable(**contentToMerge)
				dataHandle = request.context['dbSession'].merge(dataHandle)
				request.context['dbSession'].commit()
				request.context['payload']['Response'] = 'Updated job configuration for {}'.format(name)

	except:
		errorMessage(request, response)

	## end updateThisJobConfig
	return cleanPayload(request)


@hugWrapper.delete('/config/{service}/{name}')
def deleteThisJobConfig(service:text, name:text, request, response):
	"""Delete the config group for the named realm."""
	try:
		dbTable = getConfigServiceTable(service, request, response)
		if dbTable is not None:
			dataHandle = request.context['dbSession'].query(dbTable).filter(dbTable.name==name).first()
			if dataHandle is None:
				request.context['payload']['errors'].append('Job not found: {}'.format(name))
				response.status = HTTP_404
			else:
				request.context['dbSession'].delete(dataHandle)
				request.context['dbSession'].commit()
				request.context['payload']['Success'] = 'Removed job: {}'.format(name)

	except:
		errorMessage(request, response)

	## end deleteThisJobConfig
	return cleanPayload(request)


@hugWrapper.get('/runtime')
def getJobRuntimeResources(request, response):
	#staticPayload = {'Services' : ['contentGathering', 'universalJob', 'serverSide'],
	staticPayload = {'Services' : ['contentGathering', 'universalJob'],
		'/job/runtime/{service}' : {
			'methods' : {
				'GET' : 'Return a list of job names based on results tracked by the named service.'
			}
		},
		'/job/runtime/{service}/filter' : {
			'methods' : {
				'GET' : 'Return job runtime results for the service, which match the provided filter.',
				'DELETE' : 'Delete job runtime results for the service, which match the provided filter.'
			}
		},
		'/job/runtime/{service}/{jobName}' : {
			'methods' : {
				'GET' : 'Return raw runtime results for the specified job.'
			}
		},
		'/job/runtime/{service}/{jobName}/stats' : {
			'methods' : {
				'GET' : 'Return statistical analysis on the runtime results for the specified job.'
			}
		}
	}

	## end getJobRuntimeResources
	return staticPayload


@hugWrapper.get('/runtime/{service}')
def getJobRuntimeServiceList(service:text, request, response):
	"""Return list of job names with runtime results, from the specified service."""
	try:
		if service.lower() == 'contentgathering':
			getServiceJobResultList(request, response, 'contentGathering', ContentGatheringResults)
		elif service.lower() == 'universaljob':
			getServiceJobResultList(request, response, 'universalJob', UniversalJobResults)
		# elif service.lower() == 'serverside':
		# 	getServiceJobResultList(request, response, 'serverSide', ServerSideResults)
		else:
			request.context['payload']['errors'].append('Invalid resource: ./job/runtime/{}'.format(service))
			response.status = HTTP_400
	except:
		errorMessage(request, response)

	## end getJobRuntimeServiceList
	return cleanPayload(request)


@hugWrapper.get('/runtime/{service}/filter')
def executeJobResultListFilter(service:text, content:hugJson, request, response):
	"""Return job runtime results for service, matching the provided filter."""
	try:
		if hasRequiredData(request, response, content, ['filter']):
			filterConditions = content.get('filter')
			countResult = content.get('count', False)
			getJobResultsFilterHelper(request, response, filterConditions, countResult, False, service)

		## Standard conversions of dates and Decimal types to string
		request.context['payload'] = json.loads(json.dumps(request.context['payload'], default=customJsonDumpsConverter))
	except:
		errorMessage(request, response)

	## end executeJobResultListFilter
	return cleanPayload(request)


@hugWrapper.delete('/runtime/{service}/filter')
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


@hugWrapper.get('/runtime/{service}/{name}')
def executeNamedJobResultList(service:text, name:text, request, response):
	"""Return runtime results for the specified job."""
	try:
		dbTable = None
		if service.lower() == 'contentgathering':
			dbTable = ContentGatheringResults
		elif service.lower() == 'universaljob':
			dbTable = UniversalJobResults
		# elif service.lower() == 'serverside':
		# 	dbTable = ServerSideResults
		else:
			request.context['payload']['errors'].append('Invalid resource: ./job/{}'.format(service))
			response.status = HTTP_400

		if dbTable is not None:
			dataHandle = request.context['dbSession'].query(dbTable).filter(dbTable.job == name).order_by(dbTable.endpoint.desc()).all()
			for item in dataHandle:
				request.context['payload'][item.endpoint] = {col:getattr(item, col) for col in inspect(item).mapper.c.keys() if col != 'job'}

		## Standard conversions of dates and Decimal types to string
		request.context['payload'] = json.loads(json.dumps(request.context['payload'], default=customJsonDumpsConverter))

	except:
		errorMessage(request, response)

	## end executeNamedJobResultList
	return cleanPayload(request)


@hugWrapper.get('/runtime/{service}/{name}/stats')
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
			request.context['payload']['errors'].append('Invalid resource: ./job/runtime/{}'.format(service))
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


@hugWrapper.get('/review')
def getJobReviewResources(request, response):
	staticPayload = {'Services' : ['contentGathering', 'universalJob'],
		'/job/review/{service}' : {
			'methods' : {
				'GET' : 'Return a list of job names based on results tracked by the named service.'
			}
		},
		'/job/review/{service}/filter' : {
			'methods' : {
				'GET' : 'Return job review results for the service, which match the provided filter.',
				'DELETE' : 'Delete job review results for the service, which match the provided filter.'
			}
		},
		'/job/review/{service}/{jobName}' : {
			'methods' : {
				'GET' : 'Return all results for the specified job.'
			}
		}
	}

	## end getJobReviewResources
	return staticPayload


def getReviewServiceTable(service, request, response):
	"""Helper for shared code path."""
	dbTable = None
	if service.lower() == 'contentgathering':
		dbTable = ContentGatheringServiceResults
	elif service.lower() == 'universaljob':
		dbTable = UniversalJobServiceResults
	else:
		request.context['payload']['errors'].append('Invalid resource: ./job/review/{}'.format(service))
		response.status = HTTP_400
	return dbTable


@hugWrapper.get('/review/{service}')
def getJobReviewServiceList(service:text, request, response):
	"""Return a list of job names previously tracked by the specified service."""
	try:
		dbTable = getReviewServiceTable(service, request, response)
		if dbTable is not None:
			dataHandle = request.context['dbSession'].query(distinct(dbTable.job)).order_by(dbTable.job).all()
			jobNames = []
			for item in dataHandle:
				jobNames.append(item[0])
			request.context['payload']['Jobs'] = jobNames

	except:
		errorMessage(request, response)

	## end getJobReviewServiceList
	return cleanPayload(request)


@hugWrapper.get('/review/{service}/{name}')
def getThisJobReview(service:text, name:text, request, response):
	"""Return all summary results for the specified job."""
	try:
		dbTable = getReviewServiceTable(service, request, response)
		if dbTable is not None:
			dataHandle = request.context['dbSession'].query(dbTable).filter(dbTable.job == name).all()
			results = []
			for item in dataHandle:
				results.append({col:getattr(item, col) for col in inspect(item).mapper.c.keys() if col != 'job'})
			request.context['payload'][name] = results

		## Standard conversions of dates and Decimal types to string
		request.context['payload'] = json.loads(json.dumps(request.context['payload'], default=customJsonDumpsConverter))
	except:
		errorMessage(request, response)

	## end getJobReview
	return cleanPayload(request)


@hugWrapper.get('/review/{service}/filter')
def executeJobReviewFilter(service:text, content:hugJson, request, response):
	"""Return requested job summary results, matching the provided filter."""
	try:
		dbTable = getReviewServiceTable(service, request, response)
		if dbTable is not None:
			if hasRequiredData(request, response, content, ['filter']):
				filterConditions = content.get('filter')
				countResult = content.get('count', False)
				searchThisContentHelper(request, response, filterConditions, dbTable, countResult, False)

		## Standard conversions of dates and Decimal types to string
		request.context['payload'] = json.loads(json.dumps(request.context['payload'], default=customJsonDumpsConverter))
	except:
		errorMessage(request, response)

	## end executeJobReviewFilter
	return cleanPayload(request)


@hugWrapper.delete('/review/{service}/filter')
def deleteJobReviewFilter(service:text, content:hugJson, request, response):
	"""Delete job runtime results for service, matching the provided filter.

	Note: this is the runtime meta data for the job, not the CIs.
	"""
	try:
		dbTable = getReviewServiceTable(service, request, response)
		if dbTable is not None:
			if hasRequiredData(request, response, content, ['filter']):
				filterConditions = content.get('filter')
				countResult = content.get('count', False)
				searchThisContentHelper(request, response, filterConditions, dbTable, countResult, True)

	except:
		errorMessage(request, response)

	## end deleteJobReviewFilter
	return cleanPayload(request)


@hugWrapper.get('/log')
def getJobLogDirectories(request, response):
	"""Return log directories (jobNames) available in runtime/log/job."""
	try:
		logDir = os.path.join(request.context['envLogPath'], 'job')
		jobDirectories = []
		## The job directory may not yet exist
		if os.path.exists(logDir):
			for jobName in os.listdir(logDir):
				if os.path.isdir(os.path.join(logDir, jobName)):
					jobDirectories.append(jobName)

		staticPayload = {'Jobs' : jobDirectories,
			'/job/log' : {
				'methods' : {
					'GET' : 'Return a list of Job directories on the server containing (or previously containing) execution logs.'
				}
			},
			'/job/log/{job}' : {
				'methods' : {
					'GET' : 'Return logs available in the ./runtime/log/job/{job} directory.'
				}
			},
			'/job/log/{job}/{endpoint}' : {
				'methods' : {
					'GET' : 'Return the ./runtime/log/job/{job}/{endpoint}.log file.'
				}
			}
		}

	except:
		errorMessage(request, response)

	## end getJobLogDirectories
	return staticPayload


@hugWrapper.get('/log/{jobName}')
def getLogEndpointsForJob(jobName:text, request, response):
	"""Return logs available in the ./runtime/log/job/jobName directory."""
	try:
		logDir = os.path.join(request.context['envLogPath'], 'job', jobName)
		request.context['payload']['Endpoints'] = []
		for logFile in os.listdir(logDir):
			m = re.search('(.+)\.log', logFile)
			if m:
				endpoint = m.group(1)
				request.context['payload']['Endpoints'].append(endpoint)
	except:
		errorMessage(request, response)

	## end getLogEndpointsForJob
	return cleanPayload(request)


@hugWrapper.get('/log/{jobName}/{endpoint}')
def getLogForJobEndpoint(jobName:text, endpoint:text, request, response):
	"""Return the ./runtime/log/job/jobName/endpointName.log file."""
	try:
		logDir = os.path.join(request.context['envLogPath'], 'job', jobName)
		logFile = '{}.log'.format(endpoint)
		target = os.path.join(logDir, logFile)
		if os.path.isfile(target):
			request.context['payload']['job'] = jobName
			request.context['payload']['endpoint'] = endpoint
			fileContents = None
			with open(target, 'r') as fh:
				## Should we create a generator function for file chunks?
				## Current assumption is that it's not needed...
				fileContents = fh.read()
			request.context['payload']['content'] = fileContents
		else:
			request.context['payload']['errors'].append('File not found: {}'.format(target))
			response.status = HTTP_404

	except:
		errorMessage(request, response)

	## end getLogForJobEndpoint
	return cleanPayload(request)
