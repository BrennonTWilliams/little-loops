---
id: ENH-2240
title: ll-init should pre-populate the wizard from existing ll-config.json
type: ENH
priority: P4
status: open
captured_at: '2026-06-20T04:08:03Z'
discovered_date: '2026-06-20'
discovered_by: capture-issue
learning_tests_required:
- questionary
confidence_score: 97
outcome_confidence: 78
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 22
---

# ENH-2240: ll-init should pre-populate the wizard from existing ll-config.json

## Summary

When `ll-init` is run in a project that already has a `.ll/ll-config.json`, the
interactive wizard should seed every field with the existing config values rather
than falling back to project-type template defaults. This applies whether or not
`--force` is passed — any time a config already exists, existing values should be
the defaults.

## Current Behavior

- Without `--force`: exits immediately with an error, directing users to edit the
  config file directly.
- With `--force`: runs the wizard from scratch using template defaults, requiring
  users to re-enter every previously configured value.

## Expected Behavior

When `ll-init` is run in a project that already has a `.ll/ll-config.json`:
- The wizard seeds every field with the existing config values as defaults.
- This applies whether or not `--force` is passed — existing values are always the
  baseline when a config file is present.
- For headless (`--yes`) runs, CLI-supplied flags override existing values;
  un-specified fields remain unchanged.

## Motivation

Currently:
- Without `--force`: exits immediately with an error, directing users to edit the
  file directly.
- With `--force`: runs the wizard from scratch using template defaults, so users
  must re-enter every value they previously configured.

The intended use case for re-running `ll-init` on an existing project is to
*review and update* the config — not to start over. Pre-populating from the
existing config makes the wizard a non-destructive "review and edit" flow, which is
far more useful.

## Scope Boundaries

- **In scope**: Pre-populating all wizard fields from existing `ll-config.json`;
  headless `--yes` merge behavior (CLI flags override, existing values fill the
  rest); removing the early-exit guard for non-`--force` runs.
- **Out of scope**: Validating or migrating the existing config format; changes to
  the config schema itself; any host CLI behavior beyond `ll-init`.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/tui.py` — add pre-population logic; pass `default=`
  args to `questionary` prompts and pre-select values in `questionary.checkbox`
- `scripts/little_loops/init/cli.py` — merge existing config as baseline in
  `--yes` path; remove or soften the early-exit guard

_Wiring pass added by `/ll:wire-issue`:_
- `skills/init/SKILL.md` — update example comment `/ll:init --force  # overwrite existing config`; after this change `--force` is no longer required to re-run on an existing project, so the comment is misleading; also the skill passes `--force` through to `ll-init --yes $FORCE_FLAG` which remains valid passthrough but the example needs clarification [Agent 1 + Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py:76` — re-exports `main_init` from `little_loops.init.cli`; this is the console-script entry point (`ll-init`) declared in `pyproject.toml:86`

### Similar Patterns
- `scripts/little_loops/init/tui.py:run_tui()` — existing `questionary.text("Source directory:", default=project_data.get("src_dir", "src/"))` shows the `default=` pattern to replicate; replace `project_data.get(key)` with `existing_config.get("project", {}).get(key) or project_data.get(key)`
- `scripts/little_loops/init/tui.py:run_tui()` — existing `questionary.checkbox(..., choices=[Choice(..., checked=(val in default_hosts))])` shows the checkbox pre-selection pattern; replace the source set with values from existing config
- `scripts/little_loops/config/core.py:resolve_config_path()` — canonical function to locate `.ll/ll-config.json`; returns `Path | None`; safe to import and call at the top of `run_tui()` and `_run_yes()`
- `scripts/little_loops/config/core.py:deep_merge()` — merges `override` into `base` (nested dicts recursively, scalars replace, `None` removes); use in `_run_yes()` as `merged = deep_merge(existing_config, cli_flags_dict)` to implement the headless merge
- `scripts/little_loops/init/writers.py:merge_settings()` — read-existing-then-overlay pattern: `json.loads(target.read_text(encoding="utf-8"))`, `except json.JSONDecodeError: data = {}`, then mutate and write; apply the same guard when loading the existing config in `run_tui()` and `_run_yes()`

### Tests

