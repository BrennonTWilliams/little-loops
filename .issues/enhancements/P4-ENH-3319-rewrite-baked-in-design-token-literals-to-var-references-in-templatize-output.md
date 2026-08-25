---
id: ENH-3319
type: ENH
title: Rewrite baked-in design-token literals to var() references in templatize output
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-25'
captured_at: '2026-08-25T16:04:10Z'
parent: EPIC-3299
labels:
- artifact
- ll-artifact
- templatize
---

# ENH-3319: Rewrite baked-in design-token literals to var() references in templatize output

## Summary

`ll-artifact templatize`'s `_report_unlifted_tokens` (`templatize.py:717-740`)
only *reports* baked-in color literals matching known design tokens
(`unlifted-tokens.json`) — it never rewrites the spliced template body to
reference `var(--...)` / the artifact template kit's stamping unit
(`artifact_template_kit.themed_css_vars`, ENH-3035). File real
literal→`var(--...)` rewriting as its own feature.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

ENH-3035's Decisions (2026-08-25) explicitly rejected doing this as part of
the template-kit extraction: setting `manifest["theme"] = "design-tokens"`
whenever `_report_unlifted_tokens` finds matching literals would stamp
`theme_css` vars into a body that still carries the literals — unreferenced
vars *and* unlifted literals, not token lifting. Real lifting requires
locating each literal's span in the template body and splicing in a
`var(--...)` reference (or an `[[= ll.theme_css =]]`-style stamp point),
which is new feature work, not the extraction ENH-3035 scoped.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Scope

- Design how a baked-in literal is matched back to its owning design-token
  name reliably (today's report only checks value equality against resolved
  tokens, per `report_token_literals()`).
- Splice a reference in place of the literal span, using the same
  span-splicing machinery `templatize.py` already has for extracted-data
  regions (`apply_regions`/`_splice_group`).
- Preserve the byte-exact round-trip guarantee `templatize` promotes under
  today for non-token regions.

## Status

**Open** | Created: 2026-08-25 | Priority: P4
