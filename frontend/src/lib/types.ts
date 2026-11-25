export type NodeKind = 'membrane' | 'file' | 'symbol';
export type Track = 'data' | 'control' | 'security';
export type StatusState = 'verified' | 'na' | 'partial' | 'violation';

export interface Metrics {
  complexity: number;
  loc: number;
  fan_in: number;
  fan_out: number;
  churn_30d: number;
  coverage: number | null;
}

export interface StatusStrip {
  security: StatusState;
  boundary: StatusState;
  efficiency: StatusState;
  hygiene: StatusState;
  sentinel: StatusState;
  arc_start_deg: number;
  arc_end_deg: number;
}

export interface VNode {
  id: string;
  label: string;
  kind: NodeKind;
  parent: string | null;
  lod_rank: number;
  path: string | null;
  tags: string[];
  metrics: Metrics;
  status: StatusStrip;
}

export interface VEdge {
  source: string;
  target: string;
  kind: string;
  tracks: Track[];
  weight: number;
  line: number;
}

export interface VPort {
  membrane: string;
  peer: string;
  direction: 'in' | 'out';
  kind: string;
  tracks: Track[];
  count: number;
  weight: number;
}

export interface Snapshot {
  schema: string;
  source_repo: string;
  source_commit: string;
  analyzed_at: string;
  nodes: VNode[];
  edges: VEdge[];
  ports: VPort[];
}
