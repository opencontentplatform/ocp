"""Dynamic discovery for Base Application Components.

Both dynamic discovery jobs for Application Components ('Base' & 'Vocal') use
a common library with the same functions and code paths - once a process is
selected. However, the method for selecting a process is different. The 'Base'
job selects processes at the bottom of the process tree (those without any
spawned children), while the 'Vocal' job selects processes using the network.
Those two methods reveal different types of application components, and each
has proven extremely useful for automated mapping and modeling techniques.

Functions:
  startJob : standard job entry point
  vocalAppComponents : find processes using the network and start investigation
  standardVocalSetup : setup required on all OS types for 'Vocal' discovery

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Jun 25, 2018

"""
import sys
import traceback
from contextlib import suppress

## From openContentPlatform
from protocolWrapper import getClient
## From this package
import osNetworkStack
import osSoftwarePackages
import osStartTasks
import shellAppComponentsUtils


def createEstablishedLocalObjects(runtime, data, serverProcessId, serverIp, serverPort, serverSoftwareName, serverProcessName, clientProcessId, clientIp, clientPort, clientSoftwareName, clientProcessName):
	try:
		serverEndpoint = '{}:{}'.format(serverIp, serverPort)
		clientEndpointReal = '{}:{}'.format(clientIp, clientPort)
		clientEndpoint = '{}:{}:{}'.format(serverIp, serverPort, clientIp)
		runtime.logger.report('Local Component {serverSoftwareName!r} for process {serverProcessName!r} on connection {serverEndpoint!r} is server  -->  Local Component {clientSoftwareName!r} for process {clientProcessName!r} on connection {clientEndpoint!r} is client', serverSoftwareName=serverSoftwareName, serverProcessName=serverProcessName, serverEndpoint=serverEndpoint, clientSoftwareName=clientSoftwareName, clientProcessName=clientProcessName, clientEndpoint=clientEndpointReal)
		tcpIpPortId = data.serverPorts.get(serverEndpoint)
		tcpIpPortClientId = data.clientPorts.get(clientEndpoint)
		runtime.logger.report(' createEstablishedLocalObjects tcpPorts1:  tcpIpPortId {tcpIpPortId!r} - tcpIpPortClientId {tcpIpPortClientId!r}', tcpIpPortId=tcpIpPortId, tcpIpPortClientId=tcpIpPortClientId)
		if tcpIpPortId is None or tcpIpPortClientId is None:
			runtime.logger.report('   Creating Server TcpIpPort {serverEndpoint!r}', serverEndpoint=serverEndpoint)
			## Don't map multiple links between the same source/dest objects:
			##  IP --> Enclosed --> TcpIpPortClient
			##  IP --> ServerClient --> TcpIpPortClient
			## So if both client/server is on the same box, then connect the
			## processes through the client port, but don't connect IPs to port.
			(tcpIpPortId, tcpIpPortClientId) = osNetworkStack.addTcpPort(runtime, 'tcp', serverIp, serverPort, data.trackedIPs, clientIP=clientIp, isLocal=True)
			runtime.logger.report(' createEstablishedLocalObjects tcpPorts2:  tcpIpPortId {tcpIpPortId!r} - tcpIpPortClientId {tcpIpPortClientId!r}', tcpIpPortId=tcpIpPortId, tcpIpPortClientId=tcpIpPortClientId)
			if tcpIpPortId is not None:
				## Update the port dictionary with the object id
				data.serverPorts[serverEndpoint] = tcpIpPortId
			if tcpIpPortClientId is not None:
				data.clientPorts[clientEndpoint] = tcpIpPortClientId
		runtime.logger.report(' createEstablishedLocalObjects tcpPorts3:  tcpIpPortId {tcpIpPortId!r} - tcpIpPortClientId {tcpIpPortClientId!r}.  serverProcessId {serverProcessId!r} and clientProcessId {clientProcessId!r}', tcpIpPortId=tcpIpPortId, tcpIpPortClientId=tcpIpPortClientId, serverProcessId=serverProcessId, clientProcessId=clientProcessId)
		if tcpIpPortId is not None and tcpIpPortClientId is not None:
			runtime.results.addLink('Usage', serverProcessId, tcpIpPortId)
			runtime.logger.report('   Linked server process {serverProcessName!r} to static port {serverEndpoint!r}', serverProcessName=serverProcessName, serverEndpoint=serverEndpoint)
			runtime.results.addLink('ServerClient', serverProcessId, tcpIpPortClientId)
			runtime.logger.report('   Linked server process {serverProcessName!r} to server port {serverEndpoint!r}', serverProcessName=serverProcessName, serverEndpoint=serverEndpoint)
			runtime.results.addLink('Usage', clientProcessId, tcpIpPortClientId)
			runtime.logger.report('      and server port {serverEndpoint!r} to client process {clientProcessName!r}', serverEndpoint=serverEndpoint, clientProcessName=clientProcessName)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in createEstablishedLocalObjects: {stacktrace!r}', stacktrace=stacktrace)

	## end createEstablishedLocalObjects
	return


