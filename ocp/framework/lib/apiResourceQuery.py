"""Query resource for the Open Content Platform REST API.

This module defines the Application Programming Interface (API) methods for the
/<root>/query endpoint. Available resources follow::

	/<root>/query/this
	/<root>/query/simple
	/<root>/query/simple/{name}
	/<root>/query/endpoint
	/<root>/query/endpoint/{name}
	/<root>/query/config
	/<root>/query/config/simple
	/<root>/query/config/simple/{name}
	/<root>/query/config/inputdriven
	/<root>/query/config/inputdriven/{name}
	/<root>/query/config/endpoint
	/<root>/query/config/endpoint/{name}
	/<root>/query/cache
	/<root>/query/cache/{queryId}
	/<root>/query/cache/{queryId}/{chunkId}

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Sep 15, 2017
	  1.1 : (CS) Added methods, Aug 15, 2019
	  1.2 : (CS) Replaced apiUtils with Falcon middleware, Sept 2, 2019

"""

import sys
import traceback
import os
import json
from hug.types import text, number
from hug.types import json as hugJson
from falcon import HTTP_204, HTTP_400, HTTP_404, HTTP_405, HTTP_500
from sqlalchemy import inspect, and_

## From openContentPlatform
import utils
import database.schema.platformSchema as platformSchema
from apiHugWrapper import hugWrapper
from apiResourceUtils import *
## Load the global settings
import env
globalSettings = utils.loadSettings(os.path.join(env.configPath, "globalSettings.json"))


@hugWrapper.get('/')
def getQueryResources():
	staticPayload = {
		'/query/this' : {
			'methods' : {
				'GET' : 'Run the query definition provided in the payload, and return the results.',
				'DELETE': 'Delete all objects returned from running the ad-hoc query definition provided in the payload.'
			}
		},
		'/query/simple' : {
			'methods' : {
				'GET' : 'Show available resources.'
			}
		},
		'/query/endpoint' : {
			'methods' : {
				'GET' : 'Show available resources.'
			}
		},
		'/query/config' : {
			'methods' : {
				'GET' : 'Show available resources.'
			}
		},
		'/query/cache' : {
			'methods' : {
				'GET' : 'Show available resources.'
			}
		}
	}

	## end getQueryResources
	return staticPayload


@hugWrapper.get('/this')
def queryThisContent(content:hugJson, request, response):
	"""Query OCP for results matching the provided JSON."""
	try:
		countResult = content.pop('count', False)
		queryThisContentHelper(request, response, content)
		## Flat and Nested formats return a dictionary, but Nested-Simple
		## returns a list, so we can't mutate the payload... overwrite.
		payload = request.context['payload'].copy()
		request.context['logger'].info('this payload: {}'.format(payload))
		request.context['logger'].info('payload type: {}'.format(type(payload)))
		if countResult:
			request.context['payload'] = {}
			## If we are just returning a count, need to determine what type
			## of thing to count... dict vs list structure, object in Flat
			## layout, or result set in Nested or Nested-Simple format...
			if isinstance(payload, list):
				request.context['payload']['Result Count'] = len(payload)
			elif isinstance(payload, dict):
				if 'objects' in payload:
					request.context['payload']['Result Count'] = len(payload.get('objects'))
				else:
					request.context['payload']['Result Count'] = len(payload.keys())

	except:
		errorMessage(request, response)

	## end queryThisContent
	return cleanPayload(request)


@hugWrapper.delete('/this')
def deleteExecutingGivenQueries(content:hugJson, request, response):
	"""Remove the results of the add-hoc query defined in the content section.

	TODO - change the way this works.

	Deletes are an incredibly slow ORM operation on inheritance based classes.
	Instead of a blocking, single threaded REST operation... break out into a
	queued delete operation.  Result sizes over something small like 10 objects,
	should be split up and sent back out to kafka to be processed across all
	available ResultProcessing clients.

	Consider something like the cached/chunked functions, where client is given
	an id to use to continue checking back with, to see the progress and when
	the requested delete operation has fully completed.

	Every so often (increasing sleep times 5 sec, 10, 30, 60 - hold at 60?) we
	re-run the query as a GET operation and count the objects... adjust estimate
	on approximate runtime and completion datetime with expected load on current
	number of resultProcessing clients; suggest spinning up more to get done
	in less time.
	"""
	try:
		request.context['payload'].clear()
		queryThisContentHelper(request, response, content)
		## Flat and Nested formats return a dictionary, but Nested-Simple
		## returns a list, so we can't mutate the payload... overwrite.
		dataToDelete = request.context['payload']
		customHeaders = {}
		utils.getCustomHeaders(request.headers, customHeaders)
		if customHeaders['resultsFormat'].lower() == 'flat':
			content = {'objects': dataToDelete.get('objects')}
			deleteTaskContentHelper(request, response, content)
			## Payload was borrowed to store the results; clear before exiting
			request.context['payload'].clear()
		elif customHeaders['resultsFormat'].lower() == 'nested':
			content = dataToDelete
			deleteTaskContentHelper(request, response, content)
			request.context['payload'].clear()
		else:
			request.context['payload'].clear()
			request.context['payload']['errors'].append('Unsupported resultsFormat: {}'.format(customHeaders['resultsFormat']))
	except:
		errorMessage(request, response)

	## end deleteExecutingGivenQueries
	return cleanPayload(request)


