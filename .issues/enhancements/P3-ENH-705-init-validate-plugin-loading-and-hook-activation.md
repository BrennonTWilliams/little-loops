---
discovered_date: 2026-03-12
discovered_by: capture-issue
---

# ENH-705: Init should validate plugin loading and hook activation

## Summary

When a user enables hook-dependent features (context monitoring, handoff) during `/ll:init`, the init process does not verify that little-loops is actually loaded as a Claude Code plugin. If it isn't, those features silently do nothing — hooks never fire. Init should detect this condition and warn the user clearly.

## Current Behavior

`/ll:init` successfully configures features like `context_monitor.enabled: true` and `continuation.auto_detect_on_session_start: true`, writes `.claude/ll-config.json`, and reports success. If little-loops is not loaded as a plugin (e.g., only installed via CLAUDE.md instructions or scripts in PATH), the PostToolUse and PreCompact hooks never fire, but the user receives no warning.

## Expected Behavior

When init enables features that depend on hooks (`context_monitor`, handoff thresholds, precompact state), it should:
1. Detect whether little-loops appears to be loaded as a plugin (check for `.claude-plugin/plugin.json` in the loaded plugins, or inspect the Claude Code settings)
2. If not loaded as a plugin, display a clear warning explaining that these features require plugin loading
3. Optionally offer guidance on how to register the plugin

## Motivation

Silent failure is confusing. A user who follows the init wizard and enables handoff automation reasonably expects it to work. When nothing happens at 80% context, they have no signal that the feature is unconfigured. Adding a validation step surfaces the problem at setup time rather than leaving users to discover it empirically.

## Proposed Solution

Add a validation step (Step 10 or after Step 9: Write Configuration) in `skills/init/SKILL.md`:

1. Check for indicators that little-loops is loaded as a plugin:
   - Look for `${CLAUDE_PLUGIN_ROOT}` environment variable being set
   - Or check if `.claude/settings.json` references the little-loops plugin
2. If hook-dependent features are enabled but plugin loading can't be confirmed, output a warning block:
   ```
   ⚠ Hook-dependent features enabled but plugin loading not confirmed.
     Features: context_monitor, handoff auto-trigger
     These features require little-loops to be registered as a Claude Code plugin.
     See: https://docs.anthropic.com/claude-code/plugins
   ```
3. Do not block init — warn and continue

## Scope Boundaries

- **In scope**: Adding a post-write validation step to `skills/init/SKILL.md`
- **Out of scope**: Automatically installing the plugin, modifying Claude Code settings

## Implementation Steps

1. Identify which config keys signal hook-dependent features (`context_monitor.enabled`, `context_monitor.auto_handoff_threshold`, `continuation.auto_detect_on_session_start`)
2. After writing config, check if `CLAUDE_PLUGIN_ROOT` env var is set (reliable indicator when running inside the plugin)
3. If hook features enabled and plugin not detected, emit structured warning
4. Add test coverage for the warning condition

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — add validation step after config write
- `skills/init/interactive.md` — optionally surface warning in wizard summary

## Session Log
- `/ll:capture-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4922c4e9-2029-4f68-b0a3-04ae4dbcd620.jsonl`
