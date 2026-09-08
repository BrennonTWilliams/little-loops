---
id: ENH-3403
type: ENH
title: ActionSpec.scopes silently ignored by skill/prompt/mcp runners
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-08'
captured_at: '2026-09-08T00:42:38Z'
parent: EPIC-3212
reconcile_attempted: true
---

# ENH-3403: ActionSpec.scopes silently ignored by skill/prompt/mcp runners

## Summary

`ActionSpec.scopes` (ENH-3234) is documented and wired for `RunnerType.CMD` only. `_run_skill()` and `_run_prompt()` in `scripts/little_loops/runner_spec.py` never read `spec.scopes`, so a skill or prompt `ActionSpec` that declares `scopes: [github]` runs its host-CLI child with full env inheritance and no `GH_CONFIG_DIR` redirect, with no error and no `credential_scope_events` row. This is the ActionSpec-side twin of the silent no-op BUG-3400 point 2 fixes on the FSM side (`scopes: []` on a non-shell state), where the answer was fail-loud at validation time.

## Current Behavior

- `_run_cmd()` resolves `spec.scopes` into `env_allow` (and, after BUG-3400, applies `gh_scope_extra()` + writes the audit row).
- `_run_skill()` and `_run_prompt()` build their env via `project_child_env(inv)` with no `env_allow` and ignore `spec.scopes` entirely. `_run_mcp()` also ignores it.
- `run_action()` dispatches without checking the runner/scopes combination, so nothing rejects the declaration.
- `queue_store` round-trips `scopes` for every runner type, so a queued skill/prompt entry with scopes persists and later dispatches unscoped.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- Exact anchors confirmed (codebase-analyzer): `run_action()` dispatch at `runner_spec.py:362-373`; `_run_cmd()`'s scope resolution at `:237-262`; `_run_skill()` at `:103-234`; `_run_prompt()` at `:334-351`; `_run_mcp()` at `:318-331`; `ActionSpec` (incl. `scopes: frozenset[str] | None`) at `:84-100`; `RunnerType` enum at `:56-64`.
- `_run_cmd()` today resolves `spec.scopes` into `env_allow` via `resolve_scopes()` (`host_runner.py:166-183`) but does **not** yet call `gh_scope_extra()` or `write_credential_scope()` — grepping `runner_spec.py` for both symbols returns no hits. BUG-3400 (the issue that wires those in) is still `status: open`. This confirms rather than contradicts this section's own phrasing ("and, after BUG-3400, applies...") — noted here so an implementer doesn't mistake the parenthetical for already-shipped behavior.
- `_run_skill()`/`_run_prompt()` build their env via `project_child_env(inv)` with no `env_allow` kwarg, so they always take `project_child_env()`'s full-inheritance branch; `_run_mcp()` calls `call_mcp_tool()` directly with no `project_child_env()` call at all. `HostInvocation.env_allow` (`host_runner.py:312`) carries a comment stating "Nothing in this repo populates this field yet" — structural confirmation that `env_allow` cannot reach these three runners today regardless of `spec.scopes`.
- `ActionSpec` has no `__post_init__` (confirmed: no hits in `runner_spec.py`) — no construction-time validation exists for `scopes` or any other field; only `_run_cmd()`'s dispatch-time `resolve_scopes()` call ever validates scope contents, and only when `runner is CMD`.

## Expected Behavior

Pick one and test it:

