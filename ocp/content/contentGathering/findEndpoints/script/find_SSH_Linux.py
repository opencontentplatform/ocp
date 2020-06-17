"""SSH detection library for Linux.

Functions:
  queryLinux : entry point; run queries against a Linux endpoint
  parsePreviousCmdOutput : query and parse uname -a output
  queryRelease : query for standard Linux distro and release info
  querySpecialRelease : query for special Linux distro and release info
  parseReleaseFromDistro : parse release out of the distribution string
  parsePlatformFromDistro : parse platform out of the distribution string
  queryBios : query and parse System attributes
  queryOsNameContext : query and parse name and domain attributes
  queryForIps : query and parse IP addresses
  createObjects : create objects and links in the results


Comments and background on OS name/domain uniqueness:
===========================================================================
Node uniqueness in OCP indends to combine the name and domain known by the
hosted domain. The reason is because Operating System instances that are
managed by a common platform (Active Directory or an LDAP variant), will be
unique in that platform. And the uniqueness there is based off name along
with the 'domain' or 'realm'. However, since a Linux server can technically
sit out on a network with a routable IP without being joined to management
software, this solution needs to be able to also leverage Name Services
(DNS/NIS/YP/WINS). The flexibility of UX management in the case of NS
configuration, presents a challenge here. What do I mean?

Locally, if /etc/hosts isn't setup with an FQDN and /etc/hostname wasn't
modified with a domain (which was never initially meant to hold a domain),
then utilities like hostname can return an empty domain. If a server has
just one IP address configured with multiple name entries, then suggesting
that one name entry is 'primary' over another one - means nothing from the
technology perspective. If a single IP had a DNS A record and several CNAME
records, you could discuss policies to use 'A' records over 'CNAME's... but
the technology doesn't care or observe one over another. And if that IP had
multiple A records in different domains, it might be a bad policy, but it's
not a problem for a DNS server. And then you have the resolution order from
/etc/nsswitch.conf, plus settings in /etc/hosts.conf along with those in
/etc/sysconfig/network for static IP vs DHCP... where does it end? Simply
with the understanding that IPs have far less to do with servers.

That was just discussing one IP on a server and only DNS. What about other
name services with their own entries? Or what if that previous server had
more than one IP? There's no such thing as a 'primary' IP or a 'primary' DNS
based soley on the technology. A company may have policies that suggest the
primary ip address is the one associated to the eth0 configuration. But what
does that really accomplish? Even with narrowing down to a single IP, we are
back to the challenge mentioned previously with one IP; namely, that a
single IP can have many name/domain contexts. And this is within one server.

Now consider name resolution from outside the previous server - looking in.
External name resolution can vary from how other servers find that server.
Maybe the lookup mechanism is different (NIS vs DNS), and sometimes the same
lookup mechanism has different server endpoints. Such as another DNS server
with the forwarding setup differently, or with different domains configured.
That means another tool may know this server by a different domain. What if
some servers have a local host entry (like those setup in a cluster for a
particular software)? Then their internal entries may trump an external name
service. There are many corner cases to fall into if, or should I say *when*,
companies fail to maintain standards with IP address management.

Now back to the idea of a hosted domain. Consider a Linux server that was
configured and connected to a domain. Which utility or set of utilities
were used? PAM with Kerberos? Was Samba involved? Another 3rd party package?
Answers to those questions lead to different files/commands to get a domain.
Like most responses across Linux OS types, there is not a single standard
way to go after the domain/realm - even when connected.

Enterprise datacenter discovery and mapping products attempt to solve this
problem in different ways. Some vendors require provisioning of sorts (text
files, firmware stamps, agent installs), intended to drop unique identifiers
on each server endpoint. Some use simple techniques for their single silo,
which are good for that particular silo but can isolate the datasets from
other silos (asset tag, bios UUID, serial number, physical rack/row/slot
location, etc). Some vendors use more complex  techniques in their software
by combining hardware, firmware, software, operating system, and other
context into one. These approaches have their challenges. The first approach
of stamping unique identifiers on the endpoints is good if you can influence
the provisioning and release cycles, which 3rd party products obviously
would not be able to do since they are being brought in externally and turned
on. The second approach of simple unique constraints or primary keys in a
data set, creates data isolation because you don't know data about other
related silos. The last approach with requiring complex datasets can create
data isolation because you often need more data than a single silo knows
about, in order to find a target object. So all of these methods experience
challenges when integrating to/from other products. The last approach has
another sizable challenge when different tools have non-unique values for
attributes that are meant to be unique to the target.

I followed the direction from DMTF for keeping individual components split
out in their own context, while linking them together once the context is
known, which enables tool-to-tool integrations on just the context known by
each. So Location data can integrate to location objects, which may link to
Hardware objects, which may link to OS objects, which may link to IPs, etc.
And you don't have to know about all of it to do an integration flow from
a smaller dataset.
===========================================================================

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Aug 2, 2018

"""
import sys
import traceback
import re
from contextlib import suppress

