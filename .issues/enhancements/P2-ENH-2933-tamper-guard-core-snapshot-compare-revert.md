---
id: ENH-2933
title: Tamper guard core - snapshot/compare/revert over test files
type: ENH
priority: P2
status: done
discovered_date: 2026-07-30
completed_at: '2026-07-31T03:53:52Z'
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
relates_to:
- ENH-2854
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 23
---

# ENH-2933: Tamper guard core - snapshot/compare/revert over test files

## Parent Issue

Decomposed from ENH-2854: Guard against agent edits to test files during
verification. ENH-2854 scored Very Large on `/ll:issue-size-review` (11/11) —
the issue's own Impact section already anticipated this split: "if it scores
Very Large, the FSM adapter and the Python adapter are a clean sequential
split over a shared core." This child is that shared core.

## Summary

Build the guard core: a policy-parameterized (`revert` | `fail` | `allow`)
snapshot/compare/revert implementation over a changed-file set, with no FSM
or CLI-orchestrator knowledge. This is the single implementation both the
FSM adapter (ENH-2934) and the Python adapter (ENH-2935) will call — it must
land first and be independently correct and fully tested before either
adapter is built.

## Current Behavior

No mechanism exists to detect whether an agent modified test files or pytest
config files to make a verification step pass. A test suite going green is
trusted at face value, even when the change was to the test rather than the
defect.

## Expected Behavior

A policy-parameterized (`revert` | `fail` | `allow`) snapshot/compare/revert
core exists that can hash test files and resolved pytest config files before
and after a verification step, diff the two snapshots, and act on any
modified/deleted/added file per the configured policy — independent of any
FSM or CLI orchestrator.

## Motivation

"Make the tests pass" is a reward an agent can collect by weakening the
tests. Deleting an assertion, commenting out a case, loosening a comparison,
or adding a skip marker all turn a suite green without touching the defect.
Detecting it is mechanical: diff the test files (and the pytest config files
that gate which tests run) across a verification step, and compare against
what the agent was authorized to change. See ENH-2854 for the full origin
and motivation; this child implements the deterministic core mechanism.

## Proposed Solution

1. **Snapshot** test-file state (content hashes) plus the resolved pytest
   config files (`pytest.ini`, `pyproject.toml`, `tox.ini`, `setup.cfg` —
   whichever pytest actually reads for the run) over a changed-file set.
2. **Compare** two snapshots. Any modified, deleted, or newly-added file is
   a tamper finding; label config-file findings separately from test-file
   findings in the report.
3. **Policy** (`revert` | `fail` | `allow`, default `fail`):
   - `revert` — restore pre-existing test/config files to their pre-step
     state. Never deletes a file newly added during the step (that is
     ENH-2853's pre-patch check's job, not this guard's — this guard must be
     fully functional and testable with ENH-2853 absent).
   - `fail` — report the touched files; caller decides how to fail.
   - `allow` — permit the edits but still record them in the report.
