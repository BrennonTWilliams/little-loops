---
id: FEAT-2450
title: per-EPIC integration branch — CLI flags, TUI surface, docs, templates parity
type: FEAT
priority: P3
status: open
captured_at: '2026-07-02T22:30:00Z'
discovered_date: 2026-07-02
discovered_by: issue-size-review
labels:
- parallel
- sprint
- epics
- cli
- tui
- docs
- templates
- configure
parent: EPIC-2451
relates_to:
- FEAT-2339
- EPIC-2451
- FEAT-2447
- FEAT-2448
- FEAT-2449
blocked_by:
- FEAT-2449
decision_needed: false
confidence_score: 95
outcome_confidence: 70
score_complexity: 4
score_test_coverage: 18
score_ambiguity: 3
score_change_surface: 0
---

# FEAT-2450: per-EPIC integration branch — CLI flags, TUI surface, docs, templates parity

## Summary

Fourth and final child decomposed from FEAT-2339. This child handles
the **user-facing surface** of the per-EPIC integration branch
feature: CLI flags, the `ll-init` TUI, `/ll:configure` skill
displays, all documentation, the 9 project-type templates, and the
`prune_merged_feature_branches()` docstring update. All
implementation and most tests land in FEAT-2447 / FEAT-2448 /
FEAT-2449; this child is the integration polish that makes the
feature discoverable and consistent across the rest of the codebase.

Depends on FEAT-2449 (completion merge + cross-module awareness).

## Parent Issue

Decomposed from FEAT-2339: Per-EPIC integration branch strategy for
ll-parallel/ll-sprint.

## Scope

1. **`--epic-branches` CLI flag (ll-parallel)**
   (`scripts/little_loops/cli/parallel.py`) — add `add_argument()`
   at line ~137 alongside `--feature-branches`. Pass as
   `epic_branches=args.epic_branches` in the
   `create_parallel_config()` call at line 269 (mirror the
   `--feature-branches` pattern at lines 248–269).
2. **`--epic-branches` CLI flag (ll-sprint)**
   (`scripts/little_loops/cli/sprint/__init__.py`) — add
   `add_argument()` at line 142 beside `--feature-branches`.
   Thread into `_cmd_sprint_run()` at line 588 via
   `create_parallel_config(epic_branches=...)`.
3. **TUI surface (`scripts/little_loops/init/tui.py:343,378,664`)** —
   follow the `use_feature_branches` pattern:
   - variable declaration (line ~360)
   - questionary confirm prompt inside the
     `if "parallel" in selected_set:` block (~line 393)
   - pass to `_build_final_config()` (~line 628)
   - write only when truthy (~line 681)
4. **Configure skill updates** —
   - `skills/configure/areas.md` — add `epic_branches.enabled`
     display line in `## Area: parallel` (after the existing
     `use_feature_branches` row at lines 188–198) and a new Round 3
     confirm block (after the `use_feature_branches` round at
     lines 255–268).
   - `skills/configure/show-output.md` — add display lines for
     `epic_branches.{enabled, prefix, merge_to_base_on_complete,
     open_pr}` after the existing `use_feature_branches` /
     `push_feature_branches` / `open_pr_for_feature_branches` /
     `base_branch` rows at lines 50–53.
   - `skills/configure/SKILL.md` — update the "parallel area"
     description (lines 103, 136, 235, 380) to mention "epic
     branches" alongside "feature branches".
