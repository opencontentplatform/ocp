"""Class to manage protocols.

Classes:
  |  ProtocolHandler : manipulate data used in protocol connections

"""
## Module for wrapping protocol objects; avoiding standard docstrings.
import os
import sys
import traceback
import json
import datetime
from contextlib import suppress
from sqlalchemy import inspect, and_

## From openContentPlatform
import utils
import clientApiContext
import database.schema.platformSchema as platformSchema
import env

## Using an externally provided library to work with encryption; defined
## in globalSettings and located in '<install_path>/external'.
externalEncryptionLibrary = utils.loadExternalLibrary('externalEncryptionLibrary', env)

## Global for ease of update
managedProtocols = ['ProtocolSnmp', 'ProtocolWmi', 'ProtocolSsh', 'ProtocolPowerShell', 'ProtocolSqlPostgres']
sensitiveAttributes = ['password', 'community_string', 'token', 'cert_password', 'cert_key', 'key_passphrase']
ignoredAttributes = ['time_created', 'time_updated', 'object_created_by', 'object_updated_by']


class ProtocolHandler():
	def __init__(self, dbClient, globalSettings, env, logger):
		self.globalSettings = globalSettings
		self.env = env
		self.logger = logger
		self.dbClient = dbClient
		## Pull from the global section above, since we need this as an
		## independent function later in this module in doExtract
		self.externalEncryptionLibrary = externalEncryptionLibrary
		## Service needs to 'create' and get apiContext; Client does not
		if dbClient is not None:
			self.apiContext = None
			self.apiContext = clientApiContext.getApiContext(self.dbClient, self.globalSettings, self.logger)
			if self.apiContext is None:
				self.logger.error('ProtocolHandler unable to gather API context')


	def __del__(self):
		self.globalSettings = None
		self.env = None
		self.logger = None
		self.dbClient = None
		self.apiContext = None


	def create(self, jobMetaData):
		try:
			protocolType = jobMetaData.get('protocolType')
			encodedSalt = self.externalEncryptionLibrary.getToken()
			jobMetaData['jobIdentifier'] = encodedSalt
			## Get instances for all requested protocol types listed in job
			requestedProtocolTypes = []
			if protocolType is not None:
				if isinstance(protocolType, str):
					requestedProtocolTypes.append(protocolType)
				elif isinstance(protocolType, list):
					for namedType in protocolType:
						requestedProtocolTypes.append(namedType)
				else:
					raise TypeError('Value of protocolType in jobMetaData must be either string or list of strings. Found type {}'.format(type(protocolType)))
			protocols = {}
			for requestedType in requestedProtocolTypes:
				try:
					dbTable = eval('platformSchema.{}'.format(requestedType))
					dbTableColumns = inspect(dbTable).attrs
					results = None
					## The 'find' jobs should specify a 'credentialGroup', but
					## after creds are established, jobs should avoid using this
					if jobMetaData.get('credentialGroup') is not None:
						results = self.dbClient.session.query(dbTable).filter(and_(dbTable.realm == jobMetaData['realm'], dbTable.credential_group == jobMetaData['credentialGroup'])).all()
					else:
						results = self.dbClient.session.query(dbTable).filter(dbTable.realm == jobMetaData['realm']).all()

					for result in results:
						thisProtocol = {}
						thisProtocol['protocolType'] = requestedType
						thisId = result.object_id
						for column in dbTableColumns:
							colName = column.key
							if colName in sensitiveAttributes:
								## Found a sensitive attribute
								tmpVal = getattr(result, colName)
								thisProtocol[colName] = None
								if tmpVal is not None and tmpVal != '':
									if requestedType in managedProtocols:
										## Managed protocol section; keep obfuscated
										something = self.externalEncryptionLibrary.transformDefault(getattr(result, colName), encodedSalt)
										thisProtocol[colName] = something[0]
									else:
										thisProtocol[colName] = self.externalEncryptionLibrary.decode(getattr(result, colName))
							elif colName in ignoredAttributes:
								## Found an attribute we don't need to send
								continue
							else:
								## All other attributes directly mapped
								thisProtocol[colName] = getattr(result, colName)

						if requestedType in managedProtocols:
							## Managed protocol section; keep obfuscated
							thisProtocolAsString = json.dumps(thisProtocol)
							protocols[thisId] = self.externalEncryptionLibrary.encode(thisProtocolAsString, encodedSalt)
						else:
							## All other protocols... leave open
							protocols[thisId] = thisProtocol

				except:
					exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					self.logger.error('Exception in parsing protocol: {exception!r}', exception=exception)

			## Obfuscate the protocol section
			protocolsAsString = json.dumps(protocols)
			jobMetaData['protocols'] = self.externalEncryptionLibrary.encode(protocolsAsString, encodedSalt)
			## Obfuscate the API context
			apiContextAsString = json.dumps(self.apiContext)
			jobMetaData['apiContext'] = self.externalEncryptionLibrary.encode(apiContextAsString, encodedSalt)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in protocolHandler.create: {exception!r}', exception=exception)

		with suppress(Exception):
			## Return underlying DBAPI connection to the connection pool
			self.dbClient.session.close()
		## end create
		return


	def createManual(self, runtime, protocolType, protocolData):
		encodedSalt = self.externalEncryptionLibrary.getToken()
		runtime.jobMetaData['jobIdentifier'] = encodedSalt
		## Normalize protocolData to a list, so the flow is the same and a
		## job script can provide multiple entries at once
		protocolList = []
		if isinstance(protocolData, dict):
			protocolList.append(protocolData)
		elif isinstance(protocolData, list):
			for namedType in protocolData:
				protocolList.append(namedType)
		else:
			raise TypeError('Value of protocolData must either be a single protocol in dictionary form, or a list of dictionary entries. Found type {}.'.format(type(protocolType)))
		protocols = {}
		protocolId = 0
		for protocol in protocolList:
			protocolId += 1
			thisProtocol = {}
			if protocolType in managedProtocols:
				## Managed protocol section; keep obfuscated
				for key,value in protocol.items():
					if key in sensitiveAttributes:
						## Found a sensitive attribute
						thisProtocol[key] = None
						if value is not None and value != '':
							something = self.externalEncryptionLibrary.encode(value, encodedSalt)
							thisProtocol[key] = something
					else:
						## All other attributes directly mapped
						thisProtocol[key] = value
				thisProtocolAsString = json.dumps(thisProtocol)
				protocols[protocolId] = self.externalEncryptionLibrary.encode(thisProtocolAsString, encodedSalt)
			else:
				## All other protocols... leave open
				protocols[protocolId] = protocol
		runtime.protocols = protocols

		## end createManual
		return


	def open(self, jobMetaData):
		encodedSalt = jobMetaData['jobIdentifier']
		## Extract the protocols sent with the job
		protocolsRaw = jobMetaData.get('protocols')
		jobMetaData['protocols'] = json.loads(self.externalEncryptionLibrary.decode(protocolsRaw, encodedSalt))
		## Extract the API web service context
		apiContextRaw = jobMetaData.get('apiContext')
		jobMetaData['apiContext'] = json.loads(self.externalEncryptionLibrary.decode(apiContextRaw, encodedSalt))
		return


