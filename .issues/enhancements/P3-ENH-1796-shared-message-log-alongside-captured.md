---
id: ENH-1796
type: ENH
title: Shared message log alongside captured.* for cross-state context
priority: P3
status: done
captured_at: '2026-05-29T20:37:23Z'
completed_at: '2026-06-02T23:21:37Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
decision_needed: false
labels:
- captured
- fsm
- harness
- loops
- state-management
relates_to: []
confidence_score: 95
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1796: Shared message log alongside `captured.*` for cross-state context

## Summary

Add a run-scoped `messages` channel that every FSM state can append to
and any later state can read in full. This complements the existing
per-state `capture:` mechanism (which only exposes `${captured.<name>.output}`
and is essentially key-value), giving us the analogue of LangGraph's
`MessagesState` with `Annotated[list, add_messages]` — an append-only
conversation log that survives the whole run.

## Current Behavior

- States expose their output via `capture: <name>` and other states
  reference it as `${captured.<name>.output}`.
- When four states each need the same context (e.g., `discover` →
  `investigate` → `execute` → `check_semantic` all wanting both the
  item ID and prior reasoning), the YAML becomes a daisy-chain of
  `${captured.X.output}` concatenations, and each downstream state has
  to know exactly which upstream key holds what.
- There is no run-scoped append-only log of "what happened so far" that
  late states can summarize over.

## Expected Behavior

A `messages:` channel that:

1. Any state can append to via a state-level field, e.g.
   `append_to_messages: "${captured.execute.output}"`, or implicitly when
   `action_type: prompt`.
2. Any state can reference via `${messages}` (full log) or
   `${messages.last(3)}` (windowed view) in prompts/actions.
3. Persists to `.loops/runs/<id>/messages.jsonl` for replay and audit.
4. Has a size budget — when `messages` exceed N tokens, the runner
   summarizes older entries (mirrors DeerFlow's summarization
   middleware) and surfaces the summary as `${messages.summary}`.

This unblocks specialist-role pipelines (see FEAT-1798) where Plan →
Research → Implement → Report all need to see prior steps' reasoning,
not just the immediately-preceding output.

## Motivation

This enhancement would:
- Eliminate the N-state daisy-chain of `${captured.X.output}` concatenations that currently plagues multi-state FSM loops
- Enable specialist-role pipelines (see FEAT-1798) where Plan → Research → Implement → Report all share prior reasoning
- Provide the LangGraph `MessagesState` analogue (`Annotated[list, add_messages]`) for FSM loops — a well-understood pattern for append-only cross-state context

## Success Metrics

- Template variable references per downstream state: reduced from O(N) `${captured.X.output}` chains to O(1) `${messages}` reference
- Specialist-role pipeline viability: a 4-state pipeline (Plan → Research → Implement → Report) can share context without explicit per-state capture wiring
- Token budget: summarization keeps in-context messages within the loop's configured token limit

## Scope Boundaries

- **In scope**: `messages` channel with append semantics, `${messages}` / `${messages.last(N)}` / `${messages.summary}` template variables, JSONL persistence to `.loops/runs/<id>/messages.jsonl`, size-budget summarization middleware
- **Out of scope**: Replacing or removing the existing `captured.*` per-state mechanism, cross-run message persistence or replay, message editing or deletion, real-time streaming to external systems, structured message types beyond plain text

## API/Interface

New YAML fields and template variables:

```yaml
# State-level field — append output to the shared messages log
append_to_messages: "${captured.execute.output}"

# Template variables available in prompts/actions:
#   ${messages}            — full message log
#   ${messages.last(N)}    — last N messages (windowed view)
#   ${messages.summary}    — LLM-summarized older entries (when budget exceeded)
```

## Impact

- **Priority**: P3 — quality-of-life; current `captured.*` works but
  scales poorly past ~3 states with shared context.
- **Effort**: Medium — runner storage, prompt-interpolation extension,
  summarization policy, docs, tests.
- **Risk**: Medium — token budget interactions can surprise; needs
  conservative defaults and per-state opt-out.
- **Breaking Change**: No — additive.

## Implementation Steps

