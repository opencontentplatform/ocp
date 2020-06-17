"""System elements.

Objects in this structure are strongly tied to the Node/OS instance.

Classes defined are part of 'data' schema (indentation represents inheritance)::

	BaseObjects - base_objects
		SystemElement - system_element
			|  SoftwarePackage - software_package
			|  OsStartTask - os_start_task
			|  LogicalVolume - logical_volume
			|  VolumeGroup - volume_group
			|  VirtualImage - virtual_image
			|  VirtualMachine - virtual_machine
			|  VirtualDisk - virtual_disk
			|  MappedDrive - mapped_drive
			|  FileSystem - file_system

"""
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Float
from sqlalchemy.types import Boolean, CHAR, JSON
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from sqlalchemy import and_, or_
from sqlalchemy import UniqueConstraint
from sqlalchemy import event
# Base = declarative_base()
from database.schema.baseSchema import BaseObject
from database.schema.node import Node


class SystemElement(BaseObject):
	"""Defines the system_element object for the database

	Table :
	  |  system_element
	Columns :
	  |  object_id [CHAR(32)] FK(base_object.object_id) PK
	"""

	__tablename__ = 'system_element'
	__table_args__ = {'schema':'data'}
	object_id = Column(None, ForeignKey(BaseObject.object_id), primary_key=True)
	# container = Column(CHAR(32),ForeignKey(Node.object_id), nullable=False)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'system_element', 'inherit_condition': object_id == BaseObject.object_id}


class SoftwarePackage(SystemElement):
	"""Defines the software_package object for the database

	Table :
	  |  software_package
	Columns :
	  |  name [String(256)]
	  |  object_id FK(system_element.object_id) PK
	  |  container FK(node.object_id)
	Constraints :
	  |  software_package_constraint('name', 'container', 'version', 'path')
	"""

	__tablename__ = 'software_package'
	_constraints = ['name', 'container', 'version', 'path']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'software_package_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(SystemElement.object_id), primary_key=True)
	name = Column(String(256), nullable=False)
	version = Column(String(256), nullable=True)
	identifier = Column(String(256), nullable=True)
	title = Column(String(512), nullable=True)
	associated_date = Column(String(256), nullable=True)
	recorded_by = Column(String(256), nullable=True)
	path = Column(String(512), nullable=True)
	company = Column(String(256), nullable=True)
	owner = Column(String(256), nullable=True)
	vendor = Column(String(256), nullable=True)
	#Fields to be decided
	container_relationship = relationship('Node', backref = backref('software_package_objects', cascade = 'all, delete'), foreign_keys = 'SoftwarePackage.container')
	container = Column(CHAR(32), ForeignKey(Node.object_id), nullable=False)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'software_package', 'inherit_condition': object_id == SystemElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(SoftwarePackage.container == kwargs['container'], SoftwarePackage.name == kwargs['name']))


