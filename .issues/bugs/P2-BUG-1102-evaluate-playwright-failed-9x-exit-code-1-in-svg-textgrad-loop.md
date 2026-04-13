---
discovered_date: 2026-04-13
discovered_by: analyze-loop
source_loop: svg-textgrad
source_state: evaluate
---

# BUG-1102: evaluate action failed 9x (exit_code=1) in svg-textgrad loop

## Summary

The `evaluate` state in the `svg-textgrad` loop runs `playwright screenshot "file://<run_dir>/image.svg" ...` to capture a screenshot and verify the SVG rendered correctly. On every single iteration of a 20-iteration run, playwright exited with code 1 — the `CAPTURED` sentinel was never echoed, `on_yes` routing to `score` was never reached, and the loop exhausted its max_iterations limit without ever evaluating a single SVG. The output preview shows playwright navigating to the file but failing silently.

## Current Behavior

On every `evaluate` state entry, the action runs `playwright screenshot "file://<run_dir>/image.svg" ...`. Playwright prints "Navigating to file://..." then exits with code 1. The `CAPTURED` sentinel is never echoed, causing the `output_contains` evaluator to return `no` (no match). The loop routes back to `generate` instead of `score`, repeating this cycle all 20 iterations until `max_iterations` terminates the run. The `score` → `compute_gradient` → `apply_gradient` optimization cycle is never entered.

## Steps to Reproduce

1. Run the `svg-textgrad` loop: `ll-loop run svg-textgrad`
2. Observe the `evaluate` state on iteration 1
3. Check the action output: playwright prints "Navigating to file://..." then exits with `exit_code=1`
4. Observe: `CAPTURED` sentinel is not echoed; loop routes back to `generate`
5. Repeat for all iterations — the loop terminates via `max_iterations` without ever reaching `score`

## Loop Context

- **Loop**: `svg-textgrad`
- **State**: `evaluate`
- **Signal type**: action_failure
- **Occurrences**: 9 (all 9 evaluate attempts)
- **Last observed**: `2026-04-13T21:10:22.656389+00:00`

## History Excerpt

Events leading to this signal (representative sample from first and last failures):

```json
[
  {"event": "state_enter", "ts": "2026-04-13T21:01:56.195832+00:00", "state": "evaluate", "iteration": 2},
  {"event": "action_complete", "ts": "2026-04-13T21:01:57.048170+00:00", "exit_code": 1, "duration_ms": 852, "output_preview": "Navigating to file://.loops/tmp/svg-textgrad/20260413-210026/image.svg", "is_prompt": false},
  {"event": "evaluate", "ts": "2026-04-13T21:01:57.048354+00:00", "type": "output_contains", "verdict": "no", "matched": false, "pattern": "CAPTURED", "negate": false},
  {"event": "route", "ts": "2026-04-13T21:01:57.048435+00:00", "from": "evaluate", "to": "generate"},
  {"event": "state_enter", "ts": "2026-04-13T21:10:22.275902+00:00", "state": "evaluate", "iteration": 20},
  {"event": "action_complete", "ts": "2026-04-13T21:10:22.656389+00:00", "exit_code": 1, "duration_ms": 380, "output_preview": "Navigating to file://.loops/tmp/svg-textgrad/20260413-210026/image.svg", "is_prompt": false},
  {"event": "evaluate", "ts": "2026-04-13T21:10:22.656590+00:00", "type": "output_contains", "verdict": "no", "matched": false, "pattern": "CAPTURED", "negate": false},
  {"event": "loop_complete", "ts": "2026-04-13T21:10:22.656777+00:00", "final_state": "generate", "iterations": 20, "terminated_by": "max_iterations"}
]
```

## Expected Behavior

Playwright should successfully screenshot the generated SVG file and exit 0, allowing the loop to reach the `score` state and provide feedback to the `compute_gradient` → `apply_gradient` optimization cycle.

## Root Cause

- **File**: `.loops/loops/svg-textgrad/loop.yaml` (evaluate action definition)
- **Anchor**: `evaluate` state action command
- **Cause**: TBD — requires investigation. Likely causes: playwright binary not on `$PATH` or wrong command name (needs `npx playwright`); relative `file://` URI instead of absolute `file:///abs/path/image.svg`; or playwright browser binaries not installed (needs `playwright install chromium`). Stderr is not captured in the action output, hiding the specific failure reason.

## Proposed Solution

Investigate why `playwright screenshot` exits with code 1 on `file://` URIs for locally-written SVG files. Likely causes:

1. **Playwright not installed / wrong binary name** — verify `playwright` is on `$PATH` and the correct command (may need `npx playwright` or a full install).
2. **File path quoting** — the action uses `"file://${captured.run_dir.output}/image.svg"` which may produce a relative `file://` URI; needs an absolute path (e.g. `file:///abs/path/image.svg`).
3. **SVG validity** — playwright may reject an SVG with invalid markup; add a pre-check with `xmllint --noout` before screenshotting.
4. **Playwright browser missing** — run `playwright install chromium` to ensure browser binaries are present.

Add stderr capture to the evaluate action so the failure reason is visible in `output_preview`.

## Implementation Steps

1. Run `playwright screenshot` manually against a known-good SVG `file://` URI to reproduce and capture stderr
2. Fix the root cause in `.loops/loops/svg-textgrad/loop.yaml` `evaluate` action (binary name, absolute path, or browser install)
3. Add `2>&1` stderr redirect to the evaluate action command so failures surface in `output_preview`
4. Run the `svg-textgrad` loop and verify `evaluate` exits 0 and `CAPTURED` is echoed at least once
5. Confirm the loop reaches `score` → `compute_gradient` → `apply_gradient` cycle

## Integration Map

### Files to Modify
- `.loops/loops/svg-textgrad/loop.yaml` — `evaluate` state action command (fix binary, path, stderr redirect)

### Dependent Files (Callers/Importers)
- N/A — loop YAML is self-contained; no Python callers depend on this action command directly

### Similar Patterns
- Other loops using `playwright` in evaluate actions — check `.loops/loops/*/loop.yaml` for similar `playwright screenshot` commands that may have the same path quoting issue

### Tests
- TBD — no automated tests for loop YAML action correctness; manual run of `svg-textgrad` loop confirms fix

### Documentation
- N/A

### Configuration
- N/A

## Acceptance Criteria

- [ ] `evaluate` state exits with code 0 when a valid SVG is present at the run directory
- [ ] `CAPTURED` is echoed on success, allowing routing to `score`
- [ ] The loop reaches `score` → `compute_gradient` → `apply_gradient` cycle at least once per run
- [ ] Playwright failure message is surfaced in `output_preview` (stderr redirect added)

## Impact

- **Priority**: P2 — Loop is completely non-functional; the optimization cycle never runs, making the `svg-textgrad` loop useless until fixed
- **Effort**: Small — root cause is likely a one-line fix (binary name or path); stderr redirect is a one-liner
- **Risk**: Low — change is isolated to the `evaluate` action in a single loop YAML; no shared code paths affected
- **Breaking Change**: No

## Labels

`bug`, `loops`, `captured`

## Status

**Open** | Created: 2026-04-13 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-04-13T21:16:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fd5585d9-0d17-46c7-8655-fca6a1847cf7.jsonl`
