---
id: ENH-2853
title: Deterministic pre-patch test-failure check in verification loops
type: ENH
priority: P2
status: open
discovered_by: ll-product-promotion
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
blocked_by:
- ENH-2865
- ENH-2866
learning_tests_required:
- pytest
---

# ENH-2853: Deterministic pre-patch test-failure check in verification loops

Origin: ll-product #ENH-051

## Summary

A test that passes on the pre-change tree proves nothing about the change. Add a deterministic check that runs newly added or modified tests against the **pre-patch** code and requires them to fail there before a verification loop may treat them as evidence.

This is a non-LLM check and belongs in `ll-harness`, `/ll:verify-issue-loop`, and the verification-evidence bundle, alongside the existing semantic criteria rather than replacing them.

## Motivation

The most common way an agent fakes verification is writing a test that passes before and after the change. It costs nothing, it turns the suite green, and every downstream signal — transition predicates, evidence bundles, success rates — reads it as proof. Semantic criteria do not catch it reliably because the test genuinely looks correct in isolation; the defect is only visible relative to the pre-change tree.

The check is deterministic, cheap, and has no false-positive mode that matters: a test that is supposed to demonstrate a change must fail without that change.

## Proposed Change

1. **Identify the candidate tests** — from the diff of the verification step, collect test functions that were added or modified.
2. **Reconstruct the pre-patch tree** — check out the base state in an isolated worktree, then apply *only* the test changes onto it.
3. **Run the candidate tests there** and record per-test pass/fail.
4. **Verdict** — any candidate test that *passes* against the pre-patch tree is flagged. The loop must not count it as evidence; the transition either fails or the test is excluded from the evidence set, per configuration.
5. **Report** — emit per-test results (name, file, pre-patch outcome, post-patch outcome) into the verification evidence bundle so the check is auditable without re-running it.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Keep any `setup_worktree()`/`cleanup_worktree()` signature change additive — `scripts/little_loops/fsm/executor.py`, `scripts/little_loops/cli/loop/run.py`, and `scripts/little_loops/parallel/orchestrator.py` all call these directly today and are outside this issue's primary files.
7. Reconcile `skills/verify-issue-loop/SKILL.md`'s explicit "no deterministic state type" boundary text (lines 211-219) with the new state type this issue introduces, adding a state-template example.
8. ~~Schema-presence test for `project.test_patterns`~~ — moved to **ENH-2865**.
9. ~~Per-language `project.test_patterns` template defaults~~ — moved to **ENH-2865**.

## Design Notes

