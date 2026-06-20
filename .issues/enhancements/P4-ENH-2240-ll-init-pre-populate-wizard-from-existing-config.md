---
id: ENH-2240
title: "ll-init should pre-populate the wizard from existing ll-config.json"
type: ENH
priority: P4
status: open
captured_at: "2026-06-20T04:08:03Z"
discovered_date: "2026-06-20"
discovered_by: capture-issue
---

# ENH-2240: ll-init should pre-populate the wizard from existing ll-config.json

## Summary

When `ll-init` is run in a project that already has a `.ll/ll-config.json`, the
interactive wizard should seed every field with the existing config values rather
than falling back to project-type template defaults. This applies whether or not
`--force` is passed — any time a config already exists, existing values should be
the defaults.

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

## Implementation Steps

1. In `scripts/little_loops/init/tui.py`, before the wizard screens begin, check
   whether `config_path.exists()` and load the existing config JSON if present.
2. Pass the loaded config values as `default=` arguments to each `questionary`
   prompt (e.g., `questionary.text("Project name:", default=existing_name)`).
3. For list/multi-choice fields (hosts, exclude patterns), pre-select the existing
   values in the `questionary.checkbox` calls.
4. Remove the early-exit guard that blocks non-`--force` runs — or convert it to a
   softer warning — so `ll-init` without `--force` also enters the wizard with
   existing values pre-filled rather than aborting.
5. Mirror the same change in `scripts/little_loops/init/cli.py` for the
   `--yes`/headless path: when `--yes` is passed and a config already exists,
   use existing values as the baseline and only override fields supplied via CLI
   flags.

## Acceptance Criteria

- Running `ll-init` (with or without `--force`) in a project with an existing
  `ll-config.json` pre-fills every wizard field with the current value.
- The user can change any field; fields left as-is retain the existing value.
- The headless (`--yes`) path merges CLI-supplied flags over existing values,
  leaving un-specified fields unchanged.
- Existing unit tests in `scripts/tests/test_init_core.py` continue to pass.
- A new test covers the "pre-populate from existing config" scenario for both the
  interactive and headless paths.

## Session Log
- `/ll:capture-issue` - 2026-06-20T04:08:03Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74a9e1bd-1cc4-4f47-baf1-9314d4e70d16.jsonl`
