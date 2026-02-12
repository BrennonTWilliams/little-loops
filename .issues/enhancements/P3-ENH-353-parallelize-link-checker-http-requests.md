---
discovered_commit: be30013d0e2446b479c121af1d58a2309b3cfeb5
discovered_branch: main
discovered_date: 2026-02-12T16:03:46Z
discovered_by: scan_codebase
---

# ENH-353: Parallelize link checker HTTP requests

## Summary

`check_markdown_links` checks each URL sequentially with synchronous HTTP HEAD requests (up to 10s timeout each). For documentation with many external links, this can take minutes.

## Location

- **File**: `scripts/little_loops/link_checker.py`
- **Line(s)**: 213-269 (at scan commit: be30013)
- **Anchor**: `check_markdown_links`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/be30013d0e2446b479c121af1d58a2309b3cfeb5/scripts/little_loops/link_checker.py#L213-L269)

## Current Behavior

URLs are checked one at a time sequentially.

## Expected Behavior

URLs are checked concurrently using a thread pool with configurable concurrency limit.

## Proposed Solution

Use `concurrent.futures.ThreadPoolExecutor(max_workers=10)` to check URLs in parallel. The existing `check_url()` function is stateless and thread-safe.

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
- `/ll:scan_codebase` - 2026-02-12T16:03:46Z - `~/.claude/projects/<project>/024c25b4-8284-4f0a-978e-656d67211ed0.jsonl`


---

**Open** | Created: 2026-02-12 | Priority: P3
