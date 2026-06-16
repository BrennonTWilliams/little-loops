---
id: ENH-2197
type: ENH
priority: P2
status: done
captured_at: 2026-06-16 18:21:36+00:00
discovered_date: 2026-06-16
discovered_by: scope-epic
parent: EPIC-2196
labels:
- hermes
- cli
- loop
- model
---

# Add `ll-loop run --model` host-action passthrough flag

## Summary

Add a run-level `ll-loop run --model <id>` flag that propagates the model to the
host-CLI **action** invocations (prompt/slash-command states), as a default for
any state that does not set its own `StateConfig.model`. This is distinct from
the existing `--llm-model`, which only overrides the FSM evaluator/judge model
(`fsm.llm.model`) and does not affect host-CLI actions. Keystone enablement for
the Hermes `ll_route` tool, which passes a per-project `--model` preference from
the PM persona. Source: `PRD-Hermes-Integration-v4.md` (EG-1).

## Current Behavior

`ll-loop run` accepts `--llm-model` to override the FSM evaluator/judge model, but
provides no flag to set the model for host-CLI **action** invocations
(prompt/slash-command states). Each state must hard-code `model:` in its
`StateConfig` or accept whatever host default applies; there is no run-level
override available.

## Expected Behavior

`ll-loop run <loop> --model <id>` propagates the specified model to every host-CLI
action state that does not declare its own `StateConfig.model`. Per-state `model:`
values continue to take precedence (override wins). The new `--model` flag is
orthogonal to `--llm-model`; both can be set independently.

## Motivation

This enhancement enables:
- **Hermes integration** (`PRD-Hermes-Integration-v4.md` EG-1): the `ll_route` tool
  passes a per-project model preference at invocation time; without this flag the
  preference cannot reach host-action states.
- **Run-level model selection**: operators can test loops against different models
  without editing individual state YAML.
- Minimal-footprint change — threads an existing `model` param already present in
  prompt-mode runners through the CLI arg surface.

## Acceptance Criteria

- `ll-loop run <loop> --model <id>` causes every host-CLI action state without an
  explicit `model:` to be invoked with `--model <id>` (verified via host
  invocation assertion in `fsm/runners.py`).
- A state's own `StateConfig.model` continues to take precedence over the
  run-level `--model` (per-state override wins).
- `--model` and `--llm-model` are independent; setting one does not affect the other.
- Help text clearly distinguishes `--model` (host action model) from
  `--llm-model` (evaluator/judge model).

## Scope Boundaries

- **In scope**: `ll-loop run --model <id>` flag; per-state `StateConfig.model`
  override precedence; `--model` / `--llm-model` independence; help-text
  disambiguation.
- **Out of scope**: Changing how `--llm-model` works; per-state model selection UI;
  model validation against a known model registry; propagation to non-host-action
  states (e.g., `shell` states).

## API/Interface

```bash
# New CLI flag for ll-loop run
ll-loop run <loop> [--model <model-id>] [--llm-model <model-id>]

# --model       Sets default model for host-CLI action states (prompt/slash-command)
# --llm-model   Sets model for FSM evaluator/judge (existing, unchanged)
```

Thread-through in `scripts/little_loops/fsm/runners.py`:
- Prompt-mode runner already accepts a `model` param → thread `run_model` default
  from executor context when `StateConfig.model` is absent.

## Implementation Steps

1. Add `--model` CLI arg to `scripts/little_loops/cli/loop/run.py` and plumb it
   into the executor context (parallel to `--llm-model` / `fsm.llm.model`).
2. In `scripts/little_loops/fsm/runners.py`, use the run-level model default for
   host-action `--model` passthrough when `StateConfig.model` is not set.
3. Verify `--model` and `--llm-model` remain independent (setting one does not
   affect the other).
4. Confirm interaction with `--host`/`resolve_host()`; flag must work across all
   supported hosts.
5. Add host invocation assertion tests for `--model` propagation; update help text.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py` — add `--model` arg; plumb to executor
- `scripts/little_loops/fsm/runners.py` — thread run-level model default into
  host-action `--model` passthrough

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — carries run context; may need a new
  `run_model` field alongside existing `llm_model`
- `scripts/little_loops/host_runner.py` — `resolve_host()` / `HostInvocation`
  must remain compatible

### Similar Patterns
- `--llm-model` flag in `run.py` — parallel structure for the new `--model` flag

### Tests
- `scripts/tests/test_builtin_loops.py` — add host invocation assertion verifying
  `--model` propagation
- Integration tests for `--model` / `--llm-model` independence

### Documentation
- Help text in `run.py` must clearly distinguish `--model` from `--llm-model`

### Configuration
- N/A

## Impact

- **Priority**: P2 — Keystone for Hermes integration enablement (EPIC-2196); blocks
  `ll_route` model-routing capability.
- **Effort**: Small — additive flag; prompt-mode runners already accept a `model`
  param so the passthrough wiring is largely pre-built.
- **Risk**: Low — additive change; states without explicit `model:` fall back to
  host default (no behavior change for existing loops).
- **Breaking Change**: No

## Notes

- Wiring points: `scripts/little_loops/cli/loop/run.py` (arg + plumb to executor),
  `scripts/little_loops/fsm/runners.py` (host-action `--model` passthrough already
  supports a `model` param in prompt-mode — thread the run-level default through).
- Confirm interaction with `--host`/`resolve_host()`; the flag must work across hosts.

---

**Open** | Created: 2026-06-16 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-06-16T18:28:34 - `9ff04939-9a13-469c-9a20-2c716aee28cd.jsonl`