## From openContentPlatform
from utilities import addObject, addIp, addLink
from utilities import getInstanceParameters, setInstanceParameters
from utilities import updateCommand


def createObjects(runtime, osType, osAttrDict, biosAttrDict, nameAttrDict, ipAddresses, endpoint, protocolReference):
	"""Create objects and links in our results."""
	protocolId = None
	try:
		## Log when the 'printDebug' parameter is set
		runtime.logger.report('osAttrDict  : {osAttrDict!r}', osAttrDict=osAttrDict)
		runtime.logger.report('biosAttrDict: {biosAttrDict!r}', biosAttrDict=biosAttrDict)
		runtime.logger.report('nameAttrDict  : {nameAttrDict!r}', nameAttrDict=nameAttrDict)
		runtime.logger.report('ipAddresses : {ipAddresses!r}', ipAddresses=ipAddresses)

		## First create the node
		domain = nameAttrDict.get('domain')
		hostname = nameAttrDict.get('hostname')
		manufacturer = biosAttrDict.get('manufacturer')
		nodeAttributes = {}
		for thisAttr in ['distribution', 'platform', 'version', 'kernel']:
			thisValue = osAttrDict.get(thisAttr)
			if thisValue is not None:
				nodeAttributes[thisAttr] = thisValue
		nodeAttributes['hardware_provider'] = manufacturer
		nodeId = None
		if domain is None:
			nodeId, exists = addObject(runtime, osType, hostname=hostname, **nodeAttributes)
		else:
			nodeId, exists = addObject(runtime, osType, hostname=hostname, domain=domain, **nodeAttributes)

		## Establish an FQDN string for local IP addresses (loopback)
		realm = runtime.jobMetaData.get('realm', 'NA')
		FQDN = 'NA'
		if hostname is not None:
			FQDN = hostname
			if (domain is not None and domain not in hostname):
				FQDN = '{}.{}'.format(hostname, domain)
		## Now create the IPs
		for ip in ipAddresses:
			ipId = None
			if (ip in ['127.0.0.1', '::1', '0:0:0:0:0:0:0:1']):
				## Override the realm setting for two reasons: we do not want these
				## IPs in endpoint query results, and we want to track one per node
				ipId, exists = runtime.results.addIp(address=ip, realm=FQDN)
			else:
				ipId, exists = runtime.results.addIp(address=ip, realm=realm)
			addLink(runtime, 'Usage', nodeId, ipId)
		## In case the IP we've connected in on isn't in the IP table list:
		if endpoint not in ipAddresses:
			ipId, exists = addIp(runtime, address=endpoint)
			addLink(runtime, 'Usage', nodeId, ipId)

		## Now create the SSH object
		protocolId, exists = addObject(runtime, 'SSH', container=nodeId, ipaddress=endpoint, protocol_reference=protocolReference, realm=realm, node_type=osType)
		addLink(runtime, 'Enclosed', nodeId, protocolId)

		## Now create the hardware
		serial_number = biosAttrDict.get('serial_number')
		bios_info = biosAttrDict.get('bios_info')
		model = biosAttrDict.get('model')
		manufacturer = biosAttrDict.get('manufacturer')
		uuid = biosAttrDict.get('uuid')
		if serial_number is not None:
			hardwareId, exists = addObject(runtime, 'HardwareNode', serial_number=serial_number, bios_info=bios_info, model=model, vendor=manufacturer, uuid=uuid)
			addLink(runtime, 'Usage', nodeId, hardwareId)

		## Update the runtime status to success
		runtime.status(1)

	except:
		runtime.setError(__name__)

	## end createObjects
	return protocolId


