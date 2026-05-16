---
discovered_commit: 2347db3
discovered_branch: main
discovered_date: 2026-02-10T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-316: `max_continuations` listed under wrong config section in README

## Summary

Documentation issue found by `/ll:audit-docs`. The README Full Configuration Example on line 152 shows `"max_continuations": 3` under the `automation` section, but this property actually belongs under the `continuation` section per `config-schema.json`. The README automation config table (line 271) also lists it under automation.

## Current Behavior

The README shows `max_continuations` under `automation` in two places:
1. Full Configuration Example (line 152): `"max_continuations": 3` inside the `automation` block
2. Automation config table (line 271): row documenting `max_continuations` with default `3`

## Expected Behavior

`max_continuations` should not appear under `automation` in the README. It should appear under a `continuation` block in the Full Configuration Example (matching `config-schema.json` line 424), and be documented in a `continuation` config table section rather than the `automation` table.

## Steps to Reproduce

1. Open `README.md` and find the Full Configuration Example (line 119)
2. Observe `"max_continuations": 3` inside the `automation` block (line 152)
3. Open `config-schema.json` and find the `automation` section (line 145)
4. Note that `max_continuations` is NOT listed in `automation.properties` and `additionalProperties: false` is set (line 178)
5. Find `max_continuations` under `continuation.properties` instead (line 424)

## Actual Behavior

The `max_continuations` key is shown under `automation` but the schema defines it under `continuation.max_continuations`. The `automation` section in config-schema.json has `additionalProperties: false`, so placing `max_continuations` there would cause schema validation to fail or be silently ignored.

## Location

- **File**: `README.md`
- **Line(s)**: 152, 271 (at scan commit: 2347db3)
- **Anchor**: `"automation"` JSON block in Full Configuration Example; `automation` config table
- **Code**:
```json
"automation": {
    "timeout_seconds": 3600,
    "state_file": ".auto-manage-state.json",
    "worktree_base": ".worktrees",
    "max_workers": 2,
    "stream_output": true,
    "max_continuations": 3
}
```

## Proposed Solution

1. Remove `"max_continuations": 3` from the `automation` block in the Full Config Example
2. Remove the `max_continuations` row from the `automation` config table (line 271)
3. Ensure `max_continuations` appears in the `continuation` block of the Full Config Example (which currently isn't shown — add it or reference SESSION_HANDOFF.md)

**Note**: The Python code (`config.py:184`) has `max_continuations` in `AutomationConfig` and accesses it as `config.automation.max_continuations`. This is a separate schema-vs-code discrepancy that may warrant its own issue.

## Impact

- **Priority**: P2
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-10
- **Status**: Completed

### Changes Made
- `README.md`: Removed `max_continuations` from `automation` block in Full Configuration Example
- `README.md`: Added `continuation` block to Full Configuration Example (between `scan` and `context_monitor`)
- `README.md`: Removed `max_continuations` row from `automation` config table
- `README.md`: Added new `#### continuation` config table section with all 7 properties from schema

### Verification Results
- Tests: PASS (2674 passed)
- Lint: PASS (pre-existing issues only, no new issues)
- Types: N/A (documentation-only change)
- Integration: PASS

## Status

**Completed** | Created: 2026-02-10 | Completed: 2026-02-10 | Priority: P2
