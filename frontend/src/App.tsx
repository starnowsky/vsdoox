import { useCallback, useEffect, useMemo, useState } from 'react';
import { ReactFlow, Background, Controls, MiniMap, useNodesState } from '@xyflow/react';
import type { Edge, Node, NodeTypes } from '@xyflow/react';

import { DatacenterNode, DeviceNode, NetworkNode } from './nodes';
import type { DeviceData } from './nodes';
import { WaypointEdge } from './edges';
import {
  authLogin,
  createCustomType,
  createProject,
  deleteCustomType,
  deleteProject,
  exportConnectionsXlsx,
  exportVSDX,
  getCatalogProject,
  getProject,
  keycloakConfig,
  keycloakLoginUrl,
  listCustomTypes,
  listObjects,
  listProjects,
  saveProject,
} from './api';
import type { CustomType, ObjectItem, ProjectSummary } from './api';
import type { Connection as Interaction, GraphLink, GraphNode, NodeType } from './types';

const BUILTIN_NODE_TYPES: NodeTypes = {
  server: DeviceNode,
  firewall: DeviceNode,
  network: NetworkNode,
  datacenter: DatacenterNode,
};

const edgeTypes = { waypoint: WaypointEdge };

const DEFAULT_NAMES: Record<string, string> = {
  server: 'SRV',
  firewall: 'FW',
  network: 'NET',
  datacenter: 'DC',
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
  server: ['network', 'firewall', 'datacenter'],
  firewall: ['datacenter'],
  network: ['firewall', 'datacenter'],
};

function primaryAttrFor(type: string): AttrField {
  return PRIMARY_ATTR[type as NodeType] ?? { key: 'ip', label: 'IP-адрес', placeholder: '10.0.0.10' };
}

function parentOptionsFor(type: string): NodeType[] | undefined {
  if (type === 'datacenter') return undefined;
  const p = PARENT_OPTIONS[type as NodeType];
  if (p) return p;
  return ['network', 'firewall', 'datacenter'];
}

function typeName(type: string): string {
  return DEFAULT_NAMES[type] ?? type;
}

const CONN_COLORS = ['#4a6b8a', '#a86a6a', '#6a8a6a', '#a88a5a', '#7a6a9a', '#7a7f86'];
const DEFAULT_CONN_COLOR = CONN_COLORS[0];

const DC_W = 340;
const DC_HEADER = 46;
const DC_PAD = 14;
const NW_HEADER = 30;
const NW_PAD = 8;
const NW_GAP = 10;
const SRV_W = 140;
const SRV_H = 72;
const SRV_GAP = 8;
const DC_MARGIN = 30;
const FW_W = 110;
const FW_GAP = 16;
const FW_BETWEEN = 48;
const SRV_COLUMNS = Math.max(1, Math.floor(((DC_W - 2 * DC_PAD - 2 * NW_PAD) + SRV_GAP) / (SRV_W + SRV_GAP)));

function genId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'id-' + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function resolveVisualParentId(nodeId: string, nodes: Node<DeviceData>[]): string | undefined {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  let cur = byId.get(nodeId);
  let guard = 0;
  while (cur && guard++ < 20) {
    const pid = cur.data.parent_id as string | undefined;
    const parent = pid ? byId.get(pid) : undefined;
    if (parent && (parent.type === 'network' || parent.type === 'datacenter')) return parent.id;
    cur = parent;
  }
  return undefined;
}

function visualParentFor(logicalParentId: string | null, nodes: Node<DeviceData>[]): string | undefined {
  if (!logicalParentId) return undefined;
  const parent = nodes.find((n) => n.id === logicalParentId);
  if (!parent) return undefined;
  if (parent.type === 'network' || parent.type === 'datacenter') return parent.id;
  return resolveVisualParentId(parent.id, nodes);
}

function collectFirewalls(nodeId: string, nodes: Node<DeviceData>[]): string[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const fws: string[] = [];
  let cur = byId.get(nodeId);
  let guard = 0;
  while (cur && guard++ < 20) {
    const current = cur;
    if (current.type === 'firewall') fws.push(current.id);
    if (current.type === 'datacenter') {
      const dcFw = nodes.find((n) => n.type === 'firewall' && n.data.parent_id === current.id);
      if (dcFw) fws.push(dcFw.id);
    }
    const pid = current.data.parent_id as string | undefined;
    cur = pid ? byId.get(pid) : undefined;
  }
  return [...new Set(fws)];
}

