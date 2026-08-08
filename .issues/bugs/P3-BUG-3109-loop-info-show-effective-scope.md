---
id: BUG-3109
type: BUG
title: '`cli/loop/info.py` should show the effective scope (including the `["."]`
  fallback), not just declared `scope:`'
priority: P4
status: open
parent: BUG-3088
captured_at: '2026-08-08T00:00:00Z'
discovered_date: 2026-08-08
discovered_by: issue-size-review
labels:
- fsm-concurrency
- loop-authoring
relates_to:
- BUG-3088
confidence_score: 100
outcome_confidence: 95
score_complexity: 25
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3109: `cli/loop/info.py` should show the effective scope, not just declared `scope:`

## Summary

Optional/splittable deliverable from [BUG-3088](P3-BUG-3088-audit-unscoped-loops-and-warn-on-missing-scope.md).
`cmd_info`'s loop-detail display only prints a `scope:` line when `fsm.scope`
is truthy (`cli/loop/info.py:1540-1541`: `if fsm.scope:
config_parts.append(...)`), so an unscoped loop is shown as having no scope
even though it locks the repo root at runtime via the `["."]` fallback.
This is a real visibility gap but is independent of both of BUG-3088's
deliverables — the issue explicitly calls it out as "optional" and says not
to let it hold up the audit ([[BUG-3106]]).

## Current Behavior

`ll-loop show <name>` (`cmd_show()` in `cli/loop/info.py:1540-1541`) only
appends a `scope: ...` entry to the config-header line when `fsm.scope` is
truthy:

```python
if fsm.scope:
    config_parts.append(f"scope: {', '.join(fsm.scope)}")
```

For a loop with no declared `scope:` field, this branch is skipped and the
header line omits any mention of scope entirely — even though the loop still
acquires a concurrency lock on the repo root (`["."]`) at run time.

## Expected Behavior

`ll-loop show <name>` should always display the *effective* scope — the
declared `fsm.scope` if present, or the resolved `["."]` fallback otherwise
— with a clear marker (e.g. `scope: . (default)`) distinguishing an implicit
fallback from an explicit declaration, so the header accurately reflects the
runtime lock behavior in both cases.

## Steps to Reproduce

1. Create or select a loop YAML with no `scope:` field declared.
2. Run `ll-loop show <loop-name>`.
3. Observe: the printed config-header line contains no `scope:` entry,
   giving no indication that the loop still locks the repo root via the
   `["."]` fallback at run time (see `fsm/concurrency.py:162-164`).

## Parent Issue

Decomposed from [BUG-3088](P3-BUG-3088-audit-unscoped-loops-and-warn-on-missing-scope.md):
Audit unscoped loops and warn at validate time when `scope:` is missing.

## Proposed Solution

Update `cli/loop/info.py`'s loop-detail display (around lines 1540-1541) to
show the *effective* scope — `fsm.scope` if declared, or the `["."]`
fallback value with an indication that it's a default, not an explicit
declaration — so `ll-loop show` reflects the actual runtime lock behavior
rather than only the presence/absence of the declared field.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `cmd_show()`, lines 1540-1541: update the `if fsm.scope:` guard so it computes the effective scope and labels the fallback case.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/concurrency.py:35` — defines `resolve_scope(scope: list[str], context: dict[str, Any]) -> list[str]`, the function that resolves `${context.<var>}` templates in scope paths; not currently imported by `info.py`.
- `scripts/little_loops/fsm/concurrency.py:162-164` — `LockManager.acquire()` applies the same `["."]` fallback as a second, independent safety net at lock-acquisition time (not template-aware, just an empty-list check).
- `scripts/little_loops/cli/loop/run.py:373` — the only existing call site of `resolve_scope`, showing the established call shape: `resolve_scope(fsm.scope or ["."], fsm.context)`.

### Conventions in Force
- Effective scope is computed once, via `resolve_scope`, immediately before it is needed (`run.py:373` computes it right before `lock_manager.acquire()`) — evidence this is a call-time computation, not a value stored on the FSM object itself. `cmd_show` would follow the same shape rather than reading a precomputed field.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/testing.py:118-137` — established precedent for the exact "effective value with default marker" shape this issue proposes: when no `evaluate:` is declared, the code falls back to `evaluate_exit_code(...)` and sets `evaluator_type = "exit_code (default)"`, then prints `f"Evaluator: {evaluator_type}"`. The `" (default)"` suffix convention (not a separate flag/field) is the pattern to mirror for `scope: . (default)`. [codebase-pattern-finder finding]

