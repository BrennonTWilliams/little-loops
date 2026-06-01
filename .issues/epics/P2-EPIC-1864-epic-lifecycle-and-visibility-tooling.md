---
id: EPIC-1864
title: EPIC Lifecycle & Visibility Tooling
type: EPIC
priority: P2
status: open
discovered_date: 2026-06-01
discovered_by: link-epics
labels: [epic, epics, cli, skill, lifecycle, captured]
relates_to: [FEAT-1855, FEAT-1856, FEAT-1857, ENH-1858, ENH-1859, ENH-1860, ENH-1863, ENH-1866]
---

# EPIC-1864: EPIC Lifecycle & Visibility Tooling

## Summary

Add first-class tooling for managing EPICs as living containers throughout their lifecycle. The six children cover: progress aggregation (rollup of child status into %-done and blocked counts), health auditing (`/ll:review-epic`), theme decomposition (`/ll:scope-epic`), dependency tree rendering (`ll-deps tree --epic`), sprint–EPIC critical-path awareness, and cascade lifecycle (close/cancel propagating to children).

Together these close the gap between EPICs as static tracking issues and EPICs as actionable, queryable containers that give users real-time visibility into initiative progress.

## Motivation

EPICs are first-class containers (FEAT-1389, FEAT-1407) and can be dispatched as sprints (FEAT-1737), but they have no built-in visibility or lifecycle tooling. As the number of active EPICs grows (13+ at capture time), the cost of manually answering "how is this initiative going?" compounds. Each child issue captures one dimension of that gap.

## Children

- **FEAT-1855** — EPIC progress aggregation (% done / blocked rollup)
- **FEAT-1856** — `/ll:review-epic` skill — stalled-children and scope-drift audit
- **FEAT-1857** — `/ll:scope-epic` — theme-to-EPIC decomposition skill
- **ENH-1858** — `ll-deps tree --epic EPIC-NNN` — render EPIC child hierarchy with dependency edges
- **ENH-1859** — `/ll:review-sprint` EPIC awareness — flag sprints that bypass EPIC critical path
- **ENH-1860** — EPIC cascade lifecycle — propagate close/cancel to children
- **ENH-1863** — `format_epic_tree()` rendering engine for EPIC child hierarchy
- **ENH-1866** — `ll-deps tree` CLI command, tests, and docs

## Scope

### In scope

- New CLI subcommand `ll-issues epic-progress` (FEAT-1855)
- New skill `skills/review-epic/` (FEAT-1856)
- New skill `skills/scope-epic/` (FEAT-1857)
- New `ll-deps tree --epic` subcommand (ENH-1858)
- EPIC-context audit phase in `/ll:review-sprint` (ENH-1859)
- `--cascade` flag on `ll-issues set-status` (ENH-1860)

### Out of scope

- Changes to the EPIC file format itself
- EPIC creation (covered by `/ll:capture-issue`)
- Automated EPIC status promotion

## Implementation Order

1. **FEAT-1855** (`epic-progress`) first — provides the `compute_epic_progress()` pure function that FEAT-1856, ENH-1858, and ENH-1859 reuse.
2. **FEAT-1856** (`review-epic`) — depends on FEAT-1855 aggregation.
3. **ENH-1858** (`ll-deps tree`) — depends on FEAT-1855 resolution path.
4. **ENH-1859** (sprint EPIC awareness) — depends on FEAT-1855 resolution.
5. **FEAT-1857** (`scope-epic`) and **ENH-1860** (cascade) — independent; can land in any order.

## Success Metrics

- All 6 children reach `status: done`.
- `ll-issues epic-progress EPIC-NNN` returns a progress bar and status breakdown in < 1s.
- `/ll:review-epic` flags at least one stale child in the existing backlog on first run.

## Labels

`epic`, `epics`, `cli`, `skill`, `lifecycle`, `captured`

## Status

**Open** | Created: 2026-06-01 | Priority: P2
