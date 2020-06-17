"""Archive snapshots of logical application models.

Functions:
  startJob : standard job entry point

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Jul 23, 2018
  1.1 : (CS) Changed from calling DB queries directly (when running on server
        via the ServerSideService), to using the API (when running on a client
        via the UniversalJobService). Sep 3, 2019

"""
import sys
import traceback
import os
import re
import json

## From openContentPlatform
import modelCompare
from utils import compareJsonResults, customJsonDumpsConverter
import utilities

## From this package
import logicalModelUtils


def getCurrentMetaData(runtime, modelElementId, metaData, currentMetaData):
	"""Build a list of all current meta-data objects for this particular model."""
	## Collect meta data objects for this app; metaData is dict of dict format
	for resultId,resultSet in metaData.items():
		thisElementId = resultSet.get('tier4_id')
		if (thisElementId == modelElementId):
			currentMetaData[resultId] = resultSet

	## end getCurrentMetaData
	return


def processModels(runtime, timestampId, archivedModels, modelsList, metaData):
	"""Loop through and process each model."""
	for result in modelsList:
		try:
			## Since ResultsFormat of the result is Nested-Simple, each of the
			## linchpin results (application) an independent topology result.
			source = '{}.{}'.format(runtime.packageName, runtime.jobName)
			modelObjectId = result.get('identifier')
			modelType = result.get('class_name')
			modelLabel = result.get('label')
			modelCaption = result.get('data').get('caption')
			modelElementId = result.get('data').get('element_id')
			modelData = {}
			modelData['object_id'] = modelObjectId
			modelData['object_type'] = modelType
			modelData['caption'] = modelCaption
			modelData['source'] = source
			modelSnapshotData = {}
			modelSnapshotData['object_id'] = modelObjectId
			modelSnapshotData['timestamp_id'] = timestampId
			modelSnapshotData['data'] = result
			modelSnapshotData['source'] = source
			modelMetaDataSnapshotData = {}
			modelMetaDataSnapshotData['object_id'] = modelObjectId
			modelMetaDataSnapshotData['timestamp_id'] = timestampId
			modelMetaDataSnapshotData['source'] = source
			## Build a list of all current meta-data objects for this particular model
			currentMetaData = {}
			getCurrentMetaData(runtime, modelElementId, metaData, currentMetaData)
			modelMetaDataSnapshotData['meta_data'] = currentMetaData
			## Cleanup this model result; prep work for comparison operation
			runtime.logger.report('processModels: looking at {result!r}', result=result)

			## Insert the model if it doesn't exist
			if modelObjectId not in archivedModels:
				runtime.logger.report(' Inserting new model for id {object_id!r}', object_id=modelObjectId)
				## On initial insert, set data and meta_data without comparing
				modelData['data'] = result
				modelData['meta_data'] = currentMetaData
				## Insert the model and snapshot objects
				addObject(runtime, 'model', modelData)
				addObject(runtime, 'modelSnapshot', modelSnapshotData)
				addObject(runtime, 'modelMetadataSnapshot', modelMetaDataSnapshotData)

			## The model has been tracked before
			else:
				thisModel = getArchivedModelDetails(runtime, modelObjectId)
				runtime.logger.report(' Model id {object_id!r} exists; check for changes', object_id=modelObjectId)
				## Compare 'result' with the current 'data' in modelData. If it
				## is different, update the 'data' in modelData to represent the
				## current version, and insert a modelSnapshot.
				previousModelResult = thisModel.get('data')
				changeList = []
				modelCompare.jsonCompare(previousModelResult, result, changeList, ignore_value_of_keys=['time_updated', 'time_gathered', 'object_created_by', 'object_updated_by'])
				modelResultHasNotChanged = True
				if len(changeList) > 0:
					modelResultHasNotChanged = False
					modelSnapshotData['change_list'] = changeList

				previousModelMetaData = thisModel.get('meta_data')
				modelMetaDataHasNotChanged = compareJsonResults(previousModelMetaData, currentMetaData)

				## Yuck on all the double negatives! May change the (not NotChanged)
				## syntax, but right now it's not 'broke'... no need to 'fix'.
				if ((not modelResultHasNotChanged) or (not modelMetaDataHasNotChanged)):
					if (not modelResultHasNotChanged):
						runtime.logger.report('  Model id {object_id!r} RESULT   has changed... insert snapshots for timestamp id {timestampId!r}', object_id=modelObjectId, timestampId=timestampId)
						## Create a new modelSnapshot for historical retention
						addObject(runtime, 'modelSnapshot', modelSnapshotData)
						## Override the model data to the current result
						thisModel['data'] = result
					else:
						## Remove attribute if we don't need to update it
						thisModel.pop('data', None)
					if (not modelMetaDataHasNotChanged):
						runtime.logger.report('  Model id {object_id!r} METADATA has changed... insert snapshots for timestamp id {timestampId!r}', object_id=modelObjectId, timestampId=timestampId)
						## Create a new modelSnapshot for historical retention
						addObject(runtime, 'modelMetadataSnapshot', modelMetaDataSnapshotData)
						## Override the model metadata to the current result
						thisModel['meta_data'] = currentMetaData
					else:
						## Remove attribute if we don't need to update it
						thisModel.pop('meta_data', None)
					## Update the model
					thisModel['source'] = source
					updateObject(runtime, 'model', modelObjectId, thisModel)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Failure in processModels: {stacktrace!r}', stacktrace=stacktrace)

	## end processModels
	return


