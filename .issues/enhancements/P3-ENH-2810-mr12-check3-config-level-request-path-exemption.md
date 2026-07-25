---
id: ENH-2810
type: ENH
priority: P3
status: open
captured_at: "2026-07-25T15:15:00Z"
discovered_date: 2026-07-25
discovered_by: capture-issue
---

# ENH-2810: MR-12 Check 3 should honor config-level request_path sdk exemption

## Summary

`_validate_pruning_profile` Check 3 (ENH-2805) warns when a skill-invoking state has no resolvable `pruning_profile`, exempting states with `request_path: sdk`/`batch`. But the exemption only inspects the **state-level** `StateConfig.request_path` — it never sees the project's `orchestration.request_path` config default, which `FSMExecutor._resolve_request_path()` falls back to at execution time. A project with `orchestration.request_path: "sdk"` in `.ll/ll-config.json` gets MR-12 Check 3 warnings for states that will in fact dispatch via `_dispatch_live` (the SDK path), where pruning is a no-op and the warning's "pays the full static prefix" claim is false.

## Current Behavior

`ll-loop validate autodev` in a project configured with `orchestration.request_path: "sdk"` emitted five MR-12 Check 3 warnings (deposit_options, run_decide, run_spike, run_size_review, reconcile_current) even though every one of those prompt-mode states resolves to the SDK request path at runtime. `_validate_pruning_profile(fsm)` takes only the `FSMLoop`; the exemption at the Check 3 site (`fsm/validation.py`, the `state.request_path in ("sdk", "batch")` guard) cannot consult `BRConfig`.

## Expected Behavior

Validation-time exemption mirrors the executor's two-level resolution (`state.request_path` → `orchestration.request_path` config default → `"cli"`), so projects running the SDK path by config default don't get false-positive Check 3 warnings. States that explicitly set `request_path: cli` still warn regardless of config.

## Motivation

False-positive WARNs erode trust in the MR gate output and push users toward `pruning_profile_ok: true`, a blunt suppression that also silences the ERROR-tier Check 1 (tools-allowlist exclusion). Making Check 3's exemption match runtime resolution keeps the warning meaningful for CLI-path installs while staying silent where it's genuinely a no-op.

## Proposed Solution

Thread the orchestration config into validation, mirroring `_resolve_request_path`:

- Add an optional `orchestration_request_path: str | None = None` (or an `OrchestrationConfig`) parameter to `_validate_pruning_profile` / the top-level `validate()` entry, defaulting to `None` (current behavior — no exemption widening for callers that don't pass config).
- At the Check 3 exemption site, exempt when `state.request_path or orchestration_request_path` is in `("sdk", "batch")`.
- In the `ll-loop validate` CLI path, load the resolved `BRConfig` and pass `orchestration.request_path` through.
- Alternative (lighter touch): keep the warning but downgrade its message when the config default is sdk (e.g. "note: config request_path=sdk makes this a no-op at runtime"). Full exemption is preferred — a no-op warning is still noise.

Caveat: the executor downgrades sdk→cli at runtime when the `anthropic` package is unavailable (`_warn_request_path_downgrade`), so a config-level exemption is optimistic. That mirrors the existing state-level exemption's semantics, so no new inconsistency is introduced.

## Implementation Steps

1. Extend `_validate_pruning_profile` (and its caller in `validate()`) with an optional orchestration request-path input; keep default behavior unchanged when absent.
2. Apply the widened exemption only to Check 3 (Checks 1 and 2 are about allowlist/catalog consistency, not prefix cost — leave them as-is).
3. Wire `ll-loop validate` to resolve the project config and pass the value.
4. Update the MR-12 row in `.claude/CLAUDE.md` and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` to note the config-level exemption.
5. Tests: Check 3 silent with config-level sdk; still warns with config cli/unset; state-level `request_path: cli` override still warns under config sdk (or document chosen precedence); Checks 1–2 unaffected.

## Impact

- **Effort**: Small (single validation function + CLI wiring + tests)
- **Risk**: Low — exemption widening only; no new warnings introduced
- **Files**: `scripts/little_loops/fsm/validation.py`, `ll-loop` validate CLI entry, `scripts/tests/` validation tests, CLAUDE.md / HARNESS_OPTIMIZATION_GUIDE.md docs

## Context

Found while investigating five MR-12 Check 3 warnings on `autodev.yaml` in a project with `orchestration.request_path: "sdk"`; the immediate warnings were resolved by adding `pruning_profile` blocks to the five states (harmless on sdk, beneficial on cli), but the validator gap remains for any sdk-configured project.

## Session Log
- `/ll:capture-issue` - 2026-07-25T15:15:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe35d20e-b1d7-4e57-9b51-73d0a86b9144.jsonl`
