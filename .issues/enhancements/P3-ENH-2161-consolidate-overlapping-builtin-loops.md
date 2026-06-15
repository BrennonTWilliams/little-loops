---
id: ENH-2161
priority: P3
type: ENH
status: open
discovered_date: 2026-06-15
discovered_by: capture-issue
captured_at: "2026-06-15T05:06:56Z"
---

# ENH-2161: Consolidate Overlapping Built-in Loops

## Summary

Three groups of built-in loops share near-identical FSM shapes with only one or two variables differing between siblings. Consolidating each group into a single parameterized loop reduces maintenance surface, eliminates divergence risk, and makes the loop library easier to navigate.

## Current Behavior

The loop library contains 10 separate files across three structural duplicate groups:

- **APO family (5 files)**: `apo-beam.yaml`, `apo-contrastive.yaml`, `apo-feedback-refinement.yaml`, `apo-opro.yaml`, `apo-textgrad.yaml` — all share a generate-variants → score → route-convergence → apply FSM shape; the only variable is how each technique generates and scores candidates.
- **Deep research pair (2 files)**: `deep-research.yaml` and `deep-research-arxiv.yaml` — identical oracle delegation to `oracles/research-coverage`; differ only by `academic_mode` flag and recency-weighted scoring.
- **Generative art trio (3 files)**: `canvas-sketch-generator.yaml`, `p5js-sketch-generator.yaml`, `pixi-generative-art.yaml` — identical init → plan → generate → evaluate → score → snapshot FSM; framework name is the only variable.

Every shared bug fix or improvement requires the same change to be applied across multiple files, creating divergence risk over time.

## Motivation

The loop library has grown three clusters of structural duplicates:

| Group | Current files | Shared shape |
|---|---|---|
| APO family | apo-beam, apo-contrastive, apo-feedback-refinement, apo-opro, apo-textgrad (5) | generate variants → score → route convergence → apply |
| Deep research pair | deep-research, deep-research-arxiv (2) | delegate to `oracles/research-coverage`; differ only by source constraint |
| Generative art trio | canvas-sketch-generator, p5js-sketch-generator, pixi-generative-art (3) | init → plan → generate → evaluate → score → snapshot; framework is the only variable |

Keeping 10 files where 3 would suffice means every shared bug or improvement must be applied in multiple places.

## Expected Behavior

After consolidation:

- **APO**: a single `apo.yaml` with `context.technique: beam|contrastive|feedback-refinement|opro|textgrad`. Each technique adjusts its variant-generation prompt and scoring heuristic via a `lib/apo-technique-prompts.yaml` fragment (or inline routing). At minimum, `apo-contrastive` and `apo-feedback-refinement` (the thinnest overlap) merge first as a pilot.
- **Deep research**: a single `deep-research.yaml` with `context.source_filter: web|arxiv` (default `web`). The arxiv variant sets `academic_mode: true` when delegating to `oracles/research-coverage` and uses recency-weighted scoring.
- **Generative art**: a single `generative-art.yaml` with `context.framework: canvas|p5js|pixi`. Framework name drives the `init` and `generate` action prompts; the FSM states are otherwise identical.

`pixi-data-viz.yaml` is excluded — it targets data visualization, not generative art, so it belongs in a separate lineage.

Backward compatibility: existing `ll-loop run apo-contrastive ...` invocations must continue to work, either via symlink loop stubs (`name: apo-contrastive`, `alias_of: apo`, `context.technique: contrastive`) or a deprecation warning that redirects users.

## Implementation Steps

1. **Pilot the deep-research pair** (smallest merge, clearest single variable):
   - Merge `deep-research-arxiv.yaml` into `deep-research.yaml` as `source_filter: arxiv` branch.
   - Add a stub `deep-research-arxiv.yaml` that sets `alias_of: deep-research` and `context.source_filter: arxiv`.
   - Run `ll-loop validate` on both files; run `ll-loop run deep-research-arxiv "test topic"` to verify delegation still works.

2. **Merge the generative art trio**:
   - Create `generative-art.yaml` with `context.framework: canvas|p5js|pixi`.
   - Add alias stubs for `canvas-sketch-generator.yaml`, `p5js-sketch-generator.yaml`, `pixi-generative-art.yaml`.
   - Validate and smoke-test with `--dry-run` for each framework variant.

3. **Consolidate the APO family**:
   - Start with `apo-contrastive` + `apo-feedback-refinement` (most overlap; both: generate candidate(s) → evaluate → apply → converge).
   - Extend to `apo-beam`, `apo-opro`, `apo-textgrad` once the shared scaffold is stable.
   - The consolidated `apo.yaml` should expose `context.technique` and dispatch to technique-specific action text via a `lib/apo-techniques.yaml` fragment or inline conditional prompt.
   - Add alias stubs for all five original names.

4. **Update docs**: `loops/README.md` and `docs/guides/LOOPS_GUIDE.md` — remove individual entries, add consolidated entries with technique/framework/source parameter documentation.

5. **Run the full loop test suite** after each group merge to confirm no regressions.

## Acceptance Criteria

- [ ] All 10 original loop names still work via alias stubs (backward-compatible)
- [ ] `ll-loop list` shows the consolidated names as the canonical entries (aliases hidden or annotated)
- [ ] `ll-loop validate` passes on all new and alias files
- [ ] Each consolidated loop smoke-tests cleanly via `ll-loop run <name> --dry-run`
- [ ] Loop README and LOOPS_GUIDE updated to reflect consolidated names
- [ ] No divergence between the former siblings: a fix applied to the consolidated loop covers all old variants

## Scope Boundaries

Out of scope:
- `pixi-data-viz.yaml` — targets data visualization, not generative art; belongs in a separate lineage and must not be merged into `generative-art.yaml`
- FSM runner/executor changes — consolidation relies on the existing `context.*` parameter mechanism; no changes to `ll-loop` core or the FSM evaluator
- Loops outside the three identified groups — no other loop families are candidates for this consolidation pass
- Behavioral changes — each consolidated loop must produce functionally identical output to its former siblings for a given input

## Impact

- **Priority**: P3 — Maintenance improvement; reduces long-term divergence risk across 10 files but no immediate user-facing feature gap
- **Effort**: Medium — Three sequential merges of increasing complexity (deep-research pair first, then generative art trio, then APO family); alias stubs add surface area; requires `ll-loop validate` + smoke-test cycles for each group
- **Risk**: Low — Backward-compat stubs preserve all existing `ll-loop run <name>` invocations; changes are additive (new consolidated file + alias stubs replacing originals with no executor changes)
- **Breaking Change**: No — All 10 original loop names continue to work via alias stubs

## Labels

`loop-library`, `maintenance`, `consolidation`, `enhancement`

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Related Key Documentation

- `scripts/little_loops/loops/README.md` — loop library overview
- `docs/guides/LOOPS_GUIDE.md` — user-facing loop documentation
- `scripts/little_loops/loops/oracles/research-coverage` — shared oracle for deep-research family

## Session Log
- `/ll:format-issue` - 2026-06-15T05:13:51 - `668f19ad-7b6d-4dfd-96b4-ef7487916a9b.jsonl`
- `/ll:capture-issue` - 2026-06-15T05:06:56Z
