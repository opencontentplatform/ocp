"""Sends dynamically discovered data to OpsView, for auto-provisioning monitors.

Note, it would be nice to send delta's from ITDM instead of having to do all
the custom object manipulation and comparisons (if it existed before). But this
is not possible with the OpsView API at the time of writing this integration.
Several of the items defined on the Host are in list form, but do not allow any
type of insert/remove of specific elements; it's an all or nothing change on
hosttemplates, servicechecks, business_components, hostattributes... etc.

If this integration wanted to add 3 processes to the 'hostattributes' list on an
existing Host, without first pulling any current attributes (e.g. any current
disks previously defined on the host for monitoring), then the new add of those
3 processes with a PUT operation on the host, will overwrite the previous list
and effectively delete all the previously defined disks.

"""
import sys
import traceback
import os
import re
import json
from contextlib import suppress

## From openContentPlatform
from utilities import getApiQueryResultsFull, getApiQueryResultsInChunks
## From this module
from opsViewRestAPI import OpsViewRestAPI


def compareCompHostLists(runtime, opsviewHosts, itdmHosts, hosts):
	"""Compare the host lists between tools, for this logical component."""
	needToUpdate = False
	for opsviewHost in opsviewHosts:
		hosts.append({"name": opsviewHost})
	for itdmHost in itdmHosts:
		if itdmHost not in opsviewHosts:
			needToUpdate = True
			hosts.append({"name": itdmHost})

	## end compareCompHostLists
	return needToUpdate


def compareComponents(runtime, opsviewService, itdmSignatures, opsviewComponents):
	"""Compare ITDM Fingerprints to OpsView Host attributes; insert/update accordingly."""
	for itdmCompName,itdmHosts in itdmSignatures.items():
		try:
			itdmHosts = list(set(itdmHosts))
			if itdmCompName not in opsviewComponents:
				## Just create it
				payload = {}
				payload['name'] = itdmCompName
				payload['host_template'] = {"name" : "Application - ITDM"}
				opHosts = []
				for itdmHost in itdmHosts:
					opHosts.append({"name": itdmHost})
				payload['hosts'] = opHosts
				runtime.logger.report('Need to INSERT component: {itdmCompName!r}: {payload!r}', itdmCompName=itdmCompName, payload=payload)
				opsviewService.insertComponent(json.dumps(payload))

			else:
				## Tedious comparisons required to avoid clobbering list values
				opsviewCompDetails = opsviewComponents[itdmCompName]
				opsviewHostId = opsviewCompDetails['id']
				opsviewHosts = opsviewCompDetails['hosts']
				payload = {}
				payload['name'] = itdmCompName
				## Do I need to check the host template first?
				payload['host_template'] = {"name" : "Application - ITDM"}
				hosts = []
				if (compareCompHostLists(runtime, opsviewHosts, itdmHosts, hosts)):
					payload['hosts'] = hosts
					runtime.logger.report('Need to UPDATE component {itdmCompName!r}: {payload!r}', itdmCompName=itdmCompName, payload=payload)
					opsviewService.updateComponent(opsviewHostId, json.dumps(payload))
				else:
					runtime.logger.report('Component is current; no work required on {itdmCompName!r}', itdmCompName=itdmCompName)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Failure in compareComponents: {stacktrace!r}', stacktrace=stacktrace)

	## end compareComponents
	return


def compareHostSection(runtime, opsviewList, itdmList, payload, payloadAttribute, compareAttribute, keepFullEntry, needToUpdate):
	finalList = []
	needToUpdateLocal = False

	## First copy in the previous datasets, filtering where needed
	for sourceEntry in opsviewList:
		sourceValue = sourceEntry[compareAttribute]
		## For hostattributes, we need to keep the full section. For others like
		## hosttemplates and servicechecks, we only want to keep the name value.
		if keepFullEntry:
			finalList.append(sourceEntry)
		else:
			finalList.append({compareAttribute: sourceValue})

	## Now go through the itdm dataset, adding new where needed
	for targetEntry in itdmList:
		targetValue = targetEntry.get(compareAttribute)
		matched = False
		for finalEntry in finalList:
			finalValue = finalEntry.get(compareAttribute)
			if finalValue == targetValue:
				matched = True
				break
		if not matched:
			needToUpdateLocal = True
			needToUpdate = True
			runtime.logger.report('YES - found new data...', targetEntry=targetEntry)
			if keepFullEntry:
				finalList.append(targetEntry)
				runtime.logger.report('Found new section to update: {targetEntry!r}', targetEntry=targetEntry)
			else:
				finalList.append({compareAttribute: targetValue})
				runtime.logger.report('Found new part to update: {targetValue!r}', targetValue=targetValue)

	## Only if we found an update locally on this list, will we add the section
	## into payload for the final PUT operation. Ignore sections we dont need.
	if needToUpdateLocal:
		payload[payloadAttribute] = finalList

	## end compareHostSection
	return needToUpdate


