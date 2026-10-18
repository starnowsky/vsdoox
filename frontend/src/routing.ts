// Ортогональная маршрутизация рёбер связей:
// - параллельные линии со смещением (не накладываются друг на друга);
// - «мостики» (дуги) в местах пересечения линий.

export interface Pt {
  x: number;
  y: number;
}

export interface RouteItem {
  id: string;
  sourceId: string;
  targetId: string;
  fwIds: string[];
  source: Pt;
  waypoints: Pt[];
  target: Pt;
  sourceSide: string;
  targetSide: string;
  horizontalPass: boolean;
}

export const HANDLE_GAP = 12; // gap between connection points on same node side
export const NODE_EDGE_INSET = 8; // отступ линии внутрь узла от границы, чтобы не ложиться на скруглённые углы

// Константы расстояния для адаптивной толщины линий (в пикселях)
export const MIN_CONN_DIST = 30;
export const MID_CONN_DIST = 120;
export const MAX_CONN_DIST = 300;

// Константа толщины линии (в пикселях) - используется для зазора между параллельными линиями и радиуса мостиков
export const LINE_WIDTH = 2;

// Find nearest point on rectangle boundary to a target point.
// Returns the point on the closest side (top/right/bottom/left) — the clamped
// projection of the target onto that side — so lines terminate at the nearest
// boundary port instead of the node centre or a corner.
export function nearestBoundaryPoint(
  node: { position: { x: number; y: number }; width?: number; height?: number },
  target: { x: number; y: number },
): { x: number; y: number; side: 'top' | 'right' | 'bottom' | 'left' } {
  const nx = node.position.x;
  const ny = node.position.y;
  const h = node.height ?? 60;
  const w = node.width ?? 150;
  const cx = nx + w / 2;

  const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

  const dx = target.x - cx;

  // Соединяемся только с боковыми сторонами (левой/правой), независимо от
  // вертикального смещения цели. Верх/низ больше не используются.
  // Точка подключения сдвинута внутрь на NODE_EDGE_INSET, чтобы линия не «висела»
  // на скруглённом углу фигуры, а начиналась чуть ближе к центру узла.
  if (dx > 0) {
    return {
      x: nx + w - NODE_EDGE_INSET,
      y: clamp(target.y, ny + NODE_EDGE_INSET, ny + h - NODE_EDGE_INSET),
      side: 'right',
    };
  }
  return {
    x: nx + NODE_EDGE_INSET,
    y: clamp(target.y, ny + NODE_EDGE_INSET, ny + h - NODE_EDGE_INSET),
    side: 'left',
  };
}

// Вычисляет толщину линии соединения на основе расстояния между объектами.
// Возвращает толщину в пикселях.
export function getLineWidthForConnection(source: Pt, target: Pt): number {
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const distance = Math.sqrt(dx * dx + dy * dy);

  if (distance <= MIN_CONN_DIST) {
    return 1; // Толщина 1px при близком расположении узлов
  } else if (distance >= MAX_CONN_DIST) {
    return 2; // Толщина 2px при удалении
  } else {
    // Интерполяция между 1 и 2px в зависимости от расстояния
    const normalizedDist = (distance - MIN_CONN_DIST) / (MAX_CONN_DIST - MIN_CONN_DIST);
    return 1 + normalizedDist; // Возвращает значение между 1 и 2
  }
}

