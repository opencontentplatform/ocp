"""Networked service wrapper; used by all services requiring clients.

Classes:

  * :class:`.ServiceProcess` : overrides multiprocessing for service control
  * :class:`.ServiceFactory` : Twisted factory enabling common code paths for
    constructor, destructor, database initialization, kafka communication, and
    other shared functions.
  * :class:`.ServiceListener` : Twisted protocol for this shared factory
  * :class:`.CustomLineReceiverProtocol` : Override default delimiter


.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Aug 24, 2017

"""

import sys
import traceback
import os
import re
import uuid
import time
import datetime
import json
import copy
import platform
import psutil
import requests
import multiprocessing
import logging, logging.handlers
from contextlib import suppress
from twisted.internet.protocol import ServerFactory
from twisted.protocols.basic import LineReceiver
from twisted.python.filepath import FilePath
from sqlalchemy import exc
from confluent_kafka import KafkaError
from twisted.internet import threads

## Add openContentPlatform directories onto the sys path
frameworkPath = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
if frameworkPath not in sys.path:
	sys.path.append(frameworkPath)
import env
env.addLibPath()
env.addExternalPath()

## From openContentPlatform
import utils
from utils import logExceptionWithSelfLogger
from coreService import CoreService
## Using an externally provided library defined in globalSettings and located
## in '<install_path>/external'.
externalProtocolHandler = utils.loadExternalLibrary('externalProtocolHandler')
from database.connectionPool import DatabaseClient


## Overriding max length from 16K to 64M
LineReceiver.MAX_LENGTH = 1024*1024*64

class CustomLineReceiverProtocol(LineReceiver):
	"""Overriding the default delimiter"""
	## Using LineReceiver instead of Protocol, to leverage the caching/splitting
	## for partial and multiple messages coming from the TCP stream. Using a
	## custom delimiter because the data may contain the default '\r\n'.
	delimiter = b':==:'


