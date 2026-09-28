---
id: ENH-3548
type: ENH
title: Validate-time model hint warnings and hint documentation
priority: P3
status: open
parent: EPIC-3563
epic: EPIC-3563
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:15Z'
labels:
- multi-host
- loops
---

# ENH-3548: Validate-time model hint warnings and hint documentation

## Summary

Add `ll-loop validate` warnings for model hints that will not resolve, and document the hint vocabulary, support matrix and precedence. This is piece 3 of ENH-3527's delivery split (its criteria 8 and 10); design details are in ENH-3527 → Config override.

## Current Behavior

- `ll-loop validate` checks `model_hint` vocabulary and exclusivity (ENH-3527) but does not check whether a hint resolves for the configured host.
- No docs describe the hint vocabulary, support matrix or precedence.

## Expected Behavior

- For each declared hint, `ll-loop validate` resolves it against the configured host (`orchestration.host_cli` / `LL_HOST_CLI`) and emits a WARNING, not an error, for any hint that cannot resolve on a reachable request path. For a prompt action, the reachable paths are the state's `request_path` if set, else `orchestration.request_path`, plus the CLI fallback for SDK/batch.
- An evaluator hint (explicit `evaluate:` or the implicit `llm_structured` verdict on a prompt state) is checked against the CLI host only. `fsm/evaluators.py` has no SDK path, so a shell action + `llm_structured` state with `request_path: sdk` must not warn about `anthropic-api`.
- States that always downgrade to CLI (a `/ll:` skill action per `_SKILL_INVOKE_RE`, or `tools:` per BUG-2831) are checked for CLI only.
- When no host or `model_hints` is supplied to validation (the in-process callers below), resolution warnings are skipped. Vocabulary and exclusivity errors from ENH-3527 still fire.
- `haiku-gen` guidance covers hint-only `burst` generation without rejecting valid `burst` verdict states.

## Scope Boundaries

- **In scope**: validate-time WARNINGs, `haiku-gen` guidance, documentation.
- **Out of scope**: runtime dispatch (ENH-3547); new vocabulary; `cli/doctor.py`'s fleet-wide `load_and_validate` sweep (deferred — see Call Path).

## Program Design

### Types

- No new types.

### Signatures

- `resolve_model_hint(hint, *, backend, overrides=None) -> str` — from ENH-3527; validation catches its error and emits a WARNING.
- `validate_fsm(fsm: FSMLoop, orchestration_request_path: str | None = None, *, host_cli: str | None = None, model_hints: dict[str, dict[str, str | Literal[False]]] | None = None) -> list[ValidationError]` — extends the existing signature (`structural_rules.py:1169`, drifts with the file — confirm at implementation time) with the two keyword args; `host_cli=None` skips resolution warnings.
- `load_and_validate(...)` — gains the same two keyword args and forwards them, mirroring how `orchestration_request_path` is threaded today.
- `cli/logs.py`'s `_validate_builtin_loop(...)` helper (`logs.py:2326`) — the fleet-review call site at `logs.py:2761` does not call `load_and_validate` directly; it goes through this wrapper. The wrapper's own signature must also gain `host_cli`/`model_hints` and forward them to its `load_and_validate` call, or the two new kwargs stop at the wrapper boundary.

### Call Path

- `ll-loop validate` (`cli/loop/config_cmds.py:25`) → `load_and_validate(..., orchestration_request_path=, host_cli=, model_hints=)` → `validate_fsm` → structural rules → `resolve_model_hint` (per reachable request path) → WARNING
- `host_cli` comes from the host `resolve_host()` would select (`LL_HOST_CLI` / `orchestration.host_cli` / probe order). `model_hints` comes from `BRConfig(...).orchestration.model_hints`. Both are read at the same site that reads `.orchestration.request_path` today.
- `cli/logs.py:2761` (fleet-review) → `_validate_builtin_loop` (`logs.py:2326`, gains the same two kwargs) → `load_and_validate(..., host_cli=, model_hints=)`. In-process callers `cli/loop/scaffold_eval.py:278` and `scaffold_verify.py:340` stay unchanged and skip resolution warnings.
- Other `load_and_validate` callers (`cli/doctor.py:688`'s fleet-wide validate, `cli/loop/run.py:146`, `cli/loop/info.py:1472`, `cli/loop/edit_routes.py:51`, `fsm/loop_paths.py:104,128`, `fsm/executor.py:1163`) are **not** touched by this issue; they keep calling without `host_cli`/`model_hints`, so `host_cli=None`'s default skips resolution warnings there and behavior is unchanged. `cli/doctor.py` in particular validates every runnable built-in loop and is a plausible second surface for these warnings — deliberately deferred here, not an oversight; revisit as a fast-follow if fleet-wide hint-resolution coverage is wanted.

## Integration Map

- `scripts/little_loops/fsm/validation/{structural_rules,evaluator_rules}.py`.
- `validate_fsm` / `load_and_validate` plumbing and callers: `cli/loop/config_cmds.py`, `cli/logs.py`.
- Tests: `test_fsm_validation_structural.py`, `test_fsm_validation_evaluator_rules.py`, `test_wiring_reference_docs.py`, plus a `ll-loop validate` CLI-level test of the WARNING output.
- Docs are end-user docs (`docs/guides`, `docs/reference`): use consuming-project paths, no `scripts/tests/` citations (`test_docs_audience_gate.py`).

## Impact

- **Priority**: P3.
- **Effort**: Small (warnings plus `validate_fsm`/`load_and_validate` plumbing) plus a docs pass across ~6 files.
- **Risk**: Low.

## Acceptance Criteria

- [ ] Warnings fire for an unmapped hint on a reachable request path and not when every path resolves; downgrade-only states produce no SDK warning.
- [ ] An evaluator-only hint on a `request_path: sdk` state is checked against the CLI host only (no `anthropic-api` warning).
- [ ] `validate_fsm`/`load_and_validate` accept `host_cli`/`model_hints`; with `host_cli=None`, no resolution warnings fire and existing callers' output is unchanged.
- [ ] Vocabulary semantics, support matrix, precedence and the deferred skill/agent scope (ENH-3533) are documented in `docs/guides/LOOPS_GUIDE.md`, `docs/generalized-fsm-loop.md`, `docs/reference/{API,CLI,HOST_COMPATIBILITY,CONFIGURATION}.md` and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`.

## Status

**Open** | Created: 2026-09-24 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue covers validate-time WARNINGs, `haiku-gen` guidance, and documentation only. Resolver/config is ENH-3527 (done) and dispatch wiring is ENH-3547 (done). ENH-3527 dropped the `operation` parameter (2026-09-24). ENH-3547 proved the support matrix with tests that this issue's docs describe; both prerequisites have since landed, so this issue is no longer blocked.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:57 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
