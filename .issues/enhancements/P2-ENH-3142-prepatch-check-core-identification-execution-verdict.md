---
id: ENH-3142
title: "prepatch_check.py core \u2014 candidate identification, execution, verdict,\
  \ and base_dirty-aware reporting"
type: ENH
priority: P2
status: open
discovered_date: 2026-08-10
epic: EPIC-2856
parent: ENH-2991
depends_on:
- ENH-3141
labels:
- rework
- verification
testable: true
learning_tests_required:
- pytest
verify_verdict: VALID
confidence_score: 90
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3142: prepatch_check.py core — candidate identification, execution, verdict, and base_dirty-aware reporting

## Summary

Implement `scripts/little_loops/prepatch_check.py`: identify candidate tests
from a step diff, run them against the pre-patch worktree (built by ENH-3141's
`setup_prepatch_worktree()`), and produce a `PrePatchEvidence` bundle with
per-test verdicts. Includes the additive `base_dirty` reader in
`history_reader.py` and the config off-switch.

The module performs **no** FSM, CLI, or database access — the base state
arrives as arguments. Hosting is ENH-2997 (FSM executor) and ENH-2998
(non-FSM adapter).

## Parent Issue

Decomposed from ENH-2991: Pre-patch check core — candidate identification, tree
reconstruction, and verdict. Covers Proposed Change steps 1, 3, 4, and 6
(identify, run, verdict, report), the `base_dirty` reader, and the config
off-switch. Depends on ENH-3141's `setup_prepatch_worktree()` for tree
reconstruction (step 2, out of scope here).

## Current Behavior

Verification loops judge new or modified tests only with LLM-judged
`llm_structured`/`check_semantic` criteria. There is no deterministic check of
whether a candidate test actually fails without the change it claims to
demonstrate — a test that passes on both the pre-patch and post-patch tree is
accepted as evidence with no mechanism to flag it. No code implements this
check today, and (as of ENH-3141) no evidence-bundle logic consumes the
pre-patch worktree primitive.

## Expected Behavior

`run_prepatch_check()` takes a step diff and a resolved base state, and returns
a `PrePatchEvidence` bundle recording, per candidate test: node ID, file,
whether it was added or modified, its pre-patch outcome, an outcome category
(`pass | fail | error | timeout | flaky`), and an error kind. A newly *added*
test that passes pre-patch is hard-flagged; a *modified* test that passes
pre-patch is soft-flagged by default.

## Proposed Change

1. **Identify the candidate tests** — from the step diff, collect test
   functions that were added or modified. Consume ENH-2973's shared
   `scripts/little_loops/test_file_patterns.py` (`is_test_file()` /
   `filter_test_files()`) for path classification; never re-implement a glob
   list.
2. **Run the candidate tests** in the worktree ENH-3141's
   `setup_prepatch_worktree()` produces, targeting only the identified node
   IDs, and record per-test pass/fail/error/timeout.
3. **Verdict** — added-and-passes-pre-patch is a hard flag; modified-and-passes-
   pre-patch is soft by default (configurable to hard). A pass is re-run once
   before hard-flagging; pass-then-fail is recorded as `flaky` and
   soft-flagged.
4. **Report** — populate `PrePatchEvidence` with per-test outcomes, the base
   actually used (`base_source`), `base_dirty`, and any `skipped_reason`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Wire the new `PrePatchCheckConfig` into `BRConfig` in `config/core.py` —
  construction (`:302-306`), a `prepatch_check` property (`:379-386`), and
  `to_dict()` serialization (`:802-812`) — in the same commit as the
  `config-schema.json` entry, or `test_config_schema.py::TestToDictSchemaParity`
  fails.
- Add `test_pre_patch_check_in_schema` to `test_config_schema.py`, modeled on
  `test_learning_tests_in_schema` (`:247`).
- Add `TestBRConfigPrePatchCheckIntegration` to `test_config.py`, modeled on
  `TestBRConfigLearningTestsIntegration` (`:3075-3107`), covering the
  `BRConfig`-level round-trip (not just the dataclass in isolation).
