from sqlalchemy import Column, ForeignKey, String
from database.schema.systemElement import *

class FileCustom(SystemElement):
	"""Custom file object to track something for our company.

	Table :
	  |  file_custom
	Columns :
	  |  object_id FK(system_element.object_id) PK
	  |  container FK(node.object_id)
	  |  name [String(256)]
	  |  path [String(256)]
	  |  extension [String(256)]
	  |  file_created [String(256)]
	  |  file_modified [String(256)]
	  |  md5hash [String(256)]
	Constraints :
	  |  file_custom_constraint('name', 'container', 'path')
	"""

	__tablename__ = 'file_custom'
	_constraints = ['container', 'name', 'path']
	_captionRule = {'condition': [ 'name' ]}
	__table_args__ = {"schema":"data"}
	object_id = Column(None, ForeignKey(SystemElement.object_id), primary_key=True)
	container = Column(None, ForeignKey(Node.object_id), nullable=False)
	name = Column(String(256), nullable=False)
	path = Column(String(256), nullable=True)
	extension = Column(String(256), nullable=True)
	file_created = Column(String(256), nullable=True)
	file_modified = Column(String(256), nullable=True)
	md5hash = Column(String(256), nullable=True)
	container_relationship = relationship('Node', backref=backref('file_custom_objects', cascade='all, delete'), foreign_keys='FileCustom.container')
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'file_custom', 'inherit_condition': object_id == SystemElement.object_id}
