---
discovered_date: 2026-04-14
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 61
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
size: Very Large
---

# BUG-1105: FSM Loops Silently Skip All Work on 429 Rate Limit Failures

## Summary

When sub-loops (e.g., `format-issue`, `issue-size-review`) hit 429 rate limit errors during prompt actions, the FSM executor does not retry or surface the failures — it silently transitions as if the work completed, causing the parent loop to skip every queued item. The loop exits with a normal completion status despite having accomplished nothing.

Observed in run `2026-04-14T052952-auto-refine-and-implement` (loop-viz project): 56 prompt actions hit 429 across sub-loops, each timing out ~200s before failing. All issues FEAT-141 through FEAT-168+ were skipped without successful refinement.

## Current Behavior

- Prompt actions that return 429 (rate-limited) are classified as `is_prompt=true` and are excluded from the BUG action failure signal rule
- No retry or backoff is applied to rate-limited prompt actions; the action fails after ~200s timeout
- The FSM state receives a failure exit code and routes via `on_error` or `on_no` (whichever is wired), effectively skipping the current item
- Sub-loop states (`detect_children`, `recheck_scores`, `dequeue_next`) show `exit_code=1` but these match the same routing pattern as intentional `on_no` transitions (e.g., recursive-refine configs not loaded), making the failure invisible to signal rules
- The parent loop completes normally with a success status even though 100% of items were skipped

## Expected Behavior

- When a prompt action fails with a 429 response, the FSM executor detects the rate-limit condition and applies an exponential backoff retry before transitioning out of the state
- If retries are exhausted, the failure is recorded distinctly (separate from `on_no` / intentional skip routing) so that signal rules can detect it
- The loop's completion report distinguishes between "skipped (intentional)" and "skipped (rate-limited)" items
- Ideally, a global rate-limit backoff is applied across concurrent sub-loops to reduce cascading 429s

## Root Cause

The 429 condition is not currently modeled in the FSM state machine:

- **`scripts/little_loops/fsm/executor.py`** — action execution does not inspect exit codes or output for rate-limit signals before routing; `is_prompt=true` suppresses the failure signal entirely
- **Signal rules** — the `BUG_action_failure` rule explicitly excludes `is_prompt=true` actions, so 429 failures produce no alerting signal
- **Sub-loop config routing** — `exit_code=1` from a 429-failed prompt state is structurally identical to a deliberate `on_no` transition (e.g., "no items to process"), making it impossible for downstream logic to distinguish the two

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Interceptor access point**: `executor.py:455-461` — `before_route` receives `RouteContext` (`executor.py:54-64`) with `action_result: ActionResult | None`; `ActionResult` (`types.py:57-71`) exposes `output: str`, `stderr: str`, `exit_code: int`, `duration_ms: int` — all accessible for 429 detection
- **`_retry_counts` pattern**: declared at `executor.py:142-148`, incremented at `executor.py:200-206`, exhaustion check at `executor.py:229-252` — this exact structure is the model for a new `_rate_limit_retries` dict
- **Sub-loop routing confirmed**: `_execute_sub_loop()` at `executor.py:318-381` routes parent on child `terminated_by`; in `recursive-refine.yaml:90-99`, both `on_error` and `on_failure` route to `detect_children`, confirming 429-caused failures are indistinguishable from intentional skips at the parent level
- **`is_prompt` flag clarification**: the flag appears in the `action_complete` event payload emitted at `executor.py:522-532`; inside the executor it does not gate signal detection — the suppression operates at the external signal rule consumer level

## Steps to Reproduce

1. Run `auto-refine-and-implement` (or any loop with `format-issue` / `issue-size-review` sub-loops) against a large batch of issues while under API rate pressure
2. Observe that all queued issues show `exit_code=1` in sub-loop state traces
3. Observe loop completes with normal exit and no work done
4. Confirm via logs that the failures are 429-type (200s timeout + rate limit message)

## Frequency

Reproducible under sustained concurrent load. Observed once definitively (2026-04-14). Likely latent in any long-running batch run that generates ≥40 concurrent prompt actions.

## Proposed Solution

Address at two levels:

