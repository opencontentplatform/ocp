"""Content Gathering Client.

This module receives direction from the :mod:`service.contentGatheringService`.
The entry class is :class:`.ContentGatheringClient`, which inherits from the
shared :mod:`.coreClient` and :mod:`.jobClient` modules. It is invoked from
the command line through :mod:`openContentClient`, or wrapped by a corresponding
service/daemon. The majority of code resides in :mod:`.jobClient`, which is
used by contentGathering, universalJob, and future job-enabled clients.

The main purpose of this client is to run jobs as directed by the Service. The
jobs can be more "integration" based (i.e. talking to a main central management
console/repository that has information on multiple endpoints), or the jobs can
be more "discovery" based (i.e. talking to individual endpoints to gather data).

The architecture for this ContentGatheringClient allows any number of instances
to work in parallel with a horizontally scaling, multi-process architecture.
Spin up additional client instances to increase throughput of job execution.

Classes:
  * :class:`.ContentGatheringClient` : class for this client

.. hidden::

	Author: Chris Satterthwaite (CS)
	Version info:
	  1.0 : (CS) Created Dec, 2017
	  1.1 : (CS) Improved capability for clients to reconnect when the server
	        side is unavailable. Mar 25, 2019.
	  1.2 : (CS) Added remoteClient to allow shared code for job-enabled clients,
	        Aug 27, 2019.
	  1.3 : (CS) Migrated remoteClient to jobClient, to match service naming
	        convention, Aug 7, 2020.

"""
import env
import coreClient
import jobClient


class ContentGatheringClient(coreClient.ClientProcess):
	"""Entry class for this client.

	This class leverages a common wrapper for the multiprocessing code, found
	in the :mod:`.coreClient` module. The constructor below directs the
	wrapper function to use settings specific to this manager.
	"""

	def __init__(self, shutdownEvent, canceledEvent, globalSettings):
		"""Modified constructor to accept custom arguments.

		Arguments:
		  shutdownEvent  - event used to control graceful shutdown
		  globalSettings - global settings; used to direct this manager
		"""
		self.shutdownEvent = shutdownEvent
		self.canceledEvent = canceledEvent
		self.globalSettings = globalSettings
		self.clientName = 'ContentGatheringClient'
		self.clientFactory = jobClient.JobClientFactory
		self.listeningPort = int(globalSettings['contentGatheringServicePort'])
		self.pkgPath = env.contentGatheringPkgPath
		self.clientSettings = globalSettings['fileContainingContentGatheringSettings']
		self.clientLogSetup = globalSettings['fileContainingContentGatheringLogSettings']
		super().__init__()
