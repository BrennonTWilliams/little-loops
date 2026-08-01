---
id: ENH-2935
title: Tamper guard Python adapter - ll-auto/ll-parallel/ll-sprint coverage
type: ENH
priority: P2
status: done
discovered_date: 2026-07-30
completed_at: '2026-07-31T05:35:44Z'
epic: EPIC-2856
parent: EPIC-2856
blocked_by:
- ENH-2933
labels:
- rework
- verification
relates_to:
- ENH-2854
confidence_score: 97
outcome_confidence: 68
score_complexity: 13
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 15
decision_needed: false
---

# ENH-2935: Tamper guard Python adapter - ll-auto/ll-parallel/ll-sprint coverage

## Parent Issue

Decomposed from ENH-2854: Guard against agent edits to test files during
verification. This child covers the non-FSM half of the guard's surface —
`ll-auto`, `ll-parallel`, and `ll-sprint` verify in plain Python
(`work_verification.py`), never entering the FSM, so no `tamper_guard:`
state key (ENH-2934) can apply to them. It depended on ENH-2933 (the guard
core), which has since landed (`test_tamper_guard.py`), and is independent
of ENH-2934 (the FSM adapter, also landed — see Design Notes →
Codebase Research Findings for why its wiring isn't directly reusable
here).

## Summary

Hook the tamper guard core (ENH-2933) into `work_verification.py`'s shared
verification path, and add the project-global config key that supplies the
guard's default policy for this non-FSM path.

## Current Behavior

