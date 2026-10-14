import { useEffect, useState } from 'react';
import { catalogProjects, downloadConnectionsXlsx } from './api';
import type { CatalogFolder } from './api';

function fmtDate(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('ru-RU');
}

function downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export default function Catalog() {
  const [folders, setFolders] = useState<CatalogFolder[]>([]);
  const [viewer, setViewer] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await catalogProjects();
      setFolders(res.folders);
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

  const exportExcel = async (id: number, name: string) => {
    try {
      const blob = await downloadConnectionsXlsx(id);
      downloadBlob(blob, name + ' - связи.xlsx');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const total = folders.reduce((acc, f) => acc + f.projects.length, 0);

  return (
    <div className="admin-page">
      <div className="banner"><img src="/vibelogo.jpg" alt="VibeDraw" /></div>
      <div className="admin-header">
        <h1><img className="brand-icon" src="/vibeicon.jpg" alt="" /> VibeDraw · каталог проектов</h1>
        <div className="admin-header-actions">
          {viewer && <span className="muted">{viewer}</span>}
          <a href="/" className="link">← к схеме</a>
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {!error && !loading && total === 0 && (
        <div className="muted">Нет доступных проектов</div>
      )}

      {folders.map((f) => (
        <div className="folder" key={f.id ?? 'none'}>
          <div className="folder-header">
            <span>📁 {f.name}</span>
            <span className="catalog-meta muted">{f.projects.length}</span>
          </div>
          <ul className="admin-list">
            {f.projects.map((p) => (
              <li key={p.id}>
                <div className="catalog-item">
                  <span className="catalog-name">{p.name}</span>
                  <span className="catalog-meta">
                    {p.owner ?? '—'} · {p.group_name ?? 'публичный'}
                  </span>
                  <span className="catalog-meta muted">{fmtDate(p.updated_at)}</span>
                </div>
                <div className="catalog-actions">
                  <button className="primary" onClick={() => openProject(p.id)}>Открыть</button>
                  <button onClick={() => exportExcel(p.id, p.name)} title="Таблица связей (Excel)">Excel</button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}