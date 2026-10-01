// Regression tests for `node scripts/ledger.mjs check`.
//
// The case these exist for: this checker was copied from paradigm-skills at a
// commit that predated paradigm-site PR #104, so it counted entries without
// asking whether the directory existed. Against a DELETED docs/ledger it
// printed "0 entries, 0 problem(s)." and exited 0, while wired to a required
// status check. The two zero cases are tested separately because they have
// different causes and a guard aimed at one can miss the other.
//
// Run: node --test scripts/
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { runCheck } from "./ledger.mjs";

const VALID_ENTRY = [
  "# 2026-09-19 12:00 CDT - probe entry",
  "- **Who:** test",
  "- **Change:** test",
  "- **Why:** test",
  "- **State after:** test",
  "- **Refs:** test",
  "",
].join("\n");

/** Collect log/err output instead of printing it. */
function capture() {
  const lines = [];
  return { lines, log: (m) => lines.push(String(m)), err: (m) => lines.push(String(m)) };
}

function withTempDir(fn) {
  const base = mkdtempSync(join(tmpdir(), "ledger-test-"));
  try {
    return fn(base);
  } finally {
    rmSync(base, { recursive: true, force: true });
  }
}

test("a missing directory fails and says so", () => {
  withTempDir((base) => {
    const dir = join(base, "docs", "ledger"); // deliberately never created
    const out = capture();
    const code = runCheck(dir, out.log, out.err);
    assert.equal(code, 1, "a missing ledger directory must fail");
    assert.match(out.lines.join("\n"), /does not exist/);
    assert.match(out.lines.join("\n"), /nothing was checked/);
  });
});

test("an empty directory fails with a different message", () => {
  withTempDir((base) => {
    const dir = join(base, "docs", "ledger");
    mkdirSync(dir, { recursive: true });
    const out = capture();
    const code = runCheck(dir, out.log, out.err);
    assert.equal(code, 1, "an empty ledger directory must fail");
    assert.match(out.lines.join("\n"), /no entries found/);
  });
});

test("one valid entry passes", () => {
  withTempDir((base) => {
    const dir = join(base, "docs", "ledger");
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "2026-09-19-1200-probe-entry.md"), VALID_ENTRY, "utf8");
    const out = capture();
    const code = runCheck(dir, out.log, out.err);
    assert.equal(code, 0, "a well formed entry must pass");
    assert.match(out.lines.join("\n"), /1 entries, 0 problem/);
  });
});

test("a malformed entry still fails", () => {
  withTempDir((base) => {
    const dir = join(base, "docs", "ledger");
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "2026-09-19-1200-probe-entry.md"), "# wrong heading\n", "utf8");
    const out = capture();
    const code = runCheck(dir, out.log, out.err);
    assert.equal(code, 1, "a malformed entry must fail");
  });
});
