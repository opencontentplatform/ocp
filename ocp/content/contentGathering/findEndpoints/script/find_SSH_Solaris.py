"""SSH detection library for Solaris.

Stubbed only.

"""
import sys
import traceback
import re

## From openContentPlatform
from utilities import setInstanceParameters


def parsePreviousCmdOutput(client, runtime, attrDict, prevCmdOutput):
	"""Query and parse uname -a output.

	Sample output for Solaris:
	========================================================================
	uname -a
	  SunOS sun4 5.10 Generic sun4u sparc SUNW,Sun-Fire-V44
	showrev -a
	  Hostname: starbug
	  Hostid: nnnnnnnn
	  Release: 5.9
	  Kernel architecture: sun4u
	  Application architecture: sparc
	  Hardware provider: Sun_Microsystems
	  Domain: solar.com
	  Kernel version: SunOS 5.9 May 2002
	========================================================================
	"""
	try:
		runtime.logger.report('Inside parsePreviousCmdOutput with prevCmdOutput: {prevCmdOutput!r}', prevCmdOutput=prevCmdOutput)

	except:
		runtime.setError(__name__)

	## end parsePreviousCmdOutput
	return


def querySolaris(runtime, client, endpoint, protocolReference, osType, prevCmdOutput):
	"""Run queries against a Solaris endpoint.

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
