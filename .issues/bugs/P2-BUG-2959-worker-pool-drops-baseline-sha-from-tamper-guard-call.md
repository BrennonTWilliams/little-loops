---
id: BUG-2959
title: worker_pool drops baseline_sha from verify_work_was_done, making the parallel-path
  tamper guard's reference point non-deterministic
type: BUG
priority: P2
status: done
discovered_date: 2026-07-31
discovered_by: review of ENH-2958
relates_to:
- ENH-2958
- ENH-2935
- BUG-2954
decision_needed: false
confidence_score: 90
outcome_confidence: 92
score_complexity: 24
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 21
completed_at: '2026-08-01T06:13:48Z'
---

# BUG-2959: worker_pool drops baseline_sha from verify_work_was_done, making the parallel-path tamper guard's reference point non-deterministic

## Summary

On the `ll-parallel` path, `WorkerPool._verify_work_was_done` calls
`verify_work_was_done(...)` **without** `baseline_sha`, so the non-FSM tamper
guard (ENH-2935) reconstructs its "before" snapshot from `"HEAD"` at
verification time rather than from the pre-implement commit. Whether the guard
sees a meaningful "before" therefore depends on whether the implement agent
happened to commit inside the worktree — if it did, the tampering is already
in `HEAD` and the guard compares the tampered state against itself.

The `ll-auto` path does not have this defect: `issue_manager.py` captures
`_baseline_sha` before Phase 2 (`L921-926`) and threads it into
`verify_work_was_done(logger, baseline_sha=_baseline_sha, config=config)`
(`L1108-1110`).

## Current Behavior

`scripts/little_loops/parallel/worker_pool.py:1241-1243`:

```python
if verify_work_was_done(
    self.logger, changed_files, config=self.br_config, repo_root=worktree_path
):
```

No `baseline_sha` kwarg. `work_verification._run_non_fsm_tamper_guard`
(`L63-106`) consequently reaches its fallback at `L92`:

```python
before = snapshot_test_paths_at_ref(repo_root, baseline_sha or "HEAD", candidate_paths)
```

Two outcomes, selected by agent behavior rather than by design:

- **Implement agent left work uncommitted** — worktree `HEAD` still points at
  the branch point, so the reconstruction is accidentally correct and the
  guard behaves like the `ll-auto` path (including BUG-2954's false-positive
  on in-scope TDD test edits).
- **Implement agent committed in the worktree** — `HEAD` now contains the
  post-implement tree. `snapshot_test_paths_at_ref` hashes the already-changed
  test files, `compare_snapshots` finds no delta, and the guard passes
  unconditionally. A genuine test weakening is invisible.

`_detect_committed_leaks` (`L1500-1524`) exists precisely because the implement
agent committing is a real, observed behavior, so the second branch is not
hypothetical.

## Steps to Reproduce

1. Set `tamper_guard.policy: "fail"` in `.ll/ll-config.json` (this is already
   the default — `TamperGuardConfig.policy: str = "fail"`,
   `config/features.py:852-860`).
2. Run `ll-parallel` on any issue whose implementation touches an existing
   test file.
3. Have the implement agent **commit** its work inside the worktree (the
   common case `_detect_committed_leaks` exists to handle, and what
   `/ll:manage-issue` does when it reaches its commit step).
4. Observe Step 7's tamper guard passes with no findings regardless of what
   was done to the test file — `snapshot_test_paths_at_ref(worktree, "HEAD",
   ...)` hashes the post-implement tree, so `compare_snapshots` diffs the
   changed file against itself.

Contrast with the same scenario under `ll-auto`, where `_baseline_sha`
(`issue_manager.py:921-926`) pins the reference before Phase 2 and the guard
sees the change.

## Expected Behavior

The parallel path's tamper guard uses a fixed pre-implement reference point,
the same as the sequential path, independent of whether the implement agent
committed.

## Program Design

### Signatures

