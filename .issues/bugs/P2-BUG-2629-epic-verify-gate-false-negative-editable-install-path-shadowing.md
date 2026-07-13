---
id: BUG-2629
title: Epic verify gate false-negative from editable-install path shadowing
type: bug
status: open
priority: P2
captured_at: '2026-07-13T18:30:06Z'
discovered_date: 2026-07-13
discovered_by: capture-issue
relates_to:
- BUG-2614
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-2629: Epic verify gate false-negative from editable-install path shadowing

## Summary

`verify_epic_branch_before_merge()` runs `project.test_cmd` inside a scratch
worktree checked out at the EPIC branch tip, but does **not** isolate the Python
import path from the host's editable install. When `little_loops` is installed
editable (`pip install -e ./scripts`), the editable `.pth`
(`_editable_impl_little_loops.pth`) hardcodes an **absolute** path to the *main*
checkout's `scripts/` and is loaded at every interpreter startup regardless of
`cwd`. So `import little_loops` resolves to the main tree's package, not the
worktree's branch code. Any EPIC branch that adds a **new module** (or changes a
module's public surface) then fails collection/import under the verify gate —
producing a false `failed` verdict for code that is actually correct.

## Root Cause

`scripts/little_loops/worktree_utils.py` — `verify_epic_branch_before_merge()`
(~line 311) runs:

```python
result = subprocess.run(
    shlex.split(cmd), capture_output=True, text=True, cwd=worktree_path,
)  # no env= → inherits host PYTHONPATH; editable .pth still wins
```

