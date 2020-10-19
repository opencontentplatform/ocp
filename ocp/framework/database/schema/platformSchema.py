"""Objects in the platform schema.

The object model leverages SqlAlchemy (https://www.sqlalchemy.org/).

Classes defined for the 'platform' schema::

	*  Realm - realm
	*  NetworkScope - network_scope
	*  RealmScope - realm_scope
	*  ProtocolSnmp - protocol_snmp
	*  ProtocolWmi - protocol_wmi
	*  ProtocolSsh - protocol_ssh
	*  ProtocolPowerShell - protocol_powershell
	*  ProtocolRestApi - protocol_rest_api
	*  ConfigGroups - config_groups
	*  ConfigDefault - config_default
	*  OsParameters - os_parameters
	*  ContentPackage - content_package
	*  ContentPackageFile - content_package_file
	*  TriggerType - trigger_type
	*  JobContentGathering - job_content_gathering
	*  JobUniversal - job_universal
	*  JobServerSide - job_server_side
	*  EndpointQuery - endpoint_query
	*  ApiConsumerAccess - api_access_consumer
	*  ConsumerEndpoint - consumer_endpoint
	*  ApiAccess - api_access
	*  ServiceContentGatheringEndpoint - service_content_gathering_endpoint
	*  ServiceResultProcessingEndpoint - service_result_processing_endpoint
	*  ServiceUniversalJobEndpoint - service_universal_job_endpoint
	*  ServiceContentGatheringHealth - service_content_gathering_health
	*  ServiceResultProcessingHealth - service_result_processing_health
	*  ServiceUniversalJobHealth - service_universal_job_health
	*  ContentGatheringResults - content_gathering_results
	*  UniversalJobResults - universal_job_results
	*  ServerSideResults - server_side_results
	*  ContentGatheringServiceResults - service_results_content_gathering
	*  UniversalJobServiceResults - service_results_universal_job
	*  QueryResults - query_results
	*  QueryDefinition - query_definition
	*  CachedQuery - cached_query
	*  CachedQueryChunk - cached_query_chunk

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Jul 24, 2017
	  1.1 : (CS) Split out to enable use of multiple files, Oct 3, 2017
	  1.2 : (CS) Added QueryResults, Oct 17, 2018
	  1.3 : (CS) Added UniversalJob classes for clients, Aug 21, 2019

"""
import sys, traceback, logging, os, uuid
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Float
from sqlalchemy import Sequence, and_, or_
from sqlalchemy.types import JSON, Boolean, CHAR, Numeric, LargeBinary, ARRAY
## from Open Content Platform
from database.schema.baseSchema import Base, UniqueMixin
from sqlalchemy.sql import func


class Realm(UniqueMixin, Base):
	"""Defines a realm object for the database.

	Table :
	  |  realm
	Column :
	  |  name [String(256)] (PK)
	"""

	__tablename__ = 'realm'
	__table_args__ = {"schema":"platform"}
	name = Column(String(256), primary_key=True)
	## object_id required when using UniqueMixin
	object_id = Column(CHAR(32), primary_key=False, default=lambda :uuid.uuid4().hex)

	@classmethod
	def unique_hash(cls, name):
		return name

	@classmethod
	def unique_filter(cls, query, name):
		return query.filter(Realm.name == name)


class NetworkScope(Base):
	"""Defines a user created scope for the database.

	Scope entries are JSON objects that define ip/network ranges.

	Table :
	  |  network_scope
	Column :
	  |  object_id [Integer]
	  |  realm [String(256)] FK(realm.name)
	  |  active [Boolean]
	  |  description [String(256)]
	  |  count [Integer]
	  |  data [JSON]
	  |  transformed [JSON]
	"""

	__tablename__ = 'network_scope'
	__table_args__ = {"schema":"platform"}
	object_id = Column(Integer, Sequence('seq_ns_id', start=1, increment=1), autoincrement=True, primary_key=True)
	realm = Column(None, ForeignKey(Realm.name))
	active = Column(Boolean, default=True)
	description = Column(String(256), nullable=True)
	count = Column(Numeric, nullable=False)
	data = Column(JSON, nullable=False)
	transformed = Column(JSON, nullable=False)
	object_created_by = Column(String(128), nullable=True)
	time_created = Column(DateTime(timezone=True), default=func.now())


class RealmScope(Base):
	"""Defines a scope created by the system off entries in NetworkScope.

	Scope entries are JSON objects that define ip/network ranges.

	Table :
	  |  realm_scope
	Column :
	  |  object_id [CHAR(32)]
	  |  realm [String(256)] FK(realm.name) (PK)
	  |  count [Integer]
	  |  data [JSON]
	"""

	__tablename__ = 'realm_scope'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), default=lambda :uuid.uuid4().hex)
	realm = Column(None, ForeignKey(Realm.name), primary_key=True)
	count = Column(Numeric, nullable=False)
	data = Column(JSON, nullable=False)


