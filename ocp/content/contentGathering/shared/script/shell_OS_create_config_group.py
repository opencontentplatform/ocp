"""Baseline a Node endpoint and create (or update) a config group.

Active config groups are stored in the following file:
  content\contentGathering\shared\conf\configGroup\configGroups.json
Backups are saved and rolled in the same directory with a dot number extension:
  configGroups.json
  configGroups.json.1
  configGroups.json.2
  configGroups.json.3
  ...
  configGroups.json.10

Functions:
  startJob : standard job entry point
  getNodeDetails : gather node attributes
  constructParameters : build the parameters section of the config group
  createNewConfig : build the attributes of the new config group
  modifyConfigGroupFile : manage file retention on the configGroup.json file
  rotateConfigGroupFilesByName : rotate configGroup file via datetime method
  rotateConfigGroupFilesByNumber : rotate configGroup file via numerical method

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Jun 20, 2018

"""
import sys
import traceback
from contextlib import suppress
import json
import os
import re

## From openContentPlatform
from protocolWrapper import getClient
from osProcesses import getProcesses
from osSoftwarePackages import getSoftwarePackages
from osStartTasks import getStartTasks
from utilities import loadConfigGroupFile, compareFilter, getApiResult
from utilities import getApiQueryResultsFull

## Global for ease of future change
validShellTypes = ["PowerShell", "SSH"]


def modifyConfigGroupFile(runtime, newConfig):
	"""Manage file retention on the configGroup.json file, and then update.

	Arguments:
	  runtime (dict)   : object used for providing I/O for jobs and
	                     tracking the job thread through its runtime
	  newConfig (dict) : JSON of the configGroup created by this job
	"""
	try:
		realm = runtime.jobMetaData.get('realm', 'default')
		thisName = newConfig.get('name')

		responseAsJson = None
		responseCode = None
		customPayload = {}
		customPayload['content'] = {'source': 'shell_OS_create_config_group', 'content': newConfig}
		runtime.logger.report('modifyConfigGroupFile: trying a PUT on realm {realm!r}', realm=realm)
		runtime.logger.info('modifyConfigGroupFile: customPayload {customPayload!r}', customPayload=customPayload)
		apiResponse = getApiResult(runtime, 'config/ConfigGroups/{}'.format(realm), 'put', customPayload=customPayload)
		with suppress(Exception):
			responseCode = apiResponse.status_code
			responseAsJson = json.loads(apiResponse.text)
		if str(responseCode) == '200':
			runtime.logger.info('Updated configGroup: {configGroup!r}', configGroup=thisName)
		elif str(responseCode) == '404':
			runtime.logger.report('modifyConfigGroupFile: realm {realm!r} does not yet exist... issuing POST instead of PUT as a result of response: {responseAsJson!r}', realm=realm, responseAsJson=responseAsJson)
			customPayload['content'] = {'content':{'realm': realm, 'content': groups}}
			runtime.logger.info('modifyConfigGroupFile: customPayload {customPayload!r}', customPayload=customPayload)
			apiResponse = getApiResult(runtime, 'config/ConfigGroups/{}'.format(realm), 'put', customPayload=customPayload)
			runtime.logger.info('Created configGroup: {configGroup!r}', configGroup=thisName)
		if str(responseCode) != '200':
			raise EnvironmentError(apiResponse.text)

		runtime.logger.info('modifyConfigGroupFile: API query code: {responseCode!r}.  response: {responseAsJson!r}', responseCode=responseCode, responseAsJson=responseAsJson)

	except:
		runtime.setError(__name__)

	## end modifyConfigGroupFile
	return


