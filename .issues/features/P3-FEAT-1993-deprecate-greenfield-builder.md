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

## Files to Modify

- `scripts/little_loops/loops/greenfield-builder.yaml` (deprecation banner)
- `scripts/little_loops/loops/README.md`
- `docs/guides/LOOPS_GUIDE.md`
- `CHANGELOG.md`

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

## Status

- **State**: open
- **Created**: 2026-06-06
