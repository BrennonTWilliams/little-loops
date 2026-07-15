---
id: BUG-2649
type: BUG
priority: P2
status: done
captured_at: '2026-07-15T18:46:48Z'
completed_at: '2026-07-15T19:46:27Z'
discovered_date: 2026-07-15
discovered_by: capture-issue
relates_to:
- BUG-2629
- BUG-2640
- BUG-2614
decision_needed: false
confidence_score: 87
outcome_confidence: 81
score_complexity: 20
score_test_coverage: 24
score_ambiguity: 15
score_change_surface: 22
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

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-07-15):_

### ⚠ Scope change: Test 1 is already fixed on `main`

The Test 1 hermetic fix is **already committed on `main`**, landed the day
before this bug was captured:

- Commit `7bac68f3` `fix(test): make test_falsy_src_dir_leaves_pythonpath_uninjected hermetic` (2026-07-14 21:08), ancestor of current `HEAD`.
- `test_worktree_utils.py:490` already calls `monkeypatch.delenv("PYTHONPATH", raising=False)` with a docstring (`:482–489`) that names the gate self-contamination scenario verbatim.
- **Verified**: `PYTHONPATH="$(pwd)/scripts" python -m pytest …::test_falsy_src_dir_leaves_pythonpath_uninjected -n0` → **1 passed**. The test is hermetic against a pre-set ambient `PYTHONPATH` today.

**Why the gate still saw Test 1 fail on the EPIC-2570 run**: the verify gate
checks out the *EPIC branch tip*, which predated the fix. Confirmed:
`git merge-base --is-ancestor 7bac68f3 62822804^2` → **NO** (the merged
EPIC-2570 branch tip does *not* contain `7bac68f3`). So the gate ran the **old,
non-hermetic** copy of the test. The observed Test 1 failure was **branch
staleness**, not a still-broken test on `main`.

Implication for scope:
- **AC #1 is substantially satisfied on `main` already.** Remaining Test 1 work
  is at most: (a) add the explicit fail-before/pass-after regression test AC #1
  calls for (pre-set `PYTHONPATH`, assert — the current fix is only proven by the
  existing test passing under ambient `PYTHONPATH`), and (b) a process note that
  stale EPIC branches must rebase/merge `main` before the gate can trust the
  suite. The real remaining engineering is **Test 2**.

### Test 1 — how the fix works (mechanics)

`verify_epic_branch_before_merge` (`scripts/little_loops/worktree_utils.py:274`)
builds the child env at `:352–360`: only when `src_dir` is truthy does it
`env = os.environ.copy()` and prepend `worktree/scripts` to `PYTHONPATH`; when
falsy, `env` stays `None` and `subprocess.run(..., env=None)` (`:367`) inherits
the caller's `os.environ` verbatim. `monkeypatch.delenv` mutates that inherited
`os.environ`, so the scrub reaches the child. The positive companion AC #1
suggests already exists: `test_src_dir_prepends_worktree_source_onto_pythonpath`
(`test_worktree_utils.py:447`).

### Test 2 — `project_root` resolution (the real open work)

`test_string_present_in_doc` (`test_wiring_skills_and_commands.py:207–213`) reads
`project_root / ".claude/CLAUDE.md"`. The `project_root` fixture
(`conftest.py:208–211`) is **session-scoped** and anchored to
`Path(__file__).parent.parent.parent` — i.e. the *physical* `conftest.py`
location, three parents up. Under the gate, pytest is invoked with
`cwd=worktree_path` (`worktree_utils.py:367`), so the collected `conftest.py`
*is* the worktree's copy → `project_root` resolves to the **worktree root**, and
`.claude/CLAUDE.md:66` there does contain `spike` (verified). So the issue's
"conftest resolves to main vs worktree" theory does **not** hold for a
path-anchored, path-collected `conftest` — the flake mechanism is still
genuinely undetermined and should be treated as such.

