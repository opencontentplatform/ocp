"""Shared functions for the API Resource modules.

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Migrated non-url functions here, after spliting the single API
	        Application module into separate modules per API resource.

"""

import sys
import traceback
import os
import json
import uuid
import re
import shutil
from contextlib import suppress
from falcon import HTTP_200, HTTP_202, HTTP_400, HTTP_404, HTTP_500
from sqlalchemy import inspect, distinct, func, select

## From openContentPlatform
from queryProcessing import QueryProcessing
from deleteDbObjects import DeleteDbObject
import realmScope
import utils
import database.schema.platformSchema as platformSchema
import database.connectionPool as tableMapping


def cleanPayload(request):
	"""If no errors were tracked, remove 'errors' key from the final response."""
	if isinstance(request.context['payload'], dict):
		if len(request.context.get('payload', {}).get('errors', [])) <= 0:
			request.context['payload'].pop('errors', None)
	return request.context['payload']


def errorMessage(request, response):
	"""Standard exception block to catch, log, and update the response."""
	stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
	request.context['logger'].error('Exception: {}'.format(str(stacktrace)))
	request.context['payload']['errors'].append('Internal Server Error')
	with suppress(Exception):
		## Not requried, but provides useful data for log/error correlation
		exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
		request.context['payload']['errors'].append(exceptionOnly[0].strip())
	response.status = HTTP_500
	request.context['dbSession'].rollback()
	request.context['dbSession'].close()

	## end errorMessage
	return


def mergeUserAndSource(content, request):
	"""Helper function. Merge user and source context; account for null values."""
	source = content.pop('source', None)
	if source is None or len(source) <= 0:
		source = request.context['apiUser']
	else:
		source = '{}: {}'.format(request.context['apiUser'], source)
	return source


def countGivenClassHelper(request, response, className):
	"""Count instances in given class type, including counts of subtypes.

	Example. Given the following scenario:
	  * 5 base Nodes (not sub-typed)
	  * 25481 Linux (subtyped from Node, through NodeServer, to Linux)
	  * 24529 Windows (similarly subtyped Node-> NodeServer-> Windows)

	./tool/count/Node:
	Standard counts include full counts of all involved types::

		{
		  "Node": 50015,
		  "NodeServer": 50010,
		  "Linux": 25481,
		  "Windows": 24529
		}

	./tool/countExclusive/Node:
	And in contrast, exclusive counts are unique to the lowest subtypes::

		{
		  "Node": 5,
		  "Linux": 25481,
		  "Windows": 24529
		}

	"""
	customHeaders = {}
	utils.getCustomHeaders(request.headers, customHeaders)
	removeEmptyAttributes = customHeaders['removeEmptyAttributes']
	validClassObjects = dict()
	utils.getValidClassObjects(validClassObjects)
	utils.getValidLinksV2(validClassObjects)
	classNameMap = dict()
	for item in validClassObjects:
		classNameMap[item] = validClassObjects[item]['classObject'].__tablename__
	if className not in validClassObjects.keys():
		request.context['logger'].error('Received unrecognized object class_name: {}'.format(className))
		request.context['payload']['errors'].append('Invalid Class Name')
		response.status = HTTP_404
	else:
		tableName = 'data.'+classNameMap[className]
		tableObj= tableMapping.Base.metadata.tables[tableName]
		stment = select([func.count()]).select_from(tableObj)
		val = request.context['dbSession'].execute(stment).first()
		request.context['payload'][className] = val[0]
		if validClassObjects[className]['children']:
			for item in validClassObjects[className]['children']:
				tableName = 'data.'+classNameMap[item]
				tableObj= tableMapping.Base.metadata.tables[tableName]
				stment = select([func.count()]).select_from(tableObj)
				val = request.context['dbSession'].execute(stment).first()
				if not removeEmptyAttributes or val[0] != 0:
					request.context['payload'][item] = val[0]
		request.context['dbSession'].close()

	## end countGivenClassHelper
	return


