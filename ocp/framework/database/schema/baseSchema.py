"""Base Object in the data schema.

The object model leverages SqlAlchemy (https://www.sqlalchemy.org/).

"""
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Float
from sqlalchemy.types import Boolean, CHAR, JSON
from sqlalchemy.orm import relationship, noload
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy import and_, or_
from sqlalchemy import UniqueConstraint
from sqlalchemy import event
from sqlalchemy import inspect
from functools import reduce
import uuid
Base = declarative_base()
from sqlalchemy import inspect as sqlalchemy_inspect


#############################################################################
## This section is from a sqlalchemy recipy to get_or_create a unique object:
##   https://bitbucket.org/zzzeek/sqlalchemy/wiki/UsageRecipes/UniqueObject
#############################################################################
def _unique(session, cls, hashfunc, queryfunc, constructor, arg, kw):
	"""Thanks to Michael Bayer (zzzeek) for sharing this method."""

	with session.no_autoflush:
		lst = cls.__mapper__.relationships.keys()
		if 'weak_first_objects' in lst and 'weak_second_objects' in lst:
			q = session.query(cls).options([noload('weak_first_objects'), noload('weak_second_objects')])
		else:
			q = session.query(cls)
		q = queryfunc(q, *arg, **kw)
		obj = q.first()
		## UPDATE Just to update the additional fields, which will happen
		## just by calling the function as_unique.
		if obj and len(q.all()) == 1:
			var = obj.object_id
			n_obj = constructor(*arg, **kw)
			n_obj.object_id = var
			n_obj = session.merge(n_obj)
			#cache[key] = n_obj
			return n_obj
		###INSERT
		if not obj:
			# cls(*arg, **kw, **dict((attr.key, None) for attr in sqlalchemy_inspect(cls).attrs if not attr.uselist and attr.key not in **kw)))
			if 'object_updated_by' in kw.keys():
				kw['object_created_by'] = kw['object_updated_by']
			# raise("error",kw)
			obj = constructor(*arg, **kw)
			session.add(obj)
			#cache[key] = obj
			return obj

	return obj


class UniqueMixin(object):
	"""Used to get_or_create objects to avoid sql exceptions on inserts."""

	@classmethod
	def unique_hash(cls, *arg, **kw):
		raise NotImplementedError()

	@classmethod
	def unique_filter(cls, query, *arg, **kw):
		raise NotImplementedError()

	@classmethod
	def as_unique(cls, session, *arg, **kw):
		return _unique(session, cls, cls.unique_hash, cls.unique_filter, cls, arg, kw)


class BaseObject(UniqueMixin, Base):
	"""Mixin containing set of standard attributes used by all classes"""

	__tablename__ = 'base_object'
	_constraints = ['object_id']
	_captionRule = None
	# _captionRule = {
	# 	"expression": {
	# 		"operator": "and",
	# 		"entries": [
	# 			{ "condition": [ "hostname" ] },
	# 			{ "expression": {
	# 				"operator": "or",
	# 				"entries": [
	# 					{ "condition": [" (", "domain", ")"] },
	# 					{ "condition": [" {", "__tablename__", ":", "version", "}"] }
	# 				]}
	# 			},
	# 			{ "condition": [ "!" ] }
	# 		]
	# 	}
	# }
	__table_args__ = {"schema":"data"}
	object_id = Column(CHAR(32), primary_key=True, default=lambda :uuid.uuid4().hex)
	reference_id = Column(None, ForeignKey('data.base_object.object_id'), nullable=True)
	object_type = Column(String(64))
	time_created = Column(DateTime(timezone=True), server_default=func.now())
	time_updated = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
	time_gathered = Column(DateTime(timezone=True), nullable=True)
	object_created_by = Column(String(128), nullable=True)
	object_updated_by = Column(String(128), nullable=True)
	description  = Column(String(1024))
	caption = Column(String(512), nullable=True)
	base_object_children = relationship('BaseObject', cascade='all, delete', cascade_backrefs= False)
	weak_first_objects = relationship('WeakLink', backref='weak_second_object', cascade='all, delete', cascade_backrefs= False, primaryjoin= 'BaseObject.object_id == WeakLink.second_id')
	weak_second_objects = relationship('WeakLink', backref='weak_first_object', cascade='all, delete', cascade_backrefs= False, primaryjoin= 'BaseObject.object_id == WeakLink.first_id')
	strong_first_objects = relationship('StrongLink', backref='strong_second_object', cascade='all, delete', cascade_backrefs= False, primaryjoin= 'BaseObject.object_id == StrongLink.second_id')
	strong_second_objects = relationship('StrongLink', backref='strong_first_object', cascade='all, delete', cascade_backrefs= False, primaryjoin= 'BaseObject.object_id == StrongLink.first_id')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'base_object', 'polymorphic_on':object_type}


	@classmethod
	def captionRule(cls):
		return cls._captionRule

	@classmethod
	def constraints(cls):
		return cls._constraints

	@classmethod
	def unique_hash(cls,**kwargs):
		hashVal = reduce((lambda i,j: i+':==:'+j), [str(kwargs[i]) for i in cls.constraints()])
		return hashVal

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(BaseObject.object_id == kwargs['object_id'])


## Enable updates on middle container class types (NodeServer/NodeDevice/Node)
## and on the lowest level table types (Linux/AIX/HPUX/Solaris/Windows), to
## propagate up and change the BaseObject "time_update" attribute.
@event.listens_for(BaseObject, 'before_update', propagate=True)
def updateTimestampAndCaption(mapper, connect, target):
	target.time_updated = func.now()
	target.caption = setCaption(target)

@event.listens_for(BaseObject, 'before_insert', propagate=True)
def updateCaption(mapper, connect, target):
	target.caption = setCaption(target)

## Updates caption (aka display label) for a single shared attr across classes
def setCaption(objectInstance):
	rule = objectInstance.captionRule()
	if rule is None:
		## Set the caption to the name of the Python Class
		return(inspect(objectInstance).class_.__name__)
	else:
		## Set the caption according to the instance rule (based on attr values)
		return(getCaption(objectInstance, rule))

def getCaption(objectInstance, captionRule):
		tmpString = ''
		for key, value in captionRule.items():
			if key == 'expression':
				## Override operator if set (default to 'and')
				operator = value.get('operator', 'and')
				entries = value.get('entries', [])
				for expOrCond in entries:
					thisString = getCaption(objectInstance, expOrCond)
					if thisString is not None and len(thisString) > 0:
						if operator == 'or':
							return thisString
						elif operator == 'and':
							tmpString += thisString
						else:
							print('Invalid captionRule expression operator. Expected "and" or "or", but received: {}'.format(operator))
			elif key == 'condition':
				for name in value:
					attrValue = None
					if hasattr(objectInstance, str(name)):
						attrValue = getattr(objectInstance, str(name), None)
						## Entries in condition blocks are required, so abort if empty
						if attrValue is None or len(attrValue) <= 0:
							tmpString = ''
							break
						tmpString += attrValue
					else:
						tmpString += str(name)
			else:
				print('Invalid captionRule key. Expected "expression" or "condition", but received "{}"'.format(key))
			## Normalize empty strings to None
			if len(tmpString) <= 0:
				tmpString = None
			return tmpString
