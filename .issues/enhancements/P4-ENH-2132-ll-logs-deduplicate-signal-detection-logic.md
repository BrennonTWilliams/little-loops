---
id: ENH-2132
type: ENH
priority: P4
status: done
title: Deduplicate ll-logs signal detection logic (_extract_tool_name / _extract_eval_invocation)
discovered_date: 2026-06-14
discovered_by: capture-issue
captured_at: '2026-06-14T01:52:17Z'
completed_at: '2026-06-19T19:17:00Z'
parent: EPIC-1918
confidence_score: 100
outcome_confidence: 90
score_complexity: 23
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 22
---

# ENH-2132: Deduplicate ll-logs signal detection logic (_extract_tool_name / _extract_eval_invocation)

## Summary

`_extract_tool_name()` (lines 284–342) and `_extract_eval_invocation()` (lines 1397–1458) in `cli/logs.py` implement the same three-signal JSONL record detection:

- (a) `queue-operation` enqueue with `/ll:<name>` content
- (b) `user` record with `<command-name>/ll:<name>` pattern
- (c) `assistant` Bash tool-use invoking `ll-<tool>`

They share the same regex constants (`_QUEUE_SKILL_RE`, `_COMMAND_NAME_SKILL_RE`, `_LL_BASH_RE`) and the same `</command-name>` stripping logic. The only difference is the return type: `_extract_tool_name` returns `str | None`; `_extract_eval_invocation` returns `_EvalInvocation | None` (adds `runner`, `input_context`, `session_id`, `timestamp`).

This is a maintenance risk: any change to signal detection (e.g., a new record type, a new pattern) must be applied in two places.

## Motivation

Single source of truth for JSONL signal detection. A new record type added to one function but not the other would cause silent divergence between `sequences`/`stats`/`scan-failures` (which use `_extract_tool_name`) and `eval-export` (which uses `_extract_eval_invocation`).

## Success Metrics

- Signal detection implementations: 2 → 1 (`_detect_ll_signal` replaces both)
- Backward compatibility: all existing tests pass via shims with zero modifications
- Maintenance surface: a new record type requires changes in 1 place (not 2)

## Scope Boundaries

- **In scope**: Extract shared 3-signal detection into `_detect_ll_signal()`; one-liner backward-compatible shims for `_extract_tool_name` and `_extract_eval_invocation`; update any test that calls those functions directly to exercise the shared helper
- **Out of scope**: Changing signal detection behavior or regex patterns; modifying `_EvalInvocation` fields beyond the refactor; performance optimization of the detection logic

## API/Interface

Internal refactoring — no public API changes.

New internal helper (private to `cli/logs.py`):

```python
@dataclass
class _InvocationSignal:
    tool_name: str      # e.g. "ll:scan-codebase"
    runner: str         # e.g. "queue-operation" | "user" | "bash"
    input_context: str  # raw matched text

def _detect_ll_signal(record: dict) -> _InvocationSignal | None: ...
```

Existing functions become shims:

```python
def _extract_tool_name(record: dict) -> str | None:
    sig = _detect_ll_signal(record)
    return sig.tool_name if sig else None
```

## Implementation Steps

1. Introduce a shared `_InvocationSignal` dataclass (or named tuple) capturing: `tool_name: str`, `runner: str`, `input_context: str`.
2. Replace both functions with a single `_detect_ll_signal(record: dict) -> _InvocationSignal | None` that returns all three fields.
3. `_extract_tool_name(record)` becomes `sig.tool_name if (sig := _detect_ll_signal(record)) else None` — a one-liner shim for backward compatibility.
4. `_extract_eval_invocation(record)` uses `_detect_ll_signal(record)` to get the signal, then wraps it in `_EvalInvocation` with `session_id` and `timestamp` from the record.
5. Update tests to exercise `_detect_ll_signal` directly if needed; existing tests should continue to pass via the shims.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update the import block in `scripts/tests/test_ll_logs.py` (lines 16–32) to add `_InvocationSignal` and `_detect_ll_signal` to the `from little_loops.cli.logs import (...)` statement when writing new unit tests.
7. Write a `TestDetectLlSignal` class in `test_ll_logs.py` with at minimum: `test_detect_ll_signal_queue_enqueue` (queue-enqueue signal (a) has no current direct unit test), `test_detect_ll_signal_command_name_user_record`, `test_detect_ll_signal_bash_tool_use`, `test_detect_ll_signal_returns_none_for_unrelated`, and shim-equivalence tests `test_extract_tool_name_delegates_to_detect_ll_signal` / `test_extract_eval_invocation_delegates_to_detect_ll_signal`. Follow the `TestFrozenDataclassConvention` pattern (`test_host_runner.py:666`) for `_InvocationSignal` structural tests.
8. After implementation, run `ll-ctx-stats` as a behavioral smoke-test to verify the indirect `_aggregate_skill_stats → _extract_tool_name` call chain in `ctx_stats.py` remains intact.

