---
id: ENH-2058
title: Simplify hitl-md review loop to core review surface + lightweight confidence cue
type: ENH
priority: P2
status: done
captured_at: '2026-06-09T17:40:19Z'
discovered_date: 2026-06-09
discovered_by: user-session
labels:
- loops
- fsm
- hitl
- markdown
- simplification
size: Medium
completed_at: '2026-06-09T17:40:19Z'
---

# ENH-2058: Simplify hitl-md review loop to core review surface + lightweight confidence cue

## Summary

The `hitl-md` single-document review harness had grown to a 13-criterion
generator-evaluator rubric by stacking the ENH-1770 "sensemaking layer" (six
research-derived UI features) on top of the original ENH-1869 core review
surface. The maximal version (a) added extraneous cognitive load — ~10 toolbar
controls plus a side minimap on a read-and-edit surface, contradicting the
sensemaking research it cited — and (b) made the generator-evaluator near
impossible to converge: 13 coupled thresholds (5 of them strict, `8`) all had to
pass simultaneously within `max_iterations: 20`, regenerating the entire HTML
file each pass (whack-a-mole). This issue cuts the loop back to the irreducible
review loop plus the one trust-calibration signal that is specifically valuable
for AI-generated text.

## Motivation

The user observed the loop was "trying to do too much" for the actual job:
human-reviewing AI text. The generate spec (`prompts/hitl-md-generate.md`) split
cleanly at line 140 into two layers — lines 1–139 (ENH-1869 core) and lines
140–286 (ENH-1770 sensemaking layer) — which made the sprawl a contiguous,
separable block in both the prompt and the rubric.

Three concrete problems with carrying the sensemaking layer:

1. **Convergence collapse.** 13 simultaneous gates over a full-file regeneration
   loop is near-impossible to land in 20 iterations; fixing one criterion
   regresses another.
2. **It contradicted its own research basis.** The cited sensemaking literature
   (Russell's cost structure, Klein's framing, fluency-as-credibility work) is
   about *reducing* extraneous load; stacking 4 channel toggles + 4 view modes +
   density slider + trust toggle + a canvas minimap *adds* it.
3. **`schema_switching` endangered the core value.** DOM re-grouping with a
   "restore original order bit-for-bit" requirement is the one feature that can
   silently break the lossless markdown round-trip, which is the whole point.

## Decision

Selected (via interactive AskUserQuestion, cut-depth options): **Core + light
confidence cue** — keep the six ENH-1869 criteria plus one lightweight, always-on
confidence signal. Trust calibration is the only sensemaking feature specifically
about *AI* text (fluent-but-wrong), so a minimal version of it was retained while
everything else was cut. Alternatives offered were "Aggressive — pure core" (6
criteria) and "Keep trust + density" (~9 criteria).

## Changes Made

### `prompts/hitl-md-generate.md`
- Kept lines 1–139 (core review surface) verbatim.
- Replaced the ~147-line "Sensemaking layer (ENH-1770)" block (Features 1–6) with
  a single ~20-line **Confidence cue** section: segments with `data-confidence <
  0.5` get a dotted underline (muted amber) + a small "⚠ low confidence" badge
  rendered *before* the segment text in DOM order. No toolbar, no toggle, no
  click-to-reveal gate, no view modes. Purely presentational; does not touch
  selection, popover, flagging, or markdown reconstruction.

### `scripts/little_loops/loops/hitl-md.yaml`
- Description trimmed; added a "Scope note (simplified 2026-06)" recording the cut.
- `segment` state: dropped the four-dimension `channels` object (anomaly,
  claim_type) and the `length_normalized` flag; retained a single per-segment
  `confidence` score. JSON example schema updated to match.
- `run_gen_eval` rubric: reduced 13 → 7 criteria. Removed `staged_highlighting`,
  `density_control`, `multi_channel_saliency`, `schema_switching`,
  `minimap_state_rail`, `trust_calibration` (full), and `design_token_consistency`
  (which existed only to police the cut features). Added `confidence_cue`
  (threshold 7) with an explicit "if a toolbar toggle / click-gate / view mode
  reappears, deduct heavily" guard. Fixed gate wording "thirteen" → "seven".

### `scripts/tests/test_builtin_loops.py`
- Rewrote the ENH-1770 test block in the `hitl-md` structural test class. New
  tests assert the confidence cue is present (`test_segment_action_emits_confidence`,
  `test_generate_action_has_confidence_cue`, `test_rubric_binding_has_confidence_cue_criterion`)
  AND that the removed features are absent (`test_segment_action_drops_sensemaking_channels`,
  `test_generate_action_drops_sensemaking_layer`, `test_rubric_binding_drops_sensemaking_criteria`).

### `docs/guides/LOOPS_GUIDE.md`
- Updated the overview-table row (line ~1451) and the `### hitl-md` section
  (line ~1597) to describe the 7-criterion rubric and the confidence cue; added a
  "Simplified 2026-06" note recording the removed sensemaking layer and rationale.

## Kept (the round-trip)

Natural markdown render → inline saliency highlight → keyboard/click selection →
five-affordance popover (delete / insert-before / insert-after / inline-edit /
flag-for-AI) → flag-for-AI → "Copy AI prompt" → "Copy updated markdown" lossless
reconstruction.

## Cut

Staged IntersectionObserver highlight reveals, adaptive density slider,
multi-channel saliency (anomaly/claim_type channels + toggles), schema-switching
view modes, canvas minimap + localStorage visit heatmap, full trust-calibration
friction (click-to-reveal gate, length-normalized credibility marker, passive/
active toggle), and the `design_token_consistency` rubric gate.

## Acceptance Criteria

- [x] `ll-loop validate hitl-md` passes
- [x] Rubric reduced from 13 to 7 criteria; `ALL_PASS` gate wording corrected
- [x] `segment` state emits `confidence`; no longer emits `anomaly`, `claim_type`,
  or `length_normalized`
- [x] Generate spec describes the confidence cue and no longer references the
  removed sensemaking features
- [x] `hitl-md` structural test class updated and passing (27 passed)
- [x] LOOPS_GUIDE.md table + section updated with the simplified design and a
  scope note

## Impact

- **Priority**: P2
- **Effort**: Medium — surgical removal of a contiguous layer across 4 files
- **Risk**: Low — `ll-loop validate` passes, full structural test class passes,
  the cut layer was additive and separable

## Files Touched

- `prompts/hitl-md-generate.md`
- `scripts/little_loops/loops/hitl-md.yaml`
- `scripts/tests/test_builtin_loops.py`
- `docs/guides/LOOPS_GUIDE.md`

## Notes

The ENH-1770 sensemaking research is not discredited — it was the *stacking* of
every concept as a distinct, simultaneously-graded UI feature that undermined
both usability and loop convergence. The confidence cue preserves the single
insight most relevant to reviewing AI text (fluency ≠ truth) at near-zero added
surface area. A richer 3-tier confidence badge was left as a possible future
follow-up rather than the binary `< 0.5` cue.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-09T17:41:02 - `282714c3-7d9b-4b3a-9cf9-413e6bba8138.jsonl`
