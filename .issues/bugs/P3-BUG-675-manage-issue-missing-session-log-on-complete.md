---
discovered_date: 2026-03-11
discovered_by: capture-issue
---

# BUG-675: manage-issue Missing Session Log on Complete

## Summary

The `manage-issue` skill does not append a `## Session Log` entry to the issue file when completing it (moving to `completed/`). This means the Claude Code session JSONL from the actual implementation work is never linked from the completed issue, losing provenance.

## Current Behavior

When `manage-issue` completes an issue and moves it to `.issues/completed/`, no `## Session Log` entry is appended to the issue file. The completed issue has no link back to the session that implemented it.

## Expected Behavior

When `manage-issue` completes an issue, it should append a `## Session Log` entry with the current session JSONL path and ISO timestamp, e.g.:

```markdown
## Session Log
- `/ll:manage-issue` - 2026-03-11T10:00:00Z - `~/.claude/projects/<project>/session.jsonl`
```

This links the completed issue back to the implementation session for traceability.

## Motivation

Session logs are the only way to trace back from a completed issue to the actual conversation and tool calls that implemented it. Without this link, completed issues are disconnected from their implementation history, making it difficult to review decisions, debug regressions, or audit work done by automation (ll-auto, ll-parallel, ll-sprint).

## Steps to Reproduce

1. Run `/ll:manage-issue` on an active issue
2. Let it complete successfully (issue moves to `completed/`)
3. Open the completed issue file
4. Observe: no `## Session Log` section is present

## Root Cause

- **File**: `skills/manage-issue/SKILL.md`
- **Anchor**: Phase 5 completion steps
- **Cause**: The skill instructions do not include a step to append a `## Session Log` entry when moving the issue to `completed/`

## Proposed Solution

Add a step in `manage-issue`'s completion phase (after the `git mv` to `completed/`) that:

1. Finds the current session JSONL (most recent `.jsonl` in `~/.claude/projects/<encoded-project>/`, excluding `agent-*`)
2. Appends a `## Session Log` entry to the completed issue file with timestamp and session path

This is the same pattern already used by `capture-issue` when creating issues.

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md` — add session log step to completion phase

### Dependent Files (Callers/Importers)
- N/A — manage-issue is invoked directly by users or automation

### Similar Patterns
- `skills/capture-issue/SKILL.md` — already appends session log on issue creation (reference implementation)

### Tests
- N/A — skill is prompt-based, not unit-testable

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Read `manage-issue` SKILL.md and locate the completion phase
2. Add a step to append `## Session Log` after moving issue to `completed/`
3. Follow the same session JSONL discovery pattern used by `capture-issue`

## Impact

- **Priority**: P3 - Affects traceability but doesn't block functionality
- **Effort**: Small - Single skill file edit, pattern already exists in capture-issue
- **Risk**: Low - Additive change to skill instructions only
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Skill lifecycle and session management |

## Labels

`bug`, `captured`, `skill`

## Verification Notes

**Verdict: RESOLVED** — The described bug does not exist in the current codebase. The `manage-issue` skill already includes Phase 5, step 1.5 ("Append Session Log Entry") in `skills/manage-issue/SKILL.md:385-389`, with full format documentation in `skills/manage-issue/templates.md:331-340`. This has been present since the skill file was created (commit `d975158`, 2026-02-13). Grep confirms session logs are present across 24+ completed issues.

## Resolution

- **Status**: Resolved (invalid — feature already exists)
- **Verified by**: `/ll:verify-issues`
- **Date**: 2026-03-11

## Session Log
- `/ll:capture-issue` - 2026-03-11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6f09a701-d8cd-451a-aa37-9972ec066ddc.jsonl`
- `/ll:verify-issues` - 2026-03-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e2050bf-957a-4055-a5ee-c894a143d00a.jsonl`

---
## Status
**Resolved** | Created: 2026-03-11 | Priority: P3
