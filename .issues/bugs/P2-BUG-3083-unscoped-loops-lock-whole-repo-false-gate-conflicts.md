---
id: BUG-3083
type: BUG
title: Unscoped issue-management loops lock the whole repo, false-conflicting every
  narrowly-scoped loop
priority: P2
status: done
captured_at: '2026-08-06T16:17:02Z'
discovered_date: 2026-08-06
discovered_by: capture-issue
verify_verdict: VALID
labels:
- fsm-concurrency
- learning-gate
- ll-auto
- loop-authoring
relates_to:
- BUG-2864
- ENH-3084
confidence_score: 93
outcome_confidence: 40
score_complexity: 5
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 0
size: Very Large
---

# BUG-3083: Unscoped issue-management loops lock the whole repo, false-conflicting every narrowly-scoped loop

## Summary

A loop YAML that omits `scope:` acquires a lock on the repository root
(`run.py:363` — `resolve_scope(fsm.scope or ["."], fsm.context)`). Because
`_paths_overlap()` treats "one path contains the other" as an overlap
(`concurrency.py:398-415`), a repo-root lock conflicts with *every* other loop
regardless of how narrowly that loop scoped itself. 84 of the 91 built-in loops
declare no `scope:`.

This is the holder-side half of BUG-2864. That fix narrowed the *callee*
(`ready-to-implement-gate` → `scope: ["${context.run_dir}"]`) and improved
diagnostics, but a narrow callee scope provides no protection while any
concurrent loop holds `["."]`.

Observed live on 2026-08-06: `ll-auto --only "ENH-3066,ENH-3073,ENH-3053,FEAT-3076"`
started 01:17:26; `refine-to-ready-issue` started 01:17:37 in a separate shell
and held the repo-root lock through 01:30
(`.loops/runs/refine-to-ready-issue-20260806T011737/`). At 01:18:47 the learning
gate for ENH-3073 shelled out `ll-loop run ready-to-implement-gate`, hit the
conflict, exited 1, and ENH-3073 was reported `IMPLEMENT_FAILED` without Phase 2
ever running.

## Steps to Reproduce

1. In one shell: `ll-loop run refine-to-ready-issue --context issue_file=<any issue>`
   and leave it running (it declares no `scope:`, so it locks `.`).
2. In a second shell: run `ll-auto --only <ID>` on an issue that has
   `learning_tests_required` in its frontmatter (so the learning gate actually
   fires — `issue_manager.py:1105-1112`).
3. Observe the gate subprocess exit 1 with
   `Scope conflict with running loop: refine-to-ready-issue` /
   `Conflicting scope: ['<repo root>']`, and `ll-auto` report
   `IMPLEMENT_FAILED <ID>` without attempting implementation.

## Root Cause

`little_loops.cli.loop.run.cmd_run` — `scope = resolve_scope(fsm.scope or ["."], fsm.context)`
(run.py:363). The `or ["."]` fallback means "loop author did not think about
scope" is silently promoted to "this loop owns the entire repository."

`refine-to-ready-issue.yaml` has no `scope:` key, and it is the loop most likely
to run concurrently with `ll-auto` — the two are halves of the same backlog
workflow (refine to ready → implement).

Ruled out during investigation:

- **Not a stale lock.** `find_conflict()` reaps locks whose PID is dead
  (`concurrency.py:247-250`); the refine process was alive (logs through 01:30).
- **Not the ancestry carve-out failing.** `concurrency.py:259` exempts ancestor
  PIDs, but the refine loop was a sibling process launched from a separate
  shell, not a parent.
- **Not an unresolved `${context.run_dir}`.** `run_dir` is injected into
  `fsm.context` at run.py:197-198, *before* lock acquisition at run.py:363, so
  the gate's narrow scope did resolve correctly. It simply cannot escape a
  containing `["."]`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **Confirmed exact fallback and lock-acquire chain** (`scripts/little_loops/cli/loop/run.py`, `cmd_run()`): `run_dir` is seeded into `fsm.context` at lines 189-198 (only if `"run_dir" not in fsm.context`), well before line 363's `scope = resolve_scope(fsm.scope or ["."], fsm.context)`. `LockManager(loops_dir)` is constructed at line 362; `lock_manager.acquire(fsm.name, scope, instance_id=instance_id, singleton=fsm.singleton)` is attempted at lines 370-373 unless `--no-lock`.
