"""Utility module for content gathering jobs.

Classes:
  jobParameterizedLogger : creates a logger utility that in addition to standard
                           log functions, will conditionally report messages
                           based on the setting of a job parameter
  sectionedStringToIterableObject : Transform sectioned string->iterable object
  delimitedStringToIterableObject : Transform delimited string->iterable object

Functions:
  addObject : add an object onto the results set
  addLink : add add a link connecting two objects on the result set
  addIp : add an IP object onto the result set
  concatenate : string concatenate objects
  safeStr : return the string or unicode representation of an object
  loadJsonIgnoringComments : load json files by ignoring comment lines
  verifyOutputLines : split string output into lines
  updateCommand : modify a command according to config parameters
  grep : similar to a unix grep
  splitAndCleanList : Helper function for parameter parsing
  scrubQuotation: Clean quoted strings formatted by the Select-Object cmdlet
  scrubQuotationFromDelimitedString : Remove quotation around individual entries
  cleanInstallLocation : Remove args and resolve 8dot3 paths
  resolve8dot3Name : resolve Windows 8dot3 path into the full version


Author: Chris Satterthwaite (CS)
Contributors: Madhusudan Sridharan (MS)
Version info:
  1.0 : (CS) Created Mar 7, 2017

"""
import sys
import traceback
import os
import re
import time
import json
import copy
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import ipaddress
import socket
from contextlib import suppress


class jobParameterizedLogger:
	"""Conditionally log messages, based on the setting of a job parameter.

	This is a wrapper for the logger. If a parameter is set True (usually passed
	as an inputParameter via the job definition), then send all messages flowing
	through this wrapper, into the desired logger level (info/debug/error).

	Instead of just using the global logger settings, we want to provide an easy
	way for jobs to flip on/off detailed job logging for a specific job. This is
	notably used for debugging and development, but can be leveraged for system
	administration. If content gathering jobs are developed using this wrapper,
	jobs can be very quiet (increasing performance) unless/until something goes
	wrong (e.g. access revoked or partially blocked by new firewall rule). Flip
	a job parameter and you see everything the job developer wanted to expose at
	that level.  Sample usage follows:

	myLogger = runtime.logger
	printFlag = runtime.parameters.get('printDebug', False)
	log = jobParameterizedLogger(myLogger, printFlag)
	log.report('Message via the {qualifier!r} {product!r} logger', qualifier='searchable JSON', product='Twisted')

	"""
	def __init__(self, logger, flag=True, level='debug'):
		self.logger = logger
		## Normalize and set the flag for whether we plan to report messages
		self.flag = False
		if flag is True or str(flag) == '1' or re.search('true', str(flag), re.I):
			self.flag = True
		## Normalize and set the logger level
		self.function = self.reportToDebug
		if level.lower() == 'info':
			self.function = self.reportToInfo
		elif level.lower() == 'error':
			self.function = self.reportToError

	def setFlag(self, flag=True):
		self.flag = False
		if flag is True or str(flag) == '1' or re.search('true', str(flag), re.I):
			self.flag = True

	def report(self, *msg, **msgArgs):
		if self.flag:
			self.function(*msg, **msgArgs)

	def reportToDebug(self, *msg, **msgArgs):
		self.logger.debug(*msg, **msgArgs)

	def reportToInfo(self, *msg, **msgArgs):
		self.logger.info(*msg, **msgArgs)

	def reportToError(self, *msg, **msgArgs):
		self.logger.error(*msg, **msgArgs)

	## Regular functions that always log; here to avoid passing 2 loggers around
	def info(self, *msg, **msgArgs):
		self.logger.info(*msg, **msgArgs)

	def debug(self, *msg, **msgArgs):
		self.logger.debug(*msg, **msgArgs)

	def warn(self, *msg, **msgArgs):
		self.logger.warn(*msg, **msgArgs)

	def error(self, *msg, **msgArgs):
		self.logger.error(*msg, **msgArgs)


class sectionedStringToIterableObject:
	"""Transform a sectioned string result set into iterable object.

	For example, the executeProductQueryViaVBScript function in this package
	returns output like the following:
	  -=-==-=-==-=-==-=-
	  Microsoft Visual C++ 2015 x86 Additional Runtime - 14.0.24215
	  14.0.24215
	  vc_runtimeAdditional_x86.msi
	  -=-==-=-==-=-==-=-
	  Microsoft VC++ redistributables repacked.
	  12.0.0.0
	  ME_VCRedistx64.msi
	  -=-==-=-==-=-==-=-
	  ...

	This class takes the above string output delimited by carriage returns and
	the custom section demarcation (seen as '-=-==-=-==-=-==-=-' in the sample
	above), and converts it into an iterable object where we can reference data
	in each section via their numerical index value (1, 2, 3).

	Both delimitedStringToIterableObject and sectionedStringToIterableObject
	classes are setup to create the same type of iterable object from different
	formatted raw strings; this enables all content scripts to manipulate the
	PowerShell output the same, even though it was returned quite differently.
	"""
	def __init__(self, resultAsString, sectionDemarcation):
		self.resultAsList = []
		if resultAsString is not None:
			self.resultAsList = re.split(sectionDemarcation + '\r*\n', resultAsString)
		self.resultIndex = 0
		## Initialize the section iterator
		self.resultLines = []

	def next(self):
		## Return boolean value so we can use .next() in a simple while loop
		self.resultIndex = self.resultIndex + 1
		if self.resultIndex < len(self.resultAsList):
			self.resultLines = self.resultAsList[self.resultIndex].split('\n')
			return True
		else:
			return False

	def reset(self):
		self.resultIndex = 0

	def getString(self, row):
		value = None
		with suppress(Exception):
			value = self.resultLines[row-1].strip()
		return value

	def getInt(self, row):
		value = None
		with suppress(Exception):
			value = int(self.resultLines[row-1].strip())
		return value

	## end class sectionedStringToIterableObject


