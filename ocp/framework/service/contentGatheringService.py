"""Content Gathering Service.

This module manages interaction with connected clients of type
:mod:`client.contentGatheringClient`. The entry class is
:class:`.ContentGatheringService`, which inherits from the remote class
:class:`.remoteService.RemoteServiceFactory`.

This module uses the remoteService/remoteClient framework to run regularly
scheduled jobs on a horizontally scalable framework. The jobs can be more
"integration" based (i.e. connecting to a central management console/repository
that has information on multiple endpoints), or the jobs can be more "discovery"
based (i.e. connecting to individual endpoints to gather data).

The majority of code resides in :mod:`.remoteService`, which is a shared module
used by contentGathering, universalJob, and future factories using remote jobs.

Classes:

  * :class:`.ContentGatheringService` : entry class for this manager

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Aug 24, 2017
	  1.1 : (CS) added remoteService to allow shared code paths for the factory's
	        Service and Listener on remote job management. This was when the
	        dataTransformation service became the universalJob service, to allow
	        for a more generalized execution flow.  Aug 26, 2019.

"""
import os
## Add openContentPlatform directories onto the sys path
import env
env.addContentGatheringPkgPath()
env.addContentGatheringSharedScriptPath()
## From openContentPlatform
import sharedService
import remoteService
import database.schema.platformSchema as platformSchema


class ContentGatheringService(sharedService.ServiceProcess):
	"""Entry class for the contentGatheringService.

	This class leverages a common wrapper for the run method, which comes from
	the serviceProcess module. The constructor below directs the shared run
	function to use settings specific to this manager, which includes using a
	shared remoteService module that is used by contentGathering, universalJob,
	and future factories using remote job execution.
	"""

	def __init__(self, shutdownEvent, globalSettings):
		"""Modified constructor to accept custom arguments.

		Arguments:
		  shutdownEvent  - event used to control graceful shutdown
		  globalSettings - global settings; used to direct this manager
		"""
		self.serviceName = 'ContentGatheringService'
		self.multiProcessingLogContext = 'ContentGatheringServiceDebug'
		self.serviceFactory = remoteService.RemoteServiceFactory
		self.shutdownEvent = shutdownEvent
		self.globalSettings = globalSettings
		self.clientEndpointTable = platformSchema.ServiceContentGatheringEndpoint
		self.clientResultsTable = platformSchema.ContentGatheringResults
		self.serviceResultsTable = platformSchema.ContentGatheringServiceResults
		self.pkgPath = env.contentGatheringPkgPath
		self.serviceSettings = globalSettings['fileContainingContentGatheringSettings']
		self.serviceLogSetup = globalSettings['fileContainingServiceLogSettings']
		self.moduleType = 'contentGathering'
		self.listeningPort = int(globalSettings['contentGatheringServicePort'])
		super().__init__()
