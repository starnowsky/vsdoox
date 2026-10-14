import { BaseEdge } from '@xyflow/react';
import type { EdgeProps } from '@xyflow/react';

export function OrthoEdge(props: EdgeProps) {
  const { sourceX, sourceY, targetX, targetY, data } = props;
  const d = (data?.d as string) ?? '';
  const labelX = typeof data?.labelX === 'number' ? (data.labelX as number) : (sourceX + targetX) / 2;
  const labelY = typeof data?.labelY === 'number' ? (data.labelY as number) : (sourceY + targetY) / 2;
  return <BaseEdge {...props} path={d} labelX={labelX} labelY={labelY} />;
}

