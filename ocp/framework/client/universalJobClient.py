"""Universal Job Client.

This module receives direction from the :mod:`service.universalJobService`. The
entry class is :class:`.UniversalJobClient`, which inherits from the shared
:mod:`.sharedClient` and :mod:`.remoteClient` modules. It is invoked from the
command line through :mod:`openContentClient`, or wrapped by a corresponding
service/daemon. The majority of code resides in :mod:`.remoteClient`, which is
used by contentGathering, universalJob, and future job-enabled clients.

The main purpose of this client is to run jobs as directed by the Service. The
jobs are responsible for managing and manipulating data after it has come into
the database from content gathering flows. Sample jobs include creating or
updating logical models, enhancing or normalizing data, merging similar objects,
and deleting objects.

The architecture for this UniversalJobClient allows any number of instances
to work in parallel with a horizontally scaling, multi-process architecture.
Spin up additional client instances to increase throughput of job execution.

Classes:
  * :class:`.UniversalJobClient` : class for this client

.. hidden::

	Author: Chris Satterthwaite (CS)
	Version info:
	  1.0 : (CS) Created Dec, 2017
	  1.2 : (CS) added remoteClient to allow shared code for job-enabled clients.
	        Aug 27, 2019.

"""
import os
import env
import sharedClient
import remoteClient
import database.schema.platformSchema as platformSchema


class UniversalJobClient(sharedClient.ClientProcess):
	"""Entry class for this client.

	This class leverages a common wrapper for the multiprocessing code, found
	in the :mod:`.sharedClient` module. The constructor below directs the
	wrapper function to use settings specific to this manager.
	"""

	def __init__(self, shutdownEvent, globalSettings):
		"""Modified constructor to accept custom arguments.

		Arguments:
		  shutdownEvent  - event used to control graceful shutdown
		  globalSettings - global settings; used to direct this manager
		"""
		self.shutdownEvent = shutdownEvent
		self.globalSettings = globalSettings
		self.clientName = 'UniversalJobClient'
		self.clientFactory = remoteClient.RemoteClientFactory
		self.listeningPort = int(globalSettings['universalJobServicePort'])
		self.pkgPath = env.universalJobPkgPath
		self.clientSettings = globalSettings['fileContainingUniversalJobSettings']
		self.clientLogSetup = globalSettings['fileContainingUniversalJobLogSettings']
		super().__init__()
