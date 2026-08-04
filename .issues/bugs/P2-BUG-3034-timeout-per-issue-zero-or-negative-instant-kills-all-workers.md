---
id: BUG-3034
title: timeout_per_issue of 0 or negative instant-kills all ll-parallel workers
type: BUG
priority: P2
status: open
discovered_date: 2026-08-03
captured_at: '2026-08-04T04:17:13Z'
discovered_by: capture-issue
relates_to:
- ENH-2977
- BUG-2976
labels:
- ll-parallel
- timeout
- orchestrator
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3034: timeout_per_issue of 0 or negative instant-kills all ll-parallel workers

## Summary

`timeout_per_issue == 0` is meant to disable the per-issue wall-clock budget
(the sense `0` already carries for `idle_timeout_per_issue` and for
`run_claude_command`'s `timeout`). Two consumers in
`parallel/orchestrator.py` instead read `0` as "expire immediately," so a real
`0` kills every worker roughly one second into the run.

**This is live today, not latent.** The `or` fallback at
`scripts/little_loops/config/core.py:576` blocks `0` from the `--timeout` flag,
but it does not block it from the config file: `parallel.timeout_per_issue: 0`
in `.ll/ll-config.json` resolves through `None or 0` → `0` and reaches the
orchestrator intact. Negative values reach it from the CLI as well, since `-5`
is truthy — with the same instant-kill result and no `parser.error()` guard
anywhere on the path.

ENH-2977 scopes in the one-line `core.py:576` fix. Landing that without this
one additionally opens the `--timeout 0` route into the same two defects,
turning a silently-ignored flag into a worker-killing one.

**Note on the `0`-disables contract:** it is not documented yet.
`cli_args.py:121` help text is the bare `"Timeout in seconds"` and
`docs/reference/CLI.md:394` says `Timeout in seconds per issue` — neither
mentions `0`. ENH-2977 owns establishing that wording; this issue makes the
behavior match it.

## Current Behavior

`config/core.py:576`:

```python
timeout_per_issue=timeout_seconds or self._parallel.base.timeout_seconds,
```

`0 or 3600` → `3600`. The flag is accepted and discarded. (The line immediately
below it, `idle_timeout_per_issue`, uses the correct `if ... is not None else`
form — the two are inconsistent within a single call.)

That `or` only masks the CLI route. Two other inputs deliver a
worker-killing value to the orchestrator **today**:

**Config file.** `parallel.timeout_per_issue: 0` in `.ll/ll-config.json` →
`config/automation.py:114` `data.get("timeout_per_issue", ...)` → `0` →
`base.timeout_seconds == 0` → `core.py:576` evaluates `None or 0` → `0`.
Verified directly:

```python
>>> ParallelAutomationConfig.from_dict({"timeout_per_issue": 0}).base.timeout_seconds
0
```

`config-schema.json:312` declares `"minimum": 60`, but nothing validates the
schema at config-load time (no `jsonschema` use in `little_loops/config/`), so
the bound is advisory only.

**Negative values.** `ll-parallel --timeout -5` → `-5 or 3600` → `-5`, since
`-5` is truthy. No `parser.error()` guard exists on `add_timeout_arg`
(`cli_args.py:100-122`) or in `cli/parallel.py`. Both orchestrator sites then
behave exactly as they do for `0`.

## Root Cause

Two call sites treat `timeout_per_issue` as a value where `0` is meaningful
rather than a disable sentinel:

**1. `parallel/orchestrator.py:1006`** — the P0 sequential path:

```python
result = future.result(timeout=self.parallel_config.timeout_per_issue)
```

In `concurrent.futures`, `Future.result(timeout=0)` polls once and raises
`TimeoutError` immediately if the future isn't already done; `None` is the
no-timeout sentinel, not `0`. Any negative value behaves the same. With
`timeout_per_issue <= 0`, every P0 issue instantly raises, gets caught by the
bare `except Exception` at line 1009, and is marked failed.

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

`0 * max_workers` → `0` (and `-5 * 2` → `-10`), so the deadline check is true
on the first iteration and `terminate_all_processes()` fires roughly one second
into the run, killing every worker.

The `else` branch is not merely the default — it is the **only** reachable
branch from `ll-parallel`. `orchestrator_timeout` is never set by
`create_parallel_config` (`config/core.py:572-...`) and is never read by
`ParallelAutomationConfig.from_dict`; only `ParallelConfig.from_dict`
(`types.py:553`, state-file restore) touches it. So for every CLI and
config-file user it is fixed at `0`.

By contrast, `parallel/worker_pool.py:926` passes `timeout_per_issue` into
`_run_claude_base`, which bottoms out at `subprocess_utils.py:465`
(`if timeout and (now - start_time) > timeout`) — that path handles `0`
correctly. Only the two orchestrator sites are wrong.

## Expected Behavior

`timeout_per_issue == 0` means "no per-issue wall-clock limit" consistently at
every consumer:

- `orchestrator.py:1006` — pass `None` rather than `0` to `Future.result`.
- `orchestrator.py:1553-1568` — when the computed deadline is not positive,
  skip the deadline check entirely rather than treating it as already-expired.
- `config/core.py:576` — `timeout_seconds if timeout_seconds is not None else
  self._parallel.base.timeout_seconds`, matching the `idle_timeout_per_issue`
  line directly below it.

Both orchestrator guards test `> 0`, not truthiness, so a negative value is
treated as disabled rather than as already-expired. That is the safe reading if
one slips through, but the intended handling is rejection:

- `ll-parallel --timeout -N` (any negative) → `parser.error()`, mirroring the
  guard ENH-2977 specifies for `ll-auto --timeout`. Neither issue currently
  assigns this for `ll-parallel`; it belongs here, next to the code that would
  otherwise misbehave.

**Consequence of disabling, stated deliberately:** with `timeout_per_issue == 0`
there is no remaining wall-clock brake. `_wait_for_completion` becomes an
unbounded `while active_count > 0` loop, `future.result(None)` blocks
indefinitely, `orchestrator_timeout` is unreachable from the CLI (see Root
Cause), and `idle_timeout_per_issue` defaults to `0` as well. A hung worker
hangs the run until the operator interrupts it. This is the intended contract
for an explicit "no timeout" request, but it must be said in the help text
rather than discovered — `--idle-timeout` is the recommended companion.

## Steps to Reproduce

Live today, via the config file — no code change required:

```bash
# .ll/ll-config.json:  { "parallel": { "timeout_per_issue": 0 } }
ll-parallel --workers 2
# all workers terminated ~1s in; P0 issues marked failed with a TimeoutError
```

Also live today, via a negative flag value:

```bash
ll-parallel --timeout -1 --workers 2   # same instant-kill; no parser error
```

The resolution step alone:

```python
>>> ParallelAutomationConfig.from_dict({"timeout_per_issue": 0}).base.timeout_seconds
0
```

The `--timeout 0` route is the one currently masked by `core.py:576`
(`0 or 3600` → `3600`); it joins the two above the moment ENH-2977 lands that
fix.

## Proposed Fix

```python
# orchestrator.py:1006
_t = self.parallel_config.timeout_per_issue
result = future.result(timeout=_t if _t > 0 else None)

# orchestrator.py:1557-1568
if self.parallel_config.orchestrator_timeout > 0:
    timeout = self.parallel_config.orchestrator_timeout
else:
    timeout = self.parallel_config.timeout_per_issue * self.parallel_config.max_workers
...
while self.worker_pool.active_count > 0:
    if timeout > 0 and time.time() - start > timeout:
        ...

# config/core.py:576
timeout_per_issue=(
    timeout_seconds if timeout_seconds is not None
    else self._parallel.base.timeout_seconds
),

# cli/parallel.py, after parsing
if args.timeout is not None and args.timeout < 0:
    parser.error("--timeout must be >= 0 (0 disables the per-issue timeout)")
```

Note both orchestrator guards use `> 0` rather than the truthiness form
`if timeout and ...` — truthiness disables on `0` but still treats `-10` as an
expired deadline, which is the instant-kill path.

## Integration Map

### Files to Modify

- `scripts/little_loops/parallel/orchestrator.py` — lines 1006 and 1553-1568.
- `scripts/little_loops/config/core.py` — line 576.
- `scripts/little_loops/cli/parallel.py` — negative-`--timeout` `parser.error()`
  guard, alongside the existing argument wiring at `:172`/`:259`.

### Dependent Files

- `scripts/little_loops/cli/parallel.py:259` — passes `timeout_seconds=args.timeout`;
  the pass-through itself is correct and unchanged.
- `scripts/little_loops/parallel/worker_pool.py:926` — already handles `0`
  correctly via `subprocess_utils.py:465`; no change.
- `scripts/little_loops/cli_args.py:100-122` (`add_timeout_arg`) — the `help=`
  string still reads `"Timeout in seconds"`, with no mention of `0`.
  **ENH-2977 owns this edit**; if this issue lands first, the behavior will be
  correct but undocumented at the CLI. Do not duplicate the change here.
- `scripts/little_loops/config-schema.json:308-313` — `"minimum": 60` now
  contradicts a supported `0`. Unenforced at load time, so not a functional
  blocker, but it should read `"minimum": 0` with a description noting that `0`
  disables. Small enough to fold in; call it out in the PR either way.

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
- **The live config-file route**: `parallel.timeout_per_issue: 0` in
  `.ll/ll-config.json` resolves end-to-end to `ParallelConfig.timeout_per_issue
  == 0` (currently untested, and the path by which this bug is reachable
  today).
- `timeout_per_issue=0` on the P0 sequential path does not raise an immediate
  `TimeoutError`.
- `timeout_per_issue=0` does not trigger `terminate_all_processes()` in
  `_wait_for_completion` while workers are still active.
- Same two assertions for a **negative** `timeout_per_issue`, which the `> 0`
  guards must also treat as disabled rather than expired.
- `ll-parallel --timeout -1` exits via `parser.error()` (exit code 2).
- `orchestrator_timeout > 0` still takes precedence over the computed value.
  Note this field is not reachable through `create_parallel_config`, so the
  test must construct `ParallelConfig` directly — it is not a CLI-level
  assertion.

### Documentation

- `docs/reference/CLI.md:394` — the `ll-parallel` `--timeout` row currently
  reads `Timeout in seconds per issue`. This is an **edit**, not a
  confirmation: it must state that `0` disables and that negatives are
  rejected. Coordinate with ENH-2977, which changes the underlying `--timeout`
  help string for both `ll-auto` and `ll-parallel`.
- `CHANGELOG.md` — new entry in a concrete version section, not `[Unreleased]`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-04 — based on codebase analysis:_

### Existing Test Conventions to Extend

- `scripts/tests/test_config.py:1092-1216` — `is not None else` fallback tests for `create_parallel_config` follow a tri-state naming convention per flag: `..._explicit_true`, `..._explicit_false`, `..._none_falls_back_to_config_true/false`. The `timeout_per_issue`/`timeout_seconds` tests in this issue's Tests list should follow this same class and naming shape.
- `scripts/tests/test_orchestrator.py`, class `TestWaitForCompletion` (`:3705-3758`, duplicated `:4307-4342`) — existing `_wait_for_completion` timeout tests use `patch("time.time")` with a `side_effect` list of successive timestamps plus `patch("time.sleep")`, set `orchestrator.parallel_config.orchestrator_timeout`/`timeout_per_issue` directly on the fixture, then assert `orchestrator.worker_pool.terminate_all_processes.assert_called()`. No existing case in this class sets either field to `0` or negative — the disabled-timeout assertions in this issue's Tests list are new cases in this same class, asserting `assert_not_called()` instead.
- `scripts/tests/test_parallel_cli.py`, class `TestParallelEnvVarSideEffects` (`:54`) — covers `--handoff-threshold`/`--context-limit` success paths but has no `pytest.raises(SystemExit)` assertions for either flag's `parser.error()` branch, nor any existing `--timeout` coverage. The `ll-parallel --timeout -1` exit-code-2 test in this issue's Tests list is a new case in this file; the established `SystemExit`-assertion idiom elsewhere in the suite is `with pytest.raises(SystemExit) as exc_info: ...; assert exc_info.value.code == 2` (e.g. `test_cli_args.py:874-881`).

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-04 — based on codebase analysis:_

### Types

`ParallelConfig` is a `@dataclass` (`scripts/little_loops/parallel/types.py:352`). Relevant fields — both plain `int`, not `int | None`; "disabled" is an `int`-convention (`0`), not a distinct sentinel type:

- `timeout_per_issue: int` — default `3600` (`parallel/types.py:392`)
- `orchestrator_timeout: int` — default `0`, meaning "use timeout_per_issue * max_workers" (`parallel/types.py:394`)
- `idle_timeout_per_issue: int` — default `0`, the already-correct sibling this fix's contract matches (`parallel/types.py:393`)
- `timeout_seconds: int | None` — parameter of `create_parallel_config`, default `None` (`config/core.py:525`)

`ParallelConfig.from_dict` (`types.py:534`) reads `timeout_per_issue=data.get("timeout_per_issue", 7200)` — note this default (`7200`) differs from the dataclass field default (`3600`); out of scope for this fix (see § Out of Scope).

### Signatures

- `ParallelOrchestrator._process_sequential(self, issue: IssueInfo) -> None` — calls `future.result(timeout=self.parallel_config.timeout_per_issue)` at line 1006 (`orchestrator.py:987`)
- `ParallelOrchestrator._wait_for_completion(self) -> None` — computes the deadline from `orchestrator_timeout`/`timeout_per_issue * max_workers` and checks it in a `while active_count > 0` loop (`orchestrator.py:1553`)
- `WorkerPool.submit(self, issue: IssueInfo, on_complete: Callable | None = None) -> Future` — returns the future that `_process_sequential` calls `.result(timeout=...)` on (`worker_pool.py:269`)
- `BRConfig.create_parallel_config(self, timeout_seconds: int | None = None) -> ParallelConfig` — line 576 resolves `timeout_per_issue=timeout_seconds or self._parallel.base.timeout_seconds` (`config/core.py:518`)
- `add_timeout_arg(parser: ArgumentParser, default: int | None = None) -> None` — registers `--timeout`/`-t` with `type=int`, no range validation (`cli_args.py:100`)

No `parser.error()` guard currently exists for `--timeout`; the closest precedent is the `if args.X is not None: ... parser.error(...)` shape used for `--handoff-threshold`/`--context-limit` in the same file (`cli/parallel.py:231-239`).

### Call Path

```
cli/parallel.py (add_timeout_arg registers --timeout/-t, type=int, default=None)
  -> args.timeout: int | None
  -> BRConfig.create_parallel_config(timeout_seconds=args.timeout, ...)   [config/core.py:518]
       -> ParallelConfig(timeout_per_issue=timeout_seconds or self._parallel.base.timeout_seconds, ...)   [config/core.py:576]
  -> ParallelConfig.timeout_per_issue: int   [parallel/types.py:392]
  -> ParallelOrchestrator(parallel_config, br_config, ...)   [orchestrator.py:73, __init__ :92]
       -> ParallelOrchestrator._process_sequential(issue)   [orchestrator.py:987]
            -> future.result(timeout=self.parallel_config.timeout_per_issue)   [orchestrator.py:1006]
       -> ParallelOrchestrator._wait_for_completion()   [orchestrator.py:1553]
            -> timeout = self.parallel_config.timeout_per_issue * self.parallel_config.max_workers  (when orchestrator_timeout <= 0)   [orchestrator.py:1561]
            -> while ...: if time.time() - start > timeout: ... terminate_all_processes()   [orchestrator.py:1564-1568]
```

## Impact

- **Priority**: P2 — two live routes (`parallel.timeout_per_issue: 0` in config,
  and `--timeout -N`) already terminate every worker ~1s into a run with a
  misleading "Timeout waiting for workers" warning, and both look like a hung
  or broken orchestrator rather than a config problem. Also blocks ENH-2977's
  third scope item, which would open a third route.
- **Effort**: Small — four expressions and nine tests.
- **Risk**: Low. Every change narrows behavior toward the intended contract.
  The residual risk is the opposite one: with the timeout genuinely disabled a
  hung worker has no automatic brake (see Expected Behavior), which is why the
  help text and `--idle-timeout` guidance are part of the fix rather than
  follow-on polish.
- **Breaking Change**: No — except in the strict sense that a project already
  setting `timeout_per_issue: 0` in config stops having its workers killed.
  That is the bug being fixed.

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

Revised 2026-08-04 after a second review against the code: the two orchestrator
defects were originally described as latent, gated behind the `core.py:576`
`or`. They are not — the config-file and negative-value routes both reach them
today, and the proposed truthiness guard (`if timeout and ...`) would have left
the negative route broken. Scope grew by one `parser.error()` guard and four
tests.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-04_

**Readiness Score**: 100/100 → STOP — ADDRESS GAPS (Program Design hard override)
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Gaps to Address
- Program Design gate (`ll-issues check-design`) fails: the issue has no `## Program Design` section at all. All five readiness criteria otherwise score 20/20 — root cause, proposed fix, integration map, and tests are already concrete and code-anchored — so this is a missing-section gap, not a specificity gap (`PD_GAP` returned empty). Add a `## Program Design` section stating the concrete signatures/call path for the three edit sites (`orchestrator.py:1006`, `orchestrator.py:1553-1568`, `core.py:576`, `cli/parallel.py` guard), or set `program_design_not_applicable: true` in frontmatter if this is judged too small to warrant the section.

## Session Log
- `/ll:confidence-check` - 2026-08-04T05:49:42 - `9df56f7f-f5e3-45ee-877d-3b23694138c5.jsonl`
- `/ll:refine-issue` - 2026-08-04T05:33:04 - `7203ba6d-70e4-4c00-af71-408c3983ed69.jsonl`
- `/ll:confidence-check` - 2026-08-04T05:28:07 - `6fc7f771-e0c8-49da-88a4-78c95303784e.jsonl`
- `/ll:verify-issues` - 2026-08-04T04:54:18 - `0645ab21-f89c-4db8-a208-435d990eba38.jsonl`
- `/ll:capture-issue` - 2026-08-04T04:20:07 - `62eddd57-7e6c-4ca5-b631-081e050a3dc6.jsonl`
