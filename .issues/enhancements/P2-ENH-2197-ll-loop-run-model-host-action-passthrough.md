---
id: ENH-2197
type: ENH
priority: P2
status: open
captured_at: 2026-06-16T18:21:36Z
discovered_date: 2026-06-16
discovered_by: scope-epic
parent: EPIC-2196
labels: [hermes, cli, loop, model]
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

## Acceptance Criteria

- `ll-loop run <loop> --model <id>` causes every host-CLI action state without an
  explicit `model:` to be invoked with `--model <id>` (verified via host
  invocation assertion in `fsm/runners.py`).
- A state's own `StateConfig.model` continues to take precedence over the
  run-level `--model` (per-state override wins).
- `--model` and `--llm-model` are independent; setting one does not affect the other.
- Help text clearly distinguishes `--model` (host action model) from
  `--llm-model` (evaluator/judge model).

## Notes

- Wiring points: `scripts/little_loops/cli/loop/run.py` (arg + plumb to executor),
  `scripts/little_loops/fsm/runners.py` (host-action `--model` passthrough already
  supports a `model` param in prompt-mode — thread the run-level default through).
- Confirm interaction with `--host`/`resolve_host()`; the flag must work across hosts.
