"""SSH detection library for HP-UX.

Functions:
  queryHPUX : entry point; run queries against HP-UX endpoint
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

	Sample output for HP-UX:
	========================================================================
	This shows v11.31:
	uname -a
	  HP-UX hp3 B.11.31 U ia64 3875925350 unlimited-user license
	========================================================================
	"""
	try:
		runtime.logger.report('Inside parsePreviousCmdOutput with prevCmdOutput: {prevCmdOutput!r}', prevCmdOutput=prevCmdOutput)

	except:
		runtime.setError(__name__)

	## end parsePreviousCmdOutput
	return


def queryHPUX(runtime, client, endpoint, protocolReference, osType, prevCmdOutput):
	"""Run queries against a HP-UX endpoint.

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
