---
id: BUG-1978
title: context-monitor.sh misreports context usage on 1M-context models (200k denominator)
  and has no sanity clamp for transient transcript-baseline spikes
type: BUG
priority: P2
status: done
captured_at: '2026-06-06T00:00:00Z'
completed_at: '2026-06-06T20:24:37Z'
discovered_date: '2026-06-06'
discovered_by: capture-issue
decision_needed: false
labels:
- hooks
- context-monitor
- telemetry
confidence_score: 96
outcome_confidence: 76
score_complexity: 16
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 20
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

1. **Fix `get_context_limit()` sentinel (Bug 3)** — `hooks/scripts/context-monitor.sh:127-136`: Replace the `1000000` check at line 131 (`[ "$config_override" != "1000000" ]`) with a check for the empty string or `"auto"`. Change `CONFIG_LIMIT` default at line 28 from `"1000000"` to `""` (empty), making any non-empty value an explicit override. Also update `config-schema.json:689-695` — the `context_limit_estimate` field currently has `"default": 1000000` and `"type": "integer"`; the default should change to `0` (or the description updated to say "set to 0 for auto-detect") to match the new script behavior. Keep `LL_CONTEXT_LIMIT` at line 262 as the unconditional top-priority override.

2. **Add baseline auto-upgrade for 1M detection (Bug 1)** — `hooks/scripts/context-monitor.sh:260-265` (after `CONTEXT_LIMIT` is resolved): if `TRANSCRIPT_BASELINE > CONTEXT_LIMIT`, step up to the next known tier. The tier table is: 200,000 → 1,000,000 → (no further tiers known). Apply this after line 262 so it works regardless of how `CONTEXT_LIMIT` was resolved. Pattern to follow: the numeric guard chain in `context-handoff-sentinel.sh:53-67`.

3. **Add clamp guard before `USAGE_PERCENT` (Bug 2)** — `hooks/scripts/context-monitor.sh:302-320`: after the overhead addition at line 302 and before line 320 (`USAGE_PERCENT=$((...))`), add: if `NEW_TOKENS > $((CONTEXT_LIMIT * 105 / 100))`, treat as a misread — fall back to `CURRENT_TOKENS` (already in state as a validated good estimate) and skip emitting a reminder for this firing. Use the same `[ "$VAR" -gt 0 ] 2>/dev/null` guard idiom used pervasively in this script (e.g., line 288).

4. **Harden `get_transcript_baseline()` (Bug 2 defense-in-depth)** — `hooks/scripts/context-monitor.sh:114-122`: after the `jq -s` pipe, validate the numeric result using `2>/dev/null || echo 0`. Add a guard: if the jq output is not a valid integer (`! [[ "$result" =~ ^[0-9]+$ ]]`), return 0 to signal "unusable read." This matches the defensive jq patterns used in `hooks/scripts/check-duplicate-issue-id.sh:31-32` (`2>/dev/null || echo ""`).

5. **Update `context-handoff-sentinel.sh`** — `hooks/scripts/context-handoff-sentinel.sh:52-67`: This script also resolves context limit from state (`.context_limit`, lines 55-67). The hard-floor at line 67 (`[ "$CONTEXT_LIMIT" -le 0 ] && CONTEXT_LIMIT=200000`) means it won't break, but after the fix it should also reflect a 1M limit for sessions where `context_limit` was written as 1,000,000 into state. No code change needed — just verify that `context_limit` in `.ll/ll-context-state.json` is written correctly after the fix.

6. **Extend tests in `scripts/tests/test_hooks_integration.py`** — Following the existing patterns:
   - `test_1m_model_limit_resolution`: transcript with `"model": "claude-opus-4-8"` and a baseline token count of 250,000 (> 200k); assert `"1000000"` appears in stderr as the denominator. Pattern: `test_known_model_auto_detection` at line 309.
   - `test_sentinel_1000000_honored_as_explicit_override`: config with `context_limit_estimate: 1000000` and an unknown model; assert `"1000000"` appears in stderr. Pattern: `test_unknown_model_config_fallback` at line 367 (replace the `50000` value with `1000000`).
   - `test_impossible_baseline_clamped`: pre-write state with `result_token_count: 1517046`, context limit 200,000; run hook; assert `returncode != 2` (no spurious reminder) and `estimated_tokens` in state file does not exceed limit. Pattern: state injection in `test_result_token_count_used_when_present` at line 799.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Update `test_config` fixture** — `scripts/tests/test_hooks_integration.py:23`: change `"context_limit_estimate": 1000000` to either omit the field (rely on new empty default) or set `0` / `"auto"`. This is a prerequisite for all tests in `TestContextMonitor` to pass after the sentinel fix; without this change, `test_known_model_auto_detection` and several others will fail.
