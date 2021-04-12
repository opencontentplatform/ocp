"""Root resource for the Open Content Platform REST API.

This module does the setup required for API resources to be hosted through the
selected technologies. We use Twisted Web for our WSGI (Python web server), Hug
to expose functions to the API, Falcon (which Hug wraps) for the web framework,
and SqlAlchemy for the ORM and database layer.

Setup in short:

1. modify the sys path, load modules, and set the root url for this API
2. setup a logger to use for API work
3. establish a connection to the database
4. setup Falcon middleware to share the logger and database resources
5. setup Hug to load our API modules
6. create a brief, high-level response for users hitting the root url

API resources::

	/<root>/data
	/<root>/tool
	/<root>/job
	/<root>/query
	/<root>/config
	/<root>/task
	/<root>/archive

.. hidden::

	Author: Chris Satterthwaite (CS)
	Version info:
	  1.0 : (CS) Created Sep 15, 2017
	  1.1 : (CS) Updated for endpoint access and client authentication, Oct 2017
	  1.2 : (CS) Added query, job, and archive methods
	  1.3 : (CS) Split the global module into separate modules per API resource
	  1.4 : (CS) Moved SqlAlchemy DB session into falcon middleware, Aug 30, 2019
	  1.5 : (CS) Replaced apiUtils with Falcon middleware, Sep 2, 2019

"""

import os
import hug
import sys
import traceback
import logging

## Setup sys.path and load global settings
path = os.path.dirname(os.path.abspath(__file__))
import env
env.addLibPath()
import utils
from apiHugWrapper import hugWrapper
globalSettings = utils.loadSettings(os.path.join(env.configPath, "globalSettings.json"))
## Set root context (base path) for the API, as directed by the global setting
root = '/{}'.format(globalSettings.get('apiContextRoot', 'ocp'))

## Setup the logger
## Note: the default Python logger and the Twisted logger both had problems with
## trying to rotate after the size limit with I/O errors on closing the file. So
## to handle multi-process/thread access, we use concurrent-log-handler.
#logger = utils.setupLogger('ApiApplication', env, 'logSettingsServices.json', directoryName='service')
logger = logging.getLogger('ApiApplication')
logger.info('Starting apiResourceRoot')

## Create a global context for sharing the DB connection pool. When using a
## scoped_session in sqlalchemy, the code checks if there is was a previous
## thread-local session created. When one already exists, sqlalchemy will simply
## reuse it. And in order to get the thread-local session to URL functions, we
## use a middleware class (SQLAlchemySessionMiddleware below). This allows us to
## share database resources across API connections.
from database.connectionPool import DatabaseClient
dbClient = DatabaseClient(logger, globalSettings=globalSettings, env=env, poolSize=20, maxOverflow=7, poolRecycle=1800)
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

class VariableAndLoggerMiddleware:
	"""Settup variables, logging, and log each API request."""
	def __init__(self, logger, root, env, globalSettings):
		### Get a handle on the global logger
		self.logger = logger
		self.baseUrl = root
		self.env = env
		self.globalSettings = globalSettings

	def process_resource(self, request, response, resource, parameters):
		errors = []
		try:
			## Expose falcon variables for Hug
			request.context['logger'] = self.logger
			request.context['baseUrl'] = self.baseUrl
			## Expose env and globalSettings params needed by functions
			request.context['kafkaEndpoint'] = self.globalSettings['kafkaEndpoint']
			request.context['kafkaTopic'] = self.globalSettings['kafkaTopic']
			request.context['kafkaQueryTopic'] = self.globalSettings['kafkaQueryTopic']
			request.context['useCertificatesWithKafka'] = self.globalSettings['useCertificatesWithKafka']
			request.context['kafkaCaRootFile'] = self.globalSettings['kafkaCaRootFile']
			request.context['kafkaCertificateFile'] = self.globalSettings['kafkaCertificateFile']
			request.context['kafkaKeyFile'] = self.globalSettings['kafkaKeyFile']
			request.context['envConfigPath'] = self.env.configPath
			request.context['envCertPath'] = self.env.privateInternalCertPath
			request.context['envLogPath'] = self.env.logPath
			request.context['envApiQueryPath'] = self.env.apiQueryPath
			request.context['envContentGatheringSharedConfigGroupPath'] = self.env.contentGatheringSharedConfigGroupPath
			## Create an errors section so we can simply append within functions
			request.context['payload'] = {'errors': []}
		except:
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			print(exceptionOnly)
			self.logger.error('Failure in VariableAndLoggerMiddleware: {}'.format(exceptionOnly))
			errors.append(exceptionOnly)

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
hug.API(__name__).http.add_middleware(VariableAndLoggerMiddleware(logger, root, env, globalSettings))


## Import the individual API Resource modules
import apiResourceData
import apiResourceTool
import apiResourceJob
import apiResourceQuery
import apiResourceConfig
import apiResourceTask
import apiResourceArchive

## Expand the HUG framework to use all the API resource modules
hug.API(__name__).extend(apiResourceData, root+'/data')
hug.API(__name__).extend(apiResourceTool, root+'/tool')
hug.API(__name__).extend(apiResourceJob, root+'/job')
hug.API(__name__).extend(apiResourceQuery, root+'/query')
hug.API(__name__).extend(apiResourceConfig, root+'/config')
hug.API(__name__).extend(apiResourceTask, root+'/task')
hug.API(__name__).extend(apiResourceArchive, root+'/archive')


## Disable Hug's 404 auto-generated response
@hug.not_found()
def not_found_handler():
    return "Not Found"


## And now finally a brief, high-level response to users for the root URL
@hugWrapper.get(root)
def getOCP(response):
	"""Report available API endpoints."""
	apiResources = [root+"/data",
					root+"/tool",
					root+"/job",
					root+"/query",
					root+"/config",
					root+"/task",
					root+"/archive"]
	payload = {"Open Content Platform REST API Endpoints" : apiResources}

	## end getOCP
	return payload


## Functions in the individual resource modules should follow this format:
## ===========================================================================
## @hugWrapper.get('/path')
## def functionName(request, response):
## 	"""Corresponding doc string"""
## 	try:
## 		<custom code here>
##
## 	except:
## 		errorMessage(request, response)
##
## 	## end functionName
## 	return cleanPayload(request)
## ===========================================================================