def createNewConfig(runtime, nodeDetails, configParameters):
	"""Build the attributes of the new config group.

	Arguments:
	  runtime (dict)          : object used for providing I/O for jobs and
	                            tracking the job thread through its runtime
	  nodeDetails (dict)      : attributes from the Node object
	  configParameters (dict) : parameters built from constructParameters
	"""
	newConfig = {}
	try:
		runtime.logger.report('createNewConfig: nodeDetails: {nodeDetails!r}', nodeDetails=nodeDetails)
		runtime.logger.report('createNewConfig: provider: {provider!r}', provider=nodeDetails.get('provider', ' '))
		runtime.logger.report('createNewConfig: platform: {platform!r}', platform=nodeDetails.get('platform', ' '))
		runtime.logger.report('createNewConfig: version: {version!r}', version=nodeDetails.get('version', ' '))
		matchCriteriaExpression = []
		className = runtime.endpoint.get('data').get('node_type')

		vendor = nodeDetails.get('vendor')
		vendorString = ''
		if vendor is not None:
			vendorString = vendor.replace(' ', '_')
			vendorSection = {
					"condition": {
						"class_name": className,
						"attribute": "vendor",
						"operator": "==",
						"value": nodeDetails.get('vendor')
					}
				}
			matchCriteriaExpression.append(vendorSection)

		platform = nodeDetails.get('platform')
		platformString = ''
		if platform is not None:
			platformString = platform.replace(' ', '_')
			platformSection = {
					"condition": {
						"class_name": className,
						"attribute": "platform",
						"operator": "==",
						"value": nodeDetails.get('platform')
					}
				}
			matchCriteriaExpression.append(platformSection)

		version = nodeDetails.get('version')
		versionString = ''
		if version is not None:
			versionString = version.replace(' ', '_')
			versionSection = {
					"condition": {
						"class_name": className,
						"attribute": "version",
						"operator": "==",
						"value": nodeDetails.get('version')
					}
				}
			matchCriteriaExpression.append(versionSection)

		provider = nodeDetails.get('provider')
		providerString = ''
		if provider is not None:
			providerString = provider.replace(' ', '_')
			providerSection = {
					"condition": {
						"class_name": className,
						"attribute": "hardware_provider",
						"operator": "==",
						"value": nodeDetails.get('provider')
					}
				}
			matchCriteriaExpression.append(providerSection)

		nameString = vendorString + '_' + providerString + '_' + platformString + '_' + versionString
		newConfig['name'] = nameString.strip('_')
		newConfig['createdBy'] = __name__
		hostName = nodeDetails['hostname']
		if nodeDetails['domain'] is not None:
			hostName = hostName + '.' + nodeDetails['domain']
		newConfig['description'] = 'Automatically built from endpoint {} : vendor({}) provider({}) platform({}) version({})'.format(hostName, nodeDetails.get('vendor'), nodeDetails.get('provider'), nodeDetails.get('platform'), nodeDetails.get('version'))
		newConfig['matchCriteria'] = {
			"operator": "and",
			"expression": matchCriteriaExpression
		}
		newConfig['parameters'] = configParameters

	except:
		runtime.setError(__name__)

	## end createNewConfig
	return newConfig


