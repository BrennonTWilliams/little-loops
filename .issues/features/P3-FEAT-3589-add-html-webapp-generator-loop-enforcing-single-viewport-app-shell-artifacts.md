---
id: FEAT-3589
type: FEAT
title: Add html-webapp-generator loop enforcing single-viewport app-shell artifacts
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T02:02:32Z'
---

# FEAT-3589: Add html-webapp-generator loop enforcing single-viewport app-shell artifacts

## Summary

Add a standalone built-in FSM loop, `html-webapp-generator`, that produces a single-viewport, webapp-style HTML artifact: an app-shell layout with no document-level scroll. It is enforced by a non-LLM Playwright viewport gate, not just prompt wording.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

No existing loop forces single-viewport output:

- `html-website-generator` (`scripts/little_loops/loops/html-website-generator.yaml`) builds scrolling single-page websites. Its rubric explicitly scores a full-page screenshot.
- `html-anything` classifies the artifact type (`html-dashboard`, `html-website`, ...), but no rubric requires fitting one viewport. It exposes no type override either: its only inputs are `description` and `artifact_mode`. Adding an `html-webapp` type there would make routing non-deterministic, because the classifier could pick `html-dashboard` for the same description. A standalone loop gives deterministic behavior and has no coupling to `html-anything`.

## Proposed Solution

Copy the thin-wrapper shape of `html-website-generator`:

```
plan → run_gen_eval (loop: oracles/generator-evaluator) → smoke_test → viewport_gate → vision_gate → done
```

1. **Generator prompt**: require an app-shell layout sized to the viewport (`100dvh`). No document scroll. Internal scroll panes are allowed (message lists, sidebars, tables). Do **not** mandate `overflow: hidden` on `body`: that invites the generator to clip content off-screen to pass the check.
2. **Rubric**: keep the website-generator criteria and add an app-shell / layout-fit criterion (primary regions visible, no content cut off, sensible pane-level scrolling).
3. **`viewport_gate`** (new non-LLM shell state, same Playwright pattern as `smoke_test`: `NODE_PATH="$(npm root -g)" node -e ...`). At each viewport size (proposed: 1440x900, 1024x768, 375x667):
   - assert `document.documentElement.scrollHeight <= innerHeight` and `scrollWidth <= innerWidth`. `scrollHeight` counts overflowed content even under `overflow: hidden`, so page-level clipping is still caught.
   - assert the bounding boxes of key interactive elements (`button`, `a`, `input`, `select`, `textarea`, `[role=button]`) that are visible and not inside a scrollable ancestor lie within the viewport. This catches content clipped inside `overflow: hidden` containers.
4. **Feedback on failure**: before routing back to `run_gen_eval`, `viewport_gate` must append the measured dimensions and overflow amounts per viewport to `${context.run_dir}/critique.md` under an `## Issues to Address` heading, as `vision_gate` does. `smoke_test` writes nothing on failure, which would leave the regeneration pass blind to why it failed.
5. **Exit-code contract** (matches `smoke_test`): an artifact failure prints `FAIL:...` and exits 0 → `on_no: run_gen_eval`. A harness fault (node/Playwright missing, unreadable path) exits non-zero → `on_error: failed`. Bound ping-pong with a per-run round-cap file (like `vision_gate`'s `.vision_rounds`). At the cap, route to `failed` (or accept with a warning: decide during implementation).

### Explicitly out of scope: the shared oracle

Do **not** modify `scripts/little_loops/loops/oracles/generator-evaluator.yaml`. Its evaluate state hardcodes `playwright screenshot --full-page`, and 7 loops consume the oracle. No change is needed: for a page that doesn't scroll, a full-page screenshot equals the viewport screenshot. For a page that overflows, the full-page screenshot shows the overflow to the LLM scorer, which is better evidence than a viewport crop.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. Create `scripts/little_loops/loops/html-webapp-generator.yaml` from `html-website-generator.yaml` with the app-shell generator prompt and rubric.
2. Add the `viewport_gate` state (multi-viewport overflow + bounding-box check, critique append, round cap).
3. Run `ll-loop validate html-webapp-generator` (MR rules, per-run artifacts under `${context.run_dir}`).
4. Update the README.md loop count and sync mirrors (`command cp -f README.md scripts/README.md`). Add the loop to the loop docs / catalog alongside `html-website-generator`.
5. Add tests for the loop's structure/validation, following the existing tests for `html-website-generator`.
6. Do one manual end-to-end run with a known-overflowing description to confirm the gate fails, writes critique, and converges.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Use Case

A user runs `ll-loop run html-webapp-generator "kanban board for a 4-person team"`. The result is a self-contained `index.html` that fills the browser window like an app (header / sidebar / main pane). Long lists scroll inside their own panes, and the page itself never scrolls at 1440x900, 1024x768 or 375x667.

## API/Interface

New loop `html-webapp-generator` with `input_key: description` and `required_inputs: ["description"]`. Context mirrors `html-website-generator` (`pass_threshold`, `design_tokens_context`, `design_guidance_context`), with an optional `viewports` context value (default `"1440x900 1024x768 375x667"`).

## Open Questions

- **Mobile semantics**: a content-rich app shell at 375x667 with zero scrolling is often infeasible. Proposed default: "no document scroll; internal scroll panes allowed". Alternative: exempt the mobile viewport from the gate, or only require no horizontal overflow there.
- Round-cap exhaustion: fail, or accept with a warning?

## Acceptance Criteria

- `ll-loop validate html-webapp-generator` passes.
- `viewport_gate` fails (exit 0, `FAIL:` output) for a page whose document scrolls at any configured viewport, and appends per-viewport measurements to `critique.md`.
- `viewport_gate` passes for an app-shell page whose overflow is confined to internal scroll panes.
- Harness faults route to `failed`, not back to `run_gen_eval`.
- `oracles/generator-evaluator.yaml` is unchanged.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-25T02:02:39 - `09b7cc1a-1227-48d7-9d78-dac3ced876ba.jsonl`
