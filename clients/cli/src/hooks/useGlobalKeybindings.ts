/**
 * Global keybinding handlers — Claude Code's GlobalKeybindingHandlers pattern.
 *
 * Registers all global keyboard shortcuts via Ink's useInput.
 * - ctrl+o: Toggle transcript (expand/collapse) — single expansion control
 * - ctrl+g: Cycle graph sidebar mode (overview → nodes → flows)
 * - ctrl+b: Toggle graph sidebar visibility
 * - ctrl+c: Cancel stream / exit transcript / exit app
 * - Escape: Exit transcript mode
 */

import { useCallback } from "react";
import { useInput } from "ink";
import {
  GRAPH_SIDEBAR_MODES,
  useAppState,
  useSetAppState,
} from "../state/AppState.js";
import type { ScreenMode } from "../types.js";

interface Props {
  /** Called when ctrl+c should cancel the current stream. */
  onCancel: () => void;
  /** Called when ctrl+c should exit the app (no stream running). */
  onExit: () => void;
  /** Whether a stream is currently active. */
  isStreaming: boolean;
}

export function useGlobalKeybindings({
  onCancel,
  onExit,
  isStreaming,
}: Props): void {
  const screen = useAppState((s) => s.screen);
  const setAppState = useSetAppState();

  const toggleScreen = useCallback(() => {
    setAppState((prev) => ({
      ...prev,
      screen: (prev.screen === "transcript" ? "prompt" : "transcript") as ScreenMode,
    }));
  }, [setAppState]);

  const cycleGraphMode = useCallback(() => {
    setAppState((prev) => {
      const idx = GRAPH_SIDEBAR_MODES.indexOf(prev.graphSidebarMode);
      const next = GRAPH_SIDEBAR_MODES[(idx + 1) % GRAPH_SIDEBAR_MODES.length] ?? "overview";
      return {
        ...prev,
        sidebarVisible: true,
        graphSidebarMode: next,
      };
    });
  }, [setAppState]);

  const toggleSidebar = useCallback(() => {
    setAppState((prev) => ({ ...prev, sidebarVisible: !prev.sidebarVisible }));
  }, [setAppState]);

  const exitTranscript = useCallback(() => {
    setAppState((prev) => ({ ...prev, screen: "prompt" as ScreenMode }));
  }, [setAppState]);

  useInput((input, key) => {
    // ctrl+o: toggle transcript (expand/collapse all)
    if (key.ctrl && input === "o") {
      toggleScreen();
      return;
    }

    // ctrl+g: cycle graph sidebar mode
    if (key.ctrl && input === "g") {
      cycleGraphMode();
      return;
    }

    // ctrl+b: toggle sidebar visibility
    if (key.ctrl && input === "b") {
      toggleSidebar();
      return;
    }

    // Escape in transcript → return to prompt
    if (screen === "transcript" && key.escape) {
      exitTranscript();
      return;
    }

    // ctrl+c: cancel takes priority over screen changes
    if (key.ctrl && input === "c") {
      if (isStreaming) {
        onCancel();
        // Also exit transcript if we were viewing it
        if (screen === "transcript") {
          exitTranscript();
        }
      } else if (screen === "transcript") {
        exitTranscript();
      } else {
        onExit();
      }
    }
  });
}
