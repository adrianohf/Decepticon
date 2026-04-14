import { describe, expect, it } from "vitest";
import type { AgentEvent } from "../types.js";
import { deriveGraphSnapshot } from "./graph.js";

function toolEvent({
  id,
  toolName,
  content,
  timestamp,
  toolArgs,
}: {
  id: string;
  toolName: string;
  content: string;
  timestamp: number;
  toolArgs?: Record<string, unknown>;
}): AgentEvent {
  return {
    id,
    type: "tool_result",
    toolName,
    toolArgs,
    status: "success",
    content,
    timestamp,
  };
}

describe("deriveGraphSnapshot", () => {
  it("tracks kg_add_node and kg_add_edge updates", () => {
    const events: AgentEvent[] = [
      toolEvent({
        id: "1",
        toolName: "kg_add_node",
        timestamp: 1,
        content: JSON.stringify({
          id: "host-1",
          kind: "host",
          label: "10.0.0.5",
          stats: { nodes: 1, edges: 0, "node.host": 1 },
        }),
      }),
      toolEvent({
        id: "2",
        toolName: "kg_add_node",
        timestamp: 2,
        content: JSON.stringify({
          id: "svc-1",
          kind: "service",
          label: "https",
          stats: { nodes: 2, edges: 0, "node.host": 1, "node.service": 1 },
        }),
      }),
      toolEvent({
        id: "3",
        toolName: "kg_add_edge",
        timestamp: 3,
        toolArgs: { src: "host-1", dst: "svc-1", kind: "exposes", weight: 0.4 },
        content: JSON.stringify({
          id: "edge-1",
          kind: "exposes",
          stats: { nodes: 2, edges: 1, "edge.exposes": 1 },
        }),
      }),
    ];

    const snapshot = deriveGraphSnapshot(events);

    expect(snapshot.nodes["host-1"]?.label).toBe("10.0.0.5");
    expect(snapshot.nodes["svc-1"]?.kind).toBe("service");

    expect(snapshot.edges["edge-1"]).toMatchObject({
      src: "host-1",
      dst: "svc-1",
      kind: "exposes",
      weight: 0.4,
    });

    expect(snapshot.stats.nodes).toBe(2);
    expect(snapshot.stats.edges).toBe(1);
    expect(snapshot.lastUpdated).toBe(3);
  });

  it("parses fenced JSON from kg_query and neighbors", () => {
    const events: AgentEvent[] = [
      toolEvent({
        id: "1",
        toolName: "kg_query",
        timestamp: 10,
        content: [
          "```json",
          JSON.stringify(
            {
              total: 2,
              returned: 2,
              nodes: [
                {
                  id: "vuln-1",
                  kind: "vulnerability",
                  label: "RCE in API",
                  props: { severity: "critical" },
                },
                {
                  id: "url-1",
                  kind: "url",
                  label: "https://target.local/login",
                  props: {},
                },
              ],
            },
            null,
            2,
          ),
          "```",
        ].join("\n"),
      }),
      toolEvent({
        id: "2",
        toolName: "kg_neighbors",
        timestamp: 11,
        toolArgs: { node_id: "vuln-1", direction: "in" },
        content: JSON.stringify([
          {
            edge_kind: "has_vuln",
            edge_weight: 0.5,
            neighbor_id: "url-1",
            neighbor_kind: "url",
            neighbor_label: "https://target.local/login",
          },
        ]),
      }),
    ];

    const snapshot = deriveGraphSnapshot(events);

    expect(snapshot.nodes["vuln-1"]?.severity).toBe("critical");
    expect(snapshot.nodes["url-1"]?.kind).toBe("url");

    const edges = Object.values(snapshot.edges);
    expect(edges).toHaveLength(1);
    expect(edges[0]).toMatchObject({
      src: "url-1",
      dst: "vuln-1",
      kind: "has_vuln",
      weight: 0.5,
    });
  });

  it("ingests Composer-style graph payloads", () => {
    const events: AgentEvent[] = [
      toolEvent({
        id: "1",
        toolName: "show_diagram",
        timestamp: 20,
        content: JSON.stringify({
          graph: {
            nodes: [
              {
                id: "frontend",
                data: { label: "Web App", nodeType: "frontend" },
              },
              {
                id: "backend",
                data: { label: "API", nodeType: "backend" },
              },
            ],
            edges: [
              {
                id: "edge-ui-api",
                source: "frontend",
                target: "backend",
                data: { protocol: "REST" },
              },
            ],
          },
        }),
      }),
    ];

    const snapshot = deriveGraphSnapshot(events);

    expect(snapshot.nodes.frontend?.kind).toBe("frontend");
    expect(snapshot.nodes.frontend?.label).toBe("Web App");
    expect(snapshot.nodes.backend?.kind).toBe("backend");
    expect(snapshot.edges["edge-ui-api"]?.kind).toBe("REST");
    expect(snapshot.stats.nodes).toBe(2);
    expect(snapshot.stats.edges).toBe(1);
  });
});