def mapEstablishedLocalConnection(runtime, data, selfClientMapping, softwareFingerprintId, softwareName, processFingerprintId, processName, processData, localIP, localPort, remoteIP, remotePort, flipped):
	"""Map self clients, where both the client & server are on the same node."""
	try:
		mappedSelfClient = False
		for selfClientComponent in selfClientMapping:
			(remotePortPrevious, localPortPrevious, softwareIdPrevious, softwareNamePrevious, processIdPrevious, processNamePrevious, flippedPrevious) = selfClientComponent
			if ((localPort == remotePortPrevious) and (remotePort == localPortPrevious)):
				## Already parsed the other side of this connection
				mappedSelfClient = True
				## If neither port had a Listener, determine which port to
				## use as the 'server'; this is valid for socket connections
				if (flipped == flippedPrevious):
					if (localPort < remotePort):
						flipped = 0
					else:
						flipped = 1
				if flipped:
					## The second side of the connection is the server
					createEstablishedLocalObjects(runtime, data, processIdPrevious, remoteIP, remotePort, softwareNamePrevious, processNamePrevious, processFingerprintId, localIP, localPort, softwareName, processName)
				else:
					## The first side of the connection is the server
					createEstablishedLocalObjects(runtime, data, processFingerprintId, localIP, localPort, softwareName, processName, processIdPrevious, remoteIP, remotePort, softwareNamePrevious, processNamePrevious)
				break
		## If we haven't parsed the other side of this connection yet,
		## save this until we've qualified both sides of the connection
		if not mappedSelfClient:
			selfClientMapping.append((remotePort, localPort, softwareFingerprintId, softwareName, processFingerprintId, processName, flipped))
			runtime.logger.report('  Appending current Component to list... software {softwareName!r} process {processName!r} using {localEndpoint!r}', softwareName=softwareName, processName=processName, localEndpoint='{}:{}'.format(localIP, localPort))

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in mapEstablishedLocalConnection: {stacktrace!r}', stacktrace=stacktrace)

	## end mapEstablishedLocalConnection
	return


