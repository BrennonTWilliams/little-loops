---
id: ENH-810
type: ENH
priority: P3
status: completed
discovered_date: 2026-03-18
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 93
---

# ENH-810: Improve context-monitor.sh accuracy with JSONL transcript hybrid approach

## Summary

Replace or augment `context-monitor.sh`'s heuristic token estimation with a hybrid approach: read the last assistant entry's `usage` fields from the JSONL transcript (already available via `transcript_path` in the hook payload) as an accurate baseline, then add the current-turn heuristic delta. This would shift from low–medium accuracy estimates to API-exact measurements with only a one-turn lag.

## Current Behavior

`context-monitor.sh` uses weighted heuristics to estimate token usage:
- Per-turn overhead: 800 tokens
- Tool weights (e.g., Read=500, Bash=400) — linear proxies, no real tokenizer
- System prompt baseline: 10,000 tokens (actual: 8K–25K depending on MCP/tools loaded)
- Context limit default: 150,000 (see BUG-809 for the separate fix)

The heuristics produce low–medium accuracy. They cannot see cache tokens and have no model-specific tuning.

## Expected Behavior

The monitor reads `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, and `output_tokens` from the most recent assistant entry in the JSONL transcript (`$transcript_path`). This provides the exact token count as of the last API call. The current-turn tool heuristic is then added as a delta to account for any new tool calls in the current turn.

Accuracy improves from heuristic-only (±30–50%) to API-exact baseline + small delta (±5–15% for current-turn additions only).

## Motivation

Inaccurate context estimates cause either premature handoffs (wasting session continuity) or missed handoffs (context overflow). The JSONL transcript, already provided to every PostToolUse hook via `transcript_path`, contains real API token data with zero additional infrastructure. This is the best available accuracy improvement that doesn't require Anthropic to expose native token data in the PostToolUse payload.

## Context

Claude Code exposes context data through multiple surfaces:
- **PostToolUse payload**: No token/context data (GitHub issues #34340, #34879 are open; #12565 closed Not Planned Jan 2026)
- **JSONL transcript** (`transcript_path`): Each assistant entry has `usage.input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens` — real API data, one-turn lag
- **Status line**: Exact `context_window.used_percentage` per assistant message — but accessible to a different hook type, not PostToolUse
- `CLAUDE_CODE_ENABLE_TOKEN_USAGE_ATTACHMENT`: Undocumented env var potentially attaching token info to messages — worth experimenting with

The JSONL approach is the most compatible with the existing PostToolUse hook architecture.

## Proposed Solution

In `context-monitor.sh`:

1. Extract `transcript_path` from the hook's JSON stdin (currently ignored)
2. Parse the last `assistant` role entry from the JSONL file using `jq`
3. Sum `usage.input_tokens + cache_creation_input_tokens + cache_read_input_tokens + output_tokens` as `transcript_baseline`
4. Add the current-turn heuristic delta (existing tool weight logic) to get `estimated_usage`
5. Divide by `context_limit_estimate` (post BUG-809 fix: 1M) for percentage
6. Fall back to pure heuristics if `transcript_path` is absent or JSONL parse fails

## Integration Map

### Files to Modify
- `hooks/scripts/context-monitor.sh` — main implementation (add JSONL parsing block)
- `config-schema.json` — add `use_transcript_baseline: bool` config option

### Dependent Files (Callers/Importers)
- `hooks/hooks.json:42-53` — PostToolUse hook definition; `transcript_path` is in the payload schema (confirmed via `precompact-state.sh:25` which already extracts it successfully)
- `hooks/scripts/lib/common.sh:197-233` — `ll_feature_enabled` and `ll_config_value` functions used for reading the new config flag

### Similar Patterns
- `hooks/scripts/precompact-state.sh:25` — **exact pattern** for extracting `transcript_path` from stdin:
  ```bash
  TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // ""' 2>/dev/null || echo "")
  ```
- `hooks/scripts/lib/common.sh:197-211` — `ll_feature_enabled` for reading the new boolean flag
- `hooks/scripts/context-monitor.sh:169-172` — multi-arg `jq` mutation pattern to follow for new state fields

### Tests
- `scripts/tests/test_hooks_integration.py:38-92` — existing context-monitor tests; new JSONL baseline test goes here, following the same `subprocess.run` + `json.loads(state_file.read_text())` pattern
- `scripts/tests/test_hooks_integration.py:658-709` — precompact test with `transcript_path` in stdin — model test input structure from this

### Documentation
- `docs/guides/SESSION_HANDOFF.md` — document the improved accuracy mode
- `docs/reference/CONFIGURATION.md` — add `use_transcript_baseline` to config docs

### Configuration
- `config-schema.json:409-481` — `context_monitor` schema block; `"additionalProperties": false` at line 481 gates new keys; insert `use_transcript_baseline` property before line 481

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Extract `transcript_path` at `context-monitor.sh:46`** (after the existing two-field extraction at lines 44-45), using the identical pattern from `precompact-state.sh:25`:
   ```bash
   TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // ""' 2>/dev/null || echo "")
   ```

2. **Add config read at `context-monitor.sh:42`** (after existing reads at lines 26-41), using `ll_feature_enabled` from `lib/common.sh:197-211`:
   ```bash
   USE_TRANSCRIPT_BASELINE=$(ll_config_value "context_monitor.use_transcript_baseline" "true")
   ```

3. **Add new `get_transcript_baseline()` function after `context-monitor.sh:110`** (end of `estimate_tokens`). The JSONL structure per `user_messages.py:512` is `{"type":"assistant","message":{"usage":{...}}}`. Use `jq -s` to find the last assistant entry:
   ```bash
   get_transcript_baseline() {
       local path="$1"
       [ -z "$path" ] || [ ! -f "$path" ] && echo 0 && return
       jq -s 'map(select(.type == "assistant")) | last |
           (.message.usage.input_tokens // 0) +
           (.message.usage.cache_creation_input_tokens // 0) +
           (.message.usage.cache_read_input_tokens // 0) +
           (.message.usage.output_tokens // 0)' "$path" 2>/dev/null || echo 0
   }
   ```

4. **Replace accumulation logic at `context-monitor.sh:211-221`**: When `USE_TRANSCRIPT_BASELINE=true` and baseline > 0, use `baseline + current_turn_delta` instead of `CURRENT_TOKENS + TOKENS`. The `current_turn_delta` is just `$TOKENS + per-turn overhead` (the heuristic for the current tool call only).

5. **Add `transcript_baseline_tokens` field to state JSON** at `context-monitor.sh:120-129` for observability in the breakdown — follow the `--argjson` pattern used at lines 232-239.

6. **Update `config-schema.json:409-481`**: Insert `"use_transcript_baseline"` property inside `context_monitor.properties` before line 481 (`additionalProperties: false`):
   ```json
   "use_transcript_baseline": {
     "type": "boolean",
     "default": true,
     "description": "Use JSONL transcript usage fields as accurate baseline; falls back to pure heuristics if unavailable"
   }
   ```

7. **Add test to `test_hooks_integration.py`** after line 92, following the subprocess pattern at lines 38-92. Model JSONL stdin from `TestPrecompactState` at lines 658-709 (see `input_data = {"transcript_path": ...}` at line 675). Create a temp JSONL with one assistant entry containing `usage` fields, pass `transcript_path` in stdin alongside a tool call, assert `state["transcript_baseline_tokens"]` > 0 and `state["estimated_tokens"]` equals baseline + delta.

8. **Update `docs/guides/SESSION_HANDOFF.md`** with accuracy comparison table. Update `docs/reference/CONFIGURATION.md` with `use_transcript_baseline` description.

## Impact

- **Accuracy gain**: From ±30–50% error to ±5–15% (only current-turn additions are estimated)
- **Dependencies**: `jq` already required by the script; no new deps
- **Latency**: Negligible — one `jq` parse of a local file per tool call
- **Risk**: Low — fallback to heuristics on failure preserves existing behavior

## Known Limitation: context_limit_estimate is model-unaware

The transcript baseline improves the **numerator** (tokens used) to API-exact accuracy, but the **denominator** (`context_limit_estimate`) remains a static config value. Users must set it correctly for their model:

| Model | Context Window |
|---|---|
| claude-opus-4-6 | 200,000 |
| claude-sonnet-4-6 | 200,000 |
| claude-haiku-4-5 | 200,000 |
| Third-party models | Varies |

If `context_limit_estimate` is misconfigured (e.g., left at 1M for a 200K model), the percentage calculation will be wrong regardless of how accurate the numerator is. Auto-detecting the model from the JSONL and selecting the appropriate limit is out of scope here — that would be a separate enhancement.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/SESSION_HANDOFF.md` | User-facing session handoff documentation |
| `config-schema.json` lines 409–481 | Context monitor config schema |
| BUG-809 | Prerequisite: correct context_limit_estimate default |

## Labels

enhancement, context-monitor, accuracy, hooks, jq

## Session Log
- `/ll:ready-issue` - 2026-03-19T04:40:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c76ff1ee-0e20-46ac-b7b8-1af1a8922ddd.jsonl`
- `/ll:confidence-check` - 2026-03-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0769f82c-7917-4279-b938-66dfdf42d867.jsonl`
- `/ll:refine-issue` - 2026-03-19T04:15:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17e62d86-ce17-4688-90e3-90ca6ccc7acc.jsonl`
- `/ll:capture-issue` - 2026-03-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/11790a5c-4ad1-498a-9649-93255e24e9c4.jsonl`

---

## Resolution

Implemented 2026-03-18. Changes:
- `hooks/scripts/context-monitor.sh`: Reads `USE_TRANSCRIPT_BASELINE` config, extracts `TRANSCRIPT_PATH` from stdin, adds `get_transcript_baseline()` function, uses API-exact baseline + current-turn delta when transcript available, stores `transcript_baseline_tokens` in state JSON
- `config-schema.json`: Added `use_transcript_baseline` boolean property (default `true`) to `context_monitor` block
- `scripts/tests/test_hooks_integration.py`: Two new tests — baseline used when JSONL present, fallback when absent
- `docs/guides/SESSION_HANDOFF.md`: Added Transcript Baseline Mode section with accuracy comparison table; updated state file format example
- `docs/reference/CONFIGURATION.md`: Added `use_transcript_baseline` row to `context_monitor` table

## Session Log
- `/ll:manage-issue` - 2026-03-18T00:00:00Z - implementation complete