class delimitedStringToIterableObject:
	"""Transform a delimited string result set into iterable object.

	For example, the executeProductQueryViaWMI function in this package
	returns output like the following:

	  Microsoft Visual C++ 2015 x86 Additional Runtime - 14.0.24215:==:14.0.24215:==:vc_runtimeAdditional_x86.msi
	  Microsoft VC++ redistributables repacked.:==:12.0.0.0:==:ME_VCRedistx64.msi
	  Python 3.6.1 Core Interpreter (64-bit):==:3.6.1150.0:==:core.msi
	  ...

	This class takes the above string output delimited by a custom delimiter
	(seen as :==: above) and carriage returns for section demarcation, and
	converts it into an iterable object where we can reference data in each
	section via their numerical index value (1, 2, 3).

	Both delimitedStringToIterableObject and sectionedStringToIterableObject
	classes are setup to create the same type of iterable object from different
	formatted raw strings; this enables all content scripts to manipulate the
	PowerShell output the same, even though it was returned quite differently.
	"""
	def __init__(self, resultAsString, delimiter='|', sectionDemarcation='\r*\n'):
		self.resultAsList = []
		self.delimiter = delimiter
		if resultAsString is not None:
			self.resultAsList = re.split(sectionDemarcation, resultAsString)
		self.resultIndex = 0
		## Initialize the section iterator
		self.resultLines = []

	def next(self):
		## Return boolean value so we can use .next() in a simple while loop
		self.resultIndex = self.resultIndex + 1
		if self.resultIndex < len(self.resultAsList):
			self.resultLines = self.resultAsList[self.resultIndex].split(self.delimiter)
			return True
		else:
			return False

	def reset(self):
		self.resultIndex = 0

	def getString(self, row):
		value = None
		with suppress(Exception):
			value = self.resultLines[row-1].strip()
		return value

	def getInt(self, row):
		value = None
		with suppress(Exception):
			value = int(self.resultLines[row-1].strip())
		return value

	## end class delimitedStringToIterableObject


def splitAndCleanList(dataAsString, dataAsList):
	"""Helper function for parameter parsing."""
	for entry in dataAsString.split(','):
		with suppress(Exception):
			dataAsList.append(entry.strip())


def scrubQuotation(log, quotedList):
	"""Clean quoted strings formatted by the Select-Object cmdlet."""
	cleanList = []
	for entry in quotedList:
		try:
			newEntry = entry
			m = re.search('^\s*\"(.*)\"\s*$', entry)
			if m:
				newEntry = m.group(1).strip()
			newEntry = newEntry.replace('""', '"')
			cleanList.append(newEntry)
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			log.error('Exception in scrubQuotation: {stacktrace!r}', stacktrace=stacktrace)
			cleanList.append(entry)

	## end scrubQuotation
	return cleanList


def scrubQuotationFromDelimitedString(runtime, resultSet, separator='|'):
	"""Remove quotation around individual entries on the delimited line.

	For example, when using 'ConvertTo-CSV' to format PowerShell results, like
	in the executeProductQueryViaWMI function, the output is like the following:

	  "Microsoft Visual C++ 2015 x86 Additional Runtime - 14.0.24215":==:"14.0.24215":==:"vc_runtimeAdditional_x86.msi"
	  "Microsoft VC++ redistributables repacked.":==:"12.0.0.0":==:"ME_VCRedistx64.msi"
	  "Python 3.6.1 Core Interpreter (64-bit)":==:"3.6.1150.0":==:"core.msi"
	  ...

	The purpose of this function is to break it apart, strip the quotes, and
	put the line back together as a string. This redundancy is not usually
	necessary, and can be avoided by using '-join' instead of 'ConvertTo-CSV'.
	"""
	resultList = verifyOutputLines(runtime, resultSet)
	cleanResult = ""
	for result in resultList:
		try:
			## Split on delimiters and pull off the quotes
			newEntry = scrubQuotation(runtime, result.split(separator))
			## Rebuild the string based off the cleaned list
			newString = separator.join(map(str, newEntry))
			## Concatenate this onto the end of the resultSet
			cleanResult = concatenate(cleanResult, newString, '\n')
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			log.error('Exception in scrubQuotationFromDelimitedString: {stacktrace!r}', stacktrace=stacktrace)

	## end scrubQuotationFromDelimitedString
	return cleanResult


def concatenate(*args):
	"""Concatenate provided objects."""
	try:
		return ''.join(map(str,args))
	except:
		try:
			longString = ""
			for entry in args:
				entry = safeStr(entry)
				longString = longString + entry
			return longString
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			raise OSError(stacktrace)
	return None


def safeStr(obj):
	"""Return the string or unicode representation of an object."""
	try:
		return str(obj)
	except UnicodeEncodeError:
		# obj is unicode
		return unicode(obj).encode('unicode_escape')
	except:
		return obj.encode('utf8', ignore)


def loadJsonIgnoringComments(text, **kwargs):
	"""Ignore comment lines, allowing JSON config file to be self-documented."""
	lines = text.split('\n')
	cleanLines = []
	for line in lines:
		if not re.search(r'^\s*#.*$', line):
			cleanLines.append(line)
	try:
		return json.loads('\n'.join(cleanLines), **kwargs)
	except Exception:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		raise OSError(stacktrace)

	## end loadJsonIgnoringComments
	return


def verifyOutputLines(runtime, outputString):
	"""Split string output into lines."""
	outputLines = None
	if (re.search('\n', outputString)):
		outputLines = outputString.split('\n')
		runtime.logger.report('verifyOutputLines: splitting on \\n')
	elif (re.search('\r', outputString)):
		outputLines = outputString.split('\r')
		runtime.logger.report('verifyOutputLines: splitting on \\r')
	else:
		runtime.logger.report('verifyOutputLines: Expected multi-lined output, but receive the following: {output!r}', output=outputString)

	## end verifyOutput
	return outputLines


def cleanInstallLocation(runtime, client, pathName):
	"""Remove args from the Path/Process and resolve 8dot3 paths."""
	cleanPath = None
	try:
		if (pathName is None or len(pathName) <= 0):
			return None

		cleanPath = pathName
		## If the pathName is in the newer (long) format, with spaces, it
		## will be double quoted around the executable, prior to the args:
		m1 = re.search('^\s*"([^"]+)"', pathName)
		if m1:
			cleanPath = m1.group(1)

		## If the pathName is in the 8dot3 (short) format, without spaces,
		## look for the first space delimiter (quotes are resolved above):
		m2 = re.search('^\s*(\S+\~\S+)', cleanPath)
		if m2:
			(updatedPath, stdError, hitProblem) = resolve8dot3Name(log, client, m2.group(1))
			if updatedPath is not None:
				runtime.logger.report('  Conversion returned path: {resolvedPath!r}', resolvedPath=updatedPath.encode('unicode-escape'))
				if updatedPath != path and not hitProblem:
					runtime.logger.report('  Windows Process has updated path. Old value: {oldPath!r}, New value: {updatedPath!r}', oldPath=cleanPath, updatedPath=updatedPath)
					cleanPath = updatedPath

		## Debug print
		if (cleanPath and cleanPath != pathName):
			runtime.logger.report('   --> Path before cleaning: {pathName!r}', pathName=pathName)
			runtime.logger.report('   --> Path after cleaning : {cleanPath!r}', cleanPath=cleanPath)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in cleanInstallLocation: {stacktrace!r}', stacktrace=stacktrace)

	## end cleanInstallLocation
	return cleanPath


