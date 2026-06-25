---
id: BUG-2281
title: Option J guillotine path lacks the already-done guard, causing an unbounded
  respawn loop on completed issues
type: BUG
status: open
priority: P2
decision_needed: false
captured_at: '2026-06-24T23:53:24Z'
discovered_date: '2026-06-24'
discovered_by: capture-issue
labels:
- ll-auto
- continuation
- guillotine
- context-handoff
relates_to:
- BUG-2280
- BUG-1759
- BUG-2201
confidence_score: 98
outcome_confidence: 92
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 23
score_change_surface: 23
---

# BUG-2281: Option J guillotine path is missing the `_check_issue_already_done` guard

## Summary

`run_claude_with_continuation()` in `scripts/little_loops/issue_manager.py` has two
continuation triggers. The **CONTEXT_HANDOFF** path checks whether the issue is already
`done`/`cancelled` before spawning a fresh session and short-circuits to success if so
(line 296-305, added for [[BUG-1759]]). The **Option J guillotine** path (line 330-414)
has **no such guard** — it spawns a fresh continuation unconditionally whenever its
trigger condition is met. So when an issue is already complete, the guillotine keeps
spawning fresh sessions that rediscover "it's done," exit, and trigger yet another
spawn. The result is an unbounded respawn loop.

Observed with `ll-auto --only BUG-2271`: the issue was committed and marked `done`
(`4d8b0c83`), yet successive Option J continuations were spawned. Killing one
continuation revealed the orchestrator had **already spawned its replacement** — a live
respawn loop that ran until it hit `429 Too Many Requests`. The orchestrator's
`.auto-manage-state.json` stayed at `phase: processing`, `completed_issues: []`, never
recording the completion.

> Note: the *trigger* that kept firing is the defective metric in [[BUG-2280]]. This
> issue is the missing **safety net** — even after the metric is fixed, the Option J
> path should refuse to continue work that is already done.

## Motivation

The `_check_issue_already_done` guard (added in [[BUG-1759]]) prevents the CONTEXT_HANDOFF path from re-running completed work, but the Option J guillotine path was never updated to include this safeguard. Without it, a single spurious Option J trigger converts into an unbounded respawn loop:

- Each continuation rediscovers the issue is done, exits, and spawns a replacement
- The API budget is exhausted before the orchestrator records the issue as complete
- The orchestrator's `.auto-manage-state.json` remains at `phase: processing`, leaving the issue permanently orphaned in the active queue

The fix is a one-line guard insertion mirroring an existing, proven pattern — the lowest-cost safety net for preventing budget-draining loops on already-complete work.

## Steps to Reproduce

1. Run `ll-auto --only <ID>` on an issue that completes (commits + status `done`) but
   whose session trips the Option J trigger (see [[BUG-2280]]).
2. Observe repeated `Option J triggered (...): spawning fresh session` log lines after
   the issue is already `done`.
3. Each fresh session confirms the work is done, exits, and a new one is spawned.
4. The loop continues (escaping the inner `max_continuations=3` bound via outer
   re-entry — see Open Questions) until rate-limited or killed.

## Root Cause

`scripts/little_loops/issue_manager.py` — the CONTEXT_HANDOFF branch guards completion:

```python
# line 293-305 (CONTEXT_HANDOFF path)
already_done = _check_issue_already_done(issue_path, logger)
if already_done:
    logger.info("Issue already done/cancelled; skipping handoff and returning success")
    result = subprocess.CompletedProcess(..., returncode=0, ...)
    break
```

…but the Option J branch jumps straight to spawning the fresh session with no equivalent
check:

```python
# line 330-334 (Option J path) — no _check_issue_already_done
if (prompt_too_long or usage_ratio >= guillotine_threshold) and continuation_count < max_continuations:
    trigger_reason = ...
    logger.warning(f"Option J triggered ({trigger_reason}): spawning fresh session")
    # ... writes guillotine-prompt.md and continues, unconditionally ...
```

## Current Behavior

- Option J spawns continuation sessions on already-`done`/`cancelled` issues.
- Unbounded respawn loop; API budget exhausted; terminates only on rate-limit (429) or
  manual kill. State file never records completion.

## Expected Behavior