### Tests
- `scripts/tests/test_ll_loop_commands.py` — existing `cmd_show` coverage (e.g. `test_show_diagrams_and_json_mutually_exclusive`, `test_diagram_output_contains_box_chars`) uses a `_setup_loop(tmp_path)` helper to write a loop YAML and a `capsys`-based assertion on `cmd_show(...)` stdout; the new test should follow this same shape (write a loop YAML with/without `scope:`, call `cmd_show`, assert on the captured header line) rather than introducing a new test scaffold.
- No existing test currently asserts on the `config_parts` scope line specifically — it is untested today.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_validation_structural.py:1597+` (BUG-3107's `_validate_missing_scope` tests) — established three-case coverage matrix to mirror: (a) no/empty `scope:` → fallback case, (b) explicit `scope: ["."]` → explicit repo-wide opt-in, (c) explicit named path (e.g. `scope: ["src/"]`) → declared case. The new `cmd_show` test should cover the same three cases: (a) asserts the `(default)` marker appears, (b) and (c) assert it does not. [codebase-pattern-finder finding]
- Confirmed via independent trace: no test in `test_ll_loop_commands.py`, `test_ll_loop_display.py`, `test_cli_loop_layout.py`, or `test_loop_show_overview.py` asserts on the `cmd_show` config-header line's exact content — all existing assertions are loose substring checks (e.g. `"my-loop" in out`) or target unrelated diagram-facet `scope` (the `diagram_scope` kwarg, a same-named-but-unrelated concept). The scope-line change is purely additive from a test-breakage standpoint. [codebase-locator + codebase-pattern-finder findings]

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Signatures
- `resolve_scope(scope: list[str], context: dict[str, Any]) -> list[str]` — existing function at `scripts/little_loops/fsm/concurrency.py:35`; resolves `${context.<var>}` templates in each scope path and passes static paths through unchanged. Unknown-variable templates are left as the literal string (not an error).

### Call Path
`cmd_show()` (`cli/loop/info.py:1540`, has `fsm.scope` and `fsm.context` already in local scope) -> `resolve_scope(fsm.scope or ["."], fsm.context)` (`fsm/concurrency.py:35`) -> effective scope list used to build the `config_parts` display line, distinguishing the declared-`scope:` case from the `["."]` fallback case (e.g. by only appending the "(default)" qualifier when `fsm.scope` was falsy).

### Decision Rules
N/A — no new decision logic; this is a display-formatting change over an existing, already-defined resolution function.

## Implementation Steps

1. Update `cli/loop/info.py:1540-1541` to always show the effective scope,
   distinguishing declared `scope:` from the `["."]` fallback.
2. Add test coverage asserting on the new display output for both a scoped
   and an unscoped loop.

## Impact

- **Severity**: low — display-only, no behavior change. Improves
  discoverability of the existing fallback behavior.
- **Blast radius**: single-file display change plus one test.

## Status

open


## Session Log
- `/ll:confidence-check` - 2026-08-08T18:48:39 - `1b4ff01b-24fc-4de9-98e5-949ef8d76b00.jsonl`
- `/ll:wire-issue` - 2026-08-08T17:50:42 - `2f6d65a1-cd0b-4c54-a567-95d199d69f4e.jsonl`
- `/ll:format-issue` - 2026-08-08T17:35:07 - `293687b4-b50e-40d1-8c8a-ec8456bd972c.jsonl`
- `/ll:refine-issue` - 2026-08-08T17:29:23 - `0746a600-67e0-4eeb-88c7-015609fa694e.jsonl`
- `/ll:issue-size-review` - 2026-08-08T12:31:14 - `252cabd4-42b7-43f3-becc-2330b53bf3d0.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Anchor**: `cmd_show()`, lines 1540-1541 (`if fsm.scope: config_parts.append(f"scope: {', '.join(fsm.scope)}")`)
- **Cause**: The config-header line is gated purely on `fsm.scope` truthiness, so an FSM with no declared `scope:` contributes nothing to `config_parts` and the header omits any scope indication. Meanwhile the actual runtime lock behavior resolves the effective scope in two places that `cmd_show` never consults: `cli/loop/run.py:373` computes `scope = resolve_scope(fsm.scope or ["."], fsm.context)` before acquiring the lock, and `fsm/concurrency.py:162-164` (`LockManager.acquire`) independently re-applies the same `if not scope: scope = ["."]` fallback as a safety net. `cmd_show` has `fsm.context` already in scope one line earlier (line 1538, used for the `context: ...` header field), so it has everything `resolve_scope` needs but never calls it.
