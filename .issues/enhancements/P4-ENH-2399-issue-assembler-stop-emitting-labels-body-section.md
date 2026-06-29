---
id: ENH-2399
title: Issue assembler still emits `## Labels` body section for new issues post-ENH-1392
type: enhancement
status: open
priority: P4
discovered_date: 2026-06-29
discovered_by: BUG-2395 reconciliation
relates_to:
- BUG-2395
- ENH-1392
labels:
- issue-template
- assembler
- cleanup
decision_needed: false
---

# ENH-2399: Issue assembler still emits `## Labels` body section for new issues post-ENH-1392

## Summary

ENH-1392 moved labels from a `## Labels` body section into the `labels:`
frontmatter field, and BUG-2395 demoted `Labels.required` to `false` in the
section templates. But the issue assembler still lists `Labels` in
`creation_variants.full.include_common`, so newly created issues still get a
`## Labels` body heading — duplicating the canonical frontmatter location.

## Current Behavior

`scripts/little_loops/issue_template.py` (`assemble_issue_markdown()`) includes
`Labels` via `creation_variants.full.include_common`. New issues are emitted with
both `labels:` frontmatter and a `## Labels` body section. The body section is
now redundant (frontmatter is canonical) and is exactly the deprecated location
`ll-migrate-labels` strips from existing issues.

## Expected Behavior

The assembler does not emit a `## Labels` body section for new issues; labels
live only in `labels:` frontmatter. Remove `Labels` from the relevant
`include_common` list(s) in the section templates / assembler.

## Scope Boundaries

- In scope: assembler `include_common` for `Labels`; corresponding assembly test
  fixtures in `test_issue_template.py`.
- Out of scope: the `required` flag (handled by BUG-2395); migrating existing
  issues (handled by `ll-migrate-labels`).

## Impact

Cosmetic divergence: new issues carry a redundant, deprecated body section.
No functional break — `is_formatted()` and the gate no longer require it after
BUG-2395 — but it perpetuates the inconsistency BUG-2395 was about.

## Status

open
