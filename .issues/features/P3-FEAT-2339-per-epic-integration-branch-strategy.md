---
id: FEAT-2339
title: Per-EPIC integration branch strategy for ll-parallel/ll-sprint
type: FEAT
priority: P3
status: open
captured_at: "2026-06-27T02:49:31Z"
discovered_date: 2026-06-27
discovered_by: capture-issue
labels: [parallel, sprint, epics, git, worktree]
relates_to: [ENH-665, BUG-2323, ENH-2176, FEAT-1737]
decision_needed: false
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

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `skills/configure/areas.md` — `## Area: parallel` lines 188–198 (Current Values display) and lines 255–268 (Round 2 question) show `use_feature_branches` but not `epic_branches`; needs `epic_branches.enabled` display line and a new Round 3 confirm block [Agent 2 finding]
- `skills/configure/show-output.md` — lines 50–53 display `use_feature_branches`, `push_feature_branches`, `open_pr_for_feature_branches`, `base_branch`; needs `epic_branches.{enabled, prefix, merge_to_base_on_complete, open_pr}` display lines [Agent 2 finding]
- `skills/configure/SKILL.md` — lines 103, 136, 235, and 380 each describe the `parallel` area as covering "feature branches"; should mention "epic branches" alongside [Agent 2 finding]

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
   `self.config.base_branch`. Requires `MergeCoordinator` to receive per-issue
   branch metadata (epic branch or base branch) — likely via a `WorkResult` field
   or a callback.
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
(exact placement — `parallel.*` vs new `epics.branch.*` — to be decided in
design; see Edge Cases). No breaking changes to existing `parallel.*` keys.

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
- **Interaction with `use_feature_branches`**: epic mode supersedes per-issue
  feature branches for EPIC children; document precedence.
- **Reduced intra-EPIC parallelism**: children sharing one branch serialize more
  and concentrate merge conflicts on the epic branch — acceptable trade for
  atomicity but should be noted.
- **Partial failure**: if some children fail, the epic branch holds partial work
  — define whether completion-merge is blocked until all children are `done`.
- **`p0_sequential` / `base_branch` auto-detection** (BUG-2323) interplay.

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

## Session Log
- `/ll:wire-issue` - 2026-06-30T20:21:57 - `9c63a038-d9e2-4785-8e44-99ce3866d76c.jsonl`
- `/ll:decide-issue` - 2026-06-30T20:02:05 - `372cd0c6-2a98-4878-9b7c-5403c4ab9fe2.jsonl`
- `/ll:refine-issue` - 2026-06-30T19:22:50 - `59b419ef-8005-450b-883a-d993d7fe8714.jsonl`
- `/ll:format-issue` - 2026-06-27T02:52:25 - `7437556a-9bbe-47ca-9369-c97d741aff8f.jsonl`
- `/ll:capture-issue` - 2026-06-27T02:49:31Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c8ee06c-d91e-40b3-b5a3-a8f24925b3b7.jsonl`

---

## Status

- **Current**: open
- **Created**: 2026-06-27
