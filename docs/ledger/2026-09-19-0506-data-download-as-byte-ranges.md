# 2026-09-19 05:06 CDT - Data download as byte ranges
- **Who:** Agent, technical.
- **Change:** **Data download as byte ranges.** Lichess throttles one connection to about 1 MB/s; the 4 GiB prefix was fetched as six ranges and concatenated (a sixth concurrent connection drew a 429; five were fine). The manifest hashes the assembled prefix.
- **Why:** Stated inline in Change: the single-file ledger recorded what and why in one bullet, and this entry keeps that text verbatim.
- **State after:** As recorded at the time; a later entry supersedes this one only where it says so.
- **Refs:** Moved from `docs/LEDGER.md`: appended there by the commit "feat: phase-1 receipts (ladder v2, data, sup-v1 training and ratings), README, handoff" (PR #3), and moved into this file when the PR was rebased onto the one-file-per-entry ledger. The time is that commit's author time.
