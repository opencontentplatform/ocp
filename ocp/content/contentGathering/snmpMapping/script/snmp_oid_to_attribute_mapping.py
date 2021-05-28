"""Update Node or Hardware CI attributes, based on OID mapping file.

This enables quick mapping sections for private MIBs, but can also be used to
regEx parse OID response from the public MIB space.


Functions:
  startJob : standard job entry point
  getMappingFile : read JSON mapping file
  processResults : get nodes & hardware objects and check for matches
  processThisMappingSection : check for matches & update attributes
  snmpGet : simple helper function

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created May 28, 2021

"""
import sys
import traceback
import re
import os
import json
from contextlib import suppress

## From openContentPlatform
from protocolWrapper import getClient
from utilities import addObject, addLink


def snmpGet(client, oid):
	"""Simple helper function."""
	snmpResponse = {}
	client.get(oid, snmpResponse)
	return snmpResponse.get(oid, None)


def processThisMappingSection(runtime, client, mappingSection, objectTypes, prevNodeData, prevHardwareData, newNodeData, newHardwareData):
	"""Process a mapping section; check for matches & update attributes."""
	for oid,section in mappingSection.items():
		## 'samples' are just for reference
		attributes = section.get('attributes', [])
		for attributeSection in attributes:
			## Get the section attributes
			endpointQueryObject = attributeSection.get('endpointQueryObject').lower()
			objectType = attributeSection.get('objectType')
			nodeAttribute = attributeSection.get('nodeAttribute')
			assignmentOperator = attributeSection.get('assignmentOperator', '=').lower()
			assignmentValue = attributeSection.get('assignmentValue')
			overrideCurrentValues = attributeSection.get('overrideCurrentValues', False)
			
			## Attribute validation
			if endpointQueryObject not in ['node', 'hardware']:
				runtime.logger.warn('Unknown endpointQueryObject type for mapping {}. Received {} and expected either "Node" or "Hardware".'.format(ref, endpointQueryObject))
				continue
			if assignmentOperator not in ['=', 'regex']:
				runtime.logger.warn('Unknown assignmentOperator type for mapping {}. Received {} and expected either "=" or "regEx".'.format(ref, assignmentOperator))
				continue
			
			## Track Object type to create, when creating new
			if endpointQueryObject not in objectTypes:
				objectTypes[endpointQueryObject] = objectType
			
			## Issue an SNMP get
			value = snmpGet(client, oid)
			runtime.logger.report('  SNMP request: {}'.format(oid))
			if value is None:
				continue
			runtime.logger.report('  SNMP response: {}'.format(value))
			
			## Skip if value is set and we aren't overriding current value
			objectToUpdate = None
			if not overrideCurrentValues:
				if endpointQueryObject == 'hardware':
					if nodeAttribute in prevHardwareData and prevHardwareData.get(nodeAttribute) is not None:
						runtime.logger.report(' Hardware attribute {} already set: {}'.format(nodeAttribute, prevHardwareData.get('nodeAttribute')))
						continue
				else: ## endpointQueryObject == 'node'
					if nodeAttribute in prevNodeData and prevNodeData.get(nodeAttribute) is not None:
						runtime.logger.report(' Node attribute {} already set: {}'.format(nodeAttribute, prevNodeData.get('nodeAttribute')))
						continue
			
			if assignmentOperator == '=':
				if endpointQueryObject == 'hardware':
					newHardwareData[nodeAttribute] = value
				else:
					newNodeData[nodeAttribute] = value
			else: ## assignmentOperator == 'regEx'
				m = re.search(assignmentValue, value)
				if m:
					parsedValue = m.groups()
					if len(parsedValue) == 1:
						parsedValue = m.group(1)
					runtime.logger.report('  setting {}.{}: {}'.format(endpointQueryObject, nodeAttribute, parsedValue))
					if endpointQueryObject == 'hardware':
						newHardwareData[nodeAttribute] = parsedValue
					else: ## endpointQueryObject == 'node'
						newNodeData[nodeAttribute] = parsedValue
				else:
					runtime.logger.report('  no regEx match found for {}.{} on value: {}'.format(endpointQueryObject, nodeAttribute, value))

	## end processThisMappingSection
	return


