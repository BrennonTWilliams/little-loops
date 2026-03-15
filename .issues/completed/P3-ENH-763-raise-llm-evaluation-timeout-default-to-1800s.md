---
id: ENH-763
type: ENH
priority: P3
status: completed
discovered_date: 2026-03-15
discovered_by: manual
confidence_score: 100
outcome_confidence: 100
---

# ENH-763: Raise LLM evaluation timeout default from 30s to 1800s

## Summary

The default timeout for LLM-based FSM transition evaluation was 30 seconds — far too low for slow API responses, rate-limited calls, or Claude CLI startup overhead. Raised to 1800 seconds (30 minutes) to prevent spurious `"LLM evaluation timeout"` errors during loop execution.

## Problem

`LLMConfig.timeout` defaulted to 30 seconds, which was applied to the `claude` CLI subprocess call in `evaluate_with_llm()`. Any API slowness, rate limiting, or CLI startup delay could cause a timeout, surfacing as:

```
{"verdict": "error", "details": {"error": "LLM evaluation timeout", "timeout": true}}
```

This would abort an FSM transition evaluation and potentially stall or misdirect a running loop — despite the underlying call eventually succeeding if given more time.

## Solution

Raised the default from 30 to 1800 seconds across all three locations where the value was set:

- `schema.py` — `LLMConfig` dataclass field default
- `schema.py` — `to_dict()` serialization guard (only writes `timeout` to YAML if non-default)
- `schema.py` — `from_dict()` deserialization fallback
- `evaluators.py` — `evaluate_with_llm()` function signature default

Per-loop overrides via `loop.llm.timeout` in YAML still work as before.

## Files Changed

- `scripts/little_loops/fsm/schema.py` — `LLMConfig.timeout` default and serialization logic
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_with_llm()` signature default
