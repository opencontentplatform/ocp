"""Tool resource for the Open Content Platform REST API.

This module defines the Application Programming Interface (API) methods for the
/<root>/tool endpoint. Available resources follow::

	/<root>/tool/{className}
	/<root>/tool/count
	/<root>/tool/count/{className}
	/<root>/tool/countExclusive
	/<root>/tool/countExclusive/{className}
	/<root>/tool/link/{object_id}
	/<root>/tool/mergeObject

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors: Madhusudan Sridharan (MS)
	Version info:
	  1.0 : (CS) Created Sep 15, 2017
	  1.1 : (CS) Replaced apiUtils with Falcon middleware, Sep 2, 2019
	  1.2 : (CS) Extending internal mergeObject through API, Sep 5, 2019

"""

import sys
import traceback
import os
from hug.types import text, number
from falcon import HTTP_400, HTTP_404
from sqlalchemy import inspect

## From openContentPlatform
import utils
import database.connectionPool as tableMapping
from resultProcessing import ResultProcessing
from objectCache import ObjectCache
from results import Results
from apiHugWrapper import hugWrapper
from apiResourceUtils import *
## Load the global settings
import env
globalSettings = utils.loadSettings(os.path.join(env.configPath, "globalSettings.json"))


@hugWrapper.get('/')
def getTool():
	"""Show available tool resources."""
	staticPayload = {'Available Resources' : {
		'/tool/count' : {
			'methods' : {
				'GET' : 'Gives a count for all classes/links in the data schema. Parent classes include counts from all relative child classes.'
			}
		},
		'/tool/count/{ClassName_or_LinkName}' : {
			'methods' : {
				'GET' : 'Gives the count of instances in the given class, along with any subtypes. Parent classes include counts from all relative child classes.'
			}
		},
		'/tool/countExclusive' : {
			'methods' : {
				'GET' : 'Give the count of all classes/links in the data schema, excluding counts from any child classes.'
			}
		},
		'/tool/countExclusive/{ClassName_or_LinkName}' : {
			'methods' : {
				'GET' : 'Give the count of instances in the given class, excluding counts from any child classes.'
			}
		},
		'/tool/link/{id}' : {
			'methods' : {
				'GET' : 'Return all objects linked to the object specified by its id.'
			}
		}
	}}

	## end getTool
	return staticPayload


@hugWrapper.get('/count')
def countAllClasses(request, response):
	"""Count instances of all class types, including counts of their subtypes."""
	try:
		countGivenClassHelper(request, response, 'BaseObject')
		countGivenClassHelper(request, response, 'BaseLink')
	except:
		errorMessage(request, response)

	## end countAllClasses
	return cleanPayload(request)


@hugWrapper.get('/count/{className}')
def countGivenClass(className:text, request, response):
	"""Count instances in given class type, including counts of subtypes."""
	try:
		countGivenClassHelper(request, response, className)
	except:
		errorMessage(request, response)

	## end countGivenClass
	return cleanPayload(request)


@hugWrapper.get('/countExclusive')
def countExclusive(request, response):
	"""Count instances of all classes, excluding instances of subtypes."""
	try:
		countGivenClassExclusiveHelper(request, response, 'BaseObject')
		countGivenClassExclusiveHelper(request, response, 'BaseLink')
	except:
		errorMessage(request, response)

	## end countExclusive
	return cleanPayload(request)


@hugWrapper.get('/countExclusive/{className}')
def countGivenClassExclusive(className:text, request, response):
	"""Count instances in given class, excluding instances of subtypes."""
	try:
		countGivenClassExclusiveHelper(request, response, className)
	except:
		errorMessage(request, response)

	## end countGivenClassExclusive
	return cleanPayload(request)


