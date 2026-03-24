import React from "react";
import { Box, Text } from "ink";
import type { AgentEvent } from "../types.js";
import { BashResult } from "./BashResult.js";
import { TodoList, parseTodos } from "./TodoList.js";
import { renderMarkdown } from "../utils/markdown.js";

interface EventItemProps {
  event: AgentEvent;
}

const MAX_RESULT_LINES = 20;

// ── Friendly tool display names ───────────────────────────────────
const TOOL_DISPLAY: Record<string, string> = {
  read_file: "Read",
  write_file: "Write",
  edit_file: "Edit",
  ls: "List",
  glob: "Glob",
  grep: "Grep",
  execute: "Execute",
  write_todos: "Todos",
};

/** Strip /workspace/ prefix for concise display. */
function shortPath(path: string): string {
  if (path.startsWith("/workspace/")) return path.slice("/workspace/".length);
  if (path === "/workspace") return "/";
  return path;
}

/** Extract skill name from a /skills/... path. Returns null if not a skill path. */
function extractSkillName(args: Record<string, unknown>): string | null {
  const filePath = args.file_path as string | undefined;
  if (!filePath || !filePath.includes("/skills/")) return null;
  const parts = filePath.split("/");
  const skillsIdx = parts.indexOf("skills");
  const skillDir = parts[parts.length - 2];
  if (skillDir && skillDir !== "skills" && skillsIdx >= 0) return skillDir;
  return parts[skillsIdx + 1] ?? null;
}

/** Truncate and format result lines for display. */
function truncateLines(content: string): string[] {
  const lines = content.split("\n");
  if (lines.length <= MAX_RESULT_LINES) return lines;
  return [
    ...lines.slice(0, MAX_RESULT_LINES),
    `... (${lines.length - MAX_RESULT_LINES} more lines)`,
  ];
}

// ── Tool call header renderers ────────────────────────────────────

/** Render Claude Code-style tool call header.
 *
 * Examples:
 *   ● Read (engagements/test/opplan.json)
 *   ● Read (opplan.json) lines 501-1000
 *   ● Write (findings.txt)
 *   ● Edit (config.yaml)
 *   ● List (engagements/test/)
 *   ● Glob (*.json) in engagements/test
 *   ● Grep (password) in engagements/ [*.json]
 *   ● Execute (whoami)
 */
function ToolCallHeader({
  toolName,
  args,
  status,
}: {
  toolName: string;
  args: Record<string, unknown>;
  status?: "success" | "error";
}) {
  const label = TOOL_DISPLAY[toolName];
  const dotColor = status === "error" ? "red" : "green";

  if (!label) {
    // Fallback: raw format for unknown tools
    const argsStr = Object.entries(args)
      .filter(([, v]) => v != null && v !== "")
      .map(([k, v]) => {
        const val = typeof v === "string" ? `"${v}"` : String(v);
        return `${k}=${val}`;
      })
      .join(", ");
    return (
      <Text>
        <Text color={dotColor}>{"● "}</Text>
        <Text color="white" bold>{toolName}</Text>
        <Text color="gray" italic>{` (${argsStr})`}</Text>
      </Text>
    );
  }

  // Build per-tool detail suffix
  let detail = "";
  let detailDim = "";

  switch (toolName) {
    case "read_file": {
      const filePath = shortPath((args.file_path as string) ?? "");
      detail = filePath;
      const offset = Number(args.offset ?? 0);
      const limit = Number(args.limit ?? 100);
      if (offset > 0 || limit !== 100) {
        detailDim = ` lines ${offset + 1}-${offset + limit}`;
      }
      break;
    }
    case "write_file":
    case "edit_file":
      detail = shortPath((args.file_path as string) ?? "");
      break;
    case "ls":
      detail = shortPath((args.path as string) ?? "/");
      break;
    case "glob": {
      detail = (args.pattern as string) ?? "";
      const globPath = (args.path as string) ?? "/";
      if (globPath !== "/") detailDim = ` in ${shortPath(globPath)}`;
      break;
    }
    case "grep": {
      detail = (args.pattern as string) ?? "";
      const grepPath = args.path as string | undefined;
      const globFilter = args.glob as string | undefined;
      if (grepPath) detailDim = ` in ${shortPath(grepPath)}`;
      if (globFilter) detailDim += ` [${globFilter}]`;
      break;
    }
    case "execute": {
      let cmd = (args.command as string) ?? "";
      if (cmd.length > 80) cmd = cmd.slice(0, 77) + "...";
      detail = cmd;
      break;
    }
    case "write_todos":
      break;
  }

  return (
    <Text>
      <Text color={dotColor}>{"● "}</Text>
      <Text color="white" bold>{label}</Text>
      {detail ? <Text color="gray" italic>{` (${detail})`}</Text> : null}
      {detailDim ? <Text color="gray" italic>{detailDim}</Text> : null}
    </Text>
  );
}

