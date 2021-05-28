"""Node objects.

A node in the Open Content Platform represents the functional 'brain' of a
device. Common examples:

  * server OS instance
  * hypervisor instance
  * firmware instance

The only attributes of hardware that may be tracked in the Node category, are
whether the 'brain' is running on physical or virtual hardware, along with the
provider. The reason for that is because we may not need to discover specific
hardware allocations for virtual machines (e.g. the UUID, SerialNumber, Asset
tag - virtually assigned), but we may need to know if it's virtual and the type
of virtual platform providing the resources (VMware, HyperV, Xen, KVM, etc).

Classes defined are part of 'data' schema (indentation represents inheritance)::

	BaseObjects - base_objects
		Node - node
			NodeServer - node_server
				|  Linux - node_linux
				|  AIX - node_aix
				|  HPUX - node_hpux
				|  Solaris - node_solaris
				|  Windows - node_windows
			NodeDevice - node_device
				|  Switch - node_switch
				|  Firewall - node_firewall
				|  LoadBalancer - node_loadbalancer
				|  Printer - node_printer
				|  Storage - node_storage

"""
from functools import reduce
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Float
from sqlalchemy.types import Boolean, CHAR, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import and_, or_
from sqlalchemy import UniqueConstraint
from sqlalchemy import event
# Base = declarative_base()
from database.schema.baseSchema import BaseObject


class Node(BaseObject):
	"""Defines a node object for the database.

	A node object is the functional 'brain' of a device. Common examples:
	  * server OS instance
	  * hypervisor instance
	  * firmware instance

	The only attributes of hardware that may be tracked here is whether it
	is physical or virtual, along with the provider. The reason for that is
	because you may not need to discover specific HW allocations for virtual
	machines (e.g. the UUID, SerialNumber, Asset tag - virtually assigned),
	but you may need to know if it's virtual and the type of virtual platform
	providing the VM resources (VMware, HyperV, Xen, KVM, etc).

	Table :
	  |  node
	Columns :
	  |  time_created [DateTime]
	  |  time_updated [DateTime]
	  |  object_created_by [String(128)]
	  |  object_updated_by [String(128)]
	  |  description [String(256)]
	  |  hostname [String(256)] PK
	  |  domain [String(256)] PK
	  |  object_id [CHAR(32)] FK(base_object.object_id) PK
	  |  object_type [String(16)]
	  |  vendor [String(256)]
	  |  version [String(256)]
	  |  hardware_is_virtual [Boolean]
	  |  hardware_provider [String(256]
	  |  partial [Boolean]
	  |  snmp_oid [String(256]
	  |  location [String(256]
	Constraints :
	  | node_constraint (hostname, domain)
	"""

	__tablename__ = 'node'
	_constraints = ['hostname', 'domain']
	_captionRule = {"condition": [ "hostname" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name='node_constraint'), {"schema":"data"})
	hostname = Column(String(256), nullable=False)
	domain = Column(String(256), nullable=True)
	object_id = Column(CHAR(32), ForeignKey(BaseObject.object_id), primary_key=True)
	vendor = Column(String(256), nullable=True)
	platform = Column(String(256), nullable=True)
	version = Column(String(256), nullable=True)
	hardware_is_virtual = Column(Boolean, nullable=True, default=False)
	hardware_provider = Column(String(256), nullable=True)
	partial = Column(Boolean, nullable=True, default=False)
	snmp_oid = Column(String(256), nullable=True)
	location = Column(String(256), nullable=True)
	
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'node', 'inherit_condition': object_id == BaseObject.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(Node.hostname == kwargs['hostname'], Node.domain == kwargs['domain']))


class NodeServer(Node):
	"""Defines a server object for the database.

	The server category will probably not be used directly. Most often you will
	want to use a qualified sub-type (e.g. node_linux or node_windows), which
	will allow queries to return only objects of that type.

	Table :
	  |  node_server
	Column :
	  |  object_id [CHAR(32)] FK(node.object_id) PK
	"""

	__tablename__ = 'node_server'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(Node.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'node_server', 'inherit_condition': object_id == Node.object_id}


class Linux(NodeServer):
	"""Defines a node_linux object for the database.

	Table :
	  |  node_linux
	Columns:
	  |  object_id [CHAR(32)] FK(node_server.object_id) PK
	  |  distribution [String(256)]
	"""

	__tablename__ = 'node_linux'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(NodeServer.object_id), primary_key=True)
	distribution = Column(String(256), nullable=True)
	kernel = Column(String(256), nullable=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'node_linux', 'inherit_condition': object_id == NodeServer.object_id}


