---
captured_at: '2026-05-18T03:44:45Z'
completed_at: '2026-05-18T04:38:33Z'
discovered_date: 2026-05-18
discovered_by: capture-issue
status: done
confidence_score: 95
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1604: hitl-compare — add subtle write-in custom option per review item

## Summary

The hitl-compare HTML review page currently presents only the options extracted from the input documents. Reviewers have no way to record a hybrid decision or a third alternative they thought of during review. Add a subtle write-in "Custom..." affordance per item — styled as a secondary control below the main comparison options, not as a peer radio button — so reviewers can capture alternative choices without disrupting the primary comparison UX.

## Current Behavior

The hitl-compare HTML review page presents only the options extracted from the input documents. Reviewers have no mechanism to capture a hybrid decision or a third alternative formulated during review. Any such insight must be manually recorded outside the tool and applied after export.

## Expected Behavior

Each item card displays a subtle "＋ Write custom option" affordance below the last extracted option (see Design Specification for full interaction detail). Reviewers can capture free-form alternatives inline. The "Export Selections" output includes `Custom — [text]` for items with active, non-empty write-in fields. The affordance is visually subordinate and does not compete with the primary comparison controls.

## Motivation

The pruning phase surfaces items where human taste or strategic preference is the deciding signal. Often the right answer isn't Option A or Option B but a nuanced variant the reviewer formulates during the review itself. Without a write-in field, that insight is lost — the reviewer must copy the markdown export and manually amend it before pasting to the coding agent.

The affordance should be visually subordinate: small, muted, and collapsed by default. It should feel like an annotation escape hatch, not an equal alternative that competes for attention with the extracted options.

## Design Specification

**Behavior:**
- Each item card has a small "＋ Write custom option" link/button below the last extracted option, in muted secondary text color
- Clicking it reveals a `<textarea>` with placeholder text such as "Describe your preferred option..."
- Selecting the write-in textarea (or clicking anywhere within it) deselects the extracted-option radio buttons and marks the item as "custom"
- The write-in field is collapsed (hidden) when the page loads and when any extracted option is selected
- Clicking an extracted option radio re-collapses the write-in textarea

**Export behavior:**
- If the custom option is active for an item, the export JS emits: `**[Item Title]**: Custom — [first ~80 chars of textarea text]`
- If the textarea is empty when export is clicked, treat the item as unselected (same as no radio selected)

**Styling constraints (inline only — no external CSS):**
- Trigger text: `font-size: 0.85em`, `color: #888`, `cursor: pointer`, no border
- Textarea when revealed: `width: 100%`, `min-height: 60px`, `border: 1px solid #ccc`, `border-radius: 4px`, `padding: 8px`, `font-size: 0.9em`
- The write-in section must never appear at the same visual weight as the main option cards

## Proposed Solution

