import type { Layout, Position } from './layout';
import { portAngle } from './layout';
import { SLOT_ORDER, sprite, type Slot } from './sprites';
import type { Snapshot, StatusState, Track, VNode } from './types';

export type Lod = 'macro' | 'meso' | 'micro';

export interface Camera {
  k: number;
  tx: number;
  ty: number;
}

export interface SceneState {
  tracks: Set<Track>;
  selected: string | null;
  hover: string | null;
  calm: boolean;
  showStatus: boolean;
}

const TRACK_COLORS: Record<Track, string> = {
  data: '#38bdf8',
  control: '#a78bfa',
  security: '#fb7185',
};

export function lodFor(k: number): Lod {
  if (k < 0.5) return 'macro';
  if (k < 2) return 'meso';
  return 'micro';
}

function visible(position: Position, camera: Camera, width: number, height: number): boolean {
  const r = position.r * camera.k + 4;
  const x = position.x * camera.k + camera.tx;
  const y = position.y * camera.k + camera.ty;
  return x + r >= 0 && x - r <= width && y + r >= 0 && y - r <= height;
}

export function drawScene(
  ctx: CanvasRenderingContext2D,
  snapshot: Snapshot,
  layout: Layout,
  camera: Camera,
  state: SceneState,
  width: number,
  height: number,
  pick?: (id: string) => string | null,
): void {
  const lod = lodFor(camera.k);
  const nodes = new Map(snapshot.nodes.map((node) => [node.id, node]));
  const shown = (node: VNode): boolean =>
    node.kind === 'membrane'
      ? true
      : node.kind === 'file'
        ? lod !== 'macro'
        : lod === 'micro';

  if (!pick) {
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#0b1120';
    ctx.fillRect(0, 0, width, height);
  }

  // Membranes first, so their children paint on top.
  for (const id of layout.order) {
    const node = nodes.get(id);
    const position = layout.positions.get(id);
    if (!node || node.kind !== 'membrane' || !position || !shown(node)) continue;
    if (!visible(position, camera, width, height)) continue;
    const x = position.x * camera.k + camera.tx;
    const y = position.y * camera.k + camera.ty;
    const r = position.r * camera.k;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = pick
      ? (pick(id) ?? '#000000')
      : `rgba(30, 41, 59, ${lod === 'macro' ? 0.92 : lod === 'meso' ? 0.42 : 0.08})`;
    ctx.fill();
    if (!pick) {
      ctx.strokeStyle = id === state.selected ? '#facc15' : id === state.hover ? '#e2e8f0' : '#475569';
      ctx.lineWidth = id === state.selected ? 3 : 1;
      ctx.stroke();
      if (r > 22) {
        ctx.fillStyle = '#cbd5e1';
        ctx.font = '12px ui-sans-serif, system-ui';
        ctx.textAlign = 'center';
        ctx.fillText(node.label, x, y - r - 6);
      }
    }
  }

  // Leaf nodes.
  for (const id of layout.order) {
    const node = nodes.get(id);
    const position = layout.positions.get(id);
    if (!node || node.kind === 'membrane' || !position || !shown(node)) continue;
    if (!visible(position, camera, width, height)) continue;
    const x = position.x * camera.k + camera.tx;
    const y = position.y * camera.k + camera.ty;
    const r = Math.max(2, position.r * camera.k);
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = pick ? (pick(id) ?? '#000000') : node.kind === 'file' ? '#334155' : '#64748b';
    ctx.fill();
    if (!pick && state.hover === id) {
      ctx.strokeStyle = '#e2e8f0';
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  }

  // Edges: macro edges at low zoom, leaf edges at higher zoom.
  for (const edge of snapshot.edges) {
    const macro = edge.kind === 'aggregate';
    if (lod === 'macro' && !macro) continue;
    if (lod !== 'macro' && macro && state.tracks.size === 0) continue;
    if (!edge.tracks.some((track) => state.tracks.has(track))) continue;
    const source = layout.positions.get(edge.source);
    const target = layout.positions.get(edge.target);
    if (!source || !target) continue;
    if (!visible(source, camera, width, height) && !visible(target, camera, width, height)) continue;
    const sx = source.x * camera.k + camera.tx;
    const sy = source.y * camera.k + camera.ty;
    const tx = target.x * camera.k + camera.tx;
    const ty = target.y * camera.k + camera.ty;
    const track = edge.tracks.find((item) => state.tracks.has(item)) ?? edge.tracks[0];
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(tx, ty);
    ctx.strokeStyle = TRACK_COLORS[track];
    ctx.globalAlpha = macro ? 0.8 : 0.35;
    ctx.lineWidth = Math.min(6, 1 + Math.log2(edge.weight + 1));
    if (!macro && track === 'control') ctx.setLineDash([4, 3]);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
    if (macro && !pick && camera.k > 0.25) {
      ctx.fillStyle = '#94a3b8';
      ctx.font = '10px ui-sans-serif, system-ui';
      ctx.textAlign = 'center';
      ctx.fillText(String(edge.weight), (sx + tx) / 2, (sy + ty) / 2 - 3);
    }
  }

  // Ports on membrane perimeters; skip the reserved status arc in portAngle.
  if (lod !== 'macro') {
    for (const port of snapshot.ports) {
      if (!port.tracks.some((track) => state.tracks.has(track))) continue;
      const membrane = nodes.get(port.membrane);
      const position = layout.positions.get(port.membrane);
      if (!membrane || membrane.kind !== 'membrane' || !position) continue;
      if (!visible(position, camera, width, height)) continue;
      const angle = portAngle(port, layout);
      const r = position.r * camera.k;
      const x = position.x * camera.k + camera.tx + Math.cos(angle) * r;
      const y = position.y * camera.k + camera.ty + Math.sin(angle) * r;
      ctx.fillStyle = TRACK_COLORS[port.tracks[0]] ?? '#94a3b8';
      ctx.fillRect(x - 3, y - 3, 6, 6);
    }
  }

  // Polarized status strip.
  if (state.showStatus) {
    for (const id of layout.order) {
      const node = nodes.get(id);
      const position = layout.positions.get(id);
      if (!node || node.kind !== 'membrane' || !position) continue;
      if (!visible(position, camera, width, height)) continue;
      const r = position.r * camera.k;
      if (r < 16) continue;
      const x = position.x * camera.k + camera.tx;
      const y = position.y * camera.k + camera.ty;
      const states: StatusState[] = SLOT_ORDER.map((slot) => node.status[slot as Slot]);
      for (let index = 0; index < SLOT_ORDER.length; index++) {
        const value = states[index];
        if (state.calm && (value === 'verified' || value === 'na')) continue;
        const degrees = 320 + index * 16;
        const angle = (degrees * Math.PI) / 180;
        const gx = x + Math.cos(angle) * (r + 9);
        const gy = y + Math.sin(angle) * (r + 9);
        const image = sprite(SLOT_ORDER[index], value);
        ctx.drawImage(image, gx - 10, gy - 10, 20, 20);
      }
    }
  }
}