def addObject(runtime, objectType, objectData):
	content = {'content' : objectData}
	apiResponse = utilities.getApiResult(runtime, 'archive/{}'.format(objectType), 'post', customPayload=content)
	runtime.logger.report('model response: {apiResponse!r}', apiResponse=apiResponse)
	responseAsJson = json.loads(apiResponse.text)
	if str(apiResponse.status_code) != '200':
		raise EnvironmentError('Unable to add {}. Response: {}'.format(objectType, responseAsJson))

	## end addObject
	return


def updateObject(runtime, objectType, objectId, objectData):
	content = {'content' : objectData}
	apiResponse = utilities.getApiResult(runtime, 'archive/{}/{}'.format(objectType, objectId), 'put', customPayload=content)
	runtime.logger.report('model response: {apiResponse!r}', apiResponse=apiResponse)
	responseAsJson = json.loads(apiResponse.text)
	if str(apiResponse.status_code) != '200':
		raise EnvironmentError('Unable to add {}. Response: {}'.format(objectType, responseAsJson))

	## end updateObject
	return


def getArchivedModelDetails(runtime, modelId):
	"""Gather details on the provided archived model."""
	apiResponse = utilities.getApiResult(runtime, 'archive/model/{}'.format(modelId), 'get')
	runtime.logger.report('model response: {apiResponse!r}', apiResponse=apiResponse)
	responseAsJson = json.loads(apiResponse.text)
	## Sample response:
	## {
	## 	"d2c002c6da8f4a4089b8662a41694230": {
	## 		"object_id": "d2c002c6da8f4a4089b8662a41694230",
	## 		"object_type": "BusinessApplication",
	## 		"time_stamp": "2018-11-04 11:29:06",
	## 		"caption": "IT Discovery Machine",
	## 		"data" : {...}
	## 		"meta_data" : {...}
	## 	}
	## }
	thisModel = responseAsJson.get(modelId)
	## Remove informational attributes that we won't want to update
	thisModel.pop('time_stamp', None)
	thisModel.pop('object_type', None)
	thisModel.pop('caption', None)

	## end getArchivedModelDetails
	return thisModel


def getArchivedModels(runtime, archivedModels):
	"""Gather all the currently archived model entries."""
	apiResponse = utilities.getApiResult(runtime, 'archive/model', 'get')
	runtime.logger.report('model response: {apiResponse!r}', apiResponse=apiResponse)
	responseAsJson = json.loads(apiResponse.text)
	## Sample entry in the list of models:
	## {
	## 	"object_id": "d2c002c6da8f4a4089b8662a41694230",
	## 	"object_type": "BusinessApplication",
	## 	"caption": "IT Discovery Machine"
	## },
	for entry in responseAsJson.get('Models'):
		modelId = entry.get('object_id')
		modelName = entry.get('caption')
		if modelId is not None:
			archivedModels[modelId] = modelName

	## end getArchivedModels
	return


def createTimestamp(runtime):
	"""Create a new archived snapshot timestamp."""
	content = {'content' : {'source': runtime.jobName}}
	apiResponse = utilities.getApiResult(runtime, 'archive/modelSnapshotTimestamp', 'post', customPayload=content)
	runtime.logger.report('modelSnapshotTimestamp response: {apiResponse!r}', apiResponse=apiResponse)
	responseAsJson = json.loads(apiResponse.text)
	timestampId = responseAsJson.get('object_id')
	if str(apiResponse.status_code) != '200' or timestampId is None:
		raise EnvironmentError('Unable to create an archived snapshot timestamp. Response: {}'.format(responseAsJson))

	## end createTimestamp
	return timestampId


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		## Get results from the metadata query named in the parameters
		metaDataQuery = runtime.parameters.get('metaDataQuery')
		metaDataResults = logicalModelUtils.getMetaDataResults(runtime, metaDataQuery)
		if len(metaDataResults) <= 0:
			raise EnvironmentError('Job archive_application: No metaData found in database; nothing to do.')
		runtime.logger.report('metaDataResults: {metaDataResults!r}', metaDataResults=metaDataResults)

		## Get results from the modelQuery that is named in the parameters
		modelQuery = runtime.parameters.get('modelQuery')
		modelsList = logicalModelUtils.getQueryResults(runtime, modelQuery, 'Nested-Simple')
		if len(modelsList) <= 0:
			runtime.logger.report('Job archive_application: No models found; nothing to archive.')

		else:
			## Get all currently archived models
			archivedModels = {}
			getArchivedModels(runtime, archivedModels)

			## Create a snapshot timestamp entry and get the object_id back
			timestampId = createTimestamp(runtime)
			runtime.logger.report(' ---> timestamp ID: {timestampId!r}', timestampId=timestampId)

			## Start the work
			processModels(runtime, timestampId, archivedModels, modelsList, metaDataResults)

		## Update the runtime status to success
		if runtime.getStatus() == 'UNKNOWN':
			runtime.status(1)

	except:
		runtime.setError(__name__)

	## end startJob
	return