## Affected Files

- `scripts/little_loops/cli/logs.py` (lines 284–342 and 1397–1458)
- `scripts/tests/test_ll_logs.py` (tests that call `_extract_tool_name` or `_extract_eval_invocation` directly)

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/ctx_stats.py` — imports `_aggregate_skill_stats` from `logs.py` (`main_ctx_stats()`, line 494); `_aggregate_skill_stats` internally flows through `_extract_tool_name` via the sequence pipeline. No code changes needed, but a behavioral smoke-test (`ll-ctx-stats`) after the refactor is advised to confirm the indirect call chain is intact.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_logs.py` (already in Affected Files) — import block (lines 16–32) must add `_InvocationSignal` and `_detect_ll_signal` to the `from little_loops.cli.logs import (...)` statement when new direct unit tests are written
- `scripts/tests/test_cli.py` — `TestMainLogsIntegration` exercises `main_logs()` subcommands including `sequences` and `scan-failures`; no changes needed (all flows through shims)

**New tests to write in `test_ll_logs.py`** (follow `TestFrozenDataclassConvention` pattern in `test_host_runner.py:666`):
- `TestDetectLlSignal.test_detect_ll_signal_queue_enqueue` — signal (a)/queue-enqueue path currently has no direct unit test; only covered via integration in `test_sequences_includes_queue_operations`
- `TestDetectLlSignal.test_detect_ll_signal_command_name_user_record` — signal (b) direct unit test
- `TestDetectLlSignal.test_detect_ll_signal_bash_tool_use` — signal (c) direct unit test
- `TestDetectLlSignal.test_detect_ll_signal_returns_none_for_unrelated` — None path
- `test_extract_tool_name_delegates_to_detect_ll_signal` — shim equivalence: same record, same result via both paths
- `test_extract_eval_invocation_delegates_to_detect_ll_signal` — shim equivalence: `runner`/`target`/`input_context` preserved through shim

## Verification Notes

2026-06-18 (ACCURATE): `_extract_tool_name` at line 290 and `_extract_eval_invocation` at line 1405 still exist as separate functions sharing the same three-signal detection logic. No `_detect_ll_signal` helper or `_InvocationSignal` dataclass exists. Duplication confirmed unfixed.

## Resolution

Introduced `_InvocationSignal` dataclass and `_detect_ll_signal()` as the single source of truth for JSONL record detection. `_extract_tool_name` and `_extract_eval_invocation` are now one-liner shims. Added `TestDetectLlSignal` with 8 tests covering all three signal paths, None path, and shim equivalence. All 143 tests pass; `ll-ctx-stats` smoke-test confirms indirect call chain intact.

## Session Log
- `/ll:manage-issue` - 2026-06-19T19:17:00Z - `implement`
- `/ll:ready-issue` - 2026-06-19T19:09:37 - `6e43b2e2-921c-4bb2-bc72-a192f4a47639.jsonl`
- `/ll:confidence-check` - 2026-06-19T00:00:00 - `5df30e7f-4681-4aea-b159-556acfbcfac7.jsonl`
- `/ll:wire-issue` - 2026-06-19T18:56:16 - `57af7f51-7ee7-4fd8-a81a-048290060aa9.jsonl`
- `/ll:format-issue` - 2026-06-14T01:58:22 - `98cfc879-7f76-4a33-b0d6-01898726102d.jsonl`
- `/ll:capture-issue` - 2026-06-14T01:52:17Z - `audit-session`