5. **`prune_merged_feature_branches()` docstring update**
   (`scripts/little_loops/parallel/worker_pool.py:1633`) — note it
   intentionally excludes `epic/*` branches (explicit-deletion
   design in FEAT-2449's completion-merge step), so its
   `feature/*`-only scope doesn't read as a bug once epic
   branches exist. No behavior change (Decision Rationale #3 in
   FEAT-2339).
6. **9 templates parity** — stamp
   `"epic_branches": {"enabled": false}` explicitly in all 9
   project-type templates, matching the existing
   `use_feature_branches: false` convention (Decision Rationale #5
   in FEAT-2339):
   - `scripts/little_loops/templates/typescript.json` (lines 69–71)
   - `scripts/little_loops/templates/python-generic.json` (lines 71–73)
   - `scripts/little_loops/templates/generic.json` (lines 39–41)
   - `scripts/little_loops/templates/java-gradle.json` (lines 66–68)
   - `scripts/little_loops/templates/java-maven.json` (lines 64–66)
   - `scripts/little_loops/templates/javascript.json` (lines 71–73)
   - `scripts/little_loops/templates/go.json` (lines 64–66)
   - `scripts/little_loops/templates/rust.json` (lines 63–65)
   - `scripts/little_loops/templates/dotnet.json` (lines 67–69)
7. **Documentation** —
   - `docs/reference/CONFIGURATION.md` — add
     `epic_branches.{enabled, prefix, merge_to_base_on_complete,
     open_pr}` sub-keys table in the `### parallel` section
     (after lines 340–357, beside the existing `use_feature_branches`
     row).
   - `docs/reference/CLI.md` — add `--epic-branches` flag
     documentation after the `--feature-branches` lines at 351
     (ll-parallel) and 418 (ll-sprint).
   - `docs/guides/SPRINT_GUIDE.md` — add an `epic_branches`
     precedence section after the `use_feature_branches` prose at
     lines 263–307, covering precedence rules and the EPIC-child
     override semantics.
   - `docs/ARCHITECTURE.md` — update the parallel section to
     mention per-EPIC integration branches.
   - `docs/reference/API.md` — update the
     `little_loops.parallel.*` module reference (worker_pool,
     merge_coordinator, types).
8. **Tests** —
   - `scripts/tests/test_init_tui.py:_wire_q()` (line 50,
     `confirm_returns` lines 121–123) — insert `use_epic_branches:
     bool = False` parameter; insert positionally into
     `confirm_returns` immediately after `use_feature_branches`
     when `"parallel" in features`; update all call sites (the
     positional list will misalign all existing call sites that
     include `"parallel" in features`).
   - `scripts/tests/test_parallel_cli.py` — add an end-to-end
     test for `--epic-branches` flag following the existing
     `TestParallelNormalRun` pattern.
   - `scripts/tests/test_sprint.py` — add
     `test_wave_parallel_config_passes_epic_branches` counterpart
     to `test_wave_parallel_config_passes_clean_start` (line 2274)
     for `epic_branches` kwarg propagation through sprint's wave
     parallel-config build.
   - `scripts/tests/test_wiring_init_and_configure.py:DOC_STRINGS_PRESENT`
     (lines 174–176) — add new rows for `epic_branches` after
     skill files are updated.

## Out of Scope

None — this is the final child. Once this lands, FEAT-2339 is fully
implemented end-to-end.

## Acceptance Criteria

- [ ] `ll-parallel --epic-branches` and `ll-sprint --epic-branches`
      work end-to-end.
- [ ] `ll-init` TUI prompts for `epic_branches.enabled` when the
      `parallel` feature is selected.
- [ ] `/ll:configure` displays the new config keys; Round 3
      confirm block updates the setting.
- [ ] `prune_merged_feature_branches()` docstring states its
      `feature/*`-only scope is intentional.
- [ ] All 9 templates stamp `"epic_branches": {"enabled": false}`.
- [ ] Docs updated: CONFIGURATION.md, CLI.md, SPRINT_GUIDE.md,
      ARCHITECTURE.md, API.md.
- [ ] All TUI/CLI/template/doc tests pass; full
      `python -m pytest scripts/tests/` exits 0.

## Files Touched

**Implementation:**
- `scripts/little_loops/cli/parallel.py`
- `scripts/little_loops/cli/sprint/__init__.py`
- `scripts/little_loops/init/tui.py`
- `scripts/little_loops/parallel/worker_pool.py` (docstring only)
- 9 templates (`scripts/little_loops/templates/*.json`)
- `skills/configure/areas.md`
- `skills/configure/show-output.md`
- `skills/configure/SKILL.md`
- `docs/reference/CONFIGURATION.md`
- `docs/reference/CLI.md`
- `docs/guides/SPRINT_GUIDE.md`
- `docs/ARCHITECTURE.md`
- `docs/reference/API.md`

**Tests:**
- `scripts/tests/test_init_tui.py`
- `scripts/tests/test_parallel_cli.py`
- `scripts/tests/test_sprint.py`
- `scripts/tests/test_wiring_init_and_configure.py`

**Estimated file count:** 17 implementation + 4 test = **21 files**.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis of `use_feature_branches` surface patterns and verification of sibling-issue status._

### Sibling-Issue Merge Status (Verified 2026-07-06)

All sibling/parent issues remain `status: open`: **FEAT-2447**, **FEAT-2448**,
**FEAT-2449**, **EPIC-2451**, **FEAT-2339**. A grep for
`epic_branches` / `epic-branches` / `use_epic_branches` / `EpicBranchesConfig`
across `scripts/`, `skills/`, `docs/`, `config-schema.json`, and `*.json`
templates returns **zero hits**. The integration surface FEAT-2450 depends on
does not yet exist:

- `EpicBranchesConfig` dataclass — not yet defined (FEAT-2447 scope)
- `ParallelConfig.epic_branches` field — not yet defined (FEAT-2447 scope)
- `BRConfig.create_parallel_config(epic_branches=...)` kwarg — not yet accepted
  (FEAT-2447 scope; current signature ends at
  `scripts/little_loops/config/core.py:507` with `use_feature_branches` kwarg)
- `WorkerPool._resolve_branch_targets()` resolver — not yet defined
  (FEAT-2447 scope)
- `WorkerResult.epic_branch` field — not yet threaded (FEAT-2448 scope)
- Sprint in-place warning extension for epic-mode — not yet implemented
  (FEAT-2449 scope; current `_cmd_sprint_run` warns only for feature branches at
  `scripts/little_loops/cli/sprint/run.py:518-528`)

**Implication for FEAT-2450 implementation order**: When FEAT-2450 begins, the
parallel-config plumbing does not exist, so acceptance tests cannot pass
against `main` until FEAT-2447 merges. Recommended sequencing: implement
**after FEAT-2449 merges** (which already implies FEAT-2447/2448 are landed as
prerequisites). The work remains self-contained — every file/line FEAT-2450
touches is documented in the existing Scope — but the runner cannot validate
end-to-end until the dependency chain unblocks.

### Stale Anchor Corrections (verified against current file state)

| Issue Reference | Verified Location | Notes |
|-----------------|-------------------|-------|
| `cli/sprint/__init__.py:588` (sprint thread-through) | `cli/sprint/run.py:518-528` (warning) and `cli/sprint/run.py:585-594` (kwarg) | `_cmd_sprint_run` lives in `cli/sprint/run.py`; `__init__.py` is only 256 lines and stops at the parser declaration. |
| `cli/parallel.py:269` (create_parallel_config end) | `cli/parallel.py:265` | Off by 4 lines; the call ends at 265. |
| `init/tui.py:360` (variable declaration) | `init/tui.py:365` | Off by 5 lines. |
| `init/tui.py:393` (questionary confirm) | `init/tui.py:398-404` | Off by 5-11 lines. |
| `init/tui.py:628` (pass to builder) | `init/tui.py:633` | Off by 5 lines. |
| `init/tui.py:681` (truthy-write) | `init/tui.py:686-687` | Off by 5-6 lines. |
| `docs/reference/CLI.md:351` (ll-parallel) | `docs/reference/CLI.md:357` | Off by 6 lines. |
| `docs/reference/CLI.md:418` (ll-sprint) | `docs/reference/CLI.md:424` | Off by 6 lines. |
| `docs/guides/SPRINT_GUIDE.md:263-307` | `docs/guides/SPRINT_GUIDE.md:263-291` | Closing boundary is 291, not 307. Insert epic section after line 291, before the `### Cleaning up merged feature branches` section. |
| `scripts/tests/test_init_tui.py:121-123` (`confirm_returns` build) | `scripts/tests/test_init_tui.py:121-124` | Positional list extends one line further. |
| `docs/reference/CONFIGURATION.md:340-357` | `docs/reference/CONFIGURATION.md:338-361` | Table boundary is 338-361; `use_feature_branches` row at line 357. |

Anchors that verified **accurate**: `cli/parallel.py:137`, `cli/sprint/__init__.py:142-147`, `parallel/worker_pool.py:1633`, all 9 template lines, `skills/configure/areas.md:188-198` & `255-269`, `skills/configure/show-output.md:50-53`, `skills/configure/SKILL.md:103, 136, 235, 380`, `scripts/tests/test_sprint.py:2274`, `scripts/tests/test_wiring_init_and_configure.py:174-176`.

### Configure-Skill Round-Numbering Correction

The existing `skills/configure/areas.md` calls the `use_feature_branches` block
**"Round 2 (1 question)"** at lines 255-269 — not "Round 3" as the issue spec
implies. The new `epic_branches` block (Scope item 4) will therefore be
**Round 3** when inserted after line 269, following the same
`header / question / options / multiSelect: false` shape with
`{{current epic_branches.enabled}} (keep)` as the keep-option label.

### Sprint `_cmd_sprint_run` Thread-Through

The full sprint path for `--feature-branches` (and the to-be-added
`--epic-branches`) is:

1. `cli/sprint/__init__.py:142-147` — `add_argument()` declaration (correct in issue)
2. `cli/sprint/run.py:518-528` — in-place warning logic (uses
   `effective_feature_branches`, emits one-time warning when feature branches
   are enabled but wave runs in-place)
3. `cli/sprint/run.py:585-594` — `create_parallel_config()` kwarg with
   `use_feature_branches=getattr(args, "feature_branches", None)`

For FEAT-2450:

- Add `--epic-branches` to `cli/sprint/__init__.py:142-147` block (mirror
  pattern at lines 142-147)
- Add `epic_branches=getattr(args, "epic_branches", None)` to the
  `create_parallel_config()` call at `cli/sprint/run.py:585-594` (mirror the
  `use_feature_branches` kwarg placement)
- The in-place warning extension (`effective_epic_branches`) is owned by
  **FEAT-2449**, not FEAT-2450 — do not duplicate. FEAT-2450 only consumes the
  kwarg; FEAT-2449 emits the warning when the epic path runs in-place.

### Test Positional-List Mechanics (`test_init_tui.py`)

`_wire_q()` at `scripts/tests/test_init_tui.py:50-125` builds a positional
`confirm_returns` list inside `if "parallel" in features:`:

```python
confirm_returns = [install_confirmed, add_excludes]
if "parallel" in features:
    confirm_returns.append(use_feature_branches)  # position N
confirm_returns.extend([session_digest, prompt_optimization, loop_clear_default, confirmed])
```

Inserting `epic_branches` requires **inserting it positionally immediately
after `use_feature_branches`** in the same `if "parallel" in features:` block.
The existing `test_feature_branches_enabled_written_to_config` at lines 315-337
provides the assertion pattern (`config.get("parallel", {}).get("use_feature_branches") is True`)
— mirror for `epic_branches` checks
`config.get("parallel", {}).get("epic_branches", {}).get("enabled") is True`.
**All test call sites that include `"parallel" in features` must be updated** to
pass the new positional `use_epic_branches` argument.

### Pattern: TUI Nested-Dict Write

`_build_final_config()` at `scripts/little_loops/init/tui.py:620` writes
`epic_branches` as a **nested dict** (matching `EpicBranchesConfig` shape), not
a flat scalar. The existing write-when-truthy block at lines 686-687:

```python
if use_feature_branches:
    parallel_section["use_feature_branches"] = True
```

mirrors as:

```python
if use_epic_branches:
    parallel_section["epic_branches"] = {"enabled": True}
```

The questionary default reads from the existing config's nested shape:
`default=_ex_parallel.get("epic_branches", {}).get("enabled", False)`.

### Pattern: `--epic-branches` argparse shape

Use `BooleanOptionalAction` to produce both `--epic-branches` and
`--no-epic-branches`, with `default=None` to distinguish explicit-override
from fall-back-to-config (mirror `cli/parallel.py:136-141`).

### Pattern: Sprint Wave Test (`test_wave_parallel_config_passes_epic_branches`)

Mirror `test_wave_parallel_config_passes_clean_start` at
`scripts/tests/test_sprint.py:2274-2325`. The `argparse.Namespace` test pattern
avoids full argparse parsing; the `capturing_create` wrapper captures kwargs.
Assert: `assert captured_kwargs.get("epic_branches") is not None` (or
`epic_branches is True` per FEAT-2447's eventual kwarg shape).

### Pattern: `--epic-branches` Parallel-CLI End-to-End Test

Mirror `test_configured_base_branch_overrides_detection` at
`scripts/tests/test_parallel_cli.py:256-289`. Patch `ParallelOrchestrator`,
retrieve `mock_cls.call_args.kwargs["parallel_config"]`, assert
`parallel_config.epic_branches.enabled is True` after passing
`["ll-parallel", "--epic-branches", "--config", str(temp_project)]` via
`sys.argv`.

### Pattern: `DOC_STRINGS_PRESENT` Wiring Test

Add three rows to `scripts/tests/test_wiring_init_and_configure.py:174-176`
after the existing `use_feature_branches` / "feature branches" rows:

```python
("skills/configure/show-output.md", "epic_branches", "FEAT-2450"),
("skills/configure/areas.md", "epic_branches", "FEAT-2450"),
("skills/configure/SKILL.md", "epic branches", "FEAT-2450"),
```

### Template JSON Shape (9 templates)

Mirror the existing flat-bool pattern at lines 39-41 of `generic.json` (and
equivalents in the other 8 templates). Insert as a nested object after the
`use_feature_branches` line:

```json
  "parallel": {
    "use_feature_branches": false,
    "epic_branches": {
      "enabled": false
    }
  },
```

Defaults for `prefix` / `merge_to_base_on_complete` / `open_pr` come from the
`EpicBranchesConfig` dataclass defaults — no need to stamp them explicitly.

### Note on `prune_merged_feature_branches()` Docstring

`scripts/little_loops/parallel/worker_pool.py:1633` already filters branches via
`if not branch.startswith("feature/"): continue` at line 1681 — so
`epic/*` branches are **already excluded** by prefix mismatch, no behavior
change is needed. The FEAT-2450 docstring update (Scope item 5) is purely a
clarification sentence stating that `feature/*`-only scope is intentional and
NOT a bug once `epic/*` branches exist.

## Wiring Pass Findings

_Added by `/ll:wire-issue` (Phase 8) on 2026-07-06. Aggregates missing wiring
identified by the 3-agent wiring research pass (Caller Tracer, Side-Effect
Tracer, Test Gap Finder). Findings are split into gaps FEAT-2450 owns vs.
files explicitly preserved from sibling-issue scope._

### Critical Implementation Gap (missing from Files Touched)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/cli/sprint/run.py` — `create_parallel_config()` call
  at lines **585–594** includes
  `use_feature_branches=getattr(args, "feature_branches", None)` at line
  **593**. The `--epic-branches` kwarg must be threaded through here as
  `epic_branches=getattr(args, "epic_branches", None)` (mirror the existing
  pattern). **This file is NOT in the existing Files Touched list**; the
  Scope item 2 anchor at `cli/sprint/__init__.py:588` is incorrect —
  `_cmd_sprint_run` lives in `run.py`, and `__init__.py` only contains the
  argparse parser declaration (verified: `cli/sprint/__init__.py` is only
  256 lines and stops at the parser). The existing Codebase Research
  Finding (lines 256–277) already corrects this; the Scope text and Files
  Touched list should match.

### Documentation Gaps (missing from Files Touched)

_Wiring pass added by `/ll:wire-issue`:_

- `skills/configure/SKILL.md:103` — **doubled "feature branches" typo**:
  the parallel area description in the table currently reads
  `feature branches, feature branches` (verified). Replace one occurrence
  with `epic branches` so the row becomes
  `feature branches, epic branches`. This typo pre-exists Scope item 4c
  but the doubling should be resolved alongside the epic-branches update.
- `skills/configure/SKILL.md:136` — **same doubled typo** as line 103:
  `feature branches, feature branches` (verified). Same fix.
- `skills/configure/SKILL.md:380` — append `, epic branches` to the
  parallel area description in the configuration areas section
  (currently `feature branches`).
- `docs/reference/CONFIGURATION.md:53-69` — example JSON block has
  `use_feature_branches: false` at line **67** but no `epic_branches`
  parity (verified). Add `"epic_branches": {"enabled": false}` line for
  example parity with the field-table update at lines 338–361 already
  specified in Scope item 7a.
- `docs/guides/SPRINT_GUIDE.md:263, 273` — the inline backticked
  `use_feature_branches: true` examples at lines 263 and 273 need a
  one-line aside about epic branches. Partially covered by Scope item 7c
  (the section between 263–291); confirm line 273 is included when the
  epic-branches precedence section is added.

### Test Gaps (optional new tests, recommended)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_init_core.py` — add new `TestTemplateEpicBranchesShape`
  class after `TestTemplateCommandOptions` (line 2551), parametrized over
  all 9 templates
  (`generic.json + python-generic.json + typescript.json + javascript.json +
   go.json + rust.json + java-maven.json + java-gradle.json + dotnet.json`),
  asserting `"epic_branches" in data["parallel"]` and
  `data["parallel"]["epic_branches"]["enabled"] is False`. **No existing
  test currently asserts on the `parallel.epic_branches` shape in the
  templates** — this closes the gap exposed by the 9 template stamps in
  Scope item 6. Pattern: mirror the `TYPED_TEMPLATES` list at lines
  2525–2534 and the `test_generic_has_no_command_options` exception at
  line 2549.

### Boundary Preservation (Files NOT to modify)

_Wiring pass added by `/ll:wire-issue`:_

The following files contain `use_feature_branches` / `feature_branches`
references but are explicitly **out of scope** for FEAT-2450 (owned by
sibling issues FEAT-2447/2448/2449 or by `prune_merged_feature_branches()`'s
intentional design). FEAT-2450 must NOT modify these:

- `scripts/little_loops/cli/parallel.py:196, 206` — cleanup /
  cleanup-orphans `create_parallel_config()` call sites (FEAT-2180: do
  NOT touch these paths).
- `scripts/little_loops/cli/sprint/run.py:518-528` —
  `effective_feature_branches` in-place warning logic (FEAT-2449 owns the
  `effective_epic_branches` extension; the
  `"feature-branch mode does not apply"` substring is preserved by
  `TestFeatureBranchInPlaceWarning` at `test_cli_sprint.py:732-879`).
- `scripts/little_loops/worktree_utils.py` — `_is_ll_branch()` at lines
  213-223, `cleanup_worktree()` at lines 161-201 (FEAT-2339 Decision
  Rationale #3 / ARCHITECTURE-094).
- `scripts/little_loops/parallel/merge_coordinator.py:1061-1093` —
  `MergeCoordinator._cleanup_worktree()` (correct behavior by accident;
  explicit-deletion design).
- `scripts/little_loops/parallel/orchestrator.py:972, 985, 1005` —
  runtime `parallel_config.use_feature_branches` /
  `push_feature_branches` / `open_pr_for_feature_branches` checks
  (FEAT-2448 owns the epic-mode mirrors).
- `scripts/little_loops/parallel/worker_pool.py:335, 362, 1681` —
  `_process_issue()` and `prune_merged_feature_branches()` `feature/*`
  prefix check (FEAT-2447/2448 owns the resolver; **only the docstring
  update at line 1633 is FEAT-2450**).
- `scripts/tests/test_merge_coordinator.py:2180-2208` —
  `TestMergeCoordinatorCleanupWorktree`.
- `scripts/tests/test_cli_sprint.py:732-879` —
  `TestFeatureBranchInPlaceWarning` (FEAT-2449 owns the epic-mode
  counterpart).
- `scripts/tests/test_config.py:770, 881-923` —
  `test_to_dict_parallel_schema_aligned_keys` and the four
  `test_create_parallel_config_feature_branches_*` tests (FEAT-2447
  surface; mirror tests when FEAT-2447 lands the kwarg).
- `scripts/tests/test_parallel_types.py:755, 1017-1059` —
  `TestParallelConfig` default-values and roundtrip tests (FEAT-2447
  surface).
- `scripts/tests/test_config_schema.py` — schema-level assertions
  (FEAT-2447 surface).
- `scripts/tests/test_orchestrator.py:1944-3055` and
  `scripts/tests/test_worker_pool.py:2193-2203, 2871-3047` — runtime
  tests setting `parallel_config.use_feature_branches` (FEAT-2447/2448
  surface; the `prune_merged_feature_branches` docstring update is
  doc-only so no test changes needed).
- `scripts/tests/conftest.py:284-295` — `make_project` /
  `sample_config` fixtures (FEAT-2447 may add `epic_branches` for
  round-trip tests).
- `commands/cleanup-worktrees.md`, `CONTRIBUTING.md`,
  `docs/development/TROUBLESHOOTING.md`, `thoughts/**/*.md`,
  `docs/reference/COMMANDS.md`, `docs/development/MERGE-COORDINATOR.md`
  — zero hits for `feature_branches` / `use_feature_branches` /
  `--feature-branches`; no updates needed.

### Wiring Phase Implementation Steps (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included
in the implementation alongside the existing Scope items 1–8:_

9. Update `scripts/little_loops/cli/sprint/run.py:585-594` — add
   `epic_branches=getattr(args, "epic_branches", None)` to the
   `create_parallel_config()` call (mirror the `use_feature_branches`
   pattern at line 593). **Also update Scope item 2 anchor** from
   `cli/sprint/__init__.py:588` to `cli/sprint/run.py:585-594`.
10. Fix doubled-typo at `skills/configure/SKILL.md:103` — change
    `feature branches, feature branches` to `feature branches, epic branches`.
11. Fix doubled-typo at `skills/configure/SKILL.md:136` — same fix as
    line 103.
12. Add `epic_branches: {enabled: false}` parity line at
    `docs/reference/CONFIGURATION.md:67` (in the example block at lines
    53-69).
13. (Optional, recommended) Add `TestTemplateEpicBranchesShape` class in
    `scripts/tests/test_init_core.py` parametrized over all 9 templates,
    asserting the `parallel.epic_branches` stamp exists.

### CHANGELOG.md note

Per `feedback_changelog_no_unreleased.md`, **do NOT** add a CHANGELOG
entry under `[Unreleased]` — defer to release-time. The release entry
should list FEAT-2447/2448/2449/2450 by ID alongside the multi-ENH
feature-branch entry style precedent at `CHANGELOG.md:374-376`.

### `config-schema.json` prerequisite (owned by FEAT-2447)

`config-schema.json:382-407` defines `use_feature_branches` /
`push_feature_branches` / `open_pr_for_feature_branches` / `base_branch`
/ `remote_name` under `parallel.properties`, with `"additionalProperties":
false` at line 407. **FEAT-2447 (not FEAT-2450) owns adding the
`epic_branches.*` schema block** before the `additionalProperties: false`
close. Without this prerequisite, the 9 template stamps (Scope item 6)
will fail JSON-Schema validation once FEAT-2447 enables strict mode.

## Session Log
- `/ll:wire-issue` - 2026-07-06T23:39:26 - `1dad1670-580d-493a-becb-164b981e5505.jsonl`
- `/ll:refine-issue` - 2026-07-06T19:28:39 - `2a131898-32dd-4a20-b05a-4c40cefc922b.jsonl`
- `/ll:issue-size-review` - 2026-07-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e2b9d4e-1bf7-4b43-940f-7c8cc95fcaf4.jsonl`
- `/ll:wire-issue` - 2026-07-06T21:00:00Z - `[auto-mode wiring pass]`