class ProtocolBase(Base):
	"""Defines an abstract protocol object.

	Table :
	  |  protocol
	Columns :
	  |  object_id [Integer] (PK)
	  |  realm [String(256)] FK(realm.name) (PK)
	  |  credential_group [String(256)]
	  |  description [String(256)]
	  |  port [Integer]
	  |  active [Boolean]
	"""

	__tablename__ = 'protocol_base'
	__table_args__ = {"schema":"platform"}
	object_id = Column(Integer, Sequence('seq_protocol_id', start=1, increment=1), autoincrement=True, primary_key=True)
	realm = Column(None, ForeignKey(Realm.name))
	credential_group = Column(String(256), nullable=True)
	description = Column(String(256), nullable=True)
	port = Column(Integer, nullable=True)
	active = Column(Boolean, default=True)
	time_created = Column(DateTime(timezone=True), default=func.now())
	time_updated = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
	object_created_by = Column(String(128), nullable=True)
	object_updated_by = Column(String(128), nullable=True)



class ProtocolSnmp(ProtocolBase):
	"""Defines an SNMP protocol object for the database.

	Table :
	  |  protocol_snmp
	Columns :
	  |  version [String(256)]
	  |  community_string [String(256)]
	"""

	__tablename__ = 'protocol_snmp'
	__table_args__ = {"schema":"platform"}
	object_id = Column(None, ForeignKey(ProtocolBase.object_id), primary_key=True)
	version = Column(String(256), nullable=False)
	community_string = Column(String(256), nullable=False)


class ProtocolWmi(ProtocolBase):
	"""Defines an SSH protocol object for the database.

	Table :
	  |  protocol_wmi
	Columns :
	  |  user [String(256)]
	  |  password [String(256)]
	"""

	__tablename__ = 'protocol_wmi'
	__table_args__ = {"schema":"platform"}
	object_id = Column(None, ForeignKey(ProtocolBase.object_id), primary_key=True)
	user = Column(String(256), nullable=False)
	password = Column(String(256), nullable=False)


class ProtocolShell(ProtocolBase):
	"""Defines an abstract Shell protocol object (parent for shells).

	This allows jobs to select a shell protocol without specifying which.

	Table :
	  |  protocol_shell
	"""

	__tablename__ = 'protocol_shell'
	__table_args__ = {"schema":"platform"}
	object_id = Column(None, ForeignKey(ProtocolBase.object_id), primary_key=True)


class ProtocolSsh(ProtocolShell):
	"""Defines an SSH protocol object for the database.

	Table :
	  |  protocol_ssh
	Columns :
	  |  user [String(256)]
	  |  password [String(256)]
	  |  token [String(256)]
	"""

	__tablename__ = 'protocol_ssh'
	__table_args__ = {"schema":"platform"}
	object_id = Column(None, ForeignKey(ProtocolShell.object_id), primary_key=True)
	user = Column(String(256), nullable=False)
	password = Column(String(256), nullable=False)
	use_key = Column(Boolean, default=False)
	key_filename = Column(String(256), nullable=True)
	key_passphrase = Column(String(256), nullable=True)


class ProtocolPowerShell(ProtocolShell):
	"""Defines a PowerShell protocol object for the database.

	Table :
	  |  protocol_powershell
	Columns :
	  |  user [String(256)]
	  |  password [String(256)]
	"""

	__tablename__ = 'protocol_powershell'
	__table_args__ = {"schema":"platform"}
	object_id = Column(None, ForeignKey(ProtocolShell.object_id), primary_key=True)
	user = Column(String(256), nullable=False)
	password = Column(String(256), nullable=False)


class ProtocolRestApi(ProtocolBase):
	"""Defines a REST API protocol object.

	Table :
	  |  protocol_rest_api
	"""

	__tablename__ = 'protocol_rest_api'
	__table_args__ = {"schema":"platform"}
	object_id = Column(None, ForeignKey(ProtocolBase.object_id), primary_key=True)
	user = Column(String(256), nullable=True)
	password = Column(String(256), nullable=True)
	token = Column(String(256), nullable=True)
	client_id = Column(String(256), nullable=True)
	client_secret = Column(String(256), nullable=True)


class ConfigGroups(UniqueMixin, Base):
	"""Defines a config_groups object for the database.

	Table :
	  |  config_groups
	Columns :
	  |  object_id [CHAR(32)]
	  |  realm  [String(256)] FK(realm.name) PK
	  |  content [JSON]
	"""

	__tablename__ = 'config_groups'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	realm = Column(None, ForeignKey(Realm.name), primary_key=True)
	content = Column(JSON, nullable=False)
	time_created = Column(DateTime(timezone=True), server_default=func.now())
	time_updated = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
	object_created_by = Column(String(128), nullable=True)
	object_updated_by = Column(String(128), nullable=True)
	@classmethod
	def unique_hash(cls, realm, content):
		return realm
	@classmethod
	def unique_filter(cls, query, realm, content):
		return query.filter(ConfigGroup.realm == realm)


