---
id: ENH-2853
title: Deterministic pre-patch test-failure check in verification loops
type: ENH
priority: P2
status: done
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
testable: true
learning_tests_required:
- pytest
confidence_score: 82
outcome_confidence: 60
score_complexity: 14
score_test_coverage: 16
score_ambiguity: 14
score_change_surface: 16
size: Very Large
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
- **Gate placement, superseded (2026-08-02): host the check on the executor's guarded-window mechanism, not on an oracle state.** The 2026-07-30 placement review below correctly ruled out `cli/harness.py` and `/ll:verify-issue-loop` as owners, and its reachability reasoning still stands. But its *positive* prescription — an additive state in `oracles/code-run-gate.yaml` reached via the token channel, following the learning-test gate's three-layer shape — predates ENH-2854 landing on 2026-07-31. That sibling solved the identical reachability problem for the identical class of gate a different way, and it is now this repo's established precedent:
  - ENH-2854 shipped `tamper_guard` as a **first-class FSM key**, settable loop-level and state-level (`fsm/schema.py:690` and `:1311`), enforced by the executor as snapshot-on-entry / compare-on-exit (`fsm/executor.py:1295-1384`), with findings accumulated across guarded states in `ctx.context["_tamper_guard"]`, a dedicated validation lint rule, **and** a non-FSM adapter (`work_verification.py`) called from `issue_manager.py` and `parallel/worker_pool.py`.
  - `code-run-gate.yaml:50` already declares `tamper_guard: fail` at loop level — the sibling mechanism is already active in the very file the 07-30 review proposed adding a state to.
  - **Decisive on the merits, not just on consistency:** this check's input is *the diff of the verification step*. A state sitting alongside `run_test` has no natural access to that; the executor's entry/exit bracket computes exactly it. Hosting on the guarded-window mechanism also inherits ENH-2854's non-FSM path, which gives `ll-auto` / `ll-parallel` coverage without the separate follow-up issue § Scope Boundaries previously deferred.
  - **Reuse, do not re-derive**: `test_tamper_guard.snapshot_test_paths_at_ref()` / `read_paths_at_ref(repo_root, ref, paths)` read file contents at an arbitrary git ref, and `_test_functions()` (`:311`) / `measure_test_strength()` (`:235`) / `filter_weakening_findings()` (`:333`) already do AST test-function extraction and before/after per-test comparison. See the two Design Notes below that consume them.
  - The Layer-1 core (`prepatch_check.py`, no FSM or CLI imports) is unchanged by this correction and remains the deliverable both hosts call.

- **Gate placement, original review (2026-07-30) — ruling-out half retained, prescription superseded above.** The prior Integration Map installed the check in `cli/harness.py:_evaluate_and_report()` and in `/ll:verify-issue-loop`'s generator. Both are off every production verification path:
  - **No orchestrator invokes `ll-harness`.** A repo-wide grep for `ll-harness` across `scripts/little_loops/` returns only its own CLI (`cli/harness.py`), the shared `runner_spec.py` abstraction, telemetry readers (`history_reader.py:2797+`), and a permission string in `init/writers.py:70`. Nothing in `ll-auto`, `ll-parallel`, `ll-sprint`, or any `loops/*.yaml` calls it — it is a hand-run one-shot tool.
  - **`/ll:verify-issue-loop` is a generator.** A check emitted there exists only inside per-issue loop YAML someone chose to generate, never in a standing path.
  - The actual chokepoint for "did these tests prove anything" is `oracles/code-run-gate.yaml`'s `run_test` state, delegated to by `rn-refine.yaml:483`, `rn-remediate.yaml:543`, and `rn-implement`'s `run_code_gate` (`loops/README.md:64`). Hosting the check there is what makes it reachable from every green-suite transition in the `rn-*` family.
  - **Follow the learning-test gate's three-layer shape**, which is this repo's established pattern for a gate that must reach both FSM and CLI callers: gate logic in a reusable internal loop (`ready-to-implement-gate.yaml`), a thin Python adapter that shells out to it (`learning_tests/gate.py:run_learning_gate_for_issue()`), and orchestrator hooks that all call the adapter behind one shared skip flag (`cli_args.py:214` → `issue_manager.py:880`, `worker_pool.py:64`, `cli/sprint/run.py:222`). `cli/harness.py` and `/ll:verify-issue-loop` become *consumers* of the oracle, not owners of the check.
