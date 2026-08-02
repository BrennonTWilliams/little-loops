---
id: ENH-2853
title: Deterministic pre-patch test-failure check in verification loops
type: ENH
priority: P2
status: open
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
blocked_by:
- ENH-2866
learning_tests_required:
- pytest
confidence_score: 82
outcome_confidence: 60
score_complexity: 14
score_test_coverage: 16
score_ambiguity: 14
score_change_surface: 16
---

# ENH-2853: Deterministic pre-patch test-failure check in verification loops

Origin: ll-product #ENH-051

## Summary

A test that passes on the pre-change tree proves nothing about the change. Add a deterministic check that runs newly added or modified tests against the **pre-patch** code and requires them to fail there before a verification loop may treat them as evidence.

This is a non-LLM check and belongs in `ll-harness`, `/ll:verify-issue-loop`, and the verification-evidence bundle, alongside the existing semantic criteria rather than replacing them.

## Current Behavior

Verification loops (`/ll:verify-issue-loop`, `ll-harness`) judge new or modified tests only with LLM-judged `llm_structured`/`check_semantic` criteria. There is no deterministic check of whether a candidate test actually fails without the change it claims to demonstrate — a test that passes on both the pre-patch and post-patch tree is accepted as evidence with no mechanism to flag it.

## Expected Behavior

Before a newly added or modified test counts as verification evidence, it is run against the pre-patch tree (per Design Notes: dequeue-time SHA, or merge-base fallback) in an isolated worktree with only the test-file portion of the diff applied. A newly added test that passes there is hard-flagged and excluded from evidence; a modified test that passes there is recorded as a soft flag by default. Per-test outcomes (pass/fail/error, category) are written into the verification evidence bundle per Acceptance Criteria, and the check can be disabled via a config off-switch that itself leaves an explicit skip record.

## Motivation

The most common way an agent fakes verification is writing a test that passes before and after the change. It costs nothing, it turns the suite green, and every downstream signal — transition predicates, evidence bundles, success rates — reads it as proof. Semantic criteria do not catch it reliably because the test genuinely looks correct in isolation; the defect is only visible relative to the pre-change tree.

The check is deterministic and cheap, and its dominant false-positive mode is narrow: a genuinely flaky or environment-dependent test can pass pre-patch by luck and eat a hard flag it doesn't deserve. A single confirmation re-run of pass-pre-patch candidates (see Design Notes) bounds that case; everything else that passes pre-patch is exactly what should be flagged.

## Proposed Change

1. **Identify the candidate tests** — from the diff of the verification step, collect test functions that were added or modified.
2. **Reconstruct the pre-patch tree** — check out the base state in an isolated worktree, then apply *only* the test changes onto it.
3. **Run the candidate tests there** and record per-test pass/fail.
4. **Verdict** — any candidate test that *passes* against the pre-patch tree is flagged. The loop must not count it as evidence; the transition either fails or the test is excluded from the evidence set, per configuration.
5. **Report** — emit per-test results (name, file, pre-patch outcome, post-patch outcome) into the verification evidence bundle so the check is auditable without re-running it.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Keep any `setup_worktree()`/`cleanup_worktree()` signature change additive — `scripts/little_loops/fsm/executor.py`, `scripts/little_loops/cli/loop/run.py`, and `scripts/little_loops/parallel/orchestrator.py` all call these directly today and are outside this issue's primary files.
7. Update `skills/verify-issue-loop/SKILL.md` to document the new deterministic state type this issue introduces, adding a state-template example. (Note, verified 2026-07-29: the "no deterministic state type" boundary text the wiring pass cited at SKILL.md lines 211-219 no longer exists — the skill has been restructured and is now 212 lines with no `check_invariants`/`check_stall`/`check_concrete` mention. The substantive constraint stands: the skill only emits LLM-judged `llm_structured` states today — SKILL.md ~L150-165 and `templates.md` — so the work is additive documentation plus a template, not reconciling a prohibition.)
8. ~~Schema-presence test for `project.test_patterns`~~ — moved to **ENH-2973**.
9. ~~Per-language `project.test_patterns` template defaults~~ — moved to **ENH-2973**.

## Design Notes