- **`resolve_scope()` itself does not resolve `"."`** — `fsm/concurrency.py:35-53` only substitutes `${context.<var>}` templates (`_CONTEXT_VAR_RE`); a literal `"."` passes through unchanged. The CWD resolution happens later, inside `LockManager._normalize_path()` (`fsm/concurrency.py:425-427`, `str(Path(path).resolve())`), called from both `acquire()` (line 165) and `find_conflict()` (line 238). `LockManager.acquire()` also carries its own defensive `if not scope: scope = ["."]` at lines 163-164 (redundant with the `cmd_run()` fallback but present at this layer too).
- **`_paths_overlap()` full logic** (`fsm/concurrency.py:398-423`, called via `_scopes_overlap()` at 390-396, an all-pairs check over two path lists): equal paths overlap (407-408); else `p1.relative_to(p2)` succeeding (p1 is p2 or a descendant) overlaps (411-414); else `p2.relative_to(p1)` succeeding overlaps (417-420); otherwise no overlap (423). Because the resolved repo-root path is an ancestor of every in-repo path, `p2.relative_to(p1)` always succeeds for any in-repo scope — this is the exact mechanism, not just "contains."
- **`find_conflict()` full path** (`fsm/concurrency.py:212-291`): iterates every `*.lock` file in `running_dir`; PID staleness reaping at lines 246-250 (`os.kill(pid, 0)`, `ESRCH` → dead/removed, any other outcome including `EPERM` → alive); scope-overlap check at 252-266 with ancestor-PID exemption at line 259 (`lock.pid in self._get_ancestry()`); a separate singleton-conflict predicate at 268-285 (BUG-2526) applies even without scope overlap, when `caller_singleton and lock.singleton and lock.loop_name == caller_loop_name`.
- **`gate_cwd`/repo-root resolution for the observed scenario**: `run_learning_gate_for_issue()` (`learning_tests/gate.py`) runs its subprocess with `cwd=working_dir`, and `issue_manager.py` sets `gate_cwd = config.repo_path or Path.cwd()` — for issue-management automation invoked from the repo root, this CWD is the project root, confirming `"."` resolves to the repo root in the observed scenario, not merely "typically."

## Current Behavior

Any loop without an explicit `scope:` blocks all concurrent loops repo-wide.
Two loops that touch entirely disjoint files cannot run at the same time,
defeating the disjoint-scope concurrency that ENH-1354/FEAT-1789 built.

## Expected Behavior

Concurrent loops with genuinely disjoint working sets run without conflict. A
loop that has not declared `scope:` should either (a) declare a real scope, or
(b) not be silently treated as owning the repo root.

## Proposed Solution

Two independent changes; (1) is the minimum fix, (2) is the durable one.

1. **Give the issue-management loops real scopes.** They operate on `.issues/`
   plus their own run dir, not the whole repo. At minimum
   `refine-to-ready-issue.yaml`, and audit the other issue-lifecycle loops
   (`issue-refinement.yaml`, `issue-discovery-triage.yaml`,
   `issue-staleness-review.yaml`, `auto-refine-and-implement.yaml`) against the
   pattern already used by `autodev.yaml` / `prompt-across-issues.yaml` /
   `rn-refine.yaml`:

   ```yaml
   scope:
     - ".issues/"
     - "${context.run_dir}"
   ```

2. **Stop defaulting to `["."]` silently.** Options to weigh:
   - `ll-loop validate` warns when a loop declares no `scope:` (mirrors the
     MR-1..MR-14 lint surface), so new loops get a scope at authoring time.
   - Narrow the implicit default to `["${context.run_dir}"]` and require an
     explicit `scope: ["."]` for loops that genuinely mutate the whole repo.
     This is a behavior change and needs a sweep of the 84 unscoped loops
     first — many are generators that mutate nothing tracked, but some
     (`fix-quality-and-tests.yaml`, `incremental-refactor.yaml`) legitimately
     want a broad scope.

