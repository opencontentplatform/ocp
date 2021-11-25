"""Miscelaneous objects for the data schema.

Classes:
  *  ReferenceCache - reference_cache

"""
from sqlalchemy import Column, ForeignKey, DateTime
from sqlalchemy.types import CHAR
#from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from database.schema.baseSchema import Base
from database.schema.baseSchema import  BaseObject

class ReferenceCache(Base):
	"""Defines a reference_cache object for the database.

	This is intended for inheritance hierarchy which holds the weak
	and strong object connection via reference_id.

	Table :
	  |  reference_cache
	Column :
	  |  object_id [CHAR(32)] FK(base_object.object_id) PK
	  |  reference_id [CHAR(32)] FK(base_object.reference_id)
	"""
	__table_args__ = {'schema' : 'data'}
	__tablename__ = 'reference_cache'
	## Cascade is taken care at the database level, since there is no hierarchy.
	object_id = Column(CHAR(32), ForeignKey(BaseObject.object_id, ondelete='CASCADE'), primary_key=True)
	reference_id = Column(CHAR(32), ForeignKey(BaseObject.object_id, ondelete='CASCADE'), nullable = False)
	time_created = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
	## To enable deletion to work at the orm level
	## (Avoiding this inorder to do the delete at the database level)
	## container_relationship = relationship('BaseObject', foreign_keys='ReferenceCache.object_id', backref = backref('reference_cache_weak', cascade='all, delete'), cascade_backrefs=False)
	## reference_relationship = relationship('BaseObject', foreign_keys='ReferenceCache.reference_id', backref = backref('reference_cache_strong', cascade='all, delete'), cascade_backrefs=False)
