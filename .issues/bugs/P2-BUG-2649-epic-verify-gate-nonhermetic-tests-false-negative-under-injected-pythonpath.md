---
id: BUG-2649
type: BUG
priority: P2
status: open
captured_at: '2026-07-15T18:46:48Z'
discovered_date: 2026-07-15
discovered_by: capture-issue
relates_to:
- BUG-2629
- BUG-2640
- BUG-2614
decision_needed: false
---

# BUG-2649: Epic verify gate false-negatives on two non-hermetic tests under injected PYTHONPATH

## Summary

Two tests in the suite fail **only** when run by the epic-branch merge verify
gate (`verify_epic_branch_before_merge`, `scripts/little_loops/worktree_utils.py:274`)
and pass everywhere else — in isolation, and on merged `main`. Because the gate
runs `python -m pytest scripts/tests/` against the EPIC branch tip with
`env["PYTHONPATH"] = <worktree>/scripts` prepended (the BUG-2629 editable-install
`.pth` defeat, lines 352–360) under `pytest-xdist`, these tests read an ambient
environment they don't control and trip. The result is a **false-negative merge
block** (`verify_verdict=failed` / `epic_merge_verdict=held_open`) for a branch
that is actually mergeable.

Observed on the `sprint-refine-and-implement` run for **EPIC-2570** (2026-07-15):
the gate reported `2 failed, 14994 passed`, held the merge open, and both
failures reproduced as **PASS** when re-run in isolation on the branch worktree
and again after the branch was hand-merged to `main`. This is the second-order
consequence of the BUG-2629/BUG-2640 fix: the PYTHONPATH injection those issues
added to defeat editable-install shadowing is now leaking into tests that assert
about the environment or resolve paths from it.

## Current Behavior

The gate injects `PYTHONPATH=<worktree>/scripts` and runs the full suite in
parallel. Two tests fail under exactly those conditions:

**1. `scripts/tests/test_worktree_utils.py::TestVerifyEpicBranchBeforeMerge::test_falsy_src_dir_leaves_pythonpath_uninjected`** — DETERMINISTIC.
The test verifies that with `src_dir=None` the gate performs **no** PYTHONPATH
injection. It does so by having the inner gate run a subprocess
(`python3 -c "...; sys.exit(1 if basename(PYTHONPATH[0])=='scripts' else 0)"`).
But when this test itself runs *inside* the gate, the suite already carries an
ambient `PYTHONPATH=<worktree>/scripts`, which the test's child subprocess
**inherits**. So `basename(PYTHONPATH[0]) == 'scripts'` → child exits 1 →
`verify_epic_branch_before_merge(..., src_dir=None)` returns `(False, ..., 1)`,
and the assertion `== (True, None, None)` fails. The test is self-contaminating:
it never scrubs `PYTHONPATH` from the child env before asserting the
no-injection default.

**2. `scripts/tests/test_wiring_skills_and_commands.py::test_string_present_in_doc[.claude/CLAUDE.md-spike-FEAT-2567]`** — NON-DETERMINISTIC.
The test asserts `"spike" in (project_root / ".claude/CLAUDE.md").read_text()`,
where `project_root` = `conftest.py.__file__.parent.parent.parent`. The string
*is* present on the EPIC-2570 branch (`.claude/CLAUDE.md:66`). The test passes
in an isolated branch worktree run and on merged `main`, but failed under the
full parallel xdist gate run. Root cause is undetermined — most likely a
`pytest-xdist` worker/`conftest` import resolving `project_root` to the wrong
tree (main vs worktree), or a stale/racing worktree read. Behaves as a flake
under the gate's specific conditions.

## Expected Behavior

The verify gate does not fail on these two tests when run under its own
injected-`PYTHONPATH` + parallel-worktree conditions:

- Test 1 is **hermetic**: it scrubs/overrides `PYTHONPATH` in the child
  subprocess env (or passes an explicit clean `env`) so it asserts the
  `src_dir=None` no-injection default independent of whatever `PYTHONPATH` the
  gate set for the outer run. It should pass identically inside and outside the
  gate.
- Test 2 is either **root-caused and fixed** (make `project_root` resolution
  robust under the gate — anchor to the invocation `cwd`/rootdir rather than the
  physical `conftest.py` location, which can resolve to the wrong tree under
  xdist + editable install) **or explicitly quarantined** (`xfail`/`skip` under
  the gate condition) with a tracked rationale, so it stops silently blocking
  merges.

Net: a genuinely mergeable EPIC branch is no longer held open by these two
false negatives.

## Steps to Reproduce

1. On an EPIC branch that adds any importable source (so the gate injects
   `PYTHONPATH`), run the merge with `epic_branches.verify_before_merge: true`
   (or invoke `verify_epic_branch_before_merge(..., src_dir="scripts")` directly).
