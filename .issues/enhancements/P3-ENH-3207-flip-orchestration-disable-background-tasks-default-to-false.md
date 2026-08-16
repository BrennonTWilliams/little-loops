---
id: ENH-3207
type: ENH
title: Flip orchestration.disable_background_tasks default to false (background tasks
  allowed unless opted in)
priority: P3
status: done
testable: true
decision_needed: false
discovered_by: user-request
discovered_date: '2026-08-15'
captured_at: '2026-08-16T01:56:52Z'
completed_at: '2026-08-16T01:56:52Z'
supersedes: []
---

# ENH-3207: Flip `orchestration.disable_background_tasks` default to `false`

## Summary

`orchestration.disable_background_tasks` (FEAT-3078/FEAT-3060) shipped **on by default**:
any Claude Code child spawned with `automation_profile` set (`ll-auto`, FSM loops) got
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` injected into its environment, hard-disabling
tool-level background tasks (`Bash run_in_background: true`) in that child.

Per user direction (2026-08-15), the flag is now **opt-in**: the default flips `true →
false`, and this repo's `.ll/ll-config.json` sets it to `false` explicitly. The mechanism
is unchanged — only which way it points when nobody has said otherwise.

## Current Behavior

Before this change, the `true` default lived in three places that all had to agree:

- `scripts/little_loops/config-schema.json` — `orchestration.disable_background_tasks`,
  `"default": true`
- `OrchestrationConfig.disable_background_tasks` field default (`config/orchestration.py`)
- `OrchestrationConfig.from_dict()`'s `data.get(..., True)` fallback

Every *function-level* default in the call chain was already `False`
(`host_runner.py`, `issue_manager.py`, `subprocess_utils.py`, `fsm/runners.py`,
`parallel/worker_pool.py`); `True` only ever entered via config, at the
`config.orchestration.disable_background_tasks` call sites in `issue_manager.py` and
`fsm/executor.py`. So config was the single source of the on-by-default behavior.

Consequence of the old default: an `ll-auto` / FSM-loop child could not use tool-level
backgrounding at all, including a `project.run_cmd` smoke-test step that relied on it.

## Expected Behavior

- With no `orchestration.disable_background_tasks` key present, background tasks are
  **allowed** — the env var is not set to `1`.
- Setting `orchestration.disable_background_tasks: true` restores the FEAT-3078
  hard-disable.
- Scope is unchanged: Claude-Code-only (the other six runners `del` the parameter as a
  no-op), gated on `automation_profile is not None`, and shell-level `&` backgrounding
  remains outside the flag's reach.

## Motivation

Direct user decision. The original rationale for on-by-default was that a parent session
ending before it retrieved a background task's result could silently discard completed
work. That failure mode still exists and the flag still addresses it — but it is now the
user's call to opt in, rather than a capability removed from every automation run by
default.

## Proposed Solution

Flip the default in the three config-owning locations, update the docs that state the
default in prose, and invert the tests that pinned `True` (keeping both directions
covered rather than deleting the explicit-value cases).

## Program Design

No new code paths, no new symbols — the change is a value flip in the three places that
own the config default, plus the prose and tests that assert it. The injection mechanism
(`ClaudeCodeRunner.build_streaming()`) is untouched.

The default lives in exactly three config-owning locations, which must stay in agreement:

- `config-schema.json` → `orchestration.properties.disable_background_tasks.default` — the
  value `schema_default()` hands to `ll-init`, and the `$schema` contract editors surface.
- `OrchestrationConfig.disable_background_tasks` — the dataclass field default, used when
  the section is constructed without data.
- `OrchestrationConfig.from_dict(data)` — the `data.get("disable_background_tasks", ...)`
  fallback, used when a config file exists but omits the key.

Flipping only a subset reproduces exactly the class of divergence BUG-3192 was filed to
fix (schema-vs-dataclass split behaving differently by install path), so all three move
together in this pass. `TestSchemaValueParity` (added by BUG-3192) is the standing guard
against a future partial flip.

Two consumers read the resolved value and are left alone, because they already pass
whatever config resolves to rather than hardcoding a default:

- `issue_manager.py` — five call sites forwarding
  `config.orchestration.disable_background_tasks`.
- `fsm/executor.py` — the `_get_br_config().orchestration.disable_background_tasks` gate
  that conditionally adds the kwarg.

Every function-level default in the chain is already `False`, so after this flip the
"nobody configured anything" path is uniformly `False` end to end.

### Types

- `OrchestrationConfig` — the `orchestration` config section dataclass; owns the field
  default and the `from_dict` fallback being flipped
- `BRConfig` — resolves `.ll/ll-config.json` into section dataclasses and exposes
  `.orchestration`; its `to_dict()` re-emits the resolved value
- `HostInvocation` — carries `binary`/`args`/`env`; the env dict is where
  `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` is set

### Signatures

- `OrchestrationConfig.from_dict(data: dict[str, Any]) -> OrchestrationConfig` — the
  `data.get("disable_background_tasks", False)` fallback lives here; one of the three
  values changed
- `ClaudeCodeRunner.build_streaming(..., automation_profile=None, disable_background_tasks: bool = False) -> HostInvocation` — sets the env var to `"1"` when both the flag and `automation_profile` are set, and to `""` otherwise; unchanged by this issue
- `resolve_host() -> HostRunner` — the mandated entry point for host CLI invocation; the
  runner it returns is what receives the flag

### Call Path

`.ll/ll-config.json` -> `BRConfig` -> `OrchestrationConfig.from_dict`
(`config/orchestration.py:97`) -> `config.orchestration.disable_background_tasks` read by
`issue_manager.py:859` and `fsm/executor.py:2210` -> forwarded as a kwarg through
`run_claude_command` -> `resolve_host()` -> `ClaudeCodeRunner.build_streaming`
(`host_runner.py:374`) -> `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` in the child env

## Scope Boundaries

This issue flips one config default and syncs the assertions and prose that pinned the old
value. Out of scope:

- The FEAT-3078 mechanism itself — env-var name, the `automation_profile is not None`
  gate, Claude-Code-only applicability, and the six no-op runners are all unchanged.
- Shell-level backgrounding (a trailing `&`), which this flag never reached in either
  direction.
- The related-but-separate `pruning_profile:` env surface that shares the same gate.
- A CHANGELOG entry for the reversal — belongs to release prep.

## Acceptance Criteria

- [x] `config-schema.json` declares `"default": false` for
      `orchestration.disable_background_tasks` (asserted by
      `test_orchestration_disable_background_tasks_in_schema`).
- [x] `OrchestrationConfig` field default and `from_dict()` fallback are both `False`
      (asserted by `test_from_dict_disable_background_tasks_defaults_false`).
- [x] `BRConfig` with no key present resolves `False`; with an explicit `true` resolves
      `True` (asserted by the `TestBRConfigOrchestration` pair).
- [x] `BRConfig.to_dict()` emits `False` for the key when absent from config
      (asserted in `test_config.py`'s `to_dict` orchestration test).
- [x] This repo's `.ll/ll-config.json` sets `"disable_background_tasks": false` under
      `orchestration`.
- [x] No doc still states the default as `true`.
- [x] Affected test suites pass; changed files are lint/format/type clean.

## Integration Map

Files changed:

| File | Change |
| --- | --- |
| `.ll/ll-config.json` | added `"disable_background_tasks": false` to `orchestration` |
| `scripts/little_loops/config-schema.json` | `default: true → false`; description reworded to opt-in framing |
| `scripts/little_loops/config/orchestration.py` | field default and `from_dict()` fallback `True → False` |
| `scripts/little_loops/fsm/schema.py` | `PruningProfileConfig` docstring: "default ``True``" → "default ``False``" |
| `scripts/tests/test_config_schema.py` | schema-default assertion + docstring |
| `scripts/tests/test_config.py` | `to_dict` default; `from_dict` default/explicit pair; `BRConfig` file/absent pair (renamed `*_defaults_true` → `*_defaults_false`, explicit-value cases inverted so both directions stay covered) |
| `docs/ARCHITECTURE.md` | env-var table row: default `true` → `false` |
| `docs/guides/LOOPS_GUIDE.md` | default `true` → `false`; closing sentence reframed as opt-in |
| `docs/reference/CONFIGURATION.md` | table default cell `true` → `false`; "Behavior change on upgrade" paragraph (written for the original rollout) rewritten as an opt-in caveat |
| `docs/reference/HOST_COMPATIBILITY.md` | `[^bgtasks]` footnote: "is `true` (default)" → "is `true` (opt-in; default `false`)" |
| `docs/reference/API.md` | `ActionRunner` kwarg note: "(the default)" → "(opt-in; default `false`)" |

Deliberately **not** changed:

- Function-level `disable_background_tasks: bool = False` defaults throughout the call
  chain — already `False`, and now consistent with config.
- `CHANGELOG.md:85`, which describes the FEAT-3078 rollout as it shipped (historical
  entry). A new CHANGELOG line for this reversal belongs in release prep, not here.
- No `ll-init` template writes this key, so no template needed updating.

## Impact

Behavior change for anyone on the default: `ll-auto` and FSM-loop children regain
tool-level backgrounding. Projects that want the FEAT-3078 hard-disable must now set the
flag explicitly. Because all little-loops projects on this machine are `local-editable`
against this checkout, the new default is live in them immediately with no reinstall.

## Resolution

Implemented as described in Integration Map. Verification:

- `python -m pytest scripts/tests/test_config.py scripts/tests/test_config_schema.py
  scripts/tests/test_host_runner.py scripts/tests/test_fsm_executor.py
  scripts/tests/test_issue_manager.py` → **1228 passed, 11 skipped** (197s).
  The full `scripts/tests/` suite was **not** run in this session; scope was the five
  suites covering config, schema, host runner, FSM executor, and issue manager.
- `ruff check` + `ruff format --check` clean on the four changed Python files;
  `mypy` clean on the two changed source modules; both changed JSON files parse.
- Runtime spot-check: `BRConfig(Path('.')).orchestration.disable_background_tasks`
  → `False`.

## Status

**Done** | Created: 2026-08-15 | Priority: P3

## Session Log
- `hook:posttooluse-status-done` - 2026-08-16T01:57:34 - `4bfcbdbe-c87a-443d-aab4-9af6bf2f5a34.jsonl`
- ad-hoc session (no skill) - 2026-08-16T01:56:52 - config default flip + doc/test sync
