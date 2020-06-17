"""Get all IPs in our DB that fall into the range of a particular realm scope.

Sample of what 'endpoints' should look like before sent back to caller:
	{"endpoints": [
		{ "value": "192.168.121.13" },
		{ "value": "192.168.121.14" },
		{ "value": "192.168.121.15" },
		{...}
	]}

Functions:
  |  getEndpoints         : entry point
  |  buildTargetEndpoints : builds the list of endpoints

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Dec, 2017

"""
import os
import sys
import traceback
import ipaddress
import database.schema.networkElement as networkElement
import database.schema.platformSchema as platformSchema


def buildTargetEndpoints(dbClient, logger, targets, realm):
	"""Helper function that builds the list of endpoints.

	Arguments:
	  dbClient (connectionPool.Client)  : Instance of database client
	  logger                            : Log handler
	  targets (list)                    : output variable containing targets
	  realm (str)                       : realm identifier (discovery boundary)

	"""
	try:
		## Pull the realm scope for this realm
		realmScope = dbClient.session.query(platformSchema.RealmScope).filter(platformSchema.RealmScope.realm == realm).first()
		dbClient.session.commit()
		## realmScope.data is a list of networks
		networksInThisRealm = realmScope.data

		## Pull all IPs from the database
		results = dbClient.session.query(networkElement.IpAddress).all()
		dbClient.session.commit()
		for result in results:
			# if str(result.address) != '74.116.116.175':
			# 	continue
			if str(result.address) != '192.168.121.221':
				continue

			## Ensure all IPs fall within the realm; could check an attribute
			## but if someone does something to bulk override that attribute
			## across the IPs in the database, it would spell trouble. This is
			## more CPU processing on the endpoint calculation, but worth it.
			#logger.debug('Checking if IP is in realmScope: {result!r} ...', result=str(result.address))
			thisIPAsNetwork = ipaddress.ip_network(str(result.address))
			for networkAsString in networksInThisRealm:
				#thisIPAsNetwork = ipaddress.ip_network(str(result.address))
				thisNetwork = ipaddress.ip_network(networkAsString, False)
				if thisNetwork.overlaps(thisIPAsNetwork):
					## Add this IP to the target endpoints
					targets.append({ "value" : str(result.address)})
					logger.debug('  yes, IP {result!r} is in scope', result=str(result.address))
					break

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

		## Add the target list to our endpoint JSON
		endpoints['endpoints'] = targets

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in getEndpoints: {stacktrace!r}', stacktrace=stacktrace)

	## end getEndpoints
	return
