---
discovered_date: 2026-01-18
discovered_by: capture_issue
source_log: ~/.claude/debug/be36bcaa-ffd3-47cd-a3c1-f732df22cc69.txt
---

# BUG-092: Missing marketplace.json causes plugin loading error

## Summary

Claude Code looks for a `marketplace.json` file in the plugin cache directory but the file doesn't exist, causing an ENOENT error in debug logs during plugin loading.

## Context

Identified from Claude Code debug log analysis. The error appears during plugin loading but doesn't prevent the plugin from functioning.

**Debug log entry (line 271):**
```
Failed to read raw marketplace.json: Error: ENOENT: no such file or directory,
open '~/.claude/plugins/cache/little-loops/ll/.claude-plugin/marketplace.json'
```

## Current Behavior

When the `ll@little-loops` plugin is loaded, Claude Code attempts to read a `marketplace.json` file at:
```
~/.claude/plugins/cache/little-loops/ll/.claude-plugin/marketplace.json
```

This file doesn't exist, resulting in an error logged to the debug output. The plugin continues to load successfully despite this error (all 22 commands, 8 agents, 3 skills, and hooks load correctly).

## Expected Behavior

Either:
1. The `marketplace.json` file should exist with appropriate metadata, OR
2. Claude Code should gracefully handle missing marketplace.json for non-marketplace plugins without logging an error

## Proposed Solution

**Option A - Add marketplace.json file:**
Create a `.claude-plugin/marketplace.json` file with appropriate metadata:
```json
{
  "name": "ll",
  "displayName": "little-loops",
  "description": "Development workflow toolkit for Claude Code",
  "version": "1.0.0",
  "author": "BrennonTWilliams",
  "repository": "https://github.com/BrennonTWilliams/little-loops"
}
```

**Option B - Investigate if this is a Claude Code bug:**
This may be expected behavior for local plugins vs marketplace plugins. Research whether this error should be suppressed for non-marketplace plugins.

## Impact

- **Priority**: P3 (low - plugin works correctly, just logs an error)
- **Effort**: Low (likely just adding a file)
- **Risk**: Low

## Labels

`bug`, `plugin-config`, `captured`

---

## Status

**Closed - Already Fixed** | Created: 2026-01-18 | Closed: 2026-01-18 | Priority: P3

## Resolution

The `marketplace.json` file was added in commit `f0ed0ed` ("fix: enable GitHub marketplace installation"). The file now exists at `.claude-plugin/marketplace.json` with appropriate metadata. This bug is no longer reproducible.
