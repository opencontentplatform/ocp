"""QueryProcessing.

Module for Querying the database using JSON format and return JSON result.

.. hidden::

	  This module needs redone; current challenges:
	  
	  a) duplicated code blocks, should reuse code via helper functions
	  
	  b) chunking: when requested (especially with Nested formats) we need to
	  build comprehensive result sets for the desired size *during* the query
	  processing. If we attempt to post-process the query result and later split
	  it up, we're doubling performance overhead while attempting to split on 
	  less context than we had during the processing step where objects (eg. the
	  subpart containers that are treated as linchpins in their own dataset) are
	  intentionally and conditionally dropped. And those are the boundaries 
	  across which a bulk would split, and/or need added again after said split.
	  
"""
## NOTE: maximum default = 2147483647, if the size grows more than 2147483647,
## enter expected larger value.
import os, sys, traceback, json
from collections import OrderedDict
from sqlalchemy import inspect, and_, join
from sqlalchemy.orm import aliased
from sqlalchemy.orm.scoping import scoped_session as sqlAlchemyScopedSession
from sqlalchemy.orm.session import Session as sqlAlchemySession

## Add openContentPlatform directories onto the sys path
thisPath = os.path.dirname(os.path.abspath(__file__))
basePath = os.path.abspath(os.path.join(thisPath, '..'))
if basePath not in sys.path:
	sys.path.append(basePath)
import env
env.addLibPath()
import utils
import database.connectionPool as tableMapping
from database.connectionPool import DatabaseClient


