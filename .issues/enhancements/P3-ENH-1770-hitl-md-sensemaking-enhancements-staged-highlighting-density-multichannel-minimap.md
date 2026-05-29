---
id: ENH-1770
status: open
captured_at: '2026-05-28T17:00:00Z'
discovered_date: '2026-05-28'
discovered_by: capture-issue
labels:
- enhancement
- hitl-md
- ui
- sensemaking
- captured
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
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
- `docs/guides/LOOPS_GUIDE.md:1134-1188` — hitl-md loop documentation (technique, usage, FSM flow); rubric criteria names (6→12) and feature descriptions become stale
- `docs/guides/LOOPS_GUIDE.md:993` — Harness Examples table row; one-line summary needs updating for new features
- `scripts/little_loops/loops/README.md:134` — built-in loops catalog entry

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:742` — "See Also" bullet listing hitl-md; summary becomes stale [Agent 2 finding]
- `CHANGELOG.md` — new entry needed post-implementation for the 6 sensemaking enhancements [Agent 2 finding]

### Configuration
- N/A — no config changes needed

### Related Issues (Wave Sub-Issues)
- `ENH-1774` — Wave 1: extract shared `ll_commit` and `playwright_screenshot` fragments
- `ENH-1775` — Wave 2: extract `generate → evaluate → score` cycle into shared sub-loop
- `ENH-1776` — Wave 3: extract `ll_rubric_score` fragment and add convergence gate
- `FEAT-1613` — Original feature that created the hitl-md loop

## Implementation Steps

1. **Enrich segment schema** — update the `segment` state prompt (`hitl-md.yaml:94-113`) to produce `channels` object per segment (importance, anomaly, claim_type, confidence) and a `length_normalized` flag for segments exceeding document median length. The `channels` object follows the same pattern as the existing per-segment fields (`id`, `type`, `saliency_score`, `color`). See `hitl-md.yaml:97-113` for the current JSON schema instructions.
2. **Implement staged highlighting** — JS tiered reveal logic + CSS transitions in the `generate` HTML. The `generate` state prompt (`hitl-md.yaml:124-275`) already instructs the LLM to produce self-contained HTML. Add staged-reveal instructions: `IntersectionObserver` with tiered reveal groups (top 3-5 on load, next tier fades in on scroll), CSS `transition` on `opacity` and `background-color` for fade-in animation. No prior art in any loop — all constructs are new to the codebase.

    > **Design tokens:** transition durations and easings must reference design token CSS custom properties from `${context.design_tokens_context}` (e.g., `var(--motion-duration-medium)`, `var(--motion-easing-standard)`) rather than hardcoded `200ms ease`. If the active token profile lacks motion tokens, fall back to a single documented constant declared once at `:root` (`--hitl-stage-duration`, `--hitl-stage-easing`) so the values are tunable in one place. The faded-in `background-color` end-state must be a semantic color token (e.g., `var(--color-surface-raised)`), not a hex literal.

3. **Add density slider** — `<input type="range">` filtering highlighted segments by saliency threshold, defaulting to sparse (Top 10-25%). The slider is rendered in a fixed toolbar alongside the existing "Copy AI prompt" and "Copy updated markdown" controls. New to codebase — no existing loop uses range inputs.

    > **Design tokens:** slider track, thumb, focus ring, and surrounding toolbar surface must use semantic color tokens (`var(--color-surface-primary)`, `var(--color-border-subtle)`, `var(--color-action-primary)`) and the spacing scale (`var(--space-2)`, `var(--space-3)`) for padding/gap. Label typography must use `var(--font-size-sm)` / `var(--font-family-ui)` from the typography layer. No raw hex, px, or rem values for any visible style.

4. **Build multi-channel rendering** — channel toggle controls, per-channel color coding, CSS class switching. Extend the existing `data-*` attribute pattern (`hitl-md.yaml:165-172`) with `data-channel-importance`, `data-channel-anomaly`, `data-channel-confidence`, `data-claim-type`. Use design tokens CSS custom properties (`${context.design_tokens_context}`) for per-channel colors.

5. **Add calibrated friction** — confidence-before-content DOM ordering, click-to-reveal gate for high-saliency/low-confidence segments, length-normalized confidence markers, "Trust calibration" toolbar toggle. All pure JS/CSS changes within the `generate` state HTML. The toggle defaults to passive (badge-before-content only, no gating).

    > **Design tokens:** confidence badges must map confidence tiers to semantic tokens — high → `var(--color-status-success)`, mid → `var(--color-status-warning)`, low → `var(--color-status-danger)` — never hardcoded greens/yellows/reds. The click-to-reveal "Review this claim" button uses `var(--color-action-primary)` and `var(--color-action-primary-hover)`; the length-normalized ruler icon uses `var(--color-text-muted)`. Badge padding/radius and the gated-segment outline must use the spacing scale and `var(--radius-sm)` / `var(--border-width-strong)`. This is the highest-stakes wiring of the six features — friction interventions that look ad-hoc undermine the calibration signal.

6. **Add schema-switching toolbar** — view mode toggles with JS re-grouping/re-rendering. Group segments by heading, saliency tier, claim type, or anomaly score. Pure JS DOM manipulation — no new data needed beyond what `segments.json` already provides.

    > **Design tokens:** toggle buttons share the same toolbar surface/spacing/typography tokens as step 3 (slider toolbar) to keep a single visual language. Active-state highlight uses `var(--color-action-primary)` against `var(--color-surface-raised)`; inactive uses `var(--color-text-secondary)`. Group-divider rules between re-rendered sections use `var(--color-border-subtle)` and `var(--space-4)` separation.

7. **Add minimap + State Rail** — Canvas-based proportional minimap with `IntersectionObserver` for viewport tracking, `click` handler for navigation (scroll to position), and `localStorage`-backed visit heatmap. Fixed-position `<canvas>` on the right edge, redrawn on `scroll`/`resize`. All constructs (`<canvas>`, `getContext('2d')`, `IntersectionObserver`, `localStorage`) are new to the codebase.

    > **Design tokens:** canvas fills must read resolved token values at render time, not embed hex literals. Pattern: read `getComputedStyle(document.documentElement).getPropertyValue('--color-channel-importance')` (and siblings) once per draw and pass to `ctx.fillStyle`. Proportional block colors mirror the multi-channel palette from step 4. Viewport indicator uses `var(--color-action-primary)` at reduced alpha (via `color-mix()` or a pre-resolved `--color-viewport-overlay` token). Visit-heatmap intensity ramp uses the neutral scale (`--color-neutral-100` → `--color-neutral-400`). Minimap width and gutter come from the spacing scale. Tokens are read at draw-time so theme switches (light/dark) take effect on next redraw without a reload.

8. **Update score rubric** — add 7 new evaluation criteria to the `score` state (`hitl-md.yaml:293-370`): one per feature (6) plus a `design_token_consistency` criterion (1), each with individual 1-10 thresholds. Follow the existing rubric pattern: criterion name, threshold, description of what to evaluate. The `ALL_PASS` mechanism requires all criteria to meet their thresholds.

    > **`design_token_consistency` criterion (new):** Scores 1-10 whether the generated HTML/CSS sources colors, spacing, typography, motion, and radii from `${context.design_tokens_context}` CSS custom properties rather than hardcoded values. The evaluator prompt should instruct the scorer to (a) grep the rendered `<style>` block for raw hex colors (`#[0-9a-f]{3,8}`), raw px/rem values outside of `:root` declarations, and inline `style="color: …"` attributes with literal colors; (b) confirm the new step-2/3/5/6/7 features each reference at least one semantic token; (c) penalize any new visible surface that introduces a color not derived from the active token profile. Threshold suggestion: 8/10 — small concessions allowed (e.g., `1px` borders, `transparent` fallbacks) but no net-new color hardcoding. This criterion guards against the LLM regressing to literal values under prompt drift.

    > **Risk: PASS token collision** — `test_no_bare_pass_token_in_output_contains` (`test_builtin_loops.py:130`) guards against bare `"PASS"` tokens because they match per-criterion annotations like `"design_quality: 8/10 — PASS"`. The `ALL_PASS` compound token must remain the gate pattern. Per-criterion PASS/FAIL annotations in the new LLM output must not collide with the `output_contains` pattern field. [Agent 2 finding]
