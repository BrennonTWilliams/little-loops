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

## References

- Inspiration: context-mode progressive throttling on search calls
- Builds on: recent FSM rate-limit work (`fa02a186`, `95b4fed2`, `c8ea14e9`, `8dba4536`)
