# 2026-09-19 14:37 CDT - Re-ran web e2e and Python/Node tests for the phase 3 cleanups
- **Who:** agent session (chore/phase3-cleanups), technical
- **Change:** re-ran the full test set on main plus the phase 3 cleanup branch:
  Python `pytest` 22/22 passed (`uv sync --extra train`, `PYTHONPATH=.`,
  includes 6 new tests for the ladder-report TC-label fix); web `tsc -p
  tsconfig.json` clean; web `vitest run` 139/139 passed; web Playwright e2e
  (`node scripts/e2e.mjs --out ../receipts/web-v1/e2e.json`) all checks
  passed, Chromium 148.0.7778.96, Node v22.14.0, at commit
  `59dd7c54b679613fdd79d167924c44c2c932352b` (origin/main tip before this
  branch's own commits). `receipts/web-v1/e2e.json` was regenerated: the
  commit hash and per-run timing numbers changed (machine noise, e.g. fp32
  median eval 4.4ms to 4.9ms); every correctness field (269/269 parity,
  model sha256, legal-move checks, byte counts) is unchanged. `node
  scripts/ledger.mjs check` passed (27 entries, 0 problems) before this
  entry was added.
- **Why:** the phase 3 hand-off (`docs/handoffs/HANDOFF_2026-09-19_phase3.md`)
  flagged the web e2e as not re-run since the restack; this closes that gap
  as one of the three ungated cleanups (TC label, README ledger pointer, web
  e2e re-run).
- **State after:** all four test layers (pytest, tsc, vitest, e2e) are green
  on this branch; `receipts/web-v1/e2e.json` reflects this run. No behavior
  changed as a result of this item; it is a verification receipt, not a fix.
- **Refs:** `receipts/web-v1/e2e.json`, `web/README.md`, PR "chore: phase 3
  cleanups (TC label, README ledger pointer, web e2e re-run)"
