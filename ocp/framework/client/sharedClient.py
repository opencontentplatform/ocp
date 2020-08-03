"""Wrapper for clients.

This module is inherited by all clients.

Classes:
  * :class:`.ClientProcess` : creates a new process for the Twisted reactor
  * :class:`.ServiceClientFactory` : shared Twisted factory for all clients
  * :class:`.ServiceClientProtocol` : shared Twisted protocol used by clients to
    talk to their associated managers
  * :class:`.sharedClient.CustomLineReceiverProtocol` : overrides LineReceiver with a custom
    delimiter

.. hidden::

  Author: Chris Satterthwaite (CS)
  Contributors:
  Version info:
    1.0 : (CS) Created Aug 24, 2017
    1.1 : (CS) Refactored to use the same startup process controls as the service
          managers. Mar 6, 2019.

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
		""" """
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
		""" """
		print('  protocol connectionLost: reason: {}'.format(reason))
		self.factory.logger.warn('Connection lost to [{clientName!r}]', clientName=self.factory.clientName)
		self.factory.delClient()
		self.factory.connectedClient = None

	def processData(self, line):
		"""Process the communication coming into the client.

		Transform received line into dictionary structures,
		figure out what type of action is being requested, and send the content
		of the communcation to be processed according to the action requested.

		Arguments:
		  data : bytes received from Service

		"""
		try:
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

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.factory.logger.error('Exception in processData: {exception!r}', exception=exception)


	def constructAndSendData(self, action, content):
		"""Builds a JSON object and send it to the service.

		Arguments:
		  action  : String containing the action name
		  content : Dictionary containing the content based on the action string

		"""
		try:
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
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.factory.logger.error('Exception in constructAndSendData: {exception!r}', exception=exception)

	def requestAuthorization(self):
		""" """
		self.factory.logger.debug('Requesting connection authorization')
		content = self.factory.platformDetails
		content['endpointName'] = self.factory.endpointName
		content['endpointToken'] = self.factory.endpointToken
		self.constructAndSendData('connectionRequest', content)

	def requestReAuthorization(self):
		self.factory.logger.debug('Requesting re-authorization')
		content = self.factory.platformDetails
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
		""" """
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
		""" """
		self.factory.logger.warn('Server rejected communication; client {clientName!r} on endpoint {endpointName} will attempt re-authentication as defined by the global setting: waitSecondsBetweenClientAuthorizationAttempts.', clientName=self.factory.clientName, endpointName=self.factory.endpointName)
		self.factory.authorized = False

	def doHealthRequest(self, content):
		""" """
		self.factory.logger.info('Responding to health request')
		self.constructAndSendData('healthResponse', self.factory.health)

	def doJobRequest(self, content):
		""" """
		self.factory.logger.info('Responding to job request')
		self.constructAndSendData('jobResponse', {})


class ServiceClientFactory(ReconnectingClientFactory):
	"""Shared client factory wrapper."""

	protocol = ServiceClientProtocol

	def __init__(self, serviceName, globalSettings):
		"""Comment."""
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
		self.logger.debug('  ====> kafkaCaRootFile: {kafkaCaRootFile!r}', kafkaCaRootFile=self.kafkaCaRootFile)
		self.logger.debug('  ====> kafkaCertFile: {kafkaCertFile!r}', kafkaCertFile=self.kafkaCertFile)
		self.logger.debug('  ====> kafkaKeyFile: {kafkaKeyFile!r}', kafkaKeyFile=self.kafkaKeyFile)

		self.endpointKey = utils.getServiceKey(env.configPath)
		self.platformDetails = self.getPlatformDetails()
		self.endpointToken = None
		self.health = {}
		self.numPortsChanged = False
		self.disconnectedOnPurpose = False
		self.loopingSystemHealth = task.LoopingCall(self.enterSystemHealthCheck)
		self.loopingSystemHealth.start(int(self.globalSettings['waitSecondsBetweenHealthChecks']))
		self.loopingAuthenticateClient = task.LoopingCall(self.authenticateClient)
		self.loopingAuthenticateClient.start(int(self.globalSettings['waitSecondsBetweenClientAuthorizationAttempts']))
		self.pid = str(os.getpid())
		utils.pidEntry(self.serviceName, env, self.pid)
		super().__init__()
		## self.initialize() is called from the client subclass init method


	def clientConnectionLost(self, connector, reason):
		print('  factory clientConnectionLost: reason: {}'.format(reason))
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
		print('Connection failed. Reason: {}'.format(reason))
		ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)


	def initialize(self, justStarted=False):
		self.logger.debug('initialize: starting in sharedClient...')
		if not justStarted:
			if self.connectedClient is not None:
				self.logger.debug('initialize: forcing client connection closed')
				self.connectedClient.transport.loseConnection()
		self.authorized = False
		self.logger.debug('initializing : authenticateClient')
		self.authenticateClient()


	def validateAction(self, action):
		""" """
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
		payloadAsDict = self.platformDetails
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
		self.logger.debug('Inside getEndpointTokenApiCall')
		apiResponse = requests.get(urlForTokenGeneration, data=payloadAsString, headers=headersAsDict, verify=False)
		self.logger.debug('Response code: {apiResponse_status_code!r}', apiResponse_status_code=str(apiResponse.status_code))
		self.logger.debug('Response text: {apiResponse_text!r}', apiResponse_text=str(apiResponse.text))
		responseAsJson = json.loads(apiResponse.text)
		self.endpointToken = responseAsJson['token']

		## end getEndpointToken
		return


	def getGigOrMeg(self, value):
		"""Helper function for memory."""
		k, b = divmod(value, 1000)
		m, k = divmod(k, 1024)
		g, m = divmod(m, 1024)

		## Just the general amount is fine for reporting status
		total = '{} MB'.format(m)
		if g > 1:
			total = '{} GB'.format(g)

		## end getGigOrMeg
		return total


	def getPlatformDetails(self):
		"""Get the system/platform details at startup."""
		content = {}
		try:
			## Info on the server
			content['endpointName'] = self.endpointName
			content['platformType'] = platform.platform()
			content['platformSystem'] = platform.system()
			content['platformMachine'] = platform.machine()
			content['platformVersion'] = platform.version()
			## CPUs
			content['cpuType'] = platform.processor()
			content['cpuCount'] = psutil.cpu_count()
			## Memory
			memory = psutil.virtual_memory()
			content['memoryTotal'] = self.getGigOrMeg(memory.total)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in getPlatformDetails: {exception!r}', exception=exception)

		self.logger.info('Platform Details: {content!r}', content=content)

		## end getPlatformDetails
		return content


	def enterSystemHealthCheck(self):
		"""Looping method for health checks; done via non-blocking thread."""
		threadHandle = None
		try:
			threadHandle = threads.deferToThread(self.getSystemHealth)
		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in enterSystemHealthCheck: {exception!r}', exception=exception)
			exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
			self.logToKafka(str(exceptionOnly))

		## end enterSystemHealthCheck
		return threadHandle


	def getSystemHealth(self):
		"""Get regular system health checks for this client."""
		try:
			content = {}
			content['endpointName'] = self.endpointName
			currentTime = time.time()
			content['lastSystemStatus'] = datetime.datetime.fromtimestamp(currentTime).strftime('%Y-%m-%d %H:%M:%S')
			## Server wide CPU average (across all cores, threads, virtuals)
			content['cpuAvgUtilization'] = psutil.cpu_percent()
			## Server wide memory
			memory = psutil.virtual_memory()
			content['memoryAproxTotal'] = self.getGigOrMeg(memory.total)
			content['memoryAproxAvailable'] = self.getGigOrMeg(memory.available)
			content['memoryPercentUsed'] = memory.percent
			## Info on this process
			process = psutil.Process(os.getpid())
			content['processCpuPercent'] = process.cpu_percent()
			content['processMemory'] = process.memory_full_info().uss
			## Create time in epoc
			startTime = process.create_time()
			content['processStartTime'] = datetime.datetime.fromtimestamp(startTime).strftime('%Y-%m-%d %H:%M:%S')
			content['processRunTime'] = utils.prettyRunTime(startTime, currentTime)
			## Override saved settings so we don't wait a refresh interval before
			## the client connections to our services can start working again. But
			## only do this if we received results; if DB is down, don't zero out.
			self.health = content

		except psutil.AccessDenied:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in getServiceHealth: {exception!r}', exception=exception)
			self.logger.error('AccessDenied errors on Windows usually mean the client was not started as Administrator.')

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			self.logger.error('Exception in getSystemHealth: {exception!r}', exception=exception)

		self.logger.info('System Health: {health!r}', health=self.health)

		## end getSystemHealth
		return


	def addClient(self, client, clientName):
		""" """
		self.clientName = clientName
		self.activeClient = client


	def delClient(self):
		""" """
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


	def createKafkaConsumer(self, kafkaTopic, maxRetries=5, sleepBetweenRetries=0.5):
		"""Connect to Kafka and initialize a consumer."""
		kafkaConsumer = None
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
					self.cleanup()
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
		count = 0
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
					self.cleanup()
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


class ClientProcess(multiprocessing.Process):
	"""Separate process per client.

	This is needed for signalling to work in Twisted's reactor, if this is spun
	up as a Windows Service instead of just on the command line. By adding the
	same structure here as we do on the server side (new process before starting
	the twisted reactor), we are not only standardizing on the startup, but are
	also allowing the dependent libraries to work without modification.
	"""

	def run(self):
		"""Override Process run method to provide a custom wrapper for client.

		Shared by all service clients. This provides a continuous loop for
		watching the child process while keeping an ear open to the main process
		from openContentPlatform, listening for any interrupt requests.

		"""
		try:
			## There are two types of event handlers being used here:
			##   self.shutdownEvent : multiprocess.Event. This is how the main
			##                        process tells this process to shutdown
			##                        (e.g. on a Ctrl+C type event)
			##   self.canceledEvent : threading.Event. This is how this process
			##                        tells the twisted reactor to stop blocking
			##                        our main thread (e.g. Kafka/DB loops)
			self.canceledEvent = Event()
			reactor.addSystemEventTrigger('before', 'shutdown', self.canceledEvent.set)
			serviceEndpoint = self.globalSettings.get('serviceIpAddress')
			useCertificates = self.globalSettings.get('useCertificates', True)
			## Create a PID file for system administration purposes
			utils.pidEntry(self.clientName, env, self.pid)
			## Remote job clients use remoteClient, which is a shared library
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

			#reactor.run()
			## Normally we'd just call reactor.run() here and let twisted handle
			## the wait loop while watching for signals. The problem is that we
			## need the parent process (Windows service) to manage this process.
			## So this is a bit hacky in that I am using the reactor code, but
			## am manually calling what would be called if I just called run(),
			## in order to stop the loop when a shutdownEvent is received:
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
				print('Process received shutdownEvent')
				self.canceledEvent.set()
				time.sleep(5)
				print('ClientProcess: self.canceledEvent: {}'.format(self.canceledEvent.is_set()))
				with suppress(Exception):
					reactor.stop()
					time.sleep(.5)
			elif self.canceledEvent.is_set():
				print('Process received canceledEvent')
				print('ClientProcess: self.canceledEvent: {}'.format(self.canceledEvent.is_set()))
				with suppress(Exception):
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
