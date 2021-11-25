"""Utility to manage the validation and deployment of add-on content."""
import os, sys, traceback
import zipfile
import re
import time
import json
import shutil
import hashlib
import filecmp
import difflib
from contextlib import suppress
from sqlalchemy import and_

## Concurrent-log-handler's version
try:
	from concurrent_log_handler import ConcurrentRotatingFileHandler as RFHandler
except ImportError:
	from warnings import warn
	warn("concurrent_log_handler package not installed. Using builtin log handler")
	## Python's version
	from logging.handlers import RotatingFileHandler as RFHandler

## Add openContentPlatform directories onto the sys path
thisPath = os.path.dirname(os.path.abspath(__file__))
basePath = os.path.abspath(os.path.join(thisPath, '..'))
if basePath not in sys.path:
	sys.path.append(basePath)
import env
env.addLibPath()

## From openContentPlatform
import utils
import database.schema.platformSchema as platformSchema
from database.connectionPool import DatabaseClient

validPackageSystems = {
	'contentgathering':
		{ 'name' : 'contentGathering',
		  'path' : env.contentGatheringPkgPath,
		  'dbClass' : platformSchema.JobContentGathering
		},
	'universaljob':
		{ 'name' : 'universalJob',
		  'path' : env.universalJobPkgPath,
		  'dbClass' : platformSchema.JobUniversal
		},
	'serverside':
		{ 'name' : 'serverSide',
		  'path' : env.serverSidePkgPath,
		  'dbClass' : platformSchema.JobServerSide
		}
	}


def listPackages():
	globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))
	logger = utils.setupLogger('Packages', env, globalSettings['fileContainingCoreLogSettings'])
	dbClient = getDbConnection(logger)
	## Cleanup this package result; prep work for comparison operation
	dbClass = platformSchema.ContentPackage
	packages = dbClient.session.query(dbClass).order_by(dbClass.system.desc(),dbClass.name.desc()).all()
	jsonReport = {}
	for package in packages:
		packageSystem = package.system
		packageName = package.name
		packageDate = package.time_created
		if packageSystem not in jsonReport:
			jsonReport[packageSystem] = []
		jsonReport[packageSystem].append({ 'name' : packageName, 'created' : packageDate })
	dbClient.session.commit()
	## And finally report
	strReport = json.dumps(jsonReport, default=utils.customJsonDumpsConverter, indent=4)
	logger.debug('Valid packages: \n{}'.format(str(strReport)))
	print('Valid packages: \n{}'.format(str(strReport)))

	## end listPackages
	return


def updatePackage(pkgName, pkgSystem='contentGathering', pkgPath=None, forceUpdate=True):
	globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))
	logger = utils.setupLogger('Packages', env, globalSettings['fileContainingCoreLogSettings'])
	dbClient = getDbConnection(logger)
	try:
		## Initialize directories for this work
		(packageBasePath, newPackagePath, oldPackagePath) = initializePaths(logger, pkgName)

		## Check the target system for this package
		if pkgSystem.lower() not in validPackageSystems:
			raise EnvironmentError('Content management expecting package for a valid system {}, but received unknown type: {}.'.format(validPackageSystems, pkgType))
		packageSystemName = validPackageSystems[pkgSystem.lower()]['name']
		packageSystemPath = validPackageSystems[pkgSystem.lower()]['path']
		## Default the new package location to the exploded dir on the server
		newPackagePath = os.path.join(packageSystemPath, pkgName)
		if pkgPath is not None:
			## And reset that location if one was designated in the call
			newPackagePath = pkgPath

		## If package is in the database already, extract into side-by-side path
		pkgExists = getContentPackage(logger, dbClient, oldPackagePath, pkgName, stripString='content,{},{}'.format(packageSystemName, pkgName))
		if pkgExists:
			## Compare the files with filecmp/difflib and present differences...
			changes = []
			comparePackageVersions(logger, pkgName, oldPackagePath, newPackagePath, changes)
			if len(changes) <= 0:
				logger.info('No changes found; package {} remains unchanged.'.format(pkgName))
			else:
				logger.info('Changes found in package {}, with the following files: {}'.format(pkgName, str(changes)))
				if not forceUpdate:
					logger.info('Leaving package unchanged because the forceUpdate flag was not set.')
				else:
					logger.info('Overwriting previous version...')
					loadPackageIntoDB(logger, pkgName, packageSystemName, ['content', packageSystemName], dbClient, newPackagePath)

		else:
			## First time load of the package into the database
			logger.error('Attempting to update a package that did not previously exist in the database. Please compress and then add the package first.')
			print('Attempting to update a package that did not previously exist in the database. Please compress and then add the package first.')

		## Cleanup
		logger.info('Finished content management work on package {}; cleaning up.'.format(pkgName))

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in updatePackage:  {}'.format(str(stacktrace)))

	## end updatePackage
	return


