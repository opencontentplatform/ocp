"""Module for deleting objects from the DB.

In the future this may also send the deleted objects to a kafka topic.

Classes:
  * DeleteDbObject : delete objects from the database

.. hidden::

	Author: Madhusudan Sridharan (MS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Mar 7, 2018

"""

import os, sys
import traceback
import json
import twisted.logger
from sqlalchemy import inspect, and_
from sqlalchemy.orm.scoping import scoped_session as sqlAlchemyScopedSession
from sqlalchemy.orm.session import Session as sqlAlchemySession
from results import Results

## Add openContentPlatform directories onto the sys path
thisPath = os.path.dirname(os.path.abspath(__file__))
basePath = os.path.abspath(os.path.join(thisPath, '..'))
if basePath not in sys.path:
	sys.path.append(basePath)
import env
env.addLibPath()
import utils
import database.connectionPool as tableMapping


class DeleteDbObject:
	"""Utility for deleting objects from the database"""
	def __init__(self, logger, dbClient, deleteObjectList):
		self.logger = logger
		## TODO: verify and then remove this section, since we're using pools
		## across all code segments now, instead of mixed single vs pool clients
		################################################################
		## Normalize when passed both of these two db client types:
		##   database.connectionPool.DatabaseClient
		##   sqlalchemy.orm.scoping.scoped_session
		self.dbSession = None
		#logger.debug('dbClient is of type: {}'.format(type(dbClient)))
		if isinstance(dbClient, sqlAlchemySession) or isinstance(dbClient, sqlAlchemyScopedSession):
			#logger.debug('dbClient is a SqlAlchemy session')
			self.dbSession = dbClient
		elif isinstance(dbClient, tableMapping.DatabaseClient):
			#logger.debug('dbObject is a connectionPool.DatabaseClient; converting to a SqlAlchemy session')
			self.dbSession = dbClient.session
		else:
			raise EnvironmentError('The dbClient passed to QueryProcessing must be either a connectionPool.DatabaseClient or a sqlalchemy.orm.scoping.scoped_session.')
		################################################################
		## Storing the query json into a dictionary
		self.deleteObjectList = deleteObjectList
		self.validClassObjects = dict()
		self.validStrongLinks = dict()
		self.validWeakLinks = dict()
		self.getValidClassObjects()
		self.resultJson = Results('DeleteDbObjects')


	def getValidStrongLinks(self):
		"""Creates a dictionary of valid strong links."""
		strongLinkClass = tableMapping.StrongLink
		utils.classLinkDict(self.validStrongLinks, strongLinkClass)


	def getValidWeakLinks(self):
		"""Creates a dictionary of valid weak links."""
		weakLinkClass = tableMapping.WeakLink
		utils.classLinkDict(self.validWeakLinks, weakLinkClass)


	def getValidClassObjects(self):
		"""Creates a dictionary of valid BaseObjects."""
		BaseObjectClass = tableMapping.BaseObject
		tempdict = dict()
		tempdict['classObject'] = BaseObjectClass
		tempdict['children'] = [i.__name__ for i in BaseObjectClass.__subclasses__()]
		self.validClassObjects[BaseObjectClass.__name__] =  tempdict
		utils.classDict(self.validClassObjects, BaseObjectClass)
		utils.finalDictBulid(self.validClassObjects)

		## end getValidClassObjects
		return


	def preprocessNested(self, inputList, inputObject):
		"""Preprocess nested format; convert to flat before deletion."""
		try:
			for inputDictionary in inputList:
				perObject = dict()
				perObject["class_name"] = inputDictionary["class_name"]
				perObject["identifier"] = inputDictionary["identifier"]
				perObject["data"] = inputDictionary["data"]
				inputObject.append(perObject)
				if "children" in inputDictionary.keys():
					for obj in inputDictionary["children"]:
						self.logger.debug("obj {}".format(obj))
						objInstance = inputDictionary["children"][obj]
						# for label in objInstance.keys():
						self.preprocessNested(objInstance, inputObject)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in preprocessNested: {}'.format(exception))

		## end preprocessNested
		return


	def wrapNested(self):
		"""This is a helper function for performing nested delete."""
		result = {}
		try:
			objectsToDelete =[]
			for key in self.deleteObjectList:
				self.preprocessNested(self.deleteObjectList[key], objectsToDelete)
			self.deleteObjectList['objects'] = objectsToDelete
			self.logger.debug("Deleting the objects {}".format(objectsToDelete))
			result = self.queryBeforeDeletion()
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in wrapNested: {}'.format(exception))

		## end wrapNested
		return result


	def queryBeforeDeletion(self):
		"""SqlAlchemy ORM Statement is created here; later sent for deletion."""
		result = {}
		try:
			data = None
			for item in self.deleteObjectList['objects']:
				if item['class_name'] in self.validClassObjects.keys():
					className = item['class_name']
					if utils.uuidCheck(item["identifier"]):
						self.logger.info("Received a 32 hex querying the DB with the UUID")
						objectToQuery = self.validClassObjects['BaseObject']['classObject']
						entryToDelete = self.dbSession.query(objectToQuery).filter(objectToQuery.object_id==item["identifier"]).first()
					else:
						objectToQuery = self.validClassObjects[className]['classObject']
						constraints = objectToQuery.constraints()
						if item['data'].keys() and all(col in item['data'].keys() for col in constraints):
							entryToDelete = self.dbSession.query(self.validClassObjects[className]['classObject']).filter(and_((getattr(self.validClassObjects[className]['classObject'], colName) == item["data"][colName] for colName in constraints))).first()
						else:
							self.logger.warn("Insufficient data to delete: {}".format(item))
							entryToDelete = None
					self.dbSession.commit()
					data = self.deleteAndStore(entryToDelete)
			result = self.resultJson.getJson()
			if data:
				retult["objects"].extend(data)
			self.resultJson.clearJson()

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in queryBeforeDeletion: {}'.format(exception))

		## end queryBeforeDeletion
		## Note: returned result is a potential work flow for a future kafka topic
		return result


	def deleteAndStore(self, thisEntry):
		"""Used for copying connected weak objects before deletion."""
		try:
			if thisEntry is not None:
				self.logger.info('Initiating deletion for {}'.format(inspect(thisEntry).mapper.class_.__name__))
				## Copies all connected objects into resultJson and delete.
				self.recreateMappingSubtype(thisEntry)
				## Copies the weak object
				self.logger.info('Begin copying the weak uncertain BaseObjects connected to the current object')
				## Begins the storingReferenceIdObjectConnections
				## to store the weak BaseOject type before deletion.
				weakObjects = self.storingReferenceIdObjectConnections(thisEntry)
				self.logger.info('BaseObjects connected to the current object {}'.format(weakObjects))
				self.dbSession.delete(thisEntry)
				self.dbSession.commit()
				val = weakObjects.get("objects",-1)
				if val is not -1:
					weakObjects.get("objects")
					return weakObjects.get("objects")

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in deleteAndStore: {}'.format(exception))

		## end deleteAndStore
		return


	def recreateMappingSubtype(self, thisEntry):
		"""Creates a JSON copy of an object and its children using recursion.
		Arguments:
		  thisEntry (BaseObject) : DB object instance
		"""
		weakLinkObjects = set()
		StrongLinkObjects = set()
		## Store all the strong and weak links relevent to the BaseObject that
		## is about to be deleted, for recreation.
		## ignoring the weak link since are not trying to recreate the links
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
		self.logger.info('Strong Link objects added to the set {}'.format(StrongLinkObjects))

		## Add BaseObject types into objects to be reconstructed as a dictionary
		objects = set()
		objectList = []
		for item in StrongLinkObjects:
			objects.add(item.strong_second_object)
			objects.add(item.strong_first_object)

		## Handling standalone BaseObject types
		if thisEntry not in objects:
			objects.add(thisEntry)

		## BaseObject type information is stored in JSON
		for obj in objects:
			self.logger.info('Add old class entry into the result JSON {}'.format(inspect(obj).mapper.class_.__name__))

			data = {col : getattr(obj, col) for col in inspect(obj).mapper.c.keys() if getattr(obj, col) is not None}
			identifier, exists = self.resultJson.addObject(inspect(obj).mapper.class_.__name__, **data)
			objectList.append(((obj, inspect(obj).mapper.class_.__name__), identifier))

		objectsDict = dict(objectList)
		self.logger.debug('The new recreated dictionary: {}'.format(objectsDict))

		## Recreating strong link connection
		for item in StrongLinkObjects:
			self.logger.info('Adding Strong link of type {}, into the result JSON'.format(inspect(item).mapper.class_.__name__))
			first_id = objectsDict[(item.strong_first_object, inspect(item.strong_first_object).mapper.class_.__name__)]
			second_id = objectsDict[(item.strong_second_object, inspect(item.strong_second_object).mapper.class_.__name__)]
			self.resultJson.addLink(inspect(item).mapper.class_.__name__, firstId=first_id, secondId=second_id)

		## This is used for storing grandchildren of BaseObject type
		## which are about to be deleted.
		for child in thisEntry.strong_second_objects:
			if child.strong_second_object.strong_second_objects is not None and len(child.strong_second_object.strong_second_objects) > 0:
				self.logger.info('Begin recursion loop, to identify the strongly connected grandchildren')
				childObject = child.strong_second_object
				self.recreateMappingSubtype(childObject)
				self.logger.info('End of recursion loop, to identify the strongly connected grandchildren')

		## end recreateMappingSubtype
		return


	def storingReferenceIdObjectConnections(self, thisEntry):
		"""Storing BaseObject connections linked via reference_id in JSON.

		Arguments:
		  thisEntry (BaseObject)     : DB object instance
		"""
		weakObjects = {}
		entry = set(getattr(thisEntry, 'base_object_children'))
		if entry:
			self.logger.info('Copying the weak uncertain Baseobjects connected to the current object {}'.format(entry))
			weakObjects['objects'] = []
			for obj in entry:
				classObject = {}
				classObject['class_name'] = inspect(obj).mapper.class_.__name__
				self.logger.info('Adding old class object type entry into the result JSON {}'.format(inspect(obj).mapper.class_.__name__))
				## The dictionary expression below copies values from ORM
				## instance by filtering out the 'time_created' and 'reference_id'
				data = {col : getattr(obj, col) for col in inspect(obj).mapper.c.keys() if getattr(obj, col) is not None}
				classObject['data'] = data
				weakObjects['objects'].append(classObject)

		## end storingReferenceIdObjectconnections
		return weakObjects
