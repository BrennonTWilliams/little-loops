# BUG-924: context-monitor.sh jq Performance Fix

## Plan

### Problem
`context-monitor.sh` exceeds 5s hook timeout due to 15 jq subprocesses per invocation: 3× INPUT parsing, 2× full transcript slurps, and multiple state field extractions.

### Solution: 5 Changes (all in context-monitor.sh)

#### 1. Single-pass INPUT parsing (lines 44-47)
Replace 3 `echo "$INPUT" | jq` calls with one TSV extraction of `TOOL_NAME` and `TRANSCRIPT_PATH`. Do NOT extract `TOOL_RESPONSE` — it's no longer needed as a top-level variable.

#### 2. Defer tool_response extraction into estimate_tokens (lines 54-116)
Change `estimate_tokens` to accept raw `$INPUT` instead of `$TOOL_RESPONSE`. Extract `.tool_response` fields only in tool-specific branches. Optimize Read to count lines in jq (avoids putting full file content in bash var). Combine Bash's two jq calls into one.

#### 3. Move model detection after lock/state-read (lines 48-51 → inside main())
Remove pre-lock model detection. After reading state, check cached `detected_model` from state. Only fall back to `tail -50 | jq` transcript read when cache is empty. Also move `CONTEXT_LIMIT` resolution after model detection.

#### 4. Cache detected_model in state file
Add `detected_model` field to the state JSON written at line 288-295.

#### 5. Cache transcript baseline in state (lines 255-258)
Read `transcript_baseline_tokens` from state cache (already written at line 295 but never read back). Only call `get_transcript_baseline()` when cached value is 0. Also optimize `get_transcript_baseline()` to use `tail -50` instead of full `jq -s` slurp.

#### Bonus: Consolidate state field extractions (lines 248-252, 279, 284)
Combine 7 individual `jq -r` state field extractions into a single jq call outputting TSV.

### jq Call Count: Before vs After

| Phase | Before | After |
|-------|--------|-------|
| INPUT parsing | 3 | 1 |
| Model detection (transcript) | 1 | 0 (cached; 1 on first call) |
| estimate_tokens (Read) | 1 | 1 |
| estimate_tokens (Bash) | 2 | 1 |
| State field extraction | 5 | 1 (consolidated) |
| Breakdown extraction | 2 | 0 (consolidated into state read) |
| State build | 1 | 1 |
| Baseline slurp | 1 | 0 (cached; 1 on first call) |
| atomic_write validation | 1 | 1 |
| **Total (steady state)** | **~15** | **~5** |

### Files Modified
- `hooks/scripts/context-monitor.sh` — all changes

### Compatibility
- `precompact-state.sh` copies full state JSON as `context_state_at_compact` — adding `detected_model` field is additive, no breakage
- State file gains `detected_model` field — old state files without it work (jq `// ""` defaults)

### Phase 0: Write Tests (Red)
1. `test_detected_model_cached_in_state` — assert `detected_model` exists in state after call with transcript. Currently fails because state doesn't include this field.
2. `test_large_tool_response_performance` — assert hook completes within 5s with a 2000-line tool_response + transcript.

### Success Criteria
- [ ] All existing tests pass
- [ ] New tests pass
- [ ] Hook completes within 5s for Read calls with 1000+ line responses
- [ ] `detected_model` cached in state file
- [ ] Transcript baseline cached in state file (no re-slurp)
- [ ] No behavioral changes to threshold/handoff logic
