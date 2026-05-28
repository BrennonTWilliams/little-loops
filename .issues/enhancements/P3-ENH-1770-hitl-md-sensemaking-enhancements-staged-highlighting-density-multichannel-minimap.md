---
id: ENH-1770
status: open
captured_at: "2026-05-28T17:00:00Z"
discovered_date: "2026-05-28"
discovered_by: capture-issue
labels: [enhancement, hitl-md, ui, sensemaking, captured]
---

# ENH-1770: hitl-md sensemaking enhancements — staged highlighting, density control, multi-channel saliency, schema-switching, and minimap

## Summary

The hitl-md review harness currently renders a single saliency score per segment as a static background tint. Research on cognitive sensemaking (Pirolli & Card, Klein et al., Russell et al., 1993-2007) and recent HCI studies (HCEye 2024, Keyhole Effect 2025, Overgeneration Effect 2025) converge on five enhancements that together address the full spectrum of cognitive load in AI-assisted document review:

1. **Staged dynamic highlighting** — reveal saliency highlights in waves (top 3-5 on load, next tier fades in on scroll) instead of all at once, leveraging the HCEye finding that dynamic appearance captures attention better under cognitive load (Das et al., CHI 2024)
2. **Adaptive highlight density slider** — user-controlled threshold controlling what fraction of segments get highlighted (Top 10% / Top 25% / All), preventing the "everything is important" flat attention landscape (Yang et al., 2025)
3. **Multi-channel saliency** — orthogonal channels (anomaly, claim-type, confidence) with independent color coding and toggle controls, supporting Klein's Data/Frame Theory finding that single-dimension saliency anchors users in one "frame" and discourages reframing
4. **Schema-switching view toggles** — toolbar re-rendering content grouped by different schemas (by heading, by saliency, by claim type, by anomaly), making representational shifts a single click instead of a costly cognitive reconstruction (Russell et al., 1993 Cost Structure of Sensemaking)
5. **Minimap + spatial State Rail** — right-side minimap showing document structure as proportional colored blocks with viewport position indicator and visit heatmap, restoring the spatial sense that linear scrolling destroys (Reddy, Keyhole Effect 2025)

## Current Behavior

- All segments are highlighted with a static background tint on page load
- One saliency dimension (importance) with one color mapping
- Single full-document scroll view with no spatial overview
- No density control — every segment with a saliency score gets the tint treatment
- No way to re-group or re-organize content by different analytical frames

## Expected Behavior

The review page should adapt to the user's cognitive state and analytical needs:

- Highlights appear in waves (staged reveal) so the user isn't overwhelmed on first load
- A slider or toggle controls highlight density, defaulting to sparse (Top 10-25%)
- Multiple saliency channels visible with independent toggles (importance, anomaly, claim-type, confidence)
- A toolbar lets users re-render content grouped by different schemas
- A right-side minimap provides spatial orientation and progress tracking

## Motivation

AI-generated text review imposes high cognitive load — the user must verify accuracy, assess structure, spot errors, and build a mental model of the content simultaneously. The current single-dimension highlighting approach helps with initial foraging but doesn't support the full sensemaking cycle (schema formation, anomaly detection, representational shifts). These five enhancements together address the well-documented cognitive failure modes of linear AI-output review, making the tool more effective for longer and more complex documents.

## Proposed Solution

All five enhancements live in the `generate` state's HTML template (no runner changes). The data model (`segments.json`) needs minor enrichment:

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

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/hitl-md.yaml` — `segment` state prompt (add multi-channel fields), `generate` state prompt (five new features), `score` state rubric (add criterion checks)

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

1. **Enrich segment schema** — update the `segment` state prompt to produce `channels` object per segment (importance, anomaly, claim_type, confidence)
2. **Implement staged highlighting** — JS tiered reveal logic + CSS transitions in the `generate` HTML
3. **Add density slider** — range input filtering highlighted segments by saliency threshold
4. **Build multi-channel rendering** — channel toggle controls, per-channel color coding, CSS class switching
5. **Add schema-switching toolbar** — view mode toggles with JS re-grouping/re-rendering
6. **Add minimap + State Rail** — Canvas-based proportional minimap with IntersectionObserver, click-to-navigate, and visit heatmap
7. **Update score rubric** — add evaluation criteria for each new feature to the `score` state
8. **Verify end-to-end** — run `ll-loop run hitl-md` and confirm all five features work under file://

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
- `/ll:capture-issue` - 2026-05-28T17:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1814a47-ceda-478f-aac4-3e3bf601d202.jsonl`

**Open** | Created: 2026-05-28 | Priority: P3