- Before spawning an Option J continuation, check `_check_issue_already_done(issue_path)`.
- If the issue is `done`/`cancelled`, return success (returncode 0) and break — exactly
  as the CONTEXT_HANDOFF path already does.
- The orchestrator records the issue as completed and moves on.

## Proposed Solution

Add the same guard at the top of the Option J branch (before writing the guillotine
prompt). Factor the shared check so both branches call it identically:

```python
if (prompt_too_long or usage_ratio >= guillotine_threshold) and continuation_count < max_continuations:
    if _check_issue_already_done(issue_path, logger):
        logger.info("Issue already done/cancelled; skipping Option J continuation")
        result = subprocess.CompletedProcess(args=result.args, returncode=0,
                                              stdout=result.stdout, stderr=result.stderr)
        break
    # ... existing guillotine spawn ...
```

## Implementation Steps

1. **Add failing tests** (TDD):
   - In `scripts/tests/test_issue_manager.py`, class `TestRunWithContinuation` (line 1131): add `test_option_j_guard_skips_when_issue_already_done`. Pattern: write a `status: done` issue file, call `on_usage(185_000, 10_000)` in `mock_run` to drive `usage_ratio ≥ 0.90`, patch `detect_context_handoff` → `False`, assert `call_count[0] == 1` (no fresh session) and `result.returncode == 0`.
   - In `scripts/tests/test_worker_pool.py`, class `TestRunWithContinuation` (line 2340): add equivalent test using `patch.object(worker_pool, "_run_claude_command", ...)` and `issue_id="BUG-999"` pointing to a `status: done` fixture file.
2. **Fix `issue_manager.py`**: Insert before line 330 (`if (prompt_too_long or usage_ratio >= guillotine_threshold)`):
   ```python
   if _check_issue_already_done(issue_path, logger):
       logger.info("Issue already done/cancelled; skipping Option J continuation")
       result = subprocess.CompletedProcess(args=result.args, returncode=0,
                                             stdout=result.stdout, stderr=result.stderr)
       break
   ```
3. **Fix `worker_pool.py`**: Insert the equivalent guard before line 923 (`if (prompt_too_long or usage_ratio >= guillotine_threshold)`) using `self._check_issue_already_done(issue_id, working_dir)`.
4. **Run checks**: `python -m pytest scripts/tests/test_issue_manager.py scripts/tests/test_worker_pool.py -v` + `ruff check scripts/` + `python -m mypy scripts/little_loops/`.

## Open Questions

- The inner loop bounds continuations at `max_continuations` (default 3), yet the
  observed loop appeared to exceed that. **Partial answer from codebase research**: `continuation_count` is a local variable in `run_with_continuation()` and is NOT reset by the outer `AutoManager`. `AutoManager._process_issue()` calls `process_issue_inplace()` once per issue and does not re-enter on CONTEXT_HANDOFF — continuation is handled entirely within the inner loop. However, if Option J's fresh session itself emits a CONTEXT_HANDOFF signal (standard path), the CONTEXT_HANDOFF branch would print `"CONTEXT_HANDOFF: Ready for fresh session"` to stdout, which the outer FSM *could* detect and re-invoke the manager — producing a new `run_with_continuation()` call with `continuation_count=0`. This outer re-entry path remains to be confirmed by reading `ll-auto` FSM state-machine code (`AutoManager.run()` at line 1263).

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — `run_claude_with_continuation()`: add `_check_issue_already_done` guard at the head of the Option J branch (before the `trigger_reason` assignment, ~line 330)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool._run_with_continuation()`: add `self._check_issue_already_done(issue_id, working_dir)` guard at the head of the Option J branch (~line 926, before `trigger_reason` assignment) — this is the mirror fix to `issue_manager.py`; the Implementation Steps already describe this but it was absent from Files to Modify [Agent 1 + Agent 3 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:process_issue_inplace()` — calls `run_with_continuation()` at line 879; passes `issue_path=info.path`, so the guard has a valid path to check
- `scripts/little_loops/cli/sprint/run.py:66,650` — calls `process_issue_inplace()` directly (ll-sprint CLI)
- `scripts/little_loops/parallel/worker_pool.py:WorkerPool._run_with_continuation()` — **mirror implementation** of the same E+G+J logic at line 825; called from `_process_worker_issue()` at line 488; has its own `_check_issue_already_done()` at line 789 (takes `issue_id: str | None` instead of `Path`) — **also missing the guard in its Option J block at line 924** (same structural gap)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Worker pool mirror gap confirmed**: `scripts/little_loops/parallel/worker_pool.py:_run_with_continuation()` has the same structural layout — `_check_issue_already_done()` is present in the CONTEXT_HANDOFF branch (line 888) but absent from the Option J branch (line 924). The fix scope should cover both `issue_manager.py` and `worker_pool.py`.
- **Guard call differs between the two implementations**: `issue_manager._check_issue_already_done(issue_path, logger)` takes a `Path`; `worker_pool._check_issue_already_done(issue_id, working_dir)` takes `str | None` + `Path`. Both are already defined — just need the call inserted before the trigger check.
- **`sprint_context` sub-paths are covered**: the `sprint_context` and `run_dir` branches are both inside the Option J block, so adding the guard before `if (prompt_too_long or usage_ratio >= guillotine_threshold)` covers all sub-paths in a single insertion point.

