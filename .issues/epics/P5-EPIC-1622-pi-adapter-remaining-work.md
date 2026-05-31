---
id: EPIC-1622
title: Pi adapter — remaining work
type: epic
status: open
priority: P5
discovered_date: 2026-05-22
discovered_by: verify-issues
labels: [epic, pi-adapter, tracking]
relates_to: [FEAT-992, FEAT-1474, FEAT-1477]
---

# EPIC-1622: Pi adapter — remaining work

## Summary

Umbrella tracking issue for the five open Pi-adapter children whose original
parent issues (FEAT-992, FEAT-1474, FEAT-1477) all closed `done` while child
work remained open. Captured by `/ll:verify-issues` on 2026-05-22.

This epic exists purely to give the still-open work a live parent. No new
scope is added here — each child issue is the authoritative spec for its own
work.

## Children

- **FEAT-1475** — Pi Adapter Init Skill (`/ll:init --pi` support)
- **FEAT-1476** — Pi Adapter Documentation
- **FEAT-1478** — Pi Adapter TypeScript Adapter and Integration Test
- **FEAT-1479** — Pi Adapter Config Candidate, Schema, and Config Tests
- **FEAT-1480** — Wire `PiRunner` and Host Runner Tests

## Motivation

The Pi adapter sub-tree had three parent issues:

- **FEAT-992** — the original "add Pi coding-agent plugin compatibility" epic
- **FEAT-1474** — Pi Adapter Core (TypeScript adapter, config schema, tests)
- **FEAT-1477** — Pi Adapter Python Backend (config, host runner, schema, tests)

All three closed `done` before the decomposed child work landed. The five
children listed above continued referencing those closed parents in their
`parent:` frontmatter, creating dependency rot that confuses `ll-deps`,
sprint planning, and verify-issues runs.

This epic adopts the orphans so the dependency graph is consistent.

## Out of Scope

- Implementation of any child issue (each owns its own implementation steps)
- Re-litigation of decisions made in FEAT-992, FEAT-1474, or FEAT-1477
- Adding new Pi adapter scope beyond the five children

## Success Criteria

This epic closes when all five children reach `status: done` (or are
explicitly closed/deferred with rationale recorded in their own files).

## Acceptance Criteria

- All five children have `parent: EPIC-1622` in their frontmatter
- No open issue references FEAT-992, FEAT-1474, or FEAT-1477 as a live parent
- This epic's status reflects the aggregate state of the children

## Labels

`epic`, `pi-adapter`, `tracking`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-05-31T02:30:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`

- `/ll:verify-issues` - 2026-05-22 - created by verify-issues to re-parent orphaned Pi-adapter children

## Status

**Open** | Created: 2026-05-22 | Priority: P5
