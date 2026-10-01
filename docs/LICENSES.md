# License check (phase 1, 2026-09-19)

This is an engineering record, not legal advice.

**Repo license: GPL-3.0** (full text in `LICENSE`). This covers the Python
tooling, which imports python-chess (GPL-3.0-or-later), and everything else
in the repo. Third-party components keep their own licenses, listed below.

## Summary

| Component | License | Checked from | How chess-lab uses it | Ships in a browser build? |
|---|---|---|---|---|
| python-chess 1.11.2 (`chess` on PyPI) | GPL-3.0-or-later | installed wheel METADATA: `License: GPL-3.0+`, classifier `GPLv3 or later` | Python dependency of the tooling (move generation, PGN parsing, UCI driver) | No |
| Stockfish 19 (`sf_19`, `stockfish-windows-x86-64-universal.zip`) | GPL-3.0 | `Copying.txt` in the release zip | External binary over UCI, one process per game; never linked, never vendored, never committed | No |
| Lichess standard rated database (2026-08 export) | CC0 | database.lichess.org: "Database exports are released under the Creative Commons CC0 license. Use them for research, commercial purpose, publication, anything you like." | Training data (a bounded byte prefix of one month) | Only as learned weights |
| Lichess broadcast database | CC BY-SA 4.0 | same page | Not used | n/a |
| Maia-1 (`CSSLab/maia-chess`) | GPL-3.0 | GitHub API `license.spdx_id` | Not used | No |
| Maia-2 (`CSSLab/maia2`) code | MIT | GitHub API `license.spdx_id`, README "License" section | Not used | No |
| Maia-2 weights | **Unverified** | `maia2/model.py` downloads them from Google Drive (`drive.google.com/uc?id=...`); no weight-specific license or terms file was found next to them | Not used | No |
| draughts-lab (copied pieces) | MIT, Paradigm-owned | `C:\dev\draughts-lab\LICENSE` | `chesslab/stats.py`, `chesslab/seeds.py` verbatim; `chesslab/hw.py`, `chesslab/ladder.py` adapted; `web/scripts/cpu-cap.ps1` copied, `web/scripts/{pack,serve,e2e}.mjs` and the protocol, core, worker and client shape in `web/src/` adapted (provenance headers name the source file and commit) | The adapted `web/src` pieces, yes |
| chess.js 1.4.0 | BSD-2-Clause | `LICENSE` file in the installed package (Copyright (c) 2025, Jeff Hlywa) and package.json `license` | Legal move generation in the browser worker and the dev page | Yes (in `chess-lab-worker.js`; notice kept at the end of the file and in `THIRD_PARTY_NOTICES.txt`) |
| onnxruntime-web 1.30.0 | MIT | package.json `license: MIT`; the bundled file's header "Copyright (c) Microsoft Corporation. All rights reserved. Licensed under the MIT License." (the npm package ships no LICENSE file) | Runs the ONNX model in the browser worker (wasm backend) | Yes (`chess-lab-worker.js` and `ort-wasm-simd-threaded.wasm`) |
| ONNX Runtime native dependencies compiled into `ort-wasm-simd-threaded.wasm` | Various (listed in ONNX Runtime's `ThirdPartyNotices.txt`) | **Unverified**: not in the npm package | Part of the wasm runtime | Yes: that notices file must ship with any public release (VERIFY at tag v1.30.0) |
| Web dev dependencies: esbuild 0.28.2 (MIT), typescript 7.0.2 (Apache-2.0), vitest 5.0.1 (MIT), playwright-core 1.60.0 (Apache-2.0), @types/node 22.20.3 (MIT) | as listed | each package.json `license` | Build, tests, e2e | No |

Hashes and versions:

- Stockfish zip SHA-256 `3c8bf1f9ea66a09350a40df4f632288285ac206d99f33ab5842c408fc30b48a7`,
  exe SHA-256 `45bc8e4969147db9c2eb533810637994619bff0eacc81ccfd9854394901bcbd0`,
  `id name Stockfish 19`, `UCI_Elo` range 1320 to 3190.
- Lichess 2026-08 full-file SHA-256 (published): `6bf6fa8a5dee7bb81d1874ac312160060daf12f18a29dc2740a3bf6f5e5e6248`.
  The prefix actually used is hashed in the data manifest (`receipts/data/manifest.json`).

## Consequences

1. **Stockfish** is fine as an external rating opponent: GPL-3 obligations
   attach to distributing Stockfish itself, which this repo does not do (the
   binary lives under `D:\chess-lab-data\bin`, is gitignored, and is fetched
   from the official release).
2. **python-chess** is GPL-3.0-or-later. The Python tooling here imports it,
   so under a strict reading a *distributed* copy of that tooling is a
   combined work that must be GPL-3 compatible. The repo is therefore
   licensed GPL-3.0 as a whole. The copied draughts-lab code is MIT, which is
   compatible with GPL-3.0.
3. **The browser build** (`web/`, prep only, nothing public) ships the ONNX
   weights, onnxruntime-web 1.30.0 (MIT) and chess.js 1.4.0 (BSD-2-Clause),
   checked from the installed packages (table above). esbuild's metafile
   names only those two packages as inputs to the worker, but
   `ort.wasm.bundle.min.mjs` is pre-built by Microsoft, so the JS it inlines
   is not visible there. The full runtime dependency tree
   (`npm ls --omit=dev --all`: onnxruntime-common, flatbuffers, long,
   platform, guid-typescript, protobufjs and its @protobufjs parts) is MIT,
   Apache-2.0, BSD-3-Clause and ISC, so no GPL code ships either way; which of
   those the pre-built file actually contains is covered by ONNX Runtime's
   ThirdPartyNotices (VERIFY). The
   weights are trained on CC0 data; they are not a copy of python-chess or
   Stockfish. `receipts/web-v1/encode_golden.json` is output of the Python
   encoder (python-chess computes its legal moves); it holds data, not
   python-chess code, and it is used by tests, not shipped. BSD-2 and MIT
   require the notices to travel with the bundle: `web/scripts/pack.mjs`
   writes `THIRD_PARTY_NOTICES.txt` and keeps license comments in the built
   files. ONNX Runtime's own `ThirdPartyNotices.txt` (native code in the wasm
   file) still has to be added before a public release (VERIFY).
4. **Maia weights are not used anywhere in the product or in training.**
   Maia-1 is GPL-3; Maia-2's hosted weights have no verified terms. Using
   either as an *offline rating anchor* only would be allowed for Maia-1
   (GPL-3 permits private use) but needs lc0 as a runtime; not done in phase 1.
   Whether to rely on Maia-2 at all, even if its weight terms check out, is an
   open decision.
