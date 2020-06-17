"""Log Anonymizer utility.

This utility takes a directory of log files, and search/replaces all matching
instances from the defined match blocks. See the following comments illustrating
the transformation of IPv4 addresses into sensitized values for public viewing.

Note that all instances of a unique match (e.g. the "10.0.175.20" IP below) is
replaced across all logs with the same unique replacement... thereby allowing
support groups to continue correlating and troubleshoot details scattered across
logs, but now with versions of logs scrubbed of anything private or sensitive.

==============================================================================
Sample log section showing netstat output:
	tcp        0      0 10.0.175.20:1352            10.101.146.18:61607
	tcp        0      0 10.0.175.20:1352            10.101.112.183:49633
	tcp        0      0 10.0.175.20:1352            10.101.146.36:61075
	tcp        0      0 10.0.175.20:1352            10.0.147.154:56392
	udp        0      0 0.0.0.0:161                 0.0.0.0:*
	udp        0      0 127.0.0.1:50342             0.0.0.0:*
	udp        0      0 0.0.0.0:695                 0.0.0.0:*

Transforming with this match block:
	{
		"description": "Match IPv4 addresses, excluding 255.255.255.x, 0.0.0.0, 127.0.0.1. Replace with [IpAddress:<integer>].",
		"matchExpression": "\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}",
		"ignoreExpressions": ["255\\.255\\.255\\.\\d{1,3}",
							  "0\\.0\\.0\\.0",
							  "127\\.0\\.0\\.1"],
		"replaceStringStart": "[IpAddress:",
		"replaceStringEnd": "]",
		"replaceType": "integer"
	}

... causes the replacement to use integer values wrapped by custom start/stop tags:
	tcp        0      0 [IpAddress:1]:1352            [IpAddress:68]:61607
	tcp        0      0 [IpAddress:1]:1352            [IpAddress:165]:49633
	tcp        0      0 [IpAddress:1]:1352            [IpAddress:84]:61075
	tcp        0      0 [IpAddress:1]:1352            [IpAddress:166]:56392
	udp        0      0 0.0.0.0:161                 0.0.0.0:*
	udp        0      0 127.0.0.1:50342             0.0.0.0:*
	udp        0      0 0.0.0.0:695                 0.0.0.0:*

Modifying these match block parameters:
		"replaceStringStart": "",
		"replaceStringEnd": "",
		"replaceType": "uuid"

... causes the replacement to use plain 32-bit hex values:
	tcp        0      0 91b276088db74961b036449845b2b1de:1352            b32f680485364035a9c05fbffa812500:61607
	tcp        0      0 91b276088db74961b036449845b2b1de:1352            5d1ba096d0ad4c2e9337385d4d6440ae:49633
	tcp        0      0 91b276088db74961b036449845b2b1de:1352            ce845af45cc74e6d9b3fff3dac1048f3:61075
	tcp        0      0 91b276088db74961b036449845b2b1de:1352            d51da3482c624807945a8a6808b9b7b3:56392
	udp        0      0 0.0.0.0:161                 0.0.0.0:*
	udp        0      0 127.0.0.1:50342             0.0.0.0:*
	udp        0      0 0.0.0.0:695                 0.0.0.0:*
==============================================================================

Usage:
	python logAnonymizer.py <source_directory> <target_directory>

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Mar 27, 2019

"""

import sys, traceback
import os, shutil
import time, datetime
import re, json, uuid
from contextlib import suppress
CONFIG_FILE = 'logAnonymizer.json'


def getReplacementValue(match, replacedValues, replaceType, replaceValue, integer):
	"""Replace sensitive value."""
	replacementValue = None
	if replaceType == 'static':
		replacementValue = replaceValue
	elif match in replacedValues:
		replacementValue = replacedValues[match]
	else:
		if replaceType == 'integer':
			integer += 1
			replacementValue = str(integer)
		elif replaceType == 'uuid':
			replacementValue = uuid.uuid4().hex
		replacedValues[match] = replacementValue
	return (replacementValue, integer)

