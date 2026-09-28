---
id: BUG-3646
type: BUG
title: Learning-state /ll:explore-api remedy dispatched on bare SDK path under request_path
  sdk
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-28'
captured_at: '2026-09-28T22:51:25Z'
labels:
- loops
- multi-host
---

# BUG-3646: Learning-state /ll:explore-api remedy dispatched on bare SDK path under request_path sdk

## Summary

Under `request_path: sdk`/`batch` (state-level or `orchestration.request_path`) with the `anthropic` package importable and a resolvable credential, a `type: learning` state's `/ll:explore-api <target>` remedy is dispatched on the bare SDK path instead of the host CLI. The SDK path sends a tool-less single-turn request, so the skill never runs and the remedy silently no-ops.

## Current Behavior

- A `type: learning` state has no `action:` of its own. `FSMExecutor` runs the remedy as `self._run_action(f"/ll:explore-api {target}", _dc_replace(state, action_type="slash_command"), ctx)` (the learning-target loop, `# BUG:` comment above the call).
- `_run_action` resolves `request_path = self._resolve_request_path(state)` from that copied state. `_compute_request_path` downgrades sdk/batch to `cli` for a `/ll:` skill only when `_SKILL_INVOKE_RE.search(state.action)` matches — but the copy's `action` is `None`, so the downgrade never fires and the remedy goes to `_dispatch_live`.
- `_model_consumer_paths` (run-start preflight) makes the same computation for learning states, so `_preflight_model_hints` also resolves a learning state's hint against `anthropic-api` rather than the CLI host.

## Steps to Reproduce

1. Write a loop with a `type: learning` state (with `learning:` targets, at least one unproven) and `request_path: sdk` on the state or in `orchestration.request_path`.
2. Make sure the `anthropic` package is installed and a credential resolves (e.g. `ANTHROPIC_API_KEY` set).
3. Run the loop with `ll-loop run`.
4. Observe: no `request_path_downgrade` warning; the `/ll:explore-api` remedy goes out as a single-turn SDK request, no learning record is written, and the target blocks after its retries.

## Expected Behavior

- The `/ll:explore-api` remedy always runs on the host CLI (it needs the agentic tool loop), regardless of the configured request path, and emits the usual one-shot `request_path_downgrade` warning when sdk/batch was configured.
- `_model_consumer_paths` reports `["cli"]` for a learning state, so the preflight resolves its hint against the CLI host.

## Motivation

A learning state exists to prove unproven targets before work continues. On the SDK path the remedy never runs, so every unproven target burns its retries and blocks — the same failure the earlier `action_type="slash_command"` fix (the `# BUG:` comment at the call site) removed on the CLI path. It is silent apart from outcomes, and it gets likelier as `request_path: sdk` sees more use.

## Proposed Solution

Set the remedy text on the copy: `_dc_replace(state, action_type="slash_command", action=f"/ll:explore-api {target}")` at the dispatch site, and use an equivalent copy (e.g. `action="/ll:explore-api"`) in `_model_consumer_paths`'s learning branch, so `_SKILL_INVOKE_RE` matches in both places. Check that nothing else reads `state.action` from the copy in a way that changes (e.g. `action_start` payloads, interpolation).

## Program Design

### Types

- No new types.

### Signatures

- `_model_consumer_paths(self, state: StateConfig) -> list[Literal["cli", "sdk", "evaluator"]]` — unchanged signature; the learning branch builds its `slash_command` copy with `action="/ll:explore-api"` so `_compute_request_path` downgrades it to `cli`.
- `_run_action(self, action_template: str, state: StateConfig, ctx: InterpolationContext, on_usage: UsageCallback | None = None) -> ActionResult` — unchanged signature; the learning remedy caller passes a copy whose `action` is the remedy text.

### Call Path

- `FSMExecutor.run` → `FSMExecutor._preflight_model_hints` → `FSMExecutor._model_consumer_paths` → `FSMExecutor._compute_request_path`
- `FSMExecutor.run` → learning-target loop → `FSMExecutor._run_action` → `FSMExecutor._resolve_request_path` → `FSMExecutor._compute_request_path`

## Integration Map

- `scripts/little_loops/fsm/executor.py` — learning remedy dispatch, `_model_consumer_paths`, `_compute_request_path`
- `scripts/little_loops/fsm/validation/structural_rules.py` — ENH-3548's validate-time mirror for learning states must be updated to CLI-only when this lands
- Tests: learning-state tests in `scripts/tests/` (remedy under `request_path: sdk` with credentials patched available → dispatched via CLI; preflight hint resolved against the CLI host)

## Implementation Steps

1. Write failing tests first: a learning state under `request_path: sdk` with `_sdk_credentials_available` patched True dispatches the remedy through the action runner (not `_dispatch_live`), and `_model_consumer_paths` returns `["cli"]`.
2. Put the remedy text on the state copy at the dispatch site and in `_model_consumer_paths`'s learning branch.
3. If ENH-3548 has landed, switch its learning-state mirror to CLI-only and re-run its agreement test.

## Impact

- **Priority**: P3 - only affects learning states under a non-default `request_path`
- **Effort**: Small - two `_dc_replace` call sites plus tests
- **Risk**: Low - changes only the request path for the learning remedy
- **Breaking Change**: No

## Root Cause

- **Anchor**: `in method FSMExecutor._compute_request_path()` / the learning remedy call in the learning-target loop
- **Cause**: the skill-downgrade check inspects `state.action`, but the remedy's action text is passed separately to `_run_action` and never written onto the state copy.

## Acceptance Criteria

- [ ] With `request_path: sdk` and credentials available, a learning state's remedy is dispatched through the host CLI, not `_dispatch_live`.
- [ ] `_model_consumer_paths` returns `["cli"]` for a learning state under any request path.
- [ ] ENH-3548's validate-time mirror (if landed) treats learning states as CLI-only, and its validate-vs-preflight agreement test still passes.

## Related

- ENH-3548 — its validate-time mirror currently has to copy this behavior (learning states resolved on the configured path) to agree with the preflight.
- ENH-3547 — introduced `_compute_request_path` / `_model_consumer_paths`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-28 | Priority: P3