Do not treat `--queue` as the fix. It converts a hard failure into a long wait
and is orthogonal to loops over-claiming scope (see BUG-3085).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **Correction — the cited existing pattern does not exist verbatim.** A repo-wide search of `scope:` blocks under `scripts/little_loops/loops/**/*.yaml` found no loop declaring `.issues/` as a scope entry anywhere. Only 7 loops declare `scope:` at all: `autodev.yaml`, `rn-refine.yaml`, `docs-sync.yaml`, `ready-to-implement-gate.yaml`, `proof-first-task.yaml`, `dead-code-cleanup.yaml`, `prompt-across-issues.yaml` — and they disagree on shape, not just content:
  - `scope: ["${context.run_dir}"]` only (no `.issues/`): `autodev.yaml:26-27`, `prompt-across-issues.yaml:34-35`, `ready-to-implement-gate.yaml:13-14`, `proof-first-task.yaml:11-12`, `dead-code-cleanup.yaml:11-12`.
  - `scope: ["${context.plan_file}"]` — a single-file scope: `rn-refine.yaml:31-32`.
  - `scope: ["docs/", "*.md"]` — a literal directory/glob scope, no interpolation: `docs-sync.yaml:10-12`.
  - `scripts/little_loops/loops/README.md:34` documents the `autodev` choice in prose: "Uses per-instance `${context.run_dir}` ... to allow concurrent instances with disjoint issue sets" — this is the closest thing to a stated rationale in the codebase, and it argues for `${context.run_dir}` alone, not a combined `.issues/` + run_dir scope.
  - Implication for Option 1: adding `.issues/` to the issue-lifecycle loops' scope is a new scope shape, not a precedent-following one — it should be justified on its own (these loops read/write issue files outside their own run_dir, which `${context.run_dir}`-only scoping wouldn't cover), not cited as "the pattern already used."
- **Prior precedent for this exact fix shape**: BUG-2864 (status: done) is the callee-side half of this same bug — it added `scope: ["${context.run_dir}"]` to `ready-to-implement-gate.yaml` and `proof-first-task.yaml`, "matching `autodev.yaml`/`prompt-across-issues.yaml`" (its own citation names only these two, not three, and not `.issues/`).
- **Existing structural-enforcement precedent for change 2** (lint warning path): `test_builtin_loops.py` already has a per-loop-class `test_scope_declared` method (`TestPromptAcrossIssuesLoop` line 2837, `TestReadyToImplementGateLoop` line 9713, `TestProofFirstTaskLoop` line 9938) asserting `scope` is a list containing `"${context.run_dir}"`. This is a per-loop pytest assertion, not a suite-wide `ll-loop validate` lint rule — extending it to a validation-layer warning would follow the shape of `_validate_input_key_without_guard` (`fsm/validation/structural_rules.py:1195-1217`), the closest existing precedent for a "declared X but missing companion Y" `ValidationSeverity.WARNING` rule (single-condition early-return, one `ValidationError`, actionable message).

## Integration Map

