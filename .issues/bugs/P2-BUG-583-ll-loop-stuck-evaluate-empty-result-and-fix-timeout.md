---
id: BUG-583
type: BUG
priority: P2
status: open
discovered_date: 2026-03-05
discovered_by: capture-issue
---

# BUG-583: ll-loop Stuck — evaluate "Empty result field" + fix State Timeout

## Summary

`ll-loop run issue-refinement --verbose` cycles infinitely with zero progress due to two compounding bugs:

1. `evaluate_llm_structured` always errors with "Empty result field in Claude CLI response" — the `evaluate` state can never produce `success`, so `done` is unreachable.
2. The `fix` state in `.loops/issue-refinement.yaml` has no `timeout:` key, so it inherits the 120s default from `executor.py` — Claude is killed mid-refinement every iteration.

Three output clarity gaps compound the debugging difficulty:

3. `display_progress` in `_helpers.py` never shows the `raw_preview` detail field on evaluate errors, making the root cause invisible without reading source.
4. Exit code 124 is displayed as `exit: 124` — opaque; should read "timed out".
5. `ll-issues refine-status` prints its full legend block on every evaluate iteration, drowning signal in noise.

## Current Behavior

- `evaluate` state calls `evaluate_llm_structured` → Claude CLI returns envelope with empty `result` field → returns `verdict="error"` → routes via `on_error: fix` every iteration
- `fix` state spawns Claude CLI with 120s timeout → Claude is killed after exactly 2 minutes → `output=""` → no refinement work happens
- Output shows `✗ error: Empty result field in Claude CLI response` on every iteration with no diagnostic detail
- Output shows `(2m 0s)  exit: 124` with no indication this is a timeout
- Full legend block (`Key:`, `source`, `norm`, `fmt`, ...) printed after every evaluate table
- Loop runs indefinitely, never reaching `done`

## Expected Behavior

- `evaluate` LLM evaluator correctly parses the Claude CLI JSON envelope and returns `success`/`failure` verdicts
- `fix` state completes a full refinement cycle (format → verify → map → confidence-check → refine-issue) before timing out; should allow 10–20 minutes
- `raw_preview` is shown below evaluate error messages to aid diagnosis
- Timeout is displayed as `timed out` not `exit: 124`
- Legend printed only on first iteration (or suppressed in verbose loops via a flag)

## Root Cause

### Bug 1: Empty result field in Claude CLI envelope
- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Function**: `evaluate_llm_structured` (line 482–489)
- The function calls `claude --output-format json --json-schema <schema>` and expects `{"result": "<json-string>", ...}`. The `result` field is empty (`""` or absent), hitting the else-branch guard. The Claude CLI JSON envelope format may have changed across versions — the structured output object may now be embedded in a different key.
- Because `on_error: fix` is set in `evaluate` state, this silently falls through to `fix` — no error is surfaced prominently and the loop continues rather than halting.

### Bug 2: Fix state timeout too short
- **File**: `.loops/issue-refinement.yaml` (fix state, no `timeout:` key)
- **Executor**: `scripts/little_loops/fsm/executor.py:523` — `timeout=state.timeout or 120`
- The complex fix prompt requires Claude to run `/ll:format-issue`, `/ll:verify-issues`, `/ll:map-dependencies`, `/ll:confidence-check`, `/ll:refine-issue` sequentially — typically 10–20 minutes. The 120s default kills Claude every time.

### Gap 3: raw_preview hidden on evaluate errors
- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Function**: `display_progress` evaluate event handler (lines 275–295)
- The `evaluate` event carries `raw_preview` in its details dict (populated from `evaluators.py:483`), but `display_progress` only reads `error`, `confidence`, and `reason` — `raw_preview` is discarded.

### Gap 4: Opaque exit code 124
- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Function**: `display_progress` action_complete handler (lines 256–259)
- Exit code 124 is the standard `timeout` exit code but is printed as `exit: 124` with no human-readable label.

### Gap 5: Repeated legend
- **File**: `scripts/little_loops/cli/issues/refine_status.py` (outputs legend unconditionally)
- **Caller**: `_helpers.py` `display_progress` action_complete handler prints all `output_preview` lines
- Every `evaluate` iteration reprints the full legend (9 lines). No mechanism to suppress after first print.

## Proposed Solution

### Fix Bug 1 — diagnose and fix the envelope parsing
1. In `evaluate_llm_structured`, log `proc.stdout[:500]` when `result` is empty to identify what the CLI actually returns.
2. Check if the current Claude CLI version places the structured object in a different envelope key (e.g., top-level JSON, or `content[0].text`).
3. Update the parsing to handle the current format; add a fallback that tries `envelope` itself as the result object if `result` is absent.

### Fix Bug 2 — add timeout to fix state
In `.loops/issue-refinement.yaml`, add `timeout: 1200` (20 minutes) to the `fix` state:
```yaml
fix:
  action_type: prompt
  timeout: 1200
  action: |
    ...
```

### Fix Gap 3 — show raw_preview on errors
In `_helpers.py` `display_progress` evaluate handler, after printing `verdict_line`:
```python
raw_preview = event.get("raw_preview", "")
if raw_preview and verdict == "error":
    print(f"         raw: {raw_preview[:200]}", flush=True)
```

### Fix Gap 4 — humanize exit code 124
In `_helpers.py` action_complete handler:
```python
if exit_code == 124:
    parts.append("timed out")
elif exit_code != 0:
    parts.append(f"exit: {exit_code}")
```

### Fix Gap 5 — suppress repeated legend
Option A: Pass `--no-legend` flag to `ll-issues refine-status` if supported (add the flag to `refine_status.py`).
Option B: In `display_progress`, track whether the legend has been printed and strip it from subsequent iterations using a state flag in the closure.

## Implementation Steps

1. Add debug logging to `evaluate_llm_structured` — print raw envelope when `result` is empty — reproduce locally to identify the actual envelope format
2. Fix envelope parsing in `evaluators.py` to match current CLI output format
3. Add `timeout: 1200` to `fix` state in `.loops/issue-refinement.yaml`
4. Show `raw_preview` in `_helpers.py` evaluate error display
5. Translate exit code 124 to "timed out" in `_helpers.py` action_complete display
6. Add `--no-legend` flag to `ll-issues refine-status` and pass it from the loop yaml (or implement closure-based suppression in `display_progress`)
7. Verify loop makes progress end-to-end with `ll-loop run issue-refinement --verbose`

## Files to Modify

- `scripts/little_loops/fsm/evaluators.py` — `evaluate_llm_structured` envelope parsing
- `scripts/little_loops/cli/loop/_helpers.py` — `display_progress` action_complete + evaluate handlers
- `.loops/issue-refinement.yaml` — add `timeout: 1200` to fix state
- `scripts/little_loops/cli/issues/refine_status.py` — add `--no-legend` flag (optional)

## Impact

- **Priority**: P2 — `ll-loop run issue-refinement` is completely broken; produces zero output, cycles indefinitely
- **Effort**: Medium — Bug 1 requires diagnosis before fix; Bugs 2–5 are small targeted changes
- **Risk**: Low — changes are isolated to display and loop config; no schema or API changes
- **Breaking Change**: No

## Session Log

- `/ll:capture-issue` - 2026-03-05T03:36:22Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`

---

**Open** | Created: 2026-03-05 | Priority: P2