class ConfigDefault(UniqueMixin, Base):
	"""Defines a default_config object for the database.

	Table :
	  |  default_config
	Columns :
	  |  object_id [CHAR(32)]
	  |  realm  [String(256)] FK(realm.name) PK
	  |  content [JSON]
	"""

	__tablename__ = 'config_default'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	realm = Column(None, ForeignKey(Realm.name), primary_key=True)
	content = Column(JSON, nullable=False)
	time_created = Column(DateTime(timezone=True), server_default=func.now())
	time_updated = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
	object_created_by = Column(String(128), nullable=True)
	object_updated_by = Column(String(128), nullable=True)
	@classmethod
	def unique_hash(cls, realm, content):
		return realm
	@classmethod
	def unique_filter(cls, query, realm, content):
		return query.filter(DefaultConfig.realm == realm)


class OsParameters(UniqueMixin, Base):
	"""Defines a os_parameters object for the database.

	Table :
	  |  os_parameters
	Columns :
	  |  object_id [CHAR(32)]
	  |  realm  [String(256)] FK(realm.name) PK
	  |  content [JSON]
	"""

	__tablename__ = 'os_parameters'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	realm = Column(None, ForeignKey(Realm.name), primary_key=True)
	content = Column(JSON, nullable=False)
	time_created = Column(DateTime(timezone=True), server_default=func.now())
	time_updated = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
	object_created_by = Column(String(128), nullable=True)
	object_updated_by = Column(String(128), nullable=True)
	@classmethod
	def unique_hash(cls, realm, content):
		return realm
	@classmethod
	def unique_filter(cls, query, realm, content):
		return query.filter(OsParameters.realm == realm)


class ContentPackage(Base):
	"""Defines a content package object for the database.

	Table :
	  |  content_package
	Column :
	  |  name [String(256)] (PK)
	"""

	__tablename__ = 'content_package'
	__table_args__ = {"schema":"platform"}
	name = Column(String(256), primary_key=True)
	#path = Column(ARRAY(String, dimensions=1), nullable=False)
	path = Column(String(256), nullable=False)
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	snapshot = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	system = Column(String(64), nullable=False)
	files = Column(JSON, nullable=True)
	time_created = Column(DateTime(timezone=True), server_default=func.now())
	time_updated = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
	object_created_by = Column(String(128), nullable=True)
	object_updated_by = Column(String(128), nullable=True)


class ContentPackageFile(Base):
	"""Defines a module_file object for the database.

	Table :
	  |  content_package_file
	Column :
	  |  name [String(256)] (PK)
	"""

	__tablename__ = 'content_package_file'
	__table_args__ = {"schema":"platform"}
	package = Column(None, ForeignKey(ContentPackage.name), primary_key=True)
	name = Column(String(256), primary_key=True)
	path = Column(String(512), primary_key=True)
	size = Column(Integer, nullable=False)
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	content = Column(LargeBinary, nullable=False)
	file_hash = Column(CHAR(32), nullable=False)
	time_created = Column(DateTime(timezone=True), server_default=func.now())
	time_updated = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
	object_created_by = Column(String(128), nullable=True)
	object_updated_by = Column(String(128), nullable=True)


class TriggerType(UniqueMixin, Base):
	"""Defines a trigger_type object for the database.

	Table :
	  |  trigger_type
	Column :
	  |  name [String(256)] (PK)
	"""

	__tablename__ = 'trigger_type'
	__table_args__ = {"schema":"platform"}
	name = Column(String(256), primary_key=True)
	object_id = Column(CHAR(32), primary_key=False, default=lambda :uuid.uuid4().hex)
	@classmethod
	def unique_hash(cls, name):
		return name
	@classmethod
	def unique_filter(cls, query, name):
		return query.filter(TriggerType.name == name)


class JobContentGathering(UniqueMixin, Base):
	"""Defines a job_content_gathering object for the database.

	Table :
	  |  job_content_gathering
	Columns :
	  |  object_id [CHAR(32)]
	  |  name [String(256)] PK
	  |  package [String(256)] FK(content_package.name)
	  |  realm  [String(256)] FK(realm.name)
	  |  active [Boolean]
	  |  content [JSON]
	  |  time_created [DateTime]
	  |  time_updated [DateTime]
	"""

	__tablename__ = 'job_content_gathering'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	name = Column(String(256), primary_key=True)
	package = Column(None, ForeignKey(ContentPackage.name), nullable=False)
	realm = Column(None, ForeignKey(Realm.name), nullable=False)
	active = Column(Boolean, default=False)
	content = Column(JSON, nullable=False)
	object_created_by = Column(String(128), nullable=True)
	object_updated_by = Column(String(128), nullable=True)
	time_created = Column(DateTime(timezone=True), default=func.now())
	time_updated = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
	@classmethod
	def unique_hash(cls, name, module, realm, active, content):
		return name
	@classmethod
	def unique_filter(cls, query, name, module, realm, active, content):
		return query.filter(JobContentGathering.name == name)