def compareHosts(runtime, opsviewService, itdmNodes, opsviewHosts):
	"""Compare ITDM Nodes with OpsView Hosts; insert/update accordingly."""
	for itdmNodeName,itdmDetails in itdmNodes.items():
		try:
			itdmNodeIp = itdmDetails['ip']
			itdmNodeFingerprints = itdmDetails['hostattributes']
			itdmFingerprintList = [itdmNodeFingerprints[name] for name in itdmNodeFingerprints]
			runtime.logger.report('Comparing host {itdmNodeName!r}', itdmNodeName=itdmNodeName)
			if itdmNodeName not in opsviewHosts:
				## Easy... no comparison work needed; just insert
				#runtime.logger.report('Need to INSERT host: {itdmNodeName!r}', itdmNodeName=itdmNodeName)
				payload = {}
				payload['name'] = itdmNodeName
				payload['ip'] = itdmNodeIp
				payload['hostattributes'] = itdmFingerprintList
				payload['hosttemplates'] = [{"name" : "Application - ITDM"}]
				payload['servicechecks'] = [{"name" : "ITDM Process Fingerprints"}]
				runtime.logger.report('Need to INSERT host: {itdmNodeName!r}: {payload!r}', itdmNodeName=itdmNodeName, payload=payload)
				opsviewService.insertHost(json.dumps(payload))

			else:
				## Tedious comparisons required to avoid clobbering list values
				opsviewHostDetails = opsviewHosts[itdmNodeName]
				opsviewHostId = opsviewHostDetails['id']
				payload = {}
				needToUpdate = False
				needToUpdate = compareHostSection(runtime, opsviewHostDetails['hostattributes'], itdmFingerprintList, payload, 'hostattributes', 'value', True, needToUpdate)
				needToUpdate = compareHostSection(runtime, opsviewHostDetails['hosttemplates'], [{"name" : "Application - ITDM"}], payload, 'hosttemplates', 'name', False, needToUpdate)
				needToUpdate = compareHostSection(runtime, opsviewHostDetails['servicechecks'], [{"name" : "ITDM Process Fingerprints"}], payload, 'servicechecks', 'name', False, needToUpdate)
				## After the comparisons, see if we need to send an update
				if needToUpdate:
					runtime.logger.report('Need to UPDATE host {itdmNodeName!r} id {opsviewHostId!r}: {payload!r}', itdmNodeName=itdmNodeName, opsviewHostId=opsviewHostId, payload=payload)
					opsviewService.updateHost(opsviewHostId, json.dumps(payload))
				else:
					runtime.logger.report('Host is current; no work required on {itdmNodeName!r}', itdmNodeName=itdmNodeName)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Failure in compareHosts: {stacktrace!r}', stacktrace=stacktrace)

	## end compareHosts
	return


def getOpsViewBSMComponents(runtime, opsviewService, opsviewComponents):
	"""Pull all BSM Components from OpsView."""
	responseAsJson = opsviewService.getComponents()
	## TODO: Need to set up for chunking/paging
	componentList = responseAsJson.get('list', [])
	for thisComponent in componentList:
		name = thisComponent.get('name')
		compDetails = {}
		compDetails['id'] = thisComponent['id']
		hostList = thisComponent.get('hosts', [])
		hosts = []
		for thisHost in hostList:
			hosts.append(thisHost.get('name'))
		hosts = list(set(hosts))
		compDetails['hosts'] = hosts
		opsviewComponents[name] = compDetails

	## end getOpsViewBSMComponents
	return


