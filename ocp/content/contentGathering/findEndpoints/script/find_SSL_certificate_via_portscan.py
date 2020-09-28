"""Security certificate detection job.

Functions:
  startJob - Standard job entry point

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Sep 19, 2020

"""
import sys, traceback
import socket, ssl
import json
import OpenSSL
import datetime
from contextlib import suppress

## From openContentPlatform
from utilities import runPortTest
from utilities import addObject, addLink


def trackCertificate(runtime, ipAddress, ipObjectId, port, cert):
	addObject(runtime, 'IpAddress', uniqueId=ipObjectId)
	## Create TcpIpPort
	tcpIpPortId, portExists = addObject(runtime, 'TcpIpPort', name=str(port), port=int(port), ip=ipAddress, port_type='tcp', is_tcp=True)
	## Create SSLCertificate
	sslCertificateId, certExists = addObject(runtime, 'SSLCertificate', **cert)
	## Links
	addLink(runtime, 'Enclosed', ipObjectId, tcpIpPortId)
	addLink(runtime, 'Enclosed', tcpIpPortId, sslCertificateId)


def stringify(value):
	if value is not None:
		if isinstance(value, bytes):
			return value.decode('utf-8')
		return str(value)


def listToDict(x509NameList):
	value = {}
	for entry in x509NameList:
		(binKey, binValue) = entry
		value[stringify(binKey)] = stringify(binValue)
	return value


def convertTime(value):
	## Time format coming in: b'YYYYmmddHHMMSSZ'
	timeRepr = stringify(value)
	## Time format for sqlAlchemy: YYYY-mm-dd HH:MM:SSZ or YYYY-mm-dd HH:MM:SS
	## We could just string parse the value, but I'll use conversion
	dt = datetime.datetime.strptime(timeRepr, '%Y%m%d%H%M%SZ')
	return dt.strftime('%Y-%m-%d %H:%M:%SZ')


def getCertificate(nameContext, port, connectTimeout=3):
	"""Attempt the SSL handshake and pull back the certificate."""
	with socket.create_connection((nameContext, port), connectTimeout) as sock:
		ctx = ssl.create_default_context()
		ctx.check_hostname = False
		ctx.verify_mode = ssl.CERT_NONE
		with ctx.wrap_socket(sock, server_hostname=nameContext) as sslSocket:
			sslVersion = sslSocket.version()
			## The default call to getpeercert won't work with verification
			## disabled, since the certificate is dropped; need to handle this
			#cert = sslSocket.getpeercert()
			binaryCert = sslSocket.getpeercert(True)

			## Get the binary certificate and manipulate through pyOpenSSL calls
			x509cert = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_ASN1, binaryCert)

			## Pull out desired context
			issuer = listToDict(x509cert.get_issuer().get_components())
			subject = listToDict(x509cert.get_subject().get_components())
			cert = {
				'issuer' : issuer,
				'serial_number' : stringify(x509cert.get_serial_number()),
				'subject' : subject,
				'common_name' : stringify(x509cert.get_subject().CN),
				## Prefer to see the full string (TLSv1.2 instead of 2)
				#'version' : x509cert.get_version(),
				'version' : sslVersion,
				'not_before' : convertTime(stringify(x509cert.get_notBefore())),
				'not_after' : convertTime(stringify(x509cert.get_notAfter()))
			}

			## The signature algorithm may be null, but track if returned
			cert['signature_algorithm'] = None
			with suppress(Exception):
				cert['signature_algorithm'] = stringify(x509cert.get_signature_algorithm())

			## Subject alternate name section is a bit more work...
			cert['subject_alt_name'] = None
			extensionCount = x509cert.get_extension_count()
			for i in range(0, extensionCount):
				extension = x509cert.get_extension(i)
				if 'subjectAltName' in stringify(extension.get_short_name()):
					rawName = extension.__str__()
					cert['subject_alt_name'] = rawName.replace('DNS', '').replace(':', '')

			## end getCertificate
			return (sslVersion, cert)


def attemptConnection(runtime, ipAddress, port, connectTimeout):
	"""Go through name records and attempt an SSL handshake."""
	version = None
	cert = None
	try:
		## Previously this job ran through all DNS names/aliases, but it would
		## miss self-signed certs and others where the name mismatched. So now
		## the job uses IP address, ignores name matching, and pulls the cert.
		nameContext = ipAddress
		runtime.logger.report(' trying address: {}:{}'.format(nameContext, port))
		(version, cert) = getCertificate(nameContext, port, connectTimeout)
		if len(cert) <= 0:
			## Should never get here, since we are pulling the binary cert back
			runtime.logger.report(' SUCCESS with {} - but found no certificate'.format(version))
		else:
			runtime.logger.report(' SUCCESS with {}. SSL version: '.format(version))

	## Catch certain messages...

	## These two indicate the wrong name was used, but that the IP:port
	## combination has a valid certificate; it's just not sharing yet.
	##   ssl.CertificateError: hostname <name or IP> doesn't match either
	##     of '*.domain.com', 'domainsites.com'
	##   ConnectionResetError: [WinError 10054] An existing connection
	##     was forcibly closed by the remote host
	## But now that we're using the IP instead of name, we should not see this
	except ssl.CertificateError:
		msg = str(sys.exc_info()[1])
		runtime.logger.report(' CertificateError: {}'.format(msg))
	except ConnectionResetError:
		msg = str(sys.exc_info()[1])
		runtime.logger.report(' ConnectionResetError: {}'.format(msg))

	## This may indicate the IP:port isn't secured with a certificate:
	##   ssl.SSLEOFError: EOF occurred in violation of protocol
	except ssl.SSLEOFError:
		msg = str(sys.exc_info()[1])
		runtime.logger.report(' SSLEOFError: {}'.format(msg))

	## This indicates the IP:port isn't active/listening
	##   TimeoutError: [WinError 10060] A connection attempt failed
	##   because the connected party did not properly respond after a
	##   period of time, or established connection failed because
	##   connected host has failed to respond
	except TimeoutError:
		msg = str(sys.exc_info()[1])
		runtime.logger.report(' Endpoint {}:{} is not responding. TimeoutError: {}'.format(nameContext, port, msg))

	## This may indicate that the listener port isn't using SSL/TLS
	except socket.timeout:
		msg = str(sys.exc_info()[1])
		runtime.logger.report(' Endpoint {}:{} is listening, but may not be secured. Received timeout exception: {}'.format(nameContext, port, msg))

	## This may indicate the provided context could not be resolved in DNS:
	##  socket.gaierror: [Errno 11001] getaddrinfo failed
	except socket.gaierror:
		msg = str(sys.exc_info()[1])
		runtime.logger.report(' {} did not resolve in DNS. Exception: {}'.format(nameContext, port, msg))

	## For all others...
	except:
		msg = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.report(' Exception: {}'.format(str(msg)))
		runtime.setError(__name__)

	## end attemptConnection
	return (version, cert)


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
				(version, cert) = attemptConnection(runtime, ipAddress, port, connectTimeout)
				if version is not None:
					trackCertificate(runtime, ipAddress, ipObjectId, port, cert)

	except:
		runtime.setError(__name__)

	## end startJob
	return
