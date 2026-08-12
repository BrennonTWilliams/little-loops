---
id: ENH-3142
title: "prepatch_check.py core \u2014 candidate identification, execution, verdict,\
  \ and base_dirty-aware reporting"
type: ENH
priority: P2
status: done
discovered_date: 2026-08-10
completed_at: '2026-08-12T19:04:23Z'
epic: EPIC-2856
parent: ENH-2991
depends_on:
- ENH-3141
- ENH-3152
labels:
- rework
- verification
testable: true
learning_tests_required:
- pytest
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 85
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
reconcile_attempted: true
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
off-switch. Consumes ENH-3141's (done) `setup_prepatch_worktree()` for tree
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
   IDs, and record per-test pass/fail/error/timeout. `setup_prepatch_worktree()`'s
   `test_files` argument is the **post-patch** test content (see § The
   `test_files` Contract) — the whole check is new tests against old source.
3. **Verdict** — added-and-passes-pre-patch is a hard flag; modified-and-passes-
   pre-patch is soft by default (configurable to hard). A pass is re-run once
   before hard-flagging; pass-then-fail is recorded as `flaky` and
   soft-flagged.
4. **Report** — populate `PrePatchEvidence` with per-test outcomes, the base
   actually used (`base_source`), `base_dirty`, and any `skipped_reason`.

### The `test_files` Contract

`setup_prepatch_worktree(repo_path, worktree_base, base_ref, test_files,
logger, git_lock, src_dir)` (`worktree_utils.py:329-335`) forks a worktree at
`base_ref` and then **writes `test_files` over it** via `Path.write_text()`.
The value passed must therefore be the **post-patch** content of each touched
test file — new/modified tests laid onto the old source tree. That is the
entire mechanism of the check.

ENH-3141's docstring describes `test_files` as "same shape as
`read_paths_at_ref()`'s return value" — **shape only**. Passing
`read_paths_at_ref()`'s actual output would re-materialize the *base* content
over a tree that already has it, making every candidate trivially
fail-or-error and the check a no-op that always reports "clean". Implementation
must not read the base content into `test_files`.

Pin during implementation:

- **Source of the post-patch content**: the live working tree
  (`(repo_root / path).read_text()`) for each touched test path, which is what
  `filter_weakening_findings()` already does for its `after` texts
  (`test_tamper_guard.py` `_read_text(repo_root / path)`). Reconstructing
  content by applying `step_diff` is *not* required and should not be built.
- **Which paths get materialized**: every touched path for which
  `is_test_file()` is True — which by ENH-2973's default patterns includes
  `conftest.py`. Materializing the post-patch `conftest.py` is required, not
  incidental: it is what closes the fixture-added-in-conftest false negative
  described in § Design Notes.
- Non-test files are never materialized. That asymmetry is the intended
  semantics and the source of the import-error caveat in § Design Notes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Wire the new `PrePatchCheckConfig` into `BRConfig` in `config/core.py` —
  construction (`:302-306`), a `prepatch_check` property (`:379-386`), and
  `to_dict()` serialization (`:802-812`) — in the same commit as the
  `config-schema.json` entry, or `test_config_schema.py::TestToDictSchemaParity`
  fails.
- Add `test_prepatch_check_in_schema` to `test_config_schema.py`, modeled on
  `test_learning_tests_in_schema` (`:247`). (Naming pinned to `prepatch_check`
  — see Design Notes; the `pre_patch_check` spelling used elsewhere in this
  wiring section is a typo.)
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

- **Hunk→nodeid mapping has existing machinery — but not the one originally
  cited.** The reusable pair is `test_tamper_guard._test_functions(source)`
  (`:369-380`), which returns `{name: ast_node}` for top-level `test*`
  functions, and the **public** `read_paths_at_ref(repo_root, ref, paths)`
  (`test_tamper_guard.py:112-120`), which supplies the base-ref text to diff
  those names against. Added-vs-modified is then
  `set(after_names) - set(before_names)` — the same computation
  `filter_weakening_findings()` performs inline for its `relocated` set.
  > ⚠ Correction: `filter_weakening_findings()` (`:392` onward) is **not** the
  > added-vs-modified discriminator. It filters `TamperFinding` objects by
  > *strength regression* and explicitly **drops every `added` finding**
  > ("a new test file cannot weaken the suite"), so it can never surface the
  > added candidates this issue's hard flag is defined over. Do not consume it;
  > consume `_test_functions` + `read_paths_at_ref`. `measure_test_strength()`
  > is likewise a strength metric, not an identity diff.
