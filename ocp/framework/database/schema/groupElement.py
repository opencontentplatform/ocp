"""Group Elements.

Group Elements are objects that stand on their own, without a "container". Think
of a Cluster of some technology type. Individual instances within that cluster
will each have their own execution environment (nodes/software/hardware); the
cluster is a grouping of those instances, abstracting the thing being clustered
away from the execution environment.

Classes defined are part of 'data' schema (indentation represents inheritance)::

	BaseObjects - base_objects
		GroupElement - group_element
			|  SoftwareAggregate - software_aggregate
			|  SoftwareSignature - software_signature
			|  Cluster - cluster
			|  ProcessSignature - process_signature
			|  LocationGroup - location_group
			|  EnvironmentGroup - environment_group
			|  SoftwareGroup - software_group

"""
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Float
from sqlalchemy.types import Boolean, CHAR, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import and_, or_
from sqlalchemy import UniqueConstraint
from sqlalchemy import event
from database.schema.baseSchema import BaseObject

class GroupElement(BaseObject):
	"""Defines the group_element object for the database

	Table :
	  |  group_element
	Columns :
	  |  object_id [CHAR(32)] FK(base_object.object_id) PK
	"""

	__tablename__ = 'group_element'
	__table_args__ = {'schema':'data'}
	object_id = Column(None, ForeignKey(BaseObject.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'group_element', 'inherit_condition' : object_id == BaseObject.object_id}


class SoftwareAggregate(GroupElement):
	"""Defines the software_aggregate object for the database

	Table :
	  |  software_aggregate
	Columns :
	  |  object_id [CHAR(32)] FK(group_element.object_id) PK
	  |  name [String(256)]
	  |  group_type [String(64)]
	  |  software_id [String(64)]
	Constraints :
	  | software_aggregate_constraint (name, group_type)
	"""

	__tablename__ = 'software_aggregate'
	_constraints = ['name', 'group_type']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'software_aggregate_constraint'), {'schema': 'data'})
	object_id = Column(None, ForeignKey(GroupElement.object_id), primary_key=True)
	name = Column(String(256), nullable = False)
	group_type = Column(String(64), nullable = True)
	software_id = Column(String(64), nullable = True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'software_aggregate', 'inherit_condition' : object_id == GroupElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(SoftwareAggregate.name == kwargs['name'], SoftwareAggregate.group_type == kwargs['group_type']))


class SoftwareSignature(GroupElement):
	"""Defines the software_signature object for the database

	Table :
	  |  software_signature
	Columns :
	  |  object_id [CHAR(32)] FK(group_element.object_id) PK
	  |  name [String(256)]
	  |  os_type [String(16)]
	  |  software_info [String(256)]
	  |  notes [String(512)]
	Constraints :
	  |  software_signature_constraint (name, os_type, software_info)
	"""

	__tablename__ = 'software_signature'
	_constraints = ['name', 'os_type', 'software_info']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'software_signature_constraint'), {'schema': 'data'})
	object_id = Column(None, ForeignKey(GroupElement.object_id), primary_key=True)
	name = Column(String(256), nullable = False)
	os_type = Column(String(16), nullable = False)
	software_info = Column(String(256), nullable = True)
	notes = Column(String(512), nullable= True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'software_signature', 'inherit_condition' : object_id == GroupElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(SoftwareSignature.name == kwargs['name'], SoftwareSignature.os_type == kwargs['os_type'], SoftwareSignature.software_info == kwargs['software_info']))


class Cluster(GroupElement):
	"""Defines the cluster object for the database

	Table :
	  |  cluster
	Columns :
	  |  object_id [CHAR(32)] FK(group_element.object_id) PK
	  |  name [String(256)]
	  |  group_type [String(64)]
	  |  cluster_id [String(64)]
	Constraints :
	  |  cluster_constraint (name, group_type)
	"""

	__tablename__ = 'cluster'
	_constraints = ['name', 'group_type']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'cluster_constraint'), {'schema': 'data'})
	object_id = Column(None, ForeignKey(GroupElement.object_id), primary_key=True)
	name = Column(String(256), nullable=False)
	group_type = Column(String(64), nullable=True)
	cluster_id = Column(String(64), nullable=False)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'cluster', 'inherit_condition' : object_id == GroupElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(Cluster.name == kwargs['name'], Cluster.group_type == kwargs['group_type']))


class ProcessSignature(GroupElement):
	"""Defines the process_signature object in the database

	Table :
	  |  process_signature
	Columns :
	  |  object_id [CHAR(32)] FK(group_element.object_id) PK
	  |  process_hierarchy [String(512)]
	  |  name [String(256)]
	Constraints :
	  |  process_signature_constraint(process_hierarchy, name)
	"""

	__tablename__ = 'process_signature'
	_constraints = ['process_hierarchy', 'name']
	_captionRule = {"condition": [ "process_hierarchy" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'process_signature_constraint'), {'schema': 'data'})
	object_id = Column(None, ForeignKey(GroupElement.object_id), primary_key=True)
	process_hierarchy = Column(String(512), nullable=True)
	name = Column(String(256), nullable=False)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'process_signature', 'inherit_condition' : object_id == GroupElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(ProcessSignature.name == kwargs['name'], ProcessSignature.process_hierarchy == kwargs['process_hierarchy']))


class LocationGroup(GroupElement):
	"""Defines the location_group object in the database

	Table :
	  |  location_group
	Columns :
	  |  object_id [CHAR(32)] FK(group_element.object_id) PK
	  |  name [String(256)]
	Constraints :
	  |  location_group_constraint(name)
	"""

	__tablename__ = 'location_group'
	_constraints = ['unique_name']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'location_group_constraint'), {'schema': 'data'})
	object_id = Column(None, ForeignKey(GroupElement.object_id), primary_key=True)
	name = Column(String(256), nullable=False)
	unique_name = Column(String(512), nullable=False)
	qualifier = Column(String(256), nullable=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'location_group', 'inherit_condition' : object_id == GroupElement.object_id}


class EnvironmentGroup(GroupElement):
	"""Defines the environment_group object in the database

	Table :
	  |  environment_group
	Columns :
	  |  object_id [CHAR(32)] FK(group_element.object_id) PK
	  |  name [String(256)]
	Constraints :
	  |  environment_group_constraint(name)
	"""

	__tablename__ = 'environment_group'
	_constraints = ['unique_name']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'environment_group_constraint'), {'schema': 'data'})
	object_id = Column(None, ForeignKey(GroupElement.object_id), primary_key=True)
	name = Column(String(256), nullable=False)
	unique_name = Column(String(512), nullable=False)
	qualifier = Column(String(256), nullable=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'environment_group', 'inherit_condition' : object_id == GroupElement.object_id}


class SoftwareGroup(GroupElement):
	"""Defines the software_group object in the database

	Table :
	  |  software_group
	Columns :
	  |  object_id [CHAR(32)] FK(group_element.object_id) PK
	  |  name [String(256)]
	Constraints :
	  |  software_group_constraint(name)
	"""

	__tablename__ = 'software_group'
	_constraints = ['unique_name']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'software_group_constraint'), {'schema': 'data'})
	object_id = Column(None, ForeignKey(GroupElement.object_id), primary_key=True)
	name = Column(String(256), nullable=False)
	unique_name = Column(String(512), nullable=False)
	qualifier = Column(String(256), nullable=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'software_group', 'inherit_condition' : object_id == GroupElement.object_id}