def queryForIps(client, runtime, ipAddresses, shellParameters):
	"""Query and parse IP addresses."""
	try:
		ipsToIgnore = ['127.0.0.1', '::1', '0:0:0:0:0:0:0:1']
		## Using hostname works when all IPs are in DNS, though it should not
		## matter. According to the man page, this option "enumerates all
		## configured addresses on all network interfaces". However, some older
		## versions return just one IP. This method doesn't need elevated access
		(stdout, stderr, hitProblem) = client.run('hostname --all-ip-addresses')
		runtime.logger.report(' hostname --all-ip-addresses: {stdout!r}, {stderr!r}, {hitProblem!r}', stdout=stdout, stderr=stderr, hitProblem=hitProblem)
		if not hitProblem:
			#with suppress(Exception):
			if stdout is not None and len(stdout.strip()) > 0:
				valueString = stdout.strip()
				runtime.logger.report(' ipsString: {valueString!r}', valueString=valueString)
				for ipString in valueString.split():
					ipAddress = ipString.strip()
					if (ipAddress in ipAddresses or ipAddress in ipsToIgnore):
							continue
					ipAddresses.append(ipAddress)
					runtime.logger.report('IP from all-ip-addresses: {ipAddress!r}', ipAddress=ipAddress)

		## This is the proper method when available; it shows addresses assigned
		## to all network interfaces. This requires elevated access.
		command = updateCommand(runtime, 'ip addr', shellParameters)
		(stdout, stderr, hitProblem) = client.run(command)
		runtime.logger.report(' ip addr: {stdout!r}, {stderr!r}, {hitProblem!r}', stdout=stdout, stderr=stderr, hitProblem=hitProblem)
		if not hitProblem:
			if stdout is not None and len(stdout.strip()) > 0:
				for line in stdout.splitlines():
					runtime.logger.report('line: {line!r}', line=line)
					m = re.search('inet(?:6)?\s+(\S[^/\s]+)', line)
					if m:
						ipAddress = m.group(1)
						runtime.logger.report(' IP from ip addr: {ipAddress!r}', ipAddress=ipAddress)
						if (ipAddress in ipAddresses or ipAddress in ipsToIgnore):
							continue
						runtime.logger.report('Additional IP from ip addr: {ipAddress!r}', ipAddress=ipAddress)
						ipAddresses.append(ipAddress)

		## Deprecated method, but is the safety net for old OSes. This requires
		## elevated access. Also, probably would be good to somehow determine if
		## the above commands provided proper info, and only opt into trying the
		## following if they failed. Unfortunately, in testing at customers, it
		## seems that you can get partial data from the ip and hostname commands
		## above, and simply won't know if you have all the IPs without trying
		## this deprecated method. So, for now... it's still here.
		command = updateCommand(runtime, 'ifconfig', shellParameters)
		(stdout, stderr, hitProblem) = client.run(command)
		runtime.logger.report(' ifconfig: {stdout!r}, {stderr!r}, {hitProblem!r}', stdout=stdout, stderr=stderr, hitProblem=hitProblem)
		if not hitProblem:
			if stdout is not None and len(stdout.strip()) > 0:
				for line in stdout.splitlines():
					runtime.logger.report('line: {line!r}', line=line)
					m = re.search('inet(?:6)?\s+(?:addr:)?\s*(\S[^/\s]+)', line)
					if m:
						ipAddress = m.group(1)
						runtime.logger.report(' IP from ifconfig: {ipAddress!r}', ipAddress=ipAddress)
						if (ipAddress in ipAddresses or ipAddress in ipsToIgnore):
							continue
						runtime.logger.report('Additional IP from ifconfig: {ipAddress!r}', ipAddress=ipAddress)
						ipAddresses.append(ipAddress)

	except:
		runtime.setError(__name__)

	## end queryForIps
	return


