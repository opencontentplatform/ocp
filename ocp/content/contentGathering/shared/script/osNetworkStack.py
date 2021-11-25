"""Gather network stack on OS types.

Entry function:
  getNetworkStack : standard module entry point

OS agnostic functions:
  gatherNetworkData : gather network data - wrapper for OS types
  parseNetworkData : parse network data - wrapper for OS types
  parseUDPfromLSOF : UDP parsing via lsof
  parseTCPlistenerFromLSOF : TCP listener parsing via lsof
  parseTCPlistenerFromNetstat : TCP listener parsing via netstat
  parseListenerLine : TCP/UDP listener parsing - wrapper for lsof/netstat
  discoverListenerPorts : gather all TCP/UDP listener ports
  parseEstablishedFromLSOF : TCP established parsing via lsof
  parseEstablishedFromNetstat : TCP established parsing via netstat
  parseEstablishedLine : TCP established parsing - wrapper for lsof/netstat
  discoverEstablishedConnections : gather all TCP established connections
  translateSpecialIpAddress : Merge IPv4/IPv6 special addrs for common code paths
  getThisIp : reduce the number of times we lookup an IP
  addTcpPort : get a handle on an IP and link active ports
  createNetworkObjects : create objects (TCP/UDP ports, IPs, links)

OS specific functions:
  windowsGetNetworking : get Windows network stack
  windowsParseNetworking : parse Windows network stack

"""
import sys
import traceback
import os
import re
import ipaddress
from contextlib import suppress

from utilities import updateCommand, verifyOutputLines, concatenate, grep


## Global Variables
## List of format strings for IPs returned by netstat and lsof. I'm making
## this global for single code changes since multiple functions use it.
IP_MATCH_LIST = ['(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})',        #IPv4
				 '(\*)',                                        #unspecified
				 '::ffff:(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', #IPv4 to IPv6
				 '([0-9A-F]{1,4}:.*:[0-9A-F]{1,4}[^\]^:^\s]*)', #IPv6
				 '(::)',                                        #IPv6 unspecified
				 '(::1)']                                       #IPv6 local



def getNetworkStack(runtime, client, hostIP, localIpList=[], trackResults=False, hostname=None, domain=None):
	"""Standard entry point for osNetworkStack.

	This function returns list objects for ports and network connections. When
	the caller function requests to trackResults (meaning add objects onto the
	results object), this function adds all the created instances onto runtime's
	results so the caller function doesn't need to code that logic.
	"""
	trackedIPs = {}
	udpListenerList = []
	tcpListenerList = []
	tcpEstablishedList = []
	try:
		## Get the node type
		endpointContext = runtime.endpoint.get('data')
		osType = endpointContext.get('node_type')
		endpointContext['FQDN'] = 'NA'
		if hostname is not None:
			endpointContext['FQDN'] = hostname
			if (domain is not None and domain not in hostname):
				endpointContext['FQDN'] = '{}.{}'.format(hostname, domain)
		## Ensure we have a list of local IPs
		if len(localIpList) <= 0:
			address = ipaddress.ip_address(hostIP)
			isIpv4 = isinstance(address, ipaddress.IPv4Address)
			localIpList = (hostIP, isIpv4)
			runtime.logger.report('localIpList was EMPTY!')
		processDictionary = {}
		## Determine which utility to use
		networkUtility = determineNetworkUtility(runtime)
		## Gather network data
		networkConnectionsString = gatherNetworkData(runtime, client, osType, hostIP, networkUtility)
		## Parse network data
		if networkConnectionsString:
			parseNetworkData(runtime, client, osType, hostIP, localIpList, trackedIPs, networkUtility, udpListenerList, tcpListenerList, tcpEstablishedList, networkConnectionsString, processDictionary)
		## Create requested CIs and relationships
		if trackResults:
			createNetworkObjects(runtime, osType, udpListenerList, tcpListenerList, tcpEstablishedList, localIpList, trackedIPs)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in getNetworkStack: {stacktrace!r}', stacktrace=stacktrace)

	## end getNetworkStack
	return (udpListenerList, tcpListenerList, tcpEstablishedList)


###############################################################################
###########################  BEGIN GENERAL SECTION  ###########################
###############################################################################

def determineNetworkUtility(runtime):
	"""Determine the netstat-type utility to use for gathering network stack.

	The universally available utility available across Linux builds until 2018
	was netstat, though lsof was a common option. Later still was ss. Then some
	Linux builds (e.g. CentOS) were being released without netstat or lsof, and
	only with ss. The evolution of command utilities on different OS types is
	normal, and so the purpose of this function is to select the utility found
	by each node, during the protocol 'find' job configGroup/osParameters setup.
	"""
	commandsToTransform = runtime.endpoint.get('data').get('parameters', {}).get('commandsToTransform', {})
	## This comes from the configGroup setup and osParameters, but for example:
	## networkSocketUtilities = ['netstat', 'lsof', 'ss']
	networkSocketUtilities = runtime.endpoint.get('data').get('parameters', {}).get('networkSocketUtilities', [])
	for utility in networkSocketUtilities:
		if (commandsToTransform.get(utility) is not None):
			return utility
	raise OSError('The following network socket utilities are not available on this endpoint: {}'.format(networkSocketUtilities))

	## end determineNetworkUtility
	return


def gatherNetworkData(runtime, client, osType, hostIP, networkUtility, networkConnectionsString=None):
	"""Gather the network stack.

	Breaking these sections out of getNetworkStack and into general functions
	to enable calling the code segments independent of the whole; neccessary
	in my Database Usage package so that I can get all networking at the same
	time as SQL and Process data, and then come back to parse it when time
	isn't in the critical path.
	"""
	networkData = None
	runtime.logger.report('Gathering {osType!r} networking...', osType=osType)
	if (osType == 'Windows'):
		networkData = windowsGetNetworking(runtime, client, osType, hostIP, networkUtility, networkConnectionsString)
	elif (osType == 'Linux'):
		networkData = linuxGetNetworking(runtime, client, osType, hostIP, networkUtility, networkConnectionsString)
	elif (osType == 'HPUX'):
		#networkData = hpuxGetNetworking(runtime, client, osType, hostIP, networkConnectionsString)
		raise NotImplementedError('Network stack solution for HP-UX is not yet implemented')
	elif (osType == 'Solaris'):
		#networkData = solarisGetNetworking(runtime, client, osType, hostIP, networkConnectionsString)
		raise NotImplementedError('Network stack solution for Solaris is not yet implemented')
	elif (osType == 'AIX'):
		#networkData = aixGetNetworking(runtime, client, osType, hostIP, networkConnectionsString)
		raise NotImplementedError('Network stack solution for AIX is not yet implemented')

	## end gatherNetworkData
	return networkData


def parseNetworkData(runtime, client, osType, hostIP, localIpList, trackedIPs, networkUtility, udpListenerList, tcpListenerList, tcpEstablishedList, networkConnectionsString, processDictionary):
	"""Parse the network data."""
	try:
		runtime.logger.report('Parsing {osType!r} networking...', osType=osType)
		if (osType == 'Windows'):
			windowsParseNetworking(runtime, client, osType, hostIP, localIpList, trackedIPs, networkUtility, udpListenerList, tcpListenerList, tcpEstablishedList, networkConnectionsString)
		elif (osType == 'Linux'):
			linuxParseNetworking(runtime, client, osType, hostIP, localIpList, trackedIPs, networkUtility, udpListenerList, tcpListenerList, tcpEstablishedList, networkConnectionsString)
		elif (osType == 'HPUX'):
			#hpuxParseNetworking(Framework, client, osType, hostIP, localIpList, trackedIPs, udpListenerList, tcpListenerList, tcpEstablishedList, networkConnectionsString, processDictionary)
			pass
		elif (osType == 'Solaris'):
			#solarisParseNetworking(Framework, client, osType, hostIP, localIpList, trackedIPs, udpListenerList, tcpListenerList, tcpEstablishedList, networkConnectionsString, processDictionary)
			pass
		elif (osType == 'AIX'):
			#aixParseNetworking(Framework, client, osType, hostIP, localIpList, trackedIPs, udpListenerList, tcpListenerList, tcpEstablishedList, networkConnectionsString)
			pass
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in parseNetworkData: {stacktrace!r}', stacktrace=stacktrace)

	## end parseNetworkData
	return


