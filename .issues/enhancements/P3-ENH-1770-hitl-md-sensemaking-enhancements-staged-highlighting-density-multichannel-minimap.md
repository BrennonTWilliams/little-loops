---
id: ENH-1770
status: open
captured_at: "2026-05-28T17:00:00Z"
discovered_date: "2026-05-28"
discovered_by: capture-issue
labels: [enhancement, hitl-md, ui, sensemaking, captured]
---

# ENH-1770: hitl-md sensemaking enhancements — staged highlighting, density control, multi-channel saliency, schema-switching, minimap, and calibrated friction

## Summary

The hitl-md review harness currently renders a single saliency score per segment as a static background tint. Research on cognitive sensemaking (Pirolli & Card, Klein et al., Russell et al., 1993-2007) and recent HCI studies (HCEye 2024, Keyhole Effect 2025, Overgeneration Effect 2025) converge on five enhancements that together address the full spectrum of cognitive load in AI-assisted document review:

1. **Staged dynamic highlighting** — reveal saliency highlights in waves (top 3-5 on load, next tier fades in on scroll) instead of all at once, leveraging the HCEye finding that dynamic appearance captures attention better under cognitive load (Das et al., CHI 2024)
2. **Adaptive highlight density slider** — user-controlled threshold controlling what fraction of segments get highlighted (Top 10% / Top 25% / All), preventing the "everything is important" flat attention landscape (Yang et al., 2025)
3. **Multi-channel saliency** — orthogonal channels (anomaly, claim-type, confidence) with independent color coding and toggle controls, supporting Klein's Data/Frame Theory finding that single-dimension saliency anchors users in one "frame" and discourages reframing
4. **Schema-switching view toggles** — toolbar re-rendering content grouped by different schemas (by heading, by saliency, by claim type, by anomaly), making representational shifts a single click instead of a costly cognitive reconstruction (Russell et al., 1993 Cost Structure of Sensemaking)
5. **Minimap + spatial State Rail** — right-side minimap showing document structure as proportional colored blocks with viewport position indicator and visit heatmap, restoring the spatial sense that linear scrolling destroys (Reddy, Keyhole Effect 2025)
6. **Calibrated friction for trust calibration** — deliberate, low-friction interventions that disrupt the "LLM Fallacy" (fluency mistaken for competence, Kim et al. 2026 [37]) and the finding that longer explanations increase user confidence even without accuracy improvement (Steyvers et al. 2024 [15]). Confidence badges are displayed *before* segment content (not after), high-saliency low-confidence claims require click-to-reveal, and confidence scores are length-normalized so longer segments don't get an unwarranted credibility boost

## Current Behavior

- All segments are highlighted with a static background tint on page load
- One saliency dimension (importance) with one color mapping
- Single full-document scroll view with no spatial overview
- No density control — every segment with a saliency score gets the tint treatment
- No way to re-group or re-organize content by different analytical frames
- No trust calibration — confidence scores (if present) are displayed inline after content, where fluency has already shaped the user's judgment; segment length is not accounted for in credibility display

## Expected Behavior

The review page should adapt to the user's cognitive state and analytical needs:

- Highlights appear in waves (staged reveal) so the user isn't overwhelmed on first load
- A slider or toggle controls highlight density, defaulting to sparse (Top 10-25%)
- Multiple saliency channels visible with independent toggles (importance, anomaly, claim-type, confidence)
- A toolbar lets users re-render content grouped by different schemas
- A right-side minimap provides spatial orientation and progress tracking
- Confidence indicators appear *before* segment content so the reviewer's trust is calibrated prior to reading
- High-saliency but low-confidence claims are gated behind a click-to-reveal to force deliberate engagement
- Confidence display is normalized by segment length — longer segments don't get an implicit credibility bonus

## Motivation

AI-generated text review imposes high cognitive load — the user must verify accuracy, assess structure, spot errors, and build a mental model of the content simultaneously. The current single-dimension highlighting approach helps with initial foraging but doesn't support the full sensemaking cycle (schema formation, anomaly detection, representational shifts).

A parallel problem is the **LLM Fallacy** [37]: the fluency of AI-generated text acts as a metacognitive cue that users mistake for competence. Steyvers et al. [15] showed that longer explanations increase user confidence even when accuracy doesn't improve. The current design optimizes for readability and throughput, which inadvertently *amplifies* this effect — smooth scrolling, clean typography, and inline confidence scores all reinforce fluency-as-credibility. Calibrated friction at high-stakes moments (showing confidence before content, gating uncertain claims behind deliberate clicks, normalizing for segment length) actively disrupts this false signal.

These six enhancements together address the full spectrum of cognitive failure modes in linear AI-output review — both the under-supported sensemaking cycle and the over-trust problem that fluent text creates.

## Success Metrics