- Update `docs/reference/CONFIGURATION.md` with a `### \`prepatch_check\``
  section peer to `### \`learning_tests\`` (`:891`), not a table row peer to
  `confidence_gate.enabled`.
- Update `docs/reference/API.md:54`'s `little_loops.history_reader` Module
  Overview row to list the new `base_dirty` reader, and add a `prepatch_check`
  row to the `BRConfig` Properties table peer to `decisions`/`learning_tests`
  (`:158-159`).

## Design Notes

- **Hunk→nodeid mapping has existing machinery.** `test_tamper_guard._test_functions(source)`
  (`:369-380`) extracts enclosing test definitions from source;
  `measure_test_strength()` (`:287-342`) and `filter_weakening_findings()`
  (`:392` onward) perform before/after per-test AST comparison — exactly the
  discriminator the added-vs-modified split needs. Consume these rather than
  re-deriving an AST layer or a `--collect-only` diff. When function-level
  attribution is ambiguous (hunks outside any function body, conftest changes,
  shared fixtures), fall back to all test node IDs of the touched *files* —
  never the full suite.
- **Added vs. modified carry different contracts.** A newly added test must
  fail pre-patch — that is the clean "demonstrates the change" contract. A
  modified test routinely passes pre-patch legitimately (an assertion added, a
  tightened comparison, a rename). A hard flag on modified tests would punish
  exactly the assertion-strengthening behavior EPIC-2856 wants to encourage.