def resolve8dot3Name(runtime, client, path):
	"""Resolve Windows 8dot3 path into the full version."""
	try:
		if (path is not None and len(path) > 1 and path.strip() != 'null'):
			## Remove enclosing quotation
			m = re.search('^\s*\"(.*)\"\s*$', path)
			if m:
				path = m.group(1)
			## Resolve 8dot3 names (short names) into long names...
			##   e.g. c:\PROGRA~2 --> c:\Program Files (x86)
			if (re.search('\~', path)):
				encodedPath = path.encode('unicode-escape').decode('utf8')
				resolveCmd = '{}{}{}{}{}'.format(r'$tmp=""; if (Test-Path "', encodedPath, r'") {$tmp=(get-item "', encodedPath, r'").FullName}; $tmp')
				runtime.logger.report('  Trying 8dot3 conversion on: {pathToResolve!r}', pathToResolve=encodedPath)
				runtime.logger.report('     command: {resolveCmd!r}', resolveCmd=resolveCmd)
				return(client.run(resolveCmd, 10))
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in resolve8dot3Name: {stacktrace!r}', stacktrace=stacktrace)

	## end resolve8dot3Name
	return (path, None, False)


def loadConfigGroupFile(env, fileName='configDefault.json'):
	"""Get the shared OS level parameters."""
	configParametersFile = os.path.join(env.contentGatheringSharedConfigGroupPath, fileName)
	text = ''
	with open(configParametersFile) as fp:
		text = fp.read()

	## end loadConfigGroupFile
	return(loadJsonIgnoringComments(text))


def getOsParameters(env):
	"""Get the shared OS level parameters."""
	return(loadConfigGroupFile(env, fileName='osParameters.json'))


def updateCommand(runtime, cmdString, shellParameters=None):
	"""Check config parameters to see if we should modify command."""
	try:
		runtime.logger.report(' updateCommand function: Original command: {cmdString!r}', cmdString=cmdString)
		## Pull variables from runtime
		osType = runtime.endpoint.get('data').get('node_type')
		## All jobs after the Find job, shellParameters will exist; if the Find
		## job needs to update the command (e.g. dmidecode), then send these in
		if shellParameters is None:
			shellParameters = runtime.endpoint.get('data').get('parameters')
		if shellParameters is None:
			raise EnvironmentError('No Shell parameters found for this endpoint; unable to update any command.')
		#runtime.logger.report(' updateCommand: endpoint data: {data!r}', data=runtime.endpoint.get('data'))
		#runtime.logger.report(' updateCommand: shellParameters: {shellParameters!r}', shellParameters=shellParameters)
		commandsToTransform = shellParameters.get('commandsToTransform', [])
		## This is used for directing sudo on commands with cron jobs
		avoidTTYsudoRequirement = shellParameters.get('avoidTTYsudoRequirement', False)
		## Use sudo (or another elevated access utility) for desired commands
		elevatedCommandUtility = shellParameters.get('elevatedCommandUtility', 'sudo')
		## If the elevated utility was defined in commandsToTransform, it means
		## different OS instances may use different utilities. So now we use the
		## utility that was found on this particular endpoint via the find job.
		if elevatedCommandUtility in commandsToTransform:
			elevatedCommandUtility = commandsToTransform[elevatedCommandUtility]
		commandsToRunWithElevatedAccess = shellParameters.get('commandsToRunWithElevatedAccess', [])
		## Set of commands to run on lower priority to avoid system interruption
		lowPriorityCommandUtility = shellParameters.get('lowPriorityCommandUtility', 'nice')
		commandsToRunOnLowPriority = shellParameters.get('commandsToRunOnLowPriority', [])
		lowPriorityForAllCommands = shellParameters.get('lowPriorityOnAllCommands', False)

		## Section for command transformation (eg. 'ls' --> '/bin/ls')
		cmdList = cmdString.split(' ')
		commandAlias = cmdList[0]
		## Ignore errors when key doesn't exist; this just means not to replace
		with suppress(KeyError):
			cmdList[0] = commandsToTransform[commandAlias]

		## Section for elevated access utility (e.g. sudo)
		if commandAlias in commandsToRunWithElevatedAccess:
			## Simple safety nets (may add more or remove this check entirely)
			if (commandAlias == 'cat' and re.search('>', cmdString)):
				## Preventing security vulnerability with output redirection
				runtime.logger.report(' updateCommand function: Requesting to use sudo for command that contains redirection; request is DENIED.  Command: {cmdString!r}', cmdString=cmdString)
			elif (not avoidTTYsudoRequirement):
				newCommand = elevatedCommandUtility + ' ' + cmdList[0]
				cmdList[0] = newCommand
			else:
				## If sudo is required for a cron job, you need to enable the
				## requiretty setting or it fails with the following message you
				## will find in the app user's mail:
				##   "sudo: sorry, you must have a tty to run sudo"
				## By default, cron will not work with sudo without first
				## setting the requiretty... so I'm going to use a different
				## method that avoids TTY for that use case:
				cmdString = ' '.join(cmdList)
				cmdString = concatenate('su root -c "', cmdString, '"')
				## Have to look at nice here as well, because the whole
				## su command must be escaped to avoid double quote mixup
				if (lowPriorityForAllCommands or (commandAlias in commandsToRunOnLowPriority)):
					cmdString = lowPriorityCommandUtility + ' ' + cmdString
				runtime.logger.report(' updateCommand function: Updated command : {cmdString!r}', cmdString=cmdString)
				return cmdString

		## Section for background/low priority utility (e.g. nice)
		if (lowPriorityForAllCommands or (commandAlias in commandsToRunOnLowPriority)):
			newCommand = lowPriorityCommandUtility + ' ' + cmdList[0]
			cmdList[0] = newCommand

		## Reconstruct the command with the rest of the previous arguments
		cmdString = ' '.join(cmdList)
		runtime.logger.report(' updateCommand function: Updated command : {cmdString!r}', cmdString=cmdString)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in updateCommand: {stacktrace!r}', stacktrace=stacktrace)

	## end updateCommand
	return cmdString


def grep(text, matchString):
	"""Works like a Unix grep... search text for the matchString."""
	result = ''
	compiled = re.compile('(.*' + matchString + '.*)', re.I)
	matches = compiled.findall(text)
	for match in matches:
		result = result + match + '\n'

	## end grep
	return result


