"""Data resource for the Open Content Platform REST API.

This module defines the Application Programming Interface (API) methods for the
/<root>/data endpoint. Available resources follow::

	/<root>/data/{className}
	/<root>/data/{className}/{object_id}

"""

import sys
import traceback
import os
from hug.types import text
from hug.types import json as hugJson
from falcon import HTTP_400, HTTP_404

## From openContentPlatform
import utils
import database.connectionPool as tableMapping
from apiHugWrapper import hugWrapper
from apiResourceUtils import *


@hugWrapper.get('/')
def getData(request, response):
	"""Show available data resources."""
	staticPayload = {}
	try:
		BaseObjectClass = tableMapping.BaseObject
		tempdict = dict()
		tempdict['classObject'] = BaseObjectClass
		tempdict['children'] = [i.__name__ for i in BaseObjectClass.__subclasses__()]
		utils.classDict(tempdict, BaseObjectClass)
		tempdict.pop('classObject')
		tempdict.pop('children')
		staticPayload = {
			'Available classes:' : tempdict.keys(),
			'/data/{class}' : {
				'methods' : {
					'GET' : 'Report all entries in specified resource class.',
					'POST' : 'Insert entry in specified resource class.',
					'DELETE' : 'Remove all entries in specified resource class.'
				}
			},
			'/data/{class}/{id}' : {
				'methods' : {
					'GET' : 'Report entry with specified object id from the class resource.',
					'PUT' : 'Update entry with specified object id from the class resource.',
					'DELETE' : 'Remove entry with specified object id from the class resource.'
				}
			},
			'/data/schema/{class}' : {
				'methods' : {
					'GET' : 'Provide specified class definition from the data schema.'
				}
			}
		}
		del tempdict
	except:
		errorMessage(request, response)

	## end getData
	return staticPayload


@hugWrapper.get('/{className}/')
def getDataForClass(className:text, request, response):
	"""Report all data resources by given class."""
	try:
			content = dict()
			content['objects']  = []
			objectDictionary = dict()
			objectDictionary['label'] = className
			objectDictionary['attributes'] = []
			objectDictionary['class_name'] = className
			objectDictionary['minimum'] = ''
			objectDictionary['maximum'] = ''
			objectDictionary['filter'] = []
			objectDictionary['linchpin'] = 'true'
			content['objects'].append(objectDictionary)
			content['links'] = []
			## Override since we only want to work with flat here
			request.headers['resultsFormat'] = 'Flat'
			queryThisContentHelper(request, response, content)

	except:
		errorMessage(request, response)

	## end getDataForClass
	return cleanPayload(request)


@hugWrapper.delete('/{className}/')
def deleteDataForClass(className:text, request, response):
	"""Delete all instances of given class."""
	try:
		BaseObjectClass = tableMapping.BaseObject
		tempdict = dict()
		tempdict['classObject'] = BaseObjectClass
		tempdict['children'] = [i.__name__ for i in BaseObjectClass.__subclasses__()]
		utils.classDict(tempdict, BaseObjectClass)
		if className in tempdict.keys():
			dbHandle = request.context['dbSession'].query(tempdict[className]['classObject']).all()
			for obj in dbHandle:
				request.context['dbSession'].delete(obj)
				request.context['dbSession'].commit()
				del obj
			request.context['payload']['Success'] = 'Deleted all objects from {}'.format(className)
		else:
			request.context['payload']['errors'].append('Class Name : {} does not exist.'.format(className))
			response.status = HTTP_404
		del tempdict

	except:
		errorMessage(request, response)

	## end deleteDataForClass
	return cleanPayload(request)


@hugWrapper.post('/{className}/')
def insertDataForClass(className:text, content:hugJson, request, response):
	"""Insert instances of given class."""
	try:
		request.context['logger'].debug('insertDataForClass: content: {}'.format(content))
		if hasRequiredData(request, response, content, ['source', 'data']):
			BaseObjectClass = tableMapping.BaseObject
			classDictionary = dict()
			classDictionary['classObject'] = BaseObjectClass
			classDictionary['children'] = [i.__name__ for i in BaseObjectClass.__subclasses__()]
			utils.classDict(classDictionary, BaseObjectClass)
			if className in classDictionary.keys():
				source = content.pop('source', None)
				objectDictionary = dict()
				perObject = dict()
				perObject['class_name'] = className
				perObject['identifier'] = 1
				perObject['data'] = content.get('data', {})
				objectDictionary['objects'] = []
				objectDictionary['objects'].append(perObject)
				objectDictionary['source'] = source
				objectDictionary['links'] = []
				insertTaskContentHelper(request, response, objectDictionary)
			else:
				request.context['payload']['errors'].append('Class name {} does not exist'.format(className))
				response.status = HTTP_404

	except:
		errorMessage(request, response)

	## end insertDataForClass
	return cleanPayload(request)