class JobUniversal(UniqueMixin, Base):
	"""Defines a job_universal object for the database.

	Table :
	  |  job_universal
	Columns :
	  |  object_id [CHAR(32)]
	  |  name [String(256)] PK
	  |  package [String(256)] FK(content_package.name)
	  |  realm  [String(256)] FK(realm.name)
	  |  active [Boolean]
	  |  content [JSON]
	  |  time_created [DateTime]
	  |  time_updated [DateTime]
	"""

	__tablename__ = 'job_universal'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	name = Column(String(256), primary_key=True)
	package = Column(None, ForeignKey(ContentPackage.name), nullable=False)
	realm = Column(None, ForeignKey(Realm.name), nullable=False)
	active = Column(Boolean, default=False)
	content = Column(JSON, nullable=False)
	object_created_by = Column(String(128), nullable=True)
	object_updated_by = Column(String(128), nullable=True)
	time_created = Column(DateTime(timezone=True), default=func.now())
	time_updated = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
	@classmethod
	def unique_hash(cls, name, module, realm, active, content):
		return name
	@classmethod
	def unique_filter(cls, query, name, module, realm, active, content):
		return query.filter(JobUniversal.name == name)


class JobServerSide(UniqueMixin, Base):
	"""Defines a job_server_side object for the database.

	Table :
	  |  job_server_side
	Columns :
	  |  object_id [CHAR(32)]
	  |  name [String(256)] PK
	  |  package [String(256)] FK(content_package.name)
	  |  realm  [String(256)] FK(realm.name)
	  |  active [Boolean]
	  |  content [JSON]
	  |  time_created [DateTime]
	  |  time_updated [DateTime]
	"""

	__tablename__ = 'job_server_side'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	name = Column(String(256), primary_key=True)
	package = Column(None, ForeignKey(ContentPackage.name), nullable=False)
	realm = Column(None, ForeignKey(Realm.name), nullable=False)
	active = Column(Boolean, nullable=True, default=False)
	content = Column(JSON, nullable=False)
	object_created_by = Column(String(128), nullable=True)
	object_updated_by = Column(String(128), nullable=True)
	time_created = Column(DateTime(timezone=True), default=func.now())
	time_updated = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
	@classmethod
	def unique_hash(cls, name, module, realm, active, content):
		return name
	@classmethod
	def unique_filter(cls, query, name, module, realm, active, content):
		return query.filter(JobServerSide.name == name)


class EndpointQuery(UniqueMixin, Base):
	"""Defines a endpoint_query object for the database.

	Table :
	  |  endpoint_query
	Columns :
	  |  object_id [CHAR(32)]
	  |  name [String(256)] PK
	  |  json_query [JSON]
	  |  time_created [DateTime]
	  |  time_updated [DateTime]
	"""

	__tablename__ = 'endpoint_query'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	name = Column(String(256), primary_key=True)
	json_query = Column(JSON, nullable=False)
	object_created_by = Column(String(128), nullable=True)
	object_updated_by = Column(String(128), nullable=True)
	time_created = Column(DateTime(timezone=True), default=func.now())
	time_updated = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
	@classmethod
	def unique_hash(cls, name, json_query):
		return name
	@classmethod
	def unique_filter(cls, query, name, json_query):
		return query.filter(EndpointQuery.name == name)


class ApiConsumerAccess(Base):
	"""Defines an api_access_consumer object for the database.

	Table :
	  |  job_server
	Columns :
	  |  object_id [Integer] PK
	  |  key [String(32)]
	  |  name [CHAR(256)]
	  |  password [CHAR(256)]
	  |  owner [CHAR(256)]
	  |  active [Boolean]
	  |  access_read [Boolean]
	  |  access_write [Boolean]
	  |  access_delete [Boolean]
	  |  access_admin [Boolean]
	  |  time_created [DateTime]
	  |  time_updated [DateTime]
	  |  object_created_by [CHAR(128)]
	  |  object_updated_by [CHAR(128)]
	"""

	__tablename__ = 'api_access_consumer'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), primary_key=True, default=lambda :uuid.uuid4().hex)
	key = Column(CHAR(32), nullable=False, unique=True)
	password = Column(String(256), nullable=True)
	name = Column(String(256), nullable=False, unique=True)
	owner = Column(String(256), nullable=False)
	active = Column(Boolean, default=True)
	access_read = Column(Boolean, default=True)
	access_write = Column(Boolean, default=False)
	access_delete = Column(Boolean, default=False)
	access_admin = Column(Boolean, default=False)
	time_created = Column(DateTime(timezone=True), default=func.now())
	time_updated = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
	object_created_by = Column(String(128), nullable=True)
	object_updated_by = Column(String(128), nullable=True)


