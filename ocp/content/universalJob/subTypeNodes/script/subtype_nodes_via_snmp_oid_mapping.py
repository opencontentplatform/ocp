"""Move node CIs into more specific subtype categories, based on OID mapping.

Functions:
  startJob : standard job entry point
  getNodesWithoutDomains : get the first set of nodes (less qualified)
  getNodesWithDomains : get the second set of nodes (more qualified)
  getQueryResults : get query results for the node type
  processResults : loop through IPs with both qualified and partial nodes

"""
import sys
import traceback
import re
import os
import json
from contextlib import suppress

## From openContentPlatform
from utilities import getApiQueryResultsFull


def processResults(runtime, mappingEntries, queryContent):
	"""Get all nodes with snmp_oid values; update any that match a mapping."""
	try:
		queryResults = getApiQueryResultsFull(runtime, queryContent, resultsFormat='Flat', verify=runtime.ocpCertFile)
		nodeResults = queryResults.get('objects', [])
		runtime.logger.info('Found {} base nodes with SNMP OID values'.format(len(nodeResults)))
		
		## Loop through the target nodes
		for result in nodeResults:
			## Get node attributes
			identifier = result.get('identifier')
			nodeData = result.get('data', {})
			nodeName = nodeData.get('hostname')
			deviceOID = nodeData.get('snmp_oid')
			runtime.logger.report(' node: {name!r} with OID {oid!r} has ID: {identifier!r}', name=nodeName, oid=deviceOID, identifier=identifier)
			
			## Loop through the mapping entries
			foundMatch = False
			for entry in mappingEntries:
				ref = entry.get('deviceTypeForReferenceOnly')
				matchingSection = entry.get('matchingSection', {})
				
				## Matching section
				snmpOID = matchingSection.get('snmpOID')
				compareType = matchingSection.get('compareType')
				compareValue = matchingSection.get('compareValue')
				if compareType == '==': 
					if deviceOID == snmpOID:
						foundMatch = True
				elif compareType.lower() == 'regex':
					escapedOID = snmpOID.replace('.', '[.]')
					value = compareValue.replace('snmpOID', escapedOID, re.I)
					if re.search(value, deviceOID):
						foundMatch = True
				else:
					runtime.logger.info('Unknown compare type for mapping {}. Received {} and expected either "==" or "regEx".'.format(ref, compareType))
					
				## If no match, continue to the next mapping definition
				if not foundMatch:
					continue
				
				## Mapping section
				mappingSection = entry.get('mappingSection', {})
				nodeType = mappingSection.get('type')
				attributeValueOverrides = mappingSection.get('attributeValueOverrides', {})
				attributeValuesToUseWhenEmpty = mappingSection.get('attributeValuesToUseWhenEmpty', {})
				
				attrs = {}
				## Explicitly set domain to null if it was null before
				nodeDomain = nodeData.get('domain')
				attrs['hostname'] = nodeName
				attrs['domain'] = nodeDomain
				## Update static attribute values
				for key,value in attributeValuesToUseWhenEmpty.items():
					## The data section by default will not remove null values
					if key not in nodeData:
						attrs[key] = value
				for key,value in attributeValueOverrides.items():
					attrs[key] = value
				
				runtime.logger.report('  updating subtype for {}'.format(nodeName))
				runtime.logger.report('    ==================')
				runtime.logger.report('    previous data:')
				for key,value in nodeData.items():
					runtime.logger.report('      {}: {}'.format(key,value))
				runtime.logger.report('    attribute updates:')
				for key,value in attrs.items():
					runtime.logger.report('      {}: {}'.format(key,value))
				runtime.logger.report('    ==================')
				
				## Update the object and subtype accordingly
				runtime.results.addObject(nodeType, uniqueId=identifier, **attrs)
				break

	except:
		runtime.setError(__name__)

	## end processResults
	return


def getQueryContent(runtime, queryFileName):
	"""Run a query to get all matching objects."""
	queryFile = os.path.join(runtime.env.universalJobPkgPath, 'subTypeNodes', 'input', queryFileName + '.json')
	if not os.path.isfile(queryFile):
		raise EnvironmentError('Missing query file specified in the parameters: {}'.format(queryFile))
	
	queryContent = None
	with open(queryFile) as fp:
		queryContent = json.load(fp)

	## end getQueryContent
	return queryContent


def getMappingFile(runtime, mappingFileName):
	"""Check if JSON file exists and read contents."""
	mappingFile = os.path.join(runtime.env.universalJobPkgPath, 'subTypeNodes', 'conf', mappingFileName + '.json')
	if not os.path.isfile(mappingFile):
		raise EnvironmentError('Missing conf file specified in the parameters: {}'.format(mappingFile))

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
		## Parameters
		mappingFileName = runtime.parameters.get('confFileWithMapping')
		queryFileName = runtime.parameters.get('inputFileForTargetNodes')
		
		## Load files
		mappingEntries = getMappingFile(runtime, mappingFileName)
		queryContent = getQueryContent(runtime, queryFileName)

		## Do the work
		processResults(runtime, mappingEntries, queryContent)

		## Update the runtime status to success
		if runtime.getStatus() == 'UNKNOWN':
			runtime.status(1)

	except:
		runtime.setError(__name__)

	## end startJob
	return
