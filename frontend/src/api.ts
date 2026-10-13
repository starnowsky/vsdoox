import type { GraphLink, GraphNode, PathResult, Project } from './types';

export interface ProjectSummary {
  id: number;
  name: string;
  created_at?: string;
  updated_at?: string;
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
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
