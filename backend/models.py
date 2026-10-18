"""SQLAlchemy ORM-модели приложения."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow():
    """Текущее UTC-время без таймзоны (наивное) — простое и предсказуемое
    хранение и на SQLite, и на PostgreSQL."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Индексы для производительности
class _Indexes:
    # Частые запросы: поиск проектов по владельцу и группе
    pass


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    projects = relationship('Project', back_populates='owner')


class Project(Base):
    __tablename__ = 'projects'
    __table_args__ = (
        Index('ix_projects_owner_id', 'owner_id'),
        Index('ix_projects_group_id', 'group_id'),
        Index('ix_projects_folder_id', 'folder_id'),
        Index('ix_projects_updated_at', 'updated_at'),
    )
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    owner_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    group_id = Column(Integer, ForeignKey('groups.id', ondelete='SET NULL'), nullable=True)
    folder_id = Column(Integer, ForeignKey('catalog_folders.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    owner = relationship('User', back_populates='projects')
    group = relationship('Group')
    folder = relationship('CatalogFolder', back_populates='projects')
    nodes = relationship('Node', back_populates='project', cascade='all, delete-orphan')
    links = relationship('Link', back_populates='project', cascade='all, delete-orphan')
    connections = relationship('Connection', back_populates='project', cascade='all, delete-orphan')


class Node(Base):
    __tablename__ = 'nodes'
    __table_args__ = (
        Index('ix_nodes_project_id', 'project_id'),
        Index('ix_nodes_parent_id', 'parent_id'),
        Index('ix_nodes_type', 'type'),
    )
    id = Column(String(64), primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id', ondelete='CASCADE'), primary_key=True)
    type = Column(String(32), nullable=False)
    name = Column(String(255), nullable=False)
    parent_id = Column(String(64), nullable=True)  # FK removed to avoid SQLite composite FK issues
    x = Column(Float, default=0.0, nullable=False)
    y = Column(Float, default=0.0, nullable=False)
    attributes = Column(JSON, default=dict, nullable=False)
    project = relationship('Project', back_populates='nodes')


class Link(Base):
    __tablename__ = 'links'
    __table_args__ = (
        Index('ix_links_project_id', 'project_id'),
        Index('ix_links_source_id', 'source_id'),
        Index('ix_links_target_id', 'target_id'),
    )
    id = Column(String(64), primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id', ondelete='CASCADE'), primary_key=True)
    source_id = Column(String(64), nullable=False)
    target_id = Column(String(64), nullable=False)
    label = Column(String(255))
    attributes = Column(JSON, default=dict, nullable=False)
    project = relationship('Project', back_populates='links')


class Connection(Base):
    __tablename__ = 'connections'
    __table_args__ = (
        Index('ix_connections_project_id', 'project_id'),
        Index('ix_connections_source_id', 'source_id'),
        Index('ix_connections_target_id', 'target_id'),
    )
    id = Column(String(64), primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id', ondelete='CASCADE'), primary_key=True)
    source_id = Column(String(64), nullable=False)
    target_id = Column(String(64), nullable=False)
    protocol = Column(String(32))
    port = Column(String(64))
    description = Column(Text, nullable=True)
    attributes = Column(JSON, default=dict, nullable=False)
    project = relationship('Project', back_populates='connections')


class Setting(Base):
    __tablename__ = 'settings'
    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=True)


class AdminSession(Base):
    __tablename__ = 'admin_sessions'
    token = Column(String(64), primary_key=True)
    username = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class Group(Base):
    __tablename__ = 'groups'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)
    # Права группы: 'read' — только просмотр схем, 'write' — полный доступ.
    access = Column(String(16), default='write', nullable=False)


class LocalUser(Base):
    __tablename__ = 'local_users'
    __table_args__ = (
        Index('ix_local_users_group_id', 'group_id'),
    )
    id = Column(Integer, primary_key=True)
    username = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    group_id = Column(Integer, ForeignKey('groups.id', ondelete='SET NULL'), nullable=True)


class CustomType(Base):
    __tablename__ = 'custom_types'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)


class CatalogFolder(Base):
    """Каталог (папка) внутри общего каталога схем: по одной на каждую схему."""
    __tablename__ = 'catalog_folders'
    __table_args__ = (
        Index('ix_catalog_folders_updated_at', 'updated_at'),
    )
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    projects = relationship('Project', back_populates='folder')


class ObjectItem(Base):
    """Объект из схемы, сохранённый в общий каталог объектов (библиотеку)."""
    __tablename__ = 'object_items'
    __table_args__ = (
        Index('ix_object_items_group_id', 'group_id'),
        Index('ix_object_items_owner_id', 'owner_id'),
        Index('ix_object_items_type', 'type'),
        Index('ix_object_items_updated_at', 'updated_at'),
    )
    id = Column(Integer, primary_key=True)
    node_id = Column(String(64), unique=True, nullable=False)
    type = Column(String(32), nullable=False)
    name = Column(String(255), nullable=False)
    attributes = Column(JSON, default=dict, nullable=False)
    group_id = Column(Integer, ForeignKey('groups.id', ondelete='SET NULL'), nullable=True)
    owner_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    owner = relationship('User')
    group = relationship('Group')
