---
id: FEAT-2083
title: Add skip-and-return scheduling mode to ll-sprint and ll-auto
type: FEAT
priority: P3
status: cancelled
captured_at: '2026-06-10T18:12:09Z'
discovered_date: '2026-06-10'
discovered_by: capture-issue
relates_to:
- EPIC-2087
confidence_score: 86
outcome_confidence: 83
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 21
score_change_surface: 22
decision_needed: true
---

# FEAT-2083: Add skip-and-return scheduling mode to ll-sprint and ll-auto

## Summary

Add a `--skip-on-block` flag to `ll-sprint` and `ll-auto` that enables runtime deferral of blocked or unexpectedly complex issues. When triggered, blocked issues are pushed to a persistent deferred queue while the sprint continues with unblocked work; the deferred set is retried automatically after the initial pass completes.

## Current Behavior

`ll-sprint` and `ll-auto` process issues in fixed priority order. When a session encounters a blocked or unexpectedly complex issue mid-sprint, there is no mechanism to defer it and proceed — the sprint either fails or halts at that issue.

## Expected Behavior

With `--skip-on-block`, `ll-sprint` and `ll-auto` dynamically defer blocked issues and continue with the next unblocked issue in the queue. After all initially-unblocked issues complete, the deferred set is retried automatically. Skip/return events appear in the sprint summary.

## Motivation

Sprint and auto processing currently run issues in fixed priority order. Strong agents skip hard problems and return after building supporting infrastructure — a dynamic deferral strategy that improves throughput. When a Claude session encounters a blocked or unexpectedly complex issue mid-sprint, there is no mechanism to defer it and proceed to unblocked work.

## Use Case

During a sprint, an issue blocks because a dependency isn't merged. Rather than failing the sprint or halting, `ll-sprint --skip-on-block` defers the blocked issue and continues processing the next unblocked issues. After all unblocked issues complete, the deferred set is retried automatically.

## Proposed Solution

Add a `--skip-on-block` flag to `ll-sprint` and `ll-auto` that enables runtime deferral:
- If a session emits a `BLOCKED` signal or exceeds a per-issue iteration ceiling, push the issue to a deferred queue
- Continue with the next unblocked issue in the sprint
- Retry deferred issues after all initially-unblocked issues complete
- Persist the deferred queue so it survives interruptions
- Log skip/return events in the sprint summary

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`BLOCKED` signal is already wired end-to-end**: `output_parsing.py:parse_ready_issue_output()` already includes `"BLOCKED"` in `VALID_VERDICTS` and sets `is_blocked=True`; `issue_manager.py:process_issue_inplace()` returns `IssueProcessingResult(was_blocked=True)`. No changes to signal detection are needed.

**`SprintState.skipped_blocked_issues` already exists**: `sprint.py:SprintState` has a `skipped_blocked_issues: dict[str, str]` field. `cli/sprint/run.py:_cmd_sprint_run()` already populates it on `was_blocked` results — the missing piece is the post-wave retry pass gated on `--skip-on-block`.

**Per-issue iteration ceiling already exists for sprint**: `cli/sprint/run.py:_run_issue_with_wall_clock_timeout()` enforces `SprintsConfig.max_issue_wall_clock_time` (default 2700s) via `SIGALRM`. A `WALL_CLOCK_TIMEOUT` result can be treated as a deferral trigger alongside `BLOCKED`. `ll-auto` has no equivalent per-issue ceiling today.

**`run_dir` does not exist for sprint/auto**: The `${run_dir}/deferred.json` path from the original proposal is a `ll-loop`-only convention (`cli/loop/run.py` ~lines 154–163). Sprint uses `.sprint-state.json` at `cwd`; auto uses `.ll/ll-state.json` via `StateManager`. The deferred queue must integrate with these existing state files.

**`AutoManager` in `issue_manager.py` is missing from Files to Modify**: `AutoManager._process_issue()` calls `mark_attempted()` before processing, so blocked issues land permanently in `attempted_issues` and are never retried. `AutoManager.run()` needs a deferred retry loop added at the end when `--skip-on-block` is active.

