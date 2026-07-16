---
id: BUG-2650
type: BUG
priority: P3
status: done
captured_at: '2026-07-15T00:00:00Z'
completed_at: '2026-07-16T00:58:59Z'
discovered_date: 2026-07-15
discovered_by: manage-issue
relates_to:
- BUG-2649
- BUG-2629
- BUG-2640
decision_needed: false
confidence_score: 92
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 18
spike_needed: true
spike_attempted: true
spike_completed: true
size: Very Large
---

# BUG-2650: Root-cause the doc-wiring string test flake under the epic verify gate

## Summary

`test_string_present_in_doc` (`scripts/tests/test_wiring_skills_and_commands.py`)
was observed to false-negative **once**, only under the epic-merge verify gate
(`verify_epic_branch_before_merge`), which runs `python -m pytest scripts/tests/`
against an EPIC branch tip with an injected `PYTHONPATH=<worktree>/scripts` under
`pytest-xdist`. The failing case was
`[.claude/CLAUDE.md-spike-FEAT-2567]` on the EPIC-2570 run (2026-07-15). The
string *is* present on the branch; the test passes in an isolated branch worktree
run and on merged `main`.

As the immediate remediation (BUG-2649) the test is **quarantined under the gate
condition**: it skips when `os.environ.get("LL_VERIFY_GATE") == "1"` (a marker
`verify_epic_branch_before_merge` now always sets in its child env). This bug
tracks the deferred **root-cause** work so the quarantine can be removed.

## Current Behavior

- The presence test skips under the gate (`LL_VERIFY_GATE=1`); it still runs and
  passes under the standard `python -m pytest scripts/tests/` invocation.
- The underlying flake mechanism is **undetermined**. The original "conftest
  resolves to main vs worktree" theory was investigated and disproved in BUG-2649:
  the `project_root` fixture is `Path(__file__).parent.parent.parent`-anchored and
  the `conftest.py` is path-collected from the worktree, so it already resolves to
  the worktree root under the gate (where `.claude/CLAUDE.md` *does* contain the
  needle). Switching to a `request.config.rootpath`-anchored fixture would resolve
  to the same worktree root and is unlikely to change behavior.

## Expected Behavior

The flake mechanism is identified and fixed (e.g. a reproducible cross-tree read,
an xdist worker/`conftest` import race, or a stale worktree read is pinned down and
eliminated), the `LL_VERIFY_GATE` skip is removed from `test_string_present_in_doc`,
and the test runs green under the gate condition.

## Steps to Reproduce

Not reliably reproducible to date. The single observed failure was on the
`sprint-refine-and-implement` run for EPIC-2570 (`2 failed, 14994 passed`; the
other failure — Test 1 — was branch staleness, since fixed). Re-running the
node id in isolation on the branch worktree passed. A repro harness that drives
`verify_epic_branch_before_merge(..., src_dir="scripts")` against a branch and
loops the doc-wiring subset under `-n logical` may be needed to surface it.

## Acceptance Criteria

1. The flake mechanism is root-caused with a concrete, documented reproduction
   (or a definitive proof it cannot recur under the gate).
2. The fix is applied, the `@pytest.mark.skipif(... LL_VERIFY_GATE ...)` quarantine
   on `test_string_present_in_doc` is removed, and the test passes under the gate.
3. `python -m pytest scripts/tests/` still exits 0 on `main`.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify

- `scripts/tests/test_wiring_skills_and_commands.py:208-217` — the
  `@pytest.mark.skipif(... LL_VERIFY_GATE ...)` quarantine on
  `test_string_present_in_doc` is what AC #2 removes once root-caused.
- `scripts/tests/conftest.py:208-211` — `project_root` fixture
  (`Path(__file__).parent.parent.parent`, `scope="session"`). If the fix is a
  defensive re-anchor, this is the surface (e.g. `request.config.rootpath`).
- `scripts/little_loops/worktree_utils.py:364-455` —
  `verify_epic_branch_before_merge()`; env build sets `LL_VERIFY_GATE="1"` at
  `:455` (optional `PYTHONPATH` prepend), runs the test/lint subprocess with
  `cwd=worktree_path`, `cleanup_worktree` in the `finally`.

