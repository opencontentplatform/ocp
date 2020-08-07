"""Local service wrapper; used by all services not requiring clients.

Classes:

  * :class:`.ServiceProcess` : overrides multiprocessing for service control
  * :class:`.LocalService` : shared class enabling common code paths for looking at
    system health, database initialization, kafka communication, etc.

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Aug 4, 2020

"""

import sys
import traceback
import os
import time
import datetime
#import json
import platform
import psutil
import multiprocessing
from contextlib import suppress
from twisted.internet import reactor, task, defer
from sqlalchemy import exc
from confluent_kafka import KafkaError

## Add openContentPlatform directories onto the sys path
import env
env.addLibPath()

## From openContentPlatform
import utils
from coreService import CoreService
from database.connectionPool import DatabaseClient


class LocalService(CoreService):
	"""Local service wrapper, used by all services not requiring clients.

	Uses twisted.internet.interfaces.IReactorThreads for threading."""

	def __init__(self, serviceName, globalSettings, getDbClient=False):
		"""Placeholder for local-only service type construction."""
		super().__init__(serviceName, globalSettings, getDbClient)

	def stopFactory(self):
		"""Placeholder for local-only service destruction."""
		super().stopFactory()


class ServiceProcess(multiprocessing.Process):
	"""Separate process per service manager."""

	def run(self):
		"""Override Process run method to provide a custom wrapper for service.

		Shared by all local services. This provides a continuous loop for
		watching the child process while keeping an ear open to the main process
		from openContentPlatform, listening for any interrupt requests.

		"""
		logger = None
		mainHandler = None
		try:
			## There are two types of event handlers being used here:
			##   self.shutdownEvent : main process tells this one to shutdown
			##                        (e.g. on a Ctrl+C type event)
			##   self.canceledEvent : this process needs to restart
			serviceEndpoint = self.globalSettings.get('serviceIpAddress')
			useCertificates = self.globalSettings.get('useCertificates', True)

			## Create a PID file for system administration purposes
			utils.pidEntryService(self.serviceName, env, self.pid)

			## The following loop may look hacky at first glance, but solves a
			## challenge with a mix of Python multi-processing, multi-threading,
			## then Twisted multi-threading inside it's reactor.

			## The OCP main process spins up services in sub-processes, and
			## then the sub-processes may also be multi-threaded and/or use a
			## Twisted reactor (which has it's own thread management). Actually,
			## most of the services are wrapped by a Twisted reactor, which
			## further complicates our mix of process and thread management -
			## specifically with managing restarts.

			## Python threads that are not daemon types, cannot be forced closed
			## when the controlling thread closes. So it's important to pass
			## events all the way through, and have looping code catch/cleanup.

			## Whenever the main process is being shut down, it must stop all
			## sub-processes along with their work streams - which also includes
			## Twisted reactors. We do that by passing shutdownEvent into the
			## sub-processes. And whenever a service (sub-process) needs to
			## restart, it needs to notify back the other direction so the main
			## process can stop and restart it. We do that by a canceledEvent.

			## Now to the point of this verbose comment, so the reason we cannot
			## call reactor.run() here, and instead cut/paste the code here, was
			## to enhance 'while reactor._started' to also watch for our events.
			factoryArgs = (self.serviceName, self.globalSettings, self.canceledEvent, self.shutdownEvent)
			print('Starting local service: {}'.format(self.serviceName))
			reactor.callFromThread(self.serviceClass, *factoryArgs)
			#reactor.callWhenRunning(self.serviceClass *factoryArgs)
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
		## Remove the handler to avoid duplicate lines the next time it runs
		with suppress(Exception):
			logger.removeHandler(mainHandler)
		with suppress(Exception):
			reactor.stop()
		print('Stopped {}'.format(self.serviceName))

		## end run
		return
