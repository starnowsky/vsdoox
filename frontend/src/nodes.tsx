import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';

export interface DeviceData extends Record<string, unknown> {
  name: string;
  attributes?: Record<string, unknown>;
}

interface StyleDef {
  bg: string;
  border: string;
  icon: string;
  color: string;
}

const STYLES: Record<string, StyleDef> = {
  server: { bg: '#dbeafe', border: '#2563eb', icon: '🖥️', color: '#1e3a8a' },
  firewall: { bg: '#fee2e2', border: '#dc2626', icon: '🛡️', color: '#7f1d1d' },
  network: { bg: '#d1fae5', border: '#059669', icon: '🌐', color: '#064e3b' },
  datacenter: { bg: '#fef3c7', border: '#d97706', icon: '🏢', color: '#78350f' },
};

export function DeviceNode(props: NodeProps<Node<DeviceData>>) {
  const style = STYLES[props.type ?? 'server'] ?? STYLES.server;
  const name = props.data?.name ?? '';

  return (
    <div
      className="device"
      style={{
        background: style.bg,
        border: '2px solid ' + style.border,
        color: style.color,
        borderRadius: 8,
        padding: '8px 12px',
        minWidth: 120,
        textAlign: 'center',
        fontFamily: 'system-ui, sans-serif',
        fontSize: 13,
        boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
      }}
    >
      <Handle type="target" position={Position.Left} />
      <div style={{ fontWeight: 600 }}>{style.icon} {name}</div>
      <div style={{ fontSize: 11, opacity: 0.7, textTransform: 'uppercase', letterSpacing: 0.5 }}>
        {props.type}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
