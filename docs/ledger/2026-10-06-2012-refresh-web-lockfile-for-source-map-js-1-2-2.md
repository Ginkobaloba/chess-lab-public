# 2026-10-06 20:12 CDT - refresh web lockfile for source-map-js 1.2.2
- **Who:** dependabot-fix session (Claude Sonnet 5.5), unowned-repo sweep.
- **Change:** web/package-lock.json only: source-map-js 1.2.1 to 1.2.2 (transitive via postcss), generated with npm 10.
- **Why:** clears the open high Dependabot alert on source-map-js (dev scope). Not touched: torch low (uv.lock, 2.13.0) and setuptools medium (uv.lock), which is already covered by open Dependabot PR #1.
- **State after:** npm@10 ci in web/ passes, typecheck and vitest pass.
- **Refs:** web/package-lock.json, C:\dev\_status\DEPENDABOT_TRIAGE_2026-10-06.md
