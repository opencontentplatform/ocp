"""Functions for manipulating the realm scope.

The realm scope is different than the network scope. The network scope is a
list of all IPs/Networks with inclusion/exclusion ranges defined by customers,
and may have overlapping ranges and many individual entries. While the network
scope is maintained exactly as defined by the customer, which may include
considerable sprawl with many individual IPs and added/removed entries... the
same is not true of the realm scope. The realm scope is not modified directly;
it is auto-generated by the system.  It maintains a summarized version of the
comprehensive set of IPs/networks listed in the network scope, and is used by
services (e.g. content gathering) to determine actionable IPs.

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Oct 12, 2017
	  1.1 : (CS) Removed exception handling so exceptions would be passed back to
	        the calling functions or tools (e.g. the admin console). Apr, 2019.

"""
import sys
import traceback
import time
from contextlib import suppress
import ipaddress
import os

import utils
import env
globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))


def getList(entry, entryStop, logger):
	resultList = []
	if entryStop is None:
		result = ipaddress.ip_network(entry, False)
		resultList.append(result)
	else:
		## summarize_address_range returns an iterator, but we want a list
		resultList = [ipaddr for ipaddr in ipaddress.summarize_address_range(ipaddress.ip_address(entry), ipaddress.ip_address(entryStop))]

	## end getList
	return resultList


def parseEntry(targetIpAddresses, data, logger):
	networkData = None
	ipCount = 0
	logger.debug(' ==> Looking at entry: {}'.format(data))
	entryStart = data['entry']
	## entryStop may not exist
	entryStop = data.get('entryStop')
	entryExclusion = data.get('exclusion', [])
	networkData = getList(entryStart, entryStop, logger)

	for network in entryExclusion:
		logger.debug(' ====> Looking at exclusion: {}'.format(network))
		exclusion = network['entry']
		## entryStop may not exist
		exclusionStop = network.get('entryStop')
		networkDataToExclude = getList(exclusion, exclusionStop, logger)
		newNetworkData = []

		## Loop through exclusion networks stored in networkDataToExclude
		for netObjToExclude in networkDataToExclude:
			newNetworkDataPartial = []
			## Loop through inclusion networks stored in networkData
			for netObj in networkData:
				try:
					a = list(netObj.address_exclude(netObjToExclude))
					newNetworkDataPartial = newNetworkDataPartial + a
				except ValueError:
					newNetworkDataPartial.append(netObj)
			newNetworkData = newNetworkDataPartial
			networkData = newNetworkData

	for thisNet in networkData:
		thisCount = thisNet.num_addresses
		ipCount += thisCount
		targetIpAddresses.append(thisNet)
	logger.debug('{}'.format('=' * 50))
	logger.debug('totalCount: {}\n\n'.format(ipCount))

	## end parseEntry
	return ipCount


def updateRealmScope(networkEntriesForRealm, logger):
	collapsed = None
	networkList = []
	for entry in networkEntriesForRealm:
		parseEntry(networkList, entry.data, logger) # insert logger
	## Get a unique set, then colapse to the smallest number of entries
	collapsed = [ipaddr for ipaddr in ipaddress.collapse_addresses(list(set(networkList)))]

	## end updateRealmScope
	return collapsed