@hugWrapper.get('/simple')
def getQueryStoredResources(request, response):
	"""Show available simple query resources."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.QueryDefinition.name).all()
		availableQueries = []
		for item in dataHandle:
			availableQueries.append(item[0])
		resource = '/query/simple/{name}'
		methods = {
			'methods' : {
				'GET' : 'Run the named query (stored previously in the database) and return the results',
				'DELETE': 'Delete all objects returned from running the named query'
				}
		}
		request.context['payload']['Queries'] = availableQueries
		request.context['payload'][resource] = methods

	except:
		errorMessage(request, response)

	## end getQueryStoredResources
	return cleanPayload(request)


@hugWrapper.get('/simple/{name}')
def executeStoredQuery(name:text, request, response):
	"""Run the named query (stored in the database) and return the results."""
	try:
		executeSimpleQueryHelper(request, response, name)
	except:
		errorMessage(request, response)

	## end executeStoredQuery
	return cleanPayload(request)


@hugWrapper.delete('/simple/{name}')
def deleteStoredQueryDataSet(name:text, request, response):
	"""Delete all objects returned from running the named query."""
	try:
		customHeaders = {}
		utils.getCustomHeaders(request.headers, customHeaders)
		executeSimpleQueryHelper(request, response, name)
		dataToDelete = request.context['payload']
		if customHeaders['resultsFormat'].lower() == 'flat':
			content ={'objects': dataToDelete.get('objects')}
		elif customHeaders['resultsFormat'].lower() == 'nested':
			content = dataToDelete
		deleteTaskContentHelper(request, response, content)
		## Payload was borrowed to store the results; clear before exiting
		request.context['payload'].clear()

	except:
		errorMessage(request, response)

	## end deleteStoredQueryDataSet
	return cleanPayload(request)


@hugWrapper.get('/endpoint')
def getQueryEndpointResources(request, response):
	"""Show available endpoint query resources."""
	try:
		dbTable = platformSchema.EndpointQuery
		dataHandle = request.context['dbSession'].query(dbTable.name).all()
		availableQueries = []
		for item in dataHandle:
			availableQueries.append(item[0])
		resource = '/query/endpoint/{name}'
		methods = {
			'methods' : {
				'GET' : 'Run the named endpoint query and return the results'
				}
		}
		request.context['payload']['Queries'] = availableQueries
		request.context['payload'][resource] = methods

	except:
		errorMessage(request, response)

	## end getQueryEndpointResources
	return cleanPayload(request)


@hugWrapper.get('/endpoint/{name}')
def executeEndpointQuery(name:text, request, response):
	"""Run the named endpoint query and return the results."""
	try:
		dbTable = platformSchema.EndpointQuery
		dataHandle = request.context['dbSession'].query(dbTable).filter(dbTable.name == name).first()
		if dataHandle:
			queryDefinition = dataHandle.json_query
			## Pull the realm from the headers, if supplied
			realm = 'default'
			for thisHeader in request.headers:
				if thisHeader.lower() == 'realm':
					## Override when provided
					realm = request.headers.get(thisHeader)
					break
			## Get raw results, before filtering by domain
			endpointList = []
			utils.executeProvidedJsonQuery(request.context['logger'], request.context['dbSession'], queryDefinition, endpointList)
			## Now use the realm utility to filter the results, ensure a related
			## IP address is included in the requested realm before adding
			realmUtil = utils.RealmUtility(request.context['dbSession'])
			#request.context['logger'].debug('executeEndpointQuery: Endpoint list size before realm ({}) compare: {}'.format(realm, len(endpointList)))
			endpointList[:] = [x for x in endpointList if (realmUtil.isIpInRealm(x.get('data', {}).get('ipaddress', x.get('data', {}).get('address')), realm))]
			#request.context['logger'].debug('executeEndpointQuery: Endpoint list size after realm compare: {}'.format(len(endpointList)))
			request.context['logger'].debug('endpointList {}'.format(endpointList))
			request.context['payload'] = endpointList
			request.context['logger'].debug('payload charCount {}'.format(len(str(request.context['payload']))))

		else:
			request.context['payload']['errors'].append('Invalid query name')
			response.status = HTTP_400
	except:
		errorMessage(request, response)

	## end executeEndpointQuery
	return cleanPayload(request)


@hugWrapper.get('/config')
def getQueryConfigResources(request, response):
	"""Get available queries and methods for ./query/config."""
	staticPayload = {}
	staticPayload['/query/config/simple'] = {
		'methods' : {
			'GET' : 'Return the names of all saved simple queries.',
			'POST': 'Create a new simple query definition.',
			'DELETE' : 'Delete all defined simple query definitions.'
		}
	}
	staticPayload['/query/config/simple/{name}'] = {
		'methods' : {
			'GET' : 'Return the definition for the named simple query.',
			'DELETE' : 'Removes stored definition for the named simple query.',
			'PUT' :'Updates the definition for the named simple query.'
		}
	}
	staticPayload['/query/config/inputdriven'] = {
		'methods' : {
			'GET' : 'Return the name of all saved input-driven queries.',
			'POST': 'Create a new input-driven query definition.',
			'DELETE' : 'Delete all defined input-driven query definitions.'
		}
	}
	staticPayload['/query/config/inputdriven/{name}'] = {
		'methods' : {
			'GET' : 'Return the definition for the named input-driven query.',
			'DELETE' : 'Removes stored definition for the named input-driven query.',
			'PUT' :'Updates the definition for the named input-driven query.'
		}
	}
	staticPayload['/query/config/endpoint'] = {
		'methods' : {
			'GET' : 'Return the names of all saved endpoint queries.',
			'POST': 'Create a new endpoint query definition.',
			'DELETE' : 'Delete all defined endpoint query definitions.'
		}
	}
	staticPayload['/query/config/endpoint/{name}'] = {
		'methods' : {
			'GET' : 'Return the definition for the named endpoint query.',
			'DELETE' : 'Removes stored definition for the named endpoint query.',
			'PUT' :'Updates the definition for the named endpoint query.'
		}
	}

	## end getQueryConfigResources
	return staticPayload


@hugWrapper.get('/config/simple')
def getQueryConfigSimpleResources(request, response):
	"""Get available queries and methods for ./query/config/simple."""
	try:
		dbTable = platformSchema.QueryDefinition
		dataHandle = request.context['dbSession'].query(dbTable.name).order_by(dbTable.name.asc()).all()
		availableQueries = []
		for item in dataHandle:
			availableQueries.append(item[0])
		request.context['payload']['Queries'] = availableQueries

	except:
		errorMessage(request, response)

	## end getQueryConfigSimpleResources
	return cleanPayload(request)


@hugWrapper.post('/config/simple')
def postSimpleQuery(content:hugJson, request, response):
	"""Posts the query to both the database and the file system."""
	try:
		if hasRequiredData(request, response, content, ['name', 'source', 'json_query']):
			dataHandle = request.context['dbSession'].query(platformSchema.QueryDefinition).filter(platformSchema.QueryDefinition.name==content['name']).first()
			if dataHandle is not None:
				request.context['payload']['errors'].append('Cannot insert {name}; query by that name already exists'.format(name=content['name']))
				response.status = HTTP_405
			else:
				if not content['json_query'] or type(content['json_query']) != type(dict()):
					request.context['payload']['errors'].append('Expected JSON for \'json_query\' field.')
					response.status = HTTP_400
				elif content['name'] == '' or content['name'] == None:
					request.context['payload']['errors'].append('\'name\' field cannot be empty.')
					response.status = HTTP_400
				else:
					## Data looks good
					source = mergeUserAndSource(content, request)
					content['object_created_by'] = source
					dataHandle = platformSchema.QueryDefinition(**content)
					request.context['dbSession'].add(dataHandle)
					request.context['dbSession'].commit()
					apiQueryPath = request.context['envApiQueryPath']
					if not os.path.exists(apiQueryPath):
						os.makedirs(apiQueryPath)
					with open(os.path.join(apiQueryPath, content['name']+'.json'), 'w') as fh:
						json.dump(content['json_query'], fh)
					request.context['logger'].debug('Successfully created the json query in the path: {}'.format(apiQueryPath))
					request.context['payload']['Response'] = 'Success'

	except:
		errorMessage(request, response)

	## end postSimpleQuery
	return cleanPayload(request)


@hugWrapper.delete('/config/simple')
def deleteAllSimpleQueries(request, response):
	"""Delete all stored simple queries from the database and filesystem."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.QueryDefinition).all()
		deletedQueries = dict()
		apiQueryPath = request.context['envApiQueryPath']
		for item in dataHandle:
			deletedQueries[item.object_id] = { col:getattr(item, col) for col in inspect(item).mapper.c.keys() if col != 'object_id'}
			fileToRemove = os.path.join(apiQueryPath, item.name + '.json')
			if os.path.isfile(fileToRemove):
				os.remove(fileToRemove)
			request.context['dbSession'].delete(item)
		request.context['dbSession'].commit()
		request.context['payload']['Success'] = deletedQueries

	except:
		errorMessage(request, response)

	## end deleteAllSimpleQueries
	return cleanPayload(request)


