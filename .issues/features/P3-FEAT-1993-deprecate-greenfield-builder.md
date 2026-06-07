---
id: FEAT-1993
title: "Deprecate greenfield-builder in favor of rn-build"
type: FEAT
priority: P3
status: open
parent: FEAT-1990
captured_at: '2026-06-06T00:00:00Z'
discovered_date: 2026-06-06
discovered_by: capture-issue
size: Small
testable: false
blocked_by: [FEAT-1992]
relates_to:
- FEAT-1990
- FEAT-1992
labels:
- loops
- deprecation
- greenfield
---

# FEAT-1993: Deprecate `greenfield-builder` in favor of `rn-build`

## Summary

Mark `greenfield-builder` deprecated now that `rn-build` (FEAT-1992) supersedes
it. Keep the loop file present for one release so users can A/B the two builders,
but steer all docs, the wizard, and the catalog toward `rn-build`.

## Current Behavior

`greenfield-builder` is the active loop for spec-driven greenfield project
creation. No deprecation marker is present on the loop file. All documentation,
the `create-loop` wizard, and the loop catalog reference `greenfield-builder` as
the recommended tool for new projects. `rn-build` exists (post-FEAT-1992) but
nothing steers users toward it.

## Expected Behavior

`greenfield-builder.yaml` carries a deprecation signal (banner and/or
`deprecated: true` flag) pointing users to `rn-build`. The `create-loop` wizard
steers greenfield/spec-driven projects to `rn-build`. Documentation and README
include a migration note. `greenfield-builder` still validates and runs (one-
release grace period — not deleted). `ll-check-links` reports no broken links.

## Motivation

`rn-build` (FEAT-1992) delivers a recursive `rn-implement`-based build loop with
goal-cluster context propagation and value-ranked scheduling — capabilities
`greenfield-builder` lacks. Continuing to surface `greenfield-builder` as the
primary tool leaves users unaware of its superior replacement and creates the
maintenance burden of two functionally overlapping loops. Deprecation consolidates
the ecosystem around the stronger builder.

## Use Case

A developer opens the `create-loop` wizard to start a new React Native project
from a spec file. Before this change they are offered `greenfield-builder`; after,
they see `rn-build` as the recommended choice, with a note that `greenfield-builder`
is deprecated and scheduled for removal in a future release.

## Parent Issue

Decomposed from FEAT-1990: `rn-build` — Recursive Spec-to-Project Builder.

## Prerequisites

FEAT-1992 (`rn-build.yaml`) merged, so the deprecation can point at a real
successor.

## Proposed Solution

1. **Deprecation banner in the loop.** Add a `DEPRECATED:` prefix line to
   `greenfield-builder.yaml`'s `description` block pointing to `rn-build`, and a
   first-state notice (or `deprecated: true` top-level flag if the schema/runner
   supports it — verify in `ll-loop validate`; otherwise description-only).
2. **Docs migration note.** In `docs/guides/LOOPS_GUIDE.md`, add a
   "greenfield-builder → rn-build migration" note explaining the differences
   (recursive `rn-implement` vs `eval-driven-development`; `goal-cluster` context
   propagation; value-ranked scheduling) and that `greenfield-builder` will be
   removed in a future release.
3. **README.** Update `scripts/little_loops/loops/README.md` to mark
   `greenfield-builder` deprecated and cross-link `rn-build`.
4. **Wizard.** Ensure `skills/create-loop/` steers users to `rn-build` for
   greenfield/spec-driven projects (coordinate with FEAT-1994 so the two don't
   conflict).
5. **CHANGELOG.** Add a deprecation entry under the concrete release section
   (NOT `[Unreleased]`).

## Implementation Steps

1. Verify whether `ll-loop validate` supports a `deprecated: true` top-level flag
   in loop YAML schema; document finding in Open Questions
2. Add deprecation banner/flag to `greenfield-builder.yaml`
3. Update `docs/guides/LOOPS_GUIDE.md` with migration note and differences table
4. Update `scripts/little_loops/loops/README.md` to mark `greenfield-builder` deprecated
5. Steer `skills/create-loop/` wizard toward `rn-build` for greenfield projects (coordinate with FEAT-1994)
6. Add CHANGELOG deprecation entry under a concrete release section
7. Run `ll-check-links` to verify no broken links

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/greenfield-builder.yaml` (deprecation banner/flag)
- `scripts/little_loops/loops/README.md` (deprecated marker + cross-link)
- `docs/guides/LOOPS_GUIDE.md` (migration note)
- `CHANGELOG.md` (deprecation entry)
- `skills/create-loop/` (wizard steering toward `rn-build`)

### Dependent Files (Callers/Importers)
- N/A — loop files are invoked directly by users; no programmatic callers to update

### Similar Patterns
- N/A — no other deprecated loops to mirror pattern from

### Tests
- N/A — loop YAML deprecation has no unit test path; `ll-loop validate` serves as the verification step

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — needs migration note
- `scripts/little_loops/loops/README.md` — needs deprecation cross-link

### Configuration
- N/A

## Acceptance Criteria

- `greenfield-builder.yaml` clearly signals deprecation and names `rn-build` as
  the successor.
- `greenfield-builder` still validates and runs (one-release grace period — not
  deleted).
- Docs and README direct new users to `rn-build`.
- No broken links introduced (`ll-check-links`).

## Open Questions

1. Does the loop schema/runner support a `deprecated: true` top-level flag, or is
   deprecation description-only? Verify before authoring.

## Impact

- **Priority**: P3 — housekeeping deprecation; no user is blocked, but consolidation reduces confusion
- **Effort**: Small — text changes to YAML description, docs, and wizard; no logic changes
- **Risk**: Low — `greenfield-builder` remains functional throughout the grace period
- **Breaking Change**: No (grace period — loop still validates and runs)

## Status

**Open** | Created: 2026-06-06 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-07T01:11:59 - `ddd29df3-8b21-4e25-9cb4-e990152c90f5.jsonl`
