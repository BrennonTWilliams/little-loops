---
id: BUG-876
discovered_date: 2026-03-24
discovered_by: capture-issue
---

# BUG-876: Display Timing Bug When Running in External Project

## Summary

A display timing bug occurs when little-loops is run in a project other than its own repository on this machine. The exact manifestation is unknown pending investigation, but the bug was observed during real-world use of little-loops as a plugin in another project.

## Current Behavior

Display output exhibits incorrect timing behavior when little-loops CLI tools or commands are executed from a different project's working directory on this machine.

## Expected Behavior

little-loops should display output with correct timing regardless of which project it is invoked from.

## Motivation

little-loops is designed to be used across projects. If display timing is broken in external-project contexts, it degrades the experience for all users who are not developing little-loops itself — the primary intended use case.

## Steps to Reproduce

1. Install little-loops in a separate project (not the little-loops repo itself)
2. Run one of the little-loops CLI tools (e.g., `ll-auto`, `ll-parallel`, `ll-sprint`) from that project
3. Observe: display output has incorrect timing (e.g., progress updates, spinners, or output appears too early/late or in wrong sequence)

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A

## Implementation Steps

1. Reproduce the bug in an external project on this machine
2. Identify the display/timing code path responsible (likely in `scripts/little_loops/display.py` or similar)
3. Determine if the bug is path-dependent, environment-dependent, or timing-related in the Python runtime
4. Fix and add regression test
5. Verify fix works in both external-project and internal contexts

## Impact

- **Priority**: P3 - Affects real-world external-project use; not blocking but degrades core UX
- **Effort**: Small/Medium - Scope unknown until reproduced; likely isolated to display layer
- **Risk**: Low - Display code is unlikely to have broad side effects
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `display`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f7b65b55-cf2f-4329-bd1e-bb86516edd27.jsonl`

---

**Open** | Created: 2026-03-24 | Priority: P3
