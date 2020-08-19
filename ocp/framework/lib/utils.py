"""Hodge Podge of utilities for the framework.

Functions::

  parseBooleanOperator : generates a boolean expression to handle 'and' & 'or'
  parseBinaryOperator : parse and return a BinaryExpression
  classLinkDict : store all sub-children in a value list for the parent link
  classDict : store sub-children in a value list for the parent object
  recursionDict : interate through the dictionary and build out the children
  finalDictBulid - helper used to complete the creation of a dictionary
  uuidCheck : check if the identifier is a 32 bit hex
  getValidStrongLinks : creates a dictionary of valid strong links
  getValidWeakLinks : creates a dictionary of valid weak links
  getValidLinksV2 : creates a dictionary of valid strong links
  getValidClassObjects : creates a dictionary of valid BaseObjects
  valueToBoolean - convert input value to appropriate boolean
  loadSettings : read a json config file
  pidEntry : generate .pid file
  pidRemove : remove .pid file
  setupLogFile : create a log file to be connected to a Twisted observer
  masterLog : catch print statements and abnormal message not otherwise captured
  getLogFile : get a handle on the created log file
  _formatEventFactory : text format for events that's linked to FileLogObserver
  _leveDict : dictionary of twisted.logger LogLevel types
  setupObservers : setup JSON/TextFile observers based on logSetting.json
  prettyRunTime : calculate run time for log tracking via start/end time
  prettyRunTimeBySeconds : calculate run time for log tracking via seconds
  setupLogger : setup log handle that tracks application activities
  cleanDirectory : Remove all contents from within a directory
  getPlatformKey : Pull platform key from an existing .conf file
  getServiceKey : Pull service key from an  existing .conf file
  chunk : Split the list into X evenly sized chunks
  getCustomHeaders : parse out custom headers for api operations
  executeJsonQuery : retrieve results from JSON query
  getListResultsFromJsonQuery : retrieve results in List format
  getResultsFromJsonQuery : validate and retrieve results from JSON query
  getNestedResultsFromJsonQuery : retrieve results in Nested format
  getEndpointsFromJsonQuery : get endpoints by processing results from API query
  getEndpointsFromPythonScript : get endpoints by processing results from script
  cleanupJsonModel : parse model result & remove attributes that may mislead compares
  loadFile : one line wrapper for three lines of code to read a file
  grouper : collect byte-data into fixed-length chunks
  getKafkaPartitionCount : get the partition count; good for troubleshooting
  attemptKafkaConsumerConnection : helper function for createKafkaConsumer
  createKafkaConsumer : connect to Kafka and initialize a consumer
  attemptKafkaProducerConnection : helper function for createKafkaConsumer
  createKafkaProducer : connect to Kafka and initialize a producer
  loadExternalLibrary : load an externally contributed library
  getGigOrMeg : helper function for memory size readability
  logException : decorator for try/except logging, via global logger
  logExceptionWithSelfLogger : decorator for try/except logging, via self.logger
  logExceptionWithFactoryLogger : decorator for try/except logging, via factory


.. hidden::

	Authors: Chris Satterthwaite (CS), Madhusudan Sridharan (MS)
	Contributors:
	Version info:
	  0.1 : (CS) Created Jul 25, 2017
	  1.0 : (CS and MS) additional functions, Mar 2018
	  1.1 : (CS) Changed kafka clients & enabled external library path, 2019
	  1.2 : (CS) Created decorator functions for code reduction, Aug 8, 2020

"""
import json
import re
import os
import uuid
import shutil
import importlib
import io
import traceback
import sys
import pathlib
import copy
import time
import random
import ipaddress
import decimal
from datetime import datetime
import arrow
from itertools import zip_longest
from contextlib import suppress
from confluent_kafka import Consumer as KafkaConsumer
from confluent_kafka import Producer as KafkaProducer
from confluent_kafka import KafkaError
## Different logger options
###########################################################################
## Python's base
import logging
## Twisted's version
from twisted.logger import FileLogObserver, jsonFileLogObserver, LogPublisher
from twisted.logger import LogLevelFilterPredicate, LogLevel, FilteringLogObserver
import twisted.python.logfile
from twisted.python import log as rudLog
## Concurrent-log-handler's version
try:
	from concurrent_log_handler import ConcurrentRotatingFileHandler as RFHandler
except ImportError:
	from warnings import warn
	warn("concurrent_log_handler package not installed. Using builtin log handler")
	## Python's version
	from logging.handlers import RotatingFileHandler as RFHandler
###########################################################################

from sqlalchemy import inspect
from sqlalchemy import cast
from sqlalchemy import String as saString
from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy import func

import arrow
from queryProcessing import QueryProcessing
## tableMapping for StrongLink, WeakLink, BaseLink, BaseObject, RealmScope
import database.connectionPool as tableMapping
from sqlalchemy.orm.scoping import scoped_session as sqlAlchemyScopedSession
from sqlalchemy.orm.session import Session as sqlAlchemySession


def parseBooleanOperator(logger, operator='and', *attributes):
	"""Generates a boolean expression to handle 'and' & 'or'.

	Arguments:
	  logger (twisted.logger)  : logger
	  operator (str)           : String containing the operator type
	  attributes (list)        : List of attributes containing join condition
	"""
	if operator == 'and':
		logger.debug('Creating \'and\' clause')
		return and_(*attributes)
	elif operator == 'or':
		logger.debug('Creating \'or\' clause')
		return or_(*attributes)


