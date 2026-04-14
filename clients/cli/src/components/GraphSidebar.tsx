import React from "react";
import { Box, Text } from "ink";
import { useSpinnerFrame } from "../hooks/useSpinnerFrame.js";
import type { GraphSidebarMode } from "../state/AppState.js";
import { formatDuration, formatNumber } from "../utils/format.js";
import { AGENT_LABELS, AGENT_MODES } from "../utils/agents.js";
import type { GraphSnapshot } from "../utils/graph.js";
import { AGENT_COLORS, GLYPH_DOT, GLYPH_SEP } from "../utils/theme.js";

interface GraphSidebarProps {
  snapshot: GraphSnapshot;
  activeAgent: string | null;
  mode: GraphSidebarMode;
  canvasUrl: string | null;
  canvasStatus: "starting" | "running" | "error";
  canvasError: string | null;
}

const SIDEBAR_WIDTH = 40;
const MAX_LIST_ITEMS = 7;

function toTitleCase(input: string): string {
  return input
    .replaceAll("_", " ")
    .split(" ")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function truncate(input: string, max: number): string {
  if (input.length <= max) return input;
  if (max <= 1) return "…";
  return `${input.slice(0, max - 1)}…`;
}

function countsFromStats(stats: Record<string, number>, prefix: "node." | "edge."): [string, number][] {
  return Object.entries(stats)
    .filter(([k, v]) => k.startsWith(prefix) && Number.isFinite(v) && v > 0)
    .map(([k, v]): [string, number] => [k.slice(prefix.length), v])
    .sort((a, b) => b[1] - a[1]);
}

function countsFromObserved(
  values: string[],
): [string, number][] {
  const counts = new Map<string, number>();
  for (const value of values) {
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]);
}

function renderCountRows(
  items: [string, number][],
  emptyLabel: string,
): React.ReactNode {
  if (items.length === 0) {
    return <Text dimColor>{`  ${emptyLabel}`}</Text>;
  }

  return items.slice(0, 4).map(([name, count]) => (
    <Text key={name} dimColor>
      {`  ${GLYPH_DOT} ${toTitleCase(name)}: `}
      <Text color="white">{formatNumber(count)}</Text>
    </Text>
  ));
}

