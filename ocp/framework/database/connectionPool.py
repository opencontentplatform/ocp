"""Postgres wrapper that uses SqlAlchemy.

Classes:
  :class:`connectionPool.DatabaseClient` : SqlAlchemy session pool wrapper

"""

import sys
import traceback
import os
import importlib
from contextlib import suppress

## Using sqlalchemy for the wrapper around postgresql:
##     http://docs.sqlalchemy.org/en/latest/index.html
# from sqlalchemy import create_engine
# from sqlalchemy import DDL
# from sqlalchemy import event
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import exc

## In the future we may decide to load any file dropped into the database/schema
## directory, but tighter restrictions on factory classes seems appropriate.
from database.schema.linkSchema import *
from database.schema.baseSchema import *
from database.schema.node import *
from database.schema.hardware import *
from database.schema.logicalElement import *
from database.schema.locationElement import *
from database.schema.groupElement import *
from database.schema.networkElement import *
from database.schema.systemElement import *
from database.schema.softwareElement import *
from database.schema.softwareComponent import *
from database.schema.platformSchema import *
from database.schema.other import *
from database.schema.archiveSchema import *

from moduleInspect import loadAddOnModules
import utils


class DatabaseClient():
	"""Protocol type wrapper using a SqlAlchemy session pool."""

	def __init__(self, logger, settings=None, globalSettings=None, env=None, poolSize=35, maxOverflow=5, poolRecycle=1800):
		"""Constructor for the database client connection.

		Arguments:
		  logger                : handler for the database log
		  settings (json)       : database connection parameters
		  globalSettings (json) : global settings
		  env                   : module containing the env paths
		  poolSize (int)        : pool_size param for sqlalchemy.create_engine()
		  maxOverflow (int)     : max_overflow param for sqlalchemy.create_engine()
		  poolRecycle (int)     : pool_recycle param for sqlalchemy.create_engine()

		"""
		try:
			self.session = None
			self.settings = settings
			if self.settings is None:
				self.settings = {}

			## Load an external database library for the wrapped connection;
			## the provided library must contain a 'createEngine' function that
			## takes a previously created dictionary with the database
			## settings (if empty, it will be filled), the globalSettings which
			## contains named references to modules in the external directory,
			## and parameters to use in the call for sqlalchemy.create_engine().	
			externalLibrary = utils.loadExternalLibrary('externalDatabaseLibrary', env, globalSettings)
			self.engine = externalLibrary.createEngine(self.settings, globalSettings, poolSize, maxOverflow, poolRecycle)

			## Validate we are actually talking to the DB
			engineInspector = sqlalchemy_inspect(self.engine)
			schemas = engineInspector.get_schema_names()
			if schemas is None or len(schemas) <= 0:
				raise EnvironmentError('Could not connect to database')
			logger.debug('Schemas found from connection pool inspection: {}'.format(str(schemas)))
			self.createScopedSession(logger)
			
		except exc.OperationalError:
			## Intentionally catch database connection errors
			logger.error('Exception in DatabaseClient: {}'.format(str(sys.exc_info()[1])))
			raise
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			logger.error('Exception in DatabaseClient: {}'.format(str(stacktrace)))
			raise

	def createScopedSession(self, logger):
		""" Attempt a scoped session."""
		## Load additional DB classes defined in add-on packages
		loadAddOnModules(logger)
		self.session = scoped_session(sessionmaker(autocommit=False,
												   autoflush=False,
												   bind=self.engine))
		Base.query = self.session.query_property()

	def createTables(self):
		""" Creates the schemas and tables if they don't already exist """
		## The first way (commented out) of creating schemas is specific to the
		## Postgres dialect, and specifically available v9.4 and beyond:
		#for schemaName in ['data', 'platform', 'archive']:
		#	event.listen(Base.metadata, 'before_create', DDL('CREATE SCHEMA IF NOT EXISTS {}'.format(schemaName)))
		## The second way is dialect agnostic
		for schemaName in ['data', 'platform', 'archive']:
			try:
				self.engine.execute('create schema {}'.format(schemaName))
			except:
				pass
		## Now that the schemas will be created, create the tables
		Base.metadata.create_all(bind=self.engine)

	def close(self):
		with suppress(Exception):
			self.session.flush()
		with suppress(Exception):
			self.session.close()
		with suppress(Exception):
			self.session.remove()
		#with suppress(Exception):
		#	self.engine.dispose()
