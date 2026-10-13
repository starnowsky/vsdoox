export type NodeType = 'server' | 'firewall' | 'network' | 'datacenter';

export interface GraphNode {
  id: string;
  type: string;
  name: string;
  parent_id?: string | null;
  x: number;
  y: number;
  attributes: Record<string, unknown>;
}

export interface GraphLink {
  id: string;
  source_id: string;
  target_id: string;
  label?: string | null;
  attributes: Record<string, unknown>;
}

export interface Connection {
  id: string;
  source_id: string;
  target_id: string;
  protocol?: string | null;
  port?: string | null;
  attributes: Record<string, unknown>;
}

export interface Project {
  id: number;
  name: string;
  owner: string;
  created_at?: string;
  updated_at?: string;
  nodes: GraphNode[];
  links: GraphLink[];
  connections: Connection[];
}

export interface PathResult {
  found: boolean;
  path: string[];
  firewalls: string[];
  segments: string[];
}
