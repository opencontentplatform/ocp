"""SSH detection library for AIX.

Stubbed only.

"""
import sys
import traceback
import re

## From openContentPlatform
#import find_SSH
from utilities import setInstanceParameters


def parsePreviousCmdOutput(client, runtime, attrDict, prevCmdOutput):
	"""Query and parse oslevel -a output.

	Sample output for AIX:
	========================================================================
	For Version, Technology Level, Service Pack, and build date (the following
	shows AIXv6.1, Technology Level 8, Service Pack 1, built 45th week of 2012):
	oslevel -s
	   6100-08-01-1245
	Note: older versions may not work with -s, but -r will give Version and TL.
	========================================================================
	"""
	try:
		runtime.logger.report('Inside parsePreviousCmdOutput with prevCmdOutput: {prevCmdOutput!r}', prevCmdOutput=prevCmdOutput)

	except:
		runtime.setError(__name__)

	## end parsePreviousCmdOutput
	return


def queryAIX(runtime, client, endpoint, protocolReference, osType, prevCmdOutput):
	"""Run queries against a AIX endpoint.

	Arguments:
	  runtime (dict)    : object used for providing input into jobs and tracking
	                      the job thread through the life of its runtime
	  client            : PowerShell client
	  endpoint          : target endpoint for the discovery job
	  protocolReference : reference id
	  osType            : normalized string used for comparisons
	  prevCmdOutput     : previous command result (from running oslevel -s)
	"""
	try:
		## Query OperatingSystem for OS attributes
		osAttrDict = {}
		parsePreviousCmdOutput(client, runtime, osAttrDict, prevCmdOutput)
		#runtime.logger.debug('osAttrDict: {osAttrDict!r}', osAttrDict=osAttrDict)

	except:
		runtime.setError(__name__)

	## end queryLinux
	return
