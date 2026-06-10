---
id: ENH-2073
title: "FSM per-state model override for prompt and slash_command states"
type: ENH
priority: P3
status: open
captured_at: "2026-06-10T16:02:38Z"
discovered_date: "2026-06-10"
discovered_by: capture-issue
---

# ENH-2073: FSM per-state model override for prompt and slash_command states

## Summary

Add a `model:` field to individual FSM state definitions that overrides the host CLI's default model for that state's execution. The override applies only to non-bash states (`action_type: prompt` or `slash_command`); bash/shell states are unaffected.

## Motivation

Loop authors today can only set one model for the entire run (via `--model` CLI flag or host default). Some loops contain states with very different cost/quality profiles:

- A lightweight **triage** or **routing** state benefits from a fast, cheap model (e.g. Haiku).
- A **code generation** or **semantic evaluation** state needs a high-quality model (e.g. Sonnet or Opus).
- A **vision-based** scoring state already routes through `VISION_MODEL` env vars at the prompt level, but there's no first-class harness support for it.

Allowing per-state model overrides makes this cost/quality tradeoff explicit and portable, without requiring callers to splice `--model` into prompt text or manage env vars manually.

## Success Metrics

- `ll-loop validate` exits 0 on a loop YAML that uses per-state `model:` overrides
- Integration test confirms `--model <id>` is passed to the host runner for overridden states and absent for states without `model:`
- No regression in the existing loop test suite (`python -m pytest scripts/tests/`)

## Scope Boundaries

- **In scope**: `model:` field for `action_type: prompt` and `slash_command` states; schema validation WARNING for `model:` on shell/mcp_tool/contract states; JSON Schema update (`docs/reference/schemas/`); `LOOPS_GUIDE.md` state-definition reference table entry
- **Out of scope**: `shell`, `mcp_tool`, and `contract` states (host CLI not invoked — field is ignored with a WARNING, not blocked); global `--model` CLI flag behavior (unchanged); new CLI flags or config keys

## Proposed API

In a loop YAML state definition, add an optional `model:` key:

```yaml
states:
  triage:
    action: /ll:some-quick-check
    model: claude-haiku-4-5-20251001   # cheap routing state
    on_yes: generate
    on_no: done

  generate:
    action: /ll:generate-code
    # no model: key → inherits host default (or --model flag)
    on_success: evaluate

  evaluate:
    action: /ll:semantic-review
    model: claude-opus-4-8              # expensive but high-quality
    on_yes: done
    on_no: generate
```

The `model:` key is **ignored** for `action_type: shell`, `mcp_tool`, and `contract` states, since those don't invoke the host CLI. A validation warning should be emitted if `model:` is set on a shell state.

## Implementation Steps

### 1. Schema — `scripts/little_loops/fsm/schema.py`

- Add `model: str | None = None` to `StateConfig` dataclass (around line 416 where `action_type` lives).
- Update `StateConfig.to_dict()` to emit `model` when set.
- Update `StateConfig.from_dict()` to read `model` from raw data.

### 2. Executor — `scripts/little_loops/fsm/executor.py`

- In `_run_action()` (around line 1095–1105), when dispatching to `action_runner.run()` for `action_mode == "prompt"`, pass `model=state.model` alongside `agent` and `tools`.
- `ActionRunner.run()` in `runners.py` already accepts keyword args threaded through to `host_runner`; verify signature and add `model: str | None = None` if missing.
- `host_runner.build_streaming()` already emits `--model <value>` when `model` is set (line 288–289 in `host_runner.py`); no change needed there.

### 3. Validation — `scripts/little_loops/fsm/validation.py`

- Add a validation rule: if `state.model` is set and `_action_mode(state)` is not `"prompt"`, emit a `WARNING` with message: `"model: override is ignored for shell/mcp_tool/contract states"`.

### 4. Schema doc / YAML schema

- Add `model` to the JSON Schema for state definitions in `docs/reference/schemas/` (regenerate via `ll-generate-schemas`).
- Document the field in `docs/guides/LOOPS_GUIDE.md` under the state-definition reference table.

### 5. Tests

- Unit test: `StateConfig.from_dict` round-trips `model` field.
- Integration test: a loop YAML with `model: claude-haiku-4-5-20251001` on one state causes `--model claude-haiku-4-5-20251001` to be passed to the host runner for that state and not for others.
- Validation test: `model:` on a shell state emits WARNING.

## Root Cause

`StateConfig` (schema.py) and `executor._run_action()` have no mechanism to thread a per-state model through to the `action_runner.run()` call. The host runner already supports `--model`; it's purely a missing data-flow connection from YAML → schema → executor → runner.

## API / Interface Changes

- **YAML loop files**: new optional `model:` key at state level (non-breaking; absent = existing behaviour).
- **`StateConfig` dataclass**: new `model: str | None` field.
- **`ActionRunner.run()`**: may need `model: str | None = None` keyword arg depending on current signature.
- No CLI changes required.

## Acceptance Criteria

- [ ] A loop YAML with `model: <id>` on a prompt state invokes the host CLI with `--model <id>` for that state only.
- [ ] States without `model:` continue using the default/flag-provided model.
- [ ] Shell/mcp_tool/contract states with `model:` emit a validation WARNING (not ERROR) and run normally.
- [ ] `ll-loop validate` passes on a loop using per-state `model:` overrides.
- [ ] Existing loops without `model:` are unaffected (backwards-compatible).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | FSM executor and runner design |
| [docs/reference/API.md](../../docs/reference/API.md) | `host_runner` API — `build_streaming` model param |
| [docs/guides/LOOPS_GUIDE.md](../../docs/guides/LOOPS_GUIDE.md) | State definition reference |

## Session Log
- `/ll:format-issue` - 2026-06-10T16:07:29 - `44235a11-96b5-42bf-a8ef-bffe384cdaf0.jsonl`
- `/ll:capture-issue` - 2026-06-10T16:02:38Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dae493a0-2705-496d-9f16-5c7e9a05de45.jsonl`

---
## Status

**Current**: open