8. **Update `scripts/little_loops/cli_args.py`** — `add_context_limit_arg()` help string (line 163): replace `"1000000 for Sonnet/Opus"` with language reflecting the new auto-detect default (e.g., "auto-detected from session; override with this flag").
9. **Update 3 additional doc files** — change all `"context_limit_estimate": 1000000` examples to `0` (or `"auto"`) with explanatory prose in: `docs/reference/CONFIGURATION.md` (lines 132, 434), `docs/ARCHITECTURE.md` (line 1168), `docs/development/TROUBLESHOOTING.md` (line 549).
10. **Update `skills/configure/show-output.md`** — fix `(default: 150000)` string in `## context --show` section (line 128) to reflect the new auto-detect default.
11. **Update `skills/configure/areas.md`** — add an auto-detect option (e.g., `0` / `"auto"`) to the Round 1 limit question option list (lines 582–593); remove or relabel `"150000"` as `(default)`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `hooks/scripts/context-monitor.sh:28` — `CONFIG_LIMIT=$(ll_config_value "context_monitor.context_limit_estimate" "1000000")` — this is where the sentinel enters the script; changing the default `"1000000"` here to `""` is the minimal sentinel fix.
- `hooks/scripts/context-monitor.sh:131` — `[ "$config_override" != "1000000" ]` — sentinel guard; change to `[ -n "$config_override" ]` after removing the numeric default.
- `hooks/scripts/context-monitor.sh:262` — `CONTEXT_LIMIT="${LL_CONTEXT_LIMIT:-$(get_context_limit "$DETECTED_MODEL" "$CONFIG_LIMIT")}"` — the 1M auto-upgrade check belongs immediately after this line.
- `hooks/scripts/context-monitor.sh:287-302` — `NEW_TOKENS` priority cascade (RESULT_TOKEN_COUNT → TRANSCRIPT_BASELINE + TOKENS → CURRENT_TOKENS + TOKENS) + overhead addition; clamp guard belongs at line 303, before line 320.
- `config-schema.json:689-695` — `"context_limit_estimate"` has `"type": "integer"`, `"default": 1000000`, `"minimum": 50000`; default must change; minimum constraint prevents using 0, so `"default": 200000` (the real model default) plus a sentinel value of `0` would require `"minimum": 0` — or drop the minimum constraint and document 0 as "auto-detect."
- All `templates/*.json` files set `"context_limit_estimate": 1000000` as the default in generated configs — these will need updating to `0` or removal of the field (letting it default) once the sentinel changes.
- `docs/guides/SESSION_HANDOFF.md:307` — documents `context_limit_estimate` with guidance "Set to 200000 for Haiku 4.5"; update to document the new auto-detect behavior and 1M-model override.

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
- `hooks/scripts/context-monitor.sh` — `get_context_limit()` lines 127-136 (sentinel fix, 1M auto-detection), `get_transcript_baseline()` lines 114-122 (defensive JSON parse), `NEW_TOKENS` computation block lines 287-302 (clamp guard), `CONFIG_LIMIT` default line 28 (change from `"1000000"` to `""`)
- `config-schema.json:689-695` — `context_limit_estimate` field: update `"default"` and `"minimum"` to support auto-detect sentinel (0 or string); currently `"type": "integer"`, `"default": 1000000`, `"minimum": 50000`
- `scripts/little_loops/cli_args.py` — `add_context_limit_arg()` help text (line 163): documents `"1000000 for Sonnet/Opus"` as the default; update to reflect auto-detect behavior after sentinel fix [Wiring pass]
- `skills/configure/show-output.md` — `## context --show` section (line 128): hardcoded `(default: 150000)` string; already stale from BUG-809, drifts further without this update [Wiring pass]
- `skills/configure/areas.md` — `## Area: context / Round 1` option list (lines 582–593): offers no auto-detect choice and labels `"150000"` as `(default)` [Wiring pass]

