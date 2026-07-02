---
id: FEAT-2339
title: Per-EPIC integration branch strategy for ll-parallel/ll-sprint
type: FEAT
priority: P3
status: done
captured_at: '2026-06-27T02:49:31Z'
discovered_date: 2026-06-27
discovered_by: capture-issue
labels:
- parallel
- sprint
- epics
- git
- worktree
relates_to:
- ENH-665
- BUG-2323
- ENH-2176
- FEAT-1737
decision_needed: false
confidence_score: 95
outcome_confidence: 45
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 0
size: Very Large
---

# FEAT-2339: Per-EPIC integration branch strategy for ll-parallel/ll-sprint

## Summary

little-loops currently has **no epic-awareness in its branching model**. When
ll-parallel (or ll-sprint resolving an EPIC into children) processes the children
of an EPIC, each child issue gets its own per-issue branch
(`feature/<id>-<slug>` or `parallel/<id>-<timestamp>`), forks off the single
global `base_branch` (default `main`), and merges back into `base_branch`
independently.

This FEAT proposes an opt-in **per-EPIC integration branch** strategy: when
processing children of an EPIC, create an integration branch (e.g.
`epic/EPIC-1389-<slug>`) off the base branch; each child forks from and merges
**into the epic branch** rather than `main`; the epic branch lands on `main` as a
single unit (or one PR) when the EPIC is complete.

## Current Behavior

- Branch names are derived per-issue only — `parallel/worker_pool.py:334-339`:
  ```python
  if self.parallel_config.use_feature_branches:
      branch_name = f"feature/{issue.issue_id.lower()}-{slugify(issue.title)}"
  else:
      branch_name = f"parallel/{issue.issue_id.lower()}-{timestamp}"
  ```
- `base_branch` is a single global value (`parallel/types.py:382`, default
  `"main"`) used as **both** the fork point and the merge target for every
  issue — `merge_coordinator.py:624,875`.
- No code in `parallel/` or `sprint.py` reads `issue.parent` / EPIC identity to
  influence branching or merge targets. `ll-sprint` *can* resolve an `EPIC-NNN`
  argument into an ephemeral sprint of its children (`sprint.py:287`), but those
  children still branch and merge per-issue.
- Net effect: sibling children of one EPIC each fork stale `main` and never see
  each other's work until it lands on `main`; an EPIC is delivered to `main` as
  N independent merges, never atomically.

## Expected Behavior

- A configurable branch strategy that, when an issue has an EPIC parent (or a
  run is scoped to an EPIC), routes the child's fork point and merge target to a
  shared per-EPIC integration branch instead of `base_branch`.
- The integration branch is created lazily (first child of the EPIC) off
  `base_branch`, reused by all subsequent children, and merged to `base_branch`
  as a single unit on EPIC completion (or surfaced as one PR when
  `open_pr_for_feature_branches` is enabled).
- Standalone (parentless) issues retain today's behavior unchanged.
- Default OFF — existing per-issue behavior is preserved unless explicitly
  enabled.

## Motivation

little-loops is heavily epic-oriented (`/ll:scope-epic`, `/ll:review-epic`,
`ll-issues epic-progress`, EPIC cascade closure, EPIC-as-sprint resolution).
Branching is the one orchestration surface that ignores EPICs entirely. A
per-EPIC branch unlocks workflow value that maps directly to how the project
already organizes work:

- **Atomic delivery** — `main` never carries a half-finished EPIC; the EPIC lands
  (or is reverted) as one coherent unit.