def parseBinaryOperator(logger, operator, attribute, value=None):
	"""Parses and returns BinaryExpression.

	Arguments:
	  logger (twisted.logger)  : logger
	  operator (str)           : String containing the operator type
	  attribute (str)          : Attribute name
	"""
	inspectableAttribute = inspect(attribute)
	if operator == 'equal':
		if inspectableAttribute.type.python_type == type(value):
			tempBinaryExpression = attribute == value
			return tempBinaryExpression
		else:
			## casting
			newValue = inspectableAttribute.type.python_type(value)
			value = newValue
			tempBinaryExpression = attribute == value
			return tempBinaryExpression

	elif operator == 'iequal':
		if inspectableAttribute.type.python_type == type(value):
			tempBinaryExpression = func.lower(attribute) == func.lower(value)
			return tempBinaryExpression
		else:
			## casting
			newValue = inspectableAttribute.type.python_type(value)
			value = newValue
			tempBinaryExpression = func.lower(attribute) == func.lower(value)
			return tempBinaryExpression

	elif operator == 'gt':
		if inspectableAttribute.type.python_type == type(value):
			tempBinaryExpression = attribute > value
			return tempBinaryExpression
		else:
			## casting
			newValue = inspectableAttribute.type.python_type(value)
			value = newValue
			tempBinaryExpression = attribute > value
			return tempBinaryExpression

	elif operator == 'lt':
		if inspectableAttribute.type.python_type == type(value):
			tempBinaryExpression = attribute < value
			return tempBinaryExpression
		else:
			## casting
			newValue = inspectableAttribute.type.python_type(value)
			value = newValue
			tempBinaryExpression = attribute < value
			return tempBinaryExpression

	elif operator == '==':
		#logger.debug('Casting to {typeName!r}', typeName=str(inspectableAttribute.type.python_type))
		if inspectableAttribute.type.python_type == type(value):
			tempBinaryExpression = attribute == value
			return tempBinaryExpression
		else:
			## casting
			newValue = inspectableAttribute.type.python_type(value)
			value = newValue
			tempBinaryExpression = attribute == value
			return tempBinaryExpression

	elif operator == '>=':
		#logger.debug('Casting to {typeName!r}', typeName=str(inspectableAttribute.type.python_type))
		if inspectableAttribute.type.python_type == type(value):
			tempBinaryExpression = attribute >= value
			return tempBinaryExpression
		else:
			## casting
			newValue = inspectableAttribute.type.python_type(value)
			value = newValue
			tempBinaryExpression = attribute >= value
			return tempBinaryExpression

	elif operator == '<=':
		#logger.debug('Casting to {typeName!r}', typeName=str(inspectableAttribute.type.python_type))
		if inspectableAttribute.type.python_type == type(value):
			tempBinaryExpression = attribute <= value
			return tempBinaryExpression
		else:
			## casting
			newValue = inspectableAttribute.type.python_type(value)
			value = newValue
			tempBinaryExpression = attribute <= value
			return tempBinaryExpression

	elif operator == '>':
		#logger.debug('Casting to {typeName!r}', typeName=str(inspectableAttribute.type.python_type))
		if inspectableAttribute.type.python_type == type(value):
			tempBinaryExpression = attribute > value
			return tempBinaryExpression
		else:
			## casting
			newValue = inspectableAttribute.type.python_type(value)
			value = newValue
			tempBinaryExpression = attribute > value
			return tempBinaryExpression

	elif operator == '<':
		#logger.debug('Casting to {typeName!r}', typeName=str(inspectableAttribute.type.python_type))
		if inspectableAttribute.type.python_type == type(value):
			tempBinaryExpression = attribute < value
			return tempBinaryExpression
		else:
			## casting
			newValue = inspectableAttribute.type.python_type(value)
			value = newValue
			tempBinaryExpression = attribute < value
			return tempBinaryExpression

	elif operator == '!=' or operator == '<>':
		#logger.debug('Casting to {typeName!r}', typeName=str(inspectableAttribute.type.python_type))
		if inspectableAttribute.type.python_type == type(value):
			tempBinaryExpression = attribute != value
			return tempBinaryExpression
		else:
			## casting
			newValue = inspectableAttribute.type.python_type(value)
			value = newValue
			tempBinaryExpression = attribute != value
			return tempBinaryExpression

	elif operator == 'in':
		#logger.debug('Casting to {typeName!r}', typeName=str(inspectableAttribute.type.python_type))
		if all(inspectableAttribute.type.python_type == type(item) for item in value):
			tempBinaryExpression = attribute.in_(value)
			return tempBinaryExpression
		else:
			tempValueList = [inspectableAttribute.type.python_type(item) for item in value]
			tempBinaryExpression = attribute.in_(tempValueList)
			return tempBinaryExpression

	elif operator.lower() == 'isnull':
		tempBinaryExpression = attribute.is_(None)
		return tempBinaryExpression

	elif operator.lower() == 'regex':
		logger.debug('Casting the Column to handle regular expression')
		## cast(a.connectionPool.TcpIpPort.port, String).op('~')('[0-9]')
		newValue = str(value)
		tempBinaryExpression = cast(attribute, saString).op('~')(newValue)
		return tempBinaryExpression

	elif operator.lower() == 'iregex':
		logger.debug('Casting the Column to handle regular expression (case insensitive)')
		## cast(a.connectionPool.TcpIpPort.port, String).op('~')('[0-9]')
		newValue = str(value)
		tempBinaryExpression = cast(attribute, saString).op('~*')(newValue)
		return tempBinaryExpression

	elif operator == 'between':
		## not imnplemented.
		pass

	elif operator.lower() == 'betweendate':
		if isinstance(value, list) and len(value) == 2:
			tempBinaryExpression = None
			try:
				val =[arrow.get(x, 'YYYY-MM-DD HH:mm:ss ZZZ').datetime for x in value]
				val.sort()
				tempBinaryExpression =  and_(val[0] <= attribute, attribute <= val[-1])
			except:
				msg = str(sys.exc_info()[1])
				logger.error('Exception: {}.  Operator \'betweendate\' requires a list value of 2 string datetimes in this format: [\'YYYY-MM-DD HH:mm:ss ZZZ\', \'YYYY-MM-DD HH:mm:ss ZZZ\'].  The expected timezone (\'ZZZ\') should match one from pytz.  Sample values: \'UTC\', \'US/Pacific\', \'US/Arizona\', \'US/Mountain\', \'US/Central\', \'US/Eastern\'.  To view all available values in a Python shell: \'import pytz\' followed by \'pytz.all_timezones\'.'.format(msg))
				raise BaseException('Exception: {}.  Operator \'betweendate\' requires a list value of 2 string datetimes in this format: [\'YYYY-MM-DD HH:mm:ss ZZZ\', \'YYYY-MM-DD HH:mm:ss ZZZ\'].  The expected timezone (\'ZZZ\') should match one from pytz.  Sample values: \'UTC\', \'US/Pacific\', \'US/Arizona\', \'US/Mountain\', \'US/Central\', \'US/Eastern\'.  To view all available values in a Python shell: \'import pytz\' followed by \'pytz.all_timezones\'.'.format(msg))
		else:
			raise BaseException("Expected List of the form ['YYYY-MM-DD HH:mm:ss ZZZ', 'YYYY-MM-DD HH:mm:ss ZZZ']")
		return tempBinaryExpression

	elif operator.lower() == "lastnumminutes":
		if not isinstance(value, int):
			if value.isdigit():
				value=int(value)
			else:
				## raising exception
				raise BaseException("Integer Expected")
		# val.datetime
		# val = arrow.get('2018-04-20 01:36:34 GMT-5', 'YYYY-MM-DD HH:mm:ss ZZZ')
		pastMinute = arrow.utcnow().shift(minutes=-(value)).datetime
		tempBinaryExpression =  and_(pastMinute <= attribute, attribute <= arrow.utcnow().datetime)
		return tempBinaryExpression
		# tempBinaryExpression = attribute <= dt.datetime.fromtimestamp(time.time()) - dt.datetime.timedelta(minutes=value)

	elif operator.lower() == "lastnumhours":
		if not isinstance(value, int):
			if value.isdigit():
				value=int(value)
			else:
				## raising exception
				raise BaseException("Integer Expected")
		# val.datetime
		# val = arrow.get('2018-04-20 01:36:34 GMT-5', 'YYYY-MM-DD HH:mm:ss ZZZ')
		pastHour = arrow.utcnow().shift(hours=-(value)).datetime
		tempBinaryExpression =  and_(pastHour <= attribute, attribute <= arrow.utcnow().datetime)
		return tempBinaryExpression

	else:
		logger.info('Either the operator is not prperly used or not defined please check the avaliable operators')

	## end parseBinaryOperator
	return


def classLinkDict(dicts, clsObject):
	"""Recursion to store all sub-children in a value list for the parent link.

	Arguments:
	  dicts : Dictionary containing the class names as keys, and the value as
	          the object
	  clsObject : Base class to start listing
	"""
	## this is to include strongLink and weakLink baseLink classes.
	dicts[clsObject.__name__] = clsObject
	for i in clsObject.__subclasses__():
		dicts[i.__name__] = i
		if i.__subclasses__():
			classLinkDict(dicts,clsObject)

	## end classLinkDict
	return

def classDict(dicts, clsObject):
	"""Recursion to store sub-children in a value list for the parent object.

	Arguments:
	  dicts : Dictionary containing the class names as keys, and the value as
	          the object and its children
	  clsObject : Base class to start listing.
	"""
	for i in clsObject.__subclasses__():
		tempdict = dict()
		tempdict['classObject'] = i
		tempdict['children'] = [i.__name__ for i in i.__subclasses__()]
		dicts[i.__name__] = tempdict
		if i.__subclasses__():
			classDict(dicts, i)

	## end classDict
	return


def recursionDict(dicts, theList):
	"""Function to interate through the dictionary and build out the children.

	Arguments:
	  dicts : Dictionary containing the class names as keys, and the value as
	          the object and its children
	  theList : list of children of the parent class
	"""
	for i in theList:
		result = recursionDict(dicts, dicts[i]['children'])
		if len(result) > 0:
			theList.extend(result)

	## end recursionDict
	return theList


def finalDictBulid(dicts):
	"""Helper function used to complete the creation of the dictionary."""
	for i in dicts:
		dicts[i]['children'] = recursionDict(dicts,dicts[i]['children'])


def uuidCheck(identifier):
	"""This is used to check if the identifier is a 32 bit hex.

	Argumet:
	  identifier : String containing the identifier
	"""
	objIdChk  = True
	try:
		uuid.UUID(hex=identifier, version=4)
	except ValueError:
		objIdChk = False

	## end uuidCheck
	return objIdChk


