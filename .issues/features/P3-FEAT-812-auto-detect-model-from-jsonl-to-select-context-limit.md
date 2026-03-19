---
id: FEAT-812
type: FEAT
priority: P3
status: active
discovered_date: 2026-03-18
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# FEAT-812: Auto-detect model from JSONL to select context limit

## Summary

Replace the static `context_limit_estimate` config value in `context-monitor.sh` with model auto-detection: read the model identifier from the JSONL transcript and automatically select the correct context window size for that model.

## Current Behavior

`context_limit_estimate` is a static value in `ll-config.json` that users must configure manually. It defaults to 1M tokens (post BUG-809 fix), but current Claude models have a 200K context window. If the value is misconfigured — or the user switches models — the percentage calculation used to trigger handoffs will be wrong.

## Expected Behavior

`context-monitor.sh` reads the model identifier from the last assistant entry in the JSONL transcript and maps it to the correct context window. Known model context limits are applied automatically; `context_limit_estimate` becomes an optional override for unknown or custom models.

| Model | Context Window |
|---|---|
| claude-opus-4-6 | 200,000 |
| claude-sonnet-4-6 | 200,000 |
| claude-haiku-4-5 | 200,000 |
| Unknown/third-party | Falls back to `context_limit_estimate` config |

## Motivation

The transcript baseline (ENH-810) improves the numerator (tokens used) to API-exact accuracy, but the denominator (`context_limit_estimate`) remains a manual config value. A misconfigured denominator defeats the accuracy gains from ENH-810 — the resulting percentage triggers handoffs too early or too late. Auto-detection eliminates this class of misconfiguration entirely for known models.

## Use Case

A user switches from claude-sonnet-4-6 to claude-opus-4-6 (both 200K) without updating config — no impact. They later test with a custom-endpoint model at 32K — the monitor falls back to `context_limit_estimate` and a warning is logged suggesting they set it explicitly.

## Acceptance Criteria

- `context-monitor.sh` extracts the `model` field from the last assistant JSONL entry
- A lookup table maps known model IDs (or prefixes) to context window sizes
- If the model is recognized, its context window is used as the denominator
- If the model is unrecognized, `context_limit_estimate` from config is used as fallback
- A log/debug line records which path was taken (detected vs. fallback)
- `context_limit_estimate` remains a valid override: if set to a non-default value, it takes precedence over auto-detection
- Existing tests pass; new test covers the detection and fallback paths

## Proposed Solution

1. Extract `model` from the JSONL transcript (same `jq -s` pass as the token baseline in ENH-810):
   ```bash
   DETECTED_MODEL=$(jq -s 'map(select(.type == "assistant")) | last | .message.model // ""' "$TRANSCRIPT_PATH" 2>/dev/null || echo "")
   ```

2. Add a `get_context_limit()` function that maps model prefix → window size:
   ```bash
   get_context_limit() {
       local model="$1"
       local config_override="$2"
       # Config override wins if explicitly set to a non-default value.
       # NOTE: ll_config_value always returns a value (default "1000000" if unset),
       # so the only signal that the user explicitly configured it is config_override != "1000000".
       [ -n "$config_override" ] && [ "$config_override" != "1000000" ] && echo "$config_override" && return
       case "$model" in
           claude-opus-4*|claude-sonnet-4*|claude-haiku-4*) echo 200000 ;;
           *) echo "${config_override:-200000}" ;;
       esac
   }
   ```

3. Call `get_context_limit "$DETECTED_MODEL" "$CONTEXT_LIMIT_ESTIMATE"` and use the result as the denominator.

4. Log the detection outcome at the debug level:
   ```
   [context-monitor] model=claude-sonnet-4-6 → context_limit=200000 (auto-detected)
   [context-monitor] model= → context_limit=1000000 (config fallback)
   ```

## Integration Map

### Files to Modify
- `hooks/scripts/context-monitor.sh` — add `get_context_limit()` function (after `get_transcript_baseline()` at line 126), extract `DETECTED_MODEL` at line ~50 (right after `TRANSCRIPT_PATH` at line 49), replace `CONTEXT_LIMIT` assignment at line 30

### Dependent Files (Callers/Importers)
- `hooks/hooks.json:42-53` — PostToolUse hook definition; no changes needed
- `hooks/scripts/lib/common.sh:217-233` — `ll_config_value` used to read `context_limit_estimate`; no changes needed