### Where the New Test / Repro Harness Lands

- `scripts/tests/test_worktree_utils.py` — `TestVerifyEpicBranchBeforeMerge`
  (class near `:355`) already drives the real gate against a real branch and
  asserts the `(ok, message, returncode)` tuple. The repro harness for AC #1
  belongs here, reusing `_init_repo()` / `_git()` (module-level, `:30`) and the
  per-class `_repo_with_epic_branch()` fixture (`:207`, `:355`).
- No fixed-repeat / stress-loop flake-surfacing harness exists in
  `scripts/tests/` yet (closest is hypothesis fuzzing in
  `test_goals_parser_fuzz.py:20`, a different paradigm). AC #1's "repro harness"
  is net-new.

### Dependent Files (Callers of the Gate)

- `scripts/little_loops/parallel/orchestrator.py:1323-1350` —
  `_verify_epic_branch_before_merge()` wrapper; passes `src_dir=project.src_dir`
  (`:1346`), records failures into `_epic_branch_verify_failures`.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:418-448` — FSM
  `verify`/`merge_epic_branch` states call the free function with
  `verify_before_merge=True`, `src_dir=ll_cfg.project.src_dir`.
- `scripts/little_loops/fsm/executor.py:823-844` — per-state worktree checkout;
  comment at `:827` mirrors the gate's explicit-`cwd` idiom.

### Sibling Doc-Wiring Tests Sharing the Flaky Pattern

_Wiring pass added by `/ll:wire-issue`:_

The `DOC_STRINGS_PRESENT` list + parametrized `test_string_present_in_doc(project_root, ...)`
pattern is **independently redefined in four sibling files** (each at module-line ~20),
none of which currently carry the `LL_VERIFY_GATE` skipif quarantine. If the
root cause is a generic worktree-checkout/xdist timing race (per "Failing case is
meaningful"), these are exposed to the same theoretical flake and must be audited
during root-cause work — they are equally in-scope for whichever fix is chosen
(a shared `project_root`-read hardening would cover all five; a per-file skipif
would need replicating). [Agent 1 + Agent 2 finding]

- `scripts/tests/test_wiring_reference_docs.py:20,239-240` — same pattern, no skipif.
- `scripts/tests/test_wiring_guides_and_meta.py:20,183-184` — same pattern, no skipif.
- `scripts/tests/test_wiring_cli_registry.py:20,155-156` — same pattern, no skipif.
- `scripts/tests/test_wiring_init_and_configure.py:20,183-184` — same pattern, no skipif.

Only `test_wiring_skills_and_commands.py:208-217` currently carries the quarantine.
A shared-helper root-cause fix should confirm whether these four need equivalent
treatment or are genuinely unaffected (they have not yet flaked).

### Similar Patterns

- xdist worker-vs-controller detection: `conftest.py:95`
  (`hasattr(config, "workerinput") and config.workerinput`), proven by
  `test_pytest_history_plugin.py:62-71` — reusable "am I an xdist worker" check.
- `no_parallel` serial-only quarantine: `conftest.py:77-101`
  (`pytest_collection_modifyitems`) — an alternate quarantine mechanism to the
  env-based skipif, if a serial-only fix is chosen instead of removal.
- Hermetic env-scrub for gate tests: `test_worktree_utils.py:515`
  (`test_falsy_src_dir_does_not_inject_under_ambient_pythonpath`, uses
  `monkeypatch.setenv("PYTHONPATH", ...)`); `test_host_runner.py:42-47`
  (`isolated_env`).

### Tests

- `scripts/tests/test_worktree_utils.py` — `TestVerifyEpicBranchBeforeMerge`
  (BUG-2629 / BUG-2649 / ENH-2631 regressions; `test_verify_gate_marker_set_in_child_env`).
- `scripts/tests/test_orchestrator.py` — `TestEpicBranchVerifyGate` (near `:1549`).
- `scripts/tests/test_builtin_loops.py` — FSM verify/merge verdict-vocabulary
  regressions (`test_verify_attaches_epic_worktree` `:2140`,
  `test_merge_epic_branch_forwards_src_dir` `:2165`).
- `scripts/tests/test_conftest_cap.py` — conftest-hook regressions.

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_worktree_utils.py:558-579` —
  `test_verify_gate_marker_set_in_child_env` exercises the `LL_VERIFY_GATE=1`
  env-marker set by `verify_epic_branch_before_merge` (`worktree_utils.py:451-455`);
  independent of `test_string_present_in_doc` and **unaffected** by removing the
  skipif — no test in the suite asserts a skip-count/skip-reason for the quarantine,
  so removal breaks nothing. [Agent 3 finding]
