---
id: ENH-1824
title: Document p5js-sketch-generator, pixi-data-viz, and pixi-generative-art in LOOPS_GUIDE.md
type: ENH
priority: P3
captured_at: '2026-05-31T00:00:00Z'
discovered_date: '2026-05-31'
discovered_by: audit-docs
status: open
labels:
- enhancement
- documentation
- loops
---

# ENH-1824: Document p5js-sketch-generator, pixi-data-viz, and pixi-generative-art in LOOPS_GUIDE.md

## Summary

Three built-in harness loops exist in `scripts/little_loops/loops/` but have no entries in `docs/guides/LOOPS_GUIDE.md`: `p5js-sketch-generator`, `pixi-data-viz`, and `pixi-generative-art`. They parallel `svg-image-generator` and `svg-textgrad` in the Harness Examples category and need both a table row in the Built-in Loops table and a `### <name>` detail section.

## Current Behavior

Running `ll-loop list` shows all three loops as available. The Harness Examples section of the Built-in Loops table (LOOPS_GUIDE.md line 1018) lists only `svg-image-generator` and `svg-textgrad`. No `### p5js-sketch-generator`, `### pixi-data-viz`, or `### pixi-generative-art` sections exist anywhere in the guide.

## Expected Behavior

LOOPS_GUIDE.md contains:

1. **Table rows** in the Harness Examples section of the Built-in Loops table:
   - `p5js-sketch-generator` — Generator-evaluator harness for p5.js creative coding sketches (multi-frame screenshots, deterministic seeding, GAN-style architecture)
   - `pixi-data-viz` — Generator-evaluator harness for animated PixiJS data visualizations
   - `pixi-generative-art` — Generator-evaluator harness for PixiJS generative art sketches

2. **Detail sections** (`### <name>`) for each loop, following the same structure as `### svg-image-generator` and `### svg-textgrad`:
   - **Technique** — how the loop works (GAN-style, multi-frame capture, etc.)
   - **When to use** — differentiation from related harnesses
   - **Usage** — `ll-loop run <name> "description"` example
   - **Context variables** table (same columns as svg-image-generator: Variable / Default / Description)
   - **FSM flow** — state sequence description
   - **Notes** — tips, caveats, customization

## Motivation

Discovered during 2026-05-31 docs audit. Users and Claude Code itself cannot discover these loops from the guide; `ll-loop list` is the only discovery path. The loops have the same architecture as the documented SVG harnesses and merit the same treatment.

## Proposed Solution

1. Add three rows to the Harness Examples table (after the `svg-textgrad` row, ~line 1030).
2. Add three `### <name>` sections after `### svg-textgrad` (~line 1338), each following the six-block structure (Technique, When to use, Usage, Context variables, FSM flow, Notes).
3. Source content from the loop YAML files:
   - `scripts/little_loops/loops/p5js-sketch-generator.yaml` — `description:`, `context:` block, `states:` comments
   - `scripts/little_loops/loops/pixi-data-viz.yaml`
   - `scripts/little_loops/loops/pixi-generative-art.yaml`

Key differentiators to call out in each section:
- **p5js-sketch-generator**: multi-frame screenshots at deterministic frameCounts (sample_frames context var); motion evaluated, not just composition; p5.js loaded from CDN; `pass_threshold` per criterion.
- **pixi-data-viz**: synthetic-but-plausible data embedded inline; evaluates whether motion *aids* comprehension; PixiJS GPU-accelerated renderer.
- **pixi-generative-art**: GPU-accelerated idioms (filters, masks, blends); rewards Pixi-distinctive patterns over p5.js conventions.

## Success Metrics

- [ ] `docs/guides/LOOPS_GUIDE.md` Built-in Loops table includes rows for all three loops
- [ ] Three `### <name>` detail sections added, each with Technique, When to use, Usage, Context variables, FSM flow, and Notes blocks
- [ ] `ll-verify-docs` (if it checks loop counts) passes without changes
- [ ] No broken markdown links introduced

## Scope Boundaries

- Documentation only — no changes to the loop YAML files.
- No changes to other guide files unless a cross-reference is needed.
- Do not restructure the Harness Examples section; append new rows/sections after existing ones.

## Implementation Steps

1. Read `scripts/little_loops/loops/p5js-sketch-generator.yaml`, `pixi-data-viz.yaml`, `pixi-generative-art.yaml` to extract descriptions, context variables, and FSM state names.
2. Read `docs/guides/LOOPS_GUIDE.md` around lines 1018–1035 (table) and 1282–1415 (svg-image-generator / svg-textgrad sections) to understand exact format.
3. Add three table rows in the Harness Examples section.
4. Add three detail sections following the `### svg-textgrad` section, using content from the YAML files.
5. Run `ll-check-links docs/guides/LOOPS_GUIDE.md` to verify no broken links.

## Integration Map

### Files to Modify
- `docs/guides/LOOPS_GUIDE.md` — add table rows (~line 1031) and three `### <name>` sections (~line 1415+)

### Reference Files (Read Only)
- `scripts/little_loops/loops/p5js-sketch-generator.yaml`
- `scripts/little_loops/loops/pixi-data-viz.yaml`
- `scripts/little_loops/loops/pixi-generative-art.yaml`
- `docs/guides/LOOPS_GUIDE.md` lines 1282–1415 (svg-image-generator / svg-textgrad as format template)

## Impact

- **Priority**: P3 — affects discoverability of three production-ready loops
- **Effort**: Small-Medium — content exists in YAML files; writing follows a clear template
- **Risk**: Low — documentation only; no code changes
- **Breaking Change**: No

## Verification Notes

**Verdict**: VALID — verified 2026-05-31

- `scripts/little_loops/loops/p5js-sketch-generator.yaml`, `pixi-data-viz.yaml`, `pixi-generative-art.yaml` all exist.
- `grep` for all three loop names in `docs/guides/LOOPS_GUIDE.md` returns no matches.
- Harness Examples table rows (lines 1029–1030) list only `svg-image-generator` and `svg-textgrad`.
- `### svg-image-generator` at line 1282, `### svg-textgrad` at line 1338; both cited as format templates are intact.
- Line number estimates in the issue (~1031 for table insert, ~1415 for section insert) are accurate.


## Session Log
- `/ll:verify-issues` - 2026-05-31T06:12:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f18e015-8096-4bee-9b5a-4f1fdb6cf02c.jsonl`