def getValidStrongLinks(validStrongLinks):
	"""Creates a dictionary of valid strong links."""
	strongLinkClass = tableMapping.StrongLink
	classLinkDict(validStrongLinks, strongLinkClass)
	return


def getValidWeakLinks(validWeakLinks):
	"""Creates a dictionary of valid weak links."""
	weakLinkClass = tableMapping.WeakLink
	classLinkDict(validWeakLinks, weakLinkClass)
	return


def getValidLinksV2(validLinks):
	"""Creates a dictionary of valid strong links."""
	BaseLinkClass = tableMapping.BaseLink
	tempdict = dict()
	tempdict['classObject'] = BaseLinkClass
	tempdict['children'] = [i.__name__ for i in BaseLinkClass.__subclasses__()]
	validLinks[BaseLinkClass.__name__] =  tempdict
	classDict(validLinks, BaseLinkClass)
	finalDictBulid(validLinks)

	## end getValidLinksV2
	return


def getValidClassObjects(validClassObjects):
	"""Creates a dictionary of valid BaseObjects."""

	BaseObjectClass = tableMapping.BaseObject
	tempdict = dict()
	tempdict['classObject'] = BaseObjectClass
	tempdict['children'] = [i.__name__ for i in BaseObjectClass.__subclasses__()]
	validClassObjects[BaseObjectClass.__name__] =  tempdict
	classDict(validClassObjects, BaseObjectClass)
	finalDictBulid(validClassObjects)

	## end getValidClassObjects
	return


def valueToBoolean(value):
	"""Convert input value to appropriate boolean."""
	if value is not None:
		if value is True or str(value) == '1' or re.search('true', str(value), re.I) or re.search('yes', str(value), re.I):
			return True
	return False


def loadSettings(fileName):
	"""Read defined configurations from JSON file.

	Arguments:
	  fileName (str) : file to read in

	Return:
	  settings (json) : dictionary to hold the the configuration parameter

	"""
	settings = None
	try:
		with open(fileName, 'r') as json_data:
			settings = json.load(json_data)
	except:
		raise EnvironmentError('Error loading file {}: {}'.format(fileName, str(sys.exc_info()[1])))

	## end loadSettings
	return settings


def pidEntryService(serviceName, env, pid):
	"""Generates .pid file for the service.

	Arguments:
	  serviceName (str) : String containning the serviceName
	  env               : Module containing the env paths
	  pid (str)         : System generated process ID
	"""
	pidPath = env.pidPath
	if not os.path.exists(pidPath):
		os.makedirs(pidPath)
	chkFile = os.path.join(pidPath, serviceName+'.pid')
	counter = 0
	while counter < 3:
		try:
			with open(chkFile,'w') as fh:
				fh.write(str(pid)+'\n')
			return
		except:
			counter += 1
			time.sleep(random.random())
	raise TimeoutError('Unable to get a handle for the PID file: {}'.format(chkFile))

	## end pidEntryService
	return


def pidRemoveService(serviceName, env, pid):
	"""Removes previously generated .pid file for services.

	Arguments:
	  serviceName (str) : String containning the serviceName
	  env               : Module containing the env paths
	  pid (str)         : System generated process ID
	"""
	chkFile = os.path.join(env.pidPath, serviceName+'.pid')
	counter = 0
	while counter < 3:
		try:
			if os.path.exists(chkFile):
				os.remove(chkFile)
			return
		except:
			counter += 1
			time.sleep(random.random())
	raise TimeoutError('Unable to remove the PID file: {}'.format(chkFile))

	## end pidRemoveService
	return


def pidEntry(serviceName, env, pid):
	"""Generates .pid file when multiple clients are invoked on an endpoint.

	Arguments:
	  serviceName (str) : String containning the serviceName
	  env               : Module containing the env paths
	  pid (str)         : System generated process ID

	Return:
	  eFlag (bool) : Boolean value to check the existance of .pid file

	"""
	pidPath = env.pidPath
	if not os.path.exists(pidPath):
		os.makedirs(pidPath)
	lockFile = os.path.join(pidPath,serviceName+'.lock')
	chkFile = os.path.join(pidPath,serviceName+'.pid')
	cntr = 0
	eFlag = False
	try:
		while cntr < 5:
			try:
				pathlib.Path(lockFile).touch(exist_ok= False)
				if os.path.exists(chkFile):
					eFlag = True
				with open(chkFile,'a+') as fh:
					fh.write(str(pid)+'\n')
				os.remove(lockFile)
				return eFlag
			except:
				cntr = cntr + 1
				time.sleep(random.random())
		raise TimeoutError
	except TimeoutError:
		TimeoutError ('cannot get a handle for the file')

	## end pidEntry
	return eFlag


def pidRemove(serviceName, env, pid):
	"""Removes previously generated .pid file for clients.

	Arguments:
	  serviceName (str) : String containning the serviceName
	  env               : Module containing the env paths
	  pid (str)         : System generated process ID

	"""
	lockFile = os.path.join(env.pidPath, serviceName+'.lock')
	chkFile = os.path.join(env.pidPath, serviceName+'.pid')
	cntr = 0
	try:
		while cntr < 5:
			try:
				pathlib.Path(lockFile).touch(exist_ok= False)
				if os.path.exists(chkFile):
					lines =[]
					fh = open(chkFile,'r+')
					lines = fh.readlines()
					fh.seek(0)
					for i in lines:
						if pid != i.strip('\n'):
							fh.write(i)
					fh.truncate()
					fh.close()
					if os.stat(chkFile).st_size == 0:
						os.remove(chkFile)
				os.remove(lockFile)
				return
			except:
				cntr = cntr + 1
				time.sleep(random.random())
		raise TimeoutError

	except TimeoutError:
		print('Unable to remove the PID')
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		print(exception)

	## end pidRemove
	return


def setupLogFile(serviceName, env, logSettingsFileName, pid=None, directoryName=None):
	"""Setup Log file to be connected to a Twisted observer.

	Arguments:
	  serviceName (str)         : String containing the serviceName
	  env                       : Module containing the env paths
	  pid (str)	                : System generated process ID
	  logSettingsFileName (str) : JSON file containing the logsettings

	Return:
	  logfilelist (dict) : Dictionary containing the twisted LogFile instance

	"""
	configPath = env.configPath
	logPath = None
	if directoryName is not None:
		logPath = os.path.join(env.logPath, directoryName)
		pidPath = env.pidPath
		if not os.path.exists(pidPath):
			os.makedirs(pidPath)
	else:
		logPath = env.logPath
	if not os.path.exists(logPath):
		os.makedirs(logPath)
	## Open defined configurations
	logSettings = loadSettings(os.path.join(configPath, logSettingsFileName))
	## Create requested handler for this service
	logEntry = logSettings.get(serviceName)
	logFiles =[]
	jsonPath = os.path.join(logPath, 'json')
	if not os.path.exists(jsonPath):
		os.makedirs(jsonPath)
	logFile1 = os.path.join(jsonPath, logEntry.get('fileNameJson'))
	logFile2 = os.path.join(logPath, logEntry.get('fileNameText'))
	logFiles.append(logFile1)
	logFiles.append(logFile2)
	## If multiple clients are running on a single machine, we create multiple
	## log instances to avoid file handle issues, using the pid for uniqueness.
	NewlogFiles =[]
	if pid:
		try:
			for logFile in logFiles:
				m = re.search('(^.*)(\.log)', logFile)
				logFile = '{}-{}{}'.format(m.group(1), pid, m.group(2))
				NewlogFiles.append(logFile)
		except:
			pass
	if len(NewlogFiles) == 0:
		NewlogFiles = logFiles
	logFileList =dict()
	logfile1 = twisted.python.logfile.LogFile(NewlogFiles[0], logPath,
											 rotateLength=int(logEntry.get('maxSizeInBytes')),
											 maxRotatedFiles=int(logEntry.get('maxRollovers')))

	logfile2 = twisted.python.logfile.LogFile(NewlogFiles[1], logPath,
											 rotateLength=int(logEntry.get('maxSizeInBytes')),
											 maxRotatedFiles=int(logEntry.get('maxRollovers')))
	logFileList['fileNameJson'] = logfile1
	logFileList['fileNameText'] = logfile2

	## end setupLogFile
	return logFileList


