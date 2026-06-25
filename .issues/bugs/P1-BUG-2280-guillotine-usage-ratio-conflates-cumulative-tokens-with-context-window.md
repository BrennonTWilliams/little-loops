---
id: BUG-2280
title: Option J guillotine metric conflates cumulative session tokens with context-window
  occupancy, firing spurious continuations
type: BUG
status: done
priority: P1
decision_needed: false
captured_at: '2026-06-24T23:53:24Z'
completed_at: '2026-06-25T02:55:24Z'
discovered_date: '2026-06-24'
discovered_by: capture-issue
labels:
- ll-auto
- continuation
- guillotine
- context-handoff
relates_to:
- BUG-2281
- BUG-2054
- BUG-2201
- BUG-1759
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-2280: Option J guillotine `usage_ratio` measures cumulative session tokens, not context-window occupancy

## Summary

`run_with_continuation()` in `scripts/little_loops/issue_manager.py` decides
whether to fire the Option J guillotine (spawn a fresh continuation session) by
comparing `usage_ratio = total_tokens / context_limit` against
`guillotine_threshold` (0.90). But `total_tokens` is the **cumulative** token usage
for the entire agentic session, while `context_limit` is the size of a **single**
context window (200,000). These are incommensurable: a healthy multi-turn session
routinely sums to far more than one window, so the ratio exceeds 1.0 — often several
times over — for sessions that never actually overflowed context. The guillotine
therefore fires on normally-completed work.

Observed in a real `ll-auto --only BUG-2271` run: the implementation session finished
and committed cleanly (`4d8b0c83`), yet reported **"usage 495%" (989,202 / 200,000
tokens)** and triggered Option J. A 200k context window physically cannot hold 989,202
tokens — proving `total_tokens` is not a window-occupancy measure.

## Steps to Reproduce

1. Run `ll-auto --only <ID>` on any issue substantial enough to take several agentic
   turns (tool use, file reads, test runs).
2. Let the implementation session complete normally (commit + status `done`).
3. Observe the log: `Option J triggered (usage NNN%): spawning fresh session`, where
   `NNN` is well above 100% (e.g. 495%, 149%).
4. A fresh continuation session is spawned even though the work was already finished.

## Root Cause

`scripts/little_loops/issue_manager.py` — `run_with_continuation()`:

```python
# line 323-324
total_tokens = _last_input[0] + _last_output[0]
usage_ratio = total_tokens / context_limit if context_limit > 0 else 0.0
```

`_last_input` / `_last_output` are populated by the `_tracking_usage` callback
(line 267-271), which is fed from the stream-json `result` event in
`scripts/little_loops/subprocess_utils.py:438-445`:

```python
elif etype == "result":
    usage = event.get("usage", {})
    if on_usage and usage:
        on_usage(
            usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0),
            usage.get("output_tokens", 0),
        )
```

The `result` event's `usage` aggregates the **whole run**, and
`cache_read_input_tokens` in particular is the sum of cached-prompt reads across every
internal turn — each agentic turn re-reads the prior conversation from cache, so this
figure grows without bound relative to the fixed 200k window. Dividing it by
`context_limit` (200,000) yields a ratio that has nothing to do with how full the
current context window is. The `>= guillotine_threshold` (0.90) check at line 330-332
consequently trips on essentially every non-trivial completed session.

The adjacent `prompt_too_long` stderr check (line 325) is the *reliable* overflow
signal; the `usage_ratio` arm is the defective one.

## Current Behavior

- `usage_ratio` reported as >100% (up to 495% observed) on completed sessions.
- Option J fires on work that did not overflow context, spawning unnecessary fresh
  continuation sessions and burning API budget. Combined with [[BUG-2281]] (no
  already-done guard in the Option J path) this produced an unbounded respawn loop
  that ran until it hit `429 Too Many Requests`.

## Expected Behavior

- The guillotine fires only when the session genuinely exhausted (or is about to
  exhaust) its context window, or on the `prompt is too long` stderr signal.
- A normally-completed session does not trigger a continuation regardless of how many
  cumulative tokens it consumed across its turns.

## Proposed Solution

Stop deriving the overflow decision from cumulative `result`-event totals. Options
(pick during implementation):

