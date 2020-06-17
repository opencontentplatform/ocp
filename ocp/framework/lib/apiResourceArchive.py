"""Archive resource for the IT Discovery Machine REST API.

This module defines the Application Programming Interface (API) methods for the
/<root>/archive endpoint. Available resources follow::

	/<root>/archive/model
	/<root>/archive/model/{object_id}
	/<root>/archive/modelSnapshot
	/<root>/archive/modelSnapshot/{object_id}
	/<root>/archive/modelMetadataSnapshot
	/<root>/archive/modelMetadataSnapshot/{object_id}
	/<root>/archive/modelSnapshotTimestamp

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Sep 15, 2017
	  1.1 : (CS) Replaced apiUtils with Falcon middleware, Sep 2, 2019
	  1.2 : (CS) Added methods, Sep 3, 2019

"""

import sys
import traceback
import os
import json
from hug.types import text
from hug.types import json as hugJson
from falcon import HTTP_404
from sqlalchemy import inspect

## From openContentPlatform
import utils
import database.schema.archiveSchema as archiveSchema
from apiHugWrapper import hugWrapper
from apiResourceUtils import *
## Add openContentPlatform directories onto the sys path
import env
globalSettings = utils.loadSettings(os.path.join(env.configPath, "globalSettings.json"))


@hugWrapper.get('/')
def getArchive(request, response):
	"""Show available archive resources."""
	staticPayload = {}
	try:
		availableClasses = ['model', 'modelSnapshot', 'modelMetadataSnapshot']
		staticPayload['Resources'] = availableClasses
		staticPayload['/archive/{resource}'] = {
			'methods' : {
				'GET' : 'Report all entries from the specified resource',
				'POST' : 'Insert new entry in the specified resource.'
			}
		}
		staticPayload['/archive/{resource}/{id}'] = {
			'methods' : {
				'GET' : 'Report all specified resource entries containing provided id'
			}
		}
	except:
		errorMessage(request, response)

	## end getArchive
	return staticPayload


@hugWrapper.get('/model')
def getArchiveModelIds(request, response):
	"""Report all archive model resources."""
	try:
		dbTable = archiveSchema.Model
		dataHandle = request.context['dbSession'].query(dbTable).all()
		availableModels = []
		for item in dataHandle:
			thisModel = {}
			thisModel['object_id'] = item.object_id
			thisModel['object_type'] = item.object_type
			thisModel['caption'] = item.caption
			availableModels.append(thisModel)
		request.context['payload']['Models'] = availableModels

	except:
		errorMessage(request, response)

	## end getArchiveModelIds
	return cleanPayload(request)


@hugWrapper.post('/model')
def createArchiveModel(content:hugJson, request, response):
	"""Creates a new archived model entry."""
	try:
		if hasRequiredData(request, response, content, ['source', 'object_id', 'object_type', 'data', 'meta_data']):
			source = mergeUserAndSource(content, request)
			content['object_created_by'] = source
			request.context['logger'].info('createArchiveModel: content: {}'.format(content))
			dbTable = archiveSchema.Model
			dataHandle = dbTable(**content)
			request.context['dbSession'].add(dataHandle)
			request.context['dbSession'].commit()
			request.context['payload']['Response'] = 'Successfully inserted new archived model.'

	except:
		errorMessage(request, response)

	## end createArchiveModel
	return cleanPayload(request)


@hugWrapper.get('/model/{object_id}')
def getArchiveForModelObjectId(object_id:text, request, response):
	"""Report all archived models."""
	try:
		dbTable = archiveSchema.Model
		dataHandle = request.context['dbSession'].query(dbTable).filter(dbTable.object_id == object_id).all()
		for item in dataHandle:
			request.context['payload'][item.object_id] = {col:getattr(item, col) for col in inspect(item).mapper.c.keys()}
		## Standard conversions of dates to string
		request.context['payload'] = json.loads(json.dumps(request.context['payload'], default=utils.customJsonDumpsConverter))

	except:
		errorMessage(request, response)

	## end getArchiveForModelObjectId
	return cleanPayload(request)


