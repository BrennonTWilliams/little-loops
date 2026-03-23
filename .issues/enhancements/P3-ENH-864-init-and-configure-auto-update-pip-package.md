---
id: ENH-864
type: ENH
priority: P3
status: active
discovered_date: 2026-03-23
discovered_by: capture-issue
---

# ENH-864: Init and Configure Should Auto-Update Pip Package When Outdated

## Summary

`/ll:init` currently warns when the `little-loops` pip package is missing or version-mismatched but does not act. `/ll:configure` has no pip package awareness at all. Both skills should detect the installed package version and offer to update (or auto-update) when it is out of date, rather than only printing a manual install command.

## Current Behavior

- `/ll:init` (step 9.5) checks the installed `little-loops` version against `PLUGIN_VERSION` and prints a warning with a manual `pip install --upgrade` command if mismatched. It takes no action.
- `/ll:configure` performs no pip package check whatsoever.

## Expected Behavior

- `/ll:init`: After detecting a version mismatch, prompt the user (or in `--yes` mode, automatically run) `pip install --upgrade little-loops` (or `pip install -e "./scripts"` for dev installs). Report success/failure before continuing. The check remains non-blocking — failures are surfaced as warnings, not errors.
- `/ll:configure`: Add a pip package version check at the start (or end) of a configure session. When a mismatch is detected, prompt the user to update inline, mirroring the init behavior.

## Motivation

Users frequently run `/ll:init` once and then rely on `/ll:configure` for day-to-day adjustments. If the plugin is updated (e.g., via `git pull`), the pip package can drift out of sync silently. Auto-updating at both entry points ensures CLI tools (`ll-auto`, `ll-sprint`, etc.) stay aligned with the plugin version without requiring the user to remember a separate install step.

## Success Metrics

- Running `/ll:init` with a stale pip package results in a prompt (interactive) or silent auto-update (`--yes`) and a confirmation message
- Running `/ll:configure` with a stale pip package shows the same prompt/auto-update flow
- If the pip package is already current, both skills produce no pip-related output (silent success)
- If the update fails, a warning is displayed and execution continues (non-blocking)

## Scope Boundaries

- **In scope**: Adding auto-update logic to `skills/init/SKILL.md` step 9.5; adding a pip check step to `skills/configure/SKILL.md`
- **Out of scope**: Changing the install command itself; adding version checks to other skills; modifying Python scripts

## Proposed Solution

1. In `skills/init/SKILL.md` step 9.5, extend the version-mismatch branch:
   - In `--yes` mode: run `pip install --upgrade little-loops` (or `pip install -e "./scripts"` if a local `./scripts` directory is present) silently, then confirm with `✓ little-loops updated to A.B.C`.
   - In interactive mode: ask the user "Update little-loops pip package now? (y/n)" before running.
2. In `skills/configure/SKILL.md`, add a "Pip Package Check" step that runs the same version detection logic. Position it as an early step (before presenting config areas) so users see it upfront. Apply the same interactive/auto-update flow as init.
3. Reuse identical detection logic in both skills (same bash one-liner; same PLUGIN_VERSION comparison).

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — extend step 9.5 version-mismatch branch with update prompt/action
- `skills/configure/SKILL.md` — add new pip package check step

### Dependent Files (Callers/Importers)
- N/A — skill `.md` files are not imported or called programmatically

### Similar Patterns
- `skills/init/SKILL.md` step 9.5 — existing version detection bash logic to reuse in configure

### Tests
- N/A — no Python script changes; skill behavior verified by manual testing

### Documentation
- N/A — the modified skill files are themselves the documentation

### Configuration
- N/A

## Implementation Steps

1. Open `skills/init/SKILL.md`, locate step 9.5, find the "If versions differ → warn" branch
2. Replace the warn-only block with a conditional: in `--yes` mode run the install; in interactive mode use `AskUserQuestion` to confirm before running
3. Add success/failure output for the install step
4. Open `skills/configure/SKILL.md`, add a new step "0.5 Pip Package Check" (before the config area menu) with the same detection + update logic
5. Verify both skills reference the same `PLUGIN_VERSION` comment format for comparison

## API/Interface

N/A — No public API changes; this enhancement modifies skill markdown files only.

## Impact

- **Priority**: P3 — Low priority; improves UX for users who update the plugin but don't remember to run `pip install`
- **Effort**: Small — text edits to two skill files, no Python changes
- **Risk**: Low — non-blocking; only adds an opt-in update step
- **Breaking Change**: No

## Labels

enhancement, init, configure, pip, package-management

## Status

Active

## Session Log
- `/ll:format-issue` - 2026-03-23T22:16:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/795fcb4e-b6a9-48e6-b5c4-307257454953.jsonl`
- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/90e70c91-9459-4013-8a64-c4fa530434f9.jsonl`
