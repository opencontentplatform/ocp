"""Class for transforming objects/links into the UCMDB TopologyData structure."""
import json

class UcmdbTopologyData():
	"""Class for transforming objects/links into the UCMDB TopologyData structure."""
	def __init__(self, source='ITDM'):
		"""Constructor."""
		self.source = source
		self.jsonResult = {}
		self.jsonResult['cis'] = []
		self.jsonResult['relations'] = []
		self.objectId = 1

	def getObjectId(self):
		"""Auto increment a temporary identifier for object reference."""
		currentId = self.objectId
		self.objectId += 1
		return str(currentId)

	def addObject(self, className, uniqueId=None, **kargs):
		"""Adds an object into the results; return the ID of the new object.

		Arguments:
		  className (str) : BaseObject class name
		  uniqueId (str)  : String containing identifier
		  kargs (dict)    : Data on this object
		"""
		entry = {}
		entry['type'] = className
		if uniqueId is None:
			uniqueId = self.getObjectId()
		entry['ucmdbId'] = uniqueId
		properties = {}
		properties['description'] = self.source
		for name,value in kargs.items():
			properties[name] = value
		entry['properties'] = properties
		self.jsonResult['cis'].append(entry)
		return entry['ucmdbId']

	def addLink(self, className, firstId, secondId, properties={}):
		"""Adds a link entry into the results, by providing object ids.

		Arguments:
		  className (str) : Link class name
		  firstId (str)   : First object id
		  secondId (str)  : Second object id
		"""
		entry = {}
		entry['type'] = className
		entry['end1Id'] = firstId
		entry['end2Id'] = secondId
		uniqueId = self.getObjectId()
		entry['ucmdbId'] = uniqueId
		entry['properties'] = properties
		self.jsonResult['relations'].append(entry)

	def size(self):
		"""Return a count of the total objects, including links."""
		return (len(self.jsonResult.get('cis', [])) +
				len(self.jsonResult.get('relations', [])))

	def stringify(self):
		"""Return the result as a JSON encoded string."""
		return json.dumps(self.jsonResult)

	def reset(self):
		"""Empty and reinitialize the result set."""
		self.jsonResult['relations'] = None
		self.jsonResult['cis'] = None
		self.jsonResult = None
		self.jsonResult = {}
		self.jsonResult['cis'] = []
		self.jsonResult['relations'] = []
		self.objectId = 1