def queryOsNameContext(client, runtime, attrDict):
	"""Query and parse name and domain attributes.

	Note: common sense (not to mention the man page for hostname) says not to
	attempt arbitrary use of the FQDN when there are multiple IPs and/or
	multiple responses from the name service. So the play here is to take the
	hostname (short form, which returns the value from gethostname). If good
	standards are used for OS deployment with locally stamping the servers
	with their FQDN, then this is the desired route. If no domain returns from
	that query, then fall back to unstable ground with the --fqdn option.
	"""
	try:
		## Attempt hostname without arguments first
		(stdout, stderr, hitProblem) = client.run('hostname')
		runtime.logger.report(' hostname: {stdout!r}, {stderr!r}, {hitProblem!r}', stdout=stdout, stderr=stderr, hitProblem=hitProblem)
		if not hitProblem:
			if stdout is not None and len(stdout.strip()) > 0:
				valueString = stdout.strip()
				runtime.logger.report(' hostnameString: {valueString!r}', valueString=valueString)
				attrDict['hostname'] = valueString
				valueList = valueString.split('.')
				if len(valueList) > 1:
					attrDict['domain'] = '.'.join(valueList[1:])
					attrDict['hostname'] = valueList[0]
				else:
					## Fall back to using the FQDN argument
					(stdout, stderr, hitProblem) = client.run('hostname --fqdn')
					runtime.logger.report(' hostname --fqdn: {stdout!r}, {stderr!r}, {hitProblem!r}', stdout=stdout, stderr=stderr, hitProblem=hitProblem)
					if not hitProblem:
						if stdout is not None and len(stdout.strip()) > 0:
							valueString = stdout.strip()
							runtime.logger.report(' hostnameFqdnString: {valueString!r}', valueString=valueString)
							valueList = valueString.split('.')
							if len(valueList) > 1:
								attrDict['domain'] = '.'.join(valueList[1:])
								attrDict['hostname'] = valueList[0]
			runtime.logger.report(' hostname: {hostname!r}', hostname=attrDict.get('hostname'))
			runtime.logger.report(' domain: {domain!r}', domain=attrDict.get('domain'))

	except:
		runtime.setError(__name__)

	## end queryOsNameContext
	return


def executeAndUpdateAttribute(client, runtime, command, attrDict, keyName):
	try:
		## Model or Build type
		(stdout, stderr, hitProblem) = client.run(command)
		runtime.logger.report(' {command!r}: {stdout!r}, {stderr!r}, {hitProblem!r}', command=command, stdout=stdout, stderr=stderr, hitProblem=hitProblem)
		if not hitProblem:
			attrDict[keyName] = stdout.strip()
	except:
		runtime.setError(__name__)


