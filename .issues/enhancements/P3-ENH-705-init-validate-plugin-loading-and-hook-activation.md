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

Add a **Step 9.5** validation step in `skills/init/SKILL.md` (after Step 9: Update .gitignore, before Step 10: Display Completion Message), following the same non-blocking pattern as the existing Step 7.5 command availability check (`SKILL.md:212-243`):

1. Check `.claude/settings.json` (or `.claude/settings.local.json`) for a plugin entry referencing `little-loops` or `.claude-plugin/plugin.json`. Note: `CLAUDE_PLUGIN_ROOT` env var is only available at hook runtime, not during init execution, so settings file inspection is the reliable detection method.
2. Determine which hook-dependent features are active:
   - Explicitly enabled: `context_monitor.enabled: true` (set in interactive Round 3a, `interactive.md:457-462`)
   - Implicitly enabled by schema default: `continuation.enabled: true` and `continuation.auto_detect_on_session_start: true` (`config-schema.json:369-375`) — these are never configured during init because Round 9 is auto-skipped (`interactive.md:590-596`)
3. If any hook-dependent features are active but plugin loading can't be confirmed, output a warning block:
   ```
   ⚠ Hook-dependent features enabled but plugin loading not confirmed.
     Features: context_monitor, continuation/handoff auto-trigger
     These features require little-loops to be registered as a Claude Code plugin.
     Hooks affected: PostToolUse (context-monitor.sh), SessionStart (session-start.sh)
     See: https://docs.anthropic.com/claude-code/plugins
   ```
4. Do not block init — warn and continue (consistent with Step 7.5 behavior)

## Scope Boundaries

- **In scope**: Adding a post-write validation step to `skills/init/SKILL.md`
- **Out of scope**: Automatically installing the plugin, modifying Claude Code settings

## Implementation Steps

1. **Add Step 9.5 to `skills/init/SKILL.md`** (insert between Step 9 at ~line 320 and Step 10 at ~line 324):
   - Title: "### 9.5. Plugin Loading Validation"
   - Follow the structure of Step 7.5 (`SKILL.md:212-243`): non-blocking, skipped for `--dry-run`
   - Check `.claude/settings.json` and `.claude/settings.local.json` for plugin registration
   - Detect hook-dependent features: check written config for `context_monitor.enabled: true`, and note that `continuation` is implicitly enabled by schema defaults (`config-schema.json:369-375`)
   - If features active but plugin not confirmed, emit structured warning block

2. **Determine detection logic for plugin registration**:
   - Read `.claude/settings.json` (if it exists) and look for a `plugins` array or `permissions` entries referencing the little-loops plugin path
   - Fallback: check if `.claude-plugin/plugin.json` exists in the project root (confirms manifest exists, but not that Claude Code has loaded it)
   - Model after the `validate_enabled_features()` pattern in `hooks/scripts/session-start.sh:101-144` — check condition, emit warning, continue

3. **Update Step 10 completion message** (`SKILL.md:324-352`):
   - If the plugin warning was emitted in Step 9.5, include a reminder in the "Next steps" section about plugin registration

4. **Optionally update `skills/init/interactive.md`**:
   - In the wizard summary output, if hook-dependent features were selected in Round 3a (`interactive.md:183-204`), include the plugin status note

## Impact

- **Priority**: P3 - Quality-of-life improvement; silent failures are confusing but not blocking
- **Effort**: Small - Single validation step added to existing skill file
- **Risk**: Low - Warning-only, does not block init or change config behavior
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — add Step 9.5 plugin validation (insert between ~line 320 and ~line 324)
- `skills/init/interactive.md` — optionally add plugin status note to wizard summary when hook features selected in Round 3a

### Dependent Files (Callers/Importers)
- N/A — init skill is invoked directly by users, not imported

### Similar Patterns
- `skills/init/SKILL.md:212-243` — Step 7.5 command availability check: non-blocking, post-confirm, warn-and-continue pattern (direct structural analog)
- `hooks/scripts/session-start.sh:101-144` — `validate_enabled_features()`: checks enabled feature flags against sub-config completeness, emits `[little-loops] Warning:` to stderr
- `commands/align-issues.md:32-56` — Pre-check gate with remediation steps (blocking variant, shows both wizard and manual JSON paths)

### Tests
- No existing test coverage for init skill validation logic
- `scripts/tests/test_hooks_integration.py` — hook integration tests (model for testing hook-dependent behavior)
- `scripts/tests/test_config.py` — config module tests (model for testing config key detection)

### Documentation
- Warning is self-documenting in init output
- `docs/guides/GETTING_STARTED.md` — could reference the plugin validation warning

### Configuration
- Reads: `context_monitor.enabled` (`config-schema.json:413-416`, default `false`)
- Reads: `continuation.enabled` (`config-schema.json:369-372`, default `true`)
- Reads: `continuation.auto_detect_on_session_start` (`config-schema.json:373-375`, default `true`)
- Inspects: `.claude/settings.json` for plugin registration entries
- No new config keys added

## Labels

`enhancement`, `init`, `developer-experience`

## Session Log
- `/ll:capture-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4922c4e9-2029-4f68-b0a3-04ae4dbcd620.jsonl`
- `/ll:format-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/515ca590-73cd-40a5-bdc2-fd93b84ad7b4.jsonl`
- `/ll:refine-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bbd0bb4e-1acc-4e46-9be4-546db972de6a.jsonl`

---

**Open** | Created: 2026-03-12 | Priority: P3
