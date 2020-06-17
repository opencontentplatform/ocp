"""Get the current python module versions available in the environment.

Functions:
  startJob : standard job entry point
  doWork : get the list of python modules and compare to previous results
  getLocalLogger : create a local log handler; historical tracking purposes

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Oct 23, 2019

"""
import sys
import traceback
import subprocess
import os
import json
import logging, logging.handlers
from utilities import verifyJobRuntimePath


def getLocalLogger(jobRuntimePath):
	"""Setup a local log handler for client-local tracking on job.

	Arguments:
	  jobRuntimePath (str) : path to the local runtime results
	"""
	## Create a local logger for details
	logSettings = {
		"fileName" : "pythonPackages.log",
		"maxSizeInBytes" : "10485760",
		"maxRollovers" : "3",
		"logLevel" : "DEBUG",
		"lineFormat" : "%(asctime)s  %(levelname)-7s %(filename)-21s  %(message)s",
		"dateFormat" : "%Y-%m-%d %H:%M:%S"
	}
	logFile = os.path.join(jobRuntimePath, logSettings.get('fileName'))
	logger = logging.getLogger()
	logger.setLevel(logSettings.get('logLevel'))
	mainHandler = logging.handlers.RotatingFileHandler(logFile,
													   maxBytes=int(logSettings.get('maxSizeInBytes')),
													   backupCount=int(logSettings.get('maxRollovers')))
	fmt = logging.Formatter(logSettings.get('lineFormat'), datefmt = logSettings.get('dateFormat'))
	mainHandler.setFormatter(fmt)
	logger.addHandler(mainHandler)

	## end getLocalLogger
	return mainHandler


def doWork(runtime, jobRuntimePath, detailLogger):
	"""Get the PIP list and compare to previous results.

	Arguments:
	  runtime (dict) : object used for providing input into jobs and tracking
	                   the job thread through the life of its runtime.
	  jobRuntimePath (str) : path to the local runtime results
	"""

	procOutFile = os.path.join(jobRuntimePath, 'pip.output')
	procErrFile = os.path.join(jobRuntimePath, 'pip.error')
	with open(procOutFile, 'w') as fpOut:
		with open(procErrFile, 'w') as fpErr:
			proc = subprocess.Popen([sys.executable, "-m", "pip", "list", "--format", "json"], stdout=fpOut, stderr=fpErr)
			try:
				proc.communicate(timeout=30)
			except TimeoutExpired:
				detailLogger.error('pip list command timed out')
				runtime.logger.report('pip list command timed out')
				proc.kill()
				proc.communicate()

	stdoutData = None
	with open(procOutFile) as fpOut:
		stdoutData = fpOut.read()
	stderrData = None
	with open(procErrFile) as fpOut:
		stderrData = fpOut.read()
	runtime.logger.report('pip list stdout: {stdoutData!r}', stdoutData=stdoutData)
	runtime.logger.report('pip list stderr: {stderrData!r}', stderrData=stderrData)
	currentRawJson = json.loads(stdoutData)
	currentPkgs = {}
	for module in currentRawJson:
		moduleName = module.get('name')
		moduleVersion = module.get('version')
		currentPkgs[moduleName] = moduleVersion

	previousPkgsFile = os.path.join(jobRuntimePath, 'pythonPackages.json')
	if not os.path.isfile(previousPkgsFile):
		## Nothing the compare; dump the current pip list into the file
		detailLogger.info('Creating the initial pythonPackages.json file.')
		for currentName,currentVersion in currentPkgs.items():
			detailLogger.info(' ==> {} = {}'.format(currentName, currentVersion))
		with open(previousPkgsFile, 'w') as fp:
			json.dump(currentPkgs, fp, indent=4)
	else:
		## Load the file containing the previous python package versions
		previousPkgs = {}
		with open(previousPkgsFile) as fp:
			previousPkgs = json.load(fp)

		## Iterate through and compare
		updateFile = False
		for currentName,currentVersion in currentPkgs.items():
			if currentName not in previousPkgs:
				## new module found
				detailLogger.info('Found a new package: {} = {}.'.format(currentName, currentVersion))
				updateFile = True
			elif previousPkgs[currentName] != currentVersion:
				## different version found
				detailLogger.info('Previous package has a new version: {} = {} (previous version was {}).'.format(currentName, currentVersion, previousPkgs[currentName]))
				updateFile = True
		if updateFile:
			detailLogger.info('Changes found in the python packages; updating the local pythonPackages.json file.')
			with open(previousPkgsFile, 'w') as fp:
				json.dump(currentPkgs, fp, indent=4)
		else:
			detailLogger.info('No changes to the python packages found.')
			runtime.logger.report('No changes to the python packages found.')
	## end doWork
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	try:

		## Establish our runtime working directory
		jobRuntimePath = verifyJobRuntimePath(__file__)
		runtime.logger.report('path jobRuntimePath: {jobRuntimePath!r}', jobRuntimePath=jobRuntimePath)
		mainHandler = getLocalLogger(jobRuntimePath)
		detailLogger = logging.getLogger()
		doWork(runtime, jobRuntimePath, detailLogger)
		## Remove the handler to avoid duplicate lines the next time it runs
		detailLogger.removeHandler(mainHandler)

		## Update the runtime status to success
		if runtime.getStatus() == 'UNKNOWN':
			runtime.status(1)

	except:
		runtime.setError(__name__)

	## end startJob
	return
