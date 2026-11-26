import type { IndicatorArtifact, IndicatorConfig, IndicatorResult, StatusState } from './types';

const COLORS: Record<StatusState, string> = {
  verified: '#2dd4a7',
  na: '#64748b',
  partial: '#f59e0b',
  violation: '#f43f5e',
};

const DEFS = [
  ['security', 'Security / trust', 'shield', 0],
  ['boundary', 'Boundary integrity', 'gate', 1],
  ['complexity', 'Efficiency / complexity', 'bolt', 2],
  ['hygiene', 'Typing hygiene', 'check', 3],
  ['sentinel', 'Antipattern sentinel', 'bug', 4],
  ['coverage', 'Test coverage', 'gauge', 5],
  ['churn', 'Recent churn', 'clock', 6],
  ['coupling', 'Structural coupling', 'dot', 7],
  ['hotspot', 'Change hotspot', 'gauge', 8],
  ['satd', 'Self-admitted debt', 'bug', 9],
  ['code_health', 'Code health proxy', 'shield', 10],
  ['arch_drift', 'Architectural drift', 'gate', 11],
  ['cognitive_friction', 'Cognitive complexity friction', 'bolt', 12],
  ['cochange', 'Change proneness / co-change', 'clock', 13],
] as const;

/** Fallback keeps the viewer usable when /config.json is unavailable. */
export const DEFAULT_CONFIG: IndicatorConfig = {
  version: 1,
  arc: { start_deg: 315, end_deg: 45, step_deg: 5, first_deg: 320 },
  indicators: DEFS.map(([id, label, glyph, position]) => ({
    id,
    label,
    glyph,
    position,
    colors: { ...COLORS },
    enabled: position < 5 || (position >= 7 && position <= 9),
    triggers: ['render', 'change'],
  })),
};

export function groupResults(artifact: IndicatorArtifact | null): Map<string, IndicatorResult[]> {
  const grouped = new Map<string, IndicatorResult[]>();
  for (const result of artifact?.results ?? []) {
    const list = grouped.get(result.node_id) ?? [];
    list.push(result);
    grouped.set(result.node_id, list);
  }
  return grouped;
}
