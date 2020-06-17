"""Import a custom CSV according to a descriptor file.

Functions:
  startJob : Standard job entry point
  normalizeEmptyParameters : Helper to normalize empty JSON parameters to 'None'
  processCsvFile : Open the CSV and action on each row
  parseCsvRecord : Parse and validate a row in the CSV
  createCIsForThisRecord: Create and relate objects

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Mar 2, 2018

"""
import sys
import traceback
import os
import csv

## From openContentPlatform
from valueConverters import *
from utilities import addObject, addLink

## From this package
from csv_import_utils import parseCsvRecordDescriptors, setCiAttribute, valueToCiType


def createCIsForThisRecord(runtime, ciDefinitions, linkDefinitions, fieldMappings, requiredAttrValues, optionalAttrValues):
	"""When the CSV record has been validated, create/relate the objects.

	Arguments:
	  runtime (dict)           : object used for providing input into jobs and
	                             tracking the job thread through its runtime.
	  ciDefinitions (list)     : named section loaded from the CSV descriptor
	  linkDefinitions (list)   : named section loaded from the CSV descriptor
	  fieldMappings (list)     : named section loaded from the CSV descriptor
	  requiredAttrValues (dict): attributes marked as required in the descriptor
	  optionalAttrValues (dict): attributes not marked as required are skipped
	                             when empty in a CSV row, and processing will
	                             continue without assuming the row is bad.
	"""
	try:
		objectsInThisRecord = {}
		for ciDefinition in ciDefinitions:
			## Get the definition context of type and required attrs
			attributes = {}
			ciType = ciDefinition['ciType']
			ciName = ciDefinition['name']
			ciStaticAttrs = ciDefinition.get('staticAttributes', {})

			## Get the objects optional/required attribute descriptors
			attributeDictionary = requiredAttrValues.get(ciName, {})
			attributeOptDictionary = optionalAttrValues.get(ciName, {})
			runtime.logger.report('   ---- object --> {ciName!r}', ciName=ciName)

			## When there are multiple subtypes of the same ciDefinition in the
			## same spreadsheet (e.g. HardwareFirewall, HardwareStorage) for the
			## same 'super' type (e.g. Hardware), we need to set appropriately.
			## Note, this may not be a required field; check both dictionaries.
			if 'object_type' in attributeDictionary:
				ciType = attributeDictionary.pop('object_type')
			elif 'object_type' in attributeOptDictionary:
				ciType = attributeOptDictionary.pop('object_type')

			## Add the required attributes
			for attributeName in attributeDictionary:
				attributeValue = attributeDictionary[attributeName]
				runtime.logger.report('   required attribute {attributeName!r}, {attributeValue!r}', attributeName=attributeName, attributeValue=attributeValue)
				setCiAttribute(attributes, ciName, attributeName, attributeValue, fieldMappings)

			## Add the optional attributes
			if ciName in optionalAttrValues:
				for attributeName in attributeOptDictionary:
					attributeValue = attributeOptDictionary[attributeName]
					runtime.logger.report('   optional attribute {attributeName!r}, {attributeValue!r}', attributeName=attributeName, attributeValue=attributeValue)
					setCiAttribute(attributes, ciName, attributeName, attributeValue, fieldMappings)

			## Update static attributes
			for staticName, staticValue in ciStaticAttrs.items():
				attributes[staticName] = staticValue

			## Create the object
			ciId, exists = runtime.results.addObject(ciType, **attributes)
			## Save the CI for link creation
			objectsInThisRecord[ciName] = ciId


		## Now that we have the CI handles, create the relationships
		## between the CI types in this CSV record, per the definition
		for linkDefinition in linkDefinitions:
			linkType = linkDefinition['linkType']
			end1ciName = linkDefinition['end1ciName']
			end2ciName = linkDefinition['end2ciName']

			## Make sure both objects exist before creating the link.
			if (end1ciName in objectsInThisRecord and end2ciName in objectsInThisRecord):
				#addLink(runtime, linkType, objectsInThisRecord[end1ciName], objectsInThisRecord[end2ciName])
				runtime.results.addLink(linkType, objectsInThisRecord[end1ciName], objectsInThisRecord[end2ciName])
			runtime.logger.report('   linking {end1ciName!r} --> {end2ciName!r}', end1ciName=end1ciName, end2ciName=end2ciName)

		## Update the runtime status to success
		if runtime.getStatus == 'UNKNOWN':
			runtime.status(1)

		## Send results back, one row at a time
		runtime.logger.report('   result to send: {result!r}', result=runtime.results.getJson())
		runtime.sendToKafka()

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in createCIsForThisRecord: {stacktrace!r}', stacktrace=stacktrace)

	## end createCIsForThisRecord
	return


