---
id: ENH-2875
title: Give drift findings an action-severity and a throttle, and forbid opportunistic
  repair
type: ENH
parent: EPIC-2872
priority: P2
status: done
discovered_date: 2026-07-27
labels:
- verification
- ll-doctor
confidence_score: 92
outcome_confidence: 58
score_complexity: 8
score_test_coverage: 23
score_ambiguity: 20
score_change_surface: 7
decision_needed: false
size: Very Large
completed_at: '2026-07-28T07:57:30Z'
---

# ENH-2875: Give drift findings an action-severity and a throttle, and forbid opportunistic repair

Origin: ll-product #ENH-059

Parent EPIC: routed alongside this issue — "Self-describing drift and deprecation signals".

## Summary

`ll-verify-docs`, `ll-check-links`, and `ll-doctor --full` all report drift as an undifferentiated list. Nothing distinguishes a finding the tool can safely fix itself from one that needs a human, or from one that a specific other command already owns. The result is a wall of findings with no encoded next action, and no throttle — so the same low-value items resurface every run until they are tuned out entirely.

## Current Behavior

`ll-verify-docs`, `ll-check-links`, and `ll-doctor --full` each report drift as an undifferentiated list of mismatches/broken links, with no field indicating whether a finding is safe to auto-repair, needs a human, or is already owned by another command. `ll-doctor`'s existing `severity` field (`error`/`informational`, `scripts/little_loops/cli/doctor.py` lines 32-47) only governs `ll-doctor`'s own exit code — a different axis from action-severity. `main_verify_docs()`'s `--fix` path (`scripts/little_loops/cli/docs.py`) calls `fix_counts()` unconditionally for every mismatch, with no distinction by severity. No session-start/boot-time hook surfaces this drift today, and the existing `docs-sync.yaml` loop performs unconditional, undiscriminated repair on every raw-output match.

## Expected Behavior

Every drift finding carries a closed-vocabulary `auto`/`mention`/`route` action-severity. `--fix` (and any loop-driven repair) applies only to `auto` findings. `mention`/`route` findings are reported, not repaired, and are throttled to at most once per week per project via a state file, with an env-var opt-out that tests can set. A new session-start check surfaces this drift under a strict performance contract (no directory walk, no git call, no cross-workspace sweep) and, like other hooks, exits 0 on malformed input or internal error so it never fails the turn.

## Impact

Without this change, the same low-value drift findings resurface on every run with no encoded next action, training users to ignore the output entirely, and `docs-sync.yaml`'s unconditional repair keeps performing exactly the "opportunistic repair" this issue's hard rule is meant to forbid.

## Scope Boundaries

In scope: adding the action-severity field to `CountResult`/`VerificationResult`/`LinkResult`/`LinkOutcome`-adjacent findings, gating `--fix` to `auto` only, the weekly per-project throttle + opt-out, the new session-start drift check hook (with host-adapter wiring), and reworking `docs-sync.yaml` to respect the new severity model. Out of scope: changing `ll-doctor`'s existing `error`/`informational` severity axis (orthogonal, left as-is), and any new repair automation beyond what `auto`-severity already covers.

## Status

open — decision below must be resolved before implementation; see Session Log for refinement history.

## Reference pattern

In the reference pattern, staleness findings are shaped `{ id, artifact, path, severity, summary, fix }` where **severity names the action, not the badness**:

- `auto` — fixed silently on the next write to that file
- `mention` — state once
- `route` — name the command that owns the repair

Around that:

