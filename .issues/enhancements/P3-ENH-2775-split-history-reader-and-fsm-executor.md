---
id: ENH-2775
status: open
priority: P3
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:26Z
discovered_by: audit-architecture
focus_area: large-files
labels:
- enhancement
- architecture
- refactoring
- auto-generated
parent: EPIC-2789
verify_verdict: VALID
---

# ENH-2775: Split history_reader.py and fsm/executor.py along concern boundaries

## Summary

Architectural issue found by `/ll:audit-architecture`. Two more top-tier large
files sit just behind the worst offenders and are accreting unrelated
concerns.

## Location

- **File**: `scripts/little_loops/history_reader.py` — 3,351 lines (was 3,099)
- **File**: `scripts/little_loops/fsm/executor.py` — 3,758 lines (was 2,915)
- **Modules**: `little_loops.history_reader`, `little_loops.fsm.executor`

## Finding

### Current State

- `history_reader.py`: 88 top-level defs mixing JSONL parsing, session
  discovery, querying, and formatting in one flat module.
- `fsm/executor.py`: the core state-machine step loop plus retry/429 handling,
  context-handoff detection, and session-reuse continuity chains (FEAT-2711)
  in one file; it is among the most-edited files in the repo, so every feature
  lands in the same hot file.

### Impact

- **Development velocity**: both files are recurring merge-conflict hotspots.
- **Maintainability**: concern boundaries exist informally (region comments,
  naming prefixes) but not structurally.
- **Risk**: medium — executor changes for one feature (e.g. retry) can
  regress another (e.g. handoff) with no module boundary to flag the overlap.

## Proposed Solution

Split each along its existing seams, preserving public import paths via
re-exports.

### Suggested Approach

1. `history_reader` → package: `parsing.py` (JSONL/event decoding),
   `discovery.py` (session file location), `queries.py`, `formatting.py`.
2. `fsm/executor.py` → extract retry/backoff policy and
   session-reuse/handoff handling into sibling modules (`fsm/retry.py`,
   `fsm/session_continuity.py`), leaving the step loop in `executor.py`.
3. Full test suite green with no importer changes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- The Suggested Approach's step 2 targets, `fsm/retry.py` and `fsm/session_continuity.py`, are largely already satisfied under different module names: rate-limit policy lives in `fsm/rate_limit_circuit.py` (`RateLimitCircuit`), handoff detection lives in `fsm/handoff_handler.py` (`HandoffHandler`), and continuity-summary compaction lives in `fsm/continuity.py` (`summarize_completed_state`) — all three are already imported and called into by `executor.py` today (see Integration Map -> Conventions in Force, and Program Design -> Call Path). What remains unextracted in `executor.py` is the *orchestration* glue around these existing collaborators (`_handle_rate_limit`, `_check_throttle`, `_handle_handoff`, `_compact_continuity_summary`) plus two other naming-prefix method groups the issue's Current State does not mention — `_prepatch_*` (~250 lines) and `_tamper_guard_*` (~110 lines) — for which no dedicated FSM-side collaborator module exists yet (see Program Design -> Signatures).
- The two completed EPIC-2789 siblings (ENH-2772 session_store split, ENH-2774 fsm/validation split) both landed as a **subpackage** — `name/__init__.py` plus concern submodules, with matching per-submodule test files — rather than sibling flat files kept alongside an unrenamed original (see Integration Map -> Conventions in Force for both `__init__.py` examples). The `history_reader` half of this issue can mirror that shape directly. The `fsm/executor.py` half is a different case: unlike `history_reader`'s flat functions or `validation.py`'s flat rule functions, `FSMExecutor` is a single class, so there are no free functions to lift out unchanged — whether the step-loop core should become `fsm/executor/__init__.py` (matching the sibling precedent) or stay a flat `executor.py` beside new collaborator modules is an implementation-shape choice the codebase convention does not resolve on its own.

## Impact Assessment

- **Severity**: Medium
- **Effort**: Large
- **Risk**: Medium
- **Breaking Change**: No

## Integration Map

### Codebase Research Findings

### Files to Modify
- `scripts/little_loops/history_reader.py` (3,585 lines currently — grown further since capture, was 3,351) — flat module; existing region comments already mark `Dataclasses` (L104), `Helpers` (L412), `Query API` (L456, spans ~1,930 lines through L2386 and covers at least 9 distinguishable query domains — not one homogeneous group), `Summary DAG retrieval` (L2389, FEAT-1712), `Project digest — section providers` (L2624, ENH-1907), `Hook execution telemetry` (L2833, ENH-2506), `ll-harness / eval outcome telemetry` (L2966).
- `scripts/little_loops/fsm/executor.py` (3,887 lines currently — grown further since capture, was 3,758) — a single `FSMExecutor` class (91 total defs, 65 methods) plus two small dataclasses (`RouteContext`, `RouteDecision`); unlike `history_reader.py` there are no free-standing functions to relocate — every candidate extraction is a bound method.

