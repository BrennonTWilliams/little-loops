---
id: ENH-1836
title: Scaffold built-in design token profiles when selected in /ll:configure
status: done
priority: P3
type: ENH
captured_at: '2026-06-01T01:32:36Z'
completed_at: '2026-06-01T19:55:33Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
decision_needed: false
labels:
- enh
- design-system
- config
- configure
relates_to:
- ENH-1768
- FEAT-1757
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1836: Scaffold built-in design token profiles when selected in /ll:configure

## Summary

When a user selects a built-in design token profile (`default`, `editorial-mono`, `warm-paper`) in `/ll:configure design-tokens` and that profile's directory does not yet exist under `.ll/design-tokens/profiles/`, the skill should automatically copy the corresponding template tree from `templates/design-tokens/profiles/<name>/` into the project — instead of writing the config value, emitting a warning, and leaving the profile unmaterialized.

The copy can be performed via the existing `Bash(python3:*)` allowance using `shutil.copytree` — no new allowed-tool entry is required.

## Motivation

The three built-in profiles already exist as fully-authored templates in `templates/design-tokens/profiles/`. When a user picks one in `/ll:configure`, they expect it to work immediately. The current behaviour (warn + write config only) leaves the runtime loader with no tokens to serve, which silently degrades every artifact-producing loop until the user manually materialises the files — a step the skill never explains how to perform.

`/ll:init` handles this correctly: `SKILL.md` Step 8.6 copies all three profiles at once when design tokens are enabled. `/ll:configure` has no equivalent path, so users who enable or switch design tokens outside of init are stuck.

## Current Behavior

`skills/configure/areas.md` line 1071 (inside `## Area: design_tokens`) instructs the configure skill to:

> *"warn that the profile does not yet exist under `<path>/<profiles_dir or "profiles">/` and that the runtime loader will degrade to no tokens until the profile is materialized. Write the value anyway."*

Two problems with this instruction:
1. **No scaffolding step follows.** The warning does not tell the user how to materialise the profile.
2. **Warning condition is too broad.** It fires when the chosen profile is "NOT in the enumerated installed list." The installed list is derived from actual subdirectories on disk — so a built-in profile that hasn't been materialised yet also triggers the warning, even though a template for it exists.

The `## Area: design_tokens` section has **no** "Configuration Result" block (unlike other areas in the file), meaning there is no post-write scaffolding hook at all.

The `enabled: false → true` flip case is also unhandled: if a user re-enables design tokens after init never ran with tokens enabled, no profiles directory is created.

## Expected Behavior

After the user confirms the config change:

**Case A — Active profile changed to a known built-in that is not yet on disk:**

1. **Detect**: Check whether `<config.design_tokens.path>/<profiles_dir or "profiles">/<selected_profile>/` exists.
2. **Offer (or auto-scaffold)**: If it does not exist and `templates/design-tokens/profiles/<selected_profile>/` is present, offer to copy it:
   ```
   Profile 'editorial-mono' is not yet installed.
   Copy built-in template to .ll/design-tokens/profiles/editorial-mono/? [Y/n]
   ```
   Default: yes. Auto-accept without prompting if `DANGEROUSLY_SKIP_PERMISSIONS` is set or `--auto` is passed.
3. **Scaffold**: Copy the full template subtree (six files per profile: `primitives.json`, `semantic.json`, `typography.json`, `spacing.json`, `themes/light.json`, `themes/dark.json`) using `shutil.copytree` via `Bash(python3:*)`.
4. **Confirm**: Report the files created:
   ```
   ✓ Installed profile: editorial-mono → .ll/design-tokens/profiles/editorial-mono/
   ```
5. **Warning suppression**: The line-1071 "profile does not exist" warning should only fire for profiles that are NOT among the three built-ins (i.e. genuinely custom/upcoming profiles). Built-in profiles that are missing should trigger the scaffold offer, not the warning.

**Case B — `enabled` flipped from `false` → `true` and no profiles directory exists yet:**

Scaffold all three built-in profiles using the same pattern as `init` Step 8.6:
```bash
python3 -c "import shutil; shutil.copytree('templates/design-tokens/profiles', '<path>/profiles', dirs_exist_ok=False)"
```
Report: `✓ Installed all 3 built-in profiles → <path>/profiles/`

## Implementation Plan

### 1. Update `skills/configure/areas.md` — `## Area: design_tokens`