def removeFiles(logger, dbClient, packageName):
	try:
		dbClass = platformSchema.ContentPackageFile
		packageFiles = dbClient.session.query(dbClass).filter(and_(dbClass.package == packageName)).all()
		for packageFile in packageFiles:
			logger.debug('  Removing file {} --> Path: {}  Hash: {}  Size: {}'.format(packageFile.name, packageFile.path, packageFile.file_hash, packageFile.size))
			dbClient.session.delete(packageFile)
			dbClient.session.commit()

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in removeFiles:  {}'.format(stacktrace))

	## end removeFiles
	return


def removePackage(packageName):
	globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))
	logger = utils.setupLogger('Packages', env, globalSettings['fileContainingCoreLogSettings'])
	dbClient = getDbConnection(logger)
	try:
		logger.info('Searching for package in database: {}'.format(packageName))
		dbClass = platformSchema.ContentPackage
		package = dbClient.session.query(dbClass).filter(dbClass.name == packageName).first()
		if package is None:
			logger.info('Package {} not found in database... nothing to do.'.format(packageName))
		else:
			logger.info('Removing package files...'.format(packageName))
			dbClient.session.commit()
			## Remove all files first
			removeFiles(logger, dbClient, packageName)
			## And now remove the package
			package = dbClient.session.query(dbClass).filter(dbClass.name == packageName).first()
			packageType = package.system
			dbClient.session.delete(package)
			dbClient.session.commit()
			## Remove from filesystem
			packageSystemPath = validPackageSystems[pkgSystem.lower()]['path']
			packagePath = os.path.join(packageSystemPath, packageName)
			logger.info('Removing files from server directory: {}...'.format(packagePath))
			utils.cleanDirectory(logger, packagePath)
			logger.info('Package {} removed.'.format(packageName))

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in removePackage:  {}'.format(stacktrace))

	with suppress(Exception):
		dbClient.session.close()
		dbClient.close()

	## end removePackage
	return


def reportFileDiff(logger, newFile, oldFile):
	## Note: use readlines instead of read, for difflib to produce nice formats
	with open(newFile) as f1:
		newContent = f1.readlines()
	with open(oldFile) as f2:
		oldContent = f2.readlines()
	# Find and print the diff:
	output = difflib.context_diff(newContent, oldContent, fromfile=newFile, tofile=oldFile, n=3, lineterm='\n')
	for line in output:
		logger.info(line.strip('\n'))


def reportDiffs(logger, compareDetails, changes):
	for name in compareDetails.diff_files:
		logger.info('File {} found in {} and {}'.format(name, compareDetails.left, compareDetails.right))
		if not filecmp.cmp(compareDetails.left, compareDetails.right, shallow=False):
			logger.info(' --> contents are found different!')
			reportFileDiff(logger, os.path.join(compareDetails.left, name), os.path.join(compareDetails.right, name))
			changes.append(name)

	for subDetails in compareDetails.subdirs.values():
		reportDiffs(logger, subDetails, changes)


