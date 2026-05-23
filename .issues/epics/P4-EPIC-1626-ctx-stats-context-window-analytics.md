---
id: EPIC-1626
type: epic
status: open
priority: P4
discovered_date: 2026-05-22
discovered_by: manual
labels: [epic, ctx-stats, analytics, tracking]
relates_to: [FEAT-1160, FEAT-1112]
---

# EPIC-1626: ctx-stats — Context Window Analytics Command

## Summary

Umbrella tracking issue for the three-issue decomposition of FEAT-1160
(Context Window Analytics Command). FEAT-1160 closed `done` as the PRD/parent
spec; the actual implementation work was split into a data layer, CLI command,
and docs-wiring pass that share a dependency chain.

This epic exists to give the three open children a live parent and to make
the FEAT-1623 → FEAT-1624 → FEAT-1625 sequence visible to sprint planning,
`ll-deps`, and verify-issues.

## Children

- **FEAT-1623** — ctx-stats Data Layer (schema extension + `post_tool_use.py` hook)
- **FEAT-1624** — ctx-stats CLI Command (`ll-ctx-stats` implementation and tests)
- **FEAT-1625** — ctx-stats Docs and Wiring (config schema, templates, count bumps)

## Motivation

FEAT-1160 specified the `/ll:ctx-stats` feature end-to-end (16 implementation
steps spanning data capture, CLI rendering, config schema, templates, and
~17 enumeration sites). Issue-size review decomposed it into three serially
dependent issues so each can be implemented, reviewed, and merged
independently:

1. **FEAT-1623** lands the data layer (extended `tool_events` columns +
   `post_tool_use.py::handle()` becomes a data-producing writer guarded by
   `analytics.enabled`). Unblocks the CLI.
2. **FEAT-1624** ships the standalone `ll-ctx-stats` command that queries the
   data layer and renders the before/after context-savings view, per-tool
   breakdown, cache metrics, and session time gained.
3. **FEAT-1625** completes the mechanical enumeration pass: docs, config
   schema, all 9 project templates, `commands/help.md`, `areas.md` count
   bump, `skills/init/SKILL.md` allow-lists, and parallel count-assertion
   tests.

FEAT-1160's `parent:` field on each child currently points at a `done` issue
in `.issues/completed/`. This epic adopts the children so the dependency graph
stays consistent while the work is in flight.

## Dependency Chain

```
FEAT-1623 (data layer)
   ↓ depends_on
FEAT-1624 (CLI command)
   ↓ depends_on
FEAT-1625 (docs + wiring)
```

FEAT-1625 has the most file touches but the lowest implementation risk; it
should land last because its count-bump assertions assume the
`ll-ctx-stats` entry point exists.

## Out of Scope

- Implementation of any child issue (each owns its own steps)
- Re-litigation of decisions made in FEAT-1160's PRD
- Adding new analytics surfaces beyond what FEAT-1160 specified
- Wiring `ll-ctx-stats` into `ll-auto` / `ll-parallel` summaries (separate issue)

## Success Criteria

This epic closes when all three children reach `status: done`. The
end-state user experience is:

- `ll-ctx-stats` is installable and runnable from any ll project
- It reports bytes-processed-vs-bytes-in-conversation with percentage
  reduction, per-tool breakdown, prompt cache metrics, and estimated session
  time gained
- `analytics.enabled` config flag gates SQLite writes (default off)
- All 9 templates ship with the analytics key
- `README.md` CLI count, `areas.md` count, and parallel test assertions all
  bumped to reflect the new tool

## Acceptance Criteria

- [ ] All three children have `parent: EPIC-1626` in their frontmatter
- [ ] FEAT-1623 reaches `status: done` (data layer landed)
- [ ] FEAT-1624 reaches `status: done` (`ll-ctx-stats` shipped)
- [ ] FEAT-1625 reaches `status: done` (docs and counts in sync)
- [ ] No open issue references FEAT-1160 as a live parent
- [ ] This epic's status reflects the aggregate state of the children

## Labels

`epic`, `ctx-stats`, `analytics`, `tracking`

## Session Log

- Manually created 2026-05-22 to adopt FEAT-1623 / FEAT-1624 / FEAT-1625
  whose original parent FEAT-1160 closed `done`.

## Status

**Open** | Created: 2026-05-22 | Priority: P4
