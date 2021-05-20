"""Sample detection job for the Open Content Platform.

Functions:
  startJob : standard job entry point, establish a client connection
  ableToQueryResource : simple request to validate connection
  createObjects : create and connect the node and REST object

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Apr 10, 2021

"""
import sys
import traceback
from contextlib import suppress
from utilities import addObject, addLink
from ucmdbRestAPI import UcmdbRestAPI


def pingResource(runtime, client):
	"""Query a simple resource to validate the connection."""
	try:
		resource = '/ping'
		(code, response) = client.get(resource)
		## Sample output:
		## { 'status': {
		## 	 'statusCode': 200,
		## 	 'reasonPhrase': 'OK',
		## 	 'message': 'Up, is writer: true'}
		## }
		if response.get('status'):
			for key,value in response.get('status', {}).items():
				runtime.logger.report('  --> ping status: {}: {}'.format(key, value))
			## TODO ... any object creation
			
			## Update the status to SUCCESS
			runtime.status(1)

	except:
		runtime.setError(__name__)

	## end pingResource
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
		client = UcmdbRestAPI(runtime)
		## Validate the connection context still works, or raise an exception
		client.connect()
		runtime.logger.report('connection made.')
		
		## Do work
		pingResource(runtime, client)
		
	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end startJob
	return
