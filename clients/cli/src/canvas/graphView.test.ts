import { describe, expect, it } from "vitest";
import { buildCanvasGraph } from "./graphView.js";
import type { GraphSnapshot } from "../utils/graph.js";

function snapshotFixture(): GraphSnapshot {
  return {
    nodes: {
      host1: {
        id: "host1",
        kind: "host",
        label: "10.0.0.10",
        observedAt: 1,
      },
      svc1: {
        id: "svc1",
        kind: "service",
        label: "nginx",
        observedAt: 2,
      },
      vuln1: {
        id: "vuln1",
        kind: "vulnerability",
        label: "RCE",
        severity: "critical",
        observedAt: 3,
      },
      cred1: {
        id: "cred1",
        kind: "credential",
        label: "admin:hash",
        observedAt: 4,
      },
    },
    edges: {
      e1: {
        id: "e1",
        src: "host1",
        dst: "svc1",
        kind: "exposes",
        observedAt: 5,
      },
      e2: {
        id: "e2",
        src: "svc1",
        dst: "vuln1",
        kind: "has_vuln",
        weight: 0.4,
        observedAt: 6,
      },
      dangling: {
        id: "dangling",
        src: "missing",
        dst: "vuln1",
        kind: "link",
        observedAt: 7,
      },
    },
    stats: {
      nodes: 4,
      edges: 3,
      "node.vulnerability": 1,
      "node.host": 1,
      "edge.exposes": 1,
    },
    lastUpdated: 123,
  };
}

describe("buildCanvasGraph", () => {
  it("layers nodes by kind and preserves labels", () => {
    const graph = buildCanvasGraph(snapshotFixture());

    const host = graph.nodes.find((n) => n.id === "host1");
    const vuln = graph.nodes.find((n) => n.id === "vuln1");
    expect(host).toBeDefined();
    expect(vuln).toBeDefined();
    expect(host!.label).toBe("10.0.0.10");
    expect(vuln!.label).toBe("RCE");

    // Vulnerabilities should render on a later layer (greater x)
    expect(vuln!.x).toBeGreaterThan(host!.x);
  });

  it("drops edges with missing nodes and keeps edge metadata", () => {
    const graph = buildCanvasGraph(snapshotFixture());

    expect(graph.edges.map((e) => e.id)).toEqual(["e1", "e2"]);
    expect(graph.edges.find((e) => e.id === "e2")?.weight).toBe(0.4);
  });

  it("computes canvas stats including critical count", () => {
    const graph = buildCanvasGraph(snapshotFixture());

    expect(graph.stats.nodes).toBe(4);
    expect(graph.stats.edges).toBe(3);
    expect(graph.stats.critical).toBe(1);
    expect(graph.stats.lastUpdated).toBe(123);
    expect(graph.bounds.width).toBeGreaterThanOrEqual(900);
    expect(graph.bounds.height).toBeGreaterThanOrEqual(600);
  });
});
