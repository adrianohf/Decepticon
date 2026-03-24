import React, { useRef } from "react";
import { Box, Text } from "ink";
import { useSpinnerFrame } from "../hooks/useSpinnerFrame.js";
import type { StreamStats } from "../hooks/useAgent.js";

interface ActivityIndicatorProps {
  isStreaming: boolean;
  streamStats: StreamStats | null;
}

function formatElapsed(ms: number): string {
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const rem = secs % 60;
  return `${mins}m ${rem}s`;
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

// Shimmer gradient palette — Decepticon red theme
const SHIMMER_COLORS = [
  "#b91c1c", // red-700
  "#dc2626", // red-600
  "#ef4444", // red-500
  "#f87171", // red-400
  "#fca5a5", // red-300
  "#fecaca", // red-200
  "#fca5a5", // red-300
  "#f87171", // red-400
  "#ef4444", // red-500
  "#dc2626", // red-600
];

/** Render text with a shifting gradient shimmer effect. */
function ShimmerText({ text, tick }: { text: string; tick: number }) {
  const chars = text.split("");
  // Slow down: shift every 2 ticks
  const offset = Math.floor(tick / 2);
  return (
    <Text>
      {chars.map((ch, i) => {
        const colorIdx =
          (i + offset) % SHIMMER_COLORS.length;
        return (
          <Text key={i} color={SHIMMER_COLORS[colorIdx]}>
            {ch}
          </Text>
        );
      })}
    </Text>
  );
}

// Pulse palette for the ● icon — smooth bright↔dim cycle synced with shimmer
const PULSE_COLORS = [
  "#fecaca", // bright peak
  "#fca5a5",
  "#f87171",
  "#ef4444",
  "#dc2626",
  "#b91c1c", // dim trough
  "#dc2626",
  "#ef4444",
  "#f87171",
  "#fca5a5",
];

/** Activity indicator with pulsing dot, red shimmer, and animated token counter. */
export const ActivityIndicator = React.memo(function ActivityIndicator({
  isStreaming,
  streamStats,
}: ActivityIndicatorProps) {
  const { tick } = useSpinnerFrame(isStreaming);
  const displayTokensRef = useRef(0);

  if (!isStreaming) {
    displayTokensRef.current = 0;
    return null;
  }

  // Animate token count: ease toward actual value each tick (driven by 80ms re-renders)
  const targetTokens = streamStats?.totalTokens ?? 0;
  if (displayTokensRef.current < targetTokens) {
    const gap = targetTokens - displayTokensRef.current;
    const step = Math.max(1, Math.ceil(gap * 0.15));
    displayTokensRef.current = Math.min(targetTokens, displayTokensRef.current + step);
  }

  const elapsed = streamStats
    ? formatElapsed(Date.now() - streamStats.startTime)
    : "";
  const tokenCount =
    displayTokensRef.current > 0
      ? `\u2191 ${formatTokens(displayTokensRef.current)} tokens`
      : "";

  const meta = [elapsed, tokenCount].filter(Boolean).join(" \u00B7 ");
  const metaStr = meta ? ` (${meta})` : "";

  // Slow pulse: cycle through palette every 3 ticks (240ms per step)
  const pulseIdx = Math.floor(tick / 3) % PULSE_COLORS.length;

  return (
    <Box marginTop={1}>
      <Text>
        <Text color={PULSE_COLORS[pulseIdx]}>{"\u25CF"}</Text>
        <Text>{" "}</Text>
        <ShimmerText text="Hacking..." tick={tick} />
        <Text dimColor>{metaStr}</Text>
      </Text>
    </Box>
  );
});
