# ENH-353: Parallelize link checker HTTP requests

## Summary

Replace sequential URL checking in `check_markdown_links` with concurrent checking using `ThreadPoolExecutor`.

## Research Findings

- **File**: `scripts/little_loops/link_checker.py`
- **Target function**: `check_markdown_links()` (lines 180-283)
- **Sequential bottleneck**: Loop at lines 214-269 calls `check_url()` one at a time
- **`check_url()`** (lines 148-178): Fully thread-safe — no shared mutable state, creates new Request per call, all variables local
- **Existing pattern**: `ThreadPoolExecutor` used in `scripts/little_loops/parallel/worker_pool.py` with `max_workers` config
- **CLI caller**: `scripts/little_loops/cli/docs.py:190` — passes `timeout` but no `max_workers` param yet
- **Tests**: `scripts/tests/test_link_checker.py` — mock `check_url` at module level via `@patch`
- **No async/await in codebase** — `ThreadPoolExecutor` is the established pattern

## Implementation Plan

### Phase 1: Add `max_workers` parameter to `check_markdown_links`

**File**: `scripts/little_loops/link_checker.py`

Add `max_workers: int = 10` parameter to function signature (line 180-184). Import `concurrent.futures`.

### Phase 2: Restructure URL checking loop for concurrency

**File**: `scripts/little_loops/link_checker.py`

Strategy: Separate the loop into two passes:
1. **First pass** (synchronous): Classify each URL as ignored/internal/http. Collect HTTP URLs that need checking.
2. **Concurrent pass**: Submit all HTTP URLs to `ThreadPoolExecutor`, collect results.
3. **Result assembly**: Build `LinkResult` entries from both passes, update counters.

This avoids threading concerns with the shared `LinkCheckResult` counters — all counter updates happen on the main thread after futures complete.

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def check_markdown_links(
    base_dir: Path,
    ignore_patterns: list[str] | None = None,
    timeout: int = 10,
    verbose: bool = False,
    max_workers: int = 10,
) -> LinkCheckResult:
```

Inside the per-file loop, replace the URL checking block with:
- Classify ignored/internal URLs immediately (append to results)
- Collect HTTP URLs into a list of `(url, link_text, line_num, file_str)` tuples
- After file loop, use `ThreadPoolExecutor` to check all HTTP URLs concurrently
- Map futures back to URL metadata, build results

### Phase 3: Add `--workers` CLI argument

**File**: `scripts/little_loops/cli/docs.py`

Add `--workers` argument (default: 10) and pass to `check_markdown_links(max_workers=args.workers)`.

### Phase 4: Add tests for concurrent execution

**File**: `scripts/tests/test_link_checker.py`

- Test `max_workers` parameter is passed through (mock ThreadPoolExecutor or check behavior)
- Test with `max_workers=1` (sequential fallback)
- Test mixed results (some valid, some broken) under concurrency

### Phase 5: Verify

- [ ] `python -m pytest scripts/tests/ -v`
- [ ] `ruff check scripts/`
- [ ] `python -m mypy scripts/little_loops/`

## Success Criteria

- [ ] `check_markdown_links` accepts `max_workers` parameter
- [ ] HTTP URL checks execute concurrently via ThreadPoolExecutor
- [ ] Non-HTTP URLs (ignored, internal) still classified synchronously
- [ ] All counters and results are correct (no race conditions)
- [ ] CLI exposes `--workers` flag
- [ ] All existing tests pass
- [ ] New tests for concurrent execution
- [ ] Lint/type checks pass
