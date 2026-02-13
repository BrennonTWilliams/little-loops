---
discovered_date: 2026-02-12
discovered_by: plugin-audit
---

# BUG-364: marketplace.json version stuck at 1.6.0 while plugin.json is 1.9.0

## Summary

`.claude-plugin/marketplace.json` declares version `1.6.0` in two places (top-level and plugin entry), while `.claude-plugin/plugin.json` and `pyproject.toml` are both at `1.9.0`. Per the plugins reference: "If also set in the marketplace entry, plugin.json takes priority. You only need to set it in one place."

## Location

- **File**: `.claude-plugin/marketplace.json` (lines 3, 12)

## Current Behavior

Marketplace metadata advertises v1.6.0, which is 3 minor versions behind the actual plugin version. This could cause confusion for users discovering or updating the plugin through the marketplace, and may prevent `claude plugin update` from detecting available updates correctly.

## Expected Behavior

Either:
1. Update both version fields in `marketplace.json` to `1.9.0`
2. Remove the `version` fields from `marketplace.json` entirely, since `plugin.json` takes priority

## Motivation

This bug would:
- Eliminate user confusion from marketplace metadata advertising a version 3 minor versions behind the actual release
- Business value: Ensures users see accurate version information when discovering or updating the plugin
- Technical debt: Prevents potential issues with `claude plugin update` not detecting available updates correctly

## Root Cause

- **File**: `.claude-plugin/marketplace.json` (lines 3, 12)
- **Anchor**: `in version fields`
- **Cause**: The `marketplace.json` version fields were set to `1.6.0` and were never updated during subsequent releases that bumped `plugin.json` and `pyproject.toml` to `1.9.0`

## Implementation Steps

1. Decide whether to update version fields to current version or remove them entirely (since `plugin.json` takes priority)
2. If updating: change both version fields in `marketplace.json` to match `plugin.json` version
3. If removing: delete the `version` fields from `marketplace.json` to avoid future drift
4. Add a release checklist item or automation to keep marketplace version in sync
5. Verify the plugin manifest is valid after changes

## Integration Map

### Files to Modify
- `.claude-plugin/marketplace.json` — update or remove version fields

### Dependent Files (Callers/Importers)
- `.claude-plugin/plugin.json` — source of truth for version

### Similar Patterns
- N/A

### Tests
- N/A (manual verification)

### Documentation
- N/A

### Configuration
- `.claude-plugin/marketplace.json` — version metadata

## Impact

- **Priority**: P3
- **Effort**: Trivial (two-line change)
- **Risk**: Low

## Labels

`bug`, `config`, `plugin-manifest`

## Blocked By

- ENH-319: improve ll-analyze-workflows with 6 enhancements (shared plugin.json)

## Blocks

_None — all downstream issues updated to remove this resolved blocker._

---

## Session Log
- `/ll:format_issue --all --auto` - 2026-02-13

## Verification Notes

- **Verified**: 2026-02-13
- **Verdict**: RESOLVED
- All version files now at `1.10.1`: `marketplace.json` (lines 3, 12), `plugin.json`, `pyproject.toml`
- Version mismatch no longer exists — resolved during subsequent release bumps

## Status

**Resolved** | Created: 2026-02-12 | Resolved: 2026-02-13 | Priority: P3