1. **Drop the `usage_ratio` arm entirely** and gate Option J on the reliable
   `prompt_too_long` stderr signal alone. Simplest; removes the false-positive source.
> **Selected:** Option 1 (Drop `usage_ratio` arm entirely) — `usage_ratio` is fundamentally unmeasurable from cumulative `result`-event tokens; `prompt_too_long` is the proven reliable overflow signal already present.
2. **Measure actual window occupancy** instead of cumulative usage — e.g. use the
   final turn's `input_tokens` (the live prompt size, excluding summed cache reads)
   against the model-correct window, reusing the model→limit mapping fixed for the
   hook in [[BUG-2054]] rather than the hardcoded 200,000.
3. If a usage-based pre-emptive trigger is still wanted, compute it from
   single-turn/live context size, not aggregate `cache_read_input_tokens`.

Whichever path is chosen, add a regression test that feeds a `result` event with large
cumulative `cache_read_input_tokens` (simulating a long but healthy session) and
asserts Option J does **not** fire.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-24.

**Selected**: Option 1 — Drop `usage_ratio` arm entirely

**Reasoning**: The `usage_ratio` arm computes `(input_tokens + cache_read_input_tokens) / context_limit` from the cumulative `result` event, which aggregates all token reads across every internal turn — making it incommensurable with the single-window `context_limit`. This ratio is structurally broken and cannot be fixed by adjusting the threshold. The `prompt_too_long` stderr signal is the authoritative, already-proven overflow indicator already in the codebase; gating Option J on it alone removes all false positives with zero false-negative risk. Options 2/3 (pre-emptive occupancy tracking via `on_usage_detailed`) are worthwhile but are an enhancement, not a P1 bug fix — they require 4+ file changes including porting the model→window mapping from bash and wiring `LL_CONTEXT_LIMIT` into the Python path.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1 (Drop `usage_ratio`) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option 2 (Measure occupancy via `on_usage_detailed`) | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |
| Option 3 (Single-turn compute, vague) | 1/3 | 1/3 | 1/3 | 2/3 | 5/12 |

**Key evidence**:
- Option 1: `prompt_too_long` check already at `issue_manager.py:325` and `worker_pool.py:918`; fix is symmetric deletion in both files plus sentinel-write guard; regression test mirrors `test_guillotine_path_on_context_overflow` (line 1347).
- Option 2: `on_usage_detailed` + `TokenUsage` exist (`subprocess_utils.py:44-55, 446-459`) but `_run_with_continuation()` doesn't register them; requires porting model→window mapping from `context-monitor.sh` + `LL_CONTEXT_LIMIT` wiring — out of scope for a P1 fix.
- Option 3: Under-specified; resolves to Option 2 on close reading; no concrete code path named.

## Implementation Steps

1. Add a failing test in `scripts/tests/` that drives `run_with_continuation`
   with a stub session reporting ~990k cumulative tokens on a clean completion and
   asserts no continuation is spawned (`continuation_count == 0`).
2. Replace/repair the `usage_ratio` computation at `issue_manager.py:323-324` per the
   chosen option above; keep the `prompt_too_long` path intact.
3. If reusing the model→window mapping, confirm the BUG-2054 helper is importable from
   `issue_manager.py` (it currently lives in the `context-monitor.sh` hook layer) or
   port the mapping into the Python continuation path.
4. Update the sentinel-write threshold logic (line 473-477) if it shares the same
   defective ratio.
