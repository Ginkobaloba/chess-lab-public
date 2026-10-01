/**
 * Loader entry (dist/chess-lab.js): the worker client and the protocol
 * constants. A page creates one client and points it at the worker file:
 *
 *   import { EngineClient } from "./chess-lab.js";
 *   const engine = new EngineClient(new URL("./chess-lab-worker.js", import.meta.url));
 *   await engine.load("./model/manifest.json", "fp32");
 *   const reply = await engine.bestMove({ moves: ["e2e4"] }).done;
 */
export { EngineClient, type Terminal } from "./client.js";
export { MAX_MOVES, PROTOCOL_VERSION, type BestMoveEvent, type EventMessage, type ModelInfo, type Request } from "./protocol.js";
