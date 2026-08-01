---
id: BUG-2954
title: Non-FSM tamper guard baseline spans implement phase, false-positives on TDD-mode test edits
type: BUG
priority: P2
captured_at: "2026-08-01T00:26:29Z"
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to: [ENH-2854, ENH-2935, ENH-2933]
---

# BUG-2954: Non-FSM tamper guard baseline spans implement phase, false-positives on TDD-mode test edits

## Summary

`work_verification.py`'s non-FSM tamper guard (ENH-2935) rejects legitimate
test-file edits made during Phase 2 (implement) as "tampering" whenever an
issue's own required scope includes editing an *existing* test file. On a
`tdd_mode: true` project with the default `tamper_guard.policy: fail`, this
makes Phase 3 verification refuse to close any `ll-auto`/`ll-parallel`/
`ll-sprint`-driven issue that touches an existing test file — even when the
implementation is fully correct and all tests pass.

## Current Behavior

`issue_manager.py:921-926` captures `_baseline_sha` at the **start of Phase 2
(implement)** — before any code or tests are written — for an older, unrelated
purpose (detecting commits made since that point as evidence of work).
ENH-2935 reused this same `baseline_sha` as the tamper guard's "before"
snapshot reference (`work_verification.py:_run_non_fsm_tamper_guard`, via
`snapshot_test_paths_at_ref(repo_root, baseline_sha or "HEAD", ...)`). As a
result the guard's diff window spans the *entire implement+verify run*, not
just a dedicated verification step.

Observed failure: `ll-loop run autodev ENH-2937` — Phase 2 (`manage-issue`)
correctly implemented ENH-2937, including adding ~10 new tests to the
already-existing `scripts/tests/test_reconcile_issue_command.py` (in scope;
all 21 tests in that file passed). Phase 3 then logged:

```
Tamper guard (fail) failed: ['scripts/tests/test_reconcile_issue_command.py'] not resolved
REFUSING to mark ENH-2937 as completed: no code changes detected despite returncode 0
```

The second log line is also misleading: real changes existed
(`_detect_meaningful_changes` had already confirmed 5 changed files); the
tamper guard, not "no changes," is what vetoed the completion. The issue was
left `open` with uncommitted work, and autodev's finalize step reported it as
`inflight_at_finalize` / `unverified`, failing the run.

## Expected Behavior

The non-FSM tamper guard should be scoped to a dedicated verification step
(post-implementation), matching the FSM adapter's semantics and ENH-2854's
own design constraint:

> "Scope the guard to the verification step, not the whole issue run. With
> `commands.tdd_mode: true`, the implement phase legitimately writes tests
> before code. The snapshot is taken at verify-step start, never at issue
> start — otherwise every TDD run trips the guard."

