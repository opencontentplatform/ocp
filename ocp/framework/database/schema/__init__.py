"""
Database module details on SqlAlchemy attribute consumption:


From the class 'BaseObject' of baseSchema.py:

  *  weak_first_objects = relationship('WeakLink', backref='weak_second_object',
     cascade='all, delete', cascade_backrefs= False,
     primaryjoin='BaseObject.object_id == WeakLink.second_id')

     - Collection of class instances pertaining to the parent/top side of a
       weak directional relationship. So in the example [Node --> IpAddress],
       this would contain any Nodes weakly linked to a specific IpAddress.

  *  weak_second_objects = relationship('WeakLink', backref='weak_first_object',
     cascade='all, delete', cascade_backrefs= False,
     primaryjoin='BaseObject.object_id == WeakLink.first_id')

     - Collection of class instances pertaining to the child/bottom side of a
       weak directional relationship. So in the example [Node --> IpAddress],
       this would contain any IpAddresses weakly linked to a specific Node.

  *  strong_first_objects = relationship('StrongLink',
     backref='strong_second_object', cascade='all, delete',
     cascade_backrefs=False,
     primaryjoin='BaseObject.object_id == StrongLink.second_id')

     - A single class instance pertaining to the parent/top side of a strong
       directional relationship. So in the example [Node --> SNMP], this
       would contain the container Node strongly linked to a specific SNMP.

  *  strong_second_objects = relationship('StrongLink',
     backref='strong_first_object', cascade='all, delete',
     cascade_backrefs=False,
     primaryjoin='BaseObject.object_id == StrongLink.first_id')

     - Collection of class instances pertaining to the child/bottom side of a
       strong directional relationship. So in the example [Node --> SNMP], this
       would contain any SNMPs strongly linked to the container Node.


Attribute explanation for the above relationship fields:

  *  argument = 'WeakLink'

     - This mapped class or actual Mapper instance, is a named Python class
       representing the database table in which the relationship is created.

  *  backref = 'weak_second_object'

     - SQLAlchemy specific field present in the link Mapper, which triggers an
       append operation on 'weak_first_objects' in the related record.

  *  cascade = 'all, delete'

     - This is used to remove the record from the link table when the object
       from baseObject is deleted.

  *  cascade_backrefs = False

     - This avoids the deletion of instance of type BaseObject or its children
       when an entry from the link gets deleted.

  *  primaryjoin = 'BaseObject.object_id == WeakLink.second_id'

     - Since all the fields refer to an entry in BaseObject.object_id an
       explicit join condition is placed to avoid conflicts, meaning
       WeakLink.second_id will do a join with BaseObject.object_id and create a
       collection for second_object.weak_first_objects present in baseObject or
       its children.


From the class BaseLink of linkschema.py:

  *  orl1 = relationship('BaseObject', foreign_keys=first_id)
  *  orl2 = relationship('BaseObject', foreign_keys=second_id)

  .. note::

    This is required for SqlAlchemy to point at the same top-level table and
    same column in join inheritance (e.g. BaseObject.object_id). Without this
    definition you get errors with multiple FK references to the same column.


Attributes pulled from the class 'Node' of node.py::

  *  _constraints = ['hostname', 'domain']

     - This list contains the unique constraints available in the database table,
       which are really the PK but for SqlAlchemy Join table inheritance to work
       we make these 'unique constraints' and the object_id the 'primary key'.

  *  __table_args__ = (UniqueConstraint(*_constraints, name='node_constraint'),
     {"schema":"data"})

     - This holds database table level details like unique constraints and the
       schema name.

  *  object_id = Column(CHAR(32), ForeignKey(BaseObject.object_id),
     primary_key=True)

     - This is the primary key for the table that enables Join table inheritance.

  *  __mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'node',
     'inherit_condition': object_id == BaseObject.object_id}

     - This is used by the SQLAlchemy side to set up the Join table inheritance.

  *  @classmethod
     def unique_hash(cls,**kwargs):
        hashVal = reduce((lambda i,j: i+':==:'+j), [str(kwargs[i]) for i in
        cls.constraints()])
        return hashVal

     - Hash function for caching records based on _constraints.

  *  @classmethod
     def unique_filter(cls, query, **kwargs):
        return query.filter(and_(Node.hostname == kwargs['hostname'],
        Node.domain == kwargs['domain']))

     - This queries the database for objects matching the _constraints.


Attributes pulled from the class 'SNMP' of softwareElement.py::

  *  _constraints = ['container']
     - Again, this contains the unique constraints for this database table.
  *  __table_args__ = (UniqueConstraint(*_constraints, name = 'snmp_constraint')
     , {'schema':'data'})
     - Again, this holds database level details.
  *  object_id = Column(None, ForeignKey(Protocol.object_id), primary_key=True)
     - Again, this is the primary key for the table.
  *  container = Column(None, ForeignKey(Node.object_id), nullable = False)
     - This field signifies a strong (one-to-one) link between the Node table
       and this SNMP table.
  *  container_relationship = relationship('Node', backref =
     backref('snmp_objects', cascade = 'all, delete'), foreign_keys =
     'SNMP.container')
     - This contains the instance of the container object (Node record); it also
       creates an implicit relationship column in Node mapper called
       snmp_objects that holds the collection of SNMP objects based on FK
       reference.
  *  __mapper_args__ = {'with_polymorphic': '*', 'polymorphic_identity': 'snmp',
     'inherit_condition': object_id == Protocol.object_id}
     - Again, used by SQLAlchemy to set up join table inheritance.
  *  @classmethod
     def unique_filter(cls, query, **kwargs):
        return query.filter(SNMP.container == kwargs['container'])
    - Again, this queries the database for objects matching the _constraints.


Weak Link details::

  In the example [Node --> IpAddress], where there isn't a FK relationship
  between Node and IpAddress (it's just a weak link, not a strong container
  type reference), Node is the 'first_id' and Ipaddress is the 'second_id'
  in the weak_link table. The 'weak_second_objects' of Node will contain a
  collection of IpAddress instances that are linked to Node. Likewise, the
  'weak_first_objects' of IpAddress will contain a similar collection of Node
  instances linked to this IpAddress. This is from setting implicit attributes
  of the weak_link table while doing the table insert:
       link.weak_first_object = Node
       link.weak_second_object = ipAddress

Strong Link details::

  In the example [Node --> SNMP], where there is a FK relationship between
  Node and SNMP (it's a strong link with a required container reference),
  Node is the 'first_id' and SNMP is the 'second_id' in the strong_link
  table. The 'strong_second_objects' of Node will contain a collection of
  SNMP instances that are liked to Node with FK relationship. Likewise, the
  'strong_first_objects' of SNMP will contain the single Node instance linked
  to SNMP this SNMP. This is from setting implicit attributes of the
  strong_link table while doing the table insert:
       link.strong_first_object = Node
       link.strong_second_object = SNMP

.. note::

    weak_second_object, weak_first_object, strong_first_object and
    strong_second_object are implicitly declared at BaseObject mapper.
"""