class ConsumerEndpoint(Base):
	"""Defines a service_content_gathering_endpoint object for the database.

	Table :
	  |  service_content_gathering_endpoint
	Columns :
	  |  object_id [CHAR(32)]
	  |  name [String(256)] PK
	  |  remote_addr [CHAR(128)]
	  |  access_route [CHAR(128)]
	"""

	__tablename__ = 'consumer_endpoint'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	name = Column(String(256), primary_key=True)
	remote_addr = Column(String(128), nullable=False)
	access_route = Column(String(128), nullable=False)


class ApiAccess(Base):
	"""Defines an api_access object for the database.

	Table :
	  |  job_server
	Columns :
	  |  object_id [Integer] PK
	  |  key [String(32)]
	  |  name [CHAR(256)]
	"""

	__tablename__ = 'api_access'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	key = Column(CHAR(256), primary_key=True)
	name = Column(String(256), nullable=False, unique=True)


class EndpointPlatformAttributes():
	"""Mixin containing set of standard attributes for services endpoint classes.

	Columns :
	  |  platform_type [String(256)]
	  |  platform_system [String(256)]
	  |  platform_machine [String(256)]
	  |  platform_version [String(256)]
	  |  cpu_type [String(256)]
	  |  cpu_count [String(256)]
	  |  memory_total [String(256)]
	"""

	platform_type = Column(String(256), nullable=True)
	platform_system = Column(String(256), nullable=True)
	platform_machine = Column(String(256), nullable=True)
	platform_version = Column(String(256), nullable=True)
	cpu_type = Column(String(256), nullable=True)
	cpu_count = Column(String(256), nullable=True)
	memory_total = Column(String(256), nullable=True)


class ServiceContentGatheringEndpoint(EndpointPlatformAttributes, Base):
	"""Defines a service_content_gathering_endpoint object for the database.

	Table :
	  |  service_content_gathering_endpoint
	Columns :
	  |  object_id [CHAR(32)]
	  |  name [String(256)] PK
	  |  platform_type [String(256)]
	  |  platform_system [String(256)]
	  |  platform_machine [String(256)]
	  |  platform_version [String(256)]
	  |  cpu_type [String(256)]
	  |  cpu_count [String(256)]
	  |  memory_total [String(256)]
	"""

	__tablename__ = 'service_content_gathering_endpoint'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	name = Column(String(256), primary_key=True)


class ServiceResultProcessingEndpoint(EndpointPlatformAttributes, Base):
	"""Defines a service_result_processing_endpoint object for the database.

	Table :
	  |  service_result_processing_endpoint
	Columns :
	  |  object_id [CHAR(32)]
	  |  name [String(256)] PK
	  |  platform_type [String(256)]
	  |  platform_system [String(256)]
	  |  platform_machine [String(256)]
	  |  platform_version [String(256)]
	  |  cpu_type [String(256)]
	  |  cpu_count [String(256)]
	  |  memory_total [String(256)]
	"""

	__tablename__ = 'service_result_processing_endpoint'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	name = Column(String(256), primary_key=True)


class ServiceUniversalJobEndpoint(EndpointPlatformAttributes, Base):
	"""Defines a service_universal_job_endpoint object for the database.

	Table :
	  |  service_universal_job_endpoint
	Columns :
	  |  object_id [CHAR(32)]
	  |  name [String(256)] PK
	  |  platform_type [String(256)]
	  |  platform_system [String(256)]
	  |  platform_machine [String(256)]
	  |  platform_version [String(256)]
	  |  cpu_type [String(256)]
	  |  cpu_count [String(256)]
	  |  memory_total [String(256)]
	"""

	__tablename__ = 'service_universal_job_endpoint'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	name = Column(String(256), primary_key=True)


class ServiceMonitoringEndpoint(EndpointPlatformAttributes, Base):
	"""Defines a service_monitoring_endpoint object for the database.

	Table :
	  |  service_monitoring_endpoint
	Columns :
	  |  object_id [CHAR(32)]
	  |  name [String(256)] PK
	  |  platform_type [String(256)]
	  |  platform_system [String(256)]
	  |  platform_machine [String(256)]
	  |  platform_version [String(256)]
	  |  cpu_type [String(256)]
	  |  cpu_count [String(256)]
	  |  memory_total [String(256)]
	"""

	__tablename__ = 'service_monitoring_endpoint'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	name = Column(String(256), primary_key=True)