4. **Report** — the set of touched files and the nature of each change
   (modified / deleted / added, and whether it's a config file) is always
   produced, regardless of policy.

## Design Notes

- Test-file identification goes entirely through ENH-2865's
  `scripts/little_loops/test_file_patterns.py`
  (`is_test_file`/`filter_test_files`, reading `config.project.test_patterns`)
  — do not re-derive test-file membership here.
- Deterministic only. No LLM judgment about whether an edit was "reasonable".
- This module has zero imports from `fsm/` or from `issue_manager.py` /
  `worker_pool.py` / `work_verification.py` — that boundary is what lets
  ENH-2934 and ENH-2935 both depend on it without depending on each other.
- Reuse existing shapes rather than writing from scratch:
  - `scripts/little_loops/codequery/codegraph.py:_sha256_file()` (~L140-146)
    and `_content_aware_head_moved()` (~L157-185) — the only existing
    content-hash-over-a-file-set comparator in the codebase; the snapshot/
    compare step should follow this shape.
  - `scripts/little_loops/parallel/worker_pool.py:_cleanup_leaked_files()`
    (~L1362) — git-based revert distinguishing tracked
    (`git checkout -- <files>`) vs. untracked (`unlink()`) files; the
    `revert` policy's shape.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`BRConfig` location/instantiation** — `scripts/little_loops/config/core.py`.
  `ProjectConfig` (~L147-195) declares `test_patterns: list[str]` (default
  `["**/test_*.py", "**/*_test.py", "**/tests/**", "conftest.py",
  "**/conftest.py"]`). `BRConfig(project_root: Path)` (`__init__` ~L214)
  resolves `.ll/ll-config.json`, and callers access
  `config.project.test_patterns` via the `project` property (~L289-292).
  Conventional call shape elsewhere: caller builds `BRConfig(project_root)`
  once upstream and passes it down — `run_tamper_guard` should follow that,
  not reconstruct its own `BRConfig` internally.
- **`resolved_pytest_config_paths` has no prior art to call into** — searched
  the codebase for existing pytest-config-resolution helpers; the only hits
  (`dependency_mapper/analysis.py` ~L277-291,
  `parallel/file_hints.py` ~L45-55) are unrelated `COMMON_FILES_EXCLUDE`
  lists, not pytest config readers. The nearest reusable piece is
  `scripts/little_loops/init/introspect.py:_read_toml()` (~L134-138), which
  wraps `tomllib.loads()` in `try/except (OSError, tomllib.TOMLDecodeError)`
  returning `None` on failure — the established safe-parse pattern for
  `pyproject.toml`, and `_python_command()` (~L178-191) already checks for
  `"ini_options" in tool.get("pytest", {})` presence. Priority order among
  `pytest.ini` / `pyproject.toml[tool.pytest.ini_options]` /
  `tox.ini[pytest]` / `setup.cfg[tool:pytest]` has no existing helper and
  must be implemented from scratch.
- **Git subprocess pattern — use the lightweight wrapper, not `GitLock`** —
  `worker_pool.py:_cleanup_leaked_files()` calls `self._git_lock.run(...)`,
  an instance method of the `GitLock` class
  (`scripts/little_loops/parallel/git_lock.py:28`, thread-safe, retry-on-
  `index.lock`). Since this module may not import `worker_pool.py`, follow
  worker_pool's tracked/untracked *shape* (`git status --porcelain`
  classified by `?`-prefix, `git checkout --` for tracked, `Path.unlink()`
  for untracked, never raising) but implement it with a plain
  `subprocess.run(["git", ...], cwd=repo_root, capture_output=True,
  text=True)` wrapper matching `codequery/codegraph.py:_git()` (~L61-76) —
  the codebase's existing dependency-free git helper shape.
- **Import-boundary enforcement has no shared utility — write a local
  `ast`-walk test** — every existing "this module has zero imports from X"
  boundary in the codebase is enforced by a bespoke per-module test, not a
  shared linter. Follow
  `scripts/tests/test_rn_refine.py:test_no_import_of_fsm_concurrency_lockmanager`
  (~L1382-1396) or
  `scripts/tests/spike/eval_trace_capture/test_trace_capture.py:test_spike_does_not_import_production_subprocess_utils`
  (~L91-103): read the module source, `ast.parse` it, `ast.walk` collecting
  `ast.Import`/`ast.ImportFrom` node names, and assert none start with
  `little_loops.fsm`, `little_loops.issue_manager`,
  `little_loops.parallel.worker_pool`, or `little_loops.work_verification`.
  This is the concrete test to add for the "no imports from `fsm/`..." AC.
- **`BRConfig` optionality — deliberate deviation from `filter_test_files`.**
  _Wiring pass added by `/ll:wire-issue`:_ `test_file_patterns.py`'s
  `filter_test_files`/`is_test_file` take `config: BRConfig | None = None`
  and fall back to a private `_default_config() -> BRConfig` (i.e.
  `BRConfig(Path("."))`) when the caller omits it. This issue's own
  `run_tamper_guard(changed_files, config: BRConfig, ...)` makes `config`
  required with no such fallback — consistent with the Codebase Research
  Findings note that callers build `BRConfig` once upstream and pass it
  down, but a real signature-optionality mismatch with the one sibling
  module `run_tamper_guard` calls into. Keep `config` required; do not add a
  local default-construction fallback here (that would let this module
  silently diverge from the project root its own `repo_root` param
  identifies).

## Program Design

### Types

- `TamperPolicy = Literal["revert", "fail", "allow"]`
- `TamperFinding`: dataclass — `path: str`, `kind: Literal["modified", "deleted", "added"]`, `is_config: bool`
- `TamperSnapshot = dict[str, str | None]` — path → sha256, `None` for a path missing/unreadable at snapshot time
- `TamperReport`: dataclass — `policy: TamperPolicy`, `findings: list[TamperFinding]`, `reverted: list[str]`, `passed: bool`

### Signatures