def workOnLine(lineData, matchData, replacedValues, integer):
	"""Look for search hits on a log line."""
	newLine = lineData
	nuberOfSubsOnLine = 0
	for matchBlock in matchData:
		## Get the match block details
		matchExpression = matchBlock.get('matchExpression')
		ignoreExpressions = matchBlock.get('ignoreExpressions', [])
		replaceStringStart = matchBlock.get('replaceStringStart', '')
		replaceStringEnd = matchBlock.get('replaceStringEnd', '')
		replaceType = matchBlock.get('replaceType', 'integer')
		replaceValue = matchBlock.get('replaceValue', 'anonymous')
		## See if we have matches
		matchList = re.findall(matchExpression, newLine)
		if len(matchList) > 0:
			uniqueList = list(set(matchList))
			for match in uniqueList:
				ignoreMatch = False
				for ignoreExp in ignoreExpressions:
					if re.search(ignoreExp, match):
						ignoreMatch = True
						break
				if ignoreMatch:
					continue
				## We want to replace this value across the line
				(replaceValue, integer) = getReplacementValue(match, replacedValues, replaceType, replaceValue, integer)
				replaceString = '{}{}{}'.format(replaceStringStart, replaceValue, replaceStringEnd)
				## This escapedMatch converts the dots to literal dots so that
				## the following subn knows we mean a literal decimal point, to
				## avoid something like '0.0.0.0' matching '0 0.0.0'
				escapedMatch = re.sub('\.', '\\.', match)
				(newLine, numberOfSubs) = re.subn(escapedMatch, replaceString, newLine)
				nuberOfSubsOnLine += numberOfSubs
	return (newLine, integer, nuberOfSubsOnLine)

def workOnFile(sourceFile, targetFile, matchData, replacedValues, integer):
	"""Open a file and start processing."""
	numberOfSubsInFile = 0
	## Open the target file for writing
	with open(targetFile, 'w') as targetHandle:
		## Open the source file for reading
		with open(sourceFile, 'r') as sourceHandle:
			lineNumber = 0
			for lineNumber, lineData in enumerate(sourceHandle):
				(newLine, integer, nuberOfSubsOnLine) = workOnLine(lineData, matchData, replacedValues, integer)
				numberOfSubsInFile += nuberOfSubsOnLine
				targetHandle.write('{}'.format(newLine))
			print('      lines processed: {}.'.format(lineNumber))
			print('      transformations: {}.'.format(numberOfSubsInFile))
		targetHandle.flush()
	return numberOfSubsInFile

def cleanArg(value):
	"""Normalize arguments."""
	if value is not None:
		value.strip()
		m = re.search('^\"(.*)\"$', value)
		if m:
			value = m.group(1)
	return value

def doWork(argv):
	"""Standard entry point for the module."""
	try:
		startTime = time.time()
		startTimeString = datetime.datetime.fromtimestamp(startTime).strftime('%Y-%m-%d %H:%M:%S')
		with open(CONFIG_FILE) as fp:
			matchData = json.load(fp)
		if len(argv) != 3:
			print('\nPlease pass fully qualified source and target directories as input parameters.\nUsage:\n  $ python {} <source_directory> <target_directory>\n\nNote: the target directory will be removed and recreated.\n'.format(__file__))
			raise EnvironmentError('Please pass the directory as an input parameter.')
		sourceDir = cleanArg(argv[1])
		targetDir = cleanArg(argv[2])
		if not os.path.exists(sourceDir):
			print('\nThe provided directory is invalid: {}\nPlease pass a valid directory as an input parameter. Usage:\n  $ python {} <source_directory> <target_directory>\n'.format(sourceDir, __file__))
			raise EnvironmentError('The provided directory is invalid: {}'.format(sourceDir))
		print('Starting Log Anonymizer at {}'.format(startTimeString))
		print('  source directory: {}'.format(sourceDir))
		print('  target directory: {}'.format(targetDir))
		if os.path.exists(targetDir):
			shutil.rmtree(targetDir)
		time.sleep(.1)
		with suppress(Exception):
			os.mkdir(targetDir)
		logList = os.listdir(sourceDir)
		replacedValues = {}
		totalSubs = 0
		integer = 0
		for logFile in logList:
			if not re.search('\.log', logFile):
				continue
			sourceFile = os.path.join(sourceDir, logFile)
			targetFile = os.path.join(targetDir, logFile)
			print('    working on {}'.format(logFile))
			numberOfSubsInFile = workOnFile(sourceFile, targetFile, matchData, replacedValues, integer)
			totalSubs += numberOfSubsInFile
		endTime = time.time()
		endTimeString = datetime.datetime.fromtimestamp(endTime).strftime('%Y-%m-%d %H:%M:%S')
		print('\n  Unique matches found : {}'.format(len(replacedValues)))
		print('  Total transformations: {}'.format(totalSubs))
		print('\nLog Anonymizer had a runtime of {:.2f} seconds.\n'.format(endTime-startTime))
	except:
		print('Exception in doWork: {}'.format(sys.exc_info()[1]))

if __name__ == '__main__':
	sys.exit(doWork(sys.argv))