@hugWrapper.get('/config/simple/{queryName}')
def getSpecificSimpleQuery(queryName:text, request, response):
	"""Get the content of the named query"""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.QueryDefinition).filter(platformSchema.QueryDefinition.name==queryName).first()
		if dataHandle:
			for col in inspect(dataHandle).mapper.c.keys():
				request.context['payload'][col] = getattr(dataHandle, col)
		else:
			request.context['payload']['errors'].append('No query exists with name {queryName!r}'.format(queryName=queryName))
			response.status = HTTP_404

	except:
		errorMessage(request, response)

	## end getSpecificSimpleQuery
	return cleanPayload(request)


@hugWrapper.put('/config/simple/{queryName}')
def updateSpecificSimpleQuery(queryName:text, content:hugJson, request, response):
	"""Update named query with the provided JSON"""
	try:
		if hasRequiredData(request, response, content, ['source', 'json_query']):
			dataHandle = request.context['dbSession'].query(platformSchema.QueryDefinition).filter(platformSchema.QueryDefinition.name==queryName).first()
			if dataHandle is None:
				request.context['payload']['errors'].append('No query exists with name {queryName!r}'.format(queryName=queryName))
				response.status = HTTP_404
			else:
				tempObjectId = dataHandle.object_id
				## Set the source
				source = mergeUserAndSource(content, request)
				content['object_updated_by'] = source
				definedColumns = [col for col in inspect(platformSchema.QueryDefinition).mapper.c.keys() if col not in ['name', 'object_id', 'time_created', 'object_created_by', 'time_updated', 'object_updated_by']]
				request.context['logger'].debug('Printing the required column {}'.format(definedColumns))
				if any(col in content.keys() for col in definedColumns):
					content['object_id']= tempObjectId
					dataHandle = platformSchema.QueryDefinition(**content)
					try:
						apiQueryPath = request.context['envApiQueryPath']
						if not os.path.exists(apiQueryPath):
							os.makedirs(apiQueryPath)
						dataHandle = request.context['dbSession'].merge(dataHandle)
						fileToRemove = os.path.join(apiQueryPath, queryName + '.json')
						request.context['dbSession'].commit()
						if 'json_query' in content.keys():
							if os.path.isfile(fileToRemove):
								os.remove(fileToRemove)
							with open(os.path.join(fileToRemove),'w') as fh:
								json.dump(content['json_query'], fh)
						request.context['payload']['Response'] = 'Updated the query : {name}'.format(name=queryName)
					except KeyError:
						request.context['payload']['errors'].append('Invalid data, key does not exist for {queryName!r} 1'.format(queryName=queryName))
						response.status = HTTP_400
				else:
					request.context['payload']['errors'].append('Invalid data, key does not exist for {queryName!r}'.format(queryName=queryName))
					response.status = HTTP_400

	except:
		errorMessage(request, response)

	## end updateSpecificSimpleQuery
	return cleanPayload(request)


