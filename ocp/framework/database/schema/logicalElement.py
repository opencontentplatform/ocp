"""Logical Elements.

Logical Elements are objects and collections created by ITSM processes. While
these are composed of technical peices/parts, these objects themselves are more
logical in nature and generally not "discoverable".

Classes defined are part of 'data' schema (indentation represents inheritance)::

	BaseObjects - base_objects
		LogicalElement - logical_element
			|  BusinessService - Business_service
			|  InfrastructureService - infrastructure_service
			|  BusinessApplication - business_appplication
			|  TechnicalApplication - technical_application
			|  ModelMetaData - model_meta_data
			|  ModelObject - model_object

"""
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Float
from sqlalchemy.types import Boolean, CHAR, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import and_, or_
from sqlalchemy import UniqueConstraint
from sqlalchemy import event
from database.schema.baseSchema import BaseObject

class LogicalElement(BaseObject):
	"""Defines a logical_element object for the database.

	Table :
	  |  logical_element
	Columns :
	  |  object_id [CHAR(32)] FK(base_object.object_id) PK
	  |  element_id [String(256)]
	  |  element_owner [String(256)]
	  |  support_team [String(256)]
	  |  synonyms [JSON]
	"""

	__tablename__ = 'logical_element'
	_constraints = ['element_id']
	_captionRule = {"condition": [ "element_id" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'logical_element_constraint'), {'schema':'data'})
	object_id = Column(None, ForeignKey(BaseObject.object_id), primary_key=True)
	element_id = Column(String(256), nullable = True)
	element_owner = Column(String(256), nullable = True)
	support_team = Column(String(256), nullable = True)
	synonyms = Column(JSON)
	short_name = Column(String(16), nullable=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity':'logical_element', 'inherit_condition':object_id == BaseObject.object_id}


class BusinessService(LogicalElement):
	"""Defines a business_service object for the database

	Table :
	  |  business_service
	Columns :
	  |  object_id [CHAR(32)] FK(logical_element.object_id) PK
	"""

	__tablename__ = 'business_service'
	_captionRule = {"condition": [ "name" ]}
	__table_args__ = {'schema':'data'}
	name = Column(String(256), nullable = False)
	object_id = Column(None, ForeignKey(LogicalElement.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'business_service', 'inherit_condition': object_id == LogicalElement.object_id}


class InfrastructureService(LogicalElement):
	"""Defines an infrastructure_service object for the database

	Table :
	  |  infrastructure_service
	Columns :
	  |  object_id [Char(32)] FK(logical_element.object_id) PK
	"""

	__tablename__ = 'infrastructure_service'
	__table_args__ = {'schema':'data'}
	_captionRule = {"condition": [ "name" ]}
	name = Column(String(256), nullable = False)
	object_id = Column(None, ForeignKey(LogicalElement.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'infrastructure_service', 'inherit_condition': object_id == LogicalElement.object_id}


class BusinessApplication(LogicalElement):
	"""Defines a business_application object for the database

	Table :
	  |  business_application
	Columns :
	  |  object_id [CHAR(32)] FK(logical_element.object_id) PK
	"""

	__tablename__ = 'business_application'
	__table_args__ = {'schema':'data'}
	_captionRule = {"condition": [ "name" ]}
	name = Column(String(256), nullable = False)
	object_id = Column(None, ForeignKey(LogicalElement.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'business_application', 'inherit_condition': object_id == LogicalElement.object_id}


class TechnicalApplication(LogicalElement):
	"""Defines a technical_applicaiton object for the database

	Table :
	  |  technical_application
	Columns :
	  |  object_id [CHAR(32)] FK(logical_element.object_id) PK
	"""

	__tablename__ = 'technical_application'
	__table_args__ = {'schema':'data'}
	_captionRule = {"condition": [ "name" ]}
	name = Column(String(256), nullable = False)
	object_id = Column(None, ForeignKey(LogicalElement.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'technical_application', 'inherit_condition': object_id == LogicalElement.object_id}


class ModelMetaData(BaseObject):
	"""Defines a model_meta_data object for the database

	Table :
	  |  model_meta_data
	Columns :
	  |  object_id [CHAR(32)] FK(logical_element.object_id) PK
	  |  tier4_alias [String(32)]
	  |  tier4_id [String(32)]
	  |  tier4_name [String(256)]
	  |  tier3_match_class [String(128)]
	  |  tier3_match_attribute [String(128)]
	  |  tier3_match_patterns [JSON]
	  |  tier3_create_class [String(128)]
	  |  tier2_name [String(256)]
	  |  tier2_qualifier [String(128)]
	  |  tier2_create_class [String(128)]
	  |  tier1_qualifier [String(128)]
	  |  tier1_match_class [String(128)]
	  |  tier1_match_attribute [String(128)]
	  |  tier1_match_patterns [JSON]
	  |  tier1_create_class [String(128)]
	  |  model_object_name [String(512)]
	  |  target_class [String(64)]
	  |  target_match_attribute [String(128)]
	  |  target_match_value [String(512)]
	Constraints:
	  | model_metadata_constraint(tier4_name, tier2_name, model_object_name)
	"""

	__tablename__ = 'model_meta_data'
	_constraints = ['tier4_name', 'tier2_name', 'model_object_name', 'target_match_class']
	_captionRule = {"condition": ["tier4_name", ": ", "tier2_name", ": ", "model_object_name", ": ", "target_match_class"]}
	__table_args__ = (UniqueConstraint(*_constraints, name = 'model_metadata_constraint'), {'schema':'data'})
	## Tier 4 Group (top level):
	##   App
	tier4_name = Column(String(256), nullable=False)
	tier4_alias = Column(String(32), nullable=False)
	tier4_id = Column(String(32), nullable=True)
	tier4_create_class = Column(String(128), nullable=False)
	## Tier 3 Group:
	##   App -> Environment
	tier3_match_class = Column(String(128), nullable=False)
	tier3_match_attribute = Column(String(128), nullable=False)
	tier3_match_patterns = Column(JSON, nullable=False)
	tier3_qualifier = Column(String(128), nullable=True)
	tier3_create_class = Column(String(128), nullable=False)
	## Tier 2 Group:
	##   App -> Environment -> Software
	tier2_name = Column(String(256), nullable=False)
	tier2_qualifier = Column(String(128), nullable=True)
	tier2_create_class = Column(String(128), nullable=False)
	## Tier 1 Group (bottom level):
	##   App -> Environment -> Software -> Location
	tier1_match_class = Column(String(128), nullable=False)
	tier1_match_attribute = Column(String(128), nullable=False)
	tier1_match_patterns = Column(JSON, nullable=False)
	tier1_qualifier = Column(String(128), nullable=True)
	tier1_create_class = Column(String(128), nullable=False)
	## Tier 0 (generated object instance)
	##   App -> Environment -> Software -> Location -> ModelObject
	model_object_name = Column(String(512), nullable=False)
	## Discoverable object to investigate for meta data matches
	#target_class = Column(String(64), nullable=True)
	target_match_class = Column(String(64), nullable=False)
	target_match_attribute = Column(String(128), nullable=False)
	target_match_patterns = Column(JSON, nullable=False)
	object_id = Column(None, ForeignKey(BaseObject.object_id), primary_key=True)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'model_meta_data', 'inherit_condition': object_id == BaseObject.object_id}


class ModelObject(BaseObject):
	"""Defines a model_object object for the database

	Table :
	  |  model_object
	Columns :
	  |  object_id FK(software_element.object_id) PK
	  |  container FK(node.object_id)
	  |  tier4_alias [String(32)]
	  |  tier4_id [String(32)]
	  |  tier4_name [String(256)]
	  |  tier3_name [String(256)]
	  |  tier2_name [String(256)]
	  |  tier1_name [String(256)]
	  |  model_object_name [String(512)]
	  |  target_class [String(64)]
	  |  target_match_attribute [String(128)]
	  |  target_match_value [String(512)]
	Constraints:
	  | model_object_constraint(model_object_name, tier4_name, tier2_name)
	"""

	__tablename__ = 'model_object'
	_constraints = ['target_container', 'model_object_name', 'tier4_name', 'tier2_name']
	_captionRule = {"condition": [ "model_object_name" ]}
	__table_args__ = (UniqueConstraint(*_constraints, name='model_object_constraint'), {'schema':'data'})
	object_id =  Column(None, ForeignKey(BaseObject.object_id), primary_key=True)
	tier4_alias = Column(String(32), nullable=False)
	tier4_id = Column(String(32), nullable=True)
	tier4_name = Column(String(256), nullable=False)
	tier3_name = Column(String(256), nullable=False)
	tier2_name = Column(String(256), nullable=False)
	tier1_name = Column(String(256), nullable=False)
	model_object_name = Column(String(512), nullable=False)
	target_match_class = Column(String(64), nullable=False)
	target_match_attribute = Column(String(128), nullable=False)
	target_match_value = Column(String(512), nullable=False)
	target_container = Column(String(256), nullable=False)
	__mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'model_object', 'inherit_condition': object_id == BaseObject.object_id}
