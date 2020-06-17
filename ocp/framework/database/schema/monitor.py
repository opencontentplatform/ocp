"""Monitor objects.

Classes defined for the 'data' schema (indentation represents inheritance)::

	BaseObjects - base_objects
		Monitor - monitor
			|  ProcessMonitor - process_monitor

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  0.1 : (CS) Created Mar 23, 2018

"""
from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import relationship, backref
from sqlalchemy import and_
from sqlalchemy import UniqueConstraint
from database.schema.baseSchema import BaseObject
from database.schema.softwareElement import ProcessFingerprint


class Monitor(BaseObject):
	"""Defines the monitor object for the database

	Table :
	  |  monitor
	Columns :
	  |  object_id FK(base_object.object_id) PK
	"""

	__tablename__ = 'monitor'
	__table_args__ =  {'schema':'data'}
	object_id = Column(None, ForeignKey(BaseObject.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'monitor', 'inherit_condition': object_id == BaseObject.object_id}


class ProcessMonitor(Monitor):
	"""Defines the process_monitor object for the database

	Table :
	  |  process_monitor
	Columns :
	  |  object_id FK(monitor.object_id) PK
	  |  container FK(process_fingerprint.object_id)
	  |  name [String(256)]
	Constraints :
	  |  process_monitor_constraint(container, name)
	"""

	__tablename__ = 'process_monitor'
	_constraints = ['container', 'name']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name='process_monitor_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(Monitor.object_id), primary_key=True)
	container = Column(None, ForeignKey(ProcessFingerprint.object_id), nullable=False)
	name = Column(String(256), nullable=False)
	container_relationship = relationship('ProcessFingerprint', backref = backref('process_monitor_objects', cascade='all, delete'), foreign_keys = 'ProcessMonitor.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'process_monitor', 'inherit_condition': object_id == Monitor.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(ProcessMonitor.container == kwargs['container'],
								 ProcessMonitor.name == kwargs['name'], ProcessMonitor.software_version == kwargs['software_version'],
								 ProcessMonitor.software_info == kwargs['software_info']))