def parseEstablishedLocalConnections(runtime, data, establishedList):
	"""Parse Established connections that are local/within the same Node."""
	selfClientMapping = []
	networkCreateLocalConnections = runtime.endpoint.get('data').get('parameters').get('networkCreateLocalConnections', True)
	## Go through the connections
	for connectionData in establishedList:
		try:
			(localIP, localPort, remoteIP, remotePort, pid, flipped) = connectionData
			## Report even when not mapping the local connections
			if not networkCreateLocalConnections:
				runtime.logger.report(' skipping self-client {localEndpoint!r} to {remoteEndpoint!r}', localEndpoint='{}:{}'.format(localIP, localPort), remoteEndpoint='{}:{}'.format(remoteIP, remotePort))
				continue
			runtime.logger.report(' mapping self-client {localEndpoint!r} to {remoteEndpoint!r}', localEndpoint='{}:{}'.format(localIP, localPort), remoteEndpoint='{}:{}'.format(remoteIP, remotePort))

			## Get the local process context; keep in mind the local process
			## may have started after our query or may have been filtered out
			if (int(pid) not in data.processDictionary.keys()):
				runtime.logger.report('  skipping process (either filtered out or stopped/started during analysis) with pid {pid!r} using local established connection {localEndpoint!r} to {remoteEndpoint!r}', pid=pid, localEndpoint='{}:{}'.format(localIP, localPort), remoteEndpoint='{}:{}'.format(remoteIP, remotePort))
				continue

			(processData, ppid, objectId) = data.processDictionary[int(pid)]
			processName = processData.get('name')
			softwareName = 'Unknown'
			softwareFingerprintId = None
			processFingerprintId = None
			runtime.logger.report('  process {processName!r} with PID {pid!r} using local established connection {localEndpoint!r} to {remoteEndpoint!r} ---> {processData!r}', processName=processName, pid=pid, localEndpoint='{}:{}'.format(localIP, localPort), remoteEndpoint='{}:{}'.format(remoteIP, remotePort), processData=processData)

			## Determine if process already exists or if we should skip it
			(skipProcess, processFingerprintId) = shellAppComponentsUtils.shouldWeSkipThisProcess(runtime, processData, data)
			if skipProcess:
				continue
			if processFingerprintId is not None:
				## Process was passed in as input; exists in database already
				## but we won't have the software context (if it was created)
				softwareName = '(identified previously)'
				runtime.results.addObject('ProcessFingerprint', uniqueId=processFingerprintId)
			else:
				if int(pid) in data.pidTracking:
					## Process was found in a previous walkPIDtree on this
					## invocation, and so we get the handle from before
					(processFingerprintId, processData) = data.pidTracking[pid]
				else:
					## Determine if we are looking at a process we need to ignore
					## and instead look one level higher in the process tree
					(pid, processData, objectId) = shellAppComponentsUtils.translateIgnoredProcess(runtime, data, pid, processData, ppid, objectId)
					if processData is None:
						continue
					## Process wasn't found; need to do some investigation
					if not data.osSpecificSetupComplete:
						## Run osSpecificSetup if this is the first time here
						shellAppComponentsUtils.osSpecificSetup(runtime, data)
						data.osSpecificSetupComplete = True
					## Find out what this process belongs to
					(processFingerprintId, softwareFingerprintId) = shellAppComponentsUtils.walkPIDtree(runtime, data, pid, processData, objectId)
					if softwareFingerprintId is None:
						runtime.logger.report('   No SoftwareFingerprint found for pid {pid!r} using local established connection {localEndpoint!r} to {remoteEndpoint!r}', pid=pid, localEndpoint='{}:{}'.format(localIP, localPort), remoteEndpoint='{}:{}'.format(remoteIP, remotePort))
					else:
						runtime.logger.report('      SoftwareFingerprint found for pid {pid!r} using local established connection {localEndpoint!r} to {remoteEndpoint!r}', pid=pid, localEndpoint='{}:{}'.format(localIP, localPort), remoteEndpoint='{}:{}'.format(remoteIP, remotePort))
						## Set the softwareName if it has a value
						softwareObject = runtime.results.getObject(softwareFingerprintId)
						if softwareObject is not None:
							tempName = softwareObject.get('name')
							if tempName is not None:
								softwareName = tempName
					if processFingerprintId is None:
						## Nothing to do if we didn't create a processFingerprint
						runtime.logger.report('   No ProcessFingerprint  found for pid {pid!r} using local established connection {localEndpoint!r} to {remoteEndpoint!r}', pid=pid, localEndpoint='{}:{}'.format(localIP, localPort), remoteEndpoint='{}:{}'.format(remoteIP, remotePort))
						continue
					runtime.logger.report('      ProcessFingerprint  found for pid {pid!r} using local established connection {localEndpoint!r} to {remoteEndpoint!r}', pid=pid, localEndpoint='{}:{}'.format(localIP, localPort), remoteEndpoint='{}:{}'.format(remoteIP, remotePort))
					## Add process to the collection found from walkPIDtree
					data.pidTracking[pid] = (processFingerprintId, processData)

			## Map the locally established connection
			mapEstablishedLocalConnection(runtime, data, selfClientMapping, softwareFingerprintId, softwareName, processFingerprintId, processName, processData, localIP, localPort, remoteIP, remotePort, flipped)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in parseEstablishedLocalConnections: {stacktrace!r}', stacktrace=stacktrace)

	## end parseEstablishedLocalConnections
	return