def masterLog(env, fileName, pid=None, directoryName=None, setStdout=True):
	"""Catch the Twisted generated logs and abnormals.
	Arguments:
	  env               : Module containing the env paths
	  fileName (str) 	: Log file name.

	"""
	if directoryName is not None:
		logPath = os.path.join(env.logPath,directoryName)
		if not os.path.exists(logPath):
			os.makedirs(logPath)
	else:
		logPath = env.logPath
	if pid is None:
		logfilepath = os.path.join(logPath,(fileName+'.log'))
	else:
		logfilepath = os.path.join(logPath,(fileName+'-'+str(pid)+'.log'))
	if not os.path.isfile(logfilepath):
		logfile = twisted.python.logfile.LogFile(logfilepath,logPath)
	else:
		logfile = open(logfilepath,'a')
	rudLog.startLogging(logfile, setStdout)

	## end masterLog
	return


def getLogFile(serviceName, env, logSettingsFileName, directoryName=None):
	"""Get a handle on the created log file.

	WARNING: be careful with blocking.

	Arguments:
	  serviceName (str)         : String containning the serviceName
	  env                       : Module containing the env paths
	  pid (str)	                : System generated process ID
	  logSettingsFileName (str) : JSON file containing the logsettings

	Return:
	  logfilelist (dict) : Dictionary containing the twisted LogFile instance

	"""
	configPath = env.configPath
	if directoryName is not None:
		logPath = os.path.join(env.logPath,directoryName)
	## Open defined configurations
	else:
		logPath = env.logPath
	logSettings = loadSettings(os.path.join(configPath, logSettingsFileName))
	logEntry = logSettings.get(serviceName)
	logFiles =dict()
	logFile1 = os.path.join(logPath, 'json', logEntry.get('fileNameJson'))
	logFile2 = os.path.join(logPath, logEntry.get('fileNameText'))
	logFiles['fileNameJson'] = logFile1
	logFiles['fileNameText'] = logFile2

	## end getLogFile
	return logFiles


def _formatEventFactory(logSettingsFileName, env, serviceName):
	"""Text format for the events, linked to FileLogObserver for now loggerName

	Arguments:
	  logSettingsFileName (str) : JSON file containing the logsettings
	  env                       : Module containing the env paths
	  serviceName (str)	        : String containning the serviceName

	Return:
	  format (callable)         : callable object event handler for FileLogObserver

	"""
	configPath = env.configPath
	logSettings = loadSettings(os.path.join(configPath, logSettingsFileName))
	logEntry = logSettings.get(serviceName)
	msg = logEntry.get('lineFormat')
	dt = logEntry.get('dateFormat')

	def format(event):
		""" A callable returned that handles the event and returns the text
		format of the event.

		Arguments:
		  event (Twisted.Event):
		"""
		## Convert from float (log_time) to datetime, then use strftime. Format
		## override is used since time.strftime doesn't handle milliseconds, and
		## if the requested format included %f for microseconds, it won't work.
		try:
			#text = msg %{'asctime':str(time.strftime(dt, time.localtime(float(event['log_time'])))), 'levelname' : event['log_level'].name, 'message' : str(event['log_format']).format(**event)}
			text = msg %{'asctime':datetime.fromtimestamp(float(event['log_time'])).strftime(dt), 'levelname' : event['log_level'].name, 'message' : str(event['log_format']).format(**event)}
			text =  text + '\n'
		except:
			#text = msg %{'asctime':str(time.strftime(dt, time.localtime(float(event['log_time'])))), 'levelname' : event['log_level'].name, 'message' : str(event['log_format'])}
			text = msg %{'asctime':datetime.fromtimestamp(float(event['log_time'])).strftime(dt), 'levelname' : event['log_level'].name, 'message' : str(event['log_format'])}
			text =  text + '\n'
		return text

	## end _formatEventFactory
	return format


def _leveDict():
	"""Dictionary of twisted.logger LogLevel types"""
	lvs = dict(DEBUG = LogLevel.debug , ERROR = LogLevel.error, INFO = LogLevel.info, WARN = LogLevel.warn)
	return lvs


def setupObservers(logFileList, serviceName, env, logSettingsFileName, createJSON=True):
	"""Setup JSON and TextFile observers based on logSetting.json file.

	Returns LogPublisher Observer.

	Arguments:
	  logFileList (str)          : Dict containing the twisted LogFile instance
	  serviceName (str)          : String containning the serviceName
	  env                        : Module containing the env paths
	  logSettingsFileName (str)  : JSON file containing the logsettings

	Return:
	  LogPublisherInstance (str) :

	"""
	configPath = env.configPath
	logSettings = loadSettings(os.path.join(configPath, logSettingsFileName))
	logEntry = logSettings.get(serviceName)
	logLvl = logEntry.get('logLevel')
	predicate = LogLevelFilterPredicate(defaultLogLevel=_leveDict()[logLvl])
	LogPublisherInstance = None
	try:
		observers=[]
		if type(logFileList.get('fileNameJson')) != type(str()):
			callable1 = _formatEventFactory(logSettingsFileName, env, serviceName)
			FileLogObserverInstance = FilteringLogObserver(FileLogObserver(logFileList['fileNameText'],callable1), [predicate]) #placeholder for _formatEventFactory
			observers.append(FileLogObserverInstance)
			if createJSON:
				jsonObserverInstance = FilteringLogObserver(jsonFileLogObserver(logFileList['fileNameJson']), [predicate])
				observers.append(jsonObserverInstance)

		else:
			callable1 = _formatEventFactory(logSettingsFileName, env, serviceName)
			FileLogObserverInstance = FilteringLogObserver(FileLogObserver(io.open(logFileList['fileNameText'],'a'), callable1), [predicate]) #placeholder for _formatEventFactory
			observers.append(FileLogObserverInstance)
			if createJSON:
				jsonObserverInstance = FilteringLogObserver(jsonFileLogObserver(io.open(logFileList['fileNameJson'],'a')), [predicate])
				observers.append(jsonObserverInstance)

		LogPublisherInstance = LogPublisher()
		for observer in observers:
			LogPublisherInstance.addObserver(observer)

	except:
		print('Exception in setting up the Observers')
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		print(exception)

	## end setupObservers
	return LogPublisherInstance


def prettyRunTime(startTime, endTime):
	"""Get a human readable run time for log tracking, by using start/end time.

	Arguments:
	  startTime (float) : result from initial time.time() in float since the epoch
	  endTime (float)   : result from last time.time() in float since the epoch

	Return:
	  runTime (str) : String containing execution time in [N day(s) HH:MM:SS] format

	"""
	## Cast to int (or otherwise remove remainer, before using divmod)
	totalSeconds = int(endTime - startTime)

	## prettyRunTime
	return prettyRunTimeBySeconds(totalSeconds)


def prettyRunTimeBySeconds(totalSeconds):
	"""Get a human readable run time for log tracking, by using seconds.

	Arguments:
	  totalSeconds (int) : number of seconds

	Return:
	  runTime (str) : String containing execution time in [N day(s) HH:MM:SS] format

	"""
	m, s = divmod(totalSeconds, 60)
	h, m = divmod(m, 60)
	d, h = divmod(h, 24)
	runTime = '{:02}:{:02}:{:02}'.format(h, m, s)
	if d > 1:
		runTime = '{} days, {}'.format(d, runTime)
	elif d > 0:
		runTime = '{} day, {}'.format(d, runTime)

	## end prettyRunTimeBySeconds
	return runTime


