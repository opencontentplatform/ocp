"""Security certificate detection job.

Works across ports defined by job parameters.

Functions:
  startJob - Standard job entry point
  trackCertificate - Create certificate object

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Sep 19, 2020
  1.1 : (CS) Moved common functions into the shared utilities, to call from
        multiple jobs. May 18, 2020.

"""
import sys, traceback

## From openContentPlatform
from utilities import runPortTest, attemptSslHandshake, addObject, addLink


def trackCertificate(runtime, ipAddress, ipObjectId, port, cert):
	"""Create the IP, Port, and SSLCertificate."""
	addObject(runtime, 'IpAddress', uniqueId=ipObjectId)
	## Create TcpIpPort
	tcpIpPortId, portExists = addObject(runtime, 'TcpIpPort', name=str(port), port=int(port), ip=ipAddress, port_type='tcp', is_tcp=True)
	## Create SSLCertificate
	sslCertificateId, certExists = addObject(runtime, 'SSLCertificate', **cert)
	## Links
	addLink(runtime, 'Enclosed', ipObjectId, tcpIpPortId)
	addLink(runtime, 'Enclosed', tcpIpPortId, sslCertificateId)


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		endpointString = runtime.endpoint.get('data', {}).get('address')
		runtime.logger.report('Running job {name!r} on endpoint {endpoint!r}', name=__name__, endpoint=endpointString)

		## Get our targets from our runtime object passed in
		ipAddress = runtime.endpoint.get('data').get('address')
		ipObjectId = runtime.endpoint.get('identifier')

		## Port test if user requested via parameters
		portTest = runtime.parameters.get('portTestBeforeConnectionAttempt', False)
		ports = runtime.parameters.get('portsToTest', [])
		connectTimeout = int(runtime.parameters.get('connectTimeoutInSeconds', 3))
		for port in ports:
			continueFlag = True
			if portTest:
				portIsActive = runPortTest(runtime, endpointString, [int(port)])
				if not portIsActive:
					runtime.logger.report('Endpoint not listening on port {}'.format(port))
					continueFlag = False

			## Attempt the SSL handshake
			if continueFlag:
				runtime.logger.report(' Requesting SSL handshake on {}:{}'.format(ipAddress, port))
				(version, cert) = attemptSslHandshake(runtime, ipAddress, port, connectTimeout)
				if version is not None:
					trackCertificate(runtime, ipAddress, ipObjectId, port, cert)
					## Update the runtime status to SUCCESS
					runtime.status(1)

		## Update the runtime status to INFO with a relevant message
		if runtime.getStatus() == 'UNKNOWN':
			runtime.setInfo('SSL Certificates not found')

	except:
		runtime.setError(__name__)

	## end startJob
	return
