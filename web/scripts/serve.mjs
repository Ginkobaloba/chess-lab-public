// Provenance: adapted from Ginkobaloba/draughts-lab web/scripts/serve.mjs at commit
// 0a5c5a0fe6cc3443565937a738509f5de9479b19 (Paradigm-owned, MIT). Changes: the
// web root is resolved here (no esbuild-common.mjs), /model/ is served from the
// model export directory outside git, and .wasm and .onnx content types.
//
// Tiny static server for the dev page (local development and Playwright only).
//
//   node scripts/serve.mjs [--port 4318] [--models D:/chess-lab-data/export]
//   open http://localhost:4318/demo/
//
// Serves web/ (so /dist/... and /demo/...) and the model export directory at
// /model/ (its manifest.json and .onnx files; never copied into the repo).
// localhost is a secure context, so crypto.subtle works. Binds to 127.0.0.1 only.
import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

export const WEB_ROOT = fileURLToPath(new URL("..", import.meta.url));
export const MODELS_DEFAULT = process.env.CHESS_LAB_EXPORT ?? "D:/chess-lab-data/export";

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".wasm": "application/wasm",
  ".onnx": "application/octet-stream",
  ".svg": "image/svg+xml",
};

export function startServer(port = 4318, models = MODELS_DEFAULT) {
  const roots = { web: normalize(WEB_ROOT).replace(/[\\/]+$/, ""), model: normalize(models).replace(/[\\/]+$/, "") };
  const server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    let decoded;
    try {
      decoded = decodeURIComponent(url.pathname);
    } catch {
      // A malformed escape (for example %E0%A4%A) must not take the server down.
      res.writeHead(400, { "content-type": "text/plain" }).end("bad request");
      return;
    }
    const isModel = decoded.startsWith("/model/");
    const root = isModel ? roots.model : roots.web;
    let path = normalize(join(root, isModel ? decoded.slice("/model".length) : decoded));
    if (!path.startsWith(root + sep) && path !== root) {
      res.writeHead(403).end();
      return;
    }
    try {
      if (statSync(path).isDirectory()) path = join(path, "index.html");
      const size = statSync(path).size;
      res.writeHead(200, {
        "content-type": TYPES[extname(path)] ?? "application/octet-stream",
        "content-length": size,
        "cache-control": "no-store",
      });
      createReadStream(path).pipe(res);
    } catch {
      res.writeHead(404, { "content-type": "text/plain" }).end("not found");
    }
  });
  return new Promise((resolve) => server.listen(port, "127.0.0.1", () => resolve(server)));
}

if (process.argv[1]?.endsWith("serve.mjs")) {
  const { values } = parseArgs({ options: { port: { type: "string", default: "4318" }, models: { type: "string", default: MODELS_DEFAULT } } });
  const server = await startServer(Number(values.port), values.models);
  console.log(`serving ${WEB_ROOT} (and ${values.models} at /model/) at http://localhost:${server.address().port}/demo/ (pid ${process.pid})`);
}
