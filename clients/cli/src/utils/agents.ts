/** Execution modes/agents shown in CLI status UI. */
export const AGENT_MODES = [
  "decepticon",
  "soundwave",
  "recon",
  "exploit",
  "postexploit",
] as const;

export type AgentMode = (typeof AGENT_MODES)[number];

/** Display labels for the mode bar. */
export const AGENT_LABELS: Record<AgentMode, string> = {
  decepticon: "Decepticon",
  soundwave: "Soundwave",
  recon: "Recon",
  exploit: "Exploit",
  postexploit: "PostExploit",
};
