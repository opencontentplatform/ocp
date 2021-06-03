"""Link objects.

These links maintain relationships via association tables.

Classes defined are part of 'data' schema (indentation represents inheritance)::

	BaseLink - base_link
		|  StrongLink - strong_link
			|  Enclosed - enclosed
		|  WeakLink - weak_link
			|  Usage - usage
			|  ServerClient - server_client
			|  Route - route
			|  Redirect - redirect
			|  Manage - manage
			|  Contain - contain

"""
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Float
from sqlalchemy.types import Boolean, CHAR, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy import and_, or_
from sqlalchemy import event
from sqlalchemy import UniqueConstraint
from database.schema.baseSchema import Base, BaseObject, UniqueMixin

## Weak Link Example
## If there Link B/T Node and IpAddress which don't have any FK relationship
## B/T them then Node is the First_object and Ipaddress is the Second object
## in the weak_link table, the weak_second_objects of Node will contain
## collection of IpAddress objects linked to Node in weak_link table.
## the weak_first_objects of IpAddress will contains collection of Node
## objects linked to IpAddress in weak_link table.

## Strong Link Example
## If there Link B/T IpAddress and NameRecord(FK IpAddress) whith a FK
## relationship B/T them, then IpAddress is the First_object and NameRecord
## is the Second_object in the strong_link table, the strong_second_objects
## of IpAdress  will contain collection of NameRecord objects linked to
## IpAddress via FK and in strong_link table. The strong_first_objects will
## The IPAdress object that NameRecord have FK relationships with.

## Note: these are used in BaseLink below, but declared in BaseObject:
##  weak_first_object
##  weak_second_object
##  strong_first_object
##  strong_second_object

## Moving from SqlAlchemy v1.3 to 1.4, there is a new validation check when
## two or more relationships can write data to the same columns. This caused
## warnings from BaseLink and BaseClass, where we have inheritance in links
## and objects - creating many-to-many update scenarios. Sample warnings:
## ===========================================================================
## SAWarning: relationship 'BaseLink.orl1' will copy column base_object.object_id
## to column base_link.first_id, which conflicts with relationship(s):
##   'WeakLink.weak_first_object'       (copies base_object.object_id to base_link.first_id),
##   'BaseObject.weak_second_objects'   (copies base_object.object_id to base_link.first_id),
##   'StrongLink.strong_first_object'   (copies base_object.object_id to base_link.first_id),
##   'BaseObject.strong_second_objects' (copies base_object.object_id to base_link.first_id).
## ===========================================================================
## SAWarning: relationship 'BaseLink.orl2' will copy column base_object.object_id
## to column base_link.second_id, which conflicts with relationship(s):
##   'WeakLink.weak_second_object'     (copies base_object.object_id to base_link.second_id),
##   'BaseObject.weak_first_objects'   (copies base_object.object_id to base_link.second_id),
##   'StrongLink.strong_second_object' (copies base_object.object_id to base_link.second_id),
##   'BaseObject.strong_first_objects' (copies base_object.object_id to base_link.second_id).
## ===========================================================================
## Background on the error:
##   https://docs.sqlalchemy.org/en/14/errors.html#relationship-x-will-copy-column-q-to-column-p-which-conflicts-with-relationship-s-y
## Currently implementing a work around suggested on the sqlAlchemy newsgroup:
##   https://groups.google.com/g/sqlalchemy/c/-91BeaTqzh4
## Via these lines in BaseLink, to use backwards compatibility with "overlaps":
## 	#orl1 = relationship('BaseObject', foreign_keys=first_id)
##  #orl2 = relationship('BaseObject', foreign_keys=second_id)
##  orl1 = relationship('BaseObject', overlaps='weak_first_object, strong_first_object, weak_second_objects, strong_second_objects', foreign_keys=first_id)
##  orl2 = relationship('BaseObject', overlaps='weak_second_object, strong_second_object, weak_first_objects, strong_first_objects', foreign_keys=second_id)
## In the future we may consider dropping inheritance in the links, to move
## towards independent and not-inherited many-to-many Link classes. Leaving 
## this detailed message in the header for later review.