def parseUDPfromLSOF(line):
	"""UDP parsing via the open source LSOF utility."""
	ip = None
	port = None
	pid = None
	## Sample LSOF output
	## ========================================================================
	## xntpd     225306     root   4u  IPv4 0xf100020000210400    0t0  UDP *:123
	## xntpd     225306     root   5u  IPv4 0xf10002000021c800    0t0  UDP 10.41.70.59:123
	## xntpd     225306     root  13u  IPv4 0xf100020001bf6000    0t0  UDP 127.255.255.255:123
	## rpcbind     3422     root   4u  IPv4 0x30038abe060         0t0  UDP *:* (Unbound)
	## postmaste   2441    sfmdb   7u  IPv4 0xe000000177a66700    0t0  UDP 127.0.0.1:49201->127.0.0.1:49201 (Idle)
	## queueman   28567 dlogtmgr   4u  IPv4 0xe0000001c7131d00    0t0  UDP 127.0.0.1:54395 (Idle)
	## ========================================================================
	if (re.search('\sUDP\s', line, re.I) and not re.search('\(Unbound\)', line, re.I)):
		for ipMatch in IP_MATCH_LIST:
			searchString = concatenate('\s(\d+)\s.*UDP\s+(?:\[)*', ipMatch, '(?:\])*:(\d+)')
			m = re.search(searchString, line, re.I)
			if m:
				pid = int(m.group(1))
				ip = m.group(2)
				port = m.group(3)
				break

	## end parseUDPfromLSOF
	return (ip, port, pid)


def parseTCPlistenerFromLSOF(line):
	"""TCP Listener parsing via the open source LSOF utility."""
	ip = None
	port = None
	pid = None
	## Sample LSOF output
	## ========================================================================
	## tqtcpd   332028  perftool   4u  IPv4 0xf1000200001efb98   0t0  TCP *:45504 (LISTEN)
	## java    1118420  documad1 170u  IPv6 0xf10002000215d398   0t0  TCP 10.41.70.30:15025 (LISTEN)
	## inetd      1837  root       5u  IPv6 0xe000000150ce0c80   0t0  TCP *:21 (LISTEN)
	## inetd      1837  root       6u  IPv6 0xe000000150ce0980   0t0  TCP *:23 (LISTEN)
	## cimserver  2398  root       4u  IPv4 0xe0000001776f7400   0t0  TCP 127.0.0.1:49155 (LISTEN)
	## ========================================================================
	if (re.search('\(LISTEN\)', line, re.I)):
		for ipMatch in IP_MATCH_LIST:
			searchString = concatenate('\s(\d+)\s.*TCP\s+(?:\[)*', ipMatch, '(?:\])*:(\d+)\s+\(L')
			m = re.search(searchString, line, re.I)
			if m:
				pid = int(m.group(1))
				ip = m.group(2)
				port = m.group(3)
				break

	## end parseTCPlistenerFromLSOF
	return (ip, port, pid)


def parseUDPfromNetstat(line, osType, client, runtime):
	"""UDP parsing via netstat and other OS specific utilities."""
	ip = None
	port = None
	pid = None
	m = None
	if (osType == 'Windows'):
		## Sample Windows netstat output
		## ============================================================
		## Proto  Local Address        Foreign Address    State    PID
		## UDP    0.0.0.0:161          *:*                         2352
		## UDP    127.0.0.1:4460       *:*                         4332
		## UDP    192.168.1.105:123    *:*                         772
		## UDP    [fe80::cc26:d842:5816:7171%10]:546  *:*          980
		## UDP    [::1]:60179          *:*                         1768
		## ============================================================
		for ipMatch in IP_MATCH_LIST:
			## Windows throws square brackets around IPv6 addresses
			searchString = concatenate('UDP\s+(?:\[)*', ipMatch, '(?:\])*:(\d+)\s.*:.*\s(\d+)')
			m = re.search(searchString, line, re.I)
			if m:
				break

	elif (osType == 'Linux'):
		## Sample Linux netstat output
		## =============================================================
		## udp    0    0 0.0.0.0:2049        0.0.0.0:*   -
		## udp    0    0 127.0.0.1:32771     0.0.0.0:*   2456/smbd
		## udp    0    0 192.168.1.104:137   0.0.0.0:*   2063/nmbd
		## udp    0    0 0.0.0.0:847         0.0.0.0:*   1943/rpc.mountd
		## udp    0    0 192.168.1.104:123   0.0.0.0:*   1901/ntpd
		## =============================================================
		for ipMatch in IP_MATCH_LIST:
			searchString = concatenate('udp(?:\d)*.\s+\d+\s+\d+\s+', ipMatch, ':(\d+)\s.*:.*\s(\d+)')
			m = re.search(searchString, line, re.I)
			if m:
				break

	elif (osType == 'AIX'):
		## This option requires sudo permissions for SOCKINFO and KDB.
		## Sample AIX netstat output
		## ==========================================================
		## f100060002269600 udp4     0      0  *.111              *.*
		## f1000600019b3800 udp4     0      0  127.0.0.1.123      *.*
		## f10006000230fe00 udp4     0      0  *.702              *.*
		## f1000600019ece00 udp4     0      0  *.2279             *.*
		## f100060003537200 udp4     0      0  10.2.4.25.6178     *.*
		## ==========================================================
		for ipMatch in IP_MATCH_LIST:
			searchString = concatenate('(\S+)\s+udp\S*\s+\d+\s+\d+\s+', ipMatch, '\.(\d+)')
			m = re.search(searchString, line, re.I)
			if m:
				break

	elif (osType == 'HPUX'):
		## This option requires sudo premission for PFILES, available after 11i
		## Sample HP-UX netstat output
		## ===========================================================
		## udp        0      0  *.*                    *.*
		## udp        0      0  *.135                  *.*
		## udp        0      0  127.0.0.1.49153        127.0.0.1.49153
		## ===========================================================
		for ipMatch in IP_MATCH_LIST:
			searchString = concatenate('udp.\s+\d+\s+\d+\s+', ipMatch, '\.(\d+)')
			m = re.search(searchString, line, re.I)
			if m:
				break

	elif (osType == 'Solaris'):
		## This option requires sudo premission for PFILES, available by default
		## Sample Solaris netstat output
		## ===========================================================
		##       *.32803                               Idle
		##       *.161                                 Idle
		##       *.32807                               Idle
		##       15.186.240.211.68                           Idle
		##       *.177                                 Idle
		## ===========================================================
		for ipMatch in IP_MATCH_LIST:
			searchString = concatenate('\s*', ipMatch, '\.(\d+)\s+Idle')
			m = re.search(searchString, line, re.I)
			if m:
				break

	## If we matched the OS specific line, get the ip/port/pid:
	if (m):
		## Need special parsing for AIX to get PID from the socket
		if (osType == 'AIX'):
			addr = m.group(1)
			ip = m.group(2)
			port = m.group(3)
			#pid = getAIXpIDfromAddress(runtime, client, addr, 'udp')
		else:
			ip = m.group(1)
			port = m.group(2)
			## HPUX & Solaris do not know the PID yet using this method
			if (osType != 'Solaris' and osType != 'HPUX'):
				pid = int(m.group(3))
		if pid:
			pid = int(pid)

	## end parseUDPfromNetstat
	return (ip, port, pid)


