"""Hardware objects.

Classes defined are part of 'data' schema (indentation represents inheritance)::

	BaseObjects - base_objects
		Hardware - hardware
			|  HardwareNode - hardware_node
			|  HardwareRack - hardware_rack
			|  HardwareLoadBalancer - hardware_load_balancer
			|  HardwareEnclosure - hardware_enclosure
			|  HardwareFirewall - hardware_firewall
			|  HardwareAccessPoint - hardware_access_point
			|  HardwareStorage - hardware_storage
			|  HardwarePowerStrip - hardware_power_strip
			|  HardwarePrinter - hardware_printer

"""
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Float
from sqlalchemy.types import Boolean, CHAR, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import and_, or_
from sqlalchemy import UniqueConstraint
from sqlalchemy import event
from database.schema.baseSchema import BaseObject


class Hardware(BaseObject):
	"""Defines a hardware category for the database::

		Table :
		  |  hardware
		Columns :
		  |  time_created [DateTime]
		  |  time_updated [DateTime]
		  |  object_created_by [String(128)]
		  |  object_updated_by [String(128)]
		  |  description [String(256)]
		  |  object_id [CHAR(32)] PK
		  |  object_type [String(16)]
		  |  vendor [String(256)]
		  |  model [String(256)]
		  |  version [String(256)]
		  |  build [String(256)]
		  |  asset_tag [String(256)]
		  |  serial_number [String(256)]
		  Constraints :
		  |  hardware_constraint(serial_number)
	"""

	__tablename__ = 'hardware'
	_constraints = ['serial_number']
	_captionRule = {
		"expression": {
			"operator": "or",
			"entries": [
				{ "condition": ["vendor", " ", "model"] },
				{ "condition": ["[", "asset_tag", "]"] },
				{ "condition": ["(", "serial_number", ")"] }
			]
		}
	}
	__table_args__ = (UniqueConstraint(*_constraints, name='hardware_constraint'), {"schema":"data"})
	object_id = Column(None, ForeignKey(BaseObject.object_id), primary_key=True)
	vendor = Column(String(256), nullable=True)
	model = Column(String(256), nullable=True)
	version = Column(String(256), nullable=True)
	build = Column(String(256), nullable=True)
	asset_tag = Column(String(256), nullable=True)
	serial_number = Column(String(256), nullable=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'hardware', 'inherit_condition': object_id == BaseObject.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(Hardware.serial_number == kwargs['serial_number'])

class HardwareNode(Hardware):
	"""Defines a hardware_node object for the database.

	A hardware_node object represents the physical or virtual hardware that a
	node runs on. Common examples:
	  * physical 2U blade server sitting in a datacenter rack
	  * virtual hardware allocated by a virtualization platform
	  * physical appliance hardware (e.g. switch, load balancer, firewall)

	It does *not* include attributes of the node running on it.

	Table :
	  |  hardware_node
	Columns :
	  |  object_id [CHAR(32)] FK(hardware.object_id) PK
	  |  uuid [String(256)]
	  |  bios_info [String(256)]
	"""

	__tablename__ = 'hardware_node'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(Hardware.object_id), primary_key=True)
	uuid = Column(String(256), nullable=True)
	bios_info = Column(String(256), nullable=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'hardware_node', 'inherit_condition': object_id == Hardware.object_id}


class HardwareRack(Hardware):
	"""Defines a hardware_rack object for the database.

	Table :
	  |  hardware_storage
	Columns :
	  |  object_id [CHAR(32)] FK(hardware.object_id) PK
	  |  grid_location [String(256)]
	  |  building [String(256)]
	  |  floor [String(256)]
	  |  room [String(256)]
	  |  row [String(256)]
	"""

	__tablename__ = 'hardware_rack'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(Hardware.object_id), primary_key=True)
	grid_location = Column(String(256), nullable=True)
	building = Column(String(256), nullable=True)
	floor = Column(String(256), nullable=True)
	room = Column(String(256), nullable=True)
	row = Column(String(256), nullable=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'hardware_rack', 'inherit_condition': object_id == Hardware.object_id}


class HardwareLoadBalancer(Hardware):
	"""Defines a hardware_load_balancer object for the database.

	Table :
	  |  hardware_load_balancer
	Column :
	  |  object_id [CHAR(32)] FK(hardware.object_id) PK
	"""

	__tablename__ = 'hardware_load_balancer'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(Hardware.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'hardware_load_balancer', 'inherit_condition': object_id == Hardware.object_id}


class HardwareEnclosure(Hardware):
	"""Defines a hardware_enclosure object for the database.

	Table :
	  |  hardware_enclosure
	Column :
	  |  object_id [CHAR(32)] FK(hardware.object_id) PK
	"""

	__tablename__ = 'hardware_enclosure'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(Hardware.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'hardware_enclosure', 'inherit_condition': object_id == Hardware.object_id}


class HardwareFirewall(Hardware):
	"""Defines a hardware_firewall object for the database.

	Table :
	  |  hardware_firewall
	Column :
	  |  object_id [CHAR(32)] FK(hardware.object_id) PK
	"""

	__tablename__ = 'hardware_firewall'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(Hardware.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'hardware_firewall', 'inherit_condition': object_id == Hardware.object_id}


class HardwareAccessPoint(Hardware):
	"""Defines a hardware_access_point object for the database.

	Table :
	  |  hardware_access_point
	Column :
	  |  object_id [CHAR(32)] FK(hardware.object_id) PK
	"""

	__tablename__ = 'hardware_access_point'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(Hardware.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'hardware_access_point', 'inherit_condition': object_id == Hardware.object_id}


class HardwareStorage(Hardware):
	"""Defines a hardware_storage object for the database.

	Table :
	  |  hardware_storage
	Column :
	  |  object_id [CHAR(32)] FK(hardware.object_id) PK
	"""

	__tablename__ = 'hardware_storage'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(Hardware.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'hardware_storage', 'inherit_condition': object_id == Hardware.object_id}


class HardwarePowerStrip(Hardware):
	"""Defines a hardware_power_strip object for the database.

	Table :
	  |  hardware_power_strip
	Column :
	  |  object_id [CHAR(32)] FK(hardware.object_id) PK
	"""

	__tablename__ = 'hardware_power_strip'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(Hardware.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'hardware_power_strip', 'inherit_condition': object_id == Hardware.object_id}


class HardwarePrinter(Hardware):
	"""Defines a hardware_printer object for the database.

	Table :
	  |  hardware_printer
	Column :
	  |  object_id [CHAR(32)] FK(hardware.object_id) PK
	"""

	__tablename__ = 'hardware_printer'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(Hardware.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'hardware_printer', 'inherit_condition': object_id == Hardware.object_id}
