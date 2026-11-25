const cache = new Map<string, HTMLCanvasElement>();

/** Pre-rasterize each (glyph, color) sprite once; the render loop only stamps images. */
export function sprite(glyph: string, color: string): HTMLCanvasElement {
  const key = `${glyph}:${color}`;
  const existing = cache.get(key);
  if (existing) return existing;

  const canvas = document.createElement('canvas');
  canvas.width = 24;
  canvas.height = 24;
  const ctx = canvas.getContext('2d');
  if (!ctx) return canvas;
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  if (glyph === 'shield') {
    ctx.moveTo(12, 3);
    ctx.lineTo(20, 6);
    ctx.lineTo(19, 14);
    ctx.lineTo(12, 21);
    ctx.lineTo(5, 14);
    ctx.lineTo(4, 6);
    ctx.closePath();
    ctx.stroke();
  } else if (glyph === 'gate') {
    ctx.rect(4, 6, 16, 12);
    ctx.stroke();
  } else if (glyph === 'bolt') {
    ctx.moveTo(14, 2);
    ctx.lineTo(7, 13);
    ctx.lineTo(12, 13);
    ctx.lineTo(10, 22);
    ctx.lineTo(17, 10);
    ctx.lineTo(12, 10);
    ctx.closePath();
    ctx.fill();
  } else if (glyph === 'check') {
    ctx.moveTo(4, 12);
    ctx.lineTo(10, 18);
    ctx.lineTo(20, 6);
    ctx.stroke();
  } else if (glyph === 'gauge') {
    ctx.arc(12, 13, 8, Math.PI, 0);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(12, 13);
    ctx.lineTo(17, 8);
    ctx.stroke();
  } else if (glyph === 'clock') {
    ctx.arc(12, 12, 8, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(12, 7);
    ctx.lineTo(12, 12);
    ctx.lineTo(16, 14);
    ctx.stroke();
  } else if (glyph === 'bug') {
    ctx.arc(12, 12, 7, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(12, 12, 2, 0, Math.PI * 2);
    ctx.fill();
  } else {
    ctx.arc(12, 12, 6, 0, Math.PI * 2);
    ctx.fill();
  }
  cache.set(key, canvas);
  return canvas;
}
