---
id: ENH-2160
title: Add ll-loop diagnose-evaluators and calibrate-budget section to LOOPS_GUIDE.md
type: ENH
priority: P4
status: done
created: 2026-06-14
completed_at: 2026-06-15 15:40:29+00:00
affects:
- docs/guides/LOOPS_GUIDE.md
confidence_score: 94
outcome_confidence: 87
score_complexity: 25
score_test_coverage: 15
score_ambiguity: 22
score_change_surface: 25
decision_needed: false
testable: false
---

## Problem

`docs/guides/LOOPS_GUIDE.md` — the primary user-facing guide for loops — has no mention of two subcommands that are documented in CLI.md and CLAUDE.md:

- **`ll-loop diagnose-evaluators <loop>`** — validates discriminator health; flags evaluators with Bernoulli variance `p*(1-p) < 0.05` (toothless evaluators not measuring anything useful)
- **`ll-loop calibrate-budget <loop>`** — checks whether increasing `max_iterations` will improve outcomes; warns when evaluator variance is too low to benefit from more iterations

CLAUDE.md has usage examples for both. CLI.md has full reference sections. The guide leaves a gap between "create a loop" and "diagnose why it's not improving."

## Acceptance Criteria

- [ ] Add a new `### Evaluator Health` subsection inside `## Troubleshooting` in `docs/guides/LOOPS_GUIDE.md` covering:
  - `ll-loop diagnose-evaluators <loop>` — when to run it (after MR-1 passes), what the variance threshold means (`p*(1-p) < 0.05` = toothless), what to do when flagged
  - `ll-loop calibrate-budget <loop>` — when to run it before raising `max_iterations`, how to interpret the `⚠ WARN` / `✓ OK` output lines
- [ ] Add two rows to the `## CLI Quick Reference` table for both subcommands (after `ll-loop next-loop` at line 648)
- [ ] Link to CLI.md (`docs/reference/CLI.md`) for full flag reference; keep guide content concise (guide-level prose, not flag tables)

## Integration Map

### Files to Modify

- `docs/guides/LOOPS_GUIDE.md` — sole target file; two insertion points:
  1. **`## CLI Quick Reference` table** (line 632) — add two rows after `ll-loop next-loop` (line 648)
  2. **`## Troubleshooting` section** (line 916) — append a new `### Evaluator Health` subsection before `## Further Reading` (line 934)

### Source Material to Adapt (read-only)

- `.claude/CLAUDE.md` — "Loop Authoring" section (lines 163–184); contains the canonical `calibrate-budget` sample output block with `⚠ WARN` / `✓ OK` format
- `docs/reference/CLI.md` — `#### ll-loop diagnose-evaluators` (line 806) and `#### ll-loop calibrate-budget` (line 825); full flag tables and exit-code docs to link to
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — `## Validating and Measuring` (line 278) and `### Debugging a Stuck Optimizer` (line 354); shows how these commands are described in a different guide — adapt tone, do not copy verbatim

### Dependent Files (no changes needed)

- `scripts/little_loops/cli/loop/info.py` — `cmd_diagnose_evaluators()` (line 760), `cmd_calibrate_budget()` (line 816); implementation is ship-complete, no code changes
- `scripts/little_loops/analytics/variance.py` — `compute_evaluator_variance()` (line 162); shared engine for both commands, no changes needed

### Tests

No test changes required — this is a documentation-only enhancement. No existing tests cover guide content.

### Documentation

- `docs/reference/CLI.md` — already has full coverage; this issue only adds guide-level prose in LOOPS_GUIDE.md that links to it

## Implementation Steps

1. **Read the insertion context** — open `docs/guides/LOOPS_GUIDE.md` and read:
   - Lines 632–650 (`## CLI Quick Reference` table) to understand the two-column format (`Command | Description`, placeholder `<name>`)
   - Lines 916–933 (`## Troubleshooting` section) to understand the bold-paragraph pattern used by all existing entries

2. **Add two rows to `## CLI Quick Reference`** — insert after the `ll-loop next-loop` row (line 648):
   ```
   | `ll-loop diagnose-evaluators <name>` | Scan evaluator history for non-discriminating states (Bernoulli variance `p*(1-p)` below 0.05); exits 1 if any flagged |
   | `ll-loop calibrate-budget <name>` | Check whether raising `max_iterations` will earn its token cost; reports `⚠ WARN` when evaluator variance is too low |
   ```

3. **Add `### Evaluator Health` subsection** — insert between the last `## Troubleshooting` entry (line 932) and `## Further Reading` (line 934). Follow the existing bold-paragraph pattern but under a new `###` heading since the topic warrants grouping. Content to include:
   - Opening sentence tying back to MR-1: "Passing `ll-loop validate` (MR-1) confirms a non-LLM evaluator is _present_ — it does not confirm the evaluator is _discriminating_."
   - `diagnose-evaluators` paragraph: when to run (after MR-1 passes), what variance `p*(1-p) < 0.05` means, what the per-state recommendations contain (see `_generate_recommendation()` in `variance.py`), link to CLI.md
   - `calibrate-budget` paragraph: frame it as a pre-budget-raise gate, show the sample `⚠ WARN` / `✓ OK` output (adapt from CLAUDE.md lines 176–184), link to CLI.md
   - Closing guidance: "Fix toothless evaluators (broaden the judge prompt, tighten the exit-code command) _before_ raising `max_iterations`, or the extra iterations are wasted."

4. **Verify cross-references** — confirm that the CLI.md link format follows the existing guide pattern: `[CLI reference](../reference/CLI.md)` (file-relative, no absolute path)

5. **Run link check** — `ll-check-links docs/guides/LOOPS_GUIDE.md` to validate no broken anchors were introduced

## Notes

Both commands are already ship-complete. This is purely a guide-level coverage gap. See CLAUDE.md "Loop Authoring" section for the existing usage examples to adapt.

The sample output block from CLAUDE.md (the `calibrate-budget` two-evaluator example showing `check_quality` with variance 0.02 flagged and `check_exit` with variance 0.23 healthy) is the clearest artifact to embed in the guide — it makes the `⚠ WARN` / `✓ OK` format immediately readable.


## Session Log
- `/ll:ready-issue` - 2026-06-15T15:38:38 - `7653d087-4ef8-401e-a12a-57eaa27def23.jsonl`
- `/ll:refine-issue` - 2026-06-15T15:33:15 - `c5747c4e-5593-493d-87f3-2bbad9b09fdc.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00 - `e85f92ea-2c29-40a6-9a0c-959ccea80157.jsonl`