### Key Variable Locations in `context-monitor.sh`
- `line 30` — `CONTEXT_LIMIT` assignment (only assignment; single use at line 271 for `USAGE_PERCENT`)
- `line 49` — `TRANSCRIPT_PATH` extracted from stdin JSON; `DETECTED_MODEL` extraction goes here
- `line 57-105` — `estimate_tokens()` `case` statement — structural model for the `get_context_limit()` `case` block
- `line 118-126` — `get_transcript_baseline()` — direct structural model for `get_context_limit()` function

### Similar Patterns
- `hooks/scripts/precompact-state.sh:25` — `transcript_path` extraction pattern (identical jq approach)
- `hooks/scripts/context-monitor.sh:118-126` — `get_transcript_baseline()` uses the exact same `jq -s 'map(select(.type == "assistant")) | last | ...'` idiom; `get_context_limit()` reads `.message.model` instead of `.message.usage.*`
- `hooks/scripts/context-monitor.sh:57-105` — `estimate_tokens()` `case` block; the proposed model-prefix→window-size lookup follows this same pattern

### Tests
- `scripts/tests/test_hooks_integration.py:94-150` — `test_transcript_baseline_used_when_jsonl_present` is the direct template for new detection tests; new tests add `"model": "claude-sonnet-4-6"` to the `assistant_entry["message"]` dict
- `scripts/tests/test_hooks_integration.py:22-36` — `test_config` fixture; new fallback test uses an unknown model string with `context_limit_estimate: 50000` to verify config fallback

### Documentation
- `docs/reference/CONFIGURATION.md` — update `context_limit_estimate` docs to clarify it's now a fallback/override

### Configuration
- `config-schema.json:461-467` — `context_limit_estimate` field definition; update description only (no structural changes). Full `context_monitor` block is lines 409-487.

## Implementation Steps

1. ~~Implement ENH-810 first~~ — **ENH-810 is already merged and live** (`get_transcript_baseline()` at `context-monitor.sh:118-126`, `USE_TRANSCRIPT_BASELINE` at line 44, `TRANSCRIPT_PATH` at line 49)
2. Add `DETECTED_MODEL` extraction at `context-monitor.sh:~50` (immediately after `TRANSCRIPT_PATH` at line 49): `DETECTED_MODEL=$(jq -s 'map(select(.type == "assistant")) | last | .message.model // ""' "$TRANSCRIPT_PATH" 2>/dev/null || echo "")`
3. Add `get_context_limit()` function after `get_transcript_baseline()` (after line 126); follow the same function signature and `case` patterns already in the file
4. Replace `CONTEXT_LIMIT` assignment at line 30 to call `get_context_limit "$DETECTED_MODEL" "$CONFIG_LIMIT"` — the `LL_CONTEXT_LIMIT` env var override wraps the call as it does today
5. Add debug logging for the detection path (detected vs fallback)
6. Update `context_limit_estimate` description in `config-schema.json:461-467` to "fallback/override for unknown models"
7. Add tests in `scripts/tests/test_hooks_integration.py` following the `test_transcript_baseline_used_when_jsonl_present` template (lines 94-150): add `"model"` key to the JSONL `assistant_entry["message"]` dict; assert `state["estimated_tokens"]` implies correct `CONTEXT_LIMIT` denominator

## Impact

- **Priority**: P3 — improves accuracy but only matters when `context_limit_estimate` is wrong
- **Effort**: Small — piggybacks on ENH-810 JSONL parsing; minimal new logic
- **Risk**: Low — fallback to config value preserves existing behavior for unknown models
- **Breaking Change**: No — `context_limit_estimate` still works as an override

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.issues/enhancements/P3-ENH-810-improve-context-monitor-accuracy-with-jsonl-transcript-hybrid.md` | Prerequisite: adds JSONL parsing infrastructure |
| `docs/reference/CONFIGURATION.md` | `context_limit_estimate` config docs to update |
| `config-schema.json` lines 409–481 | Context monitor config schema |

## Labels

`feat`, `context-monitor`, `accuracy`, `hooks`, `jq`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74eac9b6-0514-4106-b8b2-da35fb895c2e.jsonl`
- `/ll:refine-issue` - 2026-03-19T04:48:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74626b26-3433-4c87-9955-47d8b604be07.jsonl`
- `/ll:capture-issue` - 2026-03-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---
## Status

**Open** | Created: 2026-03-18 | Priority: P3
