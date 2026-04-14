import type { AgentEvent } from "../types.js";

export interface GraphNodeSnapshot {
  id: string;
  kind: string;
  label: string;
  severity?: string;
  observedAt: number;
}

export interface GraphEdgeSnapshot {
  id: string;
  src: string;
  dst: string;
  kind: string;
  weight?: number;
  observedAt: number;
}

export interface GraphSnapshot {
  nodes: Record<string, GraphNodeSnapshot>;
  edges: Record<string, GraphEdgeSnapshot>;
  stats: Record<string, number>;
  lastUpdated: number | null;
}

export function emptyGraphSnapshot(): GraphSnapshot {
  return {
    nodes: {},
    edges: {},
    stats: {},
    lastUpdated: null,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function stripCodeFence(input: string): string {
  const match = input.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  return match?.[1]?.trim() ?? input;
}

/**
 * Extract the first balanced JSON object/array from a free-form string.
 * Handles nested braces and quoted strings.
 */
function extractFirstJsonBlock(input: string): string | null {
  let start = -1;
  const stack: string[] = [];
  let inString = false;
  let escaped = false;

  for (let i = 0; i < input.length; i += 1) {
    const ch = input[i]!;

    if (inString) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (ch === '"') {
        inString = false;
      }
      continue;
    }

    if (ch === '"') {
      inString = true;
      continue;
    }

    if (ch === "{" || ch === "[") {
      if (stack.length === 0) start = i;
      stack.push(ch);
      continue;
    }

    if (ch === "}" || ch === "]") {
      if (stack.length === 0) continue;
      const open = stack.pop();
      if (
        (open === "{" && ch !== "}") ||
        (open === "[" && ch !== "]")
      ) {
        return null;
      }
      if (stack.length === 0 && start >= 0) {
        return input.slice(start, i + 1);
      }
    }
  }

  return null;
}

function parseJsonLoose(content: string): unknown | null {
  const trimmed = content.trim();
  if (!trimmed) return null;

  const candidates = [
    trimmed,
    stripCodeFence(trimmed),
    extractFirstJsonBlock(trimmed),
  ];

  for (const candidate of candidates) {
    if (!candidate) continue;
    try {
      return JSON.parse(candidate);
    } catch {
      // try next candidate
    }
  }

  return null;
}

function extractStats(parsed: unknown): Record<string, number> | null {
  if (!isRecord(parsed)) return null;

  const statsCandidate = isRecord(parsed.stats) ? parsed.stats : parsed;
  const keys = Object.keys(statsCandidate);
  const looksLikeStats = keys.some(
    (key) =>
      key === "nodes" ||
      key === "edges" ||
      key.startsWith("node.") ||
      key.startsWith("edge."),
  );
  if (!looksLikeStats) return null;

  const stats: Record<string, number> = {};
  for (const [key, value] of Object.entries(statsCandidate)) {
    if (typeof value === "number" && Number.isFinite(value)) {
      stats[key] = value;
    }
  }
  return Object.keys(stats).length > 0 ? stats : null;
}

function ensureNode(
  state: GraphSnapshot,
  node: {
    id: string;
    kind?: string;
    label?: string;
    severity?: string;
  },
  observedAt: number,
): void {
  const existing = state.nodes[node.id];
  state.nodes[node.id] = {
    id: node.id,
    kind: node.kind ?? existing?.kind ?? "unknown",
    label: node.label ?? existing?.label ?? node.id,
    severity: node.severity ?? existing?.severity,
    observedAt: Math.max(observedAt, existing?.observedAt ?? 0),
  };
}

function ensureEdge(
  state: GraphSnapshot,
  edge: {
    id?: string;
    src: string;
    dst: string;
    kind?: string;
    weight?: number;
  },
  observedAt: number,
): void {
  const kind = edge.kind ?? "link";
  const id = edge.id ?? `${edge.src}->${kind}->${edge.dst}`;
  const existing = state.edges[id];

  state.edges[id] = {
    id,
    src: edge.src,
    dst: edge.dst,
    kind,
    weight: edge.weight ?? existing?.weight,
    observedAt: Math.max(observedAt, existing?.observedAt ?? 0),
  };
}

function ingestNodeRecord(
  state: GraphSnapshot,
  record: Record<string, unknown>,
  observedAt: number,
): boolean {
  const id = asString(record.id);
  if (!id) return false;

  const data = isRecord(record.data) ? record.data : null;
  const props = isRecord(record.props) ? record.props : null;

  const kind =
    asString(record.kind) ??
    (data ? asString(data.nodeType) : null) ??
    undefined;

  const label =
    asString(record.label) ??
    (data ? asString(data.label) ?? asString(data.name) : null) ??
    undefined;

  const severity =
    (props && typeof props.severity === "string" ? props.severity : null) ??
    (data && typeof data.severity === "string" ? data.severity : null) ??
    undefined;

  ensureNode(state, { id, kind, label, severity }, observedAt);
  return true;
}

function ingestEdgeRecord(
  state: GraphSnapshot,
  record: Record<string, unknown>,
  observedAt: number,
): boolean {
  const src = asString(record.src) ?? asString(record.source);
  const dst = asString(record.dst) ?? asString(record.target);
  if (!src || !dst) return false;

  const kind =
    asString(record.kind) ??
    (isRecord(record.data) ? asString(record.data.protocol) : null) ??
    undefined;

  ensureNode(state, { id: src }, observedAt);
  ensureNode(state, { id: dst }, observedAt);
  ensureEdge(state, {
    id: asString(record.id) ?? undefined,
    src,
    dst,
    kind,
    weight: asNumber(record.weight),
  }, observedAt);
  return true;
}

function ingestGraphObject(
  state: GraphSnapshot,
  parsed: Record<string, unknown>,
  observedAt: number,
): boolean {
  const graphCandidate = isRecord(parsed.graph) ? parsed.graph : parsed;
  let changed = false;

  if (Array.isArray(graphCandidate.nodes)) {
    for (const item of graphCandidate.nodes) {
      if (isRecord(item)) {
        changed = ingestNodeRecord(state, item, observedAt) || changed;
      }
    }
  }

  if (Array.isArray(graphCandidate.edges)) {
    for (const item of graphCandidate.edges) {
      if (isRecord(item)) {
        changed = ingestEdgeRecord(state, item, observedAt) || changed;
      }
    }
  }

  return changed;
}

function ingestKgQuery(
  state: GraphSnapshot,
  parsed: Record<string, unknown>,
  observedAt: number,
): boolean {
  if (!Array.isArray(parsed.nodes)) return false;

  let changed = false;
  for (const item of parsed.nodes) {
    if (isRecord(item)) {
      changed = ingestNodeRecord(state, item, observedAt) || changed;
    }
  }
  return changed;
}

function ingestKgNeighbors(
  state: GraphSnapshot,
  parsed: unknown,
  event: AgentEvent,
): boolean {
  if (!Array.isArray(parsed)) return false;

  const centerId = asString(event.toolArgs?.node_id);
  if (!centerId) return false;

  const direction = asString(event.toolArgs?.direction) ?? "out";
  ensureNode(state, { id: centerId }, event.timestamp);

  let changed = false;

  for (const item of parsed) {
    if (!isRecord(item)) continue;

    const neighborId = asString(item.neighbor_id);
    if (!neighborId) continue;

    ensureNode(state, {
      id: neighborId,
      kind: asString(item.neighbor_kind) ?? undefined,
      label: asString(item.neighbor_label) ?? undefined,
    }, event.timestamp);

    const isInbound = direction === "in";
    const src = isInbound ? neighborId : centerId;
    const dst = isInbound ? centerId : neighborId;

    ensureEdge(state, {
      src,
      dst,
      kind: asString(item.edge_kind) ?? undefined,
      weight: asNumber(item.edge_weight),
    }, event.timestamp);

    changed = true;
  }

  return changed;
}

function ingestKgAddEdge(
  state: GraphSnapshot,
  parsed: Record<string, unknown>,
  event: AgentEvent,
): boolean {
  const src = asString(event.toolArgs?.src);
  const dst = asString(event.toolArgs?.dst);
  if (!src || !dst) return false;

  ensureNode(state, { id: src }, event.timestamp);
  ensureNode(state, { id: dst }, event.timestamp);

  ensureEdge(state, {
    id: asString(parsed.id) ?? undefined,
    src,
    dst,
    kind: asString(parsed.kind) ?? asString(event.toolArgs?.kind) ?? undefined,
    weight: asNumber(event.toolArgs?.weight),
  }, event.timestamp);

  return true;
}

/**
 * Build a best-effort graph snapshot from streamed tool results.
 *
 * Supports Decepticon's knowledge-graph tools (`kg_*`) and Composer-style
 * graph payloads (`{ graph: { nodes, edges } }`).
 */
export function deriveGraphSnapshot(events: AgentEvent[]): GraphSnapshot {
  const state = emptyGraphSnapshot();

  for (const event of events) {
    if (event.type !== "tool_result" || event.status === "error") continue;

    const parsed = parseJsonLoose(event.content);
    if (parsed == null) continue;

    let changed = false;

    const stats = extractStats(parsed);
    if (stats) {
      state.stats = stats;
      changed = true;
    }

    if (isRecord(parsed)) {
      switch (event.toolName) {
        case "kg_add_node":
          changed = ingestNodeRecord(state, parsed, event.timestamp) || changed;
          break;
        case "kg_add_edge":
          changed = ingestKgAddEdge(state, parsed, event) || changed;
          break;
        case "kg_query":
          changed = ingestKgQuery(state, parsed, event.timestamp) || changed;
          break;
        default:
          changed = ingestGraphObject(state, parsed, event.timestamp) || changed;
          break;
      }
    }

    if (event.toolName === "kg_neighbors") {
      changed = ingestKgNeighbors(state, parsed, event) || changed;
    }

    if (changed) {
      state.lastUpdated = Math.max(state.lastUpdated ?? 0, event.timestamp);
    }
  }

  if (typeof state.stats.nodes !== "number") {
    state.stats.nodes = Object.keys(state.nodes).length;
  }
  if (typeof state.stats.edges !== "number") {
    state.stats.edges = Object.keys(state.edges).length;
  }

  return state;
}
