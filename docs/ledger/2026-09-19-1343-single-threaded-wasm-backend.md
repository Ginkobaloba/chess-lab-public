# 2026-09-19 13:43 CDT - Single-threaded wasm backend
- **Who:** Agent, technical.
- **Change:** **Single-threaded wasm backend.** Threads need cross-origin isolation (COOP/COEP) that a host page cannot be assumed to send; one evaluation takes a median 4.4 ms on the e2e machine (`receipts/web-v1/e2e.json`). WebGPU/WebGL not used: a larger runtime for a 1.5M-parameter net.
- **Why:** Stated inline in Change: the single-file ledger recorded what and why in one bullet, and this entry keeps that text verbatim.
- **State after:** As recorded at the time; a later entry supersedes this one only where it says so.
- **Refs:** Moved from `docs/LEDGER.md`: appended there by the commit "receipts(web-v1): parity, measured bundle size, e2e; docs and ledger" (PR #6) and revised by "receipts(web-v1): regenerate at 707e165 with the fp16-weight file; docs", then moved into this file when the PR was rebased onto the one-file-per-entry ledger. The time is the first commit's author time.
