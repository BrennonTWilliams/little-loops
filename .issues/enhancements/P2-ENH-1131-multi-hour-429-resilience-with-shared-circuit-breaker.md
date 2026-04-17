---
id: ENH-1131
type: ENH
priority: P2
status: open
discovered_date: 2026-04-16
discovered_by: capture-issue
related: [BUG-1107, BUG-1108, BUG-1109, ENH-1115]
---

# ENH-1131: Multi-Hour 429 Resilience with Shared Circuit Breaker and Wall-Clock Budget

## Summary

Extend the FSM executor's existing 429 handling (BUG-1107/1108/1109) so loops can survive sustained rate-limit outages of many hours without false failures, without runaway resource use, and without parallel worktrees stampeding each other. Combine four mechanisms: two-tier retry, wall-clock budget, shared circuit-breaker file, and heartbeat events during long waits.

## Motivation

Current 429 handling (commits `8dba4536`, `95b4fed2`, `c8ea14e9`) gives 3 in-place retries with 30s/60s/120s exponential backoff — total tolerance ~3.5min per state. That covers transient blips but fails immediately on real outages (token-per-day exhaustion, sustained API degradation).

Observed in autodev FEAT-292 trace (2026-04-16): both `refine_issue` and `run_size_review` exhausted retries and routed to `on_error`, masquerading as a clean "no decomposition" outcome. User saw misleading "no further decomposition possible" — when in reality the work simply hadn't been attempted past the 3.5min window.

Worse, `ll-parallel` worktrees independently discover the same outage and burn quota in parallel — N workers each retrying expensive slash commands during a global rate-limit event multiplies waste and delays recovery.

**Why:** Loops should be able to wait *hours* for quota to reset rather than failing fast and forcing the user to manually re-run. This is especially important for overnight `ll-auto`/`ll-parallel`/autodev runs.

**How to apply:** Affects `scripts/little_loops/fsm/executor.py` rate-limit detection block (currently lines 479–540), `StateConfig` schema (`fsm/schema.py`), persistence (`fsm/persistence.py`), and `lib/common.yaml` fragment.

## Current Behavior

- 3 in-place retries, exponential backoff (30s base), jittered.
- On exhaustion: emits `rate_limit_exhausted`, routes to `on_rate_limit_exhausted` or `on_error`.
- Storm detection: 3 consecutive exhaustions across states emits `rate_limit_storm`.
- No shared state between parallel processes — each worktree retries independently.
- Long sleeps interruptible via `_shutdown_requested`.
- No progress emitted during sleep windows.

## Expected Behavior

### 1. Two-tier retry strategy

Keep current short-burst retries (3×, ~3min) as "transient blip" tier. On exhaustion, instead of routing immediately to `on_rate_limit_exhausted`, enter **long-wait tier**:

- Backoff ladder: 5min → 15min → 30min → 1h → 1h → 1h … capped at 1h per attempt.
- Continue until a configurable wall-clock budget elapses.
- Only then route to `on_rate_limit_exhausted`.

### 2. Wall-clock budget instead of (only) retry count

Add `rate_limit_max_wait_seconds` to `StateConfig` (per-state) and a global default in `ll-config.json` (`commands.rate_limits.max_wait_seconds`, default 21600 = 6h). Retry-count cap remains as a backstop, but the user-meaningful knob becomes "wait up to N hours."

### 3. Shared circuit-breaker file

When any process detects a 429:

1. Acquire file lock on `.loops/tmp/rate-limit-circuit.json`.
2. Update `{first_seen, last_seen, attempts, estimated_recovery_at}` with backoff-derived recovery estimate.
3. Release lock.

Before every LLM-bearing action (slash_command / prompt / sub-loop), executor checks the file:

- If `estimated_recovery_at` is in the future → pre-sleep until that time before attempting the action.
- If file is stale (>1h since `last_seen` with no recent updates) → ignore, attempt action normally.

This eliminates the parallel stampede where N worktrees each independently hit 429 and blow their retry budget within minutes.

### 4. Heartbeat events during long waits

Emit `rate_limit_waiting` event every 60s during sleep windows: `{state, elapsed_seconds, next_attempt_at, total_waited_seconds, budget_seconds}`. Renders in `ll-loop` UI and tail logs so users can see the loop is alive and waiting, not hung.

## Acceptance Criteria

- New config keys validated in `fsm-loop-schema.json`:
  - `rate_limit_max_wait_seconds` (per state, optional)
  - `rate_limit_long_wait_ladder` (per state, optional, list of seconds)