def AlignSlashesInDirectoryPath(initialPath, osType):
	"""Align all delimiter slashes in directory."""
	modifiedPath = initialPath
	try:
		if (osType == 'Windows'):
			seperator = '\\'
			tmpPath = None
			tmpString = initialPath.split("/") or None
			if (tmpString != None):
				for piece in tmpString:
					if (tmpPath == None):
						tmpPath = piece
					else:
						tmpPath = concatenate(tmpPath, seperator, piece)
				modifiedPath = tmpPath
		else:
			## Ensure the path is uniform for Unix
			seperator = '/'
			tmpPath = None
			tmpString = initialPath.split("\\") or None
			if (tmpString != None):
				for piece in tmpString:
					if (tmpPath == None):
						tmpPath = piece
					else:
						tmpPath = concatenate(tmpPath, seperator, piece)
				modifiedPath = tmpPath
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in AlignSlashesInDirectoryPath on path {initialPath!r}: {stacktrace!r}', initialPath=initialPath, stacktrace=stacktrace)

	## end AlignSlashesInDirectoryPath
	return modifiedPath


def ReplaceCharactersInStrings(initialString, searchFor, replaceWith):
	"""Utility to search for and replace chars in a string."""
	try:
		modifiedString = initialString
		tmpList = initialString.split(searchFor) or None
		if (tmpList != None):
			tmpString = None
			for piece in tmpList:
				if (tmpString == None):
					tmpString = piece
				else:
					tmpString = concatenate(tmpString, replaceWith, piece)
			modifiedString = tmpString
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in ReplaceCharactersInStrings on initialString {initialString!r}: {stacktrace!r}', initialString=initialString, stacktrace=stacktrace)

	## end ReplaceCharactersInStrings
	return modifiedString


def addObjectIfNotExists(runtime, className, uniqueId=None, **kwargs):
	"""If the same object was previously created, return that object.

	You probably want to use the default 'checkExisting' functionality enabled
	in results.addObject, instead of this utilities function. By default the
	results.addObject method calls findExistingObject that specifically uses
	unique constraints on object types, instead of comparing all attributes.

	This function is a simple json comparison, which encounters two problems:
	1) attributes like 'time_gathered' will exist on previously created objects,
	   but wouldn't be there on new objects, or match objects with newer times.
	2) Even when the data sets aren't identical, it may be the same object. If
	   there is a value difference on an optional attribute, it doesn't matter.
	   We only need to compare values on attributes setup in unique constraints;
	   we shouldn't compare optional attributes.

	But that said, this is still a convenience method for scripts that really
	want to compare objects constructed within their control.

	Arguments:
	  className (str) : BaseObject class name
	  uniqueId (str)  : String containing identifier
	  kwargs (dict)   : Data on this object
	"""
	for thisObject in runtime.results.getObjects():
		if thisObject.get('class_name') != className:
			continue
		if uniqueId is not None:
			if thisObject.get('identifier') == uniqueId:
				return (True, thisObject.get('identifier'))
		else:
			skip = False
			thisData = thisObject.get('data', {})
			if len(kwargs) != len(thisData):
				skip = True
			else:
				for name, value in kwargs.items():
					if thisData.get(name) != value:
						skip = True
						break
			if not skip:
				runtime.logger.report('addObjectIfNotExists: FOUND a previous {className!r} object with id {thisId!r}', className=className, thisId=thisObject.get('identifier'))
				return (True, thisObject.get('identifier'))

	## Don't use 'checkExisting' in addObject; we used a custom version above
	thisId, exists = runtime.results.addObject(className, uniqueId=uniqueId, checkExisting=False, **kwargs)
	runtime.logger.report('addObjectIfNotExists: CREATED a new {className!r} object with id {thisId!r}: {kwargs!r}', className=className, thisId=thisId, kwargs=kwargs)

	## end addObjectIfNotExists
	return (False, thisId)


def addObject(runtime, className, uniqueId=None, **kwargs):
	"""Add an object onto the result set.

	Convenience method for folks wanting to see less OOP in content scripts.
	"""
	return (runtime.results.addObject(className, uniqueId=uniqueId, **kwargs))


def addLink(runtime, className, firstId, secondId):
	"""Add a link connecting two objects on the result set.

	Convenience method for folks wanting to see less OOP in content scripts.
	"""
	return (runtime.results.addLink(className, firstId, secondId))


def addIp(runtime, **kwargs):
	"""Verify and add an IP object onto the result set.

	Convenience method for folks wanting to see less OOP in content scripts.
	"""
	return (runtime.results.addIp(**kwargs))



def determineCommandsToTransform(runtime, client, endpoint, myParameters, osParameters=None):
	"""Determine which commands to transform and test.

	The purpose is to find the specific set of commands that work on this
	particular OS instance, and then store those for future use in scripts.
	"""
	newParameters = { "commandsToTransform": {} }
	try:
		runtime.logger.report('determineCommandsToTransform on: {endpoint!r}', endpoint=endpoint)
		runtime.logger.report('   myParameters: {myParameters!r}', myParameters=myParameters)
		commandsToTransform = myParameters.get('commandsToTransform', {})
		commandsToRunWithElevatedAccess = []
		elevatedCommandUtility = None
		if osParameters is not None:
			runtime.logger.report('   osParameters: {osParameters!r}', osParameters=osParameters)
			commandsToTransform = osParameters.get('commandsToTransform', {})
			commandsToRunWithElevatedAccess = osParameters.get('commandsToRunWithElevatedAccess', [])
			elevatedCommandUtility = osParameters.get('elevatedCommandUtility')

		runtime.logger.report('   commandsToTransform: {commandsToTransform!r}', commandsToTransform=commandsToTransform)
		runtime.logger.report('   commandsToRunWithElevatedAccess: {commandsToRunWithElevatedAccess!r}', commandsToRunWithElevatedAccess=commandsToRunWithElevatedAccess)
		for alias in commandsToTransform:
			runtime.logger.report('====> working on alias {alias!r} : {aliasData!r}', alias=alias, aliasData=commandsToTransform[alias])
			replacementList = commandsToTransform.get(alias).get('replacementList', [])
			testCmd = commandsToTransform.get(alias).get('testCmd')
			testOutput = commandsToTransform.get(alias).get('testOutput')
			matchedCommand = None
			for replacementCmd in replacementList:
				if testCmd is None:
					## When no testCmd is provided; assume the command is good
					matchedCommand = replacementCmd
					break

				m = re.search('(.*)\<cmd\>(.*)', testCmd, re.I)
				if not m:
					runtime.logger.report('  testCmd {testCmd!r} does NOT contain <cmd> string for replacement; skipping.', testCmd=testCmd)
					continue

				testCmdWithArgs = m.group(1) + replacementCmd + m.group(2)

				## Section for applying elevated access (e.g. sudo)
				if alias in commandsToRunWithElevatedAccess:
					runtime.logger.report('  commandsToTransform: elevating test on command {alias!r}', alias=alias)
					testCmdWithArgs = elevatedCommandUtility + ' ' + testCmdWithArgs
					#replacementCmd = elevatedCommandUtility + ' ' + replacementCmd

				## Run replacement command
				try:
					runtime.logger.report('  running testCmd: {testCmdWithArgs!r}', testCmdWithArgs=testCmdWithArgs)
					(stdOut, stdError, hitProblem) = client.run(testCmdWithArgs, 5)
					runtime.logger.report('  testCmd returned: {stdOut!r}', stdOut=stdOut)
					## Check shell command exit status to ensure success
					if hitProblem:
						continue

					## Validate output if testOutput was provided
					if testOutput is None:
						matchedCommand = replacementCmd
						break

					m = re.search(testOutput, stdOut, re.I)
					if m:
						matchedCommand = replacementCmd
						break
					runtime.logger.report('  testOutput does NOT match {testOutput!r}; skipping.', testOutput=testOutput)
				except:
					stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					runtime.logger.error('Exception in determineCommandsToTransform: {stacktrace!r}', stacktrace=stacktrace)

			## Track alias-->command mapping that was available and successful
			if matchedCommand is not None:
				newParameters['commandsToTransform'][alias] = matchedCommand

		## Update the parameters to reflect the commands determined here
		runtime.logger.report('  updated parameters: {newParameters!r}', newParameters=newParameters)
		updateParameters(myParameters, newParameters)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in determineCommandsToTransform: {stacktrace!r}', stacktrace=stacktrace)

	## end determineCommandsToTransform
	return


