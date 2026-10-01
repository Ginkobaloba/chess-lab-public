# 2026-09-19 05:06 CDT - Training length 80k steps x 2048
- **Who:** Agent, technical.
- **Change:** **Training length 80k steps x 2048** (about 1.55 epochs of 105.6M positions). Validation move-match was still rising at the end (0.512), so the final checkpoint is also the validation-best.
- **Why:** Stated inline in Change: the single-file ledger recorded what and why in one bullet, and this entry keeps that text verbatim.
- **State after:** As recorded at the time; a later entry supersedes this one only where it says so.
- **Refs:** Moved from `docs/LEDGER.md`: appended there by the commit "feat: phase-1 receipts (ladder v2, data, sup-v1 training and ratings), README, handoff" (PR #3), and moved into this file when the PR was rebased onto the one-file-per-entry ledger. The time is that commit's author time.
