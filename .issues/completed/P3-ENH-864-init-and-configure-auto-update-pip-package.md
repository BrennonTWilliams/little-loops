---
id: ENH-864
type: ENH
priority: P3
status: active
discovered_date: 2026-03-23
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 75
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`skills/init/SKILL.md` — key locations:**
- `skills/init/SKILL.md:19` — `<!-- PLUGIN_VERSION: 1.50.0 -->` version anchor (currently stale vs `1.61.1` in `scripts/little_loops/__init__.py:26`; update this alongside or after the enhancement)
- `skills/init/SKILL.md:5–10` — `allowed-tools` frontmatter: only `Bash(which:*)` is listed for Bash; add `Bash(python3:*)` and `Bash(pip:*)` to support the auto-install path in `--yes` mode
- `skills/init/SKILL.md:327–377` — full Step 9.5 content; the warn-only "versions differ" branch is at lines 370–374
- `skills/init/SKILL.md:41–54` — `--yes` flag parsing: `if [[ "$FLAGS" == *"--yes"* ]]; then YES=true; fi` — use `$YES` to gate auto-install vs interactive prompt

**`skills/configure/SKILL.md` — key locations:**
- `skills/configure/SKILL.md:4–7` — `allowed-tools` frontmatter: only `Bash(mkdir:*)` for Bash; add `Bash(python3:*)` and `Bash(pip:*)` here too; also add `AskUserQuestion` (not listed in either skill's frontmatter currently — `skills/init/SKILL.md:4–10` likewise omits it, though init uses AskUserQuestion in practice)
- `skills/configure/SKILL.md:27–39` — Step 1: Parse Arguments (flag parsing); insert pip check logic immediately after this block, before any `--list`/`--show`/`--reset` mode branching
- `skills/configure/SKILL.md:137+` — Interactive mode / Step 1: Area Selection; pip check precedes this
- No `PLUGIN_VERSION` comment exists — add `<!-- PLUGIN_VERSION: X.Y.Z -->` after the `# Configure` heading at line 17 (mirror `skills/init/SKILL.md:19`)
- Configure has **no `--yes` flag** (flags are `--list`, `--show`, `--reset` only) — pip check in configure is always interactive

**Version sources:**
- `scripts/little_loops/__init__.py:26` — `__version__ = "1.61.1"` (authoritative)
- `scripts/pyproject.toml:7` — `version = "1.61.1"` (matches)
- `skills/init/SKILL.md:19` — `<!-- PLUGIN_VERSION: 1.50.0 -->` (currently stale)

**Detection one-liner to reuse in configure (from `skills/init/SKILL.md:366`):**
```bash
python3 -c "import importlib.metadata; print(importlib.metadata.version('little-loops'))" 2>/dev/null
```

## Implementation Steps

1. Open `skills/init/SKILL.md`, locate step 9.5, find the "If versions differ → warn" branch
2. Replace the warn-only block with a conditional: in `--yes` mode run the install; in interactive mode use `AskUserQuestion` to confirm before running
3. Add success/failure output for the install step
4. Open `skills/configure/SKILL.md`, add a new step "0.5 Pip Package Check" (before the config area menu) with the same detection + update logic
5. Verify both skills reference the same `PLUGIN_VERSION` comment format for comparison

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Refined steps with exact file locations:

1. **`skills/init/SKILL.md:5–10`** — Add `Bash(python3:*)` and `Bash(pip:*)` to `allowed-tools` (required for `--yes` auto-install to run without user approval dialogs)
2. **`skills/init/SKILL.md:370–374`** — Replace the warn-only block:
   - If `$YES == true` → run `pip install --upgrade little-loops` (or `pip install -e "./scripts"` if `./scripts/` exists locally) via Bash; confirm with success/failure message before continuing
   - Else (interactive) → use `AskUserQuestion` with yes/no to confirm before running the same install command
3. **`skills/configure/SKILL.md:4–7`** — Add `Bash(python3:*)` and `Bash(pip:*)` to `allowed-tools`
4. **`skills/configure/SKILL.md:17`** — Add `<!-- PLUGIN_VERSION: 1.61.1 -->` after the `# Configure` heading (same convention as `skills/init/SKILL.md:19`)
5. **`skills/configure/SKILL.md:27–39`** — After flag parsing (Step 1), insert a "Pip Package Check" using the detection one-liner from `skills/init/SKILL.md:366`; since configure has no `--yes` flag this is always interactive; skip check if `LIST_MODE`, `SHOW_MODE`, or `RESET_MODE` is true (only relevant during a live configure session)
6. **Optional follow-up**: Update `skills/init/SKILL.md:19` PLUGIN_VERSION from `1.50.0` to `1.61.1` to match `scripts/little_loops/__init__.py:26`

## API/Interface

N/A — No public API changes; this enhancement modifies skill markdown files only.

## Impact

- **Priority**: P3 — Low priority; improves UX for users who update the plugin but don't remember to run `pip install`
- **Effort**: Small — text edits to two skill files, no Python changes
- **Risk**: Low — non-blocking; only adds an opt-in update step
- **Breaking Change**: No

## Labels

enhancement, init, configure, pip, package-management

## Resolution

- **Status**: Completed
- **Date**: 2026-03-23
- **Changes**:
  - `skills/init/SKILL.md`: Added `AskUserQuestion`, `Bash(python3:*)`, `Bash(pip:*)` to `allowed-tools`; updated `PLUGIN_VERSION` from `1.50.0` to `1.61.1`; replaced warn-only version-mismatch branch with conditional auto-update logic (`--yes` → silent install, interactive → `AskUserQuestion` prompt)
  - `skills/configure/SKILL.md`: Added `AskUserQuestion`, `Bash(python3:*)`, `Bash(pip:*)` to `allowed-tools`; added `<!-- PLUGIN_VERSION: 1.61.1 -->` comment; added Step 1.5 Pip Package Check (interactive, skipped in `--list`/`--show`/`--reset` modes)

## Status

Completed

## Session Log
- `/ll:ready-issue` - 2026-03-23T22:30:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19fd35ab-9270-4420-96ba-b9bf29365721.jsonl`
- `/ll:confidence-check` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5a9a29b-78e5-4330-acde-d4161d5e76d6.jsonl`
- `/ll:refine-issue` - 2026-03-23T22:22:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ba226300-17d6-4c1b-a577-f8f3208d00a9.jsonl`
- `/ll:format-issue` - 2026-03-23T22:16:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/795fcb4e-b6a9-48e6-b5c4-307257454953.jsonl`
- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/90e70c91-9459-4013-8a64-c4fa530434f9.jsonl`
- `/ll:manage-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
