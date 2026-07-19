---
id: BUG-2688
title: audit-docs crashes with context_length/concurrent-agent errors on full-scope unscoped file discovery
type: BUG
priority: P2
status: done
labels:
- skills
- audit-docs
- context-budget
testable: false
discovered_date: '2026-07-18'
discovered_by: human
completed_at: '2026-07-19T02:29:32Z'
---

# BUG-2688: audit-docs crashes with context_length/concurrent-agent errors on full-scope unscoped file discovery

## Summary

`/ll:audit-docs full` (and broad `dir:` invocations) crashed with
context_length overflow and/or concurrent-agent API/resource-limit errors
because Phase 1's file discovery swept the entire repository tree instead of
just documentation, and Phase 2's subagent fan-out batching was prose
guidance the executing model could ignore.

## Current Behavior (before fix)

`skills/audit-docs/SKILL.md` Phase 1's `full` case ran:

```bash
find . -name "*.md" -not -path "./.git/*" -not -path "./node_modules/*"
```

In this repo that discovered **3,734 markdown files** — 2,598 of them
`.issues/*` issue-tracker files, 593 `thoughts/*` planning notes, plus a
vendored `.venv` nested under
`.claude/skills/excalidraw-diagram/references/.venv/...` (the
`node_modules` exclude only matched the repo-root path, not nested vendor
dirs). None of these are documentation.

Phase 2 then instructed: "spawn a `codebase-analyzer` subagent... batching
~4–6 `Task` calls per message" — advisory phrasing with no enforced
sequential-wait loop and no ceiling on total file count. Given a
multi-thousand-file discovery list, the fan-out either attempted far more
concurrent `Task` spawns than the API allows, or accumulated thousands of
Task call/result pairs in the orchestrator's own context (even though each
individual subagent result was "compact"), overflowing context.

## Expected Behavior

- `full`/`dir:` scope discovery returns only actual documentation files
  (excludes `.issues/`, `thoughts/`, `.loops/`, `.ll/`, `logs/`,
  `.pytest_cache/`, `.demo/`, plugin components `skills/`/`commands/`/
  `agents/`/`hooks/`, and vendored deps anywhere in the tree).
- Subagent fan-out is a hard-bounded sequential batch loop (≤6 concurrent
  `Task` calls per message, waiting for all results before the next batch),
  not optional guidance.
- When discovery still returns a large file count (>30), the skill asks the
  user to confirm before spawning any subagents, rather than silently
  attempting a huge fan-out.

## Root Cause

- **File**: `skills/audit-docs/SKILL.md`
- **Anchor**: Phase 1 "Find Documentation Files" `find` command (`full`/
  `dir:` cases), and Phase 2 "Audit Each Document (Fan Out to Subagents)"
- **Cause**: The prior fix for this exact symptom class (ENH-2372) moved
  file *reading* out of the orchestrator by fanning out to per-file
  subagents, but never scoped the *discovered file list* itself — `find .
  -name "*.md"` matches every markdown file in the repo, not just
  documentation. Combined with non-enforced "~4-6 per message" batching
  guidance, a large/noisy discovery list translated directly into either a
  concurrent-agent-limit violation or context overflow from the sheer
  number of Task exchanges.

## Proposed Solution (implemented)

Rewrote `skills/audit-docs/SKILL.md`:

1. **Scoped discovery** (Phase 1): added a `DOC_PRUNE` exclude list applied
   to both the `full` and `dir:`/bare-path `find` invocations — excludes
   `.issues/`, `thoughts/`, `.loops/`, `.ll/`, `logs/`, `.pytest_cache/`,
   `.demo/`, `skills/`, `commands/`, `agents/`, `hooks/`, and generalized
   the vendor exclude to `*/node_modules/*`, `*/.venv/*`, `*/venv/*`
   (matches nested vendor dirs, not just repo-root). Drops `full` scope
   discovery in this repo from 3,734 files to 170.
2. **Enforced batch loop** (Phase 2): replaced "batching ~4–6 Task calls per
   message" guidance with an explicit required sequential loop — split into
   batches of at most 6, one batch's `Task` calls per message, wait for all
   results in that batch before sending the next.
3. **Large-scope guard**: added an `AskUserQuestion` confirmation step after
   Phase 1 discovery when the file count exceeds 30, offering to proceed or
   narrow scope with `dir:<subpath>`.

## Integration Map

### Files to Modify
- `skills/audit-docs/SKILL.md` - Phase 1 discovery `find` commands and
  Phase 2 fan-out batching instructions

### Dependent Files (Callers/Importers)
- N/A - Standalone skill, no other file references its internals

### Similar Patterns
- `commands/audit-claude-config.md` referenced as the wave-based subagent
  fan-out pattern this skill already mirrors — no changes needed there

### Tests
- N/A - `skills/*.md` are prompt files, not covered by `pytest`; verified
  manually (see Verification below)

### Documentation
- N/A - No other docs reference the discovery/batching internals

### Configuration
- N/A - No configuration changes needed

## Impact

- **Priority**: P2 - Skill was unusable at `full`/broad `dir:` scope in any
  repo with a non-trivial issue backlog or planning-notes directory
- **Effort**: Small - Prompt-file edit only, no Python changes
- **Risk**: Low - Narrows an existing `find` glob and tightens existing
  fan-out instructions; single-file/`readme` scopes unaffected
- **Breaking Change**: No

## Verification

- Ran the new `find`/`DOC_PRUNE` exclude list locally: `full` scope dropped
  from 3,734 to 170 files, with no `.issues/`, `thoughts/`, `.venv`,
  `skills/`, `commands/`, or `agents/` paths present.
- Read through the full updated `skills/audit-docs/SKILL.md` to confirm the
  batching loop and large-scope guard read as required control flow, not
  advisory phrasing.

## Status

**Done** | Completed: 2026-07-19 | Priority: P2


## Session Log
- `hook:posttooluse-status-done` - 2026-07-19T02:30:05 - `e85d9e54-6d06-4ebd-8f41-c96a7d0aa146.jsonl`
