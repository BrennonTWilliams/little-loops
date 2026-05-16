---
id: ENH-1376
type: ENH
priority: P3
status: open
captured_at: 2026-05-06 20:59:54+00:00
completed_at: 2026-05-06T23:25:04Z
discovered_date: 2026-05-06
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 68
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1376: Parse Stream-JSON `result` Events for Accurate Context Token Counts

## Summary

`subprocess_utils.py` skips all stream-json `result` events (line 214: `continue # skip other event types`), discarding the actual `input_tokens`/`output_tokens` counts the API returns each turn. The context monitor falls back to heuristic weight estimates, which significantly undercount large sessions, causing the handoff threshold to never fire before the API rejects with "Prompt is too long".

## Current Behavior

`run_claude_command` in `subprocess_utils.py` processes stream-json output events:
- `system/init` → extracted (model detection)
- `assistant` → extracted (text output)
- Everything else → **silently skipped** (`continue`)

This discards `result` events, which carry:
```json
{
  "type": "result",
  "usage": {
    "input_tokens": 95432,
    "output_tokens": 2847,
    "cache_read_input_tokens": 41200,
    "cache_creation_input_tokens": 0
  }
}
```

The context monitor in `context-monitor.sh` instead estimates tokens via `estimate_tokens()` using per-tool heuristics (lines × weight, Bash output chars × 0.3, etc.) plus a transcript baseline read from the JSONL with a one-turn lag. These heuristics undercount by a large margin in long implementation sessions (20+ minute run, 29-touchpoint issue → heuristics said ~49K tokens when actual was likely >150K).

## Expected Behavior

When a `result` event is received in `run_claude_command`, the actual token counts should be extracted and made available so the context monitor can use them. The cumulative token count written to `.ll/ll-context-state.json` should reflect real API usage rather than heuristic estimates.

## Proposed Solution

### Approach A: Callback in `subprocess_utils.py` (Recommended)

> **Selected:** Approach A — on_usage callback — exact structural template exists at every layer (`on_model_detected`); reuse score 2/3 vs Approach B's 1/3; Approach B would introduce file writes into `subprocess_utils.py` against the module's established IPC pattern.
Add an `on_usage` callback parameter to `run_claude_command`:

```python
UsageCallback = Callable[[int, int], None]  # (input_tokens, output_tokens)

def run_claude_command(
    ...
    on_usage: UsageCallback | None = None,
) -> subprocess.CompletedProcess[str]:
    ...
    elif etype == "result":
        usage = event.get("usage", {})
        if on_usage and usage:
            on_usage(
                usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0),
                usage.get("output_tokens", 0),
            )
        continue
```

### Approach B: State file update from `result` events
The context monitor already uses a `transcript_baseline_tokens` field. An alternative is to have the subprocess write a separate `result-token-counts.json` file that the context monitor picks up next hook invocation, bypassing the heuristic path entirely.