def comparePackageVersions(logger, pkgName, oldPackagePath, newPackagePath, changes):
	"""Compare the files with filecmp/difflib and present differences."""
	logger.debug(' Comparing package versions...')
	compareDetails = filecmp.dircmp(newPackagePath, oldPackagePath)
	reportDiffs(logger, compareDetails, changes)


def getDbConnection(logger):
	## Attempt connection
	dbClient = DatabaseClient(logger)
	if dbClient is None:
		raise SystemError('Failed to connect to database.')

	## end getDbConnection
	return dbClient


def insertEndpointQuery(logger, dbClient, entry, packageName, endpointFile):
	try:
		query = None
		if not endpointFile.endswith('.json'):
			## Don't load endpointScripts; table expects JSON, not Python format
			return
		m = re.search('(.*)\.json$', entry)
		name = m.group(1)
		with open(endpointFile, 'r') as json_data:
			query = json.load(json_data)

		attributes = {}
		attributes['name'] = name
		attributes['json_query'] = query

		logger.debug('  Inserting endpoint query: {}  from package: {} '.format(entry, packageName))
		dbClass = platformSchema.EndpointQuery
		endpointQuery = dbClient.session.query(dbClass).filter(dbClass.name == name).first()
		## Insert the file if it doesn't exist
		if endpointQuery is None:
			attributes['object_created_by'] = 'contentManagement module'
			logger.debug('  {} is new; inserting...'.format(attributes['name']))
			endpointQuery = dbClass(**attributes)
			endpointQuery = dbClient.session.add(endpointQuery)
			dbClient.session.commit()
		## The file has been tracked before
		else:
			attributes['object_updated_by'] = 'contentManagement module'
			logger.debug('  {} already exists; overwriting...'.format(attributes['name']))
			endpointQuery = dbClass(**attributes)
			endpointQuery = dbClient.session.merge(endpointQuery)
			dbClient.session.commit()
	except:
		logger.error('Error loading endpoint file {}: {}'.format(endpointFile, str(sys.exc_info()[1])))

	## end insertEndpointQuery
	return


def insertJob(logger, dbClient, entry, packageSystemName, packageName, jobFile):
	try:
		jobSettings = None
		with open(jobFile, 'r') as json_data:
			jobSettings = json.load(json_data)

		try:
			jobShortName = jobSettings.get('jobName')
			jobName = '{}.{}'.format(packageName, jobShortName)
			attributes = {}
			attributes['name'] = jobName
			attributes['package'] = packageName
			attributes['realm'] = jobSettings.get('realm', 'default')
			attributes['active'] = not jobSettings.get('isDisabled', True)
			attributes['content'] = jobSettings

			logger.debug('  Inserting job: {}.{}'.format(packageName, jobName))
			dbClass = validPackageSystems[packageSystemName.lower()]['dbClass']
			job = dbClient.session.query(dbClass).filter(dbClass.name == jobName).first()
			## Insert the file if it doesn't exist
			if job is None:
				attributes['object_created_by'] = 'contentManagement module'
				logger.debug('  {} is new; inserting...'.format(attributes['name']))
				job = dbClass(**attributes)
				job = dbClient.session.add(job)
				dbClient.session.commit()
			## The file has been tracked before
			else:
				attributes['object_updated_by'] = 'contentManagement module'
				logger.debug('  {} already exists; overwriting...'.format(attributes['name']))
				job = dbClass(**attributes)
				job = dbClient.session.merge(job)
				dbClient.session.commit()
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			logger.error('Exception on job {}:  {}'.format(jobShortName, stacktrace))
	except:
		logger.error('Error loading job file {}: {}'.format(jobFile, str(sys.exc_info()[1])))

	## end insertJob
	return