def parseUDPfromSS(line, osType, client, runtime):
	"""UDP parsing via ss."""
	ip = None
	port = None
	pid = None
	m = None

	if (osType == 'Linux'):
		## Sample Linux netstat output
		## =============================================================
		## udp    UNCONN     0      0      127.0.0.1:323         *:*         users:(("chronyd",pid=805,fd=1))
		## udp    UNCONN     0      0      192.168.122.1:53          *:*         users:(("dnsmasq",pid=1587,fd=5))
		## udp    UNCONN     0      0      *%virbr0:67          *:*         users:(("dnsmasq",pid=1587,fd=3))
		## udp    UNCONN     0      0         *:111         *:*         users:(("rpcbind",pid=705,fd=6))
		## =============================================================
		for ipMatch in IP_MATCH_LIST:
			searchString = concatenate('udp.\s+\S+\s+\d+\s+\d+\s+', ipMatch, ':(\d+)\s.*users:\((.*)\)\s*$')
			m = re.search(searchString, line, re.I)
			if m:
				break
	else:
		raise NotImplementedError('Network socket utility \'ss\' is not implemented on {}'.format(osType))

	## If we matched the OS specific line, get the ip/port/pid:
	if (m):
		ip = m.group(1)
		port = m.group(2)
		processInfo = m.group(3)
		runtime.logger.report(' parseUDPfromSS: ip {ip!r} port {port!r} processInfo {processInfo!r}', ip=ip, port=port, processInfo=processInfo)
		## Now parse the process info for the pid:  ("rpcbind",pid=705,fd=6)
		m2 = re.search('\([^,]+,pid=(\d+),', m.group(3))
		pid = int(m2.group(1))

	## end parseUDPfromSS
	return (ip, port, pid)


def parseTCPlistenerFromNetstat(line, osType, client, runtime):
	"""TCP Listener parsing via netstat and other OS specific utilities."""
	ip = None
	port = None
	pid = None
	m = None
	if (osType == 'Windows'):
		## Sample Windows netstat output
		## ============================================================
		## Proto  Local Address        Foreign Address    State           PID
		## TCP    0.0.0.0:135          0.0.0.0:0          LISTENING       408
		## TCP    127.0.0.1:1068       0.0.0.0:0          LISTENING       3888
		## TCP    192.168.1.105:139    0.0.0.0:0          LISTENING       4
		## TCP    [fe80::cc26:d842:5816:7171%10]:53  [::]:0   LISTENING   1768
		## TCP    [::1]:4065           [::]:0             LISTENING       1884
		## ============================================================
		for ipMatch in IP_MATCH_LIST:
			## Windows throws square brackets around IPv6 addresses
			searchString = concatenate('TCP\s+(?:\[)*', ipMatch, '(?:\])*:(\d+)\s.*:.*LISTENING\s+(\d+)')
			m = re.search(searchString, line, re.I)
			if m:
				break

	elif (osType == 'Linux'):
		## Sample Linux netstat output
		## ===================================================================
		## tcp    0   0 0.0.0.0:6000   0.0.0.0:*  LISTEN   -
		## tcp    0   0 0.0.0.0:22     0.0.0.0:*  LISTEN   1872/sshd
		## tcp    0   0 127.0.0.1:25   0.0.0.0:*  LISTEN   1962/sendmail: acce
		## tcp    0   0 ::ffff:127.0.0.1:8061   :::*  LISTEN  3125/java
		## tcp    0   0 :::50079       :::*       LISTEN   3125/java
		## tcp6   0   0 :::111         :::*       LISTEN      1/systemd'
		## ===================================================================
		for ipMatch in IP_MATCH_LIST:
			searchString = concatenate('TCP(?:\d)*\s+\d+\s+\d+\s+', ipMatch, ':(\d+)\s.*:.*LISTEN\s+(\d+)')
			m = re.search(searchString, line, re.I)
			if m:
				break

	elif (osType == 'AIX'):
		## This option requires sudo permissions for SOCKINFO and KDB.
		## Sample AIX netstat output
		## ===================================================================
		## f1000600036b2b98 tcp4    0   0  *.22               *.*       LISTEN
		## f10006000183cb98 tcp4    0   0  *.135              *.*       LISTEN
		## f1000600039e5b98 tcp4    0   0  10.2.4.25.60301    *.*       LISTEN
		## f100060003564b98 tcp4    0   0  10.2.4.26.25       *.*       LISTEN
		## ===================================================================
		for ipMatch in IP_MATCH_LIST:
			searchString = concatenate('(\S+)\s+tcp\S*\s+\d+\s+\d+\s+', ipMatch, '\.(\d+)\s.*\..*LISTEN')
			m = re.search(searchString, line, re.I)
			if m:
				break

	elif (osType == 'HPUX'):
		## This option requires sudo premission for PFILES, available after 11i
		## Sample HP-UX netstat output
		## ===================================================================
		## tcp        0      0  *.22                   *.*              LISTEN
		## tcp        0      0  127.0.0.1.49156        *.*              LISTEN
		## tcp        0      0  127.0.0.1.49153        *.*              LISTEN
		## ===================================================================
		for ipMatch in IP_MATCH_LIST:
			searchString = concatenate('tcp\s+\d+\s+\d+\s+', ipMatch, '\.(\d+)\s.*\..*LISTEN')
			m = re.search(searchString, line, re.I)
			if m:
				break

	elif (osType == 'Solaris'):
		## This option requires sudo premission for PFILES, available by default
		## Sample Solaris netstat output
		## ===================================================================
		##       *.29602         *.*              0      0 49152      0 LISTEN
		##       *.29807         *.*              0      0 49152      0 LISTEN
		## 127.0.0.1.32782       *.*              0      0 49152      0 LISTEN
		##       *.32785         *.*              0      0 49152      0 LISTEN
		## ===================================================================
		for ipMatch in IP_MATCH_LIST:
			searchString = concatenate('\s*', ipMatch, '\.(\d+)\s.*\..*\d+\s+\d+\s+\d+\s+\d+\s+LISTEN')
			m = re.search(searchString, line, re.I)
			if m:
				break

	## If we matched the OS specific line, get the ip/port/pid:
	if (m):
		## Need special parsing for AIX to get PID from the socket
		if (osType == 'AIX'):
			addr = m.group(1)
			ip = m.group(2)
			port = m.group(3)
			#pid = getAIXpIDfromAddress(runtime, client, addr, 'tcp')
		else:
			ip = m.group(1)
			port = m.group(2)
			## HPUX & Solaris do not know the PID yet using this method
			if (osType != 'Solaris' and osType != 'HPUX'):
				pid = int(m.group(3))
		if pid:
			pid = int(pid)

	## end parseTCPlistenerFromNetstat
	return (ip, port, pid)