- **Evidence-bundle transport follows the host** (placement review, 2026-07-30). With the check hosted by an oracle rather than `ll-harness`, `PrePatchEvidence` can no longer ride a harness-local `HarnessEvalOutcome`. It must reach the parent through the oracle's existing parent↔sub-loop token channel (the `subloop_outcome_<ID>.txt` idiom `code-run-gate` already uses) with the full bundle written under `${context.run_dir}/` per MR-3, and/or persisted to `.ll/history.db`. The harness path then reads the same artifact rather than producing its own.
- **Skip convention** (placement review, 2026-07-30; generalized 2026-08-02). The enable/disable knob must short-circuit to a SKIP pass-through when unset, never to a failure. Under the superseding executor-hosted placement this is the `tamper_guard` key's own convention — absent key (no state override, no loop default) means "not guarded," exactly as `fsm/executor.py:1305` resolves it. Under the previously-prescribed oracle placement it would have been `code-run-gate`'s null-command short-circuit. Either way it is the same mechanism as the config off-switch already required by Design Notes ("Price the check").

- **A dirty base invalidates the comparison, and nothing reads the dirty flag yet** (added 2026-08-02). ENH-2866 stamps **two** values, not one: `base_sha` *and* `base_dirty` — whether the tree had tracked modifications (`git status --porcelain --untracked-files=no`) at dequeue. Its commit message states the flag exists precisely for this consumer ("a base-state consumer reconstructs by checkout, so an untracked scratch file does not make the base approximate"). When `base_dirty` is true, a worktree forked from `base_sha` is **not** the pre-patch tree — it is missing the uncommitted work the change was actually built on. A candidate test can then fail there for reasons unrelated to the change, and a fake test is accepted as evidence: a false negative in exactly the direction this check exists to prevent. Required: (1) `history_reader.read_base_sha()` returns only the SHA (`history_reader.py:1816-1821`), so an additive `base_dirty` reader alongside it is in scope here; (2) `PrePatchEvidence` carries `base_dirty: bool | None`; (3) when the base was dirty, hard flags are downgraded to soft and the bundle says why — the check still reports, it just stops asserting.

- **Base resolution is the caller's job; the core stays DB-free** (added 2026-08-02). The reader is `history_reader.read_base_sha(issue_id, *, run_id=None, db=DEFAULT_DB_PATH)` — keyed by **issue_id**, reading `.ll/history.db`, never raising, returning `None` when unstamped. It deliberately does *not* implement the merge-base fallback (its docstring assigns that to the consumer), so this issue does own the fallback. Pin the split: the host resolves `(base_sha, base_dirty)` and passes them in; `run_prepatch_check()` takes them as arguments and performs no database access. `run_id` is a process-local uuid4 never exported to env, run-dir, or argv, so an out-of-process consumer must omit it and take the most-recent-stamped-row path. Note `code-run-gate.yaml` already declares `issue_id` as a required parameter, so the identifier is available on that path if the placement decision is ever revisited.

- **Prefer content-write over `git apply` for the partial patch** (added 2026-08-02, supersedes the "no partial-diff helper exists" framing in § Codebase Research). Still literally true that the repo has no `git apply` helper — but the partial-diff apply is avoidable entirely. `test_tamper_guard.read_paths_at_ref(repo_root, ref, paths)` (`:112`) and `snapshot_test_paths_at_ref()` (`:123`) already read file contents at an arbitrary ref without a worktree. The simpler construction: fork the worktree at `base_ref`, then write the *post-patch* test-file contents directly into it. No `git apply`, therefore no 3-way-merge conflict failure mode, no reject-hunk handling, and no new patch-parsing logic — which removes this issue's single largest new-logic risk. Pin content-write vs. `git apply` during implementation; content-write is the recommended default.

- **Hunk→nodeid mapping and the added-vs-modified split now have existing machinery** (added 2026-08-02, supersedes the "pin the approach" instruction in the mapping note above). `test_tamper_guard._test_functions(source) -> dict[str, ast.AST]` (`:311`) already extracts enclosing test definitions from source — the primitive for mapping hunk line ranges to test functions. `measure_test_strength()` (`:235`) and `filter_weakening_findings()` (`:333`) already perform before/after per-test AST comparison, which is exactly the discriminator the added-vs-modified verdict split needs (added test → must fail pre-patch, hard; modified test → soft by default). Consume these rather than re-deriving an AST layer or a `--collect-only` diff. The touched-files fallback for genuinely ambiguous hunks still applies.

