---
id: FEAT-3583
type: FEAT
title: Brainstorm mode profiles with automatic mode selection
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:13Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
- captured
blocked_by:
- FEAT-3582
---

# FEAT-3583: Brainstorm mode profiles with automatic mode selection

## Summary

Add **mode profiles as data** to the brainstorm engine plus **automatic mode
selection**: profiles `artifact`, `visual`, `functional`, `business`, selected by
`mode: auto` (default) in the first state after `init`.

## Current Behavior

Brainstorm has a single fixed pipeline with no notion of mode: every brief runs the same lenses, the same ranking prompt, and the same output shape, regardless of whether it is a name, a visual design, a functional design, or a business opportunity.

## Expected Behavior

- Each profile (a small YAML preset alongside the loop) sets: `reframe` on/off,
  default grid axes, idea schema, `ground` (none|codebase|web), `materialize`
  (none|render), tournament rubric, `premortem` on/off, output shape
  (grid | portfolio | winner + risks).
- `classify_mode` state runs right after `init` when `mode=auto`: LLM emits
  `{mode, confidence, rationale}` to the run dir; confidence below a threshold falls
  back to `artifact`.
- `mode=<x>` skips classification. Individual profile knobs can be overridden via
  context for mixed briefs.
- Downstream states read resolved profile values rather than hardcoded behavior;
  gated states route via `classify`-style routing like the current `route_sink`.

## Use Case

**Who**: A little-loops user running `ll-loop run brainstorm "<brief>"` with briefs of very different kinds — a product name, a landing-page look, an API design, a market opportunity.

**Context**: The engine should not treat every brief the same way; visual briefs need rendering, functional briefs need codebase grounding, business briefs need reframing and market evidence.

**Goal**: Have the loop pick the right behavior automatically, while still allowing an explicit `mode=` or per-knob override for mixed briefs.

**Outcome**: The run writes `${context.run_dir}/profile.json` recording the resolved profile, and downstream states behave per that profile.

## Motivation

EPIC-3581 identifies a mode mismatch: visual designs need rendered candidates judged visually, functional designs need codebase grounding, business opportunities need market grounding and reframing, and artifacts need breadth more than a single winner. Encoding this as data profiles avoids forking the loop into four copies and lets FEAT-3584/3585/3586 stay gated behind profile knobs.

## Proposed Solution

Add profiles as data alongside `scripts/little_loops/loops/brainstorm.yaml`, plus two states after `init`:

- Four profile presets (`artifact`, `visual`, `functional`, `business`), each setting `reframe`, grid axes, idea schema, `ground` (none|codebase|web), `materialize` (none|render), tournament rubric, `premortem`, and output shape.
- `classify_mode` (LLM, only when `mode=auto`) emits `{mode, confidence, rationale}`; confidence below a threshold falls back to `artifact`.
- `resolve_profile` (script) merges precedence explicit `mode=` > per-knob context override > profile default > fallback, and writes `${context.run_dir}/profile.json`.

Downstream states read resolved values from `profile.json`, and gated states route the way `route_sink` does today.

## Program Design

### Types

- `Profile`: `{mode: str, reframe: bool, axes: [str, str], ground: "none" | "codebase" | "web", materialize: "none" | "render", rubric: str, premortem: bool, output_shape: str}`
- `ModeDecision`: `{mode: str, confidence: float, rationale: str}`

### Signatures

- `classify_mode(brief: str) -> ModeDecision` — LLM state; result written to the run dir
- `resolve_profile(mode: str, overrides: dict[str, str], decision: ModeDecision | None) -> Profile` — deterministic script

### Call Path

`init` -> `classify_mode` -> `resolve_profile` -> `frame` -> `diverge` -> `route_sink`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/brainstorm.yaml` — add `classify_mode` and `resolve_profile` states; thread resolved values into `frame`/`diverge`/`tournament`/output prompts; add `mode` context key
- New profile files (proposed: `scripts/little_loops/loops/brainstorm-profiles/{artifact,visual,functional,business}.yaml`) — verify loop package-data inclusion in `scripts/pyproject.toml`

### Dependent Files (Callers/Importers)
- `ll-loop run brainstorm` callers and the sink adapters (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) inside the loop
- `scripts/little_loops/loops/lib/common.yaml` — imported fragments (`parse_tagged_json`, `queue_pop`, `retry_counter`)
- FEAT-3584, FEAT-3585, FEAT-3586 — read `ground`, `materialize`, and `premortem` from the resolved profile

### Similar Patterns
- `route_sink` in `scripts/little_loops/loops/brainstorm.yaml` — existing gated-routing pattern for the profile-gated states

### Tests
- `scripts/tests/test_brainstorm.py` — brainstorm loop structure/behavior tests
- `scripts/tests/test_builtin_loops.py` — built-in loop validation (`ll-loop validate`)
- New tests: profile schema validation, resolution precedence (explicit > override > profile > fallback), stubbed-classifier routing for one reference brief per mode

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` — brainstorm loop descriptions

### Configuration
- Context keys: add `mode` (default `auto`) and per-knob overrides (`ground`, `materialize`, `premortem`, `reframe`)

## Implementation Steps

1. Define profile schema and the four presets.
2. Add `classify_mode` + `resolve_profile` states.
3. Thread resolved values into reframe/diverge/tournament/output prompts.
4. Tests for resolution precedence (explicit > override > profile > fallback).

## Impact

- **Priority**: P2 - unblocks the gated states in FEAT-3584/3585/3586 but adds no value until FEAT-3582 lands
- **Effort**: Medium - new profile schema and two states; mostly data plus one deterministic resolver script
- **Risk**: Low - additive and gated behind `mode`; `mode=artifact` preserves generic behavior
- **Breaking Change**: No

## Acceptance Criteria

- Four profile files exist and are validated by a schema/test.
- One reference brief per mode is classified to the expected profile (test with a
  stubbed classifier output plus a documented manual reference run).
- Explicit `mode=` bypasses `classify_mode`; per-knob override beats profile default.
- Profile resolution is deterministic (script), and the resolved profile is written
  to `${context.run_dir}/profile.json`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:40 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