2. Observe the gate report `2 failed` — `test_falsy_src_dir_leaves_pythonpath_uninjected`
   and `test_string_present_in_doc[.claude/CLAUDE.md-spike-FEAT-2567]` — and the
   merge held open (`verify_verdict=failed`).
3. Re-run both failing tests in isolation on the same branch worktree:
   `PYTHONPATH=scripts python -m pytest <both nodeids> -q` → **2 passed**.
4. Confirm test 1 deterministically: pre-set `PYTHONPATH=$(pwd)/scripts` in the
   shell, then run only `test_falsy_src_dir_leaves_pythonpath_uninjected` → it
   fails, because its child subprocess inherits the ambient `PYTHONPATH` whose
   first entry's basename is `scripts`.

## Root Cause

The BUG-2629/BUG-2640 remedy — prepend `<worktree>/scripts` to `PYTHONPATH` so
branch-only modules resolve to the worktree instead of the editable-install
`.pth` pointing at the main checkout — changes the ambient environment the whole
suite runs under. Tests that (a) assert about `PYTHONPATH` contents, or (b)
resolve filesystem paths from interpreter/`conftest` location under xdist, were
written assuming a vanilla `python -m pytest scripts/tests/` invocation and are
not hermetic against the gate's injected env. `verify_epic_branch_before_merge`
sets `env["PYTHONPATH"]` at `scripts/little_loops/worktree_utils.py:357–360` and
runs each command via `subprocess.run(..., env=env)` at line 367.

## Proposed Solution

**Test 1 (deterministic, do this first):** in
`test_falsy_src_dir_leaves_pythonpath_uninjected`, build the child subprocess env
explicitly with `PYTHONPATH` removed (e.g. pass `test_cmd` a wrapper that clears
it, or extend the gate/test seam so the assertion runs with a scrubbed env). The
test must prove "no injection given `src_dir=None`" regardless of the caller's
ambient `PYTHONPATH`. Consider a companion positive test that asserts the
injected case (`src_dir="scripts"`) *does* prepend, to keep both directions
covered.

**Test 2 (non-deterministic):**
- Preferred: make `project_root` resolution anchor to the pytest rootdir / the
  worktree `cwd` the gate invokes from, not to `conftest.py.__file__`, so a
  cross-tree `conftest` import under xdist can't point the doc read at `main`.
- Fallback: mark the wiring string-presence tests `xfail`/`skip` under the gate
  condition (detectable via an env marker the gate sets) with a tracked
  follow-up, so the gate stops blocking on a flake while the root cause is
  pinned down.

Optionally, add an env marker in `verify_epic_branch_before_merge` (e.g.
`LL_VERIFY_GATE=1`) so any test that must adapt to the gate's non-standard
invocation can detect it deterministically rather than sniffing `PYTHONPATH`.

## Impact

- **Blocks real EPIC merges.** Any EPIC branch whose suite happens to include
  these tests (i.e. every branch) can be held open by the gate on false
  negatives, stranding correct, verified work on the branch.
- **Erodes trust in the gate.** Operators learn to hand-merge "held_open"
  branches after eyeballing the failures, which defeats the point of an
  automated pre-merge gate and risks a real failure being waved through.
- **Recurring class.** Third instance in this family after BUG-2629 and
  BUG-2640 — the fix for import shadowing introduced an environment-leak class
  the tests weren't hardened against.

Manual workaround (used for EPIC-2570): confirm the failures reproduce as PASS
in an isolated branch worktree, then merge by hand. Acceptable once; not a
substitute for a hermetic gate.

## Acceptance Criteria

1. `test_falsy_src_dir_leaves_pythonpath_uninjected` passes when run under an
   ambient `PYTHONPATH=<abs>/scripts` (i.e. it is hermetic against the gate's
   injected env) and still passes in a vanilla suite run. A regression test
   demonstrates it fails before the fix and passes after when `PYTHONPATH` is
   pre-set.
2. The spike wiring string test (`test_string_present_in_doc[...spike-FEAT-2567]`)
   is either root-caused + fixed to be robust under xdist + injected PYTHONPATH,
   or explicitly quarantined under the gate condition with a documented reason
   and a tracked follow-up.
3. Running the epic verify gate path (`verify_epic_branch_before_merge` with
   `src_dir="scripts"`) against a branch that includes both tests yields no
   failure attributable to either test.
4. `python -m pytest scripts/tests/` still exits 0 on `main` (no regression to
   the standard invocation).

## Status

- **Current Status**: open
- **Blockers**: None

## Session Log
- `/ll:capture-issue` - 2026-07-15T18:46:48Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b6561fde-933e-4543-855c-bc7b305d5f5f.jsonl`