Note on the "anchor to rootdir/cwd" preferred fix: there is **no existing
`request.config.rootpath` / `invocation_dir`-anchored fixture** anywhere in
`scripts/tests/` to model it after (repo-wide search: no matches). `project_root`
is the only fixture of its kind and it is `__file__`-relative. Switching it to
`request.config.rootpath` would resolve to the same worktree root under the gate
anyway, so it is unlikely to change Test 2's behavior — favor the **quarantine**
fallback (AC #2's second option) unless a concrete cross-tree read is actually
reproduced.

### Optional `LL_VERIFY_GATE` marker — precedent

No `LL_VERIFY_GATE` marker exists yet (grep-confirmed; only referenced in this
issue). If added, set it in `verify_epic_branch_before_merge`'s injected `env`
dict (`worktree_utils.py:352–360`) following the `LL_NON_INTERACTIVE="1"`
precedent (`host_runner.py`, many sites). Tests would gate on it with the
established module-level idiom
`pytestmark = pytest.mark.skipif(os.environ.get("LL_VERIFY_GATE") == "1", reason=…)`
— modeled on the `_BASH is None` / `shutil.which(...) is None` skips in
`test_claude_code_adapter.py:23` etc. (no env-var-keyed skip precedent exists
yet). Env-scrub fixture precedent for hermetic subprocess tests:
`isolated_env` in `test_host_runner.py:42–47` and the
`env = {**os.environ}; env.pop(KEY, None)` idiom in
`test_claude_code_adapter.py:171–183`.

### Integration Map

**Gate implementation**
- `scripts/little_loops/worktree_utils.py:274` — `verify_epic_branch_before_merge` (env build `:352–360`, subprocess `:367`).

**Callers of the gate (blast radius for any signature/env-marker change)**
- `scripts/little_loops/parallel/orchestrator.py:1310–1341` — `_verify_epic_branch_before_merge` wrapper; records `_epic_branch_verify_failures`.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — FSM verify state (shares the same free function).

**Tests to modify**
- `scripts/tests/test_worktree_utils.py:479` — Test 1 (already hermetic on `main`); add the explicit pre-set-`PYTHONPATH` regression per AC #1 near `:447`.
- `scripts/tests/test_wiring_skills_and_commands.py:207` — Test 2; quarantine or root-cause here.
- `scripts/tests/conftest.py:208` — `project_root` fixture (only touch if pursuing the rootdir-anchor route).

**Config / xdist context**
- `scripts/pyproject.toml` `[tool.pytest.ini_options]` — `-n logical` (parallel default), the condition under which Test 2 flakes.
- `scripts/tests/conftest.py:77–101` — `pytest_collection_modifyitems` `no_parallel` skip-on-worker idiom (a template if Test 2 needs serial-only execution).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/types.py:312–338` — `EpicBranchesConfig` dataclass (`verify_before_merge: bool = False`, `:338`); the config the gate reads. **No change needed** — an `LL_VERIFY_GATE` marker is an internal subprocess-env detail, not a config field. [Agent 1 finding]
- `scripts/little_loops/host_runner.py:268–272` + `scripts/little_loops/hooks/session_start.py:149` — the `LL_NON_INTERACTIVE` set/read precedent to mirror if the optional `LL_VERIFY_GATE` marker is added (set in the env dict, read as `os.environ.get("LL_VERIFY_GATE") == "1"`). No change required to these files themselves. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_orchestrator.py::TestEpicBranchVerifyGate` (~line 1549) — **indirect** gate coverage: patches `setup_worktree`/`cleanup_worktree`/`subprocess.run` and drives the gate through `ParallelOrchestrator`, never calling `verify_epic_branch_before_merge` by name. Run to confirm the fix doesn't break the caller path; unaffected by an env-dict-only change. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — verdict-vocabulary regression guard the fix must **not** perturb: `test_held_open_when_child_not_done` / `test_held_open_when_sibling_open_on_both_base_and_tip` assert `epic-merge-verdict.txt == "held_open"` literally; `test_finalize_surfaces_verify_verdict` / `test_finalize_verify_verdict_defaults_to_not_run` (~2489–2530) assert `verify_verdict` string literals; `test_verify_attaches_epic_worktree` (2140) / `test_merge_epic_branch_forwards_src_dir` (2165) assert `"verify_epic_branch_before_merge" in action`. No hardcoded `"2 failed"` assertion exists anywhere — that figure lives only in this issue's prose. [Agent 2/3 finding]
- No new schema test needed: `scripts/tests/test_config_schema.py:817–818` asserts only `verify_before_merge` type/default — unaffected. [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue` — only touch if the optional `LL_VERIFY_GATE` env marker is added; a marker is a pure addition to whichever of these describes the env dict:_
- `docs/reference/API.md:3336–3364` — `verify_epic_branch_before_merge` narrative describing the `src_dir` truthy/falsy branch and `env["PYTHONPATH"]` prepend; the most natural home for documenting a new marker. [Agent 2 finding]
- `docs/ARCHITECTURE.md:471,490–495` — shorter prose copy of the same PYTHONPATH-injection mechanism. [Agent 2 finding]
- `docs/development/MERGE-COORDINATOR.md:157` — third prose copy (routing-logic step 5). [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md:897–954` — documents the `verify_verdict` value set (`passed`/`failed`/`collection_error`/`skipped`/`not_run`) and `held_open` semantics; the fix must not change their **meaning** (a false-negative fix makes `passed` more accurate, adds no new verdict). [Agent 2 finding]
- **No change needed** (report only): `docs/reference/CLI.md:382`, `docs/reference/CONFIGURATION.md:376`, `docs/guides/SPRINT_GUIDE.md:334`, `skills/audit-loop-run/SKILL.md:294` — these describe the boolean flag / verdict value set, neither of which this fix alters. [Agent 2 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. After fixing/quarantining Test 2 and adding the Test 1 regression, run `scripts/tests/test_orchestrator.py::TestEpicBranchVerifyGate` and the `held_open`/`verify_verdict` assertions in `scripts/tests/test_builtin_loops.py` to confirm the gate's caller path and FSM-side verdict vocabulary are unperturbed.
2. Only if adding the optional `LL_VERIFY_GATE` env marker: document it in `docs/reference/API.md:3336–3364`'s existing env-build prose (mirror the `LL_NON_INTERACTIVE` set/read idiom); leave `config-schema.json` and `.ll/ll-config.json` untouched (internal subprocess-env detail, not a config field).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-15_

**Readiness Score**: 87/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 81/100 → HIGH CONFIDENCE

### Concerns
- Test 2's root cause is explicitly acknowledged as "genuinely undetermined" in the issue's own research findings — the original "conftest resolves to main vs worktree" theory was investigated and disproved (`project_root` is `__file__`-anchored and path-collected, so it already resolves to the worktree under the gate). Since no concrete reproduction of the flake mechanism exists and the research notes state switching to a rootdir-anchored fixture "is unlikely to change Test 2's behavior," committing to the quarantine fallback (AC #2's second option) rather than continuing to chase the root cause is the pragmatic path — flag this as a decision point before implementation starts, not something to resolve mid-implementation.

## Resolution

_Resolved by `/ll:manage-issue` on 2026-07-15._

**Test 1 (AC #1) — already hermetic on `main`; regression guard added.** The
`monkeypatch.delenv("PYTHONPATH")` scrub landed on `main` in `7bac68f3` before
this bug was captured (the EPIC-2570 gate ran a stale branch tip that predated
it). Added two explicit regression tests in
`test_worktree_utils.py::TestVerifyEpicBranchBeforeMerge`:
- `test_falsy_src_dir_does_not_inject_under_ambient_pythonpath` — pre-sets an
  ambient `PYTHONPATH=<abs>/ambient_marker` and asserts the child's `PYTHONPATH[0]`
  is that marker *verbatim* (the gate injects nothing when `src_dir` is falsy).
  Deterministic and immune to a leaked `scripts` entry; regressing the `if
  src_dir:` guard would push a different entry to the front and fail it.
- `test_verify_gate_marker_set_in_child_env` — asserts the child always carries
  `LL_VERIFY_GATE=1`.

**Test 2 (AC #2) — quarantined under the gate condition (root cause deferred).**
Per the issue's own research (the "conftest resolves to main vs worktree" theory
was disproved; `project_root` already resolves to the worktree root under the
gate; a rootdir-anchored fixture would not change behavior) and the confidence-check
decision point, the pragmatic path was quarantine, not chasing an unreproducible
flake. `verify_epic_branch_before_merge` now always sets `LL_VERIFY_GATE="1"` in
the test/lint child env (mirroring the `LL_NON_INTERACTIVE` idiom), and
`test_string_present_in_doc` skips when that marker is `"1"`. Off the gate — under
the standard `python -m pytest scripts/tests/` — all 150 cases still run (verified:
150 passed normally, 150 skipped under the marker). Root-cause follow-up tracked
by **BUG-2650**.

**AC #3 / #4** — full suite green on `main`: `15046 passed, 36 skipped`. lint,
mypy clean.

Changed:
- `scripts/little_loops/worktree_utils.py` — always build the child `env`, set
  `LL_VERIFY_GATE="1"`; docstring note.
- `scripts/tests/test_worktree_utils.py` — two regression tests.
- `scripts/tests/test_wiring_skills_and_commands.py` — `LL_VERIFY_GATE` skipif on
  `test_string_present_in_doc`; fixed a non-f-string assertion message.
- `docs/reference/API.md` — document the marker.
- `.issues/bugs/…BUG-2650…` — tracked root-cause follow-up.

## Status

- **Current Status**: done
- **Blockers**: None

## Session Log
- `/ll:manage-issue` - 2026-07-15T19:45:43Z - `61773fdf-a5b0-449b-b869-beeecf0f813b.jsonl`
- `/ll:confidence-check` - 2026-07-15T19:15:00 - `58ab2ec2-644e-4fdd-84bd-51abddc42a7a.jsonl`
- `/ll:wire-issue` - 2026-07-15T19:05:33 - `1e72aa60-fb3f-42de-95f2-db5e48012c1d.jsonl`
- `/ll:refine-issue` - 2026-07-15T18:55:42 - `3990f0fc-673f-4cb1-8647-3039d1efb245.jsonl`
- `/ll:capture-issue` - 2026-07-15T18:46:48Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b6561fde-933e-4543-855c-bc7b305d5f5f.jsonl`