### Option A: Extend Existing State Objects (Recommended)

- **Sprint**: `SprintState.skipped_blocked_issues` (already populated) serves as the deferred queue. After the `for wave_num, wave in enumerate(waves)` loop, add a retry pass that calls `process_issue_inplace()` for each entry when `--skip-on-block` is active — mirror the existing parallel-failure retry at `run.py` lines ~547–587. Deferred queue persists via `.sprint-state.json`.
- **Auto**: Add `deferred_issues: dict[str, str]` to `ProcessingState` in `state.py`. In `AutoManager._process_issue()`, when `result.was_blocked` and `skip_on_block` is set, store in `deferred_issues` instead of leaving the issue in `attempted_issues`. After the initial scan loop in `AutoManager.run()`, iterate `deferred_issues` for a retry pass. Deferred queue persists via `.ll/ll-state.json`.
- **Tradeoff**: Minimal new infrastructure; leverages existing persistence and `SprintState` fields. Requires extending `ProcessingState` with one new field and adding a retry loop to `AutoManager.run()`.

### Option B: Introduce Per-Run `deferred.json` File

- Create a timestamped run directory for sprint and auto (e.g., `.ll/sprint-runs/<sprint>-<timestamp>/`), following the `ll-loop` `run_dir` convention from `cli/loop/run.py` (~lines 154–163 and ~414–415).
- Write a standalone `deferred.json` inside that directory; do not extend existing state objects.
- **Tradeoff**: Cleaner per-run isolation and auditability; aligns with FSM run-dir convention. Requires introducing `run_dir` infrastructure that does not currently exist for sprint/auto — significantly more new code than Option A.

## Implementation Steps

1. **Add `add_skip_on_block_arg()` to `cli_args.py`** — follow the `add_skip_arg()` pattern (~line 85); add to `add_common_auto_args()` for `ll-auto`; add to the `run` subparser in `cli/sprint/__init__.py` for `ll-sprint`
2. **No signal detection changes needed** — `output_parsing.py:parse_ready_issue_output()` already recognizes `BLOCKED` in `VALID_VERDICTS` and `process_issue_inplace()` already returns `IssueProcessingResult(was_blocked=True)`
3. **Extend persistence for `ll-auto`** (Option A) — add `deferred_issues: dict[str, str]` to `ProcessingState` in `state.py`; update `to_dict()` / `from_dict()` round-trips; add `mark_deferred()` method to `StateManager`
4. **Modify `AutoManager` in `issue_manager.py`** — in `_process_issue()`, when `result.was_blocked` and `skip_on_block` is active, call `mark_deferred()` instead of leaving in `attempted_issues`; in `run()`, add a retry loop over `state.deferred_issues` after the initial scan exhausts candidates
5. **Add post-wave retry pass in `cli/sprint/run.py`** — after the `for wave_num, wave in enumerate(waves)` loop, when `--skip-on-block` is active and `state.skipped_blocked_issues` is non-empty, iterate deferred issues and call `process_issue_inplace()` for each; follow the existing retry pattern at `_cmd_sprint_run()` lines ~547–587
6. **Log skip/return events** — add deferred count to sprint summary (mirror `blocked_msg` variable pattern in `_cmd_sprint_run()`); log retry pass start/end for `ll-auto`
7. **Tests** — unit tests in `test_sprint.py` (`SprintState` deferred round-trip), `test_issue_manager.py` (`AutoManager` deferred retry), `test_cli_sprint.py` (flag dispatch via `main_sprint()`), `test_cli_args.py` (`add_skip_on_block_arg()`); integration test in `test_sprint_integration.py`
8. **Verify**: `python -m pytest scripts/tests/test_sprint.py scripts/tests/test_issue_manager.py scripts/tests/test_cli_sprint.py scripts/tests/test_cli_args.py -v`

## Acceptance Criteria