def compareValue(runtime, thisValue, operator, value):
	try:
		if operator == '==':
			return thisValue == value
		elif operator == "!=":
			return thisValue != value
		elif operator == '>':
			return thisValue > value
		elif operator == ">=":
			return thisValue >= value
		elif operator == '<':
			return thisValue < value
		elif operator == "<=":
			return thisValue <= value
		elif operator.lower() == 'isnull':
			return thisValue is None
		elif operator.lower() == 'equal':
			return str(thisValue) == str(value)
		elif operator.lower() == 'iequal':
			return str(thisValue).lower() == str(value).lower()
		elif operator.lower() == 'regex':
			return re.search(value, thisValue)
		elif operator.lower() == 'iregex':
			return re.search(value, thisValue, re.I)

	except:
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in compareValue: {exception!r}', exception=exception)

	## end compareValue
	return False


def checkCondition(runtime, className, classAttribute, operator, value, objectList):
	for thisObject in objectList:
		thisClass = thisObject.get('class_name')
		if thisClass == className:
			objectData = thisObject.get('data', {})
			if classAttribute in objectData:
				thisValue = objectData.get(classAttribute)
				runtime.logger.report('Comparing object {className!r}.{classAttribute!r}:  {thisValue!r} {operator!r} {value!r}', className=className, classAttribute=classAttribute, thisValue=thisValue, operator=operator, value=value)
				success = compareValue(runtime, thisValue, operator, value)
				if success:
					runtime.logger.report('Comparing object successful.')
					return True
				## Don't break out here; might have multiple objects of the same
				## type on the result (e.g. multiple IPs); need to each one...

	## end checkCondition
	return False


def recurseExpressions(runtime, expression, objectList):
	success = False
	operator = expression.get('operator', 'and')
	negation = expression.get('negation', False)
	subExpression = expression.get('expression')
	subCondition = expression.get('condition')
	if subExpression is not None:
		## setup and recurse
		for entry in subExpression:
			success = recurseExpressions(runtime, entry, objectList)
			## Just break out of the loop when hitting one of the following:
			##  * the first 'true' result while processing an 'or' condition
			##  * the first 'false' result while processing an 'and' condition
			if (operator == 'or' and success) or (operator == 'and' and not success):
				return success
	elif subCondition is not None:
		className = subCondition.get('class_name')
		classAttribute = subCondition.get('attribute')
		operator = subCondition.get('operator')
		value = subCondition.get('value')
		success = checkCondition(runtime, className, classAttribute, operator, value, objectList)

	## end recurseExpressions
	return success


def getConfigGroup(runtime, myParameters, configGroups):
	matchedGroup = 'default'
	objectList = runtime.results.getObjects()
	for configGroup in configGroups:
		foundMatch = recurseExpressions(runtime, configGroup.get('matchCriteria', {}), objectList)
		if foundMatch:
			matchedGroup = configGroup.get('name', 'default')
			runtime.logger.report('getConfigGroup: matched configGroup {matchedGroup!r}', matchedGroup=matchedGroup)
			break

	## end getConfigGroup
	return matchedGroup


def updateParameters(currentParameters, newParameters, skipParameters=[]):
	"""Override/Update current parameters with new parameters."""
	for param in newParameters:
		if param in skipParameters:
			continue
		thisEntry = newParameters[param]
		if isinstance(thisEntry, (list, set, tuple, dict)):
			thisCopy = copy.deepcopy(thisEntry)
			currentParameters[param] = thisCopy
		else:
			currentParameters[param] = thisEntry

	## end updateParameters
	return


def upsertParameters(currentParameters, newParameters, skipParameters=[]):
	"""Insert/Update new parameters into current parameters."""
	for param in newParameters:
		if param in skipParameters:
			continue
		thisEntry = newParameters[param]
		if isinstance(thisEntry, (list, dict)):
			## If current params do not have this entry, create new deep copy
			if currentParameters.get(param) is None:
				thisCopy = copy.deepcopy(thisEntry)
				currentParameters[param] = thisCopy
			## Otherwise we need to update each entry separately
			elif type(thisEntry) != type(currentParameters[param]):
				raise TypeError('Types do not match for updating parameters. 1) {}:{}  2){}:{}.'.format(type(thisEntry), thisEntry, type(currentParameters[param], currentParameters[param])))
			elif isinstance(thisEntry, list):
				for entry in thisEntry:
					currentParameters[param].append(entry)
			elif isinstance(thisEntry, dict):
				for entry,value in thisEntry.items():
					currentParameters[param][entry] = value
			else:
				## Unnecessary: will never get here
				raise TypeError('upsertParameters cannont handle type: {}'.format(type(thisEntry)))
		else:
			currentParameters[param] = thisEntry

	## end upsertParameters
	return


