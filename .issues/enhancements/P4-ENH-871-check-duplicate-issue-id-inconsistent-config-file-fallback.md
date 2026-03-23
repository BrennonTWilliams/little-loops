---
discovered_date: 2026-03-23
discovered_by: capture-issue
---

# ENH-871: check-duplicate-issue-id.sh inconsistent config file fallback

## Summary

`check-duplicate-issue-id.sh` hardcodes `CONFIG_FILE=".claude/ll-config.json"` with no fallback to `ll-config.json`. All other hook scripts fall back to `ll-config.json` when the `.claude/` prefixed path is absent. The inconsistency is harmless today (default `.issues` is correct), but is a latent bug for projects that use a non-standard `issues.base_dir` and place their config at `ll-config.json`.

## Current Behavior

```bash
CONFIG_FILE=".claude/ll-config.json"
ISSUES_BASE_DIR=$(jq -r '.issues.base_dir // ".issues"' "$CONFIG_FILE" 2>/dev/null || echo ".issues")
```

If the project's config is at `ll-config.json` (not `.claude/ll-config.json`), `jq` silently fails and `ISSUES_BASE_DIR` defaults to `.issues`. A non-standard `base_dir` configured at `ll-config.json` is ignored.

## Expected Behavior

The script should check both config file locations (`ll-config.json` then `.claude/ll-config.json`, or the other way) consistent with the other hook scripts in the same directory.

## Motivation

Behavioral inconsistency between scripts in the same directory is a reliability smell. While today's default happens to be correct, a project configured with `issues.base_dir: "issues"` and config at `ll-config.json` would silently get wrong duplicate checking — a hard-to-diagnose bug.

## Success Metrics

- Script reads the correct `issues.base_dir` when config is placed at `ll-config.json` (not `.claude/ll-config.json`)
- Behavior is unchanged when config exists at `.claude/ll-config.json` (existing projects unaffected)
- All hook scripts in `hooks/scripts/` use the same config-loading pattern (no one-off divergence)

## Proposed Solution

Match the fallback pattern used in other hook scripts:

```bash
# Consistent with other scripts:
CONFIG_FILE=".claude/ll-config.json"
[ ! -f "$CONFIG_FILE" ] && CONFIG_FILE="ll-config.json"
ISSUES_BASE_DIR=$(jq -r '.issues.base_dir // ".issues"' "$CONFIG_FILE" 2>/dev/null || echo ".issues")
```

Or use the shared `common.sh` config loading utility if one exists for this purpose.

## API/Interface

N/A - No public API changes (shell script internal fix only)

## Integration Map

### Files to Modify
- `hooks/scripts/check-duplicate-issue-id.sh` — add config file fallback

### Similar Patterns
- Other scripts in `hooks/scripts/` that load `ll-config.json` — verify they all use the same fallback pattern and consolidate if not

### Tests
- TBD — test with config at `ll-config.json` vs `.claude/ll-config.json`

### Documentation
- N/A

### Configuration
- N/A

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — registers this script as the `PreToolUse` Write|Edit handler

## Implementation Steps

1. Identify the canonical config-loading pattern used by other scripts in `hooks/scripts/`
2. Apply the same pattern to `check-duplicate-issue-id.sh`
3. Optionally extract into `common.sh` if a shared loader doesn't already exist

## Scope Boundaries

- Only align the config file lookup with the existing pattern used elsewhere — no changes to the duplicate-checking logic itself
- Do not change the default `base_dir` fallback value

## Impact

- **Priority**: P4 - Latent bug; currently harmless but breaks non-standard configs silently
- **Effort**: Small - 2–3 line change
- **Risk**: Low - Additive fallback; existing behavior preserved when `.claude/ll-config.json` exists
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`hooks`, `enhancement`, `captured`

## Session Log
- `/ll:format-issue` - 2026-03-23T22:44:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9850963-0ae2-487e-9014-ade593329bce.jsonl`

- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0e087610-8d6c-49f4-bacd-b3c561cb7252.jsonl`

---

**Open** | Created: 2026-03-23 | Priority: P4
