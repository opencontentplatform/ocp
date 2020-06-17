import sys
import traceback
import re
import hug
from falcon import HTTPUnauthorized
import database.schema.platformSchema as platformSchema

def validSecurityContext(request, response, context=None, **kwargs):
	authenticated = False
	try:
		apiUser = request.get_header('apiUser')
		if apiUser is None:
			raise HTTPUnauthorized('Authentication Required', 'Please provide valid security context in the headers')
		apiKey = request.get_header('apiKey')
		request.context['apiUser'] = apiUser
		request.context['apiKey'] = apiKey

		## Use variables stored in the falcon middleware to determine ACLs
		urlPath = request.relative_uri
		urlMethod = request.method
		urlRoot = request.context['baseUrl']
		## Determine required access levels for this URL
		requireAdminPerm = False
		requireWritePerm = False
		requireDeletePerm = False
		searchString = '^' + urlRoot + '/([^/]+)'
		m = re.search(searchString, urlPath)
		if m:
			apiResource = m.group(1)
			adminResources = ['config', 'archive']
			if apiResource.lower() in adminResources:
				requireAdminPerm = True
		if urlMethod == 'put' or urlMethod == 'post':
			requireWritePerm = True
		elif urlMethod == 'delete':
			requireDeletePerm = True

		## Get the user
		dbSession = request.context['dbSession']
		apiTable = platformSchema.ApiConsumerAccess
		matchedEntry = dbSession.query(apiTable).filter(apiTable.key == apiKey).first()
		if matchedEntry:
			## Make sure the user matched what was provided
			if (apiUser == matchedEntry.name):
				authenticated = True
				## Ok, user seems valid; check the ACLs
				if requireWritePerm and not matchedEntry.access_write:
					request.context['logger'].info('Access denied. This resource requires Write permission, but the user account does not have it: {}'.format(apiUser))
					request.context['payload']['errors'].append('Access denied. This resource requires Write permission, which the user account does not have.')
					authenticated = False
				if requireDeletePerm and not matchedEntry.access_delete:
					request.context['logger'].info('Access denied. This resource requires Delete permission, but the account does not have it: {}'.format(apiUser))
					request.context['payload']['errors'].append('Access denied. This resource requires Delete permission, which the user account does not have.')
					authenticated = False
				if requireAdminPerm and not matchedEntry.access_admin:
					request.context['logger'].info('Access denied. This resource requires Admin permission, but the account does not have it: {}'.format(apiUser))
					request.context['payload']['errors'].append('Access denied. This resource requires Admin permission, which the user account does not have.')
					authenticated = False
			else:
				request.context['logger'].error('Potential security concern. Valid key provided but the user was incorrect. User provided was {} when database lists user as {}'.format(apiUser, matchedEntry.name))
				request.context['payload']['errors'].append('Access denied.')
				authenticated = False
		else:
			request.context['logger'].info('User not authenticated: {}'.format(apiUser))
			request.context['payload']['errors'].append('Access denied.')
			authenticated = False

		## Authenticate user/client key
		if not authenticated:
			raise HTTPUnauthorized('Invalid Authentication', 'Provided security context was invalid')

	except:
		exceptionOnly = traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
		request.context['logger'].error('Failure in validSecurityContext: {}'.format(exceptionOnly))
		request.context['payload']['errors'].append(exceptionOnly)
		raise

	return authenticated

## Wrapper context for api functions to use
hugWrapper = hug.http(requires=validSecurityContext)
