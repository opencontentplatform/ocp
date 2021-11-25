"""Task resource for the Open Content Platform REST API.

This module defines the Application Programming Interface (API) methods for the
/<root>/task endpoint. Available resources follow::

	/<root>/task

"""

import sys
import traceback
import os
from hug.types import text
from hug.types import json as hugJson

## From openContentPlatform
import utils
from apiHugWrapper import hugWrapper
from apiResourceUtils import *
## Add openContentPlatform directories onto the sys path
import env
globalSettings = utils.loadSettings(os.path.join(env.configPath, "globalSettings.json"))


@hugWrapper.get('/')
def getTaskContent(request, response):
	"""Show available task resources."""
	staticPayload = {'Available Resources' : {
		'/task' : {
			'methods' : {
				'POST' : 'Validate and insert the provided JSON data set.',
				'DELETE' : 'Remove all objects in the provided JSON data set.'
			}
		}
	}}

	## end getTaskContent
	return staticPayload


@hugWrapper.post('/')
def insertTaskContent(content:hugJson, request, response):
	"""Validate and insert the provided JSON result map."""
	try:
		insertTaskContentHelper(request, response, content)
	except:
		errorMessage(request, response)

	## end insertTaskContent
	return cleanPayload(request)


@hugWrapper.delete('/')
def deleteTaskContent(content:hugJson, request, response):
	"""Remove all objects matching the input JSON map."""
	try:
		deleteTaskContentHelper(request, response, content)
	except:
		errorMessage(request, response)

	## end deleteTaskContent
	return cleanPayload(request)
