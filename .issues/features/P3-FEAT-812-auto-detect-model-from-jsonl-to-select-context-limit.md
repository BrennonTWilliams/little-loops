---
id: FEAT-812
type: FEAT
priority: P3
status: active
discovered_date: 2026-03-18
discovered_by: capture-issue
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
       # Config override wins if explicitly set
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
- `hooks/scripts/context-monitor.sh` — add `get_context_limit()`, extract `DETECTED_MODEL`, replace hardcoded denominator

### Dependent Files (Callers/Importers)
- `hooks/hooks.json:42-53` — PostToolUse hook definition; no changes needed
- `hooks/scripts/lib/common.sh` — `ll_config_value` used to read `context_limit_estimate`; no changes needed

### Similar Patterns
- `hooks/scripts/precompact-state.sh:25` — `transcript_path` extraction pattern (identical jq approach)
- `hooks/scripts/context-monitor.sh` — ENH-810 adds `get_transcript_baseline()`; `get_context_limit()` follows the same function pattern

### Tests
- `scripts/tests/test_hooks_integration.py` — add test for auto-detection (known model → correct window) and fallback (unknown model → config value)

### Documentation
- `docs/reference/CONFIGURATION.md` — update `context_limit_estimate` docs to clarify it's now a fallback/override

### Configuration
- `config-schema.json:409-481` — `context_limit_estimate` description update only; no structural changes

## Implementation Steps

1. Implement ENH-810 first (adds JSONL parsing infrastructure this builds on)
2. Add `DETECTED_MODEL` extraction to `context-monitor.sh` (same `jq -s` pass)
3. Add `get_context_limit()` function with model prefix lookup table
4. Replace hardcoded `CONTEXT_LIMIT_ESTIMATE` denominator with `get_context_limit` output
5. Add debug logging for detection path
6. Update `context_limit_estimate` config description to "fallback/override"
7. Add tests for detection and fallback paths

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
- `/ll:capture-issue` - 2026-03-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---
## Status

**Open** | Created: 2026-03-18 | Priority: P3
