"""Module for building a results object.

Classes:
  :class:`results.Results` : JSON structure used in ResultProcessing

"""
import sys
import traceback
import os
import ipaddress
import datetime
import utils

class Results():
	"""Class for the JSON structure used in ResultProcessing."""
	def __init__(self, source=None, usesDeleteRecreateFlow=False, realm='default'):
		"""Constructor for Results.

		Arguments:
		  source (str) : Name of the module using this class
		"""
		self.realm = realm
		self.source = source
		self.jsonResult = dict()
		self.jsonResult['source'] = source
		self.jsonResult['links'] = []
		if usesDeleteRecreateFlow:
			self.jsonResult['temp_weak_links'] = []
		self.jsonResult['objects'] = []
		self.objectId = 1
		self.gatheredTime = str(datetime.datetime.now())
		## We need constraints on DB classes for object comparison/duplicates
		self.classObjects = dict()
		utils.getValidClassObjects(self.classObjects)


	def getObjectId(self):
		"""Auto increment a temporary identifier for object reference."""
		currentId = self.objectId
		self.objectId += 1
		return str(currentId)


	def link(self, className, firstObject, secondObject, listName='links'):
		"""Adds a link entry into the results, by providing objects.

		Arguments:
		  className (str)    : Link class name
		  firstObject (str)  : First object as JSON
		  secondObject (str) : Second object as JSON
		"""
		entry = {}
		entry['class_name'] = className
		entry['first_id'] = firstObject['identifier']
		entry['second_id'] = secondObject['identifier']
		self.jsonResult[listName].append(entry)

	def addLinkIfNotExists(self, className, firstId, secondId, listName):
		"""Only adds a link if it doesn't already exist."""
		for thisLink in self.jsonResult[listName]:
			if thisLink.get('class_name') != className:
				continue
			if (thisLink.get('first_id') == firstId and
				thisLink.get('second_id') == secondId):
				## Already created
				return
		## Link not previously created; need to create
		entry = {}
		entry['class_name'] = className
		entry['first_id'] = firstId
		entry['second_id'] = secondId
		self.jsonResult[listName].append(entry)

	def addLink(self, className, firstId, secondId, listName='links'):
		"""Adds a link entry into the results, by providing object ids.

		Arguments:
		  className (str) : Link class name
		  firstId (str)   : First object id
		  secondId (str)  : Second object id
		"""
		self.addLinkIfNotExists(className, firstId, secondId, listName)

	def addTempWeak(self, className, firstId, secondId):
		"""Adds a weak link entry into the JSON result.

		Arguments:
		  className (str) : Link class name
		  firstId (str)   : First object id
		  secondId (str)  : Second object id
		"""
		self.addLink(className, firstId, secondId, 'temp_weak_links')


	def findExistingObject(self, className, uniqueId, **kargs):
		"""If the same object was previously created, return that object.

		Check if the entry exists. If a script puts duplicate instances of a
		single object into the results, the result processing side will throw
		an error on unique constraints. This is due to how the system does
		database inserts, which is a single commit per result set. Scripts can
		send multiple results or employ better object management to avoid this,
		but this is a catch-all to avoid tickets on intended behavior.

		Note, there is a challenge here with containers. The normal expectation
		is that results will include 'objects' and 'links' sections. When some
		objects require other objects for containers, the system implicitly
		adds a container attribute during the result processing - based on an
		associated strong link in the 'links' section. But at this point (when
		an object is inserted into 'objects', and before the 'links' have been
		built out), we do not have all the context. So we are left with checking
		attributes listed as constraints, minus a container constraint. If you
		want to add the same process to 5 different nodes, you must explicitly
		set a container attribute on each process, or this will think it's the
		same process and merge them all.

		Arguments:
		  className (str) : BaseObject class name
		  uniqueId (str)  : String containing identifier
		  kargs (dict)    : Data on this object
		"""
		constraintAttributes = self.classObjects[className]['classObject'].constraints()
		for thisObject in self.jsonResult.get('objects', []):
			if thisObject.get('class_name') != className:
				continue
			if uniqueId is not None:
				if thisObject.get('identifier') == uniqueId:
					return thisObject
			else:
				skip = False
				## We do not want to check for identical objects, with a json
				## comparison on attribute values. That approach has 2 problems:
				## 1) attributes like 'time_gathered' will exist on previously
				##    created objects, but wouldn't be there on new objects, or
				##    match with objects we intend to update.
				## 2) Even if the data sets aren't identical, we only want to
				##    compare values on attributes setup as unique constraints;
				##    we shouldn't even care about optional attributes.
				## Instead, the following section only uses unique constraints
				## along with a container, should it exist.
				for constraint in constraintAttributes:
					oldValue = thisObject.get('data', {}).get(constraint)
					newValue = kargs.get(constraint)
					if oldValue != newValue:
						skip = True
						break

				## Container check. Most of the time the container attribute
				## will not be set until the result processing stage, where it's
				## assigned based on the associated object connected through a
				## strong link (e.g. Enclosed). But if objects are intentionally
				## constructed with their container attribute, the check below
				## allows creating many objects that have the same attribute
				## values, but are actually separate objects intended to map
				## under separate containers (e.g. shared oracle TCP port,
				## mapped to many clients)
				oldContainer = thisObject.get('data', {}).get('container')
				newContainer = kargs.get('container')
				if newContainer is not None and oldContainer != newContainer:
					skip = True
				if not skip:
					return thisObject

		return None


	def object(self, className, uniqueId=None, checkExisting=True, **kargs):
		"""Adds an object into the results; returns the created JSON object.

		Arguments:
		  className (str) : BaseObject class name
		  uniqueId (str)  : String containing identifier
		  kargs (dict)    : Data on this object
		"""
		entry = {}
		entry['class_name'] = className
		## Determine if the object was previously created
		if checkExisting:
			existingObject = self.findExistingObject(className, uniqueId, **kargs)
			if existingObject is not None:
				return (existingObject, True)
		if uniqueId is None:
			uniqueId = self.getObjectId()
		entry['identifier'] = uniqueId
		data = {}
		for name, value in kargs.items():
			data[name] = value
		data['time_gathered'] = self.gatheredTime
		entry['data'] = data
		self.jsonResult['objects'].append(entry)
		return (entry, False)


	def addObject(self, className, uniqueId=None, checkExisting=True, **kargs):
		"""Adds an object into the results; return the ID of the new object.

		Arguments:
		  className (str) : BaseObject class name
		  uniqueId (str)  : String containing identifier
		  kargs (dict)    : Data on this object
		"""
		entry, exists = self.object(className, uniqueId=uniqueId, checkExisting=checkExisting, **kargs)
		return (entry['identifier'], exists)


	def addIp(self, **kargs):
		"""Verify and add an IP object onto the result set.

		This validates the address is a valid IPv4 or IPv6 string before adding.
		"""
		## This raises a ValueError if address is not valid
		address = ipaddress.ip_address(kargs.get('address'))
		isIpv4 = isinstance(address, ipaddress.IPv4Address)
		## Add the isIpv4 value onto the attribute list
		kargs['is_ipv4'] = isIpv4
		## Add the 'realm' if not explicitely provided
		if 'realm' not in kargs:
			kargs['realm'] = self.realm
		return (self.addObject('IpAddress', **kargs))


	def getObject(self, objectId):
		"""Returns information on the object referenced by the objectId.

		Arguments:
		  objectId (str) : String containing identifier
		"""
		for obj in self.jsonResult['objects']:
			if obj['identifier'] == objectId:
				return obj
		return None


	def updateObject(self, objectId, **kargs):
		obj = self.getObject(objectId)
		data = obj['data']
		for name, value in kargs.items():
			data[name] = value
		return


	def getObjects(self):
		"""Return all objects in the JSON result set."""
		return self.jsonResult.get('objects', [])


	def getLinks(self):
		"""Return all links in the JSON result set."""
		return self.jsonResult.get('links', [])

	def size(self):
		"""Return a count of the objects, currently ignoring links."""
		return len(self.jsonResult.get('objects', []))

	def getJson(self):
		"""Return the entire JSON result set."""
		return self.jsonResult


	def clearJson(self):
		"""Empty and reinitialize the JSON result set."""
		self.jsonResult = dict()
		self.jsonResult['source'] = self.source
		self.jsonResult['links'] = []
		self.jsonResult['temp_weak_links'] = []
		self.jsonResult['objects'] = []


def main():
	"""Test function."""
	try:
		results = Results()
		secondId, exists = results.addIp(address='192.168.10.14', address_type='ipv4')
		firstId, exists = results.addObject('Node', hostname='myhost', domain='cmsconstruct.com', description='Something clever')
		results.addLink(firstId, secondId)
		print("results: {}".format(str(results.data)))

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		print('Exception in Main: {}'.format(stacktrace))

	## end main
	return


if __name__ == "__main__":
	sys.exit(main())
