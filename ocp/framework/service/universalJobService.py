"""Universal Job Service.

This module manages interaction with connected clients of type
:mod:`client.universalJobClient`. The entry class is
:class:`.UniversalJobService`, which inherits from the remote class
:class:`.jobService.JobServiceFactory`.

This module is functionally equivalent to the :mod:`.contentGatheringService`,
and uses the same jobService/jobClient framework to run scheduled jobs on
a horizontally scalable framework. However, it is much different in purpose.

This module is responsible for managing and manipulating data AFTER it has come
into the database through content gathering flows. Sample activities include
creating or updating logical models, enhancing or normalizing data, merging
similar objects, deleting objects, reporting...

The majority of code resides in :mod:`.jobService`, which is a shared module
used by contentGathering, universalJob, and future factories using remote jobs.

Classes:

  * :class:`.UniversalJobService` : entry class for multiprocessing

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Dec 9, 2017
	  2.0 : (CS) Transitioned this service to use horizontally scalable clients,
	        instead of consuming CPU on the server side. Updated Aug 21, 2019.
	  2.1 : (CS) added jobService to allow shared code paths for the factory's
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
import networkService
import jobService
import database.schema.platformSchema as platformSchema


class UniversalJobService(networkService.ServiceProcess):
	"""Entry class for the universalJobService.

	This class leverages a common wrapper for the run method, which comes from
	the networkService module. The constructor below directs multiprocessing
	to use settings specific to this manager, including setting the expected
	class (self.serviceFactory) to the one customized for this manager.

	"""

	def __init__(self, shutdownEvent, canceledEvent, globalSettings):
		"""Modified multiprocessing.Process constructor to accept custom arguments.

		Arguments:
		  shutdownEvent  - event used by main process to shutdown this one
		  canceledEvent  - event that notifies main process to restart this one
		  globalSettings - global settings; used to direct this manager

		"""
		self.serviceName = 'UniversalJobService'
		self.serviceFactory = jobService.JobServiceFactory
		self.shutdownEvent = shutdownEvent
		self.canceledEvent = canceledEvent
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
