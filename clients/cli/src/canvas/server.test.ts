import { afterEach, describe, expect, it } from "vitest";
import { GraphCanvasServer } from "./server.js";
import type { GraphSnapshot } from "../utils/graph.js";

const servers: GraphCanvasServer[] = [];

afterEach(async () => {
  while (servers.length > 0) {
    const server = servers.pop();
    if (server) {
      await server.stop();
    }
  }
});

function minimalSnapshot(): GraphSnapshot {
  return {
    nodes: {
      host1: {
        id: "host1",
        kind: "host",
        label: "10.0.0.2",
        observedAt: Date.now(),
      },
    },
    edges: {},
    stats: { nodes: 1, edges: 0 },
    lastUpdated: Date.now(),
  };
}

describe("GraphCanvasServer", () => {
  it("serves HTML and live graph API", async () => {
    const server = new GraphCanvasServer();
    servers.push(server);

    const url = await server.start();

    const health = await fetch(`${url}/healthz`).then((r) => r.json());
    expect(health.ok).toBe(true);

    const html = await fetch(url).then((r) => r.text());
    expect(html).toContain("Decepticon Graph Canvas");

    server.update(minimalSnapshot());
    const graph = await fetch(`${url}/api/graph`).then((r) => r.json());

    expect(Array.isArray(graph.nodes)).toBe(true);
    expect(graph.nodes).toHaveLength(1);
    expect(graph.nodes[0].id).toBe("host1");
  });
});
