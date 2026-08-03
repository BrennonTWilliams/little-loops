---
id: ENH-3015
title: CONFIGURATION.md has no documentation section for the top-level cache block
type: ENH
status: open
priority: P4
discovered_date: 2026-08-02
discovered_by: multi-agent-audit
parent: EPIC-3008
depends_on:
- BUG-3009
program_design_not_applicable: true
testable: false
labels:
- docs
- config-schema
---

# ENH-3015: `CONFIGURATION.md` has no documentation section for the top-level `cache` block

## Summary

`docs/reference/CONFIGURATION.md` documents nearly every top-level
`config-schema.json` section, but the `cache` block (`config-schema.json:643-654`,
`require_repeat`) has zero coverage — the only top-level schema section
entirely undocumented there.

## Current Behavior

Searching `docs/reference/CONFIGURATION.md` for a `### \`cache\`` heading or
`require_repeat` returns no matches, even though `cache` is fully parsed into
`BRConfig` (`config/core.py:260, 349-351`) and documented (via docstring) as a
config knob in `host_runner.py:1700-1702`.

## Scope Boundaries

In scope: adding a `### \`cache\`` section to `CONFIGURATION.md`. Out of
scope: fixing the underlying wiring gap (tracked separately as BUG-3009).

**Sequencing: `depends_on: [BUG-3009]`** (now declared in frontmatter, not just
prose). This section must state *where* `require_repeat` takes effect, and until
BUG-3009 lands the honest answer is "nowhere — the key is currently inert."
Writing this section first would ship a doc that is wrong the moment BUG-3009
merges, or wrong today. Land BUG-3009 first, then document the real call site.

Note also that both this issue and ENH-3014 edit `docs/reference/CONFIGURATION.md`.
They touch different sections (`cache` vs. `skill_budget`), so they are safe to
run concurrently, but a merge conflict in the section index/TOC is possible.

## Expected Behavior

`CONFIGURATION.md` should include a `### \`cache\`` section describing
`require_repeat` (purpose, default, effect), consistent with the documentation
depth given to every other top-level section.

## Suggested Fix Direction

Add the missing section to `CONFIGURATION.md`, following the existing format
used by neighboring sections (e.g. `deferred_tools`, which is documented).
Cross-reference BUG-3009 in this same epic — once that bug is fixed, this
section should also note where `require_repeat` actually takes effect
(`fsm/executor.py` dispatch).

## Status

**Open** | Created: 2026-08-02 | Priority: P4

## Impact

- **Priority**: P4 — docs-only gap.
- **Effort**: Small.
- **Risk**: None.
- **Breaking Change**: No.