// ── Result content renderer ───────────────────────────────────────

/** Render tool result lines — ⎿ on first line, aligned indent on rest. */
function ResultContent({ content }: { content: string }) {
  const display = truncateLines(content);
  return (
    <>
      {display.map((line, i) => (
        <Text key={i} dimColor wrap="wrap">
          {i === 0 ? "  ⎿  " : "     "}{line}
        </Text>
      ))}
    </>
  );
}

// ── Main event router ─────────────────────────────────────────────

/** Routes an AgentEvent to the appropriate visual renderer. */
export const EventItem = React.memo(function EventItem({
  event,
}: EventItemProps) {
  switch (event.type) {
    case "user":
      return (
        <Box marginTop={1} marginBottom={1}>
          <Text backgroundColor="#333333" color="white" bold>
            {` \u276F ${event.content} `}
          </Text>
        </Box>
      );

    case "bash_result":
      return (
        <Box marginTop={1}>
          <BashResult
            command={(event.toolArgs?.command as string) ?? ""}
            output={event.content}
            status={event.status}
          />
        </Box>
      );

    case "tool_result": {
      const skillName = extractSkillName(event.toolArgs ?? {});
      if (skillName) {
        return (
          <Box flexDirection="column" marginTop={1}>
            <Text>
              <Text color="green">{"● "}</Text>
              <Text color="white" bold>{"Skill"}</Text>
              <Text color="gray" italic>{` (${skillName})`}</Text>
            </Text>
          </Box>
        );
      }

      // write_todos — render as checklist instead of raw result
      if (event.toolName === "write_todos") {
        const todos = parseTodos(event.toolArgs ?? {});
        if (todos.length > 0) {
          return (
            <Box flexDirection="column" marginTop={1}>
              <ToolCallHeader
                toolName="write_todos"
                args={event.toolArgs ?? {}}
                status={event.status}
              />
              <TodoList todos={todos} />
            </Box>
          );
        }
      }

      return (
        <Box flexDirection="column" marginTop={1}>
          <ToolCallHeader
            toolName={event.toolName ?? ""}
            args={event.toolArgs ?? {}}
            status={event.status}
          />
          <ResultContent content={event.content} />
        </Box>
      );
    }

    case "delegate": {
      const agent = event.subagent ?? "unknown";
      return (
        <Box flexDirection="column" marginTop={1}>
          <Text>
            <Text color="cyan">{"● "}</Text>
            <Text color="white" bold>{"Delegate"}</Text>
            <Text color="gray" italic>{` (${agent})`}</Text>
          </Text>
          <Text dimColor wrap="wrap">{`  ${event.content}`}</Text>
        </Box>
      );
    }

    case "ai_message":
      return (
        <Box flexDirection="column" marginTop={1}>
          <Text>
            <Text color="white">{"● "}</Text>
            <Text>{renderMarkdown(event.content)}</Text>
          </Text>
        </Box>
      );

    case "system":
      return (
        <Box marginTop={1}>
          <Text dimColor wrap="wrap">
            {event.content}
          </Text>
        </Box>
      );

    default:
      return null;
  }
});
