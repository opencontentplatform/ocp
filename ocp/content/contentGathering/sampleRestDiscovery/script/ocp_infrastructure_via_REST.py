"""Sample detection job for the Open Content Platform.

Functions:
  startJob : standard job entry point, establish a client connection
  gatherRuntime : request the platform's infrastructure runtime
  reportServerSection : reports on each server section
  reportClientSections : report on all clients

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Apr 10, 2021

"""
from contextlib import suppress
from ocpRestAPI import OcpRestAPI


def reportClientSections(runtime, section, response):
	endpoints = response.get(section, [])
	runtime.logger.report('Reporting runtime section: '.format(section))
	for endpoint in endpoints:
		for key,value in endpoint.items():
			if key.lower() == 'running':
				for clientType,clientNames in value.items():
					runtime.logger.report('    running {}: {}'.format(clientType, clientNames))
			else:
				runtime.logger.report('  {}: {}'.format(key, value))
	
	## end reportClientSections
	return


def reportServerSection(runtime, section, response):
	data = response.get(section, {})
	runtime.logger.report('Reporting runtime section: {}'.format(section))
	for key,value in data.items():
		runtime.logger.report('  {}: {}'.format(key, value))
	
	## end reportSection
	return


def gatherRuntime(runtime, client):
	"""Request the platform's infrastructure runtime."""
	try:
		runtime.logger.report('Trying to get OCP runtime from resource: /config/runtime')
		resource = '/config/runtime'
		(code, response) = client.get(resource)
		## Sample output:
		# {
		# 	"server": { ... },
		# 	"database": { ... },
		# 	"kafka": { ... },
		# 	"clients": [ ... ]
		# }
		if code == 200:
			serverSections = ['server', 'database', 'kafka']
			for section in serverSections:
				reportServerSection(runtime, section, response)
			reportClientSections(runtime, 'clients', response)
			## TODO ... any object creation
			
			## Update the status to SUCCESS
			runtime.status(1)

	except:
		runtime.setError(__name__)

	## end gatherRuntime
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	client = None
	try:
		## Initialize client with our REST CI context established previously
		client = OcpRestAPI(runtime)
		## Validate the connection context still works, or raise an exception
		client.connect()
		runtime.logger.report('connection made.')

		## Get a handle on our Node in order to link objects in this job
		nodeId = runtime.endpoint.get('data').get('container')
		runtime.results.addObject('Node', uniqueId=nodeId)

		## Do work
		gatherRuntime(runtime, client)
		
	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end startJob
	return
