"""Sample detection job for the Open Content Platform.

Functions:
  startJob : standard job entry point, establish a client connection
  createObjects : create and connect the node and REST object

"""
import sys
import traceback
from contextlib import suppress
from utilities import addObject, addLink, addIp
from ocpRestAPI import OcpRestAPI


def createObjects(runtime, client, realm):
	"""Create and connect the node and REST object."""
	## Get necessary info from the client
	(endpoint, reference, port, url) = client.restDetails()
	## Create the node
	nodeId, exists = addObject(runtime, 'Node', hostname=endpoint, partial=True)
	## Create a REST object to leverage for future connections
	restId, exists = addObject(runtime, 'REST', container=nodeId, ipaddress=endpoint, protocol_reference=reference, realm=realm, port=port, base_url=url, node_type='OCP')
	ipId, exists = addIp(runtime, address=endpoint)
	## And connect the objects
	addLink(runtime, 'Enclosed', nodeId, restId)
	addLink(runtime, 'Usage', nodeId, ipId)


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	client = None
	try:
		realm = runtime.jobMetaData.get('realm')
		if realm is None:
			runtime.logger.warn('Skipping job {name!r} on endpoint {endpoint!r}; realm is not set in job configuration.', name=__name__, endpoint=endpointString)
			return

		endpointString = runtime.endpoint.get('data', {}).get('address')
		runtime.logger.report('Running job {name!r} on endpoint {endpoint!r}', name=__name__, endpoint=endpointString)

		## Pull in parameters
		httpType = runtime.parameters.get('http_or_https')
		ports = runtime.parameters.get('ports')
		restPath = runtime.parameters.get('restPath')
		authPath = runtime.parameters.get('authPath')
		descriptor = runtime.parameters.get('credentialDescriptor')
		
		## Initialize client
		client = OcpRestAPI(runtime, httpType, endpointString, ports, restPath, descriptor=descriptor)
		
		## Attempt connection
		client.connect()
		runtime.logger.report('OCP connection made.')
		## Update the runtime status to SUCCESS
		runtime.status(1)
		
		## Create corresponding objects
		createObjects(runtime, client, realm)
		
	except:
		runtime.setError(__name__)

	## When no success or failure, update the status to INFO
	if runtime.getStatus() == 'UNKNOWN':
		runtime.setInfo('OCP REST API not found')

	with suppress(Exception):
		if client is not None:
			client.close()

	## end startJob
	return
