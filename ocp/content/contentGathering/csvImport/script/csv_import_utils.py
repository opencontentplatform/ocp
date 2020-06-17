"""Utility functions for the csv import job."""
import traceback, sys
import json
import re

from utilities import loadJsonIgnoringComments


def parseCsvRecordDescriptors(logger, descriptorFile):
	"""Parse the descriptor file."""
	ciDefinitions = []
	linkDefinitions = []
	fieldMappings = []
	try:
		content = ''
		with open(descriptorFile) as fp:
			content = fp.read()
		## Allow customer to place comments in the JSON file for reference
		descriptorAsJson = loadJsonIgnoringComments(content)
		## Assign descriptor content into associated lists
		ciDefinitions = descriptorAsJson.get('ciDefinitions', [])
		linkDefinitions = descriptorAsJson.get('linkDefinitions', [])
		fieldMappings = descriptorAsJson.get('fieldMappings', [])
		## In place sorting of fieldMappings, so columns are properly ordered
		fieldMappings.sort(key=lambda x: x['fieldNumber'])
	except:
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in parseCsvRecordDescriptors: {exception!r}', exception=exception)

	## end parseCsvRecordDescriptors
	return (ciDefinitions, linkDefinitions, fieldMappings)


def setCiAttribute(attributes, ciName, attributeName, attributeValue, fieldMappings):
	"""Set the object attribute. Operations depend on type and mappings."""
	## If the value is empty, don't attempt to set
	if (attributeValue is None or len(str(attributeValue)) <= 0):
		return

	## Get the user-defined type
	attributeType = None
	for fieldMapping in fieldMappings:
		## Find this field definition, to pull the attribute type
		thisAttributeName = fieldMapping.get('attributeName')
		thisCiDefinition = fieldMapping.get('ciDefinition')
		if (ciName == thisCiDefinition and attributeName == thisAttributeName):
			if 'attributeType' in fieldMapping:
				attributeType = fieldMapping.get('attributeType')
			break

	## String type (default)
	if (attributeType is None or attributeType == '' or attributeType.lower() == 'string' or attributeType.lower() == 'str'):
		attributes[attributeName] = str(attributeValue)
	## Integer
	elif (attributeType.lower() == 'integer' or attributeType.lower() == 'int'):
		attributes[attributeName] = int(attributeValue)
	## Boolean
	elif (attributeType.lower() == 'boolean' or attributeType.lower() == 'bool'):
		attributes[attributeName] = attributeValue
	## Date/time
	elif (attributeType.lower() == 'date'):
		attributes[attributeName] = attributeValue
	## Long
	elif (attributeType.lower() == 'long'):
		attributes[attributeName] = long(attributeValue)
	## Double
	elif (attributeType.lower() == 'double'):
		attributes[attributeName] = float(attributeValue)
	## Float
	elif (attributeType.lower() == 'float'):
		attributes[attributeName] = float(attributeValue)

	return


def valueToCiType(value):
	typeDict = {
		'Network Appliance' : 'Hardware',
		'Storage' : 'HardwareStorage',
		'Switch' : 'Hardware',
		'Firewall' : 'HardwareFirewall',
		'Router' : 'Hardware',
		'Load Balancer' : 'HardwareLoadBalancer'
	}
	return typeDict.get(value)