- Global defaults under `commands.rate_limits` in `ll-config.json` schema.
- `with_rate_limit_handling` fragment in `lib/common.yaml` updated to set sane long-wait defaults.
- Executor implements two-tier retry: short burst → long wait → exhaustion route.
- Shared circuit-breaker file with file locking; works correctly across `ll-parallel` worktrees.
- Pre-action circuit-breaker check skipped for non-LLM action types (`shell` without slash_command, etc.).
- Heartbeat events emitted at 60s intervals during waits; visible in `ll-loop` UI.
- New events registered in `cli/schemas.py` and EVENT-SCHEMA docs.
- Storm detection still functional as the "give up entirely" escape hatch.
- Persistence handles two-tier retry state across resume.
- Tests:
  - Two-tier ladder transitions correctly on persistent 429s.
  - Wall-clock budget enforced; respects per-state override.
  - Circuit-breaker file written/read with locking; stale entries ignored.
  - Heartbeat events emitted at expected cadence.
  - Resume restores two-tier state correctly.
- Docs updated: `LOOPS_GUIDE.md`, `CONFIGURATION.md`, `EVENT-SCHEMA.md`, `OUTPUT_STYLING.md`.

## Implementation Steps

1. **Schema + config** — Add `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` to `StateConfig`. Add `commands.rate_limits` block to `ll-config.json` schema with documented defaults.
2. **Executor two-tier logic** — Refactor the 429 detection block in `executor.py` to track `(short_retries, long_retries, total_wait_seconds)` per state. On short-tier exhaustion, transition to long-tier instead of routing.
3. **Circuit breaker** — Implement `RateLimitCircuit` helper with file-locked read/write of `.loops/tmp/rate-limit-circuit.json`. Wire pre-action check before LLM-bearing action types.
4. **Heartbeat events** — Replace blocking sleep with sleep-and-emit loop. Add `rate_limit_waiting` to schema registry.
5. **Persistence** — Extend `rate_limit_retries` dict-of-int to dict-of-record so two-tier state survives resume.
6. **Fragment update** — Update `with_rate_limit_handling` in `lib/common.yaml` with long-wait defaults; document opt-out for short-burst-only states.
7. **Tests** — Unit + integration coverage per acceptance criteria.
8. **Docs** — Update affected docs.

## API/Interface

```yaml
# StateConfig (new optional fields)
my_llm_state:
  fragment: with_rate_limit_handling
  action: "/ll:something"
  action_type: slash_command
  max_rate_limit_retries: 3              # short-burst tier (existing)
  rate_limit_backoff_base_seconds: 30    # short-burst tier (existing)
  rate_limit_max_wait_seconds: 21600     # NEW: total wall-clock budget (6h)
  rate_limit_long_wait_ladder:           # NEW: long-wait tier sleep schedule (seconds)
    - 300                                #   5min
    - 900                                #  15min
    - 1800                               #  30min
    - 3600                               #   1h (repeats until budget exhausted)
  on_rate_limit_exhausted: dequeue_next
```

```json
// ll-config.json (new section)
{
  "commands": {
    "rate_limits": {
      "max_wait_seconds": 21600,
      "long_wait_ladder": [300, 900, 1800, 3600],
      "circuit_breaker_enabled": true,
      "circuit_breaker_path": ".loops/tmp/rate-limit-circuit.json"
    }
  }
}
```

```jsonc
// rate_limit_waiting event payload
{
  "type": "rate_limit_waiting",
  "state": "refine_issue",
  "elapsed_seconds": 1830,
  "next_attempt_at": "2026-04-17T03:15:00Z",
  "total_waited_seconds": 1830,
  "budget_seconds": 21600,
  "tier": "long_wait"
}
```

## Tradeoffs / Open Questions

- **Cheap-probe optimization** (mechanism #4 from brainstorm) deferred to a follow-up — needs a decision on canonical health check.
- **`retry-after` header parsing** (mechanism #5) deferred — Claude CLI must surface the header through stderr for this to work; verify first.
- **Notification escalation** (mechanism #7) deferred — UX nicety, separate ENH if needed.
- **Circuit-breaker scope**: file is project-local (under `.loops/tmp/`), so cross-project parallel runs don't share state. That's probably fine — quotas are per-account, not per-project, so cross-project sharing would require a user-home-dir file (`~/.claude/rate-limit-circuit.json`). Worth discussing.
- **Heartbeat cadence**: 60s feels right for human observers but spams logs. Consider exponential heartbeat (60s → 5min → 15min) to match the wait ladder.

## References

- Builds on: BUG-1105 (umbrella), BUG-1107 (executor 429 detection), BUG-1108 (per-state config + storm), BUG-1109 (tests + docs)
- Related but distinct: ENH-1115 (progressive throttling for *successful* repeated calls)
- Triggering observation: autodev FEAT-292 trace, 2026-04-16 — both `refine_issue` and `run_size_review` exhausted in ~3.5min on a sustained 429 storm, parent issue then misleadingly marked "no further decomposition possible"
- Related fix already shipped this session: `run_size_review` in `loops/autodev.yaml` now opts into `with_rate_limit_handling` with `on_rate_limit_exhausted: dequeue_next`

## Session Log
- `/ll:capture-issue` - 2026-04-16T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a1d5130-4f36-4679-8288-365c673b3c29.jsonl`

---

## Status
- [ ] Open
