"""Shared thread management library for the Open Content Platform.

Classes:
 :class:`threadInstance.ThreadInstance` : Generic wrapper to manage
   multi-threaded function calls

"""
import sys, traceback
import time
from threading import Thread, currentThread


class ThreadInstance(Thread):
	"""Generic wrapper to manage multi-threaded function calls."""

	def __init__(self, logger, callerName):
		"""Constructor for ThreadInstance.

		Arguments:
		  logger           : Handler to a logging utility used by this thread
		  callerName (str) : Name of the caller function for logging purposes

		"""
		self.logger = logger
		self.callerName = callerName
		self.canceled = False
		self.threadName = None
		self.startTime = None
		self.startTimePretty = None
		self.endTime = None
		self.endpoint = None
		self.endpointsLoaded = False
		self.completed = False
		self.exception = None
		Thread.__init__(self)


	def threadedFunction(self):
		"""Custom code to run in a thread; implemented in derived classes."""
		raise NotImplementedError()


	def run(self):
		"""Override the 'run' function for the python Thread class."""
		try:
			self.threadName = currentThread().getName()
			self.startTime = time.time()
			self.startTimePretty = time.strftime('%X %x')
			self.logger.info('Started {self_obj!r}', self_obj = self)
			self.threadedFunction()
		except:
			self.canceled = True
			self.exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			print('{} interrupted: Exception in thread [{}]:  {}'.format(self.callerName, self.threadName, self.exception))
			self.logger.error('{callerName!r} interrupted: Exception in thread [{threadName!r}]:  {exception!r}', callerName=self.callerName, threadName=self.threadName, exception=self.exception)
		finally:
			self.completed = True
			self.endTime = time.time()
		## Report the thread's final status
		self.logger.info('Stopped {self_obj!r}', self_obj = self)


	def __str__(self):
		"""Build an informal string representation of this thread object."""
		if self.exception:
			if self.endTime and self.startTime:
				return 'Job {0}: {1} with runtime {2:.7f} secs: Exception: {3}'.format(self.callerName, self.threadName, self.endTime - self.startTime, self.exception)
			else:
				return 'Job {}: {} Exception: {}'.format(self.callerName, self.threadName, self.exception)
		elif self.endTime:
			return 'Job {0}: {1} with endpoint {2} and runtime {3:.2f} secs.'.format(self.callerName, self.threadName, self.endpoint, self.endTime - self.startTime)
		elif self.startTime:
			currentTime = time.time()
			timediff = int(currentTime - self.startTime)
			if (timediff < self.jobMaxJobRunTime):
				return 'Job {}: {} with endpoint {} started at {}.'.format(self.callerName, self.threadName, self.endpoint, self.startTimePretty)
			else:
				return 'Error: Job {} has exceeded maxJobRunTime of {} seconds: {} with endpoint {} started at {} and running {} seconds so far.'.format(self.callerName, self.jobMaxJobRunTime, self.threadName, self.endpoint, self.startTimePretty, timediff)
		else:
			return 'Job {}: thread not yet started.'.format(self.callerName)
	## If we maintain a list of Runnable classes and want to show or print
	## those, we should override repr() in addition to the str() method.
	__repr__ = __str__
