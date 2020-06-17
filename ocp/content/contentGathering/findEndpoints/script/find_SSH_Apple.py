"""SSH detection library for Apple.

Functions:
  queryApple : entry point; run queries against Apple endpoint
  parsePreviousCmdOutput : parse previous uname output

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  0.1 : (CS) Created stub library, Aug 2, 2018

"""
import sys
import traceback
import re

## From openContentPlatform
from utilities import setInstanceParameters


def parsePreviousCmdOutput(client, runtime, attrDict, prevCmdOutput):
	"""Query and parse uname -a output.

	Sample output for Apple:
	========================================================================
	uname -a
	  Darwin Roadrunner.local 10.3.0 Darwin Kernel Version 10.3.0: Fri Feb 26 11:58:09 PST 2010; root:xnu-1504.3.12~1/RELEASE_I386 i386
	========================================================================
	"""
	try:
		runtime.logger.report('Inside parsePreviousCmdOutput with prevCmdOutput: {prevCmdOutput!r}', prevCmdOutput=prevCmdOutput)

	except:
		runtime.setError(__name__)

	## end parsePreviousCmdOutput
	return


def queryApple(runtime, client, endpoint, protocolReference, osType, prevCmdOutput):
	"""Run queries against a Apple endpoint.

	Arguments:
	  runtime (dict)    : object used for providing input into jobs and tracking
	                      the job thread through the life of its runtime
	  client            : PowerShell client
	  endpoint          : target endpoint for the discovery job
	  protocolReference : reference id
	  osType            : normalized string used for comparisons
	  prevCmdOutput     : previous command result (from running uname -a)
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