- Apply *only* the test-file portion of the diff to the base tree. Applying the full diff defeats the purpose; applying nothing means the tests don't exist to run.
- A candidate test that **errors** on the pre-patch tree (import error because the new module doesn't exist yet) counts as failing — that is the expected outcome for a test of new code, not a harness problem. Distinguish error-vs-fail in the report but treat both as "did not pass".
- **Error-category false-negative hole (epic review, 2026-07-27).** "Errors pre-patch is accepted as evidence" also accepts a fake test that errors for *infrastructure* reasons — e.g. it depends on a fixture added in `conftest.py` that wasn't applied because `conftest.py` doesn't match typical `test_*` globs. Two mitigations are required: (1) the default `project.test_patterns` and the shared identification module MUST include `conftest.py`; (2) the evidence bundle records the error *category* — a collection/import error naming a post-patch module (expected failure of new code) vs. anything else (fixture/infrastructure error, suspicious) — so an auditor can tell them apart without re-running.
- **Diff-scope caveat, same class of hole**: applying only the test-file portion of the diff means new *non-test* helpers a test imports are absent pre-patch. Import errors referencing non-target modules should be treated with suspicion in the report, not read as clean evidence.
- Use an isolated worktree rather than mutating the working tree in place; a verification check must never leave the user's tree in a different state than it found it.
- Pure-refactor changes may legitimately have no new tests. Zero candidate tests is not a failure — report it explicitly rather than silently passing, so "no tests were added" is visible.
- Keep this independent of any LLM call. The whole value is that the signal is mechanical.
- **Added vs. modified tests carry different contracts.** A *newly added* test must fail pre-patch — that is the clean "demonstrates the change" contract. A *modified* test routinely passes pre-patch legitimately (an assertion added to an already-passing test, a tightened comparison, a rename). Split the verdict: added-and-passes-pre-patch is a hard flag; modified-and-passes-pre-patch is recorded in the evidence but soft by default (configurable to hard). A hard flag on modified tests would punish exactly the assertion-strengthening behavior the epic wants to encourage.
- **Import isolation is load-bearing in editable-install repos.** A worktree checkout of the pre-patch tree can still import the *main-tree* package when the project is installed editable (the install pins an absolute path — see the epic-verify false-negative history in this repo). A "pre-patch" run that imports post-patch code passes trivially and the check reports garbage. The pre-patch run must resolve imports from the worktree (PYTHONPATH injection ahead of site-packages, or a fresh non-editable install into the worktree's environment), and a test must prove the isolation.
- **Define the base state explicitly.** Under `ll-auto`/`ll-sprint` a verification step may span multiple commits. "Pre-patch" means the tree at the SHA recorded when the issue was dequeued (fall back to merge-base with the base branch when no dequeue SHA is recorded) — not simply `HEAD~1`.
- **The dequeue-SHA stamp is ENH-2866, not this issue** (split at epic review, 2026-07-27). Nothing records a dequeue SHA today, so this issue's primary base-state path would be dead code without it; ENH-2866 adds the stamp at `autodev.yaml`'s `dequeue_next` and `ll-parallel`'s worktree creation, plus a reader helper that returns `None` when unstamped. This issue *consumes* that helper and implements the merge-base fallback behind it. Until a given orchestrator stamps, its runs take the fallback — which is why the evidence bundle must name the base actually used.
- **Test-file identification is ENH-2865, not this issue** (split at epic review, 2026-07-27). Both this check and ENH-2854's tamper guard need to classify paths as test files; the `project.test_patterns` config key, its template defaults (including the load-bearing `conftest.py` entry), and the shared `test_file_patterns.py` module land once in ENH-2865 and are consumed here. This removes the former circular `blocked_by` between this issue and ENH-2854 — neither depends on the other now; both depend on ENH-2865.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- No existing code implements this check. Each surface the issue touches has adjacent, reusable machinery rather than a blank slate:
  - **`ll-harness`** (`scripts/little_loops/cli/harness.py`) has no per-test evidence bundle today — only a single-check `HarnessEvalOutcome` dataclass (`harness.py:242-248`) produced by `_evaluate_and_report()` (`harness.py:251-317`), with exit-code and single-LLM-semantic evaluators only (`harness.py:269-278`). `_record_harness_event()` (`harness.py:57-83`) persists a flat single-row event, not a multi-test table — any evidence bundle for this issue is new structure, not an extension of an existing one.
  - **`/ll:verify-issue-loop`** (`skills/verify-issue-loop/SKILL.md`) synthesizes purely LLM-judged `check_semantic`/`llm_structured` states per acceptance criterion (Step 3, lines 92-112) and explicitly documents that it has no deterministic state type wired in today (lines 218-219). A pre-patch check is a net-new state type this skill's generator doesn't currently emit.
  - **`autodev.yaml`'s `dequeue_next`** (lines 80-141) already snapshots pre-refine readiness to `${context.run_dir}/autodev-pre-readiness.txt` (lines 104-117, per FEAT-2751) — confirming the pattern this issue's dequeue-SHA stamp should follow — but captures no `git rev-parse HEAD` anywhere; the dequeue-time SHA stamp this issue calls for is genuinely new.
  - **`ll-parallel`** (`scripts/little_loops/cli/parallel.py`) has no direct worktree calls itself; it delegates to `little_loops.parallel.worker_pool`/`orchestrator` for lifecycle and to the shared primitive `setup_worktree()` in `scripts/little_loops/worktree_utils.py:155-267`. No commit SHA is captured at the point a per-issue worker's worktree is created.
- **Reusable worktree substrate**: `setup_worktree()` (`worktree_utils.py:155`) / `cleanup_worktree()` (`worktree_utils.py:270`) are the shared create/teardown primitives already used by `ll-parallel`, `ll-sprint`, and `ll-loop`. `setup_worktree()` accepts an optional `base_branch: str | None` validated via `git rev-parse --verify` (lines 201-208) and forks a worktree from it — this is the exact "fork from a dequeue-time SHA" hook this issue needs; no partial-diff/`git apply` helper exists anywhere in the codebase today (repo-wide `git apply` grep returns zero hits), so "apply only the test-file portion of the diff onto the base tree" is new logic to write on top of this primitive.
- **Closest structural analog**: `verify_epic_branch_before_merge()` (`worktree_utils.py:364-494`) already implements the create → run-in-isolation → teardown-in-`finally` shape this issue's Design Notes describe (worktree at lines 433-442, test/lint run at 475-491, teardown at 493-494 regardless of outcome) — not directly reusable (it checks out an *existing branch*, not a "base SHA + partial diff" state), but it's the template to follow for "never leave the user's tree different than it found it."
- **Editable-install import isolation — direct precedent, not a new problem**: `verify_epic_branch_before_merge()`'s `src_dir` parameter (`worktree_utils.py:399-409`, applied at 467-473) already solves exactly the failure mode this issue's Design Notes flag: an editable install's `_editable_impl_*.pth` hardcodes the main tree's absolute source path at interpreter startup regardless of `cwd`, so an unguarded pre-patch worktree run would still import main-tree modules. The fix — prepend `str(worktree_path / src_dir)` to `PYTHONPATH` ahead of the `.pth`-injected path — is the pattern to reuse directly. This was tracked as three linked bugs worth reading before implementing: `BUG-2629` (original false-negative), `BUG-2640` (stale main-tree source symptom), `BUG-2649` (added `LL_VERIFY_GATE=1` env marker at `worktree_utils.py:454-455` so tests sensitive to the injected PYTHONPATH/xdist-worktree combination can self-quarantine).
- **Per-test pass/fail/error classification — two existing patterns to choose between, neither currently wired to a pre/post-patch comparison**:
  - `scripts/little_loops/loops/oracles/code-run-gate.yaml`'s `run_test` state (lines 201-249) shells out to `test_cmd`, parses a `--json-report`-produced `pytest.json`'s `summary` dict (`total`/`passed`/`failed`), with a fallback to binary pass/fail when JSON reporting isn't configured. The `.ll/learning-tests/pytest-json-report.md` learning-test proof documents this exact contract (`summary.passed + failed + skipped == total`).
  - `scripts/little_loops/pytest_history_plugin.py`'s `LLHistoryPlugin` (line 81) classifies pass/fail/error natively via the `pytest_runtest_logreport` hook, distinguishing `call`-phase failures (real test failures) from `setup`/`teardown`-phase failures (errors) — directly matches this issue's "error-vs-fail" distinction requirement in Design Notes. Registered via the `pytest11` entry point in `scripts/pyproject.toml`.
- **No `project.test_patterns` config key exists yet** in `config-schema.json` or any template under `scripts/little_loops/templates/*.json`. ENH-2854 (the sibling issue this one shares test-file identification with) proposes introducing it as a new glob-list key, modeled on the existing `scan.focus_dirs` list-of-globs shape (resolved via `resolve_variable()` in `scripts/little_loops/config/core.py:886`). Both issues should land the shared identification module against this same new key rather than each defining its own glob list.
- **Evidence-bundle dataclass convention**: `scripts/little_loops/issue_history/models.py`'s `Gap`/`GapAnalysis` classes (lines 259-302) and `scripts/little_loops/cli/verify_design_tokens.py`'s `ThemeViolation`/`ProfileResult` (lines 49-60) both follow the same shape — plain-field `@dataclass` + `to_dict()` method, list fields capped to a top-N for serialization — which is the convention a new per-test evidence-bundle dataclass for this issue should follow. Note: the command doc's reference to a `TestGap` class in `issue_history/models.py` does not match current code; the actual class is named `Gap`.

## Integration Map

### Files to Modify / Create
- `scripts/little_loops/worktree_utils.py` — extend or wrap `setup_worktree()` (line 155) with a pre-patch variant: fork from a dequeue-time SHA / merge-base via the existing `base_branch` param, then apply only the test-file portion of the diff (new logic — no `git apply`-based partial-diff helper exists in the repo today).
- `scripts/little_loops/cli/harness.py` — add the pre-patch evidence bundle alongside the existing `HarnessEvalOutcome` (line 242) / `_evaluate_and_report()` (line 251) single-check path.
- `skills/verify-issue-loop/SKILL.md` — wire in the new deterministic state type; today (lines 92-127, 218-219) this skill only generates LLM-judged `llm_structured` states with no deterministic check type at all.

_Split out at epic review (2026-07-27) — no longer this issue's scope, consumed as dependencies:_
- `scripts/little_loops/loops/autodev.yaml` `dequeue_next` + `ll-parallel` worktree-creation SHA stamps → **ENH-2866**
- `project.test_patterns` config key, template defaults, and `scripts/little_loops/test_file_patterns.py` → **ENH-2865**

### Similar Patterns to Follow
- `verify_epic_branch_before_merge()` (`worktree_utils.py:364-494`) — create → run-in-isolation → teardown-in-`finally` shape, plus its `src_dir` PYTHONPATH-injection fix (lines 399-409, 467-473) for editable-install import isolation. See precedent bugs `BUG-2629`, `BUG-2640`, `BUG-2649`.
- `scripts/little_loops/pytest_history_plugin.py`'s `LLHistoryPlugin` (line 81) — per-test pass/fail/error classification via `pytest_runtest_logreport`, distinguishing `call`-phase failures from `setup`/`teardown`-phase errors.
- `scripts/little_loops/loops/oracles/code-run-gate.yaml`'s `run_test` state (lines 201-249) — alternative pass/fail parsing via `pytest.json`'s `summary` dict; see `.ll/learning-tests/pytest-json-report.md` for the proven contract.
- `scripts/little_loops/issue_history/models.py`'s `Gap`/`GapAnalysis` (lines 259-302) — dataclass + `to_dict()` convention for the new evidence-bundle structure.

### Tests
- `scripts/tests/test_worktree_utils.py` — extend for the pre-patch worktree + partial-diff-apply path.
- `scripts/tests/test_cli_harness.py` — extend for the new evidence bundle.
- `scripts/tests/test_verify_issue_loop.py` — extend for the new deterministic state.
- `scripts/tests/test_autodev_loop.py` — extend for the dequeue-time SHA stamp.
- No existing test file covers pre-patch/post-patch test comparison; a new test module is needed.

### Related Issues
- `ENH-2865` (blocking) — `project.test_patterns` + shared `test_file_patterns.py`.
- `ENH-2866` (blocking) — dequeue-time SHA stamp and its reader helper.
- `ENH-2854` (peer, **not** a dependency in either direction as of the 2026-07-27 epic review) — consumes the same ENH-2865 module. The two interact only at ordering: ENH-2854's `revert` policy must run *after* this check has read the step's diff, which is stated as a constraint in ENH-2854 rather than a blocking edge.

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
- `skills/verify-issue-loop/SKILL.md` lines 211-219 — the "Important rules" list explicitly forbids non-`llm_structured` state types (`check_invariants`/`check_stall`/`check_concrete` called out by name) as out of scope for verification loops. This boundary text must be reconciled with a new bullet describing when the deterministic pre-patch state type applies, alongside a new state-template example near lines 160-198.
- `scripts/little_loops/cli/harness.py:117-128` (`--help` epilog / `_add_evaluator_flags()`) and the hard-coded JSON key set in `_evaluate_and_report()` (lines 283-294) / `_report()` (lines 320-339) — the new per-test evidence bundle is an additive key set here, not currently present; epilog text should mention it.
- `docs/reference/CONFIGURATION.md` (if it enumerates the `project.*` block) — likely needs a `project.test_patterns` section matching the schema addition; confirm presence/absence during implementation.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_worker_pool.py`'s `TestSetupWorktreeAndCleanup` (line ~634, e.g. `test_setup_worktree_passes_base_branch_in_feature_mode` line ~963) — closest existing analog for a dequeue-time SHA-stamp test at `ll-parallel`'s worker-creation call site; currently asserts only on `git worktree add` argv shape, not any SHA capture.
- `scripts/tests/test_orchestrator.py` — patches `little_loops.worktree_utils.setup_worktree` at ~7 sites (lines 1761-1888) and asserts `base_branch` in merge/PR tests; extend if `setup_worktree()`'s signature changes.
- `scripts/tests/test_cli_loop_worktree.py` — covers `ll-loop run --worktree`'s use of `setup_worktree`/`cleanup_worktree`; needs coverage if the pre-patch variant touches this path.
- `scripts/tests/test_worktree_utils.py`'s `TestVerifyEpicBranchBeforeMerge` (lines 350-690), specifically `test_src_dir_prepends_worktree_source_onto_pythonpath` (line 447), `test_falsy_src_dir_leaves_pythonpath_uninjected` (line 479), `test_verify_gate_marker_set_in_child_env` (line 556) — the direct template for the new pre-patch-worktree import-isolation tests (probe-subprocess pattern via inline `python3 -c` one-liners asserting `PYTHONPATH`/`LL_VERIFY_GATE`).
- No existing test executes `dequeue_next` live — `test_autodev_loop.py`'s `TestDequeueNextPreReadinessSnapshot` (lines 172-186) only does string-containment checks against the raw YAML `action:` block; the new SHA-stamp test should follow that same static-assertion style (`assert "git rev-parse HEAD" in action`) rather than expecting live-execution coverage.

## Acceptance Criteria

- [ ] Newly added and modified test functions are identified from the verification step's diff.
- [ ] Those tests are run against the pre-patch tree with only the test changes applied, in an isolated worktree.
- [ ] A newly *added* candidate test that passes pre-patch is hard-flagged and is not counted as verification evidence.
- [ ] A *modified* candidate test that passes pre-patch is recorded in the evidence as soft by default, with a config option to escalate it to a hard flag.
- [ ] A candidate test that fails or errors pre-patch is accepted as evidence; the evidence bundle records the error category (import/collection error naming a post-patch module vs. other infrastructure error).
- [ ] `conftest.py` changes are applied to the pre-patch tree (guaranteed by ENH-2865's default patterns; assert it here rather than re-implementing it).
- [ ] The pre-patch run resolves imports from the pre-patch worktree, not the main tree's editable install; a test proves the isolation (post-patch-only module is unimportable in the pre-patch run).
- [ ] The base state is the dequeue-time SHA when ENH-2866's reader returns one, else the merge-base with the base branch; the chosen base is named in the evidence bundle, and a test covers the unstamped fallback path.
- [ ] Test-file identification is done via ENH-2865's shared module, not a glob list defined here.
- [ ] The zero-candidate-tests case is reported explicitly rather than passing silently.
- [ ] Per-test results (name, file, pre-patch outcome, post-patch outcome) appear in the verification evidence bundle.
- [ ] The user's working tree is unchanged after the check runs, including on failure paths.
- [ ] The check makes no LLM calls.
- [ ] Tests cover: a fake test that passes pre-patch, a genuine test that fails pre-patch, a test that errors pre-patch, and the zero-test case.


## Session Log
- `/ll:wire-issue` - 2026-07-27T16:58:09 - `8416c0b2-f15d-4605-9d27-7401bd127ac6.jsonl`
- `/ll:refine-issue` - 2026-07-27T16:25:41 - `b315bd08-df31-4315-8e3d-4da1b2c0632d.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-27T15:59:42 - `29cf17b6-04b4-4b01-9444-64f1bfdbdaa5.jsonl`
