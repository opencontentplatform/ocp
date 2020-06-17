"""Software components.

Software components are 'shared by' or 'represented across' multiple instances.
For example, a Database represented here may have multiple instances connected
to it.

This may later be folded under the 'Group element' category, which at the time
of creating this - was only intended for cluster representation. The logical
difference between the two categories is very small and so will probably not
cause many null/unused attributes if merged (which was the reason for leaving
them separate at the start).

Classes defined are part of 'data' schema (indentation represents inheritance)::

	BaseObjects - base_objects
		SoftwareComponent - software_component
			|  VirtualComponent - virtual_component
			|  WebComponent - web_component
			|  DatabaseComponent - database_component
			|  AppComponent - application_component

"""
from sqlalchemy import Column, ForeignKey, String
from database.schema.baseSchema import BaseObject


class SoftwareComponent(BaseObject):
	"""Defines the software_component object for the database

	Table :
	  |  software_component
	Columns :
	  |  object_id FK(base_object.object_id) PK
	"""
	__tablename__ = 'software_component'
	_constraints = ['name']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = {'schema': 'data'}
	object_id = Column(None, ForeignKey(BaseObject.object_id), primary_key=True)
	name = Column(String(256), nullable=False)
	component_type = Column(String(256), nullable=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'software_component', 'inherit_condition': object_id == BaseObject.object_id}


class VirtualComponent(SoftwareComponent):
	"""Defines the virtual_component object for the database

	Table :
	  |  virtual_component
	Columns :
	  |  object_id FK(software_component.object_id) PK
	"""
	__tablename__ = 'virtual_component'
	__table_args__ = {'schema':'data'}
	object_id = Column(None, ForeignKey(SoftwareComponent.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'virtual_component', 'inherit_condition': object_id == SoftwareComponent.object_id}


class WebComponent(SoftwareComponent):
	"""Defines the web_component object for the database

	Table :
	  |  web_component
	Columns :
	  |  object_id FK(software_component.object_id) PK
	"""
	__tablename__ = 'web_component'
	__table_args__ = {'schema':'data'}
	object_id = Column(None, ForeignKey(SoftwareComponent.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'web_component', 'inherit_condition': object_id == SoftwareComponent.object_id}


class DatabaseComponent(SoftwareComponent):
	"""Defines the database_component object for the database

	Table :
	  |  database_component
	Columns :
	  |  object_id FK(software_component.object_id) PK
	"""
	__tablename__ = 'database_component'
	__table_args__ = {'schema':'data'}
	object_id = Column(None, ForeignKey(SoftwareComponent.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'database_component', 'inherit_condition': object_id == SoftwareComponent.object_id}


class AppComponent(SoftwareComponent):
	"""Defines the app_component object for the database

	Table :
	  |  app_component
	Columns :
	  |  object_id FK(software_component.object_id) PK
	"""
	__tablename__ = 'app_component'
	__table_args__ = {'schema':'data'}
	object_id = Column(None, ForeignKey(SoftwareComponent.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'app_component', 'inherit_condition': object_id == SoftwareComponent.object_id}
