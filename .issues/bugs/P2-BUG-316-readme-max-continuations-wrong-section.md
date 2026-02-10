---
discovered_commit: 2347db3
discovered_branch: main
discovered_date: 2026-02-10T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-316: `max_continuations` listed under wrong config section in README

## Summary

Documentation issue found by `/ll:audit_docs`. The README Full Configuration Example on line 152 shows `"max_continuations": 3` under the `automation` section, but this property actually belongs under the `continuation` section per `config-schema.json`.

## Location

- **File**: `README.md`
- **Line**: 152
- **Section**: Full Configuration Example, `automation` block

## Current Content

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

## Problem

The `max_continuations` key is shown under `automation` but the schema defines it under `continuation.max_continuations`. The `automation` section in config-schema.json has `additionalProperties: false`, so placing `max_continuations` there would cause schema validation to fail or be silently ignored.

## Expected Content

Remove `max_continuations` from `automation` and ensure it appears in a `continuation` block in the full config example (or reference the SESSION_HANDOFF.md docs).

## Impact

- **Severity**: High (config would fail validation or be silently ignored)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P2
