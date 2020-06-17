"""Track the responsiveness of a URL.

This is a sample script, should someone want to head the direction of a
monitoring type framework with OCP.


Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Dec 17, 2018

"""
import sys
import traceback
import time
import os
import json
import logging, logging.handlers
from contextlib import suppress
import requests

## Disabling warnings from some of the less secure acceptance
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
## Some sites have SSLv2 disabled on the web server, but since Python tries to
## establish a connection via PROTOCOL_SSLv23 by default... possible error:
##   SSLError("bad handshake: SysCallError(10054, 'WSAECONNRESET')")
## The following monkey-patch should fix it, pulled directly from this post:
##   https://stackoverflow.com/questions/14102416/python-requests-requests-exceptions-sslerror-errno-8-ssl-c504-eof-occurred/24166498#24166498
import ssl
from functools import wraps
def sslwrap(func):
    @wraps(func)
    def bar(*args, **kw):
        kw['ssl_version'] = ssl.PROTOCOL_TLSv1
        return func(*args, **kw)
    return bar
ssl.wrap_socket = sslwrap(ssl.wrap_socket)

## From openContentPlatform
import utils
import utilities


def getCurrentURLs(runtime, urlList):
	"""Pull URLs from the database."""
	targetQuery = runtime.parameters.get('targetQuery')
	queryFile = os.path.join(runtime.env.contentGatheringPkgPath, 'checkUrlResponse', 'input', targetQuery + '.json')
	if not os.path.isfile(queryFile):
		raise EnvironmentError('JSON query file does not exist: {}'.format(queryFile))

	## Load the file containing the query for IPs
	queryContent = None
	with open(queryFile) as fp:
		queryContent = json.load(fp)

	## Get the results from the query
	queryResults = utilities.getApiQueryResultsFull(runtime, queryContent, resultsFormat='Flat')
	if queryResults is None or len(queryResults) <= 0:
		raise EnvironmentError('No URLs found from database; nothing to do.')

	## Convert the API results into a desired layout for our needs here
	for entry in queryResults.get('objects', []):
		url = entry.get('data').get('name')
		urlList.append(url)
	queryResults = None

	## end getCurrentURLs
	return


def getUrlReponse(runtime, urlList, waitSecondsBeforeWarn, waitSecondsBeforeError, waitSecondsBeforeTimeOut):
	"""Find processes without children and start investigation.

	Arguments:
	  runtime (dict)             : object used for providing I/O for jobs and
	                               tracking the job thread through its runtime
	  data (dataContainer)       : holds variables used across functions
	"""
	for url in urlList:
		try:
			logger = logging.getLogger('urlStatus')
			startTime = time.time()
			runtime.logger.report('Testing response for {url!r}', url=url)
			urlResponse = None
			with requests.Session() as session:
				session.verify = False
				urlResponse = session.get(url, verify=False, timeout=waitSecondsBeforeTimeOut)
			endTime = time.time()
			totalTime = endTime - startTime

			responseCode = urlResponse.status_code
			response = None
			with suppress(Exception):
				response = urlResponse.text
			logger.info('{0}:  runtime: {1:.2f}  response code: {2:}'.format(url, totalTime, responseCode))
			if str(responseCode) != '200':
				logger = logging.getLogger('urlError')
				logger.error('{0}:  runtime: {1:.2f}  response code: {2:}'.format(url, totalTime, responseCode))
			elif totalTime > waitSecondsBeforeError:
				logger = logging.getLogger('urlError')
				logger.error('{0}:  runtime: {1:.2f}  response code: {2:}'.format(url, totalTime, responseCode))
			elif totalTime > waitSecondsBeforeWarn:
				logger = logging.getLogger('urlWarn')
				logger.error('{0}:  runtime: {1:.2f}  response code: {2:}'.format(url, totalTime, responseCode))

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in getUrlReponse for {url!r}: {stacktrace!r}', url=url, stacktrace=stacktrace)
			logger = logging.getLogger('urlError')
			logger.error('{}: exception: {}'.format(url, str(sys.exc_info()[1])))

	## end getUrlReponse
	return


def configureLogging(logPath, logSettings, logHandlers):
	"""Setup requested log handlers.

	Arguments:
	  logPath (str)             : string containing path to the log directory
	  fileWithLogSettings (str) : config file path for log settings

	"""
	## Create requested handler for each log configuration
	for entityName in logSettings.keys():
		## Set each log handler as defined; no reason to wrap with exception
		## handling yet because we haven't established the logs to report it
		logEntry = logSettings.get(entityName)
		logFile = os.path.join(logPath, logEntry.get('fileName'))
		logger = None
		if entityName == 'urlStatus':
			logger = logging.getLogger()
		else:
			logger = logging.getLogger(entityName)
		logger = logging.getLogger(entityName)
		logger.setLevel(logEntry.get('logLevel'))
		thisHandler = logging.handlers.RotatingFileHandler(logFile,
														   maxBytes=int(logEntry.get('maxSizeInBytes')),
														   backupCount=int(logEntry.get('maxRollovers')))
		fmt = logging.Formatter(logEntry.get('lineFormat'), datefmt = logEntry.get('dateFormat'))
		thisHandler.setFormatter(fmt)
		logger.addHandler(thisHandler)
		logHandlers[entityName] = thisHandler

	## end setupLogging
	return


def destroyLogging(logHandlers):
	for entityName,logHandler in logHandlers.items():
		logger = logging.getLogger(entityName)
		logger.removeHandler(logHandler)


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing I/O for jobs and tracking
	                     the job thread through its runtime
	"""
	try:
		## Setup requested log handlers
		jobRuntimePath = utilities.verifyJobRuntimePath(__file__)
		runtime.logger.report('path jobRuntimePath: {jobRuntimePath!r}', jobRuntimePath=jobRuntimePath)
		logPath = os.path.join(runtime.env.contentGatheringPkgPath, 'checkUrlResponse', 'runtime')
		logDefinitions = os.path.join(runtime.env.contentGatheringPkgPath, 'checkUrlResponse', 'conf', 'logSettings.json')
		## Create log handlers
		logHandlers = {}
		logSettings = utils.loadSettings(logDefinitions)
		configureLogging(logPath, logSettings, logHandlers)

		urlList = []
		## Get URLs from the API
		getCurrentURLs(runtime, urlList)
		## Read user-defined job parameters
		waitSecondsBeforeWarn = runtime.parameters.get('waitSecondsBeforeWarn', 3)
		waitSecondsBeforeError = runtime.parameters.get('waitSecondsBeforeError', 10)
		waitSecondsBeforeTimeOut = runtime.parameters.get('waitSecondsBeforeTimeOut', 62)
		## Start the work
		getUrlReponse(runtime, urlList, waitSecondsBeforeWarn, waitSecondsBeforeError, waitSecondsBeforeTimeOut)
		## Destroy log handlers
		destroyLogging(logHandlers)
		## Update the runtime status to success
		if runtime.getStatus() == 'UNKNOWN':
			runtime.status(1)

	except:
		runtime.setError(__name__)

	## end startJob
	return