- `scripts/tests/test_init_core.py` — existing tests must continue to pass; add new tests for pre-populate (interactive) and merge (headless) scenarios
- `scripts/tests/test_init_tui.py` — contains `TestExistingConfig` class with a `test_existing_config_with_force_overwrites` test; add a sibling `test_existing_config_pre_populates_defaults` test using the `_wire_q()` / `_mock_ask()` helper pattern already established in that file

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_tui.py:TestExistingConfig.test_existing_config_without_force_returns_1_no_prompts` — **will break**: asserts `rc == 1` and `mock_q.text.assert_not_called()`, both of which target the early-exit guard being removed; replace with an assertion that the wizard runs and pre-fills defaults [Agent 3 finding]
- `scripts/tests/test_init_core.py:TestMainInit.test_yes_fails_if_exists_without_force` — **will break**: asserts `code == 1` when `--yes` is run without `--force` on an existing config; replace with an assertion that `code == 0` and the resulting config preserves existing values [Agent 3 finding]
- `scripts/tests/test_init_tui.py:TestExistingConfig.test_existing_config_with_force_overwrites` — **semantics change**: currently the only path through the wizard when a config exists; after this change `force=False` also proceeds, so the test may need to distinguish pre-population (force=False, seeded defaults) from force-overwrite behavior if any distinction is preserved [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` — documents `ll-init` flags and examples; the section describing the current early-exit behavior ("Use --force to overwrite, or edit the file directly") will need updating to reflect the new "review and edit" flow
- `docs/reference/CONFIGURATION.md` — describes the `ll-config.json` structure; no change expected unless the schema changes (out of scope)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/GETTING_STARTED.md` — `--force` flag table row says "When to use it: Re-initializing a project that already has a config"; after this change the bare `ll-init` is the natural re-run path (pre-populates), so the `--force` description and the troubleshooting entry need updating [Agent 2 finding]
- `docs/codex/getting-started.md` — contains "It also writes `.ll/ll-config.json` if one does not already exist", implying ll-init silently skips when a config exists; after this change ll-init offers a review-and-edit flow instead; update this sentence [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Early-exit guards**: identical guards exist in both `tui.py:run_tui()` (lines ~118-124) and `cli.py:_run_yes()` (lines ~90-96); both must be removed
- **`build_config()` choices injection** (`init/core.py:build_config()`): accepts a flat `choices: dict[str, Any]` where each key (`src_dir`, `test_cmd`, `lint_cmd`, `type_cmd`, `format_cmd`, `learning_tests_enabled`, `analytics_enabled`, `context_monitor_enabled`, `product_enabled`, `session_digest_enabled`) overrides a template default; the headless path can supply existing-config values here without touching TUI code
- **Config is never read during init today**: after `config_path.exists()` the file is never opened in either path; the `.exists()` result is used only as a boolean sentinel for the guard
- **`_build_final_config()` in `tui.py`** calls `build_config(template, choices_dict)` then mutates `config["project"]`, `config["scan"]`, etc.; the existing-config values should be injected into `choices_dict` before this call so they flow through `build_config()` and are then overridden by any wizard answers
- **`resolve_config_path()`** probes `.ll/ll-config.json` first then falls back to root-level `ll-config.json`; import from `little_loops.config.core` — already available in the init module's dependency tree
- **`deep_merge(base, override)`** in `config/core.py`: nested-dict-recursive, scalars/lists replace, `None` removes; already used in `session_start.py:handle()` for local-override overlays — same semantics needed for the headless path merge
- **Exact guard line numbers**: `tui.py:124–130` (`if config_path.exists() and not force: return 1`); `cli.py:90–99` (identical guard; when `force=True` a second block at lines 97–99 prints "Overwriting existing configuration.")
- **Two `questionary.select()` calls missing `default=`**: design-token profile select (`tui.py:268–279`) and settings-target select (`tui.py:314–330`); both currently have no `default=` argument — Implementation Step 3 must add `default=` here sourced from the corresponding existing config keys (`design_tokens.active` and the settings-file target key respectively)
- **Three `build_config()` choices keys absent from `_build_final_config()`'s choices_dict** (assembled at `tui.py:452–461`): `decisions_enabled`, `scratch_pad_enabled`, `session_capture_enabled` are applied as post-`build_config()` dict mutations, not through the choices dict; pre-populate for these three must read from `existing_config` directly in the post-`build_config()` mutation block — they cannot be injected via the choices dict passed to `build_config()`
- **Test assertion pattern for `default=` verification**: `_wire_q()` sets `mock_q.text.side_effect` regardless of what `default=` was passed, so it does NOT verify seeding; the new `test_existing_config_pre_populates_defaults` test must assert via `mock_q.text.call_args_list[N].kwargs.get("default")` (e.g. index 0 = project name prompt) to confirm existing config values were used; for checkbox pre-selection, verify via `mock_q.Choice.call_args_list` — `Choice(label, value=val, checked=True)` call args are captured even though the return is a MagicMock, so assert `mock_q.Choice.call_args_list[N].kwargs.get("checked") == True` for items expected to be pre-checked

## Implementation Steps

1. **Load existing config in `tui.py:run_tui()`** — After the TTY check (before the early-exit guard), call `resolve_config_path(project_root)` from `little_loops.config.core` and, if found, load the file as `existing_config: dict = json.loads(path.read_text(encoding="utf-8"))` with `except json.JSONDecodeError: existing_config = {}`.
2. **Remove / soften the early-exit guard in `tui.py:run_tui()`** — The `if config_path.exists() and not force: return 1` block (the first substantive check after the TTY guard) prevents the wizard from launching without `--force`. Remove it (or convert to a soft message) so the wizard always runs and pre-fills from `existing_config`.
3. **Seed all `questionary` prompt `default=` arguments from existing config** — Replace each `default=project_data.get(key)` with `default=existing_config.get("project", {}).get(key) or project_data.get(key)`. For checkbox fields (`features`, `hosts`), build the pre-checked set from `existing_config` keys rather than `_DEFAULT_FEATURES` / `default_hosts`. For `questionary.select()` calls that currently have no `default=`, supply the existing config value as `default=`.
4. **Mirror for headless path in `cli.py:_run_yes()`** — Remove the same early-exit guard. After `detect_project_type()`, load `existing_config` the same way as step 1. Build a `cli_flags_dict` from any flags actually supplied by the caller, then call `deep_merge(existing_config, cli_flags_dict)` (from `little_loops.config.core`) to get the merged baseline. Pass that merged dict's values as the `choices` argument to `build_config()`.
5. **Update `docs/reference/CLI.md`** — Remove or update the sentence describing the `--force`-less early-exit behavior. The `ll-init` section should reflect the new "review and edit" default flow.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Update breaking tests** — Rewrite `test_init_tui.py:TestExistingConfig.test_existing_config_without_force_returns_1_no_prompts` to assert the wizard runs and pre-fills defaults (instead of `rc == 1` and `text.assert_not_called()`). Rewrite `test_init_core.py:TestMainInit.test_yes_fails_if_exists_without_force` to assert `code == 0` and that the resulting config preserves existing values.
7. **Update `test_existing_config_with_force_overwrites`** — `--force` always seeds from existing config (same as without `--force`); the distinction is that `force=True` additionally removes the guard rather than being the only path through the wizard. Update the test to assert pre-filled defaults rather than template defaults, since the test currently runs from scratch.
8. **Update `skills/init/SKILL.md`** — Change the example comment `/ll:init --force  # overwrite existing config` to clarify that bare `/ll:init` (without `--force`) now pre-populates and proceeds on existing projects; `--force` retains its passthrough role but is no longer required to re-run.
9. **Update `docs/guides/GETTING_STARTED.md`** — Update the `--force` flag "When to use it" column and any troubleshooting entries that say `--force` is required to re-run `ll-init` on a configured project.
10. **Update `docs/codex/getting-started.md`** — Update the sentence "writes `.ll/ll-config.json` if one does not already exist" to reflect the new pre-populate behavior.