@hugWrapper.delete('/config/simple/{queryName}')
def deleteSpecificSimpleQuery(queryName:text, request, response):
	"""Delete QueryDefinition for results matching the provided JSON."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.QueryDefinition).filter(platformSchema.QueryDefinition.name==queryName).first()
		if dataHandle is None:
			request.context['payload']['errors'].append('No query exist with name {queryName!r}'.format(queryName=queryName))
			response.status = HTTP_404
		else:
			apiQueryPath = request.context['envApiQueryPath']
			fileToRemove = os.path.join(apiQueryPath, queryName +'.json')
			request.context['dbSession'].delete(dataHandle)
			if os.path.isfile(fileToRemove):
				os.remove(fileToRemove)
			request.context['dbSession'].commit()
			request.context['payload']['Response'] = 'Deleted the query: {queryName}'.format(queryName=queryName)

	except:
		errorMessage(request, response)

	## end deleteSpecificSimpleQuery
	return cleanPayload(request)


@hugWrapper.get('/config/inputdriven')
def getAvailableInputDrivenQueries(request, response):
	"""Get available input-driven query names."""
	try:
		dbTable = platformSchema.InputDrivenQueryDefinition
		dataHandle = request.context['dbSession'].query(dbTable.name).order_by(dbTable.name.asc()).all()
		availableQueries = []
		for item in dataHandle:
			availableQueries.append(item[0])
		request.context['payload']['Queries'] = availableQueries
		request.context['logger'].debug(' ---> payload: {}'.format(request.context['payload']))

	except:
		errorMessage(request, response)

	## end getAvailableQueries
	return cleanPayload(request)


@hugWrapper.post('/config/inputdriven')
def postInputDrivenQuery(content:hugJson, request, response):
	"""Posts the input driven query to both the database and the file system."""
	try:
		if hasRequiredData(request, response, content, ['name', 'source', 'json_query']):
			dataHandle = request.context['dbSession'].query(platformSchema.InputDrivenQueryDefinition).filter(platformSchema.InputDrivenQueryDefinition.name==content['name']).first()
			if dataHandle is not None:
				request.context['payload']['errors'].append('Cannot insert {name}, already exist'.format(name=content['name']))
				response.status = HTTP_405
			else:
				if not content['json_query'] or type(content['json_query']) != type(dict()):
					request.context['payload']['errors'].append('Expected JSON for \'json_query\' field.')
					response.status = HTTP_400
				elif content['name'] == '' or content['name'] == None:
					request.context['payload']['errors'].append('\'name\' field cannot be empty.')
					response.status = HTTP_400
				else:
					## Data looks good
					source = mergeUserAndSource(content, request)
					content['object_created_by'] = source
					dataHandle = platformSchema.InputDrivenQueryDefinition(**content)
					request.context['dbSession'].add(dataHandle)
					request.context['dbSession'].commit()
					apiQueryPath = request.context['envApiQueryPath']
					if not os.path.exists(apiQueryPath):
						os.makedirs(apiQueryPath)
					with open(os.path.join(apiQueryPath, content['name']+'.json'), 'w') as fh:
						json.dump(content['json_query'], fh)
					request.context['logger'].debug('Successfully created the json query in the path: {}'.format(apiQueryPath))
					request.context['payload']['Response'] = 'Success'

	except:
		errorMessage(request, response)

	## end postInputDrivenQuery
	return cleanPayload(request)


@hugWrapper.delete('/config/inputdriven')
def deleteInputDrivenQuery(request, response):
	"""Delete all stored queries from the database and filesystem."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.InputDrivenQueryDefinition).all()
		deletedQueries = dict()
		apiQueryPath = request.context['envApiQueryPath']
		for item in dataHandle:
			deletedQueries[item.object_id] = { col:getattr(item, col) for col in inspect(item).mapper.c.keys() if col != 'object_id'}
			fileToRemove = os.path.join(apiQueryPath, item.name + '.json')
			if os.path.isfile(fileToRemove):
				os.remove(fileToRemove)
			request.context['dbSession'].delete(item)
		request.context['dbSession'].commit()
		request.context['payload']['Success'] = deletedQueries

	except:
		errorMessage(request, response)

	## end deleteInputDrivenQuery
	return cleanPayload(request)


