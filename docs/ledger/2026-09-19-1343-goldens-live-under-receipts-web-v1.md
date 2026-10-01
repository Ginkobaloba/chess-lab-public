# 2026-09-19 13:43 CDT - Goldens live under `receipts/web-v1/`
- **Who:** Agent, technical; easy to move if Drew prefers.
- **Change:** **Goldens live under `receipts/web-v1/`** (not a new `golden/` directory as in draughts-lab) so every committed number and contract file stays in the one place CLAUDE.md names. `encode_golden.json` is the encoder contract; `parity.json` holds the PyTorch/ONNX parity and each position's top-1 for the browser check.
- **Why:** Stated inline in Change: the single-file ledger recorded what and why in one bullet, and this entry keeps that text verbatim.
- **State after:** As recorded at the time; a later entry supersedes this one only where it says so.
- **Refs:** Moved from `docs/LEDGER.md`: appended there by the commit "receipts(web-v1): parity, measured bundle size, e2e; docs and ledger" (PR #6), and moved into this file when the PR was rebased onto the one-file-per-entry ledger. The time is that commit's author time.
