"""Wrapper for clients.

This module is inherited by all clients.

Classes:
  * :class:`.ClientProcess` : overrides multiprocessing for client control
  * :class:`.ServiceClientFactory` : shared Twisted factory for all clients
  * :class:`.ServiceClientProtocol` : shared Twisted protocol used by clients to
      talk to their associated managers
  * :class:`.coreClient.CustomLineReceiverProtocol` : overrides LineReceiver
      with a customdelimiter

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Aug 24, 2017
	  1.1 : (CS) Refactored to use the same startup process controls as the service
	        managers. Mar 6, 2019.
	  1.2 : (CS) Split functionality out from sharedClient, to match service
	        naming convention, Aug 7, 2020

"""
import sys
import traceback
import os
import time
import datetime
import json
import platform
import psutil
import requests
import multiprocessing
from threading import Event
from contextlib import suppress
from twisted.internet import reactor, task, ssl, threads
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.python.filepath import FilePath

## Kafka client libraries... switched from kafka-python to confluent-kafka:
from confluent_kafka import Consumer as KafkaConsumer
from confluent_kafka import Producer as KafkaProducer
from confluent_kafka import KafkaError

## Add openContentPlatform directories onto the sys path
import env
env.addLibPath()
env.addExternalPath()
import utils
from utils import logExceptionWithSelfLogger, logExceptionWithFactoryLogger
from database.connectionPool import DatabaseClient

## Overriding max length from 16K to 64M
LineReceiver.MAX_LENGTH = 1024*1024*64
osType = platform.system()


class CustomLineReceiverProtocol(LineReceiver):
	"""Overriding the default '\r\n' delimiter with ':==:'."""
	## Using LineReceiver instead of Protocol, to leverage the caching/splitting
	## for partial and multiple messages coming from the TCP stream. Using a
	## custom delimiter because the data may contain the default '\r\n'.
	delimiter = b':==:'