(a) **Fail loud (recommended, matches ENH-3203 Decision #3 and BUG-3400 point 2):** `run_action()` returns `RunnerResult(exit_code=2, error=...)` without spawning when `spec.scopes is not None` and `spec.runner` is not `RunnerType.CMD`, naming the runner and stating that scopes are CMD-only. `ll-queue add` / `ll-action` / `ll-harness` surface the same message at enqueue/validate time where they already validate `ActionSpec` shape.

(b) **Honour it:** thread `env_allow` + `gh_scope_extra()` + `write_credential_scope()` into the skill/prompt runners the same way BUG-3400 does for CMD. Larger, and `resolve_host().build_*` invocations may need host-specific credential scopes (`claude-api`, etc.) declared alongside `github` to function at all, so this option needs a design pass first.

## Motivation

An operator who writes `scopes: [github]` on a queued skill or prompt task reasonably assumes the child is sandboxed the same way a CMD task is. Today that declaration is accepted, persisted, and then ignored at dispatch with no error and no audit row, so the credential-scoping feature (EPIC-3212) makes an isolation promise on a surface where it does nothing. The epic-level acceptance criterion that every declaring dispatch leaves a `credential_scope_events` row is also violated on these runners.

## Proposed Solution

Option (a) from Expected Behavior: a dispatch-time guard in `run_action()` that returns `RunnerResult(exit_code=2, error=...)` without spawning when `spec.scopes is not None` and `spec.runner is not RunnerType.CMD`, mirroring `_run_cmd()`'s existing `ValueError` fail-loud shape and the FSM shell-only rule in `structural_rules.py`. Option (b) stays open as a later design pass if skill/prompt scoping is actually wanted.

## Program Design

### Types

- No new types — reuses existing `ActionSpec.scopes: frozenset[str] | None` and `RunnerResult`.

### Signatures

- `run_action(spec: ActionSpec) -> RunnerResult` — add the guard before `handler = _DISPATCH.get(spec.runner)` dispatch.

### Call Path

`run_action()` -> (new) scope guard: `if spec.scopes is not None and spec.runner is not RunnerType.CMD: return RunnerResult(exit_code=2, error=...)` -> else existing `_DISPATCH[spec.runner](spec)` (`_run_skill`/`_run_prompt`/`_run_mcp`/`_run_cmd`)

Current call path (post-BUG-3400, confirmed at `runner_spec.py:401-419`) is no longer a
single `_DISPATCH.get()` lookup: `run_action(spec, *, run_id=None)` special-cases
`RunnerType.CMD` with an early `return _run_cmd(spec, run_id=run_id)` *before* touching
`_DISPATCH`, and `_DISPATCH` itself (`:394-398`) now maps only `SKILL`/`MCP`/`PROMPT` —
`CMD` was removed from the dict. So the new guard's insertion point is: after the
`RunnerType.CMD` early-return, before `handler = _DISPATCH.get(spec.runner)` (or folded
into that check) — the guard never sees CMD specs, matching the original design intent
but not its literal line anchor.

- Confirmed exact insertion point (`runner_spec.py:362-373`, codebase-analyzer): the guard sits **after** `handler = _DISPATCH.get(spec.runner)` resolves but **before** `return handler(spec)` — so `RunnerType.LOOP`'s existing `ValueError` raise (unregistered dispatch key, line 372, tested by `TestRunnerTypeCompleteness::test_loop_not_in_dispatch_table`) stays untouched by the new check.
  > ⚠ Superseded — `362-373` is stale; direct read of the live file (2026-09-08, this pass) confirms `run_action()` now spans `runner_spec.py:401-419`, `_DISPATCH` is at `:394-398` and no longer contains `CMD` (`RunnerType.CMD` now returns early via `if spec.runner is RunnerType.CMD: return _run_cmd(...)` at `:414-415`, before `_DISPATCH` is ever consulted). The "after `_DISPATCH.get()`, before `handler(spec)`" placement rule stated above still holds structurally — only the line numbers are wrong. `RunnerType.LOOP`'s raise is now at `:418`, not `372`.
- `RunnerType` has 6 members: `SKILL`, `CMD`, `MCP`, `PROMPT`, `DSL`, `LOOP` (`runner_spec.py:56-64`). `DSL` is absent from `_DISPATCH` — it is a batch driver over `PROMPT` per `run_action()`'s docstring, and callers loop and call `run_action()` once per task with `RunnerType.PROMPT`, never `RunnerType.DSL` — so `DSL` never reaches `_DISPATCH.get()` as a key in practice and needs no guard branch of its own.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

**Decision Rules** (ENH-3050 — this issue's new dispatch-time gate):

- **Gate**: `spec.scopes is not None and spec.runner is not RunnerType.CMD` — evaluated once per `run_action()` call, after `handler = _DISPATCH.get(spec.runner)` resolves and before `handler(spec)` is invoked.
- **On trigger**: return `RunnerResult(exit_code=2, error=<message naming the runner and stating scopes are CMD-only>)` without calling `handler(spec)` — no subprocess/skill/prompt/mcp dispatch occurs.
- **Escape hatch**: `RunnerType.CMD` is exempt unconditionally; `spec.scopes is None` on every runner type (including CMD) always passes through unchanged — matches AC2 ("scopes=None on every runner type is unchanged").
- **Message wording — contested, not resolved by this pass** (codebase-pattern-finder): two competing phrasings exist for "field invalid for this runner/state type" rejections elsewhere in this codebase, and they disagree:
  - `fsm/validation/structural_rules.py:509-519` (the FSM shell-only `scopes:` precedent this issue's Proposed Solution cites): `"state '{state_name}' declares 'scopes' but is not a shell action; scopes are enforced only for shell actions"` — names the field and states the applicability rule.
  - `runner_spec.py`'s own `resolve_scopes()` (`host_runner.py:166-183`, the CMD-side unknown-scope rejection `_run_cmd()` already returns via `except ValueError as e: return RunnerResult(exit_code=2, error=str(e))`): `f"Unknown credential scope {scope!r}. Available: {sorted(CREDENTIAL_SCOPES)}."` — different shape (names the bad value + an "Available:" list), addresses a different failure (unknown scope name, not wrong runner type).
  - Neither is a drop-in template for "scopes declared on a non-CMD runner" — the implementer chooses which convention the new message follows; both exist as live precedent in this codebase today.

## Scope Boundaries

- **In scope**: `run_action()` dispatch guard rejecting `scopes is not None` for `RunnerType.SKILL`, `RunnerType.PROMPT`, `RunnerType.MCP`; enqueue/validate-time surfacing of the same message in `ll-queue add` / `ll-action` / `ll-harness`.
- **Out of scope**: Option (b) (actually threading `env_allow`/`gh_scope_extra()`/`write_credential_scope()` into `_run_skill()`/`_run_prompt()`/`_run_mcp()`) — needs its own design pass per the Expected Behavior section and is not part of this issue.

## Integration Map

### Files to Modify
- `scripts/little_loops/runner_spec.py` — `run_action()` dispatch guard: inserted after the existing `RunnerType.CMD` early-return and after `handler = _DISPATCH.get(spec.runner)` resolves, before `handler(spec)` is invoked (current span `runner_spec.py:401-419`); `ActionSpec.scopes` field comment (line ~97) already says CMD-only.
- `scripts/little_loops/cli/action.py` — `cmd_invoke()` (`:250` stream-json branch and `:304` `--output json` branch): add code to read and emit `result.error`, since both branches currently read only `result.exit_code` and would otherwise swallow the guard's rejection message.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/queue.py`, `scripts/little_loops/cli/harness.py`, `scripts/little_loops/cli/action.py` — `ActionSpec` construction sites; none pass `scopes` today. Guard-rejection propagation differs by caller: `queue.py`/`harness.py` already propagate `RunnerResult.error` with no caller-side code change; `action.py`'s `cmd_invoke()` needs new code (see Files to Modify).
- `scripts/little_loops/queue_store.py:240-262` — `scopes` round-trip, runner-agnostic.
- Confirmed exact `run_action()` call sites (codebase-analyzer; the code-graph `callers-of` query missed all of these, surfacing only test callers — confirmed instead by direct grep): `scripts/little_loops/cli/queue.py:480` (`_drain_once()`), `scripts/little_loops/cli/harness.py:833` (`cmd_skill`), `:866` (`cmd_cmd`), `:909` (`cmd_mcp`), `:942` (`_run_prompt_action`), `scripts/little_loops/cli/action.py:250` and `:304` (both branches of `cmd_invoke()` — the one caller needing new code).

### Similar Patterns
- `scripts/little_loops/fsm/validation/structural_rules.py:499-520` — shell-only `scopes:` check on `StateConfig` (the FSM-side precedent for option a).
- `scripts/little_loops/runner_spec.py:237-262` — `_run_cmd()`'s existing `ValueError` -> `exit_code=2` fail-loud shape (confirmed exact span; corrects the issue's earlier `248-253` estimate).

### Tests
- `scripts/tests/test_runner_spec.py` — add `test_skill_dispatch_with_scopes_fails_loud_spawns_nothing` / prompt / mcp variants alongside the existing CMD scope tests (`test_cmd_dispatch_unknown_scope_fails_loud_and_spawns_nothing`).

### Documentation
- `docs/reference/API.md` `### resolve_scopes` / `ActionSpec` sections — state that scopes are CMD-only and rejected elsewhere.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- **No `--scopes` CLI flag exists anywhere yet** (codebase-analyzer; repo-wide grep for `--scope`/`--scopes` in `scripts/little_loops`): `ll-queue add` (`_classify_action()`, `cli/queue.py:122-198`), `ll-harness` (`cmd_skill`/`cmd_cmd`/`cmd_mcp`/`_run_prompt_action`, `cli/harness.py`), and `ll-action` (`cmd_invoke()`, `cli/action.py`) never construct an `ActionSpec` with `scopes=` — the only 2 unrelated `--scope` hits in the tree are `cli/learning_tests.py:341` and `cli/issues/decisions.py:56,141`, both unconnected features. `scopes` is currently reachable only via direct Python/API `ActionSpec` construction (e.g. `queue_store._deserialize_action()` round-tripping a hand-written queue entry), not through any wired CLI path. No existing enqueue-time `ActionSpec`-shape validation function exists in `cli/queue.py`/`cli/action.py`/`cli/harness.py` to extend either (`_classify_action()` only classifies runner *kind* from a bare target string; `_deserialize_action()` performs no validation at all).
- **Guard-rejection propagation differs by caller** (codebase-analyzer) — relevant to Implementation Step 2 ("surface the same rejection message... wherever they already validate ActionSpec shape"):
  - `cli/queue.py:480` (`_drain_once()`): a non-`None` `RunnerResult.error` already forces `status = "failed"` and is persisted via `update_entry_result()` — the dispatch guard's message reaches the queue store with **no caller-side code change**.
  - `cli/harness.py:833/866/909/942`: all four feed into `_evaluate_and_report()` (`harness.py:659-796`), whose generic `if result.error is not None:` branch (line ~671) already prints/reports it — **no caller-side code change** needed for `ll-harness`.
  - `cli/action.py:250` and `:304` (`cmd_invoke()`, both the stream-json and `--output json` branches): read only `result.exit_code`, never `result.error` — the stream-json `action_complete` event has no `error` field, and the `--output json` payload's `"error"` key is built from captured `stderr_lines`, not `result.error`. A guard rejection would surface as `exit_code: 2` with `error: None`/no error text — **this is the one caller that needs new code** to read and emit `result.error` for the message itself to reach the user.
- **Test patch-target precedent per runner** (codebase-pattern-finder, from existing CMD scope tests in `scripts/tests/test_runner_spec.py`): the "fails loud AND spawns nothing" assertion shape patches the runner-specific spawn primitive — `subprocess.Popen` for CMD (`test_cmd_dispatch_unknown_scope_fails_loud_and_spawns_nothing`, line 237), `subprocess.run` for SKILL/PROMPT dispatch (see `test_skill_dispatch_matches_legacy_shape`, line 122-124), and `little_loops.runner_spec.call_mcp_tool` for MCP (`test_mcp_dispatch_matches_legacy_shape`, line 181-183) — then asserts `mock.assert_not_called()`, `result.exit_code != 0`, and the offending value's substring in `result.error`. The new SKILL/PROMPT/MCP scope-guard tests (Implementation Step 3) should follow this same three-part shape with the runner-appropriate patch target.

## Implementation Steps

1. Add the dispatch-time guard in `run_action()` (`runner_spec.py:401-419`): after the existing `RunnerType.CMD` early-return (`:414-415`) and after `handler = _DISPATCH.get(spec.runner)` resolves, return `RunnerResult(exit_code=2, error=...)` naming the runner when `spec.scopes is not None` and `spec.runner is not RunnerType.CMD`, before calling `handler(spec)` — leave `RunnerType.LOOP`'s existing `ValueError` raise (`:418`) untouched. Message wording is not pinned by this issue's research (two competing conventions exist — see Codebase Research Findings under Program Design → Call Path); name the runner and state that scopes are CMD-only.
2. `cli/queue.py:480` (`_drain_once()`) and `cli/harness.py:833/866/909/942` (via `_evaluate_and_report()`) already propagate `RunnerResult.error` with no caller-side code change needed. Add new code in `cli/action.py`'s `cmd_invoke()` (both the stream-json branch at `:250` and the `--output json` branch at `:304`) to read `result.error` and emit it — today both branches read only `result.exit_code`, so a guard rejection would otherwise surface as `exit_code: 2` with no error text.
3. Add `test_skill_dispatch_with_scopes_fails_loud_spawns_nothing` (and prompt/mcp variants) to `scripts/tests/test_runner_spec.py`, alongside the existing CMD scope tests.
4. Update `docs/reference/API.md` `ActionSpec`/`resolve_scopes` sections to state scopes are CMD-only and rejected elsewhere.
5. Run `python -m pytest scripts/tests/` and confirm `scopes=None` behavior (full inherit) is unchanged for every runner type.

## Impact

- **Priority**: P3 - Silent no-op on an isolation-promising field (no error, no audit row) is a correctness/trust gap, not a crash or data-loss risk; matches the sibling FSM-side fix (BUG-3400/ENH-3235) already shipped at this priority.
- **Effort**: Small - A single guard clause in `run_action()` plus enqueue-time message surfacing and a few new unit tests; mirrors the existing `_run_cmd()` `ValueError` -> `exit_code=2` fail-loud shape, no new abstractions.
- **Risk**: Low - Guard only triggers for the currently-broken combination (`scopes is not None` on a non-CMD runner); no caller passes `scopes` on SKILL/PROMPT/MCP today (see Dependent Files), so no existing behavior changes for `scopes=None`.
- **Breaking Change**: No - Only rejects a combination that was previously silently ignored; no passing call site is affected.

## Acceptance Criteria

- [ ] An `ActionSpec` with `runner in {SKILL, PROMPT, MCP}` and `scopes is not None` fails loud before spawn: `run_action()` returns `RunnerResult(exit_code=2, error=...)` without calling `handler(spec)` — no subprocess/skill/prompt/mcp dispatch occurs (option b is out of scope, see Scope Boundaries). A test for each non-CMD runner asserts the runner's spawn primitive is never called.
- [ ] `scopes=None` on every runner type is unchanged (full inherit).
- [ ] Unit suite green: `python -m pytest scripts/tests/`.

## Relates To

- BUG-3400 (CMD-runner wiring; this issue was split out of its pre-implementation review on 2026-09-08)
- ENH-3234 (ActionSpec scopes), ENH-3235 (FSM shell-only validation), EPIC-3212

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-08 | Priority: P3


## Session Log
- `/ll:reconcile-issue` - 2026-09-08T01:08:17 - `fc5babbf-1cd9-49b0-a38d-5df21886a22b.jsonl`
- `/ll:refine-issue` - 2026-09-08T01:03:22 - `7bb68963-023d-49d0-b440-47cea1a0b4b2.jsonl`
- `/ll:refine-issue` - 2026-09-08T00:58:20 - `39586ada-651e-408c-877e-3fa446fcc2a1.jsonl`
- `/ll:format-issue` - 2026-09-08T00:46:13 - `8b45174b-5119-458a-8d19-241ee9b2e5a3.jsonl`
