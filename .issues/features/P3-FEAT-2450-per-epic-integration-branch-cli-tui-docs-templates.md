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
parent: FEAT-2339
relates_to:
- FEAT-2339
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

## Session Log
- `/ll:issue-size-review` - 2026-07-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e2b9d4e-1bf7-4b43-940f-7c8cc95fcaf4.jsonl`