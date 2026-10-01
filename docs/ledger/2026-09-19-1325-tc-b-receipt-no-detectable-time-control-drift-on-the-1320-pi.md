# 2026-09-19 13:25 CDT - TC B receipt: no detectable time-control drift on the 1320 pin
- **Who:** Agent, technical.
- **Change:** **TC B receipt: no detectable time-control drift on the 1320 pin.** 400 games, run id `tcb-v1`. The UCI_Elo 1320 pin at 1M nodes/move fits to 1342 (1294 to 1388), which contains the TC A anchor's fixed value (1320); its score against `sf-d1` (0.168, 0.122 to 0.225) matches the TC A pin's score against the same opponent (0.175, 0.129 to 0.234) within CI. Stated plainly: this is a null result at this sample size, not proof of zero drift. Receipt: `receipts/tcb/`; drift paragraph also in `receipts/ladder-v2/NOTES.md`.
- **Why:** Stated inline in Change: the single-file ledger recorded what and why in one bullet, and this entry keeps that text verbatim.
- **State after:** As recorded at the time; a later entry supersedes this one only where it says so.
- **Refs:** Moved from `docs/LEDGER.md`: appended there by the commit "receipts: TC B time-control drift check (tcb-v1, 400 games)" (PR #4), and moved into this file when the PR was rebased onto the one-file-per-entry ledger. The time is that commit's author time.
