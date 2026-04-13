---
discovered_date: 2026-04-13
discovered_by: analyze-loop
source_loop: svg-textgrad
source_state: evaluate
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
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

- **File**: `scripts/little_loops/loops/svg-textgrad.yaml` (also `scripts/little_loops/loops/svg-image-generator.yaml` — identical bug)
- **Anchor**: `evaluate` state action (line 87); `init` state (lines 29–33)
- **Cause**: The `init` state echoes a **relative** path — `DIR="${context.output_dir}/$TS"` resolves to `.loops/tmp/svg-textgrad/<timestamp>`. The `evaluate` state substitutes this into `file://${captured.run_dir.output}/image.svg`, producing `file://.loops/tmp/...` — an invalid file URI. RFC 8089 requires `file:///` followed by an absolute POSIX path; without the leading `/`, playwright parses `.loops` as a hostname and fails to load the file, exiting code 1. The playwright binary itself is found and launches correctly (confirmed by "Navigating to file://..." in `output_preview`). Stderr is piped separately by `runners.py:126-132` and excluded from `output_preview` (`executor.py:522` only includes stdout), which hides the specific playwright error.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Interpolation: `scripts/little_loops/fsm/interpolation.py:188-199` — `${captured.run_dir.output}` substituted literally with the raw captured string; no path resolution applied
- Capture: `scripts/little_loops/fsm/executor.py:535-541` — stores raw stdout of `init` shell action, stripping only trailing newlines
- Shell dispatch: `scripts/little_loops/fsm/runners.py:126-132` — `bash -c` with `stderr=subprocess.PIPE` (separate from stdout; not merged into `output`)
- Output preview: `scripts/little_loops/fsm/executor.py:522` — `output_preview = result.output[-2000:].strip()` — only stdout; stderr absent from event log

## Proposed Solution

Investigate why `playwright screenshot` exits with code 1 on `file://` URIs for locally-written SVG files. Likely causes:

1. **Playwright not installed / wrong binary name** — verify `playwright` is on `$PATH` and the correct command (may need `npx playwright` or a full install).
2. **File path quoting** — the action uses `"file://${captured.run_dir.output}/image.svg"` which may produce a relative `file://` URI; needs an absolute path (e.g. `file:///abs/path/image.svg`).
3. **SVG validity** — playwright may reject an SVG with invalid markup; add a pre-check with `xmllint --noout` before screenshotting.
4. **Playwright browser missing** — run `playwright install chromium` to ensure browser binaries are present.

Add stderr capture to the evaluate action so the failure reason is visible in `output_preview`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Confirmed cause** — Option #1 ("playwright not installed / wrong binary name") is ruled out: the binary resolves and playwright prints "Navigating to file://..." before failing. The failure is the malformed `file://` URI.

**Confirmed fix** — Change the `init` state in both loops to echo an absolute path:
```yaml
# Before (svg-textgrad.yaml:33, svg-image-generator.yaml:33)
echo "$DIR"
# After
echo "$(pwd)/$DIR"
```
This makes `${captured.run_dir.output}` an absolute path everywhere it is referenced downstream (evaluate, append_gradient, etc.), producing a valid `file:///abs/path/image.svg` URI.

## Implementation Steps