def createEstablishedRemotePort(runtime, data, serverIp, serverPort, clientIp):
	tcpIpPortId = None
	tcpIpPortClientId = None
	try:
		serverEndpoint = '{}:{}'.format(serverIp, serverPort)
		tcpIpPortId = data.serverPorts.get(serverEndpoint)
		clientEndpoint = '{}:{}:{}'.format(serverIp, serverPort, clientIp)
		tcpIpPortClientId = data.clientPorts.get(clientEndpoint)
		runtime.logger.report(' createEstablishedRemotePort tcpPorts1:  tcpIpPortId {tcpIpPortId!r} - tcpIpPortClientId {tcpIpPortClientId!r}', tcpIpPortId=tcpIpPortId, tcpIpPortClientId=tcpIpPortClientId)
		if tcpIpPortId is None or tcpIpPortClientId is None:
			runtime.logger.report('   Creating Server TcpIpPort {serverEndpoint!r}', serverEndpoint=serverEndpoint)
			(tcpIpPortId, tcpIpPortClientId) = osNetworkStack.addTcpPort(runtime, 'tcp', serverIp, serverPort, data.trackedIPs, clientIP=clientIp)
			runtime.logger.report(' createEstablishedRemotePort tcpPorts2:  tcpIpPortId {tcpIpPortId!r} - tcpIpPortClientId {tcpIpPortClientId!r}', tcpIpPortId=tcpIpPortId, tcpIpPortClientId=tcpIpPortClientId)
			## Update the port dictionaries
			if tcpIpPortId is not None:
				data.serverPorts[serverEndpoint] = tcpIpPortId
			if tcpIpPortClientId is not None:
				data.clientPorts[clientEndpoint] = tcpIpPortClientId

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in createEstablishedRemotePort: {stacktrace!r}', stacktrace=stacktrace)

	## end createEstablishedRemotePort
	return (tcpIpPortId, tcpIpPortClientId)


def mapEstablishedRemoteConnection(runtime, data, softwareName, processFingerprintId, processName, processData, localIP, localPort, remoteIP, remotePort, flipped):
	"""Map remote connections."""
	try:
		if flipped:
			## The remote side of the connection is the server
			serverEndpoint = '{}:{}'.format(remoteIP, remotePort)
			clientEndpoint = '{}:{}'.format(localIP, localPort)
			runtime.logger.report('Local Component is client:  {softwareName!r} for process {processName!r} on connection {clientEndpoint!r} --> {serverEndpoint!r}', softwareName=softwareName, processName=processName, clientEndpoint=clientEndpoint, serverEndpoint=serverEndpoint)
			(tcpIpPortId, tcpIpPortClientId) = createEstablishedRemotePort(runtime, data, remoteIP, remotePort, localIP)
			runtime.logger.report(' mapEstablishedRemoteConnection tcpPorts1:  tcpIpPortId {tcpIpPortId!r} - tcpIpPortClientId {tcpIpPortClientId!r}', tcpIpPortId=tcpIpPortId, tcpIpPortClientId=tcpIpPortClientId)
			if tcpIpPortClientId is not None:
				runtime.results.addLink('Usage', processFingerprintId, tcpIpPortClientId)
				runtime.logger.report('   Linked client process {processName!r} to client port {serverEndpoint!r} with server attributes.', processName=processName, serverEndpoint=serverEndpoint)

		else:
			## The local side of the connection is the server
			serverEndpoint = '{}:{}'.format(localIP, localPort)
			clientEndpoint = '{}:{}'.format(remoteIP, remotePort)
			runtime.logger.report('Local Component is server:  {softwareName!r} for process {processName!r} on connection {serverEndpoint!r} --> {clientEndpoint!r}', softwareName=softwareName, processName=processName, serverEndpoint=serverEndpoint, clientEndpoint=clientEndpoint)
			(tcpIpPortId, tcpIpPortClientId) = createEstablishedRemotePort(runtime, data, localIP, localPort, remoteIP)
			runtime.logger.report(' mapEstablishedRemoteConnection tcpPorts2:  tcpIpPortId {tcpIpPortId!r} - tcpIpPortClientId {tcpIpPortClientId!r}', tcpIpPortId=tcpIpPortId, tcpIpPortClientId=tcpIpPortClientId)

			if tcpIpPortId is not None:
				runtime.results.addLink('Usage', processFingerprintId, tcpIpPortId)
				runtime.logger.report('   Linked server process {processName!r} to static port {serverEndpoint!r}', processName=processName, serverEndpoint=serverEndpoint)
			if tcpIpPortClientId is not None:
				runtime.results.addLink('ServerClient', processFingerprintId, tcpIpPortClientId)
				runtime.logger.report('      and server process {processName!r} to client port {serverEndpoint!r} with server attributes.', processName=processName, serverEndpoint=serverEndpoint)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in mapEstablishedRemoteConnection: {stacktrace!r}', stacktrace=stacktrace)

	## end mapEstablishedRemoteConnection
	return


