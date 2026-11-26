<script lang="ts">
  import { onMount } from 'svelte';
  import { DEFAULT_CONFIG, groupResults } from './lib/config';
  import { computeLayout, type Layout } from './lib/layout';
  import { Picker } from './lib/picking';
  import { drawScene, lodFor, type Camera, type Lod } from './lib/render';
  import type { IndicatorArtifact, IndicatorConfig, IndicatorResult, Snapshot, Track, VNode } from './lib/types';
  import './app.css';

  let canvas: HTMLCanvasElement;
  let stage: HTMLDivElement;
  let snapshot: Snapshot | null = null;
  let layout: Layout | null = null;
  let config: IndicatorConfig | null = null;
  let resultByNode = new Map<string, IndicatorResult[]>();
  let camera: Camera = { k: 1, tx: 0, ty: 0 };
  let tracks = new Set<Track>(['data', 'control', 'security']);
  let selectedId: string | null = null;
  let auditReport: Record<string, unknown> | null = null;
  let hoverId: string | null = null;
  let calm = false;
  let showStatus = true;
  let query = '';
  let error = '';
  let width = 1000;
  let height = 700;
  let dpr = 1;
  let dragging = false;
  let moved = false;
  let lastX = 0;
  let lastY = 0;
  const picker = new Picker();
  const TRACKS: Track[] = ['data', 'control', 'security'];

  $: selected = snapshot?.nodes.find((node) => node.id === selectedId) ?? null;
  $: lod = lodFor(camera.k) as Lod;
  $: findings = (auditReport?.findings ?? []) as {
    indicator_id: string;
    state: string;
    severity: string;
    action: string;
  }[];
  $: workItemId = (auditReport?.work_item as { id: string } | undefined)?.id ?? '';

  function render(): void {
    if (!snapshot || !layout || !canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const state = { tracks, selected: selectedId, hover: hoverId, calm, showStatus, config, results: resultByNode };
    drawScene(ctx, snapshot, layout, camera, state, width, height);
    picker.clear();
    const pickCtx = picker.context;
    if (pickCtx) drawScene(pickCtx, snapshot, layout, camera, state, width, height, (id) => picker.colorFor(id));
  }

  function fit(): void {
    if (!layout) return;
    const values = [...layout.positions.values()];
    if (!values.length) return;
    const minX = Math.min(...values.map((value) => value.x - value.r));
    const maxX = Math.max(...values.map((value) => value.x + value.r));
    const minY = Math.min(...values.map((value) => value.y - value.r));
    const maxY = Math.max(...values.map((value) => value.y + value.r));
    const k = Math.min(width / (maxX - minX + 40), height / (maxY - minY + 40));
    camera = {
      k,
      tx: width / 2 - ((minX + maxX) / 2) * k,
      ty: height / 2 - ((minY + maxY) / 2) * k,
    };
    render();
  }

  function setZoom(target: number): void {
    const ratio = target / camera.k;
    camera = {
      k: target,
      tx: width / 2 - (width / 2 - camera.tx) * ratio,
      ty: height / 2 - (height / 2 - camera.ty) * ratio,
    };
    render();
  }

  function toggleTrack(track: Track): void {
    const next = new Set(tracks);
    if (next.has(track)) next.delete(track);
    else next.add(track);
    tracks = next;
    render();
  }

  async function postAction(path: string): Promise<void> {
    if (!selectedId) return;
    const response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node: selectedId }),
    });
    auditReport = await response.json();
  }

  function choose(node: VNode): void {
    selectedId = node.id;
    auditReport = null;
    const position = layout?.positions.get(node.id);
    if (position) {
      camera = {
        ...camera,
        tx: width / 2 - position.x * camera.k,
        ty: height / 2 - position.y * camera.k,
      };
    }
    render();
  }

  function search(): void {
    if (!snapshot || !query.trim()) return;
    const needle = query.trim().toLowerCase();
    const match = snapshot.nodes.find(
      (node) => node.label.toLowerCase().includes(needle) || node.id.toLowerCase().includes(needle),
    );
    if (match) choose(match);
  }

  function pointerPosition(event: PointerEvent | WheelEvent): [number, number] {
    const rect = canvas.getBoundingClientRect();
    return [event.clientX - rect.left, event.clientY - rect.top];
  }

  function onWheel(event: WheelEvent): void {
    event.preventDefault();
    const [x, y] = pointerPosition(event);
    const worldX = (x - camera.tx) / camera.k;
    const worldY = (y - camera.ty) / camera.k;
    const k = Math.min(12, Math.max(0.05, camera.k * Math.exp(-event.deltaY * 0.0015)));
    camera = { k, tx: x - worldX * k, ty: y - worldY * k };
    render();
  }

  function onPointerDown(event: PointerEvent): void {
    dragging = true;
    moved = false;
    lastX = event.clientX;
    lastY = event.clientY;
    canvas.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: PointerEvent): void {
    if (dragging) {
      const dx = event.clientX - lastX;
      const dy = event.clientY - lastY;
      if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
      camera = { ...camera, tx: camera.tx + dx, ty: camera.ty + dy };
      lastX = event.clientX;
      lastY = event.clientY;
      render();
      return;
    }
    const [x, y] = pointerPosition(event);
    const id = picker.hitTest(x, y, dpr);
    if (id !== hoverId) {
      hoverId = id;
      render();
    }
  }

  function onPointerUp(event: PointerEvent): void {
    dragging = false;
    if (!moved) {
      const [x, y] = pointerPosition(event);
      selectedId = picker.hitTest(x, y, dpr);
      render();
    }
  }

  onMount(async () => {
    dpr = window.devicePixelRatio || 1;
    const source = new URLSearchParams(window.location.search).get('graph') ?? '/graph.json';
    try {
      const [response, configResponse, resultsResponse] = await Promise.all([
        fetch(source),
        fetch('/config.json'),
        fetch('/indicators.json'),
      ]);
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      snapshot = (await response.json()) as Snapshot;
      config = configResponse.ok ? ((await configResponse.json()) as IndicatorConfig) : DEFAULT_CONFIG;
      const artifact = resultsResponse.ok ? ((await resultsResponse.json()) as IndicatorArtifact) : null;
      resultByNode = groupResults(artifact);
      layout = computeLayout(snapshot);
      observer = new ResizeObserver(() => resize());
      observer.observe(stage);
      resize();
    } catch (cause) {
      error = `Could not load ${source}: ${String(cause)}`;
    }
  });

  let observer: ResizeObserver | undefined;

  function resize(): void {
    if (!stage || !canvas) return;
    width = Math.max(320, stage.clientWidth);
    height = Math.max(240, stage.clientHeight);
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    picker.resize(width, height, dpr);
    render();
  }
