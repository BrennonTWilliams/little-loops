---
id: FEAT-1541
title: "Add html-anything generalized HTML artifact harness"
type: FEAT
status: open
priority: P2
captured_at: "2026-05-17T05:27:26Z"
discovered_date: "2026-05-17"
discovered_by: capture-issue
labels:
  - feature
  - loops
  - eval-harness
  - captured
---

# FEAT-1541: Add html-anything generalized HTML artifact harness

## Summary

Create a generalized eval-driven-development FSM harness (`html-anything.yaml`) inspired by the [html-anything](https://github.com/nexu-io/html-anything) project. The harness supports 9+ HTML surface types (websites, emails, social cards, presentations, résumés, invoices, dashboards, components, posters) with dynamically generated scoring rubrics tailored per artifact type. The existing `html-website-generator.yaml` is too narrow — this replaces its generality gap without removing it.

## Current Behavior

`html-website-generator.yaml` hardcodes 4 scoring criteria and assumes a website surface. There is no harness for emails (requiring inline styles + table layout), social cards (requiring dimensional accuracy), résumés (requiring print safety), or other HTML artifact types.

## Expected Behavior

Running `ll-loop run html-anything "a transactional email confirming a SaaS subscription"` should:
1. Classify the artifact type from the natural language description
2. Write a `brief.md` with platform-specific constraints for that artifact type
3. Write a `rubric.md` with 4–6 artifact-appropriate criteria (e.g. `inline_styles` with threshold 7–8 for emails)
4. Drive iterative generation/refinement using that rubric
5. Pass gate: ALL_PASS only when every criterion score ≥ its individual rubric threshold

## Motivation

The html-anything project generates 75+ HTML artifact types across 9 surfaces. Encoding platform constraints in the plan state and making evaluation criteria dynamic (written by `plan` at runtime, not hardcoded in YAML) unlocks the full range of HTML surface types without requiring a separate harness per type.

## Proposed Solution

A 6-state FSM harness: `init → plan → generate → evaluate → score → done` (+ `failed` terminal).

**Key design decisions:**
- `plan` state atomically classifies artifact type, writes `brief.md`, and writes `rubric.md` — keeping all three atomic ensures the rubric always matches the classification
- `score` state reads `rubric.md` dynamically to load per-criterion thresholds; uses per-criterion thresholds (not weighted average) to prevent strong aesthetics masking broken platform constraints
- Output goes to a timestamped subdir (isolated per run, matching `svg-image-generator` pattern)
- `evaluate` state uses Playwright screenshot with graceful degradation if not installed

**Artifact types to support:** `html-email`, `html-social-card`, `html-presentation`, `html-resume`, `html-invoice`, `html-dashboard`, `html-component`, `html-poster`, `html-website`

**Rubric format** (YAML-in-markdown fenced block):
```yaml
criteria:
  - name: inline_styles
    weight: 2
    threshold: 8
    description: All styles inline on elements — no <style> blocks or external CSS.
  - name: visual_identity
    weight: 1
    threshold: 6
    description: Distinctive color palette, readable typography, branded feel.
```

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/README.md` — add `html-anything` row to Harness table after `svg-image-generator`

### Files to Create
- `scripts/little_loops/loops/html-anything.yaml` — new 6-state FSM harness

### Reference Files (patterns to follow)
- `scripts/little_loops/loops/svg-image-generator.yaml` — timestamped run dir pattern (`init` state, lines 24–35)
- `scripts/little_loops/loops/html-website-generator.yaml` — critique.md format and score routing pattern

## Implementation Steps

1. Create `scripts/little_loops/loops/html-anything.yaml` with 6 states: `init`, `plan`, `generate`, `evaluate`, `score`, `done` (+ `failed` terminal)
   - `init` (shell): create timestamped run dir under `.loops/tmp/html-anything/`, capture as `run_dir`
   - `plan` (prompt): classify artifact type, write `brief.md` + `rubric.md` atomically
   - `generate` (prompt): read `brief.md` + `rubric.md` + optional `critique.md`, write `index.html` with all CSS/JS inline
   - `evaluate` (shell): Playwright screenshot with `on_error: generate` for graceful degradation
   - `score` (prompt): read `rubric.md` dynamically, score each criterion 1–10, write `critique.md`, route to `done` on ALL_PASS / `generate` on ITERATE / `failed` on error
   - `done` (prompt, terminal): report all output file paths
   - `failed` (terminal): no action, reached on unrecoverable score error
2. Update `scripts/little_loops/loops/README.md` — add row after `svg-image-generator`
3. Verify with three test runs:
   - `ll-loop run html-anything "a transactional email confirming a SaaS subscription"` → rubric should have `inline_styles` with threshold 7–8
   - `ll-loop run html-anything "a 1200x630 open graph card for a developer tool"` → rubric should have `dimensional_accuracy`
   - `ll-loop run html-anything "a single-page website for a coffee shop"` → should behave like `html-website-generator`

## Impact

- **Priority**: P2 — significant capability expansion unlocking 9 surface types from a single harness
- **Effort**: Medium — mostly YAML authoring following established patterns; no Python changes required
- **Risk**: Low — new file only; does not modify existing harnesses

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/loops/svg-image-generator.yaml` | Timestamped run dir pattern to replicate in `init` |
| `scripts/little_loops/loops/html-website-generator.yaml` | Critique format and score routing to replicate |
| `scripts/little_loops/loops/README.md` | Harness table to update |
| `~/.claude/plans/take-a-look-at-moonlit-squid.md` | Full design plan (source of this issue) |

## Labels

`loops`, `eval-harness`, `feature`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-05-17T05:27:26Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1abc7e22-2fd4-490d-8857-c86a64aecaa1.jsonl`

---

## Status

**Open** | Created: 2026-05-17 | Priority: P2