def countGivenClassExclusiveHelper(request, response, className):
	"""Count instances in given class, excluding instances of any subtypes.

	Example. Given the following scenario:

	  * 5 base Nodes (not sub-typed)
	  * 25481 Linux (subtyped from Node, through NodeServer, to Linux)
	  * 24529 Windows (similarly subtyped Node-> NodeServer-> Windows)

	./tool/countExclusive/Node:
	Exclusive counts return numbers unique to the lowest subtypes::

		{
		  "Node": 5,
		  "Linux": 25481,
		  "Windows": 24529
		}

	./tool/count/Node:
	And in contrast, standard counts includes full counts of all involved types::

		{
		  "Node": 50015,
		  "NodeServer": 50010,
		  "Linux": 25481,
		  "Windows": 24529
		}

	"""
	customHeaders = {}
	utils.getCustomHeaders(request.headers, customHeaders)
	validClassObjects = dict()
	utils.getValidClassObjects(validClassObjects)
	request.context['logger'].info('validClassObjects: {}'.format(validClassObjects))
	request.context['logger'].info('validClassObjects keys: {}'.format(validClassObjects.keys()))
	utils.getValidLinksV2(validClassObjects)
	classNameMap = dict()
	for item in validClassObjects:
		classNameMap[validClassObjects[item]['classObject'].__tablename__] = item
	request.context['logger'].info('classNameMap: {}'.format(classNameMap))
	request.context['logger'].info('classNameMap keys: {}'.format(classNameMap.keys()))
	if className not in validClassObjects.keys():
		request.context['logger'].error('Received unrecognized object class_name: {}'.foramt(className))
		request.context['payload']['errors'].append('Invalid Class Name')
		response.status = HTTP_404
	else:
		ResultSet = request.context['dbSession'].query(func.count(validClassObjects[className]['classObject'].object_id), validClassObjects[className]['classObject'].object_type).group_by(validClassObjects[className]['classObject'].object_type).all()
		for item in ResultSet:
			request.context['payload'][classNameMap[item[1]]] = item[0]
		if not customHeaders['removeEmptyAttributes']:
			for item in validClassObjects[className]['children']:
				if item not in request.context['payload'].keys():
					request.context['payload'][item] = 0

	## end countGivenClassExclusiveHelper
	return


def getServiceJobResultList(request, response, service, dbTable):
	dataHandle = request.context['dbSession'].query(distinct(dbTable.job)).order_by(dbTable.job.desc()).all()
	jobNames = []
	for item in dataHandle:
		jobNames.append(item[0])
	request.context['payload']['Jobs'] = jobNames

	## end getServiceJobResultList
	return


def queryThisContentHelper(request, response, content):
	request.context['logger'].debug('querying the database with the data {}'.format(content))
	request.context['logger'].debug(' ---> headers: {}'.format(request.headers))
	customHeaders = {}
	utils.getCustomHeaders(request.headers, customHeaders)
	if customHeaders.get('contentDeliveryMethod') == 'chunk':
		## This routes the same as if requested through ./query/cache
		storeQueryResults(request, response, customHeaders, content)
	else:
		## Work on it now, inside the runtime of this thread
		queryProcessingInstance = QueryProcessing(request.context['logger'], request.context['dbSession'], content, customHeaders['removePrivateAttributes'], customHeaders['removeEmptyAttributes'], customHeaders['resultsFormat'])
		## Message any query parsing errors back to the client so they
		## can see what to fix (e.g. 'betweendate' time formats)
		if len(queryProcessingInstance.errorList) > 0:
			for msg in queryProcessingInstance.errorList:
				request.context['payload']['errors'].append(msg)
			response.status = HTTP_400
		else:
			listOrDictResult = queryProcessingInstance.runQuery()
			request.context['logger'].debug('listOrDictResult {}'.format(listOrDictResult))
			request.context['payload'] = listOrDictResult
			request.context['logger'].debug('payload charCount {}'.format(len(str(request.context['payload']))))

	## end queryThisContentHelper
	return


def executeStoredQueryHelper(request, response, name):
	dataHandle = request.context['dbSession'].query(platformSchema.QueryDefinition.json_query).filter(platformSchema.QueryDefinition.name == name).first()
	if dataHandle:
		request.context['logger'].debug('query definition: {}'.format(dataHandle[0]))
		content = dataHandle[0]
		try:
			queryThisContentHelper(request, response, content)
		except:
			request.context['payload']['errors'].append('Invalid JSON in query')
			response.status = HTTP_500
	else:
		request.context['payload']['errors'].append('Invalid query name')
		response.status = HTTP_400

	## end executeStoredQueryHelper
	return


def storeQueryResults(request, response, customHeaders, content):
	if customHeaders.get('contentDeliveryMethod') == 'chunk' and customHeaders['resultsFormat'] != 'Flat':
		request.context['logger'].error('Requested chunk delivery method, but resultsFormat was not set to Flat. Nested formats not currently supported.')
		response.status = HTTP_400
		request.context['payload']['errors'].append('Requested chunk delivery method, but resultsFormat was not set to Flat. Nested formats not currently supported.')
	elif customHeaders.get('contentDeliveryMethod') == 'chunk' and customHeaders['resultsFormat'] == 'Flat':
		## Send to the query service
		request.context['logger'].debug('sending to query service... {}'.format(content))
		queryId = uuid.uuid4().hex
		sendToQueryService(request, response, queryId, content, customHeaders)
		request.context['payload']['identifier'] = queryId
		response.status = HTTP_202

	## end storeQueryResults
	return