def queryBios(client, runtime, attrDict, shellParameters):
	"""Query and parse System attributes.

	Sample output of dmidecode from RedHat on an HP Z220 machine:
	========================================================================
	System Information
		Manufacturer: Hewlett-Packard
		Product Name: HP Z220 CMT Workstation
		Version: Not Specified
		Serial Number: 2UA24221J7
		UUID: D855D380-12FF-11E2-B8C0-B4B52FBFB9A0
		...
	BIOS Information
		Vendor: Hewlett-Packard
		Version: K51 v01.14
		Release Date: 09/27/2012
		...
	========================================================================
	"""
	## Issue one or two commands and then perform complex string parsing, verses
	## issuing five commands with simple value returns? Choosing the latter...
	try:
		## Manufacturer (e.g. 'Hewlett-Packard')
		command = updateCommand(runtime, 'dmidecode -s system-manufacturer', shellParameters)
		(stdout, stderr, hitProblem) = client.run(command)
		runtime.logger.report(' {command!r}: {stdout!r}, {stderr!r}, {hitProblem!r}', command=command, stdout=stdout, stderr=stderr, hitProblem=hitProblem)
		if not hitProblem:
			## If the first elevated command went through, run the rest of them
			attrDict['manufacturer'] = stdout.strip()

			## Model or build type (e.g. 'HP Z220 CMT Workstation')
			executeAndUpdateAttribute(client, runtime, updateCommand(runtime, 'dmidecode -s system-product-name', shellParameters), attrDict, 'model')

			## Serial number (e.g. '2UA24221J7')
			executeAndUpdateAttribute(client, runtime, updateCommand(runtime, 'dmidecode -s system-serial-number', shellParameters), attrDict, 'serial_number')

			## Hardware UUID (e.g. 'D855D380-12FF-11E2-B8C0-B4B52FBFB9A0')
			executeAndUpdateAttribute(client, runtime, updateCommand(runtime, 'dmidecode -s system-uuid', shellParameters), attrDict, 'uuid')

			## BIOS info (e.g. 'K51 v01.14')
			executeAndUpdateAttribute(client, runtime, updateCommand(runtime, 'dmidecode -s bios-version', shellParameters), attrDict, 'bios_info')

	except:
		runtime.setError(__name__)

	## end queryBios
	return


def parsePlatformFromDistro(runtime, distribution, attrDict):
	"""Parse the OS platform context out of the distribution string."""
	platform1 = re.search('^(.*)\s+release.*', distribution, re.I)
	if platform1:
		attrDict['platform'] = platform1.group(1)
	else:
		platform2 = re.search('^(.*)([0-9\.]+)', distribution)
		if platform2:
			attrDict['platform'] = platform2.group(1)
		else:
			attrDict['platform'] = distribution

	## end parsePlatformFromDistro
	return


def parseReleaseFromDistro(runtime, distribution, attrDict):
	"""Parse the OS release context out of the distribution string."""
	release1 = re.search('([0-9\.]+(?:\s*\(.*\))*)', distribution)
	if release1:
		attrDict['version'] = release1.group(1)
	release2 = re.search('\s*release\s*(.*)', distribution, re.I)
	if release2:
		attrDict['version'] = release2.group(1)

	## end parseReleaseFromDistro
	return


def querySpecialRelease(client, runtime, attrDict, fileListing):
	"""Query for special Linux distro and release info.

	Continue building this function out, for custom parsing per special case.

	Careful with using some of the 'version' files:
	  /etc/angstrom-version - has formatting similar to os-release
	  /etc/debian_version - only has the version number
	  /etc/SuSE-release - has formatting similar to os-release
	"""
	runtime.logger.report(' querySpecialRelease: try to match other /etc/*-release,version files')
	otherReleaseFiles = {
		'Angstrom' : '/etc/angstrom-version',
		'Debian' : '/etc/debian_version',
		'SuSE' : '/etc/SuSE-release'
	}
	for targetFile in fileListing.split():
		for thisDistro,thisFile in otherReleaseFiles.items():
			if targetFile == thisFile:
				attrDict['distribution'] = thisDistro
				attrDict['platform'] = thisDistro
				runtime.logger.report('  distro: {distro!r}, release: {release!r}, platform: {platform!r}', distro=attrDict.get('distribution'), release=attrDict.get('version'), platform=attrDict.get('platform'))
				return

	## end querySpecialRelease
	return


