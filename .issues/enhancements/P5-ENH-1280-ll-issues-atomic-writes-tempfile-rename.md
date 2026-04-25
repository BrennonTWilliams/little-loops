---
discovered_date: "2026-04-24"
discovered_by: review
---

# ENH-1280: `ll-issues` Atomic Writes via `tempfile` + `os.rename()`

## Summary

`ll-issues` file-writing operations use `pathlib.Path.write_text()` directly. On a crash or signal mid-write, this can leave a partially-written file that looks valid to subsequent readers. Switch to `tempfile.NamedTemporaryFile` + `os.rename()` so every write is atomic from the reader's perspective.

## Current Behavior

`pathlib.Path.write_text()` opens, truncates, and writes in a single call with no atomicity guarantee. A process killed between truncation and write completion leaves a zero-length or partial file at the target path.

## Expected Behavior

All `ll-issues` file writes use write-to-temp + rename:
1. Write content to a `NamedTemporaryFile` in the same directory as the target (same filesystem, so `os.rename()` is atomic)
2. `os.rename(tmp_path, target_path)` — atomic on POSIX

## Files to Modify

- `scripts/little_loops/cli/issues/` — replace `Path.write_text()` calls with atomic-write helper
- `scripts/tests/test_ll_issues_atomic_write.py` — verify no partial file is visible on simulated mid-write interrupt

## Acceptance Criteria

- All `ll-issues` write paths go through the atomic-write helper
- A reader polling the target path never observes a partial file
- Unit test simulates interrupt between open and rename; target either has old content or new content, never partial

## Impact

- **Priority**: P5 — Defensive hygiene; partial writes are rare in practice and `ll-issues` operations are short
- **Effort**: Trivial — a one-function refactor across a small number of call sites
- **Risk**: Very low
- **Breaking Change**: No

## Labels

`cli`, `ll-issues`, `reliability`

## Related / See Also

- **ENH-1198** — closed invalid; this issue extracted from it
- **ENH-1279** — `ll-issues validate-catalog` (companion issue)

---

**Open** | Created: 2026-04-24 | Priority: P5