def constructParameters(runtime, processDictionary, softwareDictionary, startTaskDictionary):
	"""Build the parameters section of the config group.

	Arguments:
	  runtime (dict)             : object used for providing I/O for jobs and
	                               tracking the job thread through its runtime
	  processDictionary (dict)   : processes pulled from the Node endpoint
	  softwareDictionary (dict)  : software pulled from the Node endpoint
	  startTaskDictionary (dict) : software pulled from the Node endpoint
	"""
	configParameters = {}
	try:
		processFilterExcludeOverrideCompare = runtime.endpoint.get('data').get('parameters', {}).get('processFilterExcludeOverrideCompare', '==')
		processFilterExcludeOverrideList = runtime.endpoint.get('data').get('parameters', {}).get('processFilterExcludeOverrideList', [])
		interpreters = runtime.endpoint.get('data').get('parameters').get('interpreters', [])
		softwareFilterExcludeOverrideCompare = runtime.endpoint.get('data').get('parameters', {}).get('softwareFilterExcludeOverrideCompare', 'regex')
		softwareFilterExcludeOverrideList = runtime.endpoint.get('data').get('parameters', {}).get('softwareFilterExcludeOverrideList', [])
		runtime.logger.report('   constructParameters: processFilterExcludeOverrideCompare {processFilterExcludeOverrideCompare!r}', processFilterExcludeOverrideCompare=processFilterExcludeOverrideCompare)
		runtime.logger.report('   constructParameters: processFilterExcludeOverrideList {processFilterExcludeOverrideList!r}', processFilterExcludeOverrideList=processFilterExcludeOverrideList)
		runtime.logger.report('   constructParameters: interpreters {interpreters!r}', interpreters=interpreters)
		runtime.logger.report('   constructParameters: softwareFilterExcludeOverrideCompare {softwareFilterExcludeOverrideCompare!r}', softwareFilterExcludeOverrideCompare=softwareFilterExcludeOverrideCompare)
		runtime.logger.report('   constructParameters: softwareFilterExcludeOverrideList {softwareFilterExcludeOverrideList!r}', softwareFilterExcludeOverrideList=softwareFilterExcludeOverrideList)

		## Processes
		#runtime.logger.report('processDictionary: {processDictionary!r}', processDictionary=processDictionary)
		procList = []
		for pid, entry in processDictionary.items():
			(attributes, ppid, objectId) = entry
			process_name = attributes.get('name')
			if process_name is not None:
				skip = False
				## See if this process is in the interpreter list
				for interpreter in interpreters:
					if (interpreter == process_name or re.search('^{}\:'.format(interpreter), process_name)):
						runtime.logger.report('   constructParameters: process name {processName!r} was filtered out because it is in the interpreter list.', processName=process_name, searchString=searchString)
						skip = True
						break
				if skip:
					continue
				## See if this process is in the override list
				for filterExp in processFilterExcludeOverrideList:
					if (filterExp is None or len(filterExp) <= 0):
						continue
					searchString = filterExp.strip()
					if (compareFilter(processFilterExcludeOverrideCompare, searchString, process_name)):
						runtime.logger.report('   constructParameters: process name {processName!r} was filtered out by matchString {searchString!r} in the processFilterExcludeOverrideList.', processName=process_name, searchString=searchString)
						skip = True
						break
				if skip:
					continue
				## Extend this to filter on name, user, and path?
				procList.append(process_name)
		newProcList = sorted(list(set(procList)))
		runtime.logger.report('processFilterExcludeList: {processFilterExcludeList!r}', processFilterExcludeList=newProcList)
		configParameters['processFilterExcludeCompare'] = '=='
		configParameters['processFilterExcludeList'] = newProcList

		## Software
		#runtime.logger.report('softwareDictionary: {softwareDictionary!r}', softwareDictionary=softwareDictionary)
		swList = []
		for entry in softwareDictionary:
			softwareName = entry.get('name')
			if softwareName is not None:
				## See if this software is in the override list
				skip = False
				for filterExp in softwareFilterExcludeOverrideList:
					if (filterExp is None or len(filterExp) <= 0):
						continue
					searchString = filterExp.strip()
					if (compareFilter(softwareFilterExcludeOverrideCompare, searchString, softwareName)):
						runtime.logger.report('   constructParameters: software name {softwareName!r} was filtered out by matchString {searchString!r} in the softwareFilterExcludeOverrideList.', softwareName=softwareName, searchString=searchString)
						skip = True
						break
				if skip:
					continue
				swList.append(softwareName)
		newSwList = sorted(list(set(swList)))
		runtime.logger.report('softwareFilterExcludeList: {softwareFilterExcludeList!r}', softwareFilterExcludeList=newSwList)
		configParameters['softwareFilterExcludeCompare'] = '=='
		configParameters['softwareFilterExcludeList'] = newSwList
		configParameters['softwareFilterFlag'] = True
		configParameters['softwareFilterByPackageName'] = True
		configParameters['softwareFilterByVendor'] = False
		configParameters['softwareFilterByCompany'] = False
		configParameters['softwareFilterByOwner'] = False

		## Start Tasks
		#runtime.logger.report('startTaskDictionary: {startTaskDictionary!r}', startTaskDictionary=startTaskDictionary)
		ssList = []
		for entry in startTaskDictionary:
			ssList.append(entry)
		newSsList = sorted(list(set(ssList)))
		runtime.logger.report('startTaskFilterExcludeList: {startTaskFilterExcludeList!r}', startTaskFilterExcludeList=newSsList)
		configParameters['startTaskFilterExcludeCompare'] = '=='
		configParameters['startTaskFilterExcludeList'] = newSsList
		configParameters['startTaskFilterFlag'] = True
		configParameters['startTaskFilterByName'] = True
		configParameters['startTaskFilterByDisplayName'] = False
		configParameters['startTaskFilterByStartName'] = False
		configParameters['startTaskFilterByActiveState'] = True

	except:
		runtime.setError(__name__)

	## end constructParameters
	return configParameters


def issueApiCall(runtime):
	endpoint = None
	## Get the parameters
	inputQuery = runtime.parameters.get('inputQuery')
	targetIp = runtime.parameters.get('endpointIp')

	## Corresponding directory for our input query
	jobScriptPath = os.path.dirname(os.path.realpath(__file__))
	jobPath = os.path.abspath(os.path.join(jobScriptPath, '..'))

	## Load the file containing the query
	queryFile = os.path.join(jobPath, 'input', inputQuery + '.json')
	if not os.path.isfile(queryFile):
		raise EnvironmentError('JSON query file does not exist: {}'.format(queryFile))
	queryContent = None
	with open(queryFile, 'r') as fp:
		queryContent = fp.read()

	## We do not know shell type, and in the future there may be more. So we
	## will loop through each one, trying until we find it.

	## Note: previously this was sent in by the endpoint query, but when we
	## switched over to make the IP a parameter instead... the shell details are
	## no longer sent into the job. Hence this step to request from the API.
	## The idea was to simplify user experience by adding more code.
	queryResults = None
	for shellType in validShellTypes:
		thisQuery = queryContent
		## Replace <VALUE1> and <VALUE2> placeholders:
		##   VALUE1 = the shell type: PowerShell or SSH
		##   VALUE2 = the IP address of the target endpoint you wish to template
		thisQuery = thisQuery.replace('<VALUE1>', '"{}"'.format(shellType))
		thisQuery = thisQuery.replace('<VALUE2>', '"{}"'.format(targetIp))

		queryResults = getApiQueryResultsFull(runtime, thisQuery, resultsFormat='Nested', headers={'removeEmptyAttributes': False})
		if queryResults is not None and len(queryResults[shellType]) > 0:
			break

	if queryResults is None or len(queryResults[shellType]) <= 0:
		raise EnvironmentError('Could not find endpoint {} with a correspoinding shell. Please make sure to run the corresponding "Find" job first.'.format(targetIp))

	runtime.logger.report('queryResults: {queryResults!r}...', queryResults=queryResults)
	## Set the protocol data on runtime, as though it was sent in regularly.
	## And don't use 'get'; allow exceptions here if endpoint values are missing
	endpoint = queryResults[shellType][0]
	runtime.endpoint = {
		"class_name" : endpoint["class_name"],
		"identifier" : endpoint["identifier"],
		"data" : endpoint["data"]
	}
	runtime.setParameters()

	return endpoint