def queryRelease(client, runtime, attrDict):
	"""Query for standard Linux distro and release info.

	Order of Priority:
	1. Attempt to use the Linux Standard Base (LSB) info. Note: while this
	   is a joint project by several Linux distributions, it is neither all
	   encompassing, nor installed by default on all participanting distros.
	   (ref: https://refspecs.linuxfoundation.org/lsb.shtml)
	   (ref: https://refspecs.linuxfoundation.org/LSB_2.0.1/LSB-Core/LSB-Core/lsbrelease.html)
	2. Attempt to use /etc/os-release, which was a new configuration file
	   released with the systemd project. The goal there was to replace the
	   multitude of per-distribution release files with one. And if you're
	   not familiar with the various files, continue on to the next section.
	   (ref: https://www.freedesktop.org/software/systemd/man/os-release.html)
	3. Attempt to find a matching vendor /etc/*{release,version} file.

	Note: The /etc/*{release,version} files can be manually modified to meet
	application installation requirements (i.e. workaround for licensing). That
	can be partially mitigated with queries for package source file versions,
	but that's more than I care about.

	Sample lsb_release from RedHat:
	========================================================================
	  Distributor ID: RedHatEnterpriseServer
	  Description:    Red Hat Enterprise Linux Server release 5.7 (Tikanga)
	  Release:        5.7

	  Distributor ID: RedHatEnterpriseWorkstation
	  Description:    Red Hat Enterprise Linux Workstation release 6.3 (Santiago)
	  Release:        6.3
	========================================================================

	Sample /etc/os-release:
	========================================================================
	  NAME=Fedora
	  VERSION="17 (Beefy Miracle)"
	  ID=fedora
	  VERSION_ID=17
	  PRETTY_NAME="Fedora 17 (Beefy Miracle)"
	  ANSI_COLOR="0;34"
	  CPE_NAME="cpe:/o:fedoraproject:fedora:17"
	  HOME_URL="https://fedoraproject.org/"
	  BUG_REPORT_URL="https://bugzilla.redhat.com/"
	========================================================================

	Samples from /etc/*{release,version} files:
	========================================================================
	  Red Hat Enterprise Linux Server release 5.7 (Tikanga)
	  Red Hat Enterprise Linux Workstation release 6.3 (Santiago)
	  Enterprise Linux Enterprise Linux Server release 5.8 (Carthage)
	  Oracle Linux Server release 5.8
	  CentOS Linux release 7.4.1708 (Core)
	  Mandriva Linux release 2007.0 (Official) for i586
	  Mageia release 5 (Official) for i586
	  Gentoo Base System release 2.1
	  VMware ESX 4.1 (Kandinsky)
	========================================================================
	"""
	try:
		## 1) Try Linux Standard Base (LSB) info
		runtime.logger.report(' queryRelease: try LSB')
		lsbCommand = 'lsb_release -idr'
		(stdout, stderr, hitProblem) = client.run(lsbCommand)
		runtime.logger.report(' {lsbCommand!r}: {stdout!r}, {stderr!r}, {hitProblem!r}', lsbCommand=lsbCommand, stdout=stdout, stderr=stderr, hitProblem=hitProblem)
		if not hitProblem:
			for outputLine in stdout.split('\n'):
				m1 = re.search('^\s*Description\s*:\s*(\S.*)$', outputLine, re.I)
				if m1:
					distribution = m1.group(1)
					attrDict['distribution'] = distribution
					parsePlatformFromDistro(runtime, distribution, attrDict)
					parseReleaseFromDistro(runtime, distribution, attrDict)
					continue
				m2 = re.search('^\s*Release\s*:\s*(\S.*)$', outputLine, re.I)
				if m2:
					attrDict['version'] = m2.group(1)
			## If LSB worked, stop here
			if attrDict.get('distribution') is not None:
				runtime.logger.report('  distro: {distro!r}, release: {release!r}, platform: {platform!r}', distro=attrDict.get('distribution'), release=attrDict.get('version'), platform=attrDict.get('platform'))
				return

		## 2) Try /etc/os-release from the systemd project
		## The os-release file is similar to the output returned from LSB
		runtime.logger.report(' queryRelease: try /etc/os-release')
		osCommand = 'cat /etc/os-release'
		(stdout, stderr, hitProblem) = client.run(osCommand)
		runtime.logger.report(' {osCommand!r}: {stdout!r}, {stderr!r}, {hitProblem!r}', osCommand=osCommand, stdout=stdout, stderr=stderr, hitProblem=hitProblem)
		if not hitProblem:
			for outputLine in stdout.split('\n'):
				m1 = re.search('^\s*NAME\s*=\s*(\S.*)$', outputLine, re.I)
				if m1:
					distribution = m1.group(1).strip('"')
					attrDict['distribution'] = distribution
					parsePlatformFromDistro(runtime, distribution, attrDict)
					parseReleaseFromDistro(runtime, distribution, attrDict)
					continue
				m2 = re.search('^\s*VERSION\s*=\s*(?:")(\S.*)(?:")$', outputLine, re.I)
				if m2:
					attrDict['version'] = m2.group(1).strip('"')
			## If os-release worked, stop here
			if attrDict.get('distribution') is not None:
				runtime.logger.report('  distro: {distro!r}, release: {release!r}, platform: {platform!r}', distro=attrDict.get('distribution'), release=attrDict.get('version'), platform=attrDict.get('platform'))
				return

		## 3) Hopefully we don't get here. But if we do, we'll need to parse
		## vendor-enabled release files until we (maybe?) find a match. Expect
		## a one line response from printing the contents of any of these:
		runtime.logger.report(' queryRelease: try to match an /etc/*-release,version file')
		releaseFiles = ['/etc/system-release', '/etc/redhat-release',
						'/etc/fedora-release', '/etc/oracle-release',
						'/etc/enterprise-release', '/etc/ovs-release',
						'/etc/gentoo-release', '/etc/centos-release',
						'/etc/arch-release', '/etc/meego-release',
						'/etc/frugalware-release', '/etc/altlinux-release',
						'/etc/mandriva-release', '/etc/mageia-release',
						'/etc/slackware-version', '/etc/vmware-release']

		listReleaseFiles = 'ls /etc/*-{release,version}'
		(stdout, stderr, hitProblem) = client.run(listReleaseFiles)
		runtime.logger.report(' {listReleaseFiles!r}: {stdout!r}, {stderr!r}, {hitProblem!r}', listReleaseFiles=listReleaseFiles, stdout=stdout, stderr=stderr, hitProblem=hitProblem)
		for targetFile in stdout.split():
			if targetFile is not None and targetFile in releaseFiles:
				catReleaseFile = 'cat ' + targetFile
				(catout, stderr, hitProblem) = client.run(catReleaseFile)
				runtime.logger.report(' {catReleaseFile!r}: {catout!r}, {stderr!r}, {hitProblem!r}', catReleaseFile=catReleaseFile, catout=catout, stderr=stderr, hitProblem=hitProblem)
				if not hitProblem:
					distribution = catout.strip()
					attrDict['distribution'] = distribution
					parsePlatformFromDistro(runtime, distribution, attrDict)
					parseReleaseFromDistro(runtime, distribution, attrDict)
					m = re.search('([0-9\.]+(?:\s*\(.*\))*)', distribution)
					if m:
						value = m.group(1).strip('"')
						attrDict['version'] = value
					runtime.logger.report('  distro: {distro!r}, release: {release!r}, platform: {platform!r}', distro=attrDict.get('distribution'), release=attrDict.get('version'), platform=attrDict.get('platform'))
					return
			else:
				runtime.logger.report(' targetFile {targetFile!r} is not in our releaseFiles list; skipping.', targetFile=targetFile)

		## Continue down the rabbit hole for additional 1-off custom parsings.
		querySpecialRelease(client, runtime, attrDict, stdout)

	except:
		runtime.setError(__name__)

	## end queryRelease
	return


