// Provenance: adapted from Ginkobaloba/draughts-lab web/vitest.config.ts at commit
// 0a5c5a0fe6cc3443565937a738509f5de9479b19 (Paradigm-owned, MIT). Changes: the
// engine-ts alias is removed.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    testTimeout: 120_000,
  },
});