class ServiceListener(CustomLineReceiverProtocol):
	"""Receives and sends data through protocol of choice."""

	def __init__(self):
		self.clientName = None
		super().__init__()


	def connectionLost(self, reason):
		"""Disconnect the client and do a cleanup on the corresponding client."""
		self.factory.logger.warn('Connection lost to [{clientName!r}]', clientName=self.clientName)
		self.factory.removeClient(self, self.clientName)


	def lineReceived(self, line):
		self.factory.logger.debug('SERVICE dataReceived: [{line!r}]', line=line)
		self.processData(line)


	def processData(self, line):
		"""Process communication coming from an instance of the client process.

		Transform received bytes (in JSON format) into dictionary structures,
		figure out what type of action is being requested, and send the content
		of the communcation to be processed according to the action requested.

		Arguments:
		  data : bytes received from client

		"""
		try:
			dataDict = json.loads(line)
			action = dataDict['action']
			content = dataDict['content']
			## Special for the initial connection
			if action == 'connectionRequest':
				self.doConnectionRequest(content)
			elif self.factory.validateAction(action):
				endpointName = dataDict['endpointName']
				endpointToken = dataDict['endpointToken']
				if (not self.factory.clientJustConnected(endpointName, endpointToken, action) and
					not self.factory.validateClient(endpointName, endpointToken)):
					self.factory.logger.debug('Endpoint NOT authorized: {endpointName!r}', endpointName=endpointName)
					## Add the action to the content and send it back to the
					## client, so that the client can resubmit the message after
					## it goes through its authorization loop again; this is
					## intended to adhear to security but avoid data loss.
					content['action'] = action
					self.constructAndSendData('tokenExpired', content)
					return
				## Loop over 2 collections with zip, instead of using list index
				for thisAction, thisMethod in zip(self.factory.validActions, self.factory.actionMethods):
					if action == thisAction:
						self.factory.logger.debug('Server requests action [{action!r}]', action=action)
						eval('self.{}'.format(thisMethod))(content)
						break
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.factory.logger.error('Exception: {exception!r}', exception=exception)

		## end processData
		return


	def constructAndSendData(self, action, content):
		"""Builds a JSON object and send it to the client.

		Arguments:
		  action  : String containing the action name
		  content : Dictionary containing the content based on the action string

		"""
		try:
			message = {}
			message['action'] = action
			message['content'] = content
			self.factory.logger.debug('SERVICE constructAndSendData to {client!r}: {message!r}', client=self.clientName, message=message)
			jsonMessage = json.dumps(message)
			msg = jsonMessage.encode('utf-8')
			self.sendLine(msg)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.factory.logger.error('Exception in constructAndSendData: {exception!r}', exception=exception)

		## end constructAndSendData
		return


	def doConnectionRequest(self, content):
		"""Receives a connection request from the client instance.

		Checks if the connection request from the client is an authorized client
		before creating a unique instance number and adding it to the list of
		active clients.

		Arguments:
		  content : Dictionary containing the content based on the action string

		"""
		self.factory.logger.debug('doConnectionRequest: content: {content!r}', content=content)
		endpointName = content['endpointName']
		endpointToken = content['endpointToken']
		self.factory.logger.debug('Received new client connection from {endpointName!r}', endpointName=endpointName)
		## Checks if the endpoint is an authorized endpoint.
		if not self.factory.validateClient(endpointName, endpointToken):
			## For clients connecting the very first time, their keys were just
			## created in the database, so we'll need to get an updated list
			self.factory.getServiceClients()
			if not self.factory.validateClient(endpointName, endpointToken):
				self.constructAndSendData('connectionResponse', {'Response' : 'Not authorized to use this service'})
				return

		## Get a thread/process type integer representing this active client;
		## note, since multiple clients of the same service can run on the same
		## server - we need to manage by more than just OS name; add instance.
		instanceNumber = 0
		for thisName, thisValue in self.factory.activeClients.items():
			(thisEndpoint, thisNumber, thisClient) = thisValue
			if thisEndpoint == endpointName:
				if thisNumber > instanceNumber:
					instanceNumber = thisNumber
		instanceNumber += 1
		self.clientName = '{}-{}'.format(endpointName, instanceNumber)
		self.factory.activeClients[self.clientName] = (endpointName, instanceNumber, self)
		self.factory.logger.debug('Added client [{clientName!r}] to activeClients', clientName=self.clientName)

		## Let the client know it's registered name
		content = {}
		content['clientName'] = self.clientName
		self.constructAndSendData('connectionResponse', content)
		## Get the first health update to seed the service_endpoint_health table
		self.constructAndSendData('healthRequest', {})

		## end doConnectionRequest
		return


	def doReAuthorization(self, content):
		"""Receives a re-authorization request from the client instance.

		Similar to the doConnectionRequest, but used routinely after a client
		has already connected and was assigned a unique name. This prevents the
		re-authorization attempts from assigning new/additional unique names.

		Arguments:
		  content : Dictionary containing the content based on the action string

		"""
		self.factory.logger.debug('doReAuthorization: content: {content!r}', content=content)
		endpointName = content['endpointName']
		endpointToken = content['endpointToken']
		self.factory.logger.debug('Received new client connection from {endpointName!r}', endpointName=endpointName)
		## Checkes if the endpoint is an authorized endpoint.
		if not self.factory.validateClient(endpointName, endpointToken):
			self.constructAndSendData('unauthorized', {'Response' : 'Not authorized to use this service'})
			return

		## end doReAuthorization
		return


	def doHealthResponse(self, content):
		"""Process client health response.

		Inserts or updates received client's system health information into the
		appropriate ServiceEndpointHealth table.

		Arguments:
		  content : Dictionary containing client system health information.

		"""
		## May later update the DB table to reflect this or just log?
		self.factory.logger.debug('Health response from [{clientName!r}]: {content!r}', clientName=self.clientName, content=content)
		## The first response from a connecting client will always be empty
		if len(content) <= 0:
			return
		found = False
		try:
			self.factory.logger.debug('Attempting to update health entry for client [{clientName!r}]', clientName=self.clientName)
			ServiceEndpointHealth = self.factory.serviceHealthTable
			clients = self.factory.dbClient.session.query(ServiceEndpointHealth).all()
			self.factory.dbClient.session.commit()
			for serviceClient in clients:
				thisName = serviceClient.name
				if thisName == self.clientName:
					## Client exists; pull current record and update
					clientObject = self.factory.dbClient.session.query(ServiceEndpointHealth).filter(ServiceEndpointHealth.name == thisName).first()
					setattr(clientObject, 'last_system_status', content.get('lastSystemStatus'))
					setattr(clientObject, 'cpu_avg_utilization', content['cpuAvgUtilization'])
					setattr(clientObject, 'memory_aprox_total', content['memoryAproxTotal'])
					setattr(clientObject, 'memory_aprox_avail', content['memoryAproxAvailable'])
					setattr(clientObject, 'memory_percent_used', content['memoryPercentUsed'])
					setattr(clientObject, 'process_cpu_percent', content['processCpuPercent'])
					setattr(clientObject, 'process_memory', content['processMemory'])
					setattr(clientObject, 'process_start_time', content['processStartTime'])
					setattr(clientObject, 'process_run_time', content['processRunTime'])
					self.factory.dbClient.session.add(clientObject)
					self.factory.dbClient.session.commit()
					self.factory.logger.debug('Updated health entry for client [{clientName!r}]', clientName=self.clientName)
					found = True
					break
			if not found:
				## Client does not yet exist; create new
				thisEntry = ServiceEndpointHealth(name=self.clientName,
												  object_id=uuid.uuid4().hex,
												  last_system_status=content.get('lastSystemStatus'),
												  cpu_avg_utilization=content['cpuAvgUtilization'],
												  memory_aprox_total=content['memoryAproxTotal'],
												  memory_aprox_avail=content['memoryAproxAvailable'],
												  memory_percent_used=content['memoryPercentUsed'],
												  process_cpu_percent=content['processCpuPercent'],
												  process_memory=content['processMemory'],
												  process_start_time=content['processStartTime'],
												  process_run_time=content['processRunTime'])
				self.factory.dbClient.session.add(thisEntry)
				self.factory.dbClient.session.commit()
				self.factory.logger.debug('Created new health entry for client [{clientName!r}]', clientName=self.clientName)
			## Return underlying DBAPI connection
			self.factory.dbClient.session.commit()
			self.factory.dbClient.session.close()

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.factory.logger.error('Exception in doHealthResponse: {exception!r}', exception=exception)

		## end doHealthResponse
		return