def parsePreviousCmdOutput(client, runtime, attrDict, prevCmdOutput):
	"""Query and parse uname -a output.

	Sample output for Linux:
	========================================================================
	For the kernel name, node name, kernel release and version, machine, etc:
	uname -a
	  Linux revelation 2.6.32-279.22.1.el6.x86_64 #1 SMP Sun Jan 13 09:21:40 EST 2013 x86_64 x86_64 x86_64 GNU/Linux
	For just the kernel release string:
	uname -r
	  2.6.32-279.22.1.el6.x86_64
	========================================================================
	"""
	try:
		runtime.logger.report('Inside parsePreviousCmdOutput with prevCmdOutput: {prevCmdOutput!r}', prevCmdOutput=prevCmdOutput)
		m = re.search('^\s*Linux\s*\S+\s+(\S+)', prevCmdOutput, re.I)
		if m:
			attrDict['kernel'] = m.group(1)
			runtime.logger.report('Found kernel from uname -a: {kernel!r}', kernel=attrDict.get('kernel'))
		else:
			## Only query for 'uname -r' when we encountered a problem with
			## parsing the previous 'uname -a' output...
			(stdout, stderr, hitProblem) = client.run('uname -r')
			runtime.logger.report(' uname: {stdout!r}, {stderr!r}, {hitProblem!r}', stdout=stdout, stderr=stderr, hitProblem=hitProblem)
			if not hitProblem and len(stdout) > 0:
				attrDict['kernel'] = stdout.strip()
				runtime.logger.report('Found kernel from uname -r: {kernel!r}', kernel=attrDict.get('kernel'))

		## Now go after distribution, release, and platform
		queryRelease(client, runtime, attrDict)

	except:
		runtime.setError(__name__)

	## end parsePreviousCmdOutput
	return