def parseEstablishedRemoteConnections(runtime, data, establishedList):
	"""Parse Established connections to a remote Node."""
	## Go through the connections
	for connectionData in establishedList:
		try:
			(localIP, localPort, remoteIP, remotePort, pid, flipped) = connectionData
			runtime.logger.report(' mapping local endpoint {localEndpoint!r} to remote endpoint {remoteEndpoint!r}', localEndpoint='{}:{}'.format(localIP, localPort), remoteEndpoint='{}:{}'.format(remoteIP, remotePort))

			## Get the local process context; keep in mind the local process
			## may have started after our query or may have been filtered out
			if (int(pid) not in data.processDictionary.keys()):
				runtime.logger.report('  skipping process (either filtered out or stopped/started during analysis) with pid {pid!r} using remote established connection {localEndpoint!r} to {remoteEndpoint!r}', pid=pid, localEndpoint='{}:{}'.format(localIP, localPort), remoteEndpoint='{}:{}'.format(remoteIP, remotePort))
				continue

			(processData, ppid, objectId) = data.processDictionary[int(pid)]
			processName = processData.get('name')
			softwareName = 'Unknown'
			softwareFingerprintId = None
			processFingerprintId = None
			runtime.logger.report('  process {processName!r} with PID {pid!r} using remote established connection {localEndpoint!r} to {remoteEndpoint!r} ---> {processData!r}', processName=processName, pid=pid, localEndpoint='{}:{}'.format(localIP, localPort), remoteEndpoint='{}:{}'.format(remoteIP, remotePort), processData=processData)

			## Determine if process already exists or if we should skip it
			(skipProcess, processFingerprintId) = shellAppComponentsUtils.shouldWeSkipThisProcess(runtime, processData, data)
			if skipProcess:
				continue
			if processFingerprintId is not None:
				## Process was passed in as input; exists in database already
				## but we won't have the software context (if it was created)
				softwareName = '(identified previously)'
				runtime.results.addObject('ProcessFingerprint', uniqueId=processFingerprintId)
			else:
				if int(pid) in data.pidTracking:
					## Process was found in a previous walkPIDtree on this
					## invocation, and so we get the handle from before
					(processFingerprintId, processData) = data.pidTracking[pid]
				else:
					## Determine if we are looking at a process we need to ignore
					## and instead look one level higher in the process tree
					(pid, processData, objectId) = shellAppComponentsUtils.translateIgnoredProcess(runtime, data, pid, processData, ppid, objectId)
					if processData is None:
						continue
					## Process wasn't found; need to do some investigation
					if not data.osSpecificSetupComplete:
						## Run osSpecificSetup if this is the first time here
						shellAppComponentsUtils.osSpecificSetup(runtime, data)
						data.osSpecificSetupComplete = True
					## Find out what this process belongs to
					(processFingerprintId, softwareFingerprintId) = shellAppComponentsUtils.walkPIDtree(runtime, data, pid, processData, objectId)
					if softwareFingerprintId is None:
						runtime.logger.report('   No SoftwareFingerprint found for pid {pid!r} using local established connection {localEndpoint!r} to {remoteEndpoint!r}', pid=pid, localEndpoint='{}:{}'.format(localIP, localPort), remoteEndpoint='{}:{}'.format(remoteIP, remotePort))
					else:
						runtime.logger.report('      SoftwareFingerprint found for pid {pid!r} using local established connection {localEndpoint!r} to {remoteEndpoint!r}', pid=pid, localEndpoint='{}:{}'.format(localIP, localPort), remoteEndpoint='{}:{}'.format(remoteIP, remotePort))
						## Set the softwareName if it has a value
						softwareObject = runtime.results.getObject(softwareFingerprintId)
						if softwareObject is not None:
							tempName = softwareObject.get('name')
							if tempName is not None:
								softwareName = tempName
					if processFingerprintId is None:
						## Nothing to do if we didn't create a processFingerprint
						runtime.logger.report('   No ProcessFingerprint  found for pid {pid!r} using local established connection {localEndpoint!r} to {remoteEndpoint!r}', pid=pid, localEndpoint='{}:{}'.format(localIP, localPort), remoteEndpoint='{}:{}'.format(remoteIP, remotePort))
						continue
					runtime.logger.report('      ProcessFingerprint  found for pid {pid!r} using local established connection {localEndpoint!r} to {remoteEndpoint!r}', pid=pid, localEndpoint='{}:{}'.format(localIP, localPort), remoteEndpoint='{}:{}'.format(remoteIP, remotePort))
					## Add process to the collection found from walkPIDtree
					data.pidTracking[pid] = (processFingerprintId, processData)

			## Map the established connection
			mapEstablishedRemoteConnection(runtime, data, softwareName, processFingerprintId, processName, processData, localIP, localPort, remoteIP, remotePort, flipped)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in parseEstablishedRemoteConnections: {stacktrace!r}', stacktrace=stacktrace)

	## end parseEstablishedRemoteConnections
	return