- **`_test_functions` is private — promoted by ENH-3152, not here.** Reaching
  across modules into an underscore-prefixed name is not acceptable, so the
  rename to a public `extract_test_functions()` was split out as ENH-3152
  (`depends_on`) to keep this issue's diff to the new module plus its additive
  reader/config. Consume the public name; do not import `_test_functions`, and
  do not carry the rename in this issue's commit.
- Do not re-derive an AST layer or a `--collect-only` diff. When function-level
  attribution is ambiguous (hunks outside any function body, conftest changes,
  shared fixtures, **class-based tests** — see Codebase Research Findings), fall
  back to the touched *files* — never the full suite. Mechanically, the
  fallback target is the **file path itself** passed to pytest
  (`pytest scripts/tests/test_foo.py`), not an enumerated node-ID set; this is
  what keeps the `--collect-only` ban and the fallback compatible. Per-test
  attribution for the fallback comes back out of the run report, not out of a
  pre-run collection.
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
- **Per-node-ID results come from `--junit-xml`, not from the history plugin.**
  `pytest_history_plugin.LLHistoryPlugin.pytest_runtest_logreport()` models the
  *category dispatch* correctly but is an **in-process hook that writes to the
  history DB** — it cannot observe a subprocess running in another worktree, and
  wiring it in would violate this module's no-database contract. Run with
  `--junit-xml=<run_dir>/prepatch.xml` and parse it with stdlib
  `xml.etree.ElementTree`: JUnit XML distinguishes `<failure>` from `<error>`
  natively, which *is* the error-vs-fail split this issue needs, and it adds no
  third-party dependency (`pytest-json-report` is not in `scripts/pyproject.toml`
  and must not be added — see CLAUDE.md § Code Style). Parsing `-q` stdout is
  not acceptable; it is format-unstable and loses the failure/error distinction.
- **Timeout has no per-test resolution.** When the invocation is killed at
  `timeout_s`, pytest never writes the JUnit XML, so there is no way to know
  *which* candidate hung. Policy: every candidate with no reported result from
  that invocation is categorized `timeout`. Do not attempt per-node-ID
  invocations to narrow it — that multiplies the cost this issue explicitly
  prices down.
- **The retry-once pass is a second, narrower invocation.** Only the node IDs
  that reported `pass` in invocation 1 are re-run; everything else is already
  settled. A node that passes twice keeps `pass`; pass-then-fail (or
  pass-then-error) is reclassified `flaky`. A timeout on the retry invocation
  leaves the first pass standing — retry is confirmation, and an inconclusive
  retry must not manufacture evidence in either direction.
- **PYTHONPATH must point at the pre-patch worktree.** With an editable install
  (`pip install -e`), `little_loops` resolves to the **main tree's** absolute
  path, so tests running in the fork would import *post-patch* source and the
  check silently inverts: a genuine new test passes pre-patch and gets
  hard-flagged. The subprocess env must prepend `<worktree_path>/<src_dir>` to
  `PYTHONPATH` (the same injection `verify_epic_branch_before_merge()` does for
  BUG-2629). ENH-3141 only *validates* that `src_dir` exists in the fork; env
  construction is explicitly caller-side, i.e. this issue's. This is a
  correctness requirement, not a nicety — see Acceptance Criteria.
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
- **Config off-switch convention**: `LearningTestsConfig`
  (`config/features.py:495-530`) is the structural template — dataclass with
  `enabled: bool = False` first, plus a `from_dict()` classmethod reading each
  field with an explicit default. Its test class (`test_config.py:3001`,
  `test_enabled_defaults_to_false()` at `:3015`,
  `test_enabled_from_dict()` at `:3020`) is the test template.
  > ⚠ Correction: `LearningTestsConfig` is **not** a "lone `enabled` flag"
  > dataclass — it carries 8 fields (`auto_prove`, `stale_after_days`,
  > `discoverability`, `release_gate`, `scan_dirs`,
  > `version_aware_staleness`, `version_match_backstop_multiplier`). The
  > single-purpose-flag framing was wrong and is misleading here, because
  > `PrePatchCheckConfig` is likewise **not** a lone flag. It needs at minimum:
  > - `enabled: bool = False` — the off-switch (§ Design Notes, `skipped_reason`)
  > - `timeout_s: int = 300` — the per-invocation time box, which the issue
  >   already requires be "configurable alongside the off-switch"
  > - `modified_hard: bool = False` — escalates modified-and-passes-pre-patch
  >   from soft to hard, required by an existing Acceptance Criterion
  >
  > Section placement is **top-level** (`properties.prepatch_check`), matching
  > its `features.py` peers `decisions` (`config-schema.json:560`) and
  > `learning_tests` (`:1052`) — not nested under `commands` like
  > `confidence_gate`.
