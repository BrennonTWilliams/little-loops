---
type: ENH
id: ENH-459
title: Mention ll.local.md during init completion message
priority: P4
status: open
created: 2026-02-22
confidence_score: 90
outcome_confidence: 88
---

# Mention ll.local.md during init completion message

## Summary

The local override file `.ll/ll.local.md` is a useful feature for per-developer settings (different test commands, scan directories, etc.), but init never mentions it. Users would need to discover it through CLAUDE.md or README.md.

## Current Behavior

The Step 10 completion message does not mention `.ll/ll.local.md`. The local override file is documented in CLAUDE.md and README.md but is invisible to users who only follow the init wizard. It is unclear whether `.ll/ll.local.md` is currently listed in the Step 9 `.gitignore` entries.

## Expected Behavior

The Step 10 completion message includes a line mentioning `.ll/ll.local.md` as the path for personal/local overrides. Step 9 adds `.ll/ll.local.md` to `.gitignore` (since it's intended for per-developer settings).

## Motivation

`.ll/ll.local.md` is a useful feature for developers who have different test commands, scan directories, or preferences than the shared project config. Without init mentioning it, most users never discover it and instead modify the shared `ll-config.json`, which is not ideal for per-developer settings.

## Proposed Solution

Add a line to the Step 10 completion message:

```
Next steps:
  ...
  N. For personal overrides: create .ll/ll.local.md (gitignored)
```

Also consider adding `.ll/ll.local.md` to the `.gitignore` entries in Step 9 if not already present (it should be gitignored by default since it's for personal settings).

## Scope Boundaries

- **In scope**: Adding `.ll/ll.local.md` to Step 9 `.gitignore`; adding a mention to Step 10 completion message
- **Out of scope**: Creating the file during init, adding wizard questions for local settings, documenting the full merge behavior

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — Step 9 (lines ~301-322): add `.ll/ll.local.md` to gitignore block; Step 10 (lines ~324-352): add mention in completion message

### Similar Patterns
- Same pattern as the existing gitignore additions in Step 9

### Tests
- N/A

### Documentation
- N/A — already documented in CLAUDE.md

### Configuration
- N/A

## Implementation Steps

1. Verify whether `.ll/ll.local.md` is already in the Step 9 gitignore block
2. If not present, add `.ll/ll.local.md` to the gitignore entries in Step 9
3. Add a "For personal overrides: create .ll/ll.local.md (gitignored)" line to the Step 10 completion message

## Impact

- **Priority**: P4 — Discovery improvement; no blocking impact
- **Effort**: Small — Two-line addition (gitignore + completion message)
- **Risk**: Low — Additive changes only
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | Documents `.ll/ll.local.md` override mechanism |
| `README.md` | Documents local override file |

## Labels

`enhancement`, `init`, `local-config`, `onboarding`

## Session Log
- `/ll:verify-issues` - 2026-04-03T02:58:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b02a8b8-608b-4a1c-989a-390b7334b1d4.jsonl`
- `/ll:verify-issues` - 2026-04-01T17:45:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/712d1434-5c33-48b6-9de5-782d16771df5.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`
- `/ll:format-issue` - 2026-02-24 - auto-format batch
- `/ll:verify-issues` - 2026-02-24 - Updated Step 9/10 line references; removed satisfied blocker ENH-453 (completed)
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Confirmed: Step 9 (lines 301-323) currently adds only .auto-manage-state.json, .parallel-manage-state.json, .ll/ll-context-state.json, .ll/ll-sync-state.json to .gitignore — `.ll/ll.local.md` is NOT present and needs to be added
- `/ll:refine-issue` - 2026-03-03 - Batch re-assessment: no new knowledge gaps; research findings from 2026-02-25 remain current
- `/ll:refine-issue` - 2026-03-03T23:10:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` - Related Key Docs already present; no changes needed
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl` — VALID: `.ll/ll.local.md` still absent from Step 9 gitignore; removed stale Blocks ref ENH-587 (completed)
- `/ll:confidence-check` - 2026-03-06 - Verified: `skills/init/SKILL.md` Step 9 gitignore block confirmed — `.ll/ll.local.md` absent (only `.auto-manage-state.json`, `.parallel-manage-state.json`, `.ll/ll-context-state.json`, `.ll/ll-sync-state.json` present). Step 10 completion message confirmed to not mention `ll.local.md`. Issue is minimal scope (two-line addition), fully specified with exact target lines. Scored confidence_score=90, outcome_confidence=88.
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: still missing from gitignore and completion message
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: `.ll/ll.local.md` still absent from Step 9 gitignore and Step 10 completion message
- `/ll:verify-issues` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9511adcf-591f-4199-b7c1-7ff5d368c8f0.jsonl` — VALID: removed completed FEAT-488 from Blocks

---

## Verification Notes

- **Date**: 2026-04-02
- **Verdict**: NEEDS_UPDATE
- ENH-493 is now COMPLETED (in `completed/`) — removed from Blocked By. Issue is now unblocked.
- `.ll/ll.local.md` still absent from init SKILL.md. Enhancement not yet applied.

## Status

**Open** | Created: 2026-02-22 | Priority: P4


## Blocked By

## Blocks
