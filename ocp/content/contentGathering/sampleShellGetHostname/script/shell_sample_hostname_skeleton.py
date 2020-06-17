from protocolWrapper import getClient
def startJob(runtime):
	client = getClient(runtime)
	client.open()
	(stdout, stderr, hitProblem) = client.run('hostname')
	client.close()
	#runtime.logger.report(' --> {output!r}', output=stdout)