def isThisIpAddressLocal(thisIP, nodeIpList):
	isLocalAddress = False
	if (thisIP == '127.0.0.1' or thisIP == '::1' or
		thisIP == '0.0.0.0' or thisIP == '::0' or thisIP == '*'):
		isLocalAddress = True
	else:
		for entry in nodeIpList:
			(localIp, isIpv4) = entry
			if thisIP == localIp:
				isLocalAddress = True
				break
	return isLocalAddress


def workOnThisEstablishedList(runtime, data, thisIp, establishedListOnSameHost, establishedListOnLocalHost):
	"""Shared code to take action on connections grouped for a single IP."""
	try:
		## All connections grouped for a single IP; now separate
		## connections into lists and distinguish local/remote
		isLocalAddress = isThisIpAddressLocal(thisIp, data.ipList)
		runtime.logger.report(' prevIP {thisIp!r} is local? {isLocalAddress!r}', thisIp=thisIp, isLocalAddress=isLocalAddress)
		if isLocalAddress:
			## Add them onto the local list
			runtime.logger.report(' workOnThisEstablishedList: adding these connections for {thisIp!r} into Local query: {establishedListOnSameHost!r}', thisIp=thisIp, establishedListOnSameHost=establishedListOnSameHost)
			for entry in establishedListOnSameHost:
				establishedListOnLocalHost.append(entry)
		else:
			## Right now I am not actively following remote connections
			runtime.logger.report(' workOnThisEstablishedList: create remote objects for {thisIp!r}:  {establishedListOnSameHost!r}', thisIp=thisIp, establishedListOnSameHost=establishedListOnSameHost)
			parseEstablishedRemoteConnections(runtime, data, establishedListOnSameHost)
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in workOnThisEstablishedList: {stacktrace!r}', stacktrace=stacktrace)

	## end workOnThisEstablishedList
	return


def discoverEstablishedConnections(runtime, data):
	"""Controller function to start working on Established connections."""
	## Sort the list of connections based on the remote IP address. I need to do
	## this before working through, to optimize discovery when/if I'm going out
	## to the remote side; issue single query to IPs with multiple connections.
	data.tcpEstablishedList.sort(key=lambda x: x[2])
	## Separate the connections into two lists: remote and local
	establishedListOnSameHost = []
	establishedListOnLocalHost = []
	prevIP = None
	currIP = None
	try:
		## Group all remote connections so we can optimize discovery and issue
		## a single query to IPs with multiple Established connections
		for connectionData in data.tcpEstablishedList:
			try:
				(localIP, localPort, remoteIP, remotePort, pid) = connectionData
				runtime.logger.report('connectionData: {connectionData!r}', connectionData=connectionData)
				prevIP = currIP
				currIP = remoteIP
				if (currIP is None):
					continue

				## Identify whether local port is a client or server. We have a
				## list of server ports (from netstat/lsof), so check if local
				## port is in that list. If so, identify it as the server.
				flipped = 1
				addr1 = '{}:{}'.format(localIP, localPort)
				addr2 = '127.0.0.1:{}'.format(localPort)
				if (localIP == '0.0.0.0' or localIP == '::0' or
					addr1 in data.serverPorts.keys() or
					addr2 in data.serverPorts.keys()):
					flipped = 0

				## Add the flipped context into the Established line data
				tmpData = (localIP, localPort, remoteIP, remotePort, pid, flipped)
				## If it's the same IP, keep adding to the same list
				if (prevIP is None or prevIP == currIP):
					establishedListOnSameHost.append(tmpData)
				## If it's a new IP, do something with the last list first
				else:
					workOnThisEstablishedList(runtime, data, prevIP, establishedListOnSameHost, establishedListOnLocalHost)
					## reinitialize the list for a new IP address
					establishedListOnSameHost = []
					establishedListOnSameHost.append(tmpData)
				runtime.logger.report(' discoverEstablishedConnections:  finished {connectionData!r}', connectionData=connectionData)
			except:
				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				runtime.logger.error('Exception in discoverEstablishedConnections: {stacktrace!r}', stacktrace=stacktrace)

		## Process the last remote group
		if currIP:
			workOnThisEstablishedList(runtime, data, currIP, establishedListOnSameHost, establishedListOnLocalHost)
		## Remote lists processed, now process the local list
		runtime.logger.report(' discoverEstablishedConnections: create local objects for:  {establishedListOnLocalHost!r}', establishedListOnLocalHost=establishedListOnLocalHost)
		parseEstablishedLocalConnections(runtime, data, establishedListOnLocalHost)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in discoverEstablishedConnections: {stacktrace!r}', stacktrace=stacktrace)

	## Memory management for large queries
	establishedListOnSameHost = None
	establishedListOnLocalHost = None

	## end discoverEstablishedConnections
	return


