import { useCallback, useEffect, useState } from 'react';
import {
  adminCreateGroup,
  adminCreateUser,
  adminDeleteGroup,
  adminDeleteUser,
  adminGetKeycloak,
  adminListGroups,
  adminListProjects,
  adminListUsers,
  adminLogin,
  adminSaveKeycloak,
  adminSetProjectGroup,
  adminSetup,
  adminStatus,
} from './api';
import type { AdminUser, CatalogProject } from './api';

const TOKEN_KEY = 'vsdoox.admin.token';

interface KeycloakConfig {
  enabled: boolean;
  url: string;
  realm: string;
  client_id: string;
  client_secret: string;
}

const EMPTY_KC: KeycloakConfig = { enabled: false, url: '', realm: '', client_id: '', client_secret: '' };

export default function AdminPanel() {
  const [token, setToken] = useState<string>(() => localStorage.getItem(TOKEN_KEY) ?? '');
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [key, setKey] = useState('');
  const [keyConfirm, setKeyConfirm] = useState('');
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');

  const [kc, setKc] = useState<KeycloakConfig>(EMPTY_KC);
  const [groups, setGroups] = useState<Array<{ id: number; name: string }>>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [allProjects, setAllProjects] = useState<CatalogProject[]>([]);

  const [newGroup, setNewGroup] = useState('');
  const [newUser, setNewUser] = useState('');
  const [newPass, setNewPass] = useState('');
  const [newGroupId, setNewGroupId] = useState('');
  const [tab, setTab] = useState<'integration' | 'access'>('integration');

  useEffect(() => {
    adminStatus()
      .then((s) => setConfigured(s.configured))
      .catch(() => setConfigured(false));
  }, []);

  const loadAdmin = useCallback(async (tok: string) => {
    try {
      const [kcRes, groupsRes, usersRes, projectsRes] = await Promise.all([
        adminGetKeycloak(tok),
        adminListGroups(tok),
        adminListUsers(tok),
        adminListProjects(tok),
      ]);
      setKc({ ...EMPTY_KC, ...kcRes } as KeycloakConfig);
      setGroups(groupsRes.groups);
      setUsers(usersRes.users);
      setAllProjects(projectsRes.projects);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (token) loadAdmin(token);
  }, [token, loadAdmin]);

  const saveToken = (tok: string) => {
    localStorage.setItem(TOKEN_KEY, tok);
    setToken(tok);
  };

  const handleSetup = async () => {
    setError('');
    if (key.length < 4) {
      setError('Ключ слишком короткий (минимум 4 символа)');
      return;
    }
    if (key !== keyConfirm) {
      setError('Ключи не совпадают');
      return;
    }
    try {
      const res = await adminSetup(key);
      saveToken(res.token);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleLogin = async () => {
    setError('');
    try {
      const res = await adminLogin(key);
      saveToken(res.token);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem(TOKEN_KEY);
    setToken('');
  };

  const handleSaveKeycloak = async () => {
    setError('');
    try {
      await adminSaveKeycloak(token, kc as unknown as Record<string, unknown>);
      setStatus('Настройки Keycloak сохранены');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleAddGroup = async () => {
    setError('');
    try {
      await adminCreateGroup(token, newGroup);
      setNewGroup('');
      setGroups((await adminListGroups(token)).groups);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleDeleteGroup = async (id: number) => {
    try {
      await adminDeleteGroup(token, id);
      setGroups((await adminListGroups(token)).groups);
      setUsers((await adminListUsers(token)).users);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleAddUser = async () => {
    setError('');
    try {
      await adminCreateUser(token, newUser, newPass, newGroupId ? Number(newGroupId) : null);
      setNewUser('');
      setNewPass('');
      setNewGroupId('');
      setUsers((await adminListUsers(token)).users);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleDeleteUser = async (id: number) => {
    try {
      await adminDeleteUser(token, id);
      setUsers((await adminListUsers(token)).users);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleChangeProjectGroup = async (pid: number, groupId: number | null) => {
    setError('');
    try {
      await adminSetProjectGroup(token, pid, groupId);
      setAllProjects((await adminListProjects(token)).projects);
      setStatus('Группа проекта обновлена');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const groupName = (id: number | null) => groups.find((g) => g.id === id)?.name ?? '—';

  if (!token) {
    return (
      <div className="admin-page">
        <div className="admin-card">
          <img className="page-banner" src="/vibelogo.jpg" alt="VibeDraw" />
          <h1>VibeDraw · администрирование</h1>
          {configured === null ? (
            <p className="muted">Загрузка…</p>
          ) : configured === false ? (
            <>
              <p>Первый вход: создайте ключ доступа (без логина).</p>
              <input
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="Новый ключ"
                autoFocus
              />
              <input
                type="password"
                value={keyConfirm}
                onChange={(e) => setKeyConfirm(e.target.value)}
                placeholder="Повторите ключ"
              />
              <button className="primary" onClick={handleSetup}>Создать ключ</button>
            </>
          ) : (
            <>
              <p>Введите ключ доступа.</p>
              <input
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="Ключ"
                autoFocus
              />
              <button className="primary" onClick={handleLogin}>Войти</button>
            </>
          )}
          {error && <div className="error">{error}</div>}
          <a href="/" className="link">← к схеме</a>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <div className="admin-header">
        <img className="page-banner" src="/vibelogo.jpg" alt="VibeDraw" />
        <div className="admin-header-actions">
          <a href="/" className="link">← к схеме</a>
          <button onClick={handleLogout}>Выйти</button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {status && <div className="success">{status}</div>}

      <div className="admin-tabs">
        <div className="tabs">
          <button className={'tab' + (tab === 'integration' ? ' active' : '')} onClick={() => setTab('integration')}>Интеграция</button>
          <button className={'tab' + (tab === 'access' ? ' active' : '')} onClick={() => setTab('access')}>Настройки доступа</button>
        </div>
      </div>

      {tab === 'integration' && (
      <section className="admin-section">
        <h2>Интеграция с Keycloak</h2>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={kc.enabled}
            onChange={(e) => setKc({ ...kc, enabled: e.target.checked })}
          />
          Включить Keycloak
        </label>
        <label>URL сервера</label>
        <input value={kc.url} onChange={(e) => setKc({ ...kc, url: e.target.value })} placeholder="https://keycloak.example.com" />
        <label>Realm</label>
        <input value={kc.realm} onChange={(e) => setKc({ ...kc, realm: e.target.value })} placeholder="corp" />
        <label>Client ID</label>
        <input value={kc.client_id} onChange={(e) => setKc({ ...kc, client_id: e.target.value })} placeholder="vsdoox" />
        <label>Client Secret</label>
        <input type="password" value={kc.client_secret} onChange={(e) => setKc({ ...kc, client_secret: e.target.value })} />
        <button className="primary" onClick={handleSaveKeycloak}>Сохранить</button>
      </section>
      )}

      {tab === 'access' && (
        <>
      <section className="admin-section">
        <h2>Группы доступа</h2>
        <div className="row">
          <input value={newGroup} onChange={(e) => setNewGroup(e.target.value)} placeholder="Название группы" />
          <button className="primary" onClick={handleAddGroup}>Добавить</button>
        </div>
        <ul className="admin-list">
          {groups.map((g) => (
            <li key={g.id}>
              <span>{g.name}</span>
              <button className="del" onClick={() => handleDeleteGroup(g.id)}>✕</button>
            </li>
          ))}
        </ul>
      </section>

      <section className="admin-section">
        <h2>Локальные пользователи</h2>
        <div className="admin-user-form">
          <input value={newUser} onChange={(e) => setNewUser(e.target.value)} placeholder="Логин" />
          <input type="password" value={newPass} onChange={(e) => setNewPass(e.target.value)} placeholder="Пароль" />
          <select value={newGroupId} onChange={(e) => setNewGroupId(e.target.value)}>
            <option value="">— без группы —</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
          <button className="primary" onClick={handleAddUser}>Добавить</button>
        </div>
        <ul className="admin-list">
          {users.map((u) => (
            <li key={u.id}>
              <span>{u.username} <span className="muted">({groupName(u.group_id)})</span></span>
              <button className="del" onClick={() => handleDeleteUser(u.id)}>✕</button>
            </li>
          ))}
        </ul>
      </section>

      <section className="admin-section">
        <h2>Проекты (группы доступа)</h2>
        <ul className="admin-list">
          {allProjects.map((p) => (
            <li key={p.id}>
              <span className="catalog-item">
                <span className="catalog-name">{p.name}</span>
                <span className="catalog-meta muted">владелец: {p.owner ?? '—'}</span>
              </span>
              <select
                value={p.group_id ?? ''}
                onChange={(e) =>
                  handleChangeProjectGroup(p.id, e.target.value === '' ? null : Number(e.target.value))
                }
              >
                <option value="">публичный</option>
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>{g.name}</option>
                ))}
              </select>
            </li>
          ))}
        </ul>
      </section>
        </>
      )}
    </div>
  );
}