class BaseLink(UniqueMixin, Base):
	"""Creates the base_link object in the database
	Table :
	  |  base_link
	Columns :
	  |  first_id FK(base_object.object_id)
	  |  second_id FK(base_object.object_id)
	Constraints :
	  |  base_link_constraint(first_id, second_id)
	"""

	__tablename__ = 'base_link'
	_constraints = ['first_id', 'second_id']
	__table_args__ = (UniqueConstraint(*_constraints, name = 'base_link_constraint'), {"schema":"data"})
	object_id = Column(CHAR(32), primary_key=True)
	object_type = Column(String(16))
	first_id = Column(CHAR(32), ForeignKey(BaseObject.object_id))
	second_id = Column(CHAR(32), ForeignKey(BaseObject.object_id))
	# orl1 = relationship('BaseObject', foreign_keys=first_id)
	# orl2 = relationship('BaseObject', foreign_keys=second_id)
	orl1 = relationship('BaseObject', overlaps='weak_first_object, strong_first_object, weak_second_objects, strong_second_objects', foreign_keys=first_id)
	orl2 = relationship('BaseObject', overlaps='weak_second_object, strong_second_object, weak_first_objects, strong_first_objects', foreign_keys=second_id)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'base_link', 'polymorphic_on':object_type}

	@classmethod
	def unique_hash(cls, object_id, first_id, second_id, object_type):
		return object_id

	@classmethod
	def unique_filter(cls, query, object_id, first_id, second_id, object_type):
		return query.filter(and_(BaseLink.first_id==first_id, BaseLink.second_id==second_id))


class StrongLink(BaseLink):
	"""
	One to Many relationship and link table between base objects
	"""

	__tablename__ = 'strong_link'
	__table_args__ = {"schema":"data"}
	object_id = Column(CHAR(32), ForeignKey(BaseLink.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'strong_link', 'inherit_condition': object_id == BaseLink.object_id}


class Enclosed(StrongLink):
	"""
	One to Many relationship and link table between base objects
	"""

	__tablename__ = 'enclosed'
	__table_args__ = {"schema":"data"}
	object_id = Column(CHAR(32), ForeignKey(StrongLink.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'enclosed', 'inherit_condition': object_id == StrongLink.object_id}


class WeakLink(BaseLink):
	"""
	Many to Many relationship and link table between base objects
	"""

	__tablename__ = 'weak_link'
	__table_args__ = {"schema":"data"}
	object_id = Column(CHAR(32), ForeignKey(BaseLink.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'weak_link', 'inherit_condition': object_id == BaseLink.object_id}


class Usage(WeakLink):
	"""
	Many to Many relationship and link table between base objects
	"""

	__tablename__ = 'usage'
	__table_args__ = {"schema":"data"}
	object_id = Column(CHAR(32), ForeignKey(WeakLink.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'usage', 'inherit_condition': object_id == WeakLink.object_id}


class ServerClient(WeakLink):
	"""
	Many to Many relationship and link table between base objects
	"""

	__tablename__ = 'server_client'
	__table_args__ = {"schema":"data"}
	object_id = Column(CHAR(32), ForeignKey(WeakLink.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'server_client', 'inherit_condition': object_id == WeakLink.object_id}


class Route(WeakLink):
	"""
	Many to Many relationship and link table between base objects
	"""

	__tablename__ = 'route'
	__table_args__ = {"schema":"data"}
	object_id = Column(CHAR(32), ForeignKey(WeakLink.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'route', 'inherit_condition': object_id == WeakLink.object_id}


class Contain(WeakLink):
	"""
	Many to Many relationship and link table between base objects
	"""

	__tablename__ = 'contain'
	__table_args__ = {"schema":"data"}
	object_id = Column(CHAR(32), ForeignKey(WeakLink.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'contain', 'inherit_condition': object_id == WeakLink.object_id}


class Redirect(WeakLink):
	"""
	Many to Many relationship and link table between base objects
	"""

	__tablename__ = 'redirect'
	__table_args__ = {"schema":"data"}
	object_id = Column(CHAR(32), ForeignKey(WeakLink.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'redirect', 'inherit_condition': object_id == WeakLink.object_id}


class Manage(WeakLink):
	"""
	Many to Many relationship and link table between base objects
	"""

	__tablename__ = 'manage'
	__table_args__ = {"schema":"data"}
	object_id = Column(CHAR(32), ForeignKey(WeakLink.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'manage', 'inherit_condition': object_id == WeakLink.object_id}