- **Review efficiency**: Time-to-completion for document review tasks should decrease as staged highlighting reduces initial cognitive overload (fewer segments competing for attention on first load)
- **Schema switching frequency**: Number of distinct analytical views used per review session — target: 2+ schema switches per session (baseline: 0, no switching currently supported)
- **Density control engagement**: Density slider usage rate — users actively adjusting threshold indicates the feature is being used for cognitive load management rather than ignored
- **Trust calibration**: Reduced correlation between segment length and user confidence ratings — length-normalized confidence display should weaken the fluency-as-credibility bias documented in Steyvers et al. 2024

## Proposed Solution

All six enhancements live in the `generate` state's HTML template (no runner changes). The data model (`segments.json`) needs minor enrichment:

**Staged highlighting + density slider** are pure JS/CSS changes:
- JS `IntersectionObserver` with tiered reveal groups
- Slider input filtering visible `.seg` highlights by saliency threshold
- CSS transitions for fade-in animation

**Multi-channel saliency** requires each segment to carry additional fields:
```json
{
  "channels": {
    "importance": 0.8,
    "anomaly": 0.1,
    "claim_type": "factual",
    "confidence": 0.9
  }
}
```
These are populated during the `segment` state by the LLM. The HTML renders color coding per active channel.

**Schema-switching** is a JS re-group of the displayed content triggered by toolbar buttons. The segment data (type, saliency, channels) is already sufficient for grouping.

**Minimap** is a fixed-position `<canvas>` element on the right edge, redrawn on scroll/resize, with click-to-navigate and visit-tracking (via `localStorage`).

**Calibrated friction** is a set of small JS/CSS interventions in the `generate` HTML that disrupt fluency-driven over-trust:
- Confidence badges rendered *before* segment body text (DOM order), so the reviewer sees the calibration signal first
- Click-to-reveal gate on segments where `saliency > 0.7` AND `confidence < 0.5` — the content is hidden behind a "Review this claim" button with the confidence badge visible
- Length-normalized confidence indicator: segments longer than the document median get a visual marker (e.g., a subtle ruler icon) next to the confidence badge, since longer text gets an unwarranted credibility boost
- All interventions are opt-in via a "Trust calibration" toggle in the toolbar; default is passive (badge-before-content only, no gating)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **No prior art for 5 of 6 enhancements.** Canvas (`<canvas>`/`getContext`), `IntersectionObserver`, `localStorage`, CSS `transition`/`animation`, and `<input type="range">` do not exist in any of the 50+ built-in loop YAMLs. ENH-1770 introduces all five browser APIs to the loop ecosystem for the first time. The minimap, staged highlighting, density slider, and visit heatmap all depend on these new-to-codebase APIs.
- **Existing `data-*` attribute pattern.** The current `generate` state prompt (line 165) already uses `data-id`, `data-color`, `data-saliency`, `data-type` attributes on `.seg` elements. Multi-channel saliency should extend this pattern with `data-channel-importance`, `data-channel-anomaly`, `data-channel-confidence`, and `data-claim-type` (or a single `data-channels` JSON attribute). JS access pattern: `element.dataset.saliency` → `element.dataset.channelImportance`.
- **Data flow is filesystem-based.** The `segment` state writes `segments.json` to `${captured.run_dir.output}/`; the `generate` state reads it via LLM tool call. No runner code parses or validates `segments.json`. The FSM executor (`scripts/little_loops/fsm/executor.py:943`) resolves `${captured.run_dir.output}` through `InterpolationContext` (`scripts/little_loops/fsm/interpolation.py:37`). The enriched segment schema (adding `channels` and `length_normalized`) requires no runner changes — the LLM reads the JSON directly.
- **Design tokens are injected into context.** `cmd_run()` in `scripts/little_loops/cli/loop/run.py:183` injects `design_tokens_context` into the loop's context before execution. The `generate` state prompt already references `${context.design_tokens_context}`. The new features should use design token CSS custom properties where applicable for color consistency.
- **All 6 features are independently toggleable.** Each enhancement is a separate JS/CSS module within the single `index.html` file. The existing architecture (single-page LLM-generated HTML, no shared state between features except `segments.json`) means a bug in the minimap can't break highlighting, a broken density slider doesn't affect schema-switching, etc. The "Trust calibration" toggle is the only cross-cutting control.
- **Score rubric needs 6 new criteria.** The current `score` state (line 293) evaluates 6 criteria with independent 1-10 thresholds. Each new feature needs a corresponding criterion (e.g., `staged_highlighting`, `density_control`, `multi_channel_saliency`, `schema_switching`, `minimap_state_rail`, `trust_calibration`). The existing `ALL_PASS` mechanism (all criteria meet individual thresholds) extends naturally.
- **Tests are structural only.** The `TestHitlMdLoop` class (`test_builtin_loops.py:3467`) validates YAML schema (state existence, routing, action content, context fields). No rendering or behavioral tests exist for the generated HTML. Verification of the 6 new features depends on manual testing via `ll-loop run hitl-md` and Playwright screenshot comparison in the `evaluate` state.

## Scope Boundaries