def queryLinux(runtime, client, endpoint, protocolReference, osType, prevCmdOutput):
	"""Run queries against a Linux endpoint.

	Arguments:
	  runtime (dict)    : object used for providing input into jobs and tracking
	                      the job thread through the life of its runtime
	  client            : PowerShell client
	  endpoint          : target endpoint for the discovery job
	  protocolReference : reference id
	  osType            : normalized string used for comparisons
	  prevCmdOutput     : previous command result (from running uname -a)
	"""
	try:
		## Query OperatingSystem for OS attributes
		osAttrDict = {}
		parsePreviousCmdOutput(client, runtime, osAttrDict, prevCmdOutput)
		runtime.logger.report('osAttrDict: {osAttrDict!r}', osAttrDict=osAttrDict)

		## Only continue if the first query was successful
		if len(list(osAttrDict.keys())) > 0:
			## If connections failed before succeeding, remove false negatives
			runtime.clearMessages()

			## Assign shell configuration and potential config group
			shellParameters = {}
			getInstanceParameters(runtime, client, osType, endpoint, shellParameters)
			runtime.logger.report('shell parameters: {shellParameters!r}', shellParameters=shellParameters)

			## Query BIOS for serial number and firmware
			biosAttrDict = {}
			queryBios(client, runtime, biosAttrDict, shellParameters)
			runtime.logger.report('biosAttrDict: {biosAttrDict!r}', biosAttrDict=biosAttrDict)

			## Query for name/domain
			nameAttrDict = {}
			queryOsNameContext(client, runtime, nameAttrDict)
			runtime.logger.report('nameAttrDict: {nameAttrDict!r}', nameAttrDict=nameAttrDict)

			## Query for IPs
			ipAddresses = []
			queryForIps(client, runtime, ipAddresses, shellParameters)
			runtime.logger.report('ipAddresses: {ipAddresses!r}', ipAddresses=ipAddresses)

			## Update the runtime status to success
			runtime.status(1)

			## Create the objects
			protocolId = createObjects(runtime, osType, osAttrDict, biosAttrDict, nameAttrDict, ipAddresses, endpoint, protocolReference)
			setInstanceParameters(runtime, protocolId, shellParameters)
			#runtime.logger.report('shell parameters: {shellParameters!r}', shellParameters=runtime.results.getObject(protocolId).get('shellConfig'))

	except:
		runtime.setError(__name__)

	## end queryLinux
	return
