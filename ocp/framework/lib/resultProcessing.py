"""Module for processing results and storing them in the database.

Classes:
  :class:`ResultProcessing` : class for this module

.. hidden::

	Author: Madhusudan Sridharan (MS)
	Contributors:
	Version info:
	  0.1 : (MS) Dec 20, 2017
	  1.0 : (CS) added quick fixes for test cases to pass in 2018; TODO: revisit
	        and see if we can optimize the resulting flows.

	Note : "failBulkIfOneObjectFails" may need to do multiple rollbacks for
	deleteRecreate flow; currently the entire set is dropped if failures occur.
"""
import os, sys
import traceback
import json
import time
import uuid
import datetime
import twisted.logger
from contextlib import suppress
from sqlalchemy.orm import noload
from sqlalchemy import and_
from sqlalchemy import inspect
from results import Results
from sqlalchemy.exc import IntegrityError

## Add openContentPlatform directories onto the sys path
thisPath = os.path.dirname(os.path.abspath(__file__))
basePath = os.path.abspath(os.path.join(thisPath, '..'))
if basePath not in sys.path:
	sys.path.append(basePath)
import env
env.addLibPath()

## From openContentPlatform
import utils
import database.connectionPool as tableMapping


class ResultProcessing:
	"""Utility class for processing results and sending to the database."""

	def __init__(self, logger, dbClient, cacheData, referenceCacheData):
		"""Constructor.

		Arguments:
		  logger (twisted.logger.Logger)  : Logger handle
		  dbClient (connectionPool.DatabaseClient) : database client
		  cacheData (JSON)                : Dictionary containing BaseObject type copy
		  referenceCacheData (dict)		  : Dictionary containing  reference_id cache copy
		"""
		## Add any additional custom setup
		try:
			self.logger = logger
			self.validClassObjects = dict()
			self.validWeakLinks = dict()
			self.validStrongLinks = dict()
			self.resultJson = Results('resultProcessingDefault', True)
			self.dbClient = dbClient
			utils.getValidStrongLinks(self.validStrongLinks)
			utils.getValidWeakLinks(self.validWeakLinks)
			utils.getValidClassObjects(self.validClassObjects)
			self.validNodeSubtypes = set(self.validClassObjects['Node']['children'])
			self.validHardwareSubtypes = set(self.validClassObjects['Hardware']['children'])
			self.constraintCacheData = cacheData
			self.referenceCacheData = referenceCacheData
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			print('Exception in ResultProcessing constructor: {}'.format(str(exception)))
			with suppress(Exception):
				self.logger.error('Exception in ResultProcessing: {exception!r}', exception=exception)


	##def referenceAndMergeObjectById(self, dbClient, logger, weakId, strongId):
	def referenceAndMergeObjectById(self, weakId, strongId):
		"""Wrapper for referenceAndMergeObject.

		Arguments:
		  dbClient 						   : database client
		  logger  (twisted.logger.Logger)  : logger handle
		  weakId (str)					   : 32 bit hex
		  strongId (str)				   : 32 bit hex
		"""
		try:
			weakObject = self.dbClient.session.query(tableMapping.BaseObject).filter(tableMapping.BaseObject.object_id==weakId).first()

			self.logger.debug('referenceAndMergeObjectById: Weak object:')
			self.logger.debug('  referenceAndMergeObjectById: Attributes:')
			for item in inspect(weakObject).mapper.c.keys():
				self.logger.info('  referenceAndMergeObjectById:   {item!r} = {value!r}', item=item, value=getattr(weakObject,item))

			self.logger.info('  referenceAndMergeObjectById: Relationships:')
			for item in ['weak_first_objects', 'weak_second_objects', 'strong_first_objects', 'strong_second_objects', 'base_object_children']:
				self.logger.info('  referenceAndMergeObjectById:   {item!r} = {value!r}', item=item, value=getattr(weakObject,item))

			strongObject = self.dbClient.session.query(tableMapping.BaseObject).filter(tableMapping.BaseObject.object_id==strongId).first()

			self.logger.debug('referenceAndMergeObjectById: Strong object:')
			self.logger.debug('  referenceAndMergeObjectById: Attributes:')
			for item in inspect(strongObject).mapper.c.keys():
				self.logger.info('  referenceAndMergeObjectById:   {item!r} = {value!r}', item=item, value=getattr(strongObject,item))

			self.logger.info('  referenceAndMergeObjectById: Relationships:')
			for item in ['weak_first_objects', 'weak_second_objects', 'strong_first_objects', 'strong_second_objects', 'base_object_children']:
				self.logger.info('  referenceAndMergeObjectById:   {item!r} = {value!r}', item=item, value=getattr(strongObject,item))

			self.referenceAndMergeObject(weakObject, strongObject)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.self.logger.error('Exception in referenceAndMergeObjectById: {exception!r}', exception=exception)

		## end referenceAndMergeObjectById
		return


	def referenceAndMergeObject(self, weakEntry, strongEntry):
		"""Rereferencing the strong links and weak links from the weak
		BaseObject type to the Strong BaseObject type

		Create JSON before deleting the weak Node(BaseObject), delete the weak
		Node(BaseObject). Re-create deleted node without any links using the
		JSON to connect copied links and objects to Strong Node className name
		of replacing class.

		Arguments:
		  weakEntry (BaseObject)    : DB object instance
		  StrongEntry (BaseObject)  : DB object instance
		"""
		## cleaning the JSON structure before storing
		try:
			self.logger.info('Received {weakEntry!r},{strongEntry!r} for referenceAndMergeObject method.', weakEntry=weakEntry, strongEntry=strongEntry)
			self.resultJson.clearJson()
			tempThisEntryDict = dict()
			## The expression below copies values from the ORM instance
			##  by filtering out the 'reference_id', 'container', 'object_id',
			## 'time_updated', and 'time_created' attributes.
			tempThisEntryDict = {col : getattr(weakEntry, col) for col in inspect(weakEntry).mapper.c.keys() if col not in ['reference_id', 'container', 'object_id', 'time_updated', 'time_created']}
			weakBaseObjectClassName = inspect(weakEntry).class_.__name__
			self.recreateMappingSubtype(weakEntry, className=inspect(strongEntry).class_.__name__, strongEntry=strongEntry)
			self.logger.info('The created JSON {data} for weak object {weak!r}', data=self.resultJson.getJson(), weak=weakEntry)
			self.dbClient.session.delete(weakEntry)
			self.dbClient.session.commit()
			tempJson = self.resultJson.getJson()
			tempJson['source'] = 'internal.referenceAndMergeObject'
			self.processResult(tempJson, deleteInsertFlag=False)
			self.logger.info('Recreating the weak one without any links {temp!r} and reference id: {reference_id!r}', temp=tempThisEntryDict, reference_id=strongEntry.object_id)
			weakEntry = self.validClassObjects[weakBaseObjectClassName]['classObject'](**tempThisEntryDict, reference_id=strongEntry.object_id)
			weakEntry = self.dbClient.session.merge(weakEntry)
			self.dbClient.session.commit()

			## Inserts an entry in the referenceCache table.
			if weakEntry:

				self.logger.info("Inserting a new entry into the ReferenceCache db")
				ReferenceCacheInstance = tableMapping.ReferenceCache(object_id=weakEntry.object_id,reference_id=weakEntry.reference_id)
				ReferenceCacheInstance = self.dbClient.session.merge(ReferenceCacheInstance)
				self.dbClient.session.commit()
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in referenceAndMergeObject: {exception!r}', exception=exception)

		## end referenceAndMergeObject
		return weakEntry


	def replaceReferenceIdObject(self, thisEntry):
		"""Querying and replacing BaseObject with reference_id object.

		Before doing an insert or update, check if the BaseObject type has
		reference_id filled, if so query for the reference id and use it.

		Arguments:
		  thisEntry (BaseObject)     : DB object instance
		"""
		self.logger.debug("Inside the replaceReferenceIdObject")
		referenceId = getattr(thisEntry, 'reference_id')
		if referenceId is not None:
			self.logger.info('Querying the {className!r} with reference_id: {referenceId!r}', className=inspect(thisEntry).class_.__name__, referenceId=referenceId)
			thisEntry = self.dbClient.session.query(self.validClassObjects['BaseObject']['classObject']).filter(self.validClassObjects['BaseObject']['classObject'].object_id==referenceId).first()
			self.logger.info('Returning Stronger object {thisEntry!r} frot the class {className!r}', thisEntry=thisEntry, className=inspect(thisEntry).class_.__name__)

		self.logger.debug("Exiting the replaceReferenceIdObject")

		## end replaceReferenceIdObject
		return thisEntry


	def storingReferenceIdObjectConnections(self, thisEntry):
		"""Storing BaseObject connections linked via reference_id in JSON.

		Arguments:
		  thisEntry (BaseObject)     : DB object instance
		"""
		weakObjects = {}
		entry = set(getattr(thisEntry, 'base_object_children'))
		if entry:
			self.logger.info('Copying the weak uncertain Baseobjects connected to the current object {entry!r}')
			weakObjects['objects'] = []
			for obj in entry:
				classObject = {}
				classObject['class_name'] = inspect(obj).mapper.class_.__name__
				self.logger.info('Adding old class object type entry into the result JSON {Name!r}', Name=inspect(obj).mapper.class_.__name__)
				## The dictionary expression below copies values from ORM
				## instance by filtering out the 'time_created' and 'reference_id'
				data = {col : getattr(obj, col) for col in inspect(obj).mapper.c.keys() if col not in ['time_created', 'reference_id']}
				classObject['data'] = data
				weakObjects['objects'].append(classObject)

		## end storingReferenceIdObjectconnections
		return weakObjects


	def recreatingReferenceIdObject(self, inputDict, reference_id):
		"""Process and load the Stored JSON into DB.

		Reinserting the copied connected weak BaseObject type to restore the
		lost records into DB during deleteAndRecreate process.

		Arguments:
		  inputDict (dict)  : Dictionary Containing class relevent information
		  reference_id      : 32 bit hex
		"""
		try:
			for item in inputDict['objects']:
				self.logger.info('Reinserting the weak BaseObject {classname!r} type into the database', classname=item['class_name'])
				thisEntry = self.validClassObjects[item['class_name']]['classObject'](**item['data'], reference_id=reference_id)
				thisEntry = self.dbClient.session.merge(thisEntry)
			self.dbClient.session.commit()
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in recreatingReferenceIdObject: {exception!r}', exception=exception)

		## end recreatingReferenceIdObject
		return


	def recreateMappingSubtype(self, thisEntry, className, newData=None, strongEntry=None):
		"""Creates a JSON copy of an object and its children using recursion.

		Arguments:
		  thisEntry (BaseObject) : DB object instance
		  className (str)        : class name of the instance object
		  newData (dict)         : data dictionary containing the instance data
		  strongEntry ()		 :
		"""
		weakLinkObjects = set()
		StrongLinkObjects = set()
		onceFlag = False
		## Store all the strong and weak links relevent to the BaseObject that
		## is about to be deleted, for recreation.
		for relation in ['weak_first_objects', 'weak_second_objects']:
			## Since both weak_first_objects and weak_second_objects are
			## collections (lists), we do not need to check if they are the
			## same object type (sqlalchemy.orm.collections.InstrumentedList)
			entry = set(getattr(thisEntry, relation))
			weakLinkObjects = weakLinkObjects.union(entry)
		self.logger.info('Weak link objects added to the set {weakLinkObjects!r}', weakLinkObjects=weakLinkObjects)

		for relation in ['strong_first_objects', 'strong_second_objects']:
			## But since the strong first/second can be either a list or a
			## single entry, we need to check object types...
			if getattr(inspect(thisEntry).mapper.relationships, relation).uselist:
				entry = set(getattr(thisEntry, relation))
				StrongLinkObjects = StrongLinkObjects.union(entry)
			else:
				if getattr(thisEntry, relation) is not None:
					entry = getattr(thisEntry, relation)
					StrongLinkObjects.add(entry)
		self.logger.info('Strong Link objects added to the set {StrongLinkObjects!r}', StrongLinkObjects=StrongLinkObjects)

		## Add BaseObject types into objects to be reconstructed as a dictionary
		objects = set()
		objectList = []
		for item in StrongLinkObjects:
			objects.add(item.strong_second_object)
			objects.add(item.strong_first_object)

		for item in weakLinkObjects:
			objects.add(item.weak_second_object)
			objects.add(item.weak_first_object)

		## Handling standalone BaseObject types
		if thisEntry not in objects:
			objects.add(thisEntry)

		## BaseObject type information is stored in JSON
		for obj in objects:
			if obj is not thisEntry:
				self.logger.info('Add old class entry into the result JSON {Name!r}', Name=inspect(obj).mapper.class_.__name__)
				## The dictionary expression below copies values from ORM
				## instance by filtering out the 'container', 'object_id',
				## 'time_updated', 'time_created' attribues.
				data = {col : getattr(obj, col) for col in inspect(obj).mapper.c.keys() if col not in ['container', 'object_id', 'time_updated', 'time_created']}
				identifier, exists = self.resultJson.addObject(inspect(obj).mapper.class_.__name__, **data)
				objectList.append(((obj, inspect(obj).mapper.class_.__name__), identifier))
			else:
				## Replacing the BaseObject type that is about to be deleted
				## (parent) with new BaseObject type (child) received from JSON.
				if strongEntry is None:
					onceFlag = True
					self.logger.info('Adding new class entry into the result JSON {Name!r}, by deleting {oldName!r}', Name=className, oldName=inspect(obj).mapper.class_.__name__)
					identifier, exists = self.resultJson.addObject(className, **newData)
					objectList.append(((obj, inspect(obj).mapper.class_.__name__), identifier))
				## Replaces the weak BaseObject type with strong BaseObject
				else:
					onceFlag = True
					self.logger.info('Adding Strong class entry into the result JSON {Name!r}, by deleting {oldName!r}', Name=inspect(strongEntry).class_.__name__, oldName=inspect(obj).mapper.class_.__name__)
					## The dictionary expression below copies values from ORM
					## instance (BaseObject) by filtering out the
					# 'time_created', 'container', and 'object_id'.
					data = {col : getattr(strongEntry, col) for col in inspect(strongEntry).mapper.c.keys() if col not in ['container', 'object_id', 'time_updated', 'time_created']}
					## Copy the missing db columns from the weak BaseObject
					## type to strong BaseObject type
					self.logger.info('Copying the missing db columns in {className!r} from {className1!r}', className=inspect(strongEntry).class_.__name__, className1=inspect(strongEntry).class_.__name__)
					for thisCol in inspect(thisEntry).mapper.c.keys():
						## Add reference_id to avoid self reference FKs in table
						if thisCol not in ['container', 'object_id', 'time_updated', 'time_created', 'reference_id'] and data[thisCol] is None:
							data[thisCol] = getattr(thisEntry, thisCol)
					## Pass StrongEntry.object_id to avoid recreation
					identifier, exists = self.resultJson.addObject(inspect(strongEntry).mapper.class_.__name__, uniqueId=strongEntry.object_id, **data)
					objectList.append(((thisEntry, inspect(thisEntry).mapper.class_.__name__), identifier))

		## Ensure that we create a JSON entry for the standalone condition, the
		## objects with no strong or weak link connected to it in DB.
		if not onceFlag:
			self.logger.info('Adding new class entry into the result JSON {Name!r}, by deleting {oldName!r}', Name=className, oldName=inspect(thisEntry).mapper.class_.__name__)
			identifier, exists = self.resultJson.addObject(className, **newData)
			objectList.append(((thisEntry, inspect(thisEntry).mapper.class_.__name__), identifier))
		objectsDict = dict(objectList)
		self.logger.debug('The new recreated dictionary: {dictionary!r}', dictionary=objectsDict)

		## Recreating strong link connection
		for item in StrongLinkObjects:
			self.logger.info('Adding Strong link of type {name!r}, into the result JSON', name=inspect(item).mapper.class_.__name__)
			first_id = objectsDict[(item.strong_first_object, inspect(item.strong_first_object).mapper.class_.__name__)]
			second_id = objectsDict[(item.strong_second_object, inspect(item.strong_second_object).mapper.class_.__name__)]
			self.resultJson.addLink(inspect(item).mapper.class_.__name__, firstId=first_id, secondId=second_id)

		## Recreating weak link connection
		for item in weakLinkObjects:
			if item.weak_first_object is thisEntry:
				self.logger.info('Adding weak link of type {name!r}, into the result JSON', name=inspect(item).mapper.class_.__name__)
				first_id = objectsDict[(item.weak_first_object, inspect(item.weak_first_object).mapper.class_.__name__)]
				self.resultJson.addTempWeak(inspect(item).mapper.class_.__name__, firstId=first_id, secondId=item.weak_second_object.object_id)
			if item.weak_second_object is thisEntry:
				second_id = objectsDict[(item.weak_second_object, item.weak_second_object.__class__.__name__)]
				self.resultJson.addTempWeak(inspect(item).mapper.class_.__name__, firstId=item.weak_first_object.object_id, secondId=second_id)

		## This is used for storing grandchildren of BaseObject type
		## which are about to be deleted.
		for child in thisEntry.strong_second_objects:
			if child.strong_second_object.strong_second_objects is not None and len(child.strong_second_object.strong_second_objects) > 0:
				self.logger.info('Begin recursion loop, to identify the strongly connected grandchildren')
				childObject = child.strong_second_object
				self.recreateMappingSubtype(childObject, inspect(childObject).class_.__name__, {col : getattr(childObject,col) for col in inspect(childObject).mapper.c.keys() if col not in ['container', 'object_id', 'time_updated', 'time_created']})
				self.logger.info('End of recursion loop, to identify the strongly connected grandchildren')

		## end recreateMappingSubtype
		return


	def deleteAndRecreate(self, thisEntry, className, data, deleteInsertFlag=True, callingFomCache=False):
		"""Delete and recreate objects without loosing relationships to others.

		For example: on a BaseObject subtype, we received 'Linux' in data(JSON)
		but have received the type 'Node' from our database lookup.

		Arguments:
		  thisEntry (BaseObject)     : DB object instance ready for deletion
		  className (str)            : String containing the class name
		  data (dict)                : Dictionary containing the object data
		  deleteInsertFlag (Boolean) : Flag to avoid spiraling recursion
		"""
		try:
			self.logger.info('Received a sub class type {className!r}, but found parent class type in DB,  {thisEntry!r}', className=className, thisEntry=inspect(thisEntry).class_.__name__)
			self.logger.info('Initiating a delete and recreate for {name!r} to {newName}', name=inspect(thisEntry).class_.__name__, newName=className)
			if deleteInsertFlag:
				## Copy columns before deleting the DB object
				tempDict = dict()
				colSet = set(['object_id', 'time_updated', 'time_created', 'object_type', 'object_created_by', 'object_updated_by'])
				self.logger.debug('Data before copying {data!r}', data=data)
				for i in inspect(thisEntry).mapper.c.keys():
					if i not in colSet and getattr(thisEntry,i) is not None:
						tempDict[i] = getattr(thisEntry,i)
				for i in tempDict:
					if i not in data.keys():
						data[i] = tempDict[i]
				self.logger.debug('Data after copying {data!r}', data=data)

				## Copies all connected objects into resultJson and delete.
				self.recreateMappingSubtype(thisEntry, className, data)
				## Copies the weak object
				self.logger.info('Begin copying the weak uncertain BaseObjects connected to the current object')
				## Begins the storingReferenceIdObjectConnections
				## to store the weak BaseOject type before deletion.
				weakObjects = self.storingReferenceIdObjectConnections(thisEntry)
				self.logger.info('BaseObjects connected to the current object {value}', value=weakObjects)
				if isinstance(callingFomCache, tuple):
					## Remove cache before delete, to avoid cache update anomoly
					del self.constraintCacheData[callingFomCache[0]][callingFomCache[1]]
				self.dbClient.session.delete(thisEntry)
				self.dbClient.session.commit()

				tempJson = self.resultJson.getJson()
				tempJson['source'] = 'internal.subTyping'
				## Begins recreation with the newly created resultJson
				self.processResult(tempJson, deleteInsertFlag=False)
				self.logger.info('The JSON that is to be inserted after delete, {data}', data=self.resultJson.getJson())
				constraints = self.validClassObjects[className]['classObject'].constraints()
				thisEntry = self.dbClient.session.query(self.validClassObjects[className]['classObject']).filter(and_((getattr(self.validClassObjects[className]['classObject'], item) == data[item] for item in constraints))).first()

				## This is to handle standalone BaseObject type in the DB
				if thisEntry is None and len(tempJson['objects'])==1:
					self.logger.info('Attemting to create standalone BaseObject class: {className!r}', className=tempJson['objects'][0]['class_name'])
					thisEntry = self.validClassObjects[tempJson['objects'][0]['class_name']]['classObject'](**tempJson['objects'][0]['data'])
					thisEntry = self.dbClient.session.merge(thisEntry)
					self.dbClient.session.commit()
				## Begins the recreatingReferenceIdObject
				if 'objects' in weakObjects.keys():
					self.logger.info('Initiating recreating reference id object creation')
					self.recreatingReferenceIdObject(weakObjects,thisEntry.object_id)

				## Cleanup for next run.
				self.resultJson.clearJson()
				self.logger.debug('checking the content in received JSON data: {data!r}', data=data)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in deleteAndRecreate: {exception!r}', exception=exception)

		## end deleteAndRecreate
		return thisEntry


	def handlingDbObject(self, className, thisEntry, classNameInMemory, data, deleteInsertFlag):
		"""This function handles three main scenarios of data processing.

		This is slightly different from the cache handling scenarios in how
		each if/def block works.  But the overall concept is the same.

		Arguments:
		  className (str) 		  	 : Class Name form input JSON
		  thisEntry (BaseObject)  	 : Database handle of BaseObject type
		  classNameInMemory (str) 	 : Class Name Stored in the Database
		  data (dict)			  	 : input data
		  deleteInsertFlag (Boolean) : Flag to avoid spiraling recursion
		"""
		## reverseList is used for super class check.
		reverseList = self.validClassObjects[inspect(thisEntry).mapper.class_.__name__]['children']
		## Check if the class name of the object returned equals the class name
		## defined in the JSON result. If so, update the instance.
		if classNameInMemory == className:
			self.logger.info('There is an entry in the database for {thisEntry!r}', thisEntry=thisEntry)
			self.logger.info('Attempting update on the instance {thisEntry!r}', thisEntry=thisEntry)
			for attribute, value in data.items():
				if attribute not in thisEntry.constraints():
					setattr(thisEntry, attribute, value)
			self.logger.debug('Updated the attribute without the constraint check for columns {thisEntry!r} with data {data!r}', thisEntry=inspect(thisEntry).mapper.c.keys(), data=data)

		## The class name of the object returned does NOT equal the class name
		## defined in JSON. Check if the class name is in the list of children.
		## If so, update the instance. (given general base class, but received
		## specific child)
		elif classNameInMemory in self.validClassObjects[className]['children'] and classNameInMemory != className:
			self.logger.info('There has been a type mismatch expected {className!r} but have a child in DB {received!r}', className=className, received=classNameInMemory)
			self.logger.info('Attempting an update with {received!r} patrent attributes', received= className)
			for attribute, value in data.items():
				if attribute not in thisEntry.constraints():
					setattr(thisEntry, attribute, value)
			self.logger.debug('Updated the attributes for columns {thisEntry!r} with data {data!r}', thisEntry=inspect(thisEntry).mapper.c.keys(), data=data)

		## Now check if the class in DB is a super type of the class defined in
		## JSON. If so, then delete and recreate the object without loosing the
		## relations in the object. Ex: received Linux specific fields in the
		## JSON but only have Node. Recreate object from the parent to the child.
		elif className in reverseList and classNameInMemory != className:
			thisEntry = self.replaceReferenceIdObject(thisEntry)
			thisEntry = self.deleteAndRecreate(thisEntry, className, data, deleteInsertFlag)
			return thisEntry

		## If the class name is a completely different object, (e.g. IP instead
		## of a Node), then that's a problem... track appropriately.
		elif classNameInMemory not in self.validClassObjects[className]['children'] and classNameInMemory not in reverseList:
			self.logger.warn('There has been a type mismatch expected {className!r} but received a different class {received!r}', className=className, received=thisEntry.__class__.__name__)
			self.logger.warn('Cannot insert an object of the type {received!r} using the object id: {object_id!r} because {className!r} and {data!r}', received=thisEntry.__class__.__name__, object_id=object_id, className=className, data=data)
			thisEntry = None

		## end handlingDbObject
		return thisEntry


	def objectIdUpdateOrInsert(self, className, data, object_id=None, deleteInsertFlag=True):
		"""Update or insert when receiving 32 bit hex in the JSON message.

		Arguments:
		  className (str)            : String containing the class name
		  data (dict)                : Dictionary containing the object data
		  object_id (str)            : 32 bit uuid type 4 hex value
		  deleteInsertFlag (Boolean) : Flag to avoid spiraling recursion
		"""
		thisEntry = None
		try:
			if className not in self.validClassObjects.keys():
				self.logger.error('Received unrecognized object class_name: {className!r}', className=className)
			else:
				self.logger.debug('Query the database to see if the object_id exists {object_id!r}', object_id=object_id)
				## Query database for the object id from the baseObject
				thisEntry = self.dbClient.session.query(self.validClassObjects['BaseObject']['classObject']).filter(self.validClassObjects['BaseObject']['classObject'].object_id == object_id).first()
				## Result found in database, from the object_id query.
				if thisEntry is not None:
					## Check for reference_id and replace with stronger object
					thisEntry = self.replaceReferenceIdObject(thisEntry)
					classNameInMemory = inspect(thisEntry).mapper.class_.__name__
					## This handles the special 3 cases
					## the below condition will handle id the data dictionary is empty.
					if data:
						self.logger.debug("Printing data before handlingDbObject {data!r}", data=data)
						thisEntry = self.handlingDbObject(className, thisEntry, classNameInMemory, data, deleteInsertFlag)

				## Not able to leverage object returned by object_id, now
				## turn to the constraint method for database lookup.
				else:
					self.logger.debug('There is no entry in the database with the object_id {object_id!r}', object_id=object_id)
					constraints = self.validClassObjects[className]['classObject'].constraints()
					## This checks that all required constraints are valid keys
					## in the data section from our JSON result.

					## added to catch the null fields before processing.
					for key in list(data.keys()):
						if key in constraints and data[key] is None:
							del data[key]
					if constraints and all(col in data.keys() for col in constraints):
						self.logger.debug('Querying the database with the constraints {constraints!r}', constraints=constraints)
						thisEntry = self.dbClient.session.query(self.validClassObjects[className]['classObject']).filter(and_( (getattr(self.validClassObjects[className]['classObject'], item) == data[item] for item in constraints) )).options([noload('weak_first_objects'), noload('weak_second_objects')]).first()
						## Result found in database from the constraint query,
						## and NOT from the object_id query, even though the
						## object_id was a 32bit hex... so message that in logs.
						if thisEntry:
							## Check for reference_id and replace with stronger object
							thisEntry = self.replaceReferenceIdObject(thisEntry)
							self.logger.warn('There is an entry in DB with this constraints at {db_object_id} so cannot update the object id with {object_id!r}', className=className, object_id=object_id, db_object_id=thisEntry.object_id)
							self.logger.warn('Updating the object')
							for attribute, value in data.items():
								if attribute not in thisEntry.constraints():
									setattr(thisEntry, attribute, value)
							self.logger.debug('Updated the attributes {thisEntry!r} with {data!r}', thisEntry=inspect(thisEntry).mapper.c.keys(), data=data)

						## Result NOT found in the database by querying on
						## the constraints; do an insert into the database
						## with a new object_id since we can't use the
						## identifier value given in the JSON result.
						else:
							object_id = uuid.uuid4().hex
							self.logger.info('Inserting {className} {object_id!r}', className=className, object_id=object_id)
							data['object_created_by'] = data['object_updated_by']
							thisEntry = self.validClassObjects[className]['classObject'](**data, object_id=object_id)
							thisEntry = self.dbClient.session.merge(thisEntry)
					else:
						mandatory_clos = []
						nullable_cols = []
						for column in constraints:
							# self.logger.warn('objectIdUpdateOrInsert ====> {text!r}', text=getattr(getattr(self.validClassObjects[className]['classObject'], column),'nullable'))
							if hasattr(getattr(self.validClassObjects[className]['classObject'], column),'nullable'):
								if getattr(getattr(self.validClassObjects[className]['classObject'], column),'nullable') is True:
									nullable_cols.append(column)
								else:
									mandatory_clos.append(column)
						if all(col in data.keys() for col in mandatory_clos):
							for col in nullable_cols:
								val = data.get(col, -2)
								if val==-2:
									data[col] = None
							thisEntry = self.dbClient.session.query(self.validClassObjects[className]['classObject']).filter(and_( (getattr(self.validClassObjects[className]['classObject'], item) == data[item] for item in constraints))).options([noload('weak_first_objects'), noload('weak_second_objects')]).first()
							## Result found in database from the constraint query,
							## and NOT from the object_id query, even though the
							## object_id was a 32bit hex... so message that in logs.
							if thisEntry:
								## Check for reference_id and replace with stronger object
								thisEntry = self.replaceReferenceIdObject(thisEntry)
								self.logger.warn('There is an entry in DB with this constraints at {db_object_id} so cannot update the object id with {object_id!r}', className=className, object_id=object_id, db_object_id=thisEntry.object_id)
								self.logger.warn('Updating the object')
								for attribute, value in data.items():
									if attribute not in thisEntry.constraints():
										setattr(thisEntry, attribute, value)
								self.logger.debug('Updated the attributes {thisEntry!r} with {data!r}', thisEntry=inspect(thisEntry).mapper.c.keys(), data=data)
						else:
							self.logger.warn('JSON class {expectedClassName!r} missing constraint field in the received data, {data!r}', expectedClassName=self.validClassObjects[className]['classObject'], data=data)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in objectIdUpdateOrInsert: {exception!r}', exception=exception)

		## end objectIdUpdateOrInsert
		return thisEntry


	def specialConstraintInsertOrUpdate(self, className, expectedClassName, data, deleteInsertFlag):
		""""This is for handling only Node and Hardware classes.

		Arguments:
		  className(str)            : String containing the parent class name
		  expectedClassName(str)    : String containing the child class name
		  data(dict)                : Dictionary containing the object data
		  deleteInsertFlag(boolean) : Flag to avoid spiraling recursion
		"""
		constraints = self.validClassObjects[className]['classObject'].constraints()
		## This checks that all required constraints are valid keys
		## in the data section from our JSON result.
		thisEntry = None
		try:
			## added to catch the null fields before processing.
			for key in list(data.keys()):
				if key in constraints and data[key] is None:
					del data[key]
			if constraints and all(col in data.keys() for col in constraints):
				self.logger.debug('Initating an insert or an update based on constraints: {constraints!r}', constraints=constraints)
				thisEntry = self.dbClient.session.query(self.validClassObjects[className]['classObject']).filter(and_((getattr(self.validClassObjects[className]['classObject'], item) == data[item] for item in constraints))).first()

				if thisEntry is None:
					object_id = uuid.uuid4().hex
					self.logger.debug('Inserting {expectedClassName} {object_id!r}', expectedClassName=expectedClassName, object_id=object_id)
					data['object_created_by'] = data['object_updated_by']
					thisEntry = self.validClassObjects[expectedClassName]['classObject'](**data, object_id=object_id)
					thisEntry = self.dbClient.session.merge(thisEntry)

				else:
					## Check for reference_id and replace with stronger object
					thisEntry = self.replaceReferenceIdObject(thisEntry)
					classNameInMemory = inspect(thisEntry).mapper.class_.__name__
					className = expectedClassName
					thisEntry = self.handlingDbObject(className, thisEntry, classNameInMemory, data, deleteInsertFlag)
			else:
				mandatory_clos = []
				nullable_cols =[]
				for column in constraints:
					if hasattr(getattr(self.validClassObjects[className]['classObject'], column),'nullable'):
						if getattr(getattr(self.validClassObjects[className]['classObject'], column),'nullable') is True:
							nullable_cols.append(column)
						else:
							mandatory_clos.append(column)
				if all(col in data.keys() for col in mandatory_clos):
					for col in nullable_cols:
						val = data.get(col, -2)
						if val==-2:
							data[col] = None
					self.logger.debug('Initating an insert or an update based on constraints: {constraints!r}', constraints=constraints)
					thisEntry = self.dbClient.session.query(self.validClassObjects[className]['classObject']).filter(and_((getattr(self.validClassObjects[className]['classObject'], item) == data[item] for item in constraints))).first()
					if thisEntry is None:
						object_id = uuid.uuid4().hex
						self.logger.debug('Inserting {expectedClassName} {object_id!r}', expectedClassName=expectedClassName, object_id=object_id)
						data['object_created_by'] = data['object_updated_by']
						thisEntry = self.validClassObjects[expectedClassName]['classObject'](**data, object_id=object_id)
						thisEntry = self.dbClient.session.merge(thisEntry)

					else:
						## Check for reference_id and replace with stronger object
						thisEntry = self.replaceReferenceIdObject(thisEntry)
						classNameInMemory = inspect(thisEntry).mapper.class_.__name__
						className = expectedClassName
						thisEntry = self.handlingDbObject(className, thisEntry, classNameInMemory, data, deleteInsertFlag)
				else:
					self.logger.warn('JSON class {expectedClassName!r} missing constraint field in the received data, {data!r}', expectedClassName=self.validClassObjects[className]['classObject'], data=data)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in specialConstraintInsertOrUpdate: {exception!r}', exception=exception)

		## end of specialConstraintInsertOrUpdate
		return thisEntry


	def constraintInsertOrUpdate(self, className, data):
		"""Handles insert or update for classes other than Node and Hardware.

		Arguments:
		  className (str) : String containing the class name
		  data (dict)     : Dictionary Containing the class relevent information
		"""
		thisEntry = None
		try:
			constraints = self.validClassObjects[className]['classObject'].constraints()
			## added to catch the null fields before processing.
			for key in list(data.keys()):
				if key in constraints and data[key] is None:
					del data[key]
			if constraints and all(col in data.keys() for col in constraints):
				self.logger.debug('Initating an insert or an update based on constraints: {constraints!r}', constraints=constraints)
				thisEntry = self.dbClient.session.query(self.validClassObjects[className]['classObject']).filter(and_((getattr(self.validClassObjects[className]['classObject'], item) == data[item] for item in constraints))).first()
				## INSERT
				if thisEntry is None:
					object_id = uuid.uuid4().hex
					self.logger.debug('Inserting {className} {object_id!r}', className=className, object_id=object_id)
					data['object_created_by'] = data['object_updated_by']
					thisEntry = self.validClassObjects[className]['classObject'](**data, object_id=object_id)
					thisEntry = self.dbClient.session.merge(thisEntry)
				## UPDATE
				else:
					## Check for reference_id and replace with stronger object
					thisEntry = self.replaceReferenceIdObject(thisEntry)
					self.logger.debug('There is an entry in the database with the constraint:{constraints!r} = {thisEntry!r}', constraints=constraints, thisEntry=thisEntry)
					self.logger.debug('Attempting update on the instance {thisEntry!r}', thisEntry = thisEntry)
					for attribute, value in data.items():
						if attribute not in thisEntry.constraints():
							setattr(thisEntry, attribute, value)
					thisEntry = self.dbClient.session.merge(thisEntry)
			else:
				mandatory_clos = []
				nullable_cols = []
				for column in constraints:
					if hasattr(getattr(self.validClassObjects[className]['classObject'], column),'nullable'):
						if getattr(getattr(self.validClassObjects[className]['classObject'], column),'nullable') is True:
							nullable_cols.append(column)
						else:
							mandatory_clos.append(column)
				if all(col in data.keys() for col in mandatory_clos):
					for col in nullable_cols:
						val = data.get(col, -2)
						if val==-2:
							data[col] = None
					self.logger.debug('Initating an insert or an update based on constraints: {constraints!r}', constraints=constraints)
					thisEntry = self.dbClient.session.query(self.validClassObjects[className]['classObject']).filter(and_((getattr(self.validClassObjects[className]['classObject'], item) == data[item] for item in constraints))).first()
					## INSERT
					if thisEntry is None:
						object_id = uuid.uuid4().hex
						self.logger.debug('Inserting {className} {object_id!r}', className=className, object_id=object_id)
						data['object_created_by'] = data['object_updated_by']
						thisEntry = self.validClassObjects[className]['classObject'](**data, object_id=object_id)
						thisEntry = self.dbClient.session.merge(thisEntry)
					## UPDATE
					else:
						## Check for reference_id and replace with stronger object
						thisEntry = self.replaceReferenceIdObject(thisEntry)
						self.logger.debug('There is an entry in the database with the constraint:{constraints!r} = {thisEntry!r}', constraints=constraints, thisEntry=thisEntry)
						self.logger.debug('Attempting update on the instance {thisEntry!r}', thisEntry = thisEntry)
						for attribute, value in data.items():
							if attribute not in thisEntry.constraints():
								setattr(thisEntry, attribute, value)
						thisEntry = self.dbClient.session.merge(thisEntry)
				else:
					self.logger.warn('JSON class {className!r} missing constraint field in the received data, {data!r}', className=className, data=data)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in constraintInsertOrUpdate: {exception!r}', exception=exception)

		## end constraintInsertOrUpdate
		return thisEntry


	def constraintHandler(self, className, data, deleteInsertFlag = True):
		"""Update or insert without a 32 bit hex in the JSON message.

		Arguments:
		  className (str) : String containing the class name
		  data (dict)     : Dictionary Containing the class relevent information
		"""
		thisEntry = None
		self.logger.debug('Received a JSON entry for the class {className}', className=className)
		try:
			if className not in self.validClassObjects.keys():
				self.logger.error('Received unrecognized object class_name: {className!r}', className=className)
			else:
				if className in self.validNodeSubtypes:
					thisEntry = self.specialConstraintInsertOrUpdate('Node', className, data, deleteInsertFlag)
				elif className in self.validHardwareSubtypes:
					thisEntry = self.specialConstraintInsertOrUpdate('Hardware', className, data, deleteInsertFlag)
				else:
					## General object type (not Node/Hardware type or subtypes)
					thisEntry = self.constraintInsertOrUpdate(className, data)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in constraintHandler: {exception!r}', exception=exception)

		## end constraintHandler
		return thisEntry


	def getNewObject(self, className, data, object_id=None, deleteInsertFlag=True):
		"""Creates an ORM instance for the Class name and set in Pending State.

		Arguments:
		  className (str)            : String containing the class name
		  data (dict)                : Dictionary Containin the class relevent information
		  object_id (str)            : 32 bit uuid type 4 hex value
		  deleteInsertFlag (Boolean) : Flag to avoid spiraling recursion
		"""
		try:
			thisEntry = None
			## If temp_id is given instead of the object id, use the constraint
			## information to insert, update, or delete-recreate the objects.
			if object_id is None:
				thisEntry = self.constraintHandler(className, data, deleteInsertFlag=True)
				return thisEntry
			## The object_id is defined for this next block, meaning we have a
			## 32 bit hex from the 'identifier' attribute of the JSON result
			else:
				self.logger.info('Received a JSON entry with 32 bit hex object_id {object_id!r} for the class {className}', object_id=object_id, className=className)
				thisEntry = self.objectIdUpdateOrInsert(className, data, object_id, deleteInsertFlag)
				return thisEntry
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in getNewObject: {exception!r}', exception=exception)

		## end getNewObject
		return thisEntry


	def customUpsert(self, data, className, object_id=None):
		"""Used for handling Upsert (Insert or Update).

		Arguments:
		  data (dict) 	  : Dictionary containing the object data
		  className (str) : Class Name.
		  object_id (str) : 32 bit uuid type 4 hex value
		"""
		newData = {key : value for key,value in data.items() if key not in ['object_id']}
		newObject_id = uuid.uuid4().hex
		thisEntry = None
		try:
			## INSERT
			self.logger.info('Initiating an insert')
			thisEntry = self.validClassObjects[className]['classObject'](**newData, object_id=newObject_id)
			self.dbClient.session.add(thisEntry)
			self.dbClient.session.commit()
			self.logger.info('Inserted the entry in the database with class Name {className!r} and object_id {object_id!r}', data=data, className=className, object_id=newObject_id)

		except IntegrityError:
			## UPDATE
			constraints= self.validClassObjects[className]['classObject'].constraints()
			self.logger.info('There is an entry in the data base with the constraint:{constraints!r}',constraints=constraints)
			self.logger.info('Unique constraint violated')
			self.logger.info('Issuing a DB rollback()')
			self.dbClient.session.rollback()
			if set(constraints).issubset(set(newData.keys())):
				if object_id:
					## We have the 32 bit hex for the merge to work
					newData['object_id'] = object_id
					thisEntry = self.validClassObjects[className]['classObject'](**newData)
				else:
					thisEntry = self.dbClient.session.query(self.validClassObjects[className]['classObject']).filter(and_((getattr(self.validClassObjects[className]['classObject'], item) == newData[item] for item in constraints))).first()
				self.logger.info('Issue a DB Update for the BaseObject type {thisEntry!r}',thisEntry=thisEntry)
				for attribute, value in newData.items():
					if attribute not in thisEntry.constraints():
						setattr(thisEntry, attribute, value)
				thisEntry = self.dbClient.session.merge(thisEntry)
				self.dbClient.session.commit()
			else:
				self.logger.warn('Check the input constraint received')
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in customUpsert: {exception!r}', exception=exception)

		## end customUpsert
		return thisEntry


	def handlingCacheScenario(self, cacheRecordClassName, className, superClassName, data, deleteInsertFlag, object_id=None):
		"""Handle three main scenarios of data processing at cache level.

		Arguments:
		  cacheRecordClassName (str) : Class Name Found in the Cache
		  className (str)			 : Class Name in input JSON
		  superClassName (str)		 : Class Name of BaseObject type
		  data (str)				 : Data from kafka producer
		  deleteInsertFlag (str)	 : Flag to avoid spiraling recursion
		  object_id (str)			 : 32 bit uuid type 4 hex value
		"""
		thisEntry = None
		try:
			## reverseList is used for super class check.
			reverseList = self.validClassObjects[cacheRecordClassName]['children']
			classConstraints = self.validClassObjects[cacheRecordClassName]['classObject'].constraints()

			## Check the reference Cache and replace the New Object id
			newData = data
			if object_id is not None and object_id in self.referenceCacheData.keys():
				self.logger.info("Switching from the weak BaseObject type to strong BaseObject type. {object_id!r}--{newObject_id!r}", object_id=object_id, newObject_id=self.referenceCacheData[object_id])
				object_id = self.referenceCacheData[object_id]
				## The dictionary expression below copies values from ORM
				## instance (BaseObject) by filtering out the constraints.
				newData = {col : data[col] for col in data.keys() if col not in classConstraints}

			## Check if the class name of the object returned equals the class
			## name defined in the JSON result. If so, update the instance.
			if cacheRecordClassName == className:
				self.logger.debug('Class name in the input data and the cache matches: {className!r}', className=className)
				self.logger.info('Performing an upsert on {className!r}', className=className)
				## TODO: change the updated_by add logic
				## Should we try an try except block wrap?
				if newData:
					del newData['object_updated_by']
					thisEntry = self.validClassObjects[className]['classObject'](**newData, object_id=object_id, object_updated_by='internal.resultProcessing')
					thisEntry = self.dbClient.session.merge(thisEntry)
					self.dbClient.session.commit()
				## data is {}
				else:
					self.logger.debug("The data fiend is empty, querying with just object_id {object_id!r}", object_id=object_id)
					thisEntry = self.dbClient.session.query(self.validClassObjects[className]['classObject']).filter(self.validClassObjects[className]['classObject'].object_id == object_id).first()

			## The class name of the object returned does NOT equal the class name
			## defined in JSON. Check if the class name is in the list of children.
			## If so, update the instance. (given general base class, but received
			## specific child)
			elif cacheRecordClassName in self.validClassObjects[className]['children'] and cacheRecordClassName != className:
				self.logger.debug('There has been a type mismatch expected {className!r} but have a child in DB-Cache {received!r}', className=className, received=cacheRecordClassName)
				self.logger.info('Attempting an update with {className!r}', className=cacheRecordClassName)
				## change the updated_by add logic
				if 'object_updated_by' in newData.keys():
					del newData['object_updated_by']
				self.logger.debug("{newData!r}", newData=newData)
				thisEntry = self.validClassObjects[cacheRecordClassName]['classObject'](**newData, object_id=object_id, object_updated_by='OCP.resultProcessing')
				thisEntry = self.dbClient.session.merge(thisEntry)
				self.dbClient.session.commit()
			## Now check if the class in DB is a super type of the class defined in
			## JSON. If so, then delete and recreate the object without loosing the
			## relations in the object. Ex: received Linux specific fields in the
			## JSON but only have Node. Recreate object from the parent to the child.
			elif className in reverseList and cacheRecordClassName != className:
				self.logger.info('Subtyping {received!r} to {className!r}', className=className, received=cacheRecordClassName)
				if object_id:
					self.logger.debug('Found entry in the DB with object_id {object_id!r}', object_id=object_id)
					thisEntry = self.dbClient.session.query(self.validClassObjects[cacheRecordClassName]['classObject']).filter(self.validClassObjects[cacheRecordClassName]['classObject'].object_id == object_id).first()
					#self.logger.info('Found entry in the DB with object_id {object_id!r}', object_id=thisEntry)
				else:
					self.logger.debug('Found entry in the DB with constraint {classConstraints!r}', classConstraints=classConstraints)
					thisEntry = self.dbClient.session.query(self.validClassObjects[cacheRecordClassName]['classObject']).filter(and_((getattr(self.validClassObjects[cacheRecordClassName]['classObject'], item) == data[item] for item in classConstraints))).first()
					## Switching the weak to Strong BaseObject type if had to query based on
					thisEntry = self.replaceReferenceIdObject(thisEntry)
				self.logger.debug('Deleting the cache entry')
				thisEntry = self.deleteAndRecreate(thisEntry, className, data, deleteInsertFlag, callingFomCache = (superClassName, object_id))
				cacheEntry = [className]
				self.logger.debug('Inserted the cache entry')
				cacheEntry.extend([getattr(thisEntry,col) for col in thisEntry.constraints()])
				self.logger.debug('Inserted the cache entry {cacheEntry!r}', cacheEntry=cacheEntry)
				self.constraintCacheData[superClassName][thisEntry.object_id] = cacheEntry

				return thisEntry

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in handlingCacheScenario: {exception!r}', exception=exception)


		return thisEntry
		## end handlingCacheScenario


	def individualCacheConstraintScenario(self, superClassName, className, data, deleteInsertFlag=True):
		"""Handle update or insert with cache if there is no 32 bit hex.

		Arguments:
		  superClassName (str)    : Cache key.
		  className (str)	      : Class name to be insertrd or updated.
		  data (str)		      : Dictionary containing the object data
		  deleteInsertFlag (bool) : Flag to avoid spiraling recursion
		"""
		thisEntry = None
		self.logger.info('Processing the data with constraints since the object_id is None.')
		classConstraints = self.validClassObjects[className]['classObject'].constraints()
		try:
			## added to catch the null fields before processing.
			for key in list(data.keys()):
				if key in classConstraints and data[key] is None:
					del data[key]
			## Check if all the required columns present in the database
			if classConstraints and all(col in data.keys() for col in classConstraints):
				## Create a list Containing the Constraint Values from the data
				inputDataConstraintValues = [data[constCol] for constCol in classConstraints]
				self.logger.debug('The content of the data before insert: {inputDataConstraintValues!r}', inputDataConstraintValues=inputDataConstraintValues)
				self.logger.debug('Initiating an insert or an update based on constraints: {classConstraints!r}', classConstraints=classConstraints)
				for key, item in self.constraintCacheData[superClassName].items():
					if item[1:] == inputDataConstraintValues:
						self.logger.info('Match in the cache with the constraint')
						cacheRecordClassName = item[0]
						## Found a match in cache; break out of loop
						thisEntry = self.handlingCacheScenario(cacheRecordClassName, className, superClassName, data, deleteInsertFlag, object_id=key)
						return thisEntry

				## No 32 bit hex or constraint matches were found in the cache,
				## so now we revert to the database level methods.
				self.logger.debug('No entry in the cache to handle the changes by accessing the Database')
				thisEntry = self.specialConstraintInsertOrUpdate(superClassName, className, data, deleteInsertFlag)
			else:
				mandatory_clos = []
				nullable_cols = []
				for column in classConstraints:
					if hasattr(getattr(self.validClassObjects[className]['classObject'], column),'nullable'):
						if getattr(getattr(self.validClassObjects[className]['classObject'], column),'nullable') is True:
							nullable_cols.append(column)
						else:
							mandatory_clos.append(column)
				if all(col in data.keys() for col in mandatory_clos):
					for col in nullable_cols:
						val = data.get(col, -2)
						if val==-2:
							data[col] = None
				inputDataConstraintValues = [data[constCol] for constCol in classConstraints]
				self.logger.debug('The content of the data before insert: {inputDataConstraintValues!r}', inputDataConstraintValues=inputDataConstraintValues)
				self.logger.debug('Initiating insert or an update based on constraints: {classConstraints!r}', classConstraints=classConstraints)
				for key, item in self.constraintCacheData[superClassName].items():
					if item[1:] == inputDataConstraintValues:
						self.logger.info('Match in the cache with the constraint')
						cacheRecordClassName = item[0]
						## Found a match in cache; break out of loop
						thisEntry = self.handlingCacheScenario(cacheRecordClassName, className, superClassName, data, deleteInsertFlag, object_id=key)
						return thisEntry

				## No 32 bit hex or constraint matches were found in the cache,
				## so now we revert to the database level methods.
				self.logger.debug('No entry in the cache to handle the changes by accessing the Database')
				thisEntry = self.specialConstraintInsertOrUpdate(superClassName, className, data, deleteInsertFlag)

				self.logger.error('Received invalid data, missing constraint {data!r}', data=data)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in individualCacheConstraintScenario: {exception!r}', exception=exception)

		## end individualCacheConstraintScenario
		return thisEntry


	def individualCacheObjectIdScenario(self, superClassName, className, data, object_id=None, deleteInsertFlag=True):
		"""Handle update or insert with cache when we have a 32 bit hex.

		Arguments:
		  superClassName (str)    : Cache key.
		  className (str)	      : Class name to be insertrd or updated.
		  data (str)		      : Dictionary containing the object data
		  object_id (str)	   	  : 32 bit uuid type 4 hex value
		  deleteInsertFlag (bool) : Flag to avoid spiraling recursion
		"""
		thisEntry = None
		## Cache check for 32 bit hex
		superClassConstraintList = self.constraintCacheData[superClassName].get(object_id, list())
		try:
			if len(superClassConstraintList) > 0:
				## Data found in the cache with the input object_id
				self.logger.info('Found an entry in the cache matching the object_id {object_id!r} :{entry!r}', object_id=object_id, entry=superClassConstraintList)
				cacheRecordClassName = superClassConstraintList[0]
				cacheConstraintsValue = superClassConstraintList[1:]
				## Retrieve children of the Node subtype in the DB, for subtypes
				reverseList = self.validClassObjects[cacheRecordClassName]['children']
				classConstraints = self.validClassObjects[cacheRecordClassName]['classObject'].constraints()
				## Ensure we have valid data for constraints in JSON
				if classConstraints and all(col in data.keys() for col in classConstraints) and all(colValue in data.values() for colValue in cacheConstraintsValue):
					## The special three scenarios are handled here.
					thisEntry = self.handlingCacheScenario(cacheRecordClassName, className, superClassName, data, deleteInsertFlag, object_id)
				elif not data:
					self.logger.info("Querying with just the object id {object_id!r}",object_id=object_id)
					thisEntry = self.handlingCacheScenario(cacheRecordClassName, className, superClassName, data, deleteInsertFlag, object_id)
				elif data and utils.uuidCheck(object_id):
					self.logger.info("Querying with just the 32-bit hex object_id with insufficient {object_id!r}",object_id=object_id)
					thisEntry = self.handlingCacheScenario(cacheRecordClassName, className, superClassName, data, deleteInsertFlag, object_id)
				else:
					thisEntry = None
					self.logger.warn("Please check the cache Created or the data received from kafka for processing: {data!r}", data=data)
			else:
				self.logger.info('There is no entry in the Cache with the object_id: {object_id}', object_id=object_id)
				self.logger.info('Check with Constraints in the Cache')
				## CS: this is to see if the cached ID has changed (maybe by a
				## universalJob job with the strongObjectReference)
				thisEntry = self.individualCacheConstraintScenario(superClassName, className, data, deleteInsertFlag)
				## CS 7/18/2018: adding this to avoid instances where the cache
				## does not yet have a new node entry. This happens when a job
				## fires off with a recently created node, and the job uses only
				## the object_id to recreate the Node in the results. That means
				## the node was sent to kafka with only the identifier and not
				## with a data section; no way to check the constraints in cache
				## with the above call to individualCacheConstraintScenario.
				if thisEntry is None:
					self.logger.info('No data in cache, processing the object by accessing the database')
					thisEntry = self.getNewObject(className, data, object_id, deleteInsertFlag)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in individualCacheObjectIdScenario: {exception!r}', exception=exception)

		## end individualCacheObjectIdScenario
		return thisEntry


	def individualCacheProcessing(self, superClassName, className, data, object_id=None, deleteInsertFlag=True):
		"""Wrapper to return entry based on 32 bit hex or constraint lookup.

		 Arguments:
		  superClassName (str)    : Cache key.
		  className (str)	      : Class name to be insertrd or updated.
		  data (str)		      : Dictionary containing the object data
		  object_id (str)	   	  : 32 bit uuid type 4 hex value
		  deleteInsertFlag (bool) : Flag to avoid spiraling recursion
		 """
		thisEntry = None
		try:
			if object_id is None:
				thisEntry = self.individualCacheConstraintScenario(superClassName, className, data, deleteInsertFlag)
			else:
				## We have a 32 bit hex
				thisEntry = self.individualCacheObjectIdScenario(superClassName, className, data, object_id, deleteInsertFlag)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in individualCacheProcessing: {exception!r}', exception=exception)

		## end individualCacheProcessing
		return thisEntry


	def cacheProcessing(self, className, data, object_id=None, deleteInsertFlag=True):
		"""Process data via cache instead of DB.

		Arguments:
		  className (str)            : String containing the class name
		  data (dict)                : Dictionary Containin the class relevent information
		  object_id (str)            : 32 bit uuid type 4 hex value
		  deleteInsertFlag (Boolean) : Flag to avoid spiraling recursion
		"""
		## have not incorporated the reference cache yet.
		thisEntry = None
		try:
			## classNames will include all subtypes of database tables that are
			## considered special and handled differently with insert/merge/del.
			classNames = self.validClassObjects['Node']['children']
			classNames.extend(self.validClassObjects['Hardware']['children'])
			classNames.extend(self.validClassObjects['Cluster']['children'])
			classNames.extend(['Node', 'Hardware', 'Cluster'])

			## If the class is not a special type
			if className not in classNames:
				self.logger.debug('The given class name doesn\'t hold any information in the cache.')
				thisEntry = self.getNewObject(className, data, object_id, deleteInsertFlag)
			else:
				## Node and its subtypes
				if className == 'Node' or className in self.validNodeSubtypes:
					if self.constraintCacheData['Node']:
						self.logger.debug('Processing the kafka result using the cache information for Node or its subtypes.')
						thisEntry = self.individualCacheProcessing('Node', className, data, object_id, deleteInsertFlag)
					else:
						self.logger.info('No data in cache, processing the kafka results by accessing the database')
						thisEntry = self.getNewObject(className, data, object_id, deleteInsertFlag)
				## Hardware and its subtypes
				elif className == 'Hardware' or className in self.validHardwareSubtypes:
					if self.constraintCacheData['Hardware']:
						self.logger.debug('Processing the kafka result using the cache information for Hardware or its subtypes.')
						thisEntry = self.individualCacheProcessing('Hardware', className, data, object_id, deleteInsertFlag)
					else:
						self.logger.info('No data in cache, processing the kafka results by accessing the database')
						thisEntry = self.getNewObject(className, data, object_id, deleteInsertFlag)
				## Cluster and its subtypes
				elif className == 'Cluster' or className in self.validClassObjects['Cluster']['children']:
					if self.constraintCacheData['Cluster']:
						self.logger.debug('Processing the kafka result using the cache information for Cluster or its subtypes.')
						thisEntry = self.individualCacheProcessing('Cluster', className, data, object_id, deleteInsertFlag)
					else:
						self.logger.info('No data in cache, processing the kafka results by accessing the database')
						thisEntry = self.getNewObject(className, data, object_id, deleteInsertFlag)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in cacheProcessing: {exception!r}', exception=exception)

		## end cacheProcessing
		return thisEntry


	def createLink(self, dbResults, link):
		"""Create a link.

		Arguments:
		  dbResults (dict) : Dictionary containing DB objects
		  link (dict)      : Dictionary containing the link data
		"""
		try:
			thisLink = None
			## Parsing the adhoc JSON created for recreation of weak entries
			if link['type'] == 'temp_weak':
				self.logger.info('Handling special case of create link :temp_weak')
				weakLinkClass = self.validWeakLinks[link['class_name']]
				object_type =  weakLinkClass.__tablename__
				thisLink = weakLinkClass.as_unique(self.dbClient.session, first_id=link['first_id'], second_id=link['second_id'], object_id=uuid.uuid4().hex, object_type=object_type)
				self.logger.info('Weak link recreated {link!r}', link=thisLink)
				return

			## firstObj and secondObj are only for link type 'strong' or 'weak'
			firstObj = dbResults[link['first_id']]
			self.logger.debug('First {firstObj!r}', firstObj=firstObj)
			secondobj = dbResults[link['second_id']]
			self.logger.debug('Second {secondobj!r}', secondobj=secondobj)
			first_id = firstObj.object_id
			second_id = secondobj.object_id

			## Creates a Strong link
			if link['type'] == 'strong':
				strongLinkClass = self.validStrongLinks[link['class_name']]
				object_type = strongLinkClass.__tablename__
				thisLink = strongLinkClass.as_unique(self.dbClient.session, first_id=first_id, second_id=second_id, object_id=uuid.uuid4().hex, object_type=object_type)
				self.logger.debug('Strong link added to the session {thisLink!r}', thisLink=thisLink)
			## Creates a weak link
			elif link['type'] == 'weak':
				weakLinkClass = self.validWeakLinks[link['class_name']]
				object_type =  weakLinkClass.__tablename__
				thisLink = weakLinkClass.as_unique(self.dbClient.session, first_id=first_id, second_id=second_id, object_id=uuid.uuid4().hex, object_type=object_type)
				self.logger.debug('Weak link added to the session {thisLink!r}', thisLink=thisLink)
			else:
				self.logger.warn('Received unrecognized link class_name: {linkName!r} link_type : {link_type!r}', linkName=linkName, link_type=link['type'])

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in createLink: {exception!r}', exception=exception)

		## end createLink
		return


	def processResult(self, message, deleteInsertFlag=True):
		"""Process a JSON result pulled off kafka.

		Arguments:
		  message (JSON)             : Json object with data pulled from kafka
		  deleteInsertFlag (Boolean) : Flag to avoid spiraling recursion
		"""
		errMsg = None
		try:
			messageSource = message.get('source')
			self.logger.info('Processing the result received from Kafka, from source {messageSource!r}, with number of objects: {numberOfObjects!r}.', messageSource=messageSource, numberOfObjects=len(message['objects']))
			objectsDict = {}
			dbResults = {}
			invalidLink = False
			objectConstraints = {}
			objectIdMap = dict()
			## Save objects in a dictionary where keys are the identifiers
			newLinks = dict()
			newLinks['links'] = []
			linkCheck = dict()

			for obj in message['objects']:
				className = obj['class_name']
				identifier = obj['identifier']
				identifier = str(identifier)
				data = obj['data']
				## Updated_by field gets message['source'] value
				self.logger.debug("Printing the data before conditon check {data!r}", data = data)
				if data:
					data['object_updated_by'] = message['source']
				constraints = self.validClassObjects[className]['classObject'].constraints()

				## TODO: CS - after doing this, need code to REMOVE duplicate
				## links with the same ends; until coded, need this disabled:
				##
				## Avoid duplicate entries for objects with temp id
				# if not utils.uuidCheck(identifier):
				# 	try:
				# 		## here we are using the data of the classes to merge the duplicates,
				# 		##  should include className and the attribute name as well.
				# 		# objectKeyTuple = tuple([data.get(col) for col in constraints])
				# 		# objectKeyTuple = tuple([(col, data.get(col)) for col in constraints])
				# 		## adding the class Name.
				# 		tempConstraintList = [(col, data.get(col)) for col in constraints]
				# 		tempConstraintList.append(('class_name', className))
				# 		objectKeyTuple = tuple(tempConstraintList)
				# 		## The following check will throw an exception if one of
				# 		## the constraints are not hashable (i.e. a list/array
				# 		## such as process_fingerprint.process_hierarchy); and
				# 		## if that happens, just avoid this shortcut of trying
				# 		## to unique the failing objects before sending back
				# 		if objectKeyTuple not in objectConstraints.keys():
				# 			objectConstraints[objectKeyTuple] = identifier
				# 		else:
				# 			tmpIdentifier = objectConstraints[objectKeyTuple]
				# 			objectIdMap[identifier] = tmpIdentifier
				# 			identifier = tmpIdentifier
				# 	except:
				# 		pass

				if utils.uuidCheck(identifier):
					objectsDict[identifier] = [className, data, identifier]
				else:
					objectsDict[identifier] = [className, data, None]

			## Update the link IDs based on duplicate mapping above
			for link in message['links']:
				linkName = link['class_name']
				if linkName in self.validStrongLinks.keys():
					if link["first_id"] in objectIdMap.keys() and link["second_id"] not in objectIdMap.keys():
						link["first_id"] = objectIdMap.get(link["first_id"])
						newLinks['links'].append(link)

					elif link["first_id"] not in objectIdMap.keys() and link["second_id"] not in objectIdMap.keys():
						newLinks['links'].append(link)

					elif link["first_id"] in objectIdMap.keys() and link["second_id"] in objectIdMap.keys():
						self.logger.debug("skipping duplicates ({first_id!r}, {second_id!r})", first_id=link["first_id"], second_id=link["second_id"])

					elif link["first_id"] not in objectIdMap.keys() and link["second_id"] in objectIdMap.keys():
						link["second_id"] = objectIdMap.get(link["second_id"])

				elif linkName in self.validWeakLinks.keys():
					if link["first_id"] in objectIdMap.keys():
						link["first_id"] = objectIdMap.get(link["first_id"])

					if link["second_id"] in objectIdMap.keys():
						link["second_id"] = objectIdMap.get(link["second_id"])

					if (link["first_id"], link["second_id"]) not in linkCheck.keys():
						newLinks['links'].append(link)
						linkCheck[(link["first_id"], link["second_id"])] = link

			## removing the duplicate
			del linkCheck
			## This is to check if we have any invalid link. If we have an
			## invalid link we stop the processing.
			for link in message['links']:
				linkName = link['class_name']
				if linkName not in self.validStrongLinks.keys() and linkName not in self.validWeakLinks.keys():
					invalidLink = True
					self.logger.error("Invalid Link : {linkName!r}",linkName=linkName)
					break

			if invalidLink:
				self.logger.info('Finished processing objects.')
				return

			## Loop through links the first time, taking care of the strongly
			## linked objects (since they need established containers first)
			for link in newLinks['links']:
				linkName = link['class_name']
				## If this is a strong link, meaning the second object requires
				## the first object for the primary key/unique key constraints,
				## then we need to create the first object before using it with
				## the creation of the second object.
				if linkName in self.validStrongLinks.keys():
					firstId = link['first_id']
					secondId = link['second_id']
					firstObj = None
					secondObj = None
					## If we already created the object in the DB session, just
					## get a handle on that object; otherwise create it...
					if firstId in dbResults:
						firstObj = dbResults[firstId]
					else:
						## TODO: CNS:
						## Problem: this needs to be a type of loop because our
						## container objects may have another required container
						## object, needed before you can create the container
						## listed by the first object processed from the JSON...
						self.logger.debug("{data!r}", data=objectsDict[firstId])
						[className, data, object_id] = objectsDict[firstId]
						firstObj = self.cacheProcessing(className, data, object_id, deleteInsertFlag)
						dbResults[firstId] = firstObj
						del(objectsDict[firstId])
					if secondId in dbResults:
						# self.logger.debug("Testing Container cs-->test")
						secondObj = dbResults[secondId]
					else:
						[className, data, object_id] = objectsDict[secondId]
						data['container'] = firstObj.object_id
						# self.logger.debug("Testing Container {container!r}",container=data['container'])
						secondObj = self.cacheProcessing(className, data, object_id, deleteInsertFlag) #careful
						dbResults[secondId] = secondObj
						del(objectsDict[secondId])
					self.logger.debug('Creating strong link {linkName!r}', linkName=linkName)
					link['type'] = 'strong'
					self.createLink(dbResults, link)

			## Loop through links a second time, for the weakly linked objects
			for link in newLinks['links']:
				linkName = link['class_name']
				## If this is a strong link, meaning the second object requires
				## the first object for the primary key/unique key constraints,
				## then we need to create the first object before using it with
				## the creation of the second object.
				if linkName in self.validWeakLinks.keys():
					firstId = link['first_id']
					secondId = link['second_id']
					firstObj = None
					secondObj = None
					## If we already created the object in the DB session, just
					## get a handle on that object; otherwise create it...
					if firstId in dbResults:
						firstObj = dbResults[firstId]
					else:
						[className, data, object_id] = objectsDict[firstId]
						firstObj = self.cacheProcessing(className, data, object_id, deleteInsertFlag)
						dbResults[firstId] = firstObj
						del(objectsDict[firstId])
					self.logger.debug('First Object Weak{obj!r}', obj=firstObj)
					if secondId in dbResults:
						secondObj = dbResults[secondId]
					else:
						[className, data, object_id] = objectsDict[secondId]
						secondObj = self.cacheProcessing(className, data, object_id, deleteInsertFlag)
						dbResults[secondId] = secondObj
						del(objectsDict[secondId])
					self.logger.debug('Creating weak link {linkName!r}', linkName=linkName)
					link['type'] = 'weak'
					self.createLink(dbResults, link)

			## This is to handle delete/recreate when we have the object_id
			if 'temp_weak_links' in message.keys():
				for link in message['temp_weak_links']:
					linkName = link['class_name']
					if linkName in self.validWeakLinks.keys():
						firstId = link['first_id']
						secondId = link['second_id']
						firstObj = None
						secondObj = None

						## If either the first or second id is of the type UUID
						## we do a direct insert, else we call the getNewObject
						## to create, update or delete-recreate new objec of the
						## type BaseObject.
						if utils.uuidCheck(firstId) and utils.uuidCheck(secondId):
							self.logger.debug('Encountered a special case')
							try:
								for Id in [firstId,secondId]:
									if Id in objectsDict.keys():
										del(objectsDict[Id])
							except:
								exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
								self.logger.error('Exception in processResult: {exception!r}', exception=exception)

						elif utils.uuidCheck(firstId):
							## First is a 32bit hex; second is a temp. Need to
							## create the second and make the first value None.
							if secondId in dbResults:
								secondObj = dbResults[secondId]
								link['second_id'] = secondObj.object_id
							else:
								[className, data, object_id] = objectsDict[secondId]
								secondObj = self.cacheProcessing(className, data, object_id, deleteInsertFlag)
								link['second_id'] = secondObj.object_id
								dbResults[secondId] = secondObj
								del(objectsDict[secondId])
							dbResults[firstId] = None

						elif utils.uuidCheck(secondId):
							## Second is a 32bit hex; first is a temp. Need to
							## create the first and make the second value None.
							if firstId in dbResults:
								firstObj = dbResults[firstId]
								link['first_id'] = firstObj.object_id
							else:
								[className, data, object_id] = objectsDict[firstId]
								firstObj = self.cacheProcessing(className, data, object_id, deleteInsertFlag)
								link['first_id'] = firstObj.object_id
								dbResults[firstId] = firstObj
								del(objectsDict[firstId])
							dbResults[secondId] = None

						self.logger.debug('Recreating  link {linkName!r}', linkName=linkName)
						link['type'] = 'temp_weak'
						self.createLink(dbResults, link)

			## Check to see if everything has been created; add logging to track
			## anything that failed or anything that remains and is invalid.
			if len(list(objectsDict.keys())) > 0:
				for thisId in list(objectsDict.keys()):
					[className, data, object_id] = objectsDict[thisId]
					## to check if the given data have 'container' field and
					## it is a 32 bit hex.
					if 'container' in data.keys():
						if utils.uuidCheck(data['container']):
							thisObj = self.cacheProcessing(className, data, object_id, deleteInsertFlag)
							dbResults[thisId] = thisObj
						else:
							self.logger.error("Invalid container_id {container!r} for the standalone class: {className!r}", className=className, container=data['container'])
					else:
						thisObj = self.cacheProcessing(className, data, object_id, deleteInsertFlag)
						dbResults[thisId] = thisObj
			self.dbClient.session.commit()
			self.logger.info('Finished processing objects.')

		except:
			## Get short exception to return back/send to LogCollectionService
			errMsg = str(traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1]))
			## Database rollback
			self.dbClient.session.rollback()
			## Get full exception to drop in the local log
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in processResult: {exception!r}', exception=exception)

		## end processResult
		return errMsg


	## Newly added
	def initiateNest(self, message):
		""" Wrapper to call processNestedResults.

		Arguments:
		  message (dict) : "nested dictionary Message"
		"""
		errMsg = None
		try:
			convertedDictionary = dict()
			convertedDictionary["objects"] =[]
			convertedDictionary["links"] =[]
			convertedDictionary["source"] = message["source"]
			self.logger.info("Converting the Nested to flat")
			## calling the nested query.
			convertedDictionary = self.processNestedResults(message, convertedDictionary)
			self.logger.info("Converted result: {convertedDictionary!r}", convertedDictionary=convertedDictionary)
			## calling the normal processResult method
			errMsg = self.processResult(convertedDictionary)
		except:
			## Get short exception to return back/send to LogCollectionService
			errMsg = str(traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1]))
			## Get full exception to drop in the local log
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in initiateNest: {exception!r}', exception=exception)

		## end processResult
		return errMsg


	def processNestedResults(self, message, convertedDictionary, perspectiveIdentifier=None):
		""" This function is used to process the nested results, in the input.

		Arguments:
		  message (dict) 			   : Dictionary Containing the messages.
		  convertedDictionary (dict)   : Input dictionary for flat conversion.
		  perspectiveIdentifier (int)  : object_id for link.
		"""
		if "nested" in message.keys():
			for obj in message["nested"]:
				objInstance = message["nested"][obj]
				for item in objInstance:
					perObject = dict()
					perObject["class_name"] = item["class_name"]
					perObject["identifier"] = item["identifier"]
					perObject["data"] = item["data"]
					convertedDictionary["objects"].append(perObject)
					if "link_type" in item.keys() and "link_direction" in item.keys():
						## creating label based on nested hierarchy
						perLink = dict()
						perLink["class_name"] = item["link_type"]

						if item["link_direction"].lower() == "up":
							perLink["first_id"] = item["identifier"]
							perLink["second_id"] =  perspectiveIdentifier

						elif item["link_direction"].lower() == "down":
							perLink["first_id"] =  perspectiveIdentifier
							perLink["second_id"] = item["identifier"]

						convertedDictionary["links"].append(perLink)
					if "nested" in item.keys():
						tmpDicthandle = dict()
						tmpDicthandle["nested"] = item["nested"]
						## recurssion
						convertedDictionary = self.processNestedResults(tmpDicthandle, convertedDictionary, perspectiveIdentifier=item["identifier"])
		else:
			pass

		return convertedDictionary
