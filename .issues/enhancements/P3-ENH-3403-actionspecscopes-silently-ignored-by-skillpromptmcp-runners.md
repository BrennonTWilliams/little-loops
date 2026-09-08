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
confidence_score: 100
outcome_confidence: 83
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 21
---

# ENH-3403: ActionSpec.scopes silently ignored by skill/prompt/mcp runners

## Summary

`ActionSpec.scopes` (ENH-3234) is documented and wired for `RunnerType.CMD` only. `_run_skill()` and `_run_prompt()` in `scripts/little_loops/runner_spec.py` never read `spec.scopes`, so a skill or prompt `ActionSpec` that declares `scopes: [github]` runs its host-CLI child with full env inheritance and no `GH_CONFIG_DIR` redirect, with no error and no `credential_scope_events` row. This is the ActionSpec-side twin of the silent no-op BUG-3400 point 2 fixes on the FSM side (`scopes: []` on a non-shell state), where the answer was fail-loud at validation time.

## Current Behavior

- `_run_cmd()` resolves `spec.scopes` into `env_allow`, applies `gh_scope_extra()`, and writes the `credential_scope_events` audit row (BUG-3400, shipped; `runner_spec.py:258-275`).
- `_run_skill()` and `_run_prompt()` build their env via `project_child_env(inv)` with no `env_allow` and ignore `spec.scopes` entirely. `_run_mcp()` also ignores it.
- `run_action()` dispatches without checking the runner/scopes combination, so nothing rejects the declaration.
- `queue_store` round-trips `scopes` for every runner type, so a queued skill/prompt entry with scopes persists and later dispatches unscoped.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- Current anchors (direct read, 2026-09-07): `run_action()` at `runner_spec.py:401-419`; `_DISPATCH` at `:394-398` (SKILL/MCP/PROMPT only — CMD returns early at `:414-415`); `_run_cmd()`'s scope resolution + audit write at `:258-275`; `ActionSpec` (incl. `scopes: frozenset[str] | None`) at `:86-102`; `RunnerType` enum at `:58-66`. Line numbers drift; the structural facts are what matter.
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

`scope_runner_error(spec) -> str | None` (new pure helper in `runner_spec.py`) returns the rejection message when `spec.scopes is not None and spec.runner is not RunnerType.CMD`, else `None`. Two callers:

1. `run_action()`: CMD returns early at `:414-415` and never reaches the guard. After `handler = _DISPATCH.get(spec.runner)` (`:416`) resolves and the existing `RunnerType.LOOP` `ValueError` raise (`:418`, tested by `TestRunnerTypeCompleteness::test_loop_not_in_dispatch_table`) is left untouched, call the helper; on a message return `RunnerResult(stdout="", stderr="", exit_code=2, error=msg)` without calling `handler(spec)`.
2. `queue_store.add_entry()`: call the helper and raise `ValueError(msg)` so a scoped SKILL/PROMPT/MCP entry is rejected on enqueue rather than persisted and failed later at drain. `_deserialize_action()` stays permissive (no validation) so `ll-queue list` never crashes on a pre-existing bad entry; such an entry is caught by caller 1 when `_drain_once()` dispatches it.

- `RunnerType` has 6 members: `SKILL`, `CMD`, `MCP`, `PROMPT`, `DSL`, `LOOP` (`runner_spec.py:56-64`). `DSL` is absent from `_DISPATCH` — it is a batch driver over `PROMPT` per `run_action()`'s docstring, and callers loop and call `run_action()` once per task with `RunnerType.PROMPT`, never `RunnerType.DSL` — so `DSL` never reaches `_DISPATCH.get()` as a key in practice and needs no guard branch of its own.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

