"""Хранение на SQLAlchemy. По умолчанию SQLite, переход на PostgreSQL — замена URL.

VSDOOX_DB_URL — URL БД (по умолчанию sqlite:///<backend>/vsdoox.db).
Пример PostgreSQL: postgresql+psycopg://user:pass@host:5432/dbname
"""
import json
import os
import uuid

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from models import Base, Connection, CustomType, Group, Link, LocalUser, Node, Project, User, utcnow

NODE_TYPES = {'server', 'firewall', 'network', 'datacenter'}

_DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(__file__), 'vsdoox.db')


def _db_url():
    return os.environ.get('VSDOOX_DB_URL', f'sqlite:///{_DEFAULT_SQLITE_PATH}')


_DB_URL = _db_url()

_engine = create_engine(
    _DB_URL,
    connect_args={'check_same_thread': False} if _DB_URL.startswith('sqlite') else {},
)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(_engine)
    _migrate_schema()


def _migrate_schema():
    """Лёгкая миграция для существующих dev-БД (до появления Alembic)."""
    from sqlalchemy import inspect
    insp = inspect(_engine)
    if 'nodes' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('nodes')}
    if 'parent_id' not in cols:
        with _engine.begin() as conn:
            conn.exec_driver_sql('ALTER TABLE nodes ADD COLUMN parent_id TEXT')

    if 'projects' in insp.get_table_names():
        pcols = {c['name'] for c in insp.get_columns('projects')}
        if 'group_id' not in pcols:
            with _engine.begin() as conn:
                conn.exec_driver_sql('ALTER TABLE projects ADD COLUMN group_id INTEGER')

    if 'admin_sessions' in insp.get_table_names():
        acols = {c['name'] for c in insp.get_columns('admin_sessions')}
        if 'username' not in acols:
            with _engine.begin() as conn:
                conn.exec_driver_sql('ALTER TABLE admin_sessions ADD COLUMN username TEXT')


def _ensure_id(value):
    if value in (None, ''):
        return uuid.uuid4().hex
    return str(value)


def _norm_attributes(value):
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def _iso(value):
    return value.isoformat() if value else None


def _node_dict(n):
    return {'id': n.id, 'type': n.type, 'name': n.name,
            'parent_id': n.parent_id, 'x': n.x, 'y': n.y,
            'attributes': n.attributes or {}}


def _link_dict(l):
    return {'id': l.id, 'source_id': l.source_id, 'target_id': l.target_id,
            'label': l.label, 'attributes': l.attributes or {}}


def _conn_dict(c):
    return {'id': c.id, 'source_id': c.source_id, 'target_id': c.target_id,
            'protocol': c.protocol, 'port': c.port, 'attributes': c.attributes or {}}


def get_or_create_user(name):
    name = (name or '').strip()
    if not name:
        raise ValueError('Имя пользователя обязательно')
    with SessionLocal() as session:
        user = session.execute(select(User).where(User.name == name)).scalar_one_or_none()
        if user:
            return user.id
        user = User(name=name)
        session.add(user)
        session.commit()
        return user.id


def get_user_group_id(username):
    """Возвращает id группы локального пользователя (или None)."""
    username = (username or '').strip()
    if not username:
        return None
    with SessionLocal() as session:
        u = session.execute(
            select(LocalUser).where(LocalUser.username == username)
        ).scalar_one_or_none()
        return u.group_id if u else None


def create_project(name, owner_name, group_id=None):
    name = (name or '').strip() or 'Без названия'
    owner_id = get_or_create_user(owner_name)
    if group_id is None:
        group_id = get_user_group_id(owner_name)
    with SessionLocal() as session:
        project = Project(name=name, owner_id=owner_id, group_id=group_id)
        session.add(project)
        session.commit()
        return project.id


def _project_summary(p):
    return {
        'id': p.id,
        'name': p.name,
        'owner': p.owner.name if p.owner else None,
        'group_id': p.group_id,
        'group_name': p.group.name if p.group else None,
        'created_at': _iso(p.created_at),
        'updated_at': _iso(p.updated_at),
    }


def list_projects(owner_name):
    owner_id = get_or_create_user(owner_name)
    with SessionLocal() as session:
        rows = session.execute(
            select(Project).where(Project.owner_id == owner_id)
            .order_by(Project.updated_at.desc())
        ).scalars().all()
        return [_project_summary(p) for p in rows]


def can_read_project(project, viewer_username, is_admin=False):
    """Доступ на чтение: админ, владелец, публичный (без группы) или своя группа."""
    if is_admin:
        return True
    owner = project.owner.name if project.owner else None
    if owner == viewer_username:
        return True
    if project.group_id is None:
        return True
    return get_user_group_id(viewer_username) == project.group_id


