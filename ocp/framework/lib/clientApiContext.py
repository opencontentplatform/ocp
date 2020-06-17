## Module for wrapping the DB query for the client API user; avoiding standard
## docstrings.
import sys
import traceback
import json

## From openContentPlatform
import database.schema.platformSchema as platformSchema


def getApiContext(dbClient, globalSettings, logger):
	apiContext = None
	try:
		## Get instances of the API user created for jobs to natively access the
		## API during standard runtime.
		dbTable = platformSchema.ApiConsumerAccess
		result = dbClient.session.query(dbTable).filter(dbTable.name == globalSettings['contentGatheringClientApiUser']).first()
		## Return underlying DBAPI connection to the connection pool
		dbClient.session.close()
		if result:
			tmpValue = result.key.strip()
			## Now pull the API configurations from globalSettings
			apiTcpPort = int(globalSettings.get('apiServicePort'))
			apiEndpoint = globalSettings.get('apiIpAddress')
			apiUseCertificates = globalSettings.get('useCertificates', True)
			apiContextRoot = globalSettings.get('apiContextRoot')
			apiUrlType = 'http'
			if apiUseCertificates:
				apiUrlType = 'https'
			## And create the context
			apiContext = {}
			apiContext['url'] = '{}://{}:{}/{}'.format(apiUrlType, apiEndpoint, apiTcpPort, apiContextRoot)
			## Original style with having security JSON in payload, to support
			## any multi-factor authentication scheme. This was more flexible,
			## but doesn't follow industry standard, so placed back in headers.
			apiContext['headers'] = {'apiUser' : result.name, 'apiKey' : tmpValue}

	except:
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		self.logger.error('Exception in parsing REST API protocol: {exception!r}', exception=exception)

	## end getApiContext
	return apiContext
