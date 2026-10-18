import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';

export interface DeviceData extends Record<string, unknown> {
  name: string;
  parent_id?: string | null;
  attributes?: Record<string, unknown>;
}

const ICONS: Record<string, string> = {
  server: '🖥️',
  firewall: '🧱',
  network: '🖧',
  datacenter: '🏢',
};

const TYPE_LABELS: Record<string, string> = {
  server: 'SERVER',
  firewall: 'FIREWALL',
  network: 'NETWORK',
  datacenter: 'DATACENTER',
};

function subtitleFor(
  type: string | undefined,
  attrs: Record<string, unknown> | undefined,
): string {
  if (!attrs) return '';
  if (type === 'network') return typeof attrs.cidr === 'string' ? attrs.cidr : '';
  if (type === 'datacenter') return typeof attrs.location === 'string' ? attrs.location : '';
  if (typeof attrs.ip === 'string') return attrs.ip;
  return '';
}

function NodeHandles({ rightOnly = false }: { rightOnly?: boolean }) {
  if (rightOnly) {
    return (
      <>
        <Handle id="s-right" type="source" position={Position.Right} />
        <Handle id="t-right" type="target" position={Position.Right} />
      </>
    );
  }
  return (
    <>
      <Handle id="s-top" type="source" position={Position.Top} />
      <Handle id="t-top" type="target" position={Position.Top} />
      <Handle id="s-right" type="source" position={Position.Right} />
      <Handle id="t-right" type="target" position={Position.Right} />
      <Handle id="s-bottom" type="source" position={Position.Bottom} />
      <Handle id="t-bottom" type="target" position={Position.Bottom} />
      <Handle id="s-left" type="source" position={Position.Left} />
      <Handle id="t-left" type="target" position={Position.Left} />
    </>
  );
}

export function DeviceNode(props: NodeProps<Node<DeviceData>>) {
  const type = props.type ?? 'server';
  const name = props.data?.name ?? '';
  const subtitle = subtitleFor(type, props.data?.attributes);
  const icon = ICONS[type] ?? '🔷';
  const typeLabel = TYPE_LABELS[type] ?? type.toUpperCase();

  return (
    <div className={'device device-' + type}>
      <NodeHandles />
      <div className="device-name">{icon} {name}</div>
      {subtitle ? <div className="device-subtitle">{subtitle}</div> : null}
      <div className="device-type">{typeLabel}</div>
    </div>
  );
}

export function DatacenterNode(props: NodeProps<Node<DeviceData>>) {
  const name = props.data?.name ?? '';
  return (
    <div className="datacenter">
      <NodeHandles />
      <div className="datacenter-header">🏢 {name}</div>
    </div>
  );
}

export function NetworkNode(props: NodeProps<Node<DeviceData>>) {
  const name = props.data?.name ?? '';
  const attrs = props.data?.attributes;
  const cidr = attrs && typeof attrs.cidr === 'string' ? attrs.cidr : '';
  const vlan = attrs && typeof attrs.vlan === 'string' ? attrs.vlan : '';
  return (
    <div className="network">
      <NodeHandles />
      <div className="network-header">🖧 {name}{cidr ? ' · ' + cidr : ''}{vlan ? ' · VLAN ' + vlan : ''}</div>
    </div>
  );
}
