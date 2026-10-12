import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
} from '@xyflow/react';
import type { Connection, Edge, Node, NodeTypes } from '@xyflow/react';

import { DeviceNode } from './nodes';
import type { DeviceData } from './nodes';
import {
  analyzePath,
  createProject,
  deleteProject,
  getProject,
  listProjects,
  saveProject,
} from './api';
import type { ProjectSummary } from './api';
import type { Connection as Interaction, GraphLink, GraphNode, NodeType, PathResult, Project } from './types';

const nodeTypes: NodeTypes = {
  server: DeviceNode,
  firewall: DeviceNode,
  network: DeviceNode,
  datacenter: DeviceNode,
};

const DEFAULT_NAMES: Record<NodeType, string> = {
  server: 'Сервер',
  firewall: 'МЭ',
  network: 'Сеть',
  datacenter: 'ЦОД',
};

const NODE_TYPES: NodeType[] = ['server', 'firewall', 'network', 'datacenter'];

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
  firewall: [
    { key: 'zones', label: 'Зоны/интерфейсы', placeholder: 'outside, inside' },
  ],
  network: [
    { key: 'cidr', label: 'CIDR', placeholder: '10.0.0.0/24' },
    { key: 'vlan', label: 'VLAN', placeholder: '100' },
  ],
  datacenter: [
    { key: 'location', label: 'Расположение', placeholder: 'Москва' },
  ],
};

const PARENT_TYPES: Partial<Record<NodeType, NodeType>> = {
  server: 'network',
  firewall: 'datacenter',
  network: 'datacenter',
};

function genId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'id-' + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function toGraph(
  nodes: Node<DeviceData>[],
  edges: Edge[],
): { nodes: GraphNode[]; links: GraphLink[] } {
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
    links: edges.map((e) => ({
      id: e.id,
      source_id: e.source,
      target_id: e.target,
      label: typeof e.label === 'string' ? e.label : undefined,
      attributes: {},
    })),
  };
}

function fromProject(project: Project): { nodes: Node<DeviceData>[]; edges: Edge[] } {
  const nodes: Node<DeviceData>[] = project.nodes.map((n) => ({
    id: n.id,
    type: n.type,
    position: { x: n.x, y: n.y },
    data: { name: n.name, parent_id: n.parent_id ?? undefined, attributes: n.attributes },
  }));
  const edges: Edge[] = project.links.map((l) => ({
    id: l.id,
    source: l.source_id,
    target: l.target_id,
    label: l.label ?? undefined,
  }));
  return { nodes, edges };
}

