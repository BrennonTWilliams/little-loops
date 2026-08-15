---
id: BUG-3189
type: BUG
title: BUILTIN_HOOKS_GUIDE.md omits check-private-refs.sh blocking hook and undercounts
  hook categories
priority: P3
status: done
testable: false
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T17:51:43Z'
completed_at: '2026-08-15T19:31:33Z'
---

# BUG-3189: BUILTIN_HOOKS_GUIDE.md omits check-private-refs.sh blocking hook and undercounts hook categories

## Summary

`/ll:audit-docs` (readme scope, 2026-08-15) found `docs/guides/BUILTIN_HOOKS_GUIDE.md` omits a blocking hook and undercounts several hook categories.

## Current Behavior

- `hooks/scripts/check-private-refs.sh` is a registered, blocking (`exit 2`) PreToolUse hook (`hooks/hooks.json` matcher `Write|Edit`, gates via `ll-verify-private-refs`) that is entirely absent from the Lifecycle table, the PreToolUse section, the hook count ("Five hooks run before a tool executes" at line 199), and the flow diagram — despite the guide's stated scope of covering every blocking hook.
- `session-capture.sh` is listed in the Lifecycle table and referenced once in the PreCompact section, but has no dedicated `###` subsection under `## PostToolUse` documenting its config keys (`session_capture.enabled`) or event schema, unlike every other PostToolUse hook.
- `hooks/hooks.json` registers a third Stop hook and a second SessionEnd hook — both `record-hook-event.sh` (telemetry shim gated by `analytics.enabled` + `analytics.capture.hooks`) — neither documented in the Stop/SessionEnd sections (lines 355-384).
- Line 252: the install-nudge trigger regex list omits `uv add` (says `uv pip install` instead — the actual `_INSTALL_RE` in `scripts/little_loops/hooks/install_learning_gate.py` matches `uv add`) and omits `poetry add` entirely.

## Expected Behavior

The guide documents every registered hook in `hooks/hooks.json`, with accurate counts, and the install-nudge trigger list matches `_INSTALL_RE` exactly.

## Motivation

This guide's stated purpose is "these are the only place little-loops can deny an action outright" for blocking hooks — omitting `check-private-refs.sh` (a real blocking gate) directly contradicts that framing and could cause a contributor to be surprised by a block they didn't know existed.

## Impact

- **Priority**: P3 — doc completeness gap, not a functional bug.
- **Effort**: Small-Medium — add one PreToolUse subsection, one PostToolUse subsection, note the telemetry shims, fix the regex list and hook-count line.
- **Risk**: None — doc-only change.


## Status

**Open** | Created: 2026-08-15 | Priority: P3
