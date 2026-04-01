---
discovered_date: 2026-03-31
discovered_by: capture-issue
---

# BUG-903: `llm_structured` evaluator 1800s timeout causes 30-min hang when API is unavailable

## Summary

The `evaluate_with_llm()` function in `evaluators.py` uses a default `timeout=1800` (30 minutes) for the Claude CLI subprocess. When the claude CLI stalls on network I/O (API rate limiting or transient auth failure), the loop silently blocks for the full 1800 seconds before failing. This manifests in the `refine-to-ready-issue` built-in loop's `confidence_check` state, where a trivial threshold-comparison evaluation (two numbers vs. two thresholds) idles at 0.4% CPU for 30 minutes waiting for an unresponsive API.

## Current Behavior

When the `confidence_check` state in `refine-to-ready-issue` triggers an `llm_structured` evaluation:

1. `evaluate_with_llm()` spawns a `claude -p <prompt> --output-format json ...` subprocess with the default `timeout=1800`
2. If the Claude API is unavailable (rate limit, transient auth failure), the `claude` CLI stalls at 0.4% CPU, sleeping on network I/O
3. The loop blocks for the full 30 minutes before `subprocess.TimeoutExpired` is raised
4. Total loop runtime becomes ~40 minutes even though all productive work (format + refine + confidence action) completes in ~10 minutes

Timeline observed in testing:
- `confidence_check` action: ~2 min (OK)
- `confidence_check` evaluate (llm_structured): 30 min (TIMEOUT)

## Expected Behavior

The `llm_structured` evaluator should fail fast on API unavailability. For trivial evaluation prompts (checking if two scores meet two thresholds), a 60–120s timeout is sufficient for even slow API responses. The loop should surface an error within minutes, not 30 minutes, allowing for retry or manual intervention.

## Motivation

Automated loops like `refine-to-ready-issue` run unattended overnight or in CI. A 30-minute silent hang is invisible until the full timeout expires. The 1800s default was introduced in ENH-763 to prevent spurious failures from slow API responses, but it now masks real infrastructure failures (rate limits, auth issues) for an unreasonably long time. For trivial prompts — the `confidence_check` evaluate prompt is literally "is score A > 90 and score B > 75?" — even 60s is generous.

## Steps to Reproduce

1. Run `ll-loop run refine-to-ready-issue` on a project with pending issues
2. After the `confidence_check` action completes (at ~12 minutes), watch the evaluate step stall
3. Observe: the evaluate subprocess (pid visible via `ps`) shows 0.4% CPU for 30 minutes before failing with `"LLM evaluation timeout"`

Alternatively, reproduce by directly calling `evaluate_with_llm()` while the Anthropic API is rate-limited or unreachable.

## Root Cause

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Anchor**: `in function evaluate_with_llm()`
- **Cause**: `timeout: int = 1800` default at line 536 is applied uniformly to all `llm_structured` evaluation prompts regardless of complexity. The subprocess runs `claude -p <prompt> --output-format json --json-schema ... --dangerously-skip-permissions --no-session-persistence` (lines 565–577) and calls `subprocess.run(..., timeout=timeout)` at line 581. When the claude CLI idles on API I/O, no intermediate heartbeat or retry is possible — the caller simply waits for `subprocess.TimeoutExpired`.

There is no mechanism in the loop YAML `evaluate:` config to override the timeout per state, so all `llm_structured` evaluators inherit the 1800s default.

## Proposed Solution

**Option A (recommended)**: Lower the default timeout in `evaluate_with_llm()` from 1800s to 120s. Two minutes is generous for trivial prompts and still handles slow API responses.

```python
# scripts/little_loops/fsm/evaluators.py
def evaluate_with_llm(
    output: str,
    ...
    timeout: int = 120,  # was 1800 (ENH-763); 120s is sufficient for trivial prompts
) -> EvaluationResult:
```

**Option B**: Expose `timeout` as an optional field in FSM state `evaluate:` config blocks. Pass it through from the loop YAML to `evaluate_with_llm()`. This gives per-state control for loops with more complex evaluation prompts.

**Recommended**: Implement both — lower the default to 120s AND add optional `timeout:` override in `evaluate:` config.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_with_llm()` default timeout parameter

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — dispatches to `evaluate_with_llm()` for `llm_structured` type
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `confidence_check` state uses `llm_structured` evaluate

### Similar Patterns
- `scripts/little_loops/fsm/evaluators.py:405` — tool evaluator uses its own 30s timeout (separate code path, unaffected)

### Tests
- `scripts/tests/fsm/test_evaluators.py` — add test verifying new default and `TimeoutExpired` path

### Documentation
- `docs/reference/API.md` — update `evaluate_with_llm()` signature docs if timeout default is documented

### Configuration
- `config-schema.json` — add `timeout` field to state `evaluate:` block schema if Option B is implemented

## Implementation Steps

1. In `evaluate_with_llm()` (`evaluators.py`), change `timeout: int = 1800` to `timeout: int = 120`
2. In the FSM executor (`executor.py`), add support for optional `timeout` field in state `evaluate:` config, passing it to `evaluate_with_llm()`
3. Update `config-schema.json` to allow `timeout` in `evaluate:` blocks (if Option B)
4. Add test coverage in `test_evaluators.py` for the new default and timeout error path
5. Verify `refine-to-ready-issue` runs cleanly end-to-end with the reduced default

## Impact

- **Priority**: P2 — Causes 30-minute unattended hangs in production; directly observed in testing another project
- **Effort**: Small — single default parameter change; Option B adds minor config plumbing
- **Risk**: Low — 120s is still generous for API latency; users needing longer timeouts can override per-state via Option B
- **Breaking Change**: No — existing callers that pass an explicit `timeout` argument are unaffected

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `fsm`, `loops`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-31T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/afd36911-09cb-4a84-a407-9174c8f43270.jsonl`

---

## Status

**Open** | Created: 2026-03-31 | Priority: P2