def setupLogger(loggerName, env, logSettingsFileName, pid=None, directoryName=None, topLogger=False):
	"""Setup requested log file to be connected to a concurrent-log-handler.

	Arguments:
	  entityName (str)          : name of the JSON configuration
	  logPath (str)             : string containing path to the log directory
	  logSettingsFileName (str) : config file for log settings

	Return:
	  logger : Returns log handler for tracking activities

	"""
	configPath = env.configPath
	logPath = env.logPath
	if directoryName is not None:
		logPath = os.path.join(env.logPath, directoryName)
	if not os.path.exists(logPath):
		os.makedirs(logPath)
	## Open defined configurations
	logSettings = loadSettings(os.path.join(configPath, logSettingsFileName))
	## Create requested handler for this service
	logEntry = logSettings.get(loggerName)
	logFile = os.path.join(logPath, logEntry.get('fileName'))
	## If multiple clients are running on a single machine, we create multiple
	## log instances to avoid file handle issues, using the pid for uniqueness.
	if pid:
		try:
			m = re.search('(^.*)(\.log)', logFile)
			logFile = '{}-{}{}'.format(m.group(1), pid, m.group(2))
		except:
			pass
	logger = None
	if topLogger:
		logger = logging.getLogger()
	else:
		logger = logging.getLogger(loggerName)
	logger.handlers = []
	logger.setLevel(logEntry.get('logLevel'))
	# mainHandler = logging.handlers.RotatingFileHandler(logFile,
	# 												   maxBytes=int(logEntry.get('maxSizeInBytes')),
	# 												   backupCount=int(logEntry.get('maxRollovers')))
	mainHandler = RFHandler(logFile, maxBytes=int(logEntry.get('maxSizeInBytes')), backupCount=int(logEntry.get('maxRollovers')))
	fmt = logging.Formatter(logEntry.get('lineFormat'), datefmt = logEntry.get('dateFormat'))
	mainHandler.setFormatter(fmt)
	logger.addHandler(mainHandler)

	## end setupLogger
	return logger


def cleanDirectory(logger, location):
	"""Remove all contents within a directory; works on Linux and Windows."""
	try:
		## Older method that used a work around of going file by file
		# fileList = os.listdir(location)
		# for fileName in fileList:
		# 	fullpath=os.path.join(location, fileName)
		# 	if os.path.isfile(fullpath):
		# 		os.chmod(fullpath, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
		# 		os.remove(os.path.join(location, fileName))
		# 	elif os.path.islink(fullpath):
		# 		os.unlink(fullpath)
		# 	elif os.path.isdir(fullpath):
		# 		if len(os.listdir(fullpath)) > 0:
		# 			cleanDirectory(logger, fullpath)
		# 		shutil.rmtree(os.path.join(location, fileName), onerror=readonly_handler)

		## Newer method since Python 3.5
		shutil.rmtree(location, onerror=readonly_handler)
	except:
		# stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		# logger.error('Exception in cleanDirectory:  {}'.format(str(stacktrace)))
		exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
		logger.error('Exception in cleanDirectory:  {}'.format(str(exceptionOnly)))

	## end cleanDirectory
	return

def readonly_handler(func, path, execinfo):
	"""Fix for read only Windows files to be deleted."""
	os.chmod(path, 128)  #or os.chmod(path, stat.S_IWRITE) from "stat" module
	func(path)


def getServiceKey(configPath=None):
	"""Pull service key from an existing file.

	Return:
	  encodeKey (str) : Retruns a string containing the encoded key

	"""
	encodedKey = None
	try:
		keyFile = os.path.join('..', 'conf', 'client.conf')
		if configPath:
			keyFile = os.path.join(configPath, 'client.conf')
		with open(keyFile, 'r') as f:
			encodedKey = f.read()
		if len(encodedKey) == 0:
			raise IOError
	except IOError:
		raise IOError('Key not found')

	## end getServiceKey
	return encodedKey


def chunk(xs, n):
	'''Split the list, xs, into n evenly sized chunks.

	This example pulled directly from Word Aligned:
	  http://wordaligned.org/articles/slicing-a-list-evenly-with-python

	'''
	L = len(xs)
	assert 0 < n <= L
	s, r = divmod(L, n)
	t = s + 1

	## end chunk
	return ([xs[p:p+t] for p in range(0, r*t, t)] +
			[xs[p:p+s] for p in range(r*t, L, s)])


def getCustomHeaders(headers, customHeaders):
	"""Parse out custom headers for api operations."""
	customHeaders['Content-Type'] = 'application/json'
	customHeaders['removePrivateAttributes'] = True
	customHeaders['removeEmptyAttributes'] = True
	customHeaders['resultsFormat'] = 'Flat'
	#print('Inside getCustomHeaders:  headers: {}  customHeaders: {}'.format(headers, customHeaders))
	for thisHeader in headers:

		## Show private and empty attributes - boolean
		if thisHeader.lower() == 'removeprivateattributes':
			customHeaders['removePrivateAttributes'] = valueToBoolean(headers.get(thisHeader, True))
			#print('  --> found removePrivateAttributes.  value before: {}  value after: {}'.format(headers.get(thisHeader, True), valueToBoolean(headers.get(thisHeader, True))))
		elif thisHeader.lower() == 'removeemptyattributes':
			customHeaders['removeEmptyAttributes'] = valueToBoolean(headers.get(thisHeader, True))

		## Content delivery - all vs chunked/paged
		elif thisHeader.lower() == 'contentdeliverymethod':
			customHeaders['contentDeliveryMethod'] = 'all'
			value = headers.get(thisHeader).lower()
			## Any of these should mean the same
			if value in ['chunk', 'chunks', 'chunked', 'chunking', 'page', 'pages', 'paged', 'paging', 'pagination']:
				customHeaders['contentDeliveryMethod'] = 'chunk'
				## Default if these weren't supplied (yet)
				if 'contentIsSelfSufficient' not in customHeaders:
					customHeaders['contentIsSelfSufficient'] = False
				if 'contentDeliverySize' not in customHeaders:
					## Size is in KB, so we are defaulting to 8 MB chunks
					customHeaders['contentDeliverySize'] = 8192
		elif thisHeader.lower() == 'contentdeliverysize':
			value = headers.get(thisHeader)
			## Could be in integer or string format
			if isinstance(value, int) or value.isdigit():
				customHeaders['contentDeliverySize'] = int(value)
		elif thisHeader.lower() == 'contentisselfsufficient':
			## If the chunk is self sufficient or all inclusive, meaning all
			## required objects (like containers) exist in each chunk... which
			## effectively duplicates objects across multiple chunks
			customHeaders['contentIsSelfSufficient'] = valueToBoolean(headers.get(thisHeader, False))

		## Results format - nested, flat
		elif thisHeader.lower() == 'resultsformat':
			resultsFormat = headers.get(thisHeader)
			if re.search('Nested-Simple', resultsFormat, re.I):
				customHeaders['resultsFormat'] = 'Nested-Simple'
			elif re.search('Nested', resultsFormat, re.I):
				customHeaders['resultsFormat'] = 'Nested'

	## end getCustomHeaders
	return


def executeProvidedJsonQuery(logger, dbClient, content, resultList):
	"""Retrieve results from a JSON query."""
	#logger.debug('Querying database with the data {}'.format(str(content)))
	queryprocessing = QueryProcessing(logger, dbClient, content, resultsFormat='Nested')
	endpointsJson = queryprocessing.runQuery()
	for linchpinLabel in endpointsJson.keys():
		entries = endpointsJson.get(linchpinLabel, [])
		for thisEntry in entries:
			resultList.append(thisEntry)
	endpointsJson = None


def executeJsonQuery(logger, dbClient, queryFile, resultList):
	"""Load JSON query from file, and retrieve results."""
	try:
		queryContent = None
		with open(queryFile) as fp:
			queryContent = json.load(fp)
		executeProvidedJsonQuery(logger, dbClient, queryContent, resultList)
	except:
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in executeJsonQuery: {exception!r}', exception=exception)

	## end executeJsonQuery
	return


def getListResultsFromJsonQuery(logger, dbClient, queryFile, resultList):
	"""Validate and retrieve results from a provided JSON query definition.

	Updates an input variable instead of creating a new result variable."""
	if not os.path.isfile(queryFile):
		raise EnvironmentError('JSON query file does not exist: {}'.format(queryFile))
	executeJsonQuery(logger, dbClient, queryFile, resultList)