def getOpsViewHosts(runtime, opsviewService, opsviewHosts):
	"""Pull all Host objects from OpsView."""
	responseAsJson = opsviewService.getHosts()
	## TODO: Need to set up for chunking/paging
	hostList = responseAsJson.get('list', [])
	for thisHost in hostList:
		nodeName = thisHost.get('name')
		hostDetails = {}
		hostDetails['id'] = thisHost['id']
		hostDetails['hostattributes'] = thisHost.get('hostattributes', [])
		hostDetails['hosttemplates'] = thisHost.get('hosttemplates', [])
		hostDetails['business_components'] = thisHost.get('business_components', [])
		hostDetails['servicechecks'] = thisHost.get('servicechecks', [])
		opsviewHosts[nodeName] = hostDetails
		runtime.logger.report('OpsView Node {nodeName!r}: {hostDetails!r}', nodeName=nodeName, hostDetails=hostDetails)

	## end getOpsViewHosts
	return


def getCredentialMatchingDescriptor(runtime):
	"""Simple wrapper to get un-managed credential type (REST API here).

	Note, since this is for a REST endpoint, this data isn't encrypted as it is
	for the standard managed/wrapped types.  We we actually have to supply the
	credentials in the connection attempt.
	"""
	## Read/initialize the job parameters
	opsviewRestEndpoint = runtime.parameters.get('opsviewRestEndpoint')
	descriptor = runtime.parameters.get('credentialDescriptor', 'OpsView')
	protocolType = 'ProtocolRestApi'

	for protocolReference,entry in runtime.protocols.items():
		if (entry.get('protocolType', '').lower() == protocolType.lower()):
			protocolReference = entry.get('protocol_reference')
			endpointDescription = entry.get('description', '')
			if re.search(descriptor, endpointDescription, re.I):
				## Since this is for a REST endpoint, this data isn't encrypted;
				## we actually have to supply it during the connection attempt.
				user = entry.get('user')
				notthat = entry.get('password')
				if user is None:
					continue
				opsviewService = OpsViewRestAPI(runtime, opsviewRestEndpoint, user, notthat)
				if opsviewService.connected:
					return opsviewService
				runtime.logger.report('Failed to connect to OpsView REST API with user {user!r}', user=user)

	## end getCredentialMatchingDescriptor
	return None


def skipThisNode(skipNodeRegExList, nodeName):
	for regEx in skipNodeRegExList:
		if regEx is not None and re.search(regEx, nodeName):
			return True
	return False


def buildItdmStructures(runtime, queryResults, itdmNodes, itdmSignatures):
	"""Build OpsView-like structures from ITDM query results.

	This will create structures for the following:
	  1) Nodes (OpsView Hosts) with IP as an attribute
	  2) Process Fingerprints (tracked on the node as OpsView Host attributes),
	     and these are the items that are actionable and auto-monitored.
	  3) Software Signatures (OpsView Service Components)
	"""
	try:
		skipNodeRegExList = runtime.parameters.get('skipNodeRegExList')
		for node in queryResults.get('Node', []):
			## First object is a Node
			nodeName = node.get('data', {}).get('hostname')
			if nodeName is None:
				continue
			thisNode = {}
			nodeDomain = node.get('data', {}).get('domain')

			## Next level holds Shell and ProcessFingerprint objects
			nodeChildren = node.get('children', {})
			shellObjects = nodeChildren.get('Shell', [])
			processObjects = nodeChildren.get('ProcessFingerprint', [])
			for shellObject in shellObjects:
				nodeIp = shellObject.get('data', {}).get('ipaddress')
				if nodeIp is not None:
					thisNode['ip'] = nodeIp
					break
			## Created for troubleshooting results, but may be used later...
			if skipThisNode(skipNodeRegExList, nodeName):
				continue

			fingerprints = {}
			## Loop through all ProcessFingerprint objects
			for processObject in processObjects:
				procData = processObject.get('data', {})
				thisProcess = {}
				thisProcess['arg1'] = procData.get('name')
				thisProcess['arg2'] = procData.get('path_from_process')
				if thisProcess['arg2'] is None:
					thisProcess['arg2'] = procData.get('path_from_filesystem')
				thisProcess['arg3'] = procData.get('process_owner')
				thisProcess['arg4'] = procData.get('process_args')
				## If args weren't listed because we concatenated that part onto
				## the name (e.g. 'python:simply_fast.py'), then create the args
				if (thisProcess['arg4'] is None):
					m = re.search('^([^:]+):(.*)$', thisProcess['arg1'])
					if m:
						thisProcess['arg1'] = m.group(1)
						thisProcess['arg4'] = m.group(2)
				## Get single unique attr for OpsView, by joining constraints
				procUniqueName = thisProcess['arg1']
				for procAttr in ['arg3', 'arg4']:
					keyValue = thisProcess[procAttr]
					if keyValue is not None:
						procUniqueName = '{} {}'.format(procUniqueName, keyValue)
				procUniqueName = procUniqueName[:255]
				## Add the unique value and add to the list for this node
				thisProcess['value'] = procUniqueName
				thisProcess['name'] = 'ITDM_PROCESS_FINGERPRINT'
				fingerprints[procUniqueName] = thisProcess

				## Loop through all SoftwareFingerprint objects
				softwareName = thisProcess['arg1']
				swUniqueName = softwareName
				procChildren = processObject.get('children', {})
				softwareObjects = procChildren.get('SoftwareFingerprint', [])
				for softwareObject in softwareObjects:
					swData = softwareObject.get('data', {})
					swUniqueName = swData.get('name', thisProcess['arg1'])
					for uniqueConstraint in ['software_version', 'software_info']:
						keyValue = swData.get(uniqueConstraint)
						if keyValue is not None and keyValue != 'Unknown':
							swUniqueName = '{} {}'.format(swUniqueName, keyValue)
					swUniqueName = swUniqueName[:255]
					break
				## Add this host to the list of hosts using this sig/component
				hosts = itdmSignatures.get(swUniqueName, [])
				hosts.append(nodeName)
				itdmSignatures[swUniqueName] = hosts

			## Update the node information and add to the list
			thisNode['hostattributes'] = fingerprints
			itdmNodes[nodeName] = thisNode
			runtime.logger.report('ITDM Node {nodeName!r}: {nodeDetails!r}', nodeName=nodeName, nodeDetails=thisNode)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in buildItdmStructures: {stacktrace!r}', stacktrace=stacktrace)

	## end buildItdmStructures
	return