### Similar Patterns
- `run_claude_with_continuation()` CONTEXT_HANDOFF branch (lines 293–305) — the existing `_check_issue_already_done` call is the exact pattern to replicate

### Tests
- `scripts/tests/test_issue_manager.py` — primary test file; class `TestRunWithContinuation` (line 1131) hosts all Option J tests. New test goes here.
  - Existing Option J tests at: `test_guillotine_path_on_context_overflow` (line 1347), `test_guillotine_path_on_prompt_too_long` (line 1397), `test_guillotine_with_run_dir_writes_resume_file` (line 1435), `test_guillotine_without_run_dir_uses_summary_blob` (line 1489), `test_option_j_fresh_session_skips_option_e` (line 1571), `test_guillotine_with_sprint_context_injects_framing` (line 1639), `test_guillotine_run_dir_single_issue_scope_constraint` (line 1733)
  - Existing guard test to model after: `test_exits_cleanly_when_issue_already_done` (line 1177) tests CONTEXT_HANDOFF path — the new test mirrors this but simulates the Option J trigger (`on_usage(185_000, 10_000)` to push `usage_ratio ≥ 0.90`) instead of `detect_context_handoff=True`
- `scripts/tests/test_worker_pool.py` — class `TestRunWithContinuation` (line 2340); add parallel guard test using `patch.object(worker_pool, "_run_claude_command", ...)` pattern; existing Option J tests at lines 2435, 2481, 2538, 2593

### Documentation
- N/A — internal behavior change; no public API or user-facing docs affected

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — additive entry needed for BUG-2281 under the current version section (existing Option J entries at lines 102, 156, 391, 849; new entry is append-only) [Agent 2 finding]

### Configuration
- N/A

## Impact

- **Priority**: P2 — medium-high severity; converts a single spurious Option J trigger into a budget-draining unbounded respawn loop on already-complete issues
- **Effort**: Small — single guard insertion mirroring the existing `_check_issue_already_done` pattern from the CONTEXT_HANDOFF branch; no new utilities needed
- **Risk**: Low — adds a guard before existing spawn logic without changing the happy path; same proven check already used by CONTEXT_HANDOFF
- **Breaking Change**: No

## Related

- [[BUG-2280]] — the defective guillotine metric that keeps firing the trigger (primary
  root cause; this issue is the containment fix).
- [[BUG-1759]] — origin of `_check_issue_already_done`, currently only wired into the
  CONTEXT_HANDOFF path.
- [[BUG-2201]] — Option J continuation scope escape (same path, sibling hardening).

## Session Log
- `/ll:confidence-check` - 2026-06-25T01:10:00 - `60219707-55ed-4074-ac97-13cc49417dbb.jsonl`
- `/ll:wire-issue` - 2026-06-25T00:35:24 - `f3b734be-ae79-4eac-832f-68c245c56458.jsonl`
- `/ll:refine-issue` - 2026-06-25T00:27:50 - `5302a422-c0d1-420a-a9db-ea930a398524.jsonl`
- `/ll:format-issue` - 2026-06-25T00:18:09 - `f30048c9-359d-4c6d-8a70-303dad3df064.jsonl`
- `/ll:capture-issue` - 2026-06-24T23:53:24Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f09f2f70-372c-4009-b490-01dff83e4775.jsonl`

---

## Status

open