- A candidate test that **errors** pre-patch (import error because the new
  module doesn't exist yet) counts as failing — the expected outcome for a
  test of new code. Distinguish error-vs-fail in the report but treat both as
  "did not pass".
- **Error-category false-negative hole.** "Errors pre-patch is accepted" also
  accepts a fake test that errors for *infrastructure* reasons — e.g. it
  depends on a fixture added in `conftest.py`. ENH-2973's default patterns
  include `conftest.py`; assert that here (the worktree materializes it, per
  ENH-3141). The bundle records the error *category* — a collection/import
  error naming a post-patch module (expected) vs. anything else
  (fixture/infrastructure, suspicious).
- **Diff-scope caveat, same class of hole**: applying only the test-file
  portion means new *non-test* helpers a test imports are absent pre-patch.
  Import errors referencing non-target modules should be treated with
  suspicion in the report, not read as clean evidence.
- **Price the check: run only the candidate tests, never the suite.** The
  pre-patch invocation must target only the candidate node IDs
  (`pytest <nodeid> ...`). Ship a config off-switch for hosts where even the
  targeted run is too slow; when disabled, the bundle records "pre-patch check
  skipped by config" rather than silently omitting the section.
- **Time-box the pre-patch invocation.** A candidate test can *hang*
  pre-patch — waiting on a fixture, port, or blocking call that only exists
  post-patch. The invocation must be time-bounded (a fixed per-invocation
  timeout, configurable alongside the off-switch), and a timeout is its own
  outcome category, distinct from both fail and error.
- **Define the base state explicitly, but resolve it in the host.**
  "Pre-patch" means the tree at the SHA recorded when the issue was dequeued,
  falling back to merge-base with the base branch when no dequeue SHA is
  recorded — not `HEAD~1`. ENH-2866's `history_reader.read_base_sha(issue_id, *, run_id=None, db=DEFAULT_DB_PATH)`
  (`history_reader.py:1816-1869`, `run_id`-present vs.
  most-recent-non-null-row branching) is keyed by issue ID, never raises, and
  returns `None` when unstamped; its docstring assigns the merge-base fallback
  to the consumer, so **this issue owns the fallback logic** while the *host*
  owns the DB read. `run_prepatch_check()` takes `(base_sha, base_dirty)` as
  arguments and performs no database access.
- **A dirty base invalidates the comparison.** ENH-2866 stamps `base_dirty`
  alongside `base_sha` (tracked modifications at dequeue, via
  `git status --porcelain --untracked-files=no`). When true, a worktree forked
  from `base_sha` is missing the uncommitted work the change was built on; a
  candidate test can fail there for unrelated reasons and a fake test is
  accepted — a false negative in exactly the direction this check exists to
  prevent. `read_base_sha()` returns only the SHA, so an **additive
  `base_dirty` reader alongside it is in this issue's scope**. Write-side
  shape (`session_store/writers.py::record_orchestration_run()`,
  `:1264-1281`): `base_dirty: bool | None` is coerced to `int | None` before
  storage (`:1312`), and both `base_sha`/`base_dirty` are write-once via
  `COALESCE(excluded.x, x)` in the upsert (`:1336-1337`) — the reader must
  convert the stored int back to `bool | None` at the return boundary,
  mirroring `read_base_sha()`'s query pattern. When the base was dirty, hard
  flags are downgraded to soft and the bundle says why.
- Pure-refactor changes may legitimately have no new tests. Zero candidate
  tests is not a failure — report it explicitly rather than silently passing.
- Keep this independent of any LLM call. The whole value is that the signal is
  mechanical.
- **Host-agnostic core-module convention**: `test_tamper_guard.py`'s module
  docstring states the exact contract this module should mirror —
  "Deterministic only -- no LLM calls, no FSM or CLI-orchestrator knowledge.
  Adapters ... own step timing and call into this module; this module never
  calls into either adapter." Plain module-level functions plus `@dataclass`
  result types — never a class with instance state — tested by calling the
  functions directly with constructed inputs, no host spun up.
- **Retry-shape convention is contested, not singular.** `ready_issue.py::run_ready_issue_with_retry()`
  (`:83-127`) retries only on one named condition and returns a
  *differentiated* second attempt — the closer structural match to this
  issue's "pass → retry-once → pass-then-fail reclassified as flaky" policy.
  `parallel/git_lock.py::_run_with_retry()` (`:110-165`) instead loops with
  exponential backoff, re-running the *same* command — a uniform re-roll, not
  a differentiated retry. Neither is a full match; this issue's shape is new
  logic.
- **No subprocess-pytest node-ID-targeting precedent found anywhere in the
  codebase** — a repo-wide grep for `nodeid`/`node_id` across all
  subprocess-construction code returns zero hits outside DB/session-store
  contexts. `learning_tests/gate.py::run_learning_gate_for_issue()` (`:208`)
  is the closest analog for "subprocess result mapped to a distinct outcome
  category," though it is not pytest-specific and does not target node IDs.
- **Config off-switch convention**: `LearningTestsConfig` (`config/automation.py:498`)
  and `DecisionsConfig` (`config/automation.py:531-552`) each gate their
  entire feature with a lone `enabled: bool = False` field with no other
  threshold/knob sharing that flag — the closer analog than
  `ConfidenceGateConfig` for this issue's single-purpose off-switch.
  `LearningTestsConfig`'s test class (`test_config.py:3001`,
  `test_enabled_defaults_to_false()` at `:3015`,
  `test_enabled_from_dict()` at `:3020`) is the template. The parent config
  section (`automation`, `commands`, or a new top-level section) is not yet
  decided and should be pinned during implementation.

## Integration Map

### Files to Modify / Create

- `scripts/little_loops/prepatch_check.py` (new) — `run_prepatch_check()`,
  `collect_candidate_nodeids()`, and the `PrePatchTestOutcome` /
  `PrePatchEvidence` dataclasses per § Program Design. Consumes ENH-2973's
  `test_file_patterns` module, `test_tamper_guard`'s AST primitives
  (`_test_functions`, `filter_weakening_findings`), and ENH-3141's
  `setup_prepatch_worktree()`. **No** FSM, CLI, or database imports.
- `scripts/little_loops/history_reader.py` — additive `base_dirty` reader
  alongside `read_base_sha()` (`:1816`), which returns the SHA only.
- `scripts/little_loops/config-schema.json` — add the off-switch's schema
  entry as a peer to the `"confidence_gate"` block (`:457-477`).
- `scripts/little_loops/config/automation.py` — add a `PrePatchCheckConfig`-
  style dataclass (`enabled: bool = False` plus `from_dict()`), following
  `LearningTestsConfig`'s single-purpose-flag shape (`:498`).
  > ⚠ Superseded — belongs in `config/features.py`, not `automation.py` (see Codebase Research Findings below)