def insertFile(logger, dbClient, attributes):
	try:
		logger.debug('  {} --> Path: {}  Hash: {}  Size: {}'.format(attributes['name'], attributes['path'], attributes['file_hash'], attributes['size']))
		dbClass = platformSchema.ContentPackageFile
		packageFile = dbClient.session.query(dbClass).filter(and_(dbClass.package == attributes['package'], dbClass.name == attributes['name'], dbClass.path == attributes['path'])).first()
		## Insert the file if it doesn't exist
		if packageFile is None:
			logger.debug('  {} is new; inserting'.format(attributes['name']))
			attributes['object_created_by'] = 'contentManagement'
			packageFile = dbClass(**attributes)
			packageFile = dbClient.session.add(packageFile)
			dbClient.session.commit()
		## The file has been tracked before
		else:
			logger.debug('  {} already exists; overwriting'.format(attributes['name']))
			packageFile = dbClass(**attributes)
			packageFile = dbClient.session.merge(packageFile)
			dbClient.session.commit()

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in insertFile:  {}'.format(stacktrace))

	## end insertFile
	return


def getFileChunk(targetFile, chunkSize=8192):
	## Generator function that returns chunks of
	## binary data, to be processed one at a time
	with open(targetFile, 'rb') as fh:
		while 1:
			thisChunk = fh.read(chunkSize)
			if thisChunk:
				## generator
				yield thisChunk
			else:
				break

	## end getFileChunk
	return


def getFileDataAndHash(targetFile):
	## Iterate through file with a generator function
	## that yields a specified sized chunk at a time
	md5Hash = hashlib.md5()
	## Need to use a bytearray to concat binary chunks
	allChunks = bytearray()
	for bytes in getFileChunk(targetFile, 8):
		md5Hash.update(bytes)
		allChunks.extend(bytes)
	fileHash = md5Hash.hexdigest()

	## end getFileDataAndHash
	return (fileHash, allChunks)


def recursePathsAndInsertFiles(thisPath, relativePath, packageSystemName, fileIndex, dbClient, packageName, logger, isJobPath=False, isEndpointPath=False):
	"""Go through all files/directories in the package, and load into the DB."""
	for entry in os.listdir(thisPath):
		if entry == '__pycache__':
			continue
		target = os.path.join(thisPath, entry)
		thisIndex = {}
		if os.path.isdir(target):
			newPath = '{},{}'.format(relativePath, entry)
			isEndpointPath = False
			isJobPath = False
			if entry == 'job':
				isJobPath = True
			elif entry == 'endpoint':
				isEndpointPath = True
			recursePathsAndInsertFiles(target, newPath, packageSystemName, thisIndex, dbClient, packageName, logger, isJobPath, isEndpointPath)
		else:
			fileSize = int(os.path.getsize(target))
			(fileHash, data) = getFileDataAndHash(target)
			thisIndex['file_hash'] = fileHash
			thisIndex['name'] = entry
			thisIndex['path'] = relativePath

			attributes = {}
			attributes['package'] = packageName
			attributes['file_hash'] = fileHash
			attributes['size'] = fileSize
			attributes['name'] = entry
			attributes['path'] = relativePath
			attributes['content'] = data

			## Insert
			insertFile(logger, dbClient, attributes)

			## Do something more with job descriptors and endpoint queries
			if isJobPath:
				insertJob(logger, dbClient, entry, packageSystemName, packageName, target)
			elif isEndpointPath:
				insertEndpointQuery(logger, dbClient, entry, packageName, target)

		fileIndex[entry] = thisIndex

	## end recursePathsAndInsertFiles
	return


def updateModuleInDB(logger, fileIndex, packageName, package, dbClient):
	"""Updates the package's files attribute with all files processed."""
	package = dbClient.session.query(platformSchema.ContentPackage).filter(platformSchema.ContentPackage.name == packageName).first()
	setattr(package, 'files', fileIndex)
	setattr(package, 'object_updated_by', 'contentManagement')
	package = dbClient.session.merge(package)
	dbClient.session.commit()