class ServiceFactory(CoreService, ServerFactory):
	"""Networked service wrapper, used by all services requiring clients.

	Uses twisted.internet.interfaces.IReactorTCP for client/server connections."""

	protocol = ServiceListener

	def __init__(self, serviceName, globalSettings, hasClients=True, getDbClient=True):
		"""Constructor for the ServiceFactory."""
		## Twisted import here to avoid issues with epoll on Linux
		from twisted.internet import task

		## Need to call both inherented constructors with different args, which
		## means using 'super' won't work unless *args and **kwargs are handled:
		##   super().__init__(serviceName, globalSettings, getDbClient)
		## instead, use __init__ methods directly and pass 'self' explicitely:
		CoreService.__init__(self, serviceName, globalSettings, getDbClient)
		ServerFactory.__init__(self)

		self.jobId = 0
		self.activeJobs = {}
		self.lastJobUpdateTime = time.time()

		if getDbClient:
			self.protocolHandler = externalProtocolHandler.ProtocolHandler(self.dbClient, self.globalSettings, env, self.logger)
		if hasClients:
			if self.canceledEvent.is_set():
				self.logger.error('Cancelling startup of networkService')
				return
			self.connectedEndpoints = {}
			self.authorizedEndpoints = {}
			self.activeClients = {}
			self.cleanClientHealthTable()

			## Looping calls use threads.deferToThread() to avoid time delays
			## with blocking the main reactor thread
			self.loopingGetClients = task.LoopingCall(self.deferServiceClients)
			self.loopingGetClients.start(int(globalSettings['waitSecondsBetweenGettingNewClients']))
			self.loopingUpdateClients = task.LoopingCall(self.deferUpdateClientTokens)
			self.loopingUpdateClients.start(int(globalSettings['waitSecondsBetweenForcedTokenRefreshes']))
			self.loopingHealthUpdates = task.LoopingCall(self.deferSendHealthRequest)
			self.loopingHealthUpdates.start(int(globalSettings['waitSecondsBetweenClientHealthUpdates']))
			self.loopingJobUpdates = None
			if self.serviceJobTable is not None:
				self.loopingJobUpdates = task.LoopingCall(self.deferGetJobUpdates)
				self.loopingJobUpdates.start(int(globalSettings['waitSecondsBetweenJobUpdates']))


	def stopFactory(self):
		try:
			self.logger.info('stopFactory called in networkService')
			if self.loopingGetClients is not None:
				self.logger.debug(' stopFactory: stopping loopingGetClients')
				self.loopingGetClients.stop()
				self.loopingGetClients = None
			if self.loopingUpdateClients is not None:
				self.logger.debug(' stopFactory: stopping loopingUpdateClients')
				self.loopingUpdateClients.stop()
				self.loopingUpdateClients = None
			if self.loopingHealthUpdates is not None:
				self.logger.debug(' stopFactory: stopping loopingHealthUpdates')
				self.loopingHealthUpdates.stop()
				self.loopingHealthUpdates = None
			if self.loopingJobUpdates is not None:
				self.logger.debug(' stopFactory: stopping loopingJobUpdates')
				self.loopingJobUpdates.stop()
				self.loopingJobUpdates = None
			if self.protocolHandler is not None:
				self.logger.debug(' stopFactory: removing the protocolHandler')
				del self.protocolHandler
				self.protocolHandler = None
			super().stopFactory()
			self.logger.info(' networkService stopFactory: complete.')

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			print('Exception in networkService stopFactory: {}'.format(exception))
			with suppress(Exception):
				self.logger.debug('Exception: {exception!r}', exception=exception)

		## end stopFactory
		return


	## Note: attempted a general deferFunction(self, functionToCall) below, but
	## the task.LoopingCall didn't like it, hence 4 separate defer functions:
	@logExceptionWithSelfLogger()
	def deferServiceClients(self):
		"""Call getServiceClients in a non-blocking thread."""
		return threads.deferToThread(self.getServiceClients)

	@logExceptionWithSelfLogger()
	def deferUpdateClientTokens(self):
		"""Call updateClientTokens in a non-blocking thread."""
		return threads.deferToThread(self.updateClientTokens)

	@logExceptionWithSelfLogger()
	def deferSendHealthRequest(self):
		"""Call sendHealthRequest in a non-blocking thread."""
		return threads.deferToThread(self.sendHealthRequest)

	@logExceptionWithSelfLogger()
	def deferGetJobUpdates(self):
		"""Call getJobUpdates in a non-blocking thread."""
		return threads.deferToThread(self.getJobUpdates)


	def getSpecificJob(self, jobName):
		jobSettings = None
		## Get job descriptors from the database
		jobClass = self.serviceJobTable
		jobData = self.dbClient.session.query(jobClass).filter(jobClass.name==jobName).first()
		if jobData is not None:
			jobSettings = copy.deepcopy(jobData.content)

		## Return underlying DBAPI connection
		self.dbClient.session.commit()
		self.dbClient.session.close()

		if jobSettings is None:
			raise EnvironmentError('Job settings not found: {}'.format(jobName))

		## end getSpecificJob
		return jobSettings


	@logExceptionWithSelfLogger()
	def getJobSchedulerDetails(self, jobContent):
		triggerType = jobContent.get('triggerType')
		triggerArgs = {}
		if ('triggerArgs' in jobContent.keys() and len(jobContent.get('triggerArgs').keys()) > 0):
			for thisKey in jobContent.get('triggerArgs').keys():
				thisValue = jobContent.get('triggerArgs').get(thisKey)
				if thisValue is not None and len(str(thisValue)) > 0:
					triggerArgs[thisKey] = thisValue

		## Parse/typecast "scheduler" arguments for ApScheduler
		schedulerArgs = jobContent.get('schedulerArgs')
		schedulerMisfireGraceTime = int(schedulerArgs.get('misfire_grace_time'))
		schedulerCoalesce = bool(schedulerArgs.get('coalesce'))
		schedulerMaxInstances = int(schedulerArgs.get('max_instances'))

		## end getJobSchedulerDetails
		return (triggerType, triggerArgs, schedulerArgs, schedulerMisfireGraceTime, schedulerCoalesce, schedulerMaxInstances)


	def setupJobSchedules(self):
		self.logger.info('Creating initial job schedules...')
		self.lastJobUpdateTime = time.time()
		## Get job descriptors from the database
		jobClass = self.serviceJobTable
		jobs = self.dbClient.session.query(jobClass).all()

		for job in jobs:
			try:
				jobName = getattr(job, 'name')
				jobContent = getattr(job, 'content')
				active = getattr(job, 'active', False)
				packageName = getattr(job, 'package')
				jobShortName = jobContent.get('jobName')
				## Do not add disabled jobs into the scheduler
				if not active:
					## Nothing to schedule... job is disabled
					self.logger.debug('   skipping disabled job: {jobName!r}', jobName=jobName)
					continue

				## Helper function for shared code paths
				(triggerType, triggerArgs, schedulerArgs, schedulerMisfireGraceTime, schedulerCoalesce, schedulerMaxInstances) = self.getJobSchedulerDetails(jobContent)
				self.logger.info(' Scheduling job {jobName!r} with trigger {triggerType!r} and args {triggerArgs!r}', jobName=jobName, triggerType=triggerType, triggerArgs=triggerArgs)
				self.jobId += 1
				self.activeJobs[jobName] = str(self.jobId)
				## Now schedule the job
				self.scheduler.add_job(self.prepareJob,
									   triggerType,
									   args=[jobShortName, packageName],
									   kwargs=None,
									   id=str(self.jobId),
									   name=jobName,
									   misfire_grace_time=schedulerMisfireGraceTime,
									   coalesce=schedulerCoalesce,
									   max_instances=schedulerMaxInstances,
									   **triggerArgs)

			except:
				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error(' Exception with job report loop: {stacktrace!r}', stacktrace=stacktrace)

		## Return underlying DBAPI connection
		self.dbClient.session.commit()
		self.dbClient.session.close()

		## end setupJobSchedules
		return


	def getJobUpdates(self):
		"""Update or load new jobs when the descriptor changes."""
		thisJobUpdateTime = time.time()
		## Get job descriptors from the database
		jobClass = self.serviceJobTable
		jobs = self.dbClient.session.query(jobClass).filter(jobClass.time_updated >= datetime.datetime.fromtimestamp(self.lastJobUpdateTime)).all()
		for job in jobs:
			try:
				jobName = getattr(job, 'name')
				jobContent = getattr(job, 'content')
				active = getattr(job, 'active', False)
				packageName = getattr(job, 'package')
				jobShortName = jobContent.get('jobName')

				## If job wasn't active or being tracked
				if jobName not in self.activeJobs:
					if not active:
						## nothing to schedule; just an update on meta data
						continue
					else:
						## Helper function for shared code paths
						(triggerType, triggerArgs, schedulerArgs, schedulerMisfireGraceTime, schedulerCoalesce, schedulerMaxInstances) = self.getJobSchedulerDetails(jobContent)
						self.jobId += 1
						self.activeJobs[jobName] = str(self.jobId)
						## Now schedule the job
						self.scheduler.add_job(self.prepareJob,
											   triggerType,
											   args=[jobShortName, packageName],
											   kwargs=None,
											   id=str(self.jobId),
											   name=jobName,
											   misfire_grace_time=schedulerMisfireGraceTime,
											   coalesce=schedulerCoalesce,
											   max_instances=schedulerMaxInstances,
											   **triggerArgs)
						self.logger.info('Scheduled job {jobName!r} id {jobId!r} with trigger {triggerType!r} and args {triggerArgs!r}', jobName=jobName, jobId=self.jobId, triggerType=triggerType, triggerArgs=triggerArgs)

				else:
					## Remove and re-add the job into scheduler
					oldId = self.activeJobs[jobName]
					self.scheduler.remove_job(self.activeJobs[jobName])
					del self.activeJobs[jobName]

					## Re-add the updated job back in, if it's still enabled
					if not active:
						self.logger.info('Removed job {jobName!r} id {jobId!r}', jobName=jobName, jobId=oldId)
					else:
						## Helper function for shared code paths
						(triggerType, triggerArgs, schedulerArgs, schedulerMisfireGraceTime, schedulerCoalesce, schedulerMaxInstances) = self.getJobSchedulerDetails(jobContent)
						self.jobId += 1
						self.activeJobs[jobName] = str(self.jobId)
						## Now re-schedule the job
						self.scheduler.add_job(self.prepareJob,
											   triggerType,
											   args=[jobShortName, packageName],
											   kwargs=None,
											   id=str(self.jobId),
											   name=jobName,
											   misfire_grace_time=schedulerMisfireGraceTime,
											   coalesce=schedulerCoalesce,
											   max_instances=schedulerMaxInstances,
											   **triggerArgs)
						self.logger.info('Updated job {jobName!r}, id changed from {oldId!r} to {newId!r}, with trigger {triggerType!r} and args {triggerArgs!r}', jobName=jobName, oldId=oldId, newId=self.jobId, triggerType=triggerType, triggerArgs=triggerArgs)

			except:
				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception with updating job {jobName!r}: {stacktrace!r}', jobName=jobName, stacktrace=stacktrace)

		## Update the last time check
		self.lastJobUpdateTime = thisJobUpdateTime
		## Return underlying DBAPI connection
		self.dbClient.session.commit()
		self.dbClient.session.close()

		## end getJobUpdates
		return


	def getServiceClients(self):
		"""Calls the database and updates all the authorized clients.

		Update:
		  authorizedEndpoints : Dictionary containing all the authorized clients

		"""
		## Call database and update the authorized client list for the service
		clients = self.dbClient.session.query(self.clientEndpointTable)
		self.authorizedEndpoints = {}
		for serviceClient in clients:
			endpointName = getattr(serviceClient, 'name')
			endpointToken = getattr(serviceClient, 'object_id').strip()
			self.authorizedEndpoints[endpointName] = endpointToken
		## Return underlying DBAPI connection
		self.dbClient.session.commit()
		self.dbClient.session.close()
		self.logger.debug('Authorized client endpoints: {authorizedEndpoints!r}', authorizedEndpoints=list(self.authorizedEndpoints.keys()))


	def validateClient(self, endpointName, endpointToken):
		"""Checks if client endpoint name is in authorizedEndpoints dictionary.

		Arguments:
		  endpointName  : String contining the client endpoint name.
		  endpointToken : Authorization token for the client.

		"""
		self.logger.debug('Clients loaded from DB: {authorizedEndpoints!r}', authorizedEndpoints=list(self.authorizedEndpoints.keys()))
		for thisEndpoint, thisToken in self.authorizedEndpoints.items():
			if thisEndpoint == endpointName and thisToken == endpointToken:
				return True
		self.logger.debug('Looked for endpointToken {endpointToken!r} but not found... ', endpointToken=endpointToken)
		self.logger.error('Endpoint [{endpointName!r}] does not have access to use this service', endpointName=endpointName)
		return False


	def clientJustConnected(self, endpointName, endpointToken, action):
		"""Checks if client is newly connected and going through file checks.

		Arguments:
		  endpointName  : String contining the client endpoint name.
		  endpointToken : Authorization token for the client.
		  action        : requested action from client
		"""
		value = False
		## If this is a newly connected content gathering client, then it will
		## need to check/download files before the official client validation.
		if action in ['checkModules', 'sendModule', 'receivedFile']:
			## Check current list of connectedEndpoints
			for thisEndpoint, thisToken in self.connectedEndpoints.items():
				if thisEndpoint == endpointName and thisToken == endpointToken:
					return True
			## Not found previously, check for new values
			## Call DB and get the client list for the service
			clients = self.dbClient.session.query(self.clientEndpointTable)
			self.connectedEndpoints = {}
			for serviceClient in clients:
				thisEndpoint = getattr(serviceClient, 'name')
				thisToken = getattr(serviceClient, 'object_id').strip()
				if thisEndpoint == endpointName and thisToken == endpointToken:
					self.logger.debug('Found just connected client: {endpointName!r}', endpointName=endpointName)
					self.connectedEndpoints[endpointName] = endpointToken
					value = True
					break
			## Return underlying DBAPI connection
			self.dbClient.session.commit()
			self.dbClient.session.close()
		return value


	def validateAction(self, action):
		"""Checks if client endpoint action argument is a valid action argument.

		Arguments:
		  action : String containing the action name.
		"""
		if action in self.validActions:
			return True
		self.logger.debug('Action [{action!r}] is not valid for this service.  Valid actions follow: {validActions!r}', action=action, validActions=self.validActions)
		return False


	@logExceptionWithSelfLogger()
	def cleanClientHealthTable(self):
		"""Remove any stale clients before establishing new connections."""
		ServiceEndpointHealth = self.serviceHealthTable
		clients = self.dbClient.session.query(ServiceEndpointHealth).all()
		for serviceClient in clients:
			self.logger.debug('Removing stale client health entry for {serviceClient_name!r}, last updated {serviceClient_last_sys_stat!r}.',
							  serviceClient_name=serviceClient.name, serviceClient_last_sys_stat=serviceClient.last_system_status)
			self.dbClient.session.delete(serviceClient)
			self.dbClient.session.commit()
		## Return underlying DBAPI connection
		self.dbClient.session.commit()
		self.dbClient.session.close()

		## end cleanClientHealthTable
		return


	def removeClient(self, client, clientName):
		"""Remove client from the factory's list and from the DB table.

		Arguments:
		  client     : Client class object instance
		  clientName : String containing the client name

		"""
		newActiveClients = {}
		for thisName in self.activeClients.keys():
			(thisEndpoint, thisInstanceNumber, thisClient) = self.activeClients[thisName]
			if thisClient == client:
				self.logger.debug('Removing client [{thisName!r}] from active list', thisName=thisName)
			else:
				newActiveClients[thisName] = (thisEndpoint, thisInstanceNumber, thisClient)
		self.activeClients = newActiveClients
		## Remove the client from the group structure (used for jobs)
		try:
			if self.serviceName == 'ContentGatheringService':
				self.removeClientGroups(clientName)
			if self.serviceName == 'ContentGatheringService' or self.serviceName == 'UniversalJobService':
				## Remove the client from active jobs
				self.removeClientFromAllActiveJobs(clientName)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in removeClient: {exception!r}', exception=exception)

		## Remove client health entry out of the DB table
		ServiceEndpointHealth = self.serviceHealthTable
		## If this operation is hit during a shutdown or restart operation, and
		## stopFactory is starting - we may not have a dbClient left around:
		if self.dbClient is not None:
			clients = self.dbClient.session.query(ServiceEndpointHealth).all()
			for serviceClient in clients:
				thisName = serviceClient.name
				if thisName == clientName:
					self.dbClient.session.delete(serviceClient)
					self.dbClient.session.commit()

			## Return underlying DBAPI connection
			self.dbClient.session.commit()
			self.dbClient.session.close()

		## end removeClient
		return


	def updateClientTokens(self):
		"""Update client tokens.

		Regularly update tokens based on the settings, using the Key present on
		the client system.
		"""
		self.logger.info('Updating client tokens...')
		for endpointName, endpointToken in self.authorizedEndpoints.items():
			try:
				newToken = uuid.uuid4().hex
				## First update the DB entry
				clientObject = self.dbClient.session.query(self.clientEndpointTable).filter(self.clientEndpointTable.name == endpointName).first()
				if clientObject is None:
					## Dropped out of DB but our Service is still tracking it
					self.authorizedEndpoints.pop(endpointName, None)
					continue

				setattr(clientObject, 'object_id', newToken)
				self.dbClient.session.add(clientObject)
				self.dbClient.session.commit()

				## Update the local authorized token
				self.authorizedEndpoints[endpointName] = newToken

				## Now inform the active client (if it is currently active) to
				## refresh their token to maintain uninterrupted service.
				self.logger.info('Endpoint [{endpointName!r}] token changed.', endpointName=endpointName)
				for thisName, thisValue in self.activeClients.items():
					try:
						(thisEndpoint, thisInstanceNumber, client) = thisValue
						if thisEndpoint == endpointName:
							self.logger.debug('Token refresh notification, being sent to client [{thisName!r}]', thisName=thisName)
							client.constructAndSendData('tokenExpired', {})
					except:
						exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
						self.logger.error('Exception in updateClientTokens: {exception!r}', exception=exception)
			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception in updateClientTokens: {exception!r}', exception=exception)

		## Return underlying DBAPI connection
		self.dbClient.session.commit()
		self.dbClient.session.close()

		## end updateClientTokens
		return


	def sendHealthRequest(self):
		"""Requesting active clients to send health information"""
		for clientName, clientValue in self.activeClients.items():
			try:
				(endpointName, instanceNumber, client) = clientValue
				self.logger.debug('Health Request, being sent to client [{clientName!r}]...', clientName=clientName)
				client.constructAndSendData('healthRequest', {})
			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception in updateClientTokens: {exception!r}', exception=exception)



