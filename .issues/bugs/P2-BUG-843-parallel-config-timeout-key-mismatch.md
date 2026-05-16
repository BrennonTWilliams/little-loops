---
discovered_date: 2026-03-22T00:00:00Z
discovered_by: audit-docs
confidence_score: 100
outcome_confidence: 100
---

# BUG: Parallel config `timeout_per_issue` key silently ignored

## Summary

`CONFIGURATION.md` and `config-schema.json` document `timeout_per_issue` as the config key for parallel per-issue timeout, but `ParallelAutomationConfig.from_dict` reads `timeout_seconds` — so user-configured values are silently ignored and the default (3600s) is always used.

## Current Behavior

A user who reads the docs or schema and sets:
```json
{
  "parallel": {
    "timeout_per_issue": 7200
  }
}
```
Gets the default 3600s timeout instead. No warning is emitted.

## Expected Behavior

Setting `"timeout_per_issue"` in the `parallel` config section should apply that timeout per issue during parallel processing.

## Steps to Reproduce

1. Add `"timeout_per_issue": 7200` to the `"parallel"` section of `.claude/ll-config.json`
2. Run `ll-parallel` to process issues in parallel
3. Observe: the per-issue timeout is 3600s (the default), not the configured 7200s — no warning is emitted

## Motivation

This bug silently discards user configuration. Any user who reads `CONFIGURATION.md` or `config-schema.json` and sets `timeout_per_issue` gets no feedback that their setting is ignored. It makes the documented interface non-functional and impossible to tune parallel timeouts without editing source code.

## Root Cause

- **File**: `scripts/little_loops/config/automation.py`
- **Anchor**: `ParallelAutomationConfig.from_dict`, line 68
- **Cause**: The code reads `data.get("timeout_seconds", 3600)` for the parallel section, but the documented and schema-defined key is `timeout_per_issue`. The `automation` section uses `timeout_seconds` correctly, and someone copy-pasted that for parallel but the schema/docs use a more descriptive name.

```python
# automation.py line 68 — reads wrong key
base = AutomationConfig(
    timeout_seconds=data.get("timeout_seconds", 3600),  # ← should be "timeout_per_issue"
    ...
)
```

## Proposed Solution

Change `ParallelAutomationConfig.from_dict` to read the documented key:

```python
base = AutomationConfig(
    timeout_seconds=data.get("timeout_per_issue", data.get("timeout_seconds", 3600)),
    ...
)
```

The `data.get("timeout_seconds", ...)` fallback maintains backward-compatibility for any existing configs that might already use `timeout_seconds` directly.

## Integration Map

### Files to Modify
- `scripts/little_loops/config/automation.py` — fix `from_dict` to read `timeout_per_issue`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/config/core.py` — calls `ParallelAutomationConfig.from_dict` (no change needed)
- `scripts/little_loops/cli/parallel.py` — reads `config.parallel.base.timeout_seconds` at runtime (no change needed)

### Similar Patterns
- N/A — single-key fix in one `from_dict` method; no other config sections with documented/code key mismatches identified

### Tests
- `scripts/tests/test_config.py` — add test verifying `timeout_per_issue` key is respected

### Documentation
- N/A — docs and schema are already correct

### Configuration
- `config-schema.json` — already uses `timeout_per_issue` (correct, no change needed)

## Implementation Steps

1. Update `ParallelAutomationConfig.from_dict` to read `timeout_per_issue` (with `timeout_seconds` fallback)
2. Add a test verifying the key is honored

## Impact

- **Priority**: P2 — silent misconfiguration; users cannot override parallel timeout via documented interface
- **Effort**: Tiny (~2 LOC + test)
- **Risk**: Very Low — backward-compatible with fallback
- **Breaking Change**: No

## Labels

`bug`, `configuration`, `parallel`

## Resolution

**Fixed** in `scripts/little_loops/config/automation.py` — `ParallelAutomationConfig.from_dict` now reads `timeout_per_issue` first, falling back to `timeout_seconds` for backward compatibility.

**Tests added** in `scripts/tests/test_config.py` — three new cases verifying `timeout_per_issue` is respected, the `timeout_seconds` fallback works, and `timeout_per_issue` takes precedence when both keys are present.

## Status

**Completed** | Created: 2026-03-22 | Resolved: 2026-03-23 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-03-23T17:04:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/70acc466-5948-445b-ba9e-e29a96cf4fe3.jsonl`
- `/ll:format-issue` - 2026-03-23T16:58:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/06fdc033-986b-4b59-b280-3505ad02d65c.jsonl`
- `/ll:confidence-check` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a7e8878-823c-4c12-8f4f-537e18afd73d.jsonl`
- `/ll:manage-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
