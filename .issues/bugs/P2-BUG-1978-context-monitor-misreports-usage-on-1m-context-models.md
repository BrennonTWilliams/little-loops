---
id: BUG-1978
title: "context-monitor.sh misreports context usage on 1M-context models (200k denominator) and has no sanity clamp for transient transcript-baseline spikes"
type: BUG
priority: P2
status: open
captured_at: '2026-06-06T00:00:00Z'
discovered_date: '2026-06-06'
discovered_by: capture-issue
labels:
- hooks
- context-monitor
- telemetry
---

# BUG-1978: context-monitor misreports usage on 1M-context models + no clamp on baseline spikes

## Summary

The `context-monitor.sh` PostToolUse hook emitted a garbled reading mid-session:

```
2026-06-06T04:11:03Z | 1517046/200000 (758%) | tool=Write
2026-06-06T04:11:13Z | 137501/200000   (68%) | tool=Bash
```

Investigation found **three compounding bugs**. The session model is the 1M-context Opus variant
(`claude-opus-4-8[1m]`), but the hook caps the limit at 200,000 and has no guard against an
impossible token count, so it both chronically over-reports (every reading is 5× too high) and
occasionally prints nonsense (>100%).

## Current Behavior

On a 1M-context model (`claude-opus-4-8[1m]`):

- `context-monitor.sh` reports percentages ~5× too high (e.g., `137501/200000 (68%)`) because `get_context_limit()` always returns `200000` for all `claude-opus-4*` variants, ignoring the actual 1M window.
- Transient transcript reads during concurrent file writes can produce impossible token counts (e.g., `1517046`) that are printed verbatim with no sanity clamp, yielding readings like `1517046/200000 (758%)`.
- Setting `context_limit_estimate: 1000000` in config is silently ignored — the value `1000000` is the "auto-detect" sentinel and falls through to the `200000` default.
- Handoff reminder nags fire at ~14% true usage, far too early for a 1M-context session.

## Root Cause

### Bug 1 — 1M-context variant is unrecognized (denominator is 5× too small)

`get_context_limit()` (`hooks/scripts/context-monitor.sh:127-136`) maps every `claude-opus-4*` /
`claude-sonnet-4*` / `claude-haiku-4*` to **200000**:

```bash
case "$model" in
    claude-opus-4*|claude-sonnet-4*|claude-haiku-4*) echo 200000 ;;
    *) echo "${config_override:-200000}" ;;
esac
```

The actual session is `claude-opus-4-8[1m]` (1,000,000-token window). Worse, the model string written
to the transcript's `.message.model` (and cached in `detected_model`) is **`claude-opus-4-8` — the
`[1m]` suffix is already stripped** — so even adding a `*\[1m\]` case would not match, because the
signal never reaches the hook. Verified: `.ll/ll-context-state.json` shows
`"detected_model": "claude-opus-4-8"`, and both `claude-opus-4-8` and `claude-opus-4-8[1m]` map to
200000.

**Effect**: every percentage is inflated 5×. The crossings log shows the hook warning at "56–68%"
when true usage against the 1M window was ~11–14%. Spurious handoff nags fire for the whole session.

### Bug 2 — No sanity clamp on the token estimate (transient spike printed verbatim)

`get_transcript_baseline()` (`:114-122`) sums `input + cache_creation + cache_read + output` from the
last assistant entry via `tail -50 "$path" | jq -s '... last'`. This reads a file that Claude Code is
**concurrently appending to**; a mid-write/partial-tail read can yield an anomalous value. On the
Write firing it returned **1,517,046** — ~10× the adjacent readings (~128–140k; confirmed normal sums
in the live transcript) and **greater than even the true 1M window**, which is physically impossible
for real context usage. The value self-corrected on the next call.

`NEW_TOKENS` (`:287-302`) is then used raw: there is **no upper clamp** and **no rejection of
impossible values** (> context window). An impossible reading should be discarded (keep the prior
estimate), not reported as 758%.

### Bug 3 — `1000000` is overloaded as the "no override" sentinel

`CONFIG_LIMIT` defaults to `1000000` (`:28`), and `get_context_limit()` honors a config override only
when it is **not** `1000000` (`:131`):

```bash
[ -n "$config_override" ] && [ "$config_override" != "1000000" ] && echo "$config_override" && return
```

So a user who explicitly sets `context_monitor.context_limit_estimate: 1000000` to match a 1M model is
**silently ignored** — the value is treated as "auto-detect," which then returns 200000. The one
obvious manual workaround for Bug 1 does not work.

## Steps to Reproduce

1. Run Claude Code with a 1M-context model (`claude-opus-4-8[1m]`).
2. Use the session normally until estimated tokens exceed ~110k.
3. Observe `.ll/ll-context-crossings.log`: readings are `/200000` and percentages are ~5× the true
   usage; handoff reminders fire far too early.
4. During a large `Write`, observe an occasional `>100%` reading (transient baseline misread) printed
   without any clamp.

## Expected Behavior

- The context limit reflects the real window: 1,000,000 for the 1M variant, 200,000 otherwise.
- An estimated token count that exceeds the resolved context limit (or some sane multiple) is treated
  as a misread — discarded in favor of the prior estimate — never reported as a >100% reading.
- A user-configured `context_limit_estimate` is always honored, including `1000000`.

## Motivation