def loadPackageIntoDB(logger, packageName, packageSystemName, packagePath, dbClient, newPackagePath):
	snapshot = None
	try:
		## Cleanup this package result; prep work for comparison operation
		logger.debug('Working on package {}'.format(packageName))
		dbClass = platformSchema.ContentPackage
		package = dbClient.session.query(dbClass).filter(dbClass.name == packageName).first()
		## Insert the package if it doesn't exist
		if package is None:
			logger.debug(' Inserting Package {}'.format(packageName))
			packageData = {}
			packageData['name'] = packageName
			packageData['path'] = packagePath
			packageData['system'] = packageSystemName
			packageData['object_created_by'] = 'contentManagement'
			package = dbClass(**packageData)
			package = dbClient.session.merge(package)
			dbClient.session.commit()
			package = dbClient.session.query(dbClass).filter(dbClass.name == packageName).first()

		## The package has been tracked before
		else:
			logger.debug(' package {} exists; forcing an update...'.format(packageName))

		## Get package snapshot
		snapshot = getattr(package, 'snapshot')
		dbClient.session.commit()

		## Now create entries for all the files
		fileIndex = {}
		relativePath = ['content', packageSystemName, packageName]
		relativePathString = ','.join(relativePath)
		logger.debug(' --> recursePathsAndInsertFiles')
		recursePathsAndInsertFiles(newPackagePath, relativePathString, packageSystemName, fileIndex, dbClient, packageName, logger)

		## And finally update the top level package entry with the file list
		logger.debug('fileIndex: {}'.format(fileIndex))
		updateModuleInDB(logger, fileIndex, packageName, snapshot, dbClient)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in loadPackageIntoDB:  {}'.format(stacktrace))

	## end loadPackageIntoDB
	return


def getContentPackage(logger, dbClient, tmpPath, pkgName, stripString=None):
	"""Drops the files into a specified location on the server."""
	pkgExists = False
	try:
		contentPackage = dbClient.session.query(platformSchema.ContentPackage).filter(platformSchema.ContentPackage.name == pkgName).first()
		if contentPackage:
			pkgExists = True
			packageName = contentPackage.name
			snapshot = contentPackage.snapshot
			contentPackageFiles = dbClient.session.query(platformSchema.ContentPackageFile).filter(platformSchema.ContentPackageFile.package == pkgName).all()
			for packageFile in contentPackageFiles:
				fileName = packageFile.name
				fileContent = packageFile.content
				pathString = packageFile.path
				directory = tmpPath
				if stripString:
					## Normally this drops files into ./content/system/pkg on
					## the server; this allows dropping files into a temp dir
					pathString = re.sub(stripString, '', pathString)
				for subPath in pathString.split(','):
					directory = os.path.join(directory, subPath)
					if not os.path.exists(directory):
						os.mkdir(directory)
				filePath = directory
				with open(os.path.join(filePath, fileName), 'wb') as fh:
					fh.write(fileContent)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in getContentPackage:  {}'.format(stacktrace))

	## end getContentPackage
	return pkgExists


def extractTar(sourceFile, destinationPath):
	"""Extract a tar file type."""
	f = tarfile.open(sourceFile, 'r')
	f.extractall(destinationPath)

def extractZip(sourceFile, destinationPath):
	"""Extract a zip file type."""
	zipfile.ZipFile(sourceFile, 'r').extractall(destinationPath)

def extractContents(logger, compressedFile, pkgName, pkgExtension, packageBasePath, newPackagePath):
	"""Extract package into the local runtime directory."""
	try:
		pkgFile = compressedFile.split(os.sep)[-1]
		logger.debug('Working on {} package: {}'.format(pkgExtension.upper(), pkgFile))
		if pkgExtension.lower() == 'zip':
			extractZip(compressedFile, newPackagePath)
		elif pkgExtension.lower() == 'tar':
			extractTar(compressedFile, newPackagePath)
	except:
		exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
		raise EnvironmentError('Could not open package {}. {}'.format(compressedFile, str(exceptionOnly)))

	## end extractContents
	return