- **The check must not trip the guard whose window it runs inside** (added 2026-08-02). `tamper_guard_changed_files()` (`test_tamper_guard.py:175-190`) unions `git diff --name-only HEAD` with `git ls-files --others --exclude-standard` at the repo root. `setup_worktree()` takes a caller-supplied `worktree_path`; if the pre-patch worktree lands under the repo root, this check's own scratch state can surface as untracked files and register as a tamper finding — a self-inflicted gate failure, and under `tamper_guard: fail` (which `code-run-gate.yaml:50` sets) that jumps the run straight to the failure terminal. Confirm during implementation that the pre-patch worktree path is outside the guarded scope, and cover it with a test rather than an assumption.

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
- **Superseding note (2026-08-02) — two claims above are now stale.** (1) "No partial-diff/`git apply` helper exists anywhere in the codebase today" remains true of `git apply`, but `test_tamper_guard.read_paths_at_ref()` (`:112`) / `snapshot_test_paths_at_ref()` (`:123`) now read file contents at an arbitrary ref, making the partial-diff apply avoidable entirely — see Design Notes, "Prefer content-write over `git apply`". (2) "No existing code implements this check" is still true of the check itself, but ENH-2854 (landed 2026-07-31) shipped the hosting mechanism, the AST test-function machinery, and the non-FSM adapter shape this issue should consume — see § Similar Patterns.
- **`project.test_patterns` is introduced by ENH-2973** (blocking, since completed 2026-07-28), modeled on the existing `scan.focus_dirs` list-of-globs shape and resolved via `resolve_variable()` in `scripts/little_loops/config/core.py:886`. This issue only *consumes* the shared `scripts/little_loops/test_file_patterns.py` module; it neither defines the config key, its schema entry, nor its per-template defaults.
- **Evidence-bundle dataclass convention**: `scripts/little_loops/issue_history/models.py`'s `Gap`/`GapAnalysis` classes (lines 259-302) and `scripts/little_loops/cli/verify_design_tokens.py`'s `ThemeViolation`/`ProfileResult` (lines 49-60) both follow the same shape — plain-field `@dataclass` + `to_dict()` method, list fields capped to a top-N for serialization — which is the convention a new per-test evidence-bundle dataclass for this issue should follow. Note: the command doc's reference to a `TestGap` class in `issue_history/models.py` does not match current code; the actual class is named `Gap`.

## Integration Map

### Files to Modify / Create

_Rewritten 2026-07-30 (placement review) — the check is hosted by a reusable oracle loop; `ll-harness` and `/ll:verify-issue-loop` are demoted from owners to consumers. See Design Notes, "Gate placement"._

_Layer 2 rewritten again 2026-08-02 — the oracle-state host is superseded by the executor's guarded-window mechanism that ENH-2854 shipped on 2026-07-31. See Design Notes, "Gate placement, superseded"._

**Layer 1 — gate core (no FSM or CLI knowledge):**
- `scripts/little_loops/prepatch_check.py` (new) — `run_prepatch_check()`, `collect_candidate_nodeids()`, and the `PrePatchTestOutcome` / `PrePatchEvidence` dataclasses per § Program Design. Consumes ENH-2973's `test_file_patterns` module for identification, and `test_tamper_guard`'s ref-reading (`read_paths_at_ref`) and AST (`_test_functions`, `filter_weakening_findings`) primitives per Design Notes. Performs **no** database access — the base state arrives as arguments.
- `scripts/little_loops/worktree_utils.py` — new additive sibling `setup_prepatch_worktree()` wrapping `setup_worktree()` (line 155): fork from the dequeue-time SHA / merge-base via the existing `base_branch` param, then materialize the post-patch test-file contents into the fork (content-write, not `git apply` — see Design Notes). `setup_worktree()` / `cleanup_worktree()` signatures unchanged. The worktree path must sit outside the tamper guard's repo-root scan scope.
- `scripts/little_loops/history_reader.py` — additive `base_dirty` reader alongside `read_base_sha()` (`:1816`), which returns the SHA only. Required by the dirty-base policy in Design Notes.

