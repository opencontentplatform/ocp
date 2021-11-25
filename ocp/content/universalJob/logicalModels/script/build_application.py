"""Build objects and relationships to represent a logical application model.

Functions:
  startJob : standard job entry point
  getQueryResults : run a query to get matching objects
  getMetaDataResults : run a query to get all matching metadata objects
  processTargets : query for matching targets and work through the results
  recurseTargetResult : Loop through a result map looking for a target match
  recurseTierMatch : Loop through a result map looking for tier data
  createModel : Create all objects in the model

"""
import sys
import traceback
import os
import re
import json

## From this package
import logicalModelUtils


def createModel(runtime, metaData, containerContext, targetObjectId, targetMatchedValue, tier3Name, tier1Name):
	"""Now that we have details, create the model structure."""
	try:
		## Set attributes for ModelObject creation, used a few times below
		tier4_alias = metaData.get('tier4_alias')
		tier4_id = metaData.get('tier4_id')
		tier4_name = metaData.get('tier4_name')
		tier3_name = tier3Name
		tier2_name = metaData.get('tier2_name')
		tier1_name = tier1Name
		model_object_name = metaData.get('model_object_name')
		target_match_class = metaData.get('target_match_class')
		target_match_attribute = metaData.get('target_match_attribute')
		target_match_value = targetMatchedValue
		target_container = containerContext

		## Unique identifiers
		tier3_unique_name = '{}:{}'.format(tier4_id, tier3_name)
		tier2_unique_name = '{}:{}'.format(tier3_unique_name, tier2_name)
		tier1_unique_name = '{}:{}'.format(tier2_unique_name, tier1_name)

		## Tier 4 Group (top level):
		##   App
		t4_id, exists = runtime.results.addObject(metaData.get('tier4_create_class'), name=tier4_name, short_name=metaData.get('tier4_alias')[:16], element_id=metaData.get('tier4_id'))
		## Tier 3 Group:
		##   App -> Environment
		t3_id, exists = runtime.results.addObject(metaData.get('tier3_create_class'), name=tier3_name, unique_name=tier3_unique_name)
		runtime.results.addLink('Contain', t4_id, t3_id)
		## Tier 2 Group:
		##   App -> Environment -> Software
		t2_id, exists = runtime.results.addObject(metaData.get('tier2_create_class'), name=tier2_name, unique_name=tier2_unique_name)
		runtime.results.addLink('Contain', t3_id, t2_id)
		## Tier 1 Group (bottom level):
		##   App -> Environment -> Software -> Location
		t1_id, exists = runtime.results.addObject(metaData.get('tier1_create_class'), name=tier1_name, unique_name=tier1_unique_name)
		runtime.results.addLink('Contain', t2_id, t1_id)
		## Tier 0 (generated object instance)
		##   App -> Environment -> Software -> Location -> ModelObject
		moId, exists = runtime.results.addObject('ModelObject', tier4_alias=tier4_alias,
												 tier4_id=tier4_id, tier4_name=tier4_name,
												 tier3_name=tier3_name, tier2_name=tier2_name,
												 tier1_name=tier1_name,
												 model_object_name=model_object_name,
												 target_match_class=target_match_class,
												 target_match_attribute=target_match_attribute,
												 target_match_value=target_match_value,
												 target_container=target_container)
		runtime.results.addLink('Contain', t1_id, moId)
		## Create a handle on the target object matching our metadata, which is
		## linked to the ModelObject for consumers to follow the bread crumbs
		runtime.results.addObject(metaData.get('target_match_class'), uniqueId=targetObjectId)
		runtime.results.addLink('Usage', moId, targetObjectId)
		runtime.sendToKafka()
		## Not doing the following because I want the modeled object to exist
		## even if a node is deleted that has the discovered matching target...
		## need historical retention and drift over time, so avoiding container.
		## Create a handle on the container to hold the new ModelObject
		#runtime.results.addObject(containerClass, uniqueId=containerObjectId)
		#runtime.results.addLink('Enclosed', containerObjectId, moId)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Failure in createModel: {stacktrace!r}', stacktrace=stacktrace)

	## end createModel
	return


def recurseTierMatch(runtime, matchClassLabel, matchAttribute, matchPatterns, thisClassLabel, result):
	"""Loop through a single result map looking for the tier context."""
	groupName = None
	if thisClassLabel == matchClassLabel:
		## Class matches, now see if the values do
		thisObjectId = result.get('identifier')
		thisAttrValue = result.get('data').get(matchAttribute)
		if thisAttrValue is not None:
			for grpName,matchPattern in matchPatterns.items():
				if re.search(matchPattern, thisAttrValue):
					return grpName
	else:
		## Walk through topology result, looking to match target class label
		children = result.get('children')
		if children is not None:
			for childLabel,childList in children.items():
				for childResult in childList:
					groupName = recurseTierMatch(runtime, matchClassLabel, matchAttribute, matchPatterns, childLabel, childResult)
					if groupName is not None:
						return groupName

	## end recurseTierMatch
	return groupName


