---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
---

# ENH-496: Progressive Disclosure Convention for Memory Files

## Summary

Formalize a progressive disclosure convention for the persistent memory system: `MEMORY.md` should contain only lightweight identifiers and high-density pointers (≤150 lines), with all detailed notes in separate topic files. This is partially implemented but not enforced or documented.

## Current Behavior

The auto memory system loads `MEMORY.md` from a project-specific directory (e.g., `~/.claude/projects/<project-hash>/memory/MEMORY.md`) into every conversation context. For this project, that directory does not yet exist — no `MEMORY.md` has been created. The 200-line truncation limit is noted in the auto-memory system instructions, but there is no formal convention enforcing how memory files should be structured when they are created (pointer-only index vs. inline details, separate topic files, etc.).

## Expected Behavior

`MEMORY.md` strictly follows a 150-line limit containing:
- Project metadata (1-5 lines)
- A table of contents pointing to topic files (1-2 lines each)
- Critical cross-cutting facts that apply to every session (1-2 lines each)

All detailed notes, patterns, debugging insights, and workflow documentation live in `memory/<topic>.md` files loaded on demand.

## Motivation

Every line in `MEMORY.md` consumes context tokens in every conversation, whether relevant or not. The 3-level loading hierarchy (index → summaries → full data) is the same pattern used in production context engineering systems that achieve 87% token reduction per task. Practicing it in our memory system reduces overhead in every session.

## Proposed Solution

1. Audit current `memory/MEMORY.md` content
2. Extract any section exceeding 3–4 lines into a dedicated topic file
3. Replace extracted content with a 1-line pointer: `- [Topic](memory/topic.md) — one-sentence summary`
4. Document the convention in `CONTRIBUTING.md` or `docs/`
5. Add a note to the auto-memory system instructions enforcing the 150-line limit

## Scope Boundaries

- **In scope**: Restructuring `memory/MEMORY.md` and extracting to topic files; documenting the convention
- **Out of scope**: Changing the auto-memory system behavior, modifying hooks

## Implementation Steps

1. Read `memory/MEMORY.md` to assess current state
2. Identify sections > 3 lines that belong in topic files
3. Create or update `memory/<topic>.md` files with extracted content
4. Replace inline content in `MEMORY.md` with pointer lines
5. Verify `MEMORY.md` is ≤ 150 lines
6. Document convention

## Integration Map

### Files to Modify
- `memory/MEMORY.md` — prune to pointer-only format
- `memory/*.md` — receive extracted content

### Documentation
- `CONTRIBUTING.md` or session instructions — document 150-line convention

## Impact

- **Priority**: P4 — Low urgency; incremental context token savings per session
- **Effort**: Low — Text reorganization only
- **Risk**: Low — Memory files are not code; worst case is slightly less convenient access
- **Breaking Change**: No

## Labels

`enhancement`, `memory`, `context-engineering`, `progressive-disclosure`

## Session Log
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`
- `/ll:verify-issues` - 2026-02-25 - Updated Current Behavior: memory directory does not yet exist for this project; corrected description of what "currently" exists

---

## Status

**Open** | Created: 2026-02-24 | Priority: P4