def parseCsvRecord(runtime, row, ciDefinitions, linkDefinitions, fieldMappings, requiredAttrValues, optionalAttrValues):
	"""Parse, validate, and act on each CSV record, according to the definition.

	Arguments:
	  runtime (dict)        : object used for providing input into jobs and
	                          tracking the job thread through its runtime.
	  row (list)            : CSV file to import (full path)
	  ciDefinitions (list)  : named section loaded from the CSV descriptor file
	  linkDefinitions (list): named section loaded from the CSV descriptor file
	  fieldMappings (list)  : named section loaded from the CSV descriptor file
	  requiredAttrValues (dict): attributes marked as required in the descriptor
	  optionalAttrValues (dict): attributes not marked as required are skipped
	                             when empty in a CSV row, and processing will
	                             continue without assuming the row is bad.
	"""
	skipEntry = False
	for columnNumber in range(0, len(fieldMappings)):
		try:

			## In case some of the required content is missing, stop parsing
			if skipEntry:
				break

			for fieldMapping in fieldMappings:
				## Fields numbers start with 1 but columns numbers start
				## with 0, so I'm synchronizing for the comparison below
				fieldNumber = (int(fieldMapping['fieldNumber']) - 1)
				## Make sure we're looking at the proper field (in order)
				if (int(fieldNumber) != int(columnNumber)):
					continue

				## If instructed to ignore this field...
				ignoreField = fieldMapping.get('ignoreField', False)
				if (ignoreField):
					#runtime.logger.report(' Skipping field {column!r} since \'ignoreField\' was set to true in definition file', column=columnNumber)
					continue
				runtime.logger.report(' looking at field {column!r}', column=columnNumber)

				attributeValue = row[columnNumber]
				## Set the value to None if it's an empty string
				if (attributeValue and len(str(attributeValue).strip()) <= 0):
					attributeValue = None

				attributeName = fieldMapping.get('attributeName')
				requiredValue = fieldMapping.get('required', True)
				ciDefinition = fieldMapping.get('ciDefinition')
				attributeType = fieldMapping.get('attributeType', 'string')
				updateValue = fieldMapping.get('updateValue', True)

				## Transform the field if provided a converter function name
				converter = fieldMapping.get('converter')
				if (converter and (attributeValue is not None) and (len(str(attributeValue).strip())) > 0):
					runtime.logger.report(' Trying converter {converter!r} with old value {attributeValue!r} of type {attributeType!r}', converter=converter, attributeValue=attributeValue, attributeType=type(attributeValue))
					oldValue = attributeValue
					attributeValue = eval('{}'.format(converter))(oldValue)
					runtime.logger.report(' Old value {oldValue!r} converted from oldType {oldType!r} to newType {newType!r} new value {newValue!r}', oldValue=oldValue, oldType=type(oldValue), newType=type(attributeValue), newValue=str(attributeValue))
					row[columnNumber] = attributeValue
					runtime.logger.report(' New row as list: {row!r}', row=row)

				## See if this field is required
				if (requiredValue is True):
					## Verify the field has content
					if (attributeValue is None or len(str(attributeValue).strip()) <= 0):
						## Report and skip this record when the fields
						## identified for custom CI identification are empty
						runtime.logger.report(' Required field {column!r} {ciDefinition!r}.{attributeName!r}, is empty in CSV record: {row!r}', column=columnNumber, ciDefinition=ciDefinition, attributeName=attributeName, row=row)
						skipEntry = True
						break
					else:
						## Add it onto the list of name/value dictionary
						## for this particular CI type
						if (ciDefinition not in requiredAttrValues):
							## Need to create the dictionary for this type
							requiredAttrValues[ciDefinition] = {}
						tmpDictionary = requiredAttrValues[ciDefinition]
						tmpDictionary[attributeName] = attributeValue
						requiredAttrValues[ciDefinition] = tmpDictionary

				elif (updateValue and updateValue is False):
					## Ignore this field in the CSV
					continue

				## Track all optional fields (for CI updates)
				else:
					if (ciDefinition not in optionalAttrValues):
						## Need to create the dictionary for this type
						optionalAttrValues[ciDefinition] = {}
					tmpDictionary = optionalAttrValues[ciDefinition]
					tmpDictionary[attributeName] = attributeValue
					optionalAttrValues[ciDefinition] = tmpDictionary
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Failure in parseCsvRecord: {stacktrace!r}', stacktrace=stacktrace)

	## end parseCsvRecord
	return skipEntry


