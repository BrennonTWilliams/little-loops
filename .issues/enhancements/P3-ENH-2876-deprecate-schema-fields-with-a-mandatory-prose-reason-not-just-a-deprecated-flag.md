---
id: 2876
title: Deprecate schema fields with a mandatory prose reason, not just a deprecated flag
type: ENH
parent: EPIC-2872
priority: P3
status: open
discovered_date: 2026-07-27
labels:
- schema
---

# ENH-2876: Deprecate schema fields with a mandatory prose reason, not just a deprecated flag

Origin: ll-product #ENH-060

Parent EPIC: routed alongside this issue — "Self-describing drift and deprecation signals".

## Summary

Issue frontmatter and loop YAML are actively evolving — `superseded_by` recently became derived-and-never-written, and status synonyms are now coerced — and each such change leaves a retired field that agents keep encountering in older files. A deprecation flag alone is not enough to get a model to drop one.

## Reference pattern

In the reference pattern, retiring an axis from a product spec does not simply delete the field or mark it deprecated. A **deprecated-sections map** pairs each retired field with a **prose reason**, and the reason is mandatory. The rationale:

> "told only that a field is deprecated, models preserve it 'just in case', which is how a retired axis keeps steering current output."

The same repo applies the pattern to a retired command as well: rather than removing it, it is deprecated in place and left as an alias that "adds nothing", so existing invocations still land somewhere sane instead of erroring.

## Proposed change

1. Add a deprecated-fields map to little-loops' schema definitions (issue frontmatter first, loop YAML second): each retired key mapped to a one-line prose explanation of what replaced it and why.
2. Surface the reason wherever the schema is read or validated, so an agent encountering a stale field in an old file is told to drop it rather than faithfully carrying it forward.
3. Make the reason a required field of the map — a deprecation entry without one should be a validation error, not an accepted omission.
4. Where a retired key has a direct successor, name the successor in the reason.

## Acceptance criteria

- A retired frontmatter key carries a prose reason at the point of validation, not just a deprecation flag.
- Adding a deprecation entry without a reason fails validation.
- The already-retired cases (`superseded_by` as hand-written, coerced status synonyms) are represented in the map as the first entries.
- An agent reading a file containing a retired key sees the reason in the same output that reports the key.

## Notes

Small and self-contained; no dependency on the other children of this EPIC.