def parseTCPlistenerFromSS(line, osType, client, runtime):
	"""TCP Listener parsing via ss."""
	ip = None
	port = None
	pid = None
	m = None

	if (osType == 'Linux'):
		## Sample Linux ss output
		## =============================================================
		## tcp    LISTEN     0      128       *:111         *:*         users:(("rpcbind",pid=705,fd=8))
		## tcp    LISTEN     0      5      192.168.122.1:53          *:*         users:(("dnsmasq",pid=1587,fd=6))
		## tcp    LISTEN     0      128       *:22          *:*         users:(("sshd",pid=1160,fd=3))
		## tcp    LISTEN     0      128    127.0.0.1:631         *:*         users:(("cupsd",pid=1164,fd=12))
		## tcp    LISTEN     0      128      :::111        :::*         users:(("rpcbind",pid=705,fd=11))
		## tcp    LISTEN     0      128      :::22         :::*         users:(("sshd",pid=1160,fd=4))
		## tcp    LISTEN     0      128     ::1:631        :::*         users:(("cupsd",pid=1164,fd=11))
		## ===== older version output doesn't have 'tcp' at start ======
		## LISTEN     0      100        ::ffff:127.0.0.1:8080                    :::*      users:(("Jboss",29085,880))
		## LISTEN     0      50       ::ffff:132.120.250.106:47666                   :::*      users:(("hpbsm_RTSM",28260,883))
		## LISTEN     0      50                      ::1:31155                   :::*      users:(("oacore",18399,84))
		## LISTEN     0      128                      :::44723                   :::*      users:(("rpc.statd",1844,10))
		## =============================================================
		for ipMatch in IP_MATCH_LIST:
			#searchString = concatenate('tcp.\s+\S+\s+\d+\s+\d+\s+', ipMatch, ':(\d+)\s.*users:\((.*)\)\s*$')
			searchString = concatenate('LISTEN\s+\d+\s+\d+\s+', ipMatch, ':(\d+)\s.*users:\((.*)\)\s*$')
			m = re.search(searchString, line, re.I)
			if m:
				break
	else:
		raise NotImplementedError('Network socket utility \'ss\' is not implemented on {}'.format(osType))

	## If we matched the OS specific line, get the ip/port/pid:
	if (m):
		ip = m.group(1)
		port = m.group(2)
		pid = None
		## Now parse the process info for the pid:  ("rpcbind",pid=705,fd=6)
		m3 = re.search('\("([^"]+)",pid=(\d+),fd=(\d+)\)', m.group(3))
		m4 = re.search('\("([^"]+)",(\d+),(\d+)\)', m.group(3))
		if m3:
			procName = m3.group(1)
			pid = int(m3.group(2))
			fd = m3.group(3)
		elif m4:
			procName = m4.group(1)
			pid = int(m4.group(2))
			fd = m4.group(3)

	## end parseTCPlistenerFromSS
	return (ip, port, pid)


def parseListenerLine(runtime, client, listenerType, osType, networkUtility, line):
	"""TCP/UDP Listener parsing using different distributed methods."""
	ip = None
	port = None
	pid = None
	try:
		if line and line != '':
			if (listenerType.lower() == 'udp'):
				if networkUtility == 'lsof':
					## Use the open source LSOF utility
					(ip, port, pid) = parseUDPfromLSOF(line)
				elif networkUtility == 'netstat':
					## Need to use the OS specific utilities
					(ip, port, pid) = parseUDPfromNetstat(line, osType, client, runtime)
				elif networkUtility == 'ss':
					(ip, port, pid) = parseUDPfromSS(line, osType, client, runtime)

			elif (listenerType.lower() == 'tcp'):
				if networkUtility == 'lsof':
					## Use the open source LSOF utility
					(ip, port, pid) = parseTCPlistenerFromLSOF(line)
				elif networkUtility == 'netstat':
					## Need to use the OS specific utilities
					(ip, port, pid) = parseTCPlistenerFromNetstat(line, osType, client, runtime)
				elif networkUtility == 'ss':
					(ip, port, pid) = parseTCPlistenerFromSS(line, osType, client, runtime)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in parseListenerLine: {stacktrace!r}', stacktrace=stacktrace)

	## end parseListenerLine
	return (ip, port, pid)


def addListenerEntry(runtime, listenerList, localIp, serverPort, pid, actualIpString):
	"""Add an IP/Port/PID onto the Listener list."""
	if ((localIp, serverPort, pid) not in listenerList):
		listenerList.append((localIp, serverPort, pid))
		runtime.logger.report(' ------> Creating service address associated with {actualIpString!r}: {localIp!r}:{serverPort!r}', actualIpString=actualIpString, localIp=localIp, serverPort=str(serverPort))
	else:
		runtime.logger.report(' ------> Already mapped this for {actualIpString!r}: {localIp!r}:{serverPort!r} {pid!r}', actualIpString=actualIpString, localIp=localIp, serverPort=serverPort, pid=pid)


def discoverListenerPorts(runtime, client, outputString, osType, localIpList, listenerList, networkUtility, listenerType, relatedServerIP, isRemote=False):
	"""Discover Listener ports (TCP or UDP)."""
	## Report the risk if user selected to discover via PFILES
	#warnAboutUsingPfiles(osType, networkUtility)
	networkCreateLocalEndpoints = runtime.endpoint.get('data').get('parameters').get('networkCreateLocalEndpoints', False)
	networkResolveUnspecifiedEndpoints = runtime.endpoint.get('data').get('parameters').get('networkResolveUnspecifiedEndpoints', False)
	networkCreateLocalEndpoints = runtime.endpoint.get('data').get('parameters').get('networkCreateLocalEndpoints', False)
	errorCount = 1  ## set to 1 to avoid zero division in the calculation below
	outputLines = verifyOutputLines(runtime, outputString)
	if outputLines is None:
		return

	## Parse UDP or TCP Listener output
	for line in outputLines:
		try:
			line = line.strip()
			runtime.logger.report(' {listenerLine!r}', listenerLine=line)
			serverIP = None
			serverPort = None
			myPID = None
			(serverIP, serverPort, myPID) = parseListenerLine(runtime, client, listenerType, osType, networkUtility, line)
			runtime.logger.report(' {serverIP!r} {serverPort!r} {PID!r}', serverIP=serverIP, serverPort=serverPort, PID=myPID)

			if (serverPort and serverIP):

				## If local address, should we track the endpoints?
				if (serverIP in ['127.0.0.1', '::1', '0:0:0:0:0:0:0:1']):
					if networkCreateLocalEndpoints:
						listenerList.append((serverIP, serverPort, myPID))
					continue

				## If unspecified address, should we resolve to IP destinations?
				if (networkResolveUnspecifiedEndpoints):
					if (serverIP in ['0.0.0.0', '*']):
						## Associate all current IPv4 addresses with this port
						for ipEntry in localIpList:
							(localIp, isIpv4) = ipEntry
							if isIpv4:
								addListenerEntry(runtime, listenerList, localIp, serverPort, myPID, serverIP)
						## Need to add all IPv6 as well, if the IP is '*'
						if serverIP != '*':
							continue
					if (serverIP in ['::', '0:0:0:0:0:0:0:0', '*']):
						## Associate all current IPv6 addresses with this port
						for ipEntry in localIpList:
							(localIp, isIpv4) = ipEntry
							## Add both IPv4 and IPv6, since IPv4 maps to IPv6
							## but not visa versa...
							addListenerEntry(runtime, listenerList, localIp, serverPort, myPID, serverIP)
						continue

				## Add onto the Listener list to return
				listenerList.append((serverIP, serverPort, myPID))
			else:
				runtime.logger.report('Couldn\'t parse {listenerType!r} {line!r}', listenerType=listenerType, line=line)
				errorCount = errorCount + 1
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception found in function discoverListenerPorts: {exception!r}', exception=stacktrace)

	## If most the lines returned with empty values for proc; report to the GUI
	if (errorCount > 2 and errorCount / (len(outputLines)) > .75):
		runtime.logger.info(' Number of outputLines: {listenerPortCount!r} and number of errors: {listenerPortErrors!r}', listenerPortCount=str(len(outputLines)), listenerPortErrors=str(errorCount))
		runtime.logger.info(' Gathering network listener information retuned partial data, which suggests limited access. Should this be run with elevated rights?')
		## Don't just warn; abort the run
		raise EnvironmentError('Gathering network listener information retuned partial data, which suggests limited access. Should this be run with elevated rights?')

	## end discoverListenerPorts
	return