9. **Add structural tests** — add validation tests to `TestHitlMdLoop` in `scripts/tests/test_builtin_loops.py:3467` for: segment state produces `channels` and `length_normalized` fields, generate state references new browser APIs, score state includes new criteria. Follow existing test patterns (YAML fixture loading, string containment checks, routing assertions).
10. **Verify end-to-end** — run `ll-loop run hitl-md` with a test document and confirm all six features work under `file://`. The `evaluate` state (`hitl-md.yaml:277-291`) runs Playwright screenshot; visual verification confirms features render correctly.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. **Update documentation** — `docs/guides/LOOPS_GUIDE.md:1134-1188` (rubric criteria names expand 6→12, feature descriptions for staged highlighting/density slider/multi-channel/minimap/trust calibration), `docs/guides/LOOPS_GUIDE.md:993` (Harness Examples table row), `docs/development/sensemaking-hitl-md.md` (note patterns 1-6 moved from proposed to implemented), `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:742` ("See Also" bullet), `scripts/little_loops/loops/README.md:135` (one-line catalog entry). [Agent 2 finding]
12. **Add CHANGELOG entry** — per convention, new entry for the 6 sensemaking enhancements under a dated release section. [Agent 2 finding]

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
- `/ll:ready-issue` - 2026-05-29T18:51:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/97af05f4-024d-4e1b-8b35-cbcf8ccdca06.jsonl`
- `/ll:wire-issue` - 2026-05-29T18:30:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/174d6d2b-73db-4379-829e-28085556667d.jsonl`
- `/ll:refine-issue` - 2026-05-29T05:02:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/67b57fec-0cce-4cf6-8ad3-3e79d6cd8777.jsonl`
- `/ll:format-issue` - 2026-05-29T02:27:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2337e492-f7f1-44fd-a9a4-27d67af90051.jsonl`
- `/ll:capture-issue` - 2026-05-28T17:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1814a47-ceda-478f-aac4-3e3bf601d202.jsonl`
- `/ll:confidence-check` - 2026-05-29T22:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1d6ccc1e-b9ff-4db2-8494-fead3e4fd7cb.jsonl`

**Open** | Created: 2026-05-28 | Priority: P3
