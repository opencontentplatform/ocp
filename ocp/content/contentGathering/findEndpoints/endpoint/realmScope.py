"""Get all possible IPs included in a particular realm scope.

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
  1.0 : (CS) Created Oct 7, 2017

"""
import os
import sys
import re
import traceback
import ipaddress
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
		## Get list of networks for the scope entry of this realm
		realmScope = dbClient.session.query(platformSchema.RealmScope).filter(platformSchema.RealmScope.realm == realm).first() or None
		dbClient.session.commit()

		if realmScope is None:
			logger.warn(' No scope currently defined for requested realm {realm!r}', realm=realm)
		else:
			## Enumerate all IP addresses out of the list of networks
			count = 0
			for thisNet in sorted(realmScope.data):
				## Would like to use a standard lib to remove the broadcast
				## addresses. But ipaddress.ip_network(thisNet).hosts() doesn't
				## hit the mark. On 10.2.3.0/24 it works correctly and removes
				## 10.2.3.0 and 10.2.3.255, but on 10.2.3.0/8 it removes 10.2.3.0
				## (correctly) and 10.2.3.7 (incorrectly). And on 10.2.3.8/30 it
				## removes both 10.2.3.8 and 10.2.3.11 incorrectly.
				## ============================================================
				# for ipaddr in ipaddress.ip_network(thisNet).hosts():
				# 	targets.append({ "value" : str(ipaddr)})
				# 	count += 1
				## ============================================================
				## Soooo, just string matching and removing .0 and .255 for now.
				for ipaddr in ipaddress.ip_network(thisNet):
					## Cast from IPv4Address/IPv6Address to string value for JSON
					if re.search('\.0$', str(ipaddr)) or re.search('\.255$', str(ipaddr)):
						continue
					targets.append({ "value" : str(ipaddr)})
					count += 1

			logger.debug(' ====> Total IP count for realm {realm!r} is: {count!r}', realm=realm, count=count)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in buildTargetEndpoints: {stacktrace!r}', stacktrace=stacktrace)

	## end buildTargetEndpoints
	return


def getEndpoints(dbClient, logger, endpoints, metaData):
	"""Get data on target endpoints for a job.

	Arguments:
	  dbClient (connectionPool.Client)  : instance of database client
	  logger                            : log handler
	  endpoints (dict)                  : output variable; expecting JSON format
	  metaData (dict)                   : controlling information for this job,
	                                      defined by JSON file in the job folder
	"""
	targets = []
	try:
		logger.debug('Starting getEndpoints in {name!r}', name=__name__)
		logger.debug(' parameters: {metaData!r}', metaData=metaData)
		realm = metaData['realm']
		buildTargetEndpoints(dbClient, logger, targets, realm)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in getEndpoints: {stacktrace!r}', stacktrace=stacktrace)

	## Add the target list to our JSON
	endpoints['endpoints'] = targets

	## end getEndpoints
	return
