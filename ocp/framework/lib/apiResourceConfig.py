"""Config resource for the IT Discovery Machine REST API.

This module defines the Application Programming Interface (API) methods for the
/<root>/config endpoint. Available resources follow::

	/<root>/config/Realm
	/<root>/config/Realm/{realmName}
	/<root>/config/RealmScope
	/<root>/config/NetworkScope
	/<root>/config/NetworkScope/{realm}
	/<root>/config/NetworkScope/{realm}/{object_id}
	/<root>/config/ConfigGroups
	/<root>/config/ConfigGroups/{realm}
	/<root>/config/ConfigGroups/{realm}/{configGroupName}
	/<root>/config/ConfigDefault
	/<root>/config/ConfigDefault/{realm}
	/<root>/config/OsParameters
	/<root>/config/OsParameters/{realm}
	/<root>/config/ApiConsumerAccess
	/<root>/config/ApiConsumerAccess/{user}
	/<root>/config/client
	/<root>/config/client/{endpoint}
	/<root>/config/cred
	/<root>/config/search/{class}

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Sep 15, 2017
	  1.1 : (CS) Replaced apiUtils with Falcon middleware, Sep 2, 2019
	  1.2 : (CS) Added /config/search resources, Oct 15, 2019

"""

import sys
import traceback
import os
import json
import uuid
import inspect as pythonInspect
from hug.types import text, number
from hug.types import json as hugJson
from falcon import HTTP_200, HTTP_400, HTTP_404, HTTP_405, HTTP_500
from sqlalchemy import inspect, and_

## From openContentPlatform
import realmScope
import utils
import database.schema.platformSchema as platformSchema
from apiHugWrapper import hugWrapper
from apiResourceUtils import *
## Load the global settings
import env
globalSettings = utils.loadSettings(os.path.join(env.configPath, "globalSettings.json"))


clientToEndpointTableClass = {
	'ContentGatheringClient' : platformSchema.ServiceContentGatheringEndpoint,
	'ResultProcessingClient' : platformSchema.ServiceResultProcessingEndpoint,
	'UniversalJobClient' : platformSchema.ServiceUniversalJobEndpoint
}
clientToHealthTableClass = {
	'ContentGatheringClient' : platformSchema.ServiceContentGatheringHealth,
	'ResultProcessingClient' : platformSchema.ServiceResultProcessingHealth,
	'UniversalJobClient' : platformSchema.ServiceUniversalJobHealth
}
credTypes = {
	'snmp' : platformSchema.ProtocolSnmp,
	'wmi' : platformSchema.ProtocolWmi,
	'ssh' : platformSchema.ProtocolSsh,
	'powershell' : platformSchema.ProtocolPowerShell,
	'rest' : platformSchema.ProtocolRestApi,
	'postgres' : platformSchema.ProtocolSqlPostgres,
	'mssql' : platformSchema.ProtocolSqlMicrosoft,
	'oracle' : platformSchema.ProtocolSqlOracle,
	'mariadb' : platformSchema.ProtocolSqlMaria,
	'mysql' : platformSchema.ProtocolSqlMy,
	'db2' : platformSchema.ProtocolSqlDb2
}


@hugWrapper.get('/')
def getConfig(request, response):
	"""Show available config resources."""
	staticPayload = {'Available Resources' : {
		'/config/Realm' : {
			'methods' : {
				'GET' : 'Report all realms.'
			}
		},
		'/config/Realm/{realmName}' : {
			'methods' : {
				'POST' : 'Insert a named realm.',
				'DELETE' : 'Delete realm by name.'
			}
		},
		'/config/RealmScope' : {
			'methods' : {
				'GET' : 'Report all entries in RealmScope.'
			}
		},
		'/config/NetworkScope' : {
			'methods' : {
				'GET' : 'Report all entries in NetworkScope.',
				'POST' : 'Validate, transform, and insert a single user-provided scope entry.'
			}
		},
		'/config/NetworkScope/{realm}' : {
			'methods' : {
				'GET' : 'Report details of NetworkScope from the named realm.',
				'DELETE' : 'Delete all entries for the named realm.'
			}
		},
		'/config/NetworkScope/{realm}/{object_id}' : {
			'methods' : {
				'GET' : 'Report specific NetworkScope details from the named realm, with the provided identifier.',
				'DELETE' : 'Delete the specific NetworkScope on the named realm, with the provided identifier.'
			}
		},
		'/config/ConfigGroups' : {
			'methods' : {
				'GET' : 'Return all realms with ConfigGroup entries.',
				'DELETE' : 'Delete all ConfigGroup entries.',
				'POST' : 'Create a ConfigGroup for the target realm.'
			}
		},
		'/config/ConfigGroups/{realm}' : {
			'methods' : {
				'GET' : 'Report the ConfigGroup details from the named realm.',
				'DELETE' : 'Remove defined list of entries for the named realm.',
				'PUT' : 'Inserts or updates an entry for the named realm; supply a single entry, not a modified version of the full list.'
			}
		},
		'/config/ConfigGroups/{realm}/{configGroupName}' : {
			'methods' : {
				'DELETE' : 'Remove a named entry from the realm\'s list of entries.',
			}
		},
		'/config/ConfigDefault' : {
			'methods' : {
				'GET' : 'Return all realms with ConfigDefault entries.',
				'DELETE' : 'Delete all ConfigDefault entries.',
				'POST' : 'Create a ConfigDefault for the target realm.'
			}
		},
		'/config/ConfigDefault/{realm}' : {
			'methods' : {
				'GET' : 'Report the ConfigDefault from the named realm.',
				'DELETE' : 'Remove the ConfigDefault entry for the named realm.',
				'PUT' : 'Updates the ConfigDefault entry for the named realm.'
			}
		},
		'/config/OsParameters' : {
			'methods' : {
				'GET' : 'Return all realms with OsParameters entries.',
				'DELETE' : 'Remove all stored OsParameters.',
				'POST' : 'Insert new OsParameters.'
			}
		},
		'/config/OsParameters/{realm}' : {
			'methods' : {
				'GET' : 'Report the contents of OsParameters from the named realm.',
				'DELETE' : 'Removes entry for the named realm',
				'PUT' : 'Updates entry for the named realm'
			}
		},
		'/config/ApiConsumerAccess' : {
			'methods' : {
				'GET' : 'List all account names in ApiConsumerAccess.',
				'DELETE' : 'Remove all stored ApiConsumerAccess entries.',
				'POST' : 'Insert new ApiConsumerAccess entry.'
			}
		},
		'/config/ApiConsumerAccess/{user}' : {
			'methods' : {
				'GET' : 'Report the details of the named user.',
				'DELETE' : 'Removes entry that contains the provided name.',
				'PUT' : 'Updates entry for the provided name.'
			}
		},
		'/config/client' : {
			'methods' : {
				'GET' : 'Report all server endpoints running one or more OCP service clients.'
			}
		},
		'/config/client/{endpoint}' : {
			'methods' : {
				'GET' : 'Report details on the named endpoint.'
			}
		},
		'/config/cred' : {
			'methods' : {
				'GET' : 'Show available protocol credential types.'
			}
		},
		'/config/cred/{type}' : {
			'methods' : {
				'GET' : 'Report entries of the provided cred type.',
				'POST' : 'Insert entry into the provided cred type.',
				'DELETE' : 'Removes entries of the provided cred type.'
			}
		},
		'/config/search' : {
			'methods' : {
				'GET' : 'Show available platform schema classes that can be searched.'
			}
		},
		'/config/search/{platformClassName}' : {
			'methods' : {
				'GET' : 'Query specified class in platform schema, using the provided filter.',
				'DELETE' : 'Delete results from specified class in platform schema, using the provided filter.'
			}
		}
	}}

	## end getConfig
	return staticPayload