// Get connection point with tangential distribution along node side
function getDistributedPoint(
  node: { position: { x: number; y: number }; width?: number; height?: number },
  side: 'top' | 'right' | 'bottom' | 'left',
  count: number,
  index: number,
): { x: number; y: number } {
  const nx = node.position.x;
  const ny = node.position.y;
  const w = node.width ?? 150;
  const h = node.height ?? 60;

  // Fixed coordinate on the chosen side (x for left/right, y for top/bottom),
  // pulled inside NODE_EDGE_INSET so lines leave the flat edge, not the corner.
  let fixedX = nx + w / 2;
  let fixedY = ny + h / 2;
  let lo: number;
  let hi: number;
  if (side === 'left') {
    fixedX = nx + NODE_EDGE_INSET;
    lo = ny + NODE_EDGE_INSET;
    hi = ny + h - NODE_EDGE_INSET;
    fixedY = (lo + hi) / 2;
  } else if (side === 'right') {
    fixedX = nx + w - NODE_EDGE_INSET;
    lo = ny + NODE_EDGE_INSET;
    hi = ny + h - NODE_EDGE_INSET;
    fixedY = (lo + hi) / 2;
  } else if (side === 'top') {
    fixedY = ny + NODE_EDGE_INSET;
    lo = nx + NODE_EDGE_INSET;
    hi = nx + w - NODE_EDGE_INSET;
    fixedX = (lo + hi) / 2;
  } else {
    // bottom
    fixedY = ny + h - NODE_EDGE_INSET;
    lo = nx + NODE_EDGE_INSET;
    hi = nx + w - NODE_EDGE_INSET;
    fixedX = (lo + hi) / 2;
  }
  if (hi < lo) hi = lo;

  if (count <= 1) return { x: fixedX, y: fixedY };

  // Распределение по всей высоте стороны с центром в середине.
  // Первая линия в центре, каждая следующая смещается на HANDLE_GAP;
  // если места не хватает, шаг сжимается, чтобы линии заняли всю
  // вертикальную поверхность [lo, hi] и не наслаивались друг на друга.
  const center = (lo + hi) / 2;
  const natural = Math.max(0, count - 1) * HANDLE_GAP;
  const available = hi - lo;
  const gap = natural > available && count > 1 ? available / (count - 1) : HANDLE_GAP;
  const offset = (index - Math.max(0, count - 1) / 2) * gap;
  const v = Math.max(lo, Math.min(hi, center + offset));

  if (side === 'left' || side === 'right') {
    return { x: fixedX, y: v };
  }
  return { x: v, y: fixedY };
}

const GAP = LINE_WIDTH * 5; // отступ = 5 толщин линии (адаптивный)
const R = LINE_WIDTH * 2; // радиус «мостика» на пересечении

function orthoPath(source: Pt, waypoints: Pt[], target: Pt, lane = 0): Pt[] {
  // Линия выходит из источника и заканчивается «по горизонтали» — входим в цель
  // перпендикулярно боковой стороне (последний сегмент горизонтальный), выходя
  // из источника тоже горизонтально. Между соседними точками — Z-образный переход
  // через середину по X, без вертикального «скольжения» вдоль границе узла.
  // `lane` смещает вертикальный изгиб по горизонтали, чтобы изгибы параллельных
  // линий между одной парой узлов не накладывались друг на друга. Конечные точки
  // остаются приклеенными к граням исходного и целевого узлов.
  const pts: Pt[] = [source, ...waypoints, target];
  const path: Pt[] = [{ x: pts[0].x, y: pts[0].y }];
  for (let i = 1; i < pts.length; i++) {
    const a = path[path.length - 1];
    const b = pts[i];
    if (a.x === b.x) {
      // Точки на одной вертикали — чистый вертикальный сегмент.
      if (a.y !== b.y) path.push({ x: b.x, y: b.y });
    } else {
      const midX = (a.x + b.x) / 2 + lane;
      path.push({ x: midX, y: a.y });
      if (a.y !== b.y) path.push({ x: midX, y: b.y });
      path.push({ x: b.x, y: b.y });
    }
  }
  return path;
}

function shiftPath(path: Pt[], d: number): Pt[] {
  if (!d) return path;
  const a = path[0];
  const b = path[path.length - 1];
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const px = -dy / len;
  const py = dx / len;
  return path.map((p) => ({ x: p.x + px * d, y: p.y + py * d }));
}

function bendCorridorKey(it: RouteItem): string {
  // Коридор вертикального изгиба — середина по X между точками подключения.
  // Линии с одинаковым коридором разводятся по горизонтали, чтобы их
  // вертикальные изгибы не накладывались, независимо от пары объектов.
  // Округление до 0.5px — защита от шума плавающей точки.
  const midX = (it.source.x + it.target.x) / 2;
  return String(Math.round(midX * 2));
}

