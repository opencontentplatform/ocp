"""Merge nodes with the same IP where one or more are marked as partial.

Functions:
  startJob : standard job entry point
  getNodesWithoutDomains : get the first set of nodes (less qualified)
  getNodesWithDomains : get the second set of nodes (more qualified)
  getQueryResults : get query results for the node type
  processResults : loop through IPs with both qualified and partial nodes
  mergeObjects : issue an API call to merge the weak/strong objects

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Jan 3, 2018
  1.1 : (CS) Changed from calling DB queries directly (when running on server
        via the ServerSideService), to using the API (when running on a client
        via the UniversalJobService). Sep 5, 2019

"""
import sys
import traceback
import re
import os
import json
from contextlib import suppress

## From this package
from merge_nodes_utils import mergeObjects, getQueryResults
## From openContentPlatform
from utilities import getApiQueryResultsFull, getApiResult


def processResults(runtime):
	"""Get all qualified nodes sharing IPs with partial nodes."""
	try:
		partialNodesQuery = runtime.parameters.get('partialNodesQuery')
		queryResults = getQueryResults(runtime, partialNodesQuery, 'Nested-Simple')
		runtime.logger.info('Found {} qualified nodes sharing an IP with a partial node'.format(len(queryResults)))
		
		## Loop through the qualified Nodes
		for result in queryResults:
			qualifiedId = result.get('identifier')
			## Get qualified node info for debug reporting
			qualifiedName = result.get('data', {}).get('hostname')
			qualifiedDomain = result.get('data', {}).get('domain')
			runtime.logger.report(' qualified node: {name!r} {domain!r} {qualifiedId!r}', name=qualifiedName, domain=qualifiedDomain, qualifiedId=qualifiedId)
			
			mergedPartialNodes = []
			ips = result.get('children', [])
			## Loop through related IPs
			for ip in ips:
				address = ip.get('data', {}).get('address')
				realm = ip.get('data', {}).get('realm')
				partialNodes = ip.get('children', [])
				
				## Loop through related partial nodes
				for partialNode in partialNodes:
					partialId = partialNode.get('identifier')
					if partialId in mergedPartialNodes:
						## We've already processed and merged this node;
						## it had multiple IPs in common
						continue
					
					## Get partial node info for debug reporting
					mergedPartialNodes.append(partialId)
					partialName = partialNode.get('data', {}).get('hostname')
					partialDomain = partialNode.get('data', {}).get('domain')
					runtime.logger.report(' partial node: {name!r} {domain!r} {partialId!r}', name=partialName, domain=partialDomain, partialId=partialId)
					
					## We have the ids; now let's merge the nodes
					mergeObjects(runtime, partialId, qualifiedId)

	except:
		runtime.setError(__name__)

	## end processResults
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		## Do the work
		processResults(runtime)

		## Update the runtime status to success
		if runtime.getStatus() == 'UNKNOWN':
			runtime.status(1)

	except:
		runtime.setError(__name__)

	## end startJob
	return
