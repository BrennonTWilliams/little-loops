---
id: BUG-3034
title: ll-parallel --timeout 0 would instant-kill all workers once the core.py truthiness bug is fixed
type: BUG
priority: P2
status: open
discovered_date: 2026-08-03
captured_at: "2026-08-04T04:17:13Z"
discovered_by: capture-issue
relates_to:
- ENH-2977
- BUG-2976
labels:
- ll-parallel
- timeout
- orchestrator
---

# BUG-3034: ll-parallel --timeout 0 would instant-kill all workers once the core.py truthiness bug is fixed

## Summary

`ll-parallel --timeout 0` is documented to disable the per-issue wall-clock
budget. Today it silently does nothing, because
`scripts/little_loops/config/core.py:576` swallows the `0` with an `or`
fallback. ENH-2977 scopes in the one-line fix for that.

That fix alone is **not safe**. `timeout_per_issue` has two consumers in
`parallel/orchestrator.py` where `0` does not mean "disabled" — it means
"expire immediately." Propagating a real `0` would take
`ll-parallel --timeout 0` from *silently ignored* to *kills every worker within
one second*, which is strictly worse than the current bug.

## Current Behavior

`config/core.py:576`:

```python
timeout_per_issue=timeout_seconds or self._parallel.base.timeout_seconds,
```

`0 or 3600` → `3600`. The flag is accepted and discarded. (The line immediately
below it, `idle_timeout_per_issue`, uses the correct `if ... is not None else`
form — the two are inconsistent within a single call.)

Because `0` never reaches the orchestrator today, the two defects below are
latent rather than live.

## Root Cause

Two call sites treat `timeout_per_issue` as a value where `0` is meaningful
rather than a disable sentinel:

**1. `parallel/orchestrator.py:1006`** — the P0 sequential path:

```python
result = future.result(timeout=self.parallel_config.timeout_per_issue)
```

In `concurrent.futures`, `Future.result(timeout=0)` polls once and raises
`TimeoutError` immediately if the future isn't already done; `None` is the
no-timeout sentinel, not `0`. With `--timeout 0`, every P0 issue would
instantly raise, get caught by the bare `except Exception` at line 1009, and be
marked failed.

**2. `parallel/orchestrator.py:1553-1568`** — `_wait_for_completion`:

```python
if self.parallel_config.orchestrator_timeout > 0:
    timeout = self.parallel_config.orchestrator_timeout
else:
    timeout = self.parallel_config.timeout_per_issue * self.parallel_config.max_workers
...
while self.worker_pool.active_count > 0:
    if time.time() - start > timeout:
        self.worker_pool.terminate_all_processes()
        break
```

`0 * max_workers` → `0`, and `orchestrator_timeout` defaults to `0` so the
`else` branch is the normal path. The deadline check is true on the first
iteration, so `terminate_all_processes()` fires roughly one second into the
run, killing every worker.

By contrast, `parallel/worker_pool.py:926` passes `timeout_per_issue` into
`_run_claude_base`, which bottoms out at `subprocess_utils.py:465`
(`if timeout and (now - start_time) > timeout`) — that path handles `0`
correctly. Only the two orchestrator sites are wrong.

## Expected Behavior

`timeout_per_issue == 0` means "no per-issue wall-clock limit" consistently at
every consumer:

- `orchestrator.py:1006` — pass `None` rather than `0` to `Future.result`.
- `orchestrator.py:1553-1568` — when the computed deadline is `0`, skip the
  deadline check entirely rather than treating it as already-expired.
- `config/core.py:576` — `timeout_seconds if timeout_seconds is not None else
  self._parallel.base.timeout_seconds`, matching the `idle_timeout_per_issue`
  line directly below it.

## Steps to Reproduce

The `core.py:576` half is observable today:

```bash
ll-parallel --timeout 0 --dry-run   # resolves timeout_per_issue to 3600, not 0
```

The orchestrator half is latent and reproduces only once line 576 is fixed, or
directly:

```python
cfg = ParallelConfig(timeout_per_issue=0, max_workers=2)
# orchestrator._wait_for_completion() terminates all workers on the first tick
# orchestrator._process_sequential() raises TimeoutError per P0 issue
```

## Proposed Fix

```python
# orchestrator.py:1006
_t = self.parallel_config.timeout_per_issue
result = future.result(timeout=_t if _t else None)

# orchestrator.py:1557-1568
if self.parallel_config.orchestrator_timeout > 0:
    timeout = self.parallel_config.orchestrator_timeout
else:
    timeout = self.parallel_config.timeout_per_issue * self.parallel_config.max_workers
...
while self.worker_pool.active_count > 0:
    if timeout and time.time() - start > timeout:
        ...

# config/core.py:576
timeout_per_issue=(
    timeout_seconds if timeout_seconds is not None
    else self._parallel.base.timeout_seconds
),
```

## Integration Map

### Files to Modify

- `scripts/little_loops/parallel/orchestrator.py` — lines 1006 and 1553-1568.
- `scripts/little_loops/config/core.py` — line 576.

### Dependent Files

- `scripts/little_loops/cli/parallel.py:259` — passes `timeout_seconds=args.timeout`;
  no change, it is already correct.
- `scripts/little_loops/parallel/worker_pool.py:926` — already handles `0`
  correctly via `subprocess_utils.py:465`; no change.

### Out of Scope

`ParallelConfig.timeout_per_issue` has a default drift: the dataclass declares
`3600` (`parallel/types.py:392`) while its docstring (`:369`) and `from_dict`
(`:551`, `data.get("timeout_per_issue", 7200)`) both say `7200`. Real, but
independent of this bug — do not fold it in.

### Tests

- `create_parallel_config(timeout_seconds=0)` yields `timeout_per_issue == 0`,
  not the config default.
- `create_parallel_config(timeout_seconds=None)` still falls back to
  `parallel.base.timeout_seconds` — guards the fix from regressing the other
  way.
- `timeout_per_issue=0` on the P0 sequential path does not raise an immediate
  `TimeoutError`.
- `timeout_per_issue=0` does not trigger `terminate_all_processes()` in
  `_wait_for_completion` while workers are still active.
- `orchestrator_timeout > 0` still takes precedence over the computed value.

### Documentation

- `docs/reference/CLI.md` — the `ll-parallel` `--timeout` row (line ~402);
  confirm it states that `0` disables.
- `CHANGELOG.md` — new entry in a concrete version section, not `[Unreleased]`.

## Impact

- **Priority**: P2 — blocks ENH-2977's third scope item. The user-visible defect
  today (`--timeout 0` ignored) is minor, but the trap it sets for the
  in-flight fix is not.
- **Effort**: Small — three expressions and five tests.
- **Risk**: Low. All three changes narrow behavior to the documented contract.
  The real risk is landing ENH-2977's `core.py:576` change *without* this one.
- **Breaking Change**: No. Only affects `--timeout 0`, which today does the
  opposite of what it says.

## Related Key Documentation

- `docs/reference/CLI.md` — the canonical `ll-*` CLI reference and the
  `ll-parallel` flag table.
- `docs/reference/API.md` — documents the `parallel` module, including the
  orchestrator whose deadline handling this fixes.

## Status

**Open** | Created: 2026-08-03 | Priority: P2

Found while reviewing ENH-2977, which scopes in the `core.py:576` truthiness
fix. Verifying that `0` was safe downstream turned up these two orchestrator
sites where it is not.

## Session Log
- `/ll:capture-issue` - 2026-08-04T04:20:07 - `62eddd57-7e6c-4ca5-b631-081e050a3dc6.jsonl`
