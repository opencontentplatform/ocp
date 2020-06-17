"""Utility to insert credentials used by content gathering jobs.

Using the CLI was the original method. It's was deprecated once the API had the
capability to do the same, plus expose whatever other attributes a protocol had.

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Oct 19, 2017

"""
import getpass
import os
import sys
import traceback
import json
import logging, logging.handlers

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
from database.schema.platformSchema import ProtocolSnmp, ProtocolWmi
from database.schema.platformSchema import ProtocolSsh, ProtocolPowerShell
from database.schema.platformSchema import ProtocolRestApi, Realm

externalEncryptionLibrary = utils.loadExternalLibrary('externalEncryptionLibrary', env)

def getPassInput(column):
	"""Simple validation and transformation of a password."""
	prettyEncoding = None
	pprompt = lambda: (getpass.getpass(' {}: '.format(column)), getpass.getpass(' retype {}: '.format(column)))
	while 1:
		pass1, pass2 = pprompt()
		if pass1 != pass2:
			print('Entries do not match; try again...')
			continue
		break
	prettyEncoding = externalEncryptionLibrary.encode(pass1)

	## end getPassInput
	return prettyEncoding


def createProtocolEntry(dbClient, logger, realms):
	"""Create and insert a new protocol entry."""
	logger.debug('Generating a new protocol entry:')
	protocolType = input('Protocol Type (valid entries: [\'ProtocolRestApi\', \'ProtocolSnmp\', \'ProtocolWmi\', \'ProtocolSsh\', \'ProtocolPowerShell\']): ')
	logger.debug('  protocol type: {}'.format(protocolType))
	baseColumns = ['realm', 'credential_group', 'active', 'port', 'description']
	columnNames = eval('{}'.format(protocolType)).__table__.columns.keys()
	baseColumns.extend(columnNames)
	columnValues = {}
	for column in baseColumns:
		if column in ['object_id']:
			continue
		if column == 'realm':
			columnValues[column] = input(' Realm (valid entries: {}): '.format(realms))
			logger.debug('  ==> column [{}] set to [{}]'.format(column, columnValues[column]))
		elif column in ['password', 'community_string', 'token']:
			## Sensitive info should not be echoed out to screen
			columnValues[column] = getPassInput(column)
		elif column in ['active']:
			## Common Boolean values
			thisValue = input(' {}: '.format(column))
			columnValues[column] = utils.valueToBoolean(thisValue)
		elif column in ['port']:
			## Common Integer values
			thisValue = input(' {}: '.format(column))
			if thisValue is not None and len(thisValue.strip()) > 0:
				columnValues[column] = int(thisValue)
		else:
			thisValue = input(' {}: '.format(column))
			logger.debug('  ==> column [{}] set to [{}]'.format(column, thisValue))
			if thisValue is not None and len(thisValue.strip()) > 0:
				columnValues[column] = thisValue

	## Create the entry in the DB
	thisProtocol = eval('{}'.format(protocolType))()
	for column in columnValues.keys():
		setattr(thisProtocol, column, columnValues[column])
	dbClient.session.add(thisProtocol)
	dbClient.session.commit()

	## end createProtocolEntry
	return


def getRealms(dbClient, logger, realms):
	"""Get all valid realms from the database."""
	try:
		results = dbClient.session.query(Realm).all()
		for result in results:
			realms.append(result.name)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		print('Failure in getRealms: {}'.format(stacktrace))

	## end main
	return


def main():
	"""Entry point for this utility.

	Usage::

	  $ python createProtocolEntry.py

	"""
	try:
		## Setup requested log handlers
		logEntity = 'Protocols'
		logger = utils.setupLogger(logEntity, env, 'logSettingsCore.json')
		logger.info('Starting manageProtocols.')

		## Connect to database
		dbClient = DatabaseClient(logger)
		if dbClient is None:
			raise SystemError('Failed to connect to database; unable to initialize tables.')

		## Get list of valid realms
		realms = []
		getRealms(dbClient, logger, realms)

		## Create and insert a new credential
		createProtocolEntry(dbClient, logger, realms)

		## Cleanup
		dbClient.session.remove()
		dbClient.close()
		logger.info('Exiting configureDatabase utility.')

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		## The basic print is here for a console message in case we weren't
		## able to use the logging mechanism before encountering the failure.
		print('Failure in configureDatabase: {}'.format(stacktrace))
		try:
			logger.debug('Failure in configureDatabase: {}'.format(stacktrace))
		except:
			pass

	## end main
	return


if __name__ == '__main__':
	sys.exit(main())
