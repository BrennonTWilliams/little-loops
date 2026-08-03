---
id: BUG-3029
priority: P3
type: BUG
parent: BUG-3027
status: open
discovered_date: 2026-08-03
discovered_by: issue-size-review
confidence_score: 68
outcome_confidence: 59
score_complexity: 18
score_test_coverage: 15
score_ambiguity: 8
score_change_surface: 18
blocked_by:
- BUG-3028
---

# Audit and fix unguarded `gather_all_issue_ids()` call sites that crash CLI commands on exception

## Summary

Decomposed from BUG-3027: the `/ll:wire-issue` pass on BUG-3027 found that 5
call sites build `all_known_ids` via `gather_all_issue_ids()` with **no
try/except at all** around the call, unlike the other three call sites
BUG-3027 discusses. An exception there is unhandled and crashes the CLI
command outright — a strictly worse failure mode than the "spurious
warning" symptom BUG-3027 was originally filed for, and severe enough to
warrant its own fix and priority rather than folding into that P4 cosmetic
issue.

## Parent Issue

Decomposed from BUG-3027: ll-sprint prints "depends_on unknown issue" for a
dependency that exists and is done.

## Current Behavior

Confirmed by direct read (not just grep) in BUG-3027's wiring pass — each of
the following calls `gather_all_issue_ids()` with no surrounding
try/except, so any exception it raises propagates unhandled and crashes the
command:

- `scripts/little_loops/cli/sprint/run.py:499-502`
- `scripts/little_loops/cli/sprint/show.py:183-187`
- `scripts/little_loops/cli/sprint/manage.py:92-96`
- `scripts/little_loops/cli/sprint/edit.py:105-114`
- `scripts/little_loops/cli/deps.py:385` (the nearby `try/except` at
  lines 379-384 guards only the `BRConfig` construction, not the
  `gather_all_issue_ids()` call itself)

By contrast, `cli/issues/link.py:223-228`, `cli/issues/sequence.py:74-81`,
`cli/issues/next_issue.py:67-74`, and `cli/issues/next_issues.py:57-64`
already wrap the call in `try/except Exception: pass`/`all_known_ids =
None` and are correctly unaffected by this crash risk.

## Expected Behavior

`ll-sprint run/show/manage/edit --revalidate` and the `cli/deps.py` command
should degrade gracefully (matching the fallback shape used elsewhere in
this call-site family — see BUG-3028) rather than crashing outright if
`gather_all_issue_ids()` raises.

## Steps to Reproduce

1. Patch/mock `little_loops.dependency_mapper.gather_all_issue_ids` to raise
   an exception.
2. Run any of `ll-sprint run`, `ll-sprint show`, `ll-sprint manage`,
   `ll-sprint edit --revalidate`, or the relevant `ll-deps` command.
3. Observe the command crashes with an unhandled traceback instead of
   degrading gracefully.

## Proposed Solution

1. Wrap each of the 5 unguarded `gather_all_issue_ids()` calls
   (`cli/sprint/run.py:499-502`, `cli/sprint/show.py:183-187`,
   `cli/sprint/manage.py:92-96`, `cli/sprint/edit.py:105-114`,
   `cli/deps.py:385`) in a `try/except Exception` matching the fallback
   convention chosen for BUG-3028 (or the existing `sprint.py:378`
   `active_ids_set` pattern, whichever is decided as the shared
   convention), so an exception here degrades instead of crashing.
2. Add a test per call site (or a parametrized test covering all 5) that
   forces `gather_all_issue_ids` to raise and asserts the CLI command no
   longer crashes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Confirm BUG-3028's fallback-convention decision has landed (`.ll/decisions.d/`) before implementing — same convention must apply to all 5 sites