def getResultsFromJsonQuery(logger, dbClient, queryFile, resultsFormat='Flat'):
	"""Validate and retrieve results from a provided JSON query definition.

	Returns a new result variable."""
	if not os.path.isfile(queryFile):
		raise EnvironmentError('JSON query file does not exist: {}'.format(queryFile))
	endpointsJson = None
	try:
		queryContent = None
		with open(queryFile) as fp:
			queryContent = json.load(fp)
		logger.debug('Querying database with the data {queryContent!r}', queryContent=queryContent)
		if resultsFormat not in ['Flat', 'Nested', 'Nested-Simple']:
			raise EnvironmentError('Invalid JSON query results format: {}'.format(resultsFormat))
		queryprocessing = QueryProcessing(logger, dbClient, queryContent, resultsFormat=resultsFormat)
		endpointsJson = queryprocessing.runQuery()
		logger.debug(' ... finished endpointQuery for target endpoints: {endpointsJson!r}', endpointsJson=endpointsJson)
	except:
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in getResultsFromJsonQuery: {exception!r}', exception=exception)

	## end getResultsFromJsonQuery
	return endpointsJson


def getNestedResultsFromJsonQuery(logger, dbClient, queryFile, nestedSimple=False):
	"""Validate and retrieve results from a provided JSON query definition.

	Returns a new result variable."""
	if not os.path.isfile(queryFile):
		raise EnvironmentError('JSON query file does not exist: {}'.format(queryFile))
	endpointsJson = None
	try:
		queryContent = None
		with open(queryFile) as fp:
			queryContent = json.load(fp)
		logger.debug('Querying database with the data {queryContent!r}', queryContent=queryContent)
		resultsFormat = 'Nested'
		if nestedSimple:
			resultsFormat = 'Nested-Simple'
		queryprocessing = QueryProcessing(logger, dbClient, queryContent, resultsFormat=resultsFormat)
		endpointsJson = queryprocessing.runQuery()
		logger.debug(' ... finished endpointQuery for target endpoints: {endpointsJson!r}', endpointsJson=endpointsJson)
	except:
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in getNestedResultsFromJsonQuery: {exception!r}', exception=exception)

	## end getNestedResultsFromJsonQuery
	return endpointsJson


def getEndpointsFromJsonQuery(logger, dbClient, thisPackagePath, packageName, endpointQuery, endpointList):
	"""Validate and retrieve results from a packaged JSON endpoint query."""
	## Currently endpoint queries cannot be shared across packages; need
	## to add unique constraints for package validation if this is the
	## desired functionality, to ensure user doesn't think they are
	## processing one query when they actually working on another like-
	## named query included in a different package.
	endpointQueryFile = os.path.join(thisPackagePath, 'endpoint', '{}.json'.format(endpointQuery))
	if not os.path.isfile(endpointQueryFile):
		logger.error('Package {packageName!r} does not have the defined endpoint query {endpointQuery!r}, file path: {endpointQueryFile!r}', packageName=packageName, endpointQuery=endpointQuery, endpointQueryFile=endpointQueryFile)
		return
	executeJsonQuery(logger, dbClient, endpointQueryFile, endpointList)

	## end getEndpointsFromJsonQuery
	return


def getEndpointsFromPythonScript(logger, dbClient, thisPackagePath, packageName, endpointScript, endpointList, metaData):
	"""Get target endpoints by processing results from a Python script."""
	try:
		## Currently endpoint scripts cannot be shared across packages; need
		## to add unique constraints for package validation if they can, to
		## ensure user doesn't think they are running one script when they
		## are actually running another from a module previously in sys path
		endpointScriptFile = os.path.join(thisPackagePath, 'endpoint', '{}.py'.format(endpointScript))
		if not os.path.isfile(endpointScriptFile):
			logger.error('Package {packageName!r} does not have the defined endpoint script {endpointScript!r}, file path: {endpointScriptFile!r}', packageName=packageName, endpointScript=endpointScript, endpointScriptFile=endpointScriptFile)
			return
		endpointsModule = '{}.{}.{}'.format(packageName, 'endpoint', endpointScript)

		## Python quietly handles duplicate imports; besides, if we decide
		## to conditionally import the module - we won't get the instance
		## to call with getEndpoints below.
		endpointsJson = {}
		logger.debug('endpointScript: {endpointScript!r}', endpointScript=endpointScript)
		logger.debug('Importing module: {endpointsModule!r}', endpointsModule=endpointsModule)
		importlib.import_module(endpointsModule)
		thisFunction = getattr(importlib.import_module(endpointsModule), 'getEndpoints')
		## Run endpoint script and pull out the results
		thisFunction(dbClient, logger, endpointsJson, metaData)
		logger.debug(' ... finished endpointScript for target endpoints: {endpointScript!r}', endpointScript=endpointScript)
		## Add onto the mutable endpointList for better memory management
		for endpoint in endpointsJson['endpoints']:
			endpointList.append(endpoint)
		endpointsJson = None
	except:
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in getEndpointsFromPythonScript: {exception!r}', exception=exception)

	## end getEndpointsFromPythonScript
	return


def customJsonDumpsConverter(someObject):
	if isinstance(someObject, datetime):
		#return someObject.__str__()
		simpleDateString = someObject.__str__()
		with suppress(Exception):
			## Change the default value: 2019-06-04T12:01:35.873985-05:00
			##     to something simpler: 2019-06-04 12:01:35
			## Without going through time conversion libs... not necessary here.
			simpleDateString = simpleDateString.split('.')[0].replace('T', ' ')
		return simpleDateString
	elif isinstance(someObject, decimal.Decimal):
		return someObject.__str__()


def cleanupJsonModel(runtime, log, thisResult):
	"""Walk through result & remove attributes that would mislead comparisons.

	Replacing this with a string converter for now: customJsonDumpsConverter."""
	objectId = None
	matchedValue = None
	dataSection = thisResult.get('data')
	if dataSection is not None:
		## Pop off attributes that would provide false positives
		## during change detection (e.g. last touched from a job)
		updatedBy = dataSection.pop('object_updated_by')
		timeUpdated = dataSection.pop('time_updated')

		## Since datetime is not serialiable for the stored JSON string value,
		## we cast any dates we want to retain into string from something like:
		##  datetime.datetime(2018, 7, 25, 14, 5, 23, 677722, tzinfo=psycopg2.tz.FixedOffsetTimezone(offset=-300, name=None))
		timeCreated = dataSection.get('time_created')
		if timeCreated is not None:
			dataSection['time_created'] = str(timeCreated)

	## Continue looping through the rest of the map set
	children = thisResult.get('children')
	if children is not None:
		for childResult in children:
			cleanupJsonModel(runtime, log, childResult)

	## end cleanupJsonModel
	return


def compareJsonResults(source_data_a, source_data_b):
	"""Check whether two JSON objects are equivelant.

	There are a few ways to code this, but it's basically comparing primatives
	and iterating through any lists or dictionaries.  For listing details on
	JSON differences, I use custom code in modelCompare.
	"""
	def compare(data_a, data_b):
		## Type: list
		if (type(data_a) is list):
			## Is [data_b] a list and of same length as [data_a]?
			if ((type(data_b) != list) or
				(len(data_a) != len(data_b))):
				return False
			## Iterate over list items
			for list_index,list_item in enumerate(data_a):
				## Compare [data_a] list item against [data_b] at index
				if (not compare(list_item, data_b[list_index])):
					return False
			## List is identical
			return True

		## Type: dictionary
		if (type(data_a) is dict):
			## Is [data_b] a dictionary?
			if (type(data_b) != dict):
				return False
			## Iterate over dictionary keys
			for dict_key,dict_value in data_a.items():
				## Key exists in [data_b] dictionary, and same value?
				if ((dict_key not in data_b) or
					(not compare(dict_value, data_b[dict_key]))):
					return False
			## Dictionary is identical
			return True

		## Simple value; compare both value and type for equality
		return ((data_a == data_b) and (type(data_a) is type(data_b)))

	## Compare a to b, and then b to a
	compareResult = (compare(source_data_a, source_data_b) and
					 compare(source_data_b, source_data_a))

	## end compareJsonResults
	return compareResult


