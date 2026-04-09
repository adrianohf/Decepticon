import { readFileSync } from "node:fs";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { buildCanvasGraph, type CanvasGraph } from "./graphView.js";
import { emptyGraphSnapshot, type GraphSnapshot } from "../utils/graph.js";

const MODULE_DIR = dirname(fileURLToPath(import.meta.url));
const HTML = readFileSync(join(MODULE_DIR, "canvas.html"), "utf-8");

function send(res: ServerResponse, code: number, contentType: string, body: string): void {
  res.writeHead(code, {
    "content-type": contentType,
    "cache-control": "no-store, no-cache, must-revalidate",
  });
  res.end(body);
}

function sendJson(res: ServerResponse, value: unknown): void {
  send(res, 200, "application/json; charset=utf-8", JSON.stringify(value));
}

export class GraphCanvasServer {
  private server: Server | null = null;
  private host = "127.0.0.1";
  private port: number | null = null;
  private graph: CanvasGraph = buildCanvasGraph(emptyGraphSnapshot());

  constructor(private readonly preferredPort = 0) {}

  update(snapshot: GraphSnapshot): void {
    this.graph = buildCanvasGraph(snapshot);
  }

  getUrl(): string | null {
    if (!this.port) return null;
    return `http://${this.host}:${this.port}`;
  }

  async start(): Promise<string> {
    if (this.server && this.port) {
      return this.getUrl()!;
    }

    this.server = createServer((req, res) => this.handleRequest(req, res));

    await new Promise<void>((resolve, reject) => {
      const onError = (err: Error) => reject(err);
      this.server!.once("error", onError);
      this.server!.listen(this.preferredPort, this.host, () => {
        this.server!.off("error", onError);
        resolve();
      });
    });

    const address = this.server.address();
    if (!address || typeof address === "string") {
      throw new Error("Unable to resolve graph canvas server address");
    }

    this.port = address.port;
    return this.getUrl()!;
  }

  async stop(): Promise<void> {
    if (!this.server) return;

    await new Promise<void>((resolve, reject) => {
      this.server!.close((err) => {
        if (err) reject(err);
        else resolve();
      });
    });

    this.server = null;
    this.port = null;
  }

  private handleRequest(req: IncomingMessage, res: ServerResponse): void {
    if (req.method !== "GET") {
      send(res, 405, "text/plain; charset=utf-8", "Method Not Allowed");
      return;
    }

    const parsed = new URL(req.url ?? "/", "http://127.0.0.1");
    if (parsed.pathname === "/api/graph") {
      sendJson(res, this.graph);
      return;
    }

    if (parsed.pathname === "/healthz") {
      sendJson(res, { ok: true });
      return;
    }

    if (parsed.pathname === "/" || parsed.pathname === "/index.html") {
      send(res, 200, "text/html; charset=utf-8", HTML);
      return;
    }

    send(res, 404, "text/plain; charset=utf-8", "Not Found");
  }
}