- Add tests in `scripts/tests/test_sprint.py::TestSprintErrorHandling` (run.py), `scripts/tests/test_cli_sprint_show.py::TestCmdSprintShow` (show.py), `scripts/tests/test_sprint.py::TestSprintAnalyze` (manage.py), `scripts/tests/test_sprint.py::TestSprintEdit` (edit.py --revalidate), `scripts/tests/test_cli_deps.py` (deps.py) — patch `little_loops.dependency_mapper.gather_all_issue_ids` with `side_effect=RuntimeError(...)` per site
- Add a `CHANGELOG.md` entry on close, following the BUG-690 precedent format

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- The 5 unguarded sites are the only call sites in the codebase with zero try/except around `gather_all_issue_ids()`; the 4 already-guarded `cli/issues/*` sites, `issue_manager.py:1509-1521`, and `issue_parser.py:2135-2142` all fall back to `None`, while `sprint.py:372-379` falls back to the already-computed `active_ids_set` local instead. No shared helper function exists to wrap this try/except — each call site (guarded or not) implements it inline.
- No existing test in the codebase forces `gather_all_issue_ids` to raise via `side_effect=Exception(...)`/`side_effect=RuntimeError(...)` and asserts CLI graceful degradation — this issue's test additions would be the first of that shape for this call-site family. The codebase's general convention for forcing an exception path in a mocked dependency is `patch("<module>.<callable>", side_effect=RuntimeError("..."))` (see `scripts/tests/test_issue_manager.py:3818-3821`).

## Files to Modify

- `scripts/little_loops/cli/sprint/run.py:499-502`
- `scripts/little_loops/cli/sprint/show.py:183-187`
- `scripts/little_loops/cli/sprint/manage.py:92-96`
- `scripts/little_loops/cli/sprint/edit.py:105-114`
- `scripts/little_loops/cli/deps.py:385`
- Corresponding test files (e.g. `scripts/tests/test_cli_sprint.py`,
  `scripts/tests/test_cli_deps.py` or equivalent)

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- `run.py:499-502` — two earlier gate calls (`_run_learning_gate_preflight`, `_run_epic_base_preflight`, lines 488-496) already return non-zero exit codes and `return` before reaching this call; a fix does not need to interact with those gates
- `show.py:183-187` — the call happens before the `if getattr(args, "json", False):` early-exit (line 199); any fallback must produce identical `dep_graph` behavior for both the text-rendered and JSON output paths, since both consume the same graph
- `manage.py:92-96` — `invalid` (issues not found) is computed and logged as a warning before this call (line 80/83), independent of it; no interaction needed
- `edit.py:105-114` — the revalidate block's own trailing `invalid` warning (lines 123-125) runs *after* the `gather_all_issue_ids`/`analyze_dependencies`/`_render_dependency_analysis` sequence; a fix must decide whether that trailing block still executes when the guarded call degrades rather than crashes
- `deps.py:385` — this is the only site with an *adjacent* (not enclosing) try/except: lines 379-384 already catch `_BRConfig(...)` construction and fall back to `_dm_config = None`. A fix must choose between extending that existing try block to also cover line 385, or adding a second independent try/except immediately after it — `_dm_config` is reused right after (line 388) and already tolerates `None`, so guarding is localized to the `all_known_ids` assignment alone
- BUG-3028 (the blocking dependency) targets two *different* call sites — `issue_manager.py:1509-1521` and `issue_parser.py:2118-2126` — not any of these 5; its role here is only to pick the shared fallback-convention that must then be applied identically across the whole family, confirmed still unresolved (BUG-3028 `status: open`, zero decision fragments in `.ll/decisions.d/` or `.ll/decisions.yaml` reference it)

