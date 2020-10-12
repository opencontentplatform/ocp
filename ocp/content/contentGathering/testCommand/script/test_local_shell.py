"""Run user-provided commands on desired shell/terminal 'local' to the client.

Troubleshooting aid for client testing.

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Sep 6, 2020

"""

import sys
import traceback
from contextlib import suppress

## From openContentPlatform
from protocolWrapper import localClient


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict) : object used for providing I/O for jobs and tracking
	                   the job thread through its runtime.
	"""
	client = None
	try:
		## Get parameters controlling the job
		commandsToTest = runtime.parameters.get('commandList', [])
		commandTimeout = runtime.parameters.get('commandTimeout', 10)
		shellType = runtime.parameters.get('shellType')

		client = localClient(runtime, shellType)
		if client is not None:
			## Open client session before starting the work
			client.open()

			## Run commands
			for command in commandsToTest:
				runtime.logger.warn('Running command: {command!r}', command=command)
				(stdOut, stdError, hitProblem) = client.run(command, commandTimeout)
				if hitProblem:
					runtime.logger.warn(' command encountered a problem: {}'.format(command))
				else:
					runtime.logger.debug(' command successful: {}'.format(command))
				runtime.logger.debug('  stdOut: {stdOut!r}', stdOut=stdOut)
				if stdError is not None:
					runtime.logger.debug('  stdError: {stdError!r}', stdError=stdError)

			## Update the runtime status to success
			runtime.status(1)

	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end startJob
	return