function connColor(c: Interaction): string {
  const col = c.attributes && typeof c.attributes.color === 'string' ? c.attributes.color : '';
  return col || DEFAULT_CONN_COLOR;
}

function closestSide(from: { x: number; y: number }, to: { x: number; y: number }): string {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (Math.abs(dx) > Math.abs(dy)) return dx > 0 ? 'right' : 'left';
  return dy > 0 ? 'bottom' : 'top';
}

function absolutePositions(nodes: Node<DeviceData>[]): Map<string, { x: number; y: number }> {
  const abs = new Map<string, { x: number; y: number }>();
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const getAbs = (id: string): { x: number; y: number } => {
    const cached = abs.get(id);
    if (cached) return cached;
    const n = byId.get(id);
    if (!n) return { x: 0, y: 0 };
    const base = n.parentId ? getAbs(n.parentId) : { x: 0, y: 0 };
    const r = { x: base.x + n.position.x, y: base.y + n.position.y };
    abs.set(id, r);
    return r;
  };
  nodes.forEach((n) => abs.set(n.id, getAbs(n.id)));
  return abs;
}

function toGraph(
  nodes: Node<DeviceData>[],
  connections: Interaction[],
): { nodes: GraphNode[]; links: GraphLink[]; connections: unknown[] } {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.type ?? 'server',
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
      description: c.description ?? null,
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
    const visualParent = resolveVisualParentId(n.id, base);
    return {
      ...n,
      parentId: visualParent,
      extent: visualParent && n.type !== 'firewall' ? ('parent' as const) : undefined,
    };
  });
}

function computeSizes(nodes: Node<DeviceData>[]): Map<string, { w: number; h: number }> {
  const sizes = new Map<string, { w: number; h: number }>();
  nodes.filter((n) => n.type === 'network').forEach((nw) => {
    const count = nodes.filter((s) => s.parentId === nw.id).length;
    const rows = Math.max(1, Math.ceil(count / SRV_COLUMNS));
    sizes.set(nw.id, { w: DC_W - 2 * DC_PAD, h: NW_HEADER + NW_PAD + rows * (SRV_H + SRV_GAP) + NW_PAD });
  });
  nodes.filter((n) => n.type === 'datacenter').forEach((dc) => {
    const networks = nodes.filter((n) => n.parentId === dc.id && n.type === 'network');
    const direct = nodes.filter((n) => n.parentId === dc.id && n.type === 'server').length;
    const directRows = Math.max(1, Math.ceil(direct / SRV_COLUMNS));
    let h = DC_HEADER + DC_PAD;
    networks.forEach((nw) => {
      h += (sizes.get(nw.id)?.h ?? 60) + NW_GAP;
    });
    h += directRows * (SRV_H + SRV_GAP) + DC_PAD;
    sizes.set(dc.id, { w: DC_W, h: Math.max(h, 130) });
  });
  nodes.filter((n) => n.type === 'firewall').forEach((fw) => {
    const dc = fw.parentId ? sizes.get(fw.parentId) : undefined;
    if (dc) sizes.set(fw.id, { w: FW_W, h: dc.h });
  });
  nodes.filter((n) => n.type === 'server').forEach((srv) => {
    sizes.set(srv.id, { w: SRV_W, h: SRV_H });
  });
  return sizes;
}

function applySizes(nodes: Node<DeviceData>[]): Node<DeviceData>[] {
  const sizes = computeSizes(nodes);
  return nodes.map((n) => {
    const s = sizes.get(n.id);
    const zIndex = 10;
    return s ? { ...n, style: { width: s.w, height: s.h }, zIndex } : { ...n, zIndex };
  });
}

