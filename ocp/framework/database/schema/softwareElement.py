"""Software elements.

Software elements are instance-based CIs with a single environment. For example:
  * Software running on a single server or in a single container boundary
  * Software configured/installed/deployed into a single container

This category is slightly different from 'System elements', where the execution
environment is strongly tied to a single Node/OS instance. And is different
from 'Software components', where the component (e.g. database) is shared by
or represented across multiple instance-based CIs.

Classes defined for the 'data' schema (indentation represents inheritance)::

	BaseObjects - base_objects
		SoftwareElement - software_element
			|  SoftwareFingerprint - software_fingerprint
			|  ProcessFingerprint - process_fingerprint
			|  NormalizedSoftware - normalized_software
			|  Protocol - protocol
				|  ICMP - icmp
				|  SSH - ssh
				|  SNMP -snmp
				|  PowerShell - power_shell
			|  WebServer - web_server
				|  Apache - apache
				|  IIS - iis
			|  AppServer - app_server
				|  WebShpere - web_sphere
				|  DotNet - dotnet
				|  WebLigic - web_logic
				|  Tomcat - tomcat
				|  JBoss - jboss
				|  Twisted - twisted
			|  Database - database
				|  Postgres - postgres
				|  DB2 - db2
				|  MySQL - mysql
				|  Vertica  - vertica
				|  SqlServer - sql_server
				|  Oracle - oracle

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  0.1 : (CS) Created Jul 24, 2017
	  1.0 : (CS) Split out to enable use of multiple files, Oct 3, 2017

"""
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Float
from sqlalchemy.types import Boolean, CHAR, JSON
## Using the Postgres dialect of ARRAY to enable contains/in clauses
#from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from sqlalchemy import and_
from sqlalchemy import UniqueConstraint
from database.schema.baseSchema import BaseObject
from database.schema.node import Node
from database.schema.platformSchema import Realm


class SoftwareElement(BaseObject):
	"""Defines the software_element object for the database

	Table :
	  |  software_element
	Columns :
	  |  object_id FK(base_object.object_id) PK
	"""

	__tablename__ = 'software_element'
	__table_args__ =  {'schema':'data'}
	object_id = Column(None, ForeignKey(BaseObject.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'software_element', 'inherit_condition': object_id == BaseObject.object_id}


class SoftwareFingerprint(SoftwareElement):
	"""Defines the software_fingerprint object for the database

	Table :
	  |  software_fingerprint
	Columns :
	  |  object_id FK(software_element.object_id) PK
	  |  container FK(node.object_id)
	  |  name [String(256)]
	  |  software_version [String(256)]
	  |  software_info [String(256)]
	  |  software_id [String(64)]
	  |  software_source [String(32)]
	  |  vendor [String(64)]
	Constraints :
	  |  software_fingerprint_constraint(container, name, software_version, software_info)
	"""

	__tablename__ = 'software_fingerprint'
	_constraints = ['container', 'name', 'software_version', 'software_info']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name='software_fingerprint_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(SoftwareElement.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	name = Column(String(256), nullable=False)
	software_version = Column(String(256), nullable=True)
	software_info = Column(String(256), nullable=True)
	software_id = Column(String(64), nullable=True)
	software_source = Column(String(32), nullable=True)
	vendor = Column(String(64), nullable=True)
	container_relationship = relationship('Node', backref = backref('software_fingerprint_objects', cascade='all, delete'), foreign_keys = 'SoftwareFingerprint.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'software_fingerprint', 'inherit_condition': object_id == SoftwareElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(SoftwareFingerprint.container == kwargs['container'],
								 SoftwareFingerprint.name == kwargs['name'], SoftwareFingerprint.software_version == kwargs['software_version'],
								 SoftwareFingerprint.software_info == kwargs['software_info']))


