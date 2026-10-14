import type { GraphLink, GraphNode, PathResult, Project } from './types';

export interface ProjectSummary {
  id: number;
  name: string;
  owner?: string | null;
  group_id?: number | null;
  group_name?: string | null;
  created_at?: string;
  updated_at?: string;
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = localStorage.getItem('vsdoox.user.token');
  if (token) headers['X-User-Token'] = token;
  const res = await fetch(url, {
    headers,
    ...options,
  });
  if (!res.ok) {
    let message = 'Ошибка ' + res.status;
    try {
      const body = await res.json();
      if (body && typeof body.error === 'string') message = body.error;
    } catch {
      // тело не JSON — оставляем дефолтное сообщение
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export function listProjects(owner: string): Promise<{ projects: ProjectSummary[] }> {
  return request('/api/projects?owner=' + encodeURIComponent(owner));
}

export function createProject(name: string, owner: string): Promise<{ id: number }> {
  return request('/api/projects', {
    method: 'POST',
    body: JSON.stringify({ name, owner }),
  });
}

export function getProject(id: number): Promise<Project> {
  return request('/api/projects/' + id);
}

export function saveProject(
  id: number,
  data: { name: string; nodes: GraphNode[]; links: GraphLink[]; connections: unknown[] },
): Promise<{ ok: boolean }> {
  return request('/api/projects/' + id, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export function deleteProject(id: number): Promise<{ ok: boolean }> {
  return request('/api/projects/' + id, { method: 'DELETE' });
}

// --- Каталог (проекты всех пользователей по группам доступа) ---

export interface CatalogProject {
  id: number;
  name: string;
  owner: string | null;
  group_id: number | null;
  group_name: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface CatalogFolder {
  id: number | null;
  name: string;
  projects: CatalogProject[];
}

export function catalogProjects(): Promise<{ folders: CatalogFolder[]; viewer: string; is_admin: boolean }> {
  return request('/api/catalog');
}

export interface ObjectItem {
  id: number;
  type: string;
  name: string;
  attributes: Record<string, unknown>;
  group_id: number | null;
  group_name: string | null;
  owner: string | null;
  created_at?: string;
  updated_at?: string;
}

export function listObjects(): Promise<{ objects: ObjectItem[]; viewer: string; is_admin: boolean }> {
  return request('/api/objects');
}

export function getCatalogProject(id: number): Promise<Project> {
  return request('/api/catalog/' + id);
}

export function analyzePath(
  nodes: GraphNode[],
  links: GraphLink[],
  sourceId: string,
  targetId: string,
): Promise<PathResult> {
  return request('/api/path', {
    method: 'POST',
    body: JSON.stringify({ nodes, links, source_id: sourceId, target_id: targetId }),
  });
}

export async function exportVSDX(payload: {
  title: string;
  nodes: unknown[];
  connections: unknown[];
}): Promise<Blob> {
  const res = await fetch('/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let message = 'Ошибка экспорта';
    try {
      const body = await res.json();
      if (body && typeof body.error === 'string') message = body.error;
    } catch {
      // тело не JSON — оставляем дефолтное сообщение
    }
    throw new Error(message);
  }
  return res.blob();
}

export async function downloadConnectionsXlsx(id: number): Promise<Blob> {
  const headers: Record<string, string> = {};
  const token = localStorage.getItem('vsdoox.user.token');
  if (token) headers['X-User-Token'] = token;
  const res = await fetch('/api/projects/' + id + '/connections.xlsx', { headers });
  if (!res.ok) {
    let message = 'Ошибка экспорта';
    try {
      const body = await res.json();
      if (body && typeof body.error === 'string') message = body.error;
    } catch {
      // не JSON
    }
    throw new Error(message);
  }
  return res.blob();
}

export async function exportConnectionsXlsx(payload: {
  title: string;
  nodes: { id: string; name: string }[];
  connections: unknown[];
}): Promise<Blob> {
  const res = await fetch('/api/export/connections.xlsx', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let message = 'Ошибка экспорта';
    try {
      const body = await res.json();
      if (body && typeof body.error === 'string') message = body.error;
    } catch {
      // не JSON
    }
    throw new Error(message);
  }
  return res.blob();
}

// --- Админка ---

async function adminRequest<T>(path: string, token: string | null, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['X-Admin-Token'] = token;
  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    let message = 'Ошибка ' + res.status;
    try {
      const body = await res.json();
      if (body && typeof body.error === 'string') message = body.error;
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export function adminStatus(): Promise<{ configured: boolean }> {
  return adminRequest('/api/admin/status', null);
}

export function adminSetup(key: string): Promise<{ token: string }> {
  return adminRequest('/api/admin/setup', null, { method: 'POST', body: JSON.stringify({ key }) });
}

export function adminLogin(key: string): Promise<{ token: string }> {
  return adminRequest('/api/admin/login', null, { method: 'POST', body: JSON.stringify({ key }) });
}

export function adminGetKeycloak(token: string): Promise<Record<string, unknown>> {
  return adminRequest('/api/admin/keycloak', token);
}

export function adminSaveKeycloak(token: string, data: Record<string, unknown>): Promise<{ ok: boolean }> {
  return adminRequest('/api/admin/keycloak', token, { method: 'PUT', body: JSON.stringify(data) });
}

export interface AdminGroup {
  id: number;
  name: string;
}

export function adminListGroups(token: string): Promise<{ groups: AdminGroup[] }> {
  return adminRequest('/api/admin/groups', token);
}

export function adminCreateGroup(token: string, name: string): Promise<{ id: number }> {
  return adminRequest('/api/admin/groups', token, { method: 'POST', body: JSON.stringify({ name }) });
}

export function adminDeleteGroup(token: string, id: number): Promise<{ ok: boolean }> {
  return adminRequest('/api/admin/groups/' + id, token, { method: 'DELETE' });
}

export interface AdminUser {
  id: number;
  username: string;
  group_id: number | null;
}

export function adminListUsers(token: string): Promise<{ users: AdminUser[] }> {
  return adminRequest('/api/admin/users', token);
}

export function adminCreateUser(
  token: string,
  username: string,
  password: string,
  group_id: number | null,
): Promise<{ id: number }> {
  return adminRequest('/api/admin/users', token, {
    method: 'POST',
    body: JSON.stringify({ username, password, group_id }),
  });
}

export function adminDeleteUser(token: string, id: number): Promise<{ ok: boolean }> {
  return adminRequest('/api/admin/users/' + id, token, { method: 'DELETE' });
}

export function adminListProjects(token: string): Promise<{ projects: CatalogProject[] }> {
  return adminRequest('/api/admin/projects', token);
}

export function adminSetProjectGroup(token: string, id: number, groupId: number | null): Promise<{ ok: boolean }> {
  return adminRequest('/api/admin/projects/' + id + '/group', token, {
    method: 'PUT',
    body: JSON.stringify({ group_id: groupId }),
  });
}

// --- Кастомные типы объектов ---

export interface CustomType {
  id: number;
  name: string;
}

export function listCustomTypes(): Promise<{ types: CustomType[] }> {
  return request('/api/custom-types');
}

export function createCustomType(name: string): Promise<{ id: number }> {
  return request('/api/custom-types', { method: 'POST', body: JSON.stringify({ name }) });
}

export function deleteCustomType(id: number): Promise<{ ok: boolean }> {
  return request('/api/custom-types/' + id, { method: 'DELETE' });
}

// --- Авторизация (логин/пароль) ---

export function authLogin(username: string, password: string): Promise<{ token: string; username: string }> {
  return request('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
}

// --- Keycloak ---

export interface KeycloakPublicConfig {
  enabled: boolean;
  url: string;
  realm: string;
  client_id: string;
}

export function keycloakConfig(): Promise<KeycloakPublicConfig> {
  return request('/api/auth/keycloak/config');
}

export function keycloakLoginUrl(): string {
  return '/api/auth/keycloak/login';
}
