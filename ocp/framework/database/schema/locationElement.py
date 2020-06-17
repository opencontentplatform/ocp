"""Location Elements.

  :LocationSite: - a datacenter, building, store, or complex
  :LocationContext: - details about the site (phone, timezone, hours, etc)
  :LocationMacro: - an external mailing address and geo-coordinates
  :LocationMicro: - an internal pole or grid location

Nodes are connected to hardware, and then hardware to the LocationMicro. If a
site does not have internal grid or pole locations (for LocationMicro objects),
then you can alternatively tie hardware directly to the LocationSite.

Classes defined are part of 'data' schema (indentation represents inheritance)::

	BaseObjects - base_objects
		LocationElement - location_element
			|  LocationSite - location_site
			|  LocationMacro - location_macro
			|  LocationMicro - location_micro
			|  LocationContext - location_context


	Recommended links and topology follows:
	LocationSite
		| -- enclosure --> LocationContext
		| -- enclosure --> LocationMacro
		| -- enclosure --> LocationMicro
	Node
		| -- usage --> Hardware
	LocationMicro/LocationSite
		| -- contain --> Hardware

	Graphically it would look like the following:
	                LocationSite
	                /     |     \
	            Micro   Macro   Context
	  Node      /
	     \     /
	    Hardware

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Mar 7, 2018

"""
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Float
from sqlalchemy.types import Boolean, CHAR, JSON
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from sqlalchemy import and_, or_
from sqlalchemy import UniqueConstraint
from sqlalchemy import event
from database.schema.baseSchema import BaseObject

class LocationElement(BaseObject):
	"""Defines the location_element object in the database, an abstract object.

	Table :
	  |  location_element
	Column :
	  |  object_id [CHAR(32)] FK(base_object.object_id) PK
	"""

	__tablename__ = 'location_element'
	__table_args__ = {'schema':'data'}
	object_id = Column(None, ForeignKey(BaseObject.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'location_element', 'inherit_condition' : object_id == BaseObject.object_id}


class LocationSite(LocationElement):
	"""Top level Location object.

	An instance of this category represents the high level object, regardless of
	the type of location (store, corporate office, datacenter, warehouse, etc).
	You will have a one to one mapping of LocationSite to AddressMacro, so when
	there are multiple buildings on a single campus - represent this with each
	externally addressable building having its own LocationSite instance.

	Table :
	  |  location_site
	Columns :
	  |  object_id [CHAR(32)] FK(location_element.object_id) PK
	  |  name [String(128)]
	  |  location_type [String(64)]
	Constraints :
	  |  location_site_constraint(name, location_type)
	"""

	__tablename__ = 'location_site'
	_constraints = ['name', 'location_type']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name='location_site_constraint'), {"schema":"data"})
	object_id = Column(CHAR(32), ForeignKey(LocationElement.object_id), primary_key=True)
	name = Column(String(128), nullable=False)
	location_type = Column(String(64), nullable=False)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'location_site', 'inherit_condition': object_id == LocationElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(LocationSite.name == kwargs['name'])


