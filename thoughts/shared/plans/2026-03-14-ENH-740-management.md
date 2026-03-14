# Plan: ENH-740 — Verbose Loop History Show LLM Call Details

Date: 2026-03-14

## Problem

`ll-loop history <loop-name> --verbose` doesn't show LLM call inputs/outputs, model, or latency. The data either isn't logged or isn't rendered.

## Root Cause Analysis

**Two gaps identified:**

1. **`evaluate_llm_structured` doesn't capture metadata** — no latency measurement, no prompt stored in details, no model name in details.

2. **Default evaluate emit is incomplete** — `executor.py:654-660` only emits `type` + `verdict`, dropping all `result.details` (confidence, reason, prompt, latency). The explicit eval path at `executor.py:687-694` correctly spreads `result.details`.

3. **`_format_history_event` doesn't render all available data** — `action_complete` ignores `output_preview`, `evaluate` ignores `raw`.

## Solution

### Change 1: `evaluators.py:evaluate_llm_structured`
- Add `import time` 
- Measure `latency_ms = int((time.monotonic() - t0) * 1000)` around `subprocess.run`
- Add to all success-path `details` dicts: `llm_model`, `llm_latency_ms`, `llm_prompt` (the constructed `user_prompt`, truncated to 500 chars for storage)

### Change 2: `executor.py` default evaluate emit
- Spread `result.details` into the emit dict (line 654-660), matching the explicit path.

### Change 3: `info.py:_format_history_event`
- `action_complete` (verbose=True): show `output_preview` below the exit/duration line
- `evaluate` (verbose=True): if event has `llm_model` or `llm_prompt`, render an LLM call block showing truncated prompt, model, latency_ms, and reason
- Add `full: bool` parameter — when True, show untruncated prompt/output_preview

### Change 4: `info.py:cmd_history`
- Read `full = getattr(args, "full", False)` and pass to `_format_history_event`

### Change 5: `__init__.py`
- Add `--full` flag to `history` subcommand

## Output Format (verbose)

```
10:23:45  evaluate        ✓ success  confidence=0.95  The output looks correct
          LLM Call  model=claude-sonnet-4-6  latency=1204ms
          Prompt:   You are reviewing issue ENH-123. Evaluate whether the action...
          Response: {"verdict": "success", "confidence": 0.95, "reason": "The outp..."}
```

## Files to Modify
- `scripts/little_loops/fsm/evaluators.py`
- `scripts/little_loops/fsm/executor.py`
- `scripts/little_loops/cli/loop/info.py`
- `scripts/little_loops/cli/loop/__init__.py`
- `scripts/tests/test_ll_loop_commands.py` (new tests for verbose LLM block rendering)

## Out of Scope
- Token counts (not available from subprocess interface)
- Tool call rendering
- Changes to core FSM execution