- `doctor --fix` applies **only** `auto` findings.
- Noise is throttled rather than suppressed: **one** aggregate directive per boot for the whole set, and `mention` / `route` findings repeat at most **once a week per project** via a small state file. An environment variable opts out entirely, and tests asserting on other boot output are required to set it.
- A hard behavioral rule accompanies it: **"Never repair drift as a side effect of a design task. A staleness finding is reported, not acted on, unless the user asks."**
- The boot-time check operates under an explicit **performance contract**: it "may only spend what a boot already spends: markdown already in memory, a bounded set of stats — no directory walks, no git, no cross-workspace sweep." This is called "a performance contract, not a preference".
- Where findings are surfaced through an edit-time hook, the hook's contract is **"never break a turn. Always exit 0"** — a thin adapter with a top-level catch that audit-logs and exits zero regardless, swallowing per-file detector exceptions into an empty result plus a flag rather than propagating. Budgets replace retries throughout: caps on files scanned, findings emitted, characters emitted, and a re-entrancy guard so the hook cannot recurse through child processes.

## Integration Map

### Files to Modify
- `scripts/little_loops/doc_counts.py` — `CountResult` (line 38) and `VerificationResult` (line 50) have no severity/action field today; `add_result()` (line 57) dumps every mismatch into one undifferentiated `mismatches` bucket. `fix_counts()` (line 408) repairs every mismatch unconditionally — needs an `auto`-only gate.
- `scripts/little_loops/link_checker.py` — `LinkOutcome` enum (line 46: `VALID`/`BROKEN`/`UNREACHABLE`/`IGNORED`) and `LinkResult` (line 61) classify network reachability, not action-severity or ownership; there is no `--fix` path in this tool at all today.
- `scripts/little_loops/cli/doctor.py` — `CheckResult` (lines 32-47) already has a two-tier `severity: Literal["error", "informational"]` field, but it only gates `ll-doctor`'s own exit code via `_exit_code_for()` (lines 98-101), not an `auto`/`mention`/`route` action model. `_full_docs_check()` (line 486) and `_full_check_links_check()` (line 760) collapse the entire underlying `VerificationResult`/`LinkCheckResult` into a single `CheckResult` note string, discarding per-finding granularity at the `--full` boundary — this is where a per-finding action-severity would need to be threaded through instead of collapsed. Note: this existing `severity` field is a *different axis* (governs `ll-doctor`'s own exit code) from the new `auto`/`mention`/`route` action-severity — do not conflate or overload the existing field name.
- `scripts/little_loops/cli/docs.py` — `main_verify_docs()` (around line 101) invokes `fix_counts()` unconditionally for every mismatch under `--fix` (line 66 defines the flag); needs the `auto`-only restriction from AC #1.
- No existing session-start drift check exists to modify — this is new code. `scripts/little_loops/hooks/session_start.py::handle()` currently only loads/merges config and renders project-context digest; it has no call into `doc_counts`/`link_checker`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/docs-sync.yaml` — **this is the codebase's current instance of the "opportunistic repair" pattern AC's hard rule forbids.** Its `route_results` state regex-matches the *raw combined text output* of `ll-verify-docs`/`ll-check-links` for `"FAIL|ERROR|BROKEN|MISMATCH"` (`output_contains`), and its `fix_docs` state then dispatches a free-form LLM prompt ("Fix all documentation discrepancies... Update counts... Fix broken internal links...") with zero severity discrimination — repairing everything unconditionally, including what will become `mention`/`route`-severity findings. Must be reworked to restrict itself to `auto`-severity findings (or gated through the new `--fix`) once the severity model exists; otherwise this loop keeps performing exactly the opportunistic repair the issue's hard rule prohibits. [Agent 2 finding]
- `scripts/little_loops/loops/lib/cli.yaml` — `ll_check_links` fragment (line 70) is the shared action `docs-sync.yaml` invokes for `ll-check-links`; also has a raw-output string dependency that action-severity output changes may break. [Agent 2 finding]
- `scripts/little_loops/hooks/__init__.py` — new SessionStart-adjacent drift-check hook needs an entry in `_dispatch_table()` (lines 130-157), the module docstring's routed-intent list (lines 10-36, per [[reference_dispatch_table_usage_banner]]), and `_INTENT_EVENT_NAME` (lines 66-77) for hook-event telemetry attribution — otherwise the new hook is invocable but untracked in `hook_events`. [Agent 2 finding]
- `hooks/hooks.json` (Claude Code) — add a new `SessionStart` array entry mirroring the existing two-entry pattern (lines 4-27, each pointing to a distinct adapter shell script) if the drift check ships as its own intent rather than folded into `session_start.py`. [Agent 2 finding]
- `scripts/little_loops/hooks/adapters/codex/hooks.json` — per this repo's CLAUDE.md, Codex's hook manifest lives here (not under `hooks/adapters/codex/`); needs the equivalent SessionStart wiring for host parity. [Agent 2 finding]
- `hooks/adapters/opencode/index.ts` — `session.created` handler (lines 50-63) dispatches through `spawnIntent("session_start", ...)`; if the drift check is a new intent (not folded into `session_start`), the `Intent` type union (line 19) and handler map need a new case for OpenCode parity. [Agent 2 finding]

### Similar Patterns
- `scripts/little_loops/cli/doctor.py` `CheckResult`/`_exit_code_for()` (lines 32-47, 98-101) — orthogonal `severity` field alongside `status`, with a single rollup function interpreting severity rather than each check deciding independently. Model the new `auto`/`mention`/`route` field the same way: closed `Literal[...]` vocabulary, one interpreting function.
- `scripts/little_loops/fsm/validation.py` `ValidationSeverity` enum (lines 40-44) / `ValidationError` (lines 47-66) — alternative `Enum`-based severity shape, set explicitly at each violation call site (e.g. line 589, line 705), consumed via `v.severity == ValidationSeverity.ERROR` filters.
- `scripts/little_loops/hooks/edit_batch_nudge.py::handle()` (lines 108-152) — canonical existing throttle/re-entrancy pattern: a per-session sticky `nudged` flag (lines 126-127, 147) in a `.ll/ll-edit-batch-state.json` state file, read via best-effort `_load_state()` (lines 86-92, returns `{}` on any error) and written via locked `atomic_write_json()` + `acquire_lock()` (`_persist_state()`, lines 95-105, 3s timeout, falls back to unlocked write on `TimeoutError`). This is the closest existing analogue for the "once a week per project" throttle state file AC #3 needs — reuse the state-file/lock/atomic-write shape, replacing the sticky-flag reset condition with a timestamp comparison.
- `scripts/little_loops/hooks/sweep_stale_refs.py::handle()` (lines 141-207) — canonical "catch everything, exit 0" hook contract: whole-body `try/except Exception: return LLHookResult(exit_code=0)`. Also demonstrates the report-vs-auto-fix toggle relevant to the no-opportunistic-repair rule: a config flag (`hooks.stale_ref_fix`, default `"report"`, opt-in `"auto"`) gates whether findings are only reported or actually repaired (`_auto_fix_file`, lines 102-138), plus a telemetry write wrapped in its own bare `except Exception: pass` (`_record_sweep`, lines 210-222).
- `scripts/little_loops/hooks/session_start.py` (lines 108-123) — existing opt-out env var convention: `LL_AUTOMATION` checked via `os.environ.get(...)`, wrapped in `contextlib.suppress(Exception)` around any secondary config read so a malformed config can't crash the gate. Related narrower vars: `LL_NON_INTERACTIVE` (line 183), `LL_HISTORY_DB` (lines 166-169). No existing "disable boot output for tests" var was found — model the new opt-out on this `LL_<PURPOSE>` convention.

### Tests
- `scripts/tests/test_cli_doctor.py`, `test_cli_doctor_full.py`, `test_cli_doctor_install_checks.py` — cover `main_doctor()`, `--full` aggregation adapters (`_full_docs_data`, etc.), and install-surface checks; will need new coverage for the action-severity field and `--fix` restriction to `auto`.
- `scripts/tests/test_cli_docs.py` — covers `main_verify_docs()`/`main_check_links()`; needs coverage for the new severity field on `CountResult`/`LinkResult` and the `--fix` gate. `test_fix_flag_with_mismatches` (~line 125) and `test_fix_flag_without_mismatches` (~line 153) assume `--fix` always calls `fix_counts()` for any mismatch — will break once `--fix` becomes `auto`-only unless their fixtures gain an explicit `auto` severity. [Agent 3 finding]
- `scripts/tests/test_link_checker.py` — covers `LinkOutcome` classification; needs extension for action-severity.
- `scripts/tests/test_hook_session_start.py`, `test_hooks_integration.py` — relevant models for the new session-start drift-check hook's tests (opt-out env var, exit-0 contract).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_doc_counts.py` — direct unit coverage of `doc_counts.py` (distinct from `test_cli_docs.py`, which only covers the CLI wrapper). `TestFixCounts` (lines 425-566: `test_fix_replaces_count`, `test_fix_multiple_mismatches_same_file`, `test_fix_multiple_files`, etc.) constructs `CountResult`/`VerificationResult`/calls `fix_counts()` directly with hand-built results — every fixture needs a severity field once `fix_counts()` becomes severity-aware, or these tests will start silently skipping fixes. [Agent 3 finding]
- `scripts/tests/test_edit_batch_hook.py` — pattern model for the new weekly throttle: `_Clock` fixture (lines 35-54) for deterministic time-based throttle testing, `_load_state()` assertions on persisted JSON (lines 195-222), and `test_state_write_failure_passes_through` (line 222) for the "state-file write fails, hook still exits 0" contract the new throttle needs. [Agent 3 finding]
- `scripts/tests/test_sweep_stale_refs.py` — pattern model for the new hook's exit-0/catch-everything contract: `TestSweepStaleRefsBaseline`'s no-op ladder (lines 67-105: no config / no target / nothing-to-do, each asserting `exit_code == 0`) and its config-driven mode-switch pattern (`hooks.stale_ref_fix`, line 162) as an analogue for the throttle opt-out toggle. [Agent 3 finding]
- `scripts/tests/test_drift_check.py` (new file, does not exist yet) — per this repo's `test_<hook_module_name>.py` naming convention for lifecycle sub-behaviors (matching `test_edit_batch_hook.py`/`test_sweep_stale_refs.py`, not the `test_hook_<intent>.py` convention used for top-level dispatcher intents), the new drift-check hook's tests belong here if implemented as its own module invoked from `session_start.py`. [Agent 3 finding]
- `scripts/tests/test_config_schema.py` — validates `config-schema.json`; needs new coverage for the throttle-interval and opt-out settings this issue adds. [Agent 1 finding]

