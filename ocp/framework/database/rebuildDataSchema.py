"""Utility to drop and recreate the 'data' schema and tables.

Functions:
  |  main                : entry point
  |  createSchema        : create data schema and tables

"""
import os
import sys
import traceback

## Add openContentPlatform directories onto the sys path
thisPath = os.path.dirname(os.path.abspath(__file__))
basePath = os.path.abspath(os.path.join(thisPath, '..'))
if basePath not in sys.path:
	sys.path.append(basePath)
import env
env.addLibPath()

## from Open Content Platform
import utils
from database.connectionPool import DatabaseClient
from database.schema.linkSchema import *
from database.schema.baseSchema import *
from database.schema.archiveSchema import *

def createSchema(dbClient, logger):
	"""Create data schema and tables.

	Arguments:
	  dbClient (DatabaseClient) : Instance of database client
	  logger                    : Handler for database log

	"""
	try:
		## Remove all tables if they exist first
		dbClient.session.commit()
		print('Dropping data schema...')
		logger.debug('Dropping data schema...')
		dbClient.engine.execute('drop schema if exists data cascade')
		dbClient.engine.execute('create schema data')
		dbClient.createTables()
		print('Schema and Tables created')
		logger.debug('Schema and Tables created')
		dbClient.session.remove()
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in createSchema: {}'.format(str(stacktrace)))

	## end createSchema
	return


def main():
	"""Entry point for the database configuration utility.

	Usage::

	  $ python rebuildDataSchema.py

	"""
	try:
		## Setup requested log handlers
		logEntity = 'Database'
		logger = utils.setupLogger(logEntity, env, 'logSettingsCore.json')
		logger.info('Starting rebuildDataSchema utility.')

		## Attempt connection
		dbClient = DatabaseClient(logger)
		if dbClient is None:
			raise SystemError('Failed to connect to database; unable to rebuild data schema.')

		print('\nDatabase connection successful.')
		logger.debug('Database connection successful')

		## Start the work
		createSchema(dbClient, logger)

		## Close the connection
		dbClient.close()
		logger.info('Exiting rebuildDataSchema utility.')

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		## The basic print is here for a console message in case we weren't
		## able to use the logging mechanism before encountering the failure.
		print('Failure in rebuildDataSchema.main: {}'.format(stacktrace))
		try:
			logger.debug('Failure in rebuildDataSchema.main: {}'.format(stacktrace))
		except:
			pass

	## end main
	return


if __name__ == '__main__':
	sys.exit(main())
