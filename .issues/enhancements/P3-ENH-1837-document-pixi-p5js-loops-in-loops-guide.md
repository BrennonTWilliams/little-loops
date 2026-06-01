---
id: ENH-1837
type: ENH
priority: P3
title: "Document pixi/p5js loops in LOOPS_GUIDE.md"
status: open
created: 2026-05-31
updated: 2026-05-31
---

## Summary

`LOOPS_GUIDE.md` is missing documentation for three loops that exist in
`scripts/little_loops/loops/` but have no table entry or detail section:

- `p5js-sketch-generator` — multi-frame p5.js creative coding harness
- `pixi-data-viz` — animated PixiJS data visualization harness
- `pixi-generative-art` — PixiJS generative art harness

These parallel `svg-image-generator` / `svg-textgrad` in the Harness Examples
category and need both a table row in the Built-in Loops section and a
`### <name>` detail section.

## Context

Found during the `2026-05-31` docs/guides audit. All three YAML files are
fully implemented and runnable; the guide just never had documentation added.

## Acceptance Criteria

- [ ] Each loop has a row in the Built-in Loops table under "Harness Examples"
- [ ] Each loop has a `### <name>` section with: Technique, When to use, Usage,
      Context variables, FSM flow, and Notes (matching the shape of `svg-image-generator`)
- [ ] No other loops are missing from the Built-in Loops table

## Implementation Notes

Reference sections for shape:
- `docs/guides/LOOPS_GUIDE.md` — look at `### svg-image-generator` and
  `### svg-textgrad` for the exact section structure to replicate
- `scripts/little_loops/loops/p5js-sketch-generator.yaml`
- `scripts/little_loops/loops/pixi-data-viz.yaml`
- `scripts/little_loops/loops/pixi-generative-art.yaml`