class EndpointHealthAttributes():
	"""Mixin containing set of standard attributes for service health classes.

	Columns :
	  |  last_system_status [String(256)]
	  |  cpu_avg_utilization [String(256)]
	  |  memory_aprox_total [String(256)]
	  |  memory_aprox_avail [String(256)]
	  |  memory_percent_used [String(256)]
	  |  process_cpu_percent [String(256)]
	  |  process_memory [String(256)]
	  |  process_start_time [String(256)]
	  |  process_run_time [String(256)]
	"""

	last_system_status = Column(String(256), nullable=True)
	cpu_avg_utilization = Column(String(256), nullable=True)
	memory_aprox_total = Column(String(256), nullable=True)
	memory_aprox_avail = Column(String(256), nullable=True)
	memory_percent_used = Column(String(256), nullable=True)
	process_cpu_percent = Column(String(256), nullable=True)
	process_memory = Column(String(256), nullable=True)
	process_start_time = Column(String(256), nullable=True)
	process_run_time = Column(String(256), nullable=True)


class ServiceContentGatheringHealth(EndpointHealthAttributes, Base):
	"""Defines a service_content_gathering_health object for the database.

	Table :
	  |  service_content_gathering_health
	Columns :
	  |  object_id [CHAR(32)]
	  |  name [String(256)] PK
	  |  last_system_status [String(256)]
	  |  cpu_avg_utilization [String(256)]
	  |  memory_aprox_total [String(256)]
	  |  memory_aprox_avail [String(256)]
	  |  memory_percent_used [String(256)]
	  |  process_cpu_percent [String(256)]
	  |  process_memory [String(256)]
	  |  process_start_time [String(256)]
	  |  process_run_time [String(256)]
	"""

	__tablename__ = 'service_content_gathering_health'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	name = Column(String(256), primary_key=True)


class ServiceResultProcessingHealth(EndpointHealthAttributes, Base):
	"""Defines a service_result_processing_health object for the database.

	Table :
	  |  service_result_processing_health
	Columns :
	  |  object_id [CHAR(32)]
	  |  name [String(256)] PK
	  |  last_system_status [String(256)]
	  |  cpu_avg_utilization [String(256)]
	  |  memory_aprox_total [String(256)]
	  |  memory_aprox_avail [String(256)]
	  |  memory_percent_used [String(256)]
	  |  process_cpu_percent [String(256)]
	  |  process_memory [String(256)]
	  |  process_start_time [String(256)]
	  |  process_run_time [String(256)]
	"""

	__tablename__ = 'service_result_processing_health'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	name = Column(String(256), primary_key=True)


class ServiceUniversalJobHealth(EndpointHealthAttributes, Base):
	"""Defines a service_universal_job_health object for the database.

	Table :
	  |  service_universal_job_health
	Columns :
	  |  object_id [CHAR(32)]
	  |  name [String(256)] PK
	  |  last_system_status [String(256)]
	  |  cpu_avg_utilization [String(256)]
	  |  memory_aprox_total [String(256)]
	  |  memory_aprox_avail [String(256)]
	  |  memory_percent_used [String(256)]
	  |  process_cpu_percent [String(256)]
	  |  process_memory [String(256)]
	  |  process_start_time [String(256)]
	  |  process_run_time [String(256)]
	"""

	__tablename__ = 'service_universal_job_health'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), unique=True, default=lambda :uuid.uuid4().hex)
	name = Column(String(256), primary_key=True)


class ContentGatheringServiceResults(Base):
	"""Defines a service_results_content_gathering object for the database.

	Table :
	  |  service_results_content_gathering
	Columns :
	  |  job [String(256)] PK
	  |  time_started [DateTime] PK
	  |  active_client_list [ARRAY]
	  |  active_client_count [Integer]
	  |  endpoint_count [Integer]
	  |  completed_count [Integer]
	  |  time_finished [DateTime]
	  |  time_elapsed [Float]
	  |  job_completed [Boolean]
	  |  count_per_client [JSON]
	"""

	__tablename__ = 'service_results_content_gathering'
	__table_args__ = {"schema":"platform"}
	job = Column(String(256), primary_key=True)
	#active_clients = Column(String(512), nullable=False)
	active_client_list = Column(ARRAY(String, dimensions=1), nullable=False)
	active_client_count = Column(Integer, default=0)
	endpoint_count = Column(Integer, default=0)
	completed_count = Column(Integer, default=0)
	time_started = Column(DateTime(timezone=True), primary_key=True)
	time_finished = Column(DateTime(timezone=True), nullable=True)
	time_elapsed = Column(Float, nullable=True)
	job_completed = Column(Boolean, default=False)
	count_per_client = Column(JSON, nullable=False)
	count_per_status = Column(JSON, nullable=False)