@hugWrapper.get('/ConfigGroups')
def getAvailableConfigGroups(request, response):
	"""Get available names and methods for ./config/ConfigGroups."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.ConfigGroups.realm).all()
		configGroups = []
		for item in dataHandle:
			configGroups.append(item[0])
		request.context['payload']['Realms'] = configGroups

	except:
		errorMessage(request, response)

	## end getAvailableConfigGroups
	return cleanPayload(request)


@hugWrapper.post('/ConfigGroups')
def postConfigGroups(content:hugJson, request, response):
	"""Posts the config group to both the database and the file system."""
	try:
		if hasRequiredData(request, response, content, ['realm', 'source', 'content']):
			dataHandle = request.context['dbSession'].query(platformSchema.ConfigGroups).filter(platformSchema.ConfigGroups.realm==content['realm']).first()
			if dataHandle is not None:
				request.context['payload']['errors'].append('Cannot insert {}, definition already exists. Use PUT on ./config/ConfigGroups/{} to update.'.format(content['realm'], content['realm']))
				response.status = HTTP_405
			else:
				if not content['content'] or type(content['content']) != type(list()):
					request.context['payload']['errors'].append('Expected list format for \'content\' field.  (List of dictionary entries, where each dict is a configGroup.)')
					response.status = HTTP_400
				elif content['realm'] == '' or content['realm'] == None:
					request.context['payload']['errors'].append('\'realm\' field cannot be empty.')
					response.status = HTTP_400
				else:
					## Data looks good
					source = mergeUserAndSource(content, request)
					content['object_created_by'] = source
					dataHandle = platformSchema.ConfigGroups(**content)
					request.context['dbSession'].add(dataHandle)
					request.context['dbSession'].commit()
					## Now backup previous file and create an updated version
					fileName = 'configGroups_{}.json'.format(content['realm'])
					modifyPlatformSettingsFile(request, response, fileName, content)
					request.context['logger'].info('Sucessfully updated local file {}'.format(fileName))
					request.context['payload']['Response'] = 'Success'

	except:
		errorMessage(request, response)

	## end postConfigGroups
	return cleanPayload(request)


@hugWrapper.delete('/ConfigGroups')
def deleteConfigGroups(request, response):
	"""Delete all stored config groups from the database and filesystem."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.ConfigGroups).all()
		for item in dataHandle:
			request.context['dbSession'].delete(item)
			realm = item.realm
			## Rotate server-cached files to retain an external backup
			fileName = 'configGroups_{}.json'.format(realm)
			rotatePlatformSettingsFiles(request, response, fileName)
			## Remove the primary server-cached file
			fileToRemove = os.path.join(env.contentGatheringSharedConfigGroupPath, fileName)
			if os.path.isfile(fileToRemove):
				os.remove(fileToRemove)
		request.context['dbSession'].commit()
		request.context['payload']['Success'] = 'Removed all ConfigGroups'

	except:
		errorMessage(request, response)

	## end deleteConfigGroups
	return cleanPayload(request)


@hugWrapper.get('/ConfigGroups/{realm}')
def getSpecificConfigGroups(realm:text, request, response):
	"""Get the contents of the config group from the named realm."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.ConfigGroups).filter(platformSchema.ConfigGroups.realm==realm).first()
		if dataHandle:
			for col in inspect(dataHandle).mapper.c.keys():
				request.context['payload'][col] = getattr(dataHandle, col)
		else:
			request.context['payload']['errors'].append('No ConfigGroups exist for realm {}'.format(realm))
			response.status = HTTP_404

	except:
		errorMessage(request, response)

	## end getSpecificConfigGroups
	return cleanPayload(request)


@hugWrapper.put('/ConfigGroups/{realm}')
def updateSpecificConfigGroups(realm:text, content:hugJson, request, response):
	"""Update the config group for the named realm, with the provided JSON"""
	try:
		if hasRequiredData(request, response, content, ['source', 'content']):
			dataHandle = request.context['dbSession'].query(platformSchema.ConfigGroups).filter(platformSchema.ConfigGroups.realm==realm).first()
			if dataHandle is None:
				request.context['payload']['errors'].append('No ConfigGroups exist for realm {}, in order to update. Use POST on ./config/ConfigGroups to create.'.format(realm))
				response.status = HTTP_404
			else:
				## Get the previous ConfigGroup contents saved in the DB
				contentToUpdate = dataHandle.content
				## Update the contents with the newly provided data
				removeAndAppendPlatformSettings(request, response, content['content'], contentToUpdate)
				## Set the source
				source = mergeUserAndSource(content, request)
				## Create an object to merge/update with the previous DB entry
				newContent = {'realm' : realm,
							  'object_updated_by' : source,
							  'content' : contentToUpdate}
				dataHandle = platformSchema.ConfigGroups(**newContent)
				dataHandle = request.context['dbSession'].merge(dataHandle)
				request.context['dbSession'].commit()
				request.context['payload']['Response'] = 'Updated ConfigGroups for realm {}'.format(realm)
				## Backup previous local file and create an updated version
				fileName = 'configGroups_{}.json'.format(realm)
				modifyPlatformSettingsFile(request, response, fileName, contentToUpdate)
				request.context['logger'].debug('Updated the local file {}'.format(fileName))

	except:
		errorMessage(request, response)

	## end updateSpecificConfigGroups
	return cleanPayload(request)


@hugWrapper.delete('/ConfigGroups/{realm}')
def deleteSpecificConfigGroups(realm:text, request, response):
	"""Delete the config group for the named realm."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.ConfigGroups).filter(platformSchema.ConfigGroups.realm==realm).first()
		if dataHandle is None:
			request.context['payload']['errors'].append('No ConfigGroups exist for realm {}'.format(realm))
			response.status = HTTP_404
		else:
			request.context['dbSession'].delete(dataHandle)
			request.context['dbSession'].commit()
			## Rotate server-cached files to retain an external backup
			fileName = 'configGroups_{}.json'.format(realm)
			rotatePlatformSettingsFiles(request, response, fileName)
			## Remove the primary server-cached file
			fileToRemove = os.path.join(env.contentGatheringSharedConfigGroupPath, fileName)
			if os.path.isfile(fileToRemove):
				os.remove(fileToRemove)
			request.context['payload']['Success'] = 'Removed ConfigGroups for the realm {}'.format(realm)

	except:
		errorMessage(request, response)

	## end deleteSpecificConfigGroups
	return cleanPayload(request)