5. Fix the `usage_ratio` fallback in the **sentinel-read path** in both files (a third `usage_ratio` site not covered by step 4): `usage_pct = sentinel_data.get("usage_percent", int(usage_ratio * 100))` — remove or replace the `int(usage_ratio * 100)` fallback with `0` once `usage_ratio` no longer exists as a local variable (`issue_manager.py` line ~427, `worker_pool.py` line ~1000).
6. Update the 13 breaking tests listed in the Integration Map → Tests section: replace `on_usage(185_000, 10_000)` + `returncode=1` trigger with `stderr="API error: Prompt is too long"` to exercise the surviving `prompt_too_long` path.
7. Run `python -m pytest scripts/tests/` + `ruff check scripts/` + mypy.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Steps 1, 2, and 4 must each be applied in **both** `issue_manager.py` and `scripts/little_loops/parallel/worker_pool.py`. The parallel worker `_run_with_continuation()` is a structural copy with identical defects: `usage_ratio` at lines 916–917, Option J guard at line 924, sentinel write at lines 1042–1044.
- Step 1 (regression test) should add tests in **both** `scripts/tests/test_issue_manager.py` (`TestRunWithContinuation`) and `scripts/tests/test_worker_pool.py` (parallel guillotine tests at lines 2452–2650).

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — `run_with_continuation()` (fix `usage_ratio` computation; update sentinel-write threshold logic sharing the same defective ratio)
- `scripts/little_loops/subprocess_utils.py` — result-event `on_usage` callback (if option 2: switch to single-turn `input_tokens` rather than cumulative totals)
- `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool._run_with_continuation()`: drop `usage_ratio` guillotine arm (line 924), update sentinel-write guard (line 1042), fix `usage_pct` fallback (line 1000), update docstring [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Callers/Importers)
- `ll-auto`, `ll-parallel`, `ll-sprint` CLI entry points — all drive `run_with_continuation()` via `issue_manager.py`
- `scripts/little_loops/issue_manager.py` — `_tracking_usage` callback (internal; fed by subprocess_utils result event)

### Similar Patterns
- `context-monitor.sh` / hook layer — BUG-2054 model→window mapping; can be ported into Python continuation path if option 2 is chosen

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**New test required (does NOT yet exist):**
- `scripts/tests/test_issue_manager.py` — add `test_large_cumulative_tokens_with_clean_completion_no_guillotine` in `TestRunWithContinuation`: inject `on_usage(989_202, 0)` with `returncode=0`, assert `call_count == 1` (no continuation). Pattern: mirror `test_guillotine_path_on_context_overflow` (line 1347) but invert assertion.
- `scripts/tests/test_worker_pool.py` — mirror the same regression test in the parallel guillotine class.

**Tests that will BREAK** — currently trigger Option J via `on_usage(185_000, 10_000)` + `returncode=1` (the `usage_ratio` arm being removed); must be updated to use `stderr="API error: Prompt is too long"` as the trigger instead:

`scripts/tests/test_issue_manager.py`:
- `test_guillotine_path_on_context_overflow` (line 1347)
- `test_guillotine_with_run_dir_writes_resume_file` (line 1435)
- `test_guillotine_without_run_dir_uses_summary_blob` (line 1489)
- `test_option_j_fresh_session_skips_option_e` (line 1571)
- `test_guillotine_with_sprint_context_injects_framing` (line 1639)
- `test_guillotine_without_sprint_context_unaffected` (line 1689)
- `test_guillotine_run_dir_single_issue_scope_constraint` (line 1733)
- `test_sentinel_written_on_high_usage` (line 1534) — breaks if sentinel-write guard (step 4) is also removed

`scripts/tests/test_worker_pool.py`:
- `test_guillotine_path_on_overflow` (line 2435)
- `test_guillotine_with_run_dir_writes_resume_file` (line 2481)
- `test_guillotine_with_sprint_context_injects_framing_in_blob` (line 2538)
- `test_guillotine_with_sprint_context_and_run_dir_writes_framing_to_file` (line 2593)