Approach A is cleaner since the callback wires directly to callers that need accurate counts (e.g., `issue_manager.run_with_continuation`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Direct analogue exists**: `on_model_detected: ModelCallback | None = None` in `subprocess_utils.run_claude_command()` is the exact pattern to mirror. It uses a module-level `TypeAlias` (`ModelCallback = Callable[[str], None]`), is invoked with a bare `if on_model_detected and "model" in event:` guard inside the same stream-json event loop, and is forwarded through `issue_manager.run_claude_command()` (the wrapper) before being consumed by a closure in `AutoManager._process_issue()`.
- **Two-layer wrapper to plumb through**: `issue_manager.py` re-exports `subprocess_utils.run_claude_command` as `_run_claude_base` and defines its own `run_claude_command()` wrapper at module-level. `on_usage` must be added to **both** signatures, then forwarded; otherwise `run_with_continuation` (which calls the wrapper, not `_run_claude_base`) cannot pass it through.
- **State file field naming**: The existing field in `.ll/ll-context-state.json` is **`estimated_tokens`** (cumulative heuristic) and **`transcript_baseline_tokens`** (one-turn-lag accurate baseline read from JSONL). The issue's proposed `result_token_count` field does not yet exist in the schema — implementer should pick a new field name (e.g., `result_token_count` or overwrite `estimated_tokens` directly when authoritative counts are available).
- **`transcript_baseline_tokens` already provides accurate counts** with one-turn lag (read by `get_transcript_baseline()` in `context-monitor.sh`). The new callback path eliminates the lag — the implementer should ensure these two paths cooperate rather than duplicate.
- **Existing test will need to be updated, not just added**: `scripts/tests/test_subprocess_utils.py::test_unknown_event_type_skipped` explicitly asserts that a `{"type": "result", ...}` event produces empty stdout and no callback. After this change, `result` events should still produce empty stdout but should fire `on_usage` — that test's assertions need revision.
- **`WorkerPool` has a parallel-specific continuation loop**: `WorkerPool._run_with_continuation()` is a separate re-implementation (not shared with `issue_manager.run_with_continuation`). It currently does not forward `on_model_detected` either. Bringing it to parity with the main path is a small but separate concern flagged in scope as "may benefit".

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-06.

**Selected**: Approach A — on_usage callback in `subprocess_utils.py`

**Reasoning**: The `on_model_detected: ModelCallback | None = None` pattern in `subprocess_utils.py` is a complete structural template at every layer — TypeAlias, base function parameter, `issue_manager` wrapper pass-through, `process_issue_inplace` threading, and `AutoManager` closure accumulator — all directly reusable. Approach B would require `subprocess_utils.py` to write files for the first time, with no config-path resolver and no test templates for asserting file side effects, breaking the module's established callback-only IPC pattern. Approach A also resolves the open questions below.

**Open Questions Resolved**:
- **Field name**: Use `result_token_count` as a new field (not overwriting `estimated_tokens`). This preserves the distinction between heuristic cumulative (`estimated_tokens`) and authoritative per-invocation counts, and lets `context-monitor.sh` branch cleanly: `if result_token_count > 0, use it; else fall back to heuristics`.
- **Transcript coordination**: When `result_token_count > 0`, prefer it as authoritative (zero lag) and skip both the heuristic `estimate_tokens()` path and the `transcript_baseline_tokens` JSONL path. This avoids double-counting and is the simpler branch: a single priority check at the top of the token calculation in `context-monitor.sh:main()`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Approach A (callback) | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| Approach B (state file) | 0/3 | 0/3 | 1/3 | 1/3 | 2/12 |

**Key evidence**:
- Approach A: `on_model_detected` TypeAlias→param→wrapper→closure chain exists at every layer in `subprocess_utils.py` and `issue_manager.py`; test harness (`io.StringIO`, `_make_single_line_selector`) is fully reusable; `test_unknown_event_type_skipped` is the only test needing retargeting.
- Approach B: `subprocess_utils.py` has no file-write precedent; no config-path resolver for `.ll/` state file location exists in Python; no test templates for asserting file side effects in the subprocess test suite; the existing file-based IPC (`precompact-state.sh` → `check_compaction()`) lives entirely within the bash hook layer, not Python subprocess code.

## Motivation

The heuristic estimates were "good enough" for short sessions but fail badly for large issue implementations. The actual token counts are emitted by the API in every `result` event — we are discarding free, accurate data. This is the underlying accuracy problem that causes the context handoff threshold to fire too late (or not at all before "Prompt is too long").

## Scope Boundaries

- **In scope**: Parsing `result` events in `subprocess_utils.py`; exposing token counts via `on_usage` callback; updating `context-monitor.sh` to prefer real counts over heuristics; wiring the callback in `issue_manager.run_with_continuation`
- **Out of scope**: Reworking heuristic estimation code itself (kept as fallback when `result_token_count` is absent); supporting other stream-json event types beyond `result`; UI or reporting features for token usage; changes to `worker_pool.py` beyond optional callback pass-through

## Success Metrics

- `result_token_count` field is non-zero in `.ll/ll-context-state.json` after any `run_claude_command` invocation that receives a `result` event
- `context-monitor.sh` selects the real token count path (not heuristic) when `result_token_count > 0`
- Context handoff threshold fires before a "Prompt is too long" API rejection in a 20+-touchpoint session

## API/Interface

```python
# New type alias in subprocess_utils.py
UsageCallback = Callable[[int, int], None]  # (input_tokens, output_tokens)

# Updated signature for run_claude_command (on_usage is optional; no breaking change)
def run_claude_command(
    cmd: list[str],
    ...,
    on_usage: UsageCallback | None = None,
) -> subprocess.CompletedProcess[str]: ...
```

## Implementation Steps

1. In `scripts/little_loops/subprocess_utils.py`, add `UsageCallback = Callable[[int, int], None]` at module level next to the existing `OutputCallback`/`ProcessCallback`/`ModelCallback` TypeAliases.
2. In `subprocess_utils.run_claude_command()`, add `on_usage: UsageCallback | None = None` to the signature.
3. In the stream-json event loop in `run_claude_command()`, replace the unconditional `continue` at the `# skip other event types (result, tool_use, etc.)` branch with a check: if `etype == "result"`, extract `event.get("usage", {})`, and if `on_usage` is set, call `on_usage(input_tokens + cache_read_input_tokens, output_tokens)`. Mirror the conditional-call style of the adjacent `on_model_detected` invocation.
4. In `scripts/little_loops/issue_manager.py`, add `on_usage` parameter to both the `run_claude_command()` wrapper and `run_with_continuation()`, forwarding it down to `_run_claude_base`. Add no behavior in the wrapper itself — pure pass-through.
5. In `scripts/little_loops/issue_manager.py:process_issue_inplace()` Phase 2, construct an `on_usage` closure that accumulates cumulative `(input, output)` tokens across continuations and updates `.ll/ll-context-state.json` (decide on field name — see Open Question below). Mirror the closure shape used for `on_model_detected` in `AutoManager._process_issue()`.
6. In `hooks/scripts/context-monitor.sh:main()`, after `read_state()` parses fields, branch: if the new field is non-zero, set `NEW_TOKENS` from it directly (skipping the heuristic + transcript-baseline math). Coordinate with `transcript_baseline_tokens` so the existing accurate-baseline path is not double-counted.
7. Add tests in `scripts/tests/test_subprocess_utils.py` modeled on `TestRunClaudeCommandModelDetection`: feed a `{"type": "result", "usage": {...}}` event via `io.StringIO`, assert `on_usage` received exact tuple. Update `test_unknown_event_type_skipped` to use a different event type.
8. Add `scripts/tests/test_issue_manager.py` coverage that `run_with_continuation` forwards `on_usage`.
9. Run: `python -m pytest scripts/tests/test_subprocess_utils.py scripts/tests/test_issue_manager.py scripts/tests/test_hooks_integration.py scripts/tests/test_subprocess_mocks.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `scripts/tests/test_subprocess_mocks.py` — add `test_on_usage_forwarded_through_wrapper` to `TestRunClaudeCommand`, parallel to `test_wrapper_passes_on_model_detected`; capture `kwargs["on_usage"]` via side-effect on `_run_claude_base` and assert it matches the passed callback
11. Update `scripts/tests/test_issue_manager.py::TestAutoManagerModelDetection.test_auto_manager_logs_detected_model` — add `on_usage: Any = None` to the `mock_process_inplace` stub signature so it does not break when `process_issue_inplace` gains the new keyword argument
12. Update `docs/reference/API.md` — add `on_usage: UsageCallback | None = None` to the `#### run_claude_command` signature block and parameter table
13. Update `docs/guides/SESSION_HANDOFF.md` — extend the `### State File Format` JSON example with the new `result_token_count` field and a prose sentence explaining it
14. Update `docs/ARCHITECTURE.md` — add a note to the `**Context Estimation**` table that `result_token_count > 0` in the state file enables the real-count fast path, bypassing heuristics
15. Update `docs/development/TROUBLESHOOTING.md` — extend the `estimated_tokens` watch command and "Token Estimation accuracy" section to reference the new `result_token_count` field
16. Update `docs/reference/CONFIGURATION.md` — in the `### context_monitor` section, extend the `use_transcript_baseline` row description to reflect the new three-tier priority (`result_token_count > 0` → transcript baseline → pure heuristics); this file is not in the already-known docs list and was found by re-run wiring analysis [re-run finding]

## Open Questions

- **Field name in `.ll/ll-context-state.json`**: The proposed `result_token_count` is new. Alternative: overwrite `estimated_tokens` directly when authoritative counts are available, so `context-monitor.sh` reads the same field unconditionally. Decision should fall out of `/ll:decide-issue`.
- **Cooperation with `transcript_baseline_tokens`**: That field already provides accurate counts (one-turn lag). The `on_usage` path provides them with no lag. Pick one as authoritative or merge with `max()`.

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` in `run_claude_command()` — add `UsageCallback` TypeAlias at module level alongside `OutputCallback`/`ProcessCallback`/`ModelCallback`; add `on_usage: UsageCallback | None = None` parameter; replace the bare `continue` at the `# skip other event types (result, tool_use, etc.)` branch with `result`-event handling that calls `on_usage`
- `scripts/little_loops/issue_manager.py` in `run_claude_command()` (the wrapper) and `run_with_continuation()` — add `on_usage` parameter to both signatures and forward it; this wrapper currently does not plumb `on_process_start`/`on_process_end`/`agent`/`tools`, so adding `on_usage` is a deliberate new pass-through
- `scripts/little_loops/issue_manager.py` in `process_issue_inplace()` — Phase 2 call to `run_with_continuation()` should construct an `on_usage` closure that accumulates token counts and writes them to `.ll/ll-context-state.json` (mirror the `on_model_detected` closure in `AutoManager._process_issue()`)
- `hooks/scripts/context-monitor.sh` in `main()` — when the new state-file field (e.g., `result_token_count`) is non-zero, prefer it over the `estimate_tokens()` heuristic path; coordinate with the existing `transcript_baseline_tokens` logic so the two accurate sources don't double-count

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:run_with_continuation()` — calls the `issue_manager.run_claude_command` wrapper; primary consumer of `on_usage`
- `scripts/little_loops/issue_manager.py:process_issue_inplace()` — direct calls to the wrapper at Phase 1 ready-issue, Phase 1 fallback retry, decide-issue gate; Phase 2 implement goes through `run_with_continuation`
- `scripts/little_loops/parallel/worker_pool.py:WorkerPool._run_claude_command()` — calls `_run_claude_base` directly (bypasses `issue_manager.run_claude_command`); has its own continuation loop in `WorkerPool._run_with_continuation()`; in scope only for optional pass-through per Scope Boundaries
- `scripts/little_loops/fsm/runners.py:DefaultActionRunner.run()` — calls `run_claude_command` directly; not currently in scope but flagged for future parity
- `scripts/little_loops/cli/action.py:cmd_invoke()` — calls `run_claude_command` directly (twice, for two output modes); not in scope
- `scripts/little_loops/cli/sprint/run.py:_cmd_sprint_run()` — calls `process_issue_inplace` at two sites (sequential wave execution ~line 335, sequential retry for failed issues ~line 436); keyword `on_usage` will default to `None`; backward-compatible, no code change required [Agent 1/2 re-run finding]

### Similar Patterns
- `scripts/little_loops/subprocess_utils.py:run_claude_command()` — `on_model_detected: ModelCallback | None = None` is the closest existing pattern. Module-level `ModelCallback = Callable[[str], None]` TypeAlias, optional kwarg, invoked inline in the stream-json `system/init` branch with `if on_model_detected and "model" in event: on_model_detected(event["model"])`. New `on_usage` should follow the same shape.
- `scripts/little_loops/issue_manager.py:AutoManager._process_issue()` — closure-based callback pattern: `on_model: Callable[[str], None] | None = None` is conditionally assigned, the closure captures `self._detected_model` and `self.logger`, and the closure is forwarded into `process_issue_inplace(..., on_model_detected=on_model, ...)`. Apply the same closure shape for `on_usage` (capture cumulative state plus a state-file writer).
- `scripts/little_loops/parallel/worker_pool.py:WorkerPool.submit()` — `on_complete: Callable[[WorkerResult], None] | None = None` shows the inline-`Callable` (no TypeAlias) variant of the same pattern, used when the callback is single-site.

### Tests
- `scripts/tests/test_subprocess_utils.py` in class `TestRunClaudeCommandModelDetection` — closest existing template for new `on_usage` tests. Uses `io.StringIO` for `mock_process.stdout`, the shared `_make_single_line_selector` helper, and asserts the callback received exact values (`assert detected == ["claude-sonnet-4-6"]`). Mirror this for `result`-event JSON containing a `usage` block.
- `scripts/tests/test_subprocess_utils.py:test_unknown_event_type_skipped()` — **must be updated**: this test currently asserts that `{"type": "result", ...}` produces empty stdout and no callback. After the change, `result` events should still produce empty stdout but should fire `on_usage`. Either retarget this test to a different unknown event type (e.g., `tool_use`) or rewrite its assertions.
- `scripts/tests/test_subprocess_utils.py` shared helpers `_patch_selector_cm()` and `_make_single_line_selector()` — reuse these; do not roll new selector mocks.
- `scripts/tests/test_issue_manager.py` — add coverage for `run_with_continuation()` forwarding `on_usage` through to `_run_claude_base` (mock the underlying call and assert the kwarg is passed).
- `scripts/tests/test_hooks_integration.py` — context-monitor.sh integration tests; add coverage for the new "prefer real count" branch.
- `scripts/tests/test_subprocess_mocks.py` in `TestRunClaudeCommand` — add `test_on_usage_forwarded_through_wrapper` parallel to existing `test_wrapper_passes_on_model_detected`; verify `on_usage` kwarg is threaded from `issue_manager.run_claude_command` through to `_run_claude_base` [Agent 2/3 finding]
- `scripts/tests/test_issue_manager.py::TestAutoManagerModelDetection.test_auto_manager_logs_detected_model` — mock `process_issue_inplace` stub signature must accept `on_usage: Any = None` kwarg; the stub fires `on_model_detected` but will break on an unexpected keyword argument once `process_issue_inplace` gains the `on_usage` parameter [Agent 2/3 finding]

### Precision Notes (re-run 2026-05-06)

_Verified by codebase re-analysis — no partial implementation found (`on_usage`, `UsageCallback`, `result_token_count` absent from all files):_

**Exact line anchors:**
- `OutputCallback`/`ProcessCallback`/`ModelCallback` TypeAliases: `subprocess_utils.py:21–28`
- `run_claude_command` signature (base): `subprocess_utils.py:62–73`
- `on_model_detected` invocation + `else: continue` skip: `subprocess_utils.py:194–214`
- `run_claude_command` wrapper signature: `issue_manager.py:93–101`; call to `_run_claude_base`: `issue_manager.py:140`
- `run_with_continuation` signature (lines 149–240): **does not have `on_model_detected` either** — adding `on_usage` here is the first new callback parameter in this function
- `process_issue_inplace` signature: `issue_manager.py:315–752`; Phase 2 `run_with_continuation` call: ~line 605
- `AutoManager._process_issue` `on_model` closure: `issue_manager.py:1036–1048`
- `TestRunClaudeCommandModelDetection` class: `test_subprocess_utils.py:1333`
- `_make_single_line_selector` helper: `test_subprocess_utils.py:1336–1351`
- `test_unknown_event_type_skipped` (feeds `{"type": "result", ...}`): `test_subprocess_utils.py:1468`
- `test_wrapper_passes_on_model_detected`: `test_subprocess_mocks.py:164–202`

**Token calculation insertion point** (`context-monitor.sh:main()`, current lines 283–289):
```bash
# Current (to be extended):
if [ "${TRANSCRIPT_BASELINE}" -gt 0 ]; then
    NEW_TOKENS=$((TRANSCRIPT_BASELINE + TOKENS))
else
    NEW_TOKENS=$((CURRENT_TOKENS + TOKENS))
fi

# After ENH-1376 (priority branch inserted first):
if [ "${RESULT_TOKEN_COUNT}" -gt 0 ]; then
    NEW_TOKENS=$RESULT_TOKEN_COUNT   # authoritative, no heuristic added
elif [ "${TRANSCRIPT_BASELINE}" -gt 0 ]; then
    NEW_TOKENS=$((TRANSCRIPT_BASELINE + TOKENS))
else
    NEW_TOKENS=$((CURRENT_TOKENS + TOKENS))
fi
```
Note: the authoritative path must NOT add `TOKENS` on top — `result_token_count` already reflects the full turn usage.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### run_claude_command` section documents the existing signature; add `on_usage: UsageCallback | None = None` to the parameter list and table [Agent 2 finding]
- `docs/guides/SESSION_HANDOFF.md` — `### State File Format` JSON example shows only `estimated_tokens` and `transcript_baseline_tokens`; add the new `result_token_count` field to the example block and prose [Agent 2 finding]
- `docs/ARCHITECTURE.md` — `### Context Monitor and Session Continuation` section has a `**Context Estimation**` table describing the heuristic-only path; add a note that when `result_token_count > 0` in the state file the real count is used instead of heuristics [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` — `watch -n 1 'cat .ll/ll-context-state.json | jq .estimated_tokens'` diagnostic command and "Token Estimation accuracy" table reference heuristic path only; update to include `result_token_count` field alongside `estimated_tokens` [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `### context_monitor` section documents the two-tier token system (`estimate_weights` heuristics → `transcript_baseline`); does not reflect the new three-tier hierarchy with `result_token_count > 0` at top priority; update `use_transcript_baseline` row description and add a note about the authoritative fast path [Agent 2 re-run finding]

### Configuration
- N/A

## Impact

- **Priority**: P3 — improves automation reliability in long sessions; no data loss risk; sessions still function without it
- **Effort**: Medium (~60 lines across 3 files)
- **Risk**: Low — additive change; no existing behavior removed
- **Breaking Change**: No

## Labels

`enhancement`, `context-monitor`, `subprocess`, `automation`, `token-tracking`

---

## Status

**Open** | Created: 2026-05-06 | Priority: P3

## Related Issues

- BUG-1375: `classify_failure` misses "Prompt is too long"
- BUG (to be filed): PostToolUse hook exit 2 feedback unreliable in -p mode
- FEAT-1160: Context window analytics command (different goal; complementary)
- BUG-035 (completed): Context monitor hook not visible to Claude in non-interactive mode

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-06_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- **11 files, not "~60 lines across 3 files"**: Core is 3 source files (~60 lines), but 4 test files and 4 doc files also require changes. Budget 2-3× the original effort estimate.
- **context-monitor.sh bash integration is the riskiest touch**: The `result_token_count > 0` priority branch must be inserted before `estimate_tokens()` and the `transcript_baseline_tokens` paths without double-counting; test_hooks_integration.py is the safety net.
- **test_unknown_event_type_skipped must be retargeted first**: This test currently feeds `{"type": "result", ...}` as the "unknown" event — it will fail after step 3; switch it to `tool_use` before adding the new on_usage assertion.

## Resolution

**Status**: Completed — 2026-05-06T23:25:04Z

### Changes Made

1. **`scripts/little_loops/subprocess_utils.py`**: Added `UsageCallback = Callable[[int, int], None]` TypeAlias; added `on_usage: UsageCallback | None = None` parameter to `run_claude_command`; added `result` event handling that calls `on_usage(input_tokens + cache_read_input_tokens, output_tokens)` in the stream-json event loop.

2. **`scripts/little_loops/issue_manager.py`**: Added `json` import; added `on_usage` parameter to `run_claude_command` wrapper (forwarded to `_run_claude_base`); added `on_usage` parameter to `run_with_continuation` (forwarded to inner `run_claude_command`); added `on_usage` parameter to `process_issue_inplace`; built `_on_usage_writer` closure inside `process_issue_inplace` that writes `result_token_count` to `.ll/ll-context-state.json` and chains external `on_usage` if provided.

3. **`hooks/scripts/context-monitor.sh`**: Added `RESULT_TOKEN_COUNT` extraction from state (via jq); inserted three-tier priority branch: `result_token_count > 0` → use directly (no heuristic added); else transcript baseline → else pure heuristics.

4. **`scripts/tests/test_subprocess_utils.py`**: Retargeted `test_unknown_event_type_skipped` from `result` to `tool_use` event; added `test_on_usage_callback_called_with_result_event` and `test_on_usage_not_called_when_result_has_no_usage`.

5. **`scripts/tests/test_subprocess_mocks.py`**: Added `test_on_usage_forwarded_through_wrapper` to `TestRunClaudeCommand`.

6. **`scripts/tests/test_issue_manager.py`**: Added `on_usage: Any = None` to `mock_process_inplace` stub in `TestAutoManagerModelDetection`.

7. **`scripts/tests/test_hooks_integration.py`**: Added `test_result_token_count_used_when_present` and `test_result_token_count_zero_falls_back_to_heuristics`.

8. **Docs updated**: `docs/reference/API.md`, `docs/guides/SESSION_HANDOFF.md`, `docs/ARCHITECTURE.md`, `docs/development/TROUBLESHOOTING.md`, `docs/reference/CONFIGURATION.md`.

### Verification

- 238 targeted tests pass (test_subprocess_utils, test_subprocess_mocks, test_issue_manager, test_hooks_integration)
- Lint clean (`ruff check`)
- 13 pre-existing failures in unrelated test files unchanged

## Session Log
- `/ll:manage-issue` - 2026-05-06T23:25:04Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-05-06T23:13:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1df9f73a-9000-4c7a-9115-d1b1a8f89d7f.jsonl`
- `/ll:wire-issue` - 2026-05-06T23:08:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b152adf3-75b2-4d05-a817-c6c634d04240.jsonl`
- `/ll:refine-issue` - 2026-05-06T23:03:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/382a2462-7c10-4181-a09d-86f96f1095a0.jsonl`
- `/ll:decide-issue` - 2026-05-06T22:32:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/23e24604-d565-4cff-b89b-b443ba6c4696.jsonl`
- `/ll:confidence-check` - 2026-05-06T23:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cd74b3c8-c143-4831-b4b4-71e4cef6f2e4.jsonl`
- `/ll:confidence-check` - 2026-05-06T23:10:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfc4f28e-b755-4d83-ace1-9eddcfa8d764.jsonl`
- `/ll:confidence-check` - 2026-05-06T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d6242ac-c5ae-4ff3-ac0b-457b1639efbb.jsonl`
- `/ll:wire-issue` - 2026-05-06T22:25:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/91041a04-0374-439e-b9b5-45e3a0298f4f.jsonl`
- `/ll:refine-issue` - 2026-05-06T22:19:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c625de0-671d-4449-bde2-9d2787c568ff.jsonl`
- `/ll:format-issue` - 2026-05-06T21:09:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d5f24f2c-c15a-45a5-bd06-fac0ecb8d960.jsonl`
- `/ll:capture-issue` - 2026-05-06T20:59:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/381e1f9c-a749-4e5e-9040-a1d4e3d3e647.jsonl`
