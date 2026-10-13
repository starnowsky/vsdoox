"""Интеграция с Keycloak (OIDC Authorization Code Flow).

Настройки (url, realm, client_id, client_secret) хранятся в settings и
редактируются в админке. Модуль отвечает за построение URL авторизации,
обмен кода на токен, получение профиля и синхронизацию локального пользователя.
"""
import secrets
import urllib.parse

import requests

import admin as adminmod
from models import Group, LocalUser
from storage import SessionLocal
from sqlalchemy import select


class KeycloakError(Exception):
    pass


def get_config():
    return adminmod.get_keycloak()


def is_enabled():
    cfg = get_config()
    return bool(cfg.get('enabled') and cfg.get('url') and cfg.get('realm') and cfg.get('client_id'))


def public_config():
    """Конфиг без секретов — для фронтенда."""
    cfg = get_config()
    return {
        'enabled': is_enabled(),
        'url': cfg.get('url', ''),
        'realm': cfg.get('realm', ''),
        'client_id': cfg.get('client_id', ''),
    }


def _endpoints(cfg):
    url = (cfg.get('url') or '').rstrip('/')
    realm = cfg.get('realm') or ''
    base = f"{url}/realms/{realm}/protocol/openid-connect"
    return base


def auth_url(redirect_uri, state):
    cfg = get_config()
    base = _endpoints(cfg)
    q = urllib.parse.urlencode({
        'client_id': cfg.get('client_id', ''),
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid',
        'state': state,
    })
    return f"{base}/auth?{q}"


def exchange_code(code, redirect_uri):
    cfg = get_config()
    base = _endpoints(cfg)
    r = requests.post(
        f"{base}/token",
        data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': cfg.get('client_id', ''),
            'client_secret': cfg.get('client_secret', ''),
        },
        timeout=20,
    )
    if r.status_code >= 400:
        raise KeycloakError('Не удалось обменять код на токен')
    return r.json()


def fetch_userinfo(access_token):
    cfg = get_config()
    base = _endpoints(cfg)
    r = requests.get(
        f"{base}/userinfo",
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=20,
    )
    if r.status_code >= 400:
        raise KeycloakError('Не удалось получить профиль пользователя')
    return r.json()


def _group_names(userinfo):
    """Извлекает имена групп из профиля (claim `groups` или роли realm_access)."""
    names = userinfo.get('groups')
    if isinstance(names, list):
        return [str(n) for n in names]
    ra = userinfo.get('realm_access') or {}
    roles = ra.get('roles') or []
    return [str(n) for n in roles]


def _ensure_group(name):
    name = (name or '').strip()
    if not name:
        return None
    with SessionLocal() as s:
        g = s.execute(select(Group).where(Group.name == name)).scalar_one_or_none()
        if not g:
            g = Group(name=name)
            s.add(g)
            s.commit()
            return g.id
        return g.id


def sync_user(userinfo):
    """Создаёт/обновляет локального пользователя из профиля Keycloak.

    Возвращает (username, group_id). Пароль не используется — вход через Keycloak,
    поэтому задаётся случайный хеш.
    """
    username = (
        userinfo.get('preferred_username')
        or userinfo.get('email')
        or userinfo.get('sub')
        or ''
    ).strip()
    if not username:
        raise KeycloakError('В профиле нет имени пользователя')

    group_id = None
    for name in _group_names(userinfo):
        gid = _ensure_group(name)
        if gid is not None and group_id is None:
            group_id = gid

    with SessionLocal() as s:
        u = s.execute(select(LocalUser).where(LocalUser.username == username)).scalar_one_or_none()
        if u:
            if group_id is not None:
                u.group_id = group_id
        else:
            u = LocalUser(
                username=username,
                password_hash=adminmod.hash_secret(secrets.token_hex(16)),
                group_id=group_id,
            )
            s.add(u)
        s.commit()

    return username, group_id


def new_state():
    return secrets.token_urlsafe(24)