def initializePaths(logger, packageName):
	"""Assign and initialize temp directories for this work."""
	packageBasePath = os.path.join(env.runTimePath, 'packages', packageName)
	newPackagePath = os.path.join(packageBasePath, 'new')
	oldPackagePath = os.path.join(packageBasePath, 'old')
	if os.path.isdir(packageBasePath):
		## Remove previous package version before creating new artifacts
		logger.info('Removing previous directory on server: {}'.format(packageBasePath))
		utils.cleanDirectory(logger, packageBasePath)
		time.sleep(.1)
	if os.path.isdir(packageBasePath):
		raise EnvironmentError('Failed to clean previous directory on server: {}. Unable to continue with package operation.'.format(packageBasePath))
	os.makedirs(packageBasePath)
	os.mkdir(newPackagePath)
	os.mkdir(oldPackagePath)

	## end initializePaths
	return (packageBasePath, newPackagePath, oldPackagePath)


def validatePackage(packageName, compressedFile, pkgSystem='contentGathering', forceUpdate=False):
	"""Entry function.

	Arguments:
	  compressedFile (str) : fully qualified package to be deployed
	  forceUpdate (bool)   : whether to force update if package already exists
	  pkgSystem (str)      : package type (target system/service to deploy into)

	"""
	globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))
	logger = utils.setupLogger('Packages', env, globalSettings['fileContainingCoreLogSettings'])
	dbClient = getDbConnection(logger)
	try:
		## Check the extension
		(pkgName, pkgExtension) = compressedFile.split('.')
		if pkgExtension.lower() != 'zip' and pkgExtension.lower() != 'tar':
			raise EnvironmentError('Content management expecting package in either ZIP or TAR format; unable to work with this format: {}.'.format(pkgExtension))

		## Initialize directories for this work
		(packageBasePath, newPackagePath, oldPackagePath) = initializePaths(logger, packageName)

		## Check the target system for this package
		if pkgSystem.lower() not in validPackageSystems:
			raise EnvironmentError('Content management expecting package for a valid system {}, but received unknown type: {}.'.format(validPackageSystems, pkgType))
		packageSystemName = validPackageSystems[pkgSystem.lower()]['name']
		packageSystemPath = validPackageSystems[pkgSystem.lower()]['path']

		## Extract contents into a temp runtime directory
		extractContents(logger, compressedFile, packageName, pkgExtension, packageBasePath, newPackagePath)

		## If package is in the database already, extract into side-by-side path
		pkgExists = getContentPackage(logger, dbClient, oldPackagePath, packageName, stripString='content,{},{}'.format(packageSystemName, packageName))
		if pkgExists:
			## Compare the files with filecmp/difflib and present differences...
			changes = []
			comparePackageVersions(logger, packageName, oldPackagePath, newPackagePath, changes)
			if len(changes) <= 0:
				logger.info('No changes found; package {} remains unchanged.'.format(packageName))
			else:
				logger.info('Changes found in package {}, with the following files: {}'.format(packageName, str(changes)))
				if not forceUpdate:
					logger.info('Leaving package unchanged because the forceUpdate flag was not set.')
					print('Leaving package unchanged because the forceUpdate flag was not set.')
				else:
					logger.info('Overwriting previous version...')
					print('Overwriting previous version...')
					loadPackageIntoDB(logger, packageName, packageSystemName, ['content', packageSystemName], dbClient, newPackagePath)

		else:
			## First time load of the package into the database
			logger.info('Attempting to load new package into database...')
			loadPackageIntoDB(logger, packageName, packageSystemName, ['content', packageSystemName], dbClient, newPackagePath)

		## Cleanup
		logger.info('Finished content management work on package {}; cleaning up.'.format(packageName))
		utils.cleanDirectory(logger, packageBasePath)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in validatePackage:  {}'.format(str(stacktrace)))

	with suppress(Exception):
		dbClient.session.close()
		dbClient.close()
	## end validatePackage
	return


