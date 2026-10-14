import { useEffect, useMemo, useState } from 'react';
import { catalogProjects, downloadConnectionsXlsx } from './api';
import type { CatalogFolder, CatalogProject } from './api';

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
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<CatalogProject | null>(null);

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

  const filteredFolders = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return folders;
    return folders
      .map((f) => ({
        ...f,
        projects: f.projects.filter((p) => p.name.toLowerCase().includes(q)),
      }))
      .filter((f) => f.projects.length > 0);
  }, [folders, search]);

  const openProject = (id: number) => {
    window.location.href = '/?project=' + id;
  };

  const exportExcel = async (p: CatalogProject) => {
    try {
      const blob = await downloadConnectionsXlsx(p.id);
      downloadBlob(blob, p.name + ' - связи.xlsx');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="admin-page">
      <div className="admin-header">
        <img className="page-banner" src="/vibelogo.jpg" alt="VibeDraw" />
        <div className="admin-header-actions">
          {viewer && <span className="muted">{viewer}</span>}
          <a href="/" className="link">← к схеме</a>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="catalog-layout">
        <aside className="catalog-registry">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по названию"
          />
          {!loading && filteredFolders.length === 0 && (
            <div className="muted">Ничего не найдено</div>
          )}
          <div className="registry-list">
            {filteredFolders.map((f) => (
              <div className="folder" key={f.id ?? 'none'}>
                <div className="folder-header">
                  <span>📁 {f.name}</span>
                  <span className="catalog-meta muted">{f.projects.length}</span>
                </div>
                <ul>
                  {f.projects.map((p) => (
                    <li key={p.id}>
                      <button
                        className={'registry-item' + (selected?.id === p.id ? ' active' : '')}
                        onClick={() => setSelected(p)}
                      >
                        {p.name}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </aside>

        <main className="catalog-detail">
          {!selected ? (
            <div className="muted">Выберите схему слева</div>
          ) : (
            <>
              <h2>{selected.name}</h2>
              <p className="catalog-meta">
                Владелец: {selected.owner ?? '—'}
                <br />
                Группа: {selected.group_name ?? 'публичный'}
                <br />
                Обновлена: {fmtDate(selected.updated_at)}
              </p>
              <div className="catalog-actions">
                <button className="primary" onClick={() => openProject(selected.id)}>Открыть</button>
                <button onClick={() => exportExcel(selected)} title="Таблица протоколов/портов (Excel)">Excel</button>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}