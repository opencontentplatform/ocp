"""Module for building and managing cache used by result processing clients.

Classes:
  * ConstraintCache : build and manage cache structures

constraintCache structure::

	{
		'parentClassName':{
						object_id1: [className, **constraintValue],
						object_id2: [className, **constraintValue],
						object_id3: [className, **constraintValue],
						.
						.
						.
						}
	}

referenceCache structure::

	{'c345f92f84554a82aecd1e98600ace31':'e1c291dd3dc84572b48a133306f369b7'}

.. hidden::

	Author: Madhusudan Sridharan (MS)
	Contributors: Chris Satterthwaite (CS)
	Version info:
	  1.0 : (MS) Created Jan 18, 2018
	  2.0 : (CS) Consolidated duplicated functions, May 9, 2018
	  2.1 : (CS) Syntax changes and comments, Jun 1, 2018

"""
import os, sys
import traceback
import time
import datetime as dt
from sqlalchemy import inspect
from sqlalchemy.orm.scoping import scoped_session as sqlAlchemyScopedSession
from sqlalchemy.orm.session import Session as sqlAlchemySession

## Add openContentPlatform directories onto the sys path
thisPath = os.path.dirname(os.path.abspath(__file__))
basePath = os.path.abspath(os.path.join(thisPath, '..'))
if basePath not in sys.path:
	sys.path.append(basePath)
import env
env.addLibPath()


## From openContentPlatform
import database.connectionPool as tableMapping
#from database.connectionPool import DatabaseClient


class ObjectCache:
	"""Class used for building and managing cache."""
	def __init__(self, logger, dbClient):
		"""Constructor.

		Arguments:
		  logger    : Logger handle
		  dbClient  : Either DatabaseClient or sqlalchemy.orm.scoping.scoped_session
		"""
		self.logger = logger
		
		## Normalize when passed both of these two db client types:
		##   database.connectionPool.DatabaseClient 
		##   sqlalchemy.orm.scoping.scoped_session 
		self.dbSession = None
		if isinstance(dbClient, sqlAlchemySession) or isinstance(dbClient, sqlAlchemyScopedSession):
			self.dbSession = dbClient
		elif isinstance(dbClient, tableMapping.DatabaseClient):
			self.dbSession = dbClient.session
		else:
			raise EnvironmentError('The dbClient passed to ObjectCache must be either a database.connectionPool.DatabaseClient or a sqlalchemy.orm.scoping.scoped_session.')
		
		## Initialize dictionaries
		self.constraintCache = dict()
		self.constraintCache['Node'] = dict()
		self.constraintCache['Hardware'] = dict()
		self.constraintCache['Cluster'] = dict()
		self.referenceCache = dict()
		self.lastUpdateTime = time.time()
		## Construct the cache
		self.build()

	def remove(self):
		print(' ~~~~> removing objectCache')
		self.logger = None
		self.dbSession = None
		self.constraintCache = None
		self.referenceCache = None
		self.lastUpdateTime = None
		del(self)

	def build(self):
		"""Build cache dictionaries."""
		try:
			## Constraint cache section; build for all desired types
			nodeObjects = self.dbSession.query(tableMapping.Node).all()
			self.updateConstraintCache(nodeObjects, self.constraintCache['Node'])
			hardwareObjects = self.dbSession.query(tableMapping.Hardware).all()
			self.updateConstraintCache(hardwareObjects, self.constraintCache['Hardware'])
			clusterObjects =  self.dbSession.query(tableMapping.Cluster).all()
			self.updateConstraintCache(clusterObjects, self.constraintCache['Cluster'])

			## Reference cache section
			referenceObjects = self.dbSession.query(tableMapping.ReferenceCache).all()
			self.updateReferenceCache(referenceObjects)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in objectCache build: {}'.format(exception))

		## end build
		return


	def update(self):
		"""Update constraint cache with new objects since last update."""
		try:
			self.logger.info("Updating cache based on timestamp.")
			currentTime = time.time()

			## Constraint cache section
			nodeObjects = self.dbSession.query(tableMapping.Node).filter(tableMapping.Node.time_created <= dt.datetime.fromtimestamp(self.lastUpdateTime)).all()
			self.updateConstraintCache(nodeObjects, self.constraintCache['Node'])
			hardwareObjects = self.dbSession.query(tableMapping.Hardware).filter(tableMapping.Hardware.time_created <= dt.datetime.fromtimestamp(self.lastUpdateTime)).all()
			self.updateConstraintCache(hardwareObjects, self.constraintCache['Hardware'])
			clusterObjects =  self.dbSession.query(tableMapping.Cluster).filter(tableMapping.Cluster.time_created <= dt.datetime.fromtimestamp(self.lastUpdateTime)).all()
			self.updateConstraintCache(clusterObjects, self.constraintCache['Cluster'])
			self.logger.info("Update sucessful.")

			## Reference cache section
			referenceObjects = self.dbSession.query(tableMapping.ReferenceCache).filter(tableMapping.ReferenceCache.time_created <= dt.datetime.fromtimestamp(self.lastUpdateTime)).all()
			self.updateReferenceCache(referenceObjects)

			## Update timestamp to reflect last successful execution
			self.lastUpdateTime = currentTime

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in objectCache update: {}'.format(exception))

		## end update
		return


	def updateConstraintCache(self, classInstances, classCache):
		"""Update a specific constraint cache.

		Arguments:
		  classInstances (list) : class instances from the database
		  classCache (dict)	  : current version of the cache for this class type
		"""
		for obj in classInstances:
			lst = list()
			className = inspect(obj).class_.__name__
			lst.append(className)
			for col in obj.constraints():
				value = getattr(obj,col)
				lst.append(value)
			classCache[obj.object_id] = lst

		## end updateConstraintCache
		return


	def updateReferenceCache(self, referenceObjects):
		"""Update reference cache with provided objects.

		Arguments:
		  referenceObjects (list) : class instances from the database
		"""
		for item in referenceObjects:
			self.referenceCache[item.object_id] = item.reference_id

		## end updateReferenceCache
		return