class ServiceProcess(multiprocessing.Process):
	"""Separate process per service manager."""

	def run(self):
		"""Override Process run method to provide a custom wrapper for service.

		Shared by all networked services. This provides a continuous loop for
		watching the child process while keeping an ear open to the main process
		from openContentPlatform, listening for any interrupt requests.

		"""
		try:
			## Twisted import here to avoid issues with epoll on Linux
			from twisted.internet import reactor, ssl

			## There are two types of event handlers being used here:
			##   self.shutdownEvent : main process tells this one to shutdown
			##                        (e.g. on a Ctrl+C type event)
			##   self.canceledEvent : this process needs to restart
			serviceEndpoint = self.globalSettings.get('serviceIpAddress')
			useCertificates = self.globalSettings.get('useCertificates', True)

			## Create a PID file for system administration purposes
			utils.pidEntryService(self.serviceName, env, self.pid)

			## Network job services use networkService, which is a shared lib
			## directed by additional input parameters; set args accordingly:
			factoryArgs = None
			if (self.serviceName == 'ContentGatheringService' or self.serviceName == 'UniversalJobService'):
				factoryArgs = (self.serviceName, self.globalSettings, self.canceledEvent, self.shutdownEvent, self.moduleType, self.clientEndpointTable, self.clientResultsTable, self.serviceResultsTable, self.serviceJobTable, self.serviceHealthTable, self.pkgPath, self.serviceSettings, self.serviceLogSetup)
			else:
				factoryArgs = (self.serviceName, self.globalSettings, self.canceledEvent, self.shutdownEvent)

			if useCertificates:
				## Use TLS to encrypt the communication
				certData = FilePath(os.path.join(env.configPath, globalSettings.get('ocpCertificateFile'))).getContent()
				certificate = ssl.PrivateCertificate.loadPEM(certData)
				print('Starting encrypted service: {}'.format(self.serviceName))
				reactor.listenSSL(self.listeningPort, self.serviceFactory(*factoryArgs), certificate.options())
			else:
				## Plain text communication
				print('Starting plain text service: {}'.format(self.serviceName))
				reactor.listenTCP(self.listeningPort, self.serviceFactory(*factoryArgs), interface=serviceEndpoint)

			## The following loop may look hacky at first glance, but solves a
			## challenge with a mix of Python multi-processing, multi-threading,
			## then Twisted's reactor and threading.

			## Python threads that are not daemon types, cannot be forced closed
			## when the controlling thread closes. So it's important to pass
			## events all the way through, and have looping code catch/cleanup.

			## Whenever the main process is being shut down, it must stop all
			## sub-processes along with their work streams, which includes any
			## Twisted reactors. We do that by passing shutdownEvent into the
			## sub-processes. And whenever a service (sub-process) needs to
			## restart, it notifies the other direction so the main process can
			## verify it stopped and restart it. We do that by a canceledEvent.

			## Now to the point of this verbose comment, so the reason we cannot
			## call reactor.run() here, and instead cut/paste the same code, was
			## to enhance 'while reactor._started' to watch for our events.

			reactor.startRunning()
			## Start event wait loop
			while reactor._started and not self.shutdownEvent.is_set() and not self.canceledEvent.is_set():
				try:
					## Four lines from twisted.internet.base.mainloop:
					reactor.runUntilCurrent()
					t2 = reactor.timeout()
					t = reactor.running and t2
					reactor.doIteration(t)
				except:
					exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					print('Exception in {}: {}'.format(self.serviceName, exception))
					break
			if self.shutdownEvent.is_set():
				print('Shutdown event received for {}'.format(self.serviceName))
				self.canceledEvent.set()
				with suppress(Exception):
					time.sleep(2)
					print('Calling reactor stop for {}'.format(self.serviceName))
					reactor.stop()
					time.sleep(.5)
			elif self.canceledEvent.is_set():
				print('Canceled event received for {}'.format(self.serviceName))
				with suppress(Exception):
					time.sleep(2)
					reactor.stop()
					time.sleep(.5)

		except PermissionError:
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			print('  {}'.format(exceptionOnly))
			print('  Stopping {}'.format(self.serviceName))
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			print('Exception in {}: {}'.format(self.serviceName, exception))

		## Cleanup
		utils.pidRemoveService(self.serviceName, env, self.pid)
		with suppress(Exception):
			reactor.stop()
		print('Stopped {}'.format(self.serviceName))

		## end ServiceProcess
		return