function autoLayout(nodes: Node<DeviceData>[]): Node<DeviceData>[] {
  const sizes = computeSizes(nodes);
  const positions = new Map<string, { x: number; y: number }>();
  const dcs = nodes.filter((n) => n.type === 'datacenter');
  let cursor = DC_MARGIN;
  dcs.forEach((dc, i) => {
    const networks = nodes.filter((n) => n.parentId === dc.id && n.type === 'network');
    const fw = nodes.find((n) => n.type === 'firewall' && n.parentId === dc.id);
    const directServers = nodes.filter((n) => n.parentId === dc.id && n.type === 'server');
    let y = DC_HEADER + DC_PAD;
    for (const nw of networks) {
      positions.set(nw.id, { x: DC_PAD, y });
      const servers = nodes.filter((n) => n.parentId === nw.id);
      servers.forEach((srv, idx) => {
        const col = idx % SRV_COLUMNS;
        const row = Math.floor(idx / SRV_COLUMNS);
        positions.set(srv.id, { x: NW_PAD + col * (SRV_W + SRV_GAP), y: NW_HEADER + NW_PAD + row * (SRV_H + SRV_GAP) });
      });
      y += (sizes.get(nw.id)?.h ?? 60) + NW_GAP;
    }
    directServers.forEach((srv, idx) => {
      const col = idx % SRV_COLUMNS;
      const row = Math.floor(idx / SRV_COLUMNS);
      positions.set(srv.id, { x: DC_PAD + col * (SRV_W + SRV_GAP), y: y + row * (SRV_H + SRV_GAP) });
    });
    y += Math.ceil(directServers.length / SRV_COLUMNS) * (SRV_H + SRV_GAP);
    const side: 'right' | 'left' = i === 0 ? 'right' : 'left';
    if (side === 'right') {
      positions.set(dc.id, { x: cursor, y: DC_MARGIN });
      if (fw) positions.set(fw.id, { x: DC_W + FW_GAP, y: 0 });
      cursor += DC_W + FW_GAP + FW_W + FW_BETWEEN;
    } else {
      if (fw) positions.set(fw.id, { x: -(FW_W + FW_GAP), y: 0 });
      positions.set(dc.id, { x: cursor + FW_W + FW_GAP, y: DC_MARGIN });
      cursor += FW_W + FW_GAP + DC_W + FW_BETWEEN;
    }
  });
  return nodes.map((n) => {
    const p = positions.get(n.id);
    return p ? { ...n, position: p } : n;
  });
}

type Tab = 'manage' | 'objects' | 'library' | 'settings';

