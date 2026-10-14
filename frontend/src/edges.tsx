import { BaseEdge } from '@xyflow/react';
import type { EdgeProps } from '@xyflow/react';

interface Waypoint {
  x: number;
  y: number;
}

export function WaypointEdge(props: EdgeProps) {
  const { sourceX, sourceY, targetX, targetY, data } = props;
  const waypoints = (data?.waypoints as Waypoint[]) ?? [];
  const points = [
    { x: sourceX, y: sourceY },
    ...waypoints,
    { x: targetX, y: targetY },
  ];
  let d = `M ${points[0].x},${points[0].y}`;
  // Ортогональная маршрутизация: каждый сегмент — только горизонталь/вертикаль.
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const cur = points[i];
    d += ` L ${cur.x},${prev.y}`;
    d += ` L ${cur.x},${cur.y}`;
  }
  return <BaseEdge {...props} path={d} />;
}
