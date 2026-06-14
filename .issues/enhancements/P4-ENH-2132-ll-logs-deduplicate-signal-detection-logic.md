---
id: ENH-2132
type: ENH
priority: P4
status: open
title: Deduplicate ll-logs signal detection logic (_extract_tool_name / _extract_eval_invocation)
discovered_date: 2026-06-14
discovered_by: capture-issue
captured_at: "2026-06-14T01:52:17Z"
---

# ENH-2132: Deduplicate ll-logs signal detection logic (_extract_tool_name / _extract_eval_invocation)

## Summary

`_extract_tool_name()` (lines 290–348) and `_extract_eval_invocation()` (lines 1405–1466) in `cli/logs.py` implement the same three-signal JSONL record detection:

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

## Affected Files

- `scripts/little_loops/cli/logs.py` (lines 290–348 and 1405–1466)
- `scripts/tests/test_ll_logs.py` (tests that call `_extract_tool_name` or `_extract_eval_invocation` directly)

## Session Log
- `/ll:format-issue` - 2026-06-14T01:58:22 - `98cfc879-7f76-4a33-b0d6-01898726102d.jsonl`
- `/ll:capture-issue` - 2026-06-14T01:52:17Z - `audit-session`
