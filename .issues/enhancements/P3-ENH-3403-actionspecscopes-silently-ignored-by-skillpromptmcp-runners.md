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
---

# ENH-3403: ActionSpec.scopes silently ignored by skill/prompt/mcp runners

## Summary

`ActionSpec.scopes` (ENH-3234) is documented and wired for `RunnerType.CMD` only. `_run_skill()` and `_run_prompt()` in `scripts/little_loops/runner_spec.py` never read `spec.scopes`, so a skill or prompt `ActionSpec` that declares `scopes: [github]` runs its host-CLI child with full env inheritance and no `GH_CONFIG_DIR` redirect, with no error and no `credential_scope_events` row. This is the ActionSpec-side twin of the silent no-op BUG-3400 point 2 fixes on the FSM side (`scopes: []` on a non-shell state), where the answer was fail-loud at validation time.

## Current Behavior

- `_run_cmd()` resolves `spec.scopes` into `env_allow` (and, after BUG-3400, applies `gh_scope_extra()` + writes the audit row).
- `_run_skill()` and `_run_prompt()` build their env via `project_child_env(inv)` with no `env_allow` and ignore `spec.scopes` entirely. `_run_mcp()` also ignores it.
- `run_action()` dispatches without checking the runner/scopes combination, so nothing rejects the declaration.
- `queue_store` round-trips `scopes` for every runner type, so a queued skill/prompt entry with scopes persists and later dispatches unscoped.

## Expected Behavior

Pick one and test it:

(a) **Fail loud (recommended, matches ENH-3203 Decision #3 and BUG-3400 point 2):** `run_action()` returns `RunnerResult(exit_code=2, error=...)` without spawning when `spec.scopes is not None` and `spec.runner` is not `RunnerType.CMD`, naming the runner and stating that scopes are CMD-only. `ll-queue add` / `ll-action` / `ll-harness` surface the same message at enqueue/validate time where they already validate `ActionSpec` shape.

(b) **Honour it:** thread `env_allow` + `gh_scope_extra()` + `write_credential_scope()` into the skill/prompt runners the same way BUG-3400 does for CMD. Larger, and `resolve_host().build_*` invocations may need host-specific credential scopes (`claude-api`, etc.) declared alongside `github` to function at all, so this option needs a design pass first.

## Motivation

An operator who writes `scopes: [github]` on a queued skill or prompt task reasonably assumes the child is sandboxed the same way a CMD task is. Today that declaration is accepted, persisted, and then ignored at dispatch with no error and no audit row, so the credential-scoping feature (EPIC-3212) makes an isolation promise on a surface where it does nothing. The epic-level acceptance criterion that every declaring dispatch leaves a `credential_scope_events` row is also violated on these runners.

## Proposed Solution

Option (a) from Expected Behavior: a dispatch-time guard in `run_action()` that returns `RunnerResult(exit_code=2, error=...)` without spawning when `spec.scopes is not None` and `spec.runner is not RunnerType.CMD`, mirroring `_run_cmd()`'s existing `ValueError` fail-loud shape and the FSM shell-only rule in `structural_rules.py`. Option (b) stays open as a later design pass if skill/prompt scoping is actually wanted.

## Integration Map

### Files to Modify
- `scripts/little_loops/runner_spec.py` — `run_action()` dispatch guard (option a) or `_run_skill()`/`_run_prompt()`/`_run_mcp()` env construction (option b); `ActionSpec.scopes` field comment (line ~97) already says CMD-only.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/queue.py`, `scripts/little_loops/cli/harness.py`, `scripts/little_loops/cli/action.py` — `ActionSpec` construction sites; none pass `scopes` today.
- `scripts/little_loops/queue_store.py:240-262` — `scopes` round-trip, runner-agnostic.

### Similar Patterns
- `scripts/little_loops/fsm/validation/structural_rules.py:499-520` — shell-only `scopes:` check on `StateConfig` (the FSM-side precedent for option a).
- `scripts/little_loops/runner_spec.py:248-253` — `_run_cmd()`'s existing `ValueError` -> `exit_code=2` fail-loud shape.

### Tests
- `scripts/tests/test_runner_spec.py` — add `test_skill_dispatch_with_scopes_fails_loud_spawns_nothing` / prompt / mcp variants alongside the existing CMD scope tests (`test_cmd_dispatch_unknown_scope_fails_loud_and_spawns_nothing`).

### Documentation
- `docs/reference/API.md` `### resolve_scopes` / `ActionSpec` sections — state that scopes are CMD-only and rejected elsewhere.

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- [ ] An `ActionSpec` with `runner in {SKILL, PROMPT, MCP}` and `scopes is not None` never spawns a child unscoped: it either fails loud before spawn (option a) or is fully scoped (option b). A test pins the choice for each non-CMD runner.
- [ ] `scopes=None` on every runner type is unchanged (full inherit).
- [ ] Unit suite green: `python -m pytest scripts/tests/`.

## Relates To

- BUG-3400 (CMD-runner wiring; this issue was split out of its pre-implementation review on 2026-09-08)
- ENH-3234 (ActionSpec scopes), ENH-3235 (FSM shell-only validation), EPIC-3212

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-08 | Priority: P3
