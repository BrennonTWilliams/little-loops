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

## Impact

- **Priority**: P3
- **Effort**: Trivial (two-line change)
- **Risk**: Low

## Labels

`bug`, `config`, `plugin-manifest`

## Blocked By

- ENH-319: improve ll-analyze-workflows with 6 enhancements (shared plugin.json)

## Blocks

- ENH-366: add agents directory to plugin.json (shared plugin.json)
- ENH-374: manifest missing agents and hooks declarations (shared plugin.json)
- ENH-279: audit skill vs command allocation (shared plugin.json)

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3