export default function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<DeviceData>>([]);
  const [connections, setConnections] = useState<Interaction[]>([]);

  const [userToken, setUserToken] = useState<string>(() => localStorage.getItem('vsdoox.user.token') ?? '');
  const [loginUser, setLoginUser] = useState('');
  const [loginPass, setLoginPass] = useState('');
  const [loginError, setLoginError] = useState('');

  const [owner, setOwner] = useState<string>(() => localStorage.getItem('vsdoox.owner') ?? '');
  const [projectName, setProjectName] = useState('Схема L2');
  const [projectId, setProjectId] = useState<number | null>(null);
  const [projectOwner, setProjectOwner] = useState<string | null>(null);
  const [kcEnabled, setKcEnabled] = useState(false);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [status, setStatus] = useState('');
  const [tab, setTab] = useState<Tab>('manage');
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('vsdoox.theme');
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('vsdoox.theme', theme);
  }, [theme]);

  const [customTypes, setCustomTypes] = useState<CustomType[]>([]);
  const [newTypeName, setNewTypeName] = useState('');

  useEffect(() => {
    listCustomTypes()
      .then((r) => setCustomTypes(r.types))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!userToken) return;
    listObjects()
      .then((r) => setLibrary(r.objects))
      .catch(() => {});
  }, [userToken]);

  // Keycloak-callback (?kc_token=...&kc_user=...) и открытие проекта из каталога (?project=...).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const kcToken = params.get('kc_token');
    const kcUser = params.get('kc_user');
    const projParam = params.get('project');

    if (kcToken && kcUser) {
      localStorage.setItem('vsdoox.user.token', kcToken);
      localStorage.setItem('vsdoox.user.name', kcUser);
      localStorage.setItem('vsdoox.owner', kcUser);
      setUserToken(kcToken);
      setOwner(kcUser);
      window.history.replaceState({}, '', '/');
    }

    if (projParam) {
      getCatalogProject(Number(projParam))
        .then((project) => {
          setNodes(toRfNodes(project.nodes));
          setConnections(project.connections);
          setProjectId(project.id);
          setProjectName(project.name);
          setProjectOwner(project.owner);
          setPathResult(null);
        })
        .catch(() => {});
      window.history.replaceState({}, '', '/');
    }

    keycloakConfig()
      .then((c) => setKcEnabled(c.enabled))
      .catch(() => setKcEnabled(false));
  }, [setNodes]);

  const [eType, setEType] = useState<string>('server');
  const [eName, setEName] = useState('');
  const [eParent, setEParent] = useState('');
  const [eAttr, setEAttr] = useState('');

  const [cSource, setCSource] = useState('');
  const [cTarget, setCTarget] = useState('');
  const [cProtocol, setCProtocol] = useState('tcp');
  const [cPort, setCPort] = useState('');
  const [cDescription, setCDescription] = useState('');
  const [cColor, setCColor] = useState(DEFAULT_CONN_COLOR);
  const [cParent, setCParent] = useState('');

  const [editingNodeId, setEditingNodeId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editParent, setEditParent] = useState('');
  const [editAttrs, setEditAttrs] = useState<Record<string, string>>({});

  const [pathResult, setPathResult] = useState<{ found: boolean; path: string[]; firewalls: string[] } | null>(null);
  const [showConnTable, setShowConnTable] = useState(false);
  const [library, setLibrary] = useState<ObjectItem[]>([]);

  const displayNodes = useMemo(() => applySizes(nodes), [nodes]);

  const rfNodeTypes = useMemo<NodeTypes>(() => {
    const types: NodeTypes = { ...BUILTIN_NODE_TYPES };
    customTypes.forEach((t) => {
      types[t.name] = DeviceNode;
    });
    return types;
  }, [customTypes]);

  const edges = useMemo<Edge[]>(() => {
    const pathNodes = new Set(pathResult?.path ?? []);
    const abs = absolutePositions(nodes);
    const sizes = computeSizes(nodes);
    const groups = new Map<string, Interaction[]>();
    connections.forEach((c) => {
      const key = [c.source_id, c.target_id].sort().join('->');
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(c);
    });
    return connections.map((c) => {
      const key = [c.source_id, c.target_id].sort().join('->');
      const group = groups.get(key) ?? [c];
      const parallelIndex = group.findIndex((g) => g.id === c.id);
      const color = connColor(c);
      const label = (c.protocol ?? 'any') + (c.port ? ':' + c.port : '');
      const highlighted = pathNodes.has(c.source_id) && pathNodes.has(c.target_id);

      const sp = abs.get(c.source_id) ?? { x: 0, y: 0 };
      const tp = abs.get(c.target_id) ?? { x: 0, y: 0 };
      const ss = sizes.get(c.source_id) ?? { w: 130, h: 48 };
      const ts = sizes.get(c.target_id) ?? { w: 130, h: 48 };
      const sc = { x: sp.x + ss.w / 2, y: sp.y + ss.h / 2 };
      const tc = { x: tp.x + ts.w / 2, y: tp.y + ts.h / 2 };

      const parentId = c.attributes && typeof c.attributes.parent_id === 'string' ? c.attributes.parent_id : undefined;
      const fwIds = parentId
        ? [parentId]
        : [...new Set([...collectFirewalls(c.source_id, nodes), ...collectFirewalls(c.target_id, nodes)])];
      const waypoints = fwIds
        .filter((id) => id !== c.source_id && id !== c.target_id)
        .map((id) => {
          const p = abs.get(id) ?? { x: 0, y: 0 };
          const s = sizes.get(id) ?? { w: 100, h: 50 };
          return { x: p.x + s.w / 2, y: p.y + s.h / 2 };
        });
      const hasWaypoints = waypoints.length > 0;

      return {
        id: 'conn-' + c.id,
        source: c.source_id,
        target: c.target_id,
        sourceHandle: 's-' + closestSide(sc, tc),
        targetHandle: 't-' + closestSide(tc, sc),
        type: hasWaypoints ? 'waypoint' : 'smoothstep',
        label,
        data: hasWaypoints ? { waypoints } : undefined,
        pathOptions: hasWaypoints ? undefined : { offset: 30 + parallelIndex * 40, borderRadius: 8 },
        style: { stroke: color, strokeWidth: highlighted ? 3 : 2 },
        labelStyle: { fill: 'var(--text)', fontSize: 11, fontWeight: 600 },
        labelBgStyle: { fill: 'var(--surface)', fillOpacity: 0.92 },
        labelBgPadding: [5, 3] as [number, number],
        labelBgBorderRadius: 4,
        zIndex: 100,
      } as unknown as Edge;
    });
  }, [connections, pathResult, nodes]);

  const parentOptions = useMemo(() => {
    const allowed = parentOptionsFor(eType);
    if (!allowed) return [];
    return nodes.filter((n) => allowed.includes(n.type as NodeType));
  }, [eType, nodes]);

  const handleLogin = async () => {
    setLoginError('');
    try {
      const res = await authLogin(loginUser, loginPass);
      localStorage.setItem('vsdoox.user.token', res.token);
      localStorage.setItem('vsdoox.user.name', res.username);
      setUserToken(res.token);
      setOwner(res.username);
      localStorage.setItem('vsdoox.owner', res.username);
    } catch (e) {
      setLoginError((e as Error).message);
    }
  };

  const handleKeycloakLogin = () => {
    window.location.href = keycloakLoginUrl();
  };

  const handleLogout = () => {
    localStorage.removeItem('vsdoox.user.token');
    localStorage.removeItem('vsdoox.user.name');
    setUserToken('');
  };

  const handleAddCustomType = async () => {
    setStatus('');
    try {
      await createCustomType(newTypeName);
      setNewTypeName('');
      setCustomTypes((await listCustomTypes()).types);
    } catch (e) {
      setStatus((e as Error).message);
    }
  };

  const handleDeleteCustomType = async (id: number) => {
    try {
      await deleteCustomType(id);
      setCustomTypes((await listCustomTypes()).types);
    } catch (e) {
      setStatus((e as Error).message);
    }
  };

  const addEntity = useCallback(() => {
    const name = eName.trim() || typeName(eType);
    const logicalParent: string | null = eType === 'datacenter' ? null : eParent || null;
    const visualParent = visualParentFor(logicalParent, nodes);

    const attrs: Record<string, unknown> = {};
    const pf = primaryAttrFor(eType);
    if (eAttr.trim() && pf) {
      attrs[pf.key] = eAttr.trim();
    }

    const node: Node<DeviceData> = {
      id: genId(),
      type: eType,
      position: { x: 0, y: 0 },
      parentId: visualParent,
      extent: visualParent && eType !== 'firewall' ? ('parent' as const) : undefined,
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

  const addLibraryObject = useCallback(
    (obj: ObjectItem) => {
      const node: Node<DeviceData> = {
        id: genId(),
        type: obj.type,
        position: { x: 0, y: 0 },
        data: { name: obj.name, attributes: obj.attributes ?? {} },
      };
      setNodes((nds) => autoLayout(nds.concat(node)));
      setStatus('Добавлен объект из библиотеки: ' + obj.name);
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
      description: cDescription.trim() || undefined,
      attributes: { color: cColor, parent_id: cParent || undefined },
    };
    setConnections((cs) => cs.concat(conn));
    setCPort('');
    setCDescription('');
    setCParent('');
  }, [cSource, cTarget, cProtocol, cPort, cDescription, cColor, cParent]);

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
      const firewalls = [
        ...new Set([...collectFirewalls(c.source_id, nodes), ...collectFirewalls(c.target_id, nodes)]),
      ];
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
      // Если открыт чужой проект — сохраняем как копию в своём пространстве.
      if (pid != null && projectOwner != null && projectOwner !== owner.trim()) {
        pid = null;
        setProjectId(null);
      }
      if (pid == null) {
        const created = await createProject(projectName || 'Без названия', owner.trim());
        pid = created.id;
        setProjectId(pid);
        setProjectOwner(owner.trim());
      }
      await saveProject(pid, { name: projectName, ...graph });
      setStatus('Сохранено (проект #' + pid + ')');
      await refreshProjects();
    } catch (e) {
      setStatus((e as Error).message);
    }
  }, [owner, projectName, projectId, projectOwner, nodes, connections, refreshProjects]);

  const handleExport = useCallback(async () => {
    try {
      const sizes = computeSizes(nodes);
      const abs = absolutePositions(nodes);
      const payloadNodes = nodes.map((n) => {
        const p = abs.get(n.id) ?? { x: 0, y: 0 };
        const s = sizes.get(n.id) ?? { w: 130, h: 48 };
        return {
          id: n.id,
          type: n.type,
          name: n.data.name,
          x: p.x,
          y: p.y,
          w: s.w,
          h: s.h,
          attributes: n.data.attributes ?? {},
        };
      });

      const blob = await exportVSDX({
        title: projectName,
        nodes: payloadNodes,
        connections: connections.map((c) => ({
          source_id: c.source_id,
          target_id: c.target_id,
          protocol: c.protocol,
          port: c.port,
          color:
            c.attributes && typeof c.attributes.color === 'string' ? c.attributes.color : undefined,
        })),
      });

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = (projectName || 'Схема') + '.vsdx';
      a.click();
      URL.revokeObjectURL(url);
      setStatus('Файл .vsdx скачан');
    } catch (e) {
      setStatus((e as Error).message);
    }
  }, [nodes, connections, projectName]);

  const handleExportConnXlsx = useCallback(async () => {
    try {
      const blob = await exportConnectionsXlsx({
        title: projectName,
        nodes: nodes.map((n) => ({ id: n.id, name: n.data.name })),
        connections: connections.map((c) => ({
          source_id: c.source_id,
          target_id: c.target_id,
          protocol: c.protocol,
          port: c.port,
          description: c.description,
        })),
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = (projectName || 'Схема') + ' - связи.xlsx';
      a.click();
      URL.revokeObjectURL(url);
      setStatus('Таблица связей выгружена в Excel');
    } catch (e) {
      setStatus((e as Error).message);
    }
  }, [nodes, connections, projectName]);

  const handleLoad = useCallback(
    async (id: number) => {
      try {
        const project = await getProject(id);
        setNodes(toRfNodes(project.nodes));
        setConnections(project.connections);
        setProjectId(project.id);
        setProjectName(project.name);
        setProjectOwner(project.owner);
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
    setProjectOwner(null);
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
      autoLayout(
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
      ),
    );
    setEditingNodeId(null);
  }, [editingNodeId, editName, editParent, editAttrs, setNodes]);

  const handleEditCancel = useCallback(() => setEditingNodeId(null), []);

  const nodeName = (id: string): string => nodes.find((n) => n.id === id)?.data.name ?? id;

  const editingNode = editingNodeId ? nodes.find((n) => n.id === editingNodeId) ?? null : null;
  const editingType: string | null = editingNode ? editingNode.type ?? 'server' : null;
  const editingFields = editingType
    ? ATTR_FIELDS[editingType as NodeType] ?? [{ key: 'ip', label: 'IP-адрес', placeholder: '10.0.0.10' }]
    : [];
  const editingParentType = editingType ? parentOptionsFor(editingType) : undefined;

  if (!userToken) {
    return (
      <div className="login-page">
        <div className="login-card">
          <h1>vsdoox · сетевые схемы</h1>
          <p className="muted">Вход по логину и паролю</p>
          <input value={loginUser} onChange={(e) => setLoginUser(e.target.value)} placeholder="Логин" autoFocus />
          <input type="password" value={loginPass} onChange={(e) => setLoginPass(e.target.value)} placeholder="Пароль" />
          <button className="primary" onClick={handleLogin}>Войти</button>
          {kcEnabled && (
            <button onClick={handleKeycloakLogin}>Войти через Keycloak</button>
          )}
          {loginError && <div className="error">{loginError}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <div className="top-actions">
        <button className="admin-btn" onClick={() => window.open('/catalog', '_blank')} title="Каталог проектов">каталог</button>
        <button className="admin-btn" onClick={() => window.open('/admin', '_blank')} title="Администрирование">admin</button>
      </div>
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>
            <span className="logo-mark">V</span>
            vsdoox · сетевые схемы
          </h1>
        </div>

        <div className="tabs">
          <button className={'tab' + (tab === 'manage' ? ' active' : '')} onClick={() => setTab('manage')}>Управление</button>
          <button className={'tab' + (tab === 'objects' ? ' active' : '')} onClick={() => setTab('objects')}>Объекты</button>
          <button className={'tab' + (tab === 'library' ? ' active' : '')} onClick={() => setTab('library')}>Библиотека</button>
          <button className={'tab' + (tab === 'settings' ? ' active' : '')} onClick={() => setTab('settings')}>Настройки</button>
        </div>

        {tab === 'manage' && (
          <>
            <section>
              <label>Название схемы</label>
              <input value={projectName} onChange={(e) => setProjectName(e.target.value)} />
            </section>

            <div className="row">
              <button onClick={handleNew}>Новая</button>
              <button className="primary" onClick={handleSave}>
                {projectOwner != null && projectOwner !== owner ? 'Сохранить копию' : 'Сохранить'}
              </button>
            </div>
            <button onClick={handleExport}>Скачать .vsdx</button>
            <button onClick={() => setShowConnTable(true)}>Таблица связей</button>

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
              <select value={eType} onChange={(e) => setEType(e.target.value)}>
                <option value="server">SRV — сервер</option>
                <option value="network">NET — сеть</option>
                <option value="firewall">FW — межсетевой экран</option>
                <option value="datacenter">DC — ЦОД</option>
                {customTypes.map((t) => (
                  <option key={t.id} value={t.name}>{t.name}</option>
                ))}
              </select>
              <input value={eName} onChange={(e) => setEName(e.target.value)} placeholder="Название" />
              {parentOptions.length > 0 && (
                <select value={eParent} onChange={(e) => setEParent(e.target.value)}>
                  <option value="">— родитель —</option>
                  {parentOptions.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.data.name} ({typeName(n.type ?? '')})
                    </option>
                  ))}
                </select>
              )}
              {primaryAttrFor(eType) && (
                <input
                  value={eAttr}
                  onChange={(e) => setEAttr(e.target.value)}
                  placeholder={primaryAttrFor(eType)!.placeholder}
                />
              )}
              <button className="primary" onClick={addEntity}>Добавить</button>
            </section>
          </>
        )}

        {tab === 'objects' && (
          <>
            <section>
              <label>Связь между объектами</label>
              <select value={cSource} onChange={(e) => setCSource(e.target.value)}>
                <option value="">— откуда —</option>
                {nodes.map((n) => (
                  <option key={n.id} value={n.id}>{n.data.name}</option>
                ))}
              </select>
              <select value={cTarget} onChange={(e) => setCTarget(e.target.value)}>
                <option value="">— куда —</option>
                {nodes.map((n) => (
                  <option key={n.id} value={n.id}>{n.data.name}</option>
                ))}
              </select>
              <select value={cParent} onChange={(e) => setCParent(e.target.value)}>
                <option value="">— через (авто) —</option>
                {nodes.map((n) => (
                  <option key={n.id} value={n.id}>{n.data.name}</option>
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
              <input value={cDescription} onChange={(e) => setCDescription(e.target.value)} placeholder="Описание" />
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

            <section>
              <label>Объекты</label>
              {nodes.length === 0 ? (
                <div className="muted">Объектов пока нет</div>
              ) : (
                <ul className="projects">
                  {nodes.map((n) => (
                    <li key={n.id}>
                      <button className="link" onClick={() => openEdit(n.id)}>
                        {n.data.name} <span className="conn-meta">{typeName(n.type ?? '')}</span>
                      </button>
                      <button className="del" onClick={() => deleteNode(n.id)}>✕</button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section>
              <label>Связи</label>
              {connections.length === 0 ? (
                <div className="muted">Связей пока нет</div>
              ) : (
                <ul className="connections">
                  {connections.map((c) => (
                    <li key={c.id}>
                      <button
                        className="swatch-mini"
                        style={{ background: connColor(c) }}
                        onClick={() => cycleConnectionColor(c.id)}
                        title="Сменить цвет"
                      />
                      <button className="link" onClick={() => showConnection(c)}>
                        {nodeName(c.source_id)} → {nodeName(c.target_id)}
                        <span className="conn-meta">
                          {c.protocol ?? 'any'}{c.port ? ':' + c.port : ''}
                          {c.description ? ' · ' + c.description : ''}
                        </span>
                      </button>
                      <button className="del" onClick={() => deleteConnection(c.id)}>✕</button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}

        {tab === 'library' && (
          <>
            <section>
              <label>Библиотека объектов</label>
              <button
                onClick={() => {
                  listObjects()
                    .then((r) => setLibrary(r.objects))
                    .catch((e) => setStatus((e as Error).message));
                }}
              >
                Обновить
              </button>
              {library.length === 0 ? (
                <div className="muted">Объектов пока нет — сохраните схему, и её объекты появятся здесь</div>
              ) : (
                <ul className="projects">
                  {library.map((o) => (
                    <li key={o.id}>
                      <button className="link" onClick={() => addLibraryObject(o)} title="Добавить на схему">
                        {o.name} <span className="conn-meta">{typeName(o.type)}</span>
                      </button>
                      <span className="catalog-meta muted">{o.group_name ?? 'публичный'}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}

        {tab === 'settings' && (
          <>
            <section>
              <label>Тема</label>
              <div className="row">
                <button className={theme === 'light' ? 'primary' : ''} onClick={() => setTheme('light')}>Светлая</button>
                <button className={theme === 'dark' ? 'primary' : ''} onClick={() => setTheme('dark')}>Тёмная</button>
              </div>
            </section>

            <section>
              <label>Раскладка</label>
              <button onClick={() => setNodes(autoLayout(nodes))}>Авто-раскладка</button>
            </section>

            <section>
              <label>Типы объектов</label>
              <div className="row">
                <input value={newTypeName} onChange={(e) => setNewTypeName(e.target.value)} placeholder="Новый тип" />
                <button className="primary" onClick={handleAddCustomType}>Добавить</button>
              </div>
              <ul className="projects">
                {customTypes.map((t) => (
                  <li key={t.id}>
                    <span className="link">{t.name}</span>
                    <button className="del" onClick={() => handleDeleteCustomType(t.id)}>✕</button>
                  </li>
                ))}
              </ul>
            </section>

            <section>
              <label>Сессия</label>
              <button onClick={handleLogout}>Выйти</button>
            </section>
          </>
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
          nodeTypes={rfNodeTypes}
          edgeTypes={edgeTypes}
          zIndexMode="manual"
          fitView
        >
          <Background color={theme === 'dark' ? '#2a3340' : '#e2e6ea'} />
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
            <label>Тип: {typeName(editingType)}</label>
            {editingParentType && (
              <>
                <label>Родитель</label>
                <select value={editParent} onChange={(e) => setEditParent(e.target.value)}>
                  <option value="">— нет —</option>
                  {nodes
                    .filter((n) => editingParentType.includes(n.type as NodeType) && n.id !== editingNodeId)
                    .map((n) => (
                      <option key={n.id} value={n.id}>
                        {n.data.name} ({typeName(n.type ?? '')})
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

      {showConnTable && (
        <div className="modal-backdrop" onClick={() => setShowConnTable(false)}>
          <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
            <h2>Таблица связей</h2>
            {connections.length === 0 ? (
              <div className="muted">Связей пока нет</div>
            ) : (
              <div className="conn-table-wrap">
                <table className="conn-table">
                  <thead>
                    <tr>
                      <th>Источник</th>
                      <th>Назначение</th>
                      <th>Протокол/порт</th>
                      <th>Описание</th>
                    </tr>
                  </thead>
                  <tbody>
                    {connections.map((c) => (
                      <tr key={c.id}>
                        <td>{nodeName(c.source_id)}</td>
                        <td>{nodeName(c.target_id)}</td>
                        <td>{(c.protocol ?? 'any') + (c.port ? ':' + c.port : '')}</td>
                        <td>{c.description ?? ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="row">
              <button onClick={() => setShowConnTable(false)}>Закрыть</button>
              <button className="primary" onClick={handleExportConnXlsx} disabled={connections.length === 0}>
                Выгрузить в Excel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
