---
id: ENH-2871
title: manage-issue writes a Deviations note when implementation departs from the
  Program Design section
type: ENH
priority: P3
status: open
discovered_by: split-from-ENH-2852
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
relates_to:
- ENH-2852
- ENH-2870
labels:
- rework
- verification
---

# ENH-2871: manage-issue writes a Deviations note when implementation departs from the Program Design section

Split from ENH-2852 (2026-07-27): the amendment path is independent of the gate itself —
it concerns implementation-time behavior, not refinement-time validation — and can land
before or after the gate is armed.

## Summary

ENH-2852's `## Program Design` section follows an amendment path, not a prohibition: the
implementing agent may deviate from the refine-time design (queue-latency staleness is
real — a design fixed at refine time can be invalidated by codebase changes before
implementation starts), but the deviation must be *recorded* in the issue, never silently
rewritten over the original. Without a writer, that contract is unenforced prose: nothing
in the system would ever produce a `Deviations` note. Give it a writer in
`skills/manage-issue/SKILL.md`.

## Current Behavior

`skills/manage-issue/SKILL.md`'s "Mismatch Handling Protocol" (~L325-331) handles
plan/reality divergence interactively at implementation time but persists nothing
structured to the issue file. There is no existing "Deviations" section or frontmatter
convention anywhere in the codebase (confirmed by ENH-2852's refinement research).

## Expected Behavior

When implementation deviates from the issue's `## Program Design` section (different
signature, different call path, different type shape), `manage-issue` appends a
`Deviations` note under that section stating what changed and why — a new markdown
subsection convention, visible in the issue file — instead of rewriting the original
design or recording nothing. `/ll:reconcile-issue`'s by-design rewriting of directive
sections is unaffected.

## Proposed Change

1. **`skills/manage-issue/SKILL.md`** — extend the Mismatch Handling Protocol (~L325-331,
   the attach point) with an explicit step: when the implemented shape departs from
   `## Program Design`, append (via `Edit`) a `#### Deviations` note under that section
   with a dated entry per deviation: what the design said, what was implemented, and why.
   Never modify the original `Types`/`Signatures`/`Call Path` content.
2. **Format tolerance** — the `Deviations` subsection must not trip ENH-2852's specificity
   grading: grading operates on the `Types`/`Signatures`/`Call Path` subsections and the
   `Call Path` anchor extraction, so an appended prose `Deviations` note is inert to the
   gate. Add a test guarding this (a section that passes the gate still passes with a
   `Deviations` note appended).
3. **Docs** — `docs/reference/ISSUE_TEMPLATE.md`'s `Program Design` entry (added by
   ENH-2852) documents the `Deviations` convention: appended at implementation time,
   original design preserved.

## Acceptance Criteria

- [ ] `skills/manage-issue/SKILL.md` has an explicit step that writes a dated
      `#### Deviations` note under `## Program Design` when implementation departs from
      the recorded design — the convention ships with a writer, not as an unproduced
      section.
- [ ] The step appends; it never rewrites the original `Types`/`Signatures`/`Call Path`
      content.
- [ ] A test asserts a gate-passing `## Program Design` section still passes
      `ll-issues format-check` with a `Deviations` note appended (the note is inert to
      specificity grading).
- [ ] `docs/reference/ISSUE_TEMPLATE.md` documents the `Deviations` convention alongside
      the `Program Design` section entry.

## Scope Boundaries

- **In scope**: the `manage-issue` Deviations-writing step, the grading-inertness test,
  and the `ISSUE_TEMPLATE.md` convention docs.
- **Out of scope**: the gate, grading, grandfathering (ENH-2852); autodev routing and
  stamp arming (ENH-2870); any change to `/ll:reconcile-issue`'s by-design rewriting of
  directive sections.

## Impact

- **Priority**: P3 - the gate functions without it; this closes the "may deviate, but it
  is recorded" contract so refine-time designs stay auditable against what shipped.
- **Effort**: Small - one skill-prose step, one grading-inertness test, one docs entry.
- **Risk**: Low - additive skill instruction; the only interaction with the gate is
  covered by the inertness test.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-07-27 | Priority: P3