def parseEstablishedFromSS(line):
	"""TCP Established parsing via the SS utility."""
	localIP = None
	localPort = None
	remoteIP = None
	remotePort = None
	pid = None
	## Sample SS output
	## ========================================================================
	##
	## ESTAB      0      0        ::ffff:10.33.68.197:42582   ::ffff:10.33.68.197:5445   users:(("hpbsm_opr-backe",30488,495))
	## ESTAB      0      0        ::ffff:10.33.68.197:42686   ::ffff:10.33.68.197:5445   users:(("hpbsm_marble_su",29909,542))
	## ESTAB      0      0        ::ffff:10.33.68.197:42220   ::ffff:10.241.171.290:1521   users:(("hpbsm_marble_su",29909,534))
	## ESTAB      0      0                 127.0.0.1:65102            127.0.0.1:45093  users:(("nbdisco",3347,9))
	## ESTAB      0      0                       ::1:36700                  ::1:41757  users:(("ovbbccb",18194,19))
	## ========================================================================
	for ipMatch1 in IP_MATCH_LIST:
		## Match the local IP, to one of the many formats with IPv4 and IPv6
		searchString = concatenate('ESTAB\s+\d+\s+\d+\s+', ipMatch1, ':(\d+)\s+(\S+):(\d+)\s+users:\((.+)\)\s*$')
		m1 = re.search(searchString, line, re.I)
		if m1:
			for ipMatch2 in IP_MATCH_LIST:
				## Now match the remote IP to one of the many formats
				searchString = ipMatch2
				m2 = re.search(searchString, m1.group(3), re.I)
				if m2:
					localIP = m1.group(1)
					localPort = m1.group(2)
					remoteIP = m2.group(1)
					remotePort = m1.group(4)
					## TODO: Need to support a list of processes, e.g.:
					## users:(("httpd",pid=10522,fd=4),("httpd",pid=10521,fd=4),("httpd",pid=10520,fd=4))
					## users:(("Jboss",29085,792))
					m3 = re.search('\("([^"]+)",pid=(\d+),fd=(\d+)\)', m1.group(5))
					m4 = re.search('\("([^"]+)",(\d+),(\d+)\)', m1.group(5))
					if m3:
						procName = m3.group(1)
						pid = int(m3.group(2))
						fd = m3.group(3)
					elif m4:
						procName = m4.group(1)
						pid = int(m4.group(2))
						fd = m4.group(3)
					break
			break

	## end parseEstablishedFromSS
	return (localIP, localPort, remoteIP, remotePort, pid)


def parseEstablishedFromLSOF(line):
	"""TCP Established parsing via the open source LSOF utility."""
	localIP = None
	localPort = None
	remoteIP = None
	remotePort = None
	pid = None
	## Sample LSOF output
	## ========================================================================
	## cimserver    2398     root    6u  IPv4 0xe0000001776f7700  0t507172  TCP 127.0.0.1:49155->127.0.0.1:49156 (ESTABLISHED)
	## kcmond       2856     root   11u  IPv6 0xe000000176319400    0t1219  TCP [::1]:49243->[::1]:49237 (ESTABLISHED)
	## disk_em      2916     root   13u  IPv6 0xe000000176c80380   0t40038  TCP [::1]:49362->[::1]:49237 (ESTABLISHED)
	## java       413862 crmphai2  183u  IPv6 0xf100020002118b98       0t0  TCP 10.41.70.59:39444->10.41.71.59:60019 (ESTABLISHED)
	## documentu  843976  dmadmin   12u  IPv4 0xf100020001f8e398 0t6233273  TCP 10.41.70.59:44050->10.33.68.197:1551 (ESTABLISHED)
	## ========================================================================
	for ipMatch1 in IP_MATCH_LIST:
		## Match the local IP, to one of the many formats with IPv4 and IPv6
		searchString = concatenate('\S+\s+(\d+)\s.*TCP\s+(?:\[)*', ipMatch1, '(?:\])*:(\d+)\s*[-][>]\s*(\S+):(\d+)\s*\(E')
		m1 = re.search(searchString, line, re.I)
		if m1:
			for ipMatch2 in IP_MATCH_LIST:
				## Now match the remote IP to one of the many formats
				searchString = concatenate('(?:\[)*', ipMatch2, '(?:\])*')
				m2 = re.search(searchString, m1.group(4), re.I)
				if m2:
					pid = int(m1.group(1))
					localIP = m1.group(2)
					localPort = m1.group(3)
					remoteIP = m2.group(1)
					remotePort = m1.group(5)
					break
			break

	## end parseEstablishedFromLSOF
	return (localIP, localPort, remoteIP, remotePort, pid)


def parseEstablishedFromNetstat(runtime, line, osType, client):
	"""TCP Established parsing via netstat and other OS specific utilities.

	Only Windows, Linux and AIX will ever pass through this function; Solaris
	and HP-UX will never go through this function. If you choose not to use
	LSOF, then then you are using PFILES on Solaris & HP-UX. And PFILES has a
	different function for parsing established connections.
	"""
	localIP = None
	localPort = None
	remoteIP = None
	remotePort = None
	pid = None
	m = None
	if (osType == 'Windows'):
		## Sample Windows netstat output
		## ===================================================================
		## TCP   127.0.0.1:2561        127.0.0.1:2562       ESTABLISHED   3388
		## TCP   127.0.0.1:3405        127.0.0.1:3404       ESTABLISHED   3388
		## TCP   192.168.1.105:1964    15.200.32.67:443     ESTABLISHED   1480
		## TCP   192.168.1.105:2521    15.200.32.51:443     ESTABLISHED   1480
		## TCP   192.168.1.105:4986    192.168.1.104:445    ESTABLISHED   4
		## ===================================================================
		for ipMatch in IP_MATCH_LIST:
			## Match the local IP, to one of the many formats with IPv4 and IPv6
			searchString = concatenate('TCP\s+(?:\[)*', ipMatch, '(?:\])*:(\d+)\s+(\S+):(\d+)\s+\S+\s+(\d+)')
			m = re.search(searchString, line, re.I)
			if m:
				break

	elif (osType == 'Linux'):
		## Sample Linux netstat output
		## ====================================================================
		## tcp  0  0     192.168.1.104:139       192.168.1.140:3561          ESTABLISHED 2456/smbd
		## tcp  0  0     192.168.1.104:445       192.168.1.105:4986          ESTABLISHED 4372/smbd
		## tcp  0  0     192.168.1.104:22        192.168.1.140:4454          ESTABLISHED 4398/sshd: myuser
		## tcp  0  11064 ::ffff:16.89.27.31:22   ::ffff:16.212.184.133:4020  ESTABLISHED
		## tcp  0  0     127.0.0.1:815           127.0.0.1:33119             ESTABLISHED 5727/scopeux
		## tcp6 0  0     ::1:37976               ::1:5432                    ESTABLISHED 14975/python3.6

		## ====================================================================
		for ipMatch in IP_MATCH_LIST:
			## Match the local IP, to one of the many formats with IPv4 and IPv6
			## NOTE: the case where you see "ESTABLISHED" without any subsequent
			## text will not match the regex. This is by design, no PID means
			## we can't associate the connection with a process
			searchString = concatenate('tcp(?:\d)*\s+\d+\s+\d+\s+(?:\[)*', ipMatch, '(?:\])*:(\d+)\s+(\S+):(\d+)\s+\S+\s+(\d+)')
			m = re.search(searchString, line, re.I)
			if m:
				break

	elif (osType == 'AIX'):
		## This option requires sudo permissions for SOCKINFO and KDB.
		## Sample AIX netstat output
		## ====================================================================
		## f100060003bb9398 tcp4  0  0  10.2.4.25.22   10.2.4.25.3589     ESTABLISHED
		## f1000600035ec398 tcp4  0  0  10.2.4.25.383  10.2.34.210.58220  ESTABLISHED
		## f1000600035d2b98 tcp4  0  0  10.2.4.25.199  10.2.23.27.40898   ESTABLISHED
		## ====================================================================
		for ipMatch in IP_MATCH_LIST:
			## Match the local IP, to one of the many formats with IPv4 and IPv6
			searchString = concatenate('(\S+)\s+tcp\S*\s+\d+\s+\d+\s+(?:\[)*', ipMatch, '(?:\])*\.(\d+)\s+(\S+)\.(\d+)')
			m = re.search(searchString, line, re.I)
			if m:
				break

	## If we matched the OS specific line, get the ip/port/pid:
	if (m):
		## Need special parsing for AIX to get PID from the socket
		if (osType == 'AIX'):
			addr = m.group(1)
			localIP = m.group(2)
			localPort = m.group(3)
			remoteIP = m.group(4)
			remotePort = m.group(5)
			#pid = getAIXpIDfromAddress(runtime, client, addr, 'tcp')
		else:
			localIP = m.group(1)
			localPort = m.group(2)
			remoteIP = m.group(3)
			remotePort = m.group(4)
			pid = m.group(5)
		if pid:
			pid = int(pid)

		## Clean up and validate the remote IP
		for ipMatch in IP_MATCH_LIST:
			## Now match the remote IP to one of the many formats
			searchString = concatenate('(?:\[)*', ipMatch, '(?:\])*')
			m = re.search(searchString, remoteIP, re.I)
			if m:
				remoteIP = m.group(1)
				break

	## end parseEstablishedFromNetstat
	return (localIP, localPort, remoteIP, remotePort, pid)