Legitimate test-file edits made during Phase 2 implementation (required by
the issue's own scope, or written per `tdd_mode`) must not trip the guard.
Only edits made *after* implementation is complete — i.e., during the
verification step itself — should count as tamper candidates.

## Motivation

This silently blocks any TDD-mode `ll-auto`/`ll-parallel`/`ll-sprint`-driven
issue that legitimately requires editing an existing test file — the common
case for most feature/enhancement work, not an edge case. Every such run
burns a full implement cycle, then fails at the finalize step with a
misleading "no code changes detected" message, masking the true cause and
wasting the run's iteration budget diagnosing a phantom failure.

## Proposed Solution

Re-scope the non-FSM guard's "before" snapshot to the start of Phase 3
(verification) instead of the start of Phase 2 (implement):

- Capture a second reference point — e.g. `_verify_start_sha` or an
  in-memory `snapshot_test_paths(...)` call — immediately after Phase 2
  completes and before Phase 3's `verify_work_was_done()` call, and pass
  *that* through to `_run_non_fsm_tamper_guard` instead of the Phase-2-start
  `baseline_sha`.
- Keep `baseline_sha` (Phase-2-start) for its original, unrelated purpose in
  `_detect_meaningful_changes` (evidence-of-work detection) — do not conflate
  the two use cases again.
- Since the non-FSM path only observes on-disk state once, after the whole
  run already happened (per `snapshot_test_paths_at_ref`'s own docstring),
  the "before" for the tamper guard specifically needs to be taken right
  before Phase 3 begins, not at Phase 2's start — this likely requires
  snapshotting test-file content (not just a git ref) at the Phase 2/Phase 3
  boundary in `issue_manager.py` and `worker_pool.py`, then diffing that
  snapshot against on-disk state in `_run_non_fsm_tamper_guard`.
- Add a regression test asserting that a `tdd_mode: true` run which edits an
  *existing* test file as part of legitimate Phase 2 work does not trip the
  guard, alongside the existing coverage asserting a genuine post-implement
  test weakening still does.

## Integration Map

### Files to Modify
- `scripts/little_loops/work_verification.py` (`_run_non_fsm_tamper_guard`,
  `verify_work_was_done`) — accept and use a verify-step-start snapshot
  instead of `baseline_sha`.
- `scripts/little_loops/issue_manager.py` (~L918-1133, Phase 2/Phase 3
  boundary and Phase 3 call sites at ~L1072, ~L1109) — capture the new
  verify-step-start reference between Phase 2 and Phase 3.
- `scripts/little_loops/worker_pool.py` (~L596, `_verify_work_was_done` at
  ~L1212) — same boundary fix for `ll-parallel`/`ll-sprint`.
- `scripts/little_loops/test_tamper_guard.py` — may need a snapshot-based
  (not git-ref-based) "before" path if the fix uses an in-memory snapshot
  rather than a second git SHA.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/git_operations.py` (re-exports `verify_work_was_done`)
- `scripts/tests/test_subprocess_mocks.py` (patches `verify_work_was_done`
  via the `git_operations` re-export)

### Similar Patterns
- FSM adapter (`scripts/little_loops/fsm/executor.py`) already snapshots at
  guarded-state entry and compares at exit — same before/after shape, just
  scoped correctly by construction since it brackets a single state.

### Tests
- `scripts/tests/test_work_verification.py` —
  `TestVerifyWorkWasDoneBaselineSha` and the tamper-guard-specific tests
  added by ENH-2935 will need updating/extending for the new
  verify-step-start reference.
- `scripts/tests/test_issue_manager.py` — Phase 2/Phase 3 mocks
  (`mock_verify.assert_called_once_with(...)`) need updating for the new
  parameter.

### Documentation
- N/A

### Configuration
- N/A — no new config key; `tamper_guard.policy` semantics are unchanged,
  only the snapshot window.

## Implementation Steps

1. Add a mechanism to capture test-file state at the Phase 2/Phase 3
   boundary in `issue_manager.py` and `worker_pool.py` (in-memory snapshot
   or a fresh git ref, whichever fits `_run_non_fsm_tamper_guard`'s existing
   shape more cleanly).
2. Thread that reference through to `verify_work_was_done` /
   `_run_non_fsm_tamper_guard`, replacing `baseline_sha` for the tamper
   guard's own "before" comparison only.
3. Add regression tests: (a) a `tdd_mode`-style Phase 2 that edits an
   existing test file does not trip the guard; (b) a post-Phase-2 test edit
   still trips it under `fail` policy.
4. Run the full suite and confirm no regression in existing tamper-guard
   coverage from ENH-2933/ENH-2934/ENH-2935.

## Impact

- **Priority**: P2 - Silently blocks completion of any TDD-mode issue that
  legitimately edits an existing test file; affects the default
  configuration of every project using `ll-auto`/`ll-parallel`/`ll-sprint`
  with `tdd_mode: true` and no explicit `tamper_guard.policy` override.
- **Effort**: Medium - requires re-threading a new snapshot reference through
  two orchestrators (`issue_manager.py`, `worker_pool.py`) and the shared
  `work_verification.py` hook, plus test updates in the ENH-2935 coverage.
- **Risk**: Medium - touches the shared Phase 3 verification chokepoint used
  by all three orchestrators; must not weaken the guard's actual tamper
  detection (post-implementation test weakening) while fixing the false
  positive.
- **Breaking Change**: No

## Steps to Reproduce

1. Set `commands.tdd_mode: true` (or use a project where it's already set)
   and leave `tamper_guard.policy` unset (default `fail`).
2. Create/select an issue whose correct implementation requires adding or
   modifying test cases in an *existing* test file (not a brand-new file).
3. Run `ll-loop run autodev <ISSUE-ID>` (or `ll-auto`) and let it implement
   the issue correctly, including the test-file edit.
4. Observe Phase 3 verification log a `Tamper guard (fail) failed: [...]`
   line naming the legitimately-edited test file, followed by "REFUSING to
   mark ... as completed: no code changes detected despite returncode 0"
   even though real changes are present. The issue stays `open`/uncommitted
   and the run reports the issue as `inflight_at_finalize` / `unverified`.

## Root Cause

- **File**: `scripts/little_loops/work_verification.py`
- **Anchor**: in function `_run_non_fsm_tamper_guard()`, called from
  `verify_work_was_done()`
- **Cause**: The "before" snapshot for the tamper guard is reconstructed via
  `snapshot_test_paths_at_ref(repo_root, baseline_sha or "HEAD", ...)`, where
  `baseline_sha` (`issue_manager.py:921-926`) is captured at the *start of
  Phase 2 (implement)*, not at the start of a dedicated verification step.
  Any test-file edit made anywhere in Phase 2 — including fully legitimate,
  in-scope, TDD-mode test writes — therefore reads as a "modified"/"added"
  tamper finding, and the default `fail` policy rejects the transition
  regardless of whether the edit was legitimate implementation work or
  actual test weakening.

## Error Messages

```
Tamper guard (fail) failed: ['scripts/tests/test_reconcile_issue_command.py'] not resolved
REFUSING to mark ENH-2937 as completed: no code changes detected despite returncode 0
```

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-08-01T00:26:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6fbac205-468a-44ce-b7fb-4626b0ac42e4.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P2
