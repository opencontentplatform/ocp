"""PowerShell detection library for Apple.

Stubbed only.

"""
import sys
import traceback
import re

## From openContentPlatform
import find_PowerShell
from utilities import setInstanceParameters


def queryForIps(client, runtime, ipAddresses):
	"""Query and parse IPs."""
	try:
		raise NotImplementedError()

	except:
		runtime.setError(__name__)

	## end queryForIps
	return


def queryComputerSystem(client, runtime, attrDict):
	"""Query and parse ComputerSystem attributes."""
	try:
		raise NotImplementedError()

	except:
		runtime.setError(__name__)

	## end queryComputerSystem
	return


def queryBios(client, runtime, attrDict):
	"""Query and parse BIOS attributes."""
	try:
		raise NotImplementedError()

	except:
		runtime.setError(__name__)

	## end queryBios
	return


def queryOperatingSystem(client, runtime, attrDict):
	"""Query and parse OperatingSystem attributes."""
	try:
		raise NotImplementedError()

	except:
		runtime.setError(__name__)

	## end queryOperatingSystem
	return


def queryApple(runtime, client, endpoint, protocolReference, osType):
	"""Run queries against a Apple endpoint.

	Arguments:
	  runtime (dict)    : object used for providing input into jobs and tracking
	                      the job thread through the life of its runtime
	  client            : PowerShell client
	  endpoint          : target endpoint for the discovery job
	  protocolReference : reference id
	"""
	try:
		## Query OperatingSystem for OS attributes
		osAttrDict = {}
		queryOperatingSystem(client, runtime, osAttrDict)
		runtime.logger.debug('osAttrDict: {osAttrDict!r}', osAttrDict=osAttrDict)

		## Only continue if the first query was successful
		if len(list(osAttrDict.keys())) > 0:
			runtime.jobStatus == 'SUCCESS'
			## Query BIOS for serial number and firmware
			biosAttrDict = {}
			queryBios(client, runtime, biosAttrDict)
			runtime.logger.debug('biosAttrDict: {biosAttrDict!r}', biosAttrDict=biosAttrDict)

			## Query ComputerSystem for name/domain and HW details
			csAttrDict = {}
			queryComputerSystem(client, runtime, csAttrDict)
			runtime.logger.debug('csAttrDict: {csAttrDict!r}', csAttrDict=csAttrDict)

			## Query for IPs
			ipAddresses = []
			queryForIps(client, runtime, ipAddresses)
			runtime.logger.debug('ipAddresses: {ipAddresses!r}', ipAddresses=ipAddresses)

			## If connections failed before succeeding, remove false negatives
			runtime.clearMessages()

			## Create the objects
			protocolId = find_PowerShell.createObjects(runtime, osType, osAttrDict, biosAttrDict, csAttrDict, ipAddresses, endpoint, protocolReference)

			## Assign shell configuration and potential config group
			setInstanceParameters(runtime, client, osType, endpoint, protocolId)
			runtime.logger.report('shell parameters: {shellParameters!r}', shellParameters=runtime.results.getObject(protocolId))
			runtime.logger.report('shell parameters: {shellParameters!r}', shellParameters=runtime.results.getObject(protocolId).get('shellConfig'))

	except:
		runtime.setError(__name__)

	## end queryApple
	return
