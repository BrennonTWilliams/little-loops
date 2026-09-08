---
id: BUG-3400
type: BUG
title: 'Credential scoping: unguarded gh probe, scopes [] bypasses validation, queue
  path not gh-isolated or audited'
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-07'
captured_at: '2026-09-07T23:44:14Z'
parent: EPIC-3212
---

# BUG-3400: Credential scoping: unguarded gh probe, scopes [] bypasses validation, queue path not gh-isolated or audited

## Summary

Post-merge review of EPIC-3212 (merged to `main` in 57c0a3af1 with `verify_before_merge: false`, so no gate ran) found three defects in the credential-scoping feature. Each one silently defeats the isolation the epic promises, so they are grouped here as one fix.

## Current Behavior

1. **`gh` probe is unguarded** — `gh_scope_extra()` in `scripts/little_loops/host_runner.py` runs `subprocess.run(["gh", "auth", "token"], ...)` with no `timeout` and no handling for a missing binary. The FSM shell path in `scripts/little_loops/fsm/runners.py` wraps the call in `except RuntimeError` only, so a missing-binary error (no `gh` installed) or a hung probe escapes the catch, skips `gh_tmp.cleanup()` (leaks the `ll-gh-*` temp dir), and aborts the whole loop run instead of failing just that state. This contradicts the docstring's own claim that there is no path that leaves the child un-scoped: there is one, it just crashes.

2. **`scopes: []` bypasses validation** — `scripts/little_loops/fsm/validation/structural_rules.py` guards the unknown-scope check with `if state.scopes:` (truthy) instead of `is not None`. An explicit empty list on a non-shell state is neither rejected nor honoured; it becomes a runtime no-op with no error anywhere. No existing test exercises an empty scope list.

3. **ActionSpec/queue path is not gh-isolated and not audited** — `scripts/little_loops/runner_spec.py` (CMD runner, ~line 251) calls `resolve_scopes(spec.scopes)` to build `env_allow` but never calls `gh_scope_extra()`. A queued task declaring `scopes: [github]` gets env-name filtering only: no `GH_CONFIG_DIR` redirect, no injected `GH_TOKEN`, so the operator's ambient `gh` keyring session leaks into the child. `write_credential_scope()` is also wired only from `scripts/little_loops/fsm/executor.py`, so queue-path grants never reach the audit table. This is a partial completion of ENH-3234 ("ActionSpec credential scope declaration and runner_spec.py wiring") and breaks the epic-level acceptance criterion that "every declaring dispatch leaves a `credential_scope_events` row".

## Steps to Reproduce

1. **Unguarded `gh` probe**: On a host without `gh` on `PATH`, run an FSM loop with a shell state declaring `scopes: [github]`. In `scripts/little_loops/fsm/runners.py`, the call to `gh_scope_extra(Path(gh_tmp.name), with_token=True)` (line 338) invokes `subprocess.run(["gh", "auth", "token"], ...)` inside `host_runner.py`'s `gh_scope_extra()`, which raises `FileNotFoundError`, not `RuntimeError`. Observe: the exception escapes the `except RuntimeError` handler, aborts the whole loop run instead of failing just that state, and leaves the `ll-gh-*` temp dir behind (`gh_tmp.cleanup()` never runs).
2. **`scopes: []` bypass**: Author an FSM state with an explicit empty scope list (`scopes: []`) on a non-shell state type. Run `ll-loop validate` (or trigger the structural rule directly in `scripts/little_loops/fsm/validation/structural_rules.py`). Observe: `if state.scopes:` at line 499 is falsy for `[]`, so the unknown-scope check at line 500 never runs — no validation error, no rejection, silent no-op.
3. **Queue path not `gh`-isolated**: Submit a queued `ActionSpec` with `scopes: [github]` to the CMD runner (`scripts/little_loops/runner_spec.py`, `resolve_scopes(spec.scopes)` at line 251). Inside the spawned child, run `gh auth status`. Observe: it reports the operator's ambient `gh` keyring login — `gh_scope_extra()` is never called on this path, so no `GH_CONFIG_DIR` redirect or `GH_TOKEN` injection occurs, and no `credential_scope_events` row is written via `write_credential_scope()` (`scripts/little_loops/session_store/writers.py`).

