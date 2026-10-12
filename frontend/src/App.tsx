import { useCallback, useEffect, useMemo, useState } from 'react';
import { ReactFlow, Background, Controls, MiniMap, useNodesState } from '@xyflow/react';
import type { Edge, Node, NodeTypes } from '@xyflow/react';

import { DatacenterNode, DeviceNode } from './nodes';
import type { DeviceData } from './nodes';
import { createProject, deleteProject, getProject, listProjects, saveProject } from './api';
import type { ProjectSummary } from './api';
import type { Connection as Interaction, GraphLink, GraphNode, NodeType } from './types';

const nodeTypes: NodeTypes = {
  server: DeviceNode,
  firewall: DeviceNode,
  network: DeviceNode,
  datacenter: DatacenterNode,
};

const DEFAULT_NAMES: Record<NodeType, string> = {
  server: 'Сервер',
  firewall: 'МЭ',
  network: 'Сеть',
  datacenter: 'ЦОД',
};

interface AttrField {
  key: string;
  label: string;
  placeholder: string;
}

const ATTR_FIELDS: Record<NodeType, AttrField[]> = {
  server: [
    { key: 'ip', label: 'IP-адрес', placeholder: '10.0.0.10' },
    { key: 'ports', label: 'Порты', placeholder: '80, 443' },
  ],
  firewall: [{ key: 'zones', label: 'Зоны/интерфейсы', placeholder: 'outside, inside' }],
  network: [
    { key: 'cidr', label: 'CIDR', placeholder: '10.0.0.0/24' },
    { key: 'vlan', label: 'VLAN', placeholder: '100' },
  ],
  datacenter: [{ key: 'location', label: 'Расположение', placeholder: 'Москва' }],
};

const PRIMARY_ATTR: Record<NodeType, AttrField> = {
  server: ATTR_FIELDS.server[0],
  firewall: ATTR_FIELDS.firewall[0],
  network: ATTR_FIELDS.network[0],
  datacenter: ATTR_FIELDS.datacenter[0],
};

const PARENT_OPTIONS: Partial<Record<NodeType, NodeType[]>> = {
  server: ['network', 'datacenter'],
  firewall: ['datacenter'],
  network: ['datacenter'],
};

const CONN_COLORS = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#64748b'];
const DEFAULT_CONN_COLOR = CONN_COLORS[0];

const DC_W = 300;
const DC_HEADER = 46;
const DC_PAD = 14;
const ROW_H = 54;
const ROW_GAP = 8;
const DC_MARGIN = 30;
const FW_W = 110;
const FW_GAP = 16;
const FW_BETWEEN = 48;
const FW_H = 44;

function genId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'id-' + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function typeRank(type: string | undefined): number {
  if (type === 'firewall') return 0;
  if (type === 'network') return 1;
  if (type === 'server') return 2;
  return 3;
}

function resolveDatacenterId(nodeId: string, nodes: Node<DeviceData>[]): string | undefined {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  let cur = byId.get(nodeId);
  let guard = 0;
  while (cur && guard++ < 20) {
    if (cur.type === 'datacenter') return cur.id;
    const pid = cur.data.parent_id as string | undefined;
    cur = pid ? byId.get(pid) : undefined;
  }
  return undefined;
}

function connColor(c: Interaction): string {
  const col = c.attributes && typeof c.attributes.color === 'string' ? c.attributes.color : '';
  return col || DEFAULT_CONN_COLOR;
}

function toGraph(
  nodes: Node<DeviceData>[],
  connections: Interaction[],
): { nodes: GraphNode[]; links: GraphLink[]; connections: unknown[] } {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      type: (n.type as NodeType) ?? 'server',
      name: n.data.name,
      parent_id: n.data.parent_id ?? null,
      x: n.position.x,
      y: n.position.y,
      attributes: n.data.attributes ?? {},
    })),
    links: [],
    connections: connections.map((c) => ({
      id: c.id,
      source_id: c.source_id,
      target_id: c.target_id,
      protocol: c.protocol ?? null,
      port: c.port ?? null,
      attributes: c.attributes ?? {},
    })),
  };
}

function toRfNodes(entities: GraphNode[]): Node<DeviceData>[] {
  const base: Node<DeviceData>[] = entities.map((e) => ({
    id: e.id,
    type: e.type,
    position: { x: e.x, y: e.y },
    data: { name: e.name, parent_id: e.parent_id ?? undefined, attributes: e.attributes },
  }));
  return base.map((n) => {
    const dcId = n.type === 'datacenter' ? undefined : resolveDatacenterId(n.id, base);
    return { ...n, parentId: dcId, extent: dcId && n.type !== 'firewall' ? ('parent' as const) : undefined };
  });
}