class UniversalJobServiceResults(Base):
	"""Defines a service_results_content_gathering object for the database.

	Table :
	  |  service_results_universal_job
	Columns :
	  |  job [String(256)] PK
	  |  time_started [DateTime] PK
	  |  active_client_list [ARRAY]
	  |  active_client_count [Integer]
	  |  endpoint_count [Integer]
	  |  completed_count [Integer]
	  |  time_finished [DateTime]
	  |  time_elapsed [Float]
	  |  job_completed [Boolean]
	  |  count_per_client [JSON]
	"""

	__tablename__ = 'service_results_universal_job'
	__table_args__ = {"schema":"platform"}
	job = Column(String(256), primary_key=True)
	#active_clients = Column(String(512), nullable=False)
	active_client_list = Column(ARRAY(String, dimensions=1), nullable=False)
	active_client_count = Column(Integer, default=0)
	endpoint_count = Column(Integer, default=0)
	completed_count = Column(Integer, default=0)
	time_started = Column(DateTime(timezone=True), primary_key=True)
	time_finished = Column(DateTime(timezone=True), nullable=True)
	time_elapsed = Column(Float, nullable=True)
	job_completed = Column(Boolean, default=False)
	count_per_client = Column(JSON, nullable=False)
	count_per_status = Column(JSON, nullable=False)


class ContentGatheringResults(Base):
	"""Defines a content_gathering_results object for the database.

	Table :
	  |  content_gathering_results
	Columns :
	  |  endpoint [String(256)] PK
	  |  job [String(256)] PK
	  |  status [String(32)]
	  |  messages [String(8096)]
	  |  client_name [String(256)]
	  |  time_started [DateTime]
	  |  time_finished [DateTime]
	  |  result_count [JSON]
	  |  date_first_invocation [DateTime]
	  |  date_last_invocation [DateTime]
	  |  date_last_success [DateTime]
	  |  date_last_failure [DateTime]
	  |  consecutive_jobs_passed [Integer]
	  |  consecutive_jobs_failed [Integer]
	  |  total_jobs_passed [Integer]
	  |  total_jobs_failed [Integer]
	  |  total_job_invocations [Integer]
	"""

	__tablename__ = 'content_gathering_results'
	__table_args__ = {"schema":"platform"}
	endpoint = Column(String(256), primary_key=True)
	job = Column(String(256), primary_key=True)
	status = Column(String(32), nullable=False)
	messages = Column(String(8096), nullable=True)
	client_name = Column(String(256), nullable=False)
	time_started = Column(DateTime(timezone=True))
	time_finished = Column(DateTime(timezone=True))
	time_elapsed = Column(Float, nullable=True)
	result_count = Column(JSON, nullable=False)
	date_first_invocation = Column(DateTime(timezone=True))
	date_last_invocation = Column(DateTime(timezone=True))
	date_last_success = Column(DateTime(timezone=True))
	date_last_failure = Column(DateTime(timezone=True))
	consecutive_jobs_passed = Column(Integer, default=0)
	consecutive_jobs_failed = Column(Integer, default=0)
	total_jobs_passed = Column(Integer, default=0)
	total_jobs_failed = Column(Integer, default=0)
	total_job_invocations = Column(Integer, default=0)


class UniversalJobResults(Base):
	"""Defines a universal_job_results object for the database.

	Table :
	  |  universal_job_results
	Columns :
	  |  endpoint [String(256)] PK
	  |  job [String(256)] PK
	  |  status [String(32)]
	  |  messages [String(8096)]
	  |  client_name [String(256)]
	  |  time_started [DateTime]
	  |  time_finished [DateTime]
	  |  result_count [JSON]
	  |  date_first_invocation [DateTime]
	  |  date_last_invocation [DateTime]
	  |  date_last_success [DateTime]
	  |  date_last_failure [DateTime]
	  |  consecutive_jobs_passed [Integer]
	  |  consecutive_jobs_failed [Integer]
	  |  total_jobs_passed [Integer]
	  |  total_jobs_failed [Integer]
	  |  total_job_invocations [Integer]
	"""

	__tablename__ = 'universal_job_results'
	__table_args__ = {"schema":"platform"}
	endpoint = Column(String(256), primary_key=True)
	job = Column(String(256), primary_key=True)
	status = Column(String(32), nullable=False)
	messages = Column(String(8096), nullable=True)
	client_name = Column(String(256), nullable=False)
	time_started = Column(DateTime(timezone=True))
	time_finished = Column(DateTime(timezone=True))
	time_elapsed = Column(Float, nullable=True)
	result_count = Column(JSON, nullable=False)
	date_first_invocation = Column(DateTime(timezone=True))
	date_last_invocation = Column(DateTime(timezone=True))
	date_last_success = Column(DateTime(timezone=True))
	date_last_failure = Column(DateTime(timezone=True))
	consecutive_jobs_passed = Column(Integer, default=0)
	consecutive_jobs_failed = Column(Integer, default=0)
	total_jobs_passed = Column(Integer, default=0)
	total_jobs_failed = Column(Integer, default=0)
	total_job_invocations = Column(Integer, default=0)


