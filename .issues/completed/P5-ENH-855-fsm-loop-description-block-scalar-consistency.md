---
id: ENH-855
type: ENH
priority: P5
status: completed
discovered_date: 2026-03-21
discovered_by: manual
confidence_score: 100
outcome_confidence: 100
---

# ENH-855: Standardize FSM loop `description` fields to block scalars

## Summary

Three APO loop YAML files used inline one-liner strings for their `description`
field while all other loops used multi-line block scalars. The three one-liners
were expanded to block scalars following the established convention.

## Problem

A scan of all 23 loop YAML files in `loops/` revealed three outliers using
quoted inline strings:

- `apo-beam.yaml`: `"Beam search prompt optimization — generate N variants, score all, advance the winner"`
- `apo-opro.yaml`: `"OPRO-style prompt optimization — history-guided proposal until convergence"`
- `apo-textgrad.yaml`: `"TextGrad-style prompt optimization — test on examples, compute failure gradient, apply refinement"`

The remaining 20 loops used YAML block scalar (`|`) descriptions that follow a
consistent pattern: technique name → mechanics as a sentence chain → stopping
condition → notable requirement or parameter.

## Investigation Notes

Adding structured metadata fields (tags, prerequisites, usage) was evaluated and
rejected. The `description` block scalar already covers all documentation needs:

- `_load_loop_meta()` (`scripts/little_loops/cli/loop/info.py:35`) truncates to
  the first line for `ll-loop list`, so rich block scalars don't pollute the list
  view.
- `cmd_show()` (`info.py:664`) renders the full description for `ll-loop show`.
- The `context:` field already documents required input variables.
- Structured fields would add schema and validation complexity for zero gain.

## Solution

Expanded the three one-liners to block scalars matching the pattern established
by `apo-contrastive` and `apo-feedback-refinement`:

**apo-beam** — added beam_width/target_score parameter note.

**apo-opro** — added description of history accumulation mechanic.

**apo-textgrad** — added requirement for labeled `examples_file`.

## Files Changed

- `loops/apo-beam.yaml` — `description` field expanded to block scalar
- `loops/apo-opro.yaml` — `description` field expanded to block scalar
- `loops/apo-textgrad.yaml` — `description` field expanded to block scalar