class LocationMacro(LocationElement):
	"""An externally addressable component of a Location.

	This holds the mailing address and geo-coordinates of a building.

	Table :
	  |  location_macro
	Columns :
	  |  object_id [CHAR(32)] FK(location_element.object_id) PK
	  |  address_line_1 [String(256)]
	  |  address_line_2 [String(256)]
	  |  address_line_3 [String(256)]
	  |  address_city [String(256)]
	  |  address_state [String(64)]
	  |  address_zip_code [String(16)]
	  |  address_country [String(64)]
	  |  address_region [String(64)]
	  |  latitude [String(16)]
	  |  longitude [String(16)]
	Constraints :
	  |  location_site_constraint(address_line_1, container)
	"""

	__tablename__ = 'location_macro'
	_constraints = ['address_line_1', 'container']
	_captionRule = {"condition": [ "address_line_1" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name='location_macro_constraint'), {"schema":"data"})
	object_id = Column(CHAR(32), ForeignKey(LocationElement.object_id), primary_key=True)
	container =  Column(None, ForeignKey(LocationSite.object_id), nullable = False)
	address_line_1 = Column(String(256), nullable=False)
	address_line_2 = Column(String(256), nullable=True)
	address_line_3 = Column(String(256), nullable=True)
	address_city = Column(String(256), nullable=True)
	address_state = Column(String(64), nullable=True)
	address_zip_code = Column(String(16), nullable=True)
	address_country = Column(String(64), nullable=True)
	address_region = Column(String(64), nullable=True)
	latitude = Column(String(16), nullable=True)
	longitude = Column(String(16), nullable=True)
	container_relationship = relationship('LocationSite',  backref = backref('location_macro_objects', cascade='all, delete'), foreign_keys='LocationMacro.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'location_macro', 'inherit_condition': object_id == LocationElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(LocationMacro.address_line_1 == kwargs['address_line_1'])


class LocationMicro(LocationElement):
	"""An internally addressable component of a Location.

	This holds the pole/grid/routing coordinates within a specific building.

	Table :
	  |  location_micro
	Columns :
	  |  object_id [CHAR(32)] FK(location_element.object_id) PK
	  |  address_coordinate [String(64)]
	  |  address_floor [String(64)]
	  |  address_room [String(64)]
	Constraints :
	  |  location_site_constraint(address_coordinate, container)
	"""

	__tablename__ = 'location_micro'
	_constraints = ['address_coordinate', 'container']
	_captionRule = {"condition": [ "address_coordinate" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name='location_micro_constraint'), {"schema":"data"})
	object_id = Column(CHAR(32), ForeignKey(LocationElement.object_id), primary_key=True)
	container =  Column(None, ForeignKey(LocationSite.object_id), nullable = False)
	address_coordinate = Column(String(64), nullable=False)
	address_floor = Column(String(64), nullable=True)
	address_room = Column(String(64), nullable=True)
	container_relationship = relationship('LocationSite',  backref = backref('location_micro_objects', cascade='all, delete'), foreign_keys='LocationMicro.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'location_micro', 'inherit_condition': object_id == LocationElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(LocationMicro.address_coordinate == kwargs['address_coordinate'])


class LocationContext(LocationElement):
	"""An internally addressable component of a Location.

	This holds internal .

	Table :
	  |  location_context
	Columns :
	  |  object_id [CHAR(32)] FK(location_element.object_id) PK
	  |  address_coordinate [String(64)]
	  |  address_floor [String(64)]
	  |  address_room [String(64)]
	Constraints :
	  |  location_site_constraint(address_coordinate, container)
	"""

	__tablename__ = 'location_context'
	_constraints = ['container']
	__table_args__ = (UniqueConstraint(*_constraints, name='location_context_constraint'), {"schema":"data"})
	#__table_args__ = ({"schema":"data"})
	object_id = Column(CHAR(32), ForeignKey(LocationElement.object_id), primary_key=True)
	container =  Column(None, ForeignKey(LocationSite.object_id), nullable = False)
	location_phone = Column(String(32), nullable=True)
	location_time_zone = Column(String(64), nullable=True)
	start_time_monday = Column(String(32), nullable=True)
	start_time_tuesday = Column(String(32), nullable=True)
	start_time_wednesday = Column(String(32), nullable=True)
	start_time_thursday = Column(String(32), nullable=True)
	start_time_friday = Column(String(32), nullable=True)
	start_time_saturday = Column(String(32), nullable=True)
	start_time_sunday = Column(String(32), nullable=True)
	stop_time_monday = Column(String(32), nullable=True)
	stop_time_tuesday = Column(String(32), nullable=True)
	stop_time_wednesday = Column(String(32), nullable=True)
	stop_time_thursday = Column(String(32), nullable=True)
	stop_time_friday = Column(String(32), nullable=True)
	stop_time_saturday = Column(String(32), nullable=True)
	stop_time_sunday = Column(String(32), nullable=True)
	container_relationship = relationship('LocationSite',  backref = backref('location_context_objects', cascade='all, delete'), foreign_keys='LocationContext.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'location_context', 'inherit_condition': object_id == LocationElement.object_id}
