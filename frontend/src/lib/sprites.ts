import type { StatusState } from './types';

export const SLOT_ORDER = ['security', 'boundary', 'efficiency', 'hygiene', 'sentinel'] as const;
export type Slot = (typeof SLOT_ORDER)[number];

const COLORS: Record<StatusState, string> = {
  verified: '#2dd4a7',
  na: '#64748b',
  partial: '#f59e0b',
  violation: '#f43f5e',
};

const cache = new Map<string, HTMLCanvasElement>();

/** Pre-rasterize each (slot, state) sprite once; the render loop only stamps images. */
export function sprite(slot: Slot, state: StatusState): HTMLCanvasElement {
  const key = `${slot}:${state}`;
  const existing = cache.get(key);
  if (existing) return existing;

  const canvas = document.createElement('canvas');
  canvas.width = 24;
  canvas.height = 24;
  const ctx = canvas.getContext('2d');
  if (!ctx) return canvas;
  ctx.strokeStyle = COLORS[state];
  ctx.fillStyle = COLORS[state];
  ctx.lineWidth = 2;
  ctx.beginPath();
  if (slot === 'security') {
    ctx.moveTo(12, 3);
    ctx.lineTo(20, 6);
    ctx.lineTo(19, 14);
    ctx.lineTo(12, 21);
    ctx.lineTo(5, 14);
    ctx.lineTo(4, 6);
    ctx.closePath();
    ctx.stroke();
  } else if (slot === 'boundary') {
    ctx.rect(4, 6, 16, 12);
    ctx.stroke();
  } else if (slot === 'efficiency') {
    ctx.moveTo(14, 2);
    ctx.lineTo(7, 13);
    ctx.lineTo(12, 13);
    ctx.lineTo(10, 22);
    ctx.lineTo(17, 10);
    ctx.lineTo(12, 10);
    ctx.closePath();
    ctx.fill();
  } else if (slot === 'hygiene') {
    ctx.moveTo(4, 12);
    ctx.lineTo(10, 18);
    ctx.lineTo(20, 6);
    ctx.stroke();
  } else {
    ctx.arc(12, 12, 7, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(12, 12, 2, 0, Math.PI * 2);
    ctx.fill();
  }
  cache.set(key, canvas);
  return canvas;
}
