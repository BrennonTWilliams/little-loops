---
type: ENH
id: ENH-459
title: Mention ll.local.md during init completion message
priority: P4
status: open
created: 2026-02-22
---

# Mention ll.local.md during init completion message

## Summary

The local override file `.claude/ll.local.md` is a useful feature for per-developer settings (different test commands, scan directories, etc.), but init never mentions it. Users would need to discover it through CLAUDE.md or README.md.

## Current Behavior

The Step 10 completion message does not mention `.claude/ll.local.md`. The local override file is documented in CLAUDE.md and README.md but is invisible to users who only follow the init wizard. It is unclear whether `.claude/ll.local.md` is currently listed in the Step 9 `.gitignore` entries.

## Expected Behavior

The Step 10 completion message includes a line mentioning `.claude/ll.local.md` as the path for personal/local overrides. Step 9 adds `.claude/ll.local.md` to `.gitignore` (since it's intended for per-developer settings).

## Motivation

`.claude/ll.local.md` is a useful feature for developers who have different test commands, scan directories, or preferences than the shared project config. Without init mentioning it, most users never discover it and instead modify the shared `ll-config.json`, which is not ideal for per-developer settings.

## Proposed Solution

Add a line to the Step 10 completion message:

```
Next steps:
  ...
  N. For personal overrides: create .claude/ll.local.md (gitignored)
```

Also consider adding `.claude/ll.local.md` to the `.gitignore` entries in Step 9 if not already present (it should be gitignored by default since it's for personal settings).

## Scope Boundaries

- **In scope**: Adding `.claude/ll.local.md` to Step 9 `.gitignore`; adding a mention to Step 10 completion message
- **Out of scope**: Creating the file during init, adding wizard questions for local settings, documenting the full merge behavior

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — Step 9 (lines ~301-322): add `.claude/ll.local.md` to gitignore block; Step 10 (lines ~324-352): add mention in completion message

### Similar Patterns
- Same pattern as the existing gitignore additions in Step 9

### Tests
- N/A

### Documentation
- N/A — already documented in CLAUDE.md

### Configuration
- N/A

## Implementation Steps

1. Verify whether `.claude/ll.local.md` is already in the Step 9 gitignore block
2. If not present, add `.claude/ll.local.md` to the gitignore entries in Step 9
3. Add a "For personal overrides: create .claude/ll.local.md (gitignored)" line to the Step 10 completion message

## Impact

- **Priority**: P4 — Discovery improvement; no blocking impact
- **Effort**: Small — Two-line addition (gitignore + completion message)
- **Risk**: Low — Additive changes only
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | Documents `.claude/ll.local.md` override mechanism |
| `README.md` | Documents local override file |

## Labels

`enhancement`, `init`, `local-config`, `onboarding`

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`
- `/ll:format-issue` - 2026-02-24 - auto-format batch
- `/ll:verify-issues` - 2026-02-24 - Updated Step 9/10 line references; removed satisfied blocker ENH-453 (completed)

---

## Status

**Open** | Created: 2026-02-22 | Priority: P4

## Blocked By

- ENH-498

- FEAT-440
- FEAT-441
- FEAT-503

## Blocks

- FEAT-488