### Dependent Files (Callers/Importers)
- `history_reader` direct importers (8, via `ll-code importers-of`): `cli/history_context.py`, `cli/session.py`, `issue_history/collisions.py`, `issue_history/evolution.py`, `issue_history/rework.py`, `tests/test_assistant_messages.py`, `tests/test_enh_2505_subagent_runs.py`, `tests/test_history_reader.py`.
- `fsm/executor` direct importers (13, via `ll-code importers-of`): `fsm/__init__.py`, `fsm/persistence.py`, `extension.py`, and 10 test files including `test_fsm_executor.py`, `test_fsm_persistence.py`, `test_fsm_runners.py`.
- Transitive impact sets (`ll-code impact-of`) are larger: 16 files for `history_reader` (reaches `cli/__init__.py`, `issue_history/analysis.py`) and 31 files for `fsm/executor` (reaches `cli/loop/info.py`, `cli/loop/lifecycle.py`, `testing.py`, and the `rn-*` implementation-loop tests). The split must keep `from little_loops.history_reader import ...` and `from little_loops.fsm.executor import FSMExecutor, ...` importable unchanged across all of these — the re-export requirement the Proposed Solution already states.

_Wiring pass added by `/ll:wire-issue`:_
- `fsm/executor` direct-importer test files not previously named (7, confirmed via `ll-code -j importers-of` plus a grep of each for an actual `from little_loops.fsm.executor import ...` line): `scripts/tests/test_ll_loop_scaffold_verify.py`, `scripts/tests/test_ll_loop_display.py`, `scripts/tests/test_bug3032_wall_clock_cap.py`, `scripts/tests/test_feat3033_idle_timeout.py`, `scripts/tests/test_usage_journal.py`, `scripts/tests/test_learning_state.py`, `scripts/tests/test_host_guard.py` — these complete the "10 test files" count cited above (only 3 of the 10 were previously named).
- Full re-export symbol surface required from `little_loops.fsm.executor`, compiled from every importer's actual `import` line rather than just `FSMExecutor`: `FSMExecutor`, `ActionResult`, `ActionRunner`, `DefaultActionRunner`, `SimulationActionRunner`, `ExecutionResult`, `EventCallback`, `RouteContext`, `RouteDecision`, `derive_run_id`, `PROMPT_SIZE_WARN_EVENT`, `RATE_LIMIT_EXHAUSTED_EVENT`, `RATE_LIMIT_STORM_EVENT`, `RATE_LIMIT_WAITING_EVENT`, `STALL_DETECTED_EVENT`, `THROTTLE_HARD_EVENT`, `THROTTLE_STOP_EVENT`, `THROTTLE_WARN_EVENT` — plus three private module constants `scripts/tests/test_fsm_executor.py` imports mid-function (`_DEFAULT_RATE_LIMIT_RETRIES`, `_DEFAULT_API_ERROR_RETRIES`, `_DEFAULT_INFRA_RETRY_RETRIES`).
- `scripts/little_loops/extension.py:wire_extensions()` (L238-267) reaches past the import boundary into `FSMExecutor` instance internals directly — `fsm_executor._contributed_actions`, `fsm_executor._contributed_evaluators`, `fsm_executor._interceptors` — rather than through a public accessor. This is attribute-level coupling, not import-level: whichever module ends up owning these three attributes after the split, `wire_extensions()` must still be able to resolve them by the same names on the executor object it receives.