class AIX(NodeServer):
	"""Defines a node_aix object for the database.

	Table :
	  |  node_aix
	Column :
	  |  object_id [CHAR(32)] FK(node_server.object_id) PK
	"""

	__tablename__ = 'node_aix'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(NodeServer.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'node_aix', 'inherit_condition': object_id == NodeServer.object_id}


class HPUX(NodeServer):
	"""Defines a node_hpux object for the database.

	Table :
	  |  node_hpux
	Column :
	  |  object_id [CHAR(32)] FK(node_server.object_id) PK
	"""

	__tablename__ = 'node_hpux'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(NodeServer.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'node_hpux', 'inherit_condition': object_id == NodeServer.object_id}


class Solaris(NodeServer):
	"""Defines a node_solaris object for the database.

	Table :
	  |  node_solaris
	Columns :
	  |  object_id [CHAR(32)] FK(node_server.object_id) PK
	"""

	__tablename__ = 'node_solaris'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(NodeServer.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'node_solaris', 'inherit_condition': object_id == NodeServer.object_id}


class Windows(NodeServer):
	"""Defines a node_windows object for the database.

	Table :
	  |  node_windows
	Columns:
	  |  object_id [CHAR(32)] FK(node_server.object_id) PK
	"""

	__tablename__ = 'node_windows'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(NodeServer.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'node_windows', 'inherit_condition': object_id == NodeServer.object_id}


class NodeDevice(Node):
	"""Defines a node_device object for the database.

	The device type can either be used directly or indirectly (subclassing).

	This is a subtype of Node, which means it is intended to represent objects
	you are able to discover (or otherwise gather details on OS/firmware).

	It is normal to have information about network devices... that they exist
	and are a certain type of vendor platform/product, but always normal to be
	allowed a protocol connection and talk to their firmware/OS for details
	about them.  Only create objects that you know about.  So if you do not have
	information on the OS level, you would only create a hardware object for the
	hardware (whether physical or virtual) and relate in other records like IP
	address and Name service.  You only create an object in this node->device
	table when you have information from or about the "brain" (i.e. firmware or
	OS instance)... such as if you are able to talk to a load balancer via some
	remote protocol (e.g. SNMP, SSH, API).

	Table :
	  |  node_device
	Column :
	  |  object_id [CHAR(32)] FK(node.object_id) PK
	"""

	__tablename__ = 'node_device'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(Node.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'node_device', 'inherit_condition': object_id == Node.object_id}


class Switch(NodeDevice):
	"""Defines a node_switch object for the database.

	Table :
	  |  node_switch
	Columns:
	  |  object_id [CHAR(32)] FK(node_server.object_id) PK
	"""

	__tablename__ = 'node_switch'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(NodeDevice.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'node_switch', 'inherit_condition': object_id == NodeDevice.object_id}


class Firewall(NodeDevice):
	"""Defines a node_firewall object for the database.

	Table :
	  |  node_firewall
	Columns:
	  |  object_id [CHAR(32)] FK(node_server.object_id) PK
	"""

	__tablename__ = 'node_firewall'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(NodeDevice.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'node_firewall', 'inherit_condition': object_id == NodeDevice.object_id}


class LoadBalancer(NodeDevice):
	"""Defines a node_loadbalancer object for the database.

	Table :
	  |  node_loadbalancer
	Columns:
	  |  object_id [CHAR(32)] FK(node_server.object_id) PK
	"""

	__tablename__ = 'node_loadbalancer'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(NodeDevice.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'node_loadbalancer', 'inherit_condition': object_id == NodeDevice.object_id}


class Printer(NodeDevice):
	"""Defines a node_printer object for the database.

	Table :
	  |  node_printer
	Columns:
	  |  object_id [CHAR(32)] FK(node_server.object_id) PK
	"""

	__tablename__ = 'node_printer'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(NodeDevice.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'node_printer', 'inherit_condition': object_id == NodeDevice.object_id}


class Storage(NodeDevice):
	"""Defines a node_storage object for the database.

	Table :
	  |  node_storage
	Columns:
	  |  object_id [CHAR(32)] FK(node_server.object_id) PK
	"""

	__tablename__ = 'node_storage'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(NodeDevice.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'node_storage', 'inherit_condition': object_id == NodeDevice.object_id}


class ManagementInterface(NodeDevice):
	"""Defines a node_mgmt_interface object for the database.

	Table :
	  |  node_mgmt_interface
	Columns:
	  |  object_id [CHAR(32)] FK(node_server.object_id) PK
	"""

	__tablename__ = 'node_mgmt_interface'
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(NodeDevice.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'node_mgmt_interface', 'inherit_condition': object_id == NodeDevice.object_id}