def processCsvFile(runtime, fileToImport, ciDefinitions, linkDefinitions, fieldMappings, firstRowIsHeader, dialect, delimiter, quotechar):
	"""Open the CSV and process line by line.

	Arguments:
	  runtime (dict)         : object used for providing input into jobs and
	                           tracking the job thread through its runtime.
	  fileToImport (str)     : CSV file to import (full path)
	  ciDefinitions (list)   : named section loaded from the CSV descriptor file
	  linkDefinitions (list) : named section loaded from the CSV descriptor file
	  fieldMappings (list)   : named section loaded from the CSV descriptor file
	  firstRowIsHeader (bool): whether or not the first row is a header
	  dialect (str)          : if set, create the csv.reader with this dialect
	  delimiter (str)        : if set, create the csv.reader with this delimiter
	  quotechar (str)        : if set, create the csv.reader with this quotechar
	"""
	lines = 0
	try:
		## Direct the csv.reader how to read the file
		csvReaderArgs = {}
		if dialect is not None:
			## Dialects for the csv.reader: 'excel', 'excel-tab', 'unix'
			csvReaderArgs['dialect'] = dialect
		if delimiter is not None:
			## Override the delimter, e.g. ':==:'
			csvReaderArgs['delimiter'] = delimiter
		if quotechar is not None:
			## Override the quote character, e.g. '|'
			csvReaderArgs['quotechar'] = quotechar

		with open(fileToImport, 'r') as csvfile:
			csvReader = csv.reader(csvfile, **csvReaderArgs)
			## Assuming header; may want to parameterize this
			skippedHeader = False
			for row in csvReader:
				lines += 1
				if not skippedHeader:
					skippedHeader = True
					continue
				requiredAttrValues = {}
				optionalAttrValues = {}
				runtime.logger.report('CSV record: {row!r}', row=row)
				skipEntry = parseCsvRecord(runtime, row, ciDefinitions, linkDefinitions, fieldMappings, requiredAttrValues, optionalAttrValues)

				## In case some of the required content is missing, stop parsing
				if skipEntry:
					runtime.logger.report('Skipping CSV record: {row!r}', row=row)
					continue

				runtime.logger.report('createCIsForThisRecord record: {row!r}', row=row)
				createCIsForThisRecord(runtime, ciDefinitions, linkDefinitions, fieldMappings, requiredAttrValues, optionalAttrValues)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in processCsvFile: {stacktrace!r}', stacktrace=stacktrace)
	runtime.logger.report('Number of lines processed from CSV: {lines!r}', lines=lines)

	## end processCsvFile
	return


def normalizeEmptyParameters(runtime, name):
	"""Helper to normalize empty JSON parameters to 'None'.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	value = runtime.parameters.get(name)
	runtime.logger.report('   starting value of {parameterName!r}: {parameterValue!r}', parameterName=name, parameterValue=value)
	if (len(str(value).strip()) <= 0):
		value = None
	runtime.logger.report('   finished value of {parameterName!r}: {parameterValue!r}', parameterName=name, parameterValue=value)

	## normalizeEmptyParameters
	return value


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		## Read/initialize the job parameters
		firstRowIsHeader = runtime.parameters.get('firstRowIsHeader', False)
		dialect = normalizeEmptyParameters(runtime, 'dialect')
		delimiter = normalizeEmptyParameters(runtime, 'delimiter')
		quotechar = normalizeEmptyParameters(runtime, 'quotechar')
		descriptor = runtime.parameters.get('descriptor')
		fileToImport = runtime.parameters.get('fileToImport')
		runtime.logger.report('Running job {name!r} on endpoint {endpoint_value!r}', name=__name__, endpoint_value=runtime.endpoint['value'])
		runtime.logger.report('   fileToImport: {fileToImport!r}', name=__name__, fileToImport=fileToImport)

		## Read the CSV record descriptor; instructs the job how to proceed
		thisPath = os.path.dirname(os.path.abspath(__file__))
		thisPackageConfPath = os.path.abspath(os.path.join(thisPath, '..', 'conf'))
		descriptorFile = os.path.join(thisPackageConfPath, descriptor)
		runtime.logger.report('Step 1: Read the CSV record descriptor: {descriptorFile!r}', descriptorFile=descriptorFile)
		(ciDefinitions, linkDefinitions, fieldMappings) = parseCsvRecordDescriptors(runtime, descriptorFile)

		## Start the work
		runtime.logger.report('Step 2: Process the CSV file: {fileToImport!r}', fileToImport=fileToImport)
		processCsvFile(runtime, fileToImport, ciDefinitions, linkDefinitions, fieldMappings, firstRowIsHeader, dialect, delimiter, quotechar)

		## Update the runtime status to success
		if runtime.getStatus() == 'UNKNOWN':
			runtime.status(1)

	except:
		runtime.setError(__name__)

	## end startJob
	return