- **In scope**: The six named enhancements (staged highlighting, density slider, multi-channel saliency, schema-switching toolbar, minimap + State Rail, calibrated friction) within the hitl-md loop's `generate` state HTML template; segment schema enrichment in the `segment` state prompt; score rubric updates in the `score` state
- **Out of scope**: Runner or infrastructure changes (`scripts/little_loops/` Python code); backend processing changes beyond the loop YAML; new loop states; changes to other loops; server-side rendering (all features work under `file://`)

## API/Interface

N/A — no public API changes. All changes are internal to the hitl-md loop YAML (`generate` state HTML/JS/CSS template, `segment` state prompt, `score` state rubric).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/hitl-md.yaml` — `segment` state (line 53): add multi-channel fields to prompt; `generate` state (line 124): add six new features to HTML generation prompt; `score` state (line 293): add criterion checks for new features
- `scripts/tests/test_builtin_loops.py` — `TestHitlMdLoop` class (line 3467): add structural tests for new segment fields and generate-state directives

### Dependent Files (Callers/Importers)
- N/A — standalone loop, no callers. Confirmed by codebase analysis: no other loops or Python modules reference hitl-md.

### Similar Patterns
- Existing segment saliency infrastructure (`segments.json` structure, `data-*` attribute pattern on `.seg` elements) extends naturally to multi-channel — add `data-channels` JSON attribute alongside `data-saliency`, `data-color`, `data-type`
- Sibling harness loops (`hitl-compare.yaml`, `html-anything.yaml`, `html-website-generator.yaml`) share the same `generate → evaluate → score` GAN-style architecture
- FSM variable interpolation (`scripts/little_loops/fsm/interpolation.py`) uses `${captured.run_dir.output}` namespace for filesystem data passing between states

### Tests
- `scripts/tests/test_builtin_loops.py:3467` — `TestHitlMdLoop` class with 20+ structural tests (state existence, routing rules, action content checks, context validation). All tests are YAML schema validation; no rendering/behavioral tests exist for generated HTML.
- New structural tests needed: segment state writes `channels` and `length_normalized` fields; generate state references canvas, IntersectionObserver, localStorage, CSS transitions, range input, and trust calibration patterns

### Documentation
- `docs/development/sensemaking-hitl-md.md` — sensemaking research synthesis with 8 patterns across 3 tiers; ENH-1770 implements Tier 1 (CSS/JS only) and Tier 2 (segment model pipeline) enhancements
- `docs/guides/LOOPS_GUIDE.md:1134-1188` — hitl-md loop documentation (technique, usage, FSM flow)
- `scripts/little_loops/loops/README.md:134` — built-in loops catalog entry

### Configuration
- N/A — no config changes needed

### Related Issues (Wave Sub-Issues)
- `ENH-1774` — Wave 1: extract shared `ll_commit` and `playwright_screenshot` fragments
- `ENH-1775` — Wave 2: extract `generate → evaluate → score` cycle into shared sub-loop
- `ENH-1776` — Wave 3: extract `ll_rubric_score` fragment and add convergence gate
- `FEAT-1613` — Original feature that created the hitl-md loop

## Implementation Steps

1. **Enrich segment schema** — update the `segment` state prompt to produce `channels` object per segment (importance, anomaly, claim_type, confidence) and a `length_normalized` flag for segments exceeding document median length
2. **Implement staged highlighting** — JS tiered reveal logic + CSS transitions in the `generate` HTML
3. **Add density slider** — range input filtering highlighted segments by saliency threshold
4. **Build multi-channel rendering** — channel toggle controls, per-channel color coding, CSS class switching
5. **Add calibrated friction** — confidence-before-content DOM ordering, click-to-reveal gate for high-saliency/low-confidence segments, length-normalized confidence markers, "Trust calibration" toolbar toggle
6. **Add schema-switching toolbar** — view mode toggles with JS re-grouping/re-rendering
7. **Add minimap + State Rail** — Canvas-based proportional minimap with IntersectionObserver, click-to-navigate, and visit heatmap
8. **Update score rubric** — add evaluation criteria for each new feature to the `score` state
9. **Verify end-to-end** — run `ll-loop run hitl-md` and confirm all six features work under file://

## Impact

- **Priority**: P3 — Valuable improvements to an existing tool, not blocking other work
- **Effort**: Medium — all changes scoped to the loop YAML's `generate` state HTML template and the `segment` state prompt. No runner or infrastructure changes.
- **Risk**: Low — each enhancement is independently toggleable; a bug in the minimap doesn't break highlighting
- **Breaking Change**: No — existing behavior (static single-channel highlighting) is the default until user activates new features

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `hitl-md`, `ui`, `sensemaking`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-29T02:27:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2337e492-f7f1-44fd-a9a4-27d67af90051.jsonl`
- `/ll:capture-issue` - 2026-05-28T17:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1814a47-ceda-478f-aac4-3e3bf601d202.jsonl`

**Open** | Created: 2026-05-28 | Priority: P3