function autoLayout(nodes: Node<DeviceData>[]): Node<DeviceData>[] {
  const positions = new Map<string, { x: number; y: number }>();
  const dcs = nodes.filter((n) => n.type === 'datacenter');
  let cursor = DC_MARGIN;
  dcs.forEach((dc, i) => {
    const inside = nodes
      .filter((n) => n.parentId === dc.id && n.type !== 'firewall')
      .sort((a, b) => typeRank(a.type) - typeRank(b.type));
    const fw = nodes.find((n) => n.type === 'firewall' && n.parentId === dc.id);
    const height = DC_HEADER + DC_PAD + inside.length * (ROW_H + ROW_GAP) + DC_PAD;
    const side: 'right' | 'left' = i === 0 ? 'right' : 'left';
    if (side === 'right') {
      positions.set(dc.id, { x: cursor, y: DC_MARGIN });
      if (fw) positions.set(fw.id, { x: DC_W + FW_GAP, y: Math.round((height - FW_H) / 2) });
      cursor += DC_W + FW_GAP + FW_W + FW_BETWEEN;
    } else {
      if (fw) positions.set(fw.id, { x: -(FW_W + FW_GAP), y: Math.round((height - FW_H) / 2) });
      positions.set(dc.id, { x: cursor + FW_W + FW_GAP, y: DC_MARGIN });
      cursor += FW_W + FW_GAP + DC_W + FW_BETWEEN;
    }
    inside.forEach((c, k) => {
      positions.set(c.id, { x: DC_PAD, y: DC_HEADER + DC_PAD + k * (ROW_H + ROW_GAP) });
    });
  });
  return nodes.map((n) => {
    const p = positions.get(n.id);
    return p ? { ...n, position: p } : n;
  });
}