## Acceptance Criteria

- Running `ll-init` (with or without `--force`) in a project with an existing
  `ll-config.json` pre-fills every wizard field with the current value.
- The user can change any field; fields left as-is retain the existing value.
- The headless (`--yes`) path merges CLI-supplied flags over existing values,
  leaving un-specified fields unchanged.
- Existing unit tests in `scripts/tests/test_init_core.py` continue to pass.
- A new test covers the "pre-populate from existing config" scenario for both the
  interactive and headless paths.

## Impact

- **Priority**: P4 — Convenience enhancement; low urgency but materially improves
  UX for re-running `ll-init` on existing projects
- **Effort**: Small — Targeted changes in two files; `questionary` already supports
  `default=` arguments; no schema changes required
- **Risk**: Low — Pre-population is additive; new projects (no existing config) are
  entirely unaffected; headless path changes are guarded by existing tests
- **Breaking Change**: No

## Labels

`enhancement`, `captured`, `ux`, `ll-init`

## Session Log
- `/ll:refine-issue` - 2026-06-20T04:54:34 - `eb21245b-b71b-4640-8819-0ebd78cd0c03.jsonl`
- `/ll:wire-issue` - 2026-06-20T04:36:08 - `fc6d3d82-b485-45e4-b461-f7a2a946075c.jsonl`
- `/ll:refine-issue` - 2026-06-20T04:27:52 - `89f4d1f4-8387-4d9c-92e9-07a41c9aed63.jsonl`
- `/ll:format-issue` - 2026-06-20T04:22:11 - `4044fdb0-1f7f-4840-81ca-5c655ad9797c.jsonl`
- `/ll:capture-issue` - 2026-06-20T04:08:03Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74a9e1bd-1cc4-4f47-baf1-9314d4e70d16.jsonl`