class ServerSideResults(Base):
	"""Defines a server_side_results object for the database.

	Table :
	  |  server_side_results
	Columns :
	  |  job [String(256)] PK
	  |  status [String(32)]
	  |  messages [String(8096)]
	  |  time_started [DateTime]
	  |  time_finished [DateTime]
	  |  time_elapsed [Float]
	"""

	__tablename__ = 'server_side_results'
	__table_args__ = {"schema":"platform"}
	job = Column(String(256), primary_key=True)
	status = Column(String(32), nullable=False)
	messages = Column(String(8096), nullable=True)
	time_started = Column(DateTime(timezone=True))
	time_finished = Column(DateTime(timezone=True))
	time_elapsed = Column(Float, nullable=True)


class QueryResults(Base):
	"""Defines a query_results object for the database.

	Table :
	  |  query_results
	Columns :
	  |  job [String(256)] PK
	  |  status [String(32)]
	  |  messages [String(8096)]
	  |  time_started [DateTime]
	  |  time_finished [DateTime]
	  |  time_elapsed [Float]
	"""

	__tablename__ = 'query_results'
	__table_args__ = {"schema":"platform"}
	job = Column(String(256), primary_key=True)
	status = Column(String(32), nullable=False)
	messages = Column(String(8096), nullable=True)
	time_started = Column(DateTime(timezone=True))
	time_finished = Column(DateTime(timezone=True))
	time_elapsed = Column(Float, nullable=True)


class QueryDefinition(Base):
	"""Defines a query_definition table storing custom sql queries.
	Table :
	  |  object_id [Char(32)] pk
	  |  name [String(256)] unique
	  |  json_query [Json]
	  |  object_created_by [String(128)]
	  |  object_updated_by [String(128)]
	  |  time_created [DateTime]
	  |  time_updated [DateTime]
	  |  description [String(1024)]
	"""
	__tablename__ = 'query_definition'
	_constraints = ['name']
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), primary_key=True, default=lambda :uuid.uuid4().hex)
	name = Column(String(256),unique=True, nullable=False)
	json_query = Column(JSON, nullable=False)
	time_created = Column(DateTime(timezone=True), default=func.now())
	time_updated = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
	object_created_by = Column(String(128), nullable=True)
	object_updated_by = Column(String(128), nullable=True)
	description  = Column(String(1024))


class InputDrivenQueryDefinition(Base):
	"""Defines a query_definition table storing custom sql queries.
	Table :
	  |  object_id [Char(32)] pk
	  |  name [String(256)] unique
	  |  json_query [Json]
	  |  object_created_by [String(128)]
	  |  object_updated_by [String(128)]
	  |  time_created [DateTime]
	  |  time_updated [DateTime]
	  |  description [String(1024)]
	"""
	__tablename__ = 'input_driven_query_definition'
	_constraints = ['name']
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), primary_key=True, default=lambda :uuid.uuid4().hex)
	name = Column(String(256),unique=True, nullable=False)
	json_query = Column(JSON, nullable=False)
	time_created = Column(DateTime(timezone=True), default=func.now())
	time_updated = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
	object_created_by = Column(String(128), nullable=True)
	object_updated_by = Column(String(128), nullable=True)
	description  = Column(String(1024))


class CachedQuery(Base):
	"""Defines a cached_query object for the database.

	Table :
	  |  cached_query
	Columns :
	  |  object_id [CHAR(32)] PK
	  |  chunk_count [Integer]
	  |  time_started [DateTime]
	  |  time_finished [DateTime]
	  |  time_elapsed [Float]
	"""

	__tablename__ = 'cached_query'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), primary_key=True)
	object_created_by = Column(String(128), nullable=True)
	chunk_count = Column(Integer, nullable=True)
	original_size_in_kb = Column(Integer, nullable=True)
	chunk_size_requested = Column(Integer, nullable=True)
	time_started = Column(DateTime(timezone=True))
	time_finished = Column(DateTime(timezone=True), nullable=True)
	time_elapsed = Column(Float, nullable=True)


class CachedQueryChunk(Base):
	"""Defines a cached_query_chunk object for the database.

	Table :
	  |  cached_query_chunk
	Columns :
	  |  object_id [CHAR(32)] PK
	  |  chunk_id [Integer] PK
	  |  data [JSON]
	"""

	__tablename__ = 'cached_query_chunk'
	__table_args__ = {"schema":"platform"}
	object_id = Column(CHAR(32), primary_key=True)
	chunk_id = Column(Integer, primary_key=True)
	chunk_size_in_kb = Column(Integer, nullable=True)
	data = Column(JSON, nullable=False)
