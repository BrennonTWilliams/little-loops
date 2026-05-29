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

## Scope Boundaries

- **In scope**: The six named enhancements (staged highlighting, density slider, multi-channel saliency, schema-switching toolbar, minimap + State Rail, calibrated friction) within the hitl-md loop's `generate` state HTML template; segment schema enrichment in the `segment` state prompt; score rubric updates in the `score` state
- **Out of scope**: Runner or infrastructure changes (`scripts/little_loops/` Python code); backend processing changes beyond the loop YAML; new loop states; changes to other loops; server-side rendering (all features work under `file://`)

## API/Interface

N/A — no public API changes. All changes are internal to the hitl-md loop YAML (`generate` state HTML/JS/CSS template, `segment` state prompt, `score` state rubric).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/hitl-md.yaml` — `segment` state prompt (add multi-channel fields), `generate` state prompt (six new features), `score` state rubric (add criterion checks)

### Dependent Files (Callers/Importers)
- N/A — standalone loop, no callers

### Similar Patterns
- Existing segment saliency infrastructure (`segments.json` structure, class-based highlighting in HTML) extends naturally to multi-channel

### Tests
- `scripts/tests/` — HITL-MD loop tests if they exist; or manual verification via `ll-loop run hitl-md`

### Documentation
- N/A — loop description in YAML is self-documenting

### Configuration
- N/A

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