class QueryProcessing:
	"""Utility for processing incoming JSON query."""

	def __init__(self, logger, dbClient, queryData, removePrivateAttributes=True, removeEmptyAttributes=True, resultsFormat='Flat'):
		"""Constructor.

		Arguments:
		  logger (twisted.logger.Logger)  : Logger handle
		  dbClient (connectionPool.DatabaseClient) : Holds the global DB relevent information.
		  queryData (dict)				  : Dictionary containing the query json.
		"""
		## default value to be set if max cardinality is not given.
		self.removePrivateAttributes = removePrivateAttributes
		self.removeEmptyAttributes = removeEmptyAttributes
		self.resultsFormat = resultsFormat
		self.MAXINT = sys.maxsize
		self.logger = logger

		## Normalize when passed both of these two db client types:
		##   database.connectionPool.DatabaseClient
		##   sqlalchemy.orm.scoping.scoped_session
		self.dbSession = None
		if isinstance(dbClient, sqlAlchemySession) or isinstance(dbClient, sqlAlchemyScopedSession):
			self.dbSession = dbClient
		elif isinstance(dbClient, DatabaseClient):
			self.dbSession = dbClient.session
		else:
			raise EnvironmentError('The dbClient passed to QueryProcessing must be either a database.connectionPool.DatabaseClient or a sqlalchemy.orm.scoping.scoped_session.')

		self.givenAttributes = dict()
		self.privateAttributes = ['container', 'object_id', 'object_type', 'reference_id']
		## Storing the query json into a dictionary
		self.dictQueryContent = queryData
		self.operatorInputList = []
		self.validClassObjects = dict()
		utils.getValidClassObjects(self.validClassObjects)
		self.validWeakLinks = dict()
		self.validStrongLinks = dict()
		utils.getValidWeakLinks(self.validWeakLinks)
		utils.getValidStrongLinks(self.validStrongLinks)
		## Stores the filter condition for query preparation
		self.finalFilterList = []
		self.labelStore = []
		## Store the error list to come out of recursion.
		self.errorList = []
		## Stores the alias along with the item content dictionary
		self.dictQueryContent["objects"] = self.indexAndSubQueryObjects(self.dictQueryContent["objects"])
		## Stores the identifier set() from objects connected to a link
		self.linkDictionary = self.storeLinks(self.dictQueryContent["links"])
		## Stores all the traversed class objects
		self.traversedObjectSet = set()
		## Stores the objects for query preparation
		self.orderedObjectList = []
		self.perspectiveObjects = []
		## Stores the join condition for query preparation
		self.strJoinList = []
		self.queriedObjects = dict()
		self.queriedLinks = dict()
		self.aliasStore = []
		self.traversalStructure = OrderedDict()
		self.recursionFlag = False
		self.globalObjectManipulator = OrderedDict()


	def storeLinks(self, linksDict):
		"""Creates dictionary of links for finding the relevent link per object.

		Argument :
		  linksDict(dict) : Dictionary containing the link.
		"""
		if len(self.errorList) <= 0:
			newLinkDict = dict()
			labels =[]
			try:
				for item in linksDict:
					## Order is maintained here
					## Note :first_id first and second_id later.
					## dict[tuple('1','2')] = item
					if item.get("label","") == "":
						if item["label"] not in labels:
							item["label"] = item["first_id"]+"_TO_"+item["second_id"]
							labels.append(item["label"])
						else:
							self.errorList.append("Lable name already used cannot use the same label")
							raise ValueError("Lable name already used cannot use the same label")
					if item["first_id"] not in self.dictQueryContent["objects"].keys() or item["second_id"] not in self.dictQueryContent["objects"].keys():
						raise ValueError("The Class Name given in the 'link' and in the 'object' does not match")
					newLinkDict[tuple([item["first_id"], item["second_id"]])] = item
			except ValueError:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				errorValue = traceback.format_exception_only(exc_type, exc_value)
				stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
				self.logger.error("Failure in storeLinks: {}".format(stacktrace))
				self.errorList.append("Failure {}".format(errorValue))
			except:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				errorValue = traceback.format_exception_only(exc_type, exc_value)
				stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
				self.logger.error("Failure in storeLinks: {}".format(stacktrace))
				self.errorList.append("Failure {}".format(errorValue))

			## end storeLinks
			return newLinkDict


	def sendErrorMessage(self):
		"""TODO have to built it out."""
		return self.errorList


	def processFilter(self, filterList, classObject):
		"""This is used to process filter part of the input per object.

		Arguments:
		  filterList : input list to process.
		  classObject : The class object who's filter is being processed.
		"""
		operatorInputList = []
		if len(self.errorList) <= 0:
			try:
				for item in filterList:
					## stopping point base case.
					if "condition" in item.keys():
						simpleConditionDictionary = item["condition"]
						attribute = getattr(classObject, simpleConditionDictionary["attribute"])
						operator = simpleConditionDictionary["operator"]
						## added a list for "is null", to enable adding
						## additional operators.
						value = None
						if operator not in ["is null"]:
							value = simpleConditionDictionary["value"]
						sqlConditionExpression = None
						if operator not in ["and", "or"]:
							if attribute is not None:
								sqlConditionExpression = utils.parseBinaryOperator(self.logger, operator, attribute, value)
						## check for negation key and perform negation
						if "negation" in item.keys():
							## CS: #if item["negation"] is True or item["negation"].lower() == "true":
							if utils.valueToBoolean(item["negation"]):
								sqlConditionExpression = ~sqlConditionExpression
						operatorInputList.append(sqlConditionExpression)

					## recurse
					elif "expression" in item.keys():
						restofConditionExpression = self.processFilter(item["expression"], classObject)
						valueStore = restofConditionExpression
						if "operator" in item.keys():
							if item.get("operator","") in ["and", "or"]:
								valueStore = utils.parseBooleanOperator(self.logger, item["operator"], *restofConditionExpression)
						if "negation" in item.keys():
							## CS: #if item["negation"] is True or item["negation"].lower() == "true":
							if utils.valueToBoolean(item["negation"]):
								## Performs negation based on entry for negation key.
								if type(valueStore) != type(list()):
									valueStore = ~ valueStore
								## this is under the assumption that inside the
								## expression, if we have more than one condition
								## we have to have an 'operator' else we can
								## have 1 conditon inside expression.
								else:
									valueStore = ~ valueStore[0]
						if type(valueStore) == type(list()):
							operatorInputList.extend(valueStore)
						else:
							operatorInputList.append(valueStore)
			except:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
				errorValue = traceback.format_exception_only(exc_type, exc_value)
				self.logger.error("Failure in processFilter: {}".format(stacktrace))
				self.errorList.append("Failed processing the filter on {}".format(inspect(classObject).mapper.class_.__name__))
				self.errorList.append(str(exc_value))

			## end processFilter
			return operatorInputList


	def indexAndSubQueryObjects(self, objects):
		"""Processing and creating alias for BaseObject type.

		Arguments:
		  objects : List of of BaseObject dictionary.
		"""
		if len(self.errorList) <= 0:
			tempObjectDict = dict()
			try:
				for item in objects:
					## setting the count
					minimumValue = item.get("minimum")
					if minimumValue == "":
						item["minimum"] = 1
					elif len(minimumValue) >0:
						item["minimum"] = int(minimumValue)
					## maximum
					maximumValue = item.get("maximum")
					if maximumValue == "":
						item["maximum"] = sys.maxsize
					elif len(maximumValue) > 0:
						item["maximum"] = int(maximumValue)

					labelName = item.get("label", "")
					tempDictionary = self.validClassObjects.get(item["class_name"])

					tempObject = tempDictionary.get("classObject", None)
					tempObjectName = item.get("class_name", "")
					if labelName =="":
						if  tempObjectName!="":
							if tempObjectName not in self.labelStore:
								item["label"] = tempObjectName
								self.labelStore.append(tempObjectName)
							else:
								self.logger.error("Cannot create alias name, since the className {tempObjectName!r} is already given in the list of labels", tempObjectName=tempObjectName)
								self.errorList.append("Cannnot create alias name, since the className {} is already given in the list of labels".format(tempObjectName))
								raise ValueError("The key is already used : {}".format(tempObjectName))
						else:
							self.errorList.append("Class name is missing in input json")
							raise ValueError("Class name is missing in input json")
					if item["label"] not in self.givenAttributes.keys():
						self.givenAttributes[item["label"]] = []
					if len(item["attributes"]) > 0:
						## If these attributes are in the queryjson then we
						## give them out in the results.
						for privateAttribute in self.privateAttributes:
							if privateAttribute in item["attributes"]:
								self.givenAttributes[item["label"]].append(privateAttribute)
						## The subquery must have object_id and "container"
						## field for the join and object_id for join condition.
						if "container" in inspect(tempObject).mapper.c.keys() and "container" not in item["attributes"]:
							item["attributes"].append("container")
						if "reference_id" in inspect(tempObject).mapper.c.keys() and "reference_id" not in item["attributes"]:
							item["attributes"].append("reference_id")
						if "object_id" not in item["attributes"]:
							item["attributes"].append("object_id")
						if "object_type" not in item["attributes"]:
							item["attributes"].append("object_type")
					else:
						## If attribute field is empty then include everything.
						## The 4 private attributes are added by default later
						## remove them, based on removePrivateAttributes flag.
						if not self.removePrivateAttributes:
							for privateAttribute in self.privateAttributes:
								self.givenAttributes[item['label']].append(privateAttribute)
						item["attributes"] = [attributes for attributes in inspect(tempObject).mapper.c.keys()]
						item["attributesIsEmpty"] = True
					## Replacing the alias with subquery and querying
					## every attribute given in attributes column
					## Note: Colums that will be used in filter condition
					## should be present in attributes column.
					filterContent = item.get("filter",[])

					if filterContent:
						## Initiating create filter
						createFilterList = self.processFilter(filterContent, tempObject)
						## Only do the following if we didn't hit filter errors
						if len(self.errorList) <= 0:
							## Storing the created filter
							if type(createFilterList) ==type(list()):
								self.finalFilterList.extend(createFilterList)
							else:
								self.finalFilterList.append(createFilterList)
							item["label_alias_object"] = self.dbSession.query(*(getattr(tempObject,attribute) for attribute in item["attributes"])).filter(*self.finalFilterList).subquery(name=item["label"])
							self.dbSession.commit()
							self.finalFilterList =[]
					else:
						item["label_alias_object"] = self.dbSession.query(*(getattr(tempObject,attribute) for attribute in item["attributes"])).subquery(name=item["label"])
						self.dbSession.commit()
					tempObjectDict[item["label"]] = item

			except:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
				errorValue = traceback.format_exception_only(exc_type, exc_value)
				self.logger.error("Failure in indexAndSubQueryObjects: {}".format(stacktrace))
				self.errorList.append("Failure {}".format(errorValue))

			## end indexAndSubQueryObjects
			return tempObjectDict


	def traverse(self, inputLinksKeys, joinObject):
		""" this is the recursive step for processing the connected link.

		Arguments :
		  inputLinksKeys (list)   : List of tuples (keys) for each link
		  joinObject (sqlalchemy) : Sqlalchemy join object (actual query).
		"""
		if len(self.errorList) <= 0:
			try:
				for key in inputLinksKeys:
					tempLblName = self.dictQueryContent["objects"][key].get("label","")
					if tempLblName == "":
						tempLblName = self.dictQueryContent["objects"][key]["class_name"]
					if tempLblName in self.traversedObjectSet:
						## This is to avoid circular recursion, skips if
						## the BaseObject is processed before.
						pass
					else:
						## Recursion flow
						## Given indexAndSubQueryObjects executed properly.
						setFlag = False
						nextObject = self.dictQueryContent["objects"][key]
						tempObjectLinks = dict()
						for keySet,value in self.linkDictionary.items():
							## If label is missing replace with class name, if
							## class name already exist raise warning done in
							## indexAndSubQueryObjects. checking if label exist.
							nextObjectLabel = nextObject.get("label", "")
							if nextObjectLabel in keySet:
								tempObjectLinks[keySet] = value
							## no label in the input dictionary
							elif nextObjectLabel == "":
								## checking if classname exist
								tempLabel = nextObject.get("class_name", "")
								if tempLabel != "" and tempLabel in keySet:
									setFlag = True
									tempObjectLinks[keySet] = value
						## Deleting the current link from the created link.
						## Avoiding duplicate and circular recursion.
						if inputLinksKeys in tempObjectLinks.keys():
							del tempObjectLinks[inputLinksKeys]
						if not setFlag:
							self.traversedObjectSet.add(nextObject["label"])
						else:
							self.traversedObjectSet.add(nextObject["class_name"])
						## Recursion
						joinObject = self.recurseObjects(nextObject, tempObjectLinks, joinObject)
			except:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
				self.logger.error("Failure in traverse: {}".format(stacktrace))
				self.errorList.append("Failure {}".format(errorValue))


			## end traverse
			return joinObject


	def createWeakLink(self, inputObject, wLinkKeys, wLinkValue, InputJoinObject):
		""" This is used to process the a weak link.

		This does not check the cordinality, this will just create a join
		condition based on the input weak link.

		Arguments :
		  inputObject (Sqlalchemy) : Sqlalchemy ORM Object
		  wLinkKeys(list) 	  	 : List of weak link keys.
		  wLinkValue (list) 	  	 : List of  weak link values.
		  InputJoinObject(Sqlalchemy) : Sqlalchemy join object (actual query).
		"""
		localJoinObject = InputJoinObject
		if len(self.errorList) <= 0:
			try:
				(firstObjectKey, secondObjectKey) = wLinkKeys
				firstObject = self.dictQueryContent["objects"][firstObjectKey]
				secondObject = self.dictQueryContent["objects"][secondObjectKey]
				aliasedLink = aliased(self.validWeakLinks[wLinkValue["class_name"]], name = wLinkValue["label"])
				if inspect(aliasedLink).name not in self.orderedObjectList:
					firstJoinCondition =  getattr(firstObject["label_alias_object"].c, "object_id") == getattr(aliasedLink, "first_id")
					secondJoinCondition = getattr(secondObject["label_alias_object"].c, "object_id") == getattr(aliasedLink, "second_id")
					self.strJoinList.append(str(firstJoinCondition))
					self.strJoinList.append(str(secondJoinCondition))

					## If both the first object and second is already in
					## traversed objects list.
					if firstObject["label_alias_object"] in self.orderedObjectList and secondObject["label_alias_object"] in self.orderedObjectList:
						if localJoinObject is not None:
							if inputObject["label_alias_object"] == firstObject["label_alias_object"]:
								secondAlaisName = self._createAliasName(0, secondObject["label"])
								secondAliasTable = secondObject["label_alias_object"].alias(name=secondAlaisName)
								secondJoinCondition =  getattr(secondAliasTable.c, "object_id") == getattr(aliasedLink, "second_id")
								intermediateJoin = join(secondAliasTable, aliasedLink, secondJoinCondition)
								localJoinObject= join(localJoinObject, intermediateJoin, firstJoinCondition)
								self.aliasStore.append(secondAlaisName)
							else:
								firstAliasName = self._createAliasName(0, firstObject["label"])
								firstAliasTable = firstObject["label_alias_object"].alias(name=firstAliasName)
								firstJoinCondition =  getattr(firstAliasTable.c, "object_id") == getattr(aliasedLink, "first_id")
								intermediateJoin = join(firstAliasTable, aliasedLink, firstJoinCondition)
								localJoinObject = join(localJoinObject, intermediateJoin, secondJoinCondition)
								self.aliasStore.append(firstAliasName)

							self.orderedObjectList.append(inspect(aliasedLink).name)

						elif localJoinObject is None:
							self.logger.warn("This case should not occur create strong second")
							self.orderedObjectList.append(inspect(aliasedLink).name)

					## If the first object is in traversed objects list and
					## second object not in traversed objects list.
					elif firstObject["label_alias_object"] in self.orderedObjectList and secondObject["label_alias_object"] not in self.orderedObjectList:
						if localJoinObject is not None:
							localJoinObject= join(localJoinObject, aliasedLink, firstJoinCondition)
							localJoinObject= join(secondObject["label_alias_object"],localJoinObject, secondJoinCondition)
							self.orderedObjectList.append(secondObject["label_alias_object"])

						elif localJoinObject is None:
							firstAliasName = self._createAliasName(0, firstObject["label"])
							firstAliasTable = firstObject["label_alias_object"].alias(name=firstAliasName)
							firstJoinCondition =  getattr(firstAliasTable.c, "object_id") == getattr(aliasedLink, "first_id")
							localJoinObject = join(firstAliasTable,aliasedLink, firstJoinCondition)
							localJoinObject = join(secondObject["label_alias_object"], localJoinObject, secondJoinCondition)
							self.aliasStore.append(firstAliasName)

						self.orderedObjectList.append(secondObject["label_alias_object"])
						self.orderedObjectList.append(inspect(aliasedLink).name)

					## If the first object not in traversed objects list and
					## second object in traversed objects list.
					elif firstObject["label_alias_object"] not in self.orderedObjectList and secondObject["label_alias_object"] in self.orderedObjectList:
						if localJoinObject is not None:
							localJoinObject= join(localJoinObject, aliasedLink, secondJoinCondition)
							localJoinObject= join(firstObject["label_alias_object"], localJoinObject, firstJoinCondition)
						elif localJoinObject is None:
							secondAlaisName = self._createAliasName(0, secondObject["label"])
							secondAliasTable = secondObject["label_alias_object"].alias(name=secondAlaisName)
							secondJoinCondition =  getattr(secondAliasTable.c, "object_id") == getattr(aliasedLink, "second_id")
							localJoinObject = join(secondAliasTable, aliasedLink, secondJoinCondition)
							localJoinObject = join(firstObject["label_alias_object"], localJoinObject, firstJoinCondition)
							self.aliasStore.append(secondAlaisName)

						self.orderedObjectList.append(firstObject["label_alias_object"])
						self.orderedObjectList.append(inspect(aliasedLink).name)

					## If the both first object and second object not in
					## traversed objects list.
					elif firstObject["label_alias_object"] not in self.orderedObjectList and secondObject["label_alias_object"] not in self.orderedObjectList:
						if localJoinObject is None:
							if inputObject["label_alias_object"] == firstObject["label_alias_object"]:
								intermediateJoin = join(secondObject["label_alias_object"], aliasedLink, secondJoinCondition)
								localJoinObject =  join(firstObject["label_alias_object"], intermediateJoin, firstJoinCondition)
							else:
								intermediateJoin = join(firstObject["label_alias_object"], aliasedLink, firstJoinCondition)
								localJoinObject = join(secondObject["label_alias_object"], intermediateJoin, secondJoinCondition)
							self.orderedObjectList.append(firstObject["label_alias_object"])
							self.orderedObjectList.append(secondObject["label_alias_object"])
							self.orderedObjectList.append(inspect(aliasedLink).name)
						elif localJoinObject is not None:
							self.logger.warn("This case should not occur")

				else:
					pass
			except:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
				errorValue = traceback.format_exception_only(exc_type, exc_value)
				self.logger.error("Failure in createWeakLink: {}".format(stacktrace))
				self.errorList.append("Failure {}".format(errorValue))

			## end createWeakLink
			return localJoinObject


	def createStrongLink(self, inputObject, sLinkKeys, sLinkValue, InputJoinObject):
		""" This is used to process the a strong link.

		This does not check the cordinality (sorted based on cardinality), will
		just create a join condition based on the input strong link.

		Arguments :
		  inputObject (sqlalchemy) 	   : Sqlalchemy ORM Object.
		  sLinkKeys (list) 			   : List of strong link keys.
		  sLinkValue (list)			   : List of  strong link values.
		  InputJoinObject (sqlalchemy) : Sqlalchemy join object (actual query).
		"""
		localJoinObject = InputJoinObject
		if len(self.errorList) <= 0:
			try:
				(firstObjectKey, secondObjectKey) = sLinkKeys
				firstObject = self.dictQueryContent["objects"][firstObjectKey]
				secondObject = self.dictQueryContent["objects"][secondObjectKey]
				aliasedLink = aliased(self.validStrongLinks[sLinkValue["class_name"]], name = sLinkValue["label"])
				if inspect(aliasedLink).name not in self.orderedObjectList:
					firstJoinCondition =  getattr(firstObject["label_alias_object"].c, "object_id") == getattr(aliasedLink, "first_id")
					secondJoinCondition = getattr(secondObject["label_alias_object"].c, "object_id") == getattr(aliasedLink, "second_id")
					self.strJoinList.append(str(firstJoinCondition))
					self.strJoinList.append(str(secondJoinCondition))

					## If both the first object and second is already in
					## traversed objects list.
					if firstObject["label_alias_object"] in self.orderedObjectList and secondObject["label_alias_object"] in self.orderedObjectList:
						if localJoinObject is not None:
							if inputObject["label_alias_object"] == firstObject["label_alias_object"]:
								secondAlaisName = self._createAliasName(0, secondObject["label"])
								secondAliasTable = secondObject["label_alias_object"].alias(name=secondAlaisName)
								secondJoinCondition =  getattr(secondAliasTable.c, "object_id") == getattr(aliasedLink, "second_id")
								intermediateJoin = join(secondAliasTable, aliasedLink, secondJoinCondition)
								localJoinObject= join(localJoinObject, intermediateJoin, firstJoinCondition)
								self.aliasStore.append(secondAlaisName)
							else:
								firstAliasName = self._createAliasName(0, firstObject["label"])
								firstAliasTable = firstObject["label_alias_object"].alias(name=firstAliasName)
								firstJoinCondition =  getattr(firstAliasTable.c, "object_id") == getattr(aliasedLink, "first_id")
								intermediateJoin = join(firstAliasTable, aliasedLink, firstJoinCondition)
								localJoinObject = join(localJoinObject, intermediateJoin, secondJoinCondition)
								self.aliasStore.append(firstAliasName)
						elif localJoinObject is None:
							self.logger.warn("This case should not occure create strong second")
							self.orderedObjectList.append(inspect(aliasedLink).name)

					## If the first object is in traversed objects list and
					## second object not in traversed objects list.
					elif firstObject["label_alias_object"] in self.orderedObjectList and secondObject["label_alias_object"] not in self.orderedObjectList:
						if localJoinObject is not None:
							localJoinObject= join(localJoinObject, aliasedLink, firstJoinCondition)
							localJoinObject= join(secondObject["label_alias_object"],localJoinObject, secondJoinCondition)
							self.orderedObjectList.append(secondObject["label_alias_object"])

						elif localJoinObject is None:
							firstAliasName = self._createAliasName(0, firstObject["label"])
							firstAliasTable = firstObject["label_alias_object"].alias(name=firstAliasName)
							firstJoinCondition =  getattr(firstAliasTable.c, "object_id") == getattr(aliasedLink, "first_id")
							localJoinObject = join(firstAliasTable,aliasedLink, firstJoinCondition)
							localJoinObject = join(secondObject["label_alias_object"], localJoinObject, secondJoinCondition)
							self.aliasStore.append(firstAliasName)

						self.orderedObjectList.append(secondObject["label_alias_object"])
						self.orderedObjectList.append(inspect(aliasedLink).name)

					## If the first object not in traversed objects list and
					## second object in traversed objects list.
					elif firstObject["label_alias_object"] not in self.orderedObjectList and secondObject["label_alias_object"] in self.orderedObjectList:
						if localJoinObject is not None:
							localJoinObject= join(localJoinObject, aliasedLink, secondJoinCondition)
							localJoinObject= join(firstObject["label_alias_object"], localJoinObject, firstJoinCondition)
						elif localJoinObject is None:
							secondAlaisName = self._createAliasName(0, secondObject["label"])
							secondAliasTable = secondObject["label_alias_object"].alias(name=secondAlaisName)
							secondJoinCondition =  getattr(secondAliasTable.c, "object_id") == getattr(aliasedLink, "second_id")
							localJoinObject = join(secondAliasTable, aliasedLink, secondJoinCondition)
							localJoinObject = join(firstObject["label_alias_object"], localJoinObject, firstJoinCondition)
							self.aliasStore.append(secondAlaisName)

						self.orderedObjectList.append(firstObject["label_alias_object"])
						self.orderedObjectList.append(inspect(aliasedLink).name)

					## If the first object not in traversed objects list and
					## second object not in traversed objects list.
					elif firstObject["label_alias_object"] not in self.orderedObjectList and secondObject["label_alias_object"] not in self.orderedObjectList:
						if localJoinObject is None:
							if inputObject["label_alias_object"] == firstObject["label_alias_object"]:
								intermediateJoin = join(secondObject["label_alias_object"], aliasedLink, secondJoinCondition)
								localJoinObject =  join(firstObject["label_alias_object"], intermediateJoin, firstJoinCondition)
							else:
								intermediateJoin = join(firstObject["label_alias_object"], aliasedLink, firstJoinCondition)
								localJoinObject = join(secondObject["label_alias_object"], intermediateJoin, secondJoinCondition)
							self.orderedObjectList.append(firstObject["label_alias_object"])
							self.orderedObjectList.append(secondObject["label_alias_object"])
							self.orderedObjectList.append(inspect(aliasedLink).name)
						elif localJoinObject is not None:
							self.loggr.warn("This case should not occure")

				else:
					pass
			except:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
				errorValue = traceback.format_exception_only(exc_type, exc_value)
				self.logger.error("Failure in createStrongLink: {}".format(stacktrace))
				self.errorList.append("Failure {}".format(errorValue))

			## end CreateStrongLink
			return localJoinObject


	def _createAliasName(self,counter,inputName):
		"""Utility function for dynamic alias table_name creation.

		Arguments :
		  counter (int)	  : Integer holding the count of the objects
		  inputName (str) : String containing the object name.
		"""
		alaisName = inputName+"__alias"+str(counter)

		if alaisName in self.aliasStore:
			counter = counter+1
			alaisName = self._createAliasName(counter, inputName)

		return alaisName


	def aliasChoice(self, rightJoinObject, joinObject, innerJoinCondition, outerJoinCondition, aliasedLink, innerJoinObject=None, outerJoinObject=None, firstorSecond=True):
		"""This function determines creation of aliases for the join condition.

		Arguments:
		  rightJoinObject    (sqlalchemy) : Sqlalchemy join object (sql query).
		  joinObject 	     (sqlalchemy) : Sqlalchemy join object (sql query).
		  innerJoinCondition (sqlalchemy) : Sqlalchemy binary expression.
		  outerJoinCondition (sqlalchemy) : Sqlalchemy binary expression.
		  aliasedLink 		 (BaseLink)   : Base Link Object.
		  innerJoinObject    (sqlalchemy) : Sqlalchemy ORM Object (BaseObject type).
		  outerJoinObject    (sqlalchemy) : Sqlalchemy ORM Object (BaseObject type).
		  firstorSecond      (boolean)    : Flag to determine the join condition.
		"""
		if len(self.errorList) <= 0:
			try:
				if rightJoinObject is None and joinObject is None:
					if innerJoinObject["label_alias_object"] in self.orderedObjectList and outerJoinObject["label_alias_object"] in self.orderedObjectList:
						self.logger.warn("Case not built out 1")

					elif outerJoinObject["label_alias_object"] not in self.orderedObjectList and innerJoinObject["label_alias_object"] in self.orderedObjectList:
						## Create an alias name before the join.
						## Recreate condition-2 to override the existing join.
						aliasName = self._createAliasName(0, innerJoinObject["label"])
						aliasTable = innerJoinObject["label_alias_object"].alias(name=aliasName)
						if firstorSecond:
							innerJoinCondition =  getattr(aliasTable.c, "object_id") == getattr(aliasedLink, "first_id")
						else:
							innerJoinCondition =  getattr(aliasTable.c, "object_id") == getattr(aliasedLink, "second_id")
						## Create the first intermediate join
						aliasIntermediateJoin = join(aliasTable, aliasedLink, innerJoinCondition)
						## Create the final join
						joinObject = join(outerJoinObject["label_alias_object"], aliasIntermediateJoin, outerJoinCondition, isouter=True)
						self.aliasStore.append(aliasName)
						self.orderedObjectList.append(outerJoinObject["label_alias_object"])

					elif outerJoinObject["label_alias_object"] in self.orderedObjectList and innerJoinObject["label_alias_object"] not in self.orderedObjectList:
						self.logger.warn("Case not built out 2")

					elif outerJoinObject["label_alias_object"] not in self.orderedObjectList and innerJoinObject["label_alias_object"] not in self.orderedObjectList:

						newIntermadiateJoin = join(innerJoinObject["label_alias_object"], aliasedLink, innerJoinCondition)
						joinObject = join(outerJoinObject["label_alias_object"], newIntermadiateJoin, outerJoinCondition, isouter=True)
						self.orderedObjectList.append(innerJoinObject["label_alias_object"])
						self.orderedObjectList.append(outerJoinObject["label_alias_object"])

				elif rightJoinObject is None and joinObject is not None:

					if innerJoinObject["label_alias_object"] in self.orderedObjectList and outerJoinObject["label_alias_object"] in self.orderedObjectList:
						## Create an alias name before the join.
						aliasName = self._createAliasName(0,innerJoinObject["label"])
						aliasTable = innerJoinObject["label_alias_object"].alias(name=aliasName)
						## Recreate condition-2 to override the existing join.
						if firstorSecond:
							innerJoinCondition =  getattr(aliasTable.c, "object_id") == getattr(aliasedLink, "first_id")
						else:
							innerJoinCondition =  getattr(aliasTable.c, "object_id") == getattr(aliasedLink, "second_id")
						## Create the first intermediate join
						aliasIntermediateJoin = join(aliasTable, aliasedLink, innerJoinCondition)
						## Create the final join
						joinObject = join(joinObject, aliasIntermediateJoin, outerJoinCondition, isouter=True)
						self.aliasStore.append(aliasName)

					elif outerJoinObject["label_alias_object"] not in self.orderedObjectList and innerJoinObject["label_alias_object"] in self.orderedObjectList:
						self.logger.warn("Case not built out 1")

					elif outerJoinObject["label_alias_object"] in self.orderedObjectList and innerJoinObject["label_alias_object"] not in self.orderedObjectList:
						newIntermadiateJoin = join(innerJoinObject["label_alias_object"], aliasedLink, innerJoinCondition)
						joinObject = join(joinObject, newIntermadiateJoin, outerJoinCondition, isouter=True)
						self.orderedObjectList.append(innerJoinObject["label_alias_object"])

					elif outerJoinObject["label_alias_object"] not in self.orderedObjectList and innerJoinObject["label_alias_object"] not in self.orderedObjectList:
						self.logger.warn("Case not built out 2")

				elif rightJoinObject is not None and joinObject is None:
					if innerJoinObject["label_alias_object"] in self.orderedObjectList and outerJoinObject["label_alias_object"] in self.orderedObjectList:
						self.logger.warn("Case not built out 1 {condition!r}", condition=str(rightJoinObject))
						intermediateJoin = join(rightJoinObject, aliasedLink, innerJoinCondition)
						self.logger.warn("Case not built out 1 {condition!r}", condition=str(intermediateJoin))

					elif outerJoinObject["label_alias_object"] not in self.orderedObjectList and innerJoinObject["label_alias_object"] in self.orderedObjectList:
						intermediateJoin = join(rightJoinObject, aliasedLink, innerJoinCondition)
						joinObject = join(outerJoinObject["label_alias_object"], intermediateJoin, outerJoinCondition, isouter=True)
						self.orderedObjectList.append(outerJoinObject["label_alias_object"])

					elif outerJoinObject["label_alias_object"] in self.orderedObjectList and innerJoinObject["label_alias_object"] not in self.orderedObjectList:
						self.logger.warn("Case not built out 2")

					elif outerJoinObject["label_alias_object"] not in self.orderedObjectList and innerJoinObject["label_alias_object"] not in self.orderedObjectList:
						self.logger.warn("Case not built out 3")

				elif rightJoinObject is not None and joinObject is not None:

					if innerJoinObject["label_alias_object"] in self.orderedObjectList and outerJoinObject["label_alias_object"] in self.orderedObjectList:
						intermediateJoin = join(rightJoinObject, aliasedLink, innerJoinCondition)
						joinObject = join(joinObject, intermediateJoin, outerJoinCondition, isouter=True)

					elif outerJoinObject["label_alias_object"] not in self.orderedObjectList and ["label_alias_object"] in self.orderedObjectList:
						self.logger.warn("Case not built out 1")

					elif outerJoinObject["label_alias_object"] in self.orderedObjectList and innerJoinObject["label_alias_object"] not in self.orderedObjectList:
						self.logger.warn("Case not built out 2")

					elif outerJoinObject["label_alias_object"] not in self.orderedObjectList and innerJoinObject["label_alias_object"] not in self.orderedObjectList:
						self.logger.warn("Case not built out 3")
			except:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
				errorValue = traceback.format_exception_only(exc_type, exc_value)
				self.logger.error("Failure in aliasChoice: {}".format(stacktrace))
				self.errorList.append("Failure {}".format(errorValue))


			## end aliasChoice
			return joinObject


	def recursiveProcessWeakLink(self, inputObject, weakLinkDictionary, joinObject):
		"""Process the weak link and build join accordingly.

		Argument:
		  inputObject (BaseObject)  : Sqlalchemy ORM Object (BaseObject type).
		  weakLinkDictionary (dict) : Dictionary containing weakLinks.
		  joinObject 	(sqalchemy) : Sqlalchemy join object (sql query).
		"""
		if len(self.errorList) <= 0:
			try:
				## This is to avoid accessing same object again in recursion.
				for wLinkKeys,wLinkValue in weakLinkDictionary.items():

					(firstObjectKey, secondObjectKey) = wLinkKeys

					## This condition is used to view cardinality from
					## first-Object's perspective.
					if inputObject["label_alias_object"] == self.dictQueryContent["objects"][firstObjectKey]["label_alias_object"]:
						minCardinality = self.dictQueryContent["objects"][secondObjectKey]["minimum"]

						if minCardinality == 0:
							aliasedLink = aliased(self.validWeakLinks[wLinkValue["class_name"]], name = wLinkValue["label"])
							## Check if the aliased link exist in orderedList.
							if inspect(aliasedLink).name not in self.orderedObjectList:
								secondLinks = dict()
								secondObject = self.dictQueryContent["objects"][secondObjectKey]
								secondLabelName = secondObject.get("label","")
								# Getting all other links around second object.
								if secondLabelName == "":
									secondLabelName = secondObject.get("class_name","")
								## Gathering links around the object with
								## cardinality 0 so that we can process those
								## links first.
								for secondKeySet,secondValues in self.linkDictionary.items():
									if secondLabelName in secondKeySet:
										secondLinks[secondKeySet] = secondValues
								## Deleting the current link, which will be processed later.
								val = secondLinks[wLinkKeys]
								del secondLinks[wLinkKeys]
								del self.linkDictionary[wLinkKeys]
								## The function below is used to create new join
								## based on the secondObject and links arond
								## secondLinks. The temp linchpin perspective
								## object is set as traversed so that in case of
								## circular recursion we don't touch that
								## object until that point.
								self.orderedObjectList.append(self.dictQueryContent["objects"][firstObjectKey]["label_alias_object"])
								rightJoinObject = self.recurseObjects(secondObject, secondLinks, None)
								## The for loop below is to remove the added
								## abject firstObject["label_alias_object"].
								## so that in the case of circular recursion
								## the same object is not touched again.
								indexValue = None
								for item in self.orderedObjectList:
									if item == self.dictQueryContent["objects"][firstObjectKey]["label_alias_object"]:
										indexValue = self.orderedObjectList.index(item)
										break
								removed = self.orderedObjectList.pop(indexValue)
								self.linkDictionary[wLinkKeys] = val
								self.orderedObjectList.append(inspect(aliasedLink).name)
								innerJoinCondition =  getattr(self.dictQueryContent["objects"][secondObjectKey]["label_alias_object"].c, "object_id") == getattr(aliasedLink, "second_id")
								innerJoinObject = self.dictQueryContent["objects"][secondObjectKey]
								outerJoinCondition =  getattr(self.dictQueryContent["objects"][firstObjectKey]["label_alias_object"].c, "object_id") == getattr(aliasedLink, "first_id")
								outerJoinObject = self.dictQueryContent["objects"][firstObjectKey]

								if str(innerJoinCondition) not in self.strJoinList and str(outerJoinCondition) not in self.strJoinList:
									self.strJoinList.append(str(innerJoinCondition))
									self.strJoinList.append(str(outerJoinCondition))

								joinObject = self.aliasChoice(rightJoinObject=rightJoinObject, joinObject=joinObject, innerJoinCondition=innerJoinCondition, outerJoinCondition=outerJoinCondition, aliasedLink=aliasedLink, innerJoinObject=innerJoinObject, outerJoinObject=outerJoinObject, firstorSecond=False)

							else:
								pass


						elif minCardinality > 0:
							aliasedLink = aliased(self.validWeakLinks[wLinkValue["class_name"]], name = wLinkValue["label"])
							if inspect(aliasedLink).name not in self.orderedObjectList:
								joinObject = self.createWeakLink(inputObject, wLinkKeys, wLinkValue, joinObject)
							else:
								pass

					## The condition below is used to view cardinality from
					## second-Object's peespective.
					elif inputObject["label_alias_object"] == self.dictQueryContent["objects"][secondObjectKey]["label_alias_object"]:
						minCardinality = self.dictQueryContent["objects"][firstObjectKey]["minimum"]

						if  minCardinality == 0:
							aliasedLink = aliased(self.validWeakLinks[wLinkValue["class_name"]], name = wLinkValue["label"])
							## check if the aliased link exist in the orderedList.
							if inspect(aliasedLink).name not in self.orderedObjectList:
								firstLinks = dict()
								firstObject = self.dictQueryContent["objects"][firstObjectKey]
								firstLabelName = firstObject.get("label","")
								# Getting all the oter links around the first object.
								if firstLabelName == "":
									firstLabelName = firstObject.get("class_name","")
								## Gathering links around the object with
								## cardinality 0 so that we can process
								## those links first.
								for firstKeySet,firstValues in self.linkDictionary.items():
									if  firstLabelName in firstKeySet:
										firstLinks[firstKeySet] = firstValues
								## Deleting the current link, which will be processed later.
								val = firstLinks[wLinkKeys]
								del firstLinks[wLinkKeys]
								del self.linkDictionary[wLinkKeys]
								## The function below is used to create new join
								## based on the firstObject and links arond
								## firstLinks acts as linchpin
								self.orderedObjectList.append(self.dictQueryContent["objects"][secondObjectKey]["label_alias_object"])
								rightJoinObject = self.recurseObjects(firstObject, firstLinks, None)
								## The for loop below is to remove the added
								## object firstObject["label_alias_object"].
								## so that in the case of circular recursion
								## the same object is not touched again.
								indexValue = None
								for item in self.orderedObjectList:
									if item == self.dictQueryContent["objects"][secondObjectKey]["label_alias_object"]:
										indexValue = self.orderedObjectList.index(item)
										break
								removed = self.orderedObjectList.pop(indexValue)
								self.linkDictionary[wLinkKeys] = val
								self.orderedObjectList.append(inspect(aliasedLink).name)
								outerJoinCondition =  getattr(self.dictQueryContent["objects"][secondObjectKey]["label_alias_object"].c, "object_id") == getattr(aliasedLink, "second_id")
								outerJoinObject = self.dictQueryContent["objects"][secondObjectKey]
								innerJoinCondition =  getattr(self.dictQueryContent["objects"][firstObjectKey]["label_alias_object"].c, "object_id") == getattr(aliasedLink, "first_id")
								innerJoinObject = self.dictQueryContent["objects"][firstObjectKey]

								if str(innerJoinCondition) not in self.strJoinList and str(outerJoinCondition) not in self.strJoinList:
									self.strJoinList.append(str(innerJoinCondition))
									self.strJoinList.append(str(outerJoinCondition))
								joinObject = self.aliasChoice(rightJoinObject=rightJoinObject, joinObject=joinObject, innerJoinCondition=innerJoinCondition, outerJoinCondition=outerJoinCondition, aliasedLink=aliasedLink, innerJoinObject=innerJoinObject, outerJoinObject=outerJoinObject)

							else:
								pass

						elif minCardinality > 0:
							aliasedLink = aliased(self.validWeakLinks[wLinkValue["class_name"]], name = wLinkValue["label"])
							if inspect(aliasedLink).name not in self.orderedObjectList:
								joinObject = self.createWeakLink(inputObject, wLinkKeys, wLinkValue, joinObject)
							else:
								pass

					## this is the recursive step for processing connected link.
					joinObject = self.traverse(wLinkKeys, joinObject)

			except:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				errorValue = traceback.format_exception_only(exc_type, exc_value)
				stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
				self.logger.error("Failure in recursiveProcessWeakLink: {}".format(stacktrace))
				self.errorList.append("Failure {}".format(errorValue))

			## end recursiveProcessWeakLink
			return joinObject


	def recursiveProcessStrongLink(self, inputObject, strongLinkDictionary, joinObject):
		"""Process the strong link and build join accordingly.

		Argument:
		  inputObject (BaseObject)    : Sqlalchemy ORM Object.
		  strongLinkDictionary (dict) : Dictionary containing strongLinks.
		  joinObject (sqlalchemy)     : Sqlalchemy join object (sql query).
		"""
		if len(self.errorList) <= 0:
			try:
				## Iterate through links and process the query to create join.
				for sLinkKeys,sLinkValue in strongLinkDictionary.items():
					(firstObjectKey, secondObjectKey) = sLinkKeys

					## The condition below is used to view cardinality from
					## first-Object's peespective.
					if inputObject["label_alias_object"] == self.dictQueryContent["objects"][firstObjectKey]["label_alias_object"]:
						minCardinality = self.dictQueryContent["objects"][secondObjectKey]["minimum"]

						if minCardinality == 0:
							aliasedLink = aliased(self.validStrongLinks[sLinkValue["class_name"]], name = sLinkValue["label"])
							## check if the aliased link exist in the orderedList.
							if inspect(aliasedLink).name not in self.orderedObjectList:
								secondLinks = dict()
								secondObject = self.dictQueryContent["objects"][secondObjectKey]
								secondLabelName = secondObject.get("label","")
								# Getting all the other links around the second
								## object.
								if secondLabelName == "":
									secondLabelName = secondObject.get("class_name","")
								## Gathering links around the object with min 0,
								## so that we can process those links first.
								for secondKeySet,secondValues in self.linkDictionary.items():
									if secondLabelName in secondKeySet:
										secondLinks[secondKeySet] = secondValues

								## Deleting the current link, which will be
								## processed later.
								val = secondLinks[sLinkKeys]
								del secondLinks[sLinkKeys]
								del self.linkDictionary[sLinkKeys]
								## The function below is used to create new join
								## based on secondObject and links arond
								## secondLinks.
								self.orderedObjectList.append(self.dictQueryContent["objects"][firstObjectKey]["label_alias_object"])
								rightJoinObject = self.recurseObjects(secondObject, secondLinks, None)
								## The for loop below is to remove the added
								## abject firstObject["label_alias_object"]. So
								## that in the case of circular recursion the
								## same object is not touched again.
								indexValue = None
								for item in self.orderedObjectList:
									if item == self.dictQueryContent["objects"][firstObjectKey]["label_alias_object"]:
										indexValue = self.orderedObjectList.index(item)
										break
								removed = self.orderedObjectList.pop(indexValue)
								self.linkDictionary[sLinkKeys] = val
								self.orderedObjectList.append(inspect(aliasedLink).name)
								innerJoinCondition =  getattr(self.dictQueryContent["objects"][secondObjectKey]["label_alias_object"].c, "object_id") == getattr(aliasedLink, "second_id")
								innerJoinObject = self.dictQueryContent["objects"][secondObjectKey]
								outerJoinCondition =  getattr(self.dictQueryContent["objects"][firstObjectKey]["label_alias_object"].c, "object_id") == getattr(aliasedLink, "first_id")
								outerJoinObject = self.dictQueryContent["objects"][firstObjectKey]

								if str(innerJoinCondition) not in self.strJoinList and str(outerJoinCondition) not in self.strJoinList:
									self.strJoinList.append(str(innerJoinCondition))
									self.strJoinList.append(str(outerJoinCondition))

								joinObject = self.aliasChoice(rightJoinObject=rightJoinObject, joinObject=joinObject, innerJoinCondition=innerJoinCondition, outerJoinCondition=outerJoinCondition, aliasedLink=aliasedLink, innerJoinObject=innerJoinObject, outerJoinObject=outerJoinObject, firstorSecond=False)

							else:
								pass

						elif minCardinality > 0:
							aliasedLink = aliased(self.validStrongLinks[sLinkValue["class_name"]], name = sLinkValue["label"])
							if inspect(aliasedLink).name not in self.orderedObjectList:
								joinObject = self.createStrongLink(inputObject, sLinkKeys, sLinkValue, joinObject)
							else:
								pass

					## The condition below is used to view cardinality from second-Object's
					## perspective.
					elif inputObject["label_alias_object"] == self.dictQueryContent["objects"][secondObjectKey]["label_alias_object"]:
						minCardinality = self.dictQueryContent["objects"][firstObjectKey]["minimum"]

						if  minCardinality == 0:
							aliasedLink = aliased(self.validStrongLinks[sLinkValue["class_name"]], name = sLinkValue["label"])
							## check if the aliased link exist in orderedList.
							if inspect(aliasedLink).name not in self.orderedObjectList:
								firstLinks = dict()
								firstObject = self.dictQueryContent["objects"][firstObjectKey]
								firstLabelName = firstObject.get("label","")
								# Get all the other links around first object.
								if firstLabelName == "":
									firstLabelName = firstObject.get("class_name","")
								## Get links around the object with minimum 0
								## so that we can process those links first.
								for firstKeySet,firstValues in self.linkDictionary.items():
									if  firstLabelName in firstKeySet:
										firstLinks[firstKeySet] = firstValues
								## Delete the current link, which will be
								## processed later.
								val = firstLinks[sLinkKeys]
								del firstLinks[sLinkKeys]
								del self.linkDictionary[sLinkKeys]
								self.orderedObjectList.append(self.dictQueryContent["objects"][secondObjectKey]["label_alias_object"])
								rightJoinObject = self.recurseObjects(firstObject, firstLinks, None)
								## The for loop below is to remove the added
								## object firstObject["label_alias_object"].
								## so that in the case of circular recursion
								## the same object is not touched again.
								indexValue = None
								for item in self.orderedObjectList:
									if item == self.dictQueryContent["objects"][secondObjectKey]["label_alias_object"]:
										indexValue = self.orderedObjectList.index(item)
										break
								removed = self.orderedObjectList.pop(indexValue)
								self.linkDictionary[sLinkKeys] = val
								self.orderedObjectList.append(inspect(aliasedLink).name)
								outerJoinCondition =  getattr(self.dictQueryContent["objects"][secondObjectKey]["label_alias_object"].c, "object_id") == getattr(aliasedLink, "second_id")
								outerJoinObject = self.dictQueryContent["objects"][secondObjectKey]
								innerJoinCondition =  getattr(self.dictQueryContent["objects"][firstObjectKey]["label_alias_object"].c, "object_id") == getattr(aliasedLink, "first_id")
								innerJoinObject = self.dictQueryContent["objects"][firstObjectKey]

								if str(outerJoinCondition) not in self.strJoinList and str(innerJoinCondition) not in self.strJoinList:
									self.strJoinList.append(str(outerJoinCondition))
									self.strJoinList.append(str(innerJoinCondition))

								joinObject = self.aliasChoice(rightJoinObject=rightJoinObject, joinObject=joinObject, innerJoinCondition=innerJoinCondition, outerJoinCondition=outerJoinCondition, aliasedLink=aliasedLink, innerJoinObject=innerJoinObject, outerJoinObject=outerJoinObject)

							else:
								pass

						elif minCardinality > 0:
							aliasedLink = aliased(self.validStrongLinks[sLinkValue["class_name"]], name = sLinkValue["label"])
							if inspect(aliasedLink).name not in self.orderedObjectList:
								joinObject = self.createStrongLink(inputObject, sLinkKeys, sLinkValue, joinObject)
							else:
								pass
					## takes care of graph traversal
					joinObject = self.traverse(sLinkKeys, joinObject)

			except:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
				errorValue = traceback.format_exception_only(exc_type, exc_value)
				self.logger.error("Failure in recursiveProcessStrongLink: {}".format(stacktrace))
				self.errorList.append("Failure {}".format(errorValue))


			## end recursiveProcessStrongLink
			return joinObject


	def _customSort(self, inputObject):
		"""Decorator like function used for custom sorting, internal.

		Arguments:
		  inputObject (BaseObject) : Sqlalchemy ORM Object.
		"""

		def _createFunction(inputEntry):
			if inputObject["label"] == inputEntry[0][0]:
				return int(self.dictQueryContent["objects"][inputEntry[0][1]]['minimum'])
			else:
			  return int(self.dictQueryContent["objects"][inputEntry[0][0]]['minimum'])

		return _createFunction


	def recurseObjects(self, inputObject, inputLinks, joinObject):
		"""This function traverses json & stores joins and BaseClass Object.

		Arguments:
		  inputLinks (dict)        : Dictionary containing links
		  inputObject (BaseObject) : Sqlalchemy ORM Object.
		  joinObject (sqlqlchemy)  : Sqlalchemy join object (sql query).
		"""
		if len(self.errorList) <= 0:
			try:
				## This is to break if the circular recursion traversal.
				if inputObject["label_alias_object"] not in self.perspectiveObjects:
					self.perspectiveObjects.append(inputObject["label_alias_object"])

					strongLinkDictionary = dict()
					weakLinkDictionary = dict()
					## Process the strong and weak link.
					for linkKeys, linkValue in inputLinks.items():
						if linkValue["class_name"] in self.validStrongLinks.keys():
							strongLinkDictionary[linkKeys] = linkValue
						elif linkValue["class_name"] in self.validWeakLinks.keys():
							weakLinkDictionary[linkKeys] = linkValue
						else:
							## If the link is an invalid link, we break out of
							## the recursion.
							self.errorList.append("Error in recurseObjects : Invalid link name.")
							self.logger.warn("This is not a proper link, please check the link name {invalidLinkName!r}", invalidLinkName=linkValue["class_name"])
							self.logger.error("Breaking out of recursion loop")
							return
					## creates an ordered dictionary
					## If we have multiple links coming from an object or going
					## to an object, there is no order in which they are
					## processed. But now, if cardinality is more than one we
					## processes them in largest cardinality first then the
					## smallest. (inner join first then outer join)
					checker= self.traversalStructure.get(inputObject.get("labels"),-1)
					if checker !=-1:
						pass
					else:
						tmp = dict()
						tmp['links'] =[]
						tmp['labels'] =[]
						self.traversalStructure[inputObject.get("label")] = tmp
					if strongLinkDictionary:
						tempList = list(strongLinkDictionary.items())
						sortFunction = self._customSort(inputObject)
						tempList.sort(key=sortFunction,reverse=True)
						orderedStrongLinkDictionary =  OrderedDict(tempList)
						for item in orderedStrongLinkDictionary.keys():
							(obj1, obj2) = item
							if obj1 == inputObject.get("label"):
								if obj2 not in self.orderedObjectList:
									self.traversalStructure[inputObject.get("label")]['labels'].append(obj2)
									self.traversalStructure[inputObject.get("label")]['links'].append(orderedStrongLinkDictionary[item]['label'])
							else:
								if obj1 not in self.orderedObjectList:
									self.traversalStructure[inputObject.get("label")]['labels'].append(obj1)
									self.traversalStructure[inputObject.get("label")]['links'].append(orderedStrongLinkDictionary[item]['label'])
						joinObject = self.recursiveProcessStrongLink(inputObject, orderedStrongLinkDictionary, joinObject)

					if weakLinkDictionary:
						tempList = list(weakLinkDictionary.items())
						sortFunction =self._customSort(inputObject)
						tempList.sort(key=sortFunction,reverse=True)
						orderedWeakLinkDictionary =  OrderedDict(tempList)
						for item in orderedWeakLinkDictionary.keys():
							(obj1, obj2) = item
							if obj1 == inputObject.get("label"):
								if obj2 not in self.orderedObjectList:
									self.traversalStructure[inputObject.get("label")]['labels'].append(obj2)
									self.traversalStructure[inputObject.get("label")]['links'].append(orderedWeakLinkDictionary[item]['label'])
							else:
								if obj1 not in self.orderedObjectList:
									self.traversalStructure[inputObject.get("label")]['labels'].append(obj1)
									self.traversalStructure[inputObject.get("label")]['links'].append(orderedWeakLinkDictionary[item]['label'])
						joinObject = self.recursiveProcessWeakLink( inputObject, orderedWeakLinkDictionary, joinObject)
				else:
					objectName= inputObject.get("label")
					if objectName =="":
						objectName= inputObject.get("class_name")

			except:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
				self.errorList.append("Failure in recurseObjects: {stacktrace}".format(stacktrace))
				self.logger.error("Failure in recurseObjects: {}".format(stacktrace))

			## end recurseObjects
			return joinObject


	def runQuery(self):
		"""Wrapper for decisions on output format."""
		queryResult = {}
		joinObject, standAloneFlag = self.processQuery()
		if standAloneFlag:
			## No links... just a bunch of objects
			queryResult = self.standaloneResults(joinObject, True)
		else:
			intermediateResults = self.executeAndReturnJson(joinObject)
			## Function to call depends on the results format
			if self.resultsFormat == 'Flat':
				queryResult = self.preprocessFlatResults(intermediateResults)
			elif self.resultsFormat == 'Nested':
				queryResult = self.preprocessNestedResults(intermediateResults)
			elif self.resultsFormat == 'Nested-Simple':
				queryResult = self.preprocessSimpleNestedResults(intermediateResults)

		## CS: Using conversion between JSON/string to avoid errors like this:
		## TypeError: datetime.datetime(2016, 4, 8, 11, 22, 3, 84913) is not JSON
		## serializable, which happens on all Datetime columns as we try to store
		## them back in the database after creating chunk boundaries.
		resultStr = json.dumps(queryResult, default=utils.customJsonDumpsConverter)
		queryResult = json.loads(resultStr)

		## end runQuery
		return queryResult


	def processQuery(self):
		"""Initial funtion given for processing the input json query."""
		if len(self.errorList) <= 0:
			try:
				thisObject= None
				joinObject = None
				## The flag is to process standalone object querying.
				flag = False
				if len(self.dictQueryContent["objects"].keys()) == 1:
					flag = True
					for mkey,obj in self.dictQueryContent["objects"].items():
						## should linchpin be present in the object
						self.orderedObjectList.append(obj["label_alias_object"])
						joinObject= obj["label_alias_object"]
				else:
					for mkey,obj in self.dictQueryContent["objects"].items():
						## Checking for existance of linchpin object.
						if "linchpin" in obj.keys():
							thisObject = obj
							linchpinLink = dict()
							## Finding the links relevent to the linchpin.
							## creating the edgelists for tree traversal.
							labelName = obj.get("label","")
							for keySet,values in self.linkDictionary.items():
								if labelName == "":
									labelName = obj.get("class_name","")
								if labelName in keySet:
									linchpinLink[keySet] = values
							self.traversedObjectSet.add(labelName)
							## calling the recursive query find the link
							## connected to this link.
							joinObject = self.recurseObjects(thisObject, linchpinLink, joinObject)
							return joinObject, flag
					self.logger.warn("No linchpin assigned in query: {}", self.dictQueryContent)
					self.errorList.append("No linchpin assigned in query")
					raise Exception("No linchpin assigned")
			except:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
				errorValue = traceback.format_exception_only(exc_type, exc_value)
				self.logger.error("Failure in processQuery: {}".format(stacktrace))
				self.errorList.append("Failure {}".format(errorValue))

			## end processQuery
			return joinObject, flag


	def buildQuery(self, inputJoin):
		"""Once all the required variables are populated start building this out.

		Arguments:
		  inputJoin (sqlalchemy) : Sqlalchemy join object (sql query).
		"""
		if len(self.errorList) <= 0:
			try:
				self.logger.debug("Initiating Query build operation")
				for condition in self.strJoinList:
					pass
				queryObject = self.dbSession.query(*[item for item in self.orderedObjectList if type(item)!= type(str())]).select_entity_from(inputJoin)
				self.dbSession.commit()
				return queryObject

			except:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
				errorValue = traceback.format_exception_only(exc_type, exc_value)
				self.logger.error("Failure in buildQuery: {}".format(stacktrace))
				self.errorList.append("Failure {}".format(errorValue))

		## end buildQuery
		return

	## todo edit this.
	def jsonObjectConverter(self, inputItem):
		"""This function transforms each sqlresult into JSON.

		Argument:
		  inputItem (list) : List containing the results for each sql query.
		"""
		try:
			perEntryObject= dict()
			for eachObject in self.orderedObjectList:
				if type(eachObject) != type(str()):
					self.dictQueryContent['objects'][eachObject.name]
					dataKeys = eachObject.columns.keys()
					dataCount = len(dataKeys)
					data = dict()
					for i in range(0,dataCount):
						data[dataKeys[i]] = inputItem[i]
					object_id = data["object_id"]
					object_type = data["object_type"]
					## based on the flag the private attributes are retained
					## or removed
					for privateAttribute in self.privateAttributes:
						## the givenAttributes keeps track if the private
						## attributes are asked in the initial query
						## in the first place.
						if privateAttribute not in self.givenAttributes[eachObject.name]:
							if privateAttribute in data.keys():
								del data[privateAttribute]

					## CS: previously only covered Nested; module needs reworked
					if self.removeEmptyAttributes:
						for thisKey in list(data.keys()):
							if data[thisKey] is None:
								del data[thisKey]

					# else:
					# 	for privateAttribute in self.privateAttributes:
					# 		if privateAttribute in data.keys():
					# 			del data[privateAttribute]
					tempdict = dict()
					tempdict["data"] = data
					## Identifying the class_name
					for classObject in self.validClassObjects.values():
						if classObject['classObject'].__tablename__ == object_type:
							tempdict["class_name"] = inspect(classObject['classObject']).mapper.class_.__name__
							break
					tempdict["identifier"] = object_id
					tempdict["label"] = self.dictQueryContent['objects'][eachObject.name]["label"]
					self.queriedObjects[object_id] = tempdict
					perEntryObject[tempdict["label"]] = tempdict
					data = dict()
					tempdict = dict()
					object_id = None
					object_type = None
					inputItem = inputItem[dataCount:]
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
			errorValue = traceback.format_exception_only(exc_type, exc_value)
			self.logger.error("Failure in jsonObjectConverter: {}".format(stacktrace))
			self.errorList.append("Failure {}".format(errorValue))

		## end jsonObjectConverter
		return perEntryObject


	def buildNestedStructure(self, inputJson, line, descriptor, processedOnce, index=0):
		"""Used for creating Nested JSON structure from the sql results.

		Arguments:
		  inputJson (dict)			: result dictionary.
		  line (dict) 				: dict for each sql line.
		  descriptor (ordered dict) : ordered dict containing the traversal structure.
		  index (int)				: index for descriptor.
		"""
		try:
			## Descriptor holds the traversal structure of the the sql query.
			## which will be used to guide along the mapset.
			dictKey = list(descriptor.keys())[index]
			dataHandle = inputJson.get(dictKey,{})
			entryOnbjectId = line.get(dictKey).get('identifier')
			processedOnce.append(dictKey)
			entryValue = line.get(dictKey)
			## removing empty attributes:
			if self.removeEmptyAttributes:
				if "attributesIsEmpty" in self.dictQueryContent["objects"][entryValue["label"]].keys():
					## removing the null and empty attributes, based on removeEmptyAttributes flag.
					for eachColumn in list(entryValue["data"].keys()):
						if entryValue["data"][eachColumn] is None:
							del entryValue["data"][eachColumn]
			if dataHandle.get(entryOnbjectId, False):
				pass
			else:
				dataHandle[entryOnbjectId] = {"id_data":None}
				dataHandle[entryOnbjectId]["id_data"] = entryValue

			nest = dataHandle[entryOnbjectId].get("nested",-1)
			if nest==-1:
				dataHandle[entryOnbjectId]["nested"] = OrderedDict()
			nest=dataHandle[entryOnbjectId]["nested"]
			if len(descriptor[dictKey]['labels'])>0:
				for nDictKey in descriptor[dictKey]['labels']:
						nestHandle = nest.get(nDictKey,-1)
						if nestHandle == -1:
							nest[nDictKey] = {}
						entryOnbjectId= line.get(nDictKey).get('identifier')
						entryValue = line.get(nDictKey)
						## removing empty attributes:
						if self.removeEmptyAttributes:
							if "attributesIsEmpty" in self.dictQueryContent["objects"][entryValue["label"]].keys():
								## removing the null and empty attributes, based on removeEmptyAttributes flag.
								for eachColumn in list(entryValue["data"].keys()):
									if entryValue["data"][eachColumn] is None:
										del entryValue["data"][eachColumn]
						objHandle =nest[nDictKey].get(entryOnbjectId,-1)
						if objHandle ==-1:
							if entryOnbjectId is not None:
								nest[nDictKey][entryOnbjectId]={"id_data":None}
								nest[nDictKey][entryOnbjectId]["id_data"] = entryValue
								if nDictKey in descriptor.keys():
									if nDictKey not in processedOnce:
										lstIndex =list(descriptor.keys()).index(nDictKey)
										nest= self.buildNestedStructure(nest, line, descriptor, processedOnce, lstIndex)
									else:
										pass
						else:
							if entryOnbjectId is not None:
								if nDictKey in descriptor.keys():
									if nDictKey not in processedOnce:
										lstIndex =list(descriptor.keys()).index(nDictKey)
										nest = self.buildNestedStructure(nest, line, descriptor, processedOnce, lstIndex)
									else:
										pass
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
			errorValue = traceback.format_exception_only(exc_type, exc_value)
			self.logger.error("Failure in buildNestedStructure: {}".format(stacktrace))
			self.errorList.append("Failure {}".format(errorValue))

		## end buildNestedStructure
		return inputJson


	def filterFinalResults(self, dataHandle, dictKey):
		""" This function is used to reduce the mapSet based on cardinality.

		Arguments :
		  dataHandle (dictionary) : Dictionary of mapset.
		  dictKey (string)		  : String containin the dictionary information.
		"""
		recursionFlag = False
		try:
			for object_id in list(dataHandle.keys()):
				## CS: why are we using a class variable here to represent the
				## recursionFlag, instead of passing around a local variable?
				recursionFlag = False
				if "nested" in dataHandle[object_id].keys():
					nest = dataHandle[object_id].get("nested", {})
					for nDictKey in self.traversalStructure[dictKey]['labels']:
						if nDictKey in nest.keys():
							## recursion
							recursionFlag = self.filterFinalResults(nest[nDictKey], nDictKey)
							leftMaximum = self.dictQueryContent["objects"][nDictKey]["maximum"]
							leftMinimum = self.dictQueryContent["objects"][nDictKey]["minimum"]
							if nDictKey in nest.keys():
								if leftMinimum <= len(nest[nDictKey]) and leftMaximum >= len(nest[nDictKey]):
									pass
								else:
									recursionFlag = True
							if recursionFlag == True:
								del nest[nDictKey]
								## CS: when the cardinality doesn't match for a
								## child, the parent needs removed; allow this
								## to go back up a level
								#if leftMinimum == 0:
								if leftMinimum == 0 and leftMaximum != 0:
									recursionFlag = False
								else:
									## TODO : delete the parent: dataHandle[object_id]
									del dataHandle[object_id]
									break

		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
			errorValue = traceback.format_exception_only(exc_type, exc_value)
			self.logger.error("Failure in filterFinalResults: {}".format(stacktrace))
			self.errorList.append("Failure {}".format(errorValue))

		## end filterFinalResults
		return recursionFlag


	def standaloneResults(self, inputJoin, Flag):
		""" Created query is executed here and the results are converted to
		mapSet structure.

		Argument:
		  inputJoin (sqlalchemy object) : The query object which is used for execution.
		"""
		try:
			result = self.buildQuery(inputJoin)
			objectsDictionary = dict()
			label = None
			for item in self.dictQueryContent["objects"].values():
				label=item["label"]
			if result is not None:
				sqlResults = result.all()
			if Flag:
				objects = dict()
				objects["objects"] =[]
				## The flag is to handle the standalone objects.
				for item in sqlResults:
					line = self.jsonObjectConverter(item)
					solution= list(line.values())
					objects["objects"].append(solution[0])
			else:
				objects = dict()
				objects[label] = []
				for item in sqlResults:
					line = self.jsonObjectConverter(item)
					solution= list(line.values())
					objects[label].append(solution[0])

		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
			errorValue = traceback.format_exception_only(exc_type, exc_value)
			self.logger.error("Failure in standaloneResults: {}".format(stacktrace))
			self.errorList.append("Failure {}".format(errorValue))

		## end standaloneResults
		return objects


	def executeAndReturnJson(self, inputJoin):
		""" Created query is executed here and the results are converted to
		mapSet structure.

		Argument:
		  inputJoin (sqlalchemy object) : The query object which is used for execution.
		"""
		sqlResults = None
		nestedDictionary = None
		try:
			result = self.buildQuery(inputJoin)
			objectsDictionary = dict()
			for item in self.dictQueryContent["objects"].values():
				pass
			if result is not None:
				sqlResults = result.all()

			nestedDictionary ={list(self.traversalStructure.keys())[0]:{}}

			if len(sqlResults)>0:
				for item in sqlResults:
					line = self.jsonObjectConverter(item)
					processedOnce =[]
					nestedDictionary = self.buildNestedStructure(nestedDictionary, line, self.traversalStructure, processedOnce=processedOnce, index=0)
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
			errorValue = traceback.format_exception_only(exc_type, exc_value)
			self.logger.error("Failure in executeAndReturnJson: {}".format(stacktrace))
			self.errorList.append("Failure {}".format(errorValue))

		## end executeAndReturnJson
		return nestedDictionary


	def preprocessNestedResults(self, intermediateResults):

		"""This is an itermediate method, which acts as an wrapper to call the
		the methods createFinalResult and returnResults.
		intermediateResults (dict) : Dictionary containing the sql results
		transformed to map structure.

		Argument:
		  intermediateResults (dict) : Dictionary containing the mapSet.
		"""
		try:
			nestedResults = dict()
			dictKey = list(self.traversalStructure.keys())[0]
			dataHandle = intermediateResults.get(dictKey)
			finalResult = dict()
			## the filter result is to remove the results that doesnot fit the
			## cardinality.
			self.filterFinalResults(dataHandle, dictKey)
			nestedResults[dictKey] = []
			## The return nest results function transforms the mapset to
			## The nested-result format.
			self.returnNestedResults(dataHandle, dictKey, nestedResults[dictKey])
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
			errorValue = traceback.format_exception_only(exc_type, exc_value)
			self.logger.error("Failure in preprocessNestedResults: {}".format(stacktrace))
			self.errorList.append("Failure {}".format(errorValue))

		## end preprocessNestedResults
		return nestedResults


	def preprocessSimpleNestedResults(self, intermediateResults):

		"""This is an itermediate method, which acts as an wrapper to call the
		the methods createFinalResult and returnResults.
		intermediateResults (dict) : Dictionary containing the sql results
		transformed to map structure.

		Argument:
		  intermediateResults (dict) : Dictionary containing the mapSet.
		"""
		try:
			nestedResults = dict()
			dictKey = list(self.traversalStructure.keys())[0]
			dataHandle = intermediateResults.get(dictKey)
			finalResult = dict()
			## the filter result is to remove the results that doesnot fit the
			## cardinality.
			self.filterFinalResults(dataHandle, dictKey)
			nestedResults = []
			## The return nest results function transforms the mapset to
			## The nested-result format.
			self.returnSimpleNestedResults(dataHandle, dictKey, nestedResults)
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
			errorValue = traceback.format_exception_only(exc_type, exc_value)
			self.logger.error("Failure in preprocessSimpleNestedResults: {}".format(stacktrace))
			self.errorList.append("Failure {}".format(errorValue))

		## end preprocessSimpleResults
		return nestedResults



	def returnNestedResults(self, dataHandle, dictKey, nestedResults):
		"""This function is used to transform the mapSet into nested result format.

		Arguments:
		  dataHandle (dict)   : Dictionary of the mapSet before processing.
		  dictKey (str)       : String containing the key for traversalstructure.
		 nestedResults (list) : List handle for the dictKey.
		"""
		try:
			for object_id in dataHandle:
				MasterTempDict = dataHandle.get(object_id, {}).get("id_data", {})
				# if "container" in MasterTempDict["data"].keys():
				# 	del MasterTempDict["data"]["container"]
				MasterTempDict["children"] = dict()
				if "nested" in dataHandle[object_id].keys():
					nest = dataHandle[object_id].get("nested")
					for nDictKey in self.traversalStructure[dictKey]["labels"]:
						if nDictKey in nest.keys():
							MasterTempDict["children"][nDictKey] = []
							self.returnNestedResults(nest[nDictKey], nDictKey, MasterTempDict["children"][nDictKey])
							for item in nest:
								masterList = []
								if nest[item]:
									for key in nest[item]:
										## parent_id and child_id are in respect
										## to cardinality.
										## key is the inner object's id.
										## item is the inner object's label.
										temp_dict =nest[item][key]["id_data"]
										parentLabel= dataHandle[object_id]["id_data"]["label"]
										childLabel= nest[item][key]["id_data"]["label"]
										flag = False
										linkHandle = self.linkDictionary.get((parentLabel, childLabel), "")
										if linkHandle =="":
											flag = True
											linkHandle = self.linkDictionary.get((childLabel, parentLabel))
										if linkHandle['label'] in self.traversalStructure[parentLabel]['links']:
											if flag:
												temp_dict["link_type"] = linkHandle["class_name"]
												temp_dict["link_direction"] = "up"
											else:
												temp_dict["link_type"] = linkHandle["class_name"]
												temp_dict["link_direction"] = "down"
										masterList.append(temp_dict)
								## Adding fix with if condition; the object is
								## being mutated so when children are getting
								## removed, the return from recursion errors
								## with "KeyError: 'children'" on the line below
								##   ---> MasterTempDict["children"][item] = masterList
								if 'children' in MasterTempDict:
									MasterTempDict['children'][item] = masterList
				nestedResults.append(MasterTempDict)

		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
			errorValue = traceback.format_exception_only(exc_type, exc_value)
			self.logger.error("Failure in returnNestedResults: {}".format(stacktrace))
			self.errorList.append("Failure {}".format(errorValue))

		## end returnNestedResults
		return


	def returnSimpleNestedResults(self, dataHandle, dictKey, nestedResults):
		"""This function is used to transform mapSet into simple flat.

		Arguments:
		  dataHandle (dict)   : Dictionary of the mapSet before processing.
		  dictKey (str)       : String containing the key for traversalstructure.
		 nestedResults (list) : List handle for the dictKey.
		"""
		try:
			for object_id in dataHandle:
				MasterTempDict = dataHandle.get(object_id, {}).get("id_data", {})
				MasterTempDict["children"] = []
				if "nested" in dataHandle[object_id].keys():
					nest= dataHandle[object_id].get("nested")
					for nDictKey in self.traversalStructure[dictKey]["labels"]:
						if nDictKey in nest.keys():
							MasterTempDict["children"] = []
							self.returnSimpleNestedResults(nest[nDictKey], nDictKey, MasterTempDict["children"])
							for item in nest:
								masterList = []
								if nest[item]:
									for key in nest[item]:
										## parent_id and child_id are in respect
										## to cardinality.
										## key is the inner object's id.
										## item is the inner object's label.
										temp_dict = nest[item][key]["id_data"]
										parentLabel = dataHandle[object_id]["id_data"]["label"]
										childLabel = nest[item][key]["id_data"]["label"]
										flag = False
										linkHandle = self.linkDictionary.get((parentLabel, childLabel), "")
										if linkHandle =="":
											flag = True
											linkHandle = self.linkDictionary.get((childLabel, parentLabel))
										if linkHandle['label'] in self.traversalStructure[parentLabel]['links']:
											if flag:
												temp_dict["link_type"] = linkHandle["class_name"]
												temp_dict["link_direction"] = "up"
											else:
												temp_dict["link_type"] = linkHandle["class_name"]
												temp_dict["link_direction"] = "down"
										masterList.append(temp_dict)
								for item in masterList:
									if item not in MasterTempDict.get("children", []):
										MasterTempDict["children"].append(item)
				if 'children' not in MasterTempDict:
					del MasterTempDict["children"]
				nestedResults.append(MasterTempDict)

		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
			errorValue = traceback.format_exception_only(exc_type, exc_value)
			self.logger.error("Failure in returnSimpleNestedResults: {}".format(stacktrace))
			self.errorList.append("Failure {}".format(errorValue))

		## end returnSimpleNestedResults
		return


	def returnFlatResults(self, dataHandle, dictKey, objects, linksDict):
		"""This function is used to transform the mapSet into flat result format.

		Arguments:
		  dataHandle (dict) : Dictionary of the mapSet before processing.
		  dictKey (str)     : String containing the key for traversalstructure.
		  objects (list)	: list of all objects.
		  linksDict (dict)	: list of links dictionary.
		"""
		try:
			for object_id in dataHandle:
				## Same object may be listed under two different labels, and so
				## we can't use just the object ID as the dict key; add the label
				uniqueKey = '{}.{}'.format(object_id, dataHandle[object_id]["id_data"]["label"])
				objects[object_id] = dataHandle[object_id]["id_data"]
				self.globalObjectManipulator[uniqueKey] = dataHandle[object_id]["id_data"]
				if "nested" in dataHandle[object_id].keys():
					nest = dataHandle[object_id].get("nested")
					for nDictKey in self.traversalStructure[dictKey]["labels"]:
						if nDictKey in nest.keys():
							self.returnFlatResults(nest[nDictKey], nDictKey, objects, linksDict)

					orderedList = list(self.globalObjectManipulator.keys())
					for objId1,objId2 in zip(orderedList,orderedList[1:]):
						## Fetching the label name for each object.
						objIdLbl1= self.globalObjectManipulator[objId1]["label"]
						objIdLbl2= self.globalObjectManipulator[objId2]["label"]
						## Below condition is to check if it is a valid link,
						flag = False
						linkHandle = self.linkDictionary.get((objIdLbl1, objIdLbl2))
						## CN: do we want to assume the order isn't explicit?
						## What if A->B gives different results than B->A ?!?
						if linkHandle is None:
							linkHandle = self.linkDictionary.get((objIdLbl2, objIdLbl1))
							flag = True
						if linkHandle['label'] in self.traversalStructure[objIdLbl1].get('links', []):
							## Up above I created the IDs with ID.Label, so just
							## cleaning that back off before adding to the result
							objId1Clean = objId1.split('.')[0]
							objId2Clean = objId2.split('.')[0]
							if flag:
								linksDict[(objId2, objId1)] = {"first_id":objId2Clean,"second_id":objId1Clean,"class_name":linkHandle['class_name'],"label":linkHandle['label']}
							else:
								linksDict[(objId2, objId1)] = {"first_id":objId1Clean,"second_id":objId2Clean,"class_name":linkHandle['class_name'],"label":linkHandle['label']}

					del self.globalObjectManipulator[uniqueKey]
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
			errorValue = traceback.format_exception_only(exc_type, exc_value)
			self.logger.error("Failure in returnFlatResults: {}".format(stacktrace))
			self.errorList.append("Failure {}".format(errorValue))

		## returnFlatResults
		return


	def preprocessFlatResults(self, intermediateResults):
		"""This is an itermediate method, which acts as an wrapper to call the
		the methods createFinalResult and returnResults.
		intermediateResults (dict) : Dictionary containing the sql results
		transformed to map structure.

		Argument:
		  intermediateResults (dict) : Dictionary containing the mapSet.
		"""
		finalResult = dict()
		try:
			objectsDict = {}
			linksDict = {}
			objectList = []
			linkList=[]
			dictKey = list(self.traversalStructure.keys())[0]
			dataHandle = intermediateResults.get(dictKey)
			## filterFinalResults is used to filter the result from the mapSet
			## based on the minimum and maximum of each object.
			self.filterFinalResults(dataHandle, dictKey)
			## returnFlatResults function transforms mapset to flat format.
			self.returnFlatResults(dataHandle, dictKey, objectsDict, linksDict)
			for objectValue in objectsDict.values():
				objectList.append(objectValue)
			for linkVal in linksDict.values():
				linkList.append(linkVal)
			finalResult["objects"] = objectList
			finalResult["links"] = linkList
			finalResult["source"] = "queryProcessing.py"

		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
			errorValue = traceback.format_exception_only(exc_type, exc_value)
			self.logger.error("Failure in preprocessFlatResults: {}".format(stacktrace))
			self.errorList.append("Failure {}".format(errorValue))

		# return preprocessFlatResults
		return finalResult
