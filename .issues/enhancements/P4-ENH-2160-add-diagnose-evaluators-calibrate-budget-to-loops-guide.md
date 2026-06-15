---
id: ENH-2160
title: Add ll-loop diagnose-evaluators and calibrate-budget section to LOOPS_GUIDE.md
type: ENH
priority: P4
status: open
created: 2026-06-14
affects:
  - docs/guides/LOOPS_GUIDE.md
---

## Problem

`docs/guides/LOOPS_GUIDE.md` — the primary user-facing guide for loops — has no mention of two subcommands that are documented in CLI.md and CLAUDE.md:

- **`ll-loop diagnose-evaluators <loop>`** — validates discriminator health; flags evaluators with Bernoulli variance `p*(1-p) < 0.05` (toothless evaluators not measuring anything useful)
- **`ll-loop calibrate-budget <loop>`** — checks whether increasing `max_iterations` will improve outcomes; warns when evaluator variance is too low to benefit from more iterations

CLAUDE.md has usage examples for both. CLI.md has full reference sections. The guide leaves a gap between "create a loop" and "diagnose why it's not improving."

## Acceptance Criteria

- [ ] Add a subsection under the existing debugging/diagnostics section in LOOPS_GUIDE.md (or add a new "Evaluator Health" subsection) covering:
  - `ll-loop diagnose-evaluators <loop>` — when to run it, what the variance threshold means, what to do when flagged
  - `ll-loop calibrate-budget <loop>` — when to run it before raising `max_iterations`, how to interpret output
- [ ] Link to the full flags reference in CLI.md
- [ ] Keep the new content concise (guide-level, not reference-level); link out to CLI.md for flags

## Notes

Both commands are already ship-complete. This is purely a guide-level coverage gap. See CLAUDE.md "Loop Authoring" section for the existing usage examples to adapt.