def parseEstablishedLine(runtime, client, osType, networkUtility, line):
	"""TCP Established parsing using different distributed methods."""
	localIP = None
	localPort = None
	remoteIP = None
	remotePort = None
	pid = None
	try:
		## If using 'ss', the search string is 'ESTAB' as a short word
		#if (line and re.search('[Ee][Ss][Tt][Aa][Bb][Ll][Ii][Ss][Hh]', line)):
		if (line and re.search('[Ee][Ss][Tt][Aa][Bb]', line)):
			if networkUtility == 'lsof':
				## This method should be used for both HP-UX and Solaris
				(localIP, localPort, remoteIP, remotePort, pid) = parseEstablishedFromLSOF(line)
			elif networkUtility == 'netstat':
				## Need to use the OS specific utilities
				(localIP, localPort, remoteIP, remotePort, pid) = parseEstablishedFromNetstat(runtime, line, osType, client)
			elif networkUtility == 'ss':
				(localIP, localPort, remoteIP, remotePort, pid) = parseEstablishedFromSS(line)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception found in function parseEstablishedLine: {stacktrace!r}', stacktrace=stacktrace)

	## end parseEstablishedLine
	return (localIP, localPort, remoteIP, remotePort, pid)


def discoverEstablishedConnections(runtime, client, outputString, osType, localIpList, tcpEstablishedList, networkUtility, hostIP):
	"""Discover established connections (TCP or UDP) on local side."""
	networkCreateLocalEndpoints = runtime.endpoint.get('data').get('parameters').get('networkCreateLocalEndpoints', False)
	networkResolveUnspecifiedEndpoints = runtime.endpoint.get('data').get('parameters').get('networkResolveUnspecifiedEndpoints', False)
	errorCount = 1  ## set to 1 to avoid zero division in the calculation below
	outputLines = verifyOutputLines(runtime, outputString)
	if outputLines is None:
		return

	## Parse Established output
	for line in outputLines:
		try:
			line = line.strip()
			if line == '':
				continue
			localIP = None
			localPort = None
			remoteIP = None
			remotePort = None
			pid = None
			(localIP, localPort, remoteIP, remotePort, pid) = parseEstablishedLine(runtime, client, osType, networkUtility, line)
			if pid is None:
				runtime.logger.report(' skipping this established connection, unable to extract PID:  {line!r}', line=line)
				runtime.logger.report('                                       unable to extract PID:  {localIP!r}, {localPort!r}, {remoteIP!r}, {remotePort!r}, {pid!r}', localIP=localIP, localPort=localPort, remoteIP=remoteIP, remotePort=remotePort, pid=pid)
				continue
			if (localIP and localPort and remoteIP and remotePort and pid):

				## If local address, should we track the endpoints?
				localIPs = ['127.0.0.1', '::1', '0:0:0:0:0:0:0:1']
				if ((localIP in localIPs or remoteIP in localIPs) and not networkCreateLocalEndpoints):
					continue

				## If unspecified address, should we resolve to IP destinations?
				if (networkResolveUnspecifiedEndpoints):
					## I'll leave this in for now, but I don't believe the local
					## unspecified addresses are found on ESTABLISHED lines; I
					## think it should be an actual address unless ran locally,
					## in which case it would be on the 127.0.0.1 or ::1 side.
					if (localIP in ['0.0.0.0', '*']):
						for ipEntry in localIpList:
							(thisIp, isIpv4) = ipEntry
							if isIpv4:
								## Add onto the Established list to return
								tcpEstablishedList.append((thisIp, localPort, remoteIP, remotePort, pid))
								runtime.logger.report('-------> Creating service address associated with {localIP!r}: {thisIp!r}:{localPort!r}', localIP=localIP, thisIp=thisIp, localPort=str(localPort))
						## Need to add all IPv6 as well, if the IP is '*'
						if localIP != '*':
							continue
					if (localIP in ['::', '0:0:0:0:0:0:0:0', '*']):
						for ipEntry in localIpList:
							(thisIp, isIpv4) = ipEntry
							## Add both IPv4 and IPv6, since IPv4 maps to IPv6
							## but not visa versa...
							tcpEstablishedList.append((thisIp, localPort, remoteIP, remotePort, pid))
							runtime.logger.report('-------> Creating service address associated with {localIP!r}: {thisIp!r}:{localPort!r}', localIP=localIP, thisIp=thisIp, localPort=str(localPort))
						continue

				## Add onto the Established list to return
				tcpEstablishedList.append((localIP, localPort, remoteIP, remotePort, pid))
			else:
				runtime.logger.report(' Couldn\'t parse ESTABLISHED line: {line!r}', line=line)
				errorCount = errorCount + 1
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in discoverEstablishedConnections: {stacktrace!r}', stacktrace=stacktrace)

	## If most the lines returned with empty values for proc; report to the GUI
	if (errorCount > 2 and errorCount / (len(outputLines)) > .75):
		runtime.logger.info(' Number of outputLines: {establishedLineCount!r} and number of errors: {establishedLineErrors!r}', establishedLineCount=str(len(outputLines)), establishedLineErrors=str(errorCount))
		runtime.logger.info(' Gathering established network connections returned partial data, which suggests limited access. Was this run with elevated rights?')
		## Don't just warn; abort the run
		raise EnvironmentError('Gathering established network connections returned partial data, which suggests limited access. Was this run with elevated rights?')

	## Memory management for large queries
	outputString = None

	## Sort the list of connections in place (since we're using a mutable output
	## variable being passed through the functions), based on remote IP address
	#with suppress(Exception):
	tcpEstablishedList.sort(key=lambda x: x[2])

	## end discoverEstablishedConnections
	return