@hugWrapper.get('/config/inputdriven/{queryName}')
def getSpecificInputDrivenQuery(queryName:text, request, response):
	"""Get the content of the named input driven query"""
	try:
		dbTable = platformSchema.InputDrivenQueryDefinition
		dataHandle = request.context['dbSession'].query(dbTable).filter(dbTable.name==queryName).first()
		if dataHandle:
			for col in inspect(dataHandle).mapper.c.keys():
				request.context['payload'][col] = getattr(dataHandle, col)
		else:
			request.context['payload']['errors'].append('No inputdrivenquery exists with name {queryName!r}'.format(queryName=queryName))
			response.status = HTTP_404

	except:
		errorMessage(request, response)

	## end getSpecificInputDrivenQuery
	return cleanPayload(request)


@hugWrapper.put('/config/inputdriven/{queryName}')
def updateSpecificInputDrivenQuery(queryName:text, content:hugJson, request, response):
	"""Update named inputdrivenquery with the provided JSON"""
	try:
		if hasRequiredData(request, response, content, ['source', 'json_query']):
			dataHandle = request.context['dbSession'].query(platformSchema.InputDrivenQueryDefinition).filter(platformSchema.InputDrivenQueryDefinition.name==queryName).first()
			if dataHandle is None:
				request.context['payload']['errors'].append('No query exists with name {queryName!r}'.format(queryName=queryName))
				response.status = HTTP_404
			else:
				tempObjectId = dataHandle.object_id
				## Set the source
				source = mergeUserAndSource(content, request)
				content['object_updated_by'] = source
				definedColumns = [col for col in inspect(platformSchema.InputDrivenQueryDefinition).mapper.c.keys() if col not in ['name', 'object_id', 'time_created', 'object_created_by', 'time_updated', 'object_updated_by']]
				request.context['logger'].debug('Printing the required column {}'.format(definedColumns))
				if any(col in content.keys() for col in definedColumns):
					content['object_id']= tempObjectId
					dataHandle = platformSchema.InputDrivenQueryDefinition(**content)
					try:
						apiQueryPath = request.context['envApiQueryPath']
						if not os.path.exists(apiQueryPath):
							os.makedirs(apiQueryPath)
						dataHandle = request.context['dbSession'].merge(dataHandle)
						fileToRemove = os.path.join(apiQueryPath, queryName + '.json')
						request.context['dbSession'].commit()
						if 'json_query' in content.keys():
							if os.path.isfile(fileToRemove):
								os.remove(fileToRemove)
							with open(os.path.join(fileToRemove),'w') as fh:
								json.dump(content['json_query'], fh)
						request.context['payload']['Response'] = 'Updated the inputdrivenquery: {name}'.format(name=queryName)
					except KeyError:
						request.context['payload']['errors'].append('Invalid data, key does not exist for {queryName!r} 1'.format(queryName=queryName))
						response.status = HTTP_400
				else:
					request.context['payload']['errors'].append('Invalid data, key does not exist for {queryName!r}'.format(queryName=queryName))
					response.status = HTTP_400

	except:
		errorMessage(request, response)

	## end updateSpecificInputDrivenQuery
	return cleanPayload(request)


