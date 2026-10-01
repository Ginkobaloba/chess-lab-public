# 2026-09-19 02:13 CDT - Second GPU not used
- **Who:** Agent.
- **Change:** **Second GPU not used.** `nexus-4070` exists in `~/.ssh/config`, but the phase-1 net trains in well under an hour on the 4090 and the bottleneck is CPU-side game play for ratings, so a second GPU would not help.
- **Why:** Stated inline in Change: the single-file ledger recorded what and why in one bullet, and this entry keeps that text verbatim.
- **State after:** As recorded at the time; a later entry supersedes this one only where it says so.
- **Refs:** The original text stays in the frozen `docs/LEDGER.md` (section 2026-09-19); added in commit `69b1423` ("docs: scaffold, license check, architecture note, ledger"). The time is that commit's author time; the single-file ledger recorded dates only.