**Location**: `skills/configure/areas.md`, immediately after line 1071 (the current "write anyway" warning instruction).

Add a materialization sub-step block after the Round 1 warning text:

```
### Configuration Result — design_tokens

After writing the config, apply materialization logic:

**Case A — Active profile changed to a new value:**
  BUILTIN = ["default", "editorial-mono", "warm-paper"]
  PROFILE_DIR = <config.design_tokens.path>/<profiles_dir or "profiles">/<new_active>
  TEMPLATE_DIR = templates/design-tokens/profiles/<new_active>

  If PROFILE_DIR does not exist:
    If new_active is in BUILTIN AND TEMPLATE_DIR exists:
      If interactive (not dangerously-skip-permissions and not --auto):
        Use AskUserQuestion:
          "Profile '<new_active>' is not yet installed locally. Copy the built-in template now?"
          Options: "Yes, install it (Recommended)" / "No, skip"
        If yes:
          Bash(python3:*): python3 -c "import shutil; shutil.copytree('<TEMPLATE_DIR>', '<PROFILE_DIR>')"
          Report: ✓ Installed profile: <name> → <PROFILE_DIR>/
      Else (non-interactive):
        Bash(python3:*): python3 -c "import shutil; shutil.copytree('<TEMPLATE_DIR>', '<PROFILE_DIR>')"
        Report: ✓ Auto-installed profile: <name> → <PROFILE_DIR>/
    Else (profile is custom / not a built-in):
      [keep existing warning — user is intentionally pre-configuring]

**Case B — `enabled` changed from false → true AND profiles directory does not exist:**
  PROFILES_ROOT = <config.design_tokens.path>/<profiles_dir or "profiles">
  If PROFILES_ROOT does not exist:
    Bash(python3:*): python3 -c "import shutil; shutil.copytree('templates/design-tokens/profiles', '<PROFILES_ROOT>', dirs_exist_ok=False)"
    Report: ✓ Installed all 3 built-in profiles → <PROFILES_ROOT>/
```

### 2. Narrow the "profile does not exist" warning condition

Change the scope of the line-1071 instruction: only warn when the selected profile is **not** in `["default", "editorial-mono", "warm-paper"]` AND not on disk. The current broad condition ("NOT in the enumerated installed list") also fires for un-materialised built-ins, which now have their own scaffold path.

Replace line 1071 with:
```
If the user picks a profile name that is NOT in the enumerated installed list:
  If the name IS one of ["default", "editorial-mono", "warm-paper"]:
    → trigger the materialization sub-step in "Configuration Result" below (do not warn)
  Else (genuinely custom/unknown profile):
    → warn that the profile does not yet exist under <path>/<profiles_dir or "profiles">/
      and that the runtime loader will degrade to no tokens until the profile is materialized.
      Write the value anyway — the user may be intentionally pre-configuring for an upcoming profile.
```

### 3. No new `allowed-tools` entry needed

`skills/configure/SKILL.md` already declares `Bash(python3:*)` (line 10). The `shutil.copytree` one-liner runs entirely as a subprocess — no `Write` tool call is needed. Do **not** add `Bash(cp:*)`.

### 4. No init changes needed

`skills/init/SKILL.md` Step 8.6 already copies all profiles when enabled. No changes required there.

### 5. Write / update tests

- Add a `TestConfigureAreasMdScaffoldBlock` class to `scripts/tests/test_feat1757_configure_wiring.py` (or create `scripts/tests/test_enh1836_configure_scaffold_wiring.py` following the same class pattern) with the six assertions listed in the Tests subsection of the Integration Map above.
- Verify `scripts/tests/test_enh1768_profile_system.py::TestConfigureWiringForProfiles` still passes — it reads `areas.md` and the materialization block is additive, so no text should be removed that these tests rely on.

## Integration Map

### Files to Modify
- `skills/configure/areas.md` — Add "Configuration Result" materialization sub-step after line 1071; narrow the warning condition at line 1071 to non-built-in profiles only
- `skills/configure/SKILL.md` — No allowed-tools change needed (`Bash(python3:*)` already present at line 10)