@hugWrapper.delete('/ConfigGroups/{realm}/{configGroupName}')
def deleteRealmConfigGroupEntry(realm:text, configGroupName:text, request, response):
	"""Delete a named entry from ConfigGroups in the specified realm.

	Note 1: To expose maximum flexibility, there are no required attributes for
	an entry in ConfigGroups. It's an ordered list of dictionaries. A name
	is not required; it's just a suggested convention that is used internally.

	Note 2: Removing an entry on the list fits best in a RESTful PUT method on
	/ConfigGroups/{realm}. However, there are good reasons not to add it there.
	Probably the most important one is if an external tool (eg. OS provisioning)
	wanted to independently/externally add a new entry, instead of the internal
	mechanism via the template job. In that case, the external tool would need
	to pull the current realm setting, remove any potential conflicts (whatever
	that means) and finally issue a PUT on /ConfigGroups/realm. So, to simplify
	an update, we allowed a PUT on /ConfigGroups/realm to only contain a single
	(new or updated) entry, and then common/shared code would do the merge.

	Note 3: Given note 2, that meant we needed an explicit method to remove a
	current entry... hence this function that leverages the name.
	"""
	try:
		request.context['logger'].debug('deleteRealmConfigGroupEntry: configGroupName: {}'.format(configGroupName))
		dataHandle = request.context['dbSession'].query(platformSchema.ConfigGroups).filter(platformSchema.ConfigGroups.realm==realm).first()
		if dataHandle is None:
			request.context['payload']['errors'].append('No ConfigGroups exist for realm {}, in order to delete. Use POST on ./config/ConfigGroups to create.'.format(realm))
			response.status = HTTP_404
		else:
			## Get the previous ConfigGroup contents saved in the DB
			contentToUpdate = dataHandle.content
			request.context['logger'].debug('deleteRealmConfigGroupEntry: contentToUpdate 1: {}'.format(contentToUpdate))
			contentToUpdate[:] = [x for x in contentToUpdate if not (x.get('name') == configGroupName)]
			request.context['logger'].debug('deleteRealmConfigGroupEntry: contentToUpdate 2: {}'.format(contentToUpdate))

			## Set the source
			source = request.context['apiUser']
			## Create an object to merge/update with the previous DB entry
			newContent = {'realm' : realm,
						  'object_updated_by' : source,
						  'content' : contentToUpdate}
			dataHandle = platformSchema.ConfigGroups(**newContent)
			dataHandle = request.context['dbSession'].merge(dataHandle)
			request.context['dbSession'].commit()
			request.context['payload']['Success'] = 'Removed ConfigGroup {} from realm {}'.format(configGroupName, realm)
			## Backup previous local file and create an updated version
			fileName = 'configGroups_{}.json'.format(realm)
			modifyPlatformSettingsFile(request, response, fileName, contentToUpdate)
			request.context['logger'].debug('Updated the local file {}'.format(fileName))

	except:
		errorMessage(request, response)

	## end deleteSpecificConfigGroups
	return cleanPayload(request)


@hugWrapper.get('/ConfigDefault')
def getAvailableConfigDefault(request, response):
	"""Get available names and methods for ./config/ConfigDefault."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.ConfigDefault.realm).all()
		configs = []
		for item in dataHandle:
			configs.append(item[0])
		request.context['payload']['Realms'] = configs

	except:
		errorMessage(request, response)

	## end getAvailableConfigDefault
	return cleanPayload(request)


@hugWrapper.post('/ConfigDefault')
def postConfigDefault(content:hugJson, request, response):
	"""Posts the config default to both the database and the file system."""
	try:
		if hasRequiredData(request, response, content, ['realm', 'source', 'content']):
			dataHandle = request.context['dbSession'].query(platformSchema.ConfigDefault).filter(platformSchema.ConfigDefault.realm==content['realm']).first()
			if dataHandle is not None:
				request.context['payload']['errors'].append('Cannot insert {}, definition already exists. Use PUT on ./config/ConfigDefault/{} to update.'.format(content['realm'], content['realm']))
				response.status = HTTP_405
			else:
				if not content['content'] or type(content['content']) != type(dict()):
					request.context['payload']['errors'].append('Expected dictionary format for \'content\' field.')
					response.status = HTTP_400
				elif content['realm'] == '' or content['realm'] == None:
					request.context['payload']['errors'].append('\'realm\' field cannot be empty.')
					response.status = HTTP_400
				else:
					## Data looks good
					source = mergeUserAndSource(content, request)
					content['object_created_by'] = source
					dataHandle = platformSchema.ConfigDefault(**content)
					request.context['dbSession'].add(dataHandle)
					request.context['dbSession'].commit()
					## Now backup previous file and create an updated version
					fileName = 'configDefault_{}.json'.format(content['realm'])
					modifyPlatformSettingsFile(request, response, fileName, content)
					request.context['logger'].info('Sucessfully updated local file {}'.format(fileName))
					request.context['payload']['Response'] = 'Success'

	except:
		errorMessage(request, response)

	## end postConfigDefault
	return cleanPayload(request)


@hugWrapper.delete('/ConfigDefault')
def deleteConfigDefault(request, response):
	"""Delete all stored config groups from the database and filesystem."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.ConfigDefault).all()
		for item in dataHandle:
			request.context['dbSession'].delete(item)
			realm = item.realm
			## Rotate server-cached files to retain an external backup
			fileName = 'configDefault_{}.json'.format(realm)
			rotatePlatformSettingsFiles(request, response, fileName)
			## Remove the primary server-cached file
			fileToRemove = os.path.join(env.contentGatheringSharedConfigGroupPath, fileName)
			if os.path.isfile(fileToRemove):
				os.remove(fileToRemove)
		request.context['dbSession'].commit()
		request.context['payload']['Success'] = 'Removed all ConfigDefault entries'

	except:
		errorMessage(request, response)

	## end deleteConfigDefault
	return cleanPayload(request)


