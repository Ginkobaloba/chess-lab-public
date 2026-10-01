# 2026-09-19 13:43 CDT - Measured size replaces the memo estimate
- **Who:** Agent.
- **Change:** **Measured size replaces the memo estimate** in `docs/ARCHITECTURE.md`: the wasm runtime is 3,687,160 bytes gzip (the memo said about 3.5 MB), and the runtime plus the rated model is 9,313,529 bytes gzip before the first move (`receipts/web-v1/bundle-size.json`).
- **Why:** Stated inline in Change: the single-file ledger recorded what and why in one bullet, and this entry keeps that text verbatim.
- **State after:** As recorded at the time; a later entry supersedes this one only where it says so.
- **Refs:** Moved from `docs/LEDGER.md`: appended there by the commit "receipts(web-v1): parity, measured bundle size, e2e; docs and ledger" (PR #6) and revised by "receipts(web-v1): regenerate at 707e165 with the fp16-weight file; docs", then moved into this file when the PR was rebased onto the one-file-per-entry ledger. The time is the first commit's author time.
