import { hierarchy, pack, type HierarchyCircularNode } from 'd3-hierarchy';
import type { Snapshot, VPort } from './types';

export interface Position {
  x: number;
  y: number;
  r: number;
}

export interface Layout {
  positions: Map<string, Position>;
  order: string[];
  parent: Map<string, string | null>;
}

interface Datum {
  id: string;
  children?: Datum[];
}

/** Deterministic circle packing, run once at load and then frozen in memory. */
export function computeLayout(snapshot: Snapshot, width = 1600, height = 1000): Layout {
  const byId = new Map(snapshot.nodes.map((node) => [node.id, node]));
  const children = new Map<string, string[]>();
  const parent = new Map<string, string | null>();
  for (const node of snapshot.nodes) {
    parent.set(node.id, node.parent);
    if (node.parent && byId.has(node.parent)) {
      const list = children.get(node.parent) ?? [];
      list.push(node.id);
      children.set(node.parent, list);
    }
  }
  const datum = (id: string): Datum => ({
    id,
    children: (children.get(id) ?? []).map(datum),
  });
  const root = hierarchy(datum('.'), (d) => d.children)
    .sum(() => 1)
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  pack<Datum>().size([width, height]).padding(2)(root);

  const positions = new Map<string, Position>();
  const order: string[] = [];
  for (const node of root.descendants() as HierarchyCircularNode<Datum>[]) {
    positions.set(node.data.id, { x: node.x, y: node.y, r: node.r });
    order.push(node.data.id);
  }
  return { positions, order, parent };
}

const RESERVED_START = 315;
const RESERVED_END = 45;

/** Port angle points at its peer, nudged out of the reserved status arc. */
export function portAngle(port: VPort, layout: Layout): number {
  const membrane = layout.positions.get(port.membrane);
  const peer = layout.positions.get(port.peer);
  if (!membrane || !peer) return 0;
  let degrees = (Math.atan2(peer.y - membrane.y, peer.x - membrane.x) * 180) / Math.PI;
  if (degrees < 0) degrees += 360;
  if (degrees >= RESERVED_START || degrees < RESERVED_END) {
    const toStart = Math.min(Math.abs(degrees - RESERVED_START), 360 - degrees + RESERVED_START);
    const toEnd = Math.abs(degrees - RESERVED_END);
    degrees = toStart < toEnd ? RESERVED_START + 1 : RESERVED_END - 1;
  }
  return (degrees * Math.PI) / 180;
}