def getProtocolObjects(runtime):
	## Pull the set of protocols from job runtime
	return runtime.protocols

def getProtocolObject(runtime, reference):
	protocols = getProtocolObjects(runtime)
	## Pull a specific protocol object from job runtime
	return protocols.get(reference)

def getSalt(runtime):
	## Pull the salt from job runtime
	return runtime.jobMetaData.get('jobIdentifier')

def extractProtocol(runtime, protocol):
	encodedSalt = getSalt(runtime)
	return doExtract(encodedSalt, protocol)

def extractProtocolByReference(runtime, reference):
	protocol = getProtocolObject(runtime, reference)
	return extractProtocol(runtime, protocol)

def doExtract(encodedSalt, protocol):
	## Undo the encoding/encryption/abstraction done on the the protocol
	## and bring everything to a JSON with plain text values... ready to be
	## used directly by drivers, libraries, or protocols for a connection.
	## Also, don't change the protocolEntry in place; create a new object.
	protocolEntry = {}
	## This part decrypts the protocol object as a whole
	decodedProtocolStr = externalEncryptionLibrary.decode(protocol, encodedSalt)
	if decodedProtocolStr is None:
		raise EnvironmentError('Protocol reference not found')
	decodedProtocol = json.loads(decodedProtocolStr)
	for attribute,value in decodedProtocol.items():
		protocolEntry[attribute] = value
		if attribute in sensitiveAttributes:
			protocolEntry[attribute] = externalEncryptionLibrary.decode(value, encodedSalt)
	return protocolEntry