**Test that survives unchanged:**
- `test_guillotine_path_on_prompt_too_long` (line 1397 in `test_issue_manager.py`) — uses `prompt_too_long` path; unaffected by fix.

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Parallel copy of defect (fix in tandem)**: `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool._run_with_continuation()` (lines 825–1055) has an identical `_usage_tracker` closure (lines 866–868) and the same defective `usage_ratio` at lines 916–917 (Option J guard at line 924) and sentinel-write at lines 1042–1044. All four sites must be fixed together: `(issue_manager.py:324, worker_pool.py:917)` for the guillotine arm and `(issue_manager.py:475, worker_pool.py:1043)` for the sentinel-write arm.
- **`subprocess_utils.py` unchanged for Option 2**: The existing `on_usage_detailed` callback (lines 446–459 of `subprocess_utils.py`) already emits a `TokenUsage` dataclass with `input_tokens` (single-turn live prompt size) separate from `cache_read_tokens` (cumulative). Option 2 can register `on_usage_detailed` in `_run_with_continuation()` instead of `on_usage` and use `TokenUsage.input_tokens` as the occupancy estimate — no changes to `subprocess_utils.py` needed.
- **`LL_CONTEXT_LIMIT` env var is never consumed by the Python path**: `cli/auto.py:86` writes the CLI `--context-limit` flag to `os.environ["LL_CONTEXT_LIMIT"]`, but no Python code reads it back to set `context_limit` before calling `run_with_continuation()`. The default 200,000 is always used. The env var is consumed only by `hooks/scripts/context-monitor.sh:266`. If Option 2 ports the model→window mapping into Python, it should also wire `LL_CONTEXT_LIMIT` into the `context_limit` parameter.
- **Existing test class**: `TestRunWithContinuation` in `scripts/tests/test_issue_manager.py` (lines 1131–1787). Model the regression test after `test_guillotine_path_on_context_overflow` (line 1347): inject `on_usage(989_202, 0)` on a clean `returncode=0` result and assert `call_count[0] == 1` (no continuation spawned).
- **Worker pool regression test**: `scripts/tests/test_worker_pool.py` (lines 2452–2650) has parallel guillotine tests using the same `patch.object(worker_pool, "_run_claude_command")` stub pattern. Add a mirrored regression test there.

## Impact

- **Priority**: P1 — Fires on every non-trivial `ll-auto` / sprint / loop run; spurious continuations waste API budget and, combined with BUG-2281, produce unbounded respawn loops until rate-limited.
- **Effort**: Small — Targeted fix in `run_with_continuation()`; regression test already specified in Implementation Steps.
- **Risk**: Low — Removes a false-positive trigger while retaining the reliable `prompt_too_long` stderr check; genuine overflow handling is unchanged.
- **Breaking Change**: No
- **Blast Radius**: All autonomous issue processing paths (`ll-auto`, `ll-parallel`, `ll-sprint`, FSM loops driving `run_with_continuation()`).

## Related

- [[BUG-2281]] — Option J path missing already-done guard (the compounding defect that
  turns one spurious continuation into an unbounded respawn loop).
- [[BUG-2054]] — context-monitor hook 200k-denominator misreport (sibling metric bug in
  the hook layer; provides the model→window mapping to reuse).
- [[BUG-2201]] — Option J continuation scope escape (same guillotine path, different
  failure mode; its scope-constraint fix is present and working).
- [[BUG-1759]] — handoff-signal forwarding to outer FSM (origin of the already-done
  guard pattern referenced at `issue_manager.py:295`).

## Session Log
- `/ll:ready-issue` - 2026-06-25T02:32:14 - `1dae7405-974b-4068-920d-3cf120a46bc9.jsonl`
- `/ll:confidence-check` - 2026-06-25T02:29:27Z - `206895be-827f-4558-af0e-78773cc4bf82.jsonl`
- `/ll:wire-issue` - 2026-06-25T00:54:59 - `605a186d-3999-4d1a-a240-f61cf197c0ef.jsonl`
- `/ll:decide-issue` - 2026-06-25T00:31:36 - `27e8665e-4c56-4dde-ab56-7b5ada80a7a4.jsonl`
- `/ll:refine-issue` - 2026-06-25T00:24:47 - `9aa86380-3890-4fd3-aa75-4ce244b7e7af.jsonl`
- `/ll:format-issue` - 2026-06-25T00:16:52 - `7a36d447-8fb9-4718-a430-b2b18252ae14.jsonl`
- `/ll:capture-issue` - 2026-06-24T23:53:24Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f09f2f70-372c-4009-b490-01dff83e4775.jsonl`

---

## Resolution

Implemented Option 1: dropped the `usage_ratio >= guillotine_threshold` arm from `run_with_continuation()` in both `issue_manager.py` and `worker_pool.py`. Option J now fires only on the reliable `prompt_too_long` stderr signal. Also removed the dependent Option G Python sentinel-write block (same defective ratio) and replaced the `int(usage_ratio * 100)` fallback in the sentinel-read path with `0`. Updated all 13 breaking tests to use `stderr="API error: Prompt is too long"` as the trigger. Added 2 new regression tests asserting 989K cumulative tokens with clean completion produces no continuation.

## Status

done