@hugWrapper.put('/model/{object_id}')
def updateSpecificModelObject(object_id:text, content:hugJson, request, response):
	"""Update model containing the specified object_id, with the provided JSON."""
	try:
		if hasRequiredData(request, response, content, ['source']):
			dbTable = archiveSchema.Model
			dataHandle = request.context['dbSession'].query(dbTable).filter(dbTable.object_id==object_id).first()
			if dataHandle is None:
				request.context['payload']['errors'].append('No archived model exists with ID {}, in order to update. Use POST on ./archive/model to create.'.format(object_id))
				response.status = HTTP_404
			else:
				source = mergeUserAndSource(content, request)
				content['object_created_by'] = source
				if 'data' in content.keys():
					## Override the model data to the current result
					setattr(dataHandle, 'data', content['data'])
				if 'meta_data' in content.keys():
					## Override the model metadata to the current result
					setattr(dataHandle, 'meta_data', content['meta_data'])
				## Update the model
				dataHandle = request.context['dbSession'].merge(dataHandle)
				request.context['dbSession'].commit()
				request.context['payload']['Response'] = 'Updated archived model {}'.format(object_id)
				request.context['logger'].debug('Updated archived model {}'.format(object_id))

	except:
		errorMessage(request, response)

	## end updateSpecificConfigGroups
	return cleanPayload(request)


@hugWrapper.delete('/model/{object_id}')
def deleteModelObjects(object_id:text, content:hugJson, request, response):
	"""Delete all objects associated with this model."""
	try:
		if hasRequiredData(request, response, content, ['source']):
			dbTable = archiveSchema.Model
			dataHandle = request.context['dbSession'].query(dbTable).filter(dbTable.object_id==object_id).first()
			if dataHandle is None:
				request.context['payload']['errors'].append('No archived model exists with ID {}.'.format(object_id))
				response.status = HTTP_404
			else:
				## See if there are any ModelSnapshots or ModelMetaDataSnapshots.
				## If so, they have to go before we can remove the model, or it
				## will violate foreign key constraints on those tables.
				for dbTable in [archiveSchema.ModelSnapshot, archiveSchema.ModelMetaDataSnapshot]:
					results = request.context['dbSession'].query(dbTable).filter(dbTable.object_id == object_id).all()
					if results:
						for obj in results:
							request.context['logger'].debug('Removing archived object {} with ID {}...'.format(type(obj), obj.object_id))
							request.context['dbSession'].delete(obj)
							request.context['dbSession'].commit()
				## Now delete the initial model
				dbTable = archiveSchema.Model
				targetModel = request.context['dbSession'].query(dbTable).filter(dbTable.object_id==object_id).first()
				request.context['dbSession'].delete(targetModel)
				request.context['dbSession'].commit()
				request.context['payload']['Response'] = 'Deleted the model: {}'.format(object_id)

	except:
		errorMessage(request, response)

	## end deleteModelObjects
	return cleanPayload(request)


@hugWrapper.get('/modelSnapshot')
def getArchiveModelSnapshotIds(request, response):
	"""Report all archived model snapshots."""
	try:
		dbTable = archiveSchema.Model
		dataHandle = request.context['dbSession'].query(dbTable.object_id).all()
		availableIDs = []
		for item in dataHandle:
			availableIDs.append(item[0])
		request.context['payload']['Ids'] = availableIDs

	except:
		errorMessage(request, response)

	## end getArchiveModelSnapshotIds
	return cleanPayload(request)


@hugWrapper.post('/modelSnapshot')
def createArchiveModelSnapshot(content:hugJson, request, response):
	"""Creates a new archived model entry."""
	try:
		if hasRequiredData(request, response, content, ['source', 'object_id', 'timestamp_id', 'data']):
			source = mergeUserAndSource(content, request)
			content['object_created_by'] = source
			request.context['logger'].info('createArchiveModelSnapshot: content: {}'.format(content))
			dbTable = archiveSchema.ModelSnapshot
			dataHandle = dbTable(**content)
			request.context['dbSession'].add(dataHandle)
			request.context['dbSession'].commit()
			request.context['payload']['Response'] = 'Successfully inserted new archived model snapshot.'

	except:
		errorMessage(request, response)

	## end createArchiveModelSnapshot
	return cleanPayload(request)


