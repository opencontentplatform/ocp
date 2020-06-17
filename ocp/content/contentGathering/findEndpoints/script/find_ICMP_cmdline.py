"""ICMP/Ping detection job.

This version uses the local powershell client to issue ping on a command line,
from the content gathering client runtime. It could be enhanced to use any local
protocol on any OS type where the client is running. But that really wasn't 
necessary since the find_ICMP_socket provides an OS-agnostic way of doing that
already. This is simply an alternative if you aren't able to run the content
gathering client with elevated access (required for the raw socket version).

Functions:
  startJob - Standard job entry point
  isPingable - Uses 'ping' utility from local shell command line

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Oct 5, 2017

"""
import sys
import traceback
import re
from contextlib import suppress

## From openContentPlatform
from utilities import addIp
from protocolWrapper import localClient


def isPingable(runtime, client, endpoint):
	"""Attempt a local ping to see if an endpoint (ip/name) responds to ICMP.
	
	This is different from utilitiess.pingable(), which uses a remote connection
	and endpoint shell settings for updateCommand.
	"""
	try:
		## If this is client OS agnostic, we'll need OS and cmd line flexibility
		pingCommand = 'ping {} -n 1 -w 3000'.format(endpoint)
		## pass:
		##  Reply from 212.82.100.151: bytes=32 time=131ms TTL=53
		## fail:
		##  Reply from 212.82.100.151: Destination host unreachable
		runtime.logger.report('  Running local command: {pingCommand!r}', pingCommand=pingCommand)
		(resultString, stdError, hitProblem) = client.run(pingCommand, 10)
		## The exit status coming back (hitProblem) is not useful; a failed ping
		## to a target destination is still a successful command line execution.
		## We have to do some regEx parsing...
		if not hitProblem and resultString is not None:
			if (re.search('[Rr]equest timed out', resultString) or
				re.search('[Dd]estination [Hh]ost [Uu]nreachable', resultString)):
				runtime.logger.report('Endpoint did not respond to ping: {endpoint!r}.  Result: {resultString!r}', endpoint=endpoint, resultString=resultString)
				return False
			runtime.logger.report('Endpoint responded to ping: {endpoint!r}.', endpoint=endpoint)
			return True
		
		if stdError is not None:
			runtime.logger.error('  isPingable: Error returned: {stdError!r}', stdError=stdError)
		else:
			runtime.logger.error('  isPingable: Problem executing ping')

	except:
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in isPingable: {exception!r}', exception=exception)

	## end isPingable
	return False


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	client = None
	try:
		endpoint = runtime.endpoint['value']
		## Configure local client
		client = localClient(runtime, 'powershell')
		if client is not None:
			## Open client session before starting the work
			client.open()
			if isPingable(runtime, client, endpoint):
				runtime.logger.debug("{name!r}: SUCCESS on endpoint {endpoint!r}", name = __name__, endpoint= endpoint)
				runtime.status(1)
				## Add the IP onto the Results object
				addIp(runtime, address=endpoint)
			else:
				runtime.logger.debug("{name!r}: FAILED on endpoint {endpoint!r}", name =  __name__, endpoint = endpoint)
				runtime.status(2)
				runtime.message('Endpoint did not respond to ping.')
			## Good house keeping; though I force this after the exception below
			client.close()

	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end startJob
	return
