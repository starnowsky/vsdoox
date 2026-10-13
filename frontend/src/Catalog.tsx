import { useEffect, useState } from 'react';
import { catalogProjects } from './api';
import type { CatalogProject } from './api';

function fmtDate(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('ru-RU');
}

export default function Catalog() {
  const [projects, setProjects] = useState<CatalogProject[]>([]);
  const [viewer, setViewer] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await catalogProjects();
      setProjects(res.projects);
      setViewer(res.viewer);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openProject = (id: number) => {
    window.location.href = '/?project=' + id;
  };

  return (
    <div className="admin-page">
      <div className="admin-header">
        <h1>vsdoox · каталог проектов</h1>
        <div className="admin-header-actions">
          {viewer && <span className="muted">{viewer}</span>}
          <a href="/" className="link">← к схеме</a>
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {!error && !loading && projects.length === 0 && (
        <div className="muted">Нет доступных проектов</div>
      )}

      <ul className="admin-list">
        {projects.map((p) => (
          <li key={p.id}>
            <div className="catalog-item">
              <span className="catalog-name">{p.name}</span>
              <span className="catalog-meta">
                {p.owner ?? '—'} · {p.group_name ?? 'публичный'}
              </span>
              <span className="catalog-meta muted">{fmtDate(p.updated_at)}</span>
            </div>
            <button className="primary" onClick={() => openProject(p.id)}>Открыть</button>
          </li>
        ))}
      </ul>
    </div>
  );
}