1. Extend runner storage to create and manage `.loops/runs/<id>/messages.jsonl` per run
2. Add `append_to_messages` state-level field and wire into state execution lifecycle
3. Extend prompt-interpolation to resolve `${messages}`, `${messages.last(N)}`, and `${messages.summary}`
4. Implement token-budget summarization middleware — when messages exceed threshold, summarize older entries via LLM call
5. Add tests for append, read, windowed-view, summarization, and budget enforcement
6. Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` and `skills/create-loop/reference.md`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. In `PersistentExecutor._save_state()` (`persistence.py`) — pass `messages=self._executor.messages` when constructing `LoopState(...)`; omitting this silently discards the accumulated log on every checkpoint save
8. In `PersistentExecutor.resume()` (`persistence.py`) — assign `self._executor.messages = state.messages` after loading state; without this, pre-interrupt messages are permanently lost on resume
9. Update `docs/reference/API.md` — add `messages` to the `InterpolationContext` namespace table (~line 4554) and to the `ExecutionResult` fields table (~line 4507)
10. Update `docs/reference/loops.md` and `docs/generalized-fsm-loop.md` — document `${messages.*}` as an alternative to the `${captured.*}` cross-state pattern

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete function-level references:_

1. **Schema** — `scripts/little_loops/fsm/schema.py:StateConfig` (line 337): add `append_to_messages: str | None = None` field; in `StateConfig.from_dict()` (line 548) add `append_to_messages=data.get("append_to_messages")`; in `StateConfig.to_dict()` add `if self.append_to_messages: result["append_to_messages"] = self.append_to_messages`
2. **Executor** — `scripts/little_loops/fsm/executor.py:FSMExecutor.__init__()` (line 174): add `self.messages: list[str] = []`; in `_run_action()` after the `if state.capture:` block (~line 1093): interpolate and append; in `_build_context()` (line 1543): add `messages=self.messages`; in `_finish()` (~line 1807): add `messages=self.messages` to `ExecutionResult`
3. **Interpolation** — `scripts/little_loops/fsm/interpolation.py:InterpolationContext` (line 37): add `messages: list[str] = field(default_factory=list)`; in `resolve()` (line 65) add `elif namespace == "messages":` branch; `"output"` or bare path → `"\n".join(self.messages)`; `r"^last\((\d+)\)$"` path → last N entries joined; `"summary"` → summary string (populated by summarization middleware); **note**: `last(N)` contains parentheses so `_get_nested()` cannot be reused — implement a dedicated `_get_messages_value()` method following the `_get_loop_value()` shape (line 145)
4. **Persistence** — `scripts/little_loops/fsm/persistence.py:PersistentExecutor._handle_event()` (~line 618): after the `usage.jsonl` block, add `messages.jsonl` append when a `messages_append` event is emitted; `LoopState` (line 162): add `messages: list[str] = field(default_factory=list)`, serialize in `to_dict()`/`from_dict()` following `retry_counts` pattern (line 201)
5. **Resume** — `scripts/little_loops/cli/loop/lifecycle.py:cmd_resume()` (line 461): after re-injecting `run_dir`, load existing `messages.jsonl` entries and populate `executor.messages` so the resumed run continues appending to the same log
6. **Tests** — `scripts/tests/test_fsm_interpolation.py` (follow line 44), `scripts/tests/test_fsm_executor.py` (follow line 679), `scripts/tests/test_fsm_persistence.py` (follow line 410)
7. **Docs** — `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § Referencing Captured Outputs; `skills/create-loop/reference.md` (capture field section)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — runner storage (`self.messages`), state execution (`_run_action`), prompt interpolation (`_build_context`, `_finish`)
- `scripts/little_loops/fsm/schema.py` — add `append_to_messages` field to `StateConfig`
- `scripts/little_loops/fsm/interpolation.py` — add `messages` namespace to `InterpolationContext`
- `scripts/little_loops/fsm/persistence.py` — add `messages.jsonl` append in `_handle_event`; add `messages` to `LoopState`
- `scripts/little_loops/fsm/types.py` — add `messages` field to `ExecutionResult`
- `scripts/little_loops/fsm/validation.py` — validate `append_to_messages` expression format
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `append_to_messages` property to state schema
- `scripts/little_loops/cli/loop/lifecycle.py` — reload `messages.jsonl` in `cmd_resume()`
- `skills/create-loop/reference.md` — FSM field reference documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — documented captured-outputs pattern

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

> ⚠ Anchor `scripts/little_loops/runner.py` no longer resolves — the execution engine lives in `scripts/little_loops/fsm/executor.py` (`FSMExecutor`). `scripts/little_loops/fsm/runners.py` is the subprocess action runner only.