- **Naming is pinned to `prepatch_check`** — module `prepatch_check.py`, config
  key `prepatch_check`, dataclass `PrePatchCheckConfig`, matching ENH-3141's
  `setup_prepatch_worktree()`. The `pre_patch_check` spelling appearing in some
  wiring-pass test names below is a typo, not an alternative; the schema key and
  every test name must use `prepatch_check`.

## Integration Map

### Files to Modify

- `scripts/little_loops/prepatch_check.py` (new) — `run_prepatch_check()`,
  `collect_candidates()`, and the `PrePatchCandidate` / `PrePatchTestOutcome` /
  `PrePatchEvidence` dataclasses per § Program Design. Consumes ENH-2973's
  `test_file_patterns` module, `test_tamper_guard`'s AST/ref primitives
  (`read_paths_at_ref` and the now-public `extract_test_functions()`,
  landed by ENH-3152 at `test_tamper_guard.py:369-380` — **not**
  `filter_weakening_findings`, see Design Notes), and ENH-3141's
  `setup_prepatch_worktree()`. **No** FSM, CLI, or database imports.
- `scripts/little_loops/test_tamper_guard.py` — **not modified here.** The
  promotion of `_test_functions()` to a public `extract_test_functions()` is
  ENH-3152 (`depends_on`). This issue consumes the public name and must not
  import the underscore-prefixed one.
- `scripts/little_loops/history_reader.py` — additive `base_dirty` reader
  alongside `read_base_sha()` (`:1816`), which returns the SHA only.
- `scripts/little_loops/config-schema.json` — add the off-switch's schema
  entry as a **top-level** `properties.prepatch_check` block, peer to
  `properties.decisions` (`:560`) and `properties.learning_tests` (`:1052`) —
  not nested under `properties.commands` like `confidence_gate` (`:457-477`),
  which is a sub-config under a different, non-peer pattern.
- `scripts/little_loops/config/features.py` — add `PrePatchCheckConfig`
  (`enabled: bool = False`, `timeout_s: int = 300`,
  `modified_hard: bool = False`, plus `from_dict()`), following
  `LearningTestsConfig`'s shape (`:494-529`).
- `scripts/little_loops/config/core.py` — wire `PrePatchCheckConfig` into
  `BRConfig` at the three touchpoints `LearningTestsConfig`/`DecisionsConfig`
  use: construction (`_parse_config()`, `:304-306`), a `@property
  prepatch_check` (adjacent to `learning_tests` `:382-384` and `decisions`
  `:392-394`), and `to_dict()` serialization (adjacent to the `learning_tests`
  block `:809-814` and `decisions` block `:816-820`). Not in the issue's
  original Files to Modify list; required because
  `test_config_schema.py::TestToDictSchemaParity` (`:1099-1146`) diffs
  `config-schema.json`'s top-level `properties` against
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
- **Argv/env construction tests** (no real pytest run needed — assert on the
  captured `subprocess.run` call):
  - the command targets only candidate node IDs (or, in the fallback case, the
    touched file paths) and never the suite root;
  - `--junit-xml` is present and points inside the run dir;
  - `timeout=` is passed and equals `config.prepatch_check.timeout_s`;
  - `env["PYTHONPATH"]` **starts with** the pre-patch worktree's `src_dir`, not
    the main tree's — the editable-install false-negative guard.
- **`test_files` contract test**: assert the dict handed to
  `setup_prepatch_worktree()` holds the **post-patch** (working-tree) content
  for each touched test path, and that a touched `conftest.py` is included. A
  regression here silently turns the whole check into a no-op that always
  reports clean, so it needs a dedicated test rather than incidental coverage.
- **JUnit-XML parse tests**: `<failure>` → `fail`, `<error>` → `error`, a
  passing case → `pass`, and a missing/truncated XML (invocation killed) → all
  candidates `timeout`.