1. Fix `scripts/little_loops/loops/svg-textgrad.yaml:33` — change `echo "$DIR"` to `echo "$(pwd)/$DIR"` so `init` captures an absolute path
2. Fix `scripts/little_loops/loops/svg-image-generator.yaml:33` — same change (identical bug)
3. Fix `scripts/little_loops/loops/svg-textgrad.yaml:87` — add `2>&1` to playwright command: `playwright screenshot "file://${captured.run_dir.output}/image.svg" "${captured.run_dir.output}/screenshot.png" 2>&1 && echo "CAPTURED"`
4. Fix `scripts/little_loops/loops/svg-image-generator.yaml:98` — same `2>&1` addition
5. Run `ll-loop run svg-textgrad` and verify `evaluate` exits 0 and `CAPTURED` is echoed at least once
6. Confirm the loop reaches `score` → `compute_gradient` → `apply_gradient` cycle
7. Update `scripts/tests/test_builtin_loops.py` `TestSvgTextgradLoop` (line ~1511) to assert the `init` action echoes `$(pwd)/...` (absolute path)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Add to `TestSvgImageGeneratorLoop` — assert `init` action contains `$(pwd)` (follow pattern at `test_builtin_loops.py:891–897`: `action = state.get("action", ""); assert "$(pwd)" in action`)
9. Add to `TestSvgTextgradLoop` — same `$(pwd)` assertion for `init` action (step 7 covers only `TestSvgTextgradLoop`; step 8 covers `TestSvgImageGeneratorLoop`)
10. Add to `TestSvgTextgradLoop` — 4 evaluate-state tests mirroring `TestSvgImageGeneratorLoop:1467–1487`: `action_type: shell`, `output_contains`/`CAPTURED` pattern, `on_yes: score`, `on_no: generate`
11. Add to both `TestSvgTextgradLoop` and `TestSvgImageGeneratorLoop` — assert `evaluate` action contains `2>&1` (validates the stderr redirect is present)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/svg-textgrad.yaml:33` — `init` state: change `echo "$DIR"` to `echo "$(pwd)/$DIR"` to capture an absolute path
- `scripts/little_loops/loops/svg-textgrad.yaml:87` — `evaluate` action: add `2>&1` before `&& echo "CAPTURED"` to surface playwright stderr
- `scripts/little_loops/loops/svg-image-generator.yaml:33` — same `init` state echo fix (identical relative-path bug)
- `scripts/little_loops/loops/svg-image-generator.yaml:98` — same `evaluate` action stderr fix (identical bug)

### Dependent Files (Callers/Importers)
- N/A — loop YAML is self-contained; no Python callers depend on this action command directly

### Similar Patterns
- `scripts/little_loops/loops/svg-image-generator.yaml:98` — identical `file://${captured.run_dir.output}/image.svg` command; same relative-path `init` at line 33; needs the same fix
- `scripts/little_loops/loops/html-website-generator.yaml:77` — uses `${context.output_dir}` directly (no `init` capture); different pattern, not affected by this bug
- `scripts/little_loops/loops/evaluation-quality.yaml:53-54` — `eval "$CMD" 2>&1 | tee ...` pattern to follow for stderr capture
- `scripts/little_loops/loops/svg-textgrad.yaml:170-177` — `append_gradient` state also uses `${captured.run_dir.output}` for file writes; will benefit from absolute path captured in `init` (no `file://` issue, but cleaner paths)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:1545–1550` — `TestSvgTextgradLoop.test_init_state_is_shell_with_capture` — existing; checks `action_type`, `capture`, `next` only; does NOT read action string. **Not broken** by `$(pwd)` change.
- `scripts/tests/test_builtin_loops.py:1455–1460` — `TestSvgImageGeneratorLoop.test_init_state_is_shell_with_capture` — same shape; also does not read action string. **Not broken**.
- `scripts/tests/test_builtin_loops.py:1467–1487` — `TestSvgImageGeneratorLoop` — 4 evaluate-state tests (shell type, `output_contains`/`CAPTURED`, `on_yes: score`, `on_no: generate`); no action string assertions. **Not broken** by `2>&1` addition.
- `scripts/tests/test_builtin_loops.py` — **`TestSvgTextgradLoop` gap**: no evaluate-state tests exist; add 4 tests mirroring `TestSvgImageGeneratorLoop:1467–1487` (`action_type: shell`, `output_contains` evaluator, `on_yes: score`, `on_no: generate`)
- `scripts/tests/test_builtin_loops.py` — **Both classes gap**: add test asserting `init` action contains `$(pwd)` — follow pattern at lines 891–897: `action = init.get("action", ""); assert "$(pwd)" in action`
- `scripts/tests/test_builtin_loops.py` — **Both classes gap**: add test asserting `evaluate` action contains `2>&1` — same string-in-action pattern

### Documentation
- N/A

### Configuration
- N/A

## Acceptance Criteria

- [x] `evaluate` state exits with code 0 when a valid SVG is present at the run directory
- [x] `CAPTURED` is echoed on success, allowing routing to `score`
- [x] The loop reaches `score` → `compute_gradient` → `apply_gradient` cycle at least once per run
- [x] Playwright failure message is surfaced in `output_preview` (stderr redirect added)

## Impact

- **Priority**: P2 — Loop is completely non-functional; the optimization cycle never runs, making the `svg-textgrad` loop useless until fixed
- **Effort**: Small — root cause is likely a one-line fix (binary name or path); stderr redirect is a one-liner
- **Risk**: Low — change is isolated to the `evaluate` action in a single loop YAML; no shared code paths affected
- **Breaking Change**: No

## Labels

`bug`, `loops`, `captured`

## Resolution

Fixed in `svg-textgrad.yaml` and `svg-image-generator.yaml`:
1. `init` state now echoes `$(pwd)/$DIR` producing an absolute path captured into `run_dir`
2. `evaluate` action adds `2>&1` to surface playwright stderr in `output_preview`
Both fixes applied identically to the sibling `svg-image-generator` loop.
New tests added to `TestSvgTextgradLoop` (4 evaluate-state + 2 assertion tests) and `TestSvgImageGeneratorLoop` (2 assertion tests). All 32 tests pass.

## Status

**Resolved** | Created: 2026-04-13 | Closed: 2026-04-13 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-04-13T21:41:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a86dde56-89fe-4aa9-8745-62e28440c3ca.jsonl`
- `/ll:wire-issue` - 2026-04-13T21:24:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c747beff-7e43-47bc-99a8-7f6f0bb6cb61.jsonl`
- `/ll:refine-issue` - 2026-04-13T21:21:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f39523a9-97cc-418d-92e6-6b9bb0352a28.jsonl`
- `/ll:format-issue` - 2026-04-13T21:16:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fd5585d9-0d17-46c7-8655-fca6a1847cf7.jsonl`
- `/ll:confidence-check` - 2026-04-13T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fda6395c-5a12-49f3-b6ab-3be2fa830521.jsonl`
- `/ll:manage-issue` - 2026-04-13T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
