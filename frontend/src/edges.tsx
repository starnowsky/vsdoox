import { BaseEdge } from '@xyflow/react';
import type { EdgeProps } from '@xyflow/react';

interface Waypoint {
  x: number;
  y: number;
}

export function WaypointEdge(props: EdgeProps) {
  const { sourceX, sourceY, targetX, targetY, data } = props;
  const waypoints = (data?.waypoints as Waypoint[]) ?? [];
  let d = `M ${sourceX},${sourceY}`;
  for (const w of waypoints) {
    d += ` L ${w.x},${w.y}`;
  }
  d += ` L ${targetX},${targetY}`;
  return <BaseEdge {...props} path={d} />;
}
