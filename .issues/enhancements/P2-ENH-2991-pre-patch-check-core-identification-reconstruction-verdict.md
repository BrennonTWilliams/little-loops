---
id: ENH-2991
title: "Pre-patch check core \u2014 candidate identification, tree reconstruction,\
  \ and verdict"
type: ENH
priority: P2
status: open
discovered_date: 2026-08-02
epic: EPIC-2856
parent: ENH-2853
labels:
- rework
- verification
testable: true
learning_tests_required:
- pytest
size: Large
---

# ENH-2991: Pre-patch check core — candidate identification, tree reconstruction, and verdict

## Summary

Implement the deterministic pre-patch test-failure check as a standalone,
host-agnostic core in a new `scripts/little_loops/prepatch_check.py`: identify
candidate tests from a step diff, reconstruct the pre-patch tree in an isolated
worktree with only the test-file contents applied, run only those tests, and
produce a `PrePatchEvidence` bundle with per-test verdicts.

The module performs **no** FSM, CLI, or database access — the base state arrives
as arguments. Hosting is ENH-2997 (FSM executor) and ENH-2998 (non-FSM adapter).

## Parent Issue

Decomposed from ENH-2853: Deterministic pre-patch test-failure check in
verification loops. Covers § Proposed Change steps 1-4 and 6, and Integration Map
Layer 1.

## Current Behavior

Verification loops judge new or modified tests only with LLM-judged
`llm_structured`/`check_semantic` criteria. There is no deterministic check of
whether a candidate test actually fails without the change it claims to
demonstrate — a test that passes on both the pre-patch and post-patch tree is
accepted as evidence with no mechanism to flag it. No code implements this check
today.

## Expected Behavior

`run_prepatch_check()` takes a step diff and a resolved base state, and returns a
`PrePatchEvidence` bundle recording, per candidate test: node ID, file, whether
it was added or modified, its pre-patch outcome, an outcome category
(`pass | fail | error | timeout | flaky`), and an error kind. A newly *added*
test that passes pre-patch is hard-flagged; a *modified* test that passes
pre-patch is soft-flagged by default. The user's working tree is unchanged
afterwards, including on failure paths.

## Proposed Change

1. **Identify the candidate tests** — from the step diff, collect test functions
   that were added or modified. Consume ENH-2973's shared
   `scripts/little_loops/test_file_patterns.py` (`is_test_file()` /
   `filter_test_files()`) for path classification; never re-implement a glob list.
2. **Reconstruct the pre-patch tree** — fork a worktree at the base ref via
   `setup_prepatch_worktree()`, then write the *post-patch* test-file contents
   into it (content-write, not `git apply`).
3. **Run the candidate tests there**, targeting only the identified node IDs, and
   record per-test pass/fail/error/timeout.
4. **Verdict** — added-and-passes-pre-patch is a hard flag; modified-and-passes-
   pre-patch is soft by default (configurable to hard). A pass is re-run once
   before hard-flagging; pass-then-fail is recorded as `flaky` and soft-flagged.
5. **Report** — populate `PrePatchEvidence` with per-test outcomes, the base
   actually used (`base_source`), `base_dirty`, and any `skipped_reason`.

## Design Notes

- Apply *only* the test-file portion of the change. Applying the full diff
  defeats the purpose; applying nothing means the tests don't exist to run.
- **Prefer content-write over `git apply`.** `test_tamper_guard.read_paths_at_ref(repo_root, ref, paths)`
  (`:112`) and `snapshot_test_paths_at_ref()` (`:123`) already read file contents
  at an arbitrary ref without a worktree. Fork at `base_ref`, then write the
  post-patch test-file contents directly in. No patch parsing, no 3-way-merge
  conflict mode, no reject-hunk handling — this removes the single largest
  new-logic risk. Pin content-write vs. `git apply` during implementation;
  content-write is the recommended default.
- **Hunk→nodeid mapping has existing machinery.** `test_tamper_guard._test_functions(source)`
  (`:311`) extracts enclosing test definitions from source;
  `measure_test_strength()` (`:235`) and `filter_weakening_findings()` (`:333`)
  perform before/after per-test AST comparison — exactly the discriminator the
  added-vs-modified split needs. Consume these rather than re-deriving an AST
  layer or a `--collect-only` diff. When function-level attribution is ambiguous
  (hunks outside any function body, conftest changes, shared fixtures), fall back
  to all test node IDs of the touched *files* — never the full suite.
