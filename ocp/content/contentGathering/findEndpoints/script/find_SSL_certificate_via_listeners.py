"""Security certificate detection job.

Works across previously created listener ports.

Functions:
  startJob - Standard job entry point
  trackCertificate - Create certificate object

"""
import sys, traceback

## From openContentPlatform
from utilities import runPortTest, attemptSslHandshake, addObject, addLink


def trackCertificate(runtime, ipAddress, portObjectId, port, cert):
	"""Create the SSLCertificate with the gathered cert attributes."""
	runtime.logger.report('Creating certificate on {}:{}'.format(ipAddress, port))
	## Create TcpIpPort
	addObject(runtime, 'TcpIpPort', uniqueId=portObjectId)
	## Create SSLCertificate
	sslCertificateId, certExists = addObject(runtime, 'SSLCertificate', **cert)
	addLink(runtime, 'Enclosed', portObjectId, sslCertificateId)


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		endpointString = runtime.endpoint.get('data', {}).get('address')
		runtime.logger.report('Running job {name!r} on endpoint {endpoint!r}', name=__name__, endpoint=endpointString)

		## Port test if user requested via parameters
		portTest = runtime.parameters.get('portTestBeforeConnectionAttempt', False)
		connectTimeout = int(runtime.parameters.get('connectTimeoutInSeconds', 3))

		## Get our targets from our runtime object passed in
		ipAddress = runtime.endpoint.get('data').get('address')
		ipObjectId = runtime.endpoint.get('identifier')
		## This pulls in all directly related listener ports (TcpIpPort)
		ports = {}
		for port in runtime.endpoint.get('children', {}).get('TcpIpPort', []):
			portObjectId = port.get('identifier')
			portName = port.get('data').get('name')
			ports[portName] = portObjectId

			continueFlag = True
			if portTest:
				portIsActive = runPortTest(runtime, endpointString, [int(portName)])
				if not portIsActive:
					runtime.logger.report('Endpoint not listening on port {}'.format(portName))
					continueFlag = False

			## Attempt the SSL handshake
			if continueFlag:
				runtime.logger.report(' Requesting SSL handshake on {}:{}'.format(ipAddress, portName))
				(version, cert) = attemptSslHandshake(runtime, ipAddress, portName, connectTimeout)
				if version is not None:
					trackCertificate(runtime, ipAddress, portObjectId, portName, cert)
					## Update the runtime status to SUCCESS
					runtime.status(1)
					
		## Update the runtime status to INFO with a relevant message
		if runtime.getStatus() == 'UNKNOWN':
			runtime.setInfo('SSL Certificates not found')

	except:
		runtime.setError(__name__)

	## end startJob
	return
