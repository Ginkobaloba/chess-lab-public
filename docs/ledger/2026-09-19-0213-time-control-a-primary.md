# 2026-09-19 02:13 CDT - Time control A (primary)
- **Who:** Agent, technical.
- **Change:** **Time control A (primary):** strength-limited Stockfish rungs search 100k nodes per move on one thread (about 0.1 s here); depth rungs use a fixed depth. Node limits are machine-independent, unlike movetime. Far faster than the 120s+1s calibration TC, so this is a drift risk the ladder receipts must show, not hide. TC B (1M nodes per move) repeats the 1320 link.
- **Why:** Stated inline in Change: the single-file ledger recorded what and why in one bullet, and this entry keeps that text verbatim.
- **State after:** As recorded at the time; a later entry supersedes this one only where it says so.
- **Refs:** The original text stays in the frozen `docs/LEDGER.md` (section 2026-09-19); added in commit `69b1423` ("docs: scaffold, license check, architecture note, ledger"). The time is that commit's author time; the single-file ledger recorded dates only.