- `snapshot_test_paths(paths: list[str], repo_root: Path) -> TamperSnapshot`
- `compare_snapshots(before: TamperSnapshot, after: TamperSnapshot) -> list[TamperFinding]`
- `resolved_pytest_config_paths(repo_root: Path) -> list[str]`
- `apply_tamper_policy(policy: TamperPolicy, findings: list[TamperFinding], repo_root: Path) -> TamperReport`
- `run_tamper_guard(changed_files: list[str], config: BRConfig, policy: TamperPolicy, repo_root: Path) -> TamperReport`

### Call Path

`run_tamper_guard` → `filter_test_files` (ENH-2865) → `snapshot_test_paths`
(called twice, before/after, by whichever adapter owns step timing) →
`compare_snapshots` → `apply_tamper_policy`. Adapters (ENH-2934, ENH-2935)
call `run_tamper_guard`; this module never calls into either adapter.

### Deviations

_2026-07-30, implementation pass:_ `run_tamper_guard`'s signature gained an
explicit `before: TamperSnapshot` parameter (final signature:
`run_tamper_guard(before, changed_files, config, policy, repo_root)`), not
present in the Program Design's listed signature
(`run_tamper_guard(changed_files, config, policy, repo_root)`). Reason: the
Call Path note says the adapter "owns step timing" and calls
`snapshot_test_paths` twice (before/after) — but the original signature gave
`run_tamper_guard` no way to receive that pre-step snapshot, so it could not
actually compare before/after itself without either (a) requiring the step to
already be committed to git (comparing against HEAD, which is wrong when
TDD-mode legitimately edits test files earlier in the same uncommitted
work), or (b) silently comparing a snapshot against itself (no-op). Making
`before` an explicit parameter is the only shape where the adapter captures
state immediately prior to the step (as the Call Path text already implies)
and `run_tamper_guard` remains a single call the adapter makes right after
the step completes, using `changed_files` only to catch paths (e.g. a newly
added test file) that couldn't have been in `before`'s path set.

## Files to Modify

- `scripts/little_loops/test_tamper_guard.py` (new) — the full core described above.
- `scripts/tests/test_test_tamper_guard.py` (new) — policy/finding-kind matrix
  modeled on `scripts/tests/test_codequery_codegraph.py:TestStalenessMatrix`
  (~L267-372: `@pytest.fixture(autouse=True)` shared precondition + a private
  `_repo_with_fresh_index`-style scenario builder + `@pytest.mark.parametrize`
  over policy), plus the import-boundary `ast`-walk test described in
  Design Notes → Codebase Research Findings.
- `docs/reference/API.md` — _Wiring pass added by `/ll:wire-issue`:_ ENH-2935's
  own issue text says "module-index row (~L33) for `little_loops.test_tamper_guard`
  if not already added by ENH-2933," but ENH-2933's own scope never claimed
  it — resolving that ownership gap here. Note: the closest precedent,
  `test_file_patterns.py` (ENH-2865), did **not** get a Module Overview table
  row, only an inline prose mention under `### ProjectConfig` (~L406). Follow
  whichever of those two shapes is still accurate at implementation time;
  either way, add at least the inline mention so ENH-2935's assumption holds.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_ none — confirmed via agent trace that
`run_tamper_guard`/`apply_tamper_policy`/etc. have zero existing references
anywhere in `scripts/`. This is expected: ENH-2933 is a new standalone core
module with no callers until ENH-2934/ENH-2935 land (both explicitly out of
scope here).

### Tests

_Wiring pass added by `/ll:wire-issue` — concrete precedent files/line ranges
to model `scripts/tests/test_test_tamper_guard.py` on:_
- `scripts/tests/test_codequery_codegraph.py:267-372` (`TestStalenessMatrix`)
  — the policy-matrix shape named in Files to Modify above; companion helpers
  `_git()` (~L57), `_commit_at()` (~L68), `_init_repo()` (~L78) build a real
  temp git repo for revert-policy scenarios.
- `scripts/tests/test_rn_refine.py:1382-1396`
  (`test_no_import_of_fsm_concurrency_lockmanager`) and
  `scripts/tests/spike/eval_trace_capture/test_trace_capture.py:91-103`
  (`test_spike_does_not_import_production_subprocess_utils`) — both ast-walk
  import-boundary test shapes; the former also pairs the negative assertion
  with a positive one (still imports the intended primitive) — worth doing
  the same for `test_tamper_guard.py`.