def checkArgsForPlainText(argv):
	"""See if -plaintext was specified as a command line argument."""
	useCertificate = True
	if len(argv) > 1:
		#print('ARGV length: {}'.format(len(argv)))
		for thisArg in argv[1:]:
			#print('  this arg: {}'.format(thisArg))
			if re.search('-plaintext', thisArg, re.I):
				useCertificate = False
	print('Using certificate for traffic encryption? {}'.format(useCertificate))

	## end checkArgsForPlainText
	return useCertificate


def loadFile(fileWithPath):
	"""One line wrapper for three lines of code to read a file."""
	text = ''
	with open(fileWithPath) as fp:
		text = fp.read()
	return text


def loadConfFile(env, fileName):
	"""Get the shared OS level parameters."""
	fileWithPath = os.path.join(env.configPath, fileName)

	## end loadConfigGroupFile
	return(loadFile(fileWithPath))


def grouper(iterable, n, fillvalue=None):
	"""Collect byte data into fixed-length chunks or blocks.

	This works unless the data has null values (00), which are dropped and of
	course make the file unusable thereafter.

	Solution provided by Padraic Cunningham in the following thread:
	https://stackoverflow.com/questions/35580801/chunking-bytes-not-strings-in-python-2-and-3
	"""
	# grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
	args = [iter(iterable)] * n
	return ((bytes(bytearray(filter(None, x)))) for x in zip_longest(fillvalue=fillvalue, *args))


def updateParameters(currentParameters, newParameters, skipParameters=[]):
	"""Override/Update current parameters with new parameters."""
	for param in newParameters:
		if param in skipParameters:
			continue
		thisEntry = newParameters[param]
		if isinstance(thisEntry, (list, set, tuple, dict)):
			thisCopy = copy.deepcopy(thisEntry)
			currentParameters[param] = thisCopy
		else:
			currentParameters[param] = thisEntry

	## end updateParameters
	return


class jobParameterizedLogger:
	"""Conditionally log messages, based on the setting of a job parameter.

	This is a wrapper for the logger. If a parameter is set True (usually passed
	as an inputParameter via the job definition), then send all messages flowing
	through this wrapper, into the desired logger level (info/debug/error).

	Instead of just using the global logger settings, we want to provide an easy
	way for jobs to flip on/off detailed job logging for a specific job. This is
	notably used for debugging and development, but can be leveraged for system
	administration. If content gathering jobs are developed using this wrapper,
	jobs can be very quiet (increasing performance) unless/until something goes
	wrong (e.g. access revoked or partially blocked by new firewall rule). Flip
	a job parameter and you see everything the job developer wanted to expose at
	that level.  Sample usage follows:

	myLogger = runtime.logger
	printFlag = runtime.parameters.get('printDebug', False)
	log = jobParameterizedLogger(myLogger, printFlag)
	log.report('Message via the {qualifier!r} {product!r} logger', qualifier='searchable JSON', product='Twisted')

	"""
	def __init__(self, logger, flag=True, level='debug'):
		self.logger = logger
		## Normalize and set the flag for whether we plan to report messages
		self.flag = False
		if flag is True or str(flag) == '1' or re.search('true', str(flag), re.I):
			self.flag = True
		## Normalize and set the logger level
		self.function = self.reportToDebug
		if level.lower() == 'info':
			self.function = self.reportToInfo
		elif level.lower() == 'error':
			self.function = self.reportToError

	def setFlag(self, flag=True):
		self.flag = False
		if flag is True or str(flag) == '1' or re.search('true', str(flag), re.I):
			self.flag = True

	def report(self, *msg, **msgArgs):
		if self.flag:
			self.function(*msg, **msgArgs)

	def reportToDebug(self, *msg, **msgArgs):
		self.logger.debug(*msg, **msgArgs)

	def reportToInfo(self, *msg, **msgArgs):
		self.logger.info(*msg, **msgArgs)

	def reportToError(self, *msg, **msgArgs):
		self.logger.error(*msg, **msgArgs)

	## Regular functions that always log; here to avoid passing 2 loggers around
	def info(self, *msg, **msgArgs):
		self.logger.info(*msg, **msgArgs)

	def debug(self, *msg, **msgArgs):
		self.logger.debug(*msg, **msgArgs)

	def warn(self, *msg, **msgArgs):
		self.logger.warn(*msg, **msgArgs)

	def error(self, *msg, **msgArgs):
		self.logger.error(*msg, **msgArgs)


class RealmUtility:
	"""Utility for checking IP inclusion/exclusion from networks in the realm."""
	def __init__(self, dbClient):
		self.realms = {}
		## Normalize when passed both of these two db client types:
		##   database.connectionPool.DatabaseClient
		##   sqlalchemy.orm.scoping.scoped_session
		#self.getRealms(dbClient)
		dbSession = None
		if isinstance(dbClient, sqlAlchemySession) or isinstance(dbClient, sqlAlchemyScopedSession):
			dbSession = dbClient
		elif isinstance(dbClient, tableMapping.DatabaseClient):
			dbSession = dbClient.session
		else:
			raise EnvironmentError('The dbClient passed to RealmUtility must be either a database.connectionPool.DatabaseClient or a sqlalchemy.orm.scoping.scoped_session.')
		self.getRealms(dbSession)

	def getRealms(self, dbClient):
		"""Retrieve all RealmScope definitions and transform into networks."""
		dbTable = tableMapping.RealmScope
		dataHandle = dbClient.query(dbTable).all()
		for scope in dataHandle:
			networkObjects = []
			for networkAsString in scope.data:
				thisNetwork = ipaddress.ip_network(networkAsString, False)
				networkObjects.append(thisNetwork)
			self.realms[scope.realm] = networkObjects
		## end getRealms
		return

	def isIpInRealm(self, ipAsString, realmName):
		"""Determine if an IP falls within the boundary of the realm networks."""
		if realmName not in self.realms:
			raise EnvironmentError('Unknown realm: {}'.format(realmName))
		ipAsNetwork = ipaddress.ip_network(ipAsString)
		for network in self.realms[realmName]:
			if network.overlaps(ipAsNetwork):
				return True
		## end isIpInRealm
		return False


def getKafkaPartitionCount(logger, kafkaConsumer, kafkaTopic):
	"""Get the partition count; good for troubleshooting."""
	partitionCount = 0
	## You will hit an exception here if this is the first time the topic is
	## used (auto.create.topics.enable=true), since there will be no partitions
	#with suppress(Exception):
	filteredTopics = kafkaConsumer.list_topics(kafkaTopic)
	partitionCount = len(filteredTopics.topics[kafkaTopic].partitions)
	logger.info('Kafka topic {}: number of partitions: {}'.format(kafkaTopic, partitionCount))

	## end getPartitionCount
	return partitionCount


def attemptKafkaConsumerConnection(logger, kafkaEndpoint, kafkaTopic, useCertsWithKafka, kafkaCaRootFile, kafkaCertFile, kafkaKeyFile, useGroup=True):
	"""Helper function for createKafkaConsumer."""
	## Configure consumer properties
	kafkaProperties = {}
	kafkaProperties['bootstrap.servers'] = kafkaEndpoint
	if useGroup:
		kafkaProperties['group.id'] = kafkaTopic
	kafkaProperties['auto.offset.reset'] = 'latest'
	#kafkaProperties['auto.offset.reset'] = 'earliest'
	kafkaProperties['default.topic.config'] = {'auto.offset.reset': 'latest'}
	#kafkaProperties['default.topic.config'] = {'auto.offset.reset': 'earliest'}
	if useCertsWithKafka:
		logger.debug('Attempting secure connection for Kafka consumer to {} for topic {}'.format(kafkaEndpoint, kafkaTopic))
		kafkaProperties['security.protocol'] = 'ssl'
		kafkaProperties['ssl.ca.location'] = kafkaCaRootFile
		kafkaProperties['ssl.certificate.location'] = kafkaCertFile
		kafkaProperties['ssl.key.location'] = kafkaKeyFile
		#kafkaProperties['debug'] = 'all'
		kafkaProperties['broker.address.family'] = 'v4'
		#kafkaProperties['ssl.ca.location'] = certifi.where()
		kafkaProperties['enable.ssl.certificate.verification'] ='false'
	else:
		logger.debug('Attempting plain text connection for Kafka consumer to {} for topic {}'.format(kafkaEndpoint, kafkaTopic))
	#logger.debug('kafkaConsumer using properties: {}'.format(str(json.dumps(kafkaProperties))))
	## Attempt connection
	kafkaConsumer = KafkaConsumer(kafkaProperties)
	if kafkaConsumer is None:
		raise KafkaError('Unable to get kafkaConsumer for topic {}.'.format(kafkaTopic))
	kafkaConsumer.subscribe([kafkaTopic])
	logger.info('Connection successful; Kafka consumer connected to topic {}.'.format(kafkaTopic))

	## end attemptKafkaConsumerConnection
	return kafkaConsumer


