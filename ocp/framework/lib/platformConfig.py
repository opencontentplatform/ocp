"""Install utility.

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Nov 26, 2018

"""
import sys
import traceback
import os
import json
from tzlocal import get_localzone
from pytz import all_timezones
import datetime

## Add openContentPlatform directories onto the sys path
import createApiUser
import platformSetup
import contentManagement
import utils
thisPath = os.path.dirname(os.path.abspath(__file__))
basePath = os.path.abspath(os.path.join(thisPath, '..'))
if basePath not in sys.path:
	sys.path.append(basePath)
import env


def getInputOrReturnDefault(message, default=None):
	value = None
	## Prepare the message with default value
	if default is None:
		message = '{}: '.format(message)
	else:
		message = '{} [{}]: '.format(message, default)
	## Loop until a value is accepted
	while 1:
		value = input(message)
		if len(value) <= 0:
			if default is None:
				print('   ==> no default defined; value is required.')
			else:
				value = default
				break
		else:
			break
	## end getInputOrReturnDefault
	return value


def verifyTimeZone(myTimeZone):
	if myTimeZone in all_timezones:
		print(' ==> timezone verified: {}'.format(myTimeZone))
		return True
	
	## end verifyTimeZone
	return False


def setTimeZone(globalSettings):
	myTimeZone = None
	try:
		myTimeZone = str(get_localzone())
		if not verifyTimeZone(myTimeZone):
			myTimeZone = str(datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo)
		while not verifyTimeZone(myTimeZone):
			myTimeZone = getInputOrReturnDefault('\nTimezone could not be programatically determined. Please select from list: \n\n{}'.format(str(all_timezones)), 'UTC')
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		print('Problem getting timezone: {}'.format(stacktrace))
	if not verifyTimeZone(myTimeZone):
		myTimeZone = 'UTC'
	print('Setting local timezone to: {}'.format(myTimeZone))
	globalSettings['localTimezone'] = myTimeZone

	## end setTimeZone
	return


def main():
	"""Gather input for configuring globalSettings.json."""
	try:
		## Ask questions and update the conf/globalSettings.json
		globalSettingsFile = os.path.join(env.configPath, 'globalSettings.json')
		globalSettings = None
		with open(globalSettingsFile, 'r') as f:
			globalSettings = json.load(f)

		## Set the application server endpoints
		serviceIpAddress = globalSettings.get('serviceIpAddress')
		appServer = getInputOrReturnDefault('Application server', serviceIpAddress)
		if serviceIpAddress != appServer:
			globalSettings['serviceIpAddress'] = appServer
			globalSettings['apiIpAddress'] = appServer
			globalSettings['transportIpAddress'] = appServer

		## Are we intending to use certificates and encrypt traffic?
		useCertificates = globalSettings.get('useCertificates')
		useCerts = getInputOrReturnDefault('Encrypt OCP client/service traffic with certificates', useCertificates)
		useCerts = utils.valueToBoolean(useCerts)
		if useCertificates != useCerts:
			globalSettings['useCertificates'] = useCerts
			if useCerts:
				globalSettings['transportType'] = 'https'
			else:
				globalSettings['transportType'] = 'http'

		## Set the Kafka endpoint
		kafkaEndpoint = globalSettings.get('kafkaEndpoint')
		kafkaServer = getInputOrReturnDefault('Kafka endpoint', kafkaEndpoint)
		if kafkaEndpoint != kafkaServer:
			globalSettings['kafkaEndpoint'] = kafkaServer

		## Are we intending to use certificates and encrypt Kafka traffic?
		useCertificates = globalSettings.get('useCertificatesWithKafka')
		useCerts = getInputOrReturnDefault('Encrypt Kafka producer/consumer traffic with certificates', useCertificates)
		useCerts = utils.valueToBoolean(useCerts)
		if useCertificates != useCerts:
			globalSettings['useCertificatesWithKafka'] = useCerts

		## Set the default timezone for APScheduler
		setTimeZone(globalSettings)

		## Overwrite the globalSettings file with our values
		with open(globalSettingsFile, 'w') as f:
			json.dump(globalSettings, f, indent=4)

		print('Calling platformSetup...')
		platformSetup.main()

		print('Creating an API user account...')
		createApiUser.main()

		print('Loading Packages...')
		contentManagement.baselinePackagesInDatabase()

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		print('Exception in startWork: {}'.format(stacktrace))


if __name__ == '__main__':
	sys.exit(main())
