"""Get endpoints with an established shell protocol in this realm.

Functions:
  |  getEndpoints         : entry point
  |  buildTargetEndpoints : builds the list of endpoints

Sample of what 'endpoints' should look like before sent back to caller:
	{"endpoints": [
		{ "protocol_reference": "143", "ipaddress": "192.168.121.13", "port": "", "container": "0bce141b9bb94175ac97f622e5d9a2af", "hostname": "ServerXYZ", "domain": "leveragediscovery.com"},
		{ "protocol_reference": "143", "ipaddress": "192.168.121.14", "port": "", "container": "d0599f28d7c7421f8d3645d7c718e626", "hostname": "ServerZ", "domain": "leveragediscovery.com"},
		{ "protocol_reference": "137", "ipaddress": "192.168.121.15", "port": "", "container": "6ac9319445ee49ac9923cd633939c4ad", "hostname": "ServerABC", "domain": "leveragediscovery.com"},
		{...}
	]}

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Mar 17, 2018

"""
import os
import sys
import traceback
from database.schema.softwareElement import PowerShell
#from database.schema.softwareElement import SSH
from database.schema.platformSchema import Realm
from database.schema.node import Node


def buildTargetEndpoints(dbClient, logger, targets, realm):
	"""Helper function that builds the list of endpoints.

	Arguments:
	  dbClient (connectionPool.Client)  : Instance of database client
	  logger                            : Log handler
	  targets (list)                    : output variable containing targets

	"""
	try:
		## This needs replaced by the JSON query engine, when available, so
		## queries in the endpoints folder work similar to those sent in from
		## the API or via the Data Transformation service... yeilding JSON.

		## Pull all PowerShell objects connected to Node objects from database
		#results = dbClient.session.query(Node, PowerShell, SSH).join(PowerShell, Node.object_id==PowerShell.container).filter(Realm.name == PowerShell.realm).outterjoin(SSH, Node.object_id==SSH.container).filter(Realm.name == SSH.realm)
		results = dbClient.session.query(Node, PowerShell).join(PowerShell, Node.object_id==PowerShell.container).filter(Realm.name == PowerShell.realm)
		for result in results:
			## Add this IP to the target endpoints
			node=result[0]
			shell=result[1]
			value = {}
			value['container'] = str(shell.container)
			value['ipaddress'] = str(shell.ipaddress)
			value['protocol_reference'] = str(shell.protocol_reference)
			value['realm'] = str(shell.realm)
			value['port'] = str(shell.port)
			value['protocol_type'] = str(shell.object_type)
			value['hostname'] = str(node.hostname)
			value['domain'] = str(node.domain)
			#targets.append({ "value" : value })
			targets.append(value)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in buildTargetEndpoints: {stacktrace!r}', stacktrace=stacktrace)

	## end buildTargetEndpoints
	return


def getEndpoints(dbClient, logger, endpoints, metaData):
	"""Get data on target endpoints for a job.

	Arguments:
	  dbClient (connectionPool.Client)  : Instance of database client
	  logger                            : Log handler
	  endpoints (dict)                  : output variable; expecting JSON format
	  metaData (dict)                   : controlling information for this job,
	                                      defined by JSON file in the job folder

	"""
	try:
		logger.debug('Starting getEndpoints in {name!r}', name=__name__)
		targets = []
		realm = metaData['realm']
		buildTargetEndpoints(dbClient, logger, targets, realm)

		## add the target list to our endpoint JSON
		endpoints['endpoints'] = targets

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in getEndpoints: {stacktrace!r}', stacktrace=stacktrace)

	## end getEndpoints
	return
