import type {
  GraphEdgeSnapshot,
  GraphNodeSnapshot,
  GraphSnapshot,
} from "../utils/graph.js";

export interface CanvasNode {
  id: string;
  label: string;
  kind: string;
  severity?: string;
  x: number;
  y: number;
}

export interface CanvasEdge {
  id: string;
  source: string;
  target: string;
  kind: string;
  weight?: number;
}

export interface CanvasBounds {
  width: number;
  height: number;
}

export interface CanvasStats {
  nodes: number;
  edges: number;
  critical: number;
  lastUpdated: number | null;
}

export interface CanvasGraph {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  bounds: CanvasBounds;
  stats: CanvasStats;
}

const START_X = 120;
const START_Y = 90;
const H_GAP = 300;
const V_GAP = 150;
const MIN_WIDTH = 900;
const MIN_HEIGHT = 600;

const LAYER_ORDER: string[][] = [
  ["entrypoint", "url", "host", "frontend", "client"],
  ["service", "repo", "file", "backend"],
  ["vulnerability", "candidate", "hypothesis", "cve"],
  ["credential", "secret", "user", "finding", "database", "cache"],
  ["chain", "crown_jewel", "patch", "queue", "storage", "external"],
];

function layerForKind(kind: string): number {
  const normalized = kind.toLowerCase();
  for (let i = 0; i < LAYER_ORDER.length; i += 1) {
    if (LAYER_ORDER[i]!.includes(normalized)) return i;
  }
  return LAYER_ORDER.length - 1;
}

function stableSortNodes(nodes: GraphNodeSnapshot[]): GraphNodeSnapshot[] {
  return [...nodes].sort((a, b) => {
    const timeDiff = a.observedAt - b.observedAt;
    if (timeDiff !== 0) return timeDiff;
    return a.id.localeCompare(b.id);
  });
}

function buildNodePositions(nodes: GraphNodeSnapshot[]): CanvasNode[] {
  const layers = new Map<number, GraphNodeSnapshot[]>();

  for (const node of stableSortNodes(nodes)) {
    const layer = layerForKind(node.kind);
    const inLayer = layers.get(layer) ?? [];
    inLayer.push(node);
    layers.set(layer, inLayer);
  }

  const output: CanvasNode[] = [];
  const orderedLayers = [...layers.entries()].sort((a, b) => a[0] - b[0]);

  for (const [layerIndex, layerNodes] of orderedLayers) {
    for (let row = 0; row < layerNodes.length; row += 1) {
      const node = layerNodes[row]!;
      output.push({
        id: node.id,
        label: node.label,
        kind: node.kind,
        severity: node.severity,
        x: START_X + layerIndex * H_GAP,
        y: START_Y + row * V_GAP,
      });
    }
  }

  return output;
}

function buildEdges(
  edges: GraphEdgeSnapshot[],
  nodeSet: Set<string>,
): CanvasEdge[] {
  return edges
    .filter((edge) => nodeSet.has(edge.src) && nodeSet.has(edge.dst))
    .map((edge) => ({
      id: edge.id,
      source: edge.src,
      target: edge.dst,
      kind: edge.kind,
      weight: edge.weight,
    }))
    .sort((a, b) => a.id.localeCompare(b.id));
}

function computeBounds(nodes: CanvasNode[]): CanvasBounds {
  if (nodes.length === 0) {
    return { width: MIN_WIDTH, height: MIN_HEIGHT };
  }

  const maxX = Math.max(...nodes.map((n) => n.x));
  const maxY = Math.max(...nodes.map((n) => n.y));

  return {
    width: Math.max(MIN_WIDTH, maxX + START_X + 160),
    height: Math.max(MIN_HEIGHT, maxY + START_Y + 120),
  };
}

function countCritical(nodes: GraphNodeSnapshot[]): number {
  return nodes.filter((node) => node.severity?.toLowerCase() === "critical").length;
}

/** Convert CLI graph snapshot into positioned canvas graph data. */
export function buildCanvasGraph(snapshot: GraphSnapshot): CanvasGraph {
  const rawNodes = Object.values(snapshot.nodes);
  const positionedNodes = buildNodePositions(rawNodes);
  const nodeSet = new Set(positionedNodes.map((node) => node.id));

  const rawEdges = Object.values(snapshot.edges);
  const positionedEdges = buildEdges(rawEdges, nodeSet);

  return {
    nodes: positionedNodes,
    edges: positionedEdges,
    bounds: computeBounds(positionedNodes),
    stats: {
      nodes: snapshot.stats.nodes ?? positionedNodes.length,
      edges: snapshot.stats.edges ?? positionedEdges.length,
      critical: countCritical(rawNodes),
      lastUpdated: snapshot.lastUpdated,
    },
  };
}