interface Seg {
  edgeIndex: number;
  segIndex: number;
  a: Pt;
  b: Pt;
}

function crossing(s1: Seg, s2: Seg): Pt | null {
  const h1 = s1.a.y === s1.b.y;
  const h2 = s2.a.y === s2.b.y;
  if (h1 === h2) return null; // обе горизонтальные или обе вертикальные — не пересекаются
  const h = h1 ? s1 : s2;
  const v = h1 ? s2 : s1;
  const x = v.a.x;
  const y = h.a.y;
  const hx1 = Math.min(h.a.x, h.b.x);
  const hx2 = Math.max(h.a.x, h.b.x);
  const vy1 = Math.min(v.a.y, v.b.y);
  const vy2 = Math.max(v.a.y, v.b.y);
  if (x > hx1 && x < hx2 && y > vy1 && y < vy2) return { x, y };
  return null;
}

const round = (v: number): number => Math.round(v * 10) / 10;

interface Bridge {
  segIndex: number;
  x: number;
  y: number;
}

function buildPath(path: Pt[], bridges: Bridge[]): string {
  let d = `M ${round(path[0].x)},${round(path[0].y)}`;
  for (let i = 1; i < path.length; i++) {
    const a = path[i - 1];
    const b = path[i];
    const horizontal = a.y === b.y;
    const dir = horizontal ? (a.x <= b.x ? 1 : -1) : (a.y <= b.y ? 1 : -1);
    const segBridges = bridges
      .filter((br) => br.segIndex === i - 1)
      .sort((p, q) => dir * (horizontal ? p.x - q.x : p.y - q.y));
    if (segBridges.length === 0) {
      d += ` L ${round(b.x)},${round(b.y)}`;
      continue;
    }
    let cur = a;
    for (const br of segBridges) {
      const sweep = dir === 1 ? 1 : 0;
      if (horizontal) {
        const t = br.x;
        d += ` L ${round(t - dir * R)},${round(cur.y)}`;
        d += ` A ${R} ${R} 0 0 ${sweep} ${round(t + dir * R)},${round(cur.y)}`;
        cur = { x: t + dir * R, y: cur.y };
      } else {
        const t = br.y;
        d += ` L ${round(cur.x)},${round(t - dir * R)}`;
        d += ` A ${R} ${R} 0 0 ${sweep} ${round(cur.x)},${round(t + dir * R)}`;
        cur = { x: cur.x, y: t + dir * R };
      }
    }
    d += ` L ${round(b.x)},${round(b.y)}`;
  }
  return d;
}

function midpointAlongPath(path: Pt[]): Pt {
  let total = 0;
  const lens: number[] = [];
  for (let i = 0; i < path.length - 1; i++) {
    const l = Math.hypot(path[i + 1].x - path[i].x, path[i + 1].y - path[i].y);
    lens.push(l);
    total += l;
  }
  const half = total / 2;
  let acc = 0;
  for (let i = 0; i < path.length - 1; i++) {
    if (acc + lens[i] >= half) {
      const t = lens[i] === 0 ? 0 : (half - acc) / lens[i];
      return {
        x: path[i].x + (path[i + 1].x - path[i].x) * t,
        y: path[i].y + (path[i + 1].y - path[i].y) * t,
      };
    }
    acc += lens[i];
  }
  return path[path.length - 1];
}

