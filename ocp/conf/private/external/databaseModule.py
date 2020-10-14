"""External utility to work with database parameters and wrap the connection.

Externally referenced functions:
  |  updateSettingsFile  : create/update file containing connection parameters
  |  createEngine        : extract settings, decode/decrypt, and connect to DB


The intention with an external wrapper, is to move responsibility of protecting
sensitive data away from the open-source platform. From a modular perspective,
this module would be best coded as a single Python class. However, doing that
provides easier access to internals and so we intentionally avoid encapsulation
with individual functions.

"""
import importlib
import os
import getpass
import os
import sys
import traceback
import json

## Using sqlalchemy for the wrapper around postgresql:
##     http://docs.sqlalchemy.org/en/latest/index.html
from sqlalchemy import create_engine

## Get relative paths based on install location
import env
env.addLibPath()
import utils
globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))
## Import an externally-provided library for encoding/encrypting/hashing/etc
externalEncryptionLibrary = utils.loadExternalLibrary('externalEncryptionLibrary', env, globalSettings)

requiredParameters = ['databaseServer', 'databasePort', 'databaseName', 'databaseUser']


def encode(sensitiveData):
	## Use an externally library for sensitive data (defined and imported above)
	return externalEncryptionLibrary.encode(sensitiveData)


def decode(encodedData):
	## Use an externally library for sensitive data (defined and imported above)
	return externalEncryptionLibrary.decode(encodedData)


def missingContent(dbSettings):
	## Make sure we're not missing something required for the connection string
	if dbSettings is None or not isinstance(dbSettings, dict):
		return True
	for entry in requiredParameters:
		if entry not in dbSettings:
			return True
	return False


def getSettingsFromFile():
	databaseSettingsFile = os.path.join(env.privateInternalPath, globalSettings['fileContainingDatabaseSettings'])
	## Right now the file is stored in JSON form, but later we may obscure the
	## entire file instead of just the sensitive part(s). Return a dict format.
	newSettings = utils.loadSettings(databaseSettingsFile)
	assert isinstance(newSettings, dict)
	## If we're missing something required, report a problem with the file
	if missingContent(newSettings):
		raise EnvironmentError('Database settings file is missing data: {}'.format(databaseSettingsFile))
	return newSettings


def writeSettingsToFile(dbSettingsFile, settings):
	## Create or update the file; this is currently stored in JSON format
	with open(dbSettingsFile, 'w') as f:
		f.write(json.dumps(settings, indent=4, separators=(',', ':')))


def getPassInput():
	## Simple validation and transformation of the password.
	pass1 = None
	pprompt = lambda: (getpass.getpass('databasePassword: '), getpass.getpass('Retype password: '))
	while 1:
		pass1, pass2 = pprompt()
		if pass1 != pass2:
			print('Passwords do not match; try again...')
			continue
		elif len(pass1) < 4:
			## This isn't intended to inforce password standards; it just
			## validates user has entered something that may be relevant
			print('Password length must be at least 4 characters; try again...')
			continue
		break

	## end getPassInput
	return pass1


def requestUpdatedConfig(updatedSettings, fileSettings, logger):
	## Update or confirm to previous database connection parameters.
	logger.debug('Settings file exists; loading to suggest default values')
	print('\nHit Enter to accept the previous setting [listed in brackets]:\n')

	for entry in requiredParameters:
		updatedSettings[entry] = input('{} [{}]: '.format(entry, fileSettings.get(entry)))
		#if len(settings[entry].strip()) == 0:
		if updatedSettings.get(entry) is None or len(updatedSettings[entry].strip()) <= 0:
			updatedSettings[entry] = fileSettings.get(entry)
	updatedSettings['databaseNotThat'] = encode(getPassInput())

	## end requestUpdatedConfig
	return


def requestNewConfig(settings, logger):
	## Request all new database connection parameters.
	logger.debug('Settings file does not exist; probably running for first time')
	settings['databaseServer'] = input('databaseServer (FQDN or IP): ')
	settings['databasePort'] = input('databasePort: ')
	settings['databaseName'] = input('databaseName: ')
	settings['databaseUser'] = input('databaseUser: ')
	settings['databaseNotThat'] = encode(getPassInput())

	## end requestNewConfig
	return


def updateSettingsFile(globalSettings, logger):
	"""Get settings (new or updated) and save to config file.

	Arguments:
	  settings (dict)          : dictionary to hold the database connection parameters
	  configPath (str)         : string containing path to the conf directory
	  logger                   : log handler tracking database configuration activities

	"""
	## Settings will come from ../conf/databaseSettings.json by default
	dbSettingsFile = os.path.join(env.privateInternalPath, globalSettings.get('fileContainingDatabaseSettings'))
	fileSettings = {}
	updatedSettings = {}
	try:
		fileSettings = getSettingsFromFile()
	except IOError:
		## On the first run, it won't exist
		pass
	logger.debug('Requesting user input...')
	if missingContent(fileSettings):
		## First time invocation; set the defaults
		requestNewConfig(updatedSettings, logger)
	else:
		## Only update what's specified by user; must provide password
		requestUpdatedConfig(updatedSettings, fileSettings, logger)

	writeSettingsToFile(dbSettingsFile, updatedSettings)

	## end updateSettingsFile
	return


def createEngine(dbSettings, globalSettings, poolSize, maxOverflow, poolRecycle):

	## Load from file if we weren't passed dbSettings or are missing data
	if dbSettings is None or missingContent(dbSettings):
		newSettings = getSettingsFromFile()
		## Mutate previous dbSettings to avoid clobbering unrelated keys
		dbSettings.update(newSettings)
	
	## Pull connection string segments from dbSettings
	endpoint = dbSettings['databaseServer']
	port = dbSettings['databasePort']
	database = dbSettings['databaseName']
	user = dbSettings['databaseUser']
	notthat = decode(dbSettings['databaseNotThat'])

	## Construct our connection string for the database driver
	connectionString = 'postgresql://{}:{}@{}:{}/{}'.format(user, notthat, endpoint, port, database)
	
	## Lazy initialization. For a max of 40 connections that recycle after
	## 30 minutes:  pool_size=35, max_overflow=5, pool_recycle=1800
	#engine = create_engine(connectionString, pool_size=poolSize, max_overflow=maxOverflow, pool_recycle=poolRecycle)
	return create_engine(connectionString, pool_size=poolSize, max_overflow=maxOverflow, pool_recycle=poolRecycle)