def sendToQueryService(request, response, queryId, content, headers):
	"""Send a query over to the query service."""
	try:
		kafkaEndpoint = request.context['kafkaEndpoint']
		kafkaTopic = request.context['kafkaQueryTopic']
		request.context['logger'].debug('Trying to establish kafka producer on {}'.format(kafkaEndpoint))
		## Establish a connection
		kafkaProducer = getKafkaProducer(request, response)
		request.context['logger'].debug('Kafka producer established')
		if (content is not None and len(content['objects']) > 0):
			message = {}
			message['queryId'] = queryId
			message['apiUser'] = request.context['apiUser']
			message['headers'] = headers
			message['content'] = content
			request.context['logger'].debug('Sending query content to Kafka: {}'.format(content))
			## Send the message
			kafkaProducer.produce(kafkaTopic, value=json.dumps(message).encode('utf-8'))
			kafkaProducer.poll(0)

		## Close the producer
		if kafkaProducer is not None:
			request.context['logger'].debug('sendToQueryService: stopping kafkaProducer')
			kafkaProducer.flush()
			kafkaProducer = None
	except:
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		request.context['logger'].error('Exception in sendToQueryService: {}'.format(exception))
	request.context['logger'].debug('sendToQueryService completed.')

	## end sendToQueryService
	return


## Helper functions for ConfigGroups, DefaultConfig, and OsPArameters
def removeAndAppendPlatformSettings(request, response, newConfig, configGroupList):
	## This filters the configGroup list & removes any previous entry with
	## a name matching the new name just constructed. The purpose is to
	## allow this job to run multiple times, but to not create duplicate
	## group entries. It uses list comprehension and assigns the result to
	## a slice of the original list. Since the slice is actually the entire
	## list (configGroupList[:]), we're simply mutating the list in place &
	## removing the named entry if it exists.
	configGroupName = newConfig.get('name')
	configGroupList[:] = [x for x in configGroupList if not (x.get('name') == configGroupName)]
	## Now safely add our new configGroup onto the list; this is currently
	## being dropped at the bottom of file to imply lowest priority.
	configGroupList.append(newConfig)
	request.context['logger'].info('Added/updated configGroup name {}'.format(configGroupName))

	## end removeAndAppendPlatformSettings
	return


def modifyConfigGroupFromFileContent(request, response, newFile, newConfig):
	"""Open the current version and append this new configuration.

	Deprecated. Prefer to take current version from the DB; the backup is still
	created on the filesystem though, mainly for ease of troubleshooting.
	"""
	latestContent = []
	## Get the current contents
	with open(newFile) as fp:
		latestContent = json.load(fp)
	removeAndAppendPlatformSettings(request, response, newConfig, latestContent)

	## end modifyConfigGroupFromFileContent
	return latestContent


def rotatePlatformSettingsFiles(request, response, fileName, maxCount=10):
	"""Rotate the configGroup file using a numerical rolling method.

	Arguments:
	  fileName (string) : type_realm.json form (e.g. configGroups_default.json)
	  maxCount (int)    : threashold for number of files to retain
	"""
	try:
		directory = request.context['envContentGatheringSharedConfigGroupPath']
		rotatedFiles = {}
		for thisName in os.listdir(directory):
			m = re.search('{}\.(\d+)'.format(fileName), thisName)
			if m:
				thisNumber = int(m.group(1))
				newFileName = '{}.{}'.format(fileName, thisNumber+1)
				rotatedFiles[thisNumber] = (thisName, newFileName)
		## Go through the list in reverse and rotate files
		for fileNumber in sorted(rotatedFiles.keys(), reverse=True):
			(oldFileName, newFileName) = rotatedFiles[fileNumber]
			oldFile = os.path.join(directory, oldFileName)
			newFile = os.path.join(directory, newFileName)
			if fileNumber < maxCount:
				## First remove the file if it exists (required on Windows)
				if os.path.isfile(newFile):
					os.remove(newFile)
				## Rotate the current file number to the next digit; this means
				## 'configGroups.json.9' now becomes 'configGroups.json.10'
				shutil.move(oldFile, newFile)

		## Now move the current file to a rotated version
		oldFile = os.path.join(directory, fileName)
		newFile = os.path.join(directory, '{}.1'.format(fileName))
		if os.path.exists(oldFile):
			## First remove the file if it exists (required on Windows)
			if os.path.isfile(newFile):
				os.remove(newFile)
			shutil.move(oldFile, newFile)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		request.context['logger'].error('Failure in rotatePlatformSettingsFiles: {}'.format(stacktrace))

	## end rotatePlatformSettingsFiles
	return