export const GraphSidebar = React.memo(function GraphSidebar({
  snapshot,
  activeAgent,
  mode,
  canvasUrl,
  canvasStatus,
  canvasError,
}: GraphSidebarProps) {
  const { tick } = useSpinnerFrame(activeAgent != null);
  const blinkBright = tick % 12 < 8;

  const totalNodes = snapshot.stats.nodes ?? Object.keys(snapshot.nodes).length;
  const totalEdges = snapshot.stats.edges ?? Object.keys(snapshot.edges).length;

  const nodeKindCounts = React.useMemo(() => {
    const fromStats = countsFromStats(snapshot.stats, "node.");
    if (fromStats.length > 0) return fromStats;
    return countsFromObserved(Object.values(snapshot.nodes).map((node) => node.kind));
  }, [snapshot]);

  const edgeKindCounts = React.useMemo(() => {
    const fromStats = countsFromStats(snapshot.stats, "edge.");
    if (fromStats.length > 0) return fromStats;
    return countsFromObserved(Object.values(snapshot.edges).map((edge) => edge.kind));
  }, [snapshot]);

  const latestNodes = React.useMemo(
    () =>
      Object.values(snapshot.nodes)
        .sort((a, b) => b.observedAt - a.observedAt)
        .slice(0, MAX_LIST_ITEMS),
    [snapshot.nodes],
  );

  const latestEdges = React.useMemo(
    () =>
      Object.values(snapshot.edges)
        .sort((a, b) => b.observedAt - a.observedAt)
        .slice(0, MAX_LIST_ITEMS),
    [snapshot.edges],
  );

  const criticalCount = React.useMemo(() => {
    const fromNodes = Object.values(snapshot.nodes).filter(
      (node) => node.severity?.toLowerCase() === "critical",
    ).length;

    if (fromNodes > 0) return fromNodes;

    const vulnerabilityCount = snapshot.stats["node.vulnerability"] ?? 0;
    if (vulnerabilityCount === 0) return 0;

    const high = snapshot.stats["node.high"] ?? 0;
    const critical = snapshot.stats["node.critical"] ?? 0;
    return Math.max(critical, high);
  }, [snapshot]);

  const updatedAgo =
    snapshot.lastUpdated != null
      ? formatDuration(Math.max(Date.now() - snapshot.lastUpdated, 0))
      : null;

  const showEmptyState = totalNodes === 0 && totalEdges === 0;

  return (
    <Box width={SIDEBAR_WIDTH} flexDirection="column" marginLeft={1}>
      <Box
        borderStyle="round"
        borderColor="gray"
        paddingX={1}
        paddingY={0}
        flexDirection="column"
      >
        <Text bold color="cyan">
          {`GRAPH ${mode.toUpperCase()}`}
        </Text>

        <Text dimColor>
          {`ctrl+g cycle${GLYPH_SEP}ctrl+b hide`}
        </Text>

        <Box marginTop={1} flexDirection="column">
          <Text color="gray">Web Canvas</Text>
          {canvasStatus === "running" ? (
            <Text dimColor>{`  ${truncate(canvasUrl ?? "", SIDEBAR_WIDTH - 4)}`}</Text>
          ) : canvasStatus === "error" ? (
            <Text color="red" dimColor>{`  ${truncate(canvasError ?? "failed to start", SIDEBAR_WIDTH - 4)}`}</Text>
          ) : (
            <Text dimColor>{"  starting..."}</Text>
          )}
          <Text dimColor>{"  Open in browser for interactive SVG view"}</Text>
        </Box>

        <Box marginTop={1} flexDirection="column">
          <Text color="gray">Execution Modes</Text>
          {AGENT_MODES.map((agent) => {
            const isActive = activeAgent === agent;
            const label = AGENT_LABELS[agent];
            const color = AGENT_COLORS[agent] ?? "white";
            return (
              <Text key={agent}>
                {"  "}
                {isActive ? (
                  <Text color={color} bold={blinkBright} dimColor={!blinkBright}>
                    {`${GLYPH_DOT} ${label}`}
                  </Text>
                ) : (
                  <Text dimColor>{`${GLYPH_DOT} ${label}`}</Text>
                )}
              </Text>
            );
          })}
        </Box>

        <Box marginTop={1} flexDirection="column">
          <Text color="gray">Knowledge Graph</Text>
          <Text>
            {"  "}
            <Text color="cyan">{formatNumber(totalNodes)}</Text>
            <Text dimColor>{" nodes"}</Text>
            <Text dimColor>{GLYPH_SEP}</Text>
            <Text color="magenta">{formatNumber(totalEdges)}</Text>
            <Text dimColor>{" edges"}</Text>
          </Text>
          <Text dimColor>
            {"  "}
            {criticalCount > 0 ? (
              <>
                <Text color="red">{formatNumber(criticalCount)}</Text>
                <Text>{" critical signals"}</Text>
              </>
            ) : (
              "No critical findings yet"
            )}
          </Text>
          <Text dimColor>{`  Updated: ${updatedAgo ?? "n/a"}`}</Text>
        </Box>

        <Box marginTop={1} flexDirection="column">
          {mode === "overview" && (
            <>
              <Text color="gray">Node Types</Text>
              {renderCountRows(nodeKindCounts, "No nodes yet")}
              <Box marginTop={1}>
                <Text color="gray">Edge Types</Text>
              </Box>
              {renderCountRows(edgeKindCounts, "No edges yet")}
            </>
          )}

          {mode === "nodes" && (
            <>
              <Text color="gray">Latest Nodes</Text>
              {latestNodes.length === 0 && <Text dimColor>{"  No observed nodes"}</Text>}
              {latestNodes.map((node) => (
                <Text key={node.id} dimColor>
                  {"  "}
                  <Text color="green">{`[${truncate(node.kind, 12)}] `}</Text>
                  {truncate(node.label, SIDEBAR_WIDTH - 10)}
                </Text>
              ))}
            </>
          )}

          {mode === "flows" && (
            <>
              <Text color="gray">Latest Flows</Text>
              {latestEdges.length === 0 && <Text dimColor>{"  No observed edges"}</Text>}
              {latestEdges.map((edge) => {
                const srcLabel = snapshot.nodes[edge.src]?.label ?? edge.src;
                const dstLabel = snapshot.nodes[edge.dst]?.label ?? edge.dst;
                const flow = `${srcLabel} -> ${dstLabel}`;
                return (
                  <Text key={edge.id} dimColor>
                    {"  "}
                    <Text color="yellow">{`(${truncate(edge.kind, 10)}) `}</Text>
                    {truncate(flow, SIDEBAR_WIDTH - 12)}
                  </Text>
                );
              })}
            </>
          )}
        </Box>

        {showEmptyState && (
          <Box marginTop={1}>
            <Text dimColor>{"Run kg_stats / kg_query to populate graph."}</Text>
          </Box>
        )}
      </Box>
    </Box>
  );
});
