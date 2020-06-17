"""Objects in the archive schema.

The object model leverages SqlAlchemy (https://www.sqlalchemy.org/).

Classes defined for the 'archive' schema::

	Base - base
		|  Model - model
		|  ModelSnapshot - model_snapshot
		|  ModelSnapshotTimestamp - model_snapshot_timestamp
		|  ModelMetaDataSnapshot - model_metadata_snapshot
		|  DeletedObject - deleted_object

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Jun 1, 2018

"""
from sqlalchemy import Column, ForeignKey, String, DateTime, Integer, Sequence
from sqlalchemy.types import JSON, CHAR
from sqlalchemy.sql import func
## from Open Content Platform
from database.schema.baseSchema import Base


class Model(Base):
	"""Defines a model entry for the archive schema.

	This table makes it easier to find out which models have archived content,
	without having to parse the model_snapshot table for a high level listing.

	Table :
	  |  model_snapshot
	Column :
	  |  object_id [CHAR(32)] PK
	  |  object_type [String(256)]
	  |  time_stamp [DateTime]
	  |  data [JSON]
	"""

	__tablename__ = 'model'
	__table_args__ = {"schema": "archive"}
	object_id = Column(CHAR(32), primary_key=True)
	object_type = Column(String(256), nullable=True)
	time_stamp = Column(DateTime(timezone=True), server_default=func.now())
	caption = Column(String(512), nullable=True)
	data = Column(JSON, nullable=True)
	meta_data = Column(JSON, nullable=True)
	object_created_by = Column(String(128), nullable=True)


class ModelMetaDataSnapshot(Base):
	"""Defines a model snapshot for the archive schema.

	Model snapshots are point-in-time captures of a model. Models can be of any
	object type, but the usual types are those specifically ITSM based:
	Service, Application, and Function.

	Table :
	  |  model_metadata_snapshot
	Column :
	  |  object_id [CHAR(32)] PK
	  |  object_type [String(256)]
	  |  time_stamp [DateTime]
	  |  data [JSON]
	"""

	__tablename__ = 'model_metadata_snapshot'
	__table_args__ = {"schema": "archive"}
	object_id = Column(CHAR(32), primary_key=True)
	timestamp_id = Column(Integer, primary_key=True)
	time_stamp = Column(DateTime(timezone=True), server_default=func.now())
	meta_data = Column(JSON, nullable=True)
	object_created_by = Column(String(128), nullable=True)


class ModelSnapshot(Base):
	"""Defines a model snapshot for the archive schema.

	Model snapshots are point-in-time captures of a model. Models can be of any
	object type, but the usual types are those specifically ITSM based:
	Service, Application, and Function.

	Table :
	  |  model_snapshot
	Column :
	  |  object_id [CHAR(32)] PK
	  |  timestamp_id [Integer] PK
	  |  object_type [String(256)]
	  |  time_stamp [DateTime]
	  |  data [JSON]
	"""

	__tablename__ = 'model_snapshot'
	__table_args__ = {"schema": "archive"}
	object_id = Column(CHAR(32), primary_key=True)
	timestamp_id = Column(Integer, primary_key=True)
	time_stamp = Column(DateTime(timezone=True), server_default=func.now())
	data = Column(JSON, nullable=True)
	change_list = Column(JSON, nullable=True)
	object_created_by = Column(String(128), nullable=True)


class ModelSnapshotTimestamp(Base):
	"""Defines a model snapshot for the archive schema.

	Model snapshots are point-in-time captures of a model. Models can be of any
	object type, but the usual types are those specifically ITSM based:
	Service, Application, and Function.

	Table :
	  |  model_snapshot
	Column :
	  |  object_id [CHAR(32)] PK
	  |  object_type [String(256)]
	  |  time_stamp [DateTime]
	  |  data [JSON]
	"""

	__tablename__ = 'model_snapshot_timestamp'
	__table_args__ = {"schema": "archive"}
	object_id = Column(Integer, Sequence('seq_mstime_id', start=1, increment=1), autoincrement=True, primary_key=True)
	time_stamp = Column(DateTime(timezone=True), server_default=func.now())


# class DeletedObject(Base):
# 	"""Tracks objects deleted from the 'data' schema.
#
# 	Only special types of objects are kept for data retention purposes, usually
# 	just those required to reconstruct models and provide deltas over-time.
#
# 	Table :
# 	  |  deleted_object
# 	Column :
# 	  |  object_id [CHAR(32)] PK
# 	  |  object_type [String(256)]
# 	  |  time_stamp [DateTime]
# 	  |  data [JSON]
# 	"""
#
# 	__tablename__ = 'deleted_object'
# 	__table_args__ = {"schema": "archive"}
# 	object_id = Column(CHAR(32), primary_key=True)
# 	object_type = Column(String(256))
# 	time_stamp = Column(DateTime(timezone=True), server_default=func.now())
# 	data = Column(JSON, nullable=False)
