"""Normalize software.

This job queries the API for a desired dataset. The dataset is sent through
attribute mapping according to the desired transformation, resulting in a new
object sent to the database.

Functions:
  startJob : standard job entry point
  getNodesWithoutDomains : get the first set of nodes
  getNodesWithDomains : get the second set of nodes
  processResults : do the work

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Jan 2, 2019

"""
import sys
import traceback
import os
import json
import re

## From openContentPlatform
from utilities import getApiQueryResultsFull
from utilities import addObject, addLink


def castValue(tmpValue, dataType, thisValue):
	if dataType == 'string':
		tmpValue += str(thisValue)
	elif dataType == 'boolean':
		if not isinstance(thisValue, bool):
			## If thisValue isn't a boolean, allow a raised exception
			thisValue = bool(thisValue)
		else:
			tmpValue = thisValue
	elif dataType == 'integer':
		## Convert default empty string value to a zero if user expects an "and"
		## operator to add integer values listed together in expression, similar
		## to now the "and" operation on strings concatenates the list.
		if not isinstance(tmpValue, int):
			tmpValue = 0
		if not isinstance(thisValue, int):
			## If thisValue isn't an integer, allow a raised exception
			thisValue = int(thisValue)
		tmpValue += thisValue

	## end castValue
	return tmpValue


def getAttribute(flatenedResult, mappingRule, dataType):
	tmpValue = ''
	for key,value in mappingRule.items():
		if key == 'expression':
			## Override operator if set (default to 'and')
			operator = value.get('operator', 'and')
			entries = value.get('entries', [])
			for expOrCond in entries:
				thisString = getAttribute(flatenedResult, expOrCond, dataType)
				if thisString is not None and len(thisString) > 0:
					if operator == 'or':
						return thisString
					elif operator == 'and':
						tmpValue += thisString
					else:
						runtime.logger.warn('Invalid mappingRule expression operator. Expected "and" or "or", but received: {operator!r}', operator=operator)
		elif key == 'condition':
			## 'value' is a list type inside conditions
			## But I'm overloading the list to represent regEx search conditions
			## as the second option if provided, eg:
			##   ["ProcessFingerprint.path_from_process", "oracle(.+)"]
			## ... so don't treat as normal list.
			thisValue = value[0]
			if dataType == 'boolean':
				tmpValue = castValue(tmpValue, dataType, thisValue)
				break
			objectAttr = thisValue.split('.')
			## If class.attribute reference, get value from flatenedResult
			if len(objectAttr) == 2:
				label = objectAttr[0]
				attrName = objectAttr[1]
				attrValue = flatenedResult.get(label).get(attrName)
				## Entries in condition blocks are required, so abort if empty
				if attrValue is None:
					tmpValue = ''
					break
				## If we have RegEx expressions defined, we need to transform
				## the attrValue (via re.search) as requested - before assigning
				## the final value to the new attribute.
				if len(value) > 1:
					for regEx in value[1:]:
						thisValue = ''
						m = re.search(regEx, attrValue)
						if m is not None:
							for entry in m.groups():
								thisValue = thisValue + entry + ' '
							if thisValue is not None:
								thisValue = thisValue.strip()
								## no need to try more regEx matches; this worked
								break
					attrValue = thisValue

				tmpValue = castValue(tmpValue, dataType, attrValue)
			## Otherwise, assume it's a simple type
			else:
				tmpValue = castValue(tmpValue, dataType, thisValue)
		else:
			runtime.logger.warn('Invalid mappingRule key. Expected "expression" or "condition", but received "{key!r}"', key=key)
		## Normalize empty strings to None
		if dataType == 'string' and len(tmpValue) <= 0:
			tmpValue = None
		return tmpValue
	## end getAttribute


def getDataType(runtime, data, transformName, transformFile):
	"""Don't assume the type; require an explicit declaration and normalize."""
	dataType = data.get('dataType', 'string')
	dataType = dataType.lower()
	## If not the expected types, try to normalize the value provided
	if dataType not in ['boolean', 'integer', 'string']:
		## Boolean types
		if dataType == 'bool':
			dataType == 'boolean'
		## Integer types
		elif (dataType == 'int' or
			  dataType == 'long' or
			  dataType == 'float'):
			dataType == 'integer'
		## String types
		elif (dataType == 'str' or
			  dataType == 'char' or
			  dataType == 'varchar'):
			dataType == 'string'
		## Should we default to string or error? Right now, defaulting...
		else:
			runtime.logger.report('Invalid dataType {dataType!r} provided by transformation {transformName!r} in file {transformFile!r}; defaulting to string.', dataType=dataType, transformName=transformName, transformFile=transformFile)
			dataType == 'string'

	## end getDataType
	return dataType