def mapListeners(runtime, data, listenerList, listenerType, isRemote=False):
	"""Create Application Components for listener addresses."""
	for listenerEntry in listenerList:
		try:
			(serverIP, serverPort, pid) = listenerEntry
			listenerAddress = '{}:{}'.format(serverIP, serverPort)
			runtime.logger.report(' {listenerType!r} listener line: {listenerAddress!r}, PID: {pid!r}', listenerType=listenerType, listenerAddress=listenerAddress, pid=pid)
			## Update serverPorts, which is a simple dictionary whose existence
			## is only for identifying server ports for the TCP connections
			if (listenerType == 'TCP'):
				## Initialize to None for now; if we create the TcpIpPort below
				## then the value will be changed to the object identifier
				data.serverPorts[listenerAddress] = None

			## If process was filtered out, we won't find the PID
			if (pid and int(pid) in data.processDictionary.keys()):
				(processData, ppid, objectId) = data.processDictionary[int(pid)]
				runtime.logger.report('  process {processName!r} with PID {pid!r} is using {listenerType!r} server port {serverPort!r} ---> {processData!r}', processName=processData.get('name'), pid=pid, listenerType=listenerType, serverPort=serverPort, processData=processData)

				## Determine if process already exists or if we should skip it
				(skipProcess, processFingerprintId) = shellAppComponentsUtils.shouldWeSkipThisProcess(runtime, processData, data)
				if skipProcess:
					continue
				if processFingerprintId is not None:
					## Process was passed in as input; exists in database already
					## but we won't have the software context (if it was created)
					data.pidTracking[pid] = (processFingerprintId, processData)
					runtime.results.addObject('ProcessFingerprint', uniqueId=processFingerprintId)
				else:
					## Determine if we are looking at a process we need to ignore
					## and instead look one level higher in the process tree
					(pid, processData, objectId) = shellAppComponentsUtils.translateIgnoredProcess(runtime, data, pid, processData, ppid, objectId)
					if processData is None:
						continue
					if not data.osSpecificSetupComplete:
						## Run the osSpecificSetup before looking at the first
						## process; this is down here instead of at the start of
						## the flow because unless a new process is found, we
						## won't need to ask this of the endpoint.
						shellAppComponentsUtils.osSpecificSetup(runtime, data)
						data.osSpecificSetupComplete = True
					## Call WalkPIDtree to create objects if this is a local run
					## but wait until we qualify the match when this is remote
					(processFingerprintId, softwareFingerprintId) = shellAppComponentsUtils.walkPIDtree(runtime, data, pid, processData, objectId)
					## Add process to the collection found from walkPIDtree
					data.pidTracking[pid] = (processFingerprintId, processData)

				if processFingerprintId is not None:
					runtime.logger.report('   Creating listener TcpIpPort {serverIP!r}:{serverPort!r}', serverIP=serverIP, serverPort=serverPort)
					(tcpIpPortId, tcpIpPortClientId) = osNetworkStack.addTcpPort(runtime, listenerType.lower(), serverIP, serverPort, data.trackedIPs)
					if tcpIpPortId is not None:
						## Update the port dictionary with the object id
						data.serverPorts[listenerAddress] = tcpIpPortId
						runtime.results.addLink('Usage', processFingerprintId, tcpIpPortId)
						runtime.logger.report('   Linked process {processName!r} to port {serverIP!r}:{serverPort!r}', processName=processData.get('name'), serverIP=serverIP, serverPort=serverPort)
				else:
					runtime.logger.report('  processFingerprintId not found for PID {pid!r} is using {listenerType!r} server port {serverPort!r}', pid=pid, listenerType=listenerType, serverPort=serverPort)
			else:
				runtime.logger.report('  process \'unknown\' (either filtered out or stopped/started during analysis) with PID {pid!r} is using {listenerType!r} server port {serverPort!r}', pid=pid, listenerType=listenerType, serverPort=serverPort)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in mapListeners: {stacktrace!r}', stacktrace=stacktrace)

	## end mapListeners
	return


