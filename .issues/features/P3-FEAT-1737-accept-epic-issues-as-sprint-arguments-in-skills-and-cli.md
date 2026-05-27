---
id: FEAT-1737
type: FEAT
priority: P3
status: open
captured_at: "2026-05-27T05:02:23Z"
discovered_date: "2026-05-27"
discovered_by: capture-issue
---

# FEAT-1737: Accept EPIC Issues as Sprint Arguments in Skills and CLI Commands

## Summary

All `/ll:` skills and `ll-` CLI commands that accept a sprint file as an argument (especially `ll-sprint`) should also accept an EPIC issue ID (e.g., `EPIC-1234`) as an argument, resolving it at runtime to the collection of child issues belonging to that EPIC.

## Motivation

EPICs are already used as organizational containers for related issues via the `parent:` / `relates_to:` relationship. However, to run an EPIC's issues as a batch you currently need to first create a sprint file manually. Accepting EPICs directly as sprint arguments eliminates that friction and makes EPICs a first-class execution unit — the same way sprint files are.

## Expected Behavior

- `ll-sprint EPIC-1234` resolves EPIC-1234's child issues and executes them in dependency order, exactly as if a sprint file listing those issues had been passed.
- Skills that accept a sprint argument (e.g., `/ll:create-sprint`, `/ll:review-sprint`, `/ll:ll-sprint`) recognize an EPIC ID pattern and perform the same resolution.
- Resolution: collect all issues whose `parent: EPIC-NNN` frontmatter matches the given EPIC, filtered to active status (`open`, `in_progress`, `blocked`).
- If the EPIC has no active child issues, print a clear message and exit cleanly rather than silently running an empty set.
- The resolved issue list should respect any dependency ordering already supported by the sprint runner.

## Use Case

A developer wants to work through all open issues under EPIC-1405 (EPIC Type Registration). Instead of generating a sprint file first, they run:

```bash
ll-sprint EPIC-1405
```

The runner resolves the child issues, orders them by dependency/priority, and processes them in sequence.

## Implementation Steps

1. **Add EPIC ID detection** — before treating an argument as a sprint file path, check if it matches `^(EPIC-\d+)$`.
2. **EPIC resolution helper** — implement `resolve_epic_to_issues(epic_id) -> list[IssuePath]` in `scripts/little_loops/` that:
   - Locates the EPIC file via `ll-issues path EPIC-NNN`
   - Reads `relates_to:` and finds all issues with `parent: EPIC-NNN` in their frontmatter
   - Filters to active statuses
   - Returns ordered list (by priority, then dependency graph)
3. **Wire into `ll-sprint`** — in `scripts/little_loops/sprint_runner.py` (or equivalent), call the resolver when an EPIC ID is detected and pass the resulting issue list through the existing pipeline.
4. **Wire into skills** — update any skill that processes sprint arguments (`/ll:create-sprint`, `/ll:review-sprint`) to recognize EPIC IDs and delegate to the resolver.
5. **Error handling** — emit a helpful message when EPIC not found or has no active children.
6. **Tests** — unit test the resolver; integration test `ll-sprint EPIC-NNN` path.

## API/Interface

```python
# New helper (scripts/little_loops/epic_resolver.py or similar)
def resolve_epic_to_issues(epic_id: str) -> list[str]:
    """Return sorted list of active issue IDs belonging to the given EPIC."""
    ...
```

CLI usage (no new flags needed — transparent to the user):

```bash
ll-sprint EPIC-1234          # run all active children of EPIC-1234
ll-sprint .ll/sprints/my-sprint.yaml  # existing sprint file — unchanged behavior
```

## Session Log
- `/ll:capture-issue` - 2026-05-27T05:02:23Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c91edf22-5820-4f59-9f8d-4ab2ca66f171.jsonl`