### Dependent Files (Callers/Importers)
- `skills/configure/areas.md:1029` — pre-question enumeration reads `<path>/<profiles_dir>/` subdirectories; after scaffolding the new profile will appear in subsequent enumerations
- `scripts/little_loops/config/features.py:314` — `DesignTokensConfig` dataclass owns `active`, `profiles_dir`, and `path` fields used by the skill's template variables
- `scripts/little_loops/hooks/session_start.py:196` — runtime loader reads `design_tokens.active` and resolves `<path>/<profiles_dir>/<active>/` to load tokens; will succeed once the profile is scaffolded
- `scripts/little_loops/config/core.py` — imports `DesignTokensConfig` and exposes it via the `_design_tokens` property on `BRConfig`; no code change needed, but downstream consumers of `config.design_tokens` depend on this chain [Agent 1 finding]

### Similar Patterns
- `skills/init/SKILL.md:340` — Step 8.6: existing `Mirror the full templates/design-tokens/profiles/ tree` pattern; identical guard logic (`does not already exist`) and six-file structure to replicate
- `scripts/tests/test_enh1768_profile_system.py:293` — `_copy_templates()` test fixture uses `shutil.copytree(TEMPLATES_DIR, dest)` — confirms `shutil.copytree` is the established codebase pattern
- `scripts/little_loops/worktree_utils.py:73` — production `shutil.copytree` usage for `.claude/` subtree deploy — same one-shot copy pattern

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1768_profile_system.py` — `TestConfigureWiringForProfiles` class (lines 401–414) already reads `areas.md` to assert `design_tokens.active` presence; must remain passing after the materialization block is added (no text is removed) [Agent 2 finding]

- `scripts/tests/test_feat1757_configure_wiring.py` — existing configure wiring tests; follow this file's structure (`TestConfigureSkillMd`, `TestConfigureAreasMd`, `TestConfigureShowOutputMd`) when adding new assertions
- Add doc-wiring assertions to `test_feat1757_configure_wiring.py` (or create `scripts/tests/test_enh1836_configure_scaffold_wiring.py`):
  - `"Configuration Result" in CONFIGURE_AREAS.read_text()` — confirms the new post-write block exists
  - `"shutil.copytree" in CONFIGURE_AREAS.read_text()` — confirms the scaffold command is present
  - `"default"`, `"editorial-mono"`, `"warm-paper"` all appear in the BUILTIN list in `areas.md`
  - `"AskUserQuestion"` appears in the `Configuration Result — design_tokens` section (interactive offer is present)
  - `"DANGEROUSLY_SKIP_PERMISSIONS"` or `"--auto"` appears before `"AskUserQuestion"` in that section (guard-first ordering — Pattern B from `test_audit_loop_run_skill.py`)
  - `"Bash(python3:*)"` appears in SKILL.md frontmatter (verifies the no-new-tool-needed claim remains true)

### Documentation
- `docs/reference/CONFIGURATION.md` — no update needed (runtime behaviour is unchanged; only the skill instruction adds a scaffolding step)

### Configuration
- N/A — no config schema changes; `DesignTokensConfig.profiles_dir` default (`None` → resolved as `"profiles"`) is already handled correctly

## Out of Scope

- Authoring new profiles beyond the three built-ins — not this issue.
- Validating token file content or WCAG contrast — covered by ENH-1768 / FEAT-1748.
- The `ll-session` / runtime loader path — already handles missing profiles gracefully.

## Impact

- **Priority**: P3 — UX friction fix; users who configure design tokens outside of `/ll:init` hit a confusing dead end with no recovery path, but it does not block critical workflows
- **Effort**: Small — two targeted edits to `areas.md` (add materialization block, narrow warning condition); no Python code changes; no new allowed-tools
- **Risk**: Low — additive change only; existing warning path is preserved for non-built-in profiles; no changes to init or runtime loader
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-01 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-01T19:53:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/73c52d25-5f61-4698-a9bb-65b26c7769ce.jsonl`
- `/ll:wire-issue` - 2026-06-01T19:48:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eb83fecc-8d9c-4767-853a-533a0285f095.jsonl`
- `/ll:refine-issue` - 2026-06-01T19:41:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/db9f327f-09a9-4120-b4b7-aa4ad6b9bf35.jsonl`
- `/ll:refine-issue` - 2026-06-01T02:00:00 - `auto --full-rewrite`
- `/ll:format-issue` - 2026-06-01T01:52:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f7e90d79-437f-4d91-9dc4-087c4f8bc147.jsonl`
- `/ll:capture-issue` - 2026-06-01T01:32:36Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c319df2-64d7-4c19-97bc-1121afb93793.jsonl`
- `/ll:confidence-check` - 2026-06-01T20:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a3b49c47-258c-4323-aea2-25a8853ad4cb.jsonl`