- Apply *only* the test-file portion of the diff to the base tree. Applying the full diff defeats the purpose; applying nothing means the tests don't exist to run.
- A candidate test that **errors** on the pre-patch tree (import error because the new module doesn't exist yet) counts as failing — that is the expected outcome for a test of new code, not a harness problem. Distinguish error-vs-fail in the report but treat both as "did not pass".
- **Error-category false-negative hole (epic review, 2026-07-27).** "Errors pre-patch is accepted as evidence" also accepts a fake test that errors for *infrastructure* reasons — e.g. it depends on a fixture added in `conftest.py` that wasn't applied because `conftest.py` doesn't match typical `test_*` globs. Two mitigations are required: (1) the default `project.test_patterns` and the shared identification module MUST include `conftest.py`; (2) the evidence bundle records the error *category* — a collection/import error naming a post-patch module (expected failure of new code) vs. anything else (fixture/infrastructure error, suspicious) — so an auditor can tell them apart without re-running.
- **Diff-scope caveat, same class of hole**: applying only the test-file portion of the diff means new *non-test* helpers a test imports are absent pre-patch. Import errors referencing non-target modules should be treated with suspicion in the report, not read as clean evidence.
- Use an isolated worktree rather than mutating the working tree in place; a verification check must never leave the user's tree in a different state than it found it.
- Pure-refactor changes may legitimately have no new tests. Zero candidate tests is not a failure — report it explicitly rather than silently passing, so "no tests were added" is visible.
- Keep this independent of any LLM call. The whole value is that the signal is mechanical.
- **Price the check: run only the candidate tests, never the suite** (added 2026-07-27). The pre-patch run's cost profile is a worktree checkout + partial diff apply + a pytest invocation per verification step, per issue, in batch runs — minutes per issue if the whole suite runs. The pre-patch invocation must target only the candidate test node IDs (`pytest <nodeid> ...`), which the diff analysis already identifies. Additionally, ship a config off-switch (a single enable/disable knob for the check) for hosts where even the targeted run is too slow; when disabled, the evidence bundle records "pre-patch check skipped by config" rather than silently omitting the section.
- **Time-box the pre-patch invocation** (added 2026-07-29). A candidate test can *hang* pre-patch — it may wait on a fixture, port, or blocking call that only exists post-patch. Without a timeout, one such test stalls an entire batch run. The pre-patch pytest invocation must be time-bounded (a fixed per-invocation timeout, configurable alongside the off-switch), and a timeout is recorded as its own outcome category in the evidence bundle — treated as "did not pass" but labeled distinctly from both failure and error so an auditor can tell "the test couldn't run to completion" apart from "the test ran and failed."
- **Confirm passes with one re-run before hard-flagging** (added 2026-07-29). The hard flag on an added test that passes pre-patch is the check's only real false-positive mode: a flaky or timing-dependent test can pass pre-patch by luck. Run pass-pre-patch candidates a second time and hard-flag only on a repeated pass; a pass-then-fail outcome is recorded as flaky in the evidence bundle and soft-flagged. The re-run is cheap because it targets the same already-identified node IDs.
- **Hunk→nodeid mapping is the identification step's real complexity** (added 2026-07-29). "Collect test functions that were added or modified from the diff" is file-level trivial and function-level non-trivial: deciding *which* test functions a diff hunk modifies requires either AST-mapping hunk line ranges to enclosing test definitions or a `--collect-only` diff between trees. Pin the approach during implementation and define the fallback explicitly: when function-level attribution is ambiguous (hunks outside any function body, conftest changes, shared fixtures), fall back to running all test node IDs of the touched *files* — still never the full suite.
- **Added vs. modified tests carry different contracts.** A *newly added* test must fail pre-patch — that is the clean "demonstrates the change" contract. A *modified* test routinely passes pre-patch legitimately (an assertion added to an already-passing test, a tightened comparison, a rename). Split the verdict: added-and-passes-pre-patch is a hard flag; modified-and-passes-pre-patch is recorded in the evidence but soft by default (configurable to hard). A hard flag on modified tests would punish exactly the assertion-strengthening behavior the epic wants to encourage.
- **Import isolation is load-bearing in editable-install repos.** A worktree checkout of the pre-patch tree can still import the *main-tree* package when the project is installed editable (the install pins an absolute path — see the epic-verify false-negative history in this repo). A "pre-patch" run that imports post-patch code passes trivially and the check reports garbage. The pre-patch run must resolve imports from the worktree (PYTHONPATH injection ahead of site-packages, or a fresh non-editable install into the worktree's environment), and a test must prove the isolation.
- **Define the base state explicitly.** Under `ll-auto`/`ll-sprint` a verification step may span multiple commits. "Pre-patch" means the tree at the SHA recorded when the issue was dequeued (fall back to merge-base with the base branch when no dequeue SHA is recorded) — not simply `HEAD~1`.
- **The dequeue-SHA stamp is ENH-2866, not this issue** (split at epic review, 2026-07-27). Nothing records a dequeue SHA today, so this issue's primary base-state path would be dead code without it; ENH-2866 adds the stamp at `autodev.yaml`'s `dequeue_next` and `ll-parallel`'s worktree creation, plus a reader helper that returns `None` when unstamped. This issue *consumes* that helper and implements the merge-base fallback behind it. Until a given orchestrator stamps, its runs take the fallback — which is why the evidence bundle must name the base actually used.
- **Test-file identification is ENH-2973, not this issue** (split at epic review, 2026-07-27). Both this check and ENH-2854's tamper guard need to classify paths as test files; the `project.test_patterns` config key, its template defaults (including the load-bearing `conftest.py` entry), and the shared `test_file_patterns.py` module land once in ENH-2973 and are consumed here. This removes the former circular `blocked_by` between this issue and ENH-2854 — neither depends on the other now; both depend on ENH-2973.
- **Gate placement: the check must be hosted by a reusable oracle loop, not by `ll-harness`** (placement review, 2026-07-30). The prior Integration Map installed the check in `cli/harness.py:_evaluate_and_report()` and in `/ll:verify-issue-loop`'s generator. Both are off every production verification path:
  - **No orchestrator invokes `ll-harness`.** A repo-wide grep for `ll-harness` across `scripts/little_loops/` returns only its own CLI (`cli/harness.py`), the shared `runner_spec.py` abstraction, telemetry readers (`history_reader.py:2797+`), and a permission string in `init/writers.py:70`. Nothing in `ll-auto`, `ll-parallel`, `ll-sprint`, or any `loops/*.yaml` calls it — it is a hand-run one-shot tool.
  - **`/ll:verify-issue-loop` is a generator.** A check emitted there exists only inside per-issue loop YAML someone chose to generate, never in a standing path.
  - The actual chokepoint for "did these tests prove anything" is `oracles/code-run-gate.yaml`'s `run_test` state, delegated to by `rn-refine.yaml:483`, `rn-remediate.yaml:543`, and `rn-implement`'s `run_code_gate` (`loops/README.md:64`). Hosting the check there is what makes it reachable from every green-suite transition in the `rn-*` family.
  - **Follow the learning-test gate's three-layer shape**, which is this repo's established pattern for a gate that must reach both FSM and CLI callers: gate logic in a reusable internal loop (`ready-to-implement-gate.yaml`), a thin Python adapter that shells out to it (`learning_tests/gate.py:run_learning_gate_for_issue()`), and orchestrator hooks that all call the adapter behind one shared skip flag (`cli_args.py:214` → `issue_manager.py:880`, `worker_pool.py:64`, `cli/sprint/run.py:222`). `cli/harness.py` and `/ll:verify-issue-loop` become *consumers* of the oracle, not owners of the check.
- **Evidence-bundle transport follows the host** (placement review, 2026-07-30). With the check hosted by an oracle rather than `ll-harness`, `PrePatchEvidence` can no longer ride a harness-local `HarnessEvalOutcome`. It must reach the parent through the oracle's existing parent↔sub-loop token channel (the `subloop_outcome_<ID>.txt` idiom `code-run-gate` already uses) with the full bundle written under `${context.run_dir}/` per MR-3, and/or persisted to `.ll/history.db`. The harness path then reads the same artifact rather than producing its own.
- **Oracle skip convention** (placement review, 2026-07-30). If the check lands as an additive state inside `code-run-gate.yaml` rather than a sibling oracle, its enable/disable knob must follow that oracle's established null-command short-circuit: an unset parameter routes to a SKIP pass-through, not a failure. This is the same mechanism as the config off-switch already required by Design Notes ("Price the check"), expressed in the oracle's idiom.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- No existing code implements this check. Each surface the issue touches has adjacent, reusable machinery rather than a blank slate:
  - **`ll-harness`** (`scripts/little_loops/cli/harness.py`) has no per-test evidence bundle today — only a single-check `HarnessEvalOutcome` dataclass (`harness.py:242-248`) produced by `_evaluate_and_report()` (`harness.py:251-317`), with exit-code and single-LLM-semantic evaluators only (`harness.py:269-278`). `_record_harness_event()` (`harness.py:57-83`) persists a flat single-row event, not a multi-test table — any evidence bundle for this issue is new structure, not an extension of an existing one.
  - **`/ll:verify-issue-loop`** (`skills/verify-issue-loop/SKILL.md`) synthesizes purely LLM-judged `llm_structured` states per acceptance criterion (~L150-165, plus the state templates in `templates.md`) and documents no deterministic state type. (Line refs verified 2026-07-29 — the skill was restructured after the wiring pass; an earlier `check_semantic` reference and the L92-112/L218-219 cites are stale.) A pre-patch check is a net-new state type this skill's generator doesn't currently emit.
  - **`autodev.yaml`'s `dequeue_next`** (lines 80-141) already snapshots pre-refine readiness to `${context.run_dir}/autodev-pre-readiness.txt` (lines 104-117, per FEAT-2751) — confirming the pattern this issue's dequeue-SHA stamp should follow — but captures no `git rev-parse HEAD` anywhere; the dequeue-time SHA stamp this issue calls for is genuinely new.
  - **`ll-parallel`** (`scripts/little_loops/cli/parallel.py`) has no direct worktree calls itself; it delegates to `little_loops.parallel.worker_pool`/`orchestrator` for lifecycle and to the shared primitive `setup_worktree()` in `scripts/little_loops/worktree_utils.py:155-267`. No commit SHA is captured at the point a per-issue worker's worktree is created.
- **Reusable worktree substrate**: `setup_worktree()` (`worktree_utils.py:155`) / `cleanup_worktree()` (`worktree_utils.py:270`) are the shared create/teardown primitives already used by `ll-parallel`, `ll-sprint`, and `ll-loop`. `setup_worktree()` accepts an optional `base_branch: str | None` validated via `git rev-parse --verify` (lines 201-208) and forks a worktree from it — this is the exact "fork from a dequeue-time SHA" hook this issue needs; no partial-diff/`git apply` helper exists anywhere in the codebase today (repo-wide `git apply` grep returns zero hits), so "apply only the test-file portion of the diff onto the base tree" is new logic to write on top of this primitive.
- **Closest structural analog**: `verify_epic_branch_before_merge()` (`worktree_utils.py:364-494`) already implements the create → run-in-isolation → teardown-in-`finally` shape this issue's Design Notes describe (worktree at lines 433-442, test/lint run at 475-491, teardown at 493-494 regardless of outcome) — not directly reusable (it checks out an *existing branch*, not a "base SHA + partial diff" state), but it's the template to follow for "never leave the user's tree different than it found it."
- **Editable-install import isolation — direct precedent, not a new problem**: `verify_epic_branch_before_merge()`'s `src_dir` parameter (`worktree_utils.py:399-409`, applied at 467-473) already solves exactly the failure mode this issue's Design Notes flag: an editable install's `_editable_impl_*.pth` hardcodes the main tree's absolute source path at interpreter startup regardless of `cwd`, so an unguarded pre-patch worktree run would still import main-tree modules. The fix — prepend `str(worktree_path / src_dir)` to `PYTHONPATH` ahead of the `.pth`-injected path — is the pattern to reuse directly. This was tracked as three linked bugs worth reading before implementing: `BUG-2629` (original false-negative), `BUG-2640` (stale main-tree source symptom), `BUG-2649` (added `LL_VERIFY_GATE=1` env marker at `worktree_utils.py:454-455` so tests sensitive to the injected PYTHONPATH/xdist-worktree combination can self-quarantine).
- **Per-test pass/fail/error classification — two existing patterns to choose between, neither currently wired to a pre/post-patch comparison**:
  - `scripts/little_loops/loops/oracles/code-run-gate.yaml`'s `run_test` state (lines 201-249) shells out to `test_cmd`, parses a `--json-report`-produced `pytest.json`'s `summary` dict (`total`/`passed`/`failed`), with a fallback to binary pass/fail when JSON reporting isn't configured. The `.ll/learning-tests/pytest-json-report.md` learning-test proof documents this exact contract (`summary.passed + failed + skipped == total`).
  - `scripts/little_loops/pytest_history_plugin.py`'s `LLHistoryPlugin` (line 81) classifies pass/fail/error natively via the `pytest_runtest_logreport` hook, distinguishing `call`-phase failures (real test failures) from `setup`/`teardown`-phase failures (errors) — directly matches this issue's "error-vs-fail" distinction requirement in Design Notes. Registered via the `pytest11` entry point in `scripts/pyproject.toml`.
- **`project.test_patterns` is introduced by ENH-2973** (blocking), modeled on the existing `scan.focus_dirs` list-of-globs shape and resolved via `resolve_variable()` in `scripts/little_loops/config/core.py:886`. This issue only *consumes* the shared `scripts/little_loops/test_file_patterns.py` module; it neither defines the config key, its schema entry, nor its per-template defaults.
- **Evidence-bundle dataclass convention**: `scripts/little_loops/issue_history/models.py`'s `Gap`/`GapAnalysis` classes (lines 259-302) and `scripts/little_loops/cli/verify_design_tokens.py`'s `ThemeViolation`/`ProfileResult` (lines 49-60) both follow the same shape — plain-field `@dataclass` + `to_dict()` method, list fields capped to a top-N for serialization — which is the convention a new per-test evidence-bundle dataclass for this issue should follow. Note: the command doc's reference to a `TestGap` class in `issue_history/models.py` does not match current code; the actual class is named `Gap`.

## Integration Map

### Files to Modify / Create

_Rewritten 2026-07-30 (placement review) — the check is hosted by a reusable oracle loop; `ll-harness` and `/ll:verify-issue-loop` are demoted from owners to consumers. See Design Notes, "Gate placement"._

**Layer 1 — gate core (no FSM or CLI knowledge):**
- `scripts/little_loops/prepatch_check.py` (new) — `run_prepatch_check()`, `collect_candidate_nodeids()`, and the `PrePatchTestOutcome` / `PrePatchEvidence` dataclasses per § Program Design. Consumes ENH-2973's `test_file_patterns` module for identification and ENH-2866's reader helper for the base SHA.
- `scripts/little_loops/worktree_utils.py` — new additive sibling `setup_prepatch_worktree()` wrapping `setup_worktree()` (line 155): fork from the dequeue-time SHA / merge-base via the existing `base_branch` param, then `git apply` only the test-file portion of the diff (new logic — no partial-diff helper exists in the repo today). `setup_worktree()` / `cleanup_worktree()` signatures unchanged.

**Layer 2 — oracle host (the reachability fix):**
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — add the pre-patch check as an additive state alongside `run_test` (L201-249), gated by a new optional parameter that short-circuits to SKIP when unset (matching the oracle's existing null-command convention). Alternatively land it as a sibling `oracles/prepatch-test-gate.yaml` invoked from the same point; pin the choice during implementation. Either way the verdict and the evidence-bundle path travel the existing parent↔sub-loop token channel.

**Layer 3 — consumers (read the oracle's result; do not re-implement the check):**
- `scripts/little_loops/cli/harness.py` — surface the pre-patch evidence alongside the existing `HarnessEvalOutcome` (line 242) / `_evaluate_and_report()` (line 251) path by reading the oracle's artifact, not by hosting the check.
- `skills/verify-issue-loop/SKILL.md` — document the deterministic state type as a delegation to the oracle; today (~L150-165, plus `templates.md`) this skill only generates LLM-judged `llm_structured` states with no deterministic check type at all (line refs verified 2026-07-29 after the skill's restructuring).

_No longer this issue's install sites (they were the sole install sites before the 2026-07-30 placement review): `cli/harness.py` and `/ll:verify-issue-loop` as owners of the check._

_Split out at epic review (2026-07-27) — no longer this issue's scope, consumed as dependencies:_
- `scripts/little_loops/loops/autodev.yaml` `dequeue_next` + `ll-parallel` worktree-creation SHA stamps → **ENH-2866**
- `project.test_patterns` config key, template defaults, and `scripts/little_loops/test_file_patterns.py` → **ENH-2973**

### Similar Patterns to Follow
- `verify_epic_branch_before_merge()` (`worktree_utils.py:364-494`) — create → run-in-isolation → teardown-in-`finally` shape, plus its `src_dir` PYTHONPATH-injection fix (lines 399-409, 467-473) for editable-install import isolation. See precedent bugs `BUG-2629`, `BUG-2640`, `BUG-2649`.
- `scripts/little_loops/pytest_history_plugin.py`'s `LLHistoryPlugin` (line 81) — per-test pass/fail/error classification via `pytest_runtest_logreport`, distinguishing `call`-phase failures from `setup`/`teardown`-phase errors.
- `scripts/little_loops/loops/oracles/code-run-gate.yaml`'s `run_test` state (lines 201-249) — alternative pass/fail parsing via `pytest.json`'s `summary` dict; see `.ll/learning-tests/pytest-json-report.md` for the proven contract.
- `scripts/little_loops/issue_history/models.py`'s `Gap`/`GapAnalysis` (lines 259-302) — dataclass + `to_dict()` convention for the new evidence-bundle structure.

### Tests
- `scripts/tests/test_worktree_utils.py` — extend for the pre-patch worktree + partial-diff-apply path.
- `scripts/tests/test_cli_harness.py` — extend for the new evidence bundle.
- `scripts/tests/test_verify_issue_loop.py` — extend for the new deterministic state.
- Dequeue-SHA stamp tests (`test_autodev_loop.py`, `test_worker_pool.py`) are **ENH-2866's** scope; this issue tests only the *reader consumption* path (stamped base used, unstamped merge-base fallback).
- No existing test file covers pre-patch/post-patch test comparison; a new test module is needed.

### Related Issues
- `ENH-2973` (blocking) — `project.test_patterns` + shared `test_file_patterns.py`.
- `ENH-2866` (blocking) — dequeue-time SHA stamp and its reader helper.
- `ENH-2854` (peer, **not** a dependency in either direction as of the 2026-07-27 epic review) — consumes the same ENH-2973 module. The two interact only at ordering: ENH-2854's `revert` policy must run *after* this check has read the step's diff, which is stated as a constraint in ENH-2854 rather than a blocking edge.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` (~line 927) — calls `worktree_utils.setup_worktree()` directly for FSM worktree-backed loop runs; any non-additive signature change to `setup_worktree()` for the pre-patch/partial-diff-apply variant breaks this call site. Not previously listed as a consumer.
- `scripts/little_loops/cli/loop/run.py` (~line 472, `cleanup_worktree` paired via `atexit` at ~line 535/560) — `ll-loop run --worktree` path; same signature-compatibility concern as above.
- `scripts/little_loops/parallel/merge_coordinator.py` (~line 1061) — has its own private `_cleanup_worktree` wrapper rather than calling `little_loops.worktree_utils.cleanup_worktree` directly; confirm during implementation whether it needs updating or is genuinely independent.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (lines ~462, ~653) — FSM states call `verify_epic_branch_before_merge()`, the closest structural analog this issue extends; a wrapper/extension should stay backward-compatible with these call sites.
- `docs/reference/API.md:88` — module table entry for `little_loops.worktree_utils` names only ll-parallel/ll-sprint/ll-loop as consumers; does not yet mention the FSM executor as a fourth direct caller (confirmed above).

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:3455-3473` — existing prose block documents `verify_epic_branch_before_merge` / `setup_worktree(..., checkout_existing=True)`'s exact call shape; cross-reference here when adding the pre-patch/partial-diff-apply variant.
- `skills/verify-issue-loop/SKILL.md` ~L150-165 and `templates.md` — the skill documents only `llm_structured` verify/probe states today. Add a bullet describing when the deterministic pre-patch state type applies, alongside a new state-template example in `templates.md`. (The "Important rules" boundary text at former lines 211-219 that the wiring pass flagged for reconciliation no longer exists after the skill's restructuring — verified 2026-07-29; the work is additive documentation, not editing a prohibition.)
- `scripts/little_loops/cli/harness.py:117-128` (`--help` epilog / `_add_evaluator_flags()`) and the hard-coded JSON key set in `_evaluate_and_report()` (lines 283-294) / `_report()` (lines 320-339) — the new per-test evidence bundle is an additive key set here, not currently present; epilog text should mention it.
- `docs/reference/CONFIGURATION.md` — no change here; the `### project` table's `project.test_patterns` row ships with ENH-2973.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_orchestrator.py` — patches `little_loops.worktree_utils.setup_worktree` at ~7 sites (lines 1761-1888) and asserts `base_branch` in merge/PR tests; extend if `setup_worktree()`'s signature changes.
- `scripts/tests/test_cli_loop_worktree.py` — covers `ll-loop run --worktree`'s use of `setup_worktree`/`cleanup_worktree`; needs coverage if the pre-patch variant touches this path.
- `scripts/tests/test_worktree_utils.py`'s `TestVerifyEpicBranchBeforeMerge` (lines 350-690), specifically `test_src_dir_prepends_worktree_source_onto_pythonpath` (line 447), `test_falsy_src_dir_leaves_pythonpath_uninjected` (line 479), `test_verify_gate_marker_set_in_child_env` (line 556) — the direct template for the new pre-patch-worktree import-isolation tests (probe-subprocess pattern via inline `python3 -c` one-liners asserting `PYTHONPATH`/`LL_VERIFY_GATE`).
- Dequeue-SHA stamp coverage (`test_autodev_loop.py`'s `dequeue_next` assertions, `test_worker_pool.py`'s `TestSetupWorktreeAndCleanup`) belongs to **ENH-2866**, not this issue — see § Scope Boundary. This issue's tests cover only the reader-consumption side: stamped base honoured, unstamped merge-base fallback.

## Scope Boundaries

- **Not this issue**: the dequeue-time SHA stamp and its reader helper (moved to **ENH-2866**); the `project.test_patterns` config key, its template defaults, and the shared `test_file_patterns.py` classification module (moved to **ENH-2973**). This issue only *consumes* both.
- **Not this issue**: `ENH-2854`'s tamper-guard `revert` policy — a peer that shares the ENH-2973 module but has no dependency edge in either direction; the only interaction is ordering (its revert must run after this check reads the step's diff), which is a constraint documented on ENH-2854, not a blocking edge here.
- **Not this issue**: replacing or removing the existing LLM-judged semantic criteria in verification loops — this check is additive alongside them, never a substitute.
- **Not this issue**: running the full test suite pre-patch — only the identified candidate test node IDs are run (see Design Notes, "Price the check").
- **Not this issue** (added 2026-07-30, placement review): hooking the check into `ll-auto` / `ll-parallel` / `ll-sprint` as a standalone CLI-level pre-flight. Those orchestrators reach it transitively through the `rn-*` loops that delegate to the oracle. If a direct non-FSM entry point is later wanted, it is an additive Python adapter over the same `prepatch_check.py` core (the `learning_tests/gate.py` shape), not a second implementation — and a separate issue.

## Impact

- **Priority**: P2 - Closes a real fake-evidence hole in verification loops (per epic EPIC-2856's rework-reduction goal), but is not blocking active work until its dependencies (ENH-2973, ENH-2866) land.
- **Effort**: Large - New worktree-fork-plus-partial-diff-apply primitive, a new per-test evidence-bundle dataclass, a new deterministic FSM state type wired into `/ll:verify-issue-loop`, and import-isolation handling for editable installs; touches `worktree_utils.py`, `cli/harness.py`, and `skills/verify-issue-loop/SKILL.md`.
- **Risk**: Medium - `setup_worktree()`/`cleanup_worktree()` are called directly by `fsm/executor.py`, `cli/loop/run.py`, and `parallel/orchestrator.py`; any signature change must stay additive to avoid breaking those call sites. The check itself is otherwise isolated (worktree-scoped, non-mutating on failure).
- **Breaking Change**: No - additive worktree variant and additive evidence-bundle fields; existing semantic criteria and call sites are unaffected.
- **Placement correction (2026-07-30)**: the prior install sites (`cli/harness.py`, `/ll:verify-issue-loop`) put the check on paths no orchestrator reaches, so as previously scoped this issue would have shipped without closing the hole it describes. Re-hosting it on an oracle loop does not increase the core's effort but adds an oracle state, the token-channel evidence transport, and delegation tests. Effort stays **Large**; re-run size review before implementation.

## Program Design

Added 2026-07-29 (post-gate quality pass; the issue remains grandfathered under the
2026-07-30 cutover stamp — this section exists so `/ll:manage-issue` can track
Deviations against it, per ENH-2871).

### Types

- `PrePatchTestOutcome` — one candidate test's result: `nodeid: str`, `file: str`, `added: bool`, `pre_patch: str`, `category: str`, `error_kind: str | None`
- `PrePatchEvidence` — the per-step evidence bundle: `base_ref: str`, `base_source: str`, `outcomes: list[PrePatchTestOutcome]`, `skipped_reason: str | None`, `to_dict() -> dict`

Both are new plain-field `@dataclass`es with `to_dict()` in a new module
`scripts/little_loops/prepatch_check.py`, following the `Gap`/`GapAnalysis`
convention. `category` is one of `pass | fail | error | timeout | flaky`;
`error_kind` distinguishes a collection/import error naming a post-patch module
from any other infrastructure error. `base_source` is `dequeue-stamp` or
`merge-base`, so the bundle names the base actually used. `skipped_reason` is set
when the config off-switch disables the check, so the skip is explicit.

### Signatures

- `run_prepatch_check(step_diff: str, base_sha: str | None, timeout_s: int) -> PrePatchEvidence`
- `collect_candidate_nodeids(step_diff: str, repo_root: Path) -> list[str]`
- `setup_prepatch_worktree(base_ref: str, test_patch: str, src_dir: str | None) -> Path`
- `is_test_file(path: str, config: BRConfig | None) -> bool`

The first two are new in `prepatch_check.py`. `setup_prepatch_worktree()` is a new
additive sibling in `worktree_utils.py` wrapping `setup_worktree()` (fork from
`base_ref` via the existing `base_branch` parameter) plus the new partial-diff
`git apply` of the test-file portion; `setup_worktree()` /
`cleanup_worktree()` signatures are unchanged. `is_test_file()` /
`filter_test_files()` are ENH-2973's existing shared module, consumed for
candidate identification and never re-implemented here.

### Call Path

_Call path updated 2026-07-30 (placement review): the entry point is the oracle
state, not `_evaluate_and_report()`._

`oracles/` pre-patch state -> `run_prepatch_check` -> `collect_candidate_nodeids` -> `filter_test_files`

`run_prepatch_check` -> `setup_prepatch_worktree` -> `setup_worktree` -> `cleanup_worktree`

The oracle state emits its verdict on the parent↔sub-loop token channel and
writes the `PrePatchEvidence` bundle under `${context.run_dir}/`.
`_evaluate_and_report()` in `cli/harness.py` reads that bundle and surfaces it
alongside the existing `HarnessEvalOutcome` — it does not call
`run_prepatch_check()` itself. The worktree create → run-in-isolation →
teardown-in-finally shape and the src_dir PYTHONPATH-injection fix are taken
from `verify_epic_branch_before_merge`, and per-test pass/fail/error
classification mirrors `LLHistoryPlugin`.

## Acceptance Criteria

- [ ] Newly added and modified test functions are identified from the verification step's diff.
- [ ] Those tests are run against the pre-patch tree with only the test changes applied, in an isolated worktree.
- [ ] A newly *added* candidate test that passes pre-patch is hard-flagged and is not counted as verification evidence.
- [ ] A *modified* candidate test that passes pre-patch is recorded in the evidence as soft by default, with a config option to escalate it to a hard flag.
- [ ] A candidate test that fails or errors pre-patch is accepted as evidence; the evidence bundle records the error category (import/collection error naming a post-patch module vs. other infrastructure error).
- [ ] `conftest.py` changes are applied to the pre-patch tree (guaranteed by ENH-2973's default patterns; assert it here rather than re-implementing it).
- [ ] The pre-patch run resolves imports from the pre-patch worktree, not the main tree's editable install; a test proves the isolation (post-patch-only module is unimportable in the pre-patch run).
- [ ] The base state is the dequeue-time SHA when ENH-2866's reader returns one, else the merge-base with the base branch; the chosen base is named in the evidence bundle, and a test covers the unstamped fallback path.
- [ ] Test-file identification is done via ENH-2973's shared module, not a glob list defined here.
- [ ] The zero-candidate-tests case is reported explicitly rather than passing silently.
- [ ] Per-test results (name, file, pre-patch outcome, post-patch outcome) appear in the verification evidence bundle.
- [ ] The user's working tree is unchanged after the check runs, including on failure paths.
- [ ] The pre-patch run invokes only the candidate test node IDs, not the full suite; a test asserts the constructed pytest command targets node IDs.
- [ ] The pre-patch pytest invocation is time-bounded; a timeout is recorded as its own outcome category (distinct from fail and error) and treated as "did not pass".
- [ ] A candidate test that passes pre-patch is re-run once before being hard-flagged; a pass-then-fail outcome is recorded as flaky and soft-flagged instead.
- [ ] When function-level attribution of a modified hunk is ambiguous, the check falls back to the touched files' test node IDs (never the full suite).
- [ ] A config off-switch disables the check; when disabled, the evidence bundle records the skip explicitly.
- [ ] The check makes no LLM calls.
- [ ] Tests cover: a fake test that passes pre-patch, a genuine test that fails pre-patch, a test that errors pre-patch, and the zero-test case.

_Added 2026-07-30 (placement review) — see Design Notes, "Gate placement":_

- [ ] The check is hosted by a reusable oracle loop (an additive state in `oracles/code-run-gate.yaml` or a sibling `oracles/prepatch-test-gate.yaml`), reachable via sub-loop delegation — not implemented inside `cli/harness.py`.
- [ ] The check is reachable from the `rn-*` family's green-suite transitions; a test asserts the delegating loop (`rn-implement` / `rn-remediate` / `rn-refine`) routes through the pre-patch state.
- [ ] The gate core lives in `prepatch_check.py` with no FSM or CLI imports, so the oracle and any Python caller invoke the same implementation.
- [ ] `cli/harness.py` surfaces the pre-patch evidence by reading the oracle's artifact; it does not call `run_prepatch_check()` directly, and a test asserts the check is not re-implemented there.
- [ ] The evidence bundle reaches the parent via the parent↔sub-loop token channel with the full bundle written under `${context.run_dir}/` (MR-3), rather than only inside a harness-local dataclass.
- [ ] When the check's enabling parameter is unset, the oracle state short-circuits to a SKIP pass-through (matching `code-run-gate`'s null-command convention) rather than failing the gate.


## Status

**Open** | Created: 2026-07-27 | Priority: P2

## Session Log
- blocked_by reconciliation (manual, no skill) - 2026-08-01 - removed ENH-2973 from `blocked_by` (status: done, completed 2026-07-28); ENH-2866 remains blocking (open, undergoing refinement)
- gate-placement review (manual, no skill) - 2026-07-30 - rewrote `### Files to Modify / Create`, the Program Design call path, added Design Notes "Gate placement" / "Evidence-bundle transport" / "Oracle skip convention", 6 ACs, 1 Scope Boundary, 1 Impact note
- `/ll:format-issue` - 2026-07-27T20:01:08 - `74d428f0-7103-4a58-9168-ff504878fb04.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-27T19:42:08 - `e2303183-4e52-4649-af90-4b53254bbda4.jsonl`
- `/ll:wire-issue` - 2026-07-27T16:58:09 - `8416c0b2-f15d-4605-9d27-7401bd127ac6.jsonl`
- `/ll:refine-issue` - 2026-07-27T16:25:41 - `b315bd08-df31-4315-8e3d-4da1b2c0632d.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-27T15:59:42 - `29cf17b6-04b4-4b01-9444-64f1bfdbdaa5.jsonl`
