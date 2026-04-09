import { useEffect, useRef, useState } from "react";
import { GraphCanvasServer } from "../canvas/server.js";
import type { GraphSnapshot } from "../utils/graph.js";

export interface GraphCanvasState {
  url: string | null;
  status: "starting" | "running" | "error";
  error: string | null;
}

const DEFAULT_STATE: GraphCanvasState = {
  url: null,
  status: "starting",
  error: null,
};

/**
 * Starts a local web canvas server and keeps it updated with current graph data.
 *
 * The server is intentionally long-lived for the entire CLI session so the URL
 * stays stable while agents stream updates.
 */
export function useGraphCanvasServer(snapshot: GraphSnapshot): GraphCanvasState {
  const serverRef = useRef<GraphCanvasServer | null>(null);
  const [state, setState] = useState<GraphCanvasState>(DEFAULT_STATE);

  useEffect(() => {
    if (!serverRef.current) {
      serverRef.current = new GraphCanvasServer();
      serverRef.current
        .start()
        .then((url) => {
          setState({
            url,
            status: "running",
            error: null,
          });
        })
        .catch((err) => {
          const message = err instanceof Error ? err.message : String(err);
          setState({ url: null, status: "error", error: message });
        });
    }

    return () => {
      if (!serverRef.current) return;
      void serverRef.current.stop();
      serverRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!serverRef.current) return;
    serverRef.current.update(snapshot);
  }, [snapshot]);

  return state;
}