class ServiceClientProtocol(CustomLineReceiverProtocol):
	"""Connects/authenticates with service and then waits for requests."""

	def connectionMade(self):
		print('  protocol connectionMade')
		self.factory.logger.debug('Protocol connection started; requested authorization...')
		self.factory.connectedClient = self
		self.factory.clientName = 'Unknown'
		self.factory.clientConnectionMade()
		self.requestAuthorization()

	def lineReceived(self, line):
		self.factory.logger.debug('CLIENT dataReceived: [{line!r}]', line=line)
		self.processData(line)

	def connectionLost(self, reason):
		print('  protocol connectionLost: reason: {}'.format(str(reason).replace('\n',' ').replace('\r','')))
		self.factory.logger.warn('Connection lost to [{clientName!r}]', clientName=self.factory.clientName)
		self.factory.delClient()
		self.factory.connectedClient = None

	@logExceptionWithFactoryLogger()
	def processData(self, line):
		"""Determine type of action is being requested, and process according."""
		dataDict = json.loads(line)
		action = dataDict['action']
		if self.factory.validateAction(action):
			content = dataDict['content']
			## Loop over 2 collections with zip, instead of using list index
			for thisAction, thisMethod in zip(self.factory.validActions, self.factory.actionMethods):
				if action == thisAction:
					self.factory.logger.debug('Server requests action [{action!r}]', action=action)
					#callFromThread(eval('self.{}'.format(thisMethod)), content)
					eval('self.{}'.format(thisMethod))(content)


	@logExceptionWithFactoryLogger()
	def constructAndSendData(self, action, content):
		"""Create a message and send it to the service.

		Arguments:
		  action  : String containing the action name
		  content : Dictionary containing the content based on the action string

		"""
		message = {}
		message['action'] = action
		message['content'] = content
		message['endpointName'] = self.factory.endpointName
		message['clientName'] = self.factory.clientName
		message['endpointToken'] = self.factory.endpointToken
		jsonMessage = json.dumps(message)
		self.factory.logger.debug('CLIENT constructAndSendData from [{clientName!r}]: {jsonMessage!r}', clientName=self.factory.clientName, jsonMessage=jsonMessage)
		msg = jsonMessage.encode('utf-8')
		self.sendLine(msg)


	def requestAuthorization(self):
		self.factory.logger.debug('Requesting connection authorization')
		content = self.factory.executionEnvironment
		content['endpointName'] = self.factory.endpointName
		content['endpointToken'] = self.factory.endpointToken
		self.constructAndSendData('connectionRequest', content)

	def requestReAuthorization(self):
		self.factory.logger.debug('Requesting re-authorization')
		content = self.factory.executionEnvironment
		content['endpointName'] = self.factory.endpointName
		content['endpointToken'] = self.factory.endpointToken
		self.constructAndSendData('reAuthorization', content)

	def doTokenExpired(self, content=None):
		"""Connect to API, get new token, update self.factory.endpointToken."""
		self.factory.logger.info('Acting on token expiration notification for client [{clientName!r}]', clientName=self.factory.clientName)
		self.factory.getEndpointToken()
		if (self.factory.clientName == 'Unknown'):
			self.factory.logger.error('doTokenExpired: calling doConnectionResponse')
			## This is a valid state when trying to connect for the first time
			## and the token isn't yet known by the service. Avoid a DOS attack
			## on our API and Service processes...
			self.doConnectionResponse(content)
		else:
			self.factory.logger.error('doTokenExpired: calling requestReAuthorization')
			self.requestReAuthorization()
			## TODO - do something different than a blocking sleep. The idea is
			## that the async communication to reauthorize needs to complete
			## before resubmitting the previous action that failed on last run.
			time.sleep(2)
			## Service could have rejected messages sent to it at the same time we
			## are trying to acquire the new token; if that's the case, we need to
			## pull the action out of content and resend previously failed messages
			if (content is not None and len(content.keys()) > 0):
				action = content.pop('action')
				self.constructAndSendData(action, content)

	def doConnectionResponse(self, content):
		if content is None or not 'clientName' in content.keys():
			self.factory.logger.error('Server did not allow connection: {content!r}', content=content)
			self.factory.authorized = False
			self.factory.logger.warn('Server rejected communication; client {clientName!r} on endpoint {endpointName!r} will attempt re-authentication as defined by the global setting: waitSecondsBetweenClientAuthorizationAttempts.', clientName=self.factory.clientName, endpointName=self.factory.endpointName)
			## This adds the 'Unknown' client to the active list so that the
			## looping call with authenticateClient can re-authenticate.
			self.factory.addClient(self, self.factory.clientName)
		else:
			self.factory.logger.info('Successfully registered in server as {clientName!r}', clientName=content['clientName'])
			self.factory.addClient(self, content['clientName'])
			self.factory.authorized = True
			## If contentGathering, then need to register with groups
			if self.factory.serviceName == 'ContentGatheringClient':
				self.constructAndSendData('clientGroups', self.factory.clientGroups)
				self.factory.logger.info('just sent group subscription: {clientGroups!r}', clientGroups=self.factory.clientGroups)

	def doUnauthorized(self, content):
		self.factory.logger.warn('Server rejected communication; client {clientName!r} on endpoint {endpointName} will attempt re-authentication as defined by the global setting: waitSecondsBetweenClientAuthorizationAttempts.', clientName=self.factory.clientName, endpointName=self.factory.endpointName)
		self.factory.authorized = False

	def doHealthRequest(self, content):
		self.factory.logger.info('Responding to health request')
		self.constructAndSendData('healthResponse', self.factory.executionEnvironment['runtime'])

	def doJobRequest(self, content):
		self.factory.logger.info('Responding to job request')
		self.constructAndSendData('jobResponse', {})