@hugWrapper.delete('/config/inputdriven/{queryName}')
def deleteSpecificInputDrivenQuery(queryName:text, request, response):
	"""Delete InputDrivenQueryDefinition for results matching the provided JSON."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.InputDrivenQueryDefinition).filter(platformSchema.InputDrivenQueryDefinition.name==queryName).first()
		if dataHandle is None:
			request.context['payload']['errors'].append('No query exists with name {queryName!r}'.format(queryName=queryName))
			response.status = HTTP_404
		else:
			apiQueryPath = request.context['envApiQueryPath']
			fileToRemove = os.path.join(apiQueryPath, queryName + '.json')
			request.context['dbSession'].delete(dataHandle)
			if os.path.isfile(fileToRemove):
				os.remove(fileToRemove)
			request.context['dbSession'].commit()
			request.context['payload']['Response'] = 'Deleted the inputdrivenquery : {queryName}'.format(queryName=queryName)

	except:
		errorMessage(request, response)

	## end deleteSpecificInputDrivenQuery
	return cleanPayload(request)


@hugWrapper.get('/config/endpoint')
def getQueryConfigEndpointResources(request, response):
	"""Get available queries and methods for ./query/config/endpoint."""
	try:
		dbTable = platformSchema.EndpointQuery
		dataHandle = request.context['dbSession'].query(dbTable.name).order_by(dbTable.name.asc()).all()
		availableQueries = []
		for item in dataHandle:
			availableQueries.append(item[0])
		request.context['payload']['Queries'] = availableQueries

	except:
		errorMessage(request, response)

	## end getQueryConfigEndpointResources
	return cleanPayload(request)


@hugWrapper.post('/config/endpoint')
def postEndpointQuery(content:hugJson, request, response):
	"""Posts the endpoint query to the database."""
	try:
		if hasRequiredData(request, response, content, ['name', 'source', 'json_query']):
			dataHandle = request.context['dbSession'].query(platformSchema.EndpointQuery).filter(platformSchema.EndpointQuery.name==content['name']).first()
			if dataHandle is not None:
				request.context['payload']['errors'].append('Cannot insert {name}; query by that name already exists'.format(name=content['name']))
				response.status = HTTP_405
			else:
				if not content['json_query'] or type(content['json_query']) != type(dict()):
					request.context['payload']['errors'].append('Expected JSON for \'json_query\' field.')
					response.status = HTTP_400
				elif content['name'] == '' or content['name'] == None:
					request.context['payload']['errors'].append('\'name\' field cannot be empty.')
					response.status = HTTP_400
				else:
					## Data looks good
					source = mergeUserAndSource(content, request)
					content['object_created_by'] = source
					dataHandle = platformSchema.EndpointQuery(**content)
					request.context['dbSession'].add(dataHandle)
					request.context['dbSession'].commit()
					request.context['payload']['Response'] = 'Success'

	except:
		errorMessage(request, response)

	## end postEndpointQuery
	return cleanPayload(request)


@hugWrapper.delete('/config/endpoint')
def deleteAllEndpointQueries(request, response):
	"""Delete all stored endpoint queries."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.EndpointQuery).all()
		deletedQueries = dict()
		for item in dataHandle:
			deletedQueries[item.object_id] = { col:getattr(item, col) for col in inspect(item).mapper.c.keys() if col != 'object_id'}
			request.context['dbSession'].delete(item)
		request.context['dbSession'].commit()
		request.context['payload']['Success'] = deletedQueries

	except:
		errorMessage(request, response)

	## end deleteAllEndpointQueries
	return cleanPayload(request)