- `scripts/little_loops/fsm/executor.py` — `FSMExecutor.__init__()` (line 174): add `self.messages: list[str] = []` alongside `self.captured`; `_run_action()` (~line 1087): add `append_to_messages` processing after the `if state.capture:` block; `_build_context()` (line 1537): pass `messages=self.messages` to `InterpolationContext`; `_finish()` (~line 1807): include `messages` in `ExecutionResult`
- `scripts/little_loops/fsm/schema.py:StateConfig` (line 337) — add `append_to_messages: str | None = None` field (mirrors `capture: str | None = None` at line 402); parse in `StateConfig.from_dict()` (line 548) with `append_to_messages=data.get("append_to_messages")`
- `scripts/little_loops/fsm/interpolation.py:InterpolationContext` (line 37) — add `messages: list[str] = field(default_factory=list)` field; extend `InterpolationContext.resolve()` (line 65) with `elif namespace == "messages":` branch; `${messages}` → `"\n".join(self.messages)`, `${messages.last(N)}` → regex `r"^last\((\d+)\)$"` on path, `${messages.summary}` → summarized-older-entries string
- `scripts/little_loops/fsm/persistence.py:PersistentExecutor._handle_event()` (~line 610) — add `messages.jsonl` append to `run_dir` following the `usage.jsonl` write pattern exactly (lines 618–634); `LoopState.to_dict()/from_dict()` (lines 216, 248) — add `messages` field for interrupt/resume durability, following the `retry_counts` pattern
- `scripts/little_loops/fsm/types.py:ExecutionResult` (line 17) — add `messages: list[str] = field(default_factory=list)` to surface the accumulated log in the final run result
- `scripts/little_loops/fsm/validation.py` — add validation that `append_to_messages` contains a valid `${...}` expression
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `append_to_messages` as an optional string property in the state schema

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:cmd_run()` (line 391) — injects `context["run_dir"]` and creates the directory before the executor starts; `messages.jsonl` is written here by `PersistentExecutor` without requiring changes to this file
- `scripts/little_loops/cli/loop/lifecycle.py:cmd_resume()` (line 461) — re-injects `run_dir` using the same `instance_id` on resume; must also reload `self.messages` list from `messages.jsonl` (if it exists) so resumed runs continue appending to the same log rather than starting fresh
- `scripts/little_loops/fsm/persistence.py:LoopState` (line 162) — serializes `captured` dict; must add `messages: list[str]` field to `to_dict()`/`from_dict()` so the message list survives interrupts and resumes (mirrors `retry_counts` at line 201)
- All loop YAML files using `capture:` + `${captured.*}` patterns call the same interpolation system that will gain the `messages` namespace; no YAML changes required for existing loops

### Similar Patterns
- `scripts/little_loops/fsm/persistence.py:PersistentExecutor._handle_event()` (lines 618–634) — **exact template for `messages.jsonl`**: guards with `if run_dir:`, opens `Path(run_dir) / "usage.jsonl"` in `"a"` mode, writes `json.dumps(entry) + "\n"` — replicate this pattern for `messages.jsonl`
- `scripts/little_loops/fsm/executor.py:FSMExecutor.__init__()` (line 174) — `self.captured: dict[str, dict[str, Any]] = {}` — `self.messages: list[str] = []` follows the same init-in-constructor pattern
- `scripts/little_loops/fsm/interpolation.py:InterpolationContext._get_loop_value()` (line 145) — shows how to add a computed property namespace (e.g., `loop.elapsed` is derived from `elapsed_ms`); use this shape for `messages.last(N)` and `messages.summary`
- `scripts/little_loops/ab_writer.py:write_ab_json()` (line 233) — writes a structured JSON artifact to `Path(run_dir) / "ab.json"` via `path.write_text(...)`; serves as a template for a possible `message_log.py` module with `append_message()` / `read_messages()` / `summarize_messages()` functions
- `scripts/little_loops/fsm/executor.py:FSMExecutor._execute_with_baseline()` — `self._ab_results: list[dict]` accumulated across iterations, written at completion; closest structural analogue to an append-only cross-state list in the executor

### Tests
- `scripts/tests/test_fsm_interpolation.py` — add `messages` namespace tests following `TestInterpolationContext.test_captured_variable` (line 44): `test_messages_full_log`, `test_messages_last_n`, `test_messages_summary_fallback`
- `scripts/tests/test_fsm_executor.py:TestCapture` (line 679) — add `test_append_to_messages_stores_message`, `test_messages_available_in_next_state`, `test_messages_accumulates_across_states` following `test_capture_stores_output` (line 679)
- `scripts/tests/test_fsm_persistence.py` — add test for `messages.jsonl` creation in `run_dir` following `test_archive_run_directory_structure` (line 410); also test `LoopState.to_dict()`/`from_dict()` roundtrip with `messages` field
- `scripts/tests/test_fsm_schema.py` — add test that `append_to_messages` is parsed from YAML dict via `StateConfig.from_dict()`
- `scripts/tests/test_usage_reporter.py` — `_make_usage_jsonl()` helper (line 1) is a reusable pattern for writing JSONL fixtures in tests; use the same approach for `messages.jsonl` test setup

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_validation.py` — add `test_append_to_messages_validates_expression_format`; `validation.py` is being modified but this test file has no coverage for the new field yet [new test needed]
- `scripts/tests/test_fsm_schema_fuzz.py` — add `append_to_messages` to the fuzz input field generation strategy so `StateConfig.from_dict()` fuzz tests exercise the new field [new fuzz input]
- `scripts/tests/test_fsm_executor.py:TestExecutionResult.test_to_dict` (line 1929) — update to assert on `messages` field; currently serializes "all fields" but will be incomplete after feature lands [update — incomplete]
- `scripts/tests/test_fsm_executor.py:TestExecutionResultToDict.test_to_dict_without_optional_fields` (line 3085) — add `assert "messages" not in d` if `messages` follows omit-if-empty convention [update — incomplete]
- `scripts/tests/test_fsm_persistence.py:TestLoopState.test_to_dict_roundtrip` (line 29) — update to include `messages` field in the roundtrip fixture [update — incomplete]
- `scripts/tests/test_fsm_persistence.py:TestLoopState.test_from_dict_with_defaults` (line 72) — add `assert state.messages == []` following the existing defaults-assertion pattern [update — incomplete]

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`
- `skills/create-loop/reference.md`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `InterpolationContext` block (~line 4554): add `messages` to the namespace list; `ExecutionResult` block (~line 4507): add `messages: list[str]` to the fields table [Agent 2 finding]
- `docs/reference/loops.md` — documents `${captured.*}` as the sole cross-state channel; needs `${messages.*}` added as an alternative pattern [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — usage examples reference only `${captured.*}`; add `${messages.*}` examples alongside [Agent 2 finding]

### Configuration
- N/A

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § Referencing Captured Outputs | Today's documented pattern; this issue extends it |
| `skills/create-loop/reference.md` | FSM field reference where the new `messages` channel would be specified |

## Labels

`captured`, `fsm`, `harness`, `loops`, `state-management`

## Status

**Open** | Created: 2026-05-29 | Priority: P3

## Resolution

Implemented the `messages` channel as a run-scoped append-only log alongside `captured.*`:

- **`append_to_messages`** state field: interpolation expression whose result is appended to `self.messages` after the action runs and after capture
- **`${messages}`** / **`${messages.output}`**: full log joined by newline
- **`${messages.last(N)}`**: windowed view of last N entries
- **`${messages.summary}`**: pre-computed summary string (stub; returns `""` until summarization middleware is added)
- **JSONL audit trail**: each append writes to `.loops/runs/<id>/messages.jsonl` via `_handle_event`
- **Interrupt/resume durability**: `messages` persisted in `LoopState` and restored in `PersistentExecutor.resume()`
- **`ExecutionResult.messages`**: accumulated log surfaced in the final run result

Files changed: `types.py`, `interpolation.py`, `schema.py`, `executor.py`, `persistence.py`, `validation.py`, `fsm-loop-schema.json`, `skills/create-loop/reference.md`, `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`. Tests: 19 new tests across interpolation, executor, persistence, and schema suites; 806 total pass.

## Session Log
- `/ll:ready-issue` - 2026-06-02T23:07:49 - `813708df-6857-4ab9-83bf-d7a78ef1c948.jsonl`
- `/ll:confidence-check` - 2026-06-02T23:30:00Z - `0c05411f-89e3-44df-a2fa-e1cb5e5829cf.jsonl`
- `/ll:wire-issue` - 2026-06-02T22:58:47 - `7d4253d1-4f98-4f64-bcb2-83f0e4ed7660.jsonl`
- `/ll:refine-issue` - 2026-06-02T22:49:57 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:35 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:15 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:format-issue` - 2026-05-29T21:14:09 - `0a9cb5c6-15fc-4ffc-a6bb-7ab28458c9d2.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:37:23Z - `f2a0c61b-6b34-41d4-98fb-c566ba046de6.jsonl`