</script>

<main>
  <header>
    <strong>repo-viz</strong>
    <span class="muted">{snapshot?.source_repo ?? 'no snapshot'} · {snapshot?.source_commit.slice(0, 8) ?? '—'}</span>
    <span class="badge">{lod}</span>
    <div class="spacer"></div>
    <input bind:value={query} placeholder="find component" on:keydown={(event) => event.key === 'Enter' && search()} />
    <button on:click={search}>Find</button>
    <button on:click={fit}>Fit</button>
  </header>

  <div class="body">
    <aside class="toolbar">
      <p class="label">Level of detail</p>
      <button class:active={lod === 'macro'} on:click={() => setZoom(0.3)}>Macro</button>
      <button class:active={lod === 'meso'} on:click={() => setZoom(1)}>Meso</button>
      <button class:active={lod === 'micro'} on:click={() => setZoom(3)}>Micro</button>
      <p class="label">Tracks</p>
      {#each TRACKS as track}
        <label><input type="checkbox" checked={tracks.has(track)} on:change={() => toggleTrack(track)} /> {track}</label>
      {/each}
      <p class="label">Display</p>
      <label><input type="checkbox" bind:checked={showStatus} on:change={render} /> status strip</label>
      <label><input type="checkbox" bind:checked={calm} on:change={render} /> calm membrane</label>
      {#if error}<p class="error">{error}</p>{/if}
    </aside>

    <div class="stage" bind:this={stage}>
      <canvas
        bind:this={canvas}
        on:wheel={onWheel}
        on:pointerdown={onPointerDown}
        on:pointermove={onPointerMove}
        on:pointerup={onPointerUp}
      ></canvas>
      {#if hoverId && hoverId !== selectedId}<div class="tooltip">{hoverId}</div>{/if}
    </div>

    <aside class="panel">
      {#if selected}
        <p class="label">Selected</p>
        <h2>{selected.label}</h2>
        <p class="muted mono">{selected.id}</p>
        <dl>
          <dt>kind</dt><dd>{selected.kind}</dd>
          <dt>complexity</dt><dd>{selected.metrics.complexity}</dd>
          <dt>fan in / out</dt><dd>{selected.metrics.fan_in} / {selected.metrics.fan_out}</dd>
          <dt>churn 30d</dt><dd>{selected.metrics.churn_30d}</dd>
          <dt>coverage</dt><dd>{selected.metrics.coverage === null ? 'audit required' : selected.metrics.coverage}</dd>
        </dl>
        <p class="label">Indicators</p>
        <ul>
          {#each config?.indicators ?? [] as def}
            {@const result = (resultByNode.get(selected.id) ?? []).find((item) => item.indicator_id === def.id)}
            <li>
              {def.label}: <b>{result?.state ?? 'na'}</b>
              {#if result?.evidence}<span class="muted">{String(result.value ?? '')} · {result.evidence}</span>{/if}
            </li>
          {/each}
        </ul>
        {#if selected.tags.length}<p class="muted">tags: {selected.tags.join(', ')}</p>{/if}
        <button on:click={() => postAction('/api/audit')}>Audit component</button>
        <button on:click={() => postAction('/api/work-item')}>Prepare work-item request</button>
        {#if auditReport}
          <p class="label">Audit</p>
          <ul>
            {#each findings as finding}
              <li><b>{finding.severity}</b> {finding.indicator_id}: {finding.action}</li>
            {/each}
          </ul>
          {#if workItemId}
            <p class="muted mono">request: {workItemId}</p>
          {/if}
        {/if}
      {:else}
        <p class="muted">Click a membrane, port or cell to inspect it.</p>
      {/if}
    </aside>
  </div>
</main>