def processResults(runtime, client, mappingEntries):
	"""Get nodes & hardware objects passed in and check for matches."""
	try:
		## Get node attributes coming in
		identifier = runtime.endpoint.get('identifier')
		node = runtime.endpoint.get('children').get('Node', [])[0]
		prevNodeData = node.get('data', {})
		nodeName = prevNodeData.get('hostname')
		nodeId = node.get('identifier')
		deviceOID = prevNodeData.get('snmp_oid')
		runtime.logger.report('Processing node {} with snmp_oid {}'.format(nodeName, deviceOID))
		if deviceOID is None:
			raise ValueError('Node {} snmp_oid attribute is empty; cannot compare'.format(nodeName))
		
		## Get hardware attributes coming in
		hardware = None
		prevHardwareData = {}
		hardwareId = None
		nodeHardwareList = node.get('children').get('Hardware', [])
		if len(nodeHardwareList) > 0:
			hardware = nodeHardwareList[0]
			prevHardwareData = hardware.get('data', {})
			hardwareId = hardware.get('identifier')
		
		## Dictionaries for our attribute-to-value mapping here
		newNodeData = {}
		newHardwareData = {}
		objectTypes = {}
		foundMatch = False
		
		## Loop through the mapping entries
		for entry in mappingEntries:
			ref = entry.get('deviceTypeForReferenceOnly')
			matchingSection = entry.get('matchingSection', {})
			
			## Matching section
			snmpOID = matchingSection.get('snmpOID')
			comparisonOperator = matchingSection.get('comparisonOperator')
			comparisonValue = matchingSection.get('comparisonValue')
			if comparisonOperator == '==': 
				if deviceOID != snmpOID:
					continue
			elif comparisonOperator.lower() == 'regex':
				escapedOID = snmpOID.replace('.', '[.]')
				value = comparisonValue.replace('snmpOID', escapedOID, re.I)
				if not re.search(value, deviceOID):
					continue
			else:
				runtime.logger.warn('Unknown compare type for mapping {}. Received {} and expected either "==" or "regEx".'.format(ref, comparisonOperator))
				continue
			
			foundMatch = True
			runtime.logger.report(' Matched section: {}'.format(ref))
			
			## Mapping section
			mappingSection = entry.get('mappingSection', {})
			processThisMappingSection(runtime, client, mappingSection, objectTypes, prevNodeData, prevHardwareData, newNodeData, newHardwareData)
			
			## We already matched
			break
		
		if foundMatch:
			## Update the objects/links
			thisNode = None
			thisHardware = None
			if len(newNodeData) > 0:
				## Update the node
				thisNode, exists = addObject(runtime, 'Node', uniqueId=nodeId, **newNodeData)
			if len(newHardwareData) > 0:
				if hardwareId is None:
					## Create a new hardware object
					thisHardware, exists = addObject(runtime, objectTypes.get('hardware', 'Hardware'), **newHardwareData)
				else:
					## Update the previous hardware
					thisHardware, exists = addObject(runtime, objectTypes.get('Hardware'), uniqueId=hardwareId, **newHardwareData)
				addLink(runtime, 'Usage', thisNode, thisHardware)

		else:
			runtime.logger.report('No match found on node {} with snmp_oid {}'.format(nodeName, deviceOID))
			runtime.setInfo('No match found on node {} with snmp_oid {}'.format(nodeName, deviceOID))

	except:
		runtime.setError(__name__)

	## end processResults
	return


def getMappingFile(runtime, mappingFileName):
	"""Check if JSON file exists and read contents."""
	mappingFile = os.path.join(runtime.env.contentGatheringPkgPath, 'snmpMapping', 'conf', mappingFileName + '.json')
	if not os.path.isfile(mappingFile):
		raise EnvironmentError('Missing conf file specified in the parameters: {}.json'.format(mappingFile))

	mappingEntries = None
	with open(mappingFile) as fp:
		mappingEntries = json.load(fp)

	## end getMappingFile
	return mappingEntries


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		## Get mapping file
		mappingFileName = runtime.parameters.get('confFileWithMapping')
		mappingEntries = getMappingFile(runtime, mappingFileName)
		
		## Configure snmp client
		client = getClient(runtime)
		
		## Do the work
		processResults(runtime, client, mappingEntries)

		## Update the runtime status to success
		if runtime.getStatus() == 'UNKNOWN':
			runtime.status(1)

	except:
		runtime.setError(__name__)

	## end startJob
	return