def list_visible_projects(viewer_username, is_admin=False):
    """Все проекты, доступные пользователю: публичные, своей группы и собственные."""
    with SessionLocal() as session:
        if is_admin:
            rows = session.execute(
                select(Project).order_by(Project.updated_at.desc())
            ).scalars().all()
            return [_project_summary(p) for p in rows]
        group_id = get_user_group_id(viewer_username)
        rows = session.execute(
            select(Project).order_by(Project.updated_at.desc())
        ).scalars().all()
        result = []
        for p in rows:
            owner = p.owner.name if p.owner else None
            if owner == viewer_username or p.group_id is None or p.group_id == group_id:
                result.append(_project_summary(p))
        return result


def get_project(project_id):
    with SessionLocal() as session:
        project = session.get(Project, project_id)
        if not project:
            return None
        nodes = session.execute(
            select(Node).where(Node.project_id == project_id).order_by(Node.id)
        ).scalars().all()
        links = session.execute(
            select(Link).where(Link.project_id == project_id).order_by(Link.id)
        ).scalars().all()
        conns = session.execute(
            select(Connection).where(Connection.project_id == project_id).order_by(Connection.id)
        ).scalars().all()
        return {
            'id': project.id, 'name': project.name,
            'owner': project.owner.name if project.owner else None,
            'group_id': project.group_id,
            'group_name': project.group.name if project.group else None,
            'created_at': _iso(project.created_at),
            'updated_at': _iso(project.updated_at),
            'nodes': [_node_dict(n) for n in nodes],
            'links': [_link_dict(l) for l in links],
            'connections': [_conn_dict(c) for c in conns],
        }


def save_project(project_id, name, nodes, links, connections):
    with SessionLocal() as session:
        project = session.get(Project, project_id)
        if not project:
            return False
        project.name = (name or '').strip() or 'Без названия'
        project.updated_at = utcnow()

        session.execute(delete(Connection).where(Connection.project_id == project_id))
        session.execute(delete(Link).where(Link.project_id == project_id))
        session.execute(delete(Node).where(Node.project_id == project_id))

        for n in nodes or []:
            ntype = str(n.get('type') or 'server').strip() or 'server'
            session.add(Node(
                id=_ensure_id(n.get('id')), project_id=project_id, type=ntype,
                name=(n.get('name') or '').strip() or 'Узел',
                parent_id=n.get('parent_id') or None,
                x=float(n.get('x', 0) or 0), y=float(n.get('y', 0) or 0),
                attributes=_norm_attributes(n.get('attributes')),
            ))
        for l in links or []:
            session.add(Link(
                id=_ensure_id(l.get('id')), project_id=project_id,
                source_id=str(l.get('source_id', '')), target_id=str(l.get('target_id', '')),
                label=l.get('label'), attributes=_norm_attributes(l.get('attributes')),
            ))
        for c in connections or []:
            session.add(Connection(
                id=_ensure_id(c.get('id')), project_id=project_id,
                source_id=str(c.get('source_id', '')), target_id=str(c.get('target_id', '')),
                protocol=c.get('protocol'), port=c.get('port'),
                attributes=_norm_attributes(c.get('attributes')),
            ))
        session.commit()
        return True


def delete_project(project_id):
    with SessionLocal() as session:
        session.execute(delete(Connection).where(Connection.project_id == project_id))
        session.execute(delete(Link).where(Link.project_id == project_id))
        session.execute(delete(Node).where(Node.project_id == project_id))
        session.execute(delete(Project).where(Project.id == project_id))
        session.commit()


def set_project_group(project_id, group_id):
    """Назначает/снимает группу доступа проекта (None = публичный)."""
    with SessionLocal() as session:
        project = session.get(Project, project_id)
        if not project:
            return False
        project.group_id = group_id
        project.updated_at = utcnow()
        session.commit()
        return True


# --- Кастомные типы объектов ---

def list_custom_types():
    with SessionLocal() as session:
        rows = session.execute(select(CustomType).order_by(CustomType.name)).scalars().all()
        return [{'id': t.id, 'name': t.name} for t in rows]


def create_custom_type(name):
    name = (name or '').strip()
    if not name:
        raise ValueError('Название типа обязательно')
    with SessionLocal() as session:
        if session.execute(select(CustomType).where(CustomType.name == name)).scalar_one_or_none():
            raise ValueError('Тип уже существует')
        t = CustomType(name=name)
        session.add(t)
        session.commit()
        return t.id


def delete_custom_type(tid):
    with SessionLocal() as session:
        session.execute(delete(CustomType).where(CustomType.id == tid))
        session.commit()
