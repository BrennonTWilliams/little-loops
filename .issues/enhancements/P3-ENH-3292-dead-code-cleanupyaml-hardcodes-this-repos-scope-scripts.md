---
id: ENH-3292
type: ENH
title: 'dead-code-cleanup.yaml hardcodes this repo''s scope: ["scripts/"]'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-22'
captured_at: '2026-08-22T19:53:19Z'
labels:
- loops
- gate
- hardcode
- follow-up
relates_to:
- ENH-3281
---

# ENH-3292: dead-code-cleanup.yaml hardcodes this repo's scope: ["scripts/"]

## Summary

`dead-code-cleanup.yaml:8-9` ships `scope: ["scripts/"]` — a this-repo layout default
baked into a generic built-in loop. `scripts/` is this repo's own source directory
(`.claude/CLAUDE.md` § Key Directories); any consuming project without a top-level
`scripts/` directory gets a loop that scopes itself to a path that doesn't exist.

## Current Behavior

`scripts/little_loops/loops/dead-code-cleanup.yaml` declares a hardcoded
`scope: ["scripts/"]` at the top level, guessing this repo's own layout rather than
deriving a project-appropriate scope or defaulting to an empty/override slot.

## Expected Behavior

`dead-code-cleanup.yaml`'s `scope:` should not hardcode `scripts/`. Resolve via a
context-first default (empty override slot) or another project-layout-agnostic
mechanism, consistent with how `context.test_cmd`/`context.lint_cmd` are resolved
elsewhere in the built-in loop corpus (BUG-3276, ENH-3277, ENH-3281).

## Motivation

Flagged during ENH-3281 (generalize the this-repo-hardcode gate across all built-in
loops). `scope:` list entries are deliberately **out of scope** for that gate — they
are not exec-time content in the same sense as a state's `action` body or a top-level
`context:` default (see ENH-3281 § Program Design → Decision Rules) — so this instance
was never caught and needed its own follow-up rather than silently expanding that
gate's scope. ENH-3281 Implementation Step 5 requires this capture.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Scope Boundaries

**In scope**: fixing `dead-code-cleanup.yaml`'s `scope: ["scripts/"]` hardcode.

**Out of scope**: widening ENH-3281's hardcode gate to cover `scope:` entries —
already considered and rejected there (`scope:` entries are not exec-time content).

## Related Key Documentation

- ENH-3281 — generalize the this-repo-hardcode gate; flagged this instance as
  out-of-scope-but-must-capture in its Known Instance section and Implementation Step 5
- BUG-3276 — the original single-loop this-repo-hardcode defect (a different loop,
  `incremental-refactor.yaml`, and a different surface, `context.test_cmd`)

## Status

**Open** | Created: 2026-08-22 | Priority: P3
