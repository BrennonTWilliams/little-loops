---
id: ENH-3421
type: ENH
title: Frozen external reference/baseline guard for evaluation harnesses
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T05:49:43Z'
labels:
- harness
- evaluation
- statistics
related:
- ENH-3415
---

# ENH-3421: Frozen external reference/baseline guard for evaluation harnesses

## Summary

Companion guard to ENH-3415's n-sample redundancy: a candidate should be tested against both
the incumbent and an unchanged frozen external reference/baseline, not just its immediate
parent — otherwise a lineage of promotions can drift into a self-referential local optimum
where every generation only beats the one before it, never an outside bar. ENH-3415's
Summary calls this out as a second mandatory-structure guard from evolutionary-search
harnesses, explicitly deferred as its own issue rather than folded into that one.

This is a stub: scope, the harness(es) it applies to, and what "frozen" means operationally
(a pinned commit? a pinned model? a pinned eval set?) are all open and need research before
this is implementation-ready.

## Current Behavior

No frozen external reference/baseline guard exists in `ll-harness` or any other little-loops
evaluation harness today (confirmed by ENH-3415's own codebase research, 2026-09-09: nothing
in `.issues/` described this before ENH-3415 filed it).

## Expected Behavior

TBD — needs its own research/refine pass to determine which harness(es) this applies to and
what a "frozen baseline" comparison looks like mechanically.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Status

**Open** | Created: 2026-09-09 | Priority: P3