@hugWrapper.get('/modelSnapshot/{object_id}')
def getArchiveSnapshotsByModelId(object_id:text, request, response):
	"""Report archived model snapshots with provided id."""
	try:
		dbTable = archiveSchema.ModelSnapshot
		dataHandle = request.context['dbSession'].query(dbTable).filter(dbTable.object_id == object_id).all()
		for item in dataHandle:
			request.context['payload'][item.timestamp_id] = {col:getattr(item, col) for col in inspect(item).mapper.c.keys()}

		## Standard conversions of dates to string
		request.context['payload'] = json.loads(json.dumps(request.context['payload'], default=utils.customJsonDumpsConverter))

	except:
		errorMessage(request, response)

	## end getArchiveSnapshotsByModelId
	return cleanPayload(request)


@hugWrapper.get('/modelMetadataSnapshot')
def getArchiveModelMetaDataSnapshotIds(request, response):
	"""Report all archived metadata snapshots."""
	try:
		dbTable = archiveSchema.ModelMetaDataSnapshot
		dataHandle = request.context['dbSession'].query(dbTable.object_id).all()
		availableIDs = []
		for item in dataHandle:
			availableIDs.append(item[0])
		request.context['payload']['Ids'] = availableIDs

	except:
		errorMessage(request, response)

	## end getArchiveModelMetaDataSnapshotIds
	return cleanPayload(request)


@hugWrapper.post('/modelMetadataSnapshot')
def createArchiveModelMetaDataSnapshot(content:hugJson, request, response):
	"""Creates a new archived model entry."""
	try:
		if hasRequiredData(request, response, content, ['source', 'object_id', 'timestamp_id', 'meta_data']):
			source = mergeUserAndSource(content, request)
			content['object_created_by'] = source
			request.context['logger'].info('createArchiveModelMetaDataSnapshot: content: {}'.format(content))
			dbTable = archiveSchema.ModelMetaDataSnapshot
			dataHandle = dbTable(**content)
			request.context['dbSession'].add(dataHandle)
			request.context['dbSession'].commit()
			request.context['payload']['Response'] = 'Successfully inserted new archived model metadata snapshot.'

	except:
		errorMessage(request, response)

	## end createArchiveModelSnapshot
	return cleanPayload(request)


@hugWrapper.get('/modelMetadataSnapshot/{object_id}')
def getArchiveMetaDataSnapshotsByModelId(object_id:text, request, response):
	"""Report archived model metadata snapshots with provided model id."""
	try:
		dbTable = archiveSchema.ModelMetaDataSnapshot
		dataHandle = request.context['dbSession'].query(dbTable).filter(dbTable.object_id == object_id).all()
		for item in dataHandle:
			request.context['payload'][item.timestamp_id] = {col:getattr(item, col) for col in inspect(item).mapper.c.keys()}

		## Standard conversions of dates to string
		request.context['payload'] = json.loads(json.dumps(request.context['payload'], default=utils.customJsonDumpsConverter))

	except:
		errorMessage(request, response)

	## end getArchiveMetaDataSnapshotsByModelId
	return cleanPayload(request)


@hugWrapper.post('/modelSnapshotTimestamp')
def createModelSnapshotTimestamp(content:hugJson, request, response):
	"""Create a new archived snapshot timestamp."""
	try:
		if hasRequiredData(request, response, content, ['source']):
			## Data looks good
			source = mergeUserAndSource(content, request)
			content['object_created_by'] = source
			dbTable = archiveSchema.ModelSnapshotTimestamp
			dataHandle = dbTable()
			request.context['dbSession'].add(dataHandle)
			request.context['dbSession'].commit()
			timestampId = getattr(dataHandle, 'object_id')
			request.context['logger'].debug('createModelSnapshotTimestamp: created timestamp: {}'.format(timestampId))
			request.context['payload']['object_id'] = timestampId

	except:
		errorMessage(request, response)

	## end createModelSnapshotTimestamp
	return cleanPayload(request)
