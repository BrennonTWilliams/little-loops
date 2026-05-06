---
id: ENH-1376
type: ENH
priority: P3
status: open
captured_at: 2026-05-06T20:59:54Z
discovered_date: 2026-05-06
discovered_by: capture-issue
---

# ENH-1376: Parse Stream-JSON `result` Events for Accurate Context Token Counts

## Summary

`subprocess_utils.py` skips all stream-json `result` events (line 214: `continue # skip other event types`), discarding the actual `input_tokens`/`output_tokens` counts the API returns each turn. The context monitor falls back to heuristic weight estimates, which significantly undercount large sessions, causing the handoff threshold to never fire before the API rejects with "Prompt is too long".

## Current Behavior

`run_claude_command` in `subprocess_utils.py` processes stream-json output events:
- `system/init` → extracted (model detection)
- `assistant` → extracted (text output)
- Everything else → **silently skipped** (`continue`)

This discards `result` events, which carry:
```json
{
  "type": "result",
  "usage": {
    "input_tokens": 95432,
    "output_tokens": 2847,
    "cache_read_input_tokens": 41200,
    "cache_creation_input_tokens": 0
  }
}
```

The context monitor in `context-monitor.sh` instead estimates tokens via `estimate_tokens()` using per-tool heuristics (lines × weight, Bash output chars × 0.3, etc.) plus a transcript baseline read from the JSONL with a one-turn lag. These heuristics undercount by a large margin in long implementation sessions (20+ minute run, 29-touchpoint issue → heuristics said ~49K tokens when actual was likely >150K).

## Expected Behavior

When a `result` event is received in `run_claude_command`, the actual token counts should be extracted and made available so the context monitor can use them. The cumulative token count written to `.ll/ll-context-state.json` should reflect real API usage rather than heuristic estimates.

## Proposed Solution

### Approach A: Callback in `subprocess_utils.py` (Recommended)
Add an `on_usage` callback parameter to `run_claude_command`:

```python
UsageCallback = Callable[[int, int], None]  # (input_tokens, output_tokens)

def run_claude_command(
    ...
    on_usage: UsageCallback | None = None,
) -> subprocess.CompletedProcess[str]:
    ...
    elif etype == "result":
        usage = event.get("usage", {})
        if on_usage and usage:
            on_usage(
                usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0),
                usage.get("output_tokens", 0),
            )
        continue
```

### Approach B: State file update from `result` events
The context monitor already uses a `transcript_baseline_tokens` field. An alternative is to have the subprocess write a separate `result-token-counts.json` file that the context monitor picks up next hook invocation, bypassing the heuristic path entirely.

Approach A is cleaner since the callback wires directly to callers that need accurate counts (e.g., `issue_manager.run_with_continuation`).

## Motivation

The heuristic estimates were "good enough" for short sessions but fail badly for large issue implementations. The actual token counts are emitted by the API in every `result` event — we are discarding free, accurate data. This is the underlying accuracy problem that causes the context handoff threshold to fire too late (or not at all before "Prompt is too long").

## Scope Boundaries

- **In scope**: Parsing `result` events in `subprocess_utils.py`; exposing token counts via `on_usage` callback; updating `context-monitor.sh` to prefer real counts over heuristics; wiring the callback in `issue_manager.run_with_continuation`
- **Out of scope**: Reworking heuristic estimation code itself (kept as fallback when `result_token_count` is absent); supporting other stream-json event types beyond `result`; UI or reporting features for token usage; changes to `worker_pool.py` beyond optional callback pass-through

## Success Metrics

- `result_token_count` field is non-zero in `.ll/ll-context-state.json` after any `run_claude_command` invocation that receives a `result` event
- `context-monitor.sh` selects the real token count path (not heuristic) when `result_token_count > 0`
- Context handoff threshold fires before a "Prompt is too long" API rejection in a 20+-touchpoint session

## API/Interface

```python
# New type alias in subprocess_utils.py
UsageCallback = Callable[[int, int], None]  # (input_tokens, output_tokens)

# Updated signature for run_claude_command (on_usage is optional; no breaking change)
def run_claude_command(
    cmd: list[str],
    ...,
    on_usage: UsageCallback | None = None,
) -> subprocess.CompletedProcess[str]: ...
```

## Implementation Steps

1. Add `UsageCallback` type alias to `subprocess_utils.py`
2. Add `on_usage: UsageCallback | None = None` parameter to `run_claude_command`
3. Parse `result` events in the stream-json loop; call `on_usage` when present
4. In `issue_manager.run_with_continuation`, pass an `on_usage` callback that writes cumulative token count to `.ll/ll-context-state.json` (replacing or supplementing the heuristic field)
5. Update `context-monitor.sh` to prefer the `result_token_count` field over its own estimate when present
6. Add tests verifying `on_usage` fires with expected counts from a mocked stream

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — add `on_usage` callback, parse `result` events
- `scripts/little_loops/issue_manager.py` — pass `on_usage` in `run_with_continuation`
- `hooks/scripts/context-monitor.sh` — prefer `result_token_count` from state file when non-zero

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py` — also calls `run_claude_command`; may benefit from same callback
- `scripts/little_loops/issue_manager.py` — calls `run_claude_command` via `run_with_continuation`

### Similar Patterns
- TBD — find all callers: `grep -r "run_claude_command" scripts/little_loops/`

### Tests
- `scripts/tests/test_subprocess_utils.py` — add coverage for `on_usage` callback and `result` event parsing

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — improves automation reliability in long sessions; no data loss risk; sessions still function without it
- **Effort**: Medium (~60 lines across 3 files)
- **Risk**: Low — additive change; no existing behavior removed
- **Breaking Change**: No

## Labels

`enhancement`, `context-monitor`, `subprocess`, `automation`, `token-tracking`

---

## Status

**Open** | Created: 2026-05-06 | Priority: P3

## Related Issues

- BUG-1375: `classify_failure` misses "Prompt is too long"
- BUG (to be filed): PostToolUse hook exit 2 feedback unreliable in -p mode
- FEAT-1160: Context window analytics command (different goal; complementary)
- BUG-035 (completed): Context monitor hook not visible to Claude in non-interactive mode

## Session Log
- `/ll:format-issue` - 2026-05-06T21:09:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d5f24f2c-c15a-45a5-bd06-fac0ecb8d960.jsonl`
- `/ll:capture-issue` - 2026-05-06T20:59:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/381e1f9c-a749-4e5e-9040-a1d4e3d3e647.jsonl`