pytest collects test *files* from `<worktree>/scripts/tests/` (correct — the
branch's tests), but `import little_loops.<new_module>` resolves via the `.pth`
to the main checkout, which lacks the branch-only module → `ModuleNotFoundError`
at collection → pytest exits non-zero → verdict `failed`.

`.pth` entries are appended to `sys.path` *after* `PYTHONPATH` entries, so a
`PYTHONPATH` pointing at the worktree's source dir shadows the editable install.
This is exactly the manual workaround the FEAT-2618 sub-run used
(`PYTHONPATH=scripts python -m pytest ...`), but the shared verify function never
applies it.

## Reproduction

Observed in run `auto-refine-and-implement-20260713T123044` (scope
`EPIC-2616`). FEAT-2618 added `scripts/little_loops/cli/loop/queue.py` on the
epic branch; the verify gate ran against the worktree and reported
`verify_verdict: failed` even though the same suite passed (14857 passed) when
run with `PYTHONPATH=scripts`. Note: in that run the merge was `held_open` for a
*separate* reason (2 of 4 children skipped low_readiness), so the false negative
was advisory there — but once all children are `done`, `merge_epic_branch`'s
gate (`verify_before_merge: true`) re-runs this same broken verify and would emit
`verify_failed`, blocking a legitimate merge.

## Impact

- Shared function: used by **both** the FSM `auto-refine-and-implement` loop
  *and* `ll-parallel`'s `WorkerPool` epic path — the false negative exists on
  both orchestration paths.
- Any epic that introduces a new module is un-mergeable via the automated gate
  whenever the dev environment uses an editable install with an absolute `.pth`.

## Implementation Steps

1. Add a `src_dir: str | None = None` parameter to
   `verify_epic_branch_before_merge()` (callers pass `project.src_dir`, e.g.
   `"scripts"`).
2. When `src_dir` is truthy, build `env = os.environ.copy()` and prepend
   `str(worktree_path / src_dir)` to `PYTHONPATH`; pass `env=env` to the
   `subprocess.run` call. Skip injection when `src_dir` is falsy (preserve
   current behavior for non-editable / non-Python setups).
3. Forward `src_dir=cfg.project.src_dir` from both FSM YAML call sites in
   `scripts/little_loops/loops/auto-refine-and-implement.yaml`: the `verify`
   state (~line 396) and `merge_epic_branch` (~line 527). The non-epic in-place
   branch (`cwd=None`) needs no change — the repo-root `.pth` is already correct
   there.
4. Confirm the `ll-parallel` caller (orchestrator) also forwards `src_dir`.

### Wiring Phase (added by `/ll:wire-issue`)

_Documentation touchpoints identified by wiring analysis — the code fix above leaves
these prose descriptions incomplete:_

5. Update `docs/reference/API.md:3324-3341` — add the `src_dir` kwarg to the
   `verify_epic_branch_before_merge` signature/description.
6. Update `docs/ARCHITECTURE.md:476-491` — note PYTHONPATH isolation of the verify gate.
7. Update `docs/development/MERGE-COORDINATOR.md:471-474` — note import-path isolation
   defeating editable-install `.pth` shadowing.
8. While patching the YAML `verify` / `merge_epic_branch` actions, preserve the
   verbatim substrings asserted by `test_builtin_loops.py:2111`
   (`verify_epic_branch_before_merge`, `verify_before_merge=True`).

## Acceptance Criteria

- An EPIC branch that adds a brand-new module passes the verify gate under an
  editable install whose `.pth` points at a different checkout.
- Regression test: set up (or simulate) an editable `.pth` pointing away from the
  worktree, verify a branch containing a new module, assert the gate passes.
- Both FSM-loop and `ll-parallel` verify paths use the isolated `PYTHONPATH`.

## API/Interface

`verify_epic_branch_before_merge(..., src_dir: str | None = None)` — additive,
keyword-only, backward-compatible (defaults to today's behavior).

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis. Additive; the sections
above are preserved verbatim. Note the line numbers below refine the issue's
approximate anchors (the function starts earlier than the originally-cited ~311)._

### Root-cause anchors (verified)

- `scripts/little_loops/worktree_utils.py:245` — `verify_epic_branch_before_merge()`
  definition. Signature already uses a keyword-only block (`*,`) — the new
  `src_dir: str | None = None` slots in there, additive and backward-compatible.
- `scripts/little_loops/worktree_utils.py:311-316` — the offending `subprocess.run(shlex.split(cmd), capture_output=True, text=True, cwd=worktree_path)`
  call with **no `env=`**. This is the exact edit point.
- `scripts/little_loops/worktree_utils.py:9` — `os` is **already imported** at module
  level (alongside `subprocess:13`, `shlex:11`), so `env = os.environ.copy()` needs
  no new import.
- `ProjectConfig.src_dir` is a real field at `scripts/little_loops/config/core.py:141`
  with default `"src/"` (loaded at `core.py:156`). ⚠ **Not `None`** by default — so
  the "skip injection when falsy" guard in Implementation Step 2 will *not* skip for
  a normally-configured project (this project's value is `"scripts"`). That is the
  intended behavior; just don't expect the default to be falsy.

### Call sites (all three verified reachable — none currently forward `src_dir`)

- `scripts/little_loops/loops/auto-refine-and-implement.yaml:396-406` — `verify`
  state. ⚠ **Reads raw JSON**, not `BRConfig`: `project = cfg.get('project', {})`
  (`yaml:357-361`). So `src_dir` here must come via `project.get('src_dir', 'src/')`,
  **not** `cfg.project.src_dir`. (A `BRConfig` `ll_cfg` is constructed at `yaml:391`
  but only used for `get_worktree_base()`; `ll_cfg.project.src_dir` is an alternative
  source if preferred.)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:527-537` —
  `merge_epic_branch` state. Uses `cfg = BRConfig(...)`, so `src_dir=cfg.project.src_dir`
  follows the same attribute convention as the existing `cfg.project.test_cmd`.
  Confirmed this is a **second, independent** `verify_epic_branch_before_merge()`
  invocation (own fresh worktree); it does **not** read/reuse the earlier `verify`
  state's verdict — so both call sites must be patched. (ENH-2630 tracks de-duping
  the double run.)
- `scripts/little_loops/parallel/orchestrator.py:1323-1350` —
  `_verify_epic_branch_before_merge()` wrapper. `project = self.br_config.project`
  is already bound, so add `src_dir=project.src_dir` alongside the existing
  `test_cmd=project.test_cmd`.

### Reusable patterns for the env-build (model the fix after these)

- `scripts/little_loops/parallel/worker_pool.py:734` — canonical local idiom:
  `env = os.environ.copy()` → set key → pass `env=env` to `subprocess.run(cwd=worktree_path, ...)`.
- `scripts/tests/test_rn_refine.py` (`test_driver_cli_returns_drain_when_empty`) —
  closest precedent for the PYTHONPATH prepend itself, using the
  `os.pathsep.join(p for p in (new, existing) if p)` filter so an empty existing
  `PYTHONPATH` leaves no trailing separator. Recommend this exact idiom for Step 2.

### Test surface (model the regression test after these)

- `scripts/tests/test_worktree_utils.py:263` — `class TestVerifyEpicBranchBeforeMerge`.
  Four existing tests use real `git init` repos (`_init_repo`/`_git`) and literal
  `test_cmd="true"/"false"`. New regression test: create a branch with a new module,
  use a `test_cmd` that asserts the worktree src dir is on `PYTHONPATH`
  (e.g. `python3 -c "import os,sys; sys.exit(0 if '<worktree>/scripts' in os.environ.get('PYTHONPATH','') else 1)"`),
  and assert `(True, None)`. All four existing tests omit `src_dir` → the `None`
  default keeps them green.
- `scripts/tests/test_builtin_loops.py:2111` — `test_verify_attaches_epic_worktree`
  does static string-presence assertions on the YAML action. Add analogous asserts
  that `"src_dir="` appears in **both** the `verify` and `merge_epic_branch` action
  strings.
- `scripts/tests/test_orchestrator.py:1549` — `class TestEpicBranchVerifyGate` patches
  `setup_worktree`/`cleanup_worktree`/`subprocess.run`; if asserting the orchestrator
  forwards `src_dir`, inspect the `subprocess.run` call's `env=` kwarg here.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

These files describe `verify_epic_branch_before_merge()` / the epic verify gate and
become **incomplete** (not wrong — old behavior is preserved) once `src_dir`/PYTHONPATH
handling exists. Update prose to note that verify now prepends the worktree `src_dir`
onto `PYTHONPATH` to defeat editable-install `.pth` shadowing:

- `docs/reference/API.md:3324-3341` — canonical API reference listing
  `verify_epic_branch_before_merge` as a stateless free function with an `(ok, message)`
  return contract; add the new `src_dir` kwarg to its signature/description [Agent 2].
- `docs/ARCHITECTURE.md:476-491` (and the free-function block ~3323-3334) — describes
  the function and its three call sites; add the PYTHONPATH-isolation behavior [Agent 2].
- `docs/development/MERGE-COORDINATOR.md:471-474` — describes `verify_before_merge`
  gating "a scratch-worktree run of `test_cmd`/`lint_cmd`"; note the import-path
  isolation so the editable-install false-negative narrative is documented [Agent 2].

_Confirmed **not** a gap (agents verified, excluded from scope):_
- `config-schema.json` / `.ll/ll-config.json` — `src_dir` reuses the **existing**
  `ProjectConfig.src_dir` field; no new config surface, no schema change [Agents 1+2].
- No new callers/importers: only the 3 known call sites invoke the function;
  `worker_pool.py` does **not** call it; no `getattr`/`inspect` reflection consumers
  [Agents 1+3]. `cli/*.py` import unrelated symbols (`detect_default_branch`,
  `setup_worktree`) from `worktree_utils`, not the changed function.
- No other test files beyond the 3 already listed exercise this surface [Agent 3].

### Implementation Caution (error-string preservation)

_Wiring pass added by `/ll:wire-issue`:_ inserting `env=env` into the three
`subprocess.run` calls must not alter existing message templates that tests assert on:
- `scripts/little_loops/worktree_utils.py:319` — `f"{label}_cmd failed (exit ...)"` is
  asserted verbatim at `scripts/tests/test_orchestrator.py:1615` [Agent 2].
- `test_builtin_loops.py:2111` substring checks require the YAML action to keep
  `"verify_epic_branch_before_merge"` and `"verify_before_merge=True"` verbatim — adding
  `src_dir=...` as a new argument is safe as long as those substrings remain [Agent 2].

## Session Log
- `/ll:wire-issue` - 2026-07-13T18:44:17 - `781c2615-1802-4eab-8b18-5a814f3e9a02.jsonl`
- `/ll:refine-issue` - 2026-07-13T18:36:34 - `294207a3-b75b-4916-83ed-23137f7e0a6d.jsonl`
- `/ll:capture-issue` - 2026-07-13T18:30:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e418041f-97b9-4193-89df-c4643e9794aa.jsonl`

---

## Status

- **Status**: open
- **Priority**: P2
