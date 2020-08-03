"""Universal Job Service.

This module manages interaction with connected clients of type
:mod:`client.universalJobClient`. The entry class is
:class:`.UniversalJobService`, which inherits from the remote class
:class:`.remoteService.RemoteServiceFactory`.

This module is functionally equivalent to the :mod:`.contentGatheringService`,
and uses the same remoteService/remoteClient framework to run scheduled jobs on
a horizontally scalable framework. However, it is much different in purpose.

This module is responsible for managing and manipulating data AFTER it has come
into the database through content gathering flows. Sample activities include
creating or updating logical models, enhancing or normalizing data, merging
similar objects, deleting objects, reporting...

The majority of code resides in :mod:`.remoteService`, which is a shared module
used by contentGathering, universalJob, and future factories using remote jobs.

Classes:

  * :class:`.UniversalJobService` : entry class for this manager

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Dec 9, 2017
	  2.0 : (CS) Transitioned this service to use horizontally scalable clients,
	        instead of consuming CPU on the server side. Updated Aug 21, 2019.
	  2.1 : (CS) added remoteService to allow shared code paths for the factory's
	        Service and Listener on remote job management. This was when the
	        dataTransformation service became universalJob, to allow for a more
	        generalized execution flow.  Aug 26, 2019.

"""
import os
## Add openContentPlatform directories onto the sys path
import env
env.addUniversalJobPkgPath()
env.addContentGatheringSharedScriptPath()
## From openContentPlatform
import sharedService
import remoteService
import database.schema.platformSchema as platformSchema


class UniversalJobService(sharedService.ServiceProcess):
	"""Entry class for the universalJobService.

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
		self.serviceName = 'UniversalJobService'
		self.multiProcessingLogContext = 'UniversalJobServiceDebug'
		self.serviceFactory = remoteService.RemoteServiceFactory
		self.shutdownEvent = shutdownEvent
		self.globalSettings = globalSettings
		self.clientEndpointTable = platformSchema.ServiceUniversalJobEndpoint
		self.clientResultsTable = platformSchema.UniversalJobResults
		self.serviceResultsTable = platformSchema.UniversalJobServiceResults
		self.pkgPath = env.universalJobPkgPath
		self.serviceSettings = globalSettings['fileContainingUniversalJobSettings']
		self.serviceLogSetup = globalSettings['fileContainingServiceLogSettings']
		self.moduleType = 'universalJob'
		self.listeningPort = int(globalSettings['universalJobServicePort'])
		super().__init__()