@hugWrapper.get('/ConfigDefault/{realm}')
def getSpecificConfigDefault(realm:text, request, response):
	"""Get the contents of the config group from the named realm."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.ConfigDefault).filter(platformSchema.ConfigDefault.realm==realm).first()
		if dataHandle:
			for col in inspect(dataHandle).mapper.c.keys():
				request.context['payload'][col] = getattr(dataHandle, col)
		else:
			request.context['payload']['errors'].append('No ConfigDefault exists for realm {}'.format(realm))
			response.status = HTTP_404

	except:
		errorMessage(request, response)

	## end getSpecificConfigDefault
	return cleanPayload(request)


@hugWrapper.put('/ConfigDefault/{realm}')
def updateSpecificConfigDefault(realm:text, content:hugJson, request, response):
	"""Update the config group for the named realm, with the provided JSON"""
	try:
		if hasRequiredData(request, response, content, ['source']):
			dataHandle = request.context['dbSession'].query(platformSchema.ConfigDefault).filter(platformSchema.ConfigDefault.realm==realm).first()
			if dataHandle is None:
				request.context['payload']['errors'].append('No ConfigDefault exist for realm {}, in order to update. Use POST on ./config/ConfigDefault to create.'.format(realm))
				response.status = HTTP_404
			else:
				contentToUpdate = content['content']
				## Backup previous local file and create an updated version
				fileName = 'configDefault_{}.json'.format(realm)
				modifyPlatformSettingsFile(request, response, fileName, contentToUpdate)
				request.context['logger'].debug('Updated the local file {}'.format(fileName))
				## Set the source
				source = mergeUserAndSource(content, request)
				## Create an object to merge/update with the previous DB entry
				newContent = { 'realm' : realm,
							   'object_updated_by' : source,
							   'content' : contentToUpdate }
				dataHandle = platformSchema.ConfigDefault(**newContent)
				dataHandle = request.context['dbSession'].merge(dataHandle)
				request.context['dbSession'].commit()
				request.context['payload']['Response'] = 'Updated ConfigDefault for realm {}'.format(realm)

	except:
		errorMessage(request, response)

	## end updateSpecificConfigDefault
	return cleanPayload(request)


@hugWrapper.delete('/ConfigDefault/{realm}')
def deleteSpecificConfigDefault(realm:text, request, response):
	"""Delete the config group for the named realm."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.ConfigDefault).filter(platformSchema.ConfigDefault.realm==realm).first()
		if dataHandle is None:
			request.context['payload']['errors'].append('No ConfigDefault exists for realm {}'.format(realm))
			response.status = HTTP_404
		else:
			request.context['dbSession'].delete(dataHandle)
			request.context['dbSession'].commit()
			## Rotate server-cached files to retain an external backup
			fileName = 'configDefault_{}.json'.format(realm)
			rotatePlatformSettingsFiles(request, response, fileName)
			## Remove the primary server-cached file
			fileToRemove = os.path.join(env.contentGatheringSharedConfigGroupPath, fileName)
			if os.path.isfile(fileToRemove):
				os.remove(fileToRemove)
			request.context['payload']['Success'] = 'Removed ConfigDefault for the realm {}'.format(realm)

	except:
		errorMessage(request, response)

	## end deleteSpecificConfigDefault
	return cleanPayload(request)


@hugWrapper.get('/OsParameters')
def getAvailableOsParameters(request, response):
	"""Return all realms with OsParameters entries."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.OsParameters.realm).all()
		configs = []
		for item in dataHandle:
			configs.append(item[0])
		request.context['payload']['Realms'] = configs

	except:
		errorMessage(request, response)

	## end getAvailableOsParameters
	return cleanPayload(request)


@hugWrapper.post('/OsParameters')
def postOsParameters(content:hugJson, request, response):
	"""Posts OS parameters to both the database and the file system."""
	try:
		if hasRequiredData(request, response, content, ['realm', 'source', 'content']):
			dataHandle = request.context['dbSession'].query(platformSchema.OsParameters).filter(platformSchema.OsParameters.realm==content['realm']).first()
			if dataHandle is not None:
				request.context['payload']['errors'].append('Cannot insert {}, definition already exists. Use PUT on ./config/OsParameters/{} to update.'.format(content['realm'], content['realm']))
				response.status = HTTP_405
			else:
				if not content['content'] or type(content['content']) != type(dict()):
					request.context['payload']['errors'].append('Expected dictionary format for \'content\' field.')
					response.status = HTTP_400
				elif content['realm'] == '' or content['realm'] == None:
					request.context['payload']['errors'].append('\'realm\' field cannot be empty.')
					response.status = HTTP_400
				else:
					## Data looks good
					source = mergeUserAndSource(content, request)
					content['object_created_by'] = source
					dataHandle = platformSchema.OsParameters(**content)
					request.context['dbSession'].add(dataHandle)
					request.context['dbSession'].commit()
					## Now backup previous file and create an updated version
					fileName = 'osParameters_{}.json'.format(content['realm'])
					modifyPlatformSettingsFile(request, response, fileName, content)
					request.context['logger'].debug('Sucessfully updated local file {}'.format(fileName))
					request.context['payload']['Response'] = 'Success'

	except:
		errorMessage(request, response)

	## end postOsParameters
	return cleanPayload(request)


@hugWrapper.delete('/OsParameters')
def deleteOsParameters(request, response):
	"""Delete all stored OS parameters from the database and filesystem."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.OsParameters).all()
		for item in dataHandle:
			request.context['dbSession'].delete(item)
			realm = item.realm
			## Rotate server-cached files to retain an external backup
			fileName = 'osParameters_{}.json'.format(realm)
			rotatePlatformSettingsFiles(request, response, fileName)
			## Remove the primary server-cached file
			fileToRemove = os.path.join(env.contentGatheringSharedConfigGroupPath, fileName)
			if os.path.isfile(fileToRemove):
				os.remove(fileToRemove)
		request.context['dbSession'].commit()
		request.context['payload']['Success'] = 'Removed all OsParameters'

	except:
		errorMessage(request, response)

	## end deleteOsParameters
	return cleanPayload(request)


@hugWrapper.get('/OsParameters/{realm}')
def getSpecificOsParameters(realm:text, request, response):
	"""Get the contents of OsParameters from the named realm."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.OsParameters).filter(platformSchema.OsParameters.realm==realm).first()
		if dataHandle:
			for col in inspect(dataHandle).mapper.c.keys():
				request.context['payload'][col] = getattr(dataHandle, col)
		else:
			request.context['payload']['errors'].append('No OsParameters exists for realm {}'.format(realm))
			response.status = HTTP_404

	except:
		errorMessage(request, response)

	## end getSpecificOsParameters
	return cleanPayload(request)


@hugWrapper.put('/OsParameters/{realm}')
def updateSpecificOsParameters(realm:text, content:hugJson, request, response):
	"""Update OsParameters for the named realm, with the provided JSON"""
	try:
		if hasRequiredData(request, response, content, ['source']):
			dataHandle = request.context['dbSession'].query(platformSchema.OsParameters).filter(platformSchema.OsParameters.realm==realm).first()
			if dataHandle is None:
				request.context['payload']['errors'].append('No OsParameters exist for realm {}, in order to update. Use POST on ./config/OsParameters to create.'.format(realm))
				response.status = HTTP_404
			else:
				contentToUpdate = content['content']
				## Backup previous local file and create an updated version
				fileName = 'osParameters_{}.json'.format(realm)
				modifyPlatformSettingsFile(request, response, fileName, contentToUpdate)
				request.context['logger'].debug('Updated the local file {}'.format(fileName))
				## Set the source
				source = mergeUserAndSource(content, request)
				## Create an object to merge/update with the previous DB entry
				newContent = { 'realm' : realm,
							   'object_updated_by' : source,
							   'content' : contentToUpdate }
				dataHandle = platformSchema.OsParameters(**newContent)
				dataHandle = request.context['dbSession'].merge(dataHandle)
				request.context['dbSession'].commit()
				request.context['payload']['Response'] = 'Updated OsParameters for realm {}'.format(realm)

	except:
		errorMessage(request, response)

	## end updateSpecificOsParameters
	return cleanPayload(request)


@hugWrapper.delete('/OsParameters/{realm}')
def deleteSpecificOsParameters(realm:text, request, response):
	"""Delete OsParameters for the named realm."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.OsParameters).filter(platformSchema.OsParameters.realm==realm).first()
		if dataHandle is None:
			request.context['payload']['errors'].append('No OsParameters exist for realm {}'.format(realm))
			response.status = HTTP_404
		else:
			request.context['dbSession'].delete(dataHandle)
			request.context['dbSession'].commit()
			## Rotate server-cached files to retain an external backup
			fileName = 'osParameters_{}.json'.format(realm)
			rotatePlatformSettingsFiles(request, response, fileName)
			## Remove the primary server-cached file
			fileToRemove = os.path.join(env.contentGatheringSharedConfigGroupPath, fileName)
			if os.path.isfile(fileToRemove):
				os.remove(fileToRemove)
			request.context['payload']['Success'] = 'Removed OsParameters for the realm {}'.format(realm)

	except:
		errorMessage(request, response)

	## end deleteSpecificOsParameters
	return cleanPayload(request)