**Layer 2 — executor host (the reachability fix):**
- `scripts/little_loops/fsm/executor.py` / `fsm/schema.py` — host the check on the same guarded-window mechanism as ENH-2854's `tamper_guard` (`executor.py:1295-1384`; schema keys at `schema.py:690` loop-level and `:1311` state-level), which already brackets a state's entry and exit and therefore already holds the step diff this check consumes. Absent key = not guarded = SKIP, per the skip convention. Follow ENH-2854's shape for the record it leaves in `ctx.context`.
- `scripts/little_loops/work_verification.py` — the non-FSM adapter, mirroring how ENH-2854 reaches `issue_manager.py` and `parallel/worker_pool.py`. This is what gives `ll-auto` / `ll-parallel` coverage without a follow-up issue.
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — **no state added.** It already declares `tamper_guard: fail` at loop level (`:50`); it inherits this check the same way. Left unmodified.

**Layer 3 — consumers (read the oracle's result; do not re-implement the check):**
- `scripts/little_loops/cli/harness.py` — surface the pre-patch evidence alongside the existing `HarnessEvalOutcome` (line 242) / `_evaluate_and_report()` (line 251) path by reading the oracle's artifact, not by hosting the check.
- `skills/verify-issue-loop/SKILL.md` — document the deterministic state type as a delegation to the oracle; today (~L150-165, plus `templates.md`) this skill only generates LLM-judged `llm_structured` states with no deterministic check type at all (line refs verified 2026-07-29 after the skill's restructuring).

_No longer this issue's install sites (they were the sole install sites before the 2026-07-30 placement review): `cli/harness.py` and `/ll:verify-issue-loop` as owners of the check._

_Split out at epic review (2026-07-27) — no longer this issue's scope, consumed as dependencies:_
- `scripts/little_loops/loops/autodev.yaml` `dequeue_next` + `ll-parallel` worktree-creation SHA stamps → **ENH-2866**
- `project.test_patterns` config key, template defaults, and `scripts/little_loops/test_file_patterns.py` → **ENH-2973**

### Similar Patterns to Follow
- `scripts/little_loops/test_tamper_guard.py` + `fsm/executor.py:1295-1384` + `work_verification.py` (ENH-2854, landed 2026-07-31) — **the primary template**: the same class of gate, hosted on the executor's guarded window with a parallel non-FSM adapter. Reuse directly: `read_paths_at_ref()` (`:112`) / `snapshot_test_paths_at_ref()` (`:123`) for reading file contents at a ref without a worktree; `_test_functions()` (`:311`), `measure_test_strength()` (`:235`), `filter_weakening_findings()` (`:333`) for hunk→test-function attribution and the added-vs-modified split.
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
- ~~**Not this issue** (added 2026-07-30, placement review): hooking the check into `ll-auto` / `ll-parallel` / `ll-sprint` as a standalone CLI-level pre-flight.~~ **Reversed 2026-08-02**: the executor-hosted placement inherits ENH-2854's non-FSM adapter shape (`work_verification.py` → `issue_manager.py` / `parallel/worker_pool.py`), so the non-FSM path is now *in* scope as a thin adapter over the same `prepatch_check.py` core rather than a deferred follow-up issue. It was only ever deferred because the oracle-state host couldn't reach those callers.

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
- `PrePatchEvidence` — the per-step evidence bundle: `base_ref: str`, `base_source: str`, `base_dirty: bool | None`, `outcomes: list[PrePatchTestOutcome]`, `skipped_reason: str | None`, `to_dict() -> dict`

Both are new plain-field `@dataclass`es with `to_dict()` in a new module
`scripts/little_loops/prepatch_check.py`, following the `Gap`/`GapAnalysis`
convention. `category` is one of `pass | fail | error | timeout | flaky`;
`error_kind` distinguishes a collection/import error naming a post-patch module
from any other infrastructure error. `base_source` is `dequeue-stamp` or
`merge-base`, so the bundle names the base actually used. `base_dirty` (added
2026-08-02) carries ENH-2866's companion flag — `True` means the stamped tree had
tracked modifications at dequeue, so the fork is not faithfully the pre-patch
tree and hard flags are downgraded to soft; `None` means unknown (merge-base
fallback, or an unstamped run). `skipped_reason` is set when the config
off-switch disables the check, so the skip is explicit.

### Signatures

- `run_prepatch_check(step_diff: str, base_sha: str | None, base_dirty: bool | None, timeout_s: int) -> PrePatchEvidence`
- `collect_candidate_nodeids(step_diff: str, repo_root: Path) -> list[str]`
- `setup_prepatch_worktree(base_ref: str, test_files: dict[str, str], src_dir: str | None) -> Path`
- `is_test_file(path: str, config: BRConfig | None) -> bool`
- `read_base_sha(issue_id: str, *, run_id: str | None, db: Path | str) -> str | None` (existing, ENH-2866)

The first two are new in `prepatch_check.py`. `setup_prepatch_worktree()` is a new
additive sibling in `worktree_utils.py` wrapping `setup_worktree()` (fork from
`base_ref` via the existing `base_branch` parameter), then materializing the
post-patch test-file contents into the fork — `test_files` maps repo-relative
path to content, not a patch string, per the content-write decision in Design
Notes; `setup_worktree()` / `cleanup_worktree()` signatures are unchanged.
`is_test_file()` / `filter_test_files()` are ENH-2973's existing shared module,
consumed for candidate identification and never re-implemented here.
`read_base_sha()` is ENH-2866's existing never-raising reader in
`history_reader.py:1816`; it is called by the **host**, not by
`run_prepatch_check()`, which takes the resolved base as arguments and touches no
database. An additive `base_dirty` reader alongside it is in this issue's scope.

### Call Path

_Call path updated 2026-08-02: two hosts, one core — mirroring ENH-2854's
executor + `work_verification.py` split. Supersedes the 2026-07-30 oracle-state
entry point._

FSM host: executor guarded-window exit hook -> `read_base_sha` -> `run_prepatch_check` -> `collect_candidate_nodeids` -> `filter_test_files`

Non-FSM host: `work_verification.verify_work_was_done` -> `read_base_sha` -> `run_prepatch_check` -> (same chain)

`run_prepatch_check` -> `setup_prepatch_worktree` -> `setup_worktree` -> `cleanup_worktree`

Each host resolves `(base_sha, base_dirty)` and passes them in; the core is
database-free. The FSM host records its verdict in `ctx.context` following
ENH-2854's `_tamper_guard` record shape and writes the full `PrePatchEvidence`
bundle under `${context.run_dir}/` (MR-3). `_evaluate_and_report()` in
`cli/harness.py` reads that bundle and surfaces it alongside the existing
`HarnessEvalOutcome` — it does not call `run_prepatch_check()` itself. The
worktree create → run-in-isolation → teardown-in-finally shape and the src_dir
PYTHONPATH-injection fix are taken from `verify_epic_branch_before_merge`, and
per-test pass/fail/error classification mirrors `LLHistoryPlugin`.

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

_Placement ACs, rewritten 2026-08-02 — the 2026-07-30 oracle-state variants are
superseded. See Design Notes, "Gate placement, superseded":_

- [ ] The check is hosted on the executor's guarded-window mechanism (the shape ENH-2854 established at `fsm/executor.py:1295-1384`), not as a state inside `oracles/code-run-gate.yaml` and not inside `cli/harness.py`. `code-run-gate.yaml` is left unmodified.
- [ ] The check is reachable from the `rn-*` family's green-suite transitions; a test asserts a guarded loop (`rn-implement` / `rn-remediate` / `rn-refine`, transitively via `code-run-gate`) actually runs the check.
- [ ] A non-FSM adapter in `work_verification.py` reaches the same core from `ll-auto` / `ll-parallel`, mirroring ENH-2854's `issue_manager.py` / `worker_pool.py` wiring.
- [ ] The gate core lives in `prepatch_check.py` with no FSM, CLI, or database imports, so both hosts invoke the same implementation and the base state arrives as arguments.
- [ ] `cli/harness.py` surfaces the pre-patch evidence by reading the persisted bundle; it does not call `run_prepatch_check()` directly, and a test asserts the check is not re-implemented there.
- [ ] The FSM host records its verdict in `ctx.context` following ENH-2854's `_tamper_guard` record shape, with the full bundle written under `${context.run_dir}/` (MR-3) rather than only inside a harness-local dataclass.
- [ ] When the check's key is absent (no state override, no loop default), the guarded window short-circuits to SKIP rather than failing the gate.

_Added 2026-08-02 — base-state fidelity and self-interference:_

- [ ] The base state's `base_dirty` flag is read (via an additive reader alongside `read_base_sha()`) and recorded in the evidence bundle; when the base was dirty, hard flags are downgraded to soft with the reason stated, and a test covers the downgrade.
- [ ] The host resolves the base via `history_reader.read_base_sha(issue_id)` and passes it in; a test asserts `run_prepatch_check()` performs no database access.
- [ ] The pre-patch worktree is created outside the tamper guard's repo-root scan scope; a test asserts running this check inside a `tamper_guard`-guarded window produces no tamper finding attributable to the check itself.
- [ ] The pre-patch tree is constructed by writing post-patch test-file contents into the fork rather than by `git apply` of a partial diff (or, if `git apply` is chosen instead, reject-hunk failures are handled explicitly and recorded as a distinct skip reason).
- [ ] Hunk→test-function attribution and the added-vs-modified split consume `test_tamper_guard`'s existing AST helpers rather than a new AST layer or a `--collect-only` diff.


---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-08-02
- **Reason**: Issue too large for single session (size review score 9/11, 31 acceptance criteria, three declared layers, two hosts)

### Decomposed Into
- ENH-2991: Pre-patch check core — candidate identification, tree reconstruction, and verdict
- ENH-2997: Host the pre-patch check on the executor's guarded window
- ENH-2998: Non-FSM adapter and pre-patch evidence consumers

The split follows this issue's own Integration Map layers. ENH-2997 is blocked by
ENH-2991; ENH-2998 is blocked by both. All Proposed Change steps and Acceptance
Criteria are carried into the children — no scope was dropped. The superseding
2026-08-02 placement decision (executor guarded window, not an oracle state) is
preserved in ENH-2997's Motivation section along with the ruling-out half of the
2026-07-30 review.

## Status

**Decomposed** | Created: 2026-07-27 | Priority: P2

## Session Log
- `/ll:issue-size-review` - 2026-08-02T13:48:44 - `14957793-c5a3-42c3-8c4e-e15ef7fbe208.jsonl`
- pre-implementation review (manual, no skill) - 2026-08-02 - cleared `blocked_by` (ENH-2866 completed 2026-08-02; both blockers now done). Superseded the 2026-07-30 oracle-state placement with the executor guarded-window host that ENH-2854 established on 2026-07-31, rewriting Design Notes "Gate placement", Integration Map Layer 2, the Program Design call path, and 7 placement ACs. Added Design Notes and ACs for: `base_dirty` fidelity (ENH-2866 stamps it; no reader exists yet), host-side base resolution via `read_base_sha(issue_id)` with a DB-free core, content-write instead of `git apply`, reuse of `test_tamper_guard`'s AST helpers for hunk→nodeid attribution, and the check's potential to trip the tamper guard whose window it runs inside. Reversed the Scope Boundary that deferred the non-FSM `ll-auto`/`ll-parallel` path. **Size review not yet re-run** — still outstanding per § Impact.
- blocked_by reconciliation (manual, no skill) - 2026-08-01 - removed ENH-2973 from `blocked_by` (status: done, completed 2026-07-28); ENH-2866 remains blocking (open, undergoing refinement)
- gate-placement review (manual, no skill) - 2026-07-30 - rewrote `### Files to Modify / Create`, the Program Design call path, added Design Notes "Gate placement" / "Evidence-bundle transport" / "Oracle skip convention", 6 ACs, 1 Scope Boundary, 1 Impact note
- `/ll:format-issue` - 2026-07-27T20:01:08 - `74d428f0-7103-4a58-9168-ff504878fb04.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-27T19:42:08 - `e2303183-4e52-4649-af90-4b53254bbda4.jsonl`
- `/ll:wire-issue` - 2026-07-27T16:58:09 - `8416c0b2-f15d-4605-9d27-7401bd127ac6.jsonl`
- `/ll:refine-issue` - 2026-07-27T16:25:41 - `b315bd08-df31-4315-8e3d-4da1b2c0632d.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-27T15:59:42 - `29cf17b6-04b4-4b01-9444-64f1bfdbdaa5.jsonl`
