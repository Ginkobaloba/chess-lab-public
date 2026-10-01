# 2026-09-19 13:53 CDT - fp16-weight export added as an unrated option
- **Who:** Agent, technical.
- **Change:** **fp16-weight export added as an unrated option** (`--fp16`): float16 storage, float32 arithmetic, half the model download, same top-1 as fp32 on 269/269 positions at the same speed. It needs a ladder rating before it can replace fp32 as the served file.
- **Why:** Stated inline in Change: the single-file ledger recorded what and why in one bullet, and this entry keeps that text verbatim.
- **State after:** As recorded at the time; a later entry supersedes this one only where it says so.
- **Refs:** Moved from `docs/LEDGER.md`: appended there by the commit "receipts(web-v1): regenerate at 707e165 with the fp16-weight file; docs" (PR #6), and moved into this file when the PR was rebased onto the one-file-per-entry ledger. The time is that commit's author time.