def standardVocalSetup(runtime, data):
	"""Setup required on all OS types for 'Base' Application Components.

	Arguments:
	  runtime (dict)             : object used for providing I/O for jobs and
	                               tracking the job thread through its runtime
	  data (dataContainer)       : holds variables used across functions
	"""
	## Get the startTask and software filter parameters once, and use many times
	osStartTasks.getFilterParameters(runtime, data.osType, data.startTaskFilters)
	osSoftwarePackages.getFilterParameters(runtime, data.osType, data.softwareFilters)

	## Get Processes
	runtime.logger.report(' retrieving Processes...')
	runtime.logger.setFlag(False)
	shellAppComponentsUtils.getRawProcesses(runtime, data)
	runtime.logger.setFlag(data.savedPrintDebug)

	## Get Network activity
	runtime.logger.report(' retrieving Network...')
	runtime.logger.setFlag(False)
	(data.udpListenerList, data.tcpListenerList, data.tcpEstablishedList) = osNetworkStack.getNetworkStack(runtime, data.client, data.protocolIp, localIpList=data.ipList, trackResults=False, hostname=data.nodeName, domain=data.nodeDomain)
	runtime.logger.setFlag(data.savedPrintDebug)

	## end standardVocalSetup
	return


def vocalAppComponents(runtime, data):
	"""Find processes using the network and start investigation.

	Arguments:
	  runtime (dict)             : object used for providing I/O for jobs and
	                               tracking the job thread through its runtime
	  data (dataContainer)       : holds variables used across functions
	"""
	try:
		runtime.logger.report('Starting Vocal Application Component discovery on {nodeName!r} ({protocolIp!r})', nodeName=data.nodeName, protocolIp=data.protocolIp)
		## Setup required for all OS types
		standardVocalSetup(runtime, data)

		## Go through all processes associated to listener ports (UDP and TCP)
		runtime.logger.report(' processing local listeners...')
		#mapListeners(runtime, data, data.udpListenerList, 'UDP')
		mapListeners(runtime, data, data.tcpListenerList, 'TCP')

		## Go through all processes associated with established connections
		runtime.logger.report(' processing local established connections...')
		discoverEstablishedConnections(runtime, data)

		## OS cleanup; currently just the HPUX inventory temp file removal
		shellAppComponentsUtils.osSpecificCleanup(runtime, data)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in vocalAppComponents for {nodeName!r}: {stacktrace!r}', nodeName=data.nodeName, stacktrace=stacktrace)

	## end vocalAppComponents
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing I/O for jobs and tracking
	                     the job thread through its runtime
	"""
	client = None
	try:
		## Configure shell client
		client = getClient(runtime, commandTimeout=30)
		if client is not None:
			## Get a handle on our Node in order to link objects in this job
			nodeId = runtime.endpoint.get('data').get('container')
			runtime.results.addObject('Node', uniqueId=nodeId)

			## Initialize data container used to pass I/O between functions
			data = shellAppComponentsUtils.dataContainer(runtime, nodeId, client)

			## Open client session before starting the work
			client.open()

			## Do the work
			vocalAppComponents(runtime, data)

			## Good house keeping; though I force this after the exception below
			client.close()

			## Update the runtime status to success
			if runtime.getStatus() == 'UNKNOWN':
				runtime.status(1)

	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end startJob
	return