def getItdmDataSet(runtime, jobPath):
	"""Pull requested dataset from ITDM."""
	targetQuery = runtime.parameters.get('targetQuery')
	queryFile = os.path.join(jobPath, 'input', targetQuery + '.json')
	if not os.path.isfile(queryFile):
		raise EnvironmentError('JSON query file does not exist: {}'.format(queryFile))

	## Load the file containing the query
	queryContent = None
	with open(queryFile) as fp:
		queryContent = json.load(fp)

	## Get chunked query results from the API; best to use when the data
	## set can be quite large, but the second version can be used if you
	## want to gather everything in one call or in a non-Flat format:
	#queryResults = getApiQueryResultsInChunks(runtime, queryContent)
	queryResults = getApiQueryResultsFull(runtime, queryContent, resultsFormat='Nested', headers={'removeEmptyAttributes': False})
	if queryResults is None or len(queryResults) <= 0:
		raise EnvironmentError('No results found from ITDM; nothing to update.')

	## end getItdmDataSet
	return queryResults


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	client = None
	try:
		## Set the corresponding directories for input
		jobScriptPath = os.path.dirname(os.path.realpath(__file__))
		jobPath = os.path.abspath(os.path.join(jobScriptPath, '..'))

		## Get the current data set from ITDM
		queryResults = getItdmDataSet(runtime, jobPath)
		runtime.logger.report('Node result count from ITDM: {nodeCount!r}', nodeCount=len(queryResults.get('Node', [])))
		## Transform ITDM data into structures similar to OpsView for comparison
		itdmNodes = {}
		itdmSignatures = {}
		buildItdmStructures(runtime, queryResults, itdmNodes, itdmSignatures)
		runtime.logger.report('Node processed count from ITDM: {nodeCount!r}', nodeCount=len(itdmNodes))
		runtime.logger.report('Signature count from ITDM: {sigCount!r}', sigCount=len(itdmSignatures))

		## Establish a connection the OpsView REST API and retrieve token
		opsviewService = getCredentialMatchingDescriptor(runtime)
		if opsviewService is None:
			raise EnvironmentError('Unable to connect to OpsView')
		## Get the current data set from OpsView
		opsviewHosts = {}
		opsviewComponents = {}
		getOpsViewBSMComponents(runtime, opsviewService, opsviewComponents)
		runtime.logger.report('Component count from OpsView: {compCount!r}', compCount=len(opsviewComponents))
		getOpsViewHosts(runtime, opsviewService, opsviewHosts)
		runtime.logger.report('Node count from OpsView: {nodeCount!r}', nodeCount=len(opsviewHosts))

		## Start the comparison work
		compareHosts(runtime, opsviewService, itdmNodes, opsviewHosts)
		compareComponents(runtime, opsviewService, itdmSignatures, opsviewComponents)

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