This is a change to the `generate` state prompt in `scripts/little_loops/loops/hitl-compare.yaml`. The score rubric in the `score` state should add the write-in affordance as a sub-criterion of `comparison_ergonomics` (not a standalone criterion, since it's secondary).

### Changes

**`generate` state action** — append to the per-item rendering instructions:

```
Below the last option for each item, include a subtle secondary affordance:
a small "＋ Write custom option" trigger (muted text, no border) that when
clicked reveals a <textarea> for free-form input. Selecting the textarea
deselects any radio button; selecting a radio collapses the textarea. Style
it visually subordinate — smaller font, muted color — so it doesn't compete
with the primary comparison controls. The "Export Selections" JS should emit
"Custom — [text]" for items where the write-in field is active and non-empty.
```

**`score` state rubric** — update `comparison_ergonomics` criterion explanation:

```
comparison_ergonomics: N/10 — [does the comparison control make it easy to
  toggle between options? Is the selected state visually unambiguous? Is there
  a subtle write-in affordance below the options that is clearly secondary (not
  a peer option)?]
```

### Files to Change

| File | Change |
|------|--------|
| `scripts/little_loops/loops/hitl-compare.yaml` | `generate` state action — add write-in affordance instructions |
| `scripts/little_loops/loops/hitl-compare.yaml` | `score` state `comparison_ergonomics` explanation |

## Scope Boundaries

- **In scope**: Write-in affordance per item card; expand/collapse behavior tied to radio selection; export integration (`Custom — [text]` output); `score` state rubric update for `comparison_ergonomics`
- **Out of scope**: Persistent storage of custom entries across sessions; rich-text editing; custom options on summary or final export pages; changes to loops other than hitl-compare

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/hitl-compare.yaml` — `generate` state action (write-in affordance instructions) and `score` state `comparison_ergonomics` explanation

### Dependent Files (Callers/Importers)
- N/A — YAML loop file; consumed only by `ll-loop` runner at execution time

### Similar Patterns
- `scripts/little_loops/loops/html-website-generator.yaml` — canonical GAN-style generator-evaluator harness with screenshot-based iteration; shares the generate → evaluate → score feedback cycle pattern
- `scripts/little_loops/loops/html-anything.yaml` — generalized HTML harness with dynamic rubric scoring; same per-item card + export affordance pattern to model inline-CSS/JS constraints after

### Tests
- `scripts/tests/test_builtin_loops.py:3017` — `TestHitlCompareLoop` structural test class; new text-contains assertions should be added here to verify: (a) `generate` state action contains the write-in trigger text, (b) `score` state `comparison_ergonomics` explanation references the write-in affordance
- Manual integration test: run `ll-loop run hitl-compare` with sample input and inspect generated HTML for write-in trigger and export `Custom —` output

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. In `scripts/little_loops/loops/hitl-compare.yaml`, update the `generate` state action (lines 146–153): after the "Visually highlight the currently selected option" bullet and before the "At the bottom of the page..." paragraph (line 154), insert the write-in affordance instructions from the Design Specification. Also update the export JS format block (lines 156–162): add a `Custom — [first ~80 chars of textarea text]` branch for items where the write-in field is active and non-empty.
2. In `scripts/little_loops/loops/hitl-compare.yaml`, update the `score` state `comparison_ergonomics` explanation (lines 207–209): append the write-in sub-criterion — "Is there a subtle write-in affordance below the options that is clearly secondary (not a peer option)?" — to the existing three questions.
3. In `scripts/tests/test_builtin_loops.py` (`TestHitlCompareLoop`, line 3017): add two new structural test methods — one asserting the `generate` state action contains the write-in trigger text (e.g. `"Write custom option"`) and one asserting the `score` state `comparison_ergonomics` explanation references the write-in affordance.
4. Run `python -m pytest scripts/tests/test_builtin_loops.py::TestHitlCompareLoop -v` to verify structural tests pass.
5. Run `ll-loop run hitl-compare` with sample input and inspect `index.html` to verify: (a) write-in trigger visible below last option per card, (b) export includes `Custom — [text]` for active non-empty fields, (c) empty write-in fields produce no export line.

## Acceptance Criteria

- [ ] The generated HTML page has a collapsed write-in trigger below the last option on every item card
- [ ] The trigger is visually subordinate (smaller, muted — not a peer of the main options)
- [ ] Clicking the trigger reveals a textarea; clicking an extracted option radio re-collapses it
- [ ] "Export Selections" includes `Custom — [text]` for items with active, non-empty write-in fields
- [ ] Items with empty write-in fields export as unselected (no selection line emitted)
- [ ] `score` state correctly evaluates the presence and subordinate styling of the write-in affordance

## Impact

- **Priority**: P3 — Non-blocking enhancement; reviewers have a manual workaround (export and amend)
- **Effort**: Small — Prompt-only change to a single YAML file (`hitl-compare.yaml`); no Python code changes
- **Risk**: Low — Isolated to hitl-compare loop prompt instructions; no structural YAML changes
- **Breaking Change**: No

## Labels

`hitl-compare`, `ui-ux`, `enhancement`

## Related Issues

- FEAT-1545: initial hitl-compare loop implementation
- BUG-1602: evaluate routing fix (prerequisite — ensures loop reaches score state reliably)

## Status

**Open** | Created: 2026-05-18 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-05-18T04:36:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ab59de2b-3fb0-486c-b9c0-1922dd88280a.jsonl`
- `/ll:refine-issue` - 2026-05-18T04:04:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e39b66da-1e72-475b-ab82-8b6388836b42.jsonl`
- `/ll:format-issue` - 2026-05-18T03:52:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ab25afc6-dfd4-4acd-af80-cded46580624.jsonl`
- `/ll:confidence-check` - 2026-05-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1649998a-0fbd-40d7-9bd5-4c979e5df1a9.jsonl`
