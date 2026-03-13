---
discovered_date: 2026-03-12
discovered_by: manual
---

# BUG-680: map-dependencies creates spurious dependencies from file overlap

## Summary

`/ll:map-dependencies` appears to generate false dependency relationships between issues based on shared file references (e.g., both touching `orchestrator.py` or `issue_lifecycle.py`) rather than actual logical blocking relationships. This produces `## Blocked By` / `## Blocks` entries that are semantically incorrect.

## Current Behavior

When `/ll:map-dependencies` analyzes issues, it proposes dependencies based on file overlap — if two issues reference the same files, it infers a dependency. This led to FEAT-638 (session log hook) being marked as blocked by FEAT-565 (skill-based issue alignment) and ENH-665 (feature branch config), neither of which are actual prerequisites.

## Expected Behavior

Dependencies should only be created when there is a genuine logical blocking relationship — i.e., one issue's implementation literally cannot proceed until another is completed. File overlap alone is insufficient; many issues touch the same core files without blocking each other.

## Steps to Reproduce

1. Have multiple issues that reference the same files (e.g., `orchestrator.py`, `issue_lifecycle.py`)
2. Run `/ll:map-dependencies`
3. Observe that dependencies are proposed between unrelated issues solely because they touch the same files

## Evidence

FEAT-638 was blocked by:
- **FEAT-565** (align issues to skills) — completely unrelated functionality, shares no logical dependency
- **ENH-665** (feature branch config for ll-parallel) — changes branch behavior, not completion tracking

Both were likely linked because all three issues reference `orchestrator.py` or `issue_lifecycle.py` in their Integration Map sections. The dependencies were manually removed on 2026-03-12.

## Proposed Investigation

1. Review `/ll:map-dependencies` skill logic to understand how it scores and proposes dependencies
2. Determine whether it uses only file overlap or also considers semantic analysis
3. Identify how to add semantic filtering or a confidence threshold to reduce false positives
4. Consider requiring a brief justification string for each proposed dependency

## Impact

- **Priority**: P3 — false dependencies don't break anything but create confusion and block sprint planning
- **Effort**: Medium — requires understanding the dependency analysis heuristics and improving them
- **Risk**: Low

## Labels

`bug`, `map-dependencies`, `dependency-analysis`

---

## Status

**Open** | Created: 2026-03-12 | Priority: P3
