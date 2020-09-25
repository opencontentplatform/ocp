"""Network elements.

Classes defined are part of 'data' schema (indentation represents inheritance)::

	BaseObjects - base_objects
		NetworkElement - network_element
			|  IpAddress - ip_address
			|  TcpIpPort - tcp_ip_port
			|  TcpIpPortClient - tcp_ip_port_client
			|  Domain - domain
			|  NameRecord - name_record
			|  URL - url

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

class NetworkElement(BaseObject):
	"""Defines the network_element object in the database

	Table :
	  |  network_element
	Column :
	  |  object_id [CHAR(32)] FK(base_object.object_id) PK
	"""

	__tablename__ = 'network_element'
	__table_args__ = {'schema':'data'}
	object_id = Column(None, ForeignKey(BaseObject.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'network_element', 'inherit_condition' : object_id == BaseObject.object_id}


class IpAddress(NetworkElement):
	"""Defines an ip_address object for the database.

	Table :
	  |  ip_address
	Columns :
	  |  object_id [CHAR(32)] FK(network_element.object_id) PK
	  |  time_created [DateTime]
	  |  time_updated [DateTime]
	  |  object_created_by [String(128)]
	  |  object_updated_by [String(128)]
	  |  description [String(256)]
	  |  address [String(128)] PK
	  |  realm [String(256)] PK
	  |  address_type [String(64)]
	  |  is_ipv4 [Boolean]
	Constraints :
	  |  ip_address_constraint(address)
	"""

	__tablename__ = 'ip_address'
	_constraints = ['address', 'realm']
	_captionRule = {"condition": [ "address" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name='ip_address_constraint'), {"schema":"data"})
	object_id = Column(CHAR(32), ForeignKey(NetworkElement.object_id), primary_key=True)
	address = Column(String(128), nullable=False)
	realm = Column(String(256), nullable=False)
	address_type = Column(String(64), nullable=True)
	is_ipv4 = Column(Boolean, nullable=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'ip_address', 'inherit_condition': object_id == NetworkElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(IpAddress.address == kwargs['address'])


class TcpIpPort(NetworkElement):
	"""Defines the tcp_ip_port object for the database

	Table :
	  |  object_id [CHAR(32)] FK(network_element.object_id) PK
	  |  name [String(128)]
	  |  port [Integer]
	  |  ip_address [CHAR(32)] FK(ip_address.object_id) PK
	  |  lable [String(256)]
	Constraints :
	  |  tcp_ip_port_constraint(name)
	"""

	__tablename__ = 'tcp_ip_port'
	## CNS: it's redundant to have ip and the container on the constraint list,
	## but I'm putting this in until I build out the resultProcessing to handle
	## constraints found through the links section (i.e. the container)
	_constraints = ['container', 'name', 'ip', 'is_tcp']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'tcp_ip_port_constraint'), {'schema':'data'})
	object_id = Column(CHAR(32), ForeignKey(NetworkElement.object_id), primary_key=True)
	container =  Column(None, ForeignKey(IpAddress.object_id), nullable=False)
	name = Column(String(128), nullable=False)
	port = Column(Integer, nullable=True)
	ip = Column(String(128), nullable=False)
	is_tcp = Column(Boolean, nullable=False)
	port_type = Column(String(16), nullable=True)
	label = Column(String(256), nullable=True)
	container_relationship = relationship('IpAddress',  backref = backref('tcp_ip_port_objects', cascade='all, delete'), foreign_keys='TcpIpPort.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'tcp_ip_port', 'inherit_condition': object_id == NetworkElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(TcpIpPort.name == kwargs['name'])


class TcpIpPortClient(NetworkElement):
	"""Defines the tcp_ip_port_client object for the database

	Table :
	  |  object_id [CHAR(32)] FK(network_element.object_id) PK
	  |  name [String(128)]
	  |  port [Integer]
	  |  ip_address [CHAR(32)] FK(ip_address.object_id) PK
	  |  lable [String(256)]
	Constraints :
	  |  tcp_ip_port_client_constraint(name)
	"""

	__tablename__ = 'tcp_ip_port_client'
	## CNS: it's redundant to have ip and the container on the constraint list,
	## but I'm putting this in until I build out the resultProcessing to handle
	## constraints found through the links section (i.e. the container)
	_constraints = ['container', 'name', 'ip', 'is_tcp']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'tcp_ip_port_client_constraint'), {'schema':'data'})
	object_id = Column(CHAR(32), ForeignKey(NetworkElement.object_id), primary_key=True)
	container =  Column(None, ForeignKey(IpAddress.object_id), nullable=False)
	name = Column(String(128), nullable=False)
	port = Column(Integer, nullable=True)
	ip = Column(String(128), nullable=False)
	is_tcp = Column(Boolean, nullable=False)
	port_type = Column(String(16), nullable=True)
	label = Column(String(256), nullable=True)
	container_relationship = relationship('IpAddress',  backref = backref('tcp_ip_port_client_objects', cascade='all, delete'), foreign_keys='TcpIpPortClient.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'tcp_ip_port_client', 'inherit_condition': object_id == NetworkElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(TcpIpPortClient.name == kwargs['name'])


class Domain(NetworkElement):
	"""Defines a domain object for the database

	Table :
	  |  domain
	Columns :
	  |  object_id [CHAR(32)] FK(network_element.object_id) PK
	  |  time_created [DateTime]
	  |  time_updated [DateTime]
	  |  object_created_by [String(128)]
	  |  object_updated_by [String(128)]
	  |  description [String(256)]
	  |  name [String(128)]
	Constraints :
	  |  domain_constraint(name)
	"""
	__tablename__ ='domain'
	_constraints = ['name']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'domain_constraint'), {"schema":"data"})
	object_id = Column(CHAR(32), ForeignKey(NetworkElement.object_id), primary_key=True)
	name = Column(String(128), nullable=False)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'domain', 'inherit_condition': object_id == NetworkElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(Domain.name == kwargs['name'])


class NameRecord(NetworkElement):
	"""Defines a name_record object for the database.

	Table :
	  |  name_record
	Columns :
	  |  object_id [CHAR(32)] FK(network_element.object_id) PK
	  |  time_created [DateTime]
	  |  time_updated [DateTime]
	  |  object_created_by [String(128)]
	  |  object_updated_by [String(128)]
	  |  description [String(256)]
	  |  container [CHAR(32)] FK(ip_address.object_id) PK
	  |  name [String(128)]
	  |  value [String(64)]
	Constraints :
	  |  name_record_constraint(container, name, value)
	"""

	__tablename__ = 'name_record'
	_constraints = ['container', 'name', 'value']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name='name_record_constraint'), {"schema":"data"})
	object_id = Column(CHAR(32), ForeignKey(NetworkElement.object_id), primary_key=True)
	## If domain deleted NameRecord will be deleted (strong relationship)
	container = Column(None, ForeignKey(Domain.object_id), nullable=False)
	name = Column(String(128), nullable=False)
	value = Column(String(64), nullable=False)
	container_relationship = relationship('Domain', backref = backref('name_record_objects', cascade='all, delete'), foreign_keys = 'NameRecord.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'name_record', 'inherit_condition': object_id == NetworkElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(NameRecord.container == kwargs['container'], NameRecord.name == kwargs['name'], NameRecord.value == kwargs['value']))


class URL(NetworkElement):
	"""Defines the url object for the database

	Table :
	  |  url
	Colunms :
	  |  object_id [CHAR(32)] FK(network_element.object_id) PK
	  |  name [String(512)]
	  |  notes [String(512)]
	Constraints :
	  |  url_constraint(name)
	"""

	__tablename__ = 'url'
	_constraints = ['name']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='url_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(NetworkElement.object_id), primary_key=True)
	name = Column(String(512), nullable=False)
	notes = Column(String(512),nullable=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'url', 'inherit_condition': object_id == NetworkElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(URL.name == kwargs['name'])


class SSLCertificate(NetworkElement):
	"""Defines an ssl_certificate object for the database.

	Table :
	  |  ssl_certificate
	Columns :
	  |  object_id [CHAR(32)] FK(network_element.object_id) PK
	  |  time_created [DateTime]
	  |  time_updated [DateTime]
	  |  object_created_by [String(128)]
	  |  object_updated_by [String(128)]
	  |  description [String(256)]
	  |  container [CHAR(32)] FK(ip_address.object_id) PK
	  |  name [String(128)]
	  |  value [String(64)]
	Constraints :
	  |  ssl_certificate_constraint(container, name, value)
	"""

	__tablename__ = 'ssl_certificate'
	_constraints = ['container', 'serial_number']
	_captionRule = {
		"expression": {
			"operator": "or",
			"entries": [
				{ "condition": ["common_name"] },
				{ "condition": ["SN:", "serial_number"] }
			]
		}
	}
	__table_args__ = (UniqueConstraint(*_constraints, name='ssl_certificate_constraint'), {"schema":"data"})
	object_id = Column(CHAR(32), ForeignKey(NetworkElement.object_id), primary_key=True)
	## If TcpIpPort is deleted this will be deleted (strong relationship)
	container = Column(None, ForeignKey(TcpIpPort.object_id), nullable=False)
	serial_number = Column(String(256), nullable=False)
	subject = Column(JSON, nullable=True)
	common_name = Column(String(256), nullable=True)
	issuer = Column(JSON, nullable=True)
	version = Column(String(32), nullable=True)
	not_before = Column(DateTime(timezone=True), nullable=True)
	not_after = Column(DateTime(timezone=True), nullable=True)
	signature_algorithm = Column(String(64), nullable=True)
	subject_alt_name = Column(String(2056), nullable=True)
	container_relationship = relationship('TcpIpPort', backref = backref('ssl_certificate_objects', cascade='all, delete'), foreign_keys = 'SSLCertificate.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'ssl_certificate', 'inherit_condition': object_id == NetworkElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(SSLCertificate.container == kwargs['container'], SSLCertificate.name == kwargs['serial_number']))