### Files to Modify
- `scripts/little_loops/cli/sprint/run.py:499-502` — unguarded `gather_all_issue_ids()` call inside the module-level `ll-sprint run` command function; result feeds `analyze_dependencies(...)` (line 511, gated by `not args.skip_analysis`) and unconditionally `DependencyGraph.from_issues(issue_infos, all_known_ids=all_known_ids)` (line 516)
- `scripts/little_loops/cli/sprint/show.py:183-187` — unguarded call inside `_cmd_sprint_show()`; feeds `DependencyGraph.from_issues(...)` at line 190, gating `has_cycles`/`get_execution_waves`/`refine_waves_for_contention` for the whole command including the JSON early-exit path
- `scripts/little_loops/cli/sprint/manage.py:92-96` — unguarded call inside `_cmd_sprint_analyze()`; feeds `DependencyGraph.from_issues(...)` at line 99, driving the file-conflict/contention analysis
- `scripts/little_loops/cli/sprint/edit.py:105-114` — unguarded call inside the `if args.revalidate:` branch; feeds `analyze_dependencies(issue_infos, issue_contents, all_known_ids=_all_known_ids)` at lines 116-118. Scoped to `--revalidate` only — the earlier prune/save logic (lines 80-98) runs before this block and is unaffected
- `scripts/little_loops/cli/deps.py:385` — the nearby `try/except` at lines 379-384 guards only `_BRConfig(...)` construction (falling back to `_dm_config = None`); `gather_all_issue_ids(issues_dir, config=_dm_config)` on line 385 sits outside that block. Result feeds `dep_config = _dm_config.dependency_mapping if _dm_config else None` (line 388) and `analyze_dependencies(issues, issue_contents, completed_ids, all_known_ids, config=dep_config)` (lines 390-393)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/dependency_graph.py:60,111,129,143` — `DependencyGraph.from_issues()`'s `all_known_ids` parameter; `all_known_ids is None` short-circuits all three unknown-issue checks to always warn, so the guard's fallback value (not just "does it crash") changes downstream warning behavior
- `scripts/little_loops/dependency_mapper/analysis.py:518-533` — `analyze_dependencies()` accepts the same `all_known_ids: set[str] | None = None` contract

### Conventions in Force
- The 4 already-guarded `cli/issues/*` call sites all predeclare `all_known_ids: set[str] | None = None` before the `try`, catch bare `Exception`, and fall back to `None` with no logging — evidence: `cli/issues/link.py:223-228`, `cli/issues/sequence.py:74-81`, `cli/issues/next_issue.py:67-74`, `cli/issues/next_issues.py:57-64`
- `issue_manager.py:1509-1521` uses the same shape but logs `self.logger.debug(...)` in the except block instead of a bare `pass`
- `sprint.py:372-379` diverges: on exception it falls back to the already-computed `active_ids_set` local instead of `None` — a narrower substitute (active issues only) rather than a full degrade, with a comment explaining why `all_known_ids` must span every issue on disk, not just active ones
- These three fallback shapes disagree and neither BUG-3029 nor BUG-3028 has picked one yet — BUG-3029's own Proposed Solution defers this choice to "whichever is decided" for BUG-3028
- No shared helper function wraps this try/except anywhere in the codebase (`gather_all_issue_ids` is defined once at `dependency_mapper/operations.py:362`); each of the 9 call sites (4 guarded `cli/issues/*` + `issue_manager.py` + `issue_parser.py` + `sprint.py` + the 5 unguarded sites) implements its own inline try/except (or lacks one)

### Tests
- No existing test forces `gather_all_issue_ids` to raise and asserts CLI graceful degradation for any of the 5 unguarded sites or the 4 guarded ones
- `scripts/tests/test_cli_sprint.py:864,1122` patches `gather_all_issue_ids` for the success path (`return_value=set()`), not `side_effect=Exception(...)`
- The codebase's general convention for forcing an exception path in a mocked dependency is `patch("<module>.<callable>", side_effect=RuntimeError("..."))` — see `scripts/tests/test_issue_manager.py:3818-3821`

_Wiring pass added by `/ll:wire-issue`:_
- **Corrected test-file mapping per site** (the candidate list above conflated `manage.py`/`edit.py` coverage with `test_cli_sprint_commands.py`, which actually only covers `_cmd_sprint_create`/`_cmd_sprint_delete`/`_cmd_sprint_list` — its own header comment at lines 6-11 cross-references the real split):
  - `run.py` → `scripts/tests/test_sprint.py::TestSprintErrorHandling` (lines 654-833; closest analog: `test_unexpected_exception_returns_1`) and `scripts/tests/test_cli_sprint.py`
  - `show.py` → `scripts/tests/test_cli_sprint_show.py::TestCmdSprintShow` (lines 366+, e.g. `test_show_json_output` at 421-440)
  - `manage.py` → `scripts/tests/test_sprint.py::TestSprintAnalyze` (line 1880) — **not** `test_cli_sprint_commands.py`
  - `edit.py --revalidate` → `scripts/tests/test_sprint.py::TestSprintEdit` (line 1448) — **not** `test_cli_sprint_commands.py`; none of its existing ~13 tests set `revalidate=True`, confirm when adding
  - `deps.py` → `scripts/tests/test_cli_deps.py::TestDepsAnalyzeFormat` / `TestDepsValidateOutput` (argv-level, e.g. lines 107-117)
- Additional test files touching this call-site family not previously listed: `scripts/tests/test_deps_cli.py` (alternative CLI deps test module), `scripts/tests/test_sprint_integration.py`, `scripts/tests/test_dependency_mapper.py`, `scripts/tests/test_dependency_graph.py` — none currently force a `gather_all_issue_ids` exception; check for overlap before adding new tests
- **Confirmed mock patch target**: new tests must patch `little_loops.dependency_mapper.gather_all_issue_ids` (the re-imported path used at call sites and in existing tests, e.g. `sprint.py:374`'s `from little_loops.dependency_mapper import gather_all_issue_ids`), not `little_loops.dependency_mapper.operations.gather_all_issue_ids`
- No existing test asserts current crash behavior for any of the 5 sites, so no existing test needs updating — only new tests to add

### Documentation
- No dedicated docs page for this call-site family beyond `docs/ARCHITECTURE.md`/`docs/reference/API.md`'s general `dependency_mapper` coverage; no update required by this fix

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — add a `### Fixed` entry on close, following the BUG-690 precedent entry ("`IssueManager`: too-narrow except clause in `gather_all_issue_ids`") for this call-site family; add under a concrete version section per project convention, not `[Unreleased]`
- **Sequencing dependency**: no decision fragment exists yet in `.ll/decisions.d/` recording BUG-3028's fallback-convention choice (`None` vs. an `active_ids_set`-like local) — BUG-3029's implementation is blocked on that decision landing first, since the same convention must apply identically across `DependencyGraph`-only sites (`show.py`, `manage.py`) and `analyze_dependencies`-consuming sites (`run.py`, `edit.py`, `deps.py`) to avoid divergent warning behavior

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

### Types
- `all_known_ids: set[str] | None` — the value each call site produces; `DependencyGraph.from_issues()` and `analyze_dependencies()` both key on `None` vs a populated `set[str]` to distinguish "unknown, always warn" from "known, only warn if truly dangling" (`dependency_graph.py:60,111,129,143`; `dependency_mapper/analysis.py:518-533`)

### Signatures
- `gather_all_issue_ids(issues_dir: Path, config: BRConfig | None = None) -> set[str]` — `dependency_mapper/operations.py:362`
- `DependencyGraph.from_issues(issues, all_known_ids: set[str] | None = None)` — `dependency_graph.py:60` (consumer of the guarded value at 4 of the 5 sites)
- `analyze_dependencies(issues, issue_contents, all_known_ids=None, config=None)` — `dependency_mapper/analysis.py:518` (consumer at `run.py:511`, `edit.py:116-118`, `deps.py:390-393`)

### Call Path
`ll-sprint run/show/manage/edit --revalidate` or `ll-deps <subcommand>` -> unguarded `gather_all_issue_ids()` call -> (on exception, currently) unhandled propagation out of the CLI entry point; (once fixed) `except Exception` -> fallback value (convention TBD, see Proposed Solution) -> `DependencyGraph.from_issues(...)` / `analyze_dependencies(...)` -> unknown-issue warning logic (`dependency_graph.py:111,129,143`)

## Impact

- **Priority**: P3 - An unhandled exception here crashes CLI commands
  outright, a more severe failure mode than BUG-3027's original log-noise
  symptom.
- **Effort**: Small-Medium - 5 symmetric try/except additions plus tests;
  mechanical once the shared fallback convention is decided (see BUG-3028).
- **Risk**: Low - additive defensive handling, no behavior change on the
  non-exception path.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-08-03 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` — 2026-08-03:_

**Readiness Score: 68/100 — STOP — ADDRESS GAPS**
**Outcome Confidence: 59/100**

### Gaps to Address

- **Blocking dependency unmet**: BUG-3028's fallback-convention decision
  (`None` vs. an `active_ids_set`-like local) has not landed —
  `.ll/decisions.d/` contains zero fragments referencing it, and BUG-3028
  itself is still `open`. The issue's own Wiring Phase section states
  implementation is blocked on this decision landing first, since the same
  convention must apply identically across all 5 sites.
- **Proposed Solution is not directly actionable**: it defers the actual
  fallback value to "whichever is decided" for BUG-3028 rather than
  specifying one, so an implementer cannot proceed without first resolving
  that choice (or making an undocumented unilateral call that could diverge
  from BUG-3028's sites).

### Outcome Risk Factors

- **Ambiguity (8/25)**: three existing fallback shapes in the codebase
  disagree (`None` bare, `None` with debug log, `active_ids_set` local) and
  none has been chosen as the shared convention for this call-site family.
- **Test Coverage (15/25)**: no existing test forces `gather_all_issue_ids`
  to raise for any of the 9 call sites in this family; all 5 tests for this
  issue must be written from scratch, though the per-site test-file mapping
  is already well-researched.

## Session Log
- `/ll:refine-issue` - 2026-08-03T20:43:30 - `523aa89f-a7cc-4f86-aee0-ef200fcb0222.jsonl`
- `/ll:confidence-check` - 2026-08-03T20:40:46 - `0a42aee1-1c80-4837-96ed-6d9d9dd06774.jsonl`
- `/ll:wire-issue` - 2026-08-03T20:38:32 - `0a69b1ad-5c80-4e0c-8022-e0ea04b84a84.jsonl`
- `/ll:refine-issue` - 2026-08-03T20:33:15 - `fff9bf94-0d80-4e7a-8af6-be2a7a1c33b8.jsonl`
- `/ll:issue-size-review` - 2026-08-03T18:23:42 - `13ce9106-a2bc-4289-afb9-7b03c8d5dfa8.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- **Files**: `scripts/little_loops/cli/sprint/run.py:499-502`, `scripts/little_loops/cli/sprint/show.py:183-187`, `scripts/little_loops/cli/sprint/manage.py:92-96`, `scripts/little_loops/cli/sprint/edit.py:105-114` (inside `if args.revalidate:`), `scripts/little_loops/cli/deps.py:385`
- **Anchor**: each calls `gather_all_issue_ids(issues_dir, config=...)` (defined `scripts/little_loops/dependency_mapper/operations.py:362-394`) with no enclosing `try/except`
- **Cause**: `gather_all_issue_ids()`'s failure surface is filesystem I/O (`d.exists()`/`d.glob("*.md")` on `operations.py:388-390`, which can raise `OSError`/`PermissionError`/`NotADirectoryError`) and, when `config` is passed, attribute resolution on `config.issue_categories` (`operations.py:381`). None of the 5 call sites catches these; the exception propagates straight out of the CLI entry point. `cli/deps.py:385` is the subtlest case — a `try/except` sits immediately above it (lines 379-384) but scopes only the `_BRConfig(...)` construction, not the `gather_all_issue_ids` call itself, so the visual adjacency of a try/except is misleading.
