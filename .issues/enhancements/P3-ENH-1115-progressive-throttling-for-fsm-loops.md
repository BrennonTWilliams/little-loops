---
id: ENH-1115
type: ENH
priority: P3
status: open
discovered_date: 2026-04-15
discovered_by: capture-issue
related: []
---

# ENH-1115: Progressive Throttling for FSM Loop Tool Calls

## Summary

Extend the recent 429 / rate-limit detection in FSM loops (commits fa02a18..95b4fed2) with call-count-based progressive degradation: calls 1–3 normal, 4–8 warn + reduced output, 9+ redirect to batch execution or hard-stop.

## Motivation

Recent FSM work added per-state rate-limit config, storm detection, and in-place retry (see `d84e5f11`, `95b4fed2`, `c8ea14e9`, `fa02a186`). That handles the provider side (429s). But we still see runaway loops where the same state fires 20+ similar tool calls before any rate limit trips — burning cache, cost, and user trust without ever hitting a retry-able error.

Context-mode (github.com/mksglu/context-mode) applies "progressive throttling" at the MCP layer: call counts per logical operation escalate restrictions so noisy loops self-throttle before hitting provider limits. Same idea, but applied to FSM state transitions.

## Current Behavior

- FSM rate-limit config handles 429 responses with retry-in-place + count persistence
- No mechanism counts *successful* repeated calls from the same state
- A state that makes 15 successful Read calls in a single tick burns context with no warning

## Expected Behavior

- FSM tracks per-state tool-call count within a single state visit
- New `throttle:` section in FSM state config:
  ```yaml
  throttle:
    normal_max: 3      # calls 1-3 pass through
    warn_max: 8        # calls 4-8 get a warning injected into tool result
    hard_max: 12       # calls 9-12 trigger state transition to a batch/summarize state
    # >hard_max: hard stop, mark loop stuck
  ```
- Defaults live in `templates/` and can be overridden per state
- Warnings and hard-stops appear in loop telemetry / `analyze-loop` output

## Acceptance Criteria

- New config keys validated in FSM config schema
- Counter resets on state exit
- Unit tests cover warn / hard / stop transitions
- At least one built-in loop template uses the new throttle block
- `/ll:analyze-loop` surfaces throttle events
- Docs updated alongside existing rate-limit fields (commit `c8ea14e9` touched these)

## Scope Boundaries

- **In scope**: Per-state tool-call counter within a single state visit; new `throttle:` YAML config block for FSM states; warning injection into tool results at `warn_max`; state transition to batch/summarize state at `hard_max`; hard-stop and "stuck" marking beyond `hard_max`; default throttle values in `templates/`; throttle events in `analyze-loop` telemetry; unit test coverage
- **Out of scope**: Provider-side 429 retry handling (covered by existing FSM rate-limit config); cross-state or global tool-call aggregation; throttling non-tool-call loop operations (state transitions, sleep intervals)

## API/Interface

New `throttle:` block in FSM state YAML config (all fields optional; defaults applied from `templates/`):

```yaml
throttle:
  normal_max: 3    # calls 1–3: pass through
  warn_max: 8      # calls 4–8: inject warning into tool result
  hard_max: 12     # calls 9–12: transition to batch/summarize state
  # calls > hard_max: hard stop, mark loop stuck
```

## Proposed Solution

Implement in three layers:

1. **Schema** (`scripts/little_loops/fsm/schema.py`): Add optional `throttle:` block with `normal_max`, `warn_max`, `hard_max` integer fields; load defaults from `templates/`.
2. **Executor** (`scripts/little_loops/fsm/executor.py`): Add per-state call counter initialized on state entry, incremented on each tool call, reset on state exit; check threshold on each increment and take the appropriate action (pass / warn / transition / stop).
3. **Telemetry**: Emit throttle events to loop state so `ll:analyze-loop` can surface them. Update at least one built-in loop template to use a `throttle:` block.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — add `throttle:` block to state config schema
- `scripts/little_loops/fsm/executor.py` — add per-state call counter and threshold-check logic
- `templates/` — add default throttle config values
- Rate-limit docs (see commit `c8ea14e9`) — update alongside existing rate-limit fields

### Dependent Files (Callers/Importers)
- TBD — use `grep -r "rate_limit" scripts/little_loops/fsm/` to find related rate-limit logic to align with

### Similar Patterns
- Existing `rate_limit:` config in FSM states — `throttle:` block should follow the same schema conventions
- Storm detection logic (commits `d84e5f11`, `95b4fed2`) — similar counter-and-threshold pattern to reuse

### Tests
- TBD — add unit tests for warn/hard/stop transitions in `scripts/tests/fsm/`

### Documentation
- Rate-limit docs updated alongside commit `c8ea14e9`

### Configuration
- `templates/` — default throttle config values (applied when `throttle:` is omitted per state)

## Implementation Steps

1. Add `throttle:` block to FSM state schema (`scripts/little_loops/fsm/schema.py`) with `normal_max`, `warn_max`, `hard_max` fields; set defaults in `templates/`
2. Implement per-state call counter in FSM executor; reset on state exit
3. Add threshold-check logic: pass-through ≤ `normal_max`, warning injection ≤ `warn_max`, state-transition ≤ `hard_max`, hard-stop + stuck marking beyond `hard_max`
4. Emit throttle events to loop telemetry; update `ll:analyze-loop` to surface them
5. Add `throttle:` block to at least one built-in loop template
6. Write unit tests covering all three threshold transitions (warn, hard, stop)
7. Update rate-limit documentation

## Impact

- **Priority**: P3 — Quality-of-life improvement for runaway loop prevention; non-blocking
- **Effort**: Medium — Schema changes, executor counter logic, threshold-check wiring, and test coverage; builds on existing rate-limit infrastructure
- **Risk**: Low — New optional config section with safe defaults; omitting `throttle:` leaves existing loop behavior unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `fsm`, `loops`, `throttling`, `captured`

## Status

**Open** | Created: 2026-04-15 | Priority: P3

## References

- Inspiration: context-mode progressive throttling on search calls
- Builds on: recent FSM rate-limit work (`fa02a186`, `95b4fed2`, `c8ea14e9`, `8dba4536`)

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- No `throttle:` section in FSM state config schema (`scripts/little_loops/fsm/schema.py`) ✓
- No per-state tool-call counter in FSM executor ✓
- Feature not yet implemented ✓


## Session Log
- `/ll:format-issue` - 2026-04-24T20:51:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/952d3167-9cab-4483-a9fb-ad8fd963a3fa.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
