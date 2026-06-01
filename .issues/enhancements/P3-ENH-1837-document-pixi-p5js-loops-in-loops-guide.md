---
id: ENH-1837
type: ENH
priority: P3
title: Document pixi/p5js loops in LOOPS_GUIDE.md
status: done
created: 2026-05-31
updated: 2026-05-31
completed_at: '2026-06-01T02:37:39Z'
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

## Resolution

- **Status**: Closed - Already Fixed
- **Fix Commit**: 826f7f87 (`docs(loops-guide): document p5js-sketch-generator, pixi-data-viz, pixi-generative-art`)
- **Notes**: All three loops have table rows in the Built-in Loops "Harness Examples" section and full `### <name>` detail sections (Technique, When to use, Usage, Context variables, FSM flow, Notes). The documentation was added before this issue was filed.


## Session Log
- `/ll:ready-issue` - 2026-06-01T02:37:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cbd1e26c-d15a-4985-b164-6a194c6e9171.jsonl`