@hugWrapper.get('/config/endpoint/{queryName}')
def getSpecificEndpointQuery(queryName:text, request, response):
	"""Get the content of the named endpoint query"""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.EndpointQuery).filter(platformSchema.EndpointQuery.name==queryName).first()
		if dataHandle:
			for col in inspect(dataHandle).mapper.c.keys():
				request.context['payload'][col] = getattr(dataHandle, col)
		else:
			request.context['payload']['errors'].append('No query exists with name {queryName!r}'.format(queryName=queryName))
			response.status = HTTP_404

	except:
		errorMessage(request, response)

	## end getSpecificEndpointQuery
	return cleanPayload(request)


@hugWrapper.put('/config/endpoint/{queryName}')
def updateSpecificEndpointQuery(queryName:text, content:hugJson, request, response):
	"""Update named query with the provided JSON"""
	try:
		if hasRequiredData(request, response, content, ['source', 'json_query']):
			dataHandle = request.context['dbSession'].query(platformSchema.EndpointQuery).filter(platformSchema.EndpointQuery.name==queryName).first()
			if dataHandle is None:
				request.context['payload']['errors'].append('No query exists with name {queryName!r}'.format(queryName=queryName))
				response.status = HTTP_404
			else:
				tempObjectId = dataHandle.object_id
				## Set the source
				source = mergeUserAndSource(content, request)
				content['object_updated_by'] = source
				definedColumns = [col for col in inspect(platformSchema.EndpointQuery).mapper.c.keys() if col not in ['name', 'object_id', 'time_created', 'object_created_by', 'time_updated', 'object_updated_by']]
				request.context['logger'].debug('Printing the required column {}'.format(definedColumns))
				if any(col in content.keys() for col in definedColumns):
					content['object_id']= tempObjectId
					content['name'] = queryName
					dataHandle = platformSchema.EndpointQuery(**content)
					try:
						apiQueryPath = request.context['envApiQueryPath']
						if not os.path.exists(apiQueryPath):
							os.makedirs(apiQueryPath)
						dataHandle = request.context['dbSession'].merge(dataHandle)
						fileToRemove = os.path.join(apiQueryPath, queryName + '.json')
						request.context['dbSession'].commit()
						if 'json_query' in content.keys():
							if os.path.isfile(fileToRemove):
								os.remove(fileToRemove)
							with open(os.path.join(fileToRemove),'w') as fh:
								json.dump(content['json_query'], fh)
						request.context['payload']['Response'] = 'Updated the query : {name}'.format(name=queryName)
					except KeyError:
						request.context['payload']['errors'].append('Invalid data, key does not exist for {queryName!r} 1'.format(queryName=queryName))
						response.status = HTTP_400
				else:
					request.context['payload']['errors'].append('Invalid data, key does not exist for {queryName!r}'.format(queryName=queryName))
					response.status = HTTP_400

	except:
		errorMessage(request, response)

	## end updateSpecificEndpointQuery
	return cleanPayload(request)


