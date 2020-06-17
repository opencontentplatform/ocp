"""Module for tracking the runtime of a service thread.

Classes:
  :class:`serviceThreadRuntime.Runtime` : provide input/output variables and
    track jobs during execution

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Oct 25, 2018

"""

## From openContentPlatform
from results import Results
from utils import jobParameterizedLogger

class Runtime():
	"""Provides Input/output variables and tracks jobs during execution."""

	def __init__(self, logger, jobName, jobSettings, dbClient, env=None, sendToKafka=None):
		"""Initialize supporting variables for job execution (I/O and status).

		Arguments:
		  logger             : handler for the content gathering log
		  jobName (str)      : name of the discovery/integration job
		  jobSettings (dict) : input parameters for the job

		"""
		self.jobStatus = 'UNKNOWN'  ## value in statusEnums
		self.statusEnums = { 1 : 'SUCCESS', 2 : 'WARNING', 3 : 'FAILURE', 4 : 'UNKNOWN' }
		self.jobMessages = set()  ## set instead of list, avoids duplicate msgs
		self.jobName = jobName
		self.jobSettings = jobSettings
		self.parameters = jobSettings['inputParameters']
		self.dbClient = dbClient
		## Create a log utility that in addition to standard log functions, will
		## conditionally report messages based on the setting of a job parameter
		self.logger = jobParameterizedLogger(logger, self.parameters.get('printDebug', False))
		self.env = env
		self.sendToKafka = sendToKafka
		self.results = Results(jobName, realm=jobSettings.get('realm', 'default'))


	def __str__(self):
		"""When reporting on a job thread, provide what we know."""
		message = '{}, {}, {}, {}'.format(self.jobName, self.startTime, self.endTime, self.jobStatus)
		if self.jobMessages is not None and len(self.jobMessages) > 0:
			message = '{}, {}'.format(message, str(self.jobMessages))
		return(message)
	__repr__ = __str__


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
