---
id: ENH-2888
title: New session-start drift-check hook with weekly throttle and opt-out
type: ENH
parent: EPIC-2872
priority: P2
status: done
discovered_date: 2026-07-28
completed_at: '2026-07-28T09:18:35Z'
labels:
- verification
- ll-doctor
depends_on:
- ENH-2886
relates_to:
- ENH-2875
confidence_score: 96
outcome_confidence: 72
score_complexity: 14
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 16
decision_needed: false
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

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Decision: drift-source for the session-start hook.** See original context under Integration Map → Codebase Research Findings ("Performance-contract tension with the only existing `mention`-severity source").

**Option A**: `drift_check.py` reads a stale/cached result written by a prior `ll-doctor --full` or `ll-verify-docs`/`ll-check-links` run. Confirmed via codebase analysis: no such cache currently exists anywhere in this chain — `doctor.py:494-513` (`_full_docs_data`) and `doctor.py:771-812` (`_full_check_links_data`) call `verify_documentation()`/`check_markdown_links()` synchronously and return in-memory dicts only; `_run_full_checks()` (`doctor.py:486-491`) never persists results. Both CLI wrappers (`doc_counts.py:252`, `link_checker.py:543`) only `json.dumps` to stdout. This option requires building new persistence machinery (e.g. a `.ll/doctor-full-cache.json` write path plus a freshness/staleness check in `drift_check.py`) — not reuse of an existing artifact — and still doesn't remove the live-HTTP cost problem for link_checker findings, just staleness-bounds it.

**Option B**: `drift_check.py` restricts itself to `doc_counts.py::verify_documentation()`'s cheap output only (the same call `doctor.py:498` already makes), mapping its `action_severity`/route findings directly. No new cache file, no invalidation logic, walk-light per the issue's performance contract. `link_checker`-sourced `mention` findings are explicitly deferred to a future issue once link_checker gains a non-live-HTTP cheap path.

> **Selected:** Option B — reuses `doctor.py:498`'s existing call directly, adds no new disk-state/cache design, and stays within the issue's own performance contract; Option A requires building persistence machinery this issue's research confirms doesn't exist anywhere in the chain.

**Recommended**: Option B — it requires zero new disk-state design, while Option A requires building the cache mechanism from scratch that this issue's own research confirms doesn't exist yet.

---

**Decision: OpenCode dispatch mechanism for the second SessionStart-sharing intent.** See original context under Integration Map → Codebase Research Findings ("OpenCode `Intent` type union does not yet include a `session_end`-style second SessionStart dispatch").

**Option A**: Add a second sequential `spawnIntent("drift_check", input, ctx.cwd)` call inside the existing `session.created` handler (`hooks/adapters/opencode/index.ts:50-63`), alongside the existing `spawnIntent("session_start", ...)` call, and extend the `Intent` union (line 19) to add `"drift_check"`. Confirmed safe by codebase analysis: each `spawnIntent` call spawns a fully independent `Bun.spawn` subprocess with its own stdin/stdout/exitCode (index.ts:27-47) — no shared mutable state, no output collision between sequential calls.

**Option B**: Restructure `session.created` to loop/dispatch over multiple intents per event, generalizing beyond the current one-intent-per-handler pattern.

> **Selected:** Option A — a second sequential `spawnIntent` call is confirmed safe (independent subprocess, no shared state), matches the file's existing straight-line MVP dispatch design, and Option B's generalization has no second caller to justify it today.

**Recommended**: Option A — matches the file's existing "MVP scope" design (index.ts:11) of straight-line sequential per-intent dispatch; each existing handler already hardcodes its own exit-code contract inline (e.g. session_start's block-on-2 vs pre_compact's success-on-2), which a generic loop would have to special-case anyway, so Option B's generalization has no other caller to justify it.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-28.

**Selected**: Option B (drift-source) and Option A (OpenCode dispatch mechanism)

**Reasoning**: For the drift-source decision, Option B reuses the existing `doctor.py:498` call to `verify_documentation()` directly with zero new disk-state design, while Option A would require building cache/invalidation machinery from scratch that this issue's own research confirmed does not exist anywhere in the codebase. For the OpenCode dispatch decision, Option A (a second sequential `spawnIntent` call) is confirmed safe by the existing subprocess-isolation model and matches the file's established one-intent-per-handler MVP pattern, whereas Option B's generalization has no second caller to justify the added complexity.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Drift-source: Option A (cached result) | 0/3 | 0/3 | 1/3 | 1/3 | 2/12 |
| Drift-source: Option B (doc_counts only) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| OpenCode: Option A (second spawnIntent call) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| OpenCode: Option B (generalized dispatch loop) | 1/3 | 1/3 | 1/3 | 1/3 | 4/12 |

