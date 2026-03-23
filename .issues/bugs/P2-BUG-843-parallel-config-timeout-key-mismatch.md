---
discovered_date: 2026-03-22T00:00:00Z
discovered_by: audit-docs
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

## Status

**Open** | Created: 2026-03-22 | Priority: P2