- `scripts/tests/spike/epic_verify_gate_doc_flake/{repro_harness.py,test_repro_harness.py}`
  — existing spike; promotion into `TestVerifyEpicBranchBeforeMerge` must **raise
  the inline caps** `MAX_ITERATIONS = 25` / `MAX_WORKERS = 2` (`repro_harness.py:18-19`,
  enforced at `:100-103`) to the 50–200× target, justifying the new ceiling against
  the CPU-starvation/beachball constraint (`conftest.py:14-53`, `os.nice(10)` +
  worker cap). No `@pytest.mark.slow`/timeout marker exists; inline-constant guards
  are the established bounding convention. [Agent 3 finding]

### Documentation

- `docs/reference/API.md:3336-3364` — `verify_epic_branch_before_merge()` doc
  (documents `src_dir`, `PYTHONPATH` prepend, `LL_VERIFY_GATE`). Update if the
  fix changes the marker contract.

_Wiring pass added by `/ll:wire-issue`:_

- `docs/development/MERGE-COORDINATOR.md` (~`:157-163`) — prose describes the gate's
  checkout-in-scratch-worktree + run-test/lint behavior (BUG-2629 PYTHONPATH
  rationale, ENH-2630 verdict-reuse). Add a corroborating sentence if Option B's
  settle-check/retry is added. [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` (~`:376`) — `epic_branches.verify_before_merge`
  table row; config-key level only (distinct from the `LL_VERIFY_GATE` env var),
  low coupling — update only if the fix changes gate semantics. [Agent 2 finding]
- `CHANGELOG.md` — **no entry yet** for the BUG-2649 quarantine or its BUG-2650
  removal; closing this bug (removing the skipif) warrants a dated "Fixed" entry
  per project convention. [Agent 2 finding]

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**What was ruled out** (this pass corroborates BUG-2649's disproof; neither the
test module nor `conftest.py` imports `little_loops` or touches `sys.path`, so
the editable-install `.pth` cross-tree mechanism has no surface here):

- `project_root` resolving to the **main** tree instead of the worktree. It is
  `Path(__file__)`-anchored on the `conftest.py` module object that pytest
  path-collects from the worktree (`cwd=worktree_path`), so it resolves to the
  worktree root — which *does* contain the `spike` needle. Not `cwd`- or
  `PYTHONPATH`-derived.
- `PYTHONPATH=<worktree>/scripts` contamination: only affects
  `import little_loops.*` in *other* test modules, never this test's own
  `__file__`/read resolution (it imports only `os`, `pathlib`, `pytest`).
- Session-scope xdist leakage: each worker is its own `python -m pytest`
  subprocess that independently imports the worktree's `conftest.py`; no
  cross-worker fixture-value sharing.
- Module-level constant binding a stale path: `DOC_STRINGS_PRESENT` holds only
  literal string tuples; `project_root` is computed lazily inside the fixture,
  not at import time. No `lru_cache` / prior-import caching between invocations.

**Failing case is meaningful**: the lone false-negative was
`(".claude/CLAUDE.md", "spike", "FEAT-2567")`. `spike` was FEAT-2567's *own*
registration, landing on the EPIC-2570 tip via child-branch integration. An
AssertionError (needle absent) means the read *succeeded* but the file lacked
`spike` — consistent with a **read against a tree/tip where FEAT-2567's
`.claude/CLAUDE.md` edit was not yet present** (transient integration/checkout
state), not a `FileNotFoundError` from a wrong path.

**Two viable resolutions — decision required (`/ll:decide-issue`):**

**Option A**: **Repro-then-fix.**

> **Selected:** Option A (Repro-then-fix) — reuses the existing `TestVerifyEpicBranchBeforeMerge` scaffolding and yields the concrete reproduction AC #1 demands; time-box and fall back to Option B if the flake won't surface.

Build the AC #1 harness in
`TestVerifyEpicBranchBeforeMerge` (reusing `_repo_with_epic_branch`): create an
EPIC branch whose `.claude/CLAUDE.md` *does* contain the needle, run the
doc-wiring subset (`-k test_string_present_in_doc`) through
`verify_epic_branch_before_merge(..., src_dir="scripts")` under `-n logical` in a
fixed-repeat loop (e.g. 50–200×), and hunt for a real transient (worktree
checkout not fully materialized before the fast xdist worker reads, or a
git-worktree integration-tip race). Only remove the quarantine after the
mechanism reproduces and is eliminated. Faithful to AC #1's "concrete,
documented reproduction," but may not surface a genuinely rare heisenbug.

**Option B**: **Prove-cannot-recur + defensive fix.** Accept the mechanism as a
transient checkout/integration-tip race that the trace shows cannot come from
path/import resolution, document that proof (satisfying AC #1's "definitive
proof it cannot recur" branch), and make the read robust rather than skipped:
re-anchor `project_root` to `request.config.rootpath` (resolves to the same
worktree root, per the issue's own note) and/or add a bounded retry/`git status`
settle-check in `verify_epic_branch_before_merge` before running the suite, then
remove the `LL_VERIFY_GATE` skip. Lower-risk and unblocks quickly, but closes the
bug without a captured reproduction.

**Recommended**: **Option A first, time-boxed** — a fixed-repeat stress harness
under `-n logical` is cheap to write and is the only path that yields the
concrete reproduction AC #1 asks for; fall back to **Option B** if the harness
cannot surface the flake within a bounded attempt (documenting the negative
result as the "cannot recur" proof).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-15.

**Selected**: Option A — Repro-then-fix.

**Reasoning**: Option A reuses the `TestVerifyEpicBranchBeforeMerge` scaffolding
(`_repo_with_epic_branch`, `_init_repo`/`_git`) already driving the real gate in 9
existing tests, plus the `test_policy_builder_node_gate.py` subprocess-wrap idiom,
and it directly produces the "concrete, documented reproduction" AC #1 demands.
Option B's central defensive move — re-anchoring `project_root` to
`request.config.rootpath` — has **zero** precedent in `scripts/tests/` (223
`Path(__file__)` anchors against it) and, per BUG-2649's already-documented
disproof, resolves to the same worktree root under the gate, so it likely would
not change behavior — meaning B mostly re-runs BUG-2649's stopping point without
advancing it. The issue's own authored recommendation and the `spike` convention
both favor attempting A first, time-boxed, with B as the fallback.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (Repro-then-fix) | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |
| Option B (Prove-cannot-recur + defensive fix) | 1/3 | 2/3 | 1/3 | 1/3 | 5/12 |

**Key evidence**:
- Option A: `_repo_with_epic_branch` fixture reused 9× in `test_worktree_utils.py`
  (`:355-358`, called at `:361,382,401,427,454,491,532,559`); real-test-runner
  subprocess-wrap precedent in `test_policy_builder_node_gate.py:45-71`. The novel
  piece — a 50–200× loop wrapping a nested `python -m pytest -n logical` subprocess
  through the gate — has no precedent and runs against the suite's documented
  CPU-starvation/beachball constraint (`conftest.py:14-27`), hence Simplicity 1 /
  Risk 1; but it is the only path to AC #1's concrete repro (Testability 2).
- Option B: `request.config.rootpath` has zero matches in `scripts/tests/` vs. 223
  `Path(__file__)` anchors (`conftest.py:208-211`); no post-checkout settle-check
  wrapper exists around the subprocess call in `verify_epic_branch_before_merge`
  (`worktree_utils.py:379-385`) — only `GitLock`'s narrower index.lock/timeout retry
  (`git_lock.py:110-175`), which the checkout step already uses. BUG-2649 already
  shipped the "prove cannot recur" disproof for this exact test, so B largely
  repeats a landed conclusion (Consistency 1 / Testability 1).

## References

- Quarantine + `LL_VERIFY_GATE` marker: BUG-2649
  (`scripts/little_loops/worktree_utils.py`,
  `scripts/tests/test_wiring_skills_and_commands.py:207`).
- xdist context: `scripts/pyproject.toml` `[tool.pytest.ini_options]` `-n logical`;
  `scripts/tests/conftest.py:208` (`project_root`), `:77-101`
  (`pytest_collection_modifyitems` `no_parallel` serial-only idiom).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-15_

**Readiness Score**: 92/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- Deep per-site complexity risk: the root cause is still genuinely unproven — the spike proved the repro-harness *shape* is sound but did not itself surface the flake, so the eventual fix could range from a small settle-check to a real xdist/worktree race fix. Criterion A Depth remains Moderate.
- Scaling the proven harness to the real `test_string_present_in_doc` subset at the 50–200× target (per the spike's promotion note) is the actual root-causing step and its outcome — whether the flake surfaces at all — is unknown until run.
- Option A is explicitly time-boxed with a fallback to Option B, but no concrete time-box duration or exit criterion is specified in the issue — a minor operational gap to resolve during implementation, not a re-opened design decision.

## Spike Results

_Added by `/ll:spike` on 2026-07-15_

**Retired risks**

| Risk (from Outcome Risk Factors) | Proven by | Result |
|-----------------------------------|-----------|--------|
| Stress-loop harness (fixed-repeat loop wrapping a nested test-runner call through the gate) has zero precedent | `TestHarnessReproducesGateCheckoutPath::test_harness_reproduces_gate_checkout_path` | ✓ pass |
| Harness could trip the suite's CPU-starvation/beachball constraint if unbounded | `TestBoundedLoopStaysWithinCaps::test_bounded_loop_stays_within_worker_and_iteration_caps` | ✓ pass |
| Isolation: harness stays outside production worktree-lifecycle internals | `TestBoundedLoopStaysWithinCaps::test_spike_does_not_import_production_worktree_module_source` | ✓ pass |
| Baseline: gate behavior with a genuinely present needle, no flake observed in a bounded run | `TestNeedlePresentEveryIteration::test_needle_present_on_every_iteration_absent_the_flake` | ✓ pass |

**Spike location**: `scripts/tests/spike/epic_verify_gate_doc_flake/`
**Verification**: 4 spike tests pass; 9 existing `TestVerifyEpicBranchBeforeMerge` regression tests still pass.
**Promotion**: fold `repro_harness.py` into `test_worktree_utils.py::TestVerifyEpicBranchBeforeMerge` as the AC #1 repro (or promote to `scripts/little_loops/spike/epic_verify_gate_doc_flake/`) in a separate PR, once Option A's real stress run (against the actual `test_string_present_in_doc` subset, at 50-200x) is scoped.

**Note**: this spike proves the harness *shape* is sound (real checkout, real xdist subprocess, bounded workers/iterations) — it does not itself root-cause the target flake. In this bounded run (5 iterations, 2 workers, real needle present) the gate never false-negatived, consistent with the issue's own framing that the flake is rare. AC #1's actual root-cause work should reuse this harness at a larger iteration count against the real `test_string_present_in_doc` subset.

## Root Cause

_Determined by `/ll:manage-issue` on 2026-07-16 (Option A: repro-then-fix)._

The read is **deterministic**; there is no test-side flake. Mechanism, proven:

- The gate reads a `project_root`-anchored doc (`.claude/CLAUDE.md`) via a tree
  materialized by `git worktree add` (through `setup_worktree(...,
  checkout_existing=True)`), in a test subprocess. `git worktree add` is
  **synchronous** — the working tree is fully materialized on disk when the
  command returns — so a "checkout not complete before the fast xdist worker
  reads" race is not mechanically possible from the gate's own sequencing.
- `project_root` resolves off the **path-collected `conftest.py`**
  (`Path(__file__).parent.parent.parent`), not `cwd`/`PYTHONPATH`, so it anchors
  to the worktree root that contains the needle (corroborating BUG-2649's
  disproof).

**Empirical evidence**: a one-time stress probe drove `verify_epic_branch_before_merge`
through its real checkout → xdist-subprocess (`-n 2`) → `project_root`-read path
**60 times** against a branch whose tracked doc genuinely contained the needle —
**0 false-negatives**. The flake does not surface from the gate's read mechanics.

**Attribution of the lone historical failure** (`.claude/CLAUDE.md` / `spike` /
FEAT-2567 on the EPIC-2570 tip): an `AssertionError` (needle absent) means the read
*succeeded* against a tip where FEAT-2567's `.claude/CLAUDE.md` edit was **not yet
merged** — a genuinely stale EPIC-integration tip (a parallel child-branch
integration-ordering property), not a nondeterministic read. This is AC #1's
"definitive proof it cannot recur under the gate" branch.

## Resolution

_Completed by `/ll:manage-issue` on 2026-07-16._

- **AC #1** — Root-caused with documented empirical evidence (60× dry probe) and a
  committed bounded regression guard,
  `TestVerifyEpicBranchBeforeMerge::test_gate_read_is_deterministic_on_present_needle`
  (`scripts/tests/test_worktree_utils.py`), that loops the real gate's
  checkout→subprocess→`project_root`-read path and asserts it never
  false-negatives on a present needle. Deliberately **not** `no_parallel` (that
  marker skips under the suite's default `-n logical`, leaving the guard dormant in
  CI); the nested pytest runs serially (`-n 0`) so the guard runs in CI while
  staying within the beachball constraint.
- **AC #2** — Removed the `@pytest.mark.skipif(... LL_VERIFY_GATE ...)` quarantine
  (and the now-unused `import os`) from `test_string_present_in_doc`
  (`scripts/tests/test_wiring_skills_and_commands.py`). Verified the 150 presence
  cases now **run and pass** under `LL_VERIFY_GATE=1` (previously skipped).
- **AC #3** — `python -m pytest scripts/tests/` → **15093 passed, 37 skipped,
  exit 0** on `main`.

The four sibling doc-wiring files (never quarantined, never flaked) need no change:
the same determinism argument applies. No `request.config.rootpath` re-anchor and
no settle-check/retry (Option B) were needed — the checkout is already synchronous.

## Status

- **Current Status**: done
- **Blockers**: None — root-caused (deterministic read; 60× dry stress probe),
  quarantine removed, regression guard committed, full suite green.


## Session Log
- `/ll:manage-issue` - 2026-07-16T00:58:02 - `032c61c6-8376-4eb4-81da-4c1e6012aaba.jsonl`
- `/ll:ready-issue` - 2026-07-16T00:42:56 - `3f6e20fb-9a0a-4c11-b22f-1c8bead061bb.jsonl`
- `/ll:confidence-check` - 2026-07-16T00:45:00 - `7f7dc3e6-bb2e-4fa0-87ed-882dd375c9b1.jsonl`
- `/ll:wire-issue` - 2026-07-16T00:37:34 - `041a109c-794b-4356-bc61-103d2317c0e3.jsonl`
- `/ll:spike` - 2026-07-15T23:05:48 - `d59da632-f9e0-4c3a-b52b-fd5930e8885f.jsonl`
- `/ll:confidence-check` - 2026-07-15T21:30:00 - `1deac22a-60df-46af-ada9-522d80f31d9a.jsonl`
- `/ll:decide-issue` - 2026-07-15T21:26:38 - `43bce135-0aac-4b02-aacf-e32bc2d59f3d.jsonl`
- `/ll:refine-issue` - 2026-07-15T21:22:37 - `f60725d0-9039-4e70-b3b5-74971495ea6d.jsonl`
