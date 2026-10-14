import { BaseEdge, EdgeLabelRenderer } from '@xyflow/react';
import type { EdgeProps } from '@xyflow/react';

interface LabelStyle {
  fill?: string;
  fontSize?: number;
  fontWeight?: number;
}

interface LabelBgStyle {
  fill?: string;
}

export function OrthoEdge(props: EdgeProps) {
  const {
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    data,
    label,
    labelStyle,
    labelBgStyle,
    labelBgPadding,
    labelBgBorderRadius,
    markerEnd,
  } = props;

  const d = (data?.d as string) ?? '';
  const midX = (sourceX + targetX) / 2;
  const midY = (sourceY + targetY) / 2;

  const ls = labelStyle as LabelStyle | undefined;
  const bg = labelBgStyle as LabelBgStyle | undefined;
  const pad = labelBgPadding as [number, number] | undefined;

  return (
    <>
      <BaseEdge id={id} path={d} markerEnd={markerEnd} />
      {label ? (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan"
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${midX}px, ${midY}px)`,
              pointerEvents: 'all',
              background: bg?.fill ?? 'transparent',
              borderRadius: typeof labelBgBorderRadius === 'number' ? labelBgBorderRadius : 0,
              padding: pad ? `${pad[1]}px ${pad[0]}px` : undefined,
            }}
          >
            <span
              style={{
                display: 'block',
                color: ls?.fill ?? 'var(--text)',
                fontSize: ls?.fontSize ?? 11,
                fontWeight: ls?.fontWeight ?? 600,
                lineHeight: 1.2,
              }}
            >
              {label}
            </span>
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

