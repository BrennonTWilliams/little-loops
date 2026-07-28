---
id: ENH-2888
title: New session-start drift-check hook with weekly throttle and opt-out
type: ENH
parent: ENH-2875
priority: P2
status: open
discovered_date: 2026-07-28
labels:
- verification
- ll-doctor
depends_on:
- ENH-2886
---

# ENH-2888: New session-start drift-check hook with weekly throttle and opt-out

## Parent Issue
Decomposed from ENH-2875: Give drift findings an action-severity and a throttle, and forbid opportunistic repair

## Summary

No session-start/boot-time hook exists today that surfaces `ll-verify-docs`/`ll-check-links` drift. This issue adds a new `drift_check.py` hook, wired as its own `SessionStart`-sharing intent (per the `sweep_stale_refs.py` precedent), that surfaces `mention`/`route`-severity findings (from ENH-2886) throttled to at most once per week per project via a state file, with an env-var opt-out that tests can set — all under a strict performance contract.

## Current Behavior

No session-start/boot-time hook exists today that surfaces `ll-verify-docs`/`ll-check-links`/`ll-doctor` drift. `scripts/little_loops/hooks/session_start.py::handle()` currently only loads/merges config and renders project-context digest; it has no call into `doc_counts`/`link_checker`.

## Expected Behavior

A new session-start check surfaces drift findings (`mention`/`route`-severity, from ENH-2886) under a strict performance contract (no directory walk, no git call, no cross-workspace sweep). Findings are throttled to at most once per week per project via a state file, with an env-var opt-out that tests can set. Like other hooks, it exits 0 on malformed input or internal error so it never fails the turn.

## Decision: Hook-Intent Shape (resolved by `/ll:decide-issue`)

**Selected: Option A** — ship as its own hook intent, a new module `scripts/little_loops/hooks/drift_check.py` invoked alongside `session_start.py`, with its own entry in `_dispatch_table()`, the module docstring's routed-intent list, `_INTENT_EVENT_NAME`, `hooks/hooks.json`, the Codex adapter, and the OpenCode `Intent` type union.

Evidence: `sweep_stale_refs.py` is confirmed wired as its own distinct intent (`_dispatch_table()` at `scripts/little_loops/hooks/__init__.py:150`, `_INTENT_EVENT_NAME` at line 70) sharing the `SessionStart` host event rather than being folded into `session_start.handle()` — despite the module even needing a `SessionEnd`→`SessionStart` re-home for timeout reasons, it kept its own module/intent identity. All 10 entries in `_dispatch_table()` are single-concern modules; no precedent exists for bolting an unrelated concern onto an existing handler. `session_start.py` is also a fragile, already-326-line critical-path handler (BUG-2730/ENH-2714 pruning-gate logic) — folding drift-check logic in raises regression risk on every session.

## Decision: Config Key Naming (resolved by `/ll:decide-issue`)

**Selected: Option C** — `hooks.doc_drift_throttle_days` + `LL_DOC_DRIFT_DISABLE`.

Evidence: grep confirms zero existing uses of `doc_drift`/`docs_drift` anywhere in `scripts/`, config, or docs. The existing `enable_scope_drift_check` (`scripts/little_loops/config-schema.json:563`) is a genuinely distinct LLM-based scope-drift subsystem — no collision. The candidate matches the `hooks.*` dotted-namespace convention (`hooks.stale_ref_fix` precedent) and the `LL_<SUBSYSTEM>_<MODIFIER>` env-var convention (`LL_AUTOMATION`/`LL_NON_INTERACTIVE`/`LL_HISTORY_DB`).

## Scope Boundaries

In scope: the new `drift_check.py` hook module, the weekly per-project throttle state file, the `LL_DOC_DRIFT_DISABLE` opt-out, the `hooks.doc_drift_throttle_days` config key, and host-adapter wiring across Claude Code/Codex/OpenCode (integration test and wiring are part of the same TDD cycle as the hook implementation — not split into a follow-up). Out of scope: the action-severity field itself (ENH-2886, a prerequisite), `ll-doctor --full` aggregation (ENH-2887), `docs-sync.yaml` (ENH-2889).

## Integration Map