### Conventions in Force
- This codebase's established convention for splitting a god-module is a **subpackage**, not sibling flat files left alongside an unrenamed original: convert `name.py` -> `name/__init__.py` + concern submodules, with the `__init__.py` docstring documenting a "Package layout" (submodule -> concerns) section and a "Public API" (re-exported names) section — evidence: `scripts/little_loops/session_store/__init__.py:1-40` (ENH-2772, split into `db.py`/`lifecycle.py`/`queries.py`/`schema.py`/`writers.py`) and `scripts/little_loops/fsm/validation/__init__.py:1-30` (ENH-2774, split into `_base.py`/`structural_rules.py`/`evaluator_rules.py`/`meta_rules.py`/`reachability.py`/`shell_safety.py`) — both are completed sibling issues of this one under the same parent EPIC-2789.
- The same convention extends to tests: the flat test file is split one-for-one into per-submodule test files (`test_<pkg>_<submodule>.py`), not kept as one shared file — evidence: commit `9a4977a14` split `test_fsm_validation.py` (5,358 lines) into `test_fsm_validation_{evaluator_rules,meta_rules,reachability,shell_safety,structural}.py`.
- Where a concern already has a dedicated collaborator class, `FSMExecutor`'s remaining method is an orchestration wrapper around it, not the concern's implementation — evidence: `RateLimitCircuit` (`fsm/rate_limit_circuit.py`), `HandoffHandler` (`fsm/handoff_handler.py`), and `summarize_completed_state` (`fsm/continuity.py`) are already-extracted collaborators `FSMExecutor` imports and calls into (`fsm/executor.py:58`, `:39`, `:30`). The Proposed Solution's `fsm/retry.py` / `fsm/session_continuity.py` targets are largely already satisfied under these different module names — see the Proposed Solution findings below.
- No dedicated FSM-side tamper-guard or prepatch-orchestration module exists yet, though a deterministic prepatch-check *core* (no FSM/CLI knowledge) already lives at `scripts/little_loops/prepatch_check.py`, outside the `fsm/` package entirely — the `_prepatch_*`/`_tamper_guard_*` methods still in `executor.py` are the FSM-side orchestration glue around it, unextracted.

### Tests
- `scripts/tests/test_history_reader.py` — 3,221 lines, already organized into 25 domain-scoped `Test*` classes (e.g. `TestCostAttribution`, `TestWasteAttribution`, `TestHandoffFrequency`, `TestWorktreeSummary`, `TestSummaryDagRetrieval`) that map directly onto candidate submodule boundaries.
- `scripts/tests/test_fsm_executor.py` — 13,256 lines, all against the single `FSMExecutor` class; no existing per-concern class split the way `test_history_reader.py` already has, so a package split here would need a fresh test-file boundary decision rather than a mechanical one-class-per-file move.

### Documentation
- `docs/reference/API.md` — the `little_loops.history_reader` entry (line 54) and the `little_loops.fsm.executor`/`FSMExecutor` entries (line ~5474 module table, lines 6058-6116 class doc, plus roughly a dozen further `FSMExecutor._run_action`/`_drain_inbound`/`_finish`/`_resolve_request_path`/`_dispatch_live` call-outs scattered through the file) all cite the current flat-module layout and would need updating to the new package/module structure, matching what the issue's own Related Key Documentation row already states.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — carries structural, not just conceptual, file-path references that go stale on a split; this is the file the Related Key Documentation section already names generically, but without anchors. Specific spots: the Event Emitters table row `FSM Executor | fsm/executor.py | ...` (L597); the Read Path mermaid diagram's `HR[history_reader.py]` node (L723); the Components table row `history_reader.py | history_reader.py | Public read API: 10 query functions, 7 dataclasses, ...` (L751), which states counts that presuppose a single flat file; and prose path mentions of `scripts/little_loops/fsm/executor.py` at L904 and L1540.

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `history_reader.py` | Public functions/dataclasses (`find_user_corrections`, `search`, `cost_attribution`, `UserCorrection`, etc.) | PRESERVED | Split is purely structural; `history_reader/__init__.py` re-exports the full existing public surface per the Proposed Solution's own stated goal ("preserving public import paths via re-exports") |
| `fsm/executor.py` | `FSMExecutor` step-loop, public constructor/`run()` contract | PRESERVED | Same re-export requirement; the step loop's external behavior (states, routing, retry/handoff semantics) is not changing, only where its supporting code lives |

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- `FSMExecutor.run() -> None` (`fsm/executor.py:525`) — the step-loop entry point; the largest single method in the file (367 lines) and the part of the Proposed Solution that must stay in `executor.py`.
- `FSMExecutor._execute_state() -> None` (`fsm/executor.py:1795`) — per-step dispatch; the second-largest method (363 lines), also part of the retained step-loop core.
- `RateLimitCircuit.record_rate_limit() -> None` (`fsm/rate_limit_circuit.py`) — existing collaborator `FSMExecutor._handle_rate_limit` already delegates to; confirms rate-limit policy is not something this split still needs to extract.
- `HandoffHandler.handle() -> HandoffResult` (`fsm/handoff_handler.py`) — existing collaborator `FSMExecutor._handle_handoff` already delegates to; confirms handoff detection is not something this split still needs to extract.

### Types
- No new data shape is introduced. `RouteContext`/`RouteDecision` (small dataclasses in `fsm/executor.py`) and the 27 dataclasses in `history_reader.py` (`UserCorrection`, `FileEvent`, `SearchResult`, ... `ReviewEvent`) are relocated by the split, not changed.