def startNormalization(runtime, queryResult, flatenedResult, transformFile, transformName):
	"""Perform data normalization on a result, according to the tranformation file."""
	## Don't use dictionary.get(); I want to stop if class/attrs are missing
	classToCreate = transformFile['classToCreate']
	mappedAttributes = {}
	containerClass = None
	containerId = None
	attributes = transformFile['attributes']
	for name,data in attributes.items():
		mappingRule = data.get('mappingRule')
		if name == 'container':
			containerClass = data.get('class')
			containerId = getAttribute(flatenedResult, mappingRule, 'string')
			if (containerClass is None or containerId is None):
				runtime.logger.report('Improper mapped container values.')
				return
		else:
			isRequired = data.get('isRequired', False)
			dataType = getDataType(runtime, data, transformName, transformFile)
			mappedValue = getAttribute(flatenedResult, mappingRule, dataType)
			if mappedValue is not None:
				mappedAttributes[name] = mappedValue
			else:
				## No value found...
				if isRequired is not None:
					## Value isn't required, continue parsing the next attribute
					continue
				else:
					## Transform file listed this as required; need to abort
					runtime.logger.report('No value found for attribute {name!r}; transform file {transformFile!r} listed this as required... skipping object creation.', name=name, transformFile=transformFile)
					return

	## Create the container first, if there is one
	if (containerId is not None):
		runtime.results.addObject(containerClass, uniqueId=containerId)

	## Create the target object
	objectId, exists = addObject(runtime, classToCreate, **mappedAttributes)
	## If we have a container, link the object to the container
	if containerId is not None:
		addLink(runtime, 'Enclosed', containerId, objectId)

	## Send results back 1 at a time, to avoid conflicts causing a DB rollback
	runtime.logger.report(' result to send: {result!r}', result=runtime.results.getJson())
	runtime.sendToKafka()

	## end startNormalization
	return


def recurseNestedToFlatDict(result, flatenedResult):
	"""Recurse through the nested result and create a flat dictionary."""
	objectId = result.get('identifier')
	objectType = result.get('class_name')
	objectLabel = result.get('label')
	data = result.get('data', {})
	if objectLabel in flatenedResult:
		## We do NOT want to overwrite the value for the object with matching
		## 'label' values; avoid creating the objects and create an error.
		raise EnvironmentError('Result set had multiple entries for label {}. Not sure which should be used for normalization. Ensure input query has a unique tree without a list for a leaf node.'.format(objectLabel))
	flatenedResult[objectLabel] = data
	## Assuming the tree connected to the linchpin has only single leafs; if a
	## subtree is a list instead of a single entry, the created object will vary
	## depending on result set order.
	children = result.get('children', {})
	if len(children) > 0:
		for childResult in children:
			recurseNestedToFlatDict(childResult, flatenedResult)

	## end recurseNestedToFlatDict
	return


def processThisEntry(runtime, queryResults, transformFile, transformName):
	"""Read each result from the input query to the normalization function."""
	runtime.logger.report('  processThisEntry: on file: \n{transformFile!r}', transformFile=transformFile)
	for queryResult in queryResults:
		try:
			flatenedResult = {}
			runtime.logger.report('  originalResult: {queryResult!r}', queryResult=queryResult)
			recurseNestedToFlatDict(queryResult, flatenedResult)
			runtime.logger.report('  flatenedResult: {flatenedResult!r}', flatenedResult=flatenedResult)
			startNormalization(runtime, queryResult, flatenedResult, transformFile, transformName)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Failure with transformation {transformName!r}: {stacktrace!r}', transformName=transformName, stacktrace=stacktrace)

	## end processThisEntry
	return


def loadJsonFile(fileWithPath, fileType):
	"""Check if JSON file exists and read contents via json.load(fp)."""
	if not os.path.isfile(fileWithPath):
		raise EnvironmentError('JSON {} file does not exist: {}'.format(fileType, fileWithPath))
	queryContent = None
	with open(fileWithPath) as fp:
		queryContent = json.load(fp)

	## end loadJsonFile
	return queryContent


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		## Set the corresponding directories for input
		jobScriptPath = os.path.dirname(os.path.realpath(__file__))
		basePath = os.path.abspath(os.path.join(jobScriptPath, '..'))
		orderFile = os.path.join(basePath, 'conf', 'orderedList.json')
		inputPath = os.path.join(basePath, 'input')
		transformPath = os.path.join(basePath, 'transform')

		## Read in the conf/orderedList.json file
		with open(orderFile) as fp:
			orderedList = json.load(fp)

		for task in orderedList:
			try:
				inputName = task.get('inputName')
				transformName = task.get('transformName')
				runtime.logger.report('Working on input query {inputName!r}', inputName=inputName)

				## Read the input query and transformation descriptor files
				inputFile = loadJsonFile(os.path.join(inputPath, inputName + '.json'), 'input')
				transformFile = loadJsonFile(os.path.join(transformPath, transformName + '.json'), 'transform')
				## Query API for the query result
				queryResults = getApiQueryResultsFull(runtime, inputFile, resultsFormat='Nested-Simple', headers={'removeEmptyAttributes': False}, verify=runtime.ocpCertFile)
				if queryResults is None or len(queryResults) <= 0:
					runtime.logger.report('No results found for input query {inputName!r}; skipping.', inputName=inputName)
					continue
				runtime.logger.report(' -- queryResults: {queryResults!r}', queryResults=queryResults)
				## Special case since we need Nested format; if query was only
				## looking for a single object, the nested format drops down to
				## a Flat format, with a list of objects.
				if 'objects' in queryResults:
					queryResults = queryResults['objects']

				## Start the work
				processThisEntry(runtime, queryResults, transformFile, transformName)

			except:
				runtime.logger.error('Failure with query {inputName!r}: {stacktrace!r}', inputName=inputName, stacktrace=str(sys.exc_info()[1]))

		## Update the runtime status to success
		if runtime.getStatus() == 'UNKNOWN':
			runtime.status(1)

	except:
		runtime.setError(__name__)

	## end startJob
	return
