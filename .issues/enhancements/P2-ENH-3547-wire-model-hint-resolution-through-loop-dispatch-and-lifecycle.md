---
id: ENH-3547
type: ENH
title: Wire model hint resolution through loop dispatch and lifecycle
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:15Z'
labels:
- multi-host
- loops
blocked_by:
- ENH-3527
relates_to:
- ENH-3533
---

# ENH-3547: Wire model hint resolution through loop dispatch and lifecycle

## Summary

Wire `model_hint` resolution into every loop dispatch path: CLI actions, blocking evaluators, SDK/batch, and CLI downgrade. Preserve requested declarations through sub-loops, detach and resume, and add selection diagnostics to FSM events. This is piece 2 of ENH-3527's delivery split; ENH-3527 keeps piece 1 (declarations, resolver and config) and is the prerequisite.

## Current Behavior

- After ENH-3527, `model_hint` declarations parse and validate, but `FSMExecutor` fails fast with a not-yet-supported error before dispatch.
- CLI actions use `state.model or self.run_model` (`executor.py:2658`); evaluators use `state.model or self.fsm.llm.model` (`executor.py:3174,3221`); SDK/batch use `state.model or self.run_model or self.fsm.llm.model` (`executor.py:3570`).

## Expected Behavior

Everything below is specified in ENH-3527 (Design → Declaration and precedence, Resolve against the effective backend, Supported artifact/host matrix, Lifecycle and model identity, Call Path). ENH-3527 remains the authoritative design; this issue owns delivering it:

- Resolve after `FSMExecutor._resolve_request_path`. SDK/batch always resolves against `anthropic-api`; a downgrade to CLI re-resolves the original declaration for that runner.
- Evaluator hints are resolved in `FSMExecutor._evaluate` and passed down as `model: str`; no config is threaded into `evaluators.py`.
- Each dispatch adds `model_requested`, `model_resolved`, `model_backend` and `model_operation` to its event payload and the run header. No DB columns; observed model identity stays separate.

## Scope Boundaries

- **In scope**: dispatch wiring on every loop path, CLI downgrade re-resolution, lifecycle preservation, event/header diagnostics, portability proof, removing ENH-3527's not-yet-supported guard.
- **Out of scope**: validate warnings and docs (ENH-3548); skill/agent frontmatter (ENH-3533).

## Program Design

### Types

- Uses ENH-3527's model declaration and resolved-selection types; no new types.

### Signatures

- `resolve_model_hint(hint, *, backend, operation, overrides=None) -> str` — from ENH-3527, called at each dispatch seam.
- Evaluator functions keep `model: str`.

### Call Path

- `FSMExecutor._resolve_request_path` → `resolve_model_hint` → `build_anthropic_request` (SDK/batch)
- `FSMExecutor._resolve_request_path` → `resolve_model_hint` → `ClaudeCodeRunner.build_streaming` / `CodexRunner.build_streaming` (CLI actions)
- `FSMExecutor._evaluate` → `resolve_model_hint` → `evaluate_llm_structured` → `build_blocking_json`

## Integration Map

- `scripts/little_loops/fsm/{executor,evaluators,runners,persistence}.py`, `subprocess_utils.py`, `cli/loop/{run,lifecycle,runner,header,info}.py`.
- Tests: `test_fsm_executor.py`, `test_fsm_evaluators.py`, `test_fsm_runners.py`, `test_ll_loop_execution.py`, `test_host_runner_dispatch.py`, `test_fake_host.py`.

## Impact

- **Priority**: P2.
- **Effort**: Medium.
- **Risk**: Medium — a precedence or backend mismatch silently selects the wrong model.

## Acceptance Criteria

These carry over from ENH-3527 (its criteria 3, 4, 5, 7 and 12):

- [ ] Tests cover every precedence row; no-hint behavior and literal CLI argv are unchanged.
- [ ] CLI action, blocking evaluator, SDK and batch paths share declaration semantics; a foreign configured CLI host never supplies an Anthropic request model; downgrade re-resolves.
- [ ] Every advertised host/operation combination has a dispatch-level argv test, including Codex streaming; opencode/pi and missing/disabled mappings error explicitly.
- [ ] Sub-loop/detach/resume preserve requested declarations; event payloads carry the four selection fields.
- [ ] Portability proof: a fixture loop with `coding`/`burst` states runs unedited under fake host / `claude-code` and `anthropic-api`.

## Status

**Open** | Created: 2026-09-24 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue covers runtime dispatch, CLI downgrade re-resolution, and lifecycle wiring only; the resolver and config slice is ENH-3527 and validate-time warnings/docs are ENH-3548. The `operation` parameter in `resolve_model_hint(hint, *, backend, operation, ...)` and the `model_operation` event field depend on ENH-3527 keeping `operation` — reconcile if ENH-3527 drops it.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:56 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