@hugWrapper.delete('/config/endpoint/{queryName}')
def deleteSpecificEndpointQuery(queryName:text, request, response):
	"""Delete endpoint query with the specified name."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.EndpointQuery).filter(platformSchema.EndpointQuery.name==queryName).first()
		if dataHandle is None:
			request.context['payload']['errors'].append('No query exist with name {queryName!r}'.format(queryName=queryName))
			response.status = HTTP_404
		else:
			request.context['dbSession'].delete(dataHandle)
			request.context['dbSession'].commit()
			request.context['payload']['Response'] = 'Deleted the query: {queryName}'.format(queryName=queryName)

	except:
		errorMessage(request, response)

	## end deleteSpecificEndpointQuery
	return cleanPayload(request)


@hugWrapper.post('/cache')
def createStoredQueryResult(content:hugJson, request, response):
	"""Query and store results matching the provided JSON."""
	try:
		request.context['logger'].debug('querying the database with the data {}'.format(content))
		request.context['logger'].debug(' ---> headers: {}'.format(request.headers))
		customHeaders = {}
		utils.getCustomHeaders(request.headers, customHeaders)
		storeQueryResults(request, response, customHeaders, content)

	except:
		errorMessage(request, response)

	## end createStoredQueryResult
	return cleanPayload(request)


@hugWrapper.get('/cache')
def getSavedQueryListing(request, response):
	"""Report all stored query results sent through ./query/cache."""
	try:
		dbTable = platformSchema.CachedQuery
		results = request.context['dbSession'].query(dbTable)
		if results:
			cachedResults = []
			for entry in results:
				thisEntry = {
					'object_id' : entry.object_id,
					'chunk_count' : entry.chunk_count,
					'time_started' : entry.time_started
				}
				cachedResults.append(thisEntry)
			request.context['payload']['entries'] = cachedResults
			request.context['payload']['/query/cache'] = {
				'methods' : {
					'GET' : 'Report all stored queries.',
					'POST' : 'Query and store new results matching the provided JSON'
				}
			}
			request.context['payload']['/query/cache/{queryId}'] = {
				'methods' : {
					'GET' : 'Get details for a specific cache result set from database',
					'DELETE': 'Remove cached chunked query result from database'
				}
			}
			request.context['payload']['/query/cache/{queryId}/{chunkId}'] = {
				'methods' : {
					'GET' : 'Get a specified chunk result from the cached query'
				}
			}

	except:
		errorMessage(request, response)

	## end getSavedQueryListing
	return cleanPayload(request)


@hugWrapper.get('/cache/{queryId}/')
def getInfoOnSavedQuery(queryId:text, request, response):
	"""Get details for a specific cache result set specified chunk result from database."""
	try:
		dbTable = platformSchema.CachedQuery
		matchedEntry = request.context['dbSession'].query(dbTable).filter(dbTable.object_id == queryId).first()
		if not matchedEntry:
			request.context['logger'].error('Cached object not found with ID {}.'.format(queryId))
			response.status = HTTP_204
			request.context['payload']['errors'].append('Cached object not found with ID {}.'.format(queryId))
		else:
			request.context['logger'].debug('Found entry with ID {}'.format(queryId))
			request.context['payload']['object_id'] = matchedEntry.object_id
			request.context['payload']['object_created_by'] = matchedEntry.object_created_by
			request.context['payload']['chunk_count'] = matchedEntry.chunk_count
			request.context['payload']['original_size_in_kb'] = matchedEntry.original_size_in_kb
			request.context['payload']['time_started'] = matchedEntry.time_started
			request.context['payload']['time_finished'] = matchedEntry.time_finished
			request.context['payload']['time_elapsed'] = matchedEntry.time_elapsed

	except:
		errorMessage(request, response)

	## end getInfoOnSavedQuery
	return cleanPayload(request)


@hugWrapper.get('/cache/{queryId}/{chunkId}/')
def getSavedQueryResultChunk(queryId:text, chunkId:number, request, response):
	"""Get a specified chunk result from database."""
	try:
		dbTable = platformSchema.CachedQueryChunk
		matchedEntry = request.context['dbSession'].query(dbTable).filter(and_(dbTable.object_id == queryId, dbTable.chunk_id == chunkId)).first()
		if not matchedEntry:
			request.context['logger'].error('Error returning CachedQuery chunk; object not found with ID {} and chunk {}'.format(queryId, chunkId))
			response.status = HTTP_204
			request.context['payload']['errors'].append('No cached query found with query ID {} and chunk number {} that ID.'.format(queryId, chunkId))
		else:
			request.context['logger'].info('Found entry with ID {} and chunk {}'.format(queryId, chunkId))
			request.context['payload'] = matchedEntry.data

	except:
		errorMessage(request, response)

	## end getSavedQueryResultChunk
	return cleanPayload(request)


@hugWrapper.delete('/cache/{queryId}/')
def deleteSavedQueryByID(queryId:text, request, response):
	"""Remove cached chunked query result from database."""
	try:
		dbTable = platformSchema.CachedQuery
		matchedEntry = request.context['dbSession'].query(dbTable).filter(dbTable.object_id == queryId).first()
		if not matchedEntry:
			request.context['logger'].error('Error deleting CachedQuery entry; object_id not found: {}'.format(queryId))
			response.status = HTTP_204
			request.context['payload']['errors'].append('No cached query found by that ID.')
		else:
			request.context['logger'].info('Found entry: {}'.format(matchedEntry))
			queryId = matchedEntry.object_id
			chunkCount = matchedEntry.chunk_count
			request.context['logger'].info('Found old query ID {} with count {}'.format(queryId, chunkCount))
			## Remove chunk details
			chunkTable = platformSchema.CachedQueryChunk
			oldChunks = request.context['dbSession'].query(chunkTable).filter(chunkTable.object_id == queryId).all()
			for chunk in oldChunks:
				thisId = chunk.object_id
				thisChunkId = chunk.chunk_id
				request.context['logger'].info('Removing chunk query {} chunk {}'.format(thisId, thisChunkId))
				request.context['dbSession'].delete(chunk)
				request.context['dbSession'].commit()
			## Now remove the top level entry
			request.context['dbSession'].delete(matchedEntry)
			request.context['dbSession'].commit()

	except:
		errorMessage(request, response)

	## end deleteSavedQueryByID
	return cleanPayload(request)
