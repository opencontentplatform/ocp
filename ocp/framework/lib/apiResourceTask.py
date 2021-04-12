"""Task resource for the Open Content Platform REST API.

This module defines the Application Programming Interface (API) methods for the
/<root>/task endpoint. Available resources follow::

	/<root>/task

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Sep 15, 2017
	  1.1 : (CS) Replaced apiUtils with Falcon middleware, Sept 2, 2019

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
