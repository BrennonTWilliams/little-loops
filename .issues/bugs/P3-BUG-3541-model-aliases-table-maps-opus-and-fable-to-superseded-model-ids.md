---
id: 3541
title: MODEL_ALIASES maps opus and fable to superseded model IDs
type: BUG
priority: P3
status: open
discovered_date: '2026-09-23'
labels:
- multi-host
- models
---

# MODEL_ALIASES maps opus and fable to superseded model IDs

## Summary

`host_runner.MODEL_ALIASES` (`scripts/little_loops/host_runner.py:97-102`)
resolves `opus → claude-opus-5` and `fable → claude-fable-5`. The current
lineup is Opus 5.5 (`claude-opus-5-5`) and Fable 5.1 (`claude-fable-5-1`).
The CLI path is unaffected (the host binary resolves aliases itself), but every
SDK/batch request (`orchestration.request_path: sdk|batch`) that uses `opus` or
`fable` is sent to the older model. ENH-3527 derives its `anthropic-api`
`reasoning` hint target from this table, so the staleness would carry into
hints too.

## Current Behavior

- `resolve_model_alias("opus")` → `claude-opus-5`; `resolve_model_alias("fable")`
  → `claude-fable-5`. `sonnet → claude-sonnet-5` and `haiku → claude-haiku-4-5`
  are current.
- `advisor.py:56-58` ranks `claude-fable-5-1` but has no `claude-opus-5-5`
  entry, so ranking a resolved `claude-opus-5-5` would fall to the unknown-model
  default.
- `pricing.py` keys `claude-opus-5` / `claude-fable-5`; check whether the newer
  IDs are priced (the file has uncommitted ENH-3538 edits in progress —
  coordinate, don't conflict).

## Expected Behavior

Aliases resolve to the current model IDs; the advisor rank table and pricing
table recognize both the new and the superseded IDs (history rows keep old IDs).

## Scope

1. Update `MODEL_ALIASES` `opus`/`fable` targets.
2. Add `claude-opus-5-5` to `advisor.py` rank table (same rank as `claude-opus-5`).
3. Make sure `pricing.py` prices the new IDs (keep old entries for historical rows).
4. Update `scripts/tests/test_host_runner_dispatch.py:383-387` and
   `test_advisor.py` expectations.
5. Consider a guard test asserting every `MODEL_ALIASES` target has an advisor
   rank and a pricing entry, so the three tables cannot drift again.

## Acceptance Criteria

- [ ] `resolve_model_alias("opus") == "claude-opus-5-5"` and
      `resolve_model_alias("fable") == "claude-fable-5-1"`.
- [ ] `rank_model("claude-code", "opus") == rank_model("claude-code", "claude-opus-5-5")`.
- [ ] Every `MODEL_ALIASES` target has a rank and a price (guard test).
- [ ] Superseded IDs remain ranked/priced.

## Related

- ENH-3527 — `anthropic-api` hint targets derive from `MODEL_ALIASES`.
- ENH-3538 — in-flight `pricing.py` edits.

## Status

**Open** | Created: 2026-09-23 | Priority: P3
