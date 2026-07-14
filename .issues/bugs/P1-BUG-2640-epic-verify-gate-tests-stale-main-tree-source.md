---
id: BUG-2640
type: BUG
priority: P1
status: done
captured_at: '2026-07-14T23:40:13Z'
discovered_date: 2026-07-14
discovered_by: capture-issue
relates_to:
- BUG-2614
- BUG-2629
decision_needed: false
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
completed_at: '2026-07-14T23:55:20Z'
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

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**The exact fix this issue proposes is already implemented on `main` (BUG-2629).**
BUG-2629 (`done`, completed 2026-07-13T19:07:22Z, commit `243a29de` "fix(worktree):
isolate verify-gate PYTHONPATH from editable-install .pth shadowing") added a
keyword-only `src_dir` parameter to `verify_epic_branch_before_merge` and injects
`PYTHONPATH=<worktree>/<src_dir>` exactly as this issue's Proposed Solution asks.
Crucially, `243a29de` is a **first-parent ancestor of the current `main` HEAD and
landed a full day before the failing run this issue cites** (`sprint-refine-and-implement-20260714T180411`,
2026-07-14T18:04) — so the fix was already in place when that run reportedly failed.

- **Shadow logic**: `scripts/little_loops/worktree_utils.py` — `verify_epic_branch_before_merge()`
  lines 323–331 build `env = os.environ.copy(); env["PYTHONPATH"] = <worktree>/<src_dir>:...`
  (guarded by `if src_dir:`); the `subprocess.run(..., cwd=worktree_path, env=env)`
  at lines 338–344 runs `test_cmd`/`lint_cmd` under it. `.pth` entries land on
  `sys.path` *after* `PYTHONPATH`, so the prepend wins.
- **All three call sites already forward `src_dir`** (the issue's Integration Map asks
  to check exactly these):
  - `scripts/little_loops/parallel/orchestrator.py:1346` (`_verify_epic_branch_before_merge`) → `src_dir=project.src_dir`
  - `scripts/little_loops/loops/auto-refine-and-implement.yaml:439` (`verify` state) → `src_dir=ll_cfg.project.src_dir`
  - `scripts/little_loops/loops/auto-refine-and-implement.yaml:630` (`merge_epic_branch` state) → `src_dir=cfg.project.src_dir`
- **`ll-parallel` has no separate gap**: the worker-pool path routes epic-merge verify
  through the same `ParallelOrchestrator._verify_epic_branch_before_merge` →
  `verify_epic_branch_before_merge`. `worker_pool.py`'s only verify-adjacent subprocess
  (`_run_per_worktree_proof_first_gate`, ~line 112) is the unrelated proof-first
  learning-gate, not `test_cmd`.
- **Regression tests already exist**: `scripts/tests/test_worktree_utils.py:361`
  (`test_src_dir_prepends_worktree_source_onto_pythonpath`) and `:393`
  (`test_falsy_src_dir_leaves_pythonpath_uninjected`), plus
  `scripts/tests/test_builtin_loops.py:2139/2164`
  (`test_verify_attaches_epic_worktree`, `test_merge_epic_branch_forwards_src_dir`).
  This issue's AC #3 ("regression test that would have caught this — fails before the
  fix") is therefore already satisfied by BUG-2629.
- **Trailing-slash `src_dir` ruled out**: this repo's `.ll/ll-config.json` sets
  `src_dir: "scripts/"` (trailing slash) while the BUG-2629 test uses `"scripts"`.
  Verified empirically that `str(Path("/wt") / "scripts/") == "/wt/scripts"` — pathlib
  normalizes the trailing slash away, so the PYTHONPATH entry is identical either way.
  This is **not** the cause of the reported failure.
- **Root-cause cross-reference correction**: this issue's Root Cause cites BUG-2273 /
  BUG-885 as the sibling class, but those are `__file__`-traversal bugs in
  `templates/`/`loops/` package-data resolution — unrelated. The actual direct sibling
  (same editable-install `.pth` shadowing mechanism, same fix) is **BUG-2629**.

### Implication — this is a decision point, not a straightforward fix

Since the proposed remedy is already merged and tested, "implement the fix" is a no-op.
The open question is **why the cited run still failed despite the fix being present**:

> **Selected:** Option A — Close as already-fixed (duplicate of BUG-2629); empirically
> confirmed 2026-07-14 by `/ll:decide-issue`.

**Option A — Close as already-fixed (duplicate of BUG-2629)**: The most likely
explanation is that run `sprint-refine-and-implement-20260714T180411` executed a
**stale code snapshot** — an older installed/loaded `little_loops` (or a loop launched
from an epic worktree whose source predated `243a29de`) — so the fix was present on
`main` but not in the interpreter that ran verify. Confirm by re-running EPIC-2370's
verify gate against **current** `main` (this issue's AC #4): check out `6cc6f994` into
a fresh worktree and run `verify_epic_branch_before_merge` (or re-trigger the merge
state). If it now yields a green verdict, close BUG-2640 as a duplicate of BUG-2629 —
no code change needed.

**Option B — Re-diagnose a residual, uncovered edge**: If the EPIC-2370 re-verify
*still* fails with the fix confirmed present in the running interpreter, then BUG-2629's
shadow does not cover this run's shape. In that case the real work is to capture the
*actual* divergent path (e.g. a second import route that bypasses `PYTHONPATH`, a
`sys.path` entry that precedes it, or the loop importing `worktree_utils` from a stale
worktree copy) — **not** re-adding the PYTHONPATH prepend that already exists. Rewrite
the Root Cause / Proposed Solution around the concrete evidence from the re-verify.

**Recommended**: Option A — verify empirically first (cheap, ~1 worktree + one suite
run) before assuming a new defect. Do this before any code change; the evidence in
this issue was gathered from a single run and has not been reproduced against current
`main`.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-14.

**Selected**: Option A — Close as already-fixed (duplicate of BUG-2629)

**Reasoning**: Empirically reproduced: created a fresh worktree at `6cc6f994`
(EPIC-2370's commit), confirmed `import little_loops` resolves to the main-tree path
with no `PYTHONPATH` override (reproducing the reported failure), then re-ran with
`PYTHONPATH=<worktree>/scripts` — the same shadow `verify_epic_branch_before_merge`
already applies per BUG-2629 (`243a29de`) — and all 126 layout-related tests passed
against the worktree's own source. This confirms BUG-2629's fix is sufficient and the
cited failing run (`sprint-refine-and-implement-20260714T180411`) ran under a stale or
unshadowed interpreter rather than exposing a residual gap; Option B's hypothesis of an
uncovered edge case is not supported by evidence.

#### Scoring Summary

| Option | Evidence |
|--------|----------|
| A — already-fixed (duplicate of BUG-2629) | Confirmed: fresh worktree + PYTHONPATH shadow → 126 passed |
| B — residual uncovered edge | Not observed; no divergent import path found |

**Key evidence**:
- Option A: `python -c "import little_loops"` in the worktree resolves to
  `/Users/brennon/AIProjects/brenentech/little-loops/scripts/little_loops/__init__.py`
  without shadowing (reproducing the bug), but resolves to the worktree copy and all
  126 tests pass once `PYTHONPATH=<worktree>/scripts` is set — exactly the shadow
  `verify_epic_branch_before_merge` (BUG-2629, `worktree_utils.py:323-331`) applies.
- Option B: no evidence of a second import route bypassing `PYTHONPATH`; not pursued
  further since Option A fully explains the observed failure.

## Session Log
- `/ll:ready-issue` - 2026-07-14T23:55:01 - `0b54d7c5-5d29-4be3-9d7c-53a639bc174b.jsonl`
- `/ll:decide-issue` - 2026-07-14T23:52:58 - `dd0bf591-013a-48d9-ba0b-7073139dd9dc.jsonl`
- `/ll:refine-issue` - 2026-07-14T23:50:20 - `cd63ebe6-719a-42d0-8a76-6e355d61271c.jsonl`
- `/ll:capture-issue` - 2026-07-14T23:40:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bb11f3d4-9b5d-4067-814a-1a27441ae683.jsonl`

---

## Status

- **Status**: done
- **Priority**: P1

### Closure

- **Reason**: already_fixed (duplicate of BUG-2629)
- **Closed by**: `/ll:ready-issue` on 2026-07-14
- **Evidence**: The proposed fix (inject `PYTHONPATH=<worktree>/<src_dir>` before running
  `test_cmd` in the verify gate) was already implemented on `main` by BUG-2629 (`done`),
  commit `243a29de` — confirmed a first-parent ancestor of current `main` HEAD. All three
  call sites forward `src_dir`, and regression tests already exist
  (`test_worktree_utils.py:361/393`, `test_builtin_loops.py:2139/2164`). Empirically
  re-verified in refine/decide: EPIC-2370's `6cc6f994` passes all 126 layout tests against
  its own worktree source under the existing shadow. The cited failing run
  (`sprint-refine-and-implement-20260714T180411`) ran a stale/unshadowed interpreter, not a
  residual gap. No code change needed.


---

## Resolution

- **Status**: Closed - Already Fixed
- **Closed**: 2026-07-14
- **Reason**: already_fixed (duplicate of bug-2629)
- **Closure**: Automated (ready-issue validation)

### Closure Notes
Issue was automatically closed during validation.
The issue was determined to be invalid, already resolved, or not actionable.
