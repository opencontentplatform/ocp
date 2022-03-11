"""Utility for service/client authentication."""
import sys
import traceback
import os
import uuid
import json
import re
import io
import hug
from hug.types import text
from falcon import HTTP_401, HTTP_500
from contextlib import suppress
import logging

## Add openContentPlatform directories onto the sys path
import env
env.addLibPath()
import utils
import database.schema.platformSchema as platformSchema


## Global section
globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))

clientToEndpointTableClass = {
	'ContentGatheringClient' : platformSchema.ServiceContentGatheringEndpoint,
	'ResultProcessingClient' : platformSchema.ServiceResultProcessingEndpoint,
	'UniversalJobClient' : platformSchema.ServiceUniversalJobEndpoint
}


## Setup the logger
logger = logging.getLogger('ServiceCommunication')
logger.info('Starting serviceCommunication')

## Create a global context for sharing the DB connection pool. When using a
## scoped_session in sqlalchemy, the code checks if there is was a previous
## thread-local session created. When one already exists, sqlalchemy will simply
## reuse it. And in order to get the thread-local session to URL functions, we
## use a middleware class (SQLAlchemySessionMiddleware below). This allows us to
## share database resources across API connections.
from database.connectionPool import DatabaseClient
dbClient = DatabaseClient(logger, globalSettings=globalSettings, env=env, poolSize=3, maxOverflow=2, poolRecycle=1800)
if dbClient is None:
	logger.error('Failed to connect to the shared database connection pool.')
	raise EnvironmentError('Failed to connect to the shared database connection pool.')
dbClient.session.close()
dbClient.session.remove()
dbClient.close()
logger.info('Acquired a handle to the shared database connection pool.')


#############################################################################
## Falcon middleware section
#############################################################################
class SQLAlchemySessionMiddleware:
	"""Aquire and release a DB connection for each API request.

	This extends our SqlAlchemy session onto the request.context, for functions
	to use: request.context['dbSession']
	"""
	def __init__(self, dbClient):
		### Get a handle on the scoped session
		self.dbSession = dbClient.session

	def process_resource(self, request, response, resource, parameters):
		### Acquire a database resource from the shared pool
		request.context['dbSession'] = self.dbSession()

	def process_response(self, request, response, resource, req_succeeded):
		if request.context.get('dbSession'):
			if not req_succeeded:
				request.context['dbSession'].rollback()
			else:
				request.context['dbSession'].commit()
			### Release the database resource back to the pool
			request.context['dbSession'].close()
			self.dbSession.remove()

class AccessAndLoggerMiddleware:
	"""Settup logging, validate user, and log each API request.
	
	This extends the following variables onto the request.context, for functions
	to use::
	
		request.context['logger']
		request.context['apiUser']
		request.context['payload'] = {'errors': []}
	
	"""
	def __init__(self, logger):
		### Get a handle on the global logger
		self.logger = logger

	def process_resource(self, request, response, resource, parameters):
		errors = []
		authenticated = False
		requireWritePerm = False
		requireDeletePerm = False
		requireAdminPerm = False
		try:
			request.context['payload'] = {'errors': []}
			dbSession = request.context['dbSession']
			request.context['logger'] = self.logger
			apiUser = 'serviceClient'
			apiKey = request.get_header('endpointKey')
			allHeaders = request.headers
			apiTable = platformSchema.ApiAccess
			matchedEntry = dbSession.query(apiTable).filter(apiTable.key == apiKey).first()
			if matchedEntry:
				## Make sure the user matched what was provided
				if (apiUser == matchedEntry.name):
					authenticated = True
				else:
					self.logger.error('Potential security concern. Valid key provided but the user was incorrect. User provided was {} when database lists user as {}'.format(apiUser, matchedEntry.name))
					errors.append('Access denied.')
			else:
				self.logger.info('User not authenticated.')
				errors.append('Access denied.')

		except:
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			self.logger.error('Failure checking access: {}'.format(str(exceptionOnly)))
			errors.append(exceptionOnly)

		## Authenticate user/client key
		if not authenticated:
			response.status = HTTP_401
			response.complete = True
			response.body = json.dumps({'errors': errors})

	def process_response(self, request, response, resource, req_succeeded):
		method = request.method
		resource = request.relative_uri
		status = int(response.status[:3])
		user = request.context.get('apiUser')
		if status >= 200 and status < 300:
			self.logger.info('method [{}], resource [{}], status [{}], user [{}]'.format(method, resource, status, user))
		else:
			self.logger.error('method [{}], resource [{}], status [{}], user [{}],'.format(method, resource, status, user))
#############################################################################
#############################################################################

## Extend the above Falcon middleware objects to the HUG framework
hug.API(__name__).http.add_middleware(SQLAlchemySessionMiddleware(dbClient))
hug.API(__name__).http.add_middleware(AccessAndLoggerMiddleware(logger))

## Disable Hug's 404 auto-generated response
@hug.not_found()
def not_found_handler():
	return "Not Found"


@hug.get('/ocpcore/authenticate')
def authenticateServiceClient(endpointName:text, clientType:text, pythonVersion:text, platformType:text, platformSystem:text, platformMachine:text, platformVersion:text, cpuType:text, cpuCount:text, memoryTotal:text, request, response):
	"""Validate OCP clients."""
	try:
		token = None
		payload = None
		## See if the client already exists
		dbTable = clientToEndpointTableClass[clientType]
		matchedEntry = request.context['dbSession'].query(dbTable).filter(dbTable.name == endpointName).first()
		if matchedEntry:
			## Get the token if the client exists
			token = matchedEntry.object_id
			request.context['logger'].debug('Token already existed for [{}]'.format(endpointName))
		else:
			## Create when the client does not exist
			token = uuid.uuid4().hex
			thisEntry = dbTable(name=endpointName, object_id=token, python_version=pythonVersion, platform_type=platformType, platform_system=platformSystem, platform_machine=platformMachine, platform_version=platformVersion, cpu_type=cpuType, cpu_count=cpuCount, memory_total=memoryTotal)
			request.context['dbSession'].add(thisEntry)
			request.context['dbSession'].commit()
			request.context['logger'].debug('New token created new for [{}]'.format(endpointName))
		## Set the token to return
		payload = { 'token': token }

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		request.context['logger'].error('Failure in authenticateServiceClient: {}'.format(stacktrace))
		response.status = HTTP_500

	## end authenticateServiceClient
	return payload