export default function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<DeviceData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

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

  const [connections, setConnections] = useState<Interaction[]>([]);
  const [pathResult, setPathResult] = useState<PathResult | null>(null);

  const [connSource, setConnSource] = useState('');
  const [connTarget, setConnTarget] = useState('');
  const [connProtocol, setConnProtocol] = useState('tcp');
  const [connPort, setConnPort] = useState('');

  const [editingNodeId, setEditingNodeId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editParent, setEditParent] = useState('');
  const [editAttrs, setEditAttrs] = useState<Record<string, string>>({});

  const onConnect = useCallback(
    (conn: Connection) => {
      const edge: Edge = { ...conn, id: genId() };
      setEdges((eds) => addEdge(edge, eds));
    },
    [setEdges],
  );

  const addNode = useCallback(
    (type: NodeType) => {
      const node: Node<DeviceData> = {
        id: genId(),
        type,
        position: { x: 80 + Math.random() * 320, y: 80 + Math.random() * 220 },
        data: { name: DEFAULT_NAMES[type], parent_id: null, attributes: {} },
      };
      setNodes((nds) => nds.concat(node));
    },
    [setNodes],
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
      const graph = toGraph(nodes, edges);
      let pid = projectId;
      if (pid == null) {
        const created = await createProject(projectName || 'Без названия', owner.trim());
        pid = created.id;
        setProjectId(pid);
      }
      await saveProject(pid, {
        name: projectName,
        nodes: graph.nodes,
        links: graph.links,
        connections,
      });
      setStatus('Сохранено (проект #' + pid + ')');
      await refreshProjects();
    } catch (e) {
      setStatus((e as Error).message);
    }
  }, [owner, projectName, projectId, nodes, edges, connections, refreshProjects]);

  const handleLoad = useCallback(
    async (id: number) => {
      try {
        const project = await getProject(id);
        const { nodes: ns, edges: es } = fromProject(project);
        setNodes(ns);
        setEdges(es);
        setConnections(project.connections);
        setProjectId(project.id);
        setProjectName(project.name);
        setPathResult(null);
        setStatus('Загружен проект #' + id);
      } catch (e) {
        setStatus((e as Error).message);
      }
    },
    [setNodes, setEdges, setConnections],
  );

  const handleNew = useCallback(() => {
    setNodes([]);
    setEdges([]);
    setConnections([]);
    setProjectId(null);
    setProjectName('Схема L2');
    setPathResult(null);
    setStatus('');
  }, [setNodes, setEdges, setConnections]);

  const handleDelete = useCallback(
    async (id: number) => {
      try {
        await deleteProject(id);
        if (projectId === id) {
          setNodes([]);
          setEdges([]);
          setConnections([]);
          setProjectId(null);
          setProjectName('Схема L2');
          setPathResult(null);
        }
        await refreshProjects();
        setStatus('Проект удалён');
      } catch (e) {
        setStatus((e as Error).message);
      }
    },
    [projectId, setNodes, setEdges, setConnections, refreshProjects],
  );

  const handleAddConnection = useCallback(() => {
    if (!connSource || !connTarget) {
      setStatus('Выберите два узла для взаимодействия');
      return;
    }
    if (connSource === connTarget) {
      setStatus('Выберите разные узлы');
      return;
    }
    const conn: Interaction = {
      id: genId(),
      source_id: connSource,
      target_id: connTarget,
      protocol: connProtocol || undefined,
      port: connPort || undefined,
      attributes: {},
    };
    setConnections((cs) => cs.concat(conn));
    setConnPort('');
  }, [connSource, connTarget, connProtocol, connPort]);

  const handleShowConnection = useCallback(
    async (conn: Interaction) => {
      try {
        const graph = toGraph(nodes, edges);
        const res = await analyzePath(graph.nodes, graph.links, conn.source_id, conn.target_id);
        setPathResult(res);
        setStatus(
          res.found
            ? 'Взаимодействие: ' + res.firewalls.length + ' МЭ на пути'
            : 'Путь не найден',
        );
      } catch (e) {
        setStatus((e as Error).message);
      }
    },
    [nodes, edges],
  );

  const handleDeleteConnection = useCallback((id: string) => {
    setConnections((cs) => cs.filter((c) => c.id !== id));
  }, []);

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
                parent_id: editParent || null,
                attributes: editAttrs,
              },
            }
          : n,
      ),
    );
    setEditingNodeId(null);
  }, [editingNodeId, editName, editParent, editAttrs, setNodes]);

  const handleEditCancel = useCallback(() => {
    setEditingNodeId(null);
  }, []);

  const highlighted = useMemo(() => {
    const nodeIds = new Set<string>();
    const edgeIds = new Set<string>();
    if (pathResult?.found) {
      pathResult.path.forEach((id) => nodeIds.add(id));
      for (let i = 0; i < pathResult.path.length - 1; i++) {
        const a = pathResult.path[i];
        const b = pathResult.path[i + 1];
        edges.forEach((e) => {
          if ((e.source === a && e.target === b) || (e.source === b && e.target === a)) {
            edgeIds.add(e.id);
          }
        });
      }
    }
    return { nodeIds, edgeIds };
  }, [pathResult, edges]);

  const firewalls = useMemo(() => new Set(pathResult?.firewalls ?? []), [pathResult]);

  const styledNodes = useMemo(
    () =>
      nodes.map((n) => {
        const cls = firewalls.has(n.id)
          ? 'firewall-node'
          : highlighted.nodeIds.has(n.id)
            ? 'path-node'
            : '';
        return cls ? { ...n, className: cls } : n;
      }),
    [nodes, firewalls, highlighted],
  );

  const styledEdges = useMemo(
    () =>
      edges.map((e) =>
        highlighted.edgeIds.has(e.id)
          ? { ...e, style: { stroke: '#f59e0b', strokeWidth: 3 } }
          : e,
      ),
    [edges, highlighted],
  );

  const ownerChange = (value: string) => {
    setOwner(value);
    localStorage.setItem('vsdoox.owner', value);
  };

  const editingNode = editingNodeId ? nodes.find((n) => n.id === editingNodeId) ?? null : null;
  const editingType: NodeType | null = editingNode
    ? ((editingNode.type as NodeType) ?? 'server')
    : null;
  const editingFields = editingType ? ATTR_FIELDS[editingType] : [];
  const parentType = editingType ? PARENT_TYPES[editingType] : undefined;

  const nodeName = (id: string): string =>
    nodes.find((n) => n.id === id)?.data.name ?? id;

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>
            <span className="logo-mark">V</span>
            vsdoox · сетевые схемы
          </h1>
          <button
            className="theme-toggle"
            onClick={toggleTheme}
            title={theme === 'light' ? 'Тёмная тема' : 'Светлая тема'}
          >
            {theme === 'light' ? '🌙' : '☀️'}
          </button>
        </div>

        <section>
          <label>Владелец</label>
          <input
            value={owner}
            onChange={(e) => ownerChange(e.target.value)}
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
          <label>Добавить узел</label>
          <div className="palette">
            {NODE_TYPES.map((t) => (
              <button key={t} onClick={() => addNode(t)}>
                {DEFAULT_NAMES[t]}
              </button>
            ))}
          </div>
        </section>

        <section>
          <label>Взаимодействия (протокол/порт)</label>
          <select value={connSource} onChange={(e) => setConnSource(e.target.value)}>
            <option value="">— откуда —</option>
            {nodes.map((n) => (
              <option key={n.id} value={n.id}>
                {n.data.name}
              </option>
            ))}
          </select>
          <select value={connTarget} onChange={(e) => setConnTarget(e.target.value)}>
            <option value="">— куда —</option>
            {nodes.map((n) => (
              <option key={n.id} value={n.id}>
                {n.data.name}
              </option>
            ))}
          </select>
          <div className="row">
            <select value={connProtocol} onChange={(e) => setConnProtocol(e.target.value)}>
              <option value="tcp">TCP</option>
              <option value="udp">UDP</option>
              <option value="icmp">ICMP</option>
              <option value="any">ANY</option>
            </select>
            <input
              value={connPort}
              onChange={(e) => setConnPort(e.target.value)}
              placeholder="Порт"
            />
          </div>
          <button className="primary" onClick={handleAddConnection}>
            Добавить взаимодействие
          </button>
          {connections.length > 0 && (
            <ul className="connections">
              {connections.map((c) => (
                <li key={c.id}>
                  <button className="link" onClick={() => handleShowConnection(c)}>
                    {nodeName(c.source_id)} → {nodeName(c.target_id)}
                    <span className="conn-meta">
                      {c.protocol ?? 'any'}
                      {c.port ? ':' + c.port : ''}
                    </span>
                  </button>
                  <button className="del" onClick={() => handleDeleteConnection(c.id)}>✕</button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {pathResult && (
          <section className="path-result">
            {pathResult.found ? (
              <>
                <div>МЭ на пути: {pathResult.firewalls.length}</div>
                <div className="path-chain">
                  {pathResult.path
                    .map((id) => nodes.find((n) => n.id === id)?.data.name ?? id)
                    .join(' → ')}
                </div>
              </>
            ) : (
              <div>Путь не найден</div>
            )}
          </section>
        )}

        <div className="status">{status}</div>
      </aside>

      <main className="canvas">
        <ReactFlow
          nodes={styledNodes}
          edges={styledEdges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeDoubleClick={(_event, node) => {
            setEditingNodeId(node.id);
            setEditName(node.data.name);
            setEditParent((node.data.parent_id as string) ?? '');
            const attrs: Record<string, string> = {};
            const a = node.data.attributes ?? {};
            Object.keys(a).forEach((k) => {
              attrs[k] = typeof a[k] === 'string' ? a[k] : String(a[k]);
            });
            setEditAttrs(attrs);
          }}
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
            <h2>Свойства узла</h2>
            <label>Название</label>
            <input value={editName} onChange={(e) => setEditName(e.target.value)} autoFocus />
            <label>Тип: {DEFAULT_NAMES[editingType]}</label>
            {parentType && (
              <>
                <label>Родитель: {DEFAULT_NAMES[parentType]}</label>
                <select value={editParent} onChange={(e) => setEditParent(e.target.value)}>
                  <option value="">— нет —</option>
                  {nodes
                    .filter((n) => n.type === parentType && n.id !== editingNodeId)
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