- `scripts/little_loops/hooks/drift_check.py` — new module.
- `scripts/little_loops/hooks/__init__.py` — new entry in `_dispatch_table()` (lines 130-157), the module docstring's routed-intent list (lines 10-36, per [[reference_dispatch_table_usage_banner]]), and `_INTENT_EVENT_NAME` (lines 66-77).
- `hooks/hooks.json` (Claude Code) — new `SessionStart` array entry mirroring the existing two-entry pattern (lines 4-27).
- `scripts/little_loops/hooks/adapters/codex/hooks.json` — equivalent `SessionStart` wiring for Codex host parity.
- `hooks/adapters/opencode/index.ts` — `session.created` handler (lines 50-63) dispatches via `spawnIntent("session_start", ...)`; the `Intent` type union (line 19) and handler map need a new case for OpenCode parity.
- `scripts/little_loops/config-schema.json` — add `hooks.doc_drift_throttle_days` (~line 563 area, distinguishable from `enable_scope_drift_check`).
- `.gitignore` — verify the new weekly-throttle state file's path is covered by the existing broad `*-state.json` glob (line ~73) before assuming a new rule is needed.

## Similar Patterns

- `scripts/little_loops/hooks/edit_batch_nudge.py::handle()` (lines 108-152) — canonical existing throttle/re-entrancy pattern: a per-session sticky `nudged` flag in a `.ll/ll-edit-batch-state.json` state file, read via best-effort `_load_state()` (returns `{}` on any error) and written via locked `atomic_write_json()` + `acquire_lock()` (`_persist_state()`, 3s timeout, falls back to unlocked write on `TimeoutError`). Closest existing analogue for the "once a week per project" throttle — reuse the state-file/lock/atomic-write shape, replacing the sticky-flag reset condition with a timestamp comparison.
- `scripts/little_loops/hooks/sweep_stale_refs.py::handle()` (lines 141-207) — canonical "catch everything, exit 0" hook contract: whole-body `try/except Exception: return LLHookResult(exit_code=0)`. Also demonstrates the report-vs-auto-fix toggle: a config flag (`hooks.stale_ref_fix`, default `"report"`) gates reporting vs. repair, plus a telemetry write wrapped in its own bare `except Exception: pass` (`_record_sweep`).
- `scripts/little_loops/hooks/session_start.py` (lines 108-123) — existing opt-out env var convention: `LL_AUTOMATION`, wrapped in `contextlib.suppress(Exception)`. Related narrower vars: `LL_NON_INTERACTIVE` (line 183), `LL_HISTORY_DB` (lines 166-169). Model `LL_DOC_DRIFT_DISABLE` on this convention.

## Acceptance Criteria

- Repeat `mention`/`route`-severity findings are throttled to at most once per week per project, with `LL_DOC_DRIFT_DISABLE` as a documented opt-out that tests can set.
- The session-start drift check performs no directory walk, no git call, and no cross-workspace sweep.
- The hook exits 0 on malformed input and on internal error, and never fails the turn.
- The hook is wired through all host adapters (Claude Code, Codex, OpenCode) and the dispatch table.

## Tests

- `scripts/tests/test_hook_session_start.py`, `test_hooks_integration.py` — models for opt-out env var and exit-0 contract.
- `scripts/tests/test_edit_batch_hook.py` — `_Clock` fixture (lines 35-54) for deterministic time-based throttle testing, `_load_state()` assertions on persisted JSON, `test_state_write_failure_passes_through` for the "state-file write fails, hook still exits 0" contract.
- `scripts/tests/test_sweep_stale_refs.py` — `TestSweepStaleRefsBaseline`'s no-op ladder (exit_code == 0 for no config / no target / nothing-to-do), config-driven mode-switch pattern as an analogue for the throttle opt-out toggle.
- `scripts/tests/test_drift_check.py` (new file) — per this repo's `test_<hook_module_name>.py` naming convention, modeled on `test_edit_batch_hook.py`/`test_sweep_stale_refs.py`.
- `scripts/tests/test_config_schema.py` — new coverage for the throttle-interval and opt-out settings.

## Documentation

- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — entry for the new session-start drift-check hook and its exit-0/budget contract.
- `docs/reference/CONFIGURATION.md` — new section for the throttle/opt-out config.

## Session Log
- `/ll:issue-size-review` - 2026-07-28T08:00:00 - `f26799df-de87-40c6-90ea-225f55ba976e.jsonl`

## Status

open