def translateSpecialIpAddress(thisIP):
	"""Merge IPv4 and IPv6 special addresses for common code paths."""
	## Unspecified Addresses, set to '0.0.0.0'
	if (thisIP == '::' or thisIP == '*' or thisIP == '0:0:0:0:0:0:0:0'):
		thisIP = '0.0.0.0'
	## Local Addresses, set to '127.0.0.1'
	elif (thisIP == '::1' or thisIP == '0:0:0:0:0:0:0:1'):
		thisIP = '127.0.0.1'

	## end translateSpecialIpAddress
	return thisIP


def getThisIp(runtime, trackedIPs, thisIP):
	"""Reduce the number of times we lookup an IP and add to the results."""
	if thisIP in trackedIPs:
		return trackedIPs.get(thisIP)
	## Validate the IP first; if not valid, return None
	ipId = None
	try:
		if (thisIP in ['127.0.0.1', '::1', '0:0:0:0:0:0:0:1']):
			## Override the realm setting for two reasons: we do not want these
			## IPs in endpoint query results, and we want to track one per node
			ipId, exists = runtime.results.addIp(address=thisIP, realm=runtime.endpoint.get('data').get('FQDN', 'NA'))
		else:
			realm = runtime.jobMetaData.get('realm', 'NA')
			ipId, exists = runtime.results.addIp(address=thisIP, realm=realm)
	except ValueError:
		runtime.logger.report('ValueError in getThisIp: {valueError!r}', valueError=str(sys.exc_info()[1]))
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in getThisIp: {stacktrace!r}', stacktrace=stacktrace)
	trackedIPs[thisIP] = ipId

	## end getThisIp
	return ipId


def addTcpPort(runtime, portType, serverIP, serverPort, trackedIPs, clientIP=None, isLocal=False, avoidDuplicates=True):
	"""Get a handle on the corresponding IP and link to ports in use."""
	serverIpId = getThisIp(runtime, trackedIPs, serverIP)
	tcpIpPortId = None
	tcpIpPortClientId = None
	if serverIpId:
		isTcp = False
		if portType is not None and portType.lower() == 'tcp':
			isTcp = True

		## Check if it was added to the results already; using a custom version
		## of the more generic utilities.addObjectIfNotExists(), because I plan
		## to remove this section after building this into resultProcessing. My
		## plan is to do this on the server side to remove the requirement from
		## the script developer.
		if avoidDuplicates:
			for thisObject in runtime.results.getObjects():
				if thisObject.get('class_name') != 'TcpIpPort':
					continue
				thisData = thisObject.get('data', {})
				if (thisData.get('name') == serverPort and
					thisData.get('ip') == serverIP and
					thisData.get('is_tcp') == isTcp):
					tcpIpPortId = thisObject.get('identifier')
		if tcpIpPortId is None:
			tcpIpPortId, exists = runtime.results.addObject('TcpIpPort', name=serverPort, port=int(serverPort), ip=serverIP, port_type=portType, is_tcp=isTcp)
			## Create server-side port
			runtime.results.addLink('Enclosed', serverIpId, tcpIpPortId)

		## TODO: Probably want to use the is_local type lookup on ipaddress,
		## instead of trying to string parse for local IPv6 variants
		if clientIP:
			if clientIP in ['127.0.0.1', '::1', '0:0:0:0:0:0:0:1']:
				networkCreateLocalEndpoints = runtime.endpoint.get('data').get('parameters').get('networkCreateLocalEndpoints', False)
				if not networkCreateLocalEndpoints:
					return tcpIpPortId
			## Create a ServerClient link between the server port and the client IP
			clientIpId = getThisIp(runtime, trackedIPs, clientIP)
			if clientIpId:
				if avoidDuplicates:
					## This section isn't granular enough for multiple clients
					## from different IPs connecting into the same listener; we
					## need to track 3 unique items: serverPort, serverIP *and*
					## clientIP... but this leaves out clientIP, incorrectly
					## merging remote endpoints. Best for the calling code to
					## control this, in a separate memory structure like a dict.
					## Look at shell_app_components_vocal.py for an example in
					## createEstablishedRemotePort(), where all 3 data points
					## are used in the lookup in data.clientPorts via this key:
					##   '{}:{}:{}'.format(serverIp, serverPort, clientIp)
					## Set avoidDuplicates to False when controlled elsewhere.
					for thisObject in runtime.results.getObjects():
						if thisObject.get('class_name') != 'TcpIpPortClient':
							continue
						thisData = thisObject.get('data', {})
						if (thisData.get('name') == serverPort and
							thisData.get('ip') == serverIP and
							thisData.get('is_tcp') == isTcp):
							tcpIpPortClientId = thisObject.get('identifier')
				if tcpIpPortClientId is None:
					## Client-side port (note: we do not track the ephemeral
					## port numbers on the client; the server IP/port is simply
					## mapped under the client IP, so services hosted by shared
					## servers are mapped correctly/independently to each client
					## Also, no reason to checkExisting, since we do that here.
					tcpIpPortClientId, exists = runtime.results.addObject('TcpIpPortClient', name=serverPort, port=int(serverPort), ip=serverIP, port_type=portType, is_tcp=isTcp, checkExisting=False)
					runtime.results.addLink('Enclosed', clientIpId, tcpIpPortClientId)
					if serverIP != clientIP and not isLocal:
						## Don't use this if it's on the same server
						runtime.results.addLink('ServerClient', serverIpId, tcpIpPortClientId)

	## end addTcpPort
	return (tcpIpPortId, tcpIpPortClientId)


def createNetworkObjects(runtime, osType, udpListenerList, tcpListenerList, tcpEstablishedList, localIpList, trackedIPs):
	"""Add desired level of objects (TCP/UDP ports, IPs, links) into results."""
	runtime.logger.report('Creating requested objects for {osType!r} Networking', osType=osType)
	networkCreateUdpListeners = runtime.endpoint.get('data').get('parameters').get('networkCreateUdpListeners')
	networkCreateTcpListeners = runtime.endpoint.get('data').get('parameters').get('networkCreateTcpListeners')
	networkCreateTcpEstablished = runtime.endpoint.get('data').get('parameters').get('networkCreateTcpEstablished')

	for udpEntry in udpListenerList:
		(serverIP, serverPort, pid) = udpEntry
		runtime.logger.report('  UDP listener line: {serverIP!r}:{serverPort!r}, PID: {pid!r}', serverIP=serverIP, serverPort=serverPort, pid=pid)
		if (networkCreateUdpListeners):
			addTcpPort(runtime, 'udp', serverIP, serverPort, trackedIPs)

	for tcpEntry in tcpListenerList:
		(serverIP, serverPort, pid) = tcpEntry
		runtime.logger.report('  TCP listener line: {serverIP!r}:{serverPort!r}, PID: {pid!r}', serverIP=serverIP, serverPort=serverPort, pid=pid)
		if (networkCreateTcpListeners):
			addTcpPort(runtime, 'tcp', serverIP, serverPort, trackedIPs)

	for tcpEntry in tcpEstablishedList:
		(localIP, localPort, remoteIP, remotePort, pid) = tcpEntry
		runtime.logger.report('  TCP established line: {localIP!r}:{localPort!r}  {remoteIP!r}:{remotePort!r}, PID: {pid!r}', localIP=localIP, localPort=localPort, remoteIP=remoteIP, remotePort=remotePort, pid=pid)

		if (networkCreateTcpEstablished):
			## Figure out which is the server side
			flipped = True
			for listenerList in [udpListenerList, tcpListenerList]:
				for entry in listenerList:
					(serverIP, serverPort, myPID) = entry
					if (serverIP == localIP and serverPort == localPort):
						## Local side is serving
						flipped = False
						break

			## Local side is serving
			if not flipped:
				addTcpPort(runtime, 'tcp', localIP, localPort, trackedIPs, remoteIP)
			## Remote side is serving
			else:
				addTcpPort(runtime, 'tcp', remoteIP, remotePort, trackedIPs, localIP)

	## end createNetworkObjects
	return


