"""Get running process data from target endpoint via Shell.

Functions:
  startJob : standard job entry point

"""
from contextlib import suppress
## From openContentPlatform
from protocolWrapper import getClient
from osProcesses import getProcesses


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	client = None
	try:
		## Configure shell client
		client = getClient(runtime)
		if client is not None:
			## Get a handle on our Node in order to link objects in this job
			nodeId = runtime.endpoint.get('data').get('container')
			runtime.results.addObject('Node', uniqueId=nodeId)

			## Open client session before starting the work
			client.open()

			## Do the work
			resultDictionary = getProcesses(runtime, client, nodeId, trackResults=True)

			## Good house keeping; though I force this after the exception below
			client.close()

			## Update the runtime status to success
			if runtime.getStatus() == 'UNKNOWN':
				runtime.status(1)

			## Debug output
			runtime.logger.report('resultDictionary:\n{resultDictionary!r}', resultDictionary=resultDictionary)
			runtime.logger.report('results of shell_OS_processes: {results!r}', results=runtime.results.getJson())

	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end startJob
	return
