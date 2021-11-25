"""Get active ports and network connections from target endpoint via Shell.

Functions:
  startJob : standard job entry point

"""
from contextlib import suppress
## From openContentPlatform
from protocolWrapper import getClient
from osNetworkStack import getNetworkStack


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	client = None
	try:
		## Configure shell client
		client = getClient(runtime)
		if client is not None:
			## Get a handle on our IP in order to link objects in this job
			ipAddress = runtime.endpoint.get('data').get('ipaddress')
			ipList = []
			runtime.logger.report(' ENDPOINT: {endpoint!r}', endpoint=runtime.endpoint)
			## This pulls the first Node related to the shell (and there will
			## only be one since the max/min on the endpoint query is 1), and
			## pulls the list of IPs related to the Node for our local IPs:
			thisNode = runtime.endpoint.get('children').get('Node')[0]
			for ipObject in thisNode.get('children').get('IpAddress'):
				thisAddress = ipObject.get('data').get('address')
				is_ipv4 = ipObject.get('data').get('is_ipv4')
				if thisAddress is not None:
					ipList.append((thisAddress, is_ipv4))
			runtime.logger.report(' ipList: {ipList!r}', ipList=ipList)
			hostname = thisNode.get('data', {}).get('hostname')
			domain = thisNode.get('data', {}).get('domain')

			## Open client session before starting the work
			client.open()

			## Do the work
			(udpListenerList, tcpListenerList, tcpEstablishedList) = getNetworkStack(runtime, client, ipAddress, localIpList=ipList, trackResults=True, hostname=hostname, domain=domain)

			## Good house keeping; though I force this after the exception below
			client.close()

			## Update the runtime status to success
			if runtime.getStatus() == 'UNKNOWN':
				runtime.status(1)

			## Debug output
			runtime.logger.report('udpListenerList:', udpListenerList=udpListenerList)
			for listener in udpListenerList:
				runtime.logger.report('  {listener!r}', listener=listener)
			runtime.logger.report('tcpListenerList:', udpListenerList=udpListenerList)
			for listener in tcpListenerList:
				runtime.logger.report('  {listener!r}', listener=listener)
			runtime.logger.report('tcpEstablishedList:', udpListenerList=udpListenerList)
			for established in tcpEstablishedList:
				runtime.logger.report('  {established!r}', established=established)
			runtime.logger.report('results of shell_OS_network_stack: {results!r}', results=runtime.results.getJson())

	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end startJob
	return
