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

No built-in loop produces a single-viewport, app-shell HTML artifact:

- `html-website-generator` emits scrolling single-page websites (its rubric scores a full-page screenshot).
- `html-anything` classifies the artifact type but has no viewport-fit rubric and no type override (inputs are only `description` and `artifact_mode`), so an app-shell request can be routed to `html-dashboard`/`html-website` non-deterministically.

## Expected Behavior

`ll-loop run html-webapp-generator "<description>"` converges on a self-contained `index.html` app-shell (header / sidebar / main panes) that fills the viewport (`100dvh`) with no document-level scroll at every configured viewport (default 1440x900, 1024x768, 375x667). Overflow is confined to internal scroll panes. Violations are caught by the non-LLM `viewport_gate`, which appends per-viewport measurements to the run's `critique.md` and routes back to `run_gen_eval` for regeneration; harness faults route to `failed`.

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

## Program Design

### Types

- Loop context contract mirrors `html-website-generator` (`pass_threshold`, `design_tokens_context`, `design_guidance_context`) plus `viewports: str` — space-separated `WxH` list, default `"1440x900 1024x768 375x667"`, parsed inside the `viewport_gate` node script.

### Signatures

- `cmd_validate(loop_name: str, args: argparse.Namespace, loops_dir: Path, logger: Logger) -> int` — existing `ll-loop validate` entry; validates the new YAML with no code change.
- `test_expected_loops_exist() -> None` — existing builtin-loop inventory test; extend its expected-name list with `html-webapp-generator`.
- `test_html_webapp_generator_structure(builtin_loops: list[Path]) -> None` — new: asserts the state set (`plan → run_gen_eval → smoke_test → viewport_gate → vision_gate → done`), the `viewport_gate` exit-code routing, and the critique-append contract.

### Call Path

`resolve_loop_path(loop_name, loops_dir)` (little_loops.fsm.loop_paths) -> `load_and_validate(path)` (little_loops.fsm.validation) -> FSM executor dispatches the `viewport_gate` shell action (non-LLM `node -e` Playwright probe) -> on `FAIL:` appends measurements to `${context.run_dir}/critique.md` and routes `on_no: run_gen_eval`.

No Python source changes: the loop is package data picked up by `get_builtin_loops_dir()` automatically; the only touched Python files are tests.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/html-webapp-generator.yaml` (new file; the deliverable)
- `README.md` — loop count line (~185) and loop list
- `scripts/README.md` — mirror sync (`command cp -f README.md scripts/README.md`)
- `scripts/tests/test_builtin_loops.py` — extend `test_expected_loops_exist` name list; add structure tests

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — consumed read-only via the `run_gen_eval` state (loop: oracles/generator-evaluator); must remain unchanged
- `little_loops.fsm.loop_paths` (`get_builtin_loops_dir`, `resolve_loop_path`) — discovers the new loop automatically once the YAML lands in package data

### Similar Patterns
- `scripts/little_loops/loops/html-website-generator.yaml` — state skeleton to copy (`plan → run_gen_eval → smoke_test → vision_gate → done` thin wrapper)
- `html-anything` / `html-dashboard` — classification-based generators without viewport-fit rubrics (the gap this loop fills)
- `smoke_test` / `vision_gate` states — Playwright `node -e` shell pattern, `FAIL:` exit-0 contract, and `.vision_rounds` round-cap file to mirror in `viewport_gate`

### Tests
- `scripts/tests/test_builtin_loops.py` — `builtin_loops` fixture auto-includes the new YAML (parse/validate/gate-completeness suites run over it); add name to `test_expected_loops_exist` (~line 254); add loop-specific structure tests next to the website-generator ones

### Documentation
- `docs/reference/loops.md`, `docs/guides/LOOPS_REFERENCE.md` — add the loop alongside `html-website-generator`
- README loop-count bump trips mirror gates (see Files to Modify)

### Configuration
- None required — the loop is self-contained; `viewports` is an optional per-run context override, not an `.ll/ll-config.json` key

## Implementation Steps

1. Create `scripts/little_loops/loops/html-webapp-generator.yaml` (new file) from `html-website-generator.yaml` with the app-shell generator prompt and rubric.
2. Add the `viewport_gate` state (multi-viewport overflow + bounding-box check, critique append, round cap).
3. Run `ll-loop validate html-webapp-generator` (MR rules, per-run artifacts under `${context.run_dir}`).
4. Update the README.md loop count and sync mirrors (`command cp -f README.md scripts/README.md`). Add the loop to the loop docs / catalog alongside `html-website-generator`.
5. Add tests for the loop's structure/validation, following the existing tests for `html-website-generator`.
6. Do one manual end-to-end run with a known-overflowing description to confirm the gate fails, writes critique, and converges.

## Impact

- **Priority**: P3 - additive generator variant; no consumer blocked, quality-of-life for HTML artifact workflows
- **Effort**: Medium - one new loop YAML with a new non-LLM gate state plus tests and doc/mirror updates; no Python source changes
- **Risk**: Low - purely additive; `oracles/generator-evaluator.yaml` and its 7 consumers untouched
- **Breaking Change**: No

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
- `/ll:format-issue` - 2026-09-25T22:12:18 - `8c81fde2-1b8f-4d35-a9d4-d9e034fb1af8.jsonl`
- `/ll:capture-issue` - 2026-09-25T02:02:39 - `09b7cc1a-1227-48d7-9d78-dac3ced876ba.jsonl`
