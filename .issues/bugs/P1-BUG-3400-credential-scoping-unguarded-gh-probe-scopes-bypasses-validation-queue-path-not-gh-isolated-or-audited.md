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
learning_tests_required:
- gh
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

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

**Files to Modify (confirmed)**
- `scripts/little_loops/host_runner.py:186-231` — `gh_scope_extra()`, the unguarded probe (point 1)
- `scripts/little_loops/fsm/validation/structural_rules.py:499` — the `if state.scopes:` guard (point 2)
- `scripts/little_loops/runner_spec.py:237-262` (`_run_cmd`) — missing `gh_scope_extra()`/`write_credential_scope()` wiring (point 3)

**Conventions in Force**
- Exception-normalization for a `subprocess.run`/`Popen` failure is done inline at each call site, not through a shared helper — no repo-wide "normalize FileNotFoundError/TimeoutExpired/OSError into RuntimeError" utility exists. Two divergent local examples: `host_runner.py:2446-2469` (`run_blocking_json`) raises a `RuntimeError` subclass (`BlockingJsonError`, `host_runner.py:2321`) with `from None`; `fleet_improve.py:103-125` raises a plain-`Exception` subclass (`FleetImproveError`) with `from e`. Neither matches `gh_scope_extra()`'s own current bare `raise RuntimeError(...)` (no custom class) — the fix has no single existing convention to copy, only two disagreeing examples; the issue's own Expected Behavior already resolves this by requiring the same `RuntimeError` contract the callers already handle.
- `structural_rules.py` checks every `Optional`-typed `StateConfig` field with `is not None` (48+ occurrences, e.g. lines 471, 524) — the `if state.scopes:` truthy check at line 499 is this file's one outlier against its own idiom, not a deliberate alternate pattern (the file's two truthy checks, lines 484 and 534, guard non-Optional `dict`-typed fields with `default_factory=dict`, a different field shape).
- The FSM shell-state wiring point 3 must mirror is split across two layers, not co-located: `fsm/executor.py:2563-2582` calls `write_credential_scope()` (audit, wrapped in `except Exception: pass`, "Non-fatal (ENH-3204)") before dispatch; `fsm/runners.py:317-346` + `:462-464` does the `env_allow = resolve_scopes(scopes)` (`ValueError`-catching) and separately the `gh_tmp` tempdir + `gh_scope_extra()` (`RuntimeError`-catching) inside the runner that owns the `Popen`, with `gh_tmp.cleanup()` called both on the immediate `gh_scope_extra()` failure path and unconditionally in an outer `finally`.
- `runner_spec.py:237-262` (`_run_cmd`) already mirrors `fsm/runners.py`'s `env_allow`/`resolve_scopes`/`ValueError` block verbatim in shape (down to the variable name), but stops there — no `gh_tmp`, no `gh_scope_extra()`, no `write_credential_scope()` call anywhere in the file (confirmed by direct grep).

