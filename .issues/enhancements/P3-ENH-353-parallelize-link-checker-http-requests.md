---
discovered_commit: be30013d0e2446b479c121af1d58a2309b3cfeb5
discovered_branch: main
discovered_date: 2026-02-12T16:03:46Z
discovered_by: scan-codebase
---

# ENH-353: Parallelize link checker HTTP requests

## Summary

`check_markdown_links` checks each URL sequentially with synchronous HTTP HEAD requests (up to 10s timeout each). For documentation with many external links, this can take minutes.

## Location

- **File**: `scripts/little_loops/link_checker.py`
- **Line(s)**: 180+ (drifted from 213-269 at scan commit be30013)
- **Anchor**: `check_markdown_links`

## Current Behavior

URLs are checked one at a time sequentially.

## Expected Behavior

URLs are checked concurrently using a thread pool with configurable concurrency limit.

## Proposed Solution

Use `concurrent.futures.ThreadPoolExecutor(max_workers=10)` to check URLs in parallel. The existing `check_url()` function is stateless and thread-safe.

## Motivation

This enhancement would:
- Significantly reduce wall-clock time for documentation audits with many external links
- Business value: Faster feedback loops during `ll-check-links` and `audit-docs` workflows
- Technical debt: None introduced — uses stdlib `concurrent.futures` with no new dependencies

## Implementation Steps

1. **Import ThreadPoolExecutor**: Add `from concurrent.futures import ThreadPoolExecutor, as_completed` to `link_checker.py`
2. **Add max_workers parameter**: Add optional `max_workers: int = 10` parameter to `check_markdown_links`
3. **Wrap check_url calls in executor**: Replace the sequential URL checking loop with `ThreadPoolExecutor` submission and result collection
4. **Preserve result ordering**: Collect results from futures and map back to original URLs
5. **Verify thread safety**: Confirm `check_url()` remains stateless with no shared mutable state
6. **Update tests**: Add test cases for concurrent execution and edge cases (timeouts, mixed results)

## Integration Map

- **Files to Modify**: `scripts/little_loops/link_checker.py`
- **Dependent Files (Callers/Importers)**: `scripts/little_loops/cli/docs.py` (CLI entry point)
- **Similar Patterns**: N/A
- **Tests**: `scripts/tests/test_link_checker.py`
- **Documentation**: N/A
- **Configuration**: N/A

## Scope Boundaries

- Only parallelize HTTP checks, not file-based link validation
- Add optional `max_workers` parameter with sensible default

## Impact

- **Priority**: P3 - Improves UX for documentation audits
- **Effort**: Small - ThreadPoolExecutor is straightforward
- **Risk**: Low - check_url is already stateless
- **Breaking Change**: No

## Labels

`enhancement`, `performance`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-02-12T16:03:46Z - `~/.claude/projects/<project>/024c25b4-8284-4f0a-978e-656d67211ed0.jsonl`
- `/ll:format-issue --all --auto` - 2026-02-13


## Verification Notes

- **Verified**: 2026-02-13
- **Verdict**: VALID
- `check_markdown_links` exists at line 180 (drifted from 213-269 at scan commit)
- Confirmed sequential URL checking — no ThreadPoolExecutor used
- `check_url()` is stateless and thread-safe — ready for parallelization
- Core issue remains valid

## Resolution

- **Status**: Completed
- **Date**: 2026-02-14
- **Action**: improve

### Changes Made
- `scripts/little_loops/link_checker.py`: Added `concurrent.futures` import, restructured `check_markdown_links` into two-pass approach (classify then check concurrently), added `max_workers` parameter
- `scripts/little_loops/cli/docs.py`: Added `--workers`/`-w` CLI argument, passed to `check_markdown_links`
- `scripts/tests/test_link_checker.py`: Added 3 tests for concurrent execution (max_workers forwarding, mixed results, sequential fallback)

### Verification
- 38/38 tests pass
- Lint: clean
- Types: clean

---

**Completed** | Created: 2026-02-12 | Completed: 2026-02-14 | Priority: P3