- [ ] `ll-sprint --skip-on-block` defers blocked issues and continues with unblocked ones
- [ ] `ll-auto --skip-on-block` applies the same deferral behavior
- [ ] Deferred queue persists via existing state files (sprint: `.sprint-state.json` via `SprintState.skipped_blocked_issues`; auto: `.ll/ll-state.json` via new `ProcessingState.deferred_issues` field)
- [ ] Deferred issues are retried after initial pass completes
- [ ] Sprint summary includes skip/return event log

## API/Interface

New CLI flag added to `ll-sprint` and `ll-auto`:

```
ll-sprint [OPTIONS] [--skip-on-block]
ll-auto [OPTIONS] [--skip-on-block]
```

- `--skip-on-block`: Enable runtime deferral of blocked/ceiling-exceeded issues; deferred queue is persisted via existing state files (`.sprint-state.json` for sprint, `.ll/ll-state.json` for auto)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli_args.py` — add `add_skip_on_block_arg()` function following `add_skip_arg()` pattern; call from `add_common_auto_args()` for `ll-auto`
- `scripts/little_loops/cli/sprint/__init__.py` — register `--skip-on-block` on the `run` subparser alongside existing `--skip`, `--only`, `--type` flags
- `scripts/little_loops/cli/auto.py` — receive `--skip-on-block` from `add_common_auto_args()`; pass `skip_on_block=args.skip_on_block` to `AutoManager`
- `scripts/little_loops/cli/sprint/run.py` — gate `skipped_blocked_issues` retry pass on `--skip-on-block` in `_cmd_sprint_run()`; add retry loop following lines ~547–587 pattern
- `scripts/little_loops/issue_manager.py` — modify `AutoManager._process_issue()` to call `mark_deferred()` when `was_blocked` and `skip_on_block`; add deferred retry loop to `AutoManager.run()`
- `scripts/little_loops/state.py` — add `deferred_issues: dict[str, str]` field to `ProcessingState`; add `mark_deferred()` to `StateManager`; update `to_dict()` / `from_dict()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py` — imports `main_auto()` and `main_sprint()`; no changes needed

### Similar Patterns
- `scripts/little_loops/parallel/orchestrator.py` — `ParallelOrchestrator._deferred_issues: list[IssueInfo]` and `_requeue_deferred_issues()`: the canonical defer-and-requeue pattern to model the sprint retry pass after
- `scripts/little_loops/cli/sprint/run.py` (~lines 547–587) — existing sequential retry-after-parallel-failure loop in `_cmd_sprint_run()`: reuse this structure for the deferred-blocked retry pass
- `scripts/little_loops/sprint.py` — `SprintState.skipped_blocked_issues: dict[str, str]` already exists and is populated; retry pass just needs to be wired on `--skip-on-block`
- `scripts/little_loops/cli_args.py` — `add_skip_arg()` (~line 85): exact pattern for the new `add_skip_on_block_arg()` function
- `scripts/little_loops/state.py` — `ProcessingState` / `StateManager` with atomic `os.replace` writes: persistence pattern to follow for `deferred_issues` field

### Tests
- `scripts/tests/test_sprint.py` — add `SprintState.skipped_blocked_issues` deferred round-trip tests
- `scripts/tests/test_sprint_integration.py` — add integration test for `--skip-on-block` skip-and-retry flow
- `scripts/tests/test_cli_sprint_commands.py` — add `--skip-on-block` flag routing test
- `scripts/tests/test_cli_sprint.py` — add dispatch test: `ll-sprint run --skip-on-block` routes to `_cmd_sprint_run()` with flag set
- `scripts/tests/test_issue_manager.py` — add `AutoManager.run()` deferred-retry unit tests
- `scripts/tests/test_cli_args.py` — add `add_skip_on_block_arg()` unit test following `TestParseIssueIds` pattern

### Documentation
- `docs/reference/CLI.md` — add `--skip-on-block` to `ll-sprint run` and `ll-auto` flag tables
- `.claude/CLAUDE.md` — update `ll-sprint` and `ll-auto` CLI descriptions to mention skip-and-return mode

### Configuration
- N/A — flag is CLI-only; no config file changes needed

## Impact

- **Priority**: P3 — Quality-of-life improvement for sprint throughput; sprints can still complete without this
- **Effort**: Medium — Signal detection, queue persistence, and retry logic across two CLI entry points
- **Risk**: Low — Additive flag; existing behavior is fully unchanged when flag is omitted
- **Breaking Change**: No

## Labels

`scheduling`, `sprint`, `automation`, `ll-sprint`, `ll-auto`, `captured`

## Status

**Open** | Created: 2026-06-10 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-15_

**Readiness Score**: 76/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 78/100 → MODERATE

### Concerns
- `AutoManager.run()` (in `issue_manager.py`) likely needs deferral-queue threading to support `--skip-on-block` in `ll-auto`, but `issue_manager.py` is absent from the Integration Map's Files to Modify.
- "Per-issue iteration ceiling" is mentioned as a skip trigger but no counter mechanism or threshold is defined in the implementation steps or acceptance criteria.
- The `${run_dir}/deferred.json` persistence target uses a `run_dir` convention that exists for loops but is not currently established for `ll-sprint` — sprint currently uses `.sprint-state.json` at the project root; alignment between these two persistence approaches needs a decision.
- `Dependent Files` and `Similar Patterns` both have TBD entries; caller enumeration and existing queue patterns are unresearched.

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-06-15_ — **NO-GO (SKIP)**

**Deciding Factor**: Active P2 deprecation of `AutoManager` (FEAT-2001/FEAT-2002, both open and unblocked) makes implementing the ll-auto side strategically throwaway; the correct sequencing is to wait until the FSM migration lands and implement skip-and-return natively in the loop DSL, where defer-and-requeue is already first-class.

### Key Arguments For
- Blocked-issue signal pipeline is already 80% complete: `output_parsing.py` emits `is_blocked=True`, `issue_manager.py` returns `IssueProcessingResult(was_blocked=True)`, `SprintState.skipped_blocked_issues` captures it — only the retry loop is missing
- The parallel orchestrator already proves the pattern in production via `ParallelOrchestrator._deferred_issues` + `_requeue_deferred_issues()` (`parallel/orchestrator.py` lines 127–128, 1001–1019)

### Key Arguments Against
- FEAT-2001 (P2, open) adds a `DeprecationWarning` to `AutoManager.run()`; FEAT-2002 (P2, open) removes it from docs entirely — every line added to `AutoManager` under this issue is on a countdown timer
- `AutoManager._process_issue()` line 1333 calls `mark_attempted()` *before* processing, permanently excluding blocked issues from re-entering the queue; fixing this requires rewriting the infinite-loop guard against ~3,448 lines of `test_issue_manager.py`
- FEAT-1899 (ll-sprint FSM wave driver) will substantially rewrite `_cmd_sprint_run()` — any retry pass bolted onto the current imperative loop must be re-ported

### Rationale
The detection infrastructure is largely in place, but FEAT-2001/FEAT-2002 (both P2, open, unblocked) explicitly target `AutoManager.run()` for deprecation — making the ll-auto half of this feature immediately throwaway. The sprint side faces the same timing risk from FEAT-1899. The correct sequencing is to implement skip-and-return after the FSM migration lands, where the defer-and-requeue pattern is already natively supported.

## Session Log
- `/ll:ready-issue` - 2026-06-15T18:19:58 - `ee86154c-9df4-437c-81ee-4e4135663db8.jsonl`
- `/ll:refine-issue` - 2026-06-15T18:11:11 - `90d21ee2-6a15-4d41-85b3-bed641ff48d8.jsonl`
- `/ll:format-issue` - 2026-06-15T17:55:05 - `cce508de-9bd4-4547-8344-cb7414b4c24f.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `f2f9e529-e125-467e-97c0-8cd3031b1b3e.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `cc45e4aa-b977-42a3-9a6b-06d1dfd180d2.jsonl`
