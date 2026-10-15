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
}

const GAP = 14; // отступ = 7 толщин линии (толщина 2px)
const R = 6; // радиус «мостика» на пересечении

function orthoPath(source: Pt, waypoints: Pt[], target: Pt): Pt[] {
  const pts: Pt[] = [source, ...waypoints, target];
  const path: Pt[] = [{ x: pts[0].x, y: pts[0].y }];
  for (let i = 1; i < pts.length; i++) {
    const prev = path[path.length - 1];
    const cur = pts[i];
    if (cur.x !== prev.x) path.push({ x: cur.x, y: prev.y });
    if (cur.y !== prev.y) path.push({ x: cur.x, y: cur.y });
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

function signature(it: RouteItem): string {
  // Не сортируем — направление важно (A->B и B->A — разные сигнатуры).
  // fwIds не включаем, чтобы линии с одинаковыми source/target, но разными МСЭ,
  // всё равно разводились глобально (в начале/конце пути).
  return `${it.sourceId}>${it.targetId}`;
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

export function routeConnections(items: RouteItem[]): Array<{ id: string; d: string; labelPos: Pt }> {
  // Направление прохода (горизонтальное/вертикальное) для каждой линии.
  const passH = items.map((it) => Math.abs(it.target.x - it.source.x) >= Math.abs(it.target.y - it.source.y));

  // Лейны: линии, проходящие через один и тот же МСЭ, разводим, чтобы не ложились друг на друга.
  const fwGroups = new Map<string, number[]>();
  items.forEach((it, i) => {
    it.fwIds.forEach((fwId) => {
      if (!fwGroups.has(fwId)) fwGroups.set(fwId, []);
      fwGroups.get(fwId)!.push(i);
    });
  });
  const laneMap = new Map<string, number>();
  for (const [fwId, lines] of fwGroups) {
    const n = lines.length;
    lines.forEach((lineIdx, j) => {
      laneMap.set(`${lineIdx}:${fwId}`, (j - (n - 1) / 2) * GAP);
    });
  }

  const adjusted = items.map((it, i) => {
    const h = passH[i];
    return it.waypoints.map((wp, k) => {
      const fwId = it.fwIds[Math.floor(k / 2)];
      const lane = laneMap.get(`${i}:${fwId}`) ?? 0;
      if (h) return { x: wp.x, y: wp.y + lane };
      return { x: wp.x + lane, y: wp.y };
    });
  });

  const paths = items.map((it, i) => orthoPath(it.source, adjusted[i], it.target));

  // Смещение одинаковых маршрутов (одинаковая пара узлов).
  const offsets: number[] = new Array(items.length).fill(0);
  const groups = new Map<string, number[]>();
  items.forEach((it, i) => {
    const sig = signature(it);
    if (!groups.has(sig)) groups.set(sig, []);
    groups.get(sig)!.push(i);
  });
  for (const idxs of groups.values()) {
    const n = idxs.length;
    idxs.forEach((idx, j) => {
      offsets[idx] = (j - (n - 1) / 2) * GAP;
    });
  }

  const shifted = paths.map((p, i) => shiftPath(p, offsets[i]));

  // Сегменты всех линий — для поиска пересечений.
  const segs: Seg[] = [];
  shifted.forEach((path, edgeIndex) => {
    for (let segIndex = 0; segIndex < path.length - 1; segIndex++) {
      segs.push({ edgeIndex, segIndex, a: path[segIndex], b: path[segIndex + 1] });
    }
  });

  // «Мостики»: более новая линия «перепрыгивает» через более старую.
  const bridges: Bridge[][] = items.map(() => []);
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

  return shifted.map((path, i) => ({
    id: items[i].id,
    d: buildPath(path, bridges[i]),
    labelPos: midpointAlongPath(path),
  }));
}