- `scripts/little_loops/config/core.py` — wire `PrePatchCheckConfig` into
  `BRConfig` at the three touchpoints `LearningTestsConfig`/`DecisionsConfig`
  use: construction (`_parse_config()`, `:302-306`), a `@property
  prepatch_check` (`:379-386`, adjacent to `learning_tests`/`decisions`), and
  `to_dict()` serialization (`:802-812`). Not in the issue's original Files to
  Modify list; required because `test_config_schema.py::TestToDictSchemaParity`
  (`:1099-1146`) diffs `config-schema.json`'s top-level `properties` against
  `BRConfig.to_dict().keys()` and fails if the schema entry lands without this
  wiring. [`/ll:wire-issue` finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py` — constructs, exposes via property,
  and serializes every `BRConfig` sub-config (see Files to Modify above); the
  new `PrePatchCheckConfig` must be added here in the same commit as the
  schema entry.

### Similar Patterns to Follow

- `test_tamper_guard.py` (ENH-2854, landed 2026-07-31) — `_test_functions()`
  (`:369-380`), `measure_test_strength()` (`:287-342`),
  `filter_weakening_findings()` (`:392` onward) for hunk→test-function
  attribution and the added-vs-modified split.
- `pytest_history_plugin.py`'s `LLHistoryPlugin.pytest_runtest_logreport()`
  (`:101-116`) — the applicable model for `PrePatchTestOutcome.category`
  derivation: `report.when == "call"` classifies `passed`/`failed`/`skipped`;
  `report.when in ("setup", "teardown")` with `report.failed` classifies as an
  **error**, matching this issue's error-vs-fail distinction. Only the hook
  dispatch logic is reusable — it has no `timeout`/`flaky` categories and
  persists only aggregate counts, never per-node-ID results.
- `scripts/little_loops/issue_history/models.py`'s `Gap`/`GapAnalysis`
  (lines 259-302) — plain-field `@dataclass` + `to_dict()` convention for
  `PrePatchEvidence` (write-only, never deserialized as currently scoped). If
  a future consumer (ENH-2997/ENH-2998) needs to re-read a persisted
  `PrePatchEvidence`, `LearnTestRecord` (`learning_tests/__init__.py:45-95+`)
  is the precedent for adding `from_dict`.
- `scripts/tests/test_history_reader.py::TestReadBaseSha` (`:2907`) and its
  `_stamp()` helper — the template for a new sibling `TestReadBaseDirty`
  class.

### Tests

- New test module for pre-patch/post-patch comparison — no existing file
  covers it.
- `scripts/tests/test_history_reader.py::TestReadBaseDirty` — modeled on
  `TestReadBaseSha` (`:2907`) and its `_stamp()` helper.
- `scripts/tests/test_config.py` — new `TestPrePatchCheckConfig`-style class,
  modeled on `LearningTestsConfig`'s test class (`:3001`).
- No existing precedent for pytest-nodeid argv construction, timeout-handling,
  or retry-once/flaky-reclassification tests — write from scratch, modeled on
  the general "mock subprocess with a side_effect, assert graceful
  non-raising fallback" pattern (`test_worker_pool.py::test_is_main_repo_dirty_none_when_git_fails`
  `:4040`).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py::TestBRConfigLearningTestsIntegration`
  (`:3075-3107`) — new sibling `TestBRConfigPrePatchCheckIntegration` class
  needed, covering `BRConfig`-level round-trip (defaults-when-absent,
  override-from-`.ll/ll-config.json`, `to_dict()` structural round-trip) —
  distinct from and in addition to the dataclass-level `TestPrePatchCheckConfig`
  class already listed above, which only exercises `PrePatchCheckConfig.from_dict()`
  in isolation. [Agent 3 finding]
- `scripts/tests/test_config_schema.py::TestConfigSchema.test_learning_tests_in_schema`
  (`:247`) and sibling `test_<block>_in_schema` methods — new
  `test_pre_patch_check_in_schema` needed, asserting `"pre_patch_check" in
  data["properties"]`, `additionalProperties is False`, and per-field
  `type`/`default`. [Agent 3 finding]
- `scripts/tests/test_config_schema.py::TestToDictSchemaParity`
  (`:1099-1146`) — pre-existing schema/`to_dict()` exact-set-diff guard, not a
  test to write, but a live gate: fails if the `config-schema.json` entry and
  the `config/core.py::to_dict()` wiring land in separate commits. [Agent 3
  finding]

### Documentation

- `docs/reference/API.md` — new Module Overview table row for
  `little_loops.prepatch_check`, a new `## little_loops.prepatch_check`
  section documenting `run_prepatch_check()`, `collect_candidate_nodeids()`,
  `PrePatchTestOutcome`, `PrePatchEvidence`, and a `### base_dirty` subsection
  peer to the existing `### read_base_sha` under
  `## little_loops.history_reader`.
- `docs/reference/CONFIGURATION.md` — table row and prose entry for the new
  pre-patch-check off-switch config key, peer to the existing
  `confidence_gate.enabled` row.
   > ⚠ Superseded — confidence_gate is nested under `commands`, not a top-level peer; see wiring finding below

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:891` — `### \`learning_tests\`` section
  header is the exact peer anchor for a new `### \`prepatch_check\`` section,
  not `confidence_gate.enabled` (which lives in a table at `:429-431`, nested
  under the `commands` config block, not top-level — a different, non-peer
  pattern). [Agent 2 finding]
- `docs/reference/API.md:54` — the `little_loops.history_reader` Module
  Overview row (single long line enumerating exported dataclasses/functions)
  needs `read_base_sha` and the new `base_dirty` reader added inline.
  [Agent 2 finding]
- `docs/reference/API.md:158-159` — `BRConfig` Properties table rows for
  `decisions` and `learning_tests` are the exact peer anchors for a new
  `prepatch_check` row (own top-level `BRConfig` property), not
  `confidence_gate` (referenced only inline inside the `commands` row
  description at `:145`, since it's a sub-config, not its own `BRConfig`
  property). [Agent 2 finding]

### Related Issues

- `ENH-3141` (blocking) — supplies `setup_prepatch_worktree()`, the tree
  this issue runs tests in.
- `ENH-2991` (parent) — the original undecomposed issue.
- `ENH-2997` (dependent) — hosts this core on the FSM executor's guarded
  window.
- `ENH-2998` (dependent) — non-FSM adapter and evidence consumers.
- `ENH-2973` (blocking, done 2026-07-28) — `project.test_patterns` + shared
  `test_file_patterns.py`, consumed here.
- `ENH-2866` (blocking, done 2026-08-02) — dequeue-time SHA stamp,
  `base_dirty` companion flag, and `read_base_sha()`.
- `ENH-2854` (peer, landed 2026-07-31) — supplies the AST primitives this
  core consumes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- `scripts/little_loops/config/automation.py` does not define `LearningTestsConfig`/`DecisionsConfig` — those classes live in `scripts/little_loops/config/features.py:495-524` (`LearningTestsConfig`) and `:532-551` (`DecisionsConfig`); `automation.py` is a separate 330-line module unrelated to this pattern. The new `PrePatchCheckConfig` dataclass belongs in `config/features.py`, wired into `BRConfig` the same way `LearningTestsConfig` is: `config/core.py:303-306` constructs it via `LearningTestsConfig.from_dict(self._raw_config.get("learning_tests", {}))`, exposes it via `@property learning_tests` (`core.py:380-382`), and serializes it back out at `core.py:802-806`.
- The `confidence_gate` schema block cited as a sibling-peer target (`config-schema.json:457-477`) is nested at `properties.commands.properties.confidence_gate` — under the `commands` section, not top-level. `decisions` and `learning_tests` (the dataclasses this issue's config actually mirrors) are top-level schema entries (`properties.decisions` at `:560`, `properties.learning_tests` at `:1052`). The still-open parent-section choice should track the dataclass's `features.py` peers (top-level) unless there's a specific reason to nest it under `commands` instead.
- A concrete precedent exists for testing a `subprocess.TimeoutExpired` side effect against a timeout-bounded subprocess call: `scripts/tests/test_learning_tests_gate.py:336` mocks `side_effect=subprocess.TimeoutExpired(cmd="ll-loop", timeout=86400 + 60)` against `learning_tests/gate.py::run_learning_gate_for_issue()`, whose own `subprocess.run(..., timeout=...)` call is wrapped in `try/except subprocess.TimeoutExpired` (`gate.py:293-313`) returning a value distinct from its returncode-failure path — the same shape this issue's own timeout test can model.

## Program Design

### Types

- `PrePatchTestOutcome` — one candidate test's result: `nodeid: str`,
  `file: str`, `added: bool`, `pre_patch: str`, `category: str`,
  `error_kind: str | None`
- `PrePatchEvidence` — the per-step bundle: `base_ref: str`,
  `base_source: str`, `base_dirty: bool | None`,
  `outcomes: list[PrePatchTestOutcome]`, `skipped_reason: str | None`,
  `to_dict() -> dict`

Both are new plain-field `@dataclass`es with `to_dict()` in
`scripts/little_loops/prepatch_check.py`, following the `Gap`/`GapAnalysis`
convention. `category` is one of `pass | fail | error | timeout | flaky`;
`error_kind` distinguishes a collection/import error naming a post-patch
module from any other infrastructure error. `base_source` is `dequeue-stamp`
or `merge-base`. `base_dirty` `True` means the stamped tree had tracked
modifications at dequeue; `None` means unknown. `skipped_reason` is set when
the config off-switch disables the check.

### Signatures

- `run_prepatch_check(step_diff: str, base_sha: str | None, base_dirty: bool | None, timeout_s: int) -> PrePatchEvidence`
- `collect_candidate_nodeids(step_diff: str, repo_root: Path) -> list[str]`
- `is_test_file(path: str, config: BRConfig | None) -> bool` (existing,
  ENH-2973)
- `read_base_sha(issue_id: str, *, run_id: str | None, db: Path | str) -> str | None`
  (existing, ENH-2866)
- `setup_prepatch_worktree(base_ref: str, test_files: dict[str, str], src_dir: str | None) -> Path`
  (existing, ENH-3141)

`run_id` is a process-local uuid4 never exported to env, run-dir, or argv, so
an out-of-process consumer must omit it and take the
most-recent-stamped-row path.

### Call Path

`run_prepatch_check` -> `collect_candidate_nodeids` -> `filter_test_files`

`run_prepatch_check` -> `setup_prepatch_worktree` (ENH-3141)

The core is database-free; `(base_sha, base_dirty)` arrive as arguments,
resolved by the host (ENH-2997 / ENH-2998).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- `test_tamper_guard._test_functions(source)` (`test_tamper_guard.py:369-380`) only sees **top-level** `FunctionDef`/`AsyncFunctionDef` nodes (`tree.body`, not `ast.walk`) — it does not see class-method tests (`class TestFoo: def test_bar(self): ...`) or nested test functions. A hunk inside a class-based test (this codebase's own suite uses `TestX::test_y` node IDs throughout) will not resolve via `_test_functions()` and must go through the "ambiguous attribution" fallback to the touched file's full node-ID set already specified in this issue's Design Notes.
- `pytest_history_plugin.LLHistoryPlugin.pytest_runtest_logreport()` (`pytest_history_plugin.py:101-116`) is the exact four-category dispatch model for `PrePatchTestOutcome.category`: `report.when == "call"` branches to `passed`/`failed`/`skipped`; `report.when in ("setup", "teardown")` with `report.failed` counts as **error** (matching this issue's error-vs-fail distinction), but only `report.when == "setup" and report.skipped` counts as skipped — a teardown-phase skip is not counted at all.

## Scope Boundaries

- **Not this issue**: the pre-patch worktree fork itself, content-write, or
  import isolation — that's `setup_prepatch_worktree()`, ENH-3141.
- **Not this issue**: hosting the check. The FSM executor guarded-window host
  is ENH-2997; the non-FSM `work_verification.py` adapter and the
  `cli/harness.py` / `skills/verify-issue-loop/` consumers are ENH-2998.
- **Not this issue**: the dequeue-time SHA stamp itself (ENH-2866, done) or
  the `project.test_patterns` config key and `test_file_patterns.py` module
  (ENH-2973, done). This issue only *consumes* both. The additive
  `base_dirty` *reader* is in scope, since ENH-2866 shipped only the SHA
  reader.
- **Not this issue**: replacing or removing the existing LLM-judged semantic
  criteria — this check is additive alongside them, never a substitute.
- **Not this issue**: running the full test suite pre-patch.
- **Not this issue**: `ENH-2854`'s tamper-guard `revert` policy.

## Acceptance Criteria

- [ ] Newly added and modified test functions are identified from a
      verification step's diff.
- [ ] Those tests are run against the pre-patch worktree ENH-3141 produces,
      targeting only the identified node IDs, not the full suite; a test
      asserts the constructed pytest command targets node IDs.
- [ ] A newly *added* candidate test that passes pre-patch is hard-flagged in
      the evidence bundle.
- [ ] A *modified* candidate test that passes pre-patch is recorded as soft
      by default, with a config option to escalate it to a hard flag.
- [ ] A candidate test that fails or errors pre-patch is accepted; the bundle
      records the error category (import/collection error naming a
      post-patch module vs. other infrastructure error).
- [ ] The base state is the dequeue-time SHA when provided, else the
      merge-base with the base branch; the chosen base is named in the
      bundle via `base_source`, and a test covers the unstamped fallback
      path.
- [ ] Test-file identification is done via ENH-2973's shared module, not a
      glob list defined here.
- [ ] The zero-candidate-tests case is reported explicitly rather than
      passing silently.
- [ ] Per-test results (name, file, pre-patch outcome, category) appear in
      `PrePatchEvidence`.
- [ ] The pre-patch pytest invocation is time-bounded; a timeout is its own
      outcome category (distinct from fail and error) and treated as "did
      not pass".
- [ ] A candidate test that passes pre-patch is re-run once before being
      hard-flagged; a pass-then-fail outcome is recorded as `flaky` and
      soft-flagged instead.
- [ ] When function-level attribution of a modified hunk is ambiguous, the
      check falls back to the touched files' test node IDs (never the full
      suite).
- [ ] A config off-switch disables the check; when disabled, the bundle
      records the skip explicitly via `skipped_reason`.
- [ ] The check makes no LLM calls.
- [ ] `base_dirty` is read via an additive reader alongside `read_base_sha()`
      and recorded in the bundle; when the base was dirty, hard flags are
      downgraded to soft with the reason stated, and a test covers the
      downgrade.
- [ ] `run_prepatch_check()` performs no database access; a test asserts it.
- [ ] Hunk→test-function attribution and the added-vs-modified split consume
      `test_tamper_guard`'s existing AST helpers rather than a new AST layer
      or a `--collect-only` diff.
- [ ] Tests cover: a fake test that passes pre-patch, a genuine test that
      fails pre-patch, a test that errors pre-patch, and the zero-test case.

## Impact

- **Priority**: P2 — the core of a real fake-evidence hole in verification
  loops (per EPIC-2856's rework-reduction goal).
- **Effort**: Large — the per-test evidence-bundle logic, retry/flaky
  reclassification, and node-ID-targeted subprocess invocation are all new
  logic with no in-repo template.
- **Risk**: Low-Medium — isolated to a new module plus a small additive
  reader; depends on ENH-3141 landing first for the worktree primitive.
- **Breaking Change**: No — new module and additive reader/config only.

## Status

**Open** | Created: 2026-08-10 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-10T09:17:36 - `df55e709-f5ba-4a76-ad27-3b49b1787402.jsonl`
- `/ll:verify-issues` - 2026-08-10T09:13:39 - `975b1509-c74d-48b1-aa22-7b2aab82c1b8.jsonl`
- `/ll:wire-issue` - 2026-08-10T09:09:22 - `c2aaebfe-05da-42f3-a4a2-a8cfac3be710.jsonl`
- `/ll:refine-issue` - 2026-08-10T09:00:02 - `6cc40244-b7c6-46f8-923a-e7ed2ee0134d.jsonl`
- `/ll:issue-size-review` - 2026-08-10T07:23:33 - `7e0f8f7e-cdcf-448e-8ae7-22d89c36b63b.jsonl`