- **Flag-assignment tests**, separate from category tests: added+pass → `hard`;
  modified+pass → `soft`; modified+pass with `modified_hard=True` → `hard`;
  pass-then-fail on retry → `flaky` + `soft`; any hard flag with
  `base_dirty=True` → downgraded to `soft` with a non-empty `flag_reason`.

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
  `test_prepatch_check_in_schema` needed, asserting `"prepatch_check" in
  data["properties"]`, `additionalProperties is False`, and per-field
  `type`/`default` for all three fields (`enabled`, `timeout_s`,
  `modified_hard`). [Agent 3 finding; key name corrected from
  `pre_patch_check`]
- `scripts/tests/test_config_schema.py::TestToDictSchemaParity`
  (`:1099-1146`) — pre-existing schema/`to_dict()` exact-set-diff guard, not a
  test to write, but a live gate: fails if the `config-schema.json` entry and
  the `config/core.py::to_dict()` wiring land in separate commits. [Agent 3
  finding]

### Documentation

- `docs/reference/API.md` — new Module Overview table row for
  `little_loops.prepatch_check`, a new `## little_loops.prepatch_check`
  section documenting `run_prepatch_check()`, `collect_candidates()`,
  `PrePatchCandidate`, `PrePatchTestOutcome`, `PrePatchEvidence`, and a
  `### base_dirty` subsection peer to the existing `### read_base_sha` under
  `## little_loops.history_reader`. Also update the
  `little_loops.test_tamper_guard` section for the promoted
  `extract_test_functions()`.
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

- `ENH-3141` (done) — supplies `setup_prepatch_worktree()`, the tree
  this issue runs tests in.
- `ENH-3152` (blocking) — promotes `test_tamper_guard._test_functions()` to a
  public `extract_test_functions()`. Split out of this issue so its diff stays
  within the new module plus the additive reader/config.
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

_Added by `/ll:refine-issue` — 2026-08-12 — based on codebase analysis:_