## Expected Behavior

1. `gh_scope_extra()` bounds the probe with a timeout and converts `FileNotFoundError`/`TimeoutExpired`/`OSError` into the same `RuntimeError` contract the callers already handle; the FSM shell path cleans up the temp dir on every failure path.
2. `scopes: []` is validated the same way as a non-empty list (accepted as "declare nothing, deny all", or rejected — pick one and test it); the check uses `is not None`.
3. The CMD runner in `runner_spec.py` applies `gh_scope_extra()` when `github` is declared (mirroring `fsm/runners.py`, including temp-dir lifecycle) and records the grant via `write_credential_scope()` so both dispatch paths produce identical audit rows.

## Program Design

### Signatures

- `gh_scope_extra(config_dir: Path, *, with_token: bool) -> dict[str, str]` (`scripts/little_loops/host_runner.py:186`) — wrap the `subprocess.run(["gh", "auth", "token"], ...)` probe so `FileNotFoundError`/`TimeoutExpired`/`OSError` raise the same `RuntimeError` the docstring already promises, and add an explicit `timeout=`.
- `_validate_credential_scopes` scope check in `scripts/little_loops/fsm/validation/structural_rules.py:499` — change `if state.scopes:` to `if state.scopes is not None:`.
- `resolve_scopes(scopes: Iterable[str]) -> frozenset[str]` (`scripts/little_loops/host_runner.py:166`) — already called from `runner_spec.py:251`; mirror the adjacent `gh_scope_extra()` + `write_credential_scope()` wiring next to it.
- `write_credential_scope(db_path: Path | str, *, run_id: str, state: str, scopes: frozenset[str], var_names: frozenset[str], ts: str | None = None) -> bool` (`scripts/little_loops/session_store/writers.py:1945`) — call from the CMD runner path with the queued task's run id in place of an FSM state name.

### Call Path

`scripts/little_loops/runner_spec.py` (CMD runner, ~line 251) -> `resolve_scopes(spec.scopes)` (existing) -> **new**: `gh_scope_extra(Path(gh_tmp.name), with_token="github" in spec.scopes)` (mirroring `fsm/runners.py:338`) -> **new**: `write_credential_scope(...)` (mirroring `fsm/executor.py`'s existing call site).

## Impact

- **Priority**: P1 - A credential-isolation feature that silently does not isolate is worse than none: operators will assume queued `github`-scoped tasks are sandboxed from their keyring login when they are not, and the audit trail has a blind spot on that path.
- **Effort**: Small - three localized fixes (a try/except + timeout, an `is not None`, and mirroring ~15 lines of existing `fsm/runners.py` wiring into `runner_spec.py`) plus tests.
- **Risk**: Low - fixes are additive on paths only exercised by tasks that declare `scopes:`; undeclared tasks stay full-inherit.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] `gh_scope_extra()` with `gh` absent from `PATH` raises `RuntimeError`, not `FileNotFoundError`; the probe has an explicit timeout.
- [ ] A shell state declaring `scopes: [github]` on a host without `gh` fails that state with `exit_code=1` and the run continues per normal FSM error handling; no `ll-gh-*` temp dir is left behind.
- [ ] Test: `scopes: []` on a state is handled by `_validate_*` scope rule (either accepted deliberately or rejected with a clear message) and a test pins the choice.
- [ ] A queued `ActionSpec` with `scopes: [github]` runs its child with `GH_CONFIG_DIR` redirected and `GH_TOKEN` set; `gh auth status` inside it does not see the operator login.
- [ ] A queued `ActionSpec` with any declared scopes produces a `credential_scope_events` row keyed by its run id.
- [ ] Unit suite green: `python -m pytest scripts/tests/`.

## Relates To

- EPIC-3212, ENH-3205 (gh isolation), ENH-3234 (ActionSpec wiring), ENH-3204 (audit table), ENH-3235 (FSM wiring)
- Found by `/code-review high db393717e..1927af68d` on 2026-09-07.

## Status

**Open** | Created: 2026-09-07 | Priority: P1


## Session Log
- `/ll:format-issue` - 2026-09-08T00:06:12 - `fd8050c6-8bbf-4735-ba8f-b83f5f588867.jsonl`