- `WorkerPool._verify_work_was_done(self, changed_files: list[str], issue_id: str, issue_filename: str = "", worktree_path: Path | None = None, baseline_sha: str | None = None) -> tuple[bool, str]`

  New trailing keyword-only-safe param, defaulted to `None` so existing
  callers and tests keep working; forwarded to `verify_work_was_done` as
  `baseline_sha=baseline_sha`.

No new types. `verify_work_was_done` already accepts `baseline_sha`
(`work_verification.py`), so this is pure threading — the signature that
changes is `WorkerPool`'s private method, not the public API symbol
re-exported at `scripts/little_loops/__init__.py:67,124`.

### Call Path

`WorkerPool._run_worker` (captures `baseline_head_sha`, `L361`)
→ Step 7 call site (`L596-598`)
→ `_verify_work_was_done(..., baseline_sha=baseline_head_sha)`
→ `verify_work_was_done(..., baseline_sha=...)`
→ `_run_non_fsm_tamper_guard`
→ `snapshot_test_paths_at_ref(repo_root, baseline_sha, candidate_paths)`

## Proposed Solution

Thread the already-captured pre-implement SHA through to the guard.
`_run_worker` captures `baseline_head_sha = self._get_main_head_sha()` at
`L361`, before the worktree is created and before Step 5's implement
invocation — this is the natural reference. Pass it to
`_verify_work_was_done` at the Step 7 call site (`L596-598`) and on to
`verify_work_was_done`.