def baselinePackagesInDatabase():
	"""Called by the installer to load all content on server into the DB."""
	dbClient = None
	try:
		globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))
		logger = utils.setupLogger('Packages', env, globalSettings['fileContainingCoreLogSettings'])
		dbClient = getDbConnection(logger)

		## Work through each package system type containing packages to load
		for system,context in validPackageSystems.items():
			systemName = context.get('name')
			systemPath = context.get('path')
			logger.info('Working on {} packages: {}'.format(systemName, systemPath))
			if os.path.isdir(systemPath):
				packageList = os.listdir(systemPath)
				for packageName in packageList:
					thisPath = os.path.join(systemPath, packageName)
					if not os.path.isdir(thisPath):
						continue
					loadPackageIntoDB(logger, packageName, systemName, ['content', systemName], dbClient, thisPath)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in baselinePackagesInDatabase:  {}'.format(stacktrace))

	with suppress(Exception):
		dbClient.session.close()
		dbClient.close()

	## end baselinePackagesInDatabase
	return


usage = """
Usage:  python {} <option> [parameters]

  options:
    -list
       Display packages per system; lists name and date

    -delete <packageName>
       This removes the package and all related files from both the database and
       the server filesystem. The <packageName> parameter must be a valid name
       of an existing package. Use -list to see all valid names.

    -compressed <packageName> <system> <fullyQualifiedFile>
       This loads a compressed package into both the database and the server
       filesystem. The <system> parameter should be one of the following values:
       'contentGathering', 'universal', 'serverSide'. The <fullyQualifiedFile>
       parameter must be a valid file on the server, containing the expected
       format of a OCP package, with a zip or tar extension. If a package by
       the same name already exists, it is updated; otherwise it is created new.

    -uncompressed <packageName> <system> [<fullyQualifiedPath>]
       This loads an exploded package into both the database and the server
       filesystem. The <system> parameter should be one of the following values:
       'contentGathering', 'universal', 'serverSide'. The <fullyQualifiedPath>
       parameter defaults to the server's ./content/<system>/<packageName> path,
       if not specified. When using the uncompressed option, the package must
       already exist; if it does not yet exist, use the compressed option first.

    -baseline
       Re-runs the loading of all packages into the database, from the server's
       filesystem.

""".format(__file__)


def main():
	"""Main entry point for CLI; other functions are called from modules."""
	try:
		## Default a package test
		action = sys.argv[1].lower()
		if action == '-list':
			listPackages()
			return
		if action == '-baseline':
			print('Baseline packages in database...')
			baselinePackagesInDatabase()
			return

		packageName = sys.argv[2]
		if action == '-delete':
			## Input is a package name without the extension
			removePackage(packageName)
			print('Removed package {}'.format(packageName))
		elif action == '-compressed':
			forceUpdate = False
			system = sys.argv[3]
			## Fully qualified package filename with zip or tar extension
			compressedFile = sys.argv[4]
			print('Calling on compressed file {}'.format(compressedFile))
			validatePackage(packageName, compressedFile, system, forceUpdate)
		elif action == '-uncompressed':
			## Input is a package name without an extension; works off files in
			## the named directory on server (./content/<system>/<package>), or
			## a custom path provided as the last parameter
			packageName = sys.argv[2]
			system = sys.argv[3]
			customPath = None
			with suppress(Exception):
				customPath = sys.argv[4]
			pkgSystem = 'contentGathering'
			if len(sys.argv) > 3:
				pkgSystem = sys.argv[3]
			print('Calling on uncompressed package {}'.format(packageName))
			updatePackage(packageName, system, pkgPath=customPath)
		else:
			print(usage)


	except:
		exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
		print('Exception:  {}'.format(exceptionOnly))
		with suppress(Exception):
			logger.error('Exception in contentManagement:  {}'.format(exceptionOnly))
		print(usage)


if __name__ == '__main__':
	sys.exit(main())