class ServiceClientFactory(ReconnectingClientFactory):
	"""Shared client factory wrapper."""

	protocol = ServiceClientProtocol

	def __init__(self, serviceName, globalSettings, getDbClient=False):
		self.clientName = 'Unknown'
		self.connectedClient = None
		self.authorized = False
		self.serviceName = serviceName
		self.globalSettings = globalSettings
		self.endpointName = platform.node()
		self.apiRoot = None
		self.getApiUrl()

		self.kafkaProducer = None
		self.kafkaConsumer = None
		self.kafkaTopic = globalSettings['kafkaTopic']
		self.kafkaLogTopic = globalSettings['kafkaLogTopic']
		self.kafkaEndpoint = globalSettings['kafkaEndpoint']
		self.useCertsWithKafka = globalSettings.get('useCertificatesWithKafka')
		self.kafkaCaRootFile = os.path.join(env.configPath, globalSettings.get('kafkaCaRootFile'))
		self.kafkaCertFile = os.path.join(env.configPath, globalSettings.get('kafkaCertificateFile'))
		self.kafkaKeyFile = os.path.join(env.configPath, globalSettings.get('kafkaKeyFile'))

		self.endpointKey = utils.getServiceKey(env.configPath)
		self.executionEnvironment = None
		self.baselineEnvironment()
		self.endpointToken = None
		self.numPortsChanged = False
		self.disconnectedOnPurpose = False

		self.dbClient = None
		if getDbClient:
			self.getDbSession()

		self.loopingHealthCheck = task.LoopingCall(self.deferHealthCheck)
		self.loopingHealthCheck.start(self.globalSettings['waitSecondsBetweenHealthChecks'])
		self.loopingGetExecutionEnvironment = task.LoopingCall(self.deferGetExecutionEnvironment)
		## Should the initial environment check wait for the client to startup?
		## We see a false negative (higher reading) when measured at startup...
		#self.loopingGetExecutionEnvironment.start(self.globalSettings['waitSecondsBetweenExecutionEnvironmentChecks'], now=False)
		self.loopingGetExecutionEnvironment.start(self.globalSettings['waitSecondsBetweenExecutionEnvironmentChecks'])
		self.loopingAuthenticateClient = task.LoopingCall(self.authenticateClient)
		self.loopingAuthenticateClient.start(int(self.globalSettings['waitSecondsBetweenClientAuthorizationAttempts']))
		self.pid = str(os.getpid())
		utils.pidEntry(self.serviceName, env, self.pid)
		super().__init__()
		## self.initialize() is called from the client subclass init method


	def cleanup(self):
		self.logger.debug('cleanup called in {}'.format(self.serviceName))
		## Probably some operation is out there lingering and needs moved into
		## the main Twisted thread, because calling reactor.stop the following
		## recommended way does not always call the stopFactory functions:
		#reactor.callFromThread(reactor.stop)

		## For now I'll force a stopFactory call here to ensure shutdown of
		## resources that may stop the reactor from doing thread cleanup (e.g.
		## database client, Kafka connections, looping calls updating class
		## state), and rely on the multiprocessing code to ensure it stops.

		## TODO: figure out why I need to manually call this...
		self.stopFactory()
		#reactor.callFromThread(self.stopFactory)
		self.logger.info(' cleanup complete.')
		reactor.callFromThread(reactor.stop)


	def stopFactory(self):
		try:
			self.logger.debug('stopFactory called in coreClient:')
			if self.loopingHealthCheck is not None:
				self.logger.debug(' stopFactory: stopping loopingHealthCheck')
				self.loopingHealthCheck.stop()
				self.loopingHealthCheck = None
			if self.loopingGetExecutionEnvironment is not None:
				self.logger.debug(' stopFactory: stopping loopingGetExecutionEnvironment')
				self.loopingGetExecutionEnvironment.stop()
				self.loopingGetExecutionEnvironment = None
			self.logger.debug(' stopFactory: removing executionEnvironment details')
			self.executionEnvironment = None
			if self.loopingAuthenticateClient is not None:
				self.logger.debug(' stopFactory: stopping loopingAuthenticateClient')
				self.loopingAuthenticateClient.stop()
				self.loopingAuthenticateClient = None
			if self.dbClient is not None:
				self.logger.debug(' stopFactory: closing database connection')
				self.dbClient.session.close()
				self.dbClient.close()
				self.dbClient = None
			self.kafkaEndpoint = None
			self.useCertsWithKafka = None
			self.kafkaCaRootFile = None
			self.kafkaCertFile = None
			self.kafkaKeyFile = None
			self.logger.info(' coreClient stopFactory complete.')
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			print('Exception in coreClient stopFactory: {}'.format(exception))
			with suppress(Exception):
				self.logger.error('Exception: {exception!r}', exception=exception)


	def clientConnectionLost(self, connector, reason):
		print('  factory clientConnectionLost: reason: {}'.format(str(reason).replace('\n',' ').replace('\r','')))
		self.logger.info('  factory clientConnectionLost: Reason:{reason!r}', reason=reason)
		#############################################################
		## Patch to keep reactor alive when the main connection drops
		#############################################################
		self.numPortsChanged = True
		self.numPorts += 1
		#############################################################
		ReconnectingClientFactory.clientConnectionLost(self, connector, reason)
		print('  factory clientConnectionLost: end.')


	def clientConnectionMade(self):
		print('  factory clientConnectionMade')
		self.logger.info('  factory clientConnectionMade')
		#############################################################
		## Resetting from patched value
		#############################################################
		if self.numPortsChanged :
			self.numPorts -= 1
			self.numPortsChanged = False
		#############################################################


	def clientConnectionFailed(self, connector, reason):
		self.logger.debug('Connection failed. Reason:{reason!r}', reason=reason)
		print('Connection failed. Reason: {}'.format(str(reason).replace('\n',' ').replace('\r','')))
		ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)


	def initialize(self, justStarted=False):
		self.logger.debug('initialize coreClient...')
		if not justStarted:
			if self.connectedClient is not None:
				self.logger.debug(' initialize: forcing client connection closed')
				self.connectedClient.transport.loseConnection()
		self.authorized = False
		self.logger.debug(' initializing : authenticateClient')
		self.authenticateClient()


	def validateAction(self, action):
		if action in self.validActions:
			return True
		## Ok for debugging and testing, but don't do this by default; avoid
		## logging the instructions for hackers to use the service.
		self.logger.debug('Action [{action!r}] is not valid for this service.', action=action)
		return False


	def getApiUrl(self):
		"""Build the base URL used for interaction with the API."""
		communicationType = self.globalSettings['transportType']
		endpoint = self.globalSettings['transportIpAddress']
		port = self.globalSettings['transportServicePort']
		self.apiRoot = '{}://{}:{}/ocpcore'.format(communicationType, endpoint, port)


	def getEndpointToken(self):
		"""Error handling wrapper for API call on client token generation."""
		self.logger.debug('Inside getEndpointToken')
		urlForTokenGeneration = '{}/authenticate'.format(self.apiRoot)
		## Create the payload
		payloadAsDict = self.executionEnvironment
		payloadAsDict['endpointName'] = self.endpointName
		payloadAsDict['clientType'] = self.serviceName
		## Convert payload Dictionary into json string format (not json)
		payloadAsString = json.dumps(payloadAsDict)
		## Tell the web service to use json
		headersAsDict = {}
		headersAsDict['Content-Type'] = 'application/json'
		headersAsDict['endpointKey'] = self.endpointKey

		while True:
			try:
				## Issue a GET call to URL for token generation
				self.getEndpointTokenApiCall(urlForTokenGeneration, payloadAsString, headersAsDict)
				break
			except (ConnectionError, requests.exceptions.ConnectionError) as exception:
				self.logger.debug('Server is down; wait and request again.  Connection message:  {exception!r}', exception=exception)
				## Fails if the API is unavailable (ie. during service restarts);
				## continue retrying until the API is responding
				time.sleep(20)
			except KeyError:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.debug('Client is being rejected.  (client.conf is bad or API is down?)  Connection message:  {exception!r}', exception=exception)
				## Fails if the API is unavailable (ie. during service restarts);
				## continue retrying until the API is responding
				time.sleep(20)
			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception in getEndpointToken: {exception!r}', exception=exception)
				break

		## end getEndpointToken
		return


	def getEndpointTokenApiCall(self, urlForTokenGeneration, payloadAsString, headersAsDict):
		"""Issue an API call for client token generation."""
		apiResponse = requests.get(urlForTokenGeneration, data=payloadAsString, headers=headersAsDict, verify=False)
		self.logger.debug('getEndpointTokenApiCall response code: {apiResponse_status_code!r}', apiResponse_status_code=str(apiResponse.status_code))
		#self.logger.debug('Response text: {apiResponse_text!r}', apiResponse_text=str(apiResponse.text))
		responseAsJson = json.loads(apiResponse.text)
		self.endpointToken = responseAsJson['token']

		## end getEndpointToken
		return


	@logExceptionWithSelfLogger()
	def baselineEnvironment(self):
		"""Gather initial platform details for tracking execution environment."""
		self.executionEnvironment = { 'runtime': {}}
		## Info on the server
		self.executionEnvironment['endpointName'] = self.endpointName
		self.executionEnvironment['platformType'] = platform.platform()
		self.executionEnvironment['platformSystem'] = platform.system()
		self.executionEnvironment['platformMachine'] = platform.machine()
		self.executionEnvironment['platformVersion'] = platform.version()
		self.executionEnvironment['pythonVersion'] = platform.python_build()
		## CPUs
		self.executionEnvironment['cpuType'] = platform.processor()
		self.executionEnvironment['cpuCount'] = psutil.cpu_count()
		## Memory
		memory = psutil.virtual_memory()
		self.executionEnvironment['memoryTotal'] = utils.getGigOrMeg(memory.total)
		self.logger.info('Platform Details: {content!r}', content=self.executionEnvironment)

		## end baselineEnvironment
		return


	@logExceptionWithSelfLogger()
	def deferGetExecutionEnvironment(self):
		"""Call getExecutionEnvironment in a non-blocking thread."""
		d = threads.deferToThread(self.getExecutionEnvironment)
		d.addCallback(self.updateExecutionEnvironment)
		return d


	@logExceptionWithSelfLogger()
	def updateExecutionEnvironment(self, data):
		content = self.executionEnvironment['runtime']
		## Mutate in place and in the main thread
		content.clear()
		for key,value in data.items():
			content[key] = value
		self.logger.info('Execution Environment:  {runtime!r}', runtime=content)


	def getExecutionEnvironment(self):
		"""Get regular execution environment updates for this client."""
		data = {}
		try:
			currentTime = time.time()
			data['lastSystemStatus'] = datetime.datetime.fromtimestamp(currentTime).strftime('%Y-%m-%d %H:%M:%S')
			## Server wide CPU average (across all cores, threads, virtuals)
			data['cpuAvgUtilization'] = psutil.cpu_percent()
			## Server wide memory
			memory = psutil.virtual_memory()
			data['memoryAproxTotal'] = utils.getGigOrMeg(memory.total)
			data['memoryAproxAvailable'] = utils.getGigOrMeg(memory.available)
			data['memoryPercentUsed'] = memory.percent
			## Info on this process
			data['pid'] = os.getpid()
			process = psutil.Process(data['pid'])
			data['processCpuPercent'] = process.cpu_percent()
			data['processMemory'] = process.memory_full_info().uss
			## Create time in epoc
			startTime = process.create_time()
			data['processStartTime'] = datetime.datetime.fromtimestamp(startTime).strftime('%Y-%m-%d %H:%M:%S')
			data['processRunTime'] = utils.prettyRunTime(startTime, currentTime)

		except psutil.AccessDenied:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception: {exception!r}', exception=exception)
			self.logger.error('AccessDenied errors on Windows usually mean the client was not started as Administrator.')
			print('AccessDenied errors for environment usually mean the client was not started as Administrator; please run with an elevated account.')

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception: {exception!r}', exception=exception)

		## end getExecutionEnvironment
		return data


	def addClient(self, client, clientName):
		self.clientName = clientName
		self.activeClient = client


	def delClient(self):
		self.clientName = 'Unknown'
		self.activeClient = None


	def authenticateClient(self):
		"""Authenticate the client for service connection.

		This is done automatically at the start of the client, but it may have
		failed if the server was unavailable during the initial connection.
		Furthermore, if there was delay between the client token refresh and the
		next server side communication, the client may have been rejected. So we
		need to handle unexpected issues...

		"""
		try:
			if self.authorized != True:
				self.logger.debug(' inside authenticateClient: calling getEndpointToken')
				self.getEndpointToken()
				if self.connectedClient is not None:
					self.connectedClient.requestAuthorization()
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in authenticateClient: {exception!r}', exception=exception)


	def getDbSession(self):
		"""Get instance for database client from defined configuration."""
		## If the database isn't up when the client is starting... wait on it.
		self.logger.debug('Attempting to connect to database')
		while self.dbClient is None and not self.shutdownEvent.is_set() and not self.canceledEvent.is_set():
			try:
				## Hard coding the connection pool settings for now; may want to
				## pull into a localSetting if they need to be independently set
				self.dbClient = DatabaseClient(self.logger, globalSettings=self.globalSettings, env=env, poolSize=1, maxOverflow=2, poolRecycle=900)
				if self.dbClient is None:
					self.canceledEvent.set()
					raise EnvironmentError('Failed to connect to database')
				self.logger.debug('Database connection successful')
			except exc.OperationalError:
				self.logger.debug('DB is not available; waiting {waitCycle!r} seconds before next retry.', waitCycle=self.globalSettings['waitSecondsBeforeRetryingDatabaseConnection'])
				self.logToKafka('DB is not available; waiting {waitCycle!r} seconds before next retry.'.format(self.globalSettings['waitSecondsBeforeRetryingDatabaseConnection']))
				time.sleep(int(self.globalSettings['waitSecondsBeforeRetryingDatabaseConnection']))
			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception: {exception!r}', exception=exception)
				self.canceledEvent.set()
				self.logToKafka(sys.exc_info()[1])
				break

		## end getDbSession
		return


	def createKafkaConsumer(self, kafkaTopic, maxRetries=5, sleepBetweenRetries=0.5):
		"""Connect to Kafka and initialize a consumer."""
		kafkaConsumer = None
		errorCount = 0
		while kafkaConsumer is None and not self.canceledEvent.is_set() and not self.shutdownEvent.is_set():
			try:
				kafkaConsumer = utils.attemptKafkaConsumerConnection(self.logger, self.kafkaEndpoint, kafkaTopic, self.useCertsWithKafka, self.kafkaCaRootFile, self.kafkaCertFile, self.kafkaKeyFile)
				self.connectedToKafkaConsumer = True

			except KafkaError:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception in createKafkaConsumer: Kafka error: {exception!r}', exception=exception)
				exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
				self.logToKafka(str(exceptionOnly))
				if errorCount >= maxRetries:
					self.logger.error('Too many connect attempts to kafka; need to clean/refresh client.')
					self.disconnectClient()
					break
				errorCount += 1
				time.sleep(sleepBetweenRetries)
				self.connectedToKafkaConsumer = False

			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception in createKafkaConsumer: {exception!r}', exception=exception)
				exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
				self.logToKafka(str(exceptionOnly))
				self.connectedToKafkaConsumer = False
				break

		## end createKafkaConsumer
		return kafkaConsumer


	def createKafkaProducer(self, maxRetries=5, sleepBetweenRetries=0.5):
		"""Connect to Kafka and initialize a producer."""
		errorCount = 0
		while self.kafkaProducer is None and not self.canceledEvent.is_set() and not self.shutdownEvent.is_set():
			try:
				self.kafkaProducer = utils.attemptKafkaProducerConnection(self.logger, self.kafkaEndpoint, self.useCertsWithKafka, self.kafkaCaRootFile, self.kafkaCertFile, self.kafkaKeyFile)
				self.connectedToKafkaProducer = True

			except KafkaError:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception in createKafkaProducer: Kafka error: {exception!r}', exception=exception)
				exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
				self.logToKafka(str(exceptionOnly))
				if errorCount >= maxRetries:
					self.logger.error('Too many connect attempts to kafka; need to clean/refresh client.')
					self.disconnectClient()
					break
				errorCount += 1
				time.sleep(sleepBetweenRetries)
				self.connectedToKafkaProducer = False

			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				self.logger.error('Exception in createKafkaProducer: {exception!r}', exception=exception)
				exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
				self.logToKafka(str(exceptionOnly))
				self.connectedToKafkaProducer = False
				break

		## end createKafkaProducer
		return


	def logToKafka(self, data=None):
		"""Send results from a thread over to kafka queues/topics."""
		if data is not None and self.kafkaProducer is not None:
			message = {}
			message['serviceName'] = self.serviceName
			message['endpointName'] = self.endpointName
			message['content'] = data
			self.logger.debug('Logging to Kafka: {message!r}', message=message)
			self.kafkaProducer.produce(self.kafkaLogTopic, value=json.dumps(message).encode('utf-8'))
			self.kafkaProducer.poll(0)
			self.kafkaProducer.flush()


	@logExceptionWithSelfLogger()
	def deferHealthCheck(self):
		"""Call healthCheck in a non-blocking thread."""
		d = threads.deferToThread(self.healthCheck)
		d.addCallback(self.shutdownCheck)
		return d


	@logExceptionWithSelfLogger()
	def shutdownCheck(self, needToShutdown):
		if needToShutdown:
			self.canceledEvent.set()
			self.logger.info('Need to shutdown after health check.')
		self.checkEvents()


	@logExceptionWithSelfLogger()
	def healthCheck(self):
		"""Watch for shutdown events and enforce self-client restarts."""
		needToShutdown = False

		## Ensure the system status is being updated
		previousTime = self.executionEnvironment['runtime'].get('lastSystemStatus')
		## Nothing to compare against if it hasn't been set the first time;
		## Keep in mind, the first check isn't until 30 seconds in (or
		## whatever the global waitSecondsBetweenExecutionEnvironmentChecks
		## setting has been changed to), while the first health check is
		## shorter (2 seconds is default for waitSecondsBetweenHealthChecks)
		if previousTime is not None:
			currentTime = datetime.datetime.now()
			deltaTime = currentTime - datetime.datetime.strptime(previousTime, '%Y-%m-%d %H:%M:%S')
			secondsSinceLastSystemStatus = deltaTime.seconds
			## If it has been longer than expected, set the canceledEvent. Note:
			## the local maxSecondsSinceLastSystemStatus setting must be larger
			## than the global waitSecondsBetweenExecutionEnvironmentChecks, or
			## this puts the client in an infinite restart cycle. ;)
			if secondsSinceLastSystemStatus > self.localSettings['maxSecondsSinceLastSystemStatus']:
				self.logger.info('healthCheck: system status is outdated: {}; need to request client restart.'.format(previousTime))
				needToShutdown = True

			## Check memory consumption on this process
			maxMemoryThreshold = self.localSettings['maxProcessMemoryUsageThreshold']
			## User may not want to check this (if setting is empty or set to 0)
			if maxMemoryThreshold is not None and maxMemoryThreshold != 0:
				processMemory = self.executionEnvironment['runtime'].get('processMemory')
				if processMemory is None:
					self.logger.info('healthCheck: processMemory not found; execution environment runtime invalid: {}; need to request client restart.'.format(self.executionEnvironment['runtime']))
					needToShutdown = True
				elif processMemory >= maxMemoryThreshold:
					self.logger.info('healthCheck: processMemory: {} is not less than defined threshold {}; need to request client restart.'.format(processMemory, maxMemoryThreshold))
					needToShutdown = True

			## Check CPU consumption on this process
			maxCpuPercentThreshold = self.localSettings['maxProcessCpuPercentUsageThreshold']
			## User may not want to check this (if setting is empty or set to 0)
			if maxCpuPercentThreshold is not None and maxCpuPercentThreshold != 0:
				processCpuPercent = self.executionEnvironment['runtime'].get('processCpuPercent')
				if processCpuPercent is None:
					self.logger.info('healthCheck: processCpuPercent not found; execution environment runtime invalid: {}; need to request client restart.'.format(self.executionEnvironment['runtime']))
					needToShutdown = True
				elif processCpuPercent >= maxCpuPercentThreshold:
					self.logger.info('healthCheck: processCpuPercent: {} is not less than defined threshold {}; need to request client restart.'.format(processCpuPercent, maxMemoryThreshold))
					needToShutdown = True

			# ## Test block
			# maxRunTimeBeforeRestart = 7200
			# processStartTime = self.executionEnvironment['runtime'].get('processStartTime')
			# currentTime = datetime.datetime.now()
			# deltaTime = currentTime - datetime.datetime.strptime(processStartTime, '%Y-%m-%d %H:%M:%S')
			# runtimeInSeconds = deltaTime.seconds
			# ## If it has been longer than expected, set the canceledEvent. Note:
			# ## the local maxSecondsSinceLastSystemStatus setting must be larger
			# ## than the global waitSecondsBetweenExecutionEnvironmentChecks, or
			# ## this puts the client in an infinite restart cycle. ;)
			# if runtimeInSeconds > maxRunTimeBeforeRestart:
			# 	self.logger.info('healthCheck: process runtime: {} is longer than max {}; need to request client restart.'.format(runtimeInSeconds, maxRunTimeBeforeRestart))
			# 	needToShutdown = True

		## end healthCheck
		return needToShutdown


	def checkEvents(self):
		if self.shutdownEvent.is_set() or self.canceledEvent.is_set():
			## Reactor.stop() may have been called from the process wrapper if
			## the shutdownEvent was set. So we attempt to cleanup as much as
			## possible (DB clients, Kafka clients, loggers, etc) with a manual
			## stopFactory call, attempting to interrupt any non-reactor threads
			## that may be blocking, before the client sub-process is killed by
			## the parent process.
			if self.shutdownEvent.is_set():
				self.logger.info('checkEvents: shutdownEvent is set; need to shutdown client.')
			else:
				self.logger.info('checkEvents: canceledEvent is set; need to request client restart.')

			## Need to call reactor.stop() on the main reactor thread
			#reactor.callFromThread(reactor.stop)

			## Well, that doesn't work. The reactor.callFromThread(reactor.stop)
			## call does not invoke our stopFactory functions! So that means
			## there is likely some operation lingering on a separate thread
			## (i.e. not on the main reactor thread) that needs to be wrapped
			## with callFromThread. Stubbing a cleanup() function for now since
			## we can control from the process level instead of thread level,
			## but I'll need to come back to this later:
			self.logger.info('checkEvents: calling cleanup.')
			self.cleanup()
			reactor.stop()

		## end checkEvents
		return