export default function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<DeviceData>>([]);
  const [connections, setConnections] = useState<Interaction[]>([]);

  const [owner, setOwner] = useState<string>(() => localStorage.getItem('vsdoox.owner') ?? '');
  const [projectName, setProjectName] = useState('Схема L2');
  const [projectId, setProjectId] = useState<number | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [status, setStatus] = useState('');
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('vsdoox.theme');
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('vsdoox.theme', theme);
  }, [theme]);
  const toggleTheme = () => setTheme((t) => (t === 'light' ? 'dark' : 'light'));

  const [eType, setEType] = useState<NodeType>('server');
  const [eName, setEName] = useState('');
  const [eParent, setEParent] = useState('');
  const [eAttr, setEAttr] = useState('');

  const [cSource, setCSource] = useState('');
  const [cTarget, setCTarget] = useState('');
  const [cProtocol, setCProtocol] = useState('tcp');
  const [cPort, setCPort] = useState('');
  const [cColor, setCColor] = useState(DEFAULT_CONN_COLOR);

  const [editingNodeId, setEditingNodeId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editParent, setEditParent] = useState('');
  const [editAttrs, setEditAttrs] = useState<Record<string, string>>({});

  const [pathResult, setPathResult] = useState<{ found: boolean; path: string[]; firewalls: string[] } | null>(null);

  const displayNodes = useMemo(() => {
    return nodes.map((n) => {
      if (n.type === 'datacenter') {
        const childCount = nodes.filter((c) => c.parentId === n.id && c.type !== 'firewall').length;
        const h = DC_HEADER + DC_PAD + childCount * (ROW_H + ROW_GAP) + DC_PAD;
        return { ...n, style: { width: DC_W, height: Math.max(h, 130) } };
      }
      return n;
    });
  }, [nodes]);

  const edges = useMemo<Edge[]>(() => {
    const pathNodes = new Set(pathResult?.path ?? []);
    return connections.map((c) => {
      const color = connColor(c);
      const label = (c.protocol ?? 'any') + (c.port ? ':' + c.port : '');
      const highlighted = pathNodes.has(c.source_id) && pathNodes.has(c.target_id);
      return {
        id: 'conn-' + c.id,
        source: c.source_id,
        target: c.target_id,
        type: 'smoothstep',
        label,
        style: { stroke: color, strokeWidth: highlighted ? 3 : 2 },
        labelStyle: { fill: 'var(--text)', fontSize: 11, fontWeight: 600 },
        labelBgStyle: { fill: 'var(--surface)', fillOpacity: 0.92 },
        labelBgPadding: [5, 3] as [number, number],
        labelBgBorderRadius: 4,
      };
    });
  }, [connections, pathResult]);

  const parentOptions = useMemo(() => {
    const allowed = PARENT_OPTIONS[eType];
    if (!allowed) return [];
    return nodes.filter((n) => allowed.includes(n.type as NodeType));
  }, [eType, nodes]);

  const addEntity = useCallback(() => {
    const name = eName.trim() || DEFAULT_NAMES[eType];
    const logicalParent: string | null = eType === 'datacenter' ? null : eParent || null;
    const dcId = logicalParent ? resolveDatacenterId(logicalParent, nodes) : undefined;

    let parentId: string | undefined;
    let position: { x: number; y: number };
    if (dcId) {
      parentId = dcId;
      position = { x: DC_PAD, y: DC_HEADER + DC_PAD };
    } else {
      position = { x: DC_MARGIN + Math.random() * 200, y: DC_MARGIN + Math.random() * 200 };
    }

    const attrs: Record<string, unknown> = {};
    if (eAttr.trim()) {
      const key = PRIMARY_ATTR[eType].key;
      attrs[key] = eAttr.trim();
    }

    const node: Node<DeviceData> = {
      id: genId(),
      type: eType,
      position,
      parentId,
      extent: parentId && eType !== 'firewall' ? ('parent' as const) : undefined,
      data: { name, parent_id: logicalParent ?? undefined, attributes: attrs },
    };
    setNodes((nds) => autoLayout(nds.concat(node)));
    setEName('');
    setEAttr('');
    setEParent('');
  }, [eType, eName, eParent, eAttr, nodes, setNodes]);

  const deleteNode = useCallback(
    (id: string) => {
      setNodes((nds) => autoLayout(nds.filter((n) => n.id !== id && n.data.parent_id !== id)));
      setConnections((cs) => cs.filter((c) => c.source_id !== id && c.target_id !== id));
    },
    [setNodes],
  );

  const addConnection = useCallback(() => {
    if (!cSource || !cTarget) {
      setStatus('Выберите два объекта');
      return;
    }
    if (cSource === cTarget) {
      setStatus('Выберите разные объекты');
      return;
    }
    const conn: Interaction = {
      id: genId(),
      source_id: cSource,
      target_id: cTarget,
      protocol: cProtocol || undefined,
      port: cPort || undefined,
      attributes: { color: cColor },
    };
    setConnections((cs) => cs.concat(conn));
    setCPort('');
  }, [cSource, cTarget, cProtocol, cPort, cColor]);

  const deleteConnection = useCallback((id: string) => {
    setConnections((cs) => cs.filter((c) => c.id !== id));
  }, []);

  const cycleConnectionColor = useCallback((id: string) => {
    setConnections((cs) =>
      cs.map((c) => {
        if (c.id !== id) return c;
        const idx = CONN_COLORS.indexOf(connColor(c));
        const next = CONN_COLORS[(idx + 1) % CONN_COLORS.length];
        return { ...c, attributes: { ...c.attributes, color: next } };
      }),
    );
  }, []);

  const showConnection = useCallback(
    (c: Interaction) => {
      const srcDc = resolveDatacenterId(c.source_id, nodes);
      const dstDc = resolveDatacenterId(c.target_id, nodes);
      let firewalls: string[] = [];
      if (srcDc && dstDc && srcDc !== dstDc) {
        firewalls = nodes
          .filter((n) => n.type === 'firewall' && (n.data.parent_id === srcDc || n.data.parent_id === dstDc))
          .map((n) => n.id);
      }
      setPathResult({ found: true, path: [c.source_id, ...firewalls, c.target_id], firewalls });
      setStatus(firewalls.length ? 'МЭ на пути: ' + firewalls.length : 'В пределах одного ЦОД');
    },
    [nodes],
  );

  const refreshProjects = useCallback(async () => {
    if (!owner.trim()) return;
    try {
      const res = await listProjects(owner.trim());
      setProjects(res.projects);
    } catch (e) {
      setStatus((e as Error).message);
    }
  }, [owner]);

  const handleSave = useCallback(async () => {
    if (!owner.trim()) {
      setStatus('Укажите владельца');
      return;
    }
    try {
      const graph = toGraph(nodes, connections);
      let pid = projectId;
      if (pid == null) {
        const created = await createProject(projectName || 'Без названия', owner.trim());
        pid = created.id;
        setProjectId(pid);
      }
      await saveProject(pid, { name: projectName, ...graph });
      setStatus('Сохранено (проект #' + pid + ')');
      await refreshProjects();
    } catch (e) {
      setStatus((e as Error).message);
    }
  }, [owner, projectName, projectId, nodes, connections, refreshProjects]);

  const handleLoad = useCallback(
    async (id: number) => {
      try {
        const project = await getProject(id);
        setNodes(toRfNodes(project.nodes));
        setConnections(project.connections);
        setProjectId(project.id);
        setProjectName(project.name);
        setPathResult(null);
        setStatus('Загружен проект #' + id);
      } catch (e) {
        setStatus((e as Error).message);
      }
    },
    [setNodes],
  );

  const handleNew = useCallback(() => {
    setNodes([]);
    setConnections([]);
    setProjectId(null);
    setProjectName('Схема L2');
    setPathResult(null);
    setStatus('');
  }, [setNodes]);

  const handleDelete = useCallback(
    async (id: number) => {
      try {
        await deleteProject(id);
        if (projectId === id) handleNew();
        await refreshProjects();
        setStatus('Проект удалён');
      } catch (e) {
        setStatus((e as Error).message);
      }
    },
    [projectId, handleNew, refreshProjects],
  );

  const openEdit = useCallback(
    (id: string) => {
      const node = nodes.find((n) => n.id === id);
      if (!node) return;
      setEditingNodeId(id);
      setEditName(node.data.name);
      setEditParent((node.data.parent_id as string) ?? '');
      const attrs: Record<string, string> = {};
      const a = node.data.attributes ?? {};
      Object.keys(a).forEach((k) => {
        attrs[k] = typeof a[k] === 'string' ? a[k] : String(a[k]);
      });
      setEditAttrs(attrs);
    },
    [nodes],
  );

  const handleEditSave = useCallback(() => {
    if (!editingNodeId) return;
    setNodes((nds) =>
      nds.map((n) =>
        n.id === editingNodeId
          ? {
              ...n,
              data: {
                ...n.data,
                name: editName.trim() || n.data.name,
                parent_id: editParent || undefined,
                attributes: editAttrs,
              },
            }
          : n,
      ),
    );
    setEditingNodeId(null);
  }, [editingNodeId, editName, editParent, editAttrs, setNodes]);

  const handleEditCancel = useCallback(() => setEditingNodeId(null), []);

  const nodeName = (id: string): string => nodes.find((n) => n.id === id)?.data.name ?? id;

  const editingNode = editingNodeId ? nodes.find((n) => n.id === editingNodeId) ?? null : null;
  const editingType: NodeType | null = editingNode ? ((editingNode.type as NodeType) ?? 'server') : null;
  const editingFields = editingType ? ATTR_FIELDS[editingType] : [];
  const editingParentType = editingType ? PARENT_OPTIONS[editingType] : undefined;

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>
            <span className="logo-mark">V</span>
            vsdoox · сетевые схемы
          </h1>
          <button className="theme-toggle" onClick={toggleTheme} title="Переключить тему">
            {theme === 'light' ? '🌙' : '☀️'}
          </button>
        </div>

        <section>
          <label>Владелец</label>
          <input
            value={owner}
            onChange={(e) => {
              setOwner(e.target.value);
              localStorage.setItem('vsdoox.owner', e.target.value);
            }}
            placeholder="Имя пользователя"
          />
        </section>

        <section>
          <label>Название схемы</label>
          <input value={projectName} onChange={(e) => setProjectName(e.target.value)} />
        </section>

        <div className="row">
          <button onClick={handleNew}>Новая</button>
          <button className="primary" onClick={handleSave}>Сохранить</button>
        </div>

        <section>
          <label>Мои проекты</label>
          <button onClick={refreshProjects}>Обновить список</button>
          <ul className="projects">
            {projects.map((p) => (
              <li key={p.id}>
                <button className="link" onClick={() => handleLoad(p.id)}>
                  {p.name} (#{p.id})
                </button>
                <button className="del" onClick={() => handleDelete(p.id)}>✕</button>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <label>Добавить объект</label>
          <select value={eType} onChange={(e) => setEType(e.target.value as NodeType)}>
            <option value="server">Сервер</option>
            <option value="network">Сеть</option>
            <option value="firewall">МЭ (межсетевой экран)</option>
            <option value="datacenter">ЦОД</option>
          </select>
          <input value={eName} onChange={(e) => setEName(e.target.value)} placeholder="Название" />
          {parentOptions.length > 0 && (
            <select value={eParent} onChange={(e) => setEParent(e.target.value)}>
              <option value="">— родитель —</option>
              {parentOptions.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.data.name}
                </option>
              ))}
            </select>
          )}
          <input
            value={eAttr}
            onChange={(e) => setEAttr(e.target.value)}
            placeholder={PRIMARY_ATTR[eType].placeholder}
          />
          <div className="row">
            <button className="primary" onClick={addEntity}>Добавить</button>
            <button onClick={() => setNodes(autoLayout(nodes))}>Авто-раскладка</button>
          </div>
        </section>

        {nodes.length > 0 && (
          <section>
            <label>Объекты</label>
            <ul className="projects">
              {nodes.map((n) => (
                <li key={n.id}>
                  <button className="link" onClick={() => openEdit(n.id)}>
                    {n.data.name} <span className="conn-meta">{DEFAULT_NAMES[n.type as NodeType] ?? n.type}</span>
                  </button>
                  <button className="del" onClick={() => deleteNode(n.id)}>✕</button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <label>Связь между объектами</label>
          <select value={cSource} onChange={(e) => setCSource(e.target.value)}>
            <option value="">— откуда —</option>
            {nodes.map((n) => (
              <option key={n.id} value={n.id}>
                {n.data.name}
              </option>
            ))}
          </select>
          <select value={cTarget} onChange={(e) => setCTarget(e.target.value)}>
            <option value="">— куда —</option>
            {nodes.map((n) => (
              <option key={n.id} value={n.id}>
                {n.data.name}
              </option>
            ))}
          </select>
          <div className="row">
            <select value={cProtocol} onChange={(e) => setCProtocol(e.target.value)}>
              <option value="tcp">TCP</option>
              <option value="udp">UDP</option>
              <option value="icmp">ICMP</option>
              <option value="any">ANY</option>
            </select>
            <input value={cPort} onChange={(e) => setCPort(e.target.value)} placeholder="Порт" />
          </div>
          <div className="swatches">
            {CONN_COLORS.map((col) => (
              <button
                key={col}
                className={'swatch' + (cColor === col ? ' active' : '')}
                style={{ background: col }}
                onClick={() => setCColor(col)}
                title={col}
              />
            ))}
          </div>
          <button className="primary" onClick={addConnection}>Добавить связь</button>
        </section>

        {connections.length > 0 && (
          <section>
            <label>Связи</label>
            <ul className="connections">
              {connections.map((c) => (
                <li key={c.id}>
                  <button className="swatch-mini" style={{ background: connColor(c) }} onClick={() => cycleConnectionColor(c.id)} title="Сменить цвет" />
                  <button className="link" onClick={() => showConnection(c)}>
                    {nodeName(c.source_id)} → {nodeName(c.target_id)}
                    <span className="conn-meta">
                      {c.protocol ?? 'any'}
                      {c.port ? ':' + c.port : ''}
                    </span>
                  </button>
                  <button className="del" onClick={() => deleteConnection(c.id)}>✕</button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {pathResult && (
          <section className="path-result">
            {pathResult.firewalls.length > 0 ? (
              <div>МЭ на пути: {pathResult.firewalls.length}</div>
            ) : (
              <div>В пределах одного ЦОД</div>
            )}
          </section>
        )}

        <div className="status">{status}</div>
      </aside>

      <main className="canvas">
        <ReactFlow
          nodes={displayNodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onNodeDoubleClick={(_event, node) => openEdit(node.id)}
          nodeTypes={nodeTypes}
          fitView
        >
          <Background color={theme === 'dark' ? '#1e293b' : '#e2e8f0'} />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </main>

      {editingNode && editingType && (
        <div className="modal-backdrop" onClick={handleEditCancel}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Свойства объекта</h2>
            <label>Название</label>
            <input value={editName} onChange={(e) => setEditName(e.target.value)} autoFocus />
            <label>Тип: {DEFAULT_NAMES[editingType]}</label>
            {editingParentType && (
              <>
                <label>Родитель</label>
                <select value={editParent} onChange={(e) => setEditParent(e.target.value)}>
                  <option value="">— нет —</option>
                  {nodes
                    .filter((n) => editingParentType.includes(n.type as NodeType) && n.id !== editingNodeId)
                    .map((n) => (
                      <option key={n.id} value={n.id}>
                        {n.data.name}
                      </option>
                    ))}
                </select>
              </>
            )}
            {editingFields.map((f) => (
              <div key={f.key} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <label>{f.label}</label>
                <input
                  value={editAttrs[f.key] ?? ''}
                  placeholder={f.placeholder}
                  onChange={(e) => setEditAttrs((prev) => ({ ...prev, [f.key]: e.target.value }))}
                />
              </div>
            ))}
            <div className="row">
              <button onClick={handleEditCancel}>Отмена</button>
              <button className="primary" onClick={handleEditSave}>Сохранить</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
