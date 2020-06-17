from contextlib import suppress
from protocolWrapper import getClient

def startJob(runtime):
	client = None
	try:
		client = getClient(runtime)
		if client is not None:
			client.open()
			command = 'hostname'
			(stdout, stderr, hitProblem) = client.run(command)
			if (hitProblem):
				raise OSError('Command failed {}. Error returned {}.'.format(command, stderr))
			runtime.logger.report(' --> {command!r}: {output!r}', command=command, output=stdout)
	except:
		runtime.setError(__name__)

	if client is not None:
		with suppress(Exception):
			client.close()