def getNodeDetails(runtime):
	"""Pull attributes off the node sent in the endpoint.

	Arguments:
	  runtime (dict) : object used for providing I/O for jobs and tracking
	                   the job thread through its runtime.
	"""
	nodeDetails = {}
	endpoint = issueApiCall(runtime)

	## Node should be directly connected to the endpoint linchpin
	objectsLinkedToLinchpin = endpoint.get('children',{})
	nodeFound = False
	hostname = None
	for objectLabel, objectList in objectsLinkedToLinchpin.items():
		runtime.logger.report(' looking for Node in related objects label {objectLabel!r}...', objectLabel=objectLabel)
		for entry in objectList:
			if 'hostname' not in entry.get('data').keys():
				break
			nodeDetails['hostname'] = entry.get('data').get('hostname')
			nodeDetails['domain'] = entry.get('data').get('domain')
			nodeDetails['vendor'] = entry.get('data').get('vendor')
			nodeDetails['platform'] = entry.get('data').get('platform')
			nodeDetails['version'] = entry.get('data').get('version')
			nodeDetails['provider'] = entry.get('data').get('hardware_provider')
			runtime.logger.report(' --> found hostname {hostname!r}: {vendor!r}, {platform!r}, {version!r}, {provider!r}', hostname=nodeDetails['hostname'], vendor=nodeDetails['vendor'], platform=nodeDetails['platform'], version=nodeDetails['version'], provider=nodeDetails['provider'])
			return nodeDetails

	## end getNodeDetails
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict) : object used for providing I/O for jobs and tracking
	                   the job thread through its runtime.
	"""
	client = None
	try:
		nodeDetails = getNodeDetails(runtime)

		## Pull details from the node object, used in creating automated entry
		nodeDetails = getNodeDetails(runtime)
		if nodeDetails is None:
			raise EnvironmentError('Unable to pull node details from endpoint.')

		## Configure shell client
		client = getClient(runtime)
		if client is not None:
			## Open client session before starting the work
			client.open()

			## Go after all processes
			runtime.endpoint.get('data').get('parameters', {})['processFilterExcludeList'] = []
			## Go after all software
			runtime.endpoint.get('data').get('parameters', {})['softwareFilterFlag'] = False
			## Only go after Running Services
			runtime.endpoint.get('data').get('parameters', {})['startTaskFilterFlag'] = True
			runtime.endpoint.get('data').get('parameters', {})['startTaskFilterExcludeCompare'] = '=='
			runtime.endpoint.get('data').get('parameters', {})['startTaskFilterExcludeList'] = ['Stopped']
			runtime.endpoint.get('data').get('parameters', {})['startTaskFilterByActiveState'] = True
			runtime.endpoint.get('data').get('parameters', {})['startTaskFilterByName'] = False
			runtime.endpoint.get('data').get('parameters', {})['startTaskFilterByDisplayName'] = False
			runtime.endpoint.get('data').get('parameters', {})['startTaskFilterByStartName'] = False

			nodeId = 'tempId'
			processDictionary = getProcesses(runtime, client, nodeId, trackResults=False, includeFilteredProcesses=True)
			softwareDictionary = getSoftwarePackages(runtime, client, nodeId, trackResults=False)
			startTaskDictionary = getStartTasks(runtime, client, nodeId, trackResults=False)

			## Good house keeping; though I force this after the exception below
			client.close()

			## Create the parameters section from the above result sets
			configParameters = constructParameters(runtime, processDictionary, softwareDictionary, startTaskDictionary)
			## Create the rest of the configGroup
			newConfig = createNewConfig(runtime, nodeDetails, configParameters)
			## Now backup the previous file and create an updated file
			modifyConfigGroupFile(runtime, newConfig)

			## Update the runtime status to success
			runtime.status(1)

	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end startJob
	return
