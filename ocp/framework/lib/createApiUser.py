"""Utility to insert a new API user.

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Mar 24, 2018

"""
import os
import sys
import traceback
import uuid
import json
import twisted.logger

## Add openContentPlatform directories onto the sys path
thisPath = os.path.dirname(os.path.abspath(__file__))
basePath = os.path.abspath(os.path.join(thisPath, '..'))
if basePath not in sys.path:
	sys.path.append(basePath)
import env
env.addLibPath()

## From openContentPlatform
import utils
from database.connectionPool import DatabaseClient
from database.schema.platformSchema import ApiConsumerAccess


def createUserEntry(dbClient, logger, users):
	"""Create and insert a new entry."""
	print('Generating a new API user...')
	## Name
	while 1:
		name = input(' Enter Name: ')
		if len(name) <= 0:
			print('   ==> Name is required.')
		elif name in users:
			print('   ==> user {} already exists, please choose a unique name.'.format(name))
		else:
			break
	## Owner
	owner = input(' Enter Owner: ')
	while len(owner) == 0:
		print('   ==> Owner is required.')
		owner = input(' Enter Owner: ')
	print(' Key must be at least 32 chars; if left empty one will be generated for you.')
	## Key
	key = input(' Enter Key: ')
	while len(key) > 0 and len(key) < 32:
		print('   ==> Key must either be empty, or have at least 32 characters...')
		key = input(' Enter Key: ')
	if len(key) == 0:
		key = uuid.uuid4().hex
	if len(key) > 32:
		key = key[:32]
	## Security access level
	print(' Saved User Key: {}'.format(key))
	print(' Access criteria (true|yes|1==True); defaults to false if left empty:')
	access_write = utils.valueToBoolean(input(' Write Access ? '))
	access_delete = utils.valueToBoolean(input(' Delete Access ? '))
	access_admin = utils.valueToBoolean(input(' Admin Access ? '))

	## Create the entry in the DB
	newApiUser = ApiConsumerAccess(name=name, key=key, owner=owner, access_write=access_write, access_delete=access_delete, access_admin=access_admin)
	dbClient.session.add(newApiUser)
	dbClient.session.commit()
	logger.debug('Created new API user: {}'.format(name))

	## end createUserEntry
	return


def getUsers(dbClient, logger, users):
	"""Get all valid API users."""
	try:
		results = dbClient.session.query(ApiConsumerAccess).all()
		logger.debug('Current users: ')
		for result in results:
			users[result.name] = result.key
			logger.debug('  {userName!r} : {userKey}', userName=result.name, userKey=result.key)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		print('Failure in getUsers: {}'.format(stacktrace))

	## end getUsers
	return


def main():
	"""Entry point for this utility.

	Usage::

	  $ python createApiUser.py

	"""
	try:
		## Setup requested log handlers
		globalSettings = utils.loadSettings(os.path.join(env.configPath, "globalSettings.json"))
		logFiles = utils.setupLogFile("ApiApplication", env, globalSettings['fileContainingServiceLogSettings'], directoryName='service')
		logObserver  = utils.setupObservers(logFiles, "ApiApplication", env, globalSettings['fileContainingServiceLogSettings'])
		logger = twisted.logger.Logger(observer=logObserver, namespace="ApiApplication")
		logger.info('Starting createApiUser')

		## Connect to database
		dbClient = DatabaseClient(logger)
		if dbClient is None:
			raise SystemError('Failed to connect to database; unable to initialize tables.')

		## Get list of valid users
		users = {}
		getUsers(dbClient, logger, users)

		## Create and insert a new credential
		createUserEntry(dbClient, logger, users)

		## Cleanup
		dbClient.session.remove()
		dbClient.close()
		logger.info('Exiting configureDatabase utility.')

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		## The basic print is here for a console message in case we weren't
		## able to use the logging mechanism before encountering the failure.
		print('Failure in createApiUser: {}'.format(stacktrace))
		try:
			logger.debug('Failure in createApiUser: {}'.format(stacktrace))
		except:
			pass

	## end main
	return


if __name__ == '__main__':
	sys.exit(main())
