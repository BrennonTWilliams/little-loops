---
id: ENH-2012
title: "rn-build — Spec file format guide and sample spec"
type: ENH
priority: P3
status: open
parent: EPIC-1811
captured_at: '2026-06-08T01:29:25Z'
discovered_date: 2026-06-08
discovered_by: capture-issue
size: Small
blocked_by:
- FEAT-1992
relates_to:
- FEAT-1990
- FEAT-1992
- ENH-2014
labels:
- loops
- docs
- rn-build
- greenfield
testable: false
---

# ENH-2012: `rn-build` — Spec file format guide and sample spec

## Summary

`rn-build` accepts a Markdown spec file but nowhere documents what a useful spec
looks like. No format guide, no template, and no example spec exist. Users
attempting to run `ll-loop run rn-build path/to/spec.md` have no guidance on
what sections, level of detail, or structure the spec should contain to produce
useful tech research, design artifacts, and feature decomposition downstream.

## Current Behavior

`rn-build` accepts a Markdown spec file path but provides no guidance on what the
spec should contain. No format guide, template, or example spec exists in the
repository. Users must infer the required structure, resulting in specs that are
either too vague for useful research output or too implementation-detailed to
benefit from the design phases.

## Expected Behavior

A `specs/SPEC_TEMPLATE.md` annotated template and a `specs/sample.md` example spec
exist in the repository. The `rn-build` entry in `docs/guides/LOOPS_GUIDE.md`
includes a "Spec file format" subsection pointing to the template and describing
the minimum viable spec (Overview + Core Features + Acceptance Criteria).
`rn-build.yaml`'s description references the template so users discover it from
`ll-loop list`.

## Motivation

The `tech_research`, `design_artifacts`, and `scope_project` states in
`rn-build.yaml` say "analyze the project spec" but the quality of their output
is entirely dependent on the spec quality. Without a format guide, users will
write specs that are too vague (producing shallow research) or too
implementation-detailed (bypassing the design phases). `greenfield-builder` has
the same implicit spec format — this gap predates `rn-build` but `rn-build`'s
deprecation of `greenfield-builder` makes it the right place to fix it.

## Proposed Solution

### 1. `specs/SPEC_TEMPLATE.md`

Create a spec template at the root of the repo with annotated sections:

```markdown
# [Project Name]

## Overview
<!-- 2-4 sentences: what the project does and why it exists. -->

## Core Features
<!-- Bulleted list of top-level capabilities. Each bullet becomes a candidate
     feature issue after scope-epic runs. Aim for 5-15 features. -->

## Data Model (optional)
<!-- Key entities and relationships if known. rn-build will derive these from
     the Overview + Core Features if omitted. -->

## Non-Goals
<!-- What this project explicitly does NOT do. Prevents scope creep during
     rn-implement. -->

## Tech Constraints (optional)
<!-- Required languages, platforms, or libraries. rn-build picks the stack
     autonomously if omitted. -->

## Acceptance Criteria
<!-- High-level observable outcomes. rn-build uses these to configure the
     eval harness (eval_harness phase). At least 2-3 concrete scenarios. -->
```

### 2. `specs/sample.md`

Create a minimal but realistic sample spec that can serve both as a user
reference and as the E2E test fixture for ENH-2014. Suggested project:
a small CLI tool (e.g., a Markdown link checker or a JSON schema validator)
with 4-6 features, 2-3 acceptance criteria, and no hard tech constraints.

### 3. `docs/guides/LOOPS_GUIDE.md` — spec format section

Under the `rn-build` entry in LOOPS_GUIDE, add a "Spec file format" subsection
(~10 lines) pointing to `SPEC_TEMPLATE.md` and covering the minimum viable
spec (Overview + Core Features + Acceptance Criteria are required; all other
sections are optional).

## Implementation Steps

1. Create `specs/SPEC_TEMPLATE.md` with annotated sections (see Proposed Solution)
2. Create `specs/sample.md` — minimal CLI project with 4-6 features, 2-3 AC
3. Add a "Spec file format" subsection to the `rn-build` entry in `docs/guides/LOOPS_GUIDE.md`
4. Update `rn-build.yaml`'s `description:` block to mention `specs/SPEC_TEMPLATE.md`
5. Run `ll-check-links` to verify no broken references

## Integration Map

### Files to Create
- `specs/SPEC_TEMPLATE.md` — annotated spec template for users
- `specs/sample.md` — minimal sample project spec (also serves ENH-2014)

### Files to Modify
- `docs/guides/LOOPS_GUIDE.md` — add spec format subsection under `rn-build` entry
- `scripts/little_loops/loops/rn-build.yaml` — update description to reference `SPEC_TEMPLATE.md`

### Dependent Files (Callers/Importers)
- N/A — new files have no existing callers

### Similar Patterns
- N/A — no analogous spec templates exist in the repo today

### Tests
- `specs/sample.md` doubles as the E2E test fixture for ENH-2014; no additional unit tests required for this issue

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — primary doc change (see Files to Modify above)

### Configuration
- N/A

## Acceptance Criteria

- `specs/SPEC_TEMPLATE.md` exists with all six sections and annotation comments.
- `specs/sample.md` exists with Overview, Core Features (4-6 items), and
  Acceptance Criteria (2-3 scenarios).
- `docs/guides/LOOPS_GUIDE.md` rn-build section includes a "Spec file format"
  subsection linking to `SPEC_TEMPLATE.md`.
- `rn-build.yaml` description references the template.
- `ll-check-links` reports no broken references.

## Scope Boundaries

- No changes to `rn-build.yaml` FSM logic or state transitions (documentation only)
- No new spec validation or linting by the loop runner
- No enforcement — the template is the *ideal input* and normalization target; `rn-build` continues to accept any Markdown file
- Auto-normalization of malformed specs (the pre-gate state that rewrites loose input toward this template) is tracked separately in **ENH-2017** and is blocked on this issue shipping first
- The `specs/sample.md` fixture is created here; ENH-2014 owns the E2E smoke test that uses it

## Impact

- **Priority**: P3 — user-facing gap; no existing rn-build user can know what
  to put in their spec without this
- **Effort**: Small — documentation and template authoring; no logic changes
- **Risk**: Low
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-08

## Session Log
- `/ll:format-issue` - 2026-06-08T01:35:43 - `6443e1b2-a4d1-4257-be1b-aa306b6f46e7.jsonl`
- `/ll:capture-issue` - 2026-06-08T01:29:25Z - `00fefddf-56f7-43f8-8a57-dd53f6c3526d.jsonl`
