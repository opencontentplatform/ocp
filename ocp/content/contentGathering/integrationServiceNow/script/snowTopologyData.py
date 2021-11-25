"""Class for transforming objects/links into the ServiceNow JSON structure."""
import json

class SnowTopologyData():
	"""Class for transforming objects/links into the ServiceNow JSON structure."""
	def __init__(self, source='ITDM'):
		"""Constructor."""
		self.source = source
		self.jsonResult = {}
		self.jsonResult['items'] = []
		self.jsonResult['relations'] = []
		self.objectId = 0


	def getThisEntryPosition(self):
		"""Auto increment a temporary identifier for object reference."""
		currentId = self.objectId
		self.objectId += 1
		return currentId


	def addObject(self, className, uniqueId=None, **kargs):
		"""Adds an object into the results; return the ID of the new object.

		Arguments:
		  className (str) : BaseObject class name
		  uniqueId (str)  : String containing identifier
		  kargs (dict)    : Data on this object
		"""
		entry = {}
		entry['className'] = className
		properties = {}
		if uniqueId is not None:
			properties['sys_id'] = uniqueId
		for name,value in kargs.items():
			properties[name] = value
		entry['values'] = properties
		self.jsonResult['items'].append(entry)

		## In ServiceNow, the numerical position of the object in the submitted
		## list, is not shown in the object section, but is used for linking.
		entryPosition = self.getThisEntryPosition()
		return entryPosition


	def addLink(self, className, firstId, secondId, properties={}):
		"""Adds a link entry into the results, by providing object ids.

		Arguments:
		  className (str) : Link class name
		  firstId (str)   : First object id
		  secondId (str)  : Second object id
		"""
		entry = {}
		entry['type'] = className
		entry['parent'] = firstId
		entry['child'] = secondId
		self.jsonResult['relations'].append(entry)


	def size(self):
		"""Return a count of the total objects, including links."""
		return (len(self.jsonResult.get('items', [])) +
				len(self.jsonResult.get('relations', [])))

	def finalize(self):
		"""Remove the relationships if there are none."""
		if len(self.jsonResult['relations']) <= 0:
			self.jsonResult.pop('relations')

	def stringify(self):
		"""Return the result as a JSON encoded string."""
		return json.dumps(self.jsonResult)

	def reset(self):
		"""Empty and reinitialize the result set."""
		self.jsonResult['relations'] = None
		self.jsonResult['items'] = None
		self.jsonResult = None
		self.jsonResult = {}
		self.jsonResult['items'] = []
		self.jsonResult['relations'] = []
		self.objectId = 0
