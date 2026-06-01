---
id: ENH-1836
title: Scaffold built-in design token profiles when selected in /ll:configure
status: open
priority: P3
type: ENH
captured_at: '2026-06-01T01:32:36Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
labels:
- enh
- design-system
- config
- configure
relates_to:
- ENH-1768
- FEAT-1757
---

# ENH-1836: Scaffold built-in design token profiles when selected in /ll:configure

## Summary

When a user selects a built-in design token profile (`default`, `editorial-mono`, `warm-paper`) in `/ll:configure design-tokens` and that profile's directory does not yet exist under `.ll/design-tokens/profiles/`, the skill should automatically copy the corresponding template tree from `templates/design-tokens/profiles/<name>/` into the project — instead of writing the config value, emitting a warning, and leaving the profile unmaterialized.

## Motivation

The three built-in profiles already exist as fully-authored templates in `templates/design-tokens/profiles/`. When a user picks one, they expect it to work immediately. The current behaviour (warn + write config only) leaves the runtime loader with no tokens to serve, which silently degrades every artifact-producing loop until the user manually materialises the files — a step the skill never explains how to perform.

`/ll:init` handles this correctly: Step 8 copies all three profiles at once when design tokens are enabled. `/ll:configure` has no equivalent path, so users who enable or switch design tokens outside of init are stuck.

## Current Behavior

`areas.md` (line 1068) instructs the configure skill to:
> *"warn that the profile does not yet exist … and that the runtime loader will degrade to no tokens until the profile is materialized. Write the value anyway."*

No scaffolding step follows. The warning does not tell the user how to materialise the profile.

## Expected Behavior

After the user confirms the config change and the selected profile is a known built-in that does not yet exist on disk:

1. **Detect**: Check whether `<config.design_tokens.path>/<profiles_dir>/<selected_profile>/` exists.
2. **Offer (or auto-scaffold)**: If it does not exist and `templates/design-tokens/profiles/<selected_profile>/` is present, offer to copy it:
   ```
   Profile 'editorial-mono' is not yet installed.
   Copy built-in template to .ll/design-tokens/profiles/editorial-mono/? [Y/n]
   ```
   Default: yes. Auto-accept without prompt if running non-interactively.
3. **Scaffold**: Copy the full template subtree (six files per profile: `primitives.json`, `semantic.json`, `typography.json`, `spacing.json`, `themes/light.json`, `themes/dark.json`) using the same skip-if-exists guard that `/ll:init` uses.
4. **Confirm**: Report the files created, e.g.:
   ```
   ✓ Installed profile: editorial-mono → .ll/design-tokens/profiles/editorial-mono/
   ```
5. **Suppress warning**: The "profile does not exist" warning in `areas.md` should only fire for profiles that are NOT among the three built-ins (i.e. genuinely custom/upcoming profiles).

The same scaffolding logic should apply when design tokens are first enabled (checkbox flipped from `false` → `true`) and no profiles directory exists yet — matching the init path.

## Implementation Plan

### 1. Update `skills/configure/areas.md` — `## Area: design_tokens`

**After the config-write step**, add a materialization sub-step:

```
After writing the config:

If active profile changed to a new value:
  PROFILE_DIR = <config.design_tokens.path>/<profiles_dir or "profiles">/<new_active>
  TEMPLATE_DIR = templates/design-tokens/profiles/<new_active>

  If PROFILE_DIR does not exist AND TEMPLATE_DIR exists:
    Use AskUserQuestion:
      "Profile '<new_active>' is not yet installed locally.
       Copy the built-in template now?"
      Options: "Yes, install it" / "No, skip"
    If yes:
      Bash: cp -r <TEMPLATE_DIR>/ <PROFILE_DIR>/
      Report: ✓ Installed profile: <name> → <PROFILE_DIR>/
  Else if PROFILE_DIR does not exist AND TEMPLATE_DIR does not exist:
    [keep existing warning — this is a custom/pre-config profile]

If enabled changed from false → true AND profiles directory does not exist:
  Bash: cp -r templates/design-tokens/profiles/ <config.design_tokens.path>/profiles/
  Report: ✓ Installed all 3 built-in profiles → <path>/profiles/
```

### 2. Update the "profile does not exist" warning condition

Change `areas.md` line 1068 scope: only warn when the selected profile is **not** in the built-in list (`default`, `editorial-mono`, `warm-paper`) AND not on disk. Built-in profiles that are missing should trigger the scaffold offer, not the warning.

### 3. Add `Bash(cp:*)` to the configure skill's `allowed-tools`

`skills/configure/SKILL.md` currently allows `Bash(mkdir:*)` but not `cp`. Add `Bash(cp:*)` (or use a Python one-liner via the existing `Bash(python3:*)` allowance if `cp` feels too broad).

### 4. No init changes needed

`/ll:init` Step 8 already copies all profiles when enabled. No changes required there.

## Integration Map

### Files to Modify
- `skills/configure/areas.md` — update `## Area: design_tokens` with materialization sub-step and revised warning condition
- `skills/configure/SKILL.md` — add `Bash(cp:*)` to `allowed-tools`

### Dependent Files (Callers/Importers)
- TBD — use grep to find references: `grep -r "design.tokens\|design_tokens" skills/configure/`

### Similar Patterns
- `skills/init/SKILL.md` Step 8 — existing `cp -r templates/design-tokens/profiles/` pattern to reuse

### Tests
- TBD — identify test files to update

### Documentation
- `docs/reference/API.md` — may need update if configure skill API docs exist

### Configuration
- N/A

## Out of Scope

- Authoring new profiles beyond the three built-ins — not this issue.
- Validating token file content or WCAG contrast — covered by ENH-1768 / FEAT-1748.
- The `ll-session` / runtime loader path — already handles missing profiles gracefully.

## Impact

- **Priority**: P3 — UX friction fix; users who configure design tokens outside of `/ll:init` hit a confusing dead end with no recovery path, but it does not block critical workflows
- **Effort**: Small — changes limited to `areas.md` instruction update and `SKILL.md` allowed-tools addition; copy logic already proven and reusable from `/ll:init` Step 8
- **Risk**: Low — additive change only; existing warning path is preserved for non-built-in profiles; no changes to init or runtime loader
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-01 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-06-01T01:52:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f7e90d79-437f-4d91-9dc4-087c4f8bc147.jsonl`
- `/ll:capture-issue` - 2026-06-01T01:32:36Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c319df2-64d7-4c19-97bc-1121afb93793.jsonl`