@hugWrapper.get('/{className}/{object_id}')
def getDataForClassObjectId(className:text, object_id:text, request, response):
	"""Report on a specific instance of a class."""
	try:
		BaseObjectClass = tableMapping.BaseObject
		tempdict = dict()
		tempdict['classObject'] = BaseObjectClass
		tempdict['children'] = [i.__name__ for i in BaseObjectClass.__subclasses__()]
		utils.classDict(tempdict, BaseObjectClass)
		if className in tempdict.keys():
			if utils.uuidCheck(object_id):
				## use db handle code
				## have to process this in either flat or in nested form
				myInstance = request.context['dbSession'].query(tempdict[className]['classObject']).filter(tempdict[className]['classObject'].object_id==object_id).first()
				if myInstance:
					## There is an entry in the DB with a valid object_id
					content = dict()
					content['objects']  = []
					objectDictionary = dict()
					objectDictionary['label'] = className
					objectDictionary['attributes'] = []
					objectDictionary['class_name'] = className
					objectDictionary['minimum'] = ''
					objectDictionary['maximum'] = ''
					objectDictionary['filter'] = [{
					'negation': 'False',
					'condition': {
						'attribute': 'object_id',
						'operator': 'equal',
						'value': object_id
						}
					}]
					objectDictionary['linchpin'] = 'true'
					content['objects'].append(objectDictionary)
					content['links'] = []
					queryThisContentHelper(request, response, content)

				else:
					request.context['payload']['errors'].append('Object_id {} does not exist in the class {}'.format(object_id, className))
					response.status = HTTP_404
			else:
				request.context['payload']['errors'].append('Expected 32-bit hex for id')
				response.status = HTTP_400
		else:
			request.context['payload']['errors'].append('Invalid Class Name')
			response.status = HTTP_400
		del tempdict

	except:
		errorMessage(request, response)

	## end getDataForClassObjectId
	return cleanPayload(request)


@hugWrapper.put('/{className}/{object_id}')
def putDataForClassObjectId(className:text, object_id:text, content:hugJson, request, response):
	"""Update a specific instance of a class."""
	try:
		request.context['logger'].debug('putDataForClassObjectId: received content: {}'.format(content))
		if hasRequiredData(request, response, content, ['source', 'data']):
			BaseObjectClass = tableMapping.BaseObject
			tempdict = dict()
			tempdict['classObject'] = BaseObjectClass
			tempdict['children'] = [i.__name__ for i in BaseObjectClass.__subclasses__()]
			utils.classDict(tempdict, BaseObjectClass)
			if className in tempdict.keys():
				if utils.uuidCheck(object_id):
					myInstance = request.context['dbSession'].query(tempdict[className]['classObject']).filter(tempdict[className]['classObject'].object_id==object_id).first()
					if myInstance:
						source = content.pop('source', None)
						objectDictionary = dict()
						perObject = dict()
						perObject['class_name'] = className
						perObject['identifier'] = object_id
						perObject['data'] = content.get('data', {})
						objectDictionary['objects'] = []
						objectDictionary['objects'].append(perObject)
						objectDictionary['source'] = source
						objectDictionary['links'] = []
						insertTaskContentHelper(request, response, objectDictionary)
					else:
						request.context['payload']['errors'].append('Object_id {object_id} doesn\'t exist in the class {className}'.format(object_id=object_id, className=className))
						response.status = HTTP_404
				else:
					request.context['payload']['errors'].append('Expected 32-bit hex for id')
					response.status = HTTP_400
			else:
				request.context['payload']['errors'].append('Invalid Class Name')
				response.status = HTTP_400
			del tempdict

	except:
		errorMessage(request, response)

	## end putDataForClassObjectId
	return cleanPayload(request)


@hugWrapper.delete('/{className}/{object_id}')
def deleteDataForClassObjectId(className:text, object_id:text, request, response):
	"""Report on a specifically requested object."""
	try:
		BaseObjectClass = tableMapping.BaseObject
		tempdict = dict()
		tempdict['classObject'] = BaseObjectClass
		tempdict['children'] = [i.__name__ for i in BaseObjectClass.__subclasses__()]
		utils.classDict(tempdict, BaseObjectClass)
		if className in tempdict.keys():
			if utils.uuidCheck(object_id):
				myInstance = request.context['dbSession'].query(tempdict[className]['classObject']).filter(tempdict[className]['classObject'].object_id==object_id).first()
				if myInstance:
					request.context['dbSession'].delete(myInstance)
					request.context['dbSession'].commit()
					request.context['payload']['Response'] = 'Removed entry with object_id {} from class {}'.format(object_id, className)
				else:
					request.context['payload']['errors'].append('Object_id {} does not exist in the class {}'.format(object_id, className))
					response.status = HTTP_404
			else:
				request.context['payload']['errors'].append('Expected 32-bit hex for id')
				response.status = HTTP_400
		else:
			request.context['payload']['errors'].append('Invalid Class Name')
			response.status = HTTP_400
		del tempdict

	except:
		errorMessage(request, response)

	## end deleteDataForClassObjectId
	return cleanPayload(request)


@hugWrapper.get('/schema/{className}')
def getDataSchemaClassDefinition(className, request, response):
	"""Report class definition."""
	staticPayload = {}
	try:
		request.context['logger'].debug('getSchemaDataClassDefinition: className: {}'.format(className))
		table = eval('tableMapping.{}'.format(className))
		classTable = table.__tablename__
		staticPayload["class"] = className
		staticPayload["table"] = classTable
		#staticPayload["args"] = str(table.__table_args__)
		## Leave constraints in list form
		#staticPayload["constraints"] = str(table._constraints)
		staticPayload["constraints"] = table._constraints
		attrs = {}
		for entry in inspect(table).mapper.c:
			mapperTable = str(entry.table)
			value = { "type": str(entry.type) }
			if mapperTable == classTable or mapperTable.endswith('.{}'.format(classTable)):
				value["inherited"] = False
			else:
				value["inherited"] = True
			value["table"] = str(entry.table)
			attrs[str(entry.name)] = value
		staticPayload["attributes"] = attrs
		request.context['logger'].debug(' staticPayload ==> {}'.format(staticPayload))
	except:
		errorMessage(request, response)

	## end getDataSchemaClassDefinition
	return staticPayload