@hugWrapper.get('/ApiConsumerAccess')
def getAvailableApiConsumerAccess(request, response):
	"""List all account names in ApiConsumerAccess."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.ApiConsumerAccess.name).all()
		users = []
		for item in dataHandle:
			users.append(item[0])
		request.context['payload']['Users'] = users

	except:
		errorMessage(request, response)

	## end getAvailableApiConsumerAccess
	return cleanPayload(request)


@hugWrapper.post('/ApiConsumerAccess')
def postApiConsumerAccess(content:hugJson, request, response):
	"""Posts new ApiConsumerAccess entry."""
	try:
		if hasRequiredData(request, response, content, ['name', 'owner', 'source']):
			if 'key' not in content.keys():
				content['key'] = uuid.uuid4().hex
			dataHandle = request.context['dbSession'].query(platformSchema.ApiConsumerAccess).filter(platformSchema.ApiConsumerAccess.name==content['name']).first()
			if dataHandle is not None:
				request.context['payload']['errors'].append('Cannot insert {}, definition already exists. Use PUT on ./config/ApiConsumerAccess/{} to update.'.format(content['name'], content['name']))
				response.status = HTTP_405
			else:
				## Data looks good
				source = mergeUserAndSource(content, request)
				content['object_created_by'] = source
				dataHandle = platformSchema.ApiConsumerAccess(**content)
				request.context['dbSession'].add(dataHandle)
				request.context['dbSession'].commit()
				request.context['payload']['Response'] = 'Success'

	except:
		errorMessage(request, response)

	## end postApiConsumerAccess
	return cleanPayload(request)


@hugWrapper.delete('/ApiConsumerAccess')
def deleteApiConsumerAccess(request, response):
	"""Delete all stored ApiConsumerAccess entries."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.ApiConsumerAccess).all()
		for item in dataHandle:
			request.context['dbSession'].delete(item)
		request.context['dbSession'].commit()
		request.context['payload']['Success'] = 'Removed all ApiConsumerAccess entries'

	except:
		errorMessage(request, response)

	## end deleteApiConsumerAccess
	return cleanPayload(request)


