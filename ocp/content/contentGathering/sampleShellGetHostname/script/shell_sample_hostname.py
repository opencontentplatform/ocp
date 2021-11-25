"""Sample script illustrating how to gather new content.

Crash course for logging:
  These are available for all scripts, and work off the settings found in the
  configuration files located in the ./conf directory:
    runtime.logger.error()
    runtime.logger.warn()
    runtime.logger.info()
    runtime.logger.debug()

  So for a contentGathering job (like this sample), we look at the "JobDetail"
  section found in conf/logSettingsContentGathering.json. Specifically look at
  the "logLevel" setting. If set to "DEBUG", then all of the above log message
  types will print (debug, info, warn, and error). If set to "INFO", then any
  line with .debug() will not make it to the logs. If set to "ERROR", then the
  .info() .debug() and .warn() lines will be ignored. This is a broad stroke.

  To enable logging specific to a job, we leverage 'printDebug' in the job input
  parameters section. That enables the following type of messages:
    runtime.logger.report()

  When printDebug is false, all report lines will be ignored. If developers
  of new content make a habit of using the .report() syntax, then they enable
  focused script debugging. Enable debugging by flipping an input parameter
  on the job, instead of stopping all active jobs (to prevent non-essential
  job noise and excessive log rotations) before changing a global setting.

  One final method is a wrapped version inside of runtime. It's purpose is
  simply to call .error() as well as setting the job status to FAILURE for
  the tracked job statistics.

  Suggested conventions for folks developing new content:
    runtime.setError() - for exceptions that reflect fatal failures
    runtime.logger.error() - for exceptions caught but are not fatal
    runtime.logger.report() - for anything useful to debugging
    runtime.logger.debug - simply avoid; use .report instead
    runtime.logger.info - if you really want to work off global log levels
    runtime.logger.warn - if you really want to work off global log levels


Functions:
  startJob : standard job entry point
  doSomething : worker function to issue a command and check results
  parserFunction : helper function to illustrate the difference with logging

"""
import re
import sys
import traceback
from contextlib import suppress
## From openContentPlatform
from protocolWrapper import getClient


def parserFunction(runtime, value):
	"""Helper function to illustrate the difference with logging.

	Notice the exception handling here is using 'runtime.logger.error()' instead
	of 'runtime.setError()'. This is because I wouldn't consider a failure here
	to imply the job failed.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	  value (str)      : string object evaluated in this function
	"""
	parsedValue = value
	try:
		m = re.search('^([a-zA-Z].*)', value)
		## If the hostname starts with a letter
		if m:
			## Forcing a failure; should be group(1) and I'm asking for group(2)
			#parsedValue = m.group(1)
			parsedValue = m.group(2)

	except:
		## Printing out the error, but it's not a show stopper because I already
		## have the value from issuing the 'hostname' command, returned below
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error(' Failure in parserFunction: {stacktrace!r}', stacktrace=stacktrace)

	## end parserFunction
	return parsedValue


def doSomething(runtime, client):
	"""Worker function to issue a command and check results.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	  client (shell)   : instance of the shell wrapper
	"""
	try:
		## For clients using shell protocols (SSH and PowerShell), invoking a
		## general command is done by calling client.run(command, timeout) with
		## timeout (in seconds) being optional. That will produce three output
		## parameters: standard out (STDOUT), any errors (STDERR), and a
		## normalized exit status to tells us if the command hit a problem.
		command = 'hostname'
		(outputString, stderr, hitProblem) = client.run(command, 3)

		## If we hit an error, or the command produced zero output, raise a
		## custom exception and catch it below with runtime.setError()
		if (hitProblem or outputString is None or len(outputString) <= 0):
			raise OSError('Command failed {}. Error returned {}'.format(command, stderr))

		## If we get here, the command passed and life is good. Now let's parse
		## the result. I could do this here, but I'll call a helper function
		## for the purpose of illustrating differences with logging.
		myParsedValue = parserFunction(runtime, outputString)
		runtime.logger.report(' --> parsed value {value!r}', value=myParsedValue)

		## TODO: send result to the bus for a target destination (CMS or other);
		## proceed to next sample job to see how that works. If target is CMS,
		## then use addObject() and then runtime.sendToKafka(). If target is
		## another destination, and you still want to use the bus then use this:
		#runtime.sendToKafka('customTopic', outputString)

	except:
		runtime.setError(__name__)

	## end doSomething
	return


def startJob(runtime):
	"""Standard job entry point.

	Arguments:
	  runtime (dict)   : object used for providing input into jobs and tracking
	                     the job thread through the life of its runtime.
	"""
	client = None
	try:
		## Drop our input parameters into the log
		for inputParameter in runtime.parameters:
			runtime.logger.report(' --> input parameter {name!r}: {value!r}', name=inputParameter, value=runtime.parameters.get(inputParameter))

		## Configure shell client
		client = getClient(runtime)
		if client is not None:
			## Client is configured and ready to use, but we won't establish
			## an actual connection until needed

			## Open the client before starting the work
			client.open()

			## Now do something simple; issue a command and check results
			doSomething(runtime, client)

			## Good house keeping; though I force this after the exception below
			client.close()

			## Update the runtime status to success, for job tracking and proper
			## statistics. You don't want jobs to list UNKNOWN if you know they
			## either passed or failed. Likewise, you may not want to leave them
			## tagged with FAILED if some of the previous failures can be safely
			## disregarded upon a final success criteria.
			if runtime.getStatus() == 'UNKNOWN':
				runtime.status(1)

	except:
		runtime.setError(__name__)

	with suppress(Exception):
		if client is not None:
			client.close()

	## end startJob
	return