**Level 1 — Retry with backoff at the executor level:**
- Detect 429 / rate-limit responses via the existing `before_route` interceptor hook (`executor.py:455-461`), which receives the full `ActionResult` before routing occurs
- Apply exponential backoff sleep (e.g., 30s → 60s → 120s) inside the interceptor and return `RouteDecision(current_state)` to retry the state in-place
- Add `max_rate_limit_retries: int` to `StateConfig` (parallel to existing `max_retries`); executor tracks retries in a new `_rate_limit_retries` dict
- After retries exhausted, route to `on_rate_limit_exhausted` (new `StateConfig` field, parallel to existing `on_retry_exhausted`) or fall back to `on_error`

**Level 2 — Distinguishable failure signal:**
- Use a new `on_rate_limit_exhausted: str` routing field on `StateConfig` (consistent with `on_retry_exhausted` pattern) rather than a synthetic exit code — exit codes as internal signals are a design smell
- Emit a distinct `rate_limit_exhausted` event from the executor when retries are exhausted, keyed on the new routing field
- Add a `RATE_LIMIT_STORM` detection rule in `signal_detector.py`: if N consecutive states hit `rate_limit_exhausted`, emit a halt/pause signal

**Level 3 — Concurrent backoff coordination (optional):**
- When multiple sub-loops are active and one hits 429, propagate a global cooldown to sibling sub-loops to prevent pile-on (shared file-backed semaphore checked by all executor instances)

**Fragment Library — Routing reuse across loops:**
- Add a `with_rate_limit_handling` fragment to `scripts/little_loops/loops/lib/common.yaml`
- Fragment wires `max_rate_limit_retries` and `on_rate_limit_exhausted` via context interpolation so loops can opt in with a single `fragment:` line
- Loops that don't need custom exhaustion handling get the executor default (fall through to `on_error`) with no config changes at all

## Integration Map

- `scripts/little_loops/fsm/executor.py` — `before_route` interceptor (detection + backoff), `_rate_limit_retries` dict, exhaustion routing
- `scripts/little_loops/fsm/schema.py` — `StateConfig`; add `max_rate_limit_retries` and `on_rate_limit_exhausted` fields
- `scripts/little_loops/fsm/signal_detector.py` — `RATE_LIMIT_STORM` signal rule
- `scripts/little_loops/loops/lib/common.yaml` — `with_rate_limit_handling` fragment
- Loop YAML configs — `auto-refine-and-implement`, `recursive-refine`, any loop with sub-loop prompt actions

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Additional files to modify:**
- `scripts/little_loops/fsm/types.py:57-71` — `ActionResult` dataclass; read-only (used in interceptor for detection, no changes needed)
- `scripts/little_loops/fsm/validation.py:280-301` — add paired validation for `max_rate_limit_retries` + `on_rate_limit_exhausted` (exact mirror of existing `max_retries` paired validation)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — update JSON Schema for new `StateConfig` fields
- `scripts/little_loops/cli/loop/layout.py:201-202` — add `on_rate_limit_exhausted` diagram edge (mirrors `on_retry_exhausted` edge at line 201)

**Reusable existing code:**
- `scripts/little_loops/issue_lifecycle.py:62-75` — `classify_failure()` has canonical 429-detection patterns: `["429", "rate limit", "too many requests", "quota exceeded", "resource exhausted", "resourceexhausted", "out of extra usage", "usage limit", "api limit"]` — reuse these in the `before_route` interceptor

**Test files:**
- `scripts/tests/test_fsm_executor.py:3238-3253` — `MockActionRunner(use_indexed_order=True)` pattern for sequential retry scenarios
- `scripts/tests/test_fsm_executor.py:3336-3357` — `event_callback` capture pattern to assert `rate_limit_exhausted` events are emitted
- `scripts/tests/test_signal_detector.py:49-55` — custom `SignalPattern` test pattern
- `scripts/tests/test_fsm_schema.py` — existing schema field test patterns to follow
- `scripts/tests/test_fsm_validation.py` — existing paired-field validation test patterns to follow