def modifyPlatformSettingsFile(request, response, fileName, updatedContent):
	"""Manage file retention on the configGroup.json file, and then update.

	Arguments:
	  fileName (string) : type_realm.json form (e.g. configGroups_default.json)
	  newConfig (dict)  : configGroup contents in JSON format
	"""
	try:
		## Rotates file by number (retaining 10 changes by default)
		rotatePlatformSettingsFiles(request, response, fileName)
		## Save the new config group file
		configGroupsFile = os.path.join(request.context['envContentGatheringSharedConfigGroupPath'], fileName)
		with open(configGroupsFile, 'w') as f:
			f.write(json.dumps(updatedContent, indent=4))
		request.context['logger'].info('Created configGroup file {}'.format(configGroupsFile))

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		request.context['logger'].error('Failure in modifyPlatformSettingsFile: {}'.format(stacktrace))

	## end modifyPlatformSettingsFile
	return


def hasRequiredData(request, response, dataDict, requiredKeys):
	for entry in requiredKeys:
		if entry not in dataDict.keys():
			request.context['payload']['errors'].append('Required key not found in content: {}. This resource requires the following fields in the content section: {}'.format(entry, requiredKeys))
			response.status = HTTP_400
			return False

	## end hasRequiredData
	return True


def parseNetworkScope(request, response, results, realm=None):
	if results:
		scopes = []
		for entry in results:
			thisScope = { col:getattr(entry, col) for col in inspect(entry).mapper.c.keys() }
			## Standard conversions of dates and Decimal types to string
			cleanScope = json.loads(json.dumps(thisScope, default=utils.customJsonDumpsConverter))
			scopes.append(cleanScope)
		request.context['payload']['scopes'] = scopes
	else:
		request.context['payload']['Response'] = 'No NetworkScope defined'

	## end parseNetworkScope
	return


def recalculateRealmScope(request, response, realm):
	## Recalculate the realmScope entry
	networkEntriesForRealm = request.context['dbSession'].query(platformSchema.NetworkScope).filter(platformSchema.NetworkScope.realm == realm).all()
	collapsed = realmScope.updateRealmScope(networkEntriesForRealm, request.context['logger'])
	## And sort the entries so they are easy to browse with the human eye
	count = 0
	strList = []
	for thisNet in sorted(collapsed):
		thisCount = thisNet.num_addresses
		## Put into string form for adding into JSON
		strList.append(str(thisNet))
		request.context['logger'].debug(' ====> IP address count in thisNet [{}] is: {}'.format(thisNet, thisCount))
		count += thisCount
	request.context['logger'].debug('{}'.format('='*50))
	request.context['logger'].debug('totalCount: {}\n\n'.format(count))
	request.context['logger'].debug('IP address count in realm [{}] is: {}'.format(realm, count))
	## Update or insert into RealmScope table
	matchedRealmScope = request.context['dbSession'].query(platformSchema.RealmScope).filter(platformSchema.RealmScope.realm == realm).first()
	if matchedRealmScope:
		request.context['logger'].debug('RealmScope match found for [{}]'.format(realm))
		setattr(matchedRealmScope, 'count', count)
		setattr(matchedRealmScope, 'data', strList)
		request.context['dbSession'].add(matchedRealmScope)
		request.context['dbSession'].commit()
	else:
		newRealmScope = platformSchema.RealmScope(realm=realm, count=count, data=strList)
		request.context['dbSession'].add(newRealmScope)
		request.context['dbSession'].commit()

	## end recalculateRealmScope
	return

def getKafkaProducer(request, response):
	"""Simple wrapper to get the parameters and connect the kafka producer."""
	kafkaEndpoint = request.context['kafkaEndpoint']
	useCertsWithKafka = request.context['useCertificatesWithKafka']
	kafkaCaRootFile = os.path.join(request.context['envConfigPath'], request.context['kafkaCaRootFile'])
	kafkaCertFile = os.path.join(request.context['envConfigPath'], request.context['kafkaCertificateFile'])
	kafkaKeyFile = os.path.join(request.context['envConfigPath'], request.context['kafkaKeyFile'])
	## Connect to the producer
	kafkaProducer = utils.createKafkaProducer(request.context['logger'], kafkaEndpoint, useCertsWithKafka, kafkaCaRootFile, kafkaCertFile, kafkaKeyFile)
	if kafkaProducer is None:
		raise EnvironmentError('Unable to connect a KafkaProducer.')

	## end getKafkaProducer
	return kafkaProducer