| File | Anchor | Change |
|------|--------|--------|
| `scripts/little_loops/loops/refine-to-ready-issue.yaml` | top-level keys | Add `scope:` |
| `scripts/little_loops/cli/loop/run.py` | `cmd_run`, line 363 | Default-scope policy |
| `scripts/little_loops/fsm/validation.py` | loop lint rules | Optional no-scope warning |
| `scripts/tests/test_fsm_concurrency.py` | — | Regression: two disjoint-scope loops coexist |

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_helpers.py:1552` — `run_background()` has an independent, second occurrence of the identical `resolve_scope(fsm.scope or ["."], scope_context)` fallback (the pre-flight check used for `--background` runs), plus its own `"Scope conflict with running loop"` / `"Conflicting scope"` print at lines 1559-1560. Needs the same "change 2" treatment as `run.py:363` to stay consistent. [Agent 1/2 finding]
- `scripts/little_loops/fsm/concurrency.py:163-164` — `LockManager.acquire()` carries its own redundant `if not scope: scope = ["."]` defensive fallback at the lock-manager layer, independent of both CLI-layer fallbacks; a "narrow the default" fix at the CLI layer alone would leave this un-narrowed. [Agent 2 finding]
- `scripts/little_loops/cli/loop/info.py:1540-1541` — `cmd_info`'s loop-detail display only prints a `scope:` line when `fsm.scope` is truthy; it does not reflect the resolved effective scope (i.e. an unscoped loop still shown as having no scope, though it locks the repo root at runtime). [Agent 2 finding]
- `scripts/little_loops/cli/sprint/run.py:198-262` — `_run_learning_gate_preflight()` shells out to `ll-loop run ready-to-implement-gate` the same way `learning_tests/gate.py` does, but with no `--queue` and no inline comment acknowledging the scope-conflict mechanism; a non-zero exit here aborts the entire sprint dispatch. [Agent 2 finding]
- `scripts/little_loops/parallel/worker_pool.py:52-89` — `_run_per_worktree_proof_first_gate()` explicitly says (line 66) it "mirrors the ordering in `cli/sprint/run.py:_run_learning_gate_preflight`" and has the same gap — no scope-conflict awareness. [Agent 2 finding]
- `scripts/little_loops/learning_tests/gate.py:127-133` — inline comment already documents this exact bug as a known caveat; once `refine-to-ready-issue.yaml` gains a real `scope:` (Proposed Solution change 1), this comment's premise becomes partially stale for that specific loop and should be revisited. [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:786-816,848-849` — "Scope-Based Concurrency" section documents `scope:` mechanics but has no mention of the current `["."]` default-when-absent behavior; the "Notes" bullet at line 849 ("Loops with non-overlapping scopes run concurrently") is inaccurate for any unscoped loop today. [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md:812-827,1285` — existing "Scope conflict" troubleshooting entries describe stale-lock symptoms only, not the false-conflict-from-unscoped-loop mechanism this bug fixes. [Agent 2 finding]
- `docs/reference/API.md:5179,6162-6207` — mirrors `FSMLoop.scope` field docstring and the `LockManager`/`resolve_scope` reference block; would go stale if the fallback's shape (not just its default value) changes. [Agent 2 finding]
- `docs/reference/CLI.md:789-812` — enumerates every `ll-loop validate` structural/meta-loop lint rule in a fixed format (severity, trigger, rationale, suppression flag); a new no-scope WARNING rule (change 2, option A) must be added here in the same format. [Agent 2 finding]
- `scripts/little_loops/loops/README.md:28-34` — documents `autodev`'s `scope: ["${context.run_dir}"]` rationale in prose but has no equivalent note for the issue-lifecycle loops this bug scopes. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_concurrency.py::TestMultiInstanceSameName` — new pair `test_refine_to_ready_issue_with_run_dir_scopes_both_acquire_concurrently` / `test_refine_to_ready_issue_with_dot_scope_still_conflicts`, mirroring the existing `autodev`/`ready-to-implement-gate` pairs at lines 605-667/669-730 exactly (real `LockManager(tmp_loops)`, two `threading.Thread`s + `threading.Barrier(2)`). [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::TestRefineToReadyIssueSubLoop` (line 1242) — add a `test_scope_declared` method; the class and its `data` fixture already exist but no scope test does. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — add `test_scope_declared` to `TestIssueRefinementSubLoop` (line 1144), `TestIssueStalenessReviewLoop` (line 10534), `TestRecursiveRefineLoop` (line 7085), `TestAutoRefineAndImplementLoop` (line 2867) if Implementation Step 1's audit scopes these loops too; `issue-discovery-triage.yaml` has no dedicated test class yet (only a string entry in `TestBuiltinLoopFiles.test_expected_loops_exist`, line 125) — a new small class is needed if it gets scoped. [Agent 3 finding]
- `scripts/tests/test_cli_loop_background.py::TestRunBackground` — `test_scope_conflict_returns_1` (line 671), `test_no_lock_bypasses_scope_conflict` (line 733), `test_queue_bypasses_preflight_check` (line 706) are **break-risk**, not just coverage: they rely on the `my-loop.yaml` fixture (line 190-197, no `scope:` field) resolving to `["."]` and conflicting with a `["."]`-scoped `blocker` lock. If Implementation Step 4 narrows the default-scope fallback, this fixture and these three tests need to be updated or the conflict stops firing. [Agent 3 finding]
- `scripts/tests/test_fsm_validation_structural.py::TestRequiredInputsValidation` (line 1539) — pattern to follow if change 2's lint-warning option is chosen: `_make_fsm()` helper, direct-call trigger/non-trigger tests, plus `..._wired_into_validate_fsm` variants asserting dispatch from `validate_fsm()`. [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **Stale test reference**: Integration Map's existing row cites `scripts/tests/test_fsm_concurrency.py` — this file does not exist. Concurrency tests live in `scripts/tests/test_concurrency.py`; the two-loop lock conflict/coexistence pattern lives in `class TestMultiInstanceSameName` (`test_concurrency.py:544`), with two already-landed pairs from BUG-2864 to mirror: `test_autodev_with_run_dir_scopes_both_acquire_concurrently` / `test_autodev_with_dot_scope_still_conflicts` (`:605-667`) and `test_ready_to_implement_gate_with_run_dir_scopes_both_acquire_concurrently` / `test_ready_to_implement_gate_with_dot_scope_still_conflicts` (`:669-~730`). Pattern: real `LockManager(tmp_loops)` against real `tmp_path`, two `threading.Thread`s coordinated by `threading.Barrier(2)`, assert on `results.count(True)`.
- **Separate structural test file**: `scripts/tests/test_builtin_loops.py` carries the non-concurrency structural counterpart — a per-loop-class `test_scope_declared` method asserting `scope` is a list containing `"${context.run_dir}"` (present for `TestPromptAcrossIssuesLoop` line 2837, `TestReadyToImplementGateLoop` line 9713, `TestProofFirstTaskLoop` line 9938 — each citing its originating issue ID). No such method exists yet for `autodev.yaml`/`dead-code-cleanup.yaml` despite them declaring `scope:`, nor for any of the issue-lifecycle loops this bug targets.
- **Existing "sweep all loops" idiom** (for Implementation Step 1's audit): `class TestBuiltinLoopFiles` in `test_builtin_loops.py:29-38` supplies a `builtin_loops` fixture — `sorted(p for p in BUILTIN_LOOPS_DIR.rglob("*.yaml") if is_runnable_loop(p))` — reused by sweep tests like `test_all_parse_as_yaml`, `test_all_validate_as_valid_fsm`, `test_no_failure_edge_routes_to_a_success_terminal` (`:57-96`, using an `offenders: list[str]` accumulate-then-single-assert idiom for a sweep expected to flag multiple files at once). `is_runnable_loop()` itself is at `structural_rules.py:1456-1483`.
- **Exact scope-declaring loop set** (7 total, not 9): `autodev.yaml`, `rn-refine.yaml`, `docs-sync.yaml`, `ready-to-implement-gate.yaml`, `proof-first-task.yaml`, `dead-code-cleanup.yaml`, `prompt-across-issues.yaml`. None declare `.issues/` in scope — see Proposed Solution findings below.
- **Learning gate subprocess build**: the actual `ll-loop run ready-to-implement-gate --context targets=... --queue` invocation lives in `scripts/little_loops/learning_tests/gate.py`, `run_learning_gate_for_issue()` (lines 65-196, subprocess build ~120-134). Its inline comment (lines 127-132) already documents this exact BUG-3083 mechanism as a known caveat, dated to the ENH-3073 follow-up — i.e. the gate's own source acknowledges the bug this issue tracks.
- **FSMLoop.scope field**: `scripts/little_loops/fsm/schema.py:1278` — `scope: list[str] = field(default_factory=list)` on the `FSMLoop` dataclass (starting line 1249); docstring at line 1260 documents `${context.<var>}` template support.

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **`fsm/validation.py` path is stale**: it was split into a package by ENH-2774. Current location: `scripts/little_loops/fsm/validation/` — `meta_rules.py` (MR-1..MR-6), `structural_rules.py` (structural checks + `validate_fsm()`/`load_and_validate()` entry points), `evaluator_rules.py` (MR-8/10/12/13), `shell_safety.py` (MR-7/9/11), `reachability.py`. A "no-scope warning" lint rule (Proposed Solution change 2) would live in `structural_rules.py`, following the shape of `_validate_input_key_without_guard` (`structural_rules.py:1195-1217`) — single-condition early-return, one `ValidationError(severity=ValidationSeverity.WARNING)`, re-exported through `validation/__init__.py`'s `__all__`.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Types
- `FSMLoop.scope: list[str] = field(default_factory=list)` — `scripts/little_loops/fsm/schema.py:1278` (dataclass starts line 1249); parsed 1:1 from the loop YAML's `scope:` key. Docstring (line 1260): "Paths this loop operates on (for concurrency control). Supports `${context.<var>}` template variables that are resolved at runtime."
- `ScopeLock` — dataclass persisted as `running_dir/<instance_id or loop_name>.lock` JSON via `to_dict()`/`from_dict()` (`fsm/concurrency.py`); carries `pid`, `loop_name`, `singleton`, and the normalized `scope` list read back by `find_conflict()`.

### Signatures
- `resolve_scope(scope: list[str], context: dict[str, Any]) -> list[str]` — `fsm/concurrency.py:35-53`
- `LockManager.acquire(self, loop_name: str, scope: list[str], *, instance_id: str | None = None, singleton: bool = False) -> bool` — `fsm/concurrency.py:142-200`
- `LockManager.find_conflict(self, scope: list[str], *, caller_loop_name: str | None = None, caller_singleton: bool = False) -> ScopeLock | None` — `fsm/concurrency.py:212-291`
- `LockManager._scopes_overlap(self, scope1: list[str], scope2: list[str]) -> bool` — `fsm/concurrency.py:390-396`
- `LockManager._paths_overlap(self, path1: str, path2: str) -> bool` — `fsm/concurrency.py:398-423`
- `LockManager._normalize_path(path: str) -> str` — `fsm/concurrency.py:425-427`

### Call Path
`cli/loop/run.py:cmd_run()` line 363 (`scope = resolve_scope(fsm.scope or ["."], fsm.context)`) -> `LockManager.acquire()` (lines 370-373) -> `LockManager.find_conflict()` -> `LockManager._scopes_overlap()` -> `LockManager._paths_overlap()` -> on conflict, `cmd_run()` exits non-zero -> `learning_tests/gate.py:run_learning_gate_for_issue()` subprocess sees non-`FAILURE_TERMINAL_EXIT_CODE` exit -> returns `"impl_failed"` -> `issue_manager.py` lines ~1130-1147 prints `IMPLEMENT_FAILED {issue_id}` and returns a failure result.

### Decision Rules
N/A — no new runtime decision logic. Proposed Solution's "change 2" is an authoring-time implementation choice (lint warning vs. narrowed default) explicitly left open as unresolved options to weigh, not a keyword/threshold/gate the implementer must pin down now.

## Implementation Steps

1. Audit the 84 `scope:`-less loops and classify: genuinely repo-wide vs.
   should-be-narrow. Record the classification in the issue before editing.
2. Add `scope:` to the issue-lifecycle loops (change 1).
3. Add a regression test asserting `refine-to-ready-issue` and
   `ready-to-implement-gate` can hold locks simultaneously.
4. Decide on change 2 (lint warning vs. default narrowing) and implement.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/loop/_helpers.py` (`run_background()`, line 1552) — the `--background` pre-flight path has its own independent `fsm.scope or ["."]` fallback; any "change 2" default-narrowing must be applied here too, not just in `cmd_run()` (`run.py:363`), or the two paths diverge.
- Audit `scripts/little_loops/loops/issue-refinement.yaml`, `issue-staleness-review.yaml`, `recursive-refine.yaml`, `auto-refine-and-implement.yaml`, and `issue-discovery-triage.yaml` alongside `refine-to-ready-issue.yaml` for Implementation Step 1 — all six confirmed to currently lack `scope:` (per `grep -l '^scope:' scripts/little_loops/loops/*.yaml`, which returns only the 7 loops already cited in this issue's Codebase Research Findings).
- Add `test_scope_declared` to each existing test class for the loops that get scoped: `TestRefineToReadyIssueSubLoop` (`test_builtin_loops.py:1242`), `TestIssueRefinementSubLoop` (`:1144`), `TestIssueStalenessReviewLoop` (`:10534`), `TestRecursiveRefineLoop` (`:7085`), `TestAutoRefineAndImplementLoop` (`:2867`); add a new class for `issue-discovery-triage.yaml` if it is scoped (no existing class).
- If Implementation Step 4 narrows the default-scope fallback, update the break-risk fixture/tests in `scripts/tests/test_cli_loop_background.py::TestRunBackground` (`test_scope_conflict_returns_1`, `test_no_lock_bypasses_scope_conflict`, `test_queue_bypasses_preflight_check`) so their `my-loop.yaml` fixture still exercises a genuine conflict.
- Update `scripts/little_loops/learning_tests/gate.py`'s inline comment (lines 127-133) once `refine-to-ready-issue.yaml` is scoped — its premise becomes partially stale for that specific loop.
- If change 2's lint-warning option is chosen, wire the new rule into `scripts/little_loops/fsm/validation/__init__.py`'s `__all__` and document it in `docs/reference/CLI.md`'s `ll-loop validate` rule catalog (lines 789-812), following the existing fixed format (severity/trigger/rationale/suppression flag).
- Update `docs/guides/LOOPS_GUIDE.md` (Scope-Based Concurrency section, lines 786-816, 848-849) and `scripts/little_loops/loops/README.md` (lines 28-34) to reflect the new default and/or newly-scoped loops.

## Impact

- **Severity**: silent, non-deterministic loss of automated work. ENH-3073 was
  marked `IMPLEMENT_FAILED` with no implementation attempted, and the failure
  reason surfaced as "implementation failed" — actively misleading.
- **Blast radius**: any concurrent `ll-auto` + refine workflow. Only issues
  carrying `learning_tests_required` hit the gate, so it presents as an
  intermittent, issue-specific failure rather than an obvious concurrency bug.
- **Under `autodev`**, `IMPLEMENT_FAILED` routes to remediation rather than
  retry, so contention consumes a remediation cycle.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM concurrency / scope-lock design |
| `.claude/CLAUDE.md` § Loop Authoring | Where a `scope:` authoring rule would live |

## Status

done

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-08-06
- **Reason**: Issue too large for single session (score 8/11, Very Large)

### Decomposed Into
- BUG-3087: Scope the issue-lifecycle loops so they stop locking the repo root
- BUG-3088: Stop silently defaulting unscoped loops' lock to the repo root

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-06_

**Readiness Score**: 93/100 → PROCEED
**Outcome Confidence**: 40/100 → LOW

### Outcome Risk Factors
- Broad blast radius: the fallback-narrowing half of "change 2" touches at least two independent CLI-layer fallback sites (`run.py:363`, `_helpers.py:1552` `run_background()`) plus `LockManager.acquire()`'s own defensive `["."]` fallback (`concurrency.py:163-164`), `info.py`'s scope display, and two preflight-gate callers (`cli/sprint/run.py`, `parallel/worker_pool.py`) — a change here that misses one site leaves it un-narrowed while the others move.
- "Change 2" (lint warning vs. narrowed default) is an explicitly unresolved design decision (see Decision Rules: "left open as unresolved options to weigh") — whichever option is picked mid-implementation will drive materially different Criterion D blast radius and test-fixture churn (`test_cli_loop_background.py`'s break-risk tests depend on which option is chosen).
- If default-narrowing is chosen, three named tests in `test_cli_loop_background.py::TestRunBackground` (`test_scope_conflict_returns_1`, `test_no_lock_bypasses_scope_conflict`, `test_queue_bypasses_preflight_check`) rely on the current `["."]` fallback and need coordinated updates or they'll start asserting a conflict that no longer fires.

## Session Log
- `/ll:issue-size-review` - 2026-08-06T16:59:24 - `23212449-a121-4dca-9bc5-bc0a0164c75f.jsonl`
- `/ll:confidence-check` - 2026-08-06T16:56:28 - `3b41b5be-91aa-492c-a828-7f1bd5915392.jsonl`
- `/ll:verify-issues` - 2026-08-06T16:54:03 - `d9606028-5f64-4d2f-85f1-3dd39a6ef770.jsonl`
- `/ll:wire-issue` - 2026-08-06T16:51:39 - `5049911c-bc17-42e5-a63c-2f7e9cfb7d40.jsonl`
- `/ll:refine-issue` - 2026-08-06T16:39:06 - `86683c6f-e26b-48ab-8d60-55f38cef990f.jsonl`
- `/ll:capture-issue` - 2026-08-06T16:20:22 - `ee676905-966c-42aa-ac9d-d7d4aaeea91d.jsonl`
