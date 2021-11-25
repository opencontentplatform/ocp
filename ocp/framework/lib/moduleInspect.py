"""Utility to manage the validation and deployment of add-on content."""
import os, re, sys, traceback
import inspect
import zipfile
import shutil
import stat
import time

## Add openContentPlatform directories onto the sys path
thisPath = os.path.dirname(os.path.abspath(__file__))
basePath = os.path.abspath(os.path.join(thisPath, '..'))
if basePath not in sys.path:
	sys.path.append(basePath)
import env
env.addLibPath()
import utils


def loadAddOnModules(logger):
	try:
		databaseSchemas = {}
		for packageName in os.listdir(env.contentGatheringPkgPath):
			if packageName == '__pycache__':
				continue
			packageDir = os.path.join(env.contentGatheringPkgPath, packageName)
			if (os.path.isdir(packageDir) and os.path.isdir(os.path.join(packageDir, 'database'))):
				parseModules(logger, databaseSchemas, os.path.join(packageDir, 'database'), packageName)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in loadAddOnModules:  {}'.format(stacktrace))

	## end loadAddOnModules
	return


def cleanDirectory(location):
	fileList = os.listdir(location)
	for fileName in fileList:
		try:
			fullpath=os.path.join(location, fileName)
			if os.path.isfile(fullpath):
				os.chmod(fullpath, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
				os.remove(os.path.join(location, fileName))
			elif os.path.islink(fullpath):
				os.unlink(fullpath)
			elif os.path.isdir(fullpath):
				if len(os.listdir(fullpath)) > 0:
					cleanDirectory(fullpath)
				shutil.rmtree(os.path.join(location, fileName))
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			logger.error('Exception in cleanDirectory:  {}'.format(stacktrace))

	## end cleanDirectory
	return


def getModuleNamesInDirectory(path):
	"""Get list of modules in the provided directory.

	Arguments:
	  path (str) : location to look for modules

	"""
	regex = '^(.+)\.py([cdo]?)$'
	result = []
	for entry in os.listdir(path):
			if not os.path.isfile(os.path.join(path, entry)):
				continue
			regexp_result = re.search(regex, entry)
			if regexp_result and regexp_result.group(1) != '__init__':
					result.append(regexp_result.group(1))

	## end getModuleNamesInDirectory
	return result


def parseModules(logger, databaseSchemas, modulePath, packageName):
	"""Parse any database table classes from all modules in given directory.

	This function is meant to be called multiple times, for all directories
	containing modules that define database classes. Call first with system
	default clasess, then with previously deployed add-on packages, and last
	with the new package to be validated/deployed.  It accomplishes a couple
	functions:

	First, it parses all files looking for database classes defined according
	to the sqlalchemy syntax. If the class has a '__tablename__' and a schema
	listed in '__table_args__', then it's considered a valid table.

	Second, it checks for any table conflicts (based on order of parsing) and
	logs this for visibility. This is a pre-deployment mechanism indended to
	help with package maintenance. If a user creates an add-on package with a
	class name conflicting with a current class, message it and prevent the
	package from being deployed.


	Arguments:
	  logger                 : The handler for database log
	  databaseSchemas (dict) : tracks DB schema/tables without conflicts
	  modulePath (str)       : directory containing this module
	  packageName (str)      : name of package containing the module(s)

	"""
	sys.path.append(modulePath)
	databaseObjects = []
	hitException = False
	for moduleName in sorted(getModuleNamesInDirectory(modulePath)):
		logger.info('InspectModule is parsing module [{}] from package [{}]'.format(moduleName, packageName))
		localDict = {}
		hitException = False
		try:
			t = __import__(moduleName)
			classResult = inspect.getmembers(t, lambda member: inspect.isclass(member) and member.__module__ == moduleName)
			for className, obj in classResult:
				classObj = getattr(t, className)
				dirList = dir(classObj)
				table = None
				schema = None
				for thisName in dirList:
					if thisName == '__tablename__':
						table = getattr(classObj, thisName)
					elif thisName == '__table_args__':
						args = getattr(classObj, thisName)
						schema = args['schema']
						if schema not in databaseSchemas:
							databaseSchemas[schema] = {}
					if (table and schema):
						if table in databaseSchemas[schema]:
							(prevClassName, prevModule) = databaseSchemas[schema][table]
							raise SystemError('Table name conflict with [{}].  Defined by [{}] and now [{}].  Skipping.'.format(table, prevModule, moduleName))
						else:
							localDict[table] = (className, moduleName, schema)
						break

		except SystemError:
			hitException = True
			logger.error('SystemError:  {}'.format(str(sys.exc_info()[1])))

		except:
			hitException = True
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			logger.error('Exception with module {}:  {}'.format(moduleName, stacktrace))

		## After processing all classes in the module, if working on the new
		## package and we didn't hit any problems with this module, then
		if not hitException:
			if len(localDict) <= 0:
				logger.debug('No appropriate database definitions found inside {}'.format(moduleName))
			else:
				for table, value in localDict.items():
					(className, moduleName, schema) = value
					logger.debug('  Class [{}.{}] uses table [{}]'.format(schema, className, table))
					databaseSchemas[schema][table] = (className, moduleName)

	## end parseModules
	return hitException


def main(pkgPath, pkgFile):
	"""Entry function for deployModule.

	This function is meant to be called multiple times, for all directories
	containing modules that define database classes. Call first with system
	default clasess, then with previously deployed add-on packages, and last
	with the new package to be validated/deployed.  It accomplishes a couple
	functions:

	First, it parses all files looking for database classes defined according
	to the sqlalchemy syntax. If the class has a '__tablename__' and a schema
	listed in '__table_args__', then it's considered a valid table.

	Second, it checks for any table conflicts (based on order of parsing) and
	logs this for visibility. This is a pre-deployment mechanism indended to
	help with package maintenance. If a user creates an add-on package with a
	class name conflicting with a current class, message it and prevent the
	package from being deployed.


	Arguments:
	  pkgPath (str)  : directory containing the package to be deployed
	  pkgFile (str)  : name of the package file (e.g. testPackage.zip)

	"""
	try:
		## Global section
		globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))
		logger = utils.setupLogger('Database', env, globalSettings['fileContainingCoreLogSettings'])

		## Assume package was created (by API); explode package in directory
		packageName = pkgFile.split('.')[0]
		package = os.path.join(pkgPath, pkgFile)
		newPackagePath = os.path.join(env.contentGatheringPkgPath, packageName)
		try:
			if os.path.isdir(newPackagePath):
				## Remove previous package version before creating new artifacts
				logger.info('Removing previous package version on server: {}'.format(newPackagePath))
				cleanDirectory(newPackagePath)
				time.sleep(.1)
			if not os.path.isdir(newPackagePath):
				os.mkdir(newPackagePath)
			zipfile.ZipFile(package, 'r').extractall(newPackagePath)
		except IOError:
			logger.error('Could not open compressed package: {}'.format(package))
		else:
			databaseSchemas = {}
			## First parse the packaged schemas
			parseModules(logger, databaseSchemas, env.schemaPath, 'default')
			## Next parse additional add-on modules from previous packages
			for entry in os.listdir(env.schemaAddonPath):
				## Exclude python cache directories and this package's directory
				## if it was deployed previously; intention is to overwrite.
				if entry == '__pycache__' or entry == packageName:
					continue
				addOnDir = os.path.join(env.schemaAddonPath, entry)
				if os.path.isdir(addOnDir):
					parseModules(logger, databaseSchemas, addOnDir, entry)

			## Now parse the new add-on module(s)
			logger.info('Previous modules complete.')
			hitException = parseModules(logger, databaseSchemas, os.path.join(newPackagePath, 'database'), packageName)
			## If we hit a problem, clean up the package artifacts
			if hitException:
				utils.cleanDirectory(newPackagePath)

			## Debug output for the logs:
			for schema in databaseSchemas:
				logger.info('  {0:43}  {1}'.format('SCHEMA.TABLE', 'MODULE.CLASS defining the table'))
				logger.info('  {}'.format('='*76))
				for table in databaseSchemas[schema]:
					(className, moduleName) = databaseSchemas[schema][table]
					logger.info('  {0:43}  {1}'.format(schema+'.'+table, moduleName+'.'+className))

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in deployModule:  {}'.format(stacktrace))

	## end main
	return


if __name__ == '__main__':
	sys.exit(main(r'E:\Work\openContentPlatform\temp', 'jobTemplate.zip'))
