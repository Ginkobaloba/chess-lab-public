# 2026-09-19 13:43 CDT - fp32 is the shipped default because it is the rated file
- **Who:** Agent, technical; coordinator confirmed fp32 default.
- **Change:** **fp32 is the shipped default because it is the rated file**: the re-export is byte-identical to `ckpt_080000.onnx`. int8 stays optional; PR #5 rates it separately on the ladder, and in onnxruntime-web it is also slower (29.6 ms median against 4.4 ms, `receipts/web-v1/e2e.json`), so it only saves download.
- **Why:** Stated inline in Change: the single-file ledger recorded what and why in one bullet, and this entry keeps that text verbatim.
- **State after:** As recorded at the time; a later entry supersedes this one only where it says so.
- **Refs:** Moved from `docs/LEDGER.md`: appended there by the commit "receipts(web-v1): parity, measured bundle size, e2e; docs and ledger" (PR #6) and revised by "receipts(web-v1): regenerate at 707e165 with the fp16-weight file; docs", then moved into this file when the PR was rebased onto the one-file-per-entry ledger. The time is the first commit's author time.
