---
id: FEAT-3585
type: FEAT
title: 'Brainstorm materialize state: rendered mockups judged visually'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:14Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
- captured
blocked_by:
- FEAT-3582
---

# FEAT-3585: Brainstorm materialize state: rendered mockups judged visually

## Summary

Add a gated `materialize` state for **visual** brainstorming: finalists are rendered
as standalone HTML/SVG mockups, screenshotted with Playwright, and the tournament
judges **image pairs** instead of text descriptions.

## Current Behavior

Brainstorm judges every idea as text, including visual ones: a "dense, warm-paper landing page" is ranked from its one-line description, never from a rendering.

## Expected Behavior

- Visual profile grid axes are visual dimensions (e.g. density × palette/typography
  temperament).
- For each shortlisted idea: LLM writes a self-contained HTML/SVG mockup under
  `${context.run_dir}/mockups/`; a Playwright probe (existing on-demand loop +
  probe pattern under `.loops/`, resolving Playwright from the global npm install)
  captures a PNG.
- Tournament pairs are judged from the two screenshots side by side (position
  swapped).
- Output includes a gallery section linking mockups + screenshots.
- Degrades gracefully when Playwright is unavailable: judges HTML source and notes
  the degradation in the report.

## Use Case

**Who**: A little-loops user brainstorming visual directions (landing page, UI theme, brand look).

**Context**: Text descriptions of visual ideas are hard to compare; the real differences show only when rendered.

**Goal**: Have finalists rendered as mockups and judged from screenshots rather than prose.

**Outcome**: `brainstorm.md` includes a ranked gallery linking each mockup and screenshot under the run dir.

## Motivation

EPIC-3581 lists visual designs as needing rendered candidates judged visually. Judging screenshots side by side (position swapped) removes the gap between how a design is described and how it looks, and follows the existing on-demand Playwright probe pattern rather than adding a new browser dependency.

## Proposed Solution

Add a gated `materialize` state to `scripts/little_loops/loops/brainstorm.yaml`, run only when the resolved profile sets `materialize=render`:

1. For each shortlisted idea, an LLM writes a self-contained HTML/SVG mockup to `${context.run_dir}/mockups/`.
2. A Playwright probe (on-demand pattern under `.loops/probes/`, Playwright resolved from the global npm install) captures a PNG per mockup.
3. `tournament` judges pairs from the two screenshots side by side, position swapped.
4. Output gains a gallery section linking mockups and screenshots.
5. If Playwright is unavailable, judge the HTML source and note the degradation in the report; a render failure drops only that idea.

## Program Design

### Types

- `Mockup`: `{idea_id: str, html_path: str, png_path: str, rendered: bool}`

### Signatures

- `render_mockup(idea: IdeaRecord, run_dir: str) -> Mockup` — LLM writes HTML/SVG under `mockups/`
- `capture_screenshot(html_path: str, png_path: str) -> bool` — Playwright probe, False on failure
- `judge_pair_visual(a: Mockup, b: Mockup) -> PairVerdict` — image-pair judgment, both orders

### Call Path

`diverge` -> `materialize` -> `capture_screenshot` -> `feat-3488-browser-probes.mjs` -> `tournament`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/brainstorm.yaml` — add gated `materialize` state, screenshot step, image-pair judging, gallery output
- New probe under `.loops/probes/` (proposed name: `brainstorm-materialize-probes.mjs`)

### Dependent Files (Callers/Importers)
- `ll-loop run brainstorm` callers and the sink adapters (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) inside the loop
- `scripts/little_loops/loops/lib/common.yaml` — imported fragments (`parse_tagged_json`, `queue_pop`, `retry_counter`)

### Similar Patterns
- `.loops/probes/feat-3488-browser-probes.mjs`, `enh-3506-theme-probes.mjs`, `enh-3507-served-page-probes.mjs` — existing on-demand Playwright probe pattern

### Tests
- `scripts/tests/test_brainstorm.py` — brainstorm loop structure/behavior tests
- `scripts/tests/test_builtin_loops.py` — built-in loop validation (`ll-loop validate`)
- No pytest gate may depend on Playwright; test only the gating and degradation logic with stubbed probe output

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` — brainstorm loop descriptions

### Configuration
- Context key: `materialize` (none|render), normally resolved from the profile (FEAT-3583); Playwright from the global npm install (`~/.npm-global/@playwright/test`)

## Implementation Steps

1. Add the `materialize` state, gated on the resolved profile (FEAT-3583), writing only under `${context.run_dir}/mockups/`.
2. Write the Playwright screenshot probe modeled on the existing `.loops/probes/*.mjs` scripts, resolving Playwright from the global npm install.
3. Extend `tournament` to judge screenshot pairs (position swapped) and fall back to HTML-source judging when Playwright is missing.
4. Add the gallery section to the output and drop, not fail on, per-idea render errors.
5. Validate with `ll-loop validate brainstorm` and one documented manual visual-mode run; keep browser probes out of the pytest gate.

## Impact

- **Priority**: P3 - improves visual-mode quality only; the core and other modes work without it
- **Effort**: Large - LLM-authored mockups, a browser probe, image-pair judging, and graceful degradation
- **Risk**: Medium - depends on a local Playwright install; contained by graceful fallback and per-idea failure handling
- **Breaking Change**: No

## Acceptance Criteria

- Mockups and screenshots land only under the run dir.
- A render failure for one idea drops that idea, not the run.
- No pytest gate depends on Playwright (browser probes stay on-demand).
- Reference visual-mode run produces ≥ N rendered finalists and a ranked gallery.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:48 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
