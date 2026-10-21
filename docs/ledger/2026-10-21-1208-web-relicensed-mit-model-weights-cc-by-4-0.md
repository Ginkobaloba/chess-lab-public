# 2026-10-21 12:08 CDT - web/ relicensed MIT; model weights CC BY 4.0
- **Who:** DraughtsStripe seat (Claude Opus 5.5), for Drew.
- **Change:** `web/` is now MIT: new `web/LICENSE`, plus `license: MIT` in `web/package.json` and the lockfile root, and the `pack.mjs` notice header. The rest of the repo stays GPL-3.0. README, `web/README.md` and `docs/LICENSES.md` say so, and also that the model weights are CC BY 4.0.
- **Why:** Drew's decisions, first-hand on 2026-10-21 (Q1 and Q2 of the /lab/chess spec rev 2). paradigm.codes will vendor the browser build, and a GPL wrapper in the site's build output would need a notice and a source offer.
  - The pre-check passed. web/ imports nothing from outside web/. `web/package-lock.json` lists no GPL, LGPL or AGPL package in either the shipped or the dev tree: shipped is MIT, BSD-2, BSD-3, Apache-2.0 and ISC; dev also has MPL-2.0. Drew is the sole contributor.
  - The Python tooling stays GPL-3.0, because it imports python-chess.
- **State after:** the licence text only; no code behaviour changes. ONNX Runtime's native `ThirdPartyNotices.txt` is still not shipped, and remains a release blocker (docs/LICENSES.md).
- **Refs:** `C:\dev\_status\CHESS_LAB_REDESIGN_SPEC_2026-10-21.md` section 9 a and b; `web/LICENSE`; `docs/LICENSES.md`.