@hugWrapper.get('/link/{object_id}')
def getLinkedObjects(object_id:text, request, response):
	"""Return all objects linked to the object specified by its id."""
	try:
		if utils.uuidCheck(object_id):
			dataHandle = request.context['dbSession'].query(tableMapping.BaseObject).filter(tableMapping.BaseObject.object_id == object_id).first()
			if dataHandle:
				customHeaders = {}
				utils.getCustomHeaders(request.headers, customHeaders)
				resultJson = Results('tool/link/{object_id}'.format(object_id=object_id), True)
				weakLinkObjects = set()
				StrongLinkObjects = set()
				onceFlag = False
				for relation in ['weak_first_objects', 'weak_second_objects']:
					entry = set(getattr(dataHandle, relation))
					weakLinkObjects = weakLinkObjects.union(entry)
				for relation in ['strong_first_objects', 'strong_second_objects']:
					if getattr(inspect(dataHandle).mapper.relationships, relation).uselist:
						entry = set(getattr(dataHandle, relation))
						StrongLinkObjects = StrongLinkObjects.union(entry)
					else:
						if getattr(dataHandle, relation) is not None:
							entry = getattr(dataHandle, relation)
							StrongLinkObjects.add(entry)
				objects = set()
				objectList = []
				for item in StrongLinkObjects:
					objects.add(item.strong_second_object)
					objects.add(item.strong_first_object)
				for item in weakLinkObjects:
					objects.add(item.weak_second_object)
					objects.add(item.weak_first_object)
				if dataHandle not in objects:
					objects.add(dataHandle)

				for obj in objects:
					objectId = getattr(obj, 'object_id')
					data = None
					if customHeaders['removePrivateAttributes']:
						data = {col : getattr(obj, col) for col in inspect(obj).mapper.c.keys() if col not in ['container', 'object_type', 'reference_id']}
					else:
						data = {col : getattr(obj, col) for col in inspect(obj).mapper.c.keys() }
					identifier, exists = resultJson.addObject(inspect(obj).mapper.class_.__name__, uniqueId=objectId, **data)
					objectList.append(((obj, inspect(obj).mapper.class_.__name__), identifier))
				objectsDict = dict(objectList)
				for item in StrongLinkObjects:
					first_id = objectsDict[(item.strong_first_object, inspect(item.strong_first_object).mapper.class_.__name__)]
					second_id = objectsDict[(item.strong_second_object, inspect(item.strong_second_object).mapper.class_.__name__)]
					resultJson.addLink(inspect(item).mapper.class_.__name__, firstId=first_id, secondId=second_id)

				## Recreating weak link connection
				for item in weakLinkObjects:
					if item.weak_first_object is dataHandle:
						first_id = objectsDict[(item.weak_first_object, inspect(item.weak_first_object).mapper.class_.__name__)]
						resultJson.addLink(inspect(item).mapper.class_.__name__, firstId=first_id, secondId=item.weak_second_object.object_id)
					if item.weak_second_object is dataHandle:
						second_id = objectsDict[(item.weak_second_object, item.weak_second_object.__class__.__name__)]
						resultJson.addLink(inspect(item).mapper.class_.__name__, firstId=item.weak_first_object.object_id, secondId=second_id)
				tempJson = resultJson.getJson()
				## pop off temp_weak_links
				tempJson.pop('temp_weak_links', None)
				request.context['payload'] = tempJson
				resultJson.clearJson()
				del resultJson

			else:
				request.context['payload']['errors'].append('The provided object_id {} does not exist in the database.'.format(object_id))
				response.status = HTTP_404
		else:
			request.context['payload']['errors'].append('Expected 32-bit hex for id')
			response.status = HTTP_400
	except:
		errorMessage(request, response)

	## end getLinkedObjects
	return cleanPayload(request)


@hugWrapper.post('/mergeObject')
def referenceAndMergeObject(weakId:text, strongId:text, request, response):
	"""Merge a weak object into a strong object, includes attributes and links."""
	try:
		objectCache = ObjectCache(request.context['logger'], apiUtils.dbClient)
		resultProcessingUtility = ResultProcessing(request.context['logger'], apiUtils.dbClient, cacheData=objectCache.constraintCache, referenceCacheData=objectCache.referenceCache)
		resultProcessingUtility.referenceAndMergeObjectById(weakId, strongId)
		request.context['logger'].debug('Sucessfully merged weakId {} to strongId {}.'.format(weakId, strongId))
		request.context['payload']['Response'] = 'Success'

	except:
		errorMessage(request, response)

	## end referenceAndMergeObject
	return cleanPayload(request)