def getInstanceParameters(runtime, client, osType, endpoint, myParameters):
	"""Get configurations for this specific OS instance.

	Assign alias-to-command mapping on this OS instance, which isn't generalized
	on the OS type. For example, on older CentOS builds you can use netstat, but
	on newer builds that library is not available by default. On newer builds we
	can use ss by default, or choose lsof if that's deployed. But each of these
	parameters are specific to each OS instance, which is different from those
	per OS type (in osParameters.json) or global settings (in configDefault.json)
	or settings per configuration group (in configGroups.json).
	"""
	try:
		## Set the OS type in case the endpoint query doesn't have the context
		myParameters['osType'] = osType
		## Get necessary parameters
		shellConfig = runtime.shellConfig
		osParameters = shellConfig.get('osParameters', {}).get(osType, {})
		myParameters['commandsToRunWithElevatedAccess'] = osParameters.get('commandsToRunWithElevatedAccess', [])

		## Resolve the entries in a commandsToTransform section (find which
		## command, path, elevated utility, etc, to use on this OS instance);
		## determine this in the initial shell detection job only.
		runtime.logger.report('getInstanceParameters1 for {osType!r}: {myParameters!r}', osType=osType, myParameters=myParameters)
		determineCommandsToTransform(runtime, client, endpoint, myParameters, osParameters)
		runtime.logger.report('getInstanceParameters2 for {osType!r}: {myParameters!r}', osType=osType, myParameters=myParameters)

	except:
		runtime.setError(__name__)

	## end getInstanceParameters
	return


def setInstanceParameters(runtime, protocolId, myParameters):
	"""Set configurations for this specific OS instance."""
	try:
		## Get necessary parameters
		shellConfig = runtime.shellConfig
		configGroups = shellConfig.get('configGroups', {})
		## Set the config group name
		myParameters['configGroup'] = getConfigGroup(runtime, myParameters, configGroups)
		runtime.logger.report('getInstanceParameters config group: {matchedGroup!r}', matchedGroup=myParameters['configGroup'])

		## Now store the customized set of parameters for this shell, which will
		## be leveraged by shell-based jobs hitting this endpoint moving forward
		runtime.logger.report('setParameters: results: {results!r}', results=runtime.results.getJson())
		runtime.logger.report('setParameters: protocolId: {protocolId!r}', protocolId=protocolId)
		runtime.results.updateObject(protocolId, config_group=myParameters['configGroup'], parameters=myParameters)

	except:
		runtime.setError(__name__)

	## end setInstanceParameters
	return


def compareFilter(method, compareString, thisValue):
	"""Conditionally use equal vs regEx compare methods."""
	if method == '==':
		if str(compareString) == str(thisValue):
			return True
	elif re.search(compareString, thisValue, re.I):
		return True
	return False


def requestsRetrySession(retries=5, backoff_factor=0.3, status_forcelist=(500, 501, 502, 503, 504)):
	"""Retry a request by supplying parameters to urllib3 Retry."""
	session = requests.Session()
	retry = Retry(total=retries, read=retries, connect=retries, backoff_factor=backoff_factor, status_forcelist=status_forcelist)
	adapter = HTTPAdapter(max_retries=retry)
	session.mount('http://', adapter)
	session.mount('https://', adapter)
	return session


def getApiResult(runtime, resourcePath, method, customHeaders=None, customPayload=None, verify=False):
	"""Get API result set.

	Services will have the API data in the runtime.jobSettings location, whereas
	the Clients will have it in runtime.jobMetaData.
	"""
	apiInfo = None
	apiResponse = None
	try:
		apiInfo = runtime.jobMetaData
	except:
		apiInfo = runtime.jobSettings

	## Create the REST API resource path (root context plus provided path)
	baseUrl = apiInfo.get('apiContext', {}).get('url')
	url = '{}/{}'.format(baseUrl, resourcePath)

	## Create default headers
	headers = apiInfo.get('apiContext', {}).get('headers', {}).copy()
	headers['Content-Type'] = 'application/json'

	## Insert any custom headers provided from parameters
	if customHeaders is not None and isinstance(customHeaders, dict):
		for entry,value in customHeaders.items():
			## Need to manually convert numerical (and bool) header values to
			## string values, in order for the requests library to accept them.
			if isinstance(value, int):
				value = str(value)
			headers[entry] = value

	baseContext = {}
	## Insert any custom payload provided from parameters
	if customPayload is not None and isinstance(customPayload, dict):
		for entry,value in customPayload.items():
			baseContext[entry] = value
	payload = json.dumps(baseContext)

	## Execute the query
	runtime.logger.report(' Sending {method!r} to URL {url!r}', method=str(method).upper(), url=url)
	if method.lower() == 'get':
		apiResponse = requestsRetrySession().get(url, data=payload, headers=headers, verify=verify)
	elif method.lower() == 'post':
		apiResponse = requestsRetrySession().post(url, data=payload, headers=headers, verify=verify)
	elif method.lower() == 'put':
		apiResponse = requestsRetrySession().put(url, data=payload, headers=headers, verify=verify)
	elif method.lower() == 'delete':
		apiResponse = requestsRetrySession().delete(url, data=payload, headers=headers, verify=verify)
	else:
		raise NotImplementedError('getApiResult works with get/post/delete, but not {}'.format(method))

	## end getApiResult
	return apiResponse


def loopThroughApiQueryResults(runtime, queryId, totalChunks, queryResults, verify=False):
	## Loop through the chunks and build the full dataset
	try:
		for chunkId in range(1, totalChunks+1):
			resourcePath = 'query/cache/{}/{}'.format(queryId, chunkId)
			method = 'get'
			responseAsJson = None
			apiResponse = getApiResult(runtime, resourcePath, method, verify=verify)
			with suppress(Exception):
				responseCode = apiResponse.status_code
				responseAsJson = json.loads(apiResponse.text)
			if str(responseCode) == '204':
				runtime.logger.report('Chunk not available: ', responseAsJson=responseAsJson)
				break
			elif str(responseCode) == '200':
				totalChunks = responseAsJson.get('chunk_count', 0)
				if len(responseAsJson) > 0:
					upsertParameters(queryResults, responseAsJson)
				else:
					runtime.logger.report('Response empty, nothing to do.')
			else:
				runtime.logger.warn('Unexpected query response in loopThroughApiQueryResults. Status: {responseCode!r}. Payload: {responseAsJson!r}', responseCode=responseCode, responseAsJson=responseAsJson)
				break

	except:
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in loopThroughApiQueryResults: {exception!r}', exception=exception)

	## end loopThroughApiQueryResults
	return queryResults


