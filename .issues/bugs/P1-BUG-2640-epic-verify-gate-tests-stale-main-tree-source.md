---
id: BUG-2640
type: BUG
priority: P1
status: open
captured_at: '2026-07-14T23:40:13Z'
discovered_date: 2026-07-14
discovered_by: capture-issue
relates_to:
- BUG-2614
---

# BUG-2640: Epic-branch verify gate tests stale main-tree source, not the branch's source

## Summary

The epic-branch merge verify gate (wired into the FSM `auto-refine-and-implement`
path by BUG-2614) runs `python -m pytest scripts/tests/` inside a throwaway
worktree checked out at the epic-branch head. Because `little_loops` is installed
editable (`pip install -e ./scripts`), `import little_loops` resolves to the
**absolute main-working-tree path** (`/…/little-loops/scripts/little_loops`), not
the worktree's source. So the gate collects the *branch's* new/modified tests but
exercises *main's* stale implementation — a guaranteed failure for any branch that
adds a CLI argument, function, or other importable API surface. The result is a
**false-negative merge block**: correct work is rejected and stranded on the epic
branch.

## Current Behavior

Confirmed empirically on run
`sprint-refine-and-implement-20260714T180411` (EPIC-2370 → FEAT-2337, "graph-aware
clusters tree layout"):

- The implementer added `--layout {tree,list,boxes}` to
  `scripts/little_loops/cli/issues/__init__.py` (line 463 on the epic branch),
  updated tests, and committed `6cc6f994` on
  `epic/epic-2370-ll-issues-clusters-ux-improvements`.
- The implementer's own suite run passed (14943 passed) — but **only** because it
  used `PYTHONPATH=scripts` to shadow the install with the worktree source (it even
  noted "the editable install points at the main repo").
- The merge verify gate ran the configured `test_cmd`
  (`python -m pytest scripts/tests/`) with **no** `PYTHONPATH` override. Result:
  9 failures, all `ll-issues: error: unrecognized arguments: --layout boxes`, exit 1
  → `verify_verdict: failed`, `epic_merge_verdict: verify_failed`.
- `6cc6f994` was left on the epic branch; never merged to `main`.

Reproduced independently by checking out `6cc6f994` into a fresh worktree and running
the configured `test_cmd`: same 9 failures. `git grep` confirms `--layout` exists in
the epic branch's `__init__.py` but not on `main`; `python -c "import little_loops"`
resolves to the main-tree path — proving the gate never imported the branch code.

## Expected Behavior

The verify gate should exercise the **epic branch's** source, not the main tree's.
Before running `test_cmd` in the verify worktree, it should either:
- prepend the worktree's package dir to `PYTHONPATH` (e.g. `PYTHONPATH=scripts`), or
- run an editable reinstall scoped to the worktree, or
- otherwise ensure `import little_loops` resolves to the worktree copy.

A branch whose tests genuinely pass against its own source must produce a green
verify and be eligible for merge.

## Root Cause

`pip install -e` records an absolute path to the main working tree; any process that
imports `little_loops` from a different worktree still loads the main-tree copy unless
the path is explicitly shadowed. The verify-gate invocation (the merge-back verify
step added for BUG-2614, mirroring `_verify_epic_branch_before_merge` /
`_merge_epic_branch_to_base` in `scripts/little_loops/parallel/orchestrator.py`) does
not shadow it. Locate the exact call site that runs `test_cmd` for the epic verify and
inject the worktree path there. Relates to the same editable-install path-pinning
class as BUG-2273 / BUG-885.

## Impact

Every epic-worktree run that touches `little_loops/` source (i.e. most feature/enh
work) is at risk of a spurious merge block. Correct, committed work silently fails to
land and requires manual diagnosis + override — which also erodes trust in the gate
and invites blanket overrides that would defeat BUG-2614's purpose.

## Proposed Solution

1. Find the verify-gate `test_cmd` invocation for the FSM epic-branch path (and the
   `ll-parallel` path if it shares the same gap).
2. Set `PYTHONPATH` (worktree package dir first) in that subprocess's env, or reinstall
   editable into the worktree before verify.
3. Add a regression test: a synthetic branch that adds an importable symbol + a test
   using it must produce a green verify from the gate (not just from a PYTHONPATH-hacked
   manual run).

## Implementation Steps

1. Grep for the epic verify call site (`verify_before_merge` / the `test_cmd` runner in
   the epic-merge path).
2. Thread a `PYTHONPATH=<worktree>/scripts` (or reinstall) into the verify subprocess env.
3. Confirm the `ll-parallel` worker-pool verify path has the same fix (or already differs).
4. Add the regression test described above.
5. Re-run the EPIC-2370 verify to confirm `6cc6f994` now passes and can merge.

## Acceptance Criteria

- [ ] The epic verify gate imports `little_loops` from the branch's worktree, not main.
- [ ] A branch adding a new CLI arg + passing test yields a green verify from the gate.
- [ ] Regression test added that would have caught this (fails before the fix).
- [ ] EPIC-2370's `6cc6f994` verifies green and is mergeable via the normal path.

## Integration Map

- `scripts/little_loops/parallel/orchestrator.py` — `_verify_epic_branch_before_merge`,
  `_merge_epic_branch_to_base` (~lines 1129–1388) — verify/merge logic.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `finalize` /
  epic-merge states that invoke the verify gate (BUG-2614 wiring).
- Config: `parallel.epic_branches.verify_before_merge`, `.merge_to_base_on_complete`.

## Session Log
- `/ll:capture-issue` - 2026-07-14T23:40:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bb11f3d4-9b5d-4067-814a-1a27441ae683.jsonl`

---

## Status

- **Status**: open
- **Priority**: P1