**Decision Rules** (ENH-3050 — this issue's new dispatch-time gate):

- **Gate**: `spec.scopes is not None and spec.runner is not RunnerType.CMD` — evaluated once per `run_action()` call, after `handler = _DISPATCH.get(spec.runner)` resolves and before `handler(spec)` is invoked.
- **On trigger**: return `RunnerResult(exit_code=2, error=<message naming the runner and stating scopes are CMD-only>)` without calling `handler(spec)` — no subprocess/skill/prompt/mcp dispatch occurs.
- **Escape hatch**: `RunnerType.CMD` is exempt unconditionally; `spec.scopes is None` on every runner type (including CMD) always passes through unchanged — matches AC2 ("scopes=None on every runner type is unchanged").
- **Message wording (decided 2026-09-07)**: follow the `fsm/validation/structural_rules.py:509-519` precedent, since it is the same failure class (field declared on a runner/state type that cannot enforce it). Exact text, asserted by tests as a stable substring:
  ```
  ActionSpec {spec.name!r} declares 'scopes' but runner is {spec.runner.value!r}; scopes are enforced only for RunnerType.CMD
  ```
  The `resolve_scopes()` "Unknown credential scope ... Available: [...]" shape is for a different failure (bad scope name) and is not used here.
- **No audit row on rejection**: the guard returns before any dispatch and must not call `write_credential_scope()`, matching `_run_cmd()`'s unknown-scope rejection. `credential_scope_events` only reflects real dispatches.

## Scope Boundaries

- **In scope**: `run_action()` dispatch guard rejecting `scopes is not None` for `RunnerType.SKILL`, `RunnerType.PROMPT`, `RunnerType.MCP`; the same check at enqueue time in `queue_store.add_entry()` (the only path that can actually produce a scoped non-CMD spec today is a hand-written or round-tripped queue entry).
- **Out of scope**: CLI-side surfacing in `ll-action` / `ll-harness`. No CLI flag sets `scopes`, and `cli/action.py`'s `cmd_invoke()` builds its own unscoped `ActionSpec`, so the guard can never fire through those entry points. (`cmd_invoke()` also never emits `RunnerResult.error` for any failure, e.g. `FileNotFoundError` — a real but unrelated gap; capture separately if wanted.) `ll-harness` and `ll-queue` drain already propagate `RunnerResult.error` unchanged.
- **Out of scope**: Option (b) (actually threading `env_allow`/`gh_scope_extra()`/`write_credential_scope()` into `_run_skill()`/`_run_prompt()`/`_run_mcp()`) — needs its own design pass per the Expected Behavior section and is not part of this issue.

## Integration Map

### Files to Modify
- `scripts/little_loops/runner_spec.py` — new `scope_runner_error(spec)` helper (export in `__all__`); `run_action()` guard after `handler = _DISPATCH.get(spec.runner)` resolves and after the LOOP `ValueError`, before `handler(spec)` (current span `:401-419`); `ActionSpec.scopes` field comment (`:99-101`) already says CMD-only.
- `scripts/little_loops/queue_store.py` — `add_entry()` (`:316`) calls `scope_runner_error()` and raises `ValueError` on a message. `_deserialize_action()` (`:253`) unchanged.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/queue.py`, `scripts/little_loops/cli/harness.py`, `scripts/little_loops/cli/action.py` — `ActionSpec` construction sites; none pass `scopes` today. `queue.py` `_drain_once()` and `harness.py` `_evaluate_and_report()` already propagate `RunnerResult.error` with no caller-side code change. `cli/action.py` is out of scope (see Scope Boundaries).
- `scripts/little_loops/queue_store.py:240-262` — `scopes` round-trip, runner-agnostic.
- Confirmed exact `run_action()` call sites (codebase-analyzer; the code-graph `callers-of` query missed all of these, surfacing only test callers — confirmed instead by direct grep): `scripts/little_loops/cli/queue.py:480` (`_drain_once()`), `scripts/little_loops/cli/harness.py:833` (`cmd_skill`), `:866` (`cmd_cmd`), `:909` (`cmd_mcp`), `:942` (`_run_prompt_action`), `scripts/little_loops/cli/action.py:250` and `:304` (both branches of `cmd_invoke()` — the one caller needing new code).

### Similar Patterns
- `scripts/little_loops/fsm/validation/structural_rules.py:499-520` — shell-only `scopes:` check on `StateConfig` (the FSM-side precedent for option a).
- `scripts/little_loops/runner_spec.py:237-262` — `_run_cmd()`'s existing `ValueError` -> `exit_code=2` fail-loud shape (confirmed exact span; corrects the issue's earlier `248-253` estimate).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/mcp_server/tools.py:539-582` (`_tool_queue_add`) — reads `spec.scopes` into its dry-run preview JSON (`"scopes": sorted(spec.scopes) if spec.scopes is not None else None`). No code change needed: `_classify_action()` (`cli/queue.py`) has no parameter for setting `scopes`, so this preview field is unconditionally `None` today and this MCP surface cannot currently construct a scoped SKILL/PROMPT/MCP spec to trip the new guard — confirmed inert, informational only. [Agent 1 + Agent 2 findings]
- `scripts/tests/test_enh3184_spawn_site_guard.py:28` — pins `runner_spec.py`'s spawn call-site count `(3, 0)` via a static AST guard. Not applicable to this issue: the guard clause is a pure early-return, adding no new `subprocess.run|Popen|check_output|call` sites. Only relevant if Option (b) (out of scope) later threads real spawns into `_run_skill`/`_run_prompt`/`_run_mcp`. [Agent 1 finding]

### Tests
- `scripts/tests/test_runner_spec.py` — add `test_skill_dispatch_with_scopes_fails_loud_spawns_nothing` / prompt / mcp variants alongside the existing CMD scope tests (`test_cmd_dispatch_unknown_scope_fails_loud_and_spawns_nothing`); each asserts the message substring, `exit_code == 2`, the runner's spawn primitive not called, and no `credential_scope_events` row written.
- `scripts/tests/test_queue_store.py` (or the existing queue tests) — `add_entry()` with a scoped SKILL spec raises `ValueError` carrying the message; a hand-written scoped SKILL entry written directly to the queue file still deserializes and, when drained by `_drain_once()`, lands `status: failed` with the guard message persisted and no spawn.

_Wiring pass added by `/ll:wire-issue` (revised 2026-09-07):_
- `scripts/tests/test_action.py` — no changes. `cmd_invoke()` cannot construct a scoped spec, so the earlier plan to patch `run_action` and assert `result.error` surfacing there tested an unreachable path; dropped along with the `cli/action.py` change.

### Documentation
- `docs/reference/API.md` `### resolve_scopes` / `ActionSpec` sections — state that scopes are CMD-only, rejected at `run_action()` and `add_entry()` for other runners, and that a hand-edited `scopes` on a non-cmd queue entry now fails at enqueue or drain.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- **No `--scopes` CLI flag exists anywhere yet** (codebase-analyzer; repo-wide grep for `--scope`/`--scopes` in `scripts/little_loops`): `ll-queue add` (`_classify_action()`, `cli/queue.py:122-198`), `ll-harness` (`cmd_skill`/`cmd_cmd`/`cmd_mcp`/`_run_prompt_action`, `cli/harness.py`), and `ll-action` (`cmd_invoke()`, `cli/action.py`) never construct an `ActionSpec` with `scopes=` — the only 2 unrelated `--scope` hits in the tree are `cli/learning_tests.py:341` and `cli/issues/decisions.py:56,141`, both unconnected features. `scopes` is currently reachable only via direct Python/API `ActionSpec` construction (e.g. `queue_store._deserialize_action()` round-tripping a hand-written queue entry), not through any wired CLI path. No existing enqueue-time `ActionSpec`-shape validation function exists in `cli/queue.py`/`cli/action.py`/`cli/harness.py` to extend either (`_classify_action()` only classifies runner *kind* from a bare target string; `_deserialize_action()` performs no validation at all).
- **Guard-rejection propagation differs by caller** (codebase-analyzer) — relevant to Implementation Step 2 ("surface the same rejection message... wherever they already validate ActionSpec shape"):
  - `cli/queue.py:480` (`_drain_once()`): a non-`None` `RunnerResult.error` already forces `status = "failed"` and is persisted via `update_entry_result()` — the dispatch guard's message reaches the queue store with **no caller-side code change**.
  - `cli/harness.py:833/866/909/942`: all four feed into `_evaluate_and_report()` (`harness.py:659-796`), whose generic `if result.error is not None:` branch (line ~671) already prints/reports it — **no caller-side code change** needed for `ll-harness`.
  - `cli/action.py:250` and `:304` (`cmd_invoke()`): read only `result.exit_code`, never `result.error`. Irrelevant to this guard because `cmd_invoke()` never sets `scopes`; see Scope Boundaries.
- **Test patch-target precedent per runner** (codebase-pattern-finder, from existing CMD scope tests in `scripts/tests/test_runner_spec.py`): the "fails loud AND spawns nothing" assertion shape patches the runner-specific spawn primitive — `subprocess.Popen` for CMD (`test_cmd_dispatch_unknown_scope_fails_loud_and_spawns_nothing`, line 237), `subprocess.run` for SKILL/PROMPT dispatch (see `test_skill_dispatch_matches_legacy_shape`, line 122-124), and `little_loops.runner_spec.call_mcp_tool` for MCP (`test_mcp_dispatch_matches_legacy_shape`, line 181-183) — then asserts `mock.assert_not_called()`, `result.exit_code != 0`, and the offending value's substring in `result.error`. The new SKILL/PROMPT/MCP scope-guard tests (Implementation Step 3) should follow this same three-part shape with the runner-appropriate patch target.

## Implementation Steps

1. Add `scope_runner_error(spec: ActionSpec) -> str | None` to `runner_spec.py` returning the pinned message (see Decision Rules) when `spec.scopes is not None and spec.runner is not RunnerType.CMD`, else `None`. Export it.
2. In `run_action()` (`runner_spec.py:401-419`): after `handler = _DISPATCH.get(spec.runner)` and the existing LOOP `ValueError` raise (`:418`, untouched), call the helper and return `RunnerResult(stdout="", stderr="", exit_code=2, error=msg)` before `handler(spec)`. Do not write a `credential_scope_events` row.
3. In `queue_store.add_entry()` (`:316`): call the helper and raise `ValueError(msg)`. Leave `_deserialize_action()` permissive.
4. Tests: `test_runner_spec.py` skill/prompt/mcp fail-loud variants (patch `subprocess.run` for SKILL/PROMPT, `little_loops.runner_spec.call_mcp_tool` for MCP; assert not called, `exit_code == 2`, message substring, no audit row); queue tests for `add_entry()` rejection and for drain of a hand-written scoped entry landing `status: failed`.
5. Update `docs/reference/API.md` `ActionSpec`/`resolve_scopes` sections.
6. Run `python -m pytest scripts/tests/` and confirm `scopes=None` behavior (full inherit) is unchanged for every runner type.

## Impact

- **Priority**: P3 - Silent no-op on an isolation-promising field (no error, no audit row) is a correctness/trust gap, not a crash or data-loss risk; matches the sibling FSM-side fix (BUG-3400/ENH-3235) already shipped at this priority.
- **Effort**: Small - One pure helper called from `run_action()` and `add_entry()` plus a few new unit tests; mirrors the existing `_run_cmd()` `ValueError` -> `exit_code=2` fail-loud shape, no new abstractions.
- **Risk**: Low - Guard only triggers for the currently-broken combination (`scopes is not None` on a non-CMD runner); no caller passes `scopes` on SKILL/PROMPT/MCP today (see Dependent Files), so no existing behavior changes for `scopes=None`.
- **Breaking Change**: No - Only rejects a combination that was previously silently ignored; no passing call site is affected.

## Acceptance Criteria

- [ ] An `ActionSpec` with `runner in {SKILL, PROMPT, MCP}` and `scopes is not None` fails loud before spawn: `run_action()` returns `RunnerResult(exit_code=2, error=...)` without calling `handler(spec)` — no subprocess/skill/prompt/mcp dispatch occurs (option b is out of scope, see Scope Boundaries). A test for each non-CMD runner asserts the runner's spawn primitive is never called.
- [ ] The rejection `error` contains the pinned substring `declares 'scopes' but runner is` and names the runner value; tests assert it.
- [ ] Rejection writes no `credential_scope_events` row.
- [ ] `queue_store.add_entry()` raises `ValueError` with the same message for a scoped SKILL/PROMPT/MCP spec; a pre-existing hand-written scoped entry still deserializes, and draining it via `_drain_once()` lands `status: failed` with the message persisted and no spawn.
- [ ] `scopes=None` on every runner type is unchanged (full inherit).
- [ ] `docs/reference/API.md` states scopes are CMD-only and rejected elsewhere.
- [ ] Unit suite green: `python -m pytest scripts/tests/`.

## Relates To

- BUG-3400 (CMD-runner wiring; this issue was split out of its pre-implementation review on 2026-09-08)
- ENH-3234 (ActionSpec scopes), ENH-3235 (FSM shell-only validation), EPIC-3212

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-08 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-08T01:54:57 - `3710cbe8-3506-4b26-97b7-8bdd79bd826f.jsonl`
- `/ll:confidence-check` - 2026-09-08T01:41:55 - `5c412270-4e77-46e7-a79d-14f0a29f4fa0.jsonl`
- `/ll:wire-issue` - 2026-09-08T01:37:29 - `21067197-6e6b-4b15-a586-82cc6fecc33e.jsonl`
- `/ll:reconcile-issue` - 2026-09-08T01:08:17 - `fc5babbf-1cd9-49b0-a38d-5df21886a22b.jsonl`
- `/ll:refine-issue` - 2026-09-08T01:03:22 - `7bb68963-023d-49d0-b440-47cea1a0b4b2.jsonl`
- `/ll:refine-issue` - 2026-09-08T00:58:20 - `39586ada-651e-408c-877e-3fa446fcc2a1.jsonl`
- `/ll:format-issue` - 2026-09-08T00:46:13 - `8b45174b-5119-458a-8d19-241ee9b2e5a3.jsonl`
