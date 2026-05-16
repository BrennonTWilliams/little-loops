---
discovered_date: 2026-03-23
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

`check-duplicate-issue-id.sh` already sources `lib/common.sh` at **line 14**, which provides `ll_resolve_config()` at `lib/common.sh:184-191`. The canonical fix is to call `ll_resolve_config` (which sets `$LL_CONFIG_FILE`) and then use that variable:

```bash
# Replace lines 45-46 in check-duplicate-issue-id.sh:
ll_resolve_config
ISSUES_BASE_DIR=$(jq -r '.issues.base_dir // ".issues"' "$LL_CONFIG_FILE" 2>/dev/null || echo ".issues")
```

`ll_resolve_config()` definition (`lib/common.sh:184-191`):
```bash
ll_resolve_config() {
    LL_CONFIG_FILE=""
    if [ -f ".claude/ll-config.json" ]; then
        LL_CONFIG_FILE=".claude/ll-config.json"
    elif [ -f "ll-config.json" ]; then
        LL_CONFIG_FILE="ll-config.json"
    fi
}
```

Note: `session-cleanup.sh:20` has the same hardcoded pattern and doesn't source `common.sh`. Fixing both in one pass is within scope boundaries (aligning config lookup), but the issue's Scope Boundaries section already limits this to `check-duplicate-issue-id.sh` — document `session-cleanup.sh` as a follow-on.

## API/Interface

N/A - No public API changes (shell script internal fix only)

## Integration Map

### Files to Modify
- `hooks/scripts/check-duplicate-issue-id.sh` — add config file fallback

### Similar Patterns
- Other scripts in `hooks/scripts/` that load `ll-config.json` — verify they all use the same fallback pattern and consolidate if not

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Scripts using the canonical `ll_resolve_config()` pattern (to model after):
- `hooks/scripts/user-prompt-check.sh:20` — calls `ll_resolve_config` after sourcing `lib/common.sh:14`
- `hooks/scripts/context-monitor.sh:20-21` — calls `ll_resolve_config` after sourcing `lib/common.sh:14`

Scripts also affected by the same hardcoded pattern (out of current scope):
- `hooks/scripts/session-cleanup.sh:20` — hardcodes `CONFIG_FILE=".claude/ll-config.json"`, does not source `common.sh`

Shared utility:
- `hooks/scripts/lib/common.sh:184-191` — `ll_resolve_config()` function; `lib/common.sh:213-233` — `ll_config_value()` for typed key reads

### Tests
- TBD — test with config at `ll-config.json` vs `.claude/ll-config.json`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_hooks_integration.py:867` — `TestDuplicateIssueId` class covers `check-duplicate-issue-id.sh` with concurrent Write attempts; does **not** currently test config file fallback
- `scripts/tests/test_hooks_integration.py:967` — `TestSharedConfigFunctions` class tests `ll_resolve_config` directly including `test_resolve_config_finds_root_fallback` (line 997); use as model for new test case
- New test needed: `TestDuplicateIssueId` should add a test that places config at `ll-config.json` (not `.claude/ll-config.json`) and verifies `ISSUES_BASE_DIR` is read correctly

### Documentation
- N/A

### Configuration
- N/A

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — registers this script as the `PreToolUse` Write|Edit handler

## Implementation Steps

1. In `hooks/scripts/check-duplicate-issue-id.sh`, replace lines 45-46:
   - Remove: `CONFIG_FILE=".claude/ll-config.json"`
   - Remove: `ISSUES_BASE_DIR=$(jq -r '.issues.base_dir // ".issues"' "$CONFIG_FILE" 2>/dev/null || echo ".issues")`
   - Add: `ll_resolve_config` (the function is already available — `common.sh` is sourced at line 14)
   - Add: `ISSUES_BASE_DIR=$(jq -r '.issues.base_dir // ".issues"' "$LL_CONFIG_FILE" 2>/dev/null || echo ".issues")`
   - Edge case: if `LL_CONFIG_FILE` is empty (neither file exists), `jq` will fail and the `|| echo ".issues"` default is correct

2. Add a test case to `scripts/tests/test_hooks_integration.py:TestDuplicateIssueId`:
   - Model after `test_resolve_config_finds_root_fallback` in `TestSharedConfigFunctions:997`
   - Set up config at `ll-config.json` (not `.claude/ll-config.json`) with a custom `issues.base_dir`
   - Verify the script reads the correct `base_dir` from `ll-config.json`

3. Run `python -m pytest scripts/tests/test_hooks_integration.py::TestDuplicateIssueId -v` to verify

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
- `/ll:ready-issue` - 2026-03-23T23:50:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1f7fbcea-525d-4652-8284-cea6f618964c.jsonl`
- `/ll:confidence-check` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2136e4cf-cc6c-4f72-94b8-567ca85f0bb1.jsonl`
- `/ll:refine-issue` - 2026-03-23T22:58:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/28a4fa2e-a84b-4c4a-a10a-2ed013e02491.jsonl`
- `/ll:format-issue` - 2026-03-23T22:44:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9850963-0ae2-487e-9014-ade593329bce.jsonl`

- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0e087610-8d6c-49f4-bacd-b3c561cb7252.jsonl`

- `/ll:manage-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---

## Resolution

**Status**: Completed 2026-03-23

**Changes made**:
- `hooks/scripts/check-duplicate-issue-id.sh` lines 45–46: replaced hardcoded `CONFIG_FILE=".claude/ll-config.json"` with `ll_resolve_config` call (already available via `common.sh` sourced at line 14), then used `$LL_CONFIG_FILE` for the `jq` lookup
- `scripts/tests/test_hooks_integration.py`: added `test_config_fallback_to_root_ll_config` to `TestDuplicateIssueId` — verifies script reads custom `issues.base_dir` from `ll-config.json` at root

**Verification**: All 3 `TestDuplicateIssueId` tests pass; full suite 3874 passed; `ruff check` clean.

---

**Completed** | Created: 2026-03-23 | Priority: P4