The context-monitor handoff system becomes actively misleading on 1M-context models: it fires handoff nags at ~14% true usage and periodically prints nonsensical >100% readings. Users on 1M models cannot trust the context-usage signal, which either causes premature session handoffs (wasted tokens, lost context) or trains users to ignore the warnings entirely — defeating the safety net the hook provides. Bug 3 (sentinel collision) also silently blocks the most obvious workaround, making the issue hard to resolve manually.

## Proposed Solution

1. **Decouple the override sentinel from the value (Bug 3).** Use a non-numeric sentinel
   (e.g. unset / `"auto"`) for "auto-detect" instead of `1000000`, so any explicit numeric override —
   including `1000000` — is honored. Keep `LL_CONTEXT_LIMIT` as the top-priority explicit override.

2. **Detect the 1M window despite the stripped suffix (Bug 1).** Since `detected_model` loses `[1m]`,
   add a robust fallback: if the observed transcript baseline (a real, measured prompt size) exceeds
   the model's default mapped limit, raise the limit to the next known tier (e.g. 200k → 1M) rather
   than reporting >100%. Optionally also match a `*\[1m\]` / `*-1m` pattern if a raw model id with the
   suffix is ever available (e.g. via an env var the harness can set). Document that 1M sessions
   should set `context_limit_estimate: 1000000` until auto-detection is reliable (works once Bug 3 is
   fixed).

3. **Clamp/guard the estimate (Bug 2).** Before computing `USAGE_PERCENT`, reject any `NEW_TOKENS`
   that exceeds the context limit by more than a small margin (e.g. > 1.05 × limit) as a misread:
   fall back to `CURRENT_TOKENS` (the last good estimate) and skip the reminder for that firing. This
   makes a single bad transcript read non-fatal. Consider reading the transcript more defensively
   (e.g. validate the parsed object, ignore the final line if it fails to parse as JSON).

## Implementation Steps

1. Fix `get_context_limit()`: replace the `1000000` sentinel with `"auto"` / unset so any explicit numeric override (including `1000000`) is honored; keep `LL_CONTEXT_LIMIT` env var as top-priority override.
2. Add baseline-exceeds-limit auto-upgrade in `get_context_limit()`: if the observed transcript token count exceeds the currently mapped limit, raise the limit to the next known tier (200k → 1M).
3. Add clamp guard before `USAGE_PERCENT`: reject `NEW_TOKENS > 1.05 × limit`, fall back to `CURRENT_TOKENS`, and skip the reminder for that firing.
4. Harden `get_transcript_baseline()`: validate parsed JSON object and skip the final line if it fails to parse (guards against mid-write partial reads).
5. Extend `scripts/tests/test_hooks_integration.py` with tests covering: 1M-limit resolution, `sentinel-1000000` honored as explicit override, and impossible-baseline rejection.

## Acceptance Criteria

- [ ] On a 1M model, `get_context_limit` resolves to 1,000,000 (via auto-detection and/or honored
      config). (Bug 1)
- [ ] `context_limit_estimate: 1000000` in config is honored, not treated as the sentinel. (Bug 3)
- [ ] A `NEW_TOKENS` value exceeding ~1.05× the limit is discarded (prior estimate retained) and no
      `>100%` reminder is emitted. (Bug 2)
- [ ] Crossings log percentages for a 1M session reflect the true window (e.g. ~14%, not 68%).
- [ ] Tests cover: 1M-limit resolution, sentinel-1000000 honored, and impossible-baseline rejection
      (extend `scripts/tests/test_hooks_integration.py`).

## Integration Map

### Files to Modify
- `hooks/scripts/context-monitor.sh` — `get_context_limit()` (sentinel fix, 1M auto-detection), `get_transcript_baseline()` (defensive JSON parse), `NEW_TOKENS` computation block (clamp guard)

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — registers `context-monitor.sh` as the PostToolUse hook

### Similar Patterns
- N/A — context monitoring is self-contained in `context-monitor.sh`

### Tests
- `scripts/tests/test_hooks_integration.py` — extend with: 1M-limit resolution, `sentinel-1000000` honored as explicit override, impossible-baseline rejection

### Documentation
- N/A

### Configuration
- `.ll/ll-config.json` → `context_monitor.context_limit_estimate` (user override field)
- `.ll/ll-context-state.json` — runtime state cache (`detected_model`, current token estimate)

## Impact

- **Priority**: P2 — not destructive, but it makes the handoff/context safety system actively
  misleading on 1M models: it nags at ~14% true usage and prints nonsensical >100% readings,
  eroding trust in the signal and potentially triggering premature handoffs.
- **Effort**: Small–Medium — localized to `context-monitor.sh` (+ `get_context_limit`,
  baseline guard) and a few tests.
- **Risk**: Low — guard logic is additive; sentinel change needs care so existing 200k behavior is
  unchanged.
- **Breaking Change**: No.
- **Blast radius**: Every session on a 1M-context model; transient spikes affect any session during
  large tool outputs / concurrent transcript writes.

## Status

**Open** | Created: 2026-06-06 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-06-06T04:21:05 - `449e4685-e5d3-4369-88b5-c343effe4548.jsonl`
- `/ll:capture-issue` - 2026-06-06 - garbled reading 1517046/200000 (758%) on Write; transcript model `claude-opus-4-8`, true window 1M