### Documentation
- `docs/reference/CLI.md` — documents `ll-verify-docs`, `ll-check-links`, `ll-doctor` output; will need updating for the new severity field and `--fix` semantics.
- `docs/reference/CONFIGURATION.md` — would need a new section for the throttle/opt-out config.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — hook system docs; would need an entry for the new session-start drift-check hook and its exit-0/budget contract.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — documents `CheckResult`, `LinkResult`, `LinkOutcome`, `VerificationResult`, `CountResult` at the module-reference level; needs updating for the new severity/action field on each. [Agent 1 finding]
- `scripts/little_loops/loops/README.md` — loop catalog listing likely describes `docs-sync.yaml`'s current unconditional-fix behavior; needs updating once that loop is reworked to respect action-severity. [Agent 2 finding]
- `CONTRIBUTING.md` (line ~664) — the release checklist hand-asserts a specific `ll-doctor` output string ("{N} tool(s) discovered"); a `--full` output-shape change for action-severity should be checked against this. [Agent 2 finding]
- `scripts/little_loops/adapters/capabilities.py` (docstring ~line 20) — states `CheckResult` "mirrors `host_runner.CapabilityEntry`'s frozen-dataclass + closed-status shape"; this comment goes stale if `CheckResult`'s shape changes for the new severity axis. [Agent 2 finding]