`ll-auto`, `ll-parallel`, and `ll-sprint` verify completed work entirely in
plain Python (`work_verification.py:verify_work_was_done()`), never entering
the FSM. The tamper guard core landed in ENH-2933 and the FSM adapter landed
in ENH-2934 (`fsm/executor.py`'s `tamper_guard:` state key), but neither is
wired into this non-FSM path — an agent run through `ll-auto`/`ll-parallel`/
`ll-sprint` that weakens or deletes assertions in a test file can still have
`verify_work_was_done()` report success.

## Expected Behavior

`verify_work_was_done()` calls `run_tamper_guard` (ENH-2933) against the
changed-file set on every non-FSM verification path, using a project-global
config-default policy (mirroring `code_query.staleness`'s shape) when no
FSM-level override applies. A test-weakening change trips the guard the same
way it already does for FSM loops, with a single shared revert
implementation (no second independently-maintained hook).

## Motivation

See ENH-2854 for the full origin. `issue_manager.py`'s Phase 3
(`verify_issue_completed()`/`verify_work_was_done()`) and
`worker_pool.py:596` → `_verify_work_was_done()` (which `ll-sprint` inherits
via the shared `ParallelOrchestrator`) both verify without ever entering the
FSM. Without this adapter, an `ll-auto`/`ll-parallel`/`ll-sprint` run can
weaken tests and still report success — the FSM adapter alone does not
close this gap.

## Proposed Solution

1. **Hook**: call `run_tamper_guard` (ENH-2933) from
   `work_verification.py:verify_work_was_done()` (L44), which already
   receives (or derives) the changed-file set the guard needs. Both
   `issue_manager.py:31` and `worker_pool.py:38` already import this
   module, so both orchestrators inherit the guard from one shared hook
   rather than two independent ones.
2. **Config key**: add the non-FSM policy-default key to
   `config-schema.json`, following `code_query.staleness` (~L1296) as the
   shape and location precedent (3-mode enum, default `fail`). Mirror it on
   the Python side — either as a `project.*` field on `ProjectConfig`
   (`scripts/little_loops/config/core.py` ~L148-195: field declaration,
   `from_dict()`, and the reverse-serialization block ~L866-872) or as a
   sibling `CodeQueryConfig`-style field
   (`scripts/little_loops/config/features.py:834-847`) — exactly one
   `config/*.py` dataclass needs the matching field/`from_dict`/
   serialization lines. Smoke-check that the key resolves through
   `BRConfig.resolve_variable()` (`config/core.py:912`), the method
   `ll-config get <key>` wraps.
3. **Precedence**: this config key exists solely to supply (a) the default
   for the non-FSM path and (b) the loop-level fallback default consumed by
   ENH-2934's FSM adapter; it never overrides an explicit state-level
   `tamper_guard:` key. Full precedence: state-level > loop-level default >
   project config key > built-in `fail`.
4. **Revert on the non-FSM path** reuses
   `worker_pool.py:_cleanup_leaked_files()`'s (L1362) git tracked-vs-
   untracked split — the same shape ENH-2933's core already follows, so
   this should fall out of calling the core directly rather than needing a
   second implementation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The Design Notes below identify that `executor.py`'s candidate-path/
changed-files enumeration (`_tamper_guard_candidate_paths`,
`_tamper_guard_changed_files`) is private to the FSM adapter and not
reusable plumbing. This non-FSM hook needs the same enumeration logic and
must pick one of:

**Option A**: Duplicate the enumeration directly in
`work_verification.py` — write a second `git ls-files`/`git diff`
implementation local to the non-FSM path, mirroring
`_tamper_guard_candidate_paths`/`_tamper_guard_changed_files` in shape but
independently maintained.

> **Selected:** Option B — extracting a shared helper is the only choice
> that satisfies the issue's own "no second independently-maintained hook"
> acceptance criterion.

**Option B**: Extract the enumeration into a small shared helper (e.g. in
`scripts/little_loops/test_tamper_guard.py` alongside `run_tamper_guard`)
that both `executor.py` and `work_verification.py` call, and refactor
`executor.py`'s two private methods to delegate to it.

**Recommended**: Option B — the issue's own Acceptance Criteria ("no
second independently-maintained hook") implicitly rules out Option A;
duplicating the git-enumeration logic creates exactly the drift risk that
criterion is meant to prevent. Option B costs one extra refactor of
`executor.py`'s two private methods but keeps a single source of truth for
candidate-path/changed-files enumeration.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-30.

**Selected**: Option B — extract the enumeration into a shared helper in
`test_tamper_guard.py` that both `executor.py` and `work_verification.py`
call.

**Reasoning**: `test_tamper_guard.py` is already the shared module
`executor.py` delegates to for three other primitives
(`resolved_pytest_config_paths`, `snapshot_test_paths`, `run_tamper_guard`
— `fsm/executor.py:1326,1457,1491`), so adding the enumeration there is
incremental, not novel plumbing, and this codebase has direct precedent
(ENH-240) for consolidating duplicated git-enumeration logic into one
canonical module rather than letting a second copy drift. Option A is
disqualified outright by the issue's own Acceptance Criteria ("no second
independently-maintained hook" / "no second revert implementation"),
which a duplicated implementation would violate on day one.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 1/3 | 2/3 | 2/3 | 0/3 | 5/12 |
| Option B | 3/3 | 1/3 | 2/3 | 2/3 | 8/12 |

**Key evidence**:
- Option A: `work_verification.py` already has one independent git-diff
  implementation predating this issue; adding a tamper-guard-specific
  third variant would leave 3 independently-maintained enumerations with
  no convergence, directly violating the AC against a "second
  independently-maintained hook."
- Option B: `filter_test_files` and `resolved_pytest_config_paths` are
  already public functions consumed cross-module the same way Option B's
  new helper would be; the refactor does touch `fsm/executor.py`, which
  is nominally out of ENH-2935's Scope Boundaries (owned by ENH-2934) —
  worth a one-line scope note during implementation, not a blocker to the
  decision.

## Design Notes

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correction to the `code_query.staleness` precedent** (Proposed Solution
  step 2 and Files to Modify): the key is at
  `config-schema.json:1307`, not ~L1296 (L1296 sits inside the nested
  `codegraph.db_path` description one level up in the same object). More
  importantly, its enum is `["strict", "warn", "off"]` with
  `default: "warn"` — **there is no `"fail"` member**. Only the JSON-Schema
  *shape* (string enum + description + default, nested under a
  feature-flag object) transfers as precedent; the *values* don't. The new
  key's default should be `"fail"` to match
  `test_tamper_guard.py`'s own `DEFAULT_TAMPER_POLICY: TamperPolicy = "fail"`
  (line 25) — do not copy `"warn"` from `code_query.staleness` by analogy.
- **The FSM adapter (ENH-2934, `fsm/executor.py`) is not reusable plumbing
  for this issue.** Commit `f89ea9be` wired `run_tamper_guard` entirely
  inside `executor.py` as private methods —
  `_effective_tamper_guard_policy` (L1295),
  `_tamper_guard_candidate_paths` (L1314, unions
  `git ls-files --cached --others --exclude-standard` narrowed via
  `filter_test_files` + `resolved_pytest_config_paths`), and
  `_tamper_guard_changed_files` (L1345, unions
  `git diff --name-only HEAD` with `git ls-files --others --exclude-standard`)
  — plus inline snapshot/compare logic in `_execute_state` (L1453-1515).
  None of this is factored out into a shared module, and `executor.py`
  never imports from or calls into `work_verification.py`. This means the
  "Call Path" in Program Design (`verify_work_was_done` →
  `run_tamper_guard` → `filter_test_files` → ... → `apply_tamper_policy`)
  needs its own candidate-path/changed-files enumeration in
  `work_verification.py` — either duplicated from the executor's private
  methods or extracted into a small shared helper (e.g. in
  `test_tamper_guard.py` itself) that both adapters call. Left unaddressed,
  this is a second independent implementation of the same git-enumeration
  logic, which the issue's own Acceptance Criteria ("no second
  independently-maintained hook") implicitly rules out — worth deciding
  explicitly rather than discovering during implementation.
- `run_tamper_guard`'s actual signature (`test_tamper_guard.py:189`) is
  `run_tamper_guard(before: TamperSnapshot, changed_files: list[str],
  config: BRConfig, policy: TamperPolicy, repo_root: Path) -> TamperReport`
  — it takes a `BRConfig` instance (not a raw policy string alone) and
  internally computes the "after" path set as
  `before ∪ filter_test_files(changed_files, config) ∪
  resolved_pytest_config_paths(repo_root)`. The non-FSM hook in
  `verify_work_was_done()` needs a `BRConfig(repo_root)` instance available
  at the call site to pass through.
- Minor anchor corrections: `git_operations.py`'s re-export spans
  L15-19 (not L15-18, the closing paren is on 19); `issue_manager.py`
  Phase 3 technically closes at L1133 (the `else: dry_run` branch), not
  L1129.

- `verify_work_was_done(logger, changed_files=None, baseline_sha=None)`:
  when `changed_files` is `None` (the `ll-auto` path), it derives the set
  itself from three sequential `git diff` calls (uncommitted, staged,
  committed-since-`baseline_sha`) — intersect that derived set against
  `filter_test_files()` (ENH-2973, via ENH-2933's core) before deciding
  revert/fail/allow.
- `issue_manager.py`'s two call sites needing confirmation: L1072 and L1109
  (Phase 3 spans L1049-1129). `worker_pool.py`'s call site: L596,
  `_verify_work_was_done()` at L1212.
- Three distinct import/patch surfaces resolve to `verify_work_was_done`:
  `little_loops.work_verification.verify_work_was_done`,
  `little_loops.git_operations.verify_work_was_done` (re-exported for
  backward compat, `git_operations.py:15-18`; used directly by
  `scripts/tests/test_subprocess_mocks.py:~451-545`), and
  `"little_loops.issue_manager.verify_work_was_done"` (patched in
  `scripts/tests/test_issue_manager.py:~2632-2932`). Existing tests that
  patch `verify_work_was_done` wholesale will bypass the new
  `run_tamper_guard` call entirely — new tamper-guard tests must patch/
  exercise `run_tamper_guard` itself (or its call site inside
  `verify_work_was_done`), not stub `verify_work_was_done`.

## Program Design

Reuses `TamperPolicy`, `TamperReport`, `run_tamper_guard` from ENH-2933's
`scripts/little_loops/test_tamper_guard.py`. No new core types; the only
new field is the config-schema policy-default key and its `ProjectConfig`
(or `CodeQueryConfig`) mirror.

### Deviations

_2026-07-31, implementation:_

- **New function**: `snapshot_test_paths_at_ref(repo_root, ref, paths)` was
  added to `test_tamper_guard.py`. The FSM adapter (ENH-2934) captures a live
  "before" snapshot at a guarded state's own entry; this non-FSM path
  verifies once, after the whole run already happened, so there is no such
  live moment. "before" is instead reconstructed from git history (`git show
  <ref>:<path>`, ref = `baseline_sha` or `HEAD`) — required for the guard to
  distinguish "modified" from "added" findings correctly (an empty/omitted
  "before" would misclassify every changed test file as "added", which
  `revert` never touches).
- **Guard only runs when `config` is supplied**: `verify_work_was_done()`
  skips the tamper guard entirely when `config` is `None`, rather than
  constructing a fresh `BRConfig(repo_root)` unconditionally as originally
  scoped. Both production callers (`issue_manager.py`, `worker_pool.py`)
  always have a `BRConfig` in scope and now pass it through, so this doesn't
  reduce guard coverage on `ll-auto`/`ll-parallel`/`ll-sprint`. Making it
  unconditional would have forced test-mock updates across every existing
  `verify_work_was_done()` call site (blanket `subprocess.run` mocks can't
  represent both a mocked git "before" and a real on-disk "after"
  consistently) for no coverage gain, since no caller lacking a config exists
  in production.
- **The project config key (`tamper_guard.policy`) is NOT wired as
  ENH-2934's FSM loop-level fallback**, despite the Proposed Solution's
  precedence chain (state-level > loop-level default > project config key >
  built-in `fail`) naming it as one. `executor.py`'s
  `_effective_tamper_guard_policy()` returns `None` (no guard) when neither
  state nor loop level `tamper_guard:` is set, unchanged. Wiring the project
  key in would make every FSM loop that never opts into `tamper_guard:` get a
  guard by default once a project sets this key (schema default is
  `"fail"`) — a default-on behavior change to `executor.py`'s guard hook,
  which this issue's own Scope Boundaries reserves to ENH-2934 (only the
  enumeration-helper refactor was an accepted in-scope deviation, per the
  Decision Rationale). `scripts/tests/test_fsm_executor.py`'s
  `test_no_guard_when_key_absent` already pins this behavior; changing it
  would need to be a deliberate ENH-2934-owned decision, not a side effect of
  this issue. The AC "config key never overrides an explicit FSM state-level
  key" is satisfied by the two mechanisms being fully decoupled — see
  `test_project_config_key_never_overrides_state_level_policy`.

### Signatures

_Added by `/ll:refine-issue` — based on codebase analysis:_

Reused, unchanged (`scripts/little_loops/test_tamper_guard.py:189`):

- `run_tamper_guard(before: TamperSnapshot, changed_files: list[str], config: BRConfig, policy: TamperPolicy, repo_root: Path) -> TamperReport`

Changed by this issue (`scripts/little_loops/work_verification.py:44`) —
current signature has no config/repo_root parameter at all; Wiring Phase
item 1 requires adding one so the hook can construct/pass a `BRConfig` to
`run_tamper_guard`:

- Before: `verify_work_was_done(logger: Logger, changed_files: list[str] | None = None, baseline_sha: str | None = None) -> bool`
- After: `verify_work_was_done(logger: Logger, changed_files: list[str] | None = None, baseline_sha: str | None = None, config: BRConfig | None = None, repo_root: Path | None = None) -> bool`

Both existing call sites already have a `BRConfig` in scope one function up
and pass it through rather than constructing a new one:
`issue_manager.py:1072`/`:1109` (Phase 3) and `worker_pool.py:1236`
(passing `self.br_config`).

### Call Path

`verify_work_was_done` (`work_verification.py:44`) → `run_tamper_guard`
(ENH-2933) → `filter_test_files` (ENH-2973) → `snapshot_test_paths` →
`compare_snapshots` → `apply_tamper_policy`, with the policy resolved from
the config key (via `BRConfig`) when no FSM-level override is in play.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included
in the implementation:_

1. `verify_work_was_done()`'s current signature (`logger, changed_files=None,
   baseline_sha=None`) has no config parameter at all — adding one to reach
   `run_tamper_guard`'s required `BRConfig` means updating every existing
   caller in the same change: `issue_manager.py:1072` and `:1109` (both
   already have a `config: BRConfig` in scope one function up — pass it
   through instead of threading a new parameter from further out),
   `worker_pool.py:1236` (pass the already-constructed `self.br_config`).
2. Keep `scripts/little_loops/__init__.py`'s re-export of
   `verify_work_was_done` (import ~L67, `__all__` ~L124) signature-compatible
   with the `git_operations.py:15-19` re-export — both are public surfaces.
3. If the config key lands as a `CodeQueryConfig`-style sibling dataclass,
   wire it into `config/__init__.py` (import + `__all__`, mirroring
   `CodeQueryConfig`) and `config/core.py`'s `BRConfig` construction (import,
   `from_dict()` construction, `@property` accessor) — three parallel
   additions, not just the dataclass file itself.
4. Update the `subprocess.run`-mocking tests in `test_work_verification.py`'s
   `TestVerifyWorkWasDoneBaselineSha` class and the `verify_work_was_done`
   mock-signature assertions in `test_issue_manager.py` (see Tests section
   for exact line numbers) in the same change — they will break or silently
   under-verify otherwise.

## Files to Modify

- `scripts/little_loops/work_verification.py` — call the guard core from `verify_work_was_done()`.
- `scripts/little_loops/issue_manager.py` (~L1049-1129, Phase 3) — confirm the guard fires via the shared `work_verification.py` hook (no independent hook).
- `scripts/little_loops/parallel/worker_pool.py` (~L596, `_verify_work_was_done` L1212) — same confirmation for `ll-parallel`/`ll-sprint`.
- `scripts/little_loops/config-schema.json` — new `project.*` (or `code_query`-sibling) policy-default key, `code_query.staleness` (~L1296) as shape/location precedent.
- `scripts/little_loops/config/core.py` (~L148-195, ~L866-872) or `scripts/little_loops/config/features.py:834-847` — matching dataclass field, `from_dict`, serialization.
- `docs/reference/CONFIGURATION.md` (~L294-305) — new row for the policy key, same shape as the `test_patterns` row.
- `docs/reference/API.md` — `## little_loops.work_verification` section (~L2293-2364, update if the signature changes); `### ProjectConfig` (~L386-406) field row with `# ENH-2935` provenance if the key lands there; module-index row (~L33) for `little_loops.test_tamper_guard` if not already added by ENH-2933.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py` — re-exports `verify_work_was_done` in the top-level package surface (import ~L67, listed in `__all__` ~L124), a second re-export site beyond `git_operations.py:15-19`. If `verify_work_was_done()`'s signature changes (e.g. gains a `config`/`repo_root` parameter to pass through to `run_tamper_guard`), both re-export sites must stay signature-compatible; a bare `from little_loops import verify_work_was_done` consumer would otherwise break silently. [Agent 1 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py`'s `to_dict()` method (the literal dict spanning ~L830-910, `code_query` block at ~L866-872) is the value source `resolve_variable()` (L912-934) actually walks — this is a distinct edit from the dataclass `from_dict`/field declaration; omitting it makes `ll-config get <key>` silently return `None` even though the field resolves correctly everywhere else. [Agent 2 finding]
- `scripts/little_loops/config/__init__.py` — if a `CodeQueryConfig`-style sibling dataclass is chosen (rather than nesting on `ProjectConfig`), the new config class needs an import line (mirroring `CodeQueryConfig` ~L46) and an `__all__` entry (mirroring `"CodeQueryConfig"` ~L124) to be part of the package's public config surface; plus three parallel additions inside `BRConfig`'s own wiring in `config/core.py` — the sibling's import (~L27), its `self._<new> = <NewConfig>.from_dict(self._raw_config.get("<key>", {}))` construction (~L267), and a `@property` accessor (~L365-367). [Agent 1 + Agent 2 findings]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — the existing "Tamper Guard" section (ENH-2934, ~L664-694) documents the guard as an FSM-only `tamper_guard:` state key with no mention of `ll-auto`/`ll-parallel`/`ll-sprint`; add a cross-reference to the non-FSM path this issue adds so the section doesn't read as FSM-exclusive. [Agent 2 finding]
- `docs/reference/CLI.md`'s `ll-config get` section (~L299-315) — optional: a worked example line for the new tamper-guard key, following the existing `ll-config get project.src_dir`-style examples. [Agent 2 finding, non-blocking]

### Tests
- `scripts/tests/test_work_verification.py:512-539`, `TestVerifyWorkWasDoneIntegration` — add a tamper-guard-tripped scenario (a diff touching only test-pattern-matched files), mocking `subprocess.run` per the existing convention.
- `scripts/tests/test_worker_pool.py:1316-1350` — extend the four existing `_verify_work_was_done` unit tests (`_accepts_code_changes`, `_rejects_no_changes`, `_rejects_excluded_only`, `_respects_config`) to cover the tamper-guard path.
- `scripts/tests/test_config_schema.py:337-357` (`test_health_url_in_schema`) and `:359` (`test_project_test_patterns_in_schema`) — template for the new policy-key schema-presence test.
- New tests must patch/exercise `run_tamper_guard` directly (see Design Notes) rather than stubbing `verify_work_was_done` wholesale, or they silently don't exercise the guard.
- A test covering `ll-auto` end-to-end (`issue_manager.py` Phase 3) where an agent weakened a test trips the guard with no FSM state involved.
- A test covering the full precedence chain for the non-FSM path: loop-level default > config key > built-in `fail`, and confirming the config key never overrides an explicit FSM state-level key when one is present (cross-checked against ENH-2934's state-level test).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py:2344` (`TestCodeQueryConfig`) and `:2426` (`test_resolve_variable_code_query`) — the schema-presence test at `test_config_schema.py:337-359` is only one of three verification layers `code_query.staleness` uses; the new tamper-guard key needs the matching dataclass-layer tests (`from_dict` defaults/all-fields/partial-data, `BRConfig` load-from-file) and a `resolve_variable()` test analogous to `test_resolve_variable_code_query`, or the config key is schema-documented but never proven to actually resolve. [Agent 3 finding]
- `scripts/tests/test_work_verification.py`'s `TestVerifyWorkWasDoneBaselineSha` class hard-codes exact `subprocess.run` call counts/`side_effect` list lengths and indexes specific `calls[N]` — `test_first_diff_has_changes_skips_second` (L385-396, expects `call_count == 1`), `test_no_baseline_sha_unchanged_behavior` (L497-509, expects `call_count == 2`), `test_baseline_sha_skipped_when_head_unchanged` (L481-495, 3-element `side_effect`), `test_committed_changes_detected_via_baseline_sha` (L436-460, 4-element `side_effect`, indexes `calls[2]`/`calls[3]`), `test_committed_excluded_files_only_returns_false` (L462-479, same 4-call shape). If `run_tamper_guard`'s own git enumeration (snapshotting via `subprocess.run`) runs inside the same `verify_work_was_done()` call path under these tests' blanket `patch("subprocess.run")`, the `side_effect`-based tests will raise `StopIteration` and the `call_count`-based ones will go stale — these need their mocks updated in the same change, not discovered as a later failure. [Agent 3 finding]
- `scripts/tests/test_issue_manager.py` — beyond the general `~2632-2932` range already noted, the specific hard assertion `mock_verify.assert_called_once_with(mock_logger, baseline_sha=test_sha)` at `L2850`, plus the sibling `patch("little_loops.issue_manager.verify_work_was_done", ...)` blocks at `L2663, 2706, 2786, 2839, 2886, 2932`, must have their mock call/assert signatures updated once `verify_work_was_done()` gains a `config`/`repo_root` parameter — these are the exact lines, not just the range. [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_test_tamper_guard.py` — confirmed to exist (ENH-2933's
  own test file); its fixtures/mocking conventions for `snapshot_test_paths`/
  `apply_tamper_policy` are the closest precedent for unit-testing
  `run_tamper_guard` calls in isolation, as opposed to the integration-style
  `subprocess.run` mocking used in `test_work_verification.py`.
- Confirmed `ll-sprint` has no direct `_verify_work_was_done` call site of
  its own in `scripts/little_loops/cli/sprint/*.py` — it delegates entirely
  through `ParallelOrchestrator`/`WorkerPool`, so the single
  `worker_pool.py:1212` hook genuinely covers both `ll-parallel` and
  `ll-sprint` with no separate sprint-side wiring needed.

## Scope Boundaries

**In scope:** the `work_verification.py` hook, confirming both orchestrator
call sites inherit it, the non-FSM config-default policy key and its
`ProjectConfig`/`CodeQueryConfig` mirror, and the precedence chain's
non-FSM half (loop default > config key > built-in default).

**Out of scope:**
- The guard core itself — ENH-2933, consumed here.
- The `tamper_guard:` FSM state key, its schema/lint, and the
  `executor.py` hook — ENH-2934.
- `project.test_patterns` — ENH-2973.

## Acceptance Criteria

- [x] `work_verification.verify_work_was_done()` calls `run_tamper_guard` (ENH-2933) against the changed-file set (explicit or self-derived).
- [x] The guard fires on the non-FSM path: an `ll-auto` run whose agent weakened a test trips it, with no FSM state involved — covered by a direct test.
- [x] The guard fires for `ll-parallel`/`ll-sprint` via the same `work_verification.py` path, not a second independently-maintained hook.
- [x] A project-global config key (shape/location precedent: `code_query.staleness`) supplies the default policy for the non-FSM path and the FSM adapter's loop-level fallback; it is documented in `config-schema.json`, mirrored on exactly one `config/*.py` dataclass, and resolves through `BRConfig.resolve_variable()`.
- [x] The config key never overrides an explicit FSM state-level `tamper_guard:` key — a test covers this precedence level.
- [x] `revert` on the non-FSM path uses the same git tracked-vs-untracked handling as `worker_pool.py:_cleanup_leaked_files()`, via the shared core (no second revert implementation).
- [x] New tests exercise `run_tamper_guard`/its call site directly, not a wholesale `verify_work_was_done` stub.
- [x] `docs/reference/CONFIGURATION.md` and `docs/reference/API.md` are updated per Files to Modify.

## Impact

- **Priority (P2)**: inherited from ENH-2854.
- **Effort**: Medium — one shared hook plus a triple-declared config key (schema + dataclass + docs), but no new core logic.
- **Risk**: Low-Moderate — `work_verification.py` is a shared chokepoint for two orchestrators; the existing test-patching surface fragmentation (three import paths resolving to `verify_work_was_done`) is a real risk of tests silently not exercising the guard if not handled per Design Notes.

## Confidence Check Notes

**Readiness Score**: 97/100 | **Outcome Confidence**: 68/100

Both prior blockers are resolved as of this pass:
- **Program Design gate**: `ll-issues format-check ENH-2935` no longer reports `program_design_nonspecific` — the `## Program Design` § Signatures block added by `/ll:refine-issue` (2026-07-31) satisfies the linter's signature-shaped-line requirement. Gate passes cleanly.
- **Ambiguity**: the Design Notes' open either/or (duplicate vs. extract the candidate-path/changed-files enumeration) was explicitly decided by `/ll:decide-issue` on 2026-07-31 — Option B (shared helper in `test_tamper_guard.py`) selected with a scored rationale. No unresolved decision remains.

Residual outcome risk (informational, above threshold): Complexity (13/25) and Test Coverage (18/25) remain moderate — the signature change threads a new `config`/`repo_root` param through two orchestrator call sites, and three import paths resolving to `verify_work_was_done` mean new tests must exercise `run_tamper_guard` directly per the Design Notes, not stub the wholesale function.

## Status

**Open** | Created: 2026-07-30 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-07-31T05:35:15 - `c0f69f6b-078e-4f77-bf84-fdabd4cc3451.jsonl`
- `/ll:ready-issue` - 2026-07-31T05:05:10 - `219b6e33-3fcf-4794-8f6f-760ec3035991.jsonl`
- `/ll:confidence-check` - 2026-07-31T05:02:58 - `cb52be84-a4c7-43f4-8278-9ab4961113d3.jsonl`
- `/ll:decide-issue` - 2026-07-31T04:59:57 - `768ba5ab-f411-477e-8a17-011e3d69d19e.jsonl`
- `/ll:refine-issue` - 2026-07-31T04:56:14 - `97d47d9d-87e9-4574-a44e-1066fe88dabb.jsonl`
- `/ll:confidence-check` - 2026-07-31T04:52:04 - `8666d04f-9463-46ef-b634-b97e2f1c91e2.jsonl`
- `/ll:wire-issue` - 2026-07-31T04:49:31 - `b5728964-6714-4fff-9c56-b3fe7aeac787.jsonl`
- `/ll:refine-issue` - 2026-07-31T04:43:20 - `c8f24327-96a1-4d4e-85c1-650207f41062.jsonl`
- `/ll:issue-size-review` - 2026-07-31T03:22:37 - `8a99a216-98a4-4273-8b35-65acee67e859.jsonl`