- `scripts/tests/test_worker_pool.py:1562-1636`
  (`test_cleanup_leaked_files_tracked`/`_untracked`/`_empty_list`/`_gitignored`)
  — the direct tracked-vs-untracked revert-policy precedent this issue's
  `apply_tamper_policy("revert", ...)` tests should mirror; supporting
  fixtures `temp_repo_with_config` (~L45), `br_config` (~L81-83, the
  `BRConfig(temp_repo_with_config)` one-liner), `mock_git_lock` (~L86-89).
  Two established styles coexist for exercising git state in tests — real
  `git` subprocesses (`test_codequery_codegraph.py`) vs. mocked
  `git_lock.run` (`test_worker_pool.py`) — pick whichever matches how
  `test_tamper_guard.py`'s revert function ends up calling git.
- `scripts/tests/test_test_file_patterns.py` — shows a lighter-weight
  `SimpleNamespace(project=SimpleNamespace(test_patterns=patterns))`
  stand-in for `BRConfig` (`_config_with_patterns()` helper) as an
  alternative to constructing a real `BRConfig`, since `is_test_file`/
  `filter_test_files` only touch `config.project.test_patterns`.

## Scope Boundaries

**In scope:** the guard core module — types, snapshot/compare/revert/apply,
`resolved_pytest_config_paths`, and its own test suite covering all three
policies and all three finding kinds (modified/deleted/added), plus config-
file findings.

**Out of scope:**
- `project.test_patterns` and `test_file_patterns.py` — owned by ENH-2865,
  consumed here.
- The FSM state-level `tamper_guard:` key, `ll-loop validate` lint, and the
  `executor.py` hook — ENH-2934.
- The `work_verification.py` hook, the two orchestrator call sites, and the
  non-FSM config-default policy key — ENH-2935.
- ENH-2853's pre-patch check and its ordering relative to `revert` — this
  guard exposes the ordering constraint (never deletes a newly-added file)
  but the pre-patch check itself is ENH-2853's.

## Acceptance Criteria

- [x] `TamperPolicy`, `TamperFinding`, `TamperSnapshot`, `TamperReport` are defined per Program Design.
- [x] `snapshot_test_paths` hashes content over a path set; missing/unreadable paths snapshot as `None`.
- [x] `resolved_pytest_config_paths` returns the pytest config files pytest actually reads for the repo (`pytest.ini` / `pyproject.toml` `[tool.pytest.ini_options]` / `tox.ini` / `setup.cfg`), and these are included in the snapshot set alongside test-pattern-matched files.
- [x] `compare_snapshots` detects modified, deleted, and newly-added files.
- [x] `apply_tamper_policy` implements `revert` (restores pre-existing files via git tracked/untracked split, never deletes a newly-added file), `fail` (reports touched files, does not mutate the working tree), and `allow` (no mutation, still records findings).
- [x] Default policy is `fail`.
- [x] `TamperReport` always includes the full findings list and marks config-file findings via `is_config`, regardless of policy.
- [x] The module makes no LLM calls and has no imports from `fsm/`, `issue_manager.py`, `worker_pool.py`, or `work_verification.py`.
- [x] Test discovery goes through `test_file_patterns.filter_test_files`, not a hardcoded list.
- [x] Tests cover: commented-out assertion, added skip marker, deleted test file, newly-added test file, untouched tests, a config-only tamper (e.g. an added `--deselect`), and each of the three policies — following `scripts/tests/test_codequery_codegraph.py:TestStalenessMatrix`'s parametrized-policy-matrix shape.

## Impact

- **Priority (P2)**: inherited from ENH-2854.
- **Effort**: Small-Medium — a single new module with no cross-cutting wiring; the two adapters (ENH-2934, ENH-2935) depend on this landing first.
- **Risk**: Low — deterministic, no LLM calls, git-based revert has a direct precedent in `worker_pool.py`.

## Status

**Open** | Created: 2026-07-30 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-07-31T03:53:14 - `b8789ea5-29d1-4109-a3be-1de2b4bdddf6.jsonl`
- `/ll:ready-issue` - 2026-07-31T03:42:18 - `a1481288-0918-4492-94cd-f609611cb033.jsonl`
- `/ll:confidence-check` - 2026-07-31T03:40:07 - `6cea27c4-b940-46e0-bf44-9e682cbf64c5.jsonl`
- `/ll:wire-issue` - 2026-07-31T03:38:01 - `d0e9cb81-a06b-4195-8575-a9745df47d46.jsonl`
- `/ll:refine-issue` - 2026-07-31T03:30:31 - `5737acee-8b08-4e70-96d4-5496e0f16811.jsonl`
- `/ll:issue-size-review` - 2026-07-31T03:22:37 - `8a99a216-98a4-4273-8b35-65acee67e859.jsonl`