### Configuration
- `scripts/little_loops/config-schema.json` — add the throttle-interval and opt-out settings here. Note: an existing `enable_scope_drift_check` key (~line 563, unrelated LLM-based scope-drift subsystem) creates a naming-collision risk with "drift" terminology — pick a distinguishable key name. [Agent 2 finding]
- `hooks/hooks.json` — register the new session-start drift-check hook if implemented as a `SessionStart` intent (parallel to how `sweep_stale_refs.py` is already wired to `SessionStart`, `hooks/hooks.json:16-26`, despite its `SessionEnd`-named module — see docstring re: Claude Code's ~1.5s `SessionEnd` kill ceiling).

_Wiring pass added by `/ll:wire-issue`:_
- `.gitignore` — verify the new weekly-throttle state file's path is covered by the existing broad `*-state.json` glob (line ~73) before assuming a new `.gitignore` rule is needed. [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- No tool currently has an action-severity axis distinguishing "auto-fixable" from "needs-human" from "owned-by-another-command." `ll-doctor`'s existing `severity` field (`error`/`informational`) only governs whether a check fails `ll-doctor`'s own exit code — a different axis entirely from the `auto`/`mention`/`route` model this issue proposes.
- No session-start/boot-time hook exists today that surfaces `ll-verify-docs`/`ll-check-links`/`ll-doctor` drift — AC #4's "session-start drift check" is new code, not an extension of an existing hook. The nearest boot-time precedent, `sweep_stale_refs.py`, sweeps stale cross-issue references, not doc/link drift, but is a good model for the exit-0 + report-vs-auto-fix-toggle contract.
- The per-project throttle state file this issue needs ("once a week per project") has one direct precedent in the codebase: `edit_batch_nudge.py`'s `.ll/ll-edit-batch-state.json` (sticky-flag shape, not timestamp-based) — the mechanics (locked atomic JSON write, best-effort fail-open read) transfer directly; only the throttle-decision logic (timestamp compare vs. sticky flag) needs to change.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Rework `scripts/little_loops/loops/docs-sync.yaml` — this loop is the codebase's live instance of opportunistic repair (`route_results` regex-matches raw output, `fix_docs` free-form-repairs everything). Restrict it to `auto`-severity findings once the severity model lands, or it keeps violating the hard rule this issue introduces.
2. Wire the new drift-check hook through all host adapters, not just `session_start.py`: `hooks/hooks.json` (Claude Code), `scripts/little_loops/hooks/adapters/codex/hooks.json` (Codex), `hooks/adapters/opencode/index.ts` (OpenCode), plus `scripts/little_loops/hooks/__init__.py`'s `_dispatch_table()`, docstring intent list, and `_INTENT_EVENT_NAME` if it ships as a distinct intent.
3. Pick a config key name for the throttle/opt-out settings that doesn't collide with the existing unrelated `enable_scope_drift_check` key in `config-schema.json`.
4. Update `docs/reference/API.md` and `scripts/little_loops/loops/README.md` alongside the already-planned CLI/CONFIGURATION/BUILTIN_HOOKS_GUIDE doc updates.
5. Add `scripts/tests/test_doc_counts.py` and `scripts/tests/test_config_schema.py` coverage, and create `scripts/tests/test_drift_check.py` for the new hook module, modeled on `test_edit_batch_hook.py` (throttle/state-file pattern) and `test_sweep_stale_refs.py` (exit-0/no-op-ladder pattern).

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Two structural decisions gate the implementation and were left as open "if X" branches in the Integration Map and Confidence Check Notes. Formatting them here so `decision_needed` is machine-checkable:

**Option A**: Ship the session-start drift check as its own hook intent — a new module (e.g. `scripts/little_loops/hooks/drift_check.py`, following the `test_drift_check.py` naming convention already anticipated in Tests) invoked alongside `session_start.py`, with its own entry in `_dispatch_table()`, the module docstring's routed-intent list, `_INTENT_EVENT_NAME`, `hooks/hooks.json`, the Codex adapter, and the OpenCode `Intent` type union.

> **Selected:** Option A — matches the `sweep_stale_refs.py` precedent of a distinct intent sharing the `SessionStart` host event, keeping the fragile `session_start.py` handler untouched.

**Option B**: Fold the drift check directly into the existing `scripts/little_loops/hooks/session_start.py::handle()`, alongside its current config-merge and project-context digest logic — no new dispatch-table entry or host-adapter wiring required, at the cost of growing an already-multi-purpose handler.

**Recommended**: Option A — the codebase's existing convention (`sweep_stale_refs.py`, wired as its own `SessionStart` intent despite being conceptually adjacent to session start) favors a distinct intent per concern, and the Integration Map's wiring-phase touchpoints (dispatch table, host adapters, intent list) were already scoped assuming a standalone module.

**Option C**: Config key name for the throttle/opt-out settings — must avoid colliding with the existing unrelated `enable_scope_drift_check` key (`scripts/little_loops/config-schema.json` ~line 563, an LLM-based scope-drift subsystem). Candidate: `hooks.doc_drift_throttle_days` (mirrors the `hooks.stale_ref_fix` naming precedent in `sweep_stale_refs.py`) paired with an `LL_DOC_DRIFT_DISABLE`-style opt-out env var (mirrors the `LL_AUTOMATION`/`LL_NON_INTERACTIVE`/`LL_HISTORY_DB` convention in `session_start.py`).

> **Selected:** Option C — `hooks.doc_drift_throttle_days` + `LL_DOC_DRIFT_DISABLE`; verified zero existing collisions and matches both the `hooks.*` dotted-namespace and `LL_<SUBSYSTEM>_<MODIFIER>` env-var conventions.

**Recommended**: Option C's candidate naming — `doc_drift`/`docs_drift` as the namespace prefix reads unambiguously distinct from `scope_drift` at a glance, satisfying the collision-avoidance requirement from the Integration Map.

### Anchor Corrections

_Added by `/ll:refine-issue` (gap-analysis) — line references verified against current codebase; minor drift found, noted here rather than editing the original Integration Map prose:_

> ⚠ `scripts/little_loops/cli/docs.py::main_verify_docs()` is defined at line 15, not ~101 (line 101 falls inside the function body, near the `--fix` handling).
> ⚠ `scripts/little_loops/fsm/validation.py` `ValidationSeverity`/`ValidationError` usage sites are at lines 586 and 702, not 589/705 (off by a few lines).
> ⚠ The "mirrors `host_runner.CapabilityEntry`'s frozen-dataclass + closed-status shape" phrase actually lives in `cli/doctor.py`'s `CheckResult` docstring (~line 36); `scripts/little_loops/adapters/capabilities.py` (~line 20) only references that precedent rather than restating it.

### Decision Rationale

_Added by `/ll:decide-issue`:_

Two decisions were resolved via codebase-evidence scoring (`ll:codebase-locator`/Explore
agents verified each candidate against actual repo state):

**Decision 1 — hook-intent shape: Option A selected** (own module vs. folding into
`session_start.py`).

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — own intent | 3 | 2 | 3 | 3 | 11/12 |
| B — fold into `session_start.py` | 0 | 2 | 1 | 1 | 4/12 |

Evidence: `sweep_stale_refs.py` is confirmed wired as its own distinct intent
(`_dispatch_table()` at `scripts/little_loops/hooks/__init__.py:150`, `_INTENT_EVENT_NAME`
at line 70) sharing the `SessionStart` host event rather than being folded into
`session_start.handle()` — despite the module even needing a `SessionEnd`→`SessionStart`
re-home for timeout reasons, it kept its own module/intent identity. All 10 entries in
`_dispatch_table()` are single-concern modules; no precedent exists for bolting an
unrelated concern onto an existing handler. `session_start.py` is also a fragile,
already-326-line critical-path handler (BUG-2730/ENH-2714 pruning-gate logic) — folding
drift-check logic in raises regression risk on every session.

**Decision 2 — config key naming: Option C selected** (`hooks.doc_drift_throttle_days` +
`LL_DOC_DRIFT_DISABLE`).

Evidence: grep confirms zero existing uses of `doc_drift`/`docs_drift` anywhere in
`scripts/`, config, or docs. The existing `enable_scope_drift_check`
(`scripts/little_loops/config-schema.json:563`) is a genuinely distinct LLM-based
scope-drift subsystem — no collision. The candidate matches the `hooks.*` dotted-namespace
convention (`hooks.stale_ref_fix` precedent) and the `LL_<SUBSYSTEM>_<MODIFIER>` env-var
convention (`LL_AUTOMATION`/`LL_NON_INTERACTIVE`/`LL_HISTORY_DB`).

## Acceptance criteria

- Every drift finding carries an action-severity, and `--fix` applies only auto-fixable ones.
- A routed finding names the command that owns its repair.
- Repeat findings are throttled per project, with a documented opt-out that tests can set.
- A session-start drift check performs no directory walk, no git call, and no cross-workspace sweep.
- A hook that surfaces findings exits 0 on malformed input and on internal error, and never fails the turn.


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-28_

**Readiness Score**: 92/100 → PROCEED
**Outcome Confidence**: 58/100 → LOW

### Concerns
- None — required sections are all present (`format-check` reports zero gaps) and both structural decisions (hook-intent shape, config key naming) are now resolved with recorded rationale.

### Outcome Risk Factors
- Broad breadth: touchpoints span 5+ core library files, 3 host adapters (Claude Code, Codex, OpenCode), the hook dispatch table, config schema, a loop YAML rework, and ~8 test files — deep per-site complexity is mostly mitigated by strong precedents (`edit_batch_nudge.py` throttle shape, `sweep_stale_refs.py` exit-0 contract), but the sheer count of dependent wiring sites still carries integration risk.
- New module, no existing tests to extend: the session-start drift-check hook (`drift_check.py`) is net-new code: `test_drift_check.py` does not yet exist and must be authored from the `test_edit_batch_hook.py`/`test_sweep_stale_refs.py` models rather than extended from an existing suite.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-28
- **Reason**: Issue too large for single session (score 11/11, Very Large)

### Decomposed Into
- ENH-2886: Add action-severity field to drift findings and gate --fix to auto
- ENH-2887: Thread action-severity through ll-doctor --full aggregation
- ENH-2888: New session-start drift-check hook with weekly throttle and opt-out
- ENH-2889: Rework docs-sync.yaml to respect action-severity model

## Session Log
- `/ll:issue-size-review` - 2026-07-28T08:00:00 - `f26799df-de87-40c6-90ea-225f55ba976e.jsonl`
- `/ll:confidence-check` - 2026-07-28T07:55:00 - `826728c6-13a6-4cad-a87d-549c15165f3b.jsonl`
- `/ll:decide-issue` - 2026-07-28T07:52:13 - `4ef8bacb-5c2c-48e6-a9cb-df62e31fee4c.jsonl`
- `/ll:refine-issue` - 2026-07-28T07:49:12 - `b0a8fe44-c46a-460e-acb6-f74a2e514b4f.jsonl`
- `/ll:confidence-check` - 2026-07-28T07:45:02 - `58786ea0-61bd-4f7d-9422-c0ca1f5040d3.jsonl`
- `/ll:wire-issue` - 2026-07-28T07:42:51 - `43684f63-0308-4498-aec4-6c75e97444b4.jsonl`
- `/ll:refine-issue` - 2026-07-28T07:35:21 - `bcb16e3c-19bb-4a4c-8a3b-d768cca504e4.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-07-28
- **Decomposed into**: ENH-2886, ENH-2887, ENH-2888, ENH-2889

Work for ENH-2875 is now carried by its child issues; this parent was closed by rn-decompose.
