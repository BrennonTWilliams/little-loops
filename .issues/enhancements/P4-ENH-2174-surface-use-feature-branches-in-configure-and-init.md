---
id: ENH-2174
title: Surface use_feature_branches in /ll:configure and init templates
type: ENH
status: done
priority: P4
parent: EPIC-2171
captured_at: '2026-06-15T16:51:50Z'
completed_at: '2026-06-16T19:44:48Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels:
- parallel
- configure
- init
- feature-branches
- dx
- discoverability
depends_on:
- ENH-2176
relates_to:
- ENH-2175
confidence_score: 99
outcome_confidence: 81
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 20
---

# ENH-2174: Surface use_feature_branches in /ll:configure and init templates

## Summary

`parallel.use_feature_branches` switches `ll-parallel` (and `ll-sprint`) to a branch-per-issue / PR-based workflow, but it is invisible everywhere a user would discover it — not in `/ll:configure`, `ll-init`, or any config template. This enhancement adds the flag to those discovery surfaces so users can find and enable it without hand-editing JSON.

## Motivation

`parallel.use_feature_branches` is defined in the config schema and honored by
the runtime, but it is invisible everywhere a user would actually discover it:
it does not appear in `/ll:configure`, in `ll-init`, or in the config
`templates/`. The only way to enable it is to know it exists and hand-edit
`.ll/ll-config.json`. For a flag whose whole purpose is to change the default
development workflow (branch-per-issue / PR-based), discoverability matters.

## Current Behavior

- `grep -rln "use_feature_branches" templates/ scripts/little_loops/cli/init* /ll:configure`
  → no matches in templates, init, or the configure surface.
- A user reading `/ll:configure` output has no way to learn the flag exists.

## Expected Behavior

- `/ll:configure` lists `use_feature_branches` under parallel settings with an accurate one-line description and lets the user toggle it.
- Config templates include a documented (commented or `false`-defaulted) `use_feature_branches` entry in the parallel block.
- `ll-init` optionally prompts for the flag when the user indicates a PR-based / CI workflow.
- All description text reflects actual implemented behavior (coordinated with BUG-2172 outcome).

## Proposed Solution

1. Add `use_feature_branches` (and, once BUG-2172 lands, any push/PR sub-flags)
   to the `parallel` section presented by `/ll:configure`, with a one-line
   description of the PR-based workflow it enables.
2. Surface it in the parallel block of the relevant config `templates/` (commented
   default `false`) so generated configs document its existence.
3. Optionally prompt for it during `ll-init` when the user opts into a
   PR-based / CI workflow.

## Acceptance Criteria

1. `/ll:configure` lists `use_feature_branches` under parallel settings with an
   accurate description and lets the user toggle it.
2. Config templates include a documented (commented or default-false) entry.
3. Description text matches actual behavior (kept in sync with BUG-2172 outcome —
   do not advertise push/PR unless implemented).
4. The toggle's description states its **coverage boundary**: feature-branch mode
   applies to parallel (multi-issue) waves; it does not apply to `ll-auto`
   (sequential, in-place) and — pending ENH-2176 — single-issue / contention
   sub-waves in `ll-sprint`. Users should not be surprised that the flag no-ops
   for some paths.

## Scope Boundaries

- **In scope**: Adding `use_feature_branches` to `/ll:configure` parallel settings display; adding a documented entry in config templates; optional `ll-init` prompt under a PR-workflow opt-in.
- **Out of scope**: Implementing push/PR behavior itself (owned by BUG-2172 and ENH-2173); changing the flag's default value; adding new sub-flags beyond `use_feature_branches`.

## Integration Map

### Files to Modify

**Configure skill:**
- `skills/configure/areas.md` (`## Area: parallel`) — extend the **Current Values** display block to show `use_feature_branches`, `push_feature_branches`, `open_pr_for_feature_branches`; add a **Round 2** question block with a `use_feature_branches` toggle following the `Stream` question pattern (header / question / `{{current …}} (keep)` / `true` / `false`, `multiSelect: false`)
- `skills/configure/show-output.md` (`## parallel --show`) — add four new rows after `worktree_copy_files`: `use_feature_branches`, `push_feature_branches`, `open_pr_for_feature_branches`, `base_branch`, each following the `  key_name: {{config.parallel.key_name}}  (default: VALUE)` format
- `skills/configure/SKILL.md` — update the `parallel` area description string from `"ll-parallel: workers, timeouts, worktree files"` to include feature branches in both the `## Mode: --list` table row and the area-picker `description` field

**Init TUI:**
- `scripts/little_loops/init/tui.py` — in `run_tui()` under `if "parallel" in selected_set:` (around line 224), add a `questionary.confirm("Enable feature-branch mode (branch-per-issue)?", default=False)` prompt; propagate the result through `_build_final_config()` (around line 465) to write `"use_feature_branches": True` to the `parallel` section when selected

**Config templates:**
- All `templates/*.json` files (`generic.json`, `python-generic.json`, `typescript.json`, `javascript.json`, `go.json`, `rust.json`, `java-maven.json`, `java-gradle.json`, `dotnet.json`) — no `parallel` block exists in any template; add a `"parallel": {"use_feature_branches": false}` entry so generated configs document the flag

### Dependent Files (Read-Only / No Change Required)
- `scripts/little_loops/config/automation.py` (`ParallelAutomationConfig.from_dict()`) — already deserializes `use_feature_branches`, `push_feature_branches`, `open_pr_for_feature_branches`, `base_branch`, `remote_name`; no change needed
- `scripts/little_loops/config/core.py` (`BRConfig.to_dict()`, lines 550–568) — already exports all feature-branch keys; `{{config.parallel.use_feature_branches}}` resolves correctly in skill templates