class OsStartTask(SystemElement):
	"""Defines the os_start_task object for the database

	Table :
	  |  os_start_task
	Columns :
	  |  object_id FK(system_element.object_id) PK
	  |  container FK(node.object_id)
	  |  name [String(256)]
	  |  path [String(512)]
	  |  process_id [Integer]
	  |  process_name [String(512)]
	  |  start_mode [String(64)]
	  |  title [String(256)]
	  |  type [String(64)]
	Constraints :
	  |  os_start_task_constraint('container', 'name')
	"""

	__tablename__ = 'os_start_task'
	_constraints = ['name', 'container']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'os_start_task_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(SystemElement.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	name = Column(String(256), nullable=False)
	path = Column(String(512), nullable=True)
	process_id = Column(Integer, nullable=True)
	process_name = Column(String(512), nullable=True)
	command_line = Column(String(512), nullable=True)
	start_mode = Column(String(64), nullable=True)
	start_type = Column(String(64), nullable=True)
	environment = Column(String(512), nullable=True)
	user = Column(String(64),nullable=True)
	display_name = Column(String(256), nullable=True)
	state = Column(String(64), nullable=True)
	container_relationship = relationship('Node', backref = backref('os_start_task_objects', cascade = 'all, delete'), foreign_keys = 'OsStartTask.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'os_start_task', 'inherit_condition': object_id == SystemElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(OsStartTask.container == kwargs['container'], OsStartTask.name == kwargs['name']))


class LogicalVolume(SystemElement):
	"""Defines the logical_volume object for the database

	Table :
	  |  logical_volume
	Columns :
	  |  object_id FK(system_element.object_id) PK
	  |  container FK(node.object_id)
	  |  name [String(256)]
	  |
	Constraints :
	  |  logical_volume_constraint('name', 'container')
	"""

	__tablename__ = 'logical_volume'
	_constraints = ['container', 'name']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'logical_volume_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(SystemElement.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	name = Column(String(256), nullable=False)
	#Fields to be decided
	container_relationship = relationship('Node', backref = backref('logical_volume_objects', cascade = 'all, delete'), foreign_keys = 'LogicalVolume.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'logical_volume', 'inherit_condition': object_id == SystemElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(LogicalVolume.container == kwargs['container'], LogicalVolume.name == kwargs['name']))


class VolumeGroup(SystemElement):
	"""Defines the volume_group object for the database.

	Table :
	  |  volume_group
	Columns :
	  |  object_id FK(system_element.object_id) PK
	  |  container FK(node.object_id)
	  |  name [String(256)]
	Constraints :
	  |  volume_group_constraint('name', 'container')
	"""

	__tablename__ = 'volume_group'
	_constraints = ['container', 'name']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'volume_group_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(SystemElement.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	name = Column(String(256), nullable=False)
	#Fields to be decided
	container_relationship = relationship('Node', backref = backref('volume_group_objects', cascade = 'all, delete'), foreign_keys = 'VolumeGroup.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'volume_group', 'inherit_condition': object_id == SystemElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(VolumeGroup.container == kwargs['container'], VolumeGroup.name == kwargs['name']))


class MappedDrive(SystemElement):
	"""Defines the mapped_drive object for the database

	Table :
	  |  mapped_drive
	Columns :
	  |  object_id FK(system_element.object_id) PK
	  |  container FK(node.object_id)
	  |  name [String(256)]
	Constraints :
	  |  mapped_drive_constraint('name', 'container')
	"""

	__tablename__ = 'mapped_drive'
	_constraints = ['container', 'name']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'mapped_drive_objects'), {'schema':'data'})
	object_id = Column(None, ForeignKey(SystemElement.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	name = Column(String(256), nullable=False)
	#Fields to be decided
	container_relationship = relationship('Node', backref = backref('mapped_drive_objects', cascade = 'all, delete'), foreign_keys = 'MappedDrive.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'mapped_drive', 'inherit_condition': object_id == SystemElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(MappedDrive.container == kwargs['container'], MappedDrive.name == kwargs['name']))


class FileSystem(SystemElement):
	"""Defines the file_system object for the database

	Table :
	  |  file_system
	Columns :
	  |  object_id FK(system_element.object_id) PK
	  |  container FK(node.object_id)
	  |  name [String(256)]
	Constraints :
	  |  file_system_constraint('name', 'container')
	"""

	__tablename__ = 'file_system'
	_constraints = ['container', 'name']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'file_system_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(SystemElement.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	name = Column(String(256), nullable=False)
	#Fields to be decided
	container_relationship = relationship('Node', backref = backref('file_system_objects', cascade = 'all, delete'), foreign_keys = 'FileSystem.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'file_system', 'inherit_condition': object_id == SystemElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(FileSystem.container == kwargs['container'], FileSystem.name == kwargs['name']))


class VirtualMachine(SystemElement):
	"""Defines the virtual_machine object for the database

	Table :
	  |  virtual_machine
	Columns :
	  |  object_id FK(system_element.object_id) PK
	  |  container FK(node.object_id)
	  |  vendor [String(256)]
	Constraints :
	  |  virtual_machine_constraint('vendor', 'container')
	"""

	__tablename__ = 'virtual_machine'
	_constraints = ['container', 'vendor']
	_captionRule = {"condition": [ "vendor" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'virtual_machine_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(SystemElement.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	vendor = Column(String(256), nullable=False)
	#Fields to be decided
	container_relationship = relationship('Node', backref = backref('virtual_machine_objects', cascade = 'all, delete'), foreign_keys = 'VirtualMachine.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'virtual_machine', 'inherit_condition': object_id == SystemElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(VirtualMachine.container == kwargs['container'], VirtualMachine.vendor == kwargs['vendor']))


class VirtualImage(SystemElement):
	"""Defines the virtual_image object for the database

	Table :
	  |  virtual_image
	Columns :
	  |  object_id FK(system_element.object_id) PK
	  |  container FK(node.object_id)
	  |  vendor [String(256)]
	Constraints :
	  |  virtual_image_constraint('vendor', 'container')
	"""

	__tablename__ = 'virtual_image'
	_constraints = ['container', 'vendor']
	_captionRule = {"condition": [ "vendor" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'virtual_image_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(SystemElement.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	vendor = Column(String(256), nullable=False)
	#Fields to be decided
	container_relationship = relationship('Node', backref = backref('virtual_image_objects', cascade = 'all, delete'), foreign_keys = 'VirtualImage.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'virtual_image', 'inherit_condition': object_id == SystemElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(VirtualImage.container == kwargs['container'], VirtualImage.vendor == kwargs['vendor']))


class VirtualDisk(SystemElement):
	"""Defines the virtual_disk object for the database

	Table :
	  |  virtual_disk
	COlumns :
	  |  object_id FK(system_element.object_id) PK
	  |  container FK(node.object_id)
	  |  name [String(256)]
	Constraints :
	  |  virtual_disk_constraint('name', 'container')
	"""

	__tablename__ = 'virtual_disk'
	_constraints = ['container', 'name']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'virtual_disk_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(SystemElement.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	name = Column(String(256), nullable=False)
	#Fields to be decided
	container_relationship = relationship('Node', backref = backref('virtual_disk_objects', cascade = 'all, delete'), foreign_keys = 'VirtualDisk.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'virtual_disk', 'inherit_condition': object_id == SystemElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(VirtualDisk.container == kwargs['container'], VirtualDisk.name == kwargs['name']))
