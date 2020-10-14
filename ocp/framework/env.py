"""Environment class.

This defines relative paths based on the installed location, and extends
some convenience functions to conditionally add to sys.path.

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Aug 17, 2017
	  1.1 : (CS) Moved external and internal private paths, Oct 14, 2020

"""
import os, sys

basePath = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

## ./conf
configPath = os.path.join(basePath, 'conf')
## ./docs
docsPath = os.path.join(basePath, 'docs')
## ./temp
tempPath = os.path.join(basePath, 'temp')

## ./runtime
runTimePath = os.path.join(basePath, 'runtime')
## ./runtime/log
logPath = os.path.join(runTimePath, 'log')
## ./runtime/pid
pidPath = os.path.join(runTimePath, 'pid')

## ./framework (the original script directory)
scriptPath = os.path.join(basePath, 'framework')
## ./framework/lib
libPath = os.path.join(scriptPath, 'lib')
## ./framework/lib/thirdParty
libThirdPartyPath = os.path.join(libPath, 'thirdParty')
## ./framework/service
servicePath = os.path.join(scriptPath, 'service')
## ./framework/client
clientPath = os.path.join(scriptPath, 'client')
## ./framework/database
databasePath = os.path.join(scriptPath, 'database')
## ./framework/database/schema
schemaPath = os.path.join(scriptPath, 'database', 'schema')

## ./content
packagePath = os.path.join(basePath, 'content')
## ./content/apiData/query
apiQueryPath = os.path.join(packagePath, 'apiData', 'query')
## ./content/contentGathering
contentGatheringPkgPath = os.path.join(packagePath, 'contentGathering')
## ./content/contentGathering/shared
contentGatheringSharedPath = os.path.join(contentGatheringPkgPath, 'shared')
## ./content/contentGathering/shared/script
contentGatheringSharedScriptPath = os.path.join(contentGatheringPkgPath, 'shared', 'script')
## ./content/contentGathering/shared/conf
contentGatheringSharedConfPath = os.path.join(contentGatheringPkgPath, 'shared', 'conf')
## ./content/contentGathering/shared/conf/configGroup
contentGatheringSharedConfigGroupPath = os.path.join(contentGatheringPkgPath, 'shared', 'conf', 'configGroup')
## ./content/contentGathering/shared/endpoint
contentGatheringSharedEndpointPath = os.path.join(contentGatheringPkgPath, 'shared', 'endpoint')
## ./content/universalJob
universalJobPkgPath = os.path.join(packagePath, 'universalJob')
## ./content/serverSide
serverSidePkgPath = os.path.join(packagePath, 'serverSide')

## ./conf/private
privatePath = os.path.join(configPath, 'private')
## ./conf/private/content
privateContentPath = os.path.join(privatePath, 'content')
privateContentCertPath = os.path.join(privateContentPath, 'certs')
privateContentKeyPath = os.path.join(privateContentPath, 'keys')
## ./conf/private/internal
privateInternalPath = os.path.join(privatePath, 'internal')
privateInternalCertPath = os.path.join(privateInternalPath, 'certs')
privateInternalKeyPath = os.path.join(privateInternalPath, 'keys')
## ./conf/private/external
privateExternalPath = os.path.join(privatePath, 'external')


def addFrameworkPath():
	"""Add ./framework to sys.path if not already there."""
	if scriptPath not in sys.path:
		sys.path.append(scriptPath)

def addScriptPath():
	addFrameworkPath()

def addLibPath():
	"""Add ./framework/lib to sys.path if not already there."""
	if libPath not in sys.path:
		sys.path.append(libPath)

def addLibThirdPartyPath():
	"""Add ./framework/lib/thirdParty to sys.path if not already there."""
	if libThirdPartyPath not in sys.path:
		sys.path.append(libThirdPartyPath)

def addExternalPath():
	"""Add ./external to sys.path if not already there."""
	if privateExternalPath not in sys.path:
		sys.path.append(privateExternalPath)

def addPackagePath():
	"""Add ./content to sys.path if not already there."""
	if packagePath not in sys.path:
		sys.path.append(packagePath)

def addContentGatheringPkgPath():
	"""Add ./content/contentGathering to sys.path if not already there."""
	if contentGatheringPkgPath not in sys.path:
		sys.path.append(contentGatheringPkgPath)

def addContentGatheringSharedScriptPath():
	"""Add ./content/contentGathering/shared/script to sys.path if not already there."""
	if contentGatheringSharedScriptPath not in sys.path:
		sys.path.append(contentGatheringSharedScriptPath)

def addUniversalJobPkgPath():
	"""Add ./content/universalJob to sys.path if not already there."""
	if universalJobPkgPath not in sys.path:
		sys.path.append(universalJobPkgPath)

def addServerSidePkgPath():
	"""Add ./content/serverSide to sys.path if not already there."""
	if serverSidePkgPath not in sys.path:
		sys.path.append(serverSidePkgPath)

def addServicePath():
	"""Add ./framework/service to sys.path if not already there."""
	if servicePath not in sys.path:
		sys.path.append(servicePath)

def addClientPath():
	"""Add ./framework/client to sys.path if not already there."""
	if clientPath not in sys.path:
		sys.path.append(clientPath)

def addDatabasePath():
	"""Add ./framework/database to sys.path if not already there."""
	if databasePath not in sys.path:
		sys.path.append(databasePath)

def addSchemaPath():
	"""Add ./framework/database/schema to sys.path if not already there."""
	if schemaPath not in sys.path:
		sys.path.append(schemaPath)