class ClientProcess(multiprocessing.Process):
	"""Separate process per client."""

	def run(self):
		"""Override Process run method to provide a custom wrapper for client.

		Shared by all clients. This provides a continuous loop for watching and
		restarting the child process, while keeping an ear open to the main
		process from openContentClient, listening for any interrupt requests.

		"""
		try:
			## There are two types of event handlers being used here:
			##   self.shutdownEvent : main process tells this one to shutdown
			##                        (e.g. on a Ctrl+C type event)
			##   self.canceledEvent : this process needs to restart
			serviceEndpoint = self.globalSettings.get('serviceIpAddress')
			useCertificates = self.globalSettings.get('useCertificates', True)

			## Create a PID file for system administration purposes
			utils.pidEntry(self.clientName, env, self.pid)

			## Job enabled clients use jobClient, which is a shared library
			## directed by additional input parameters; set args accordingly:
			factoryArgs = None
			if (self.clientName == 'ContentGatheringClient' or self.clientName == 'UniversalJobClient'):
				factoryArgs = (self.clientName, self.globalSettings, self.canceledEvent, self.shutdownEvent, self.pkgPath, self.clientSettings, self.clientLogSetup)
			else:
				factoryArgs = (self.clientName, self.globalSettings, self.canceledEvent, self.shutdownEvent)

			if useCertificates:
				## Use TLS to encrypt the communication
				certData = FilePath(os.path.join(env.configPath, 'server_cert_public.pem')).getContent()
				authority = ssl.Certificate.loadPEM(certData)
				sslOptions = ssl.optionsForClientTLS(serviceEndpoint, authority)
				print('Starting encrypted client: {}'.format(self.clientName))
				reactor.connectSSL(serviceEndpoint, self.listeningPort, self.clientFactory(*factoryArgs), sslOptions, timeout=300)
			else:
				## Plain text communication
				print('Starting plain text client: {}'.format(self.clientName))
				reactor.connectTCP(serviceEndpoint, self.listeningPort, self.clientFactory(*factoryArgs), timeout=300)

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
					print('Exception in {}: {}'.format(self.clientName, exception))
					break
			if self.shutdownEvent.is_set():
				print('Shutdown event received')
				self.canceledEvent.set()
				with suppress(Exception):
					time.sleep(2)
					print('Calling reactor stop')
					reactor.stop()
					time.sleep(.5)
			elif self.canceledEvent.is_set():
				print('Canceled event received')
				with suppress(Exception):
					time.sleep(2)
					reactor.stop()
					time.sleep(.5)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			print('Exception in {}: {}'.format(self.clientName, exception))

		## Cleanup
		utils.pidRemove(self.clientName, env, self.pid)
		with suppress(Exception):
			reactor.stop()
		print('Stopped {}'.format(self.clientName))

		## end ClientProcess
		return