###############################################################################
############################  END GENERAL SECTION  ############################
###############################################################################


###############################################################################
###########################  BEGIN WINDOWS SECTION  ###########################
###############################################################################

def windowsGetNetworking(runtime, client, osType, hostIP, networkUtility='netstat', networkConnectionsString=None):
	"""Get Windows Network Data."""
	if networkConnectionsString is None:
		## Gather full netstat output
		try:
			runtime.logger.report('Gathering netstat information on: {hostIP!r}', hostIP=hostIP)
			netstatCmd = updateCommand(runtime, 'netstat -aon')
			(networkConnectionsString, stdError, hitProblem) = client.run(netstatCmd, 30)
			runtime.logger.report('network stack returned: {networkConnectionsString!r}', networkConnectionsString=networkConnectionsString)
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in windowsGetNetworking querying netstat information: {stacktrace!r}', stacktrace=stacktrace)

	## end windowsGetNetworking
	return networkConnectionsString


def windowsParseNetworking(runtime, client, osType, hostIP, localIpList, trackedIPs, networkUtility, udpListenerList, tcpListenerList, tcpEstablishedList, networkConnectionsString):
	"""Parse Windows Network Data."""
	## Use NETSTAT output to create an array of UDP ports
	try:
		runtime.logger.report('Parsing UDP Listener information on {hostIP!r}', hostIP=hostIP)
		outputString = grep(networkConnectionsString , 'udp')
		runtime.logger.report(' UDP listeners: {outputString!r}', outputString=outputString)
		discoverListenerPorts(runtime, client, outputString, osType, localIpList, udpListenerList, networkUtility, 'UDP', hostIP)
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in windowsParseNetworking querying UDP Listeners: {stacktrace!r}', stacktrace=stacktrace)
		## Don't return yet; most the work can be done without UDP

	## Use NETSTAT output to create an array of TCP LISTENING ports
	try:
		runtime.logger.report('Parsing TCP Listener information on {hostIP!r}', hostIP=hostIP)
		outputString = grep(networkConnectionsString , 'listen')
		runtime.logger.report(' TCP listeners: {outputString!r}', outputString=outputString)
		discoverListenerPorts(runtime, client, outputString, osType, localIpList, tcpListenerList, networkUtility, 'TCP', hostIP)
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in windowsParseNetworking querying TCP Listeners: {stacktrace!r}', stacktrace=stacktrace)
		return

	## Use NETSTAT output to create an array of TCP ESTABLISHED ports
	try:
		runtime.logger.report('Parsing TCP Connections on {hostIP!r}', hostIP=hostIP)
		outputString = grep(networkConnectionsString , 'established')
		runtime.logger.report(' TCP connections: {outputString!r}', outputString=outputString)
		networkConnectionsString = None
		discoverEstablishedConnections(runtime, client, outputString, osType, localIpList, tcpEstablishedList, networkUtility, hostIP)
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in windowsParseNetworking querying TCP connections: {stacktrace!r}', stacktrace=stacktrace)

	## end windowsParseNetworking
	return

###############################################################################
############################  END WINDOWS SECTION  ############################
###############################################################################


###############################################################################
############################  BEGIN LINUX SECTION  ############################
###############################################################################

def linuxGetNetworking(runtime, client, osType, hostIP, networkUtility, networkConnectionsString=None):
	"""Get Linux Network Data."""
	if networkConnectionsString is None:
		## Parameters vary between utility types, and may vary between OS types.
		## Specifically piping 'ss' output through the 'cat' utility in order to
		## strip TTY context so the trailing 'users:(("dnsmasq",pid=1587,fd=6))'
		## context does not appear on the next line (auto width) or in color.
		commandLines = {
			'netstat': 'netstat -anp',
			'lsof': 'lsof -nP -i',
			'ss': 'ss -nap | grep "LISTEN\|ESTAB" | cat'
		}
		##'ss': 'ss -nap | grep "tcp\|udp" | cat'
		command = commandLines.get(networkUtility)
		if command is None:
			raise NotImplementedError('Network socket utility {} is not implemented on Linux'.format(networkUtility))

		## Gather full network stack details
		try:
			runtime.logger.report('Gathering {networkUtility!r} information on: {hostIP!r}', networkUtility=networkUtility, hostIP=hostIP)
			command = updateCommand(runtime, command)
			(networkConnectionsString, stdError, hitProblem) = client.run(command, 30)
			runtime.logger.report('network stack returned: {networkConnectionsString!r}', networkConnectionsString=networkConnectionsString)
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in linuxGetNetworking using {networkUtility!r} information: {stacktrace!r}', networkUtility=networkUtility, stacktrace=stacktrace)

	## end linuxGetNetworking
	return networkConnectionsString


def linuxParseNetworking(runtime, client, osType, hostIP, localIpList, trackedIPs, networkUtility, udpListenerList, tcpListenerList, tcpEstablishedList, networkConnectionsString):
	"""Parse Linux Network Data."""
	## Create an array of UDP ports
	try:
		runtime.logger.report('Parsing UDP Listener information on {hostIP!r}', hostIP=hostIP)
		outputString = grep(networkConnectionsString , 'udp')
		runtime.logger.report(' UDP listeners: {outputString!r}', outputString=outputString)
		discoverListenerPorts(runtime, client, outputString, osType, localIpList, udpListenerList, networkUtility, 'UDP', hostIP)
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in linuxParseNetworking querying UDP Listeners: {stacktrace!r}', stacktrace=stacktrace)
		## Don't return yet; most the work can be done without UDP

	## Create an array of TCP LISTENING ports
	try:
		runtime.logger.report('Parsing TCP Listener information on {hostIP!r}', hostIP=hostIP)
		#outputString = grep(networkConnectionsString , 'tcp.*listen')
		outputString = grep(networkConnectionsString , 'listen')
		runtime.logger.report(' TCP listeners: {outputString!r}', outputString=outputString)
		discoverListenerPorts(runtime, client, outputString, osType, localIpList, tcpListenerList, networkUtility, 'TCP', hostIP)
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in linuxParseNetworking querying TCP Listeners: {stacktrace!r}', stacktrace=stacktrace)
		return

	## Create an array of TCP ESTABLISHED ports
	try:
		runtime.logger.report('Parsing TCP Connections on {hostIP!r}', hostIP=hostIP)
		#outputString = grep(networkConnectionsString , 'tcp.*estab')
		outputString = grep(networkConnectionsString , 'estab')
		runtime.logger.report(' TCP connections: {outputString!r}', outputString=outputString)
		networkConnectionsString = None
		discoverEstablishedConnections(runtime, client, outputString, osType, localIpList, tcpEstablishedList, networkUtility, hostIP)
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in linuxParseNetworking querying TCP connections: {stacktrace!r}', stacktrace=stacktrace)

	## end linuxParseNetworking
	return

###############################################################################
#############################  END LINUX SECTION  #############################
###############################################################################