**Documentation to update:**
- `docs/reference/schemas/retry_exhausted.json` — model new `rate_limit_exhausted` event schema after this
- `docs/reference/EVENT-SCHEMA.md` — register new event type

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/persistence.py:426,493` — **CRITICAL**: reads `self._executor._retry_counts` directly to save/restore retry state on pause/resume; must also save/restore `_rate_limit_retries` dict or rate-limit retry counts will be lost across resumes [Agent 1 finding]
- `scripts/little_loops/fsm/__init__.py` — re-exports public FSM symbols (`FSMExecutor`, `ActionResult`, `RouteContext`, `RouteDecision`, `SignalPattern`, `StateConfig`, `FSMLoop`); any new public event type constant needs to be re-exported here [Agent 1 finding]
- `scripts/little_loops/extensions/reference_interceptor.py` — implements `before_route` protocol; verify `RouteContext` call signature is unchanged after adding rate-limit detection [Agent 1 finding]

### Additional Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/cli.py:76-116` — `CliColorsEdgeLabelsConfig` needs a `rate_limit_exhausted: str` color field (parallel to `retry_exhausted: str` at line 86) for user-configurable diagram edge coloring [Agent 2 finding]
- `scripts/little_loops/config/core.py:475-484` — `BRConfig.to_dict()` must include `"rate_limit_exhausted"` in the `fsm_edge_labels` dict to make the new color field configurable [Agent 2 finding]
- `scripts/little_loops/generate_schemas.py:78-290` — `SCHEMA_DEFINITIONS` is a **manual registry** (not auto-discovered); add `rate_limit_exhausted` entry here for `ll-generate-schemas` to produce the new schema file [Agent 2 finding]
- `scripts/little_loops/cli/schemas.py:15` — docstring hardcodes count "19 LLEvent types"; update to "20" after adding new event type [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will break (must update before first test run):**
- `scripts/tests/test_signal_detector.py:149-154` — `test_default_patterns` asserts `len(detector.patterns) == 3` and `pattern_names == {"handoff", "error", "stop"}`; adding `RATE_LIMIT_STORM` breaks both assertions [Agent 3 finding]
- `scripts/tests/test_generate_schemas.py:18-19,23-43,50-53,165-168` — 4 test bodies assert count 19 and/or exact set of 19 event type strings; update count to 20 and add `"rate_limit_exhausted"` to the set literal [Agent 2/3 finding]

**New tests to write (follow existing patterns):**
- `scripts/tests/test_fsm_executor.py` — new `TestRateLimitHandling` class; mirror `TestPerStateRetryLimits` (lines 3206–3376): 429 detection in `before_route`, backoff sleep calls, `_rate_limit_retries` dict tracking, `rate_limit_exhausted` event emission [Agent 3 finding]
- `scripts/tests/test_fsm_schema.py` — tests for `max_rate_limit_retries`/`on_rate_limit_exhausted` fields: construction, `from_dict`, `to_dict`, `get_referenced_states`, roundtrip; mirror `on_blocked` pattern (lines 342–398) [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py` — paired field validation: `max_rate_limit_retries` without `on_rate_limit_exhausted` → error, and vice versa; mirror `validation.py:280–301` logic [Agent 3 finding]
- `scripts/tests/test_signal_detector.py` — `RATE_LIMIT_STORM` pattern test: match, no-match, payload; mirror `test_custom_pattern` (lines 49–55) [Agent 3 finding]
- `scripts/tests/test_fsm_fragments.py` — `with_rate_limit_handling` defined in `common.yaml`, correct fields, resolves from real `common.yaml`; mirror `test_llm_gate_*` pattern (lines 534–584); **the new fragment must include a non-empty `description` field or `test_all_common_yaml_fragments_have_description` (line 945) will fail** [Agent 3 finding]
- `scripts/tests/test_ll_loop_display.py:2378-2387` — add parallel test for `on_rate_limit_exhausted` edge appearing in `_collect_edges()` output [Agent 2/3 finding]
- `scripts/tests/test_config.py:1324` — add assertion for `rate_limit_exhausted` default color value on `CliColorsEdgeLabelsConfig` [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:594` — `cli.colors.fsm_edge_labels` table; add `rate_limit_exhausted` row [Agent 2 finding]
- `docs/reference/OUTPUT_STYLING.md:59,203,214` — edge label color table (line 59), `_collect_edges()` prose naming `on_retry_exhausted` (line 203), edge label color table (line 214); add `rate_limit_exhausted` to all three locations [Agent 2 finding]
- `docs/reference/API.md:3780-3802` — `StateConfig` class API block; add `max_rate_limit_retries` and `on_rate_limit_exhausted` fields [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:993-1003,1620-1627` — `max_retries`+`on_retry_exhausted` pattern docs; add parallel section for `max_rate_limit_retries`+`on_rate_limit_exhausted` [Agent 2 finding]
- `skills/analyze-loop/SKILL.md:107,143-147` — event type table (line 107) and signal classification rules (lines 143–147); add `rate_limit_exhausted` event and a parallel detection rule [Agent 2 finding]
- `skills/create-loop/reference.md:891-937` — `max_retries`/`on_retry_exhausted` reference section; add parallel `max_rate_limit_retries`/`on_rate_limit_exhausted` section [Agent 2 finding]
- `skills/create-loop/loop-types.md:789-790,849` — per-item retry safeguard mentions; add parallel rate-limit note [Agent 2 finding]
- `docs/reference/COMMANDS.md:512` — `/ll:analyze-loop` signal detection rules mention `retry_exhausted`; add `rate_limit_exhausted` rule [Agent 2 finding]

## Implementation Steps

1. Add 429/rate-limit detection via the existing `before_route` interceptor in `executor.py` (inspect `ActionResult.output` + `stderr` for rate-limit patterns)
2. Implement exponential backoff sleep inside the interceptor; return `RouteDecision(current_state)` to retry in-place
3. Add `max_rate_limit_retries: int` and `on_rate_limit_exhausted: str` fields to `StateConfig` in `scripts/little_loops/fsm/schema.py`; track retries in a new `_rate_limit_retries` dict (parallel to `_retry_counts`)
4. Emit a `rate_limit_exhausted` event and add a `RATE_LIMIT_STORM` detection rule in `scripts/little_loops/fsm/signal_detector.py`
5. Add `with_rate_limit_handling` fragment to `scripts/little_loops/loops/lib/common.yaml` to distribute routing wiring across loops
6. Test with a mock 429 response in the executor test suite
7. Update affected loop YAML configs (`auto-refine-and-implement`, `recursive-refine`) to import `lib/common.yaml` and apply the fragment where per-state exhaustion routing is needed

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 — `before_route` detection mechanics:**
- Interceptor fires at `executor.py:455-461`; receives `RouteContext` (`executor.py:54-64`) with `route_ctx.action_result.output` and `route_ctx.action_result.stderr`
- **Do NOT use `"$current"` in `RouteDecision`** — `"$current"` is only resolved by `_resolve_route()` (`executor.py:764-776`), which is bypassed when `before_route` returns a `RouteDecision`; use `route_ctx.state_name` for in-place retry
- Reuse detection patterns from `issue_lifecycle.py:62-75` — `classify_failure()` already implements the canonical list; copy/import the pattern strings rather than reimplementing
- Model the backoff sleep after the interruptible pattern at `executor.py:299-305` (polls `_shutdown_requested` every 100 ms to remain cancellable)

**Step 3 — Schema changes (5-part pattern):**
- Follow the exact 5-part pattern used by `max_retries` / `on_retry_exhausted`:
  1. Docstring (`schema.py:187-211`)
  2. Field declaration (`schema.py:228-229`)
  3. `to_dict` serialization (`schema.py:270-273`)
  4. `from_dict` deserialization + register `on_rate_limit_exhausted` in `_known_on_keys` set (`schema.py:305-338`) to prevent capture in `extra_routes`
  5. `get_referenced_states` (`schema.py:362-363`)
- Add paired validation at `validation.py:280-301` (both fields required together; `max_rate_limit_retries >= 1`)
- Update `fsm-loop-schema.json` for new fields
- Add `on_rate_limit_exhausted` edge at `cli/loop/layout.py:201-202`

**Step 4 — RATE_LIMIT_STORM approach clarification:**
- `SignalPattern` instances in `signal_detector.py:73-76` match text in `action.output` at runtime — they cannot directly detect executor-tracked exhaustion events
- Correct model: emit a `rate_limit_exhausted` event inside the executor (parallel to `retry_exhausted` at `executor.py:229-252`); add a consecutive-exhaustion counter in the main loop; trigger halt/pause when threshold exceeded
- A `SignalPattern`-based `RATE_LIMIT_STORM` only makes sense if an action explicitly writes `RATE_LIMIT_STORM: ...` to stdout, which is not the case here
- New event schema: add `docs/reference/schemas/rate_limit_exhausted.json` modeled after `docs/reference/schemas/retry_exhausted.json`

**Step 6 — Test patterns:**
- Mock 429: `ActionResult(output="rate limit exceeded (429)", stderr="", exit_code=1, duration_ms=100)`
- Use `MockActionRunner(use_indexed_order=True)` from `test_fsm_executor.py:3238-3253` to sequence: [429-fail, 429-fail, ..., success] or [429-fail × N → exhausted]
- Assert emitted events with `event_callback` pattern from `test_fsm_executor.py:3336-3357`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/fsm/persistence.py:426,493` — save and restore `_rate_limit_retries` dict in parallel with `_retry_counts` (critical: without this, rate-limit retry counts are lost on loop pause/resume)
9. Update `scripts/little_loops/config/cli.py:86` + `config/core.py:475-484` — add `rate_limit_exhausted: str` field to `CliColorsEdgeLabelsConfig` and include it in the `fsm_edge_labels` dict in `BRConfig.to_dict()`
10. Update `scripts/little_loops/generate_schemas.py:78-290` — add `rate_limit_exhausted` entry to `SCHEMA_DEFINITIONS` manual registry; update count docstring in `scripts/little_loops/cli/schemas.py:15`
11. Fix breaking tests before first test run: update `test_signal_detector.py:149-154` (`len == 3` → `4`, add `"rate_limit_storm"` to set), update `test_generate_schemas.py:18-43,50-53,165-168` (count 19 → 20, add `"rate_limit_exhausted"` to set literal)
12. Update `scripts/little_loops/cli/loop/layout.py:27-36` (`_EDGE_LABEL_COLORS` dict) and `layout.py:62-74` (`_edge_line_color()` priority tuple) — add `"rate_limit_exhausted"` to both so diagram edges render with color (these lines are within the already-listed `layout.py` file)
13. Update documentation: `docs/reference/CONFIGURATION.md:594`, `OUTPUT_STYLING.md:59,203,214`, `API.md:3780-3802`, `LOOPS_GUIDE.md:993,1620`, `COMMANDS.md:512`, `skills/analyze-loop/SKILL.md:107,143`, `skills/create-loop/reference.md:891`, `skills/create-loop/loop-types.md:789,849`

## Impact

- **Priority**: P2 — Causes complete silent loss of all loop work under rate-limit pressure; difficult to detect without log inspection
- **Effort**: Medium — Executor changes are contained; signal rule additions are low-risk
- **Risk**: Low — Retry logic is additive; existing routing unchanged for non-429 exits
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM executor design |
| `scripts/little_loops/fsm/executor.py` | Primary implementation target |

## Labels

`bug`, `fsm`, `rate-limit`, `executor`, `reliability`, `captured`

## Session Log
- `/ll:wire-issue` - 2026-04-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/50dc0377-0fe3-4e41-ab44-2e09d1e2b197.jsonl`
- `/ll:refine-issue` - 2026-04-14T15:36:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/50dc0377-0fe3-4e41-ab44-2e09d1e2b197.jsonl`
- `/ll:confidence-check` - 2026-04-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/48e37646-1fa6-41c1-b624-9b5f6b0c635f.jsonl`
- `/ll:capture-issue` - 2026-04-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfe2ed92-588d-4d5f-8160-dba65d8166e5.jsonl`
- `/ll:issue-size-review` - 2026-04-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4abdbd46-1b62-4801-9d00-a2569583afde.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-14
- **Reason**: Issue too large for single session (score: 11/11)

### Decomposed Into
- BUG-1107: FSM Executor 429 Detection, Retry, and Persistence
- BUG-1108: StateConfig Schema, Validation, Signal Detection, Config, and UI for Rate Limit Handling
- BUG-1109: Tests and Documentation for Rate Limit Handling

---

## Status

**Decomposed** | Created: 2026-04-14 | Priority: P2