**Tests**
- `scripts/tests/test_host_runner.py:496-546` — existing `TestGhScopeExtra` class (the test home for point 1's fix); `test_with_token_raises_when_no_token_obtainable` mocks `little_loops.host_runner.subprocess.run` via `patch(...)`.
- `scripts/tests/test_fsm_validation_structural.py:2254-2326` — existing `TestScopesValidation` class (the test home for point 2); no test in this class or elsewhere exercises `scopes=[]` at the structural-validation layer today (the only repo-wide `scopes=[]` hits are in `test_fsm_runners.py:442,450,471`, which test the execution layer, not validation).
- `scripts/tests/test_runner_spec.py:133,208-253` — existing CMD-dispatch scope tests (`test_cmd_dispatch_no_scopes_keeps_full_inherit`, `test_cmd_dispatch_declared_scope_allows_its_vars_denies_others`, `test_cmd_dispatch_unknown_scope_fails_loud_and_spawns_nothing`) use `patch("subprocess.Popen")` + `mock_popen.assert_not_called()` for the fail-loud-without-spawning shape; none assert `GH_TOKEN`/`GH_CONFIG_DIR` isolation via `gh_scope_extra()` — the existing `test_cmd_dispatch_declared_scope_allows_its_vars_denies_others` only proves ambient `GH_TOKEN` passes through via `env_allow`, which is exactly the leak point 3 reports.
- `scripts/tests/test_session_store_writers.py:2861-2897` (`TestWriteCredentialScope`) and `scripts/tests/test_fsm_executor.py:3774-3843` (`TestCredentialScopeAudit`) — existing audit-row assertion patterns at two layers: direct-call (`write_credential_scope(...)` then `recent(db, kind="credential_scope")`) and executor-integration (mock `write_credential_scope` and inspect `call_args.kwargs`, or a real sqlite `SELECT * FROM credential_scope_events` to prove no secret value leaked). No equivalent test exists yet for the CMD-runner path.

**Documentation**
- `docs/reference/API.md:10232` documents `gh_scope_extra()`'s signature and caller behavior; `docs/reference/API.md:10011` notes `env_allow` re: ENH-3395. Both describe only the FSM path today.
- `docs/ARCHITECTURE.md:680` and `docs/guides/LOOPS_GUIDE.md` describe the credential-scoping design; neither currently documents a CMD-runner/queue-path isolation guarantee, matching the gap this issue reports.

**Configuration**
- No dedicated configuration file governs `gh_scope_extra`/`resolve_scopes`/`write_credential_scope`/`CREDENTIAL_SCOPES` — confirmed by a repo-wide grep with no hits outside `scripts/little_loops/*.py`, `scripts/tests/*.py`, `docs/*`, and `.issues/*`.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/harness.py:25` — imports `runner_spec`/`ActionSpec`; no `scopes` keyword in this file (0 hits).
- `scripts/little_loops/cli/queue.py:33` — imports `ActionSpec`; no `scopes` keyword in this file (0 hits).
- `scripts/little_loops/queue_store.py:36` — imports `ActionSpec, RunnerType`; `_serialize_action`/`_deserialize_action` (lines 240, 253/256) round-trip `ActionSpec.scopes` but call no scope-isolation function themselves.
- `scripts/little_loops/cli/action.py:218` — imports `ActionSpec, RunnerType, run_action`; constructs `ActionSpec(...)` at lines 242 and 295; no `scopes` keyword found in this file (0 hits) — these construction sites do not pass `scopes` today.
- `scripts/tests/test_runner_spec.py:25`, `scripts/tests/test_queue_store.py:28`, `scripts/tests/test_cli_queue.py:17`, `scripts/tests/test_cli_harness.py:14` — existing test files importing `runner_spec`/`ActionSpec`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py:130,132` — imports `ActionSpec, RunnerType`; constructs `ActionSpec(name=loop_name, runner=RunnerType.LOOP, ...)` with no `scopes=` kwarg — a fifth `ActionSpec` construction site not covered by the issue's original caller list. [Agent 1 finding]
- `scripts/little_loops/fsm/schema.py:728-731,836-837,959` — defines `StateConfig.scopes: list[str] | None = None` (the field the `structural_rules.py:499` guard validates) plus its `to_dict`/`from_dict` round-trip. [Agent 1 finding]
- `scripts/little_loops/session_store/schema.py:82,1317,1325-1326` and `scripts/little_loops/session_store/schema_manifest.json:87,929,956` — define the `credential_scope_events` table DDL/manifest that `write_credential_scope()` inserts into; the code comment above the `CREATE TABLE` (~`schema.py:1317`) claims writes come only from `FSMExecutor`, a claim point 3's fix makes stale. [Agent 1 + Agent 2 findings]
- `scripts/little_loops/cli/queue.py:480` — the drain loop already has `entry.id` (a `QueueEntry.id`) in scope at the `run_action(entry.action)` call site but does not thread it through; this is the one caller with a real run-identifier available for the point-3 `write_credential_scope(run_id=...)` wiring. [Agent 2 finding]
- `scripts/little_loops/cli/harness.py:833,866,909,942` and `scripts/little_loops/cli/action.py:250,304` — construct `ActionSpec(...)`/call `run_action`/`_run_cmd` with no run-identifier concept at all today; if `run_action()`/`_run_cmd()` gain a `run_id` keyword for point 3's audit wiring, these four call sites have no real id to pass — needs a decision (synthetic id from `spec.name`/`spec.target`, or skip the audit row for non-queue dispatch paths). See Wiring Phase below. [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/HISTORY_SESSION_GUIDE.md` (~lines 140-148) — the "What Gets Recorded" table states `credential_scope_events` is "written by `FSMExecutor` via `write_credential_scope()`" only; needs updating once the CMD/queue path also writes. [Agent 2 finding]
- `scripts/little_loops/session_store/schema.py` (comment above the `credential_scope_events` `CREATE TABLE`, ~line 1317) — in-source comment claims "written from FSMExecutor before the spawn"; same stale single-writer claim in code-comment form. [Agent 2 finding]
- `docs/reference/API.md:10190` (`### resolve_scopes` section) — a third API.md location (distinct from `:10011`/`:10232` already noted above) claims the FSM `StateConfig` surface is "a separate, not-yet-wired consumer" of `resolve_scopes` — already inaccurate today (it's fully wired via `fsm/runners.py`/`fsm/executor.py`) and remains stale in the opposite direction once the CMD path is wired too. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_runners.py` (`TestDefaultActionRunnerShellPath`, lines 227-522) — the FSM shell path's full isolation-test suite; referenced in this issue's Codebase Research prose but missing from the formal test list. This is the direct model the new CMD-path isolation test in `test_runner_spec.py` should mirror: `test_shell_declared_scope_allows_its_vars_denies_others` (416-436, `scopes=["github"]`), `test_shell_declared_empty_scopes_redirects_config_dir_no_token` (438-454, `scopes=[]`), `test_shell_undeclared_scopes_no_config_dir_redirect` (456-463, `scopes=None`), `test_shell_github_scope_no_token_fails_state_spawns_nothing` (476-495, RuntimeError-before-`Popen` + cleanup), `test_shell_scoped_tempdir_removed_after_timeout` (497-522, cleanup-on-timeout). [Agent 1 + Agent 3 findings]
- `scripts/tests/test_enh3184_spawn_site_guard.py:38-51` — a spawn-site-inventory guard hard-coding `"little_loops/host_runner.py": (2, 0)` (2 `subprocess.run`/`Popen` calls, 0 exempted). Wrapping the existing `gh auth token` call in `try`/`except` with a `timeout=` kwarg keeps the count unchanged; only touch this guard if the fix adds a *second* new subprocess call site in `host_runner.py`. [Agent 3 finding]
- `scripts/tests/test_cli_queue_run.py:26,265` and `scripts/tests/test_feat_queue_mcp_tools.py:147` — import `ActionSpec`/`RunnerType`/`run_action` inside tests; check for breakage if `run_action()` gains a `run_id` parameter (see the `cli/queue.py:480` note above). [Agent 1 finding]
- Confirmed: no existing test asserts `FileNotFoundError`/`TimeoutExpired` propagating from `gh_scope_extra()`'s probe or being caught by `fsm/runners.py`'s `except RuntimeError` — normalizing to `RuntimeError` is a pure test gap, not a breaking change to any existing assertion. [Agent 3 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fsm-loop-schema.json:597-602` — the FSM loop-YAML JSON Schema's own `"scopes"` property definition (separate from `config-schema.json`, which this issue already confirmed has no `scopes` references). It has no `minItems` constraint, so schema-level validation already structurally permits `scopes: []` — consistent with, not blocking, the Python-level fix in `structural_rules.py:499`. No edit required; noted for completeness. [Agent 1 + Agent 2 findings]

## Program Design

### Signatures

- `gh_scope_extra(config_dir: Path, *, with_token: bool) -> dict[str, str]` (`scripts/little_loops/host_runner.py:186`) — wrap the `subprocess.run(["gh", "auth", "token"], ...)` probe so `FileNotFoundError`/`TimeoutExpired`/`OSError` raise the same `RuntimeError` the docstring already promises, and add an explicit `timeout=`.
- `_validate_credential_scopes` scope check in `scripts/little_loops/fsm/validation/structural_rules.py:499` — change `if state.scopes:` to `if state.scopes is not None:`.
- `resolve_scopes(scopes: Iterable[str]) -> frozenset[str]` (`scripts/little_loops/host_runner.py:166`) — already called from `runner_spec.py:251`; mirror the adjacent `gh_scope_extra()` + `write_credential_scope()` wiring next to it.
- `write_credential_scope(db_path: Path | str, *, run_id: str, state: str, scopes: frozenset[str], var_names: frozenset[str], ts: str | None = None) -> bool` (`scripts/little_loops/session_store/writers.py:1945`) — call from the CMD runner path with the queued task's run id in place of an FSM state name.

### Call Path

`scripts/little_loops/runner_spec.py` (CMD runner, ~line 251) -> `resolve_scopes(spec.scopes)` (existing) -> **new**: `gh_scope_extra(Path(gh_tmp.name), with_token="github" in spec.scopes)` (mirroring `fsm/runners.py:338`) -> **new**: `write_credential_scope(...)` (mirroring `fsm/executor.py`'s existing call site).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Decide how a run-identifier reaches `write_credential_scope(run_id=...)` from the CMD path: `run_action()`/`_run_cmd()` (`runner_spec.py:362,237`) take only an `ActionSpec` today, with no id field distinct from `name`/`target`. Of the three callers, only `cli/queue.py:480` has a real id in scope (`entry.id`, a `QueueEntry.id`) and should thread it through; `cli/harness.py:833,866,909,942` and `cli/action.py:250,304` have no id concept and need an explicit choice (synthetic id from `spec.name`/`spec.target`, or skip the audit row for non-queue dispatch).
- Update `docs/guides/HISTORY_SESSION_GUIDE.md` (~140-148) and the `session_store/schema.py` comment above the `credential_scope_events` `CREATE TABLE` (~line 1317) — both currently claim `FSMExecutor` is the sole writer.
- Update `docs/reference/API.md:10190` (`### resolve_scopes`) — currently claims the FSM `StateConfig` surface is "a separate, not-yet-wired consumer," which is already stale and becomes more so once the CMD path is symmetric with it.
- Add a CMD-runner isolation test in `test_runner_spec.py` mirroring `test_fsm_runners.py::TestDefaultActionRunnerShellPath` (`scopes=["github"]`, `scopes=[]`, RuntimeError-before-`Popen` cleanup, timeout cleanup) per the Tests subsection above.

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
- BUG-3402 — a deeper, related isolation gap surfaced by `/ll:wire-issue` on 2026-09-08: on keychain-backed macOS `gh`, `gh auth token` still succeeds via Keychain regardless of the `GH_CONFIG_DIR` redirect this issue's fix relies on. This issue's acceptance criteria only test `gh auth status`, so its fix will pass while BUG-3402's gap remains — fixing this issue does not resolve BUG-3402.

## Status

**Open** | Created: 2026-09-07 | Priority: P1


## Session Log
- `/ll:wire-issue` - 2026-09-08T00:33:51 - `818ac84c-8dd8-46bc-9d1e-d582e9b2e72e.jsonl`
- `/ll:refine-issue` - 2026-09-08T00:21:05 - `79946685-eebd-494a-af0a-cc7c04146960.jsonl`
- `/ll:format-issue` - 2026-09-08T00:06:12 - `fd8050c6-8bbf-4735-ba8f-b83f5f588867.jsonl`