export function routeConnections(
  items: RouteItem[],
  nodes: Map<string, { position: { x: number; y: number }; width?: number; height?: number }>
): Array<{ id: string; d: string; labelPos: Pt }> {
  // --- 1. Determine the boundary side for every endpoint (nearest point) ---
  // This must happen before grouping, because distribution is per (node, side):
  // lines leaving the same node on different sides must not share an index.
  type Side = 'top' | 'right' | 'bottom' | 'left';
  const endpointSides: { sourceSide: Side; targetSide: Side }[] = items.map((it) => {
    const sourceNode = nodes.get(it.sourceId);
    const targetNode = nodes.get(it.targetId);
    const sourceSide = sourceNode
      ? nearestBoundaryPoint(sourceNode, it.target).side
      : (it.sourceSide as Side);
    const targetSide = targetNode
      ? nearestBoundaryPoint(targetNode, it.source).side
      : (it.targetSide as Side);
    return { sourceSide, targetSide };
  });

  // --- 2. Group by (node, side), merging source and target ends together.
  // This makes a line A→B and the reverse line B→A share the same side-group
  // on each node, so their connection points spread vertically instead of
  // collapsing onto the centre point of the side.
  interface EndpointRef {
    itemIndex: number;
    end: 'source' | 'target';
    sortKey: number; // y of the opposite end — spatial order for deterministic lanes
  }

  const sideGroups = new Map<string, EndpointRef[]>();
  items.forEach((it, i) => {
    const sKey = `${it.sourceId}:${endpointSides[i].sourceSide}`;
    const tKey = `${it.targetId}:${endpointSides[i].targetSide}`;
    if (!sideGroups.has(sKey)) sideGroups.set(sKey, []);
    if (!sideGroups.has(tKey)) sideGroups.set(tKey, []);
    sideGroups.get(sKey)!.push({ itemIndex: i, end: 'source', sortKey: it.target.y });
    sideGroups.get(tKey)!.push({ itemIndex: i, end: 'target', sortKey: it.source.y });
  });

  // Deterministic ordering: spatial (by opposite end) + tie-break by item index.
  const distIndex = new Map<string, { count: number; index: number }>();
  for (const refs of sideGroups.values()) {
    refs.sort((a, b) => a.sortKey - b.sortKey || a.itemIndex - b.itemIndex);
    refs.forEach((ref, j) => {
      distIndex.set(`${ref.itemIndex}:${ref.end}`, { count: refs.length, index: j });
    });
  }

  // Apply tangential distribution to source/target points
  const distributedItems = items.map((it, i) => {
    const sourceNode = nodes.get(it.sourceId);
    const targetNode = nodes.get(it.targetId);
    const { sourceSide, targetSide } = endpointSides[i];

    let newSource = it.source;
    let newTarget = it.target;
    let newSourceSide = it.sourceSide as Side;
    let newTargetSide = it.targetSide as Side;

    if (sourceNode) {
      const info = distIndex.get(`${i}:source`);
      if (info) {
        const distributed = getDistributedPoint(sourceNode, sourceSide, info.count, info.index);
        newSource = { x: distributed.x, y: distributed.y };
        newSourceSide = sourceSide;
      }
    }

    if (targetNode) {
      const info = distIndex.get(`${i}:target`);
      if (info) {
        const distributed = getDistributedPoint(targetNode, targetSide, info.count, info.index);
        newTarget = { x: distributed.x, y: distributed.y };
        newTargetSide = targetSide;
      }
    }

    return { ...it, source: newSource, target: newTarget, sourceSide: newSourceSide, targetSide: newTargetSide };
  });

  // Направление прохода берётся из RouteItem (рассчитано в App.tsx из центров узлов),
  // чтобы не расходиться с осью, по которой уже построены waypoints.
  const passH = distributedItems.map((it) => it.horizontalPass);

  // Лейны: линии, проходящие через один и тот же МСЭ, разводим, чтобы не ложились друг на друга.
  const fwGroups = new Map<string, number[]>();
  distributedItems.forEach((it, i) => {
    it.fwIds.forEach((fwId) => {
      if (!fwGroups.has(fwId)) fwGroups.set(fwId, []);
      fwGroups.get(fwId)!.push(i);
    });
  });
  const laneMap = new Map<string, number>();
  // Перпендикулярная координата «коридора» линии — ось, по которой
  // разводятся лейны у МСЭ. Горизонтальный проход → середина по Y,
  // вертикальный проход → середина по X.
  const corridorKey = (it: RouteItem): number =>
    it.horizontalPass ? (it.source.y + it.target.y) / 2 : (it.source.x + it.target.x) / 2;

  for (const [fwId, lines] of fwGroups) {
    // Линии по одному маршруту (через один и тот же МСЭ) должны получать
    // лейны в пространственном порядке, а не в порядке вставки в массив
    // connections — иначе при «обратном» порядке добавления связей линии
    // сходятся и пересекаются. Тай-брейк по индексу делает порядок детерминированным.
    const sorted = [...lines].sort(
      (a, b) =>
        corridorKey(distributedItems[a]) - corridorKey(distributedItems[b]) || a - b
    );
    const n = sorted.length;
    sorted.forEach((lineIdx, j) => {
      laneMap.set(`${lineIdx}:${fwId}`, (j - (n - 1) / 2) * GAP);
    });
  }

  const adjusted = distributedItems.map((it, i) => {
    const h = passH[i];
    return it.waypoints.map((wp, k) => {
      const fwId = it.fwIds[Math.floor(k / 2)];
      const lane = laneMap.get(`${i}:${fwId}`) ?? 0;
      if (h) return { x: wp.x, y: wp.y + lane };
      return { x: wp.x + lane, y: wp.y };
    });
  });

  // Вертикальные изгибы линий, у которых изгиб попадает в один коридор (одна и
  // та же середина по X между источником и целью), разводятся по горизонтали,
  // чтобы не накладываться друг на друга — вне зависимости от пары объектов.
  const bendLane = new Array(distributedItems.length).fill(0);
  const bendGroups = new Map<string, number[]>();
  distributedItems.forEach((it, i) => {
    const key = bendCorridorKey(it);
    if (!bendGroups.has(key)) bendGroups.set(key, []);
    bendGroups.get(key)!.push(i);
  });
  for (const lines of bendGroups.values()) {
    const n = lines.length;
    lines.forEach((idx, j) => {
      bendLane[idx] = (j - (n - 1) / 2) * GAP;
    });
  }

  const paths = distributedItems.map((it, i) =>
    orthoPath(it.source, adjusted[i], it.target, bendLane[i])
  );

  // Сегменты всех линий — для поиска пересечений.
  const segs: Seg[] = [];
  paths.forEach((path, edgeIndex) => {
    for (let segIndex = 0; segIndex < path.length - 1; segIndex++) {
      segs.push({ edgeIndex, segIndex, a: path[segIndex], b: path[segIndex + 1] });
    }
  });

  // «Мостики»: более новая линия «перепрыгивает» через более старую.
  const bridges: Bridge[][] = distributedItems.map(() => []);
  for (let i = 0; i < segs.length; i++) {
    for (let j = i + 1; j < segs.length; j++) {
      const s1 = segs[i];
      const s2 = segs[j];
      if (s1.edgeIndex === s2.edgeIndex) continue;
      const p = crossing(s1, s2);
      if (!p) continue;
      const newer = s1.edgeIndex > s2.edgeIndex ? s1 : s2;
      bridges[newer.edgeIndex].push({ segIndex: newer.segIndex, x: p.x, y: p.y });
    }
  }

  return paths.map((path, i) => ({
    id: distributedItems[i].id,
    d: buildPath(path, bridges[i]),
    labelPos: midpointAlongPath(path),
  }));
}

// Force inclusion in bundle (prevents tree-shaking of routing functions)
export const ROUTING_SYMBOLS = {
  routeConnections,
  nearestBoundaryPoint,
  HANDLE_GAP,
  getDistributedPoint,
  orthoPath,
  shiftPath,
  crossing,
  buildPath,
  midpointAlongPath,
  bendCorridorKey,
  getLineWidthForConnection,
  LINE_WIDTH,
  MIN_CONN_DIST,
  MAX_CONN_DIST,
} as const;

// Build marker: verifies this module is included in the frontend bundle.
export const ROUTING_BUILD_MARKER = 'routing_build_marker_20261018_v2';