### Dependent Files (Callers/Importers)
- `hooks/hooks.json:82-86` — registers `context-monitor.sh` as the PostToolUse hook
- `hooks/hooks.json:137-141` — registers `context-handoff-sentinel.sh` as the Stop hook
- `hooks/scripts/context-handoff-sentinel.sh:52-67` — also resolves `context_limit` from state; has its own fallback chain with hard-floor of 200,000; verify it reflects updated `context_limit` value from state after fix
- `hooks/scripts/precompact-state.sh` — reads `CONTEXT_STATE_FILE` / `.ll/ll-context-state.json`; advisory — verify it handles a `context_limit` of 1,000,000 after the fix [Wiring pass, advisory]
- `scripts/little_loops/cli/ctx_stats.py` — reads `.ll/ll-context-state.json` as fallback (lines 29–30); accesses `estimated_tokens` and `result_token_count`; no code change needed [Wiring pass, advisory]

### Similar Patterns
- `hooks/scripts/context-handoff-sentinel.sh:53-67` — numeric guard chain (default-zero → check-for-zero → config fallback → hard-floor); model for the clamp guard
- `hooks/scripts/scratch-pad-redirect.sh:51-54` — string sentinel check (`AUTO_ONLY="true"` pattern) for non-numeric config guard
- `hooks/scripts/check-duplicate-issue-id.sh:31-32` — defensive jq extraction pattern (`2>/dev/null || echo ""`)

### Tests
- `scripts/tests/test_hooks_integration.py` — class `TestContextMonitor` (line 14); extend with 3 new test methods (see Implementation Step 6 for names and patterns); reference: `test_known_model_auto_detection` line 309, `test_unknown_model_config_fallback` line 367, `test_result_token_count_used_when_present` line 799
- **BREAKING — `test_config` fixture (line 23)**: currently sets `context_limit_estimate: 1000000` as the no-op sentinel default; after the sentinel fix, `1000000` becomes an explicit 1M override (not auto-detect) — ALL ~15 tests using this fixture will change behavior. Update fixture to drop `context_limit_estimate` (or set `0` / `"auto"`) to preserve test intent [Wiring pass]
- **BREAKING — `test_known_model_auto_detection` (line 309)**: relies on `1000000` being ignored so auto-detect returns `200000`; after fix, `1000000` from fixture is honored → limit becomes 1M → 180k/1M = 18% → hook does not fire → `returncode == 0` instead of `2` → assertion on `"200000"` in stderr fails. Must update fixture value before this test will pass [Wiring pass]

### Documentation
- `docs/guides/SESSION_HANDOFF.md:307` — documents `context_limit_estimate`; update to explain new auto-detect default and 1M override behavior
- `docs/reference/CONFIGURATION.md` — JSON example (line 132) and `context_monitor` reference table (line 434) both show `"context_limit_estimate": 1000000`; update default cell and description prose [Wiring pass]
- `docs/ARCHITECTURE.md` — JSON example under `## Context Monitor and Session Continuation / Configuration` (line 1168) shows `"context_limit_estimate": 1000000` [Wiring pass]
- `docs/development/TROUBLESHOOTING.md` — tuning guidance JSON example (line 549) shows `"context_limit_estimate": 1000000` [Wiring pass]

### Configuration
- `.ll/ll-config.json` → `context_monitor.context_limit_estimate` (user override field; sentinel semantics changing)
- `templates/*.json` — all 9 template files set `"context_limit_estimate": 1000000`; update default value after sentinel change
- `.ll/ll-context-state.json` — runtime state cache (`detected_model`, `estimated_tokens`, `context_limit`, `result_token_count`)

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
- `/ll:ready-issue` - 2026-06-06T20:04:07 - `e7a60e1c-1f7a-43c5-94b7-650409a63183.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:00:00Z - `8da81e23-9a86-45a0-892b-ea7fc9faa5ea.jsonl`
- `/ll:wire-issue` - 2026-06-06T19:58:10 - `bc19e9f1-b796-4f10-896b-5f271b0c432a.jsonl`
- `/ll:refine-issue` - 2026-06-06T19:50:36 - `466bd496-d413-4f6c-95a6-9c241c735ce2.jsonl`
- `/ll:format-issue` - 2026-06-06T04:21:05 - `449e4685-e5d3-4369-88b5-c343effe4548.jsonl`
- `/ll:capture-issue` - 2026-06-06 - garbled reading 1517046/200000 (758%) on Write; transcript model `claude-opus-4-8`, true window 1M
