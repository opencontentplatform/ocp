"""ICMP/Ping detection job.

This version uses a pure Python implementation using raw sockets, which means
it requires the client threads to run with elevated access. If that's not an
option, you can alternatively run the 'find_ICMP_cmdline' job instead.

Functions:
  startJob - Standard job entry point

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Oct 9, 2017

"""
import sys
import ping

## From openContentPlatform
from utilities import addIp


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		endpoint = runtime.endpoint['value']

		## Raw socket connection via Python - requires client to run elevated
		failed = ping.ping_ip(endpoint, maxTries=3, logger=runtime.logger)
		if failed:
			runtime.logger.debug("{name!r}: FAILED on endpoint {endpoint!r}", name =  __name__, endpoint = endpoint)
			runtime.status(2)
			runtime.message('Endpoint did not respond to ping.')
		else:
			runtime.logger.debug("{name!r}: SUCCESS on endpoint {endpoint!r}", name = __name__, endpoint= endpoint)
			runtime.status(1)

			## Add the IP onto the Results object
			addIp(runtime, address=endpoint)

	except:
		runtime.setError(__name__)

	## end startJob
	return