def waitForApiQueryResults(runtime, queryId, maxAttempts=10, waitSecondsBetweenAttempts=3, verify=False):
	queryResults = {}
	## Loop through hitting /<root>/query/cache/id, waiting for the full result set
	resourcePath = 'query/cache/{}'.format(queryId)
	method = 'get'
	for count in range(0, maxAttempts):
		## Sleep between each attempt, and start with a sleep to give the query
		## time to run through kafka and into the queryService for processing.
		runtime.logger.report('Waiting {sec!r} seconds between query attempts to allow request to be fed through kafka and into Query service for processing', sec=waitSecondsBetweenAttempts)
		time.sleep(waitSecondsBetweenAttempts)
		## Issue an API query to check status on the cached result
		responseAsJson = None
		responseCode = None
		apiResponse = getApiResult(runtime, resourcePath, method, verify=verify)
		with suppress(Exception):
			responseCode = apiResponse.status_code
			responseAsJson = json.loads(apiResponse.text)
		if str(responseCode) == '204':
			runtime.logger.report('Query result is not yet stubbed: ', responseAsJson=responseAsJson)
		elif str(responseCode) == '200':
			runtime.logger.report('API query result: {responseAsJson!r}', responseAsJson=responseAsJson)
			totalChunks = responseAsJson.get('chunk_count', 0)
			if totalChunks <= 0:
				runtime.logger.report('Query result is being processed: {responseAsJson!r}', responseAsJson=responseAsJson)
			else:
				runtime.logger.report('Query result is complete. Contains {totalChunks!r} chunks: {responseAsJson!r}', totalChunks=totalChunks, responseAsJson=responseAsJson)
				loopThroughApiQueryResults(runtime, queryId, totalChunks, queryResults)
			break
		else:
			runtime.logger.warn('Unexpected query response in waitForApiQueryResults. Status: {responseCode!r}. Payload: {responseAsJson!r}', responseCode=responseCode, responseAsJson=responseAsJson)

	## Cleanup the cached result set
	runtime.logger.report('Cleaning up cached query results for: {queryId!r}', queryId=queryId)
	apiResponse = getApiResult(runtime, resourcePath, 'delete', verify=verify)

	## end waitForApiQueryResults
	return queryResults


def getApiQueryResultsInChunks(runtime, queryContent, resultsFormat='Flat', headers=None, verify=False):
	"""Request an API query to be cached/chunked and then retrieved."""
	queryResults = None
	if len(str(queryContent)) <= 1:
		raise TypeError('Invalid API query: {}'.format(queryContent))

	## Customize the request and query the API
	resourcePath = 'query/cache'
	method = 'post'
	customHeaders = {}
	if headers is not None:
		customHeaders = headers
	customHeaders['contentDeliveryMethod'] = 'chunked'
	customHeaders['contentDeliverySize'] = 1
	customHeaders['resultsFormat'] = resultsFormat
	customHeaders['removePrivateAttributes'] = True
	customPayload = {}
	customPayload['content'] = queryContent
	## Now issue the query
	apiResponse = getApiResult(runtime, resourcePath, method, customHeaders, customPayload, verify=verify)

	responseCode = None
	responseAsJson = {}
	with suppress(Exception):
		responseCode = apiResponse.status_code
	with suppress(Exception):
		responseAsJson = json.loads(apiResponse.text)

	if responseCode is not None and str(responseCode) == '202':
		responseAsJson = json.loads(apiResponse.text)
		queryId = responseAsJson.get('identifier')
		queryResults = waitForApiQueryResults(runtime, queryId)
	else:
		raise EnvironmentError('Unexpected response from API. Code: {}. Payload: {}'.format(responseCode, responseAsJson))

	## end getApiQueryResultsInChunks
	return queryResults


def getApiQueryResultsFull(runtime, queryContent, resultsFormat='Flat', headers=None, verify=False):
	"""Retrieve a complete API query result set."""
	queryResults = None
	if len(str(queryContent)) <= 1:
		raise TypeError('Invalid API query: {}'.format(queryContent))

	## Customize the request and query the API
	resourcePath = 'query/this'
	method = 'get'
	customHeaders = {}
	if headers is not None:
		customHeaders = headers
	customHeaders['resultsFormat'] = resultsFormat
	customHeaders['removePrivateAttributes'] = True
	customPayload = {}
	customPayload['content'] = queryContent
	## Now issue the query
	apiResponse = getApiResult(runtime, resourcePath, method, customHeaders, customPayload, verify=verify)

	responseCode = None
	responseAsJson = {}
	with suppress(Exception):
		responseCode = apiResponse.status_code
	with suppress(Exception):
		responseAsJson = json.loads(apiResponse.text)

	if responseCode is not None and str(responseCode) == '200':
		queryResults = json.loads(apiResponse.text)
	else:
		raise EnvironmentError('Unexpected response from API. Code: {}. Payload: {}'.format(responseCode, responseAsJson))

	## end getApiQueryResultsFull
	return queryResults


class RealmUtility:
	"""Utility for checking IP inclusion/exclusion from networks in the realm."""
	def __init__(self, runtime, configuredRealmOnly=True):
		self.runtime = runtime
		self.configuredRealmOnly = configuredRealmOnly
		self.scopes = None
		self.ocpCertFile = runtime.ocpCertFile
		self.networkStrings = []
		self.networkObjects = []
		self.getRealmNetworksFromApi()
		self.transformNetworks()

	def getRealmsFromApi(self):
		"""Retrieve all realms from the API."""
		responseCode = None
		## Customize the request and query the API
		apiResponse = getApiResult(self.runtime, 'config/RealmScope', 'get', {}, {}, verify=self.ocpCertFile)
		with suppress(Exception):
			responseCode = apiResponse.status_code
		if str(apiResponse.status_code) == '200':
			with suppress(Exception):
				apiResults = json.loads(apiResponse.text)
				self.scopes = apiResults.get('scopes')
		else:
			raise EnvironmentError('Unexpected response from API. Code: {}. Payload: {}'.format(responseCode, self.scopes))
		## end getApiQueryResultsInChunks
		return

	def getRealmNetworksFromApi(self):
		"""Retrieve the data section of the realm(s), which holds a list of networks."""
		self.getRealmsFromApi()
		if self.scopes is None:
			raise EnvironmentError('No realms found')
		## If looking for the specific realm configured for the job
		if self.configuredRealmOnly:
			targetRealm = self.runtime.jobMetaData.get('realm', 'default')
			for thisRealm in self.scopes:
				if thisRealm.get('realm') == targetRealm:
					for thisNetwork in thisRealm.get('data', []):
						self.networkStrings.append(thisNetwork)
					return
			raise EnvironmentError('Did not find realm {} in results {}'.format(targetRealm, self.scopes))
		## Otherwise we construct a raw listing of all realm networks
		else:
			for thisRealm in self.scopes:
				for thisNetwork in thisRealm.get('data', []):
					self.networkStrings.append(thisNetwork)
		## end getRealmNetworksFromApi
		return

	def transformNetworks(self):
		"""Transform the String list into an ip_network list.

		We don't want to instantiate these on each IP check, which can be 100K
		times in a DNS job. Need to transform once and reference these later.
		"""
		for networkAsString in self.networkStrings:
			thisNetwork = ipaddress.ip_network(networkAsString, False)
			self.networkObjects.append(thisNetwork)
		## end transformNetworks
		return

	def isIpInRealm(self, ipAsString):
		"""Determine if an IP falls within the boundary of the realm networks."""
		ipAsNetwork = ipaddress.ip_network(ipAsString)
		for network in self.networkObjects:
			if network.overlaps(ipAsNetwork):
				return True
		## end isIpInRealm
		return False