@hugWrapper.get('/ApiConsumerAccess/{user}')
def getSpecificApiConsumerAccess(user:text, request, response):
	"""Get the details of the provided user."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.ApiConsumerAccess).filter(platformSchema.ApiConsumerAccess.name==user).first()
		if dataHandle:
			for col in inspect(dataHandle).mapper.c.keys():
				request.context['payload'][col] = getattr(dataHandle, col)
			## Standard conversions of dates to string
			request.context['payload'] = json.loads(json.dumps(request.context['payload'], default=utils.customJsonDumpsConverter))
		else:
			request.context['payload']['errors'].append('No ApiConsumerAccess exists for user {}'.format(user))
			response.status = HTTP_404

	except:
		errorMessage(request, response)

	## end getSpecificApiConsumerAccess
	return cleanPayload(request)


@hugWrapper.put('/ApiConsumerAccess/{user}')
def updateSpecificApiConsumerAccess(user:text, content:hugJson, request, response):
	"""Update entry by the provided user."""
	try:
		if hasRequiredData(request, response, content, ['source']):
			dataHandle = request.context['dbSession'].query(platformSchema.ApiConsumerAccess).filter(platformSchema.ApiConsumerAccess.name==user).first()
			if dataHandle is None:
				request.context['payload']['errors'].append('No ApiConsumerAccess exists with the user {}, in order to update. Use POST on ./config/ApiConsumerAccess to create.'.format(user))
				response.status = HTTP_404
			else:
				request.context['logger'].debug('dataHandle: {}'.format(dataHandle))
				tempObjectId = dataHandle.object_id
				definedColumns = [col for col in inspect(platformSchema.ApiConsumerAccess).mapper.c.keys() if col not in ['name', 'object_id', 'time_created', 'object_created_by', 'time_updated', 'object_updated_by']]
				request.context['logger'].debug('ApiConsumerAccess provided content: {}'.format(content))
				request.context['logger'].debug('ApiConsumerAccess definedColumns: {}'.format(definedColumns))
				## Set the source
				source = mergeUserAndSource(content, request)
				## If any provided columns are valid for this class, then merge:
				if any(col in content.keys() for col in definedColumns):
					content['object_updated_by'] = source
					content['object_id'] = tempObjectId
					dataHandle = platformSchema.ApiConsumerAccess(**content)
					dataHandle = request.context['dbSession'].merge(dataHandle)
					request.context['dbSession'].commit()
					request.context['payload']['Response'] = 'Updated ApiConsumerAccess for user {}'.format(user)
					request.context['logger'].debug('Updated user with content: {}'.format(content))
				else:
					request.context['payload']['Response'] = 'No valid columns provided for updating ApiConsumerAccess entry {}'.format(user)
					request.context['logger'].debug('NO updates for user with definedColumns: {}'.format(definedColumns))
					response.status = HTTP_400

	except:
		errorMessage(request, response)

	## end updateSpecificApiConsumerAccess
	return cleanPayload(request)


@hugWrapper.delete('/ApiConsumerAccess/{user}')
def deleteSpecificApiConsumerAccess(user:text, request, response):
	"""Delete entry that contains the provided user."""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.ApiConsumerAccess).filter(platformSchema.ApiConsumerAccess.name==user).first()
		if dataHandle is None:
			request.context['payload']['errors'].append('No ApiConsumerAccess exists with the user {}'.format(user))
			response.status = HTTP_404
		else:
			request.context['dbSession'].delete(dataHandle)
			request.context['dbSession'].commit()
			request.context['payload']['Success'] = 'Removed ApiConsumerAccess entry with the user {}'.format(user)

	except:
		errorMessage(request, response)

	## end deleteSpecificApiConsumerAccess
	return cleanPayload(request)


@hugWrapper.get('/cred')
def getCredResource(request, response):
	"""Get available resources for ./config/cred."""
	try:
		request.context['payload']['Types'] = credTypes.keys()
	except:
		errorMessage(request, response)

	## end getCredResource
	return cleanPayload(request)


@hugWrapper.get('/cred/{credType}')
def getCredByType(credType:text, request, response):
	"""Report all cred entries of the provided type."""
	try:
		if credType.lower() not in credTypes.keys():
			request.context['payload']['errors'].append('Invalid resource')
			response.status = HTTP_404
		else:
			dbTable = credTypes[credType.lower()]
			results = request.context['dbSession'].query(dbTable).all()
			ignoreList = ['object_id', 'password', 'community_string', 'token']
			for item in results:
				request.context['payload'][item.object_id] = { col:getattr(item, col) for col in inspect(item).mapper.c.keys() if col not in ignoreList}
			## Standard conversions of dates to string
			request.context['payload'] = json.loads(json.dumps(request.context['payload'], default=utils.customJsonDumpsConverter))

	except:
		errorMessage(request, response)

	## end getCredByType
	return cleanPayload(request)


@hugWrapper.post('/cred/{credType}')
def postCredByType(credType:text, content:hugJson, request, response):
	"""Posts new cred entry."""
	try:
		if hasRequiredData(request, response, content, ['source']):
			if credType.lower() not in credTypes.keys():
				request.context['payload']['errors'].append('Invalid resource')
				response.status = HTTP_404
			else:
				dbTable = credTypes[credType.lower()]
				source = mergeUserAndSource(content, request)
				content['object_created_by'] = source
				## Handle sensitive strings
				tool = None
				if content.get('wrench'):
					tool = content.pop('wrench')
				externalEncryptionLibrary = utils.loadExternalLibrary('externalEncryptionLibrary', env, globalSettings)
				for key in ['password', 'community_string', 'token']:
					if key in content:
						(content[key], other) = externalEncryptionLibrary.transform(content[key], tool)
				request.context['logger'].info('postCredByType: content: {}'.format(content))
				dataHandle = dbTable(**content)
				request.context['dbSession'].add(dataHandle)
				request.context['dbSession'].commit()
				request.context['payload']['Response'] = 'Success'

	except:
		errorMessage(request, response)

	## end postCredByType
	return cleanPayload(request)


@hugWrapper.delete('/cred/{credType}')
def deleteCredByType(credType:text, request, response):
	"""Delete all stored cred entries of requested type."""
	try:
		dbTable = credTypes[credType.lower()]
		results = request.context['dbSession'].query(dbTable).all()
		for item in results:
			request.context['dbSession'].delete(item)
		request.context['dbSession'].commit()
		request.context['payload']['Success'] = 'Removed all {} entries'.format(credType)

	except:
		errorMessage(request, response)

	## end deleteCredByType
	return cleanPayload(request)


@hugWrapper.get('/cred/{credType}/{credId}')
def getSpecificCred(credType:text, credId:text, request, response):
	"""Get details of a cred entry with this id."""
	try:
		dbTable = credTypes[credType.lower()]
		ignoreList = ['object_id']
		result = request.context['dbSession'].query(dbTable).filter(dbTable.object_id==credId).first()
		if result:
			for col in inspect(result).mapper.c.keys():
				if col not in ignoreList:
					request.context['payload'][col] = getattr(result, col)
			## Standard conversions of dates to string
			request.context['payload'] = json.loads(json.dumps(request.context['payload'], default=utils.customJsonDumpsConverter))
		else:
			request.context['payload']['errors'].append('No {} cred entry with the requested id {}'.format(credType, credId))
			response.status = HTTP_404

	except:
		errorMessage(request, response)

	## end getSpecificCred
	return cleanPayload(request)


@hugWrapper.put('/cred/{credType}/{credId}')
def updateSpecificCred(credType:text, credId:text, content:hugJson, request, response):
	"""Update entry by the provided name"""
	try:
		if hasRequiredData(request, response, content, ['source']):
			dbTable = credTypes[credType.lower()]
			result = request.context['dbSession'].query(dbTable).filter(dbTable.object_id==credId).first()
			if result is None:
				request.context['payload']['errors'].append('No {} cred entry with the requested id {}, in order to update. Use POST on ./config/cred/{} to create.'.format(credType, credId, credType))
				response.status = HTTP_404
			else:
				request.context['logger'].debug('result: {}'.format(result))
				tempObjectId = result.object_id
				tool = None
				if content.get('wrench'):
					tool = content.pop('wrench')
				## Set the source
				source = mergeUserAndSource(content, request)
				definedColumns = [col for col in inspect(dbTable).mapper.c.keys() if col not in ['name', 'object_id', 'time_created', 'object_created_by', 'time_updated', 'object_updated_by']]
				## If any provided columns are valid for this class, then merge:
				if any(col in content.keys() for col in definedColumns):
					content['object_updated_by'] = source
					content['object_id'] = tempObjectId
					## Handle sensitive strings
					externalEncryptionLibrary = utils.loadExternalLibrary('externalEncryptionLibrary', env, globalSettings)
					for key in ['password', 'community_string', 'token']:
						if key in content.keys():
							(content[key], other) = externalEncryptionLibrary.transform(content[key], tool)
					result = dbTable(**content)
					result = request.context['dbSession'].merge(result)
					request.context['dbSession'].commit()
					request.context['payload']['Response'] = 'Updated {} cred entry with id {}'.format(credType, credId)
				else:
					request.context['payload']['Response'] = 'No valid columns provided for updating {} cred entry {}'.format(credType, credId)
	except:
		errorMessage(request, response)

	## end updateSpecificCred
	return cleanPayload(request)


@hugWrapper.delete('/cred/{credType}/{credId}')
def deleteSpecificCred(credType:text, credId:text, request, response):
	"""Delete entry that contains the provided name."""
	try:
		dbTable = credTypes[credType.lower()]
		result = request.context['dbSession'].query(dbTable).filter(dbTable.object_id==credId).first()
		if result is None:
			request.context['payload']['errors'].append('No {} cred entry with the requested id {}.'.format(credType, credId))
			response.status = HTTP_404
		else:
			request.context['dbSession'].delete(result)
			request.context['dbSession'].commit()
			request.context['payload']['Success'] = 'Removed {} cred entry with the requested id {}.'.format(credType, credId)

	except:
		errorMessage(request, response)

	## end deleteSpecificCred
	return cleanPayload(request)


@hugWrapper.get('/Realm')
def getAllRealmNames(request, response):
	"""Get all realm names."""
	try:
		results = request.context['dbSession'].query(platformSchema.Realm)
		if results:
			realms = {}
			for entry in results:
				thisRealm = { col:getattr(entry, col) for col in inspect(entry).mapper.c.keys() }
				realms[entry.name] = thisRealm
			request.context['payload']['realms'] = realms
		else:
			request.context['payload']['Response'] = 'No realms defined'

	except:
		errorMessage(request, response)

	## end getAllRealmNames
	return cleanPayload(request)


@hugWrapper.post('/Realm/{realmName}')
def insertNewRealmName(realmName:text, request, response):
	"""Insert a named realm"""
	try:
		dataHandle = request.context['dbSession'].query(platformSchema.Realm).filter(platformSchema.Realm.name==realmName).first()
		if dataHandle is not None:
			request.context['payload']['errors'].append('Realm name already exists: {realmName!r}'.format(realmName=realmName))
			response.status = HTTP_404
		else:
			thisEntry = platformSchema.Realm(name=realmName)
			request.context['dbSession'].add(thisEntry)
			request.context['dbSession'].commit()
			request.context['payload']['Response'] = 'Inserted realm: {realmName}'.format(realmName=realmName)

	except:
		errorMessage(request, response)

	## end insertNewRealmName
	return cleanPayload(request)


@hugWrapper.delete('/Realm/{realmName}')
def deleteRealmByName(realmName:text, request, response):
	"""Delete realm by name."""
	try:
		dbTable = platformSchema.Realm
		dataHandle = request.context['dbSession'].query(dbTable).filter(dbTable.name==realmName).first()
		request.context['dbSession'].commit()
		if dataHandle is None:
			request.context['payload']['errors'].append('Realm by this name does not exist: {realmName!r}'.format(realmName=realmName))
			response.status = HTTP_404
		else:
			## See if there are any NetworkScopes or a RealmScope for the realm.
			## If so, they have to go before we can remove the realm; otherwise
			## it violates foreign key constraints on those tables.
			for dbTable in [platformSchema.NetworkScope, platformSchema.RealmScope]:
				results = request.context['dbSession'].query(dbTable).filter(dbTable.realm==realmName).all()
				if results:
					for obj in results:
						request.context['logger'].debug('Removing scope object {} with ID {}...'.format(type(obj), obj.object_id))
						request.context['dbSession'].delete(obj)
						request.context['dbSession'].commit()
			## Same thing for any protocol entries... need to remove those too.
			## We really should not static code this here, rather get the child
			## listing automatically. Not sure how to skip the middle abstract
			## classes like ProtocolShell though, so for now it's static:
			for dbTable in [platformSchema.ProtocolSnmp, platformSchema.ProtocolWmi, platformSchema.ProtocolSsh, platformSchema.ProtocolPowerShell, platformSchema.ProtocolRestApi]:
				results = request.context['dbSession'].query(dbTable).filter(dbTable.realm==realmName).all()
				if results:
					for obj in results:
						request.context['logger'].debug('Removing cred object {} with ID {}...'.format(type(obj), obj.object_id))
						request.context['dbSession'].delete(obj)
						request.context['dbSession'].commit()
			## Now delete the initial realm
			dbTable = platformSchema.Realm
			targetRealm = request.context['dbSession'].query(dbTable).filter(dbTable.name==realmName).first()
			request.context['dbSession'].delete(targetRealm)
			request.context['dbSession'].commit()
			request.context['payload']['Response'] = 'Deleted the realm: {realmName}'.format(realmName=realmName)

	except:
		errorMessage(request, response)

	## end deleteRealmByName
	return cleanPayload(request)


@hugWrapper.get('/NetworkScope')
def getNetworkScope(request, response):
	"""Report all entries in NetworkScope.

	Report all entries from NetworkScope. These were provided by users as IPs,
	IP ranges, or Networks, before being translated into networks that are then
	given to the Realm. These are not directly used by the tool, but rather
	provide the bread crumb trail to determine how RealmScope was generated.
	"""
	try:
		dbTable = platformSchema.NetworkScope
		results = request.context['dbSession'].query(dbTable)
		parseNetworkScope(request, response, results)

	except:
		errorMessage(request, response)

	## end getNetworkScope
	return cleanPayload(request)


@hugWrapper.post('/NetworkScope')
def addNetworkScope(content:hugJson, request, response):
	"""Validate, transform, and insert a single user-provided scope entry.
	"""
	try:
		request.context['logger'].debug('NetworkScope content: {}'.format(content))
		if hasRequiredData(request, response, content, ['realm', 'source', 'data']):
			targetIpAddresses = []

			ipCount = realmScope.parseEntry(targetIpAddresses, content.get('data', {}), request.context['logger'])
			## Set the source
			source = mergeUserAndSource(content, request)
			content['object_created_by'] = source
			realm = content.get('realm')
			active = utils.valueToBoolean(content.get('active'))
			description = content.get('description')
			data = content.get('data')
			transformed = str(targetIpAddresses)
			object_created_by = source
			## Insert the new scope into the NetworkScope table
			thisEntry = platformSchema.NetworkScope(realm=realm, active=active, description=description, count=ipCount, data=data, transformed=transformed, object_created_by=object_created_by)
			request.context['dbSession'].add(thisEntry)
			request.context['dbSession'].commit()
			request.context['payload']['Success'] = 'IP count for inserted scope: {}'.format(ipCount)
			request.context['payload']['object_id'] = thisEntry.object_id
			recalculateRealmScope(request, response, realm)

	except:
		errorMessage(request, response)

	## end addNetworkScope
	return cleanPayload(request)


@hugWrapper.get('/NetworkScope/{realm}')
def getNetworkScopeByRealm(realm:text, request, response):
	"""Report all Network Scope entries belonging to the provided realm."""
	try:
		dbTable = platformSchema.NetworkScope
		results = request.context['dbSession'].query(dbTable).filter(dbTable.realm==realm).all()
		parseNetworkScope(request, response, results, realm)

	except:
		errorMessage(request, response)

	## end getNetworkScopeByRealm
	return cleanPayload(request)


@hugWrapper.delete('/NetworkScope/{realm}')
def deleteNetworkScopeByRealm(realm:text, request, response):
	"""Delete all Network Scope entries belonging to the provided realm."""
	try:
		dbTable = platformSchema.NetworkScope
		results = request.context['dbSession'].query(dbTable).filter(dbTable.realm==realm).all()
		if results:
			for obj in results:
				request.context['dbSession'].delete(obj)
				request.context['dbSession'].commit()
				recalculateRealmScope(request, response, realm)
		else:
			request.context['payload']['errors'].append('Realm Name {realm} doesn\'t exist'.format(realm=realm))
			response.status = HTTP_404

	except:
		errorMessage(request, response)

	## end deleteNetworkScopeByRealm
	return cleanPayload(request)


@hugWrapper.delete('/NetworkScope/{realm}/{object_id}')
def deleteNetworkScopeByRealmOjbectId(realm:text, object_id:text, request, response):
	"""Report all Network Scope entries belonging to the provided realm."""
	try:
		dbTable = platformSchema.NetworkScope
		if request.context['dbSession'].query(dbTable).filter(dbTable.realm==realm).all():
			try:
				result = request.context['dbSession'].query(dbTable).filter(and_(dbTable.realm==realm, dbTable.object_id == int(object_id))).first()
				if result:
					request.context['dbSession'].delete(result)
					request.context['dbSession'].commit()
					recalculateRealmScope(request, response, realm)
				else:
					request.context['payload']['errors'].append('Object_id {object_id} doesn\'t exist in the realm {realm}'.format(object_id=object_id, realm=realm))
					response.status = HTTP_404
			except:
				request.context['payload']['errors'].append('{}'.format(str(sys.exc_info()[1])))
				response.status = HTTP_500
		else:
			request.context['payload']['errors'].append('Realm Name {realm} doesn\'t exist'.format(realm=realm))
			response.status = HTTP_404

	except:
		errorMessage(request, response)

	## end deleteNetworkScopeByRealmOjbectId
	return cleanPayload(request)


@hugWrapper.get('/NetworkScope/{realm}/{object_id}')
def getNetworkScopeByRealmOjbectId(realm:text, object_id:text, request, response):
	"""Report all Network Scope entries belonging to the provided realm."""
	try:
		dbTable = platformSchema.NetworkScope
		if request.context['dbSession'].query(dbTable).filter(dbTable.realm==realm).all():
			results = request.context['dbSession'].query(dbTable).filter(and_(dbTable.realm==realm, dbTable.object_id == int(object_id))).first()
			if results:
				for col in inspect(results).mapper.c.keys():
					request.context['payload'][col] = getattr(results, col)
			else:
				request.context['payload']['errors'].append('object_id {object_id} doesn\'t exist under the realm {realm}'.format(object_id=object_id, realm=realm))
				response.status = HTTP_404
		else:
			request.context['payload']['errors'].append('Realm Name {realm} doesn\'t exist'.format(realm=realm))
			response.status = HTTP_404
		request.context['dbSession'].commit()

	except:
		errorMessage(request, response)

	## end getNetworkScopeByRealmOjbectId
	return cleanPayload(request)


@hugWrapper.get('/RealmScope')
def getRealmScope(request, response):
	"""Report all entries in RealmScope."""
	try:
		dbTable = platformSchema.RealmScope
		results = request.context['dbSession'].query(dbTable)
		if results:
			scopes = []
			for entry in results:
				thisScope = { col:getattr(entry, col) for col in inspect(entry).mapper.c.keys() }
				scopes.append(thisScope)
			request.context['payload']['scopes'] = scopes
		else:
			request.context['payload']['Response'] = 'No NetworkScope defined'

	except:
		errorMessage(request, response)

	## end getRealmScope
	return cleanPayload(request)


@hugWrapper.get('/client')
def getClients(request, response):
	"""List all previously registered service clients."""
	try:
		for tableName in clientToEndpointTableClass:
			dbTable = clientToEndpointTableClass[tableName]
			results = request.context['dbSession'].query(dbTable)
			if results:
				clients = []
				for entry in results:
					request.context['logger'].debug('Key match found for [{}]'.format(entry.name))
					clients.append(entry.name)
				request.context['payload'][tableName] = clients

	except:
		errorMessage(request, response)

	## end getClients
	return cleanPayload(request)


@hugWrapper.get('/client/{endpointName}')
def getClientByName(endpointName, request, response):
	"""Report details on the provided endpoint."""
	try:
		matched = False
		for tableName in clientToEndpointTableClass:
			dbTable = clientToEndpointTableClass[tableName]
			results = request.context['dbSession'].query(dbTable)
			matchedEntry = request.context['dbSession'].query(dbTable).filter(dbTable.name == endpointName).first()
			if matchedEntry:
				request.context['logger'].debug('Key match found for [{}]'.format(matchedEntry.name))
				request.context['payload']['endpointName'] = matchedEntry.name
				request.context['payload']['platformType'] = matchedEntry.platform_type
				request.context['payload']['platformSystem'] = matchedEntry.platform_system
				request.context['payload']['platformMachine'] = matchedEntry.platform_machine
				request.context['payload']['platformVersion'] = matchedEntry.platform_version
				request.context['payload']['cpuType'] = matchedEntry.cpu_type
				request.context['payload']['cpuCount'] = matchedEntry.cpu_count
				request.context['payload']['memoryTotal'] = matchedEntry.memory_total
				request.context['payload']['health'] = {}
				matched = True
				## Now add health info from active clients on this endpoint
				for tableName2 in clientToHealthTableClass:
					dbTable2 = clientToHealthTableClass[tableName2]
					results = request.context['dbSession'].query(dbTable2)
					matchSet = request.context['dbSession'].query(dbTable2).all()
					clientHealth = []
					for entry in matchSet:
						thisClientName = entry.name
						if re.search('{}\-\d+'.format(endpointName), thisClientName, re.I):
							clientHealth.append({ col:getattr(entry, col) for col in inspect(entry).mapper.c.keys() })
					request.context['payload']['health'][tableName2] = clientHealth
				break
		if not matched:
			request.context['payload']['errors'].append('Client endpoint does not exist: {}'.format(endpointName))
			response.status = HTTP_404

	except:
		errorMessage(request, response)

	## end getClientByName
	return cleanPayload(request)


@hugWrapper.get('/search')
def getPlatformSchemaClasses(request, response):
	"""Show available platform schema classes that can be searched."""
	try:
		availableClasses = [name for name, obj in pythonInspect.getmembers(platformSchema, pythonInspect.isclass) if obj.__module__ == 'database.schema.platformSchema']
		request.context['payload']['Available classes'] = availableClasses

	except:
		errorMessage(request, response)

	## end getPlatformSchemaClasses
	return cleanPayload(request)


@hugWrapper.get('/search/{className}')
def getSearchResults(className, content:hugJson, request, response):
	"""Query specified class in platform schema, using the provided filter.

	Sample content:
	============================================================
	"content": {
		"count": false,
		"filter": [{
			"operator": "and",
			"expression": [{
					"condition": {
						"attribute": "name",
						"operator": "==",
						"value": "TestCluster.com"
					}
				},{
					"condition": {
						"attribute": "group_type",
						"operator": "==",
						"value": "test harness"
					}
				}
			]
		}]}
	============================================================
	"""
	try:
		if hasRequiredData(request, response, content, ['filter']):
			filterConditions = content.get('filter')
			countResult = content.pop('count', False)
			dbTable = eval('platformSchema.{}'.format(className))
			searchThisContentHelper(request, response, filterConditions, dbTable, countResult, False)

	except:
		errorMessage(request, response)

	## end getSearchResults
	return cleanPayload(request)


@hugWrapper.delete('/search/{className}')
def removeSearchResults(className, content:hugJson, request, response):
	"""Delete results from specified class in platform schema, using provided filter."""
	try:
		if hasRequiredData(request, response, content, ['filter']):
			filterConditions = content.get('filter')
			countResult = content.pop('count', False)
			dbTable = eval('platformSchema.{}'.format(className))
			searchThisContentHelper(request, response, filterConditions, dbTable, countResult, True)
	except:
		errorMessage(request, response)

	## end removeSearchResults
	return cleanPayload(request)