def recurseTargetResult(runtime, targetClassLabel, targetMatchAttribute, targetMatchPatterns, thisClassLabel, result):
	"""Loop through a single result map looking for a match on the target"""
	objectId = None
	matchedValue = None
	if thisClassLabel == targetClassLabel:
		runtime.logger.report('   targetClassLabel: {targetClassLabel!r}', targetClassLabel=targetClassLabel)
		## Class matches, now see if the values do
		thisObjectId = result.get('identifier')
		thisAttrValue = result.get('data').get(targetMatchAttribute)
		if thisAttrValue is not None:
			for matchPattern in targetMatchPatterns:
				if re.search(matchPattern, thisAttrValue):
					runtime.logger.report('  MATCH FOUND while looking at {thisAttrValue!r}, comparing to {matchPattern!r}', thisAttrValue=thisAttrValue, matchPattern=matchPattern)
					return (thisObjectId, thisAttrValue)
	else:
		## Walk through topology result, looking to match target class label
		children = result.get('children')
		if children is not None:
			for childLabel,childList in children.items():
				for childResult in childList:
					(objectId, matchedValue) = recurseTargetResult(runtime, targetClassLabel, targetMatchAttribute, targetMatchPatterns, childLabel, childResult)
					## If we need to map more than one match on the same object
					## (node with 5 postgres matches via 5 ProcessFingerprints)
					## then the unique constraint needs to change, in addition
					## to calling the tier lookup and object creation from here;
					## For now I am just returning and allowing it to be created
					## inside processTargets.
					if objectId is not None:
						return (objectId, matchedValue)

	## end recurseTargetResult
	return (objectId, matchedValue)


def processTargets(runtime, metaData, targetResults):
	"""Query for matching targets and work through the results."""
	runtime.logger.report('metadata: looking for metadata {metadata!r}', metadata=metaData)
	runtime.logger.report('metadata: looking for target_match_patterns {metadata!r}', metadata=metaData.get('target_match_patterns'))
	runtime.logger.report('metadata: looking for target_match_attribute {metadata!r}', metadata=metaData.get('target_match_attribute'))
	for nestedLabel,nestedSet in targetResults.items():
		try:
			## Since ResultsFormat of the result is Nested, that makes each
			## linchpin result an independent topology result...
			for result in nestedSet:
				if result is None or not isinstance(result, dict) or result.get('data') is None:
					continue
				runtime.logger.report(' processTargets: looking at {result!r}', result=result.get('data'))
				containerObjectId = result.get('identifier')
				containerClass = result.get('class_name')
				containerContext = result.get('data').get('hostname')
				## First go through this result and see if the target matches
				(targetObjectId, targetMatchedValue) = recurseTargetResult(runtime, metaData.get('target_match_class'), metaData.get('target_match_attribute'), metaData.get('target_match_patterns'), nestedLabel, result)
				runtime.logger.report('   targetObjectId: {targetObjectId!r}', targetObjectId=targetObjectId)
				if targetObjectId is None:
					continue
				runtime.logger.report('  MATCH FOUND: {targetObjectId!r} {targetMatchedValue!r}', targetObjectId=targetObjectId, targetMatchedValue=targetMatchedValue)
				## Target matched, now find our tier information, which can be
				## in ANY object and at ANY level. This is controlled by a label
				## in the targetQuery definition in the job parameter, matching
				## the object listed in tier3_match_class and tier1_match_class.

				## Go through this result and try to find a tier3 match
				tier3Name = recurseTierMatch(runtime, metaData.get('tier3_match_class'), metaData.get('tier3_match_attribute'), metaData.get('tier3_match_patterns'), nestedLabel, result)
				if tier3Name is None:
					runtime.logger.report('   No match found for Tier3 for object {targetObjectId!r} matched with {targetMatchedValue!r}', targetObjectId=targetObjectId, targetMatchedValue=targetMatchedValue)
					continue
				runtime.logger.report('   Tier3 found: {tier3Name!r}', tier3Name=tier3Name)

				## Go through the same result, looking for a tier1 match
				tier1Name = recurseTierMatch(runtime, metaData.get('tier1_match_class'), metaData.get('tier1_match_attribute'), metaData.get('tier1_match_patterns'), nestedLabel, result)
				if tier1Name is None:
					runtime.logger.report('   No match found for Tier1 for object {targetObjectId!r} matched with {targetMatchedValue!r}', targetObjectId=targetObjectId, targetMatchedValue=targetMatchedValue)
					continue
				runtime.logger.report('   Tier1 found: {tier1Name!r}', tier1Name=tier1Name)

				## Create objects...
				createModel(runtime, metaData, containerContext, targetObjectId, targetMatchedValue, tier3Name, tier1Name)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Failure in processTargets: {stacktrace!r}', stacktrace=stacktrace)

	## end processTargets
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:
		## Get results from the metadata query named in the parameters
		metaDataQuery = runtime.parameters.get('metaDataQuery')
		metaDataResults = logicalModelUtils.getMetaDataResults(runtime, metaDataQuery)
		if len(metaDataResults) <= 0:
			raise EnvironmentError('Job build_application: No metaData found in database; nothing to do.')

		## Get results from the target query named in the parameters
		targetQuery = runtime.parameters.get('targetQuery')
		targetResults = logicalModelUtils.getQueryResults(runtime, targetQuery, 'Nested')
		runtime.logger.report('Job build_application: targetResults: {targetResults!r}', targetResults=targetResults)
		if len(targetResults) <= 0:
			runtime.logger.report('Job build_application: No results found; nothing to build.')
		else:
			for metaDataId,metaDataResult in metaDataResults.items():
				## Re-run through all targets looking for matches on each meta
				## data result. I can't pop results off as I iterate through
				## for efficient processing, because of shared services. That
				## means a single target can match many models.
				processTargets(runtime, metaDataResult, targetResults)

		## Update the runtime status to success
		if runtime.getStatus() == 'UNKNOWN':
			runtime.status(1)

	except:
		runtime.setError(__name__)

	## end startJob
	return