def verifyJobRuntimePath(thisFile):
	"""Establish a local directory cache space for a job runtime."""
	jobScriptPath = os.path.dirname(os.path.realpath(thisFile))
	jobRuntimePath = os.path.abspath(os.path.join(jobScriptPath, '..', 'runtime'))
	if not os.path.exists(jobRuntimePath):
		os.mkdir(jobRuntimePath)

	## end verifyJobRuntimePath
	return jobRuntimePath


def cleanupJobRuntimePath(thisFile):
	"""Clean up locally cached contents from a job runtime."""
	jobScriptPath = os.path.dirname(os.path.realpath(thisFile))
	jobRuntimePath = os.path.abspath(os.path.join(jobScriptPath, '..', 'runtime'))
	for thisFile in os.listdir(jobRuntimePath):
		os.remove(os.path.join(jobRuntimePath, thisFile))

	## end verifyJobRuntimePath
	return


def runPortTest(runtime, endpoint, ports=[], timeoutOnAttempt=.5, maxAttempts=2):
	"""Test for specified listener port(s) on target endpoint."""
	for port in ports:
		listener = '{}:{}'.format(endpoint, port)
		runtime.logger.report('runPortTest: endpoint {listener!r}', listener=listener)
		attemptCount = 1
		## Try multiple times in case
		while attemptCount <= maxAttempts:
			attemptCount += 1
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			sock.settimeout(timeoutOnAttempt)
			result = sock.connect_ex((endpoint, port))
			with suppress(Exception):
				sock.close()
			if result == 0:
				runtime.logger.report('runPortTest: endpoint {listener!r} is active', listener=listener)
				return True

	## end runPortTest
	return False


def pingLookup(runtime, client, osType, name):
	"""Resolve name to IP on remote endpoint.

	This method resolves the IP as the server would; not caring about the server
	configured resolution order, local host entries, DNS setup, WINS, etc.
	"""
	ipAddress = None
	command = None
	searchString = None
	try:
		## Set the command and parsing specific to this OS
		if (osType.lower() == 'windows'):
			command = concatenate('ping ', name, ' -n 1 |find /I \"pinging \"')
			##  Pinging hpucmdb01 [10.118.216.12] with 32 bytes of data:
			searchString = concatenate('[Pp]inging ', name, '[^\[]*\[(\S+)\]')
		elif (osType.lower() == 'linux'):
			command = concatenate('ping ', name, ' -c 1')
			##  PING hpucmdb01 (10.118.216.12) 56(84) bytes of data.
			searchString = concatenate('[Pp][Ii][Nn][Gg] ', name, '[^(]+\s*\((\S+)\)')
		else:
			runtime.logger.warn('Function pingLookup does not have parsing for osType {osType!r}.  Supported types: Windows & Linux.', osType=osType)
			return ipAddress

		pingCmd = updateCommand(runtime, command)
		runtime.logger.report('  Running command: {pingCmd!r}', pingCmd=pingCmd)
		(resultString, stdError, hitProblem) = client.run(pingCmd, 10)

		## If nothing returned, don't attempt to parse
		if hitProblem:
			runtime.logger.warn('  pingLookup: Problem executing ping')
			if stdError is not None:
				runtime.logger.error('  pingLookup: Error returned: {stdError!r}', stdError=stdError)
		if resultString is not None:
			## Parse the result
			runtime.logger.report('  Ping output: {resultString!r}', resultString=resultString)
			m = re_search(searchString, resultString, re_I)
			if m:
				ipAddress = m.group(1)
				runtime.logger.report('  pingLookup found IP: {ipAddress!r}', ipAddress=ipAddress)

	except:
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in pingLookup: {exception!r}', exception=exception)

	## end pingLookup
	return ipAddress


def pingable(runtime, client, osType, endpoint):
	"""Attempt a local ping to see if an endpoint (ip/name) responds to ICMP."""
	ipAddress = None
	command = None
	searchString = None
	try:
		## Set the command and parsing specific to this OS
		if (osType.lower() == 'windows'):
			command = concatenate('ping ', endpoint, ' -n 1 -w 3000')
			##  Pinging 212.82.100.151 with 32 bytes of data:
			##  Reply from 212.82.100.151: bytes=32 time=131ms TTL=53
		elif (osType.lower() == 'linux'):
			command = concatenate('ping ', endpoint, ' -c 1 -W 3')
			##  PING 212.82.100.151 (212.82.100.151) 56(84) bytes of data.
			##  64 bytes from 212.82.100.151: icmp_seq=1 ttl=53 time=130 ms
		else:
			runtime.logger.warn('Function pingLookup does not have parsing for osType {osType!r}.  Supported types: Windows & Linux.', osType=osType)
			return ipAddress

		pingCmd = updateCommand(runtime, command)
		runtime.logger.report('  Running command: {pingCmd!r}', pingCmd=pingCmd)
		(resultString, stdError, hitProblem) = client.run(pingCmd, 10)

		## If nothing returned, don't attempt to parse
		if hitProblem:
			runtime.logger.warn('  pingLookup: Problem executing ping')
			if stdError is not None:
				runtime.logger.error('  pingLookup: Error returned: {stdError!r}', stdError=stdError)
		else:
			runtime.logger.report('  pingLookup was able to ping {ipAddress!r}', ipAddress=ipAddress)

		## Better to look at exit status instead of parsing the result; we can
		## expect string success matches to change over time, plus the Linux
		## variants will not match, eg. CentOS vs RHEL differ on stderr today.
		# if resultString is not None:
		# 	if ((osType.lower() == 'windows' and (not re.search('[Rr]equest timed out', resultString))) or
		# 		(osType.lower() == 'linux' and (not re.search('[Dd]estination [Hh]ost [Uu]nreachable', resultString)))):
		# 		pass

	except:
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in pingLookup: {exception!r}', exception=exception)

	## end pingLookup
	return ipAddress