- **ENH-3152 has landed** (status `done`, completed 2026-08-12T05:21:13Z, after this issue's last refine on 2026-08-10). `extract_test_functions()` is now public at `test_tamper_guard.py:369-380`, confirmed unchanged in shape from what this issue's Program Design assumes (walks `tree.body` only — top-level `FunctionDef`/`AsyncFunctionDef` starting with `test`, `None` on `SyntaxError`). Its scope limitation (class-method tests excluded, falling back to file-level attribution per this issue's Design Notes) is now test-locked at `scripts/tests/test_test_tamper_guard.py:845-850` (`TestExtractTestFunctions.test_class_method_tests_are_not_returned`), whose docstring states verbatim: "Documented scope limitation: walks tree.body, not ast.walk." Both `depends_on` entries (ENH-3141, ENH-3152) are now `done`; this issue is unblocked.
- **Line-anchor drift** since last refine, caused by an unrelated commit (`3ca8415a`, 2026-08-11) inserting a new `McpTransportPolicyConfig` dataclass into `config/features.py` between `LearningTestsConfig` and `DecisionsConfig`:
  - `config/features.py` `DecisionsConfig`: cited `:532-551`, now `:611-632`.
  - `config/core.py` `learning_tests` `@property`: cited `:379-386`, now `:382-384`; `decisions` `@property` now `:392-394`.
  - `config/core.py` `to_dict()` learning_tests block: cited `:802-812`, now `:809-814`; decisions block now `:816-820`.
  - `docs/reference/API.md` `BRConfig` Properties table: `decisions`/`learning_tests` rows cited `:158-159`, now `:159-160`.
  - Confirmed still accurate (no drift): `LearningTestsConfig` (`:494-529`, off by ~1 line from the `:495-530` citation), `config/core.py` construction block (`:304-306`), `config-schema.json` `confidence_gate` block (`:457-482`), `test_config.py`'s `TestLearningTestsConfig`/`test_enabled_defaults_to_false`/`test_enabled_from_dict`/`TestBRConfigLearningTestsIntegration` (`:3001`, `:3015`, `:3020`, `:3075-3107`), `test_config_schema.py`'s `test_learning_tests_in_schema`/`TestToDictSchemaParity` (`:247`, `:1099-1146`), `docs/reference/CONFIGURATION.md`'s `learning_tests` header/`confidence_gate.enabled` row (`:891`, `:429-431`), `docs/reference/API.md`'s `history_reader` module row (`:54`).

## Program Design

### Types

- `PrePatchCandidate` — one identified candidate before it is run:
  `nodeid: str`, `file: str`, `added: bool`, `attribution: str`
  (`function` | `file-fallback`)
- `PrePatchTestOutcome` — one candidate test's result: `nodeid: str`,
  `file: str`, `added: bool`, `category: str`, `error_kind: str | None`,
  `flag: str`, `flag_reason: str | None`
- `PrePatchEvidence` — the per-step bundle: `base_ref: str`,
  `base_source: str`, `base_dirty: bool | None`,
  `outcomes: list[PrePatchTestOutcome]`, `verdict: str`,
  `skipped_reason: str | None`, `to_dict() -> dict`

All three are new plain-field `@dataclass`es with `to_dict()` in
`scripts/little_loops/prepatch_check.py`, following the `Gap`/`GapAnalysis`
convention; `PrePatchEvidence.to_dict()` serializes `outcomes` as
`[o.to_dict() for o in self.outcomes]` per the codebase-wide nested-dataclass
convention.

- `category` is one of `pass | fail | error | timeout | flaky`.
- `flag` is one of `hard | soft | none` and is **the verdict this issue
  exists to produce** — the original type list had no field to hold it, leaving
  four Acceptance Criteria (added-passes ⇒ hard, modified-passes ⇒ soft,
  flaky ⇒ soft, dirty-base ⇒ downgrade) with nowhere to land. `flag_reason`
  carries the human-readable why, and is **required** whenever a dirty base
  downgrades a hard flag to soft.
- `verdict` is the bundle-level rollup: `clean | flagged | skipped`
  (`flagged` when any outcome is `hard`; `skipped` covers both the config
  off-switch and — distinctly, via `skipped_reason` text — the
  zero-candidate case).
- The original `pre_patch: str` field is **dropped**: it duplicated `category`
  with no defined distinct meaning. There is one outcome field.
- `error_kind` distinguishes a collection/import error naming a post-patch
  module from any other infrastructure error. `base_source` is `dequeue-stamp`
  or `merge-base`. `base_dirty` `True` means the stamped tree had tracked
  modifications at dequeue; `None` means unknown.
- `skipped_reason` is set when the config off-switch disables the check **and**
  when zero candidate tests were identified — the two cases carry different
  reason strings so the zero-candidate case is explicit rather than
  indistinguishable from a clean pass.

### Signatures

```python
def run_prepatch_check(
    *,
    step_diff: str,
    repo_root: Path,
    worktree_base: str | Path,
    base_sha: str | None,
    base_dirty: bool | None,
    base_branch: str,
    logger: Logger,
    git_lock: GitLock,
    config: BRConfig | None = None,
) -> PrePatchEvidence: ...

def collect_candidates(step_diff: str, repo_root: Path, base_ref: str,
                       config: BRConfig | None = None) -> list[PrePatchCandidate]: ...
```

> ⚠ The previous signature
> (`run_prepatch_check(step_diff, base_sha, base_dirty, timeout_s)`) was not
> callable and could not satisfy its own Acceptance Criteria. Changes:
>
> - **`repo_root`, `worktree_base`, `logger`, `git_lock` added** —
>   `setup_prepatch_worktree()` (`worktree_utils.py:329-335`) requires all four
>   with no defaults. The refine pass flagged this and left it unresolved; it is
>   now resolved by threading them through, since the host (ENH-2997/ENH-2998)
>   already holds them. Pass a gitignored `worktree_base` (e.g. `".worktrees"`),
>   per ENH-3141's docstring, so the fork stays outside
>   `tamper_guard_changed_files()`'s scan scope.
> - **`base_branch` added** — this issue owns the merge-base fallback when
>   `base_sha` is `None`. That fallback is a `git merge-base` call, which needs
>   both a repo and a branch to compute against. Neither was in the signature.
> - **`config` added, `timeout_s` removed** — `timeout_s` is one field of
>   `PrePatchCheckConfig`, and the core also needs `enabled` (it is the code
>   that writes `skipped_reason`), `modified_hard`, and the `project.test_patterns`
>   that `is_test_file()` reads. Taking a `BRConfig` supplies all four through
>   one already-established parameter convention; a bare `timeout_s` cannot.
>   This does not violate the host-resolves-state rule — that rule is about the
>   **database** (`base_sha`/`base_dirty` still arrive as arguments and the module
>   still performs no DB access). Config is a file read, exactly as
>   `is_test_file(path, config=None)` already does internally.
> - **`collect_candidate_nodeids() -> list[str]` replaced by
>   `collect_candidates() -> list[PrePatchCandidate]`** — a bare list of node-ID
>   strings discards the `added` bit, and added-vs-modified is the discriminator
>   the entire hard/soft verdict is defined over. It also gains `base_ref`, needed
>   to fetch the before-text via `read_paths_at_ref()` for the
>   `set(after) - set(before)` split.

- `is_test_file(path: str, config: BRConfig | None) -> bool` (existing,
  ENH-2973)
- `read_paths_at_ref(repo_root: Path, ref: str, paths: list[str]) -> dict[str, str | None]`
  (existing, ENH-2854, `test_tamper_guard.py:112`) — supplies the base-ref
  before-text for the added-vs-modified split
- `read_base_sha(issue_id: str, *, run_id: str | None, db: Path | str) -> str | None`
  (existing, ENH-2866)
- `setup_prepatch_worktree(base_ref: str, test_files: dict[str, str], src_dir: str | None) -> Path`
  (existing, ENH-3141)

`run_id` is a process-local uuid4 never exported to env, run-dir, or argv, so
an out-of-process consumer must omit it and take the
most-recent-stamped-row path.

### Call Path

`run_prepatch_check` -> `collect_candidates` -> `filter_test_files`,
`read_paths_at_ref`, `_test_functions` (promoted; see Design Notes)

`run_prepatch_check` -> (post-patch test content from the working tree) ->
`setup_prepatch_worktree` (ENH-3141)

`run_prepatch_check` -> `subprocess.run(pytest <targets> --junit-xml=...,
timeout=config.prepatch_check.timeout_s, env=PYTHONPATH-injected)` ->
JUnit-XML parse -> per-node categories -> retry-once over the passing node IDs
-> flag assignment (incl. dirty-base downgrade) -> `PrePatchEvidence`

The core is database-free; `(base_sha, base_dirty)` arrive as arguments,
resolved by the host (ENH-2997 / ENH-2998). It does perform git and filesystem
reads (merge-base fallback, working-tree test content, worktree fork) — only
the *database* is out of bounds.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- `test_tamper_guard._test_functions(source)` (`test_tamper_guard.py:369-380`) only sees **top-level** `FunctionDef`/`AsyncFunctionDef` nodes (`tree.body`, not `ast.walk`) — it does not see class-method tests (`class TestFoo: def test_bar(self): ...`) or nested test functions. A hunk inside a class-based test (this codebase's own suite uses `TestX::test_y` node IDs throughout) will not resolve via `_test_functions()` and must go through the "ambiguous attribution" fallback to the touched file's full node-ID set already specified in this issue's Design Notes.
- `pytest_history_plugin.LLHistoryPlugin.pytest_runtest_logreport()` (`pytest_history_plugin.py:101-116`) is the exact four-category dispatch model for `PrePatchTestOutcome.category`: `report.when == "call"` branches to `passed`/`failed`/`skipped`; `report.when in ("setup", "teardown")` with `report.failed` counts as **error** (matching this issue's error-vs-fail distinction), but only `report.when == "setup" and report.skipped` counts as skipped — a teardown-phase skip is not counted at all.

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- `setup_prepatch_worktree()`'s actual signature (`worktree_utils.py:329-335`) is `setup_prepatch_worktree(repo_path: Path, worktree_base: str | Path, base_ref: str, test_files: dict[str, str], logger: Logger, git_lock: GitLock, src_dir: str | None = None) -> Path` — wider than this issue's own Program Design signature list (`base_ref, test_files, src_dir` only). `repo_path`, `worktree_base`, `logger`, and `git_lock` have no defaults and are required; `run_prepatch_check()`'s own signature per this issue's design takes none of them, so the caller (this module's `run_prepatch_check()`, or the host per ENH-2997/ENH-2998) must supply them from context. State explicitly in the implementation how `run_prepatch_check()` obtains these four values, since the current Program Design signature is not directly callable against the real function.
- Nested-dataclass `to_dict()` serialization in this codebase consistently uses a list comprehension calling each item's own `to_dict()` — `GapAnalysis.to_dict()` (`issue_history/models.py:294-302`) returns `"gaps": [g.to_dict() for g in self.gaps]`; same shape at `learning_tests/__init__.py:65-74` (`LearnTestRecord.to_dict()`), `analytics/variance.py:71`, `issue_history/rework.py:123`. No alternate pattern (e.g. `dataclasses.asdict()`) appears anywhere in this role. `PrePatchEvidence.to_dict()`'s `outcomes` field should follow this exact shape: `[o.to_dict() for o in self.outcomes]`.
- `OrchestrationRun` (`history_reader.py:220-236`) already carries `base_dirty: int | None = None` as a plain unconverted int field alongside `base_sha: str | None = None`; the general `list_orchestration_runs`-style query at `history_reader.py:1738` selects both columns inline with no bool conversion. The int→bool conversion this issue's new `base_dirty` reader needs is unique to the point-lookup reader contract being added — it does not exist anywhere else in `history_reader.py` today.

_Added by `/ll:refine-issue` — 2026-08-12 — based on codebase analysis:_

- Re-confirmed unchanged since last refine: `read_paths_at_ref()` (`test_tamper_guard.py:112`, `{path: _git(repo_root, "show", f"{ref}:{path}") for path in paths}`, missing-at-ref paths map to `None`), `read_base_sha()` (`history_reader.py:1816-1821`, query dispatch at `:1849-1861` — `run_id`-present does an exact `run_id + issue_id` lookup, `run_id`-absent does `WHERE issue_id = ? AND base_sha IS NOT NULL ORDER BY id DESC LIMIT 1`, never raises), `setup_prepatch_worktree()` (`worktree_utils.py:329-337`, exact signature match), and `pytest_history_plugin.LLHistoryPlugin.pytest_runtest_logreport()` (`:101-116`, category dispatch unchanged).
- `OrchestrationRun.base_dirty` (`history_reader.py:236`) is confirmed still `int | None = None` with no existing point-lookup reader — the only existing reader touching the column is `recent_orchestration_runs()` (`:1722-1762`, a list/filter query that happens to select the column as part of the full row shape, not a single-value keyed lookup). The additive `base_dirty` reader this issue must add remains genuinely net-new.
- No JUnit-XML parsing (`xml.etree.ElementTree` against `--junit-xml` output) and no subprocess-pytest node-ID-targeting precedent exists anywhere in `scripts/little_loops/` as of this refine pass — re-confirmed after ENH-3141 and ENH-3152 landed; neither touched pytest invocation. `scripts/little_loops/prepatch_check.py` remains entirely greenfield.
- Nested-dataclass `to_dict()` convention re-confirmed as list-comprehension-of-child-`.to_dict()` (e.g. `GapAnalysis.to_dict()`, `issue_history/models.py:294-302`, now at class line `:285`). `dataclasses.asdict()` exists elsewhere (`mcp_server/tools.py:134`, `cli/history.py:392,410,457`) but only for flat records with no nested-dataclass-list fields — that specific "bundle with mixed dataclass-list + scalar fields, each item self-serializing" shape has no `asdict()` precedent anywhere in the codebase, confirming the hand-rolled `to_dict()` choice for `PrePatchEvidence`.

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
- **Not this issue**: the `_test_functions()` → `extract_test_functions()`
  promotion in `test_tamper_guard.py` — that is ENH-3152, a blocking
  dependency. This issue touches no file in `test_tamper_guard.py`.

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
      `test_tamper_guard`'s existing AST/ref helpers — the promoted
      `extract_test_functions()` (promoted by ENH-3152) plus
      `read_paths_at_ref()` — rather than a new AST layer or a
      `--collect-only` diff, and without importing `_test_functions`. (**Not**
      `filter_weakening_findings()`, which drops all `added` findings and
      cannot produce the added-vs-modified split; see Design Notes.)
- [ ] Tests cover: a fake test that passes pre-patch, a genuine test that
      fails pre-patch, a test that errors pre-patch, and the zero-test case.
- [ ] The content written into the pre-patch worktree via
      `setup_prepatch_worktree()`'s `test_files` is the **post-patch** content
      of each touched test path (including a touched `conftest.py`), never the
      base-ref content; a dedicated test asserts this.
- [ ] The pre-patch pytest subprocess runs with `<worktree>/<src_dir>`
      prepended to `PYTHONPATH`, so an editable install cannot resolve
      `little_loops` to the post-patch main tree; a test asserts the
      constructed env.
- [ ] Per-node-ID outcomes are parsed from `--junit-xml` with stdlib
      `xml.etree`, distinguishing `<failure>` from `<error>`; no new
      third-party dependency is added and stdout is not parsed.
- [ ] When the invocation is killed at `timeout_s` and no JUnit XML is
      produced, every unreported candidate is categorized `timeout`; a test
      covers it.
- [ ] The retry-once pass is a second invocation targeting only the node IDs
      that passed in the first; a test asserts the narrowed target set.
- [ ] Each outcome carries an explicit `flag` (`hard | soft | none`) and the
      bundle carries a rollup `verdict`; a dirty-base downgrade sets a
      non-empty `flag_reason`.
- [ ] The config block is top-level `prepatch_check` with `enabled`,
      `timeout_s`, and `modified_hard`; the schema key, dataclass, module, and
      every test name use the `prepatch_check` spelling (never
      `pre_patch_check`).
- [ ] `run_prepatch_check()` resolves the merge-base fallback itself from
      `repo_root` + `base_branch` when `base_sha` is `None` — both are
      parameters, and a test covers the fallback without any DB access.

## Impact

- **Priority**: P2 — the core of a real fake-evidence hole in verification
  loops (per EPIC-2856's rework-reduction goal).
- **Effort**: Large — the per-test evidence-bundle logic, retry/flaky
  reclassification, and node-ID-targeted subprocess invocation are all new
  logic with no in-repo template.
- **Risk**: Low-Medium — isolated to a new module plus a small additive
  reader; consumes ENH-3141's (done) worktree primitive.
- **Breaking Change**: No — new module and additive reader/config only.

## Resolution

Implemented `scripts/little_loops/prepatch_check.py` (`run_prepatch_check()`,
`collect_candidates()`, `PrePatchCandidate`/`PrePatchTestOutcome`/`PrePatchEvidence`),
the additive `read_base_dirty()` reader in `history_reader.py`, and the
top-level `prepatch_check` config block (`PrePatchCheckConfig` in
`config/features.py`, wired into `BRConfig`, schema, and `ll-init`'s untouched-
section allowlist). 36 new tests in `test_prepatch_check.py` plus sibling
classes in `test_history_reader.py`/`test_config.py`/`test_config_schema.py`;
docs updated in `API.md` and `CONFIGURATION.md`. Full suite green
(19019 passed), `ruff check`/`ruff format` clean, `mypy` clean on all changed
files.

## Status

**Done** | Created: 2026-08-10 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-12T19:03:28 - `436ddeaa-1886-42d9-b97f-73e55dd913c6.jsonl`
- `/ll:ready-issue` - 2026-08-12T18:17:41 - `95710935-6e8e-48bc-b7d6-f9447ab6f33d.jsonl`
- `/ll:confidence-check` - 2026-08-12T18:15:01 - `7cde9f76-e1e6-4fcf-9dfe-5de92f713a63.jsonl`
- `/ll:reconcile-issue` - 2026-08-12T18:12:36 - `b3e9a0eb-04f5-44c7-86be-e2fecad3a581.jsonl`
- `/ll:refine-issue` - 2026-08-12T18:08:00 - `48d1933d-4a37-43f5-a750-25c3548e0b10.jsonl`
- pre-implementation review - 2026-08-11 - resolved 4 blocking gaps (`test_files`
  post-patch contract, missing verdict/`flag` fields, JUnit-XML result
  extraction, uncallable `run_prepatch_check()` signature) and corrected 4
  factual claims (`filter_weakening_findings` is not the added-vs-modified
  discriminator; `LearningTestsConfig` is not a lone-flag dataclass;
  `prepatch_check` naming pinned; file-path fallback reconciles the
  `--collect-only` ban). Added a PYTHONPATH-injection AC for the
  editable-install false negative.
- `/ll:refine-issue` - 2026-08-10T20:19:53 - `1dd56f24-b781-4e16-84f6-d8ee895776d1.jsonl`
- `/ll:confidence-check` - 2026-08-10T09:17:36 - `df55e709-f5ba-4a76-ad27-3b49b1787402.jsonl`
- `/ll:verify-issues` - 2026-08-10T09:13:39 - `975b1509-c74d-48b1-aa22-7b2aab82c1b8.jsonl`
- `/ll:wire-issue` - 2026-08-10T09:09:22 - `c2aaebfe-05da-42f3-a4a2-a8cfac3be710.jsonl`
- `/ll:refine-issue` - 2026-08-10T09:00:02 - `6cc40244-b7c6-46f8-923a-e7ed2ee0134d.jsonl`
- `/ll:issue-size-review` - 2026-08-10T07:23:33 - `7e0f8f7e-cdcf-448e-8ae7-22d89c36b63b.jsonl`
