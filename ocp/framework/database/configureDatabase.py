"""Utility to create or update database connection parameters.

Run this after initial install and whenever the database password changes.

Functions:
  |  main : entry point

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created July 25, 2017
	  2.0 : (CS) Migrated to using external library, Apr 24, 2020

"""
import os
import sys
import traceback
from contextlib import suppress
from sqlalchemy import exc

## Add openContentPlatform directories onto the sys path
thisPath = os.path.dirname(os.path.abspath(__file__))
basePath = os.path.abspath(os.path.join(thisPath, '..'))
if basePath not in sys.path:
	sys.path.append(basePath)
import env
env.addLibPath()

## from Open Content Platform
import utils
from connectionPool import DatabaseClient


def main():
	"""Entry point for the database configuration utility.

	Usage::

	  $ python configureDatabase.py

	"""
	try:
		## Setup requested log handlers
		logEntity = 'Database'
		logger = utils.setupLogger(logEntity, env, 'logSettingsCore.json')
		logger.info('Starting configureDatabase utility.')

		## Using an externally provided library to create and/or update a local
		## config file for database parameters; defined in globalSettings and
		## located in '<install_path>/external/'.
		globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))
		externalLibrary = utils.loadExternalLibrary('externalDatabaseLibrary', env)
		
		dbClient = None
		while dbClient is None:
			try:
				## Get settings from user (new or updated) and save to file
				externalLibrary.updateSettingsFile(globalSettings, logger)
				## Attempt connection with the new or updated settings
				dbClient = DatabaseClient(logger)
				## In case we fall through the cracks without an exception...
				if dbClient is None:
					## The settings didn't work; request a new set
					print('Failed to connect to database with provided settings; try again...')
					logger.debug('Failed to connect to database with provided settings; try again...')

			except exc.OperationalError:
				## Intentionally catch database connection errors
				print('\nException in configureDatabase: {}'.format(str(sys.exc_info()[1])))
				logger.error('Exception in configureDatabase: {}'.format(str(sys.exc_info()[1])))
				## The settings didn't work; request a new set
				print('\nFailed to connect to database with provided settings; try again...')
				logger.debug('Failed to connect to database with provided settings; try again...')

		print('\nDatabase connection successful\n')
		logger.debug('Database connection successful')

		## Close the connection
		dbClient.close()
		logger.info('Exiting configureDatabase utility.')

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		print('Failure in configureDatabase.main: {}'.format(stacktrace))
		with suppress(Exception):
			logger.debug('Failure in configureDatabase: {}'.format(stacktrace))

	## end main
	return


if __name__ == '__main__':
	sys.exit(main())