### Signatures
- `history_reader.py` has no classes besides its dataclasses; its 75 module-level functions are grouped by naming/region rather than by class. The "Query API" region alone (L456-2386) spans roughly 35 of those 75 functions across at least 9 distinguishable domains — cost/waste attribution, usage aggregation, context-pressure curves, commit events, prompt-opt events, learning tests, lifecycle/handoff, worktree summaries, subagent tree/retries/budget, orchestration/loop-run aggregation, issue effort/velocity, session metadata, and grep/search formatting (`ll_grep`/`ll_expand`/`ll_describe`) — finer-grained than a single `queries.py` module would comfortably hold.
- `FSMExecutor` (`fsm/executor.py:197`) is a single class with 65 methods. The three largest are `run()` (L525-892, 367 lines), `_execute_state()` (L1795-2158, 363 lines), and `__init__()` (L197-468, 271 lines) — these implement the step-loop core the Proposed Solution says stays in `executor.py`.
- Two naming-prefix method groups already exist in `FSMExecutor` and are candidate collaborator extractions, mirroring the `RateLimitCircuit`/`HandoffHandler` precedent already present in the file, but the Current State section does not mention them: `_prepatch_*` (`_effective_prepatch_check_policy`, `_prepatch_git`, `_prepatch_step_diff`, `_prepatch_existing_forks`, `_prepatch_teardown`, `_check_prepatch_check`; L1546-1794, ~250 lines) and `_tamper_guard_*` (`_effective_tamper_guard_policy`, `_tamper_guard_candidate_paths`, `_tamper_guard_changed_files`, `_check_tamper_guard`; L1433-1545, ~110 lines).
- `FSMExecutor.run() -> None` (`fsm/executor.py:525`) — the retained step-loop entry point.
- `RateLimitCircuit.record_rate_limit(backoff_seconds: float) -> None` (`fsm/rate_limit_circuit.py:44`) — existing collaborator confirming rate-limit policy is already extracted.
- `HandoffHandler.handle(loop_name: str, continuation: str | None) -> HandoffResult` (`fsm/handoff_handler.py:68`) — existing collaborator confirming handoff detection is already extracted.

### Call Path
- `FSMExecutor._handle_rate_limit` (L3409) -> `RateLimitCircuit.record_rate_limit()` / `FSMExecutor._exhaust_rate_limit()` -> `FSMExecutor._interruptible_sleep()` / `FSMExecutor._emit()` — confirms rate-limit *policy* already lives in `RateLimitCircuit` (`fsm/rate_limit_circuit.py`); `_handle_rate_limit` is orchestration glue only.
- `FSMExecutor._handle_handoff` (L781) -> `HandoffHandler.handle()` -> `FSMExecutor._emit()` — confirms handoff *detection* already lives in `HandoffHandler` (`fsm/handoff_handler.py`); `_handle_handoff` is orchestration glue only.
- `FSMExecutor._compact_continuity_summary` (L2503) -> `FSMExecutor._get_br_config()`, `summarize_completed_state()` (`fsm/continuity.py`) — confirms continuity-summary compaction already lives outside the class; `FSMExecutor` only carries `self._continuity_summary` state across steps (FEAT-2711).

### Decision Rules
N/A — no new decision logic; this issue is a structural module split introducing no new gate, threshold, or classification rule.

## Related Key Documentation

- `docs/reference/API.md` — documents `history_reader` and `fsm/executor` module-by-module; splitting either file requires updating those entries to match the new package/module layout.
- `docs/ARCHITECTURE.md` — describes the FSM loop engine and Sequential Mode (`ll-auto`) internals that `fsm/executor.py` and `history_reader.py` implement; a structural split of either is exactly the kind of architecture change this doc covers.

## Verification Notes

- 2026-08-16: Core issue still real; both files have grown further since capture
  rather than shrunk — `history_reader.py` is now 3,351 lines (was 3,099) and
  `fsm/executor.py` is now 3,758 lines (was 2,915). Verdict: OUTDATED (line
  counts updated above).

## Session Log
- `/ll:wire-issue` - 2026-08-29T23:19:32 - `3877ebdc-d9d3-4449-9bcf-1a7f4ef3ce26.jsonl`
- `/ll:refine-issue` - 2026-08-29T23:06:34 - `ed9b2f61-6325-4a0c-aa2f-badcd208e1b6.jsonl`
- `/ll:verify-issues` - 2026-08-16T16:40:49 - `6160b806-1147-4cb9-be05-f6b3edf1653b.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:57 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P3