class ProcessFingerprint(SoftwareElement):
	"""Defines the process_fingerprint object for the database

	Table :
	  |  process_fingerprint
	Columns :
	  |  object_id FK(software_element.object_id) PK
	  |  container FK(node.object_id)
	  |  name [String(256)]
	  |  process_hierarchy [Array(String)]
	  |  process_owner [String(64)]
	  |  path_from_process [String(256)]
	  |  path_from_filesystem [String(256)]
	  |  path_from_analysis [String(256)]
	  |  process_args [String(256)]
	Constraints:
	  | process_fingerprint_constraint(container, name, process_hierarchy, process_owner, path_from_process, path_from_filesystem, path_from_analysis)
	"""

	__tablename__ = 'process_fingerprint'
	_constraints = ['container', 'name', 'process_hierarchy', 'process_owner', 'process_args', 'path_from_process', 'path_from_filesystem', 'path_from_analysis', 'process_args']
	_captionRule = {
		"expression": {
			"operator": "and",
			"entries": [
				{ "condition": [ "name" ] },
				{ "expression": {
					"operator": "or",
					"entries": [
						{ "condition": [":", "process_args"] },
						##{ "condition": [" (", "process_args", ")"] },
						{ "condition": [""] }
					]}
				}
			]
		}
	}
	__table_args__ = (UniqueConstraint(*_constraints, name='process_fingerprint_constraint'), {'schema':'data'})
	object_id =  Column(None, ForeignKey(SoftwareElement.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	name = Column(String(256), nullable=False)
	## Can't use JSON for a primary or constraint
	#process_hierarchy = Column(JSON, nullable=False)
	## I'd like to use ARRAY, but need to build more flexible ORM statements so
	## .filter(and_((getattr(class, item) == data[item] for item in constraints)))
	## type functionality in resultProcessing won't throw errors on a malformed
	## array literal. Need to check the type and use an array comparator like
	## 'any' instead of '==' when it's not a literal type (str, int, bool, date)
	#process_hierarchy = Column(ARRAY(String, dimensions=1), nullable=False)
	process_hierarchy = Column(String(512), nullable=False)
	process_owner = Column(String(64), nullable=False)
	path_from_process = Column(String(256), nullable=True)
	path_from_filesystem = Column(String(256), nullable=True)
	path_from_analysis = Column(String(256), nullable=True)
	path_working_dir = Column(String(256), nullable=True)
	process_args = Column(String(256), nullable=True)
	is_filtered_out = Column(Boolean, nullable=True, default=False)
	container_relationship = relationship('Node', backref = backref('process_fingerprint_objects', cascade='all, delete'), foreign_keys = 'ProcessFingerprint.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'process_fingerprint', 'inherit_condition': object_id == SoftwareElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(ProcessFingerprint.container == kwargs['container'], ProcessFingerprint.name == kwargs['name'],
								 ProcessFingerprint.process_hierarchy == kwargs['process_hierarchy'], ProcessFingerprint.process_owner == kwargs['process_owner'],
								 ProcessFingerprint.path_from_process == kwargs['path_from_process'], ProcessFingerprint.path_from_filesystem == kwargs['path_from_filesystem'],
								 ProcessFingerprint.path_from_analysis == kwargs['path_from_analysis']))



class NormalizedSoftware(SoftwareElement):
	"""Defines the normalized_software object for the database

	Table :
	  |  normalized_software
	Columns :
	  |  object_id FK(software_element.object_id) PK
	  |  container FK(process_fingerprint.object_id)
	  |  name [String(256)]
	  |  path [String(256)]
	  |  version [String(256)]
	  |  vendor [String(64)]
	  |  is_filled_out [Boolean]
	Constraints:
	  | normalized_software_constraint(container, name, process_hierarchy, process_owner, path_from_process, path_from_filesystem, path_from_analysis)
	"""

	__tablename__ = 'normalized_software'
	_constraints = ['container', 'name', 'version', 'path']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name='normalized_software_constraint'), {'schema':'data'})
	object_id =  Column(None, ForeignKey(SoftwareElement.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	name = Column(String(256), nullable=False)
	path = Column(String(256), nullable=False)
	version = Column(String(256), nullable=False)
	vendor = Column(String(64), nullable=True)
	is_filled_out = Column(Boolean, nullable=True, default=True)
	container_relationship = relationship('Node', backref = backref('normalized_software_objects', cascade='all, delete'), foreign_keys = 'NormalizedSoftware.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'normalized_software', 'inherit_condition': object_id == SoftwareElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(NormalizedSoftware.container == kwargs['container'], NormalizedSoftware.name == kwargs['name'],
								 NormalizedSoftware.process_hierarchy == kwargs['path'], NormalizedSoftware.process_owner == kwargs['version'],
								 NormalizedSoftware.path_from_process == kwargs['vendor']))


class WebServer(SoftwareElement):
	"""Defines the web_server object for the database

	Table :
	  |  web_server
	Column :
	  |  object_id FK(software_element.object_id) PK
	"""

	__tablename__ = 'web_server'
	__table_args__ = {'schema':'data'}
	object_id =  Column(None, ForeignKey(SoftwareElement.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'web_server', 'inherit_condition': object_id == SoftwareElement.object_id}


class AppServer(SoftwareElement):
	"""Defines the app_server object for the database

	Table :
	  |  app_server
	Column :
	  |  object_id FK(software_element.object_id) PK
	"""

	__tablename__ = 'app_server'
	__table_args__ = {'schema':'data'}
	object_id =  Column(None, ForeignKey(SoftwareElement.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'app_server', 'inherit_condition': object_id == SoftwareElement.object_id}


class Protocol(SoftwareElement):
	"""Defines the protocol object for the database

	Table :
	  |  protocol
	Column :
	  |  object_id FK(software_element.object_id) PK
	"""

	__tablename__ = 'protocol'
	#_constraints = ['container', 'ipaddress', 'protocol_reference', 'realm']
	#_constraints = ['container', 'ipaddress', 'object_type', 'realm']
	#__table_args__ = (UniqueConstraint(*_constraints, name='protocol_constraint'), {'schema':'data'})
	__table_args__ = {'schema':'data'}
	object_id =  Column(None, ForeignKey(SoftwareElement.object_id), primary_key=True)
	#container = Column(None, ForeignKey(Node.object_id), nullable=False)
	ipaddress = Column(String(128), nullable=False)
	endpoint = Column(String(256), nullable=True)
	protocol_reference = Column(String(32), nullable=False)
	node_type = Column(String(32), nullable=True)
	realm = Column(None, ForeignKey(Realm.name), nullable=False)
	port = Column(Integer, nullable=True)
	#container_relationship = relationship('Node', backref = backref('protocol_objects', cascade = 'all, delete'), foreign_keys = 'Protocol.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'protocol', 'inherit_condition': object_id == SoftwareElement.object_id}

	# @classmethod
	# def unique_filter(cls, query, **kwargs):
	# 	#return query.filter(and_(Protocol.container == kwargs['container'], Protocol.ipaddress == kwargs['ipaddress'], Protocol.protocol_reference == kwargs['protocol_reference'], Protocol.realm == kwargs['realm']))
	# 	#return query.filter(and_(Protocol.container == kwargs['container'], Protocol.ipaddress == kwargs['ipaddress'], Protocol.realm == kwargs['realm']))
	# 	return query.filter(Protocol.container == kwargs['container'])


class ICMP(Protocol):
	"""Defines the icmp object for the database

	Table :
	  |  icmp
	Columns :
	  |  object_id FK(protocol.object_id) PK
	  |  container FK(node.object_id)
	  |  protocol_reference [String(32)]
	Constraints :
	  |  icmp_constraint(container)
	"""

	__tablename__ = 'icmp'
	__table_args__ = {'schema':'data'}
	object_id = Column(None, ForeignKey(Protocol.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	container_relationship = relationship('Node', backref = backref('icmp_objects', cascade = 'all, delete'), foreign_keys = 'ICMP.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'icmp', 'inherit_condition': object_id == Protocol.object_id}


class SNMP(Protocol):
	"""Defines the snmp object for the database

	Table :
	  |  snmp
	Columns :
	  |  object_id FK(protocol.object_id) PK
	  |  container FK(node.object_id)
	  |  protocol_reference [String(32)]
	Constraints :
	  |  snmp_constraint(container)
	"""

	__tablename__ = 'snmp'
	#__table_args__ = {'schema':'data'}
	_constraints = ['container']
	__table_args__ = (UniqueConstraint(*_constraints, name='snmp_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(Protocol.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	container_relationship = relationship('Node', backref = backref('snmp_objects', cascade = 'all, delete'), foreign_keys = 'SNMP.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'snmp', 'inherit_condition': object_id == Protocol.object_id}


class WMI(Protocol):
	"""Defines the wmi object for the database

	Table :
	  |  wmi
	Columns :
	  |  object_id FK(protocol.object_id) PK
	  |  container FK(node.object_id)
	  |  protocol_reference [String(32)]
	Constraints :
	  |  wmi_constraint(container)
	"""

	__tablename__ = 'wmi'
	#__table_args__ = {'schema':'data'}
	_constraints = ['container']
	__table_args__ = (UniqueConstraint(*_constraints, name='wmi_constraint'), {'schema':'data'})
	object_id =  Column(None, ForeignKey(Protocol.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	container_relationship = relationship('Node', backref = backref('wmi_objects', cascade = 'all, delete'), foreign_keys = 'WMI.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'wmi', 'inherit_condition': object_id == Protocol.object_id}


class Shell(Protocol):
	"""Defines a general shell object for the database

	Table :
	  |  shell
	Column :
	  |  object_id FK(protocol.object_id) PK
	"""

	__tablename__ = 'shell'
	__table_args__ = {'schema':'data'}
	object_id = Column(None, ForeignKey(Protocol.object_id), primary_key=True)
	config_group = Column(String(128), nullable=True)
	parameters = Column(JSON, nullable=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'shell', 'inherit_condition': object_id == Protocol.object_id}


class SSH(Shell):
	"""Defines the ssh object for the database

	Table :
	  |  ssh
	Columns :
	  |  object_id FK(protocol.object_id) PK
	  |  container FK(node.object_id)
	  |  protocol_reference [String(32)]
	Constraints :
	  |  ssh_constraint(container)
	"""

	__tablename__ = 'ssh'
	#__table_args__ = {'schema':'data'}
	_constraints = ['container']
	__table_args__ = (UniqueConstraint(*_constraints, name='ssh_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(Shell.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	container_relationship = relationship('Node', backref = backref('ssh_objects', cascade = 'all, delete'), foreign_keys = 'SSH.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'ssh', 'inherit_condition': object_id == Shell.object_id}


class PowerShell(Shell):
	"""Defines the powershell object for the database

	Table :
	  |  powershell
	Columns :
	  |  object_id FK(protocol.object_id) PK
	  |  container FK(node.object_id)
	  |  protocol_reference [String(32)]
	Constraints :
	  |  powershell_constraint(container)
	"""

	__tablename__ = 'powershell'
	#__table_args__ = {'schema':'data'}
	_constraints = ['container']
	__table_args__ = (UniqueConstraint(*_constraints, name='powershell_constraint'), {'schema':'data'})
	object_id =  Column(None, ForeignKey(Shell.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	container_relationship = relationship('Node', backref = backref('powershell_objects', cascade = 'all, delete'), foreign_keys = 'PowerShell.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'powershell', 'inherit_condition': object_id == Shell.object_id}


class SQL(Protocol):
	"""Defines the sql object for the database

	Table :
	  |  sql
	Columns :
	  |  object_id FK(protocol.object_id) PK
	  |  container FK(node.object_id)
	  |  protocol_reference [String(32)]
	Constraints :
	  |  sql_constraint(container)
	"""

	__tablename__ = 'sql'
	#__table_args__ = {'schema':'data'}
	_constraints = ['container']
	__table_args__ = (UniqueConstraint(*_constraints, name='sql_constraint'), {'schema':'data'})
	object_id =  Column(None, ForeignKey(Protocol.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	container_relationship = relationship('Node', backref = backref('sql_objects', cascade = 'all, delete'), foreign_keys = 'SQL.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'sql', 'inherit_condition': object_id == Protocol.object_id}


class REST(Protocol):
	"""Defines the rest_api object for the database

	Table :
	  |  rest_api
	Columns :
	  |  object_id FK(protocol.object_id) PK
	  |  container FK(node.object_id)
	  |  protocol_reference [String(32)]
	Constraints :
	  |  rest_api_constraint(container)
	"""

	__tablename__ = 'rest_api'
	_constraints = ['container']
	__table_args__ = (UniqueConstraint(*_constraints, name='rest_api_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(Protocol.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	container_relationship = relationship('Node', backref = backref('rest_api_objects', cascade = 'all, delete'), foreign_keys = 'REST.container')
	base_url = Column(String(512), nullable=False)
	auth_url = Column(String(512), nullable=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'rest_api', 'inherit_condition': object_id == Protocol.object_id}


class Apache(WebServer):
	"""Defines the apache object for the database

	Table :
	  |  apache
	Columns :
	  |  object_id FK(web_server.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  apache_constraint(container, path)
	"""

	__tablename__ = 'apache'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "path" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='apache_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(WebServer.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	container_relationship = relationship('Node', backref = backref('apache_objects', cascade = 'all, delete'), foreign_keys = 'Apache.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'apache', 'inherit_condition': object_id == WebServer.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(Apache.container == kwargs['container'], Apache.path == kwargs['path']))


class IIS(WebServer):
	"""Defines the iis object for the database

	Table :
	  |  iis
	Columns :
	  |  object_id FK(web_server.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  iis_constraint(container, path)
	"""

	__tablename__ = 'iis'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "path" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='iis_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(WebServer.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	container_relationship = relationship('Node', backref = backref('iis_objects', cascade = 'all, delete'), foreign_keys = 'IIS.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'iis', 'inherit_condition': object_id == WebServer.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(IIS.container == kwargs['container'], IIS.path == kwargs['path']))


class WebSphere(AppServer):
	"""Defines the websphere object for the database

	Table :
	  |  websphere
	Columns :
	  |  object_id FK(app_server.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  websphere_constraint(container, path)
	"""

	__tablename__ = 'websphere'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "path" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='websphere_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(AppServer.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	container_relationship = relationship('Node', backref = backref('websphere_objects', cascade = 'all, delete'), foreign_keys = 'WebSphere.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'websphere', 'inherit_condition': object_id == AppServer.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(WebSphere.container == kwargs['container'], WebSphere.path == kwargs['path']))


class DotNet(AppServer):
	"""Defines the dotnet object for the database

	Table :
	  |  dotnet
	Columns :
	  |  object_id FK(app_server.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  dotnet_constraint(container, path)
	"""

	__tablename__ = 'dotnet'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "path" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='dotnet_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(AppServer.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	container_relationship = relationship('Node', backref = backref('dotnet_objects', cascade = 'all, delete'), foreign_keys = 'DotNet.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'dotnet', 'inherit_condition': object_id == AppServer.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(DotNet.container == kwargs['container'], DotNet.path == kwargs['path']))


class WebLogic(AppServer):
	"""Defines the weblogic object for the database

	Table :
	  |  weblogic
	Columns :
	  |  object_id FK(app_server.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  weblogic_constraint(container, path)
	"""

	__tablename__ = 'weblogic'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "path" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='weblogic_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(AppServer.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	container_relationship = relationship('Node', backref = backref('weblogic_objects', cascade = 'all, delete'), foreign_keys = 'WebLogic.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'weblogic', 'inherit_condition': object_id == AppServer.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(WebLogic.container == kwargs['container'], WebLogic.path == kwargs['path']))


class Tomcat(AppServer):
	"""Defines the tomcat object for the database

	Table :
	  |  tomcat
	Columns :
	  |  object_id FK(app_server.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  tomcat_constraint(container, path)
	"""

	__tablename__ = 'tomcat'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "path" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='tomcat_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(AppServer.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	container_relationship = relationship('Node', backref= backref('tomcat_objects', cascade = 'all, delete'), foreign_keys = 'Tomcat.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'tomcat', 'inherit_condition': object_id == AppServer.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(Tomcat.container == kwargs['container'], Tomcat.path == kwargs['path']))


class JBoss(AppServer):
	"""Defines the jboss object for the database

	Table :
	  |  jboss
	Columns :
	  |  object_id FK(app_server.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  jboss_constraint(container, path)
	"""

	__tablename__ = 'jboss'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "path" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='jboss_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(AppServer.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	container_relationship = relationship('Node', backref = backref('jboss_objects', cascade = 'all, delete'), foreign_keys = 'JBoss.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'jboss', 'inherit_condition': object_id == AppServer.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(JBoss.container == kwargs['container'], JBoss.path == kwargs['path']))


class Twisted(AppServer):
	"""Defines the twisted object for the database

	Table :
	  |  twisted
	Columns :
	  |  object_id FK(app_server.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  twisted_constraint(container, path)
	"""

	__tablename__ = 'twisted'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "path" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='twisted_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(AppServer.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	container_relationship = relationship('Node', backref = backref('twisted_objects', cascade = 'all, delete'), foreign_keys = 'Twisted.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'twisted', 'inherit_condition': object_id == AppServer.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(Twisted.container == kwargs['container'], Twisted.path == kwargs['path']))



class DatabaseContext(SoftwareElement):
	"""Represents a configured or installed database object; may not be running

	Table :
	  |  database_context
	Column :
	  |  object_id FK(software_element.object_id) PK
	"""

	__tablename__ = 'database_context'
	__table_args__ = {'schema':'data'}
	object_id =  Column(None, ForeignKey(SoftwareElement.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'database_context', 'inherit_condition': object_id == SoftwareElement.object_id}


class DBConnectionParameter(SoftwareElement):
	"""Represents a connection parameter configured for a database context

	Table :
	  |  database_connection_parameter
	Columns :
	  |  object_id FK(database.object_id) PK
	  |  container FK(node.object_id)
	  |  ip_address [String(128)]
	  |  name [String(128)]
	  |  protocol [String(128)]
	  |  port [Integer]
	  |  name [String(128)]
	  |  name [String(128)]
	Constraints :
	  |  database_connection_parameter_constraint(container, path)
	"""

	__tablename__ = 'database_connection_parameter'
	_constraints = ['container', 'name', 'protocol', 'ip_address']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='database_connection_parameter_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(SoftwareElement.object_id), primary_key=True)
	container = Column(None, ForeignKey(DatabaseContext.object_id), nullable=False)
	name = Column(String(128), nullable=False)
	protocol = Column(String(128), nullable=False)
	ip_address = Column(String(128), nullable=True)
	port = Column(Integer, nullable=True)
	db_type = Column(String(128), nullable=True)
	source = Column(String(128), nullable=True)
	hostname = Column(String(128), nullable=True)
	logical_context = Column(String(256), nullable=True)
	container_relationship = relationship('DatabaseContext', backref = backref('database_connection_parameter_objects', cascade = 'all, delete'), foreign_keys = 'DBConnectionParameter.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'database_connection_parameter', 'inherit_condition': object_id == SoftwareElement.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(DBConnectionParameter.container == kwargs['container'], DBConnectionParameter.path == kwargs['path']))


class SqlServerContext(DatabaseContext):
	"""Represents a configured or installed Microsoft SQL Server database

	Table :
	  |  sqlserver_context
	Columns :
	  |  object_id FK(database.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  sqlserver_context_constraint(container, path)
	"""

	__tablename__ = 'sqlserver_context'
	_constraints = ['container', 'name', 'path']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='sqlserver_context_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(DatabaseContext.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	name = Column(String(128), nullable=False)
	path = Column(String(512), nullable=False)
	version = Column(String(128), nullable=True)
	patch_level = Column(String(128), nullable=True)
	edition = Column(String(128), nullable=True)
	edition_type = Column(String(128), nullable=True)
	program_dir = Column(String(512), nullable=True)
	container_relationship = relationship('Node', backref = backref('sqlserver_context_objects', cascade = 'all, delete'), foreign_keys = 'SqlServerContext.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'sqlserver_context', 'inherit_condition': object_id == DatabaseContext.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(SqlServerContext.container == kwargs['container'], SqlServerContext.path == kwargs['path']))


class OracleContext(DatabaseContext):
	"""Represents a configured or installed Oracle database

	Table :
	  |  oracle_context
	Columns :
	  |  object_id FK(database.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  oracle_context_constraint(container, path)
	"""

	__tablename__ = 'oracle_context'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='oracle_context_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(DatabaseContext.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	name = Column(String(128))
	version = Column(String(128))
	container_relationship = relationship('Node', backref = backref('oracle_context_objects', cascade = 'all, delete'), foreign_keys = 'OracleContext.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'oracle_context', 'inherit_condition': object_id == DatabaseContext.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(OracleContext.container == kwargs['container'], OracleContext.path == kwargs['path']))



class Database(SoftwareElement):
	"""Defines the database object for the database

	Table :
	  |  database
	Column :
	  |  object_id FK(software_element.object_id) PK
	"""

	__tablename__ = 'database'
	__table_args__ = {'schema':'data'}
	object_id =  Column(None, ForeignKey(SoftwareElement.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'database', 'inherit_condition': object_id == SoftwareElement.object_id}


class Postgres(Database):
	"""Defines the postgres object for the database

	Table :
	  |  postgres
	Columns :
	  |  object_id FK(database.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  postgres_constraint(container, path)
	"""

	__tablename__ = 'postgres'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "path" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='postgres_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(Database.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	container_relationship = relationship('Node', backref = backref('postgres_objects', cascade = 'all, delete'), foreign_keys = 'Postgres.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'postgres', 'inherit_condition': object_id == Database.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(Postgres.container == kwargs['container'], Postgres.path == kwargs['path']))


class DB2(Database):
	"""Defines the db2 object for the database

	Table :
	  |  db2
	Columns :
	  |  object_id FK(database.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  db2_constraint(container, path)
	"""

	__tablename__ = 'db2'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "path" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='db2_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(Database.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	container_relationship = relationship('Node', backref= backref('db2_objects', cascade = 'all, delete'), foreign_keys = 'DB2.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'db2', 'inherit_condition': object_id == Database.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(DB2.container == kwargs['container'], DB2.path == kwargs['path']))


class MySQL(Database):
	"""Defines the mysql object for the database

	Table :
	  |  mysql
	Columns :
	  |  object_id FK(database.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  mysql_constraint(container, path)
	"""

	__tablename__ = 'mysql'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "path" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='mysql_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(Database.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	container_relationship = relationship('Node', backref = backref('mysql_objects', cascade = 'all, delete'), foreign_keys = 'MySQL.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'mysql', 'inherit_condition': object_id == Database.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(MySQL.container == kwargs['container'], MySQL.path == kwargs['path']))


class MariaDB(Database):
	"""Defines the mariadb object for the database

	Table :
	  |  mariadb
	Columns :
	  |  object_id FK(database.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  mariadb_constraint(container, path)
	"""

	__tablename__ = 'mariadb'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "path" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='mariadb_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(Database.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	container_relationship = relationship('Node', backref = backref('mariadb_objects', cascade = 'all, delete'), foreign_keys = 'MariaDB.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'mariadb', 'inherit_condition': object_id == Database.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(MariaDB.container == kwargs['container'], MariaDB.path == kwargs['path']))


class SqlServer(Database):
	"""Defines the sqlserver object for the database

	Table :
	  |  sqlserver
	Columns :
	  |  object_id FK(database.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  sqlserver_constraint(container, path)
	"""

	__tablename__ = 'sqlserver'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "path" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='sqlserver_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(Database.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	container_relationship = relationship('Node', backref = backref('sqlserver_objects', cascade = 'all, delete'), foreign_keys = 'SqlServer.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'sqlserver', 'inherit_condition': object_id == Database.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(SqlServer.container == kwargs['container'], SqlServer.path == kwargs['path']))


class Vertica(Database):
	"""Defines the vertica object for the database

	Table :
	  |  vertica
	Columns :
	  |  object_id FK(database.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  vertica_constraint(container, path)
	"""

	__tablename__ = 'vertica'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "path" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='vertica_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(Database.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	container_relationship = relationship('Node', backref = backref('vertica_objects', cascade = 'all, delete'), foreign_keys = 'Vertica.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'vertica', 'inherit_condition': object_id == Database.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(Vertica.container == kwargs['container'], Vertica.path == kwargs['path']))


class Oracle(Database):
	"""Defines the oracle object for the database

	Table :
	  |  oracle
	Columns :
	  |  object_id FK(database.object_id) PK
	  |  container FK(node.object_id)
	  |  path [String(512)]
	Constraints :
	  |  oracle_constraint(container, path)
	"""

	__tablename__ = 'oracle'
	_constraints = ['container', 'path']
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name ='oracle_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(Database.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	path = Column(String(512), nullable=False)
	name = Column(String(128))
	version = Column(String(128))
	container_relationship = relationship('Node', backref = backref('oracle_objects', cascade = 'all, delete'), foreign_keys = 'Oracle.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'oracle', 'inherit_condition': object_id == Database.object_id}

	@classmethod
	def unique_filter(cls, query, **kwargs):
		return query.filter(and_(Oracle.container == kwargs['container'], Oracle.path == kwargs['path']))