- **One PR per EPIC** for review instead of N noisy per-child PRs.
- **Intra-EPIC dependencies work** — children build on each other inside the
  integration branch instead of each forking stale `main` (today a child can't
  see a sibling's not-yet-merged change).

## Proposed Solution

Introduce a branch-strategy concept with three modes; epic mode is the new one:

- `per_issue` (today's default) — fork from / merge to `base_branch`.
- `per_epic` — children of an EPIC share `epic/<EPIC-ID>-<slug>`; EPIC branch
  merges to `base_branch` on completion.

Add config under the existing `parallel` namespace (or a new `epics.branch`
sub-object — see Edge Cases). Sketch:

```jsonc
"parallel": {
  "epic_branches": {
    "enabled": false,            // master switch for per-EPIC integration branches
    "prefix": "epic/",           // branch name prefix
    "merge_to_base_on_complete": true,  // auto-merge epic branch to base_branch when EPIC done
    "open_pr": false             // open one PR for the epic branch instead of auto-merge
  }
}
```

Key implementation insight — **the worktree plumbing is half-built already**:
`worker_pool.create_worktree(..., base_branch=...)` (`worker_pool.py:648`)
already accepts a per-call base/fork-point. The gap is on the merge side:
`merge_coordinator` hardcodes `self.config.base_branch` as the target
(`merge_coordinator.py:624,875`). The core change is making the *target* a
function of the issue's EPIC parent, not a global constant.

EPIC-completion detection should lean on `ll-issues epic-progress`. ⚠️ Note:
epic-progress counts only **direct** `parent:` children (non-recursive) — a
sub-EPIC's grandchildren will not roll up automatically, so nested EPICs need an
explicit decision (treat each EPIC level as its own branch, or flatten).

### Codebase Research Findings

_Added by `/ll:refine-issue` — config placement options and implementation patterns:_

**Config placement — two concrete options (decide before implementation):**

**Option A — `parallel.epic_branches.*` (near other worktree/branch knobs)**
> **Selected:** Option A — `parallel.epic_branches.*` — follows the established 4-location extension pattern (`use_feature_branches`/`open_pr_for_feature_branches`) with all test infrastructure directly reusable; nested-object precedent exists in `commands.*`
Add `epic_branches` as a nested object inside the existing `"parallel"` block in
`config-schema.json` (lines 305–409, before `"additionalProperties": false` at
line 408). Mirror in `types.py:ParallelConfig`, `config/automation.py:ParallelAutomationConfig`,
and `config/core.py:create_parallel_config()`. Follows the exact same 4-location
pattern as `use_feature_branches` / `open_pr_for_feature_branches`.

**Option B — `epics.branch.*` (separate top-level EPIC lifecycle namespace)**
Add a new `"epics"` top-level object in `config-schema.json` with a `"branch"`
sub-object. Requires a new `EpicsConfig` dataclass in `config/` (likely
`config/features.py` or a new `config/epics.py`) and wiring through
`BRConfig.create_parallel_config()` to pass into `ParallelConfig`. Cleaner
namespacing but more scaffolding.

**4-location config extension pattern (for whichever option is chosen):**
1. `parallel/types.py:ParallelConfig` — field + `to_dict()` entry + `from_dict()` entry
2. `config/automation.py:ParallelAutomationConfig` — mirrored field + `from_dict()` entry
3. `config/core.py:BRConfig.create_parallel_config()` — explicit keyword passthrough (line ~496)
4. `config-schema.json` — schema entry with `"type"`, `"description"`, `"default"`

**`compute_epic_progress()` — use as library, not subprocess:**
```python
from little_loops.issue_progress import compute_epic_progress
prog = compute_epic_progress(epic_id, all_issues)
is_complete = prog is not None and prog.done_count == prog.total_count
```

**Branch cleanup — do NOT add `epic/*` to `_is_ll_branch()` auto-delete list:**
`worktree_utils.py:_is_ll_branch()` must NOT be changed to auto-delete `epic/*`
branches. The epic integration branch is long-lived; it must only be deleted after
the EPIC-completion merge to `base_branch`. Add an explicit `delete_epic_branch()`
method (or inline in the EPIC-completion step) that only runs after successful merge.

**Update (2026-07-02) — `compute_epic_progress()` is no longer non-recursive:**
Commit `4887c87c` (same day, "fix(issues): walk transitive parent chain for epic
progress rollup") changed `compute_epic_progress()` (`issue_progress.py:83`, was
line 67) to walk the `parent:` chain **transitively** via a new cycle-guarded
`_issue_descends_to()` helper (`issue_progress.py:67-80`), mirroring
`cli/issues/list_cmd.py::_find_epic_ancestor`. New docstring: "Child resolution
walks the `parent:` chain transitively (cycle-guarded)... so an issue nests under
an EPIC even if its immediate parent is a (done) intermediate FEAT." Signature is
unchanged (`compute_epic_progress(epic_id: str, all_issues: list[IssueInfo]) ->
EpicProgress | None`).

Effect: **EPIC-completion detection (Implementation Step 5) already rolls up
grandchildren correctly** — the ⚠️ note above ("epic-progress counts only direct
`parent:` children (non-recursive)") is now stale for progress *counting*.

This does **not** resolve the nested-EPIC *branch-routing* question (see Edge
Cases / Acceptance Criteria): `compute_epic_progress()` tells you whether the
top-level EPIC is done, not which integration branch a grandchild should fork
from/merge into. Separately, `sprint.py:326`'s own EPIC→children resolution
(`ll-sprint EPIC-NNN`, used to build the run's issue list) still does a
**direct-only** `info.parent == epic_id` match and was not touched by `4887c87c`.
Run-construction and completion-detection therefore use two different traversal
depths today — the branch-routing design still needs to pick one level
(own-branch-per-level vs. flatten-to-nearest) independent of this fix.

**Anchor corrections (verified 2026-07-02, no functional impact):**
- The "Key implementation insight" paragraph above cites
  `worker_pool.create_worktree(..., base_branch=...)` — the actual method name is
  `_setup_worktree(self, worktree_path, branch_name, base_branch=None)` (still
  line 648), which delegates to `setup_worktree()` in `worktree_utils.py`. Grep
  for `_setup_worktree`, not `create_worktree`.
- Integration Map cites `orchestrator.py:400,1122` for "rev-list/diff comparisons
  currently against `base_branch`". Only one such comparison exists — the
  `rev-list --count base_branch..branch_name` call, now at line 415 (drifted from
  ~400 by the BUG-2424 completion-commit-scoping change in `4453b0a0`). The
  second citation (was 1122) now lands inside `_open_pr_for_branch()` (line 1142)
  — that's the same `gh pr create --base` code already covered separately below;
  it is not a second rev-list/diff site.
- `cli/sprint/run.py` (Codebase Research Findings, Dependent Files) has **zero**
  occurrences of "EPIC"/"epic" as of 2026-07-02 — EPIC resolution lives
  exclusively in `sprint.py:286-338` (`Sprint.load_or_resolve()`). If
  epic-branch context needs to reach `create_parallel_config()` for
  sprint-driven runs (Implementation Step 6), it must be threaded through
  `sprint.py`'s resolution path, not added to `run.py` directly.
- `issue_parser.py:IssueInfo.parent` field drifted from line 251 to line 437
  (docstring comment at 424); field name/type unchanged.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-30.

**Selected**: Option A — `parallel.epic_branches.*`

**Reasoning**: Option A reuses the established 4-location config extension pattern (`use_feature_branches`, `push_feature_branches`, `open_pr_for_feature_branches`) with all target files, test infrastructure, and serialization conventions already in place. The sub-dataclass shape (`EpicBranchesConfig`) is directly modeled on `ConfidenceGateConfig` in `commands.*`, proving it is viable. Option B's cleaner semantic namespacing is outweighed by requiring 8-10 file touches, an entirely net-new Python layer despite a schema stub, and cross-namespace coupling that threads `epics` config through the already crowded `create_parallel_config()`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (`parallel.epic_branches.*`) | 2/3 | 3/3 | 3/3 | 2/3 | 10/12 |
| Option B (`epics.branch.*`) | 3/3 | 1/3 | 2/3 | 1/3 | 7/12 |

**Key evidence**:
- Option A: `use_feature_branches`/`open_pr_for_feature_branches` 4-location pattern is replicated verbatim; nested-object-within-config precedent exists in `CommandsConfig` (`confidence_gate`, `rate_limits`); all five test patterns (roundtrip, config-override, orchestrator mock, worker-pool spread, TUI) extend directly from `test_parallel_types.py` and `test_config.py`
- Option B: `epics` key exists in `config-schema.json` (lines 1299–1337) with `scope`/`cascade` sub-objects, but zero Python backing; adding `branch` requires net-new `EpicsConfig` in `features.py`, wiring through the 230-line hand-maintained `to_dict()`, and growing `create_parallel_config()`'s already 23-param signature

## Integration Map

- `scripts/little_loops/parallel/worker_pool.py` — branch-name derivation
  (`:334-339`) and `create_worktree` fork point (`:648`); resolve epic branch +
  fork point per issue.
- `scripts/little_loops/parallel/merge_coordinator.py` — merge target
  (`:624,875`); route to epic branch instead of `base_branch`; add epic-branch →
  base merge on completion.
- `scripts/little_loops/parallel/types.py` — `base_branch` field (`:382`) and
  `BrConfig`/parallel config (de)serialization (`:463,509`); add
  `epic_branches` config.
- `scripts/little_loops/parallel/orchestrator.py` — run scoping; rev-list/diff
  comparisons currently against `base_branch` (`:400,1122`) must be
  epic-branch-aware.
- `scripts/little_loops/sprint.py` — EPIC→children resolution (`:287`) is the
  natural place to flag a run as epic-scoped.
- `scripts/little_loops/init/tui.py` — surface the new flag in `ll-init`
  alongside `use_feature_branches` (`:343,378,664`).
- `config-schema.json` — add `parallel.epic_branches` (or `epics.branch`) block.
- Lifecycle: who creates/deletes the epic branch and when it merges to base —
  align with `worker_pool.py:736-744` branch-cleanup (currently only deletes
  `parallel/`-prefixed branches).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Missing integration points not in the map above:**

- `scripts/little_loops/config/automation.py:ParallelAutomationConfig` — mirrors
  every boolean field in `ParallelConfig` (lines 57–62: `use_feature_branches`,
  `push_feature_branches`, `open_pr_for_feature_branches`). A new `epic_branches`
  sub-object must be added here AND to `types.py:ParallelConfig` or the config
  key will be silently ignored when read from `ll-config.json`.
- `scripts/little_loops/config/core.py:BRConfig.create_parallel_config()` (line 415) —
  bridges `ParallelAutomationConfig` fields into `ParallelConfig` via explicit
  keyword mapping (e.g. line 496 `open_pr_for_feature_branches=self._parallel.open_pr_for_feature_branches`).
  Must add the new `epic_branches` field mapping here too — **4-location pattern**,
  not 3.
- `scripts/little_loops/parallel/worker_pool.py:_update_branch_base()` — does
  `git rebase <remote>/<base_branch>` before merging; must rebase against the
  epic branch when `epic_branches` is active, not global `base_branch`.
- `scripts/little_loops/parallel/worker_pool.py:_get_changed_files()` — does
  `git diff --name-only <base_branch> HEAD`; must diff against epic branch for
  accurate changed-file detection when children share the epic branch.
- `scripts/little_loops/cli/sprint/run.py:~578` — duplicates the
  `git rev-parse --abbrev-ref HEAD` base-branch auto-detection that also appears
  in `cli/parallel.py:main()`; both need epic-branch awareness for sprint-driven runs.
- `scripts/little_loops/parallel/orchestrator.py:_open_pr_for_branch()` — runs
  `gh pr create --base <base_branch> --head <branch>`. In epic mode with
  `open_pr=True`, the PR target must be the epic branch (not `base_branch`) so
  the child's PR lands on the integration branch.
- `scripts/little_loops/worktree_utils.py:_is_ll_branch()` — only matches
  `parallel/*` and timestamp-named branches as auto-delete-safe. `epic/*` branches
  will NOT be auto-deleted by `_cleanup_worktree()`. The epic branch lifecycle
  (who deletes it and when) needs an explicit decision: do NOT add `epic/*` to
  the auto-delete list without careful consideration — the epic branch is
  intentionally long-lived until EPIC completion.
- `scripts/little_loops/issue_progress.py:compute_epic_progress()` (line 67) —
  canonical function for EPIC-completion detection; call as a library, not
  subprocess. Signature: `compute_epic_progress(epic_id: str, all_issues:
  list[IssueInfo]) -> EpicProgress | None`.
- `scripts/little_loops/issue_parser.py:IssueInfo.parent` (line 251: `parent:
  str | None = None`) — the resolver (implementation step 2) should use
  `issue.parent` from the already-parsed `IssueInfo` objects. Note: `IssueInfo`
  also has an `IssueInfo.epic` field (separate from `parent`); the canonical
  parent-lookup approach used everywhere else (`issue_progress.py:87`,
  `sprint.py:326`) is `i.parent == epic_id`, not `i.epic`.

**EPIC context drop point:**
After `SprintManager.load_or_resolve()` returns the ordered issue IDs, all EPIC
identity is discarded before `create_parallel_config()` is called. The epic-branch
resolver needs to either (a) receive the epic_id alongside the issue list when
`create_parallel_config()` is invoked, or (b) look it up at runtime per-issue
using the `IssueInfo.parent` field by re-parsing or caching issue metadata.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/parallel.py` — `main_parallel()` calls `create_parallel_config(use_feature_branches=args.feature_branches, base_branch=_base_branch)` (lines 248–269); needs `--epic-branches` CLI flag + kwarg passthrough matching the `--feature-branches` pattern [Agent 1 finding]
- `scripts/little_loops/cli/sprint/__init__.py` — defines `--feature-branches` argument for the `run` subparser (line 142); needs a parallel `--epic-branches` `add_argument()` call if a CLI flag is added [Agent 1 finding]
- `scripts/little_loops/config/core.py:BRConfig.to_dict()` — explicitly enumerates every `parallel.*` key at lines 555–574 (`use_feature_branches`, `push_feature_branches`, `open_pr_for_feature_branches`, `base_branch`, `remote_name`); `epic_branches` sub-object must be serialized here or the `to_dict()` output silently omits it [Agent 2 finding]

_Second wiring pass (`/ll:wire-issue`, 2026-07-02):_
- `scripts/little_loops/parallel/__init__.py` — explicit `__all__` list (line ~35) re-exports `ParallelConfig` and sibling dataclasses imported from `types.py:22-30`; if `EpicBranchesConfig` is added as a new nested dataclass (per Decision Rationale, modeled on `ConfidenceGateConfig`), it needs a matching import + `__all__` entry here — mirrors how `ConfidenceGateConfig` is re-exported from `config/__init__.py` (verified: both files use explicit `__all__` lists, not wildcard exports) [caller-tracer agent finding, verified]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `### parallel` section (lines 340–357) has a table row for each existing `parallel.*` key including `use_feature_branches`, `push_feature_branches`, `open_pr_for_feature_branches`, `base_branch`; needs a new `epic_branches.{enabled, prefix, merge_to_base_on_complete, open_pr}` sub-object block [Agent 2 finding]
- `docs/reference/CLI.md` — lines 351 and 418 document `--feature-branches` for `ll-parallel` and `ll-sprint` respectively; needs `--epic-branches` flag documentation (or config-only note) [Agent 2 finding]
- `docs/guides/SPRINT_GUIDE.md` — lines 263–307 contain extensive prose about `use_feature_branches` including the coverage boundary note, prune section, and PR workflow table; needs a new section describing `epic_branches` precedence over `use_feature_branches` for EPIC children [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Tests to update (will break or miss new field):**
- `scripts/tests/test_parallel_types.py:TestParallelConfig.test_roundtrip_serialization` (lines 1017–1059) — constructs `ParallelConfig` with all non-default fields and asserts field-by-field; must add `epic_branches` constructor arg and assert; won't immediately fail but will miss coverage [Agent 3 finding]
- `scripts/tests/test_init_tui.py:_wire_q()` (line 50, confirm_returns lines 121–123) — positional list for TUI confirm answers; inserting a new `epic_branches.enabled` confirm between `use_feature_branches` and `session_digest` will misalign all existing call sites that include `"parallel" in features` [Agent 3 finding]
- `scripts/tests/conftest.py:sample_config` fixture (line 232) — `parallel` block has `"use_feature_branches": True`; tests for the new sub-object need fixture variants; existing tests produce a safe default silently but `epic_branches` tests need explicit fixture entries [Agent 3 finding]
- `scripts/tests/test_worker_pool.py:_update_branch_base` tests (lines 1714–1791) — three tests set `worker_pool.parallel_config.base_branch = "main"` before calling `_update_branch_base()`; when that method becomes epic-branch-aware, epic-mode variants are needed [Agent 2 + 3 finding]

**Tests to write (new coverage gaps):**
- `scripts/tests/test_config_schema.py` — no test for `parallel.epic_branches` block; add pattern analogous to `test_commands_recursive_refine_in_schema()` asserting `enabled` (bool, default False), `prefix` (string), `merge_to_base_on_complete` (bool), `open_pr` (bool) all present inside `parallel["properties"]["epic_branches"]` [Agent 3 finding]
- `scripts/tests/test_config.py:TestBRConfig` — four `create_parallel_config_feature_branches_*` tests (lines 907–949) need `epic_branches` counterparts using the same explicit/None/fallback pattern [Agent 2 + 3 finding]
- `scripts/tests/test_merge_coordinator.py` — only tests error string detection (`_is_local_changes_error`, `_is_untracked_files_error`); no coverage of merge target selection; new tests needed for epic-branch vs base-branch routing [Agent 3 finding]
- `scripts/tests/test_parallel_cli.py` — no end-to-end test for `--epic-branches` flag; add one following existing `TestParallelNormalRun` pattern [Agent 3 finding]
- `scripts/tests/test_sprint.py` — needs `test_wave_parallel_config_passes_epic_branches` counterpart to `test_wave_parallel_config_passes_clean_start` (line 2274) for `epic_branches` kwarg propagation [Agent 3 finding]

**Tests to audit (won't break, but reference adjacent functionality):**
- `scripts/tests/test_orchestrator.py:test_cleanup_orphaned_worktrees` (line 509) and `test_inspect_worktree_with_feature_branch` (line 1001) — need audit to check `_inspect_worktree` and `_cleanup_orphaned_worktrees` handle `epic/*` prefix correctly [Agent 3 finding]
- `scripts/tests/test_wiring_init_and_configure.py:DOC_STRINGS_PRESENT` (lines 174–176) — parametrized assertions on `use_feature_branches` presence in skill files; add new rows for `epic_branches` after skill files are updated [Agent 2 finding]

_Second wiring pass (`/ll:wire-issue`, 2026-07-02) — new test files/gaps not in the original pass above:_

**Tests to update (existing coverage that must change or is a hidden dependency):**
- `scripts/tests/test_config.py:test_to_dict_parallel_schema_aligned_keys` (lines 776–797, verified — distinct from the already-listed `TestBRConfig` passthrough tests at 907–949) — asserts specific keys inside `BRConfig.to_dict()["parallel"]` (`use_feature_branches`, `remote_name`, `worktree_copy_files`, etc.); needs an `"epic_branches" in parallel` assertion or Wiring Phase step 10 (`to_dict()` serialization) regresses silently
- `scripts/tests/test_worker_pool.py:test_process_issue_uses_feature_branch_name_when_enabled` (2191–2236) — the `MagicMock()` issue only sets `issue_id`/`issue_type`/`path`/`title` (lines 2211–2215), never `issue.parent`. Once epic-mode branch-naming checks `issue.parent`, MagicMock's truthy auto-attribute for an unset field could cause a false-pass/false-fail — add explicit `issue.parent = None` when this area is touched
- `scripts/tests/test_orchestrator.py:test_on_worker_complete_feature_branch_open_pr` (2008–2052) — only asserts `args[0]=="gh" and args[1]=="pr"`, never checks the `--base <value>` argument. No existing test would catch a regression if `_open_pr_for_branch()`'s `--base` target silently fails to switch to the epic branch — add an assertion on the actual `--base` value
- `scripts/tests/test_cli_sprint.py:TestFeatureBranchInPlaceWarning` (new file/class, not in original Tests list) — see "Additional Coupling" finding above; needs an `epic_branches` counterpart once the in-place/contention-subwave warning path is made epic-aware
- `scripts/tests/test_subprocess_mocks.py` (new file, not in original Tests list) — `test_setup_worktree_with_base_branch_appends_commit_ish` (~line 615) plus two more assertions (~838, ~892) check that `config.base_branch`'s literal value appears in captured `git checkout` commands. Hidden dependency on `_setup_worktree()`'s fork-point argument — currently only covers the standalone-issue path; needs a counterpart for the epic-branch substitution path

**Tests to write (new coverage gaps):**
- `scripts/tests/test_config.py:TestParallelAutomationConfig` (lines 340–412) — direct unit tests of `ParallelAutomationConfig.from_dict()`; needs an `epic_branches` counterpart test. Template: `TestConfidenceGateConfig` (415–443) — the exact sub-dataclass shape (`ConfidenceGateConfig`) `EpicBranchesConfig` is modeled on per the Decision Rationale
- `scripts/tests/test_sprint.py:TestSprintManagerLoadOrResolve` (~2329–2540, "FEAT-1737") — direct-only EPIC→children resolution tests (`info.parent == epic_id`); no grandchild/nested-EPIC test exists here, unlike `test_issue_progress.py`'s transitive-walk coverage — confirms the run-construction vs. completion-detection depth-mismatch (noted in Edge Cases) is untested on the `sprint.py` side; add a nested-EPIC test

**Existing precedent (not a gap — cite as the resolver-test template):**
- `scripts/tests/test_issue_progress.py:TestComputeEpicProgress` (whole file, 277 lines) — full unit-test suite for `compute_epic_progress()`, including `test_transitive_chain_includes_grandchildren` (244) and `test_cycle_in_parent_chain_does_not_loop` (254). Uses a `_make_issue(tmp_path, issue_id, parent=...)` helper (12–64) building real temp-file-backed `IssueInfo` objects. Best template for a new `_resolve_branch_targets()` resolver test (Implementation Step 2): construct `IssueInfo`s with `parent="EPIC-X"`, call the resolver directly, assert `(fork_point, merge_target)`.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `skills/configure/areas.md` — `## Area: parallel` lines 188–198 (Current Values display) and lines 255–268 (Round 2 question) show `use_feature_branches` but not `epic_branches`; needs `epic_branches.enabled` display line and a new Round 3 confirm block [Agent 2 finding]
- `skills/configure/show-output.md` — lines 50–53 display `use_feature_branches`, `push_feature_branches`, `open_pr_for_feature_branches`, `base_branch`; needs `epic_branches.{enabled, prefix, merge_to_base_on_complete, open_pr}` display lines [Agent 2 finding]
- `skills/configure/SKILL.md` — lines 103, 136, 235, and 380 each describe the `parallel` area as covering "feature branches"; should mention "epic branches" alongside [Agent 2 finding]

_Second wiring pass (`/ll:wire-issue`, 2026-07-02):_
- `scripts/little_loops/templates/{typescript,java-gradle,java-maven,python-generic,dotnet,rust,javascript,generic,go}.json` (9 files, verified) — each stamps a `"parallel": {"use_feature_branches": false}` block at project-scaffold time (e.g. `python-generic.json:72`); no existing test enforces new `parallel.*` keys are mirrored here (`test_wiring_init_and_configure.py`'s `DOC_STRINGS_PRESENT` table only checks `skills/configure/*`, not `templates/`). Open decision, not yet resolved anywhere in this issue: does `epic_branches` need explicit parity in these 9 templates, or is it intentionally left to schema-default fallback? [side-effect-analyzer agent finding, verified]

### Additional Coupling — Hardcoded Branch-Prefix Gates & Cleanup Surfaces

_Second wiring pass (`/ll:wire-issue`, 2026-07-02) — three independent branch-prefix mechanisms beyond `worktree_utils._is_ll_branch()` (already covered above), each needing its own epic-mode decision:_

- `scripts/little_loops/parallel/merge_coordinator.py:_cleanup_worktree()` (gate at line 1088, verified) — `if branch_name.startswith("parallel/"):` before deleting the local branch post-merge, called from `_finalize_merge()`. This is a **second, separate** prefix-deletion guard from `worktree_utils._is_ll_branch()`. It won't delete an `epic/*` branch (matches long-lived intent), but it also won't delete whatever naming convention epic-mode *children* use once they fork from/merge into the epic branch — needs an explicit decision alongside `_is_ll_branch()`.
  > **Decided (2026-07-02):** No change needed. Epic-mode children keep their
  > existing `feature/`/`parallel/` naming (only fork/merge target changes),
  > so this gate already handles them correctly.
- `scripts/little_loops/parallel/worker_pool.py:prune_merged_feature_branches()` (line 1633, verified; filter at line 1681 `if not branch.startswith("feature/")`) — a third, independent branch-cleanup mechanism (ENH-2181), wired to `--prune-merged-branches` in `cli/parallel.py`. Only considers `feature/*` branches merged into a single `base_branch`. Once `epic/*` branches exist, this utility will silently skip merged epic branches (consistent with the FEAT's explicit-deletion design in Implementation Step 5), but its docstring ("Delete local feature/* branches already merged into base_branch") becomes incomplete once a second long-lived branch type exists — update docstring when this FEAT lands.
  > **Decided (2026-07-02):** No behavior change; docstring-only update
  > (Implementation Step 22) to state the `feature/*`-only scope is
  > intentional now that `epic/*` is a second long-lived branch type.
- `scripts/little_loops/cli/sprint/run.py` (verified, lines 485, 518–528) — a **second, distinct** warning site from the one already cited in the Integration Map (`~578`, multi-issue `_base_branch` auto-detection). This one is inside the in-place/single-issue/contention-subwave path: `effective_feature_branches = _feature_branches_arg if ... else config.parallel.use_feature_branches`, then warns `"feature-branch mode does not apply to single-issue / contention sub-waves..."` (gated by `_fb_warning_emitted`, ENH-2176). Since Edge Cases states epic mode supersedes per-issue feature branches for EPIC children, this path needs an analogous `epic_branches`-aware branch/warning. Test coupling: `scripts/tests/test_cli_sprint.py:TestFeatureBranchInPlaceWarning` asserts on the literal substring `"feature-branch mode does not apply"` — not previously listed in this issue's Tests section.
  > **Decided (2026-07-02):** Extend the existing warning with a parallel
  > `effective_epic_branches` check; append to (not replace) the existing
  > message so the `"feature-branch mode does not apply"` substring the
  > existing test asserts on stays intact. See Decision Rationale below.

## Implementation Steps

1. **Config schema + dataclasses (4 locations)** — Add `epic_branches` nested
   object to `config-schema.json` inside the `"parallel"` properties block
   (before `additionalProperties: false` at line 408). Add matching dataclass
   field to `types.py:ParallelConfig` + `to_dict()` + `from_dict()`; mirror in
   `config/automation.py:ParallelAutomationConfig` + its `from_dict()`; add
   passthrough in `config/core.py:BRConfig.create_parallel_config()` (~line 496).
2. **Epic-branch resolver** — Add `_resolve_branch_targets(issue: IssueInfo) ->
   tuple[str, str]` (fork_point, merge_target) to `WorkerPool`. Uses
   `issue.parent` (from `issue_parser.py:IssueInfo.parent`, line 251) and
   `self.parallel_config.epic_branches.enabled`; lazily creates
   `epic/<EPIC-ID>-<slug>` off `base_branch` on first call per epic_id.
3. **Wire resolver into branch naming + worktree setup** (`worker_pool.py:334-360`) —
   When epic mode active, use `f"epic/{parent_id.lower()}-{slugify(epic_title)}"`;
   pass the epic branch as `base_branch` to `_setup_worktree()` (replacing global
   `parallel_config.base_branch`). Also update `_get_changed_files()` (diff) and
   `_update_branch_base()` (rebase) to use the epic branch as the comparison base.
4. **Wire resolver into merge coordinator** (`merge_coordinator.py:624,875`) —
   Pass `merge_target` from resolver as the checkout/pull/merge target instead of
   `self.config.base_branch`. Shape decision (locked 2026-07-02, verified against
   `worker_pool.py:281-364`, `types.py:52-135`, `types.py:197-222`,
   `merge_coordinator.py:113-122` / `:615-630` / `:873-885`,
   `orchestrator.py:914-1059` / `:1135-1145`):
   - **Add `epic_branch: str | None = None` to `WorkerResult`** with matching
     `to_dict()`/`from_dict()` rows, mirroring how `was_blocked` (ENH-036) and
     `interrupted` were added.
   - **Populate once in `WorkerPool._process_issue()`** at the same site as
     `branch_name` / `worktree_path`, immediately above the
     `_setup_worktree(base_branch=...)` call. The fork point and merge target
     are the *same string* per Decision Rationale #1 (flatten-to-nearest), so
     the same `_resolve_branch_targets()` return value threads through both
     `_setup_worktree(base_branch=...)` (fork) and
     `WorkerResult.epic_branch` (merge target).
   - **At the three downstream consumer sites**, replace
     `base = self.config.base_branch` with
     `base = result.epic_branch or self.config.base_branch` —
     `merge_coordinator.py:624` (checkout in `_process_single_merge()`),
     `merge_coordinator.py:875` (fetch+rebase in same method), and
     `orchestrator.py:1142` (`gh pr create --base` in `_open_pr_for_branch()`).
   - **Rejected shapes:**
     - *Callable on `MergeCoordinator`* (`resolve_merge_target: Callable[[WorkerResult], str]`)
       is strictly more flexible than the decision permits — there is no
       scenario where the merge target differs from the fork point. Adds a
       constructor param, a new method, and a closure wiring in the
       orchestrator for no payoff.
     - *Field on `MergeRequest`* (`merge_target: str`) introduces a
       synchronization point where merge target can disagree with what was
       used as the fork point — e.g., if `_resolve_branch_targets()` ever
       takes config that can change between fork and merge. Option A keeps
       "what the worker forked from" and "where the merge should land" as the
       same string, by construction.
5. **EPIC-completion → epic-branch merge** — After all children of an EPIC are
   done, call `compute_epic_progress(epic_id, all_issues)` (from
   `issue_progress.py:67`); when complete, merge `epic/<id>` → `base_branch`
   (or open PR via `gh pr create --base base_branch --head epic/<id>`, analogous
   to `orchestrator._open_pr_for_branch()` pattern). Then delete the epic branch.
   Update `orchestrator._open_pr_for_branch()` for epic-child PRs to use
   `--base epic/<id>` instead of `--base base_branch`.
6. **Orchestrator and sprint-runner epic-branch awareness** — Update
   `orchestrator._inspect_worktree()` rev-list (`:400`) to compare against the
   epic branch; update `cli/sprint/run.py:~578` base-branch detection to carry
   epic context into `create_parallel_config()`.
7. **TUI surface** (`init/tui.py:343,378,664`) — follow the
   `use_feature_branches` pattern: variable declaration (line ~360), questionary
   confirm prompt inside `if "parallel" in selected_set:` block (~line 393),
   pass to `_build_final_config()` (~line 628), and write only when truthy
   (~line 681).
8. **Tests** — Follow patterns from `test_worker_pool.py:2191-2236` (branch-naming
   via `ParallelConfig(**{**default_parallel_config.to_dict(), "epic_branches": {...}})`)
   and `test_orchestrator.py:2008-2052` (feature-branch/PR mock pattern). Cover:
   per-EPIC fork/merge routing, standalone-issue regression (unchanged),
   completion-merge, PR-mode (child → epic branch, epic → base_branch).
   Round-trip serialization test in `test_parallel_types.py` (see lines 1017–1058).
9. **Docs** — Update `docs/ARCHITECTURE.md` parallel section and
   `docs/reference/API.md:little_loops.parallel.*`. Run `python -m pytest scripts/tests/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. **`BRConfig.to_dict()` serialization** (`config/core.py:555-574`) — add `epic_branches` sub-object to the explicit `parallel` key enumeration in `to_dict()`; omitting it causes `ll-issues decisions sync` / config round-trip to silently lose the setting
11. **CLI flag: `cli/parallel.py`** — add `--epic-branches` argument in `main_parallel()` alongside `--feature-branches` (line 137); pass as `epic_branches=args.epic_branches` in the `create_parallel_config()` call at line 269
12. **CLI flag: `cli/sprint/__init__.py`** — add `--epic-branches` `add_argument()` call at line 142 beside `--feature-branches`; thread into `_cmd_sprint_run()` at line 588 via `create_parallel_config(epic_branches=...)`
13. **Configure skill updates** — update `skills/configure/areas.md` (add `epic_branches.enabled` display + Round 3 confirm block after the `use_feature_branches` round), `skills/configure/show-output.md` (add `epic_branches.*` display lines), and `skills/configure/SKILL.md` (update "parallel area" description to mention epic branches)
14. **Update `test_parallel_types.py:test_roundtrip_serialization`** — add `epic_branches=EpicBranchesConfig(enabled=True, ...)` to the constructor call and `assert restored.epic_branches == original.epic_branches` to the assertions
15. **Update `test_init_tui.py:_wire_q()`** — add `use_epic_branches: bool = False` parameter; insert positionally into `confirm_returns` immediately after `use_feature_branches` when `"parallel" in features`; update all call sites
16. **Add `test_config_schema.py` test** — `test_parallel_epic_branches_in_schema()` asserting `"epic_branches"` in `parallel["properties"]` with sub-properties `enabled` (bool, default False), `prefix` (string), `merge_to_base_on_complete` (bool), `open_pr` (bool)
17. **Add `test_config.py` epic_branches tests** — four counterparts to the `feature_branches` group (lines 907–949): explicit-True, explicit-False, None-falls-back-to-config-True, None-falls-back-to-config-False
18. **Add `test_merge_coordinator.py` merge-target tests** — verify that `MergeCoordinator` routes the merge target to the epic branch (not `base_branch`) when the issue has a parent EPIC and `epic_branches.enabled=True`
19. **Add `test_worker_pool.py:_update_branch_base` epic-mode variants** (lines 1714–1791) — assert rebase target is the epic branch when `epic_branches.enabled=True` and `issue.parent` is set
20. **Update docs** — `docs/reference/CONFIGURATION.md` (add `epic_branches.*` sub-keys table), `docs/reference/CLI.md` (add `--epic-branches` flag docs), `docs/guides/SPRINT_GUIDE.md` (add `epic_branches` precedence section after `use_feature_branches` prose)

_Second wiring pass (`/ll:wire-issue`, 2026-07-02):_

21. **No wiring change needed** for the second branch-prefix gate in `merge_coordinator.py:_cleanup_worktree()` (line 1088) — **Decided (2026-07-02):** epic-mode children keep their existing `feature/`/`parallel/` naming, so this gate (and `_is_ll_branch()`) already handles them correctly with no changes. See Decision Rationale (Remaining Open Questions).
22. **Update `worker_pool.py:prune_merged_feature_branches()` docstring** (line 1633) to note it intentionally excludes `epic/*` branches (explicit-deletion design, Implementation Step 5), so its `feature/*`-only scope doesn't read as a bug once epic branches exist
23. **Make the in-place/contention-subwave warning in `cli/sprint/run.py` epic-aware** (lines 485, 518–528) — this is a second, distinct site from the multi-issue `_base_branch` auto-detection already covered in step 6. **Decided (2026-07-02):** add an `effective_epic_branches` check (mirrors `effective_feature_branches`) and append to the existing warning message, preserving the `"feature-branch mode does not apply"` substring `TestFeatureBranchInPlaceWarning` asserts on.
24. **Export `EpicBranchesConfig` from `scripts/little_loops/parallel/__init__.py`** — add the import + `__all__` entry alongside `ParallelConfig`, mirroring how `ConfidenceGateConfig` is re-exported from `config/__init__.py`
25. **`templates/*.json` parity** — 9 project-type scaffolds (`typescript`, `java-gradle`, `java-maven`, `python-generic`, `dotnet`, `rust`, `javascript`, `generic`, `go`) each stamp `parallel.use_feature_branches: false`. **Decided (2026-07-02):** stamp `epic_branches: {"enabled": false}` explicitly in all 9, matching the existing convention.
26. **Add/update tests per the second-pass Tests section**: `test_to_dict_parallel_schema_aligned_keys` assertion, `TestParallelAutomationConfig` epic_branches counterpart, `test_process_issue_uses_feature_branch_name_when_enabled` explicit `issue.parent = None`, `test_on_worker_complete_feature_branch_open_pr` `--base` value assertion, `TestFeatureBranchInPlaceWarning` epic counterpart, `test_subprocess_mocks.py` epic-branch coverage, `TestSprintManagerLoadOrResolve` nested-EPIC test

## Use Case

A developer runs `ll-sprint EPIC-1389` to implement a 6-child EPIC. With
`epic_branches.enabled`, ll-parallel creates `epic/EPIC-1389-add-epic-type` off
`main`, processes the 6 children into worktrees that fork from and merge into the
epic branch, and on completion opens a single PR (or merges) `epic/EPIC-1389-…`
→ `main`. The reviewer sees one cohesive PR; `main` only ever gains the complete
EPIC, never a partial one.

## API/Interface

New config (additive, default-off, backward compatible):
`parallel.epic_branches.{enabled, prefix, merge_to_base_on_complete, open_pr}`
(placement decided as Option A — `parallel.epic_branches.*` — see Decision
Rationale under Proposed Solution). No breaking changes to existing
`parallel.*` keys.

## Acceptance Criteria

- [ ] With `epic_branches.enabled: false` (default), branching/merge behavior is
      byte-for-byte identical to today (regression-tested).
- [ ] With it enabled, children of an EPIC fork from and merge into a single
      `epic/<EPIC-ID>-<slug>` branch; standalone issues still use `base_branch`.
- [ ] The epic integration branch is created once (first child) and reused.
- [ ] On EPIC completion, the epic branch merges to `base_branch` (or one PR is
      opened) per config.
- [ ] Nested-EPIC behavior is explicitly defined and tested.
- [ ] Config is documented in `config-schema.json`, ARCHITECTURE, and surfaced in
      `ll-init`/`/ll:configure`.

## Edge Cases

- **Config placement**: `parallel.epic_branches.*` keeps it near other
  worktree/branch knobs; `epics.branch.*` groups it with EPIC lifecycle. Decide
  in design.
- **Nested EPICs**: epic-progress is non-recursive — define whether each EPIC
  level gets its own branch or grandchildren flatten to the nearest EPIC.
  _Update 2026-07-02: `compute_epic_progress()` now walks the `parent:` chain
  transitively (commit `4887c87c`), so EPIC-completion **detection** already
  aggregates grandchildren correctly. The branch-**routing** question (own
  branch per level vs. flatten to nearest) is unaffected and remains the only
  open nested-EPIC decision — see Proposed Solution → Codebase Research
  Findings for detail._
  > **Decided (2026-07-02):** Flatten to the nearest EPIC ancestor — one
  > integration branch per issue's nearest EPIC ancestor, not a chained
  > per-level branch hierarchy. See Decision Rationale below.
- **Interaction with `use_feature_branches`**: epic mode supersedes per-issue
  feature branches for EPIC children; document precedence.
- **Reduced intra-EPIC parallelism**: children sharing one branch serialize more
  and concentrate merge conflicts on the epic branch — acceptable trade for
  atomicity but should be noted.
- **Partial failure**: if some children fail, the epic branch holds partial work
  — define whether completion-merge is blocked until all children are `done`.
  > **Decided (2026-07-02):** Completion-merge is blocked until ALL children
  > reach `done`; a failed/blocked child holds the epic branch open rather
  > than triggering a partial merge. See Decision Rationale below.
- **`p0_sequential` / `base_branch` auto-detection** (BUG-2323) interplay.

### Codebase Research Findings (Third Pass, 2026-07-02)

_Added by `/ll:refine-issue` — concrete data resolving the "decide in design" open questions above:_

**Nested-EPIC routing — data available today:** `sprint.py:Sprint.load_or_resolve()`
(`:324-326`) resolves an EPIC-scoped sprint via a **union of two direct-only
lookups**: `forward_ids = set(epic_info.relates_to)` (only what's literally
listed on the top-level EPIC file) and `backward_ids = {info.issue_id for info
in all_active if info.parent == epic_id}` (one-hop only). A grandchild whose
`parent:` points at an intermediate sub-EPIC is invisible to the backward scan
unless it also appears in the top-level EPIC's `relates_to:` — i.e.
**`sprint.py`'s run-construction path silently drops nested grandchildren
today**, independent of the branch-routing question. Two transitive-walk
utilities already exist but answer different questions, neither of which is
"which immediate sub-EPIC does this grandchild nest under":
`issue_progress.py:_issue_descends_to()` returns a boolean ("does X eventually
chain up to target epic_id"), and `cli/issues/list_cmd.py:_find_epic_ancestor()`
returns the *nearest* EPIC ancestor (flattening intermediate levels). Neither is
exposed as a shared/importable helper. **There is no depth/level concept
anywhere in the codebase** — every existing EPIC traversal is either
direct-only (depth=1, `sprint.py`) or an unranked transitive walk
(`issue_progress.py`, `list_cmd.py`, and a third independent BFS in
`cli/issues/set_status.py:cmd_set_status()` `--cascade`, lines 86-97).
Implication: a new depth-aware helper is needed regardless of which
nested-EPIC policy (own-branch-per-level vs. flatten) is chosen — reuse the
`_issue_descends_to()` cycle-guard shape (`seen` set) rather than the
direct-only `sprint.py` lookup.

**Partial-failure merge policy — data available today:** Failure tracking is
per-issue and immediate, with **no existing EPIC-level aggregation** anywhere:
`WorkerResult` (`parallel/types.py`) carries `success`/`error`/`was_blocked`/
`interrupted` per issue; `MergeCoordinator` tracks `self._merged: list[str]` /
`self._failed: dict[str, str]` (`merge_coordinator.py:67`, exposed via
`merged_ids`/`failed_merges` properties); `IssuePriorityQueue` separately
tracks `failed_ids`/`completed_ids` (`priority_queue.py:186-194`);
`EpicProgress.by_status` (`issue_progress.py`) separately rolls up status
counts per EPIC via `_TERMINAL_STATUSES`/`_OPEN_STATUSES` frozensets. These
three trackers are not unified. The closest existing precedent for "gate a
downstream action on group failure" is `Orchestrator.run()`'s exit-code/cleanup
gate (`orchestrator.py:827-831`): `if not shutdown_requested and
self.queue.failed_count == 0: self._cleanup_state()` / `return 0 if
failed_count == 0 else 1` — a plain `== 0` count check. An
epic-completion-merge gate would need to cross-reference `state.failed_issues`
(or `queue.failed_ids`) against the EPIC's child-ID set (computed via the
depth-aware helper above), since no existing structure already scopes these
dicts by EPIC.

**Shared-branch concurrency precedent:** the closest existing "N workers write
into one shared target" pattern is `GitLock` (`parallel/git_lock.py`) — a
single process-wide `threading.RLock` serializing git calls onto the shared
repo index, with retry/backoff layered underneath for transient contention —
plus the fact that `MergeCoordinator` already processes queued merge requests
through one instance/one internal lock sequentially. The epic-branch merge
point should reuse this "one coordinator, one lock, sequential processing"
shape rather than introducing a new locking primitive.

**`merge_coordinator._cleanup_worktree()` (line ~1088) — exact end-to-end
behavior:** no-op if worktree path doesn't exist → `git worktree unlock`
(best-effort) → `git worktree remove --force` → `shutil.rmtree
(ignore_errors=True)` fallback → **branch deletion is gated by
`branch_name.startswith("parallel/")` only** — `feature/*`-named branches (the
naming scheme relevant once `epic_branches` is enabled) are never deleted by
this function today. Runs once per merged issue (from `_finalize_merge()`), no
epic-scoped/batch variant exists.

**Historical precedent for the branch-prefix-gate decision (BUG-2324):** this
codebase's actual history with new branch prefixes is "introduce it without
touching the cleanup gates → gates silently miss the new prefix → drift
discovered later → separate bug-fix issue unifies the gates." `ENH-665`
introduced `feature/` without touching any of the three deletion-guard gates
("the `parallel/` deletion guard already correctly preserves `feature/`
branches" — explicitly out of scope). A later drift (three independent gates
all hardcoding `parallel/`, none updated for the `ll-loop` `YYYYMMDD-HHMMSS-`
prefix) was fixed only in `BUG-2324`, which consolidated two of the four
current sites onto the shared `worktree_utils._is_ll_branch()` predicate.
`merge_coordinator._cleanup_worktree()`'s inline `startswith("parallel/")`
check and `worker_pool.prune_merged_feature_branches()`'s inline
`startswith("feature/")` check were **never migrated** and remain independent
today. Recommendation: FEAT-2339 should decide the `epic/*` cleanup policy for
**all four** sites in one implementation step rather than deferring any of
them, to avoid repeating the BUG-2324 drift-then-fix cycle.

**Template parity — exact locations (9/9 verified):** all nine files stamp the
identical two-line block `"parallel": { "use_feature_branches": false }`:
`templates/typescript.json:69-71`, `templates/python-generic.json:71-73`,
`templates/generic.json:39-41`, `templates/java-gradle.json:66-68`,
`templates/java-maven.json:64-66`, `templates/javascript.json:71-73`,
`templates/go.json:64-66`, `templates/rust.json:63-65`,
`templates/dotnet.json:67-69`.
> **Decided (2026-07-02):** Add an explicit `"epic_branches": {"enabled":
> false}` stamp to all 9 templates, matching the existing
> `use_feature_branches` convention. See Decision Rationale below.

**`cli/sprint/run.py` in-place warning — exact code (confirms no epic-branch
data reaches this path):**
```python
_fb_warning_emitted = False  # line 485, declared once before the wave loop
...
_current_branch = _detect_current_branch()  # git rev-parse --abbrev-ref HEAD, default "main"
_feature_branches_arg = getattr(args, "feature_branches", None)
effective_feature_branches = (
    _feature_branches_arg if _feature_branches_arg is not None
    else config.parallel.use_feature_branches
)
if effective_feature_branches and not _fb_warning_emitted:
    logger.warning(...)  # fires once per `ll-sprint run` invocation
    _fb_warning_emitted = True
```
Critically, `effective_feature_branches` is computed **only** to decide
whether to log the warning — it is never passed into
`process_issue_inplace()`, which always runs on whatever `_current_branch`
currently is. No worktree, feature branch, or epic branch is ever created on
this path. An epic-aware warning would need a new epic-membership check (via
the depth-aware helper above) at this call site, since none exists today.

### Decision Rationale — Remaining Open Questions (2026-07-02)

Decided directly against the codebase evidence in the Third Pass research
above (not run through `/ll:decide-issue`'s scoring pipeline — none of these
five questions were expressed as enumerable `### Option` alternatives, so
`decision_needed` never re-triggered even after two `/ll:refine-issue` and
`/ll:wire-issue` passes; see Confidence Check Notes below for how this
surfaced).

**1. Nested-EPIC branch routing — Flatten to nearest EPIC ancestor.**
Own-branch-per-level requires new multi-level merge-chain infrastructure
(sub-branch → parent-branch → base, cascading completion detection at each
level) that's out of scope for this FEAT's single epic-branch-to-base model
and declared "Medium effort." Flattening to the nearest EPIC ancestor keeps
exactly one integration branch per top-level unit of work, matches how
`compute_epic_progress()` already treats completion as a single-level
rollup, and reuses the existing traversal shape
(`_issue_descends_to()`'s cycle-guard) rather than inventing branch-chaining
semantics. True multi-level nested-EPIC branch chains are out of scope for
this FEAT; `sprint.py`'s separate grandchild-drop gap in run-construction is
a pre-existing, independent issue and doesn't block this decision.

**2. Partial-failure merge policy — Block until all children are `done`.**
The FEAT's own motivation is atomic delivery ("main never carries a
half-finished EPIC"); a partial-merge policy would directly contradict that
goal. This also reuses the one existing precedent for group-failure gating
in this codebase, `Orchestrator.run()`'s `failed_count == 0` all-or-nothing
cleanup gate, rather than inventing new partial-tolerance semantics. A
failed/blocked child holds the epic branch open (unmerged, undeleted); it
does not trigger a partial merge.

**3. Branch-prefix cleanup-gate ownership — No change to the three existing
gates.** Epic-mode children keep their existing `feature/`/`parallel/`
naming — only their fork point and merge target change in epic mode, not
their name — so `_is_ll_branch()`, `_cleanup_worktree()`'s `parallel/`
check, and `prune_merged_feature_branches()`'s `feature/` check already
handle them correctly with no wiring changes. The new `epic/*` prefix is
deliberately invisible to all three (none match `epic/`), and its lifecycle
is owned exclusively by this FEAT's own explicit `delete_epic_branch()` step
(Implementation Step 5), which runs only after a successful
completion-merge. This makes the exclusion explicit and intentional rather
than the accidental drift the BUG-2324 history warns about — the only
remaining work is the docstring update already scoped in Implementation
Step 22.

**4. In-place/contention-subwave warning — Extend the existing warning, don't
build a new one.** The in-place path never creates a worktree, so it
structurally cannot use an epic branch for exactly the same reason it can't
use a feature branch — same limitation, same cause. Add a parallel
`effective_epic_branches` check (identical shape to
`effective_feature_branches`) and append to the existing warning message
rather than replacing it, preserving the `"feature-branch mode does not
apply"` substring `test_cli_sprint.py:TestFeatureBranchInPlaceWarning`
already asserts on.

**5. `templates/*.json` parity — Stamp `epic_branches` explicitly in all 9
templates.** The repo's established convention already stamps
`use_feature_branches: false` explicitly even though it matches the schema
default; consistency says `epic_branches` should follow the same
convention rather than being the one `parallel.*` key left to silent
default-fallback, which would read as an oversight rather than a decision.

## Impact

- **Scope**: Concentrated in `parallel/` (worker_pool, merge_coordinator, types,
  orchestrator) + `sprint.py` + `config-schema.json` + init/configure surfaces +
  tests/docs. Medium effort.
- **Risk**: Touches merge ordering and EPIC-completion semantics; the design
  (config placement, nested EPICs, partial-failure policy) should be written
  before implementation.
- **Backward compatibility**: Additive and default-off; no behavior change unless
  explicitly enabled.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | System design — parallel/worktree orchestration model that this feature extends |
| `docs/reference/API.md` | Python module reference for `little_loops.parallel.*` (worker_pool, merge_coordinator, types) |
| `.claude/CLAUDE.md` | Issue/EPIC conventions and parent/relates_to relationship rules |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-02_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 45/100 → LOW

### Outcome Risk Factors
- **Broad enumeration across 30+ sites**: the Integration Map, Dependent Files, Documentation, Configuration, Additional Coupling, and templates sections together touch 30+ files across `parallel/` (worker_pool, merge_coordinator, types, orchestrator), `sprint.py`, `config-schema.json`, init/configure surfaces, 9 project-type templates, and 15+ test files — a wide blast radius even though most individual sites are mechanical (schema fields, doc rows, test assertions).
- **Cross-module state threading is the core remaining risk**: merge-target routing requires passing per-issue epic-branch metadata across the `WorkerPool` → `MergeCoordinator` boundary (a new `WorkResult` field or callback) — this subset of sites carries genuine shared-state risk that the now-resolved design decisions don't reduce.
- **Ambiguity substantially reduced since the prior check**: all 5 previously open decision points (nested-EPIC routing, partial-failure merge policy, branch-prefix cleanup-gate ownership, in-place warning epic-awareness, templates parity) are now resolved directly against codebase evidence in "Decision Rationale — Remaining Open Questions." The API/Interface section's stale "to be decided in design" cross-reference has been corrected to point at the Option A decision.

## Session Log
- `decision-lock (WorkerPool→MergeCoordinator shape)` - 2026-07-02T22:05:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/720b87af-c61f-409e-9d4d-6ce5a0eb1828.jsonl`
- `/ll:confidence-check` - 2026-07-02T22:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/720b87af-c61f-409e-9d4d-6ce5a0eb1828.jsonl`
- `/ll:confidence-check` - 2026-07-02T21:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c47d5ac-c6d5-40ca-b8ab-eaf74e22bf17.jsonl`
- `/ll:decide-issue` - 2026-07-02T21:29:52 - `6a6c3737-d0f8-415a-8e68-41f5eab7fb61.jsonl`
- `/ll:refine-issue` - 2026-07-02T21:20:48 - `e83a86e2-2433-4c62-8bd3-e89cf4de8930.jsonl`
- `/ll:decide-issue` - 2026-07-02T21:13:45 - `91ad88d1-e6df-4d81-8bd0-c684e4ae5b28.jsonl`
- `/ll:confidence-check` - 2026-07-02T21:15:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ccbae3b0-7e7e-4a10-b840-e0bd627af3c1.jsonl`
- `/ll:wire-issue` - 2026-07-02T21:03:47 - `e0b87abc-cc6a-457e-9cb8-b8e89dbde2b9.jsonl`
- `/ll:refine-issue` - 2026-07-02T20:51:26 - `18e3bf28-9c2a-4641-9381-6338d587afef.jsonl`
- `/ll:confidence-check` - 2026-07-02T20:39:46Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0b9128ff-bdbe-4dee-bc4f-63dc65e67034.jsonl`
- `/ll:wire-issue` - 2026-06-30T20:21:57 - `9c63a038-d9e2-4785-8e44-99ce3866d76c.jsonl`
- `/ll:decide-issue` - 2026-06-30T20:02:05 - `372cd0c6-2a98-4878-9b7c-5403c4ab9fe2.jsonl`
- `/ll:refine-issue` - 2026-06-30T19:22:50 - `59b419ef-8005-450b-883a-d993d7fe8714.jsonl`
- `/ll:format-issue` - 2026-06-27T02:52:25 - `7437556a-9bbe-47ca-9369-c97d741aff8f.jsonl`
- `/ll:capture-issue` - 2026-06-27T02:49:31Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c8ee06c-d91e-40b3-b5a3-a8f24925b3b7.jsonl`
- `/ll:issue-size-review` - 2026-07-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e2b9d4e-1bf7-4b43-940f-7c8cc95fcaf4.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-02
- **Reason**: Issue scored 11/11 (Very Large) on size review — ~5500 words, 26 implementation steps, 30+ files; exceeding single-session capacity.

### Decomposed Into
Parent EPIC: **EPIC-2451: Per-EPIC integration branch strategy**

- **FEAT-2447**: per-EPIC integration branch — config schema, dataclasses, resolver, and serialization
- **FEAT-2448**: per-EPIC integration branch — worker_pool + merge_coordinator wiring (blocked by FEAT-2447)
- **FEAT-2449**: per-EPIC integration branch — EPIC-completion merge + orchestrator/sprint awareness (blocked by FEAT-2448)
- **FEAT-2450**: per-EPIC integration branch — CLI flags, TUI surface, docs, templates parity (blocked by FEAT-2449)

Execution pattern: strictly sequential with shared scope (config → wiring → completion → polish).

---

## Status

- **Current**: open
- **Created**: 2026-06-27