def kafkaDeliveryReport(err, msg):
	""" Called once for each message produced to indicate delivery result.
		Triggered by poll() or flush(). """
	## TODO: change over to using a logger
	if err is not None:
		print('Message delivery failed: {}'.format(err))
	else:
		print('Message delivered to {} [{}]'.format(msg.topic(), msg.partition()))


def insertTaskContentHelper(request, response, content):
	"""Send results into Kafka as input for the resultsProcessingClient."""
	if hasRequiredData(request, response, content, ['source', 'objects']):
		## Update the source with the user
		content['source'] = mergeUserAndSource(content, request)
		## Establish a connection
		kafkaProducer = getKafkaProducer(request, response)
		kafkaTopic = request.context['kafkaTopic']
		request.context['logger'].debug('Kafka producer established')
		## Send the message
		request.context['logger'].debug('Sending content to Kafka: {}'.format(content))
		kafkaProducer.produce(kafkaTopic, value=json.dumps(content).encode('utf-8'), callback=kafkaDeliveryReport)
		kafkaProducer.poll(0)
		## Close the producer
		kafkaProducer.flush()
		request.context['logger'].debug('Flushed kafka producer using topic {}'.format(kafkaTopic))
		kafkaProducer = None

	## end insertTaskContentHelper
	return


def deleteTaskContentHelper(request, response, content):
	customHeaders = {}
	utils.getCustomHeaders(request.headers, customHeaders)
	request.context['logger'].debug('Deleting content in ./task request from database')
	deleteDbContent = DeleteDbObject(request.context['logger'], request.context['dbSession'], content)
	if customHeaders['resultsFormat'] == 'Flat':
		deletedObjects = deleteDbContent.queryBeforeDeletion()
	else:
		deletedObjects = deleteDbContent.wrapNested()
	payload = deletedObjects

	## end deleteTaskContentHelper
	return


def searchThisContentHelper(request, response, filterContent, dbTable, countResult, deleteResult):
	## Not using the queryProcessing module to do this; just borrowing
	## the processFilter inside, to share the same filter syntax/parsing
	customHeaders = {}
	utils.getCustomHeaders(request.headers, customHeaders)
	qpInstance = QueryProcessing(request.context['logger'], request.context['dbSession'], {'objects': [], 'links': []}, customHeaders['removePrivateAttributes'], customHeaders['removeEmptyAttributes'], customHeaders['resultsFormat'])
	createdFilterList = qpInstance.processFilter(filterContent, dbTable)
	filterList = []
	## Message any query parsing errors back to the client so they
	## can see what to fix (e.g. 'betweendate' time formats)
	if len(qpInstance.errorList) > 0:
		for msg in qpInstance.errorList:
			request.context['payload']['errors'].append(msg)
		response.status = HTTP_400
	## Only do the following if we didn't hit filter errors
	else:
		if type(createdFilterList) == type(list()):
			filterList.extend(createdFilterList)
		else:
			filterList.append(createdFilterList)
		dataHandle = request.context['dbSession'].query(dbTable).filter(*filterList)
		## Number the results; makes it easier for users to visually parse
		tmpJobResultNumber = 0
		objectList = []
		for item in dataHandle:
			tmpJobResultNumber += 1
			if deleteResult:
				request.context['dbSession'].delete(item)
				request.context['dbSession'].commit()
			elif not countResult:
				request.context['payload'][tmpJobResultNumber] = {col:getattr(item, col) for col in inspect(item).mapper.c.keys()}

		if deleteResult:
			request.context['payload']['Results Removed'] = tmpJobResultNumber
			request.context['logger'].debug('searchThisContentHelper: removed total objects: {}'.format(tmpJobResultNumber))
		elif countResult:
			request.context['payload']['Result Count'] = tmpJobResultNumber

	## end searchThisContentHelper
	return


def getJobResultsFilterHelper(request, response, filterContent, countResult, deleteResult, service):
	"""Gather job results matching the provided filter, then return or delete."""
	dbTable = None
	if service.lower() == 'contentgathering':
		dbTable = platformSchema.ContentGatheringResults
	elif service.lower() == 'universaljob':
		dbTable = platformSchema.UniversalJobResults
	else:
		request.context['payload']['errors'].append('Invalid resource: ./job/{}'.format(service))
		response.status = HTTP_400
	if dbTable is not None:
		searchThisContentHelper(request, response, filterContent, dbTable, countResult, deleteResult)

	## end getJobResultsFilterHelper
	return