- **Added vs. modified carry different contracts.** A newly added test must fail
  pre-patch — that is the clean "demonstrates the change" contract. A modified
  test routinely passes pre-patch legitimately (an assertion added, a tightened
  comparison, a rename). A hard flag on modified tests would punish exactly the
  assertion-strengthening behavior EPIC-2856 wants to encourage.
- A candidate test that **errors** pre-patch (import error because the new module
  doesn't exist yet) counts as failing — the expected outcome for a test of new
  code. Distinguish error-vs-fail in the report but treat both as "did not pass".
- **Error-category false-negative hole.** "Errors pre-patch is accepted" also
  accepts a fake test that errors for *infrastructure* reasons — e.g. it depends
  on a fixture added in `conftest.py`. ENH-2973's default patterns include
  `conftest.py`; assert that here. The bundle records the error *category* — a
  collection/import error naming a post-patch module (expected) vs. anything else
  (fixture/infrastructure, suspicious).
- **Diff-scope caveat, same class of hole**: applying only the test-file portion
  means new *non-test* helpers a test imports are absent pre-patch. Import errors
  referencing non-target modules should be treated with suspicion in the report,
  not read as clean evidence.
- **Price the check: run only the candidate tests, never the suite.** The
  pre-patch invocation must target only the candidate node IDs
  (`pytest <nodeid> ...`). Ship a config off-switch for hosts where even the
  targeted run is too slow; when disabled, the bundle records
  "pre-patch check skipped by config" rather than silently omitting the section.
- **Time-box the pre-patch invocation.** A candidate test can *hang* pre-patch —
  waiting on a fixture, port, or blocking call that only exists post-patch. The
  invocation must be time-bounded (a fixed per-invocation timeout, configurable
  alongside the off-switch), and a timeout is its own outcome category, distinct
  from both fail and error.
- **Import isolation is load-bearing in editable-install repos.** A worktree
  checkout of the pre-patch tree can still import the *main-tree* package when
  the project is installed editable (the install pins an absolute path). A
  "pre-patch" run that imports post-patch code passes trivially and reports
  garbage. Resolve imports from the worktree (PYTHONPATH injection ahead of
  site-packages), and prove the isolation with a test. Direct precedent:
  `verify_epic_branch_before_merge()`'s `src_dir` parameter
  (`worktree_utils.py:399-409`, applied at `467-473`); read `BUG-2629`,
  `BUG-2640`, `BUG-2649` before implementing.
- **Define the base state explicitly, but resolve it in the host.** "Pre-patch"
  means the tree at the SHA recorded when the issue was dequeued, falling back to
  merge-base with the base branch when no dequeue SHA is recorded — not
  `HEAD~1`. ENH-2866's `history_reader.read_base_sha(issue_id, *, run_id=None, db=DEFAULT_DB_PATH)`
  (`history_reader.py:1816-1821`) is keyed by issue ID, never raises, and returns
  `None` when unstamped; its docstring assigns the merge-base fallback to the
  consumer, so **this issue owns the fallback logic** while the *host* owns the
  DB read. `run_prepatch_check()` takes `(base_sha, base_dirty)` as arguments and
  performs no database access.
- **A dirty base invalidates the comparison.** ENH-2866 stamps `base_dirty`
  alongside `base_sha` (tracked modifications at dequeue, via
  `git status --porcelain --untracked-files=no`). When true, a worktree forked
  from `base_sha` is missing the uncommitted work the change was built on; a
  candidate test can fail there for unrelated reasons and a fake test is accepted
  — a false negative in exactly the direction this check exists to prevent.
  `read_base_sha()` returns only the SHA, so an **additive `base_dirty` reader
  alongside it is in this issue's scope**. When the base was dirty, hard flags
  are downgraded to soft and the bundle says why.
- **The check must not trip the guard whose window it runs inside.**
  `tamper_guard_changed_files()` (`test_tamper_guard.py:175-190`) unions
  `git diff --name-only HEAD` with `git ls-files --others --exclude-standard` at
  the repo root. `setup_worktree()` takes a caller-supplied `worktree_path`; if
  the pre-patch worktree lands under the repo root, this check's own scratch
  state surfaces as untracked files and registers as a tamper finding — and under
  `tamper_guard: fail` (which `code-run-gate.yaml:50` sets) that jumps the run
  straight to the failure terminal. The pre-patch worktree path must sit outside
  the guarded scope, covered by a test rather than an assumption.
- Use an isolated worktree rather than mutating the working tree in place; a
  verification check must never leave the user's tree in a different state than
  it found it.
- Pure-refactor changes may legitimately have no new tests. Zero candidate tests
  is not a failure — report it explicitly rather than silently passing.
- Keep this independent of any LLM call. The whole value is that the signal is
  mechanical.

## Integration Map

### Files to Modify / Create

- `scripts/little_loops/prepatch_check.py` (new) — `run_prepatch_check()`,
  `collect_candidate_nodeids()`, and the `PrePatchTestOutcome` /
  `PrePatchEvidence` dataclasses per § Program Design. Consumes ENH-2973's
  `test_file_patterns` module for identification and `test_tamper_guard`'s
  ref-reading (`read_paths_at_ref`) and AST (`_test_functions`,
  `filter_weakening_findings`) primitives. **No** FSM, CLI, or database imports.
- `scripts/little_loops/worktree_utils.py` — new additive sibling
  `setup_prepatch_worktree()` wrapping `setup_worktree()` (`:155`): fork from the
  base ref via the existing `base_branch` param (validated by `git rev-parse
  --verify`, lines 201-208), then materialize the post-patch test-file contents
  into the fork. `setup_worktree()` / `cleanup_worktree()` signatures **unchanged**
  — `fsm/executor.py` (~927), `cli/loop/run.py` (~472), and
  `parallel/orchestrator.py` all call them directly.
- `scripts/little_loops/history_reader.py` — additive `base_dirty` reader
  alongside `read_base_sha()` (`:1816`), which returns the SHA only.

### Similar Patterns to Follow

- `scripts/little_loops/test_tamper_guard.py` (ENH-2854, landed 2026-07-31) —
  `read_paths_at_ref()` (`:112`) / `snapshot_test_paths_at_ref()` (`:123`) for
  reading file contents at a ref without a worktree; `_test_functions()` (`:311`),
  `measure_test_strength()` (`:235`), `filter_weakening_findings()` (`:333`) for
  hunk→test-function attribution and the added-vs-modified split.
- `verify_epic_branch_before_merge()` (`worktree_utils.py:364-494`) — the
  create → run-in-isolation → teardown-in-`finally` shape (worktree at 433-442,
  run at 475-491, teardown at 493-494 regardless of outcome), plus its `src_dir`
  PYTHONPATH-injection fix for editable-install import isolation.
- `scripts/little_loops/pytest_history_plugin.py`'s `LLHistoryPlugin` (`:81`) —
  per-test pass/fail/error classification via `pytest_runtest_logreport`,
  distinguishing `call`-phase failures (real failures) from `setup`/`teardown`-phase
  failures (errors). Registered via the `pytest11` entry point.
- `oracles/code-run-gate.yaml`'s `run_test` state (lines 201-249) — alternative
  pass/fail parsing via `pytest.json`'s `summary` dict; see
  `.ll/learning-tests/pytest-json-report.md` for the proven contract
  (`summary.passed + failed + skipped == total`).
- `scripts/little_loops/issue_history/models.py`'s `Gap`/`GapAnalysis`
  (lines 259-302) — plain-field `@dataclass` + `to_dict()` convention for the new
  evidence-bundle structure. (The command doc's reference to a `TestGap` class
  does not match current code; the actual class is named `Gap`.)

### Tests

- New test module for pre-patch/post-patch comparison — no existing file covers it.
- `scripts/tests/test_worktree_utils.py` — extend for `setup_prepatch_worktree()`.
  `TestVerifyEpicBranchBeforeMerge` (lines 350-690), specifically
  `test_src_dir_prepends_worktree_source_onto_pythonpath` (`:447`),
  `test_falsy_src_dir_leaves_pythonpath_uninjected` (`:479`), and
  `test_verify_gate_marker_set_in_child_env` (`:556`) are the direct template for
  the import-isolation tests (probe-subprocess pattern via inline `python3 -c`).
- `scripts/tests/test_orchestrator.py` patches
  `little_loops.worktree_utils.setup_worktree` at ~7 sites (lines 1761-1888) and
  `scripts/tests/test_cli_loop_worktree.py` covers `ll-loop run --worktree` —
  both must keep passing, which the additive-signature constraint guarantees.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Line-number corrections** (verified against current code): `setup_worktree()` starts at `worktree_utils.py:157` (not 155); `verify_epic_branch_before_merge()` spans `worktree_utils.py:371-501` (not 364-494); the `src_dir` PYTHONPATH-injection code itself is at `worktree_utils.py:474-480` (the docstring describing it is at 406-423 — the earlier `~399-473` range covers the docstring, not the injection line).
- `_test_functions(source: str) -> dict[str, ast.AST] | None` (`test_tamper_guard.py:311-321`) is a **private, unexported** helper (top-level `FunctionDef`/`AsyncFunctionDef` nodes named `test*`, keyed by name; returns `None` on `SyntaxError`). Consuming it means an internal import (`from little_loops.test_tamper_guard import _test_functions`), not a public API call — worth confirming that's acceptable or whether it should be promoted to a public name as part of this change.
- `read_paths_at_ref(repo_root, ref, paths) -> dict[str, str | None]` (`test_tamper_guard.py:112-120`) already does exactly the "read file content at an arbitrary ref" operation this issue needs for reconstructing pre-patch test-file text (`git show {ref}:{path}` via the module's `_git()` helper, `test_tamper_guard.py:508-522`). A repo-wide grep for `git apply` returns zero hits — there is no existing content-materialization precedent to compare content-write against; `read_paths_at_ref` is the only established primitive in this space, and it already points toward content-write (it returns text to be written, not a diff to be applied).
- `setup_worktree()`'s existing `copy_files` mechanism (`worktree_utils.py:245-262`) copies **whole files from the main repo** into the worktree (`shutil.copy2`) — it does not accept synthesized in-memory content. `setup_prepatch_worktree()`'s `test_files: dict[str, str]` content-write is a genuinely new capability, not a reuse of `copy_files` under a different name.
- **No existing precedent for two design decisions this issue specifies**: (1) a "run once, retry on pass, reclassify pass-then-fail as flaky" loop — a repo-wide grep for `flaky`/`retry.*once`/`re-run.*once` returns only unrelated test-fixture/doc hits; (2) a subprocess pytest invocation targeting a *subset* of node IDs — both existing pytest-invocation patterns in the repo (`pytest_history_plugin.py`'s in-process `pytest11` plugin, and `code-run-gate.yaml`'s `run_test` state via `pytest --json-report`) run whatever `test_cmd` names, which is normally the full suite. Both are new logic with no in-repo template to follow, not oversights in this research pass.
- **Off-switch convention disagreement in the codebase** — two shapes exist: `verify_epic_branch_before_merge()`'s `verify_before_merge: bool` param short-circuits to a silent `(True, None, None)` with no recorded reason (`worktree_utils.py:434-435`); `run_learning_gate_for_issue()`'s `skip: bool` param and `code-run-gate.yaml`'s `run_test`/`run_build` states instead short-circuit to an explicitly named skip state (`"skipped"` / `"SKIP test_cmd=null"` written to output). This issue's `skipped_reason: str | None` field matches the second, explicit-record convention, not the first. For the `BRConfig`-backed boolean itself, the dominant idiom is a plain `enabled: bool` dataclass field with a `from_dict(data.get("enabled", default))` reader (e.g. `ConfidenceGateConfig` in `config/automation.py:143-159`), distinct from the FSM-level "presence of a key marks it active" convention `StateConfig.tamper_guard` uses (`fsm/schema.py:690`) — the two are not interchangeable, and this issue's off-switch is a `BRConfig` concern, not an FSM one.

### Related Issues

- `ENH-2997` (dependent) — hosts this core on the FSM executor's guarded window.
- `ENH-2998` (dependent) — non-FSM adapter and evidence consumers.
- `ENH-2973` (blocking, done 2026-07-28) — `project.test_patterns` + shared
  `test_file_patterns.py`, consumed here.
- `ENH-2866` (blocking, done 2026-08-02) — dequeue-time SHA stamp,
  `base_dirty` companion flag, and `read_base_sha()`.
- `ENH-2854` (peer, landed 2026-07-31) — supplies the AST and ref-reading
  primitives this core consumes.

## Program Design

### Types

- `PrePatchTestOutcome` — one candidate test's result: `nodeid: str`, `file: str`,
  `added: bool`, `pre_patch: str`, `category: str`, `error_kind: str | None`
- `PrePatchEvidence` — the per-step bundle: `base_ref: str`, `base_source: str`,
  `base_dirty: bool | None`, `outcomes: list[PrePatchTestOutcome]`,
  `skipped_reason: str | None`, `to_dict() -> dict`

Both are new plain-field `@dataclass`es with `to_dict()` in
`scripts/little_loops/prepatch_check.py`, following the `Gap`/`GapAnalysis`
convention. `category` is one of `pass | fail | error | timeout | flaky`;
`error_kind` distinguishes a collection/import error naming a post-patch module
from any other infrastructure error. `base_source` is `dequeue-stamp` or
`merge-base`, so the bundle names the base actually used. `base_dirty` `True`
means the stamped tree had tracked modifications at dequeue, so the fork is not
faithfully the pre-patch tree and hard flags are downgraded to soft; `None` means
unknown (merge-base fallback, or an unstamped run). `skipped_reason` is set when
the config off-switch disables the check, so the skip is explicit.

### Signatures

- `run_prepatch_check(step_diff: str, base_sha: str | None, base_dirty: bool | None, timeout_s: int) -> PrePatchEvidence`
- `collect_candidate_nodeids(step_diff: str, repo_root: Path) -> list[str]`
- `setup_prepatch_worktree(base_ref: str, test_files: dict[str, str], src_dir: str | None) -> Path`
- `is_test_file(path: str, config: BRConfig | None) -> bool` (existing, ENH-2973)
- `read_base_sha(issue_id: str, *, run_id: str | None, db: Path | str) -> str | None` (existing, ENH-2866)

`test_files` maps repo-relative path to content, not a patch string, per the
content-write decision. `run_id` is a process-local uuid4 never exported to env,
run-dir, or argv, so an out-of-process consumer must omit it and take the
most-recent-stamped-row path.

### Call Path

`run_prepatch_check` -> `collect_candidate_nodeids` -> `filter_test_files`

`run_prepatch_check` -> `setup_prepatch_worktree` -> `setup_worktree` -> `cleanup_worktree`

The core is database-free; `(base_sha, base_dirty)` arrive as arguments, resolved
by the host (ENH-2997 / ENH-2998).

## Scope Boundaries

- **Not this issue**: hosting the check. The FSM executor guarded-window host is
  ENH-2997; the non-FSM `work_verification.py` adapter and the `cli/harness.py` /
  `skills/verify-issue-loop/` consumers are ENH-2998.
- **Not this issue**: the dequeue-time SHA stamp itself (ENH-2866, done) or the
  `project.test_patterns` config key and `test_file_patterns.py` module
  (ENH-2973, done). This issue only *consumes* both. The additive `base_dirty`
  *reader* is in scope, since ENH-2866 shipped only the SHA reader.
- **Not this issue**: replacing or removing the existing LLM-judged semantic
  criteria — this check is additive alongside them, never a substitute.
- **Not this issue**: running the full test suite pre-patch.
- **Not this issue**: `ENH-2854`'s tamper-guard `revert` policy.

## Acceptance Criteria

- [ ] Newly added and modified test functions are identified from a verification step's diff.
- [ ] Those tests are run against the pre-patch tree with only the test changes applied, in an isolated worktree.
- [ ] A newly *added* candidate test that passes pre-patch is hard-flagged in the evidence bundle.
- [ ] A *modified* candidate test that passes pre-patch is recorded as soft by default, with a config option to escalate it to a hard flag.
- [ ] A candidate test that fails or errors pre-patch is accepted; the bundle records the error category (import/collection error naming a post-patch module vs. other infrastructure error).
- [ ] `conftest.py` changes are applied to the pre-patch tree (guaranteed by ENH-2973's default patterns; assert it here rather than re-implementing it).
- [ ] The pre-patch run resolves imports from the pre-patch worktree, not the main tree's editable install; a test proves a post-patch-only module is unimportable in the pre-patch run.
- [ ] The base state is the dequeue-time SHA when provided, else the merge-base with the base branch; the chosen base is named in the bundle via `base_source`, and a test covers the unstamped fallback path.
- [ ] Test-file identification is done via ENH-2973's shared module, not a glob list defined here.
- [ ] The zero-candidate-tests case is reported explicitly rather than passing silently.
- [ ] Per-test results (name, file, pre-patch outcome, post-patch outcome) appear in `PrePatchEvidence`.
- [ ] The user's working tree is unchanged after the check runs, including on failure paths.
- [ ] The pre-patch run invokes only the candidate test node IDs, not the full suite; a test asserts the constructed pytest command targets node IDs.
- [ ] The pre-patch pytest invocation is time-bounded; a timeout is its own outcome category (distinct from fail and error) and treated as "did not pass".
- [ ] A candidate test that passes pre-patch is re-run once before being hard-flagged; a pass-then-fail outcome is recorded as `flaky` and soft-flagged instead.
- [ ] When function-level attribution of a modified hunk is ambiguous, the check falls back to the touched files' test node IDs (never the full suite).
- [ ] A config off-switch disables the check; when disabled, the bundle records the skip explicitly via `skipped_reason`.
- [ ] The check makes no LLM calls.
- [ ] `base_dirty` is read via an additive reader alongside `read_base_sha()` and recorded in the bundle; when the base was dirty, hard flags are downgraded to soft with the reason stated, and a test covers the downgrade.
- [ ] `run_prepatch_check()` performs no database access; a test asserts it.
- [ ] The pre-patch worktree is created outside the tamper guard's repo-root scan scope; a test asserts running the check inside a `tamper_guard`-guarded window produces no tamper finding attributable to the check itself.
- [ ] The pre-patch tree is constructed by writing post-patch test-file contents into the fork rather than by `git apply` of a partial diff (or, if `git apply` is chosen instead, reject-hunk failures are handled explicitly and recorded as a distinct skip reason).
- [ ] Hunk→test-function attribution and the added-vs-modified split consume `test_tamper_guard`'s existing AST helpers rather than a new AST layer or a `--collect-only` diff.
- [ ] `setup_worktree()` / `cleanup_worktree()` signatures are unchanged; existing call sites in `fsm/executor.py`, `cli/loop/run.py`, and `parallel/orchestrator.py` keep passing.
- [ ] Tests cover: a fake test that passes pre-patch, a genuine test that fails pre-patch, a test that errors pre-patch, and the zero-test case.

## Impact

- **Priority**: P2 — the core of a real fake-evidence hole in verification loops
  (per EPIC-2856's rework-reduction goal).
- **Effort**: Large — new worktree-fork-plus-content-write primitive, a new
  per-test evidence-bundle dataclass, and import-isolation handling for editable
  installs.
- **Risk**: Medium — `setup_worktree()`/`cleanup_worktree()` are called directly
  by `fsm/executor.py`, `cli/loop/run.py`, and `parallel/orchestrator.py`; any
  signature change must stay additive. The check is otherwise isolated
  (worktree-scoped, non-mutating on failure).
- **Breaking Change**: No — additive worktree variant and a new module.

## Status

**Open** | Created: 2026-08-02 | Priority: P2

## Session Log
- `/ll:refine-issue` - 2026-08-02T15:16:50 - `2231e95c-29bd-4ab8-9d98-d3859068eb51.jsonl`
- `/ll:issue-size-review` - 2026-08-02T13:48:43 - `14957793-c5a3-42c3-8c4e-e15ef7fbe208.jsonl`

## Related Key Documentation

- `docs/reference/API.md` — documents `history_reader` (`read_base_sha()`, consumed here) and `work_verification`; this issue's new `prepatch_check.py` module and `worktree_utils.setup_prepatch_worktree()` addition sit directly alongside those documented modules.