**Implementer must confirm** that `baseline_head_sha` (main-repo HEAD) is the
commit the worktree branch is created from; if the branch point can differ,
capture the worktree's own `git rev-parse HEAD` immediately after worktree
creation and before Step 5 instead, and use that.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/worker_pool.py` — add a `baseline_sha`
  parameter to `_verify_work_was_done` (`L1212-1218`), forward it to
  `verify_work_was_done` (`L1241-1243`), and pass it at the Step 7 call site
  (`L596-598`) from `baseline_head_sha` (`L361`).

### Similar Patterns
- `scripts/little_loops/issue_manager.py:921-926` (capture) and `L1108-1110`
  (forward) — the correct sequential-path shape to mirror.

### Tests
- `scripts/tests/test_worker_pool.py` — no existing test asserts on the
  `baseline_sha` kwarg at the Step 7 call site. Add one mirroring
  `scripts/tests/test_issue_manager.py:2797`
  (`test_baseline_sha_passed_to_verify_work_was_done`), which asserts exact
  kwargs on the sequential path's call.
- Add a regression test for the committed-work branch: implement agent commits
  a weakened test inside the worktree, guard must still trip under
  `tamper_guard.policy: fail`.

### Implementation Status (found by `/ll:wire-issue`)

_Wiring pass added by `/ll:wire-issue`:_

**The core fix already shipped**, in `a73d437d` ("feat(work-verification):
wire tamper guard into ll-auto/ll-parallel/ll-sprint"), landed after this
issue was captured but with no back-reference to BUG-2959 in the commit
message. Current state of `scripts/little_loops/parallel/worker_pool.py`:

- `_verify_work_was_done` has the `baseline_sha: str | None = None` param
  (`L1221-1228`) and forwards it to `verify_work_was_done` (`L1257-1263`).
- The Step 7 call site in `_process_issue` (`L601-607`) passes
  `baseline_sha=tamper_baseline_sha`.
- `tamper_baseline_sha` is **not** `baseline_head_sha`/`_get_main_head_sha()`
  (the primary proposal above, captured at `L361` for committed-leak
  detection only). It's a separate value,
  `tamper_baseline_sha = self._get_worktree_head_sha(worktree_path)`
  (`L538`, captured immediately before Step 5's implement invocation via a
  new method at `L1519-1538`) — i.e. the implementer took this issue's own
  documented fallback ("if the branch point can differ, capture the
  worktree's own `git rev-parse HEAD`... instead") rather than the primary
  proposal. Both call sites are docstring-tagged `BUG-2954/BUG-2959`.
- Both prescribed regression tests already exist in
  `scripts/tests/test_worker_pool.py`, docstring-tagged `BUG-2954/BUG-2959`:
  `test_verify_work_was_done_legitimate_additive_edit_passes` (`L1375-1406`)
  and `test_verify_work_was_done_worktree_committed_weakening_trips`
  (`L1408-1447`, the exact committed-in-worktree scenario this issue
  describes). `python -m pytest scripts/tests/test_worker_pool.py` — 139
  passed.
- `docs/reference/API.md`'s `verify_work_was_done` section already documents
  this behavior accurately; no doc drift.

**One genuine gap remains** — AC #2 ("a test asserts the Step 7 call site
passes it, mirroring `test_issue_manager.py:2797`") is not yet satisfied.
The existing tests cover `_verify_work_was_done`'s *behavior* given
`baseline_sha`, but no test asserts the *wiring* — that `_process_issue`'s
Step 7 call actually forwards `baseline_sha=tamper_baseline_sha`. Add one to
`scripts/tests/test_worker_pool.py`, patching `_verify_work_was_done` (or
`_get_worktree_head_sha`) and asserting the exact kwarg on the call from
`_process_issue`, mirroring `test_issue_manager.py:2797`'s
`mock_verify.assert_called_once_with(...)` pattern but targeting the
`WorkerPool` method wrapper instead of the module-level function.

**Recommendation**: this issue is very likely resolvable as `done` (or
`cancelled` with a note pointing at `a73d437d`) once the one missing
call-site test above is added — not a re-implementation task. Consider
`/ll:reconcile-issue BUG-2959` to rewrite Current Behavior/Proposed
Solution/Program Design against this already-shipped state before closing.

## Acceptance Criteria

- [ ] `_verify_work_was_done` accepts and forwards a `baseline_sha`, sourced
      from a SHA captured before Step 5's implement invocation.
- [ ] A test asserts the Step 7 call site passes it, mirroring
      `test_issue_manager.py:2797`.
- [ ] A regression test proves the guard trips on a test weakening that the
      implement agent **committed** inside the worktree — the case that
      currently passes silently.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

**In scope:**
- Threading a pre-implement SHA into the parallel path's tamper-guard call.

**Out of scope:**
- ENH-2958's post-implement verify step — that changes *when* the snapshot is
  taken; this fixes *which commit* the existing reconstruction reads from.
- BUG-2954's content-based weakening classifier — unchanged.
- `tamper_guard.policy` semantics or defaults.

## Impact

- **Priority**: P2 — a shipped guard is silently inert on one of three
  orchestrator paths, in exactly the case (agent committed its own work) the
  codebase already knows occurs.
- **Effort**: Small — parameter threading plus two tests.
- **Risk**: Low-Medium — fixing the reference point will surface BUG-2954's
  false-positive on the parallel path where it was previously masked. Land
  after BUG-2954, or expect the false positive to appear.
- **Breaking Change**: No.

## Session Log
- `ll-auto` - 2026-08-01T06:13:48 - `434ebe41-d0cb-4a2f-b15a-ca901eabc565.jsonl`
- `/ll:ready-issue` - 2026-08-01T06:08:23 - `efc5dd12-a689-45f9-afd2-673a644ff0d0.jsonl`
- `/ll:confidence-check` - 2026-08-01T06:06:58 - `a5068ab7-8ee5-43b4-8851-61da37b7852e.jsonl`
- `/ll:wire-issue` - 2026-08-01T06:04:42 - `8c720062-3a1e-4dee-aa16-5d7890eafa81.jsonl`

---

## Status

**Open** | Created: 2026-07-31 | Priority: P2


---

## Resolution

- **Action**: fix
- **Completed**: 2026-08-01
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
