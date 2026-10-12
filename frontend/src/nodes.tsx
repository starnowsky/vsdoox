import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';

export interface DeviceData extends Record<string, unknown> {
  name: string;
  parent_id?: string | null;
  attributes?: Record<string, unknown>;
}

const ICONS: Record<string, string> = {
  server: '🖥️',
  firewall: '🛡️',
  network: '🌐',
  datacenter: '🏢',
};

function subtitleFor(
  type: string | undefined,
  attrs: Record<string, unknown> | undefined,
): string {
  if (!attrs) return '';
  switch (type) {
    case 'server':
      return typeof attrs.ip === 'string' ? attrs.ip : '';
    case 'network':
      return typeof attrs.cidr === 'string' ? attrs.cidr : '';
    case 'datacenter':
      return typeof attrs.location === 'string' ? attrs.location : '';
    default:
      return '';
  }
}

export function DeviceNode(props: NodeProps<Node<DeviceData>>) {
  const type = props.type ?? 'server';
  const name = props.data?.name ?? '';
  const subtitle = subtitleFor(type, props.data?.attributes);

  return (
    <div className={'device device-' + type}>
      <Handle type="target" position={Position.Left} />
      <div className="device-name">{ICONS[type] ?? ''} {name}</div>
      {subtitle ? <div className="device-subtitle">{subtitle}</div> : null}
      <div className="device-type">{type}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

export function DatacenterNode(props: NodeProps<Node<DeviceData>>) {
  const name = props.data?.name ?? '';
  return (
    <div className="datacenter">
      <div className="datacenter-header">🏢 ЦОД — {name}</div>
    </div>
  );
}
