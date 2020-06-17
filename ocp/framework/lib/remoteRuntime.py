"""Runtime for content gathering jobs.

Classes:
  :class:`remoteRuntime.Runtime` : Supporting memory structure for job
    execution (I/O and status)

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Oct, 2017

"""
import sys
import traceback
import datetime
import time
from contextlib import suppress

## From openContentPlatform
from results import Results
from utils import jobParameterizedLogger, updateParameters


class Runtime():
	"""Provides workflow, I/O, status, and tracking of jobs during execution."""

	def __init__(self, logger, env, packageName, jobName, endpoint, jobMetaData, sendToKafka, parameters, protocolType, protocols, shellConfig=None):
		"""Initialize supporting variables for job execution (I/O and status).

		Arguments:
		  logger             : handler for the client log
		  jobName (str)      : name of the discovery/integration job
		  endpoint (str)     : target endpoint for client
		  jobMetaData (dict) : input parameters for the job
		  sendToKafka (dict) : function for sending results to kafka topic

		"""
		self.jobStatus = 'UNKNOWN'  ## value in statusEnums
		self.statusEnums = { 1 : 'SUCCESS', 2 : 'WARNING', 3 : 'FAILURE', 4 : 'UNKNOWN' }
		self.jobMessages = set()  ## set instead of list, avoids duplicate msgs
		self.setupComplete = False
		self.startTime = datetime.datetime.now()
		self.packageName = packageName
		self.jobName = jobName
		self.results = Results(jobName, realm=jobMetaData.get('realm', 'default'))
		self.endpoint = endpoint
		self.env = env
		self.jobMetaData = jobMetaData
		self.parameters = parameters
		self.protocolType = protocolType
		self.protocols = protocols
		self.shellConfig = shellConfig
		self.clearMessages()
		self.endTime = None
		self.sendToKafka = sendToKafka
		## Create a log utility that in addition to standard log functions, will
		## conditionally report messages based on the setting of a job parameter
		self.logger = jobParameterizedLogger(logger, self.parameters.get('printDebug', False))
		## Update parameters for endpoint (globals, config group, OS type)
		self.setParameters()


	def __str__(self):
		"""When reporting on a job thread, provide what we know."""
		## Don't include the custom parameters; too long for
		## a simple statistic going to the log and to the DB
		endpointForLog = self.endpoint
		with suppress(Exception):
			endpointForLog.pop('children')
		try:
			endpointForLog.get('data').pop('parameters')
		except:
			with suppress(Exception):
				endpointForLog.pop('parameters')
		message = '{}, {}, {}, {}, {}'.format(self.jobName, str(endpointForLog), self.startTime, self.endTime, self.jobStatus)
		if self.jobMessages is not None and len(self.jobMessages) > 0:
			message = '{}, {}, {}, {}, {}, {}'.format(self.jobName, str(endpointForLog), self.startTime, self.endTime, self.jobStatus, str(self.jobMessages))
		return(message)
	__repr__ = __str__


	def setEndTime(self):
		"""Called at the end of a job's execution cycle, to set timestamp."""
		self.endTime = datetime.datetime.now()


	def report(self):
		"""Called at the end of a job's execution cycle, to report status."""
		self.logger.info(str(self))


	def status(self, providedStatus):
		"""Method to update the status of this job.

		Arguments:
		  providedStatus (int) : integer matching a key in statusEnums
		"""
		if (providedStatus is not None):
			if (str(providedStatus).isdigit() and int(providedStatus) in self.statusEnums.keys()):
				self.jobStatus = self.statusEnums[int(providedStatus)]
			else:
				self.logger.info('Incorrect status provided')


	def getStatus(self):
		"""Get the readable status, not the enum digit."""
		return self.jobStatus


	def message(self, messages):
		"""Add warning or log messages onto the message list.

		Arguments:
		  messages (str/list) : a single message string or a list of strings
		"""
		if (isinstance(messages, list)):
			for message in messages:
				self.jobMessages.add(str(message))
		else:
			self.jobMessages.add(str(messages))


	def clearMessages(self):
		"""Clears out false negatives, such as when iterating through protocols."""
		self.jobMessages = set()

	def setError(self, functionName):
		"""Everything you'd want to drop in a main exception block."""
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		self.logger.error('Failure in {functionName!r}: {stacktrace!r}', functionName=functionName, stacktrace=stacktrace)
		self.status(3)
		self.message(str(sys.exc_info()[1]))

	def setErrorMsg(self, functionName):
		"""Similar to setError, but log the message without stacktrace."""
		msg = str(sys.exc_info()[1])
		self.logger.error('Failure in {functionName!r}: {msg!r}', functionName=functionName, msg=msg)
		self.status(3)
		self.message(str(msg))

	def setWarning(self, msg):
		"""Send a custom warning message and set the status to warning."""
		self.logger.warn('{msg!r}', msg=msg)
		self.status(2)
		self.message(str(msg))

	def setParameters(self):
		"""Update parameters for endpoint (globals, config group, OS type).

		Default, override, and customize all settings needed for core jobs. Settings
		like where to find certain commands on this build, whether to run a command
		in elevated mode, what type of elevated utility will be used, what type of
		objects to ignore or include with discovery jobs, etc.
		"""
		try:
			if self.jobMetaData.get('updateParameters', False):
				if len(self.shellConfig) <= 0:
					raise EnvironmentError('Unable to read shellConfig; aborting Runtime initialization.')

				## Get the OS and config group parameters for shell protocols
				osParameters = self.shellConfig.get('osParameters', {})
				configDefault = self.shellConfig.get('configDefault', {})
				configGroups = self.shellConfig.get('configGroups', {})

				parameters = self.endpoint.get('data').get('parameters')
				osType = parameters.get('osType')
				configGroupName = parameters.get('configGroup')

				## Update with OS parameters
				updateParameters(parameters, osParameters.get(osType, {}), skipParameters=['commandsToTransform'])

				## Update with global parameters
				updateParameters(parameters, configDefault)

				## Update with config group	parameters
				for configGroup in configGroups:
					if configGroupName == configGroup.get('name'):
						updateParameters(parameters, configGroup.get('parameters', {}))
						break
				self.logger.report('setParameters: {parameters!r}', parameters=parameters)
			self.setupComplete = True

		except:
			self.setError(__name__)

		## end setParameters
		return
