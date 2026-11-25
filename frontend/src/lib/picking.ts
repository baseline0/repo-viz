/** Offscreen flat-color buffer: O(1) hit testing regardless of glyph count. */
export class Picker {
  private canvas = document.createElement('canvas');
  private ctx: CanvasRenderingContext2D | null;
  private colors = new Map<string, string>();
  private owners = new Map<string, string>();

  constructor() {
    this.ctx = this.canvas.getContext('2d', { willReadFrequently: true });
  }

  resize(width: number, height: number, dpr: number): void {
    this.canvas.width = Math.max(1, Math.floor(width * dpr));
    this.canvas.height = Math.max(1, Math.floor(height * dpr));
    if (this.ctx) this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  get context(): CanvasRenderingContext2D | null {
    return this.ctx;
  }

  clear(): void {
    if (this.ctx) this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
  }

  colorFor(id: string): string {
    const existing = this.colors.get(id);
    if (existing) return existing;
    const index = this.colors.size + 1;
    const color = `rgb(${(index >> 16) & 255}, ${(index >> 8) & 255}, ${index & 255})`;
    this.colors.set(id, color);
    this.owners.set(color, id);
    return color;
  }

  hitTest(x: number, y: number, dpr: number): string | null {
    if (!this.ctx) return null;
    const pixel = this.ctx.getImageData(
      Math.floor(x * dpr),
      Math.floor(y * dpr),
      1,
      1,
    ).data;
    if (pixel[3] === 0) return null;
    return this.owners.get(`rgb(${pixel[0]}, ${pixel[1]}, ${pixel[2]})`) ?? null;
  }
}