### Optional: Explicit-Default in Init Core
- `scripts/little_loops/init/core.py` (`build_config()`, lines 96–103) — consider writing `"use_feature_branches": false` into an explicit `parallel` block in `build_config()`, following the `loops.run_defaults` precedent (ENH-2113) that writes explicit defaults so the key is discoverable in generated configs even without TUI interaction

### Similar Patterns to Follow
- `skills/configure/areas.md` — `Stream` question (lines 240–250): exact template for the `use_feature_branches` boolean toggle (header `"Feature branches"`, `(keep)`, `true`, `false` options)
- `scripts/little_loops/init/tui.py` — `questionary.confirm("Add custom exclude patterns?", default=False)` at line 193: pattern for optional boolean prompts in the TUI
- `scripts/little_loops/init/core.py` `build_config()` lines 96–103: `loops.run_defaults` explicit-defaults precedent for always exposing a feature key in generated config

### Tests
- `scripts/tests/test_wiring_init_and_configure.py` — doc-wiring tests for init and configure; assert `use_feature_branches` appears in the configure parallel area output
- `scripts/tests/test_init_tui.py` — add test for the new feature-branch TUI prompt path
- `scripts/tests/test_init_core.py` — cover `build_config()` if the explicit-default parallel block is added

### Dependencies
- Coordinate description text with **BUG-2172**: only describe push/PR behavior
  if that issue implements it; otherwise describe local-branch retention.
- The coverage-boundary prose (feature-branch mode applies to parallel waves, not `ll-auto` or single-issue sprint sub-waves) should reference or quote the `docs/guides/SPRINT_GUIDE.md` paragraph finalized by **ENH-2176** rather than authoring independent text (per the `/ll:audit-issue-conflicts` note).

## Implementation Steps

1. **Configure skill — `--show` output** (`skills/configure/show-output.md`, `## parallel --show`): Add four rows after `worktree_copy_files`: `use_feature_branches (default: false)`, `push_feature_branches (default: false)`, `open_pr_for_feature_branches (default: false)`, `base_branch (default: main)`.

2. **Configure skill — interactive area** (`skills/configure/areas.md`, `## Area: parallel`): Add `use_feature_branches`, `push_feature_branches`, `open_pr_for_feature_branches` to the Current Values block; add a Round 2 question block following the `Stream` pattern (lines 240–250) — note the coverage-boundary caveat in the `false` option description (applies to parallel waves only; see ENH-2176/SPRINT_GUIDE.md for scope language).

3. **Configure skill — area description** (`skills/configure/SKILL.md`): Update the `parallel` description string in `## Mode: --list` and the area-picker entries from `"ll-parallel: workers, timeouts, worktree files"` to also mention feature branches.

4. **Init TUI** (`scripts/little_loops/init/tui.py`, `run_tui()` around line 224): Under `if "parallel" in selected_set:`, add `questionary.confirm("Enable feature-branch mode (branch-per-issue)?", default=False)` and propagate the result through `_build_final_config()` (around line 465) to emit `"use_feature_branches": True` in the `parallel` section when selected.

5. **Config templates** (`templates/*.json` — all 9 files): Add `"parallel": {"use_feature_branches": false}` to each template. This follows the `product: {enabled: false}` / `context_monitor: {enabled: true}` pattern of writing explicit-default keys for discoverability.

6. **Coordinate with BUG-2172**: Read BUG-2172's outcome before writing description text — only mention push/PR behavior if implemented; otherwise restrict to "creates and retains a local `feature/<id>-<slug>` branch, skipping auto-merge." Pull coverage-boundary wording from `docs/guides/SPRINT_GUIDE.md` (finalized by ENH-2176) rather than writing new prose.

7. **Verify**: Run `/ll:configure parallel` to confirm `use_feature_branches` appears; run `ll-init --yes` to confirm a generated config exposes the key; run `python -m pytest scripts/tests/test_wiring_init_and_configure.py scripts/tests/test_init_tui.py -v`.

## Impact

- **Priority**: P4 — discoverability/polish; no functional gap once ENH-2173 and
  BUG-2172 land, but completes the "expose it" capstone of the EPIC.
- **Effort**: Small.
- **Risk**: Low.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-15 | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-06-16T19:27:05 - `2d0784ea-20ea-4342-b7d5-61cd71315525.jsonl`
- `/ll:confidence-check` - 2026-06-16T20:00:00Z - `8bb197a1-c4a2-4bce-985e-788fa46c1c85.jsonl`
- `/ll:refine-issue` - 2026-06-16T19:20:16 - `308688f6-076c-43c9-af14-37a7a9f88806.jsonl`
- `/ll:confidence-check` - 2026-06-16T00:00:00Z - `3132e209-9d0e-4a66-ae96-3bb5ef8cc7d2.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-15T20:47:56 - `fc9e22f8-f75a-4ab7-a570-0b05a961077c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-15T20:33:23 - `708f5540-fdfd-4ca1-92bc-72a7cb548730.jsonl`
- `/ll:format-issue` - 2026-06-15T16:57:30 - `bbf7e27c-ea9f-4af6-b201-de02c8065217.jsonl`
- `/ll:capture-issue` - 2026-06-15T16:51:50Z - `5b1dd63b-714f-41e9-b9c2-f55f8ebd0e98.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): [ENH-2176] is the canonical source for the coverage-boundary prose explaining that `use_feature_branches` does not apply to single-issue / contention sub-waves. The toggle description this issue adds to `/ll:configure` and config templates should reference or quote ENH-2176's `docs/guides/SPRINT_GUIDE.md` coverage-boundary paragraph rather than authoring independent text. Sequence ENH-2174's description wording after ENH-2176's SPRINT_GUIDE paragraph is finalized to keep the two surfaces consistent.
