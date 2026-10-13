"""Администрирование: ключ доступа, Keycloak, локальные пользователи и группы."""
import hashlib
import json
import os
import secrets

from sqlalchemy import delete, select

from models import AdminSession, Group, LocalUser, Setting
from storage import SessionLocal

_KEY_ITERATIONS = 100_000


def _hash(secret, salt):
    return hashlib.pbkdf2_hmac('sha256', secret.encode('utf-8'), salt, _KEY_ITERATIONS)


def hash_secret(secret):
    salt = os.urandom(16)
    return salt.hex() + ':' + _hash(secret, salt).hex()


def verify_secret(secret, stored):
    try:
        salt_hex, h_hex = stored.split(':', 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(h_hex)
        return secrets.compare_digest(_hash(secret, salt), expected)
    except (ValueError, TypeError):
        return False


def is_configured():
    with SessionLocal() as s:
        row = s.get(Setting, 'admin_key')
        return bool(row and row.value)


def _create_session():
    token = secrets.token_hex(32)
    with SessionLocal() as s:
        s.add(AdminSession(token=token))
        s.commit()
    return token


def setup_key(key):
    key = (key or '').strip()
    if not key:
        raise ValueError('Ключ не может быть пустым')
    if is_configured():
        raise ValueError('Ключ уже задан')
    with SessionLocal() as s:
        s.add(Setting(key='admin_key', value=hash_secret(key)))
        s.commit()
    return _create_session()


def login(key):
    key = (key or '').strip()
    with SessionLocal() as s:
        row = s.get(Setting, 'admin_key')
        if not row or not row.value or not verify_secret(key, row.value):
            return None
    return _create_session()


def verify_token(token):
    if not token:
        return False
    with SessionLocal() as s:
        return s.get(AdminSession, token) is not None


# --- Keycloak ---

_DEFAULT_KEYCLOAK = {
    'enabled': False,
    'url': '',
    'realm': '',
    'client_id': '',
    'client_secret': '',
}


def get_keycloak():
    with SessionLocal() as s:
        row = s.get(Setting, 'keycloak')
        if not row or not row.value:
            return dict(_DEFAULT_KEYCLOAK)
        try:
            data = json.loads(row.value)
            return {**_DEFAULT_KEYCLOAK, **data}
        except (ValueError, TypeError):
            return dict(_DEFAULT_KEYCLOAK)


def save_keycloak(data):
    data = {**_DEFAULT_KEYCLOAK, **(data or {})}
    with SessionLocal() as s:
        row = s.get(Setting, 'keycloak')
        value = json.dumps(data, ensure_ascii=False)
        if row:
            row.value = value
        else:
            s.add(Setting(key='keycloak', value=value))
        s.commit()


# --- Группы ---

def list_groups():
    with SessionLocal() as s:
        rows = s.execute(select(Group).order_by(Group.name)).scalars().all()
        return [{'id': g.id, 'name': g.name} for g in rows]


def create_group(name):
    name = (name or '').strip()
    if not name:
        raise ValueError('Название группы обязательно')
    with SessionLocal() as s:
        if s.execute(select(Group).where(Group.name == name)).scalar_one_or_none():
            raise ValueError('Группа уже существует')
        g = Group(name=name)
        s.add(g)
        s.commit()
        return g.id


def delete_group(gid):
    with SessionLocal() as s:
        s.execute(delete(Group).where(Group.id == gid))
        s.commit()


# --- Локальные пользователи ---

def list_users():
    with SessionLocal() as s:
        rows = s.execute(select(LocalUser).order_by(LocalUser.username)).scalars().all()
        return [{'id': u.id, 'username': u.username, 'group_id': u.group_id} for u in rows]


def create_user(username, password, group_id=None):
    username = (username or '').strip()
    if not username or not password:
        raise ValueError('Логин и пароль обязательны')
    with SessionLocal() as s:
        if s.execute(select(LocalUser).where(LocalUser.username == username)).scalar_one_or_none():
            raise ValueError('Пользователь уже существует')
        u = LocalUser(username=username, password_hash=hash_secret(password), group_id=group_id or None)
        s.add(u)
        s.commit()
        return u.id


def delete_user(uid):
    with SessionLocal() as s:
        s.execute(delete(LocalUser).where(LocalUser.id == uid))
        s.commit()
