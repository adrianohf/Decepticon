"""Agent streaming engine — UI-framework independent.

Dispatches streaming events to a UIRenderer, reusable across CLI / Web.
Includes observation masking to reduce context consumption from verbose tool outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

# ── Observation masking thresholds ──────────────────────────────────────
# Tool outputs > MASK_THRESHOLD chars that are older than MASK_AGE_TURNS
# get replaced with compact summaries to preserve context budget.
MASK_THRESHOLD = 5_000  # chars — outputs below this are kept in full
MASK_AGE_TURNS = 3  # turns before masking kicks in


class UIRenderer(Protocol):
    """Interface for rendering streaming events."""

    def on_tool_call(self, tool_name: str, tool_args: dict) -> None: ...
    def on_tool_result(self, tool_name: str, tool_args: dict, content: str) -> None: ...
    def on_ai_message(self, text: str) -> None: ...
    def on_stream_end(self) -> None: ...
    def on_cancelled(self) -> None: ...
    def on_tool_progress(self, tool_name: str, session: str, status: str, detail: str) -> None: ...

    # Sub-agent streaming — emitted by StreamingRunnable during task() execution
    def on_subagent_start(self, name: str, prompt: str) -> None: ...
    def on_subagent_tool_call(self, name: str, tool_name: str, tool_args: dict) -> None: ...
    def on_subagent_tool_result(
        self, name: str, tool_name: str, tool_args: dict, content: str
    ) -> None: ...
    def on_subagent_message(self, name: str, text: str) -> None: ...
    def on_subagent_end(
        self, name: str, elapsed: float, cancelled: bool = False, error: bool = False
    ) -> None: ...


def _mask_observation(content: str, tool_name: str, tool_args: dict) -> str:
    """Create a compact summary of a verbose tool output for context efficiency.

    Replaces the full content with a reference that preserves key metadata
    while dramatically reducing token consumption.
    """
    line_count = content.count("\n") + 1
    char_count = len(content)

    # Extract key details based on tool type
    if tool_name == "bash":
        cmd = tool_args.get("command", "")
        session = tool_args.get("session", "main")
        # Keep first 200 chars as preview
        preview = content[:200].strip()
        if len(content) > 200:
            preview += "..."
        return (
            f"[Observation masked — {line_count} lines / {char_count} chars]\n"
            f"Command: {cmd[:100]}\n"
            f"Session: {session}\n"
            f"Preview: {preview}\n"
            f'[Use bash(session="{session}") to re-read or check /workspace/ for saved files]'
        )

    # Generic masking for other tools
    preview = content[:300].strip()
    if len(content) > 300:
        preview += "..."
    return (
        f"[Observation masked — {line_count} lines / {char_count} chars]\n"
        f"Tool: {tool_name}\n"
        f"Preview: {preview}"
    )


@dataclass
class StreamingEngine:
    """Streams agent execution and dispatches events to a UIRenderer.

    Context optimization features:
    - Observation masking: verbose tool outputs from older turns are replaced
      with compact summaries to keep the context window focused on recent,
      high-signal information.
    """

    agent: Any
    renderer: UIRenderer
    _turn_count: int = field(default=0, init=False)

    def run(self, user_input: str, config: dict) -> None:
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        from decepticon.core.subagent_streaming import (
            clear_subagent_renderer,
            set_subagent_renderer,
        )

        self._turn_count += 1

        # Skip printing history
        try:
            current_state = self.agent.get_state(config)
            messages_in_state = (
                current_state.values.get("messages", [])
                if current_state and hasattr(current_state, "values")
                else []
            )
            last_count = len(messages_in_state)

            # ── Observation masking on older tool messages ──
            self._mask_old_observations(messages_in_state, config)

        except Exception:
            last_count = 0

        active_tool_calls: dict[str, dict] = {}
        responded_tool_ids: set[str] = set()

        # Enable sub-agent streaming: StreamingRunnable reads the renderer
        # from this context var and emits events during task() execution
        token = set_subagent_renderer(self.renderer)

        try:
            for state_snapshot in self.agent.stream(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
                stream_mode="values",
            ):
                messages = state_snapshot.get("messages", [])
                new_messages = messages[last_count:]
                last_count = len(messages)

                for msg in new_messages:
                    if isinstance(msg, HumanMessage):
                        continue

                    if isinstance(msg, AIMessage):
                        text = msg.content
                        if isinstance(text, list):
                            text = " ".join(
                                block.get("text", "") if isinstance(block, dict) else str(block)
                                for block in text
                            ).strip()
                        if text:
                            text = text.replace("<result>", "").replace("</result>", "").strip()
                            if text:
                                self.renderer.on_ai_message(text)

                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                active_tool_calls[tc["id"]] = tc
                                self.renderer.on_tool_call(tc["name"], tc["args"])

                    elif isinstance(msg, ToolMessage):
                        responded_tool_ids.add(msg.tool_call_id)
                        tc = active_tool_calls.get(msg.tool_call_id)
                        tool_name = tc["name"] if tc else "unknown"
                        tool_args = tc["args"] if tc else {}
                        self.renderer.on_tool_result(tool_name, tool_args, str(msg.content))

        except KeyboardInterrupt:
            # Patch dangling tool calls so the conversation state stays valid.
            # Without this, the next run() would fail because LangGraph expects
            # a ToolMessage for every pending tool_call.
            dangling = [
                tc_id for tc_id in active_tool_calls if tc_id not in responded_tool_ids
            ]
            if dangling:
                patch_messages = [
                    ToolMessage(
                        content="[Cancelled by user]",
                        tool_call_id=tc_id,
                    )
                    for tc_id in dangling
                ]
                try:
                    self.agent.update_state(
                        config,
                        {"messages": patch_messages},
                    )
                except Exception:
                    pass  # Best-effort — don't break the CLI

            self.renderer.on_cancelled()
            return
        finally:
            clear_subagent_renderer(token)

        self.renderer.on_stream_end()

    def _mask_old_observations(self, messages: list, config: dict) -> None:
        """Replace verbose tool outputs from older turns with compact summaries.

        This is the core observation masking strategy from context-optimization:
        tool outputs comprise 80%+ of tokens in agent trajectories. Once the agent
        has acted on the output, keeping the full text provides diminishing value.

        Only masks outputs that are:
        1. Older than MASK_AGE_TURNS
        2. Larger than MASK_THRESHOLD characters
        3. ToolMessage type (never masks AI reasoning or system prompts)
        """
        from langchain_core.messages import AIMessage, ToolMessage

        if self._turn_count <= MASK_AGE_TURNS:
            return

        # Count turns backwards to find the masking boundary
        turn_boundary = 0
        turns_seen = 0
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], AIMessage) and not (
                hasattr(messages[i], "tool_calls") and messages[i].tool_calls
            ):
                turns_seen += 1
                if turns_seen >= MASK_AGE_TURNS:
                    turn_boundary = i
                    break

        if turn_boundary == 0:
            return

        # Mask verbose tool outputs before the boundary
        masked_count = 0
        for i in range(turn_boundary):
            msg = messages[i]
            if not isinstance(msg, ToolMessage):
                continue
            content = str(msg.content)
            # Already masked
            if content.startswith("[Observation masked"):
                continue
            # Mask status-signal responses regardless of size (polling artifacts)
            if content.startswith(("[RUNNING]", "[IDLE]", "[STALLED]", "[TIMEOUT]", "[BACKGROUND]")):
                msg.content = "[Observation masked — status check]"
                masked_count += 1
                continue
            if len(content) <= MASK_THRESHOLD:
                continue

            masked = _mask_observation(content, "bash", {})
            msg.content = masked
            masked_count += 1

        if masked_count > 0:
            # Update the agent state with masked messages
            try:
                self.agent.update_state(config, {"messages": messages})
            except Exception:
                pass  # Masking is best-effort; don't break the agent loop
