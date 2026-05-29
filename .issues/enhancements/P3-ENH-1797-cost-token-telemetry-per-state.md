---
id: ENH-1797
type: ENH
title: Cost / token telemetry per FSM state in loop runs
priority: P3
status: open
captured_at: '2026-05-29T20:37:23Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
  - captured
  - fsm
  - harness
  - loops
  - telemetry
  - cost
relates_to: [FEAT-1689, ENH-1726]
parent: EPIC-1744
---

# ENH-1797: Cost / token telemetry per FSM state in loop runs

## Summary

Record token spend (input / output / cache) per FSM state per iteration
and surface aggregates in `ll-loop run` output and the per-run artifacts
directory. Today the runner has no idea what each harness costs, which
makes "is this loop worth running 200 iterations?" an unanswerable
question. DeerFlow's `TokenUsageMiddleware` attributes subagent token
usage back to the dispatching step — we should do the equivalent for
states.

## Motivation

This enhancement would:
- Surface which FSM states dominate token spend, making "is this loop worth running 200 iterations?" an answerable question
- Enable cost-aware loop design: a `check_skill` state that drags 50× more than `check_concrete` shouldn't be invisible
- Business value: honest cost recommendations for long-running harnesses
- Technical debt: removes the need to read CLI billing logs out-of-band to understand harness cost

## Current Behavior

- `ll-loop run` reports iteration counts, transitions, and verdicts.
- There is no breakdown of tokens / cost per state or per iteration.
- A `check_skill` state that costs 50× more than `check_concrete` is
  invisible until you read the host CLI's billing logs out-of-band.
- `ll-ctx-stats` exists for the project level but doesn't slice by FSM
  state.

## Expected Behavior

1. Runner captures input/output/cache tokens from each `action_type:
   prompt` / `slash_command` / `mcp_tool` invocation (whatever the host
   adapter exposes — `claude` already returns usage; `codex` / `opencode`
   may need shim work).
2. Per-iteration usage is journaled to `.loops/runs/<id>/usage.jsonl`
   alongside the existing event log.
3. `ll-loop run` end-of-run summary prints a table:
   `state | invocations | input | output | est_cost`.
4. `ll-loop runs show <id>` (or whatever the per-run reporter is, post
   ENH-1726) surfaces the same breakdown.
5. Sets a foundation for budget-aware control: a future `max_cost:`
   field at the loop level can abort cleanly when crossed (parallel to
   today's `max_iterations`).

## Proposed Solution

Pipe host-adapter token usage through the runner's action execution layer into a per-run
`usage.jsonl` journal and a terminal summary table.

1. **Capture**: Extend the runner's action-invocation path to record `input_tokens`,
   `output_tokens`, `cache_tokens` (and optionally `cache_write_tokens`) from each
   host-adapter response. `claude` already returns usage; `codex`/`opencode` may need
   shim work deferred to adapter tickets.
2. **Journal**: Write per-iteration usage lines to `.loops/runs/<id>/usage.jsonl`
   alongside the existing event log, keyed by `{iteration, state, action_type, ...}`.
3. **Summarize**: In the end-of-run reporter, aggregate usage by state and emit a table:
   `state | invocations | input_tokens | output_tokens | cache_tokens | est_cost`.
4. **Per-run reporter** (post ENH-1726): `ll-loop runs show <id>` surfaces the same
   breakdown from `usage.jsonl`.
5. **Future**: Add `max_cost:` loop-level field (out of scope here) that gates iteration
   when cumulative cost exceeds the threshold.

## API/Interface

### New file format: `.loops/runs/<id>/usage.jsonl`

```jsonl
{"iteration": 0, "state": "check_skill", "action_type": "slash_command", "input_tokens": 1234, "output_tokens": 567, "cache_tokens": 890, "timestamp": "..."}
```

### End-of-run summary table (stdout from `ll-loop run`)

```
state           invocations  input    output   cache   est_cost
check_skill     1            1234     567      890     $0.016
check_concrete  1            234      56       100     $0.003
```

### `ll-loop runs show <id>` integration

The per-run reporter reads `usage.jsonl` and surfaces the same aggregated breakdown
as a sub-table under the iteration log.

## Implementation Steps

1. Extend the runner action-execution path to capture token usage from host responses
2. Add `usage.jsonl` journaling alongside the existing event log
3. Add per-state aggregation in the end-of-run reporter (`ll-loop run` summary)
4. Wire the per-run reporter (`ll-loop runs show <id>`) to surface usage breakdown
5. Add tests: verify `usage.jsonl` is written, aggregation is correct, table output renders

## Integration Map

### Files to Modify
- `scripts/little_loops/loop_runner.py` — action-execution path, journaling, aggregation
- `scripts/little_loops/loop_reporter.py` — end-of-run summary table
- `scripts/little_loops/host_runner.py` — token-usage passthrough from host adapters

### Dependent Files (Callers/Importers)
- `scripts/tests/test_loop_runner.py` — new tests for usage journaling
- `scripts/tests/test_loop_reporter.py` — new tests for summary output

### Similar Patterns
- `ll-ctx-stats` — project-level token analytics; follow same aggregation style

### Tests
- `scripts/tests/test_usage_journal.py` — verify `usage.jsonl` format and content
- `scripts/tests/test_usage_reporter.py` — verify end-of-run table output

### Documentation
- `docs/reference/API.md` — document new `usage.jsonl` format
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add cost-awareness section

### Configuration
- N/A — no new config keys in this issue (`max_cost` is deferred to a follow-up)

## Impact

- **Priority**: P3 — observability now, gating later. Without it we
  can't honestly recommend long-running harnesses.
- **Effort**: Medium — host-adapter pass-through, runner journaling,
  reporter format. Cost is dominated by host adapters that don't yet
  expose usage cleanly.
- **Risk**: Low — pure instrumentation.
- **Breaking Change**: No.

## Success Metrics

- `ll-loop run` end-of-run summary includes a per-state token/cost table
- `usage.jsonl` is written for every loop run and contains one line per action invocation
- The most expensive state in a loop can be identified from the summary alone (no out-of-band billing logs required)
- Cost estimate in summary is within ±15% of the host CLI's billing totals

## Scope Boundaries

- **In scope**:
  - Per-state token capture for `action_type: prompt`, `slash_command`, and `mcp_tool`
  - `usage.jsonl` journaling per iteration
  - End-of-run summary table in `ll-loop run` output
  - Integration with per-run reporter (`ll-loop runs show <id>`, post ENH-1726)
- **Out of scope**:
  - Budget-aware gating (`max_cost` loop-level field) — deferred to follow-up
  - Host-adapter engineering for `codex`/`opencode` token reporting — blocked on adapter work
  - Per-project cost dashboards or historical cost trending (future `ll-ctx-stats` extension)

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § Tips | "Set `timeout` for long runs" — the cost dimension belongs alongside |
| `FEAT-1689` | `ll-harness` CLI for one-shot evaluation — natural consumer |
| `ENH-1726` | Per-run artifacts directory — the storage target |

## Labels

`captured`, `cost`, `fsm`, `harness`, `loops`, `telemetry`

## Status

**Open** | Created: 2026-05-29 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-05-29T21:14:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf11edc6-7c38-44c6-bc14-9d68aba363ce.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:37:23Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f2a0c61b-6b34-41d4-98fb-c566ba046de6.jsonl`
