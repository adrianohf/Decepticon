import React, { useState, useCallback, useRef, useEffect } from "react";
import { Box, Text, useInput } from "ink";
import { TextInput } from "@inkjs/ui";
import { useTerminalSize } from "../hooks/useTerminalSize.js";
import { useSpinnerFrame } from "../hooks/useSpinnerFrame.js";

interface PromptProps {
  isDisabled: boolean;
  onSubmit: (input: string) => void;
  /** Currently active agent name, e.g. "recon". null when idle. */
  activeAgent?: string | null;
}

const COMMANDS = [
  { cmd: "/help", desc: "Show this help" },
  { cmd: "/clear", desc: "Clear conversation" },
  { cmd: "/quit", desc: "Exit" },
  { cmd: "/exit", desc: "Exit" },
];

/** All agents in execution order. */
const AGENTS = ["decepticon", "planner", "recon", "exploit", "postexploit"];

/** Display labels for the agent bar. */
const AGENT_LABELS: Record<string, string> = {
  decepticon: "Decepticon",
  planner: "Planner",
  recon: "Recon",
  exploit: "Exploit",
  postexploit: "PostExploit",
};

const DEBOUNCE_MS = 150;

/** Agent status bar: shows all agents, active one blinks. */
const AgentBar = React.memo(function AgentBar({
  activeAgent,
}: {
  activeAgent: string | null;
}) {
  const { tick } = useSpinnerFrame(activeAgent != null);
  // Blink cycle: bright for 8 ticks, dim for 4 ticks
  const bright = (tick % 12) < 8;

  return (
    <Box flexDirection="row">
      {AGENTS.map((agent, i) => {
        const label = AGENT_LABELS[agent] ?? agent;
        const isActive = agent === activeAgent;
        const separator = i < AGENTS.length - 1 ? " | " : "";

        return (
          <Text key={agent}>
            {isActive ? (
              <Text color="#ef4444" bold={bright} dimColor={!bright}>
                {label}
              </Text>
            ) : (
              <Text dimColor>{label}</Text>
            )}
            {separator && <Text dimColor>{separator}</Text>}
          </Text>
        );
      })}
    </Box>
  );
});

export const Prompt = React.memo(function Prompt({
  isDisabled,
  onSubmit,
  activeAgent = null,
}: PromptProps) {
  const lastSubmitRef = useRef(0);
  const { columns } = useTerminalSize();
  const [inputValue, setInputValue] = useState("");
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [inputKey, setInputKey] = useState(0);

  // Filter commands — exclude exact matches (already fully typed)
  const isTypingCommand =
    inputValue.startsWith("/") && !inputValue.includes(" ");
  const filteredCommands = isTypingCommand
    ? COMMANDS.filter(
        (c) => c.cmd.startsWith(inputValue) && c.cmd !== inputValue,
      )
    : [];
  const showMenu = filteredCommands.length > 0;

  // Reorder suggestions so selected dropdown item is first
  const suggestionList = showMenu
    ? [
        filteredCommands[selectedIdx]?.cmd,
        ...COMMANDS.map((c) => c.cmd).filter(
          (c) => c !== filteredCommands[selectedIdx]?.cmd,
        ),
      ].filter((c): c is string => c != null)
    : COMMANDS.map((c) => c.cmd);

  // Reset selection on input change
  useEffect(() => {
    setSelectedIdx(0);
  }, [inputValue]);

  // Up/Down/Tab — TextInput explicitly ignores these, so they bubble here
  useInput((_input, key) => {
    if (isDisabled || !showMenu) return;

    if (key.upArrow) {
      setSelectedIdx((prev) => Math.max(0, prev - 1));
    } else if (key.downArrow) {
      setSelectedIdx((prev) =>
        Math.min(filteredCommands.length - 1, prev + 1),
      );
    } else if (key.tab) {
      const cmd = filteredCommands[selectedIdx]?.cmd;
      if (cmd) {
        setInputValue(cmd);
        setInputKey((prev) => prev + 1);
      }
    }
  });

  const handleChange = useCallback((value: string) => {
    setInputValue(value);
  }, []);

  const handleSubmit = useCallback(
    (value: string) => {
      const now = Date.now();
      if (now - lastSubmitRef.current < DEBOUNCE_MS) return;
      lastSubmitRef.current = now;
      setInputValue("");
      setInputKey((prev) => prev + 1);
      onSubmit(value);
    },
    [onSubmit],
  );

  const maxCmdLen = Math.max(...COMMANDS.map((c) => c.cmd.length));

  return (
    <Box flexDirection="column" marginTop={1}>
      <Text dimColor>{"─".repeat(columns)}</Text>
      <Box flexDirection="row">
        <Text color="white">{"› "}</Text>
        <TextInput
          key={inputKey}
          placeholder=""
          defaultValue={inputValue || undefined}
          suggestions={suggestionList}
          isDisabled={isDisabled}
          onChange={handleChange}
          onSubmit={handleSubmit}
        />
      </Box>

      {showMenu && (
        <Box flexDirection="column" marginLeft={2}>
          {filteredCommands.map((cmd, i) => (
            <Text key={cmd.cmd}>
              <Text
                bold={i === selectedIdx}
                dimColor={i !== selectedIdx}
              >
                {` ${cmd.cmd.padEnd(maxCmdLen + 2)}`}
              </Text>
              <Text dimColor>{cmd.desc}</Text>
            </Text>
          ))}
        </Box>
      )}

      <Text dimColor>{"─".repeat(columns)}</Text>

      {/* Agent status bar — visible while streaming */}
      {activeAgent && <AgentBar activeAgent={activeAgent} />}
    </Box>
  );
});