**Key evidence**:
- Drift-source Option A: no cache artifact exists anywhere in the `doctor.py`/`doc_counts.py`/`link_checker.py` chain; would still leave the link_checker HTTP-cost problem staleness-bounded, not solved.
- Drift-source Option B: identical call already made at `doctor.py:498`; walk-light per the issue's own performance contract; link_checker `mention` findings explicitly deferred, not silently dropped.
- OpenCode Option A: each `spawnIntent` call spawns an independent `Bun.spawn` subprocess (`index.ts:27-47`) — no shared mutable state, no output collision.
- OpenCode Option B: no existing test harness for `hooks/adapters/opencode/index.ts`, so a generalized dispatch loop is greenfield surface with no precedent caller.

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/__init__.py` — `_USAGE` string (lines 108-112), the static comma-joined banner `main_hooks()` prints when invoked with no intent argument. Distinct from the docstring intent list, `_dispatch_table()`, and `_INTENT_EVENT_NAME` already named above — a fourth enumeration site in the same file that must also gain a `drift_check` entry, per the `dispatch_table_usage_banner` convention (not test-enforced, discoverability only). [Agent 1 + 2 finding]
- `hooks/adapters/codex/README.md` — has an explicit "Event → Intent Mapping (MVP)" table (lines 29-38) and a **Trust Model key list** (lines 147-157) enumerating every `SessionStart`/`PreCompact`/etc. trust-hash key by literal `group_index:handler_index`. Adding a second `SessionStart` hook group to the Codex `hooks.json` shifts/adds trust-hash keys this doc enumerates literally — currently missing entirely from the Integration Map. [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `## little_loops.hooks` section's adapter-integration bullet list (~line 8664) names each adapter shim literally (`session-start.sh`, `precompact.sh`, ...); needs the new drift-check shim added alongside the Codex `matcher: "startup"` note (~line 8666). [Agent 2 finding]
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — three distinct edit sites beyond a generic mention: the "Lifecycle at a Glance" table (lines 50-74, add a `drift-check` row under `SessionStart`), the "A Session from Hook's Perspective" narrative walkthrough (lines 77-112, add a `drift_check` step), and the "Configuration Reference" table (lines 453-474, add a row for `hooks.doc_drift_throttle_days` plus an opt-out callout for `LL_DOC_DRIFT_DISABLE` near the "Safe by Default" section, lines 116-128). [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — follow the `hooks.pre_compact.rubric` sub-section precedent (lines 1243-1256) for a new `hooks.doc_drift_throttle_days` entry, and update the raw-JSON example block starting at line 1260 (`"hooks": {`) to include the new key. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_intents.py` — `test_dispatch_table_merges_hook_intent_registry` (line 726) is the only test that directly calls `_dispatch_table()`; it doesn't enumerate the full key set so it won't break, but a parallel `test_dispatch_drift_check_happy_path` (following existing per-intent subprocess-dispatch tests in the same file, e.g. `test_dispatch_session_start_happy_path`) is needed for parity — no existing test proves the new intent is wired end-to-end. [Agent 2 + 3 finding]
- `scripts/tests/test_claude_code_adapter.py` — `test_hooks_json_registers_sweep_under_session_start` (lines 92-114) is direct precedent for a new `test_hooks_json_registers_drift_check_under_session_start`, asserting the new `SessionStart` command entry exists in `hooks/hooks.json`. [Agent 2 finding]
- `scripts/tests/test_hook_session_start.py` — `test_hooks_json_uses_matcher_startup` (line 68) asserts `"matcher": "startup"` holds on **every** Codex `SessionStart` group; the new Codex drift-check entry must include this matcher or this existing test breaks. [Agent 3 finding]
- No test enforces cross-consistency between `_dispatch_table()`, `_INTENT_EVENT_NAME`, and `_USAGE` — adding `drift_check` to only one or two of the three sites would pass all existing tests silently; consider a new assertion covering this. [Agent 3 finding]
- `hooks/adapters/opencode/index.ts` has no existing test scaffold at all (no Bun/Node test harness found for this file) — the OpenCode `Intent` union/`session.created` dispatch change is a greenfield test addition, not an update to an existing test. [Agent 3 finding]

## Similar Patterns

- `scripts/little_loops/hooks/edit_batch_nudge.py::handle()` (lines 108-152) — canonical existing throttle/re-entrancy pattern: a per-session sticky `nudged` flag in a `.ll/ll-edit-batch-state.json` state file, read via best-effort `_load_state()` (returns `{}` on any error) and written via locked `atomic_write_json()` + `acquire_lock()` (`_persist_state()`, 3s timeout, falls back to unlocked write on `TimeoutError`). Closest existing analogue for the "once a week per project" throttle — reuse the state-file/lock/atomic-write shape, replacing the sticky-flag reset condition with a timestamp comparison.
- `scripts/little_loops/hooks/sweep_stale_refs.py::handle()` (lines 141-207) — canonical "catch everything, exit 0" hook contract: whole-body `try/except Exception: return LLHookResult(exit_code=0)`. Also demonstrates the report-vs-auto-fix toggle: a config flag (`hooks.stale_ref_fix`, default `"report"`) gates reporting vs. repair, plus a telemetry write wrapped in its own bare `except Exception: pass` (`_record_sweep`).
- `scripts/little_loops/hooks/session_start.py` (lines 108-123) — existing opt-out env var convention: `LL_AUTOMATION`, wrapped in `contextlib.suppress(Exception)`. Related narrower vars: `LL_NON_INTERACTIVE` (line 183), `LL_HISTORY_DB` (lines 166-169). Model `LL_DOC_DRIFT_DISABLE` on this convention.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Performance-contract tension with the only existing `mention`-severity source**: `link_checker.py::check_markdown_links()` (lines 259-412) is currently the only function emitting `action_severity="mention"` findings (stamped on file-read errors at line 353, `unreachable` at line 395, `broken` at line 408) — but it does its own `base_dir.rglob("*.md")` recursive walk (line 284) plus live HTTP HEAD requests via a `ThreadPoolExecutor` (lines 358-410). This directly conflicts with the issue's "no directory walk, no git call, no cross-workspace sweep" performance contract (Expected Behavior / AC #2). `doc_counts.py::verify_documentation()` (lines 133-195) is walk-light (globs only `COUNT_TARGETS`' fixed dirs, reads 3 literal `DOC_FILES`) but, per its own docstring (lines 46-50), only ever emits `action_severity="auto"` today — so neither existing source currently satisfies both "produces `mention`/`route` findings" and "cheap enough for session-start" simultaneously. `scripts/little_loops/cli/doctor.py::_full_docs_data()`/`_full_check_links_data()` (lines 494-513, 771+) call these functions live with no caching layer, so there is no existing artifact `drift_check.py` could read instead of invoking the walk/network path itself. **See Option A/B decision under Proposed Solution → Codebase Research Findings.**
- **ENH-2886 dependency status**: confirmed `done` (`.issues/enhancements/P2-ENH-2886-add-action-severity-field-to-drift-findings-and-gate-fix-to-auto.md`) — `action_severity: Literal["auto", "mention", "route"]` already exists on both `CountResult` (`doc_counts.py:38-60`) and `LinkResult` (`link_checker.py:61-90`) in the working tree. `drift_check.py` is unblocked on this dependency.
- **Codex adapter matcher differs from Claude Code**: `scripts/little_loops/hooks/adapters/codex/hooks.json` currently has a single `SessionStart` entry with `matcher: "startup"` (not `"*"` like Claude Code's two entries in `hooks/hooks.json:4-27`) — the new drift-check entry in the Codex manifest should reuse `matcher: "startup"` to match the existing convention there, not blindly copy Claude Code's `"*"`.
- **OpenCode `Intent` type union does not yet include a `session_end`-style second SessionStart dispatch**: `hooks/adapters/opencode/index.ts`'s `Intent` union (line 19) is currently `"session_start" | "pre_compact" | "post_tool_use"` and the `"session.created"` handler (lines 50-63) calls `spawnIntent("session_start", ...)` once. Unlike Claude Code/Codex (which get a second hooks.json array entry), OpenCode parity requires either a second `spawnIntent("drift_check", ...)` call inside the same `session.created` handler, or extending the union and adding a sequential dispatch — this needs an explicit implementation decision, not just "mirror the existing case" as the Integration Map currently implies. **See Option A/B decision under Proposed Solution → Codebase Research Findings.**

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-28_

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 72/100 → LOW CONFIDENCE

Both open decisions flagged by the prior confidence check (drift-source choice, OpenCode dispatch mechanism) were resolved by `/ll:decide-issue` with evidence-backed rationale, resolving the prior blocking ambiguity.

### Outcome Risk Factors
- Broad enumeration across roughly 15 change sites (hook module, four dispatch-table registration sites, three host adapters, three docs, five test files) — each site is individually mechanical, but the count raises the chance one site is missed during implementation.
- No automated assertion checks cross-consistency across the four dispatch-table registration sites (`_dispatch_table()`, the module docstring list, `_INTENT_EVENT_NAME`, `_USAGE`) — a partial registration could pass all existing tests silently, per the issue's own wiring-pass finding.

## Session Log
- `/ll:manage-issue` - 2026-07-28T09:18:09Z - `d60ba261-e1e6-49da-a408-e89be9323ef5.jsonl`
- `/ll:confidence-check` - 2026-07-28T13:15:00 - `cee2b715-ead9-4fe1-807c-c59172e4443a.jsonl`
- `/ll:decide-issue` - 2026-07-28T08:58:42 - `5a1a19e1-e7b9-4a54-99e4-fd9c442bacf9.jsonl`
- `/ll:refine-issue` - 2026-07-28T08:56:25 - `01a9ed45-41ad-441e-9e71-2b1ee738630d.jsonl`
- `/ll:confidence-check` - 2026-07-28T12:56:00 - `cee2b715-ead9-4fe1-807c-c59172e4443a.jsonl`
- `/ll:wire-issue` - 2026-07-28T08:51:15 - `de7b27ff-8a02-48d2-bbb2-5a208ecdd9b8.jsonl`
- `/ll:refine-issue` - 2026-07-28T08:46:03 - `265a0187-483f-4b12-94b7-8d28465f68c4.jsonl`
- `/ll:issue-size-review` - 2026-07-28T08:00:00 - `f26799df-de87-40c6-90ea-225f55ba976e.jsonl`

## Status

open