def createKafkaConsumer(logger, kafkaEndpoint, kafkaTopic, useCertsWithKafka=False, kafkaCaRootFile=None, kafkaCertFile=None, kafkaKeyFile=None, maxRetries=5, sleepBetweenRetries=0.5):
	"""Connect to Kafka and initialize a consumer."""
	## This is very close to the same named function in the sharedClient and
	## sharedService modules. The main difference: the controlling while loop in
	## the other modules checks Event objects (cancelled and shutdown), which
	## we wouldn't have in other modules... like the API.
	errorCount = 0
	kafkaConsumer = None
	while kafkaConsumer is None:
		try:
			kafkaConsumer = attemptKafkaConsumerConnection(logger, kafkaEndpoint, kafkaTopic, useCertsWithKafka, kafkaCaRootFile, kafkaCertFile, kafkaKeyFile)

		except KafkaError:
			logger.error('Exception in createKafkaConsumer: Kafka error: {}'.format(str(sys.exc_info()[1])))
			if errorCount >= maxRetries:
				logger.error('Too many error attempts to connect; aborting createKafkaConsumer.')
				break
			errorCount += 1
			time.sleep(sleepBetweenRetries)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			logger.error('Exception in createKafkaConsumer: {}'.format(exception))
			break

	## end createKafkaConsumer
	return kafkaConsumer


def attemptKafkaProducerConnection(logger, kafkaEndpoint, useCertsWithKafka, kafkaCaRootFile, kafkaCertFile, kafkaKeyFile):
	"""Helper function for createKafkaConsumer."""
	## Configure producer properties
	kafkaProperties = {}
	kafkaProperties['bootstrap.servers'] = kafkaEndpoint
	kafkaProperties['message.send.max.retries'] = 10000000
	kafkaProperties['enable.idempotence'] = True
	kafkaProperties['message.max.bytes'] = 15728640
	## available compression.type values: gzip, snappy, lz4, zstd
	kafkaProperties['compression.type'] = 'gzip'
	if useCertsWithKafka:
		logger.debug('Attempting secure connection for Kafka producer to {}'.format(kafkaEndpoint))
		kafkaProperties['security.protocol'] = 'ssl'
		kafkaProperties['ssl.ca.location'] = kafkaCaRootFile
		kafkaProperties['ssl.certificate.location'] = kafkaCertFile
		kafkaProperties['ssl.key.location'] = kafkaKeyFile
		kafkaProperties['broker.address.family'] = 'v4'
		#kafkaProperties['ssl.ca.location'] = certifi.where()
		kafkaProperties['enable.ssl.certificate.verification'] ='false'
	else:
		logger.debug('Attempting plain text connection for Kafka producer to {}'.format(kafkaEndpoint))
	## Attempt connection
	kafkaProducer = KafkaProducer(kafkaProperties)
	if kafkaProducer is None:
		raise KafkaError('Unable to get kafkaProducer.')
	logger.info('Connection successful; Kafka producer connected.')

	## end attemptKafkaProducerConnection
	return kafkaProducer


def createKafkaProducer(logger, kafkaEndpoint, useCertsWithKafka=False, kafkaCaRootFile=None, kafkaCertFile=None, kafkaKeyFile=None, maxRetries=5, sleepBetweenRetries=0.5):
	"""Connect to Kafka and initialize a producer."""
	## This is very close to the same named function in the sharedClient and
	## sharedService modules. The main difference: the controlling while loop in
	## the other modules checks the cancelled and shutdown event objects, which
	## we wouldn't have in other areas of the program.
	errorCount = 0
	kafkaProducer = None
	while kafkaProducer is None:
		try:
			kafkaProducer = attemptKafkaProducerConnection(logger, kafkaEndpoint, useCertsWithKafka, kafkaCaRootFile, kafkaCertFile, kafkaKeyFile)

		except KafkaError:
			logger.error('Exception in createKafkaConsumer: Kafka error: {}'.format(str(sys.exc_info()[1])))
			if errorCount >= maxRetries:
				logger.error('Too many error attempts to connect; aborting createKafkaProducer.')
				break
			errorCount += 1
			time.sleep(sleepBetweenRetries)

		except:
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			logger.error('Exception in createKafkaProducer: {}'.format(exception))
			break

	## end createKafkaProducer
	return kafkaProducer


def loadExternalLibrary(libraryAlias, env=None, globalSettings=None):
	"""Load an externally contributed library (wrapper for something sensitive).

	Arguments:
	  libraryAlias (str)    : external library key found in globalSettings
	  env                   : Module containing the env paths
	  globalSettings (json) : system settings from ./conf/globalSettings.json
	"""
	if env is None:
		import env
	if globalSettings is None:
		globalSettings = loadSettings(os.path.join(env.configPath, 'globalSettings.json'))
	## Get defined name of the external library
	externalDatabaseLibrary = globalSettings.get(libraryAlias)
	## Add the external directory onto sys.path before calling the library
	env.addExternalPath()

	## end loadExternalLibrary
	return importlib.import_module(externalDatabaseLibrary)


def getGigOrMeg(value):
	"""Helper function for memory sizing and human readability."""
	k, b = divmod(value, 1000)
	m, k = divmod(k, 1024)
	g, m = divmod(m, 1024)

	## Just the general amount is fine for reporting status
	total = '{} MB'.format(m)
	if g > 1:
		total = '{} GB'.format(g)

	## end getGigOrMeg
	return total


def logExceptionWithSelfLogger(skipTraceback=False, reRaiseException=False):
	"""Decorator to wrap any function with try/except logging.

	This version uses self.logger from the class method being called."""
	def decorator(function):
		def wrapper(self, *args, **kwargs):
			logger = self.logger
			try:
				return function(self, *args, **kwargs)
			except:
				if skipTraceback:
					message = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
					logger.error('Exception in {}: {}'.format(function.__name__, message))
				else:
					## Don't use logger.exception because we don't know the type
					## of logger we have: python, twisted, multiprocess, etc:
					#logger.exception('Exception: ')
					exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					logger.error('Exception:  {}'.format(exception))
				if reRaiseException:
					raise
		return wrapper
	return decorator


def logExceptionWithFactoryLogger(skipTraceback=False, reRaiseException=False):
	"""Decorator to wrap any function with try/except logging.

	This version uses self.logger from the class' factory."""
	def decorator(function):
		def wrapper(self, *args, **kwargs):
			logger = self.factory.logger
			try:
				return function(self, *args, **kwargs)
			except:
				if skipTraceback:
					message = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
					logger.error('Exception in {}: {}'.format(function.__name__, message))
				else:
					## Don't use logger.exception because we don't know the type
					## of logger we have: python, twisted, multiprocess, etc:
					#logger.exception('Exception: ')
					exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					logger.error('Exception:  {}'.format(exception))
				if reRaiseException:
					raise
		return wrapper
	return decorator


def logException(skipTraceback=False, reRaiseException=False):
	"""Decorator to wrap any function with try/except logging.

	This version assumes 'logger' is a globally accessible variable."""
	def decorator(function):
		def wrapper(*args, **kwargs):
			try:
				return function(*args, **kwargs)
			except:
				if skipTraceback:
					message = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
					logger.error('Exception in {}: {}'.format(function.__name__, message))
				else:
					## Don't use logger.exception because we don't know the type
					## of logger we have: python, twisted, multiprocess, etc:
					#logger.exception('Exception: ')
					exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					logger.error('Exception:  {}'.format(exception))
				if reRaiseException:
					raise
		return wrapper
	return decorator
