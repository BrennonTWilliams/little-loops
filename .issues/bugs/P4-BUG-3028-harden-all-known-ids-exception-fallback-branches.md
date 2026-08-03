---
id: BUG-3028
priority: P4
type: BUG
parent: BUG-3027
status: done
discovered_date: 2026-08-03
discovered_by: issue-size-review
completed_at: '2026-08-03T21:17:26Z'
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# Harden `all_known_ids` exception-fallback branches in `AutoManager.__init__` and `find_issues(skip_blocked=True)`

## Summary

Decomposed from BUG-3027: the originally-reported spurious "unknown issue"
warning was already fixed on the `sprint.py` path by commit `15152136`
(closing BUG-3024). The remaining, still-open scope from BUG-3027 is
hardening the two other `all_known_ids` construction sites that share the
same `gather_all_issue_ids()` try/except shape but currently degrade to
`all_known_ids = None` on exception (a stricter, untested failure mode)
instead of a `gather_all_issue_ids`-derived fallback like `sprint.py` now
uses.

## Parent Issue

Decomposed from BUG-3027: ll-sprint prints "depends_on unknown issue" for a
dependency that exists and is done.

## Current Behavior

- `scripts/little_loops/issue_manager.py:1509-1521` (`AutoManager.__init__`):
  `except Exception: self.logger.debug(...)` leaves `all_known_ids = None`.
- `scripts/little_loops/issue_parser.py:2118-2126` (`find_issues()`'s
  `skip_blocked` branch): `except Exception: pass` leaves
  `all_known_ids = None`, with no logging at all.
- Per `dependency_graph.py`'s guard (`if all_known_ids is None or <id> not in
  all_known_ids: warn`), `None` triggers warnings on *every* referenced ID
  outside the graph — reachable only if `gather_all_issue_ids()` itself
  raises, not on the normal path. Neither branch is exercised by any
  existing test.
- Three coexisting conventions for the fallback body already disagree:
  `sprint.py:378` (`all_known_ids = active_ids_set`, marked
  `# pragma: no cover - defensive, mirrors issue_parser`),
  `issue_manager.py:1520-1521` (`None` + `logger.debug`), `issue_parser.py`
  (`None` + bare `pass`). No existing precedent picks one over the others
  for this exception specifically.

## Expected Behavior

Both remaining sites degrade consistently with the already-fixed
`sprint.py` site: on `gather_all_issue_ids()` exception, fall back to a
`gather_all_issue_ids`-derived set (or, if that's not feasible, at minimum
log the swallowed exception rather than silently leaving `all_known_ids =
None`) — and cover the exception path with a regression test at each site,
since none currently exists anywhere in this call-site family.

## Steps to Reproduce

1. Patch `little_loops.dependency_mapper.gather_all_issue_ids` (or the
   `little_loops.dependency_mapper.operations.gather_all_issue_ids` it
   re-exports) with `side_effect=RuntimeError("boom")`.
2. Either construct `AutoManager(config)` (`issue_manager.py:1509-1521`) or
   call `find_issues(config, skip_blocked=True)` (`issue_parser.py:2135-2142`)
   against a project with at least one non-terminal issue whose
   `blocked_by`/`blocks`/`depends_on` references an ID excluded from the
   non-terminal node list (e.g. a `done`/`cancelled`/`deferred` issue).
3. Observe: `all_known_ids` is left `None` in the except body, so
   `DependencyGraph.from_issues(..., all_known_ids=None)` warns on every
   such out-of-graph reference (`dependency_graph.py:111,129,143`'s
   `if all_known_ids is None or <id> not in all_known_ids: warn` guard
   short-circuits true unconditionally) — the same spurious-warning failure
   mode BUG-3024/BUG-3027 fixed on the `sprint.py` path, but here reachable
   only via this forced exception and currently untested at both sites.

## Proposed Solution

1. `issue_manager.py:1509-1521` (`AutoManager.__init__`): change the
   except-branch's fallback shape to match `sprint.py`'s post-fix pattern
   (derive `all_known_ids` from the already-active-ids set, or another
   `gather_all_issue_ids`-shaped fallback), keeping the existing
   `logger.debug` call or upgrading it per whatever convention is chosen.
2. `issue_parser.py:2118-2126` (`find_issues()`'s `skip_blocked` branch):
   same fallback-shape fix; add at least a `logger.debug` call since none
   exists today.
3. Add a test forcing the exception path for `AutoManager.__init__`,
   modeled on `test_dependency_graph_built_on_init`
   (`scripts/tests/test_issue_manager.py:613-626`) and its fixture
   `temp_project_with_deps` (`:568-611`); patch
   `little_loops.dependency_mapper.gather_all_issue_ids` to raise, construct
   `AutoManager`, and assert it doesn't crash and produces the expected
   `all_known_ids`/warning behavior.
4. Add a test forcing the exception path for `find_issues(skip_blocked=True)`,
   modeled on `test_find_issues_skip_blocked_terminal_blocker_unblocks` /
   `test_find_issues_skip_blocked_deferred_blocker_still_blocks`
   (`scripts/tests/test_issue_parser.py:1352-1394`), same patch approach.

## Files to Modify

- `scripts/little_loops/issue_manager.py:1509-1521`
- `scripts/little_loops/issue_parser.py:2118-2126`
  > ⚠ Superseded — line range is stale; current location is 2135-2142
- `scripts/tests/test_issue_manager.py` (new exception-path test)
- `scripts/tests/test_issue_parser.py` (new exception-path test)

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/issue_manager.py:1509-1521` — `AutoManager.__init__`; `all_issues` (via `find_issues_for_graph`) is computed before the try block and feeds `self.dep_graph = DependencyGraph.from_issues(all_issues, all_known_ids=all_known_ids)` right after. `self.dep_graph` is built once at construction and reused for the whole autonomous run's dependency-aware sequencing (ENH-016 comment at line 1509).
- `scripts/little_loops/issue_parser.py:2135-2142` — `find_issues()`'s `skip_blocked` branch; `all_active: list[IssueInfo]` is built before the try block by walking every category directory and keeping only non-terminal-status issues, then feeds `graph = DependencyGraph.from_issues(all_active, all_known_ids=all_known_ids)`, whose `get_ready_issues()` output filters the final `issues` list returned by the function. This graph is rebuilt fresh on every call with `skip_blocked=True`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/dependency_graph.py:111,129,143` — `DependencyGraph.from_issues()`'s three edge-kind warning guards (`blocked_by`, one-sided `blocks:`, `depends_on`), each `if all_known_ids is None or <id> not in all_known_ids: warn`
- `scripts/little_loops/dependency_graph.py:80-82` — docstring: "Set of all issue IDs that exist on disk. When provided, references to issues in this set are silently skipped (not warned) even if they are not in the graph."
- `scripts/little_loops/dependency_mapper/operations.py:362-394` — `gather_all_issue_ids(issues_dir, config=None) -> set[str]`, the guarded function itself; called identically (`gather_all_issue_ids(issues_dir, config=config)`) at every one of the 9 call sites in this family

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/auto.py:100` (`main_auto()`) — the only production (non-test) caller that constructs `AutoManager(...)`; the only real-world path through which `AutoManager.__init__`'s hardened except-branch is reachable (the `ll-auto` command). No change needed here — `AutoManager.__init__`'s public signature is untouched — but it is the concrete production consumer this fix protects. `scripts/little_loops/__init__.py:136` also re-exports `AutoManager` in `__all__`; no change needed since the export target's signature is unchanged.

### Conventions in Force
- Every guarded call site predeclares `all_known_ids: set[str] | None = None` before a `try` that catches bare `Exception` — the only variation across sites is the except-body. Three fallback shapes coexist and disagree, and neither this issue nor sibling BUG-3029 has picked one: (1) `None` + bare `pass` — `cli/issues/link.py:223-228`, `cli/issues/sequence.py:74-81`, `cli/issues/next_issue.py:67-74`, `cli/issues/next_issues.py:57-64`, and `issue_parser.py:2135-2142` (this issue's own site); (2) `None` + `self.logger.debug(...)` — `issue_manager.py:1509-1521` (this issue's own site), the only site that logs anything on the exception path while still leaving `all_known_ids = None`; (3) `active_ids_set`-local fallback — `sprint.py:372-379` only, the sole site with a non-`None` fallback.
- `# pragma: no cover` on an `except` line, paired with a short dash-separated reason, is this codebase's established convention for marking a defensive/believed-unreachable branch (`sprint.py:378`, `issue_parser.py:72`, `file_utils.py:55`, `workflow_sequence/io.py:50`, `hooks/edit_batch_nudge.py:217`, `issue_history/parsing.py:369,381`) — enforced via `scripts/pyproject.toml:234-241`'s coverage `exclude_lines`. Neither of this issue's two target except-branches currently carries this annotation.
- No shared helper function wraps the `all_known_ids: set[str] | None = None` / `try` / `except Exception` shape anywhere — each of the 9 call sites (4 guarded `cli/issues/*`, `issue_manager.py`, `issue_parser.py`, `sprint.py`, plus BUG-3029's 5 unguarded sites) reimplements it inline.
- Forcing an exception path in a mocked dependency uses `patch("<module>.<callable>", side_effect=RuntimeError("..."))` — e.g. `scripts/tests/test_issue_manager.py:3818-3821` (`test_run_preserves_state_file_after_fatal_exception`, patching `process_issue_inplace`). No existing test currently patches `gather_all_issue_ids` with `side_effect=...`; the only two test sites that patch it at all (`scripts/tests/test_cli_sprint.py:864,1122`) use `return_value=set()` (success path).

### Tests
- `scripts/tests/test_issue_manager.py:613-626` — `test_dependency_graph_built_on_init`, exercises the success path for `AutoManager.__init__` using fixture `temp_project_with_deps` (`:568-611`); does not exercise the except branch
- `scripts/tests/test_issue_parser.py:1352-1394` — `test_find_issues_skip_blocked_terminal_blocker_unblocks` / `test_find_issues_skip_blocked_deferred_blocker_still_blocks`, exercise the success path for `find_issues(skip_blocked=True)`; does not exercise the except branch
- `scripts/tests/test_dependency_graph.py` — `test_depends_on_unknown_target_warns`, `test_known_but_absent_target_no_warning`, covering `DependencyGraph`'s warning-guard logic directly (not via these two call sites)
- `scripts/tests/test_dependency_mapper.py:674-768` — tests `gather_all_issue_ids()` directly against on-disk fixtures, not via mocking/side_effect

### Documentation
- No dedicated docs page for this call-site family beyond `docs/ARCHITECTURE.md`/`docs/reference/API.md`'s general `dependency_mapper` coverage; no update required by this fix

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

### Types
- `all_known_ids: set[str] | None` — the value each call site produces; `DependencyGraph.from_issues()` keys on `None` vs a populated `set[str]` to distinguish "unknown, always warn" from "known, only warn if truly dangling" (`dependency_graph.py:111,129,143`)

### Signatures
- `gather_all_issue_ids(issues_dir: Path, config: BRConfig | None = None) -> set[str]` — `dependency_mapper/operations.py:362`, the guarded function at both target sites
- `DependencyGraph.from_issues(issues, all_known_ids: set[str] | None = None)` — `dependency_graph.py:60`, the consumer at both target sites (`AutoManager.__init__` passes `all_issues`; `find_issues(skip_blocked=True)` passes `all_active`)

### Call Path
`AutoManager.__init__` / `find_issues(skip_blocked=True)` -> `gather_all_issue_ids(issues_dir, config=config)` inside `try` -> (on exception, currently) `all_known_ids = None` -> `DependencyGraph.from_issues(..., all_known_ids=None)` -> every `blocked_by`/`blocks`/`depends_on` reference outside the graph's own node list warns (`dependency_graph.py:111,129,143`); (once hardened, per the `sprint.py:372-379` precedent) `except Exception: all_known_ids = <local id-set already computed before the try>` -> only references absent from *both* the graph nodes and the fallback set warn

## Impact

- **Priority**: P4 - Consistency/hardening fix; no user-visible crash today,
  only a stricter (but unexercised) warning-suppression degrade path.
- **Effort**: Small - two symmetric fallback-shape edits plus two new
  mock-based exception-path tests, modeled directly on existing test
  patterns.
- **Risk**: Low - narrow, well-isolated code paths with clear precedent to
  follow from the already-fixed `sprint.py` site.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-08-03 | Priority: P4


## Session Log
- `/ll:manage-issue` - 2026-08-03T21:17:03 - `38806321-3a26-4aba-be12-0a62dc980662.jsonl`
- `/ll:ready-issue` - 2026-08-03T21:08:56 - `3e7816f2-7b6d-4cdf-b22d-004c7ab74ddc.jsonl`
- `/ll:confidence-check` - 2026-08-03T21:05:15 - `826449f0-a9da-4046-bdfe-e58773b9c9b8.jsonl`
- `/ll:wire-issue` - 2026-08-03T21:02:24 - `f45f750b-6054-401c-b4fe-d777c59f5fb6.jsonl`
- `/ll:refine-issue` - 2026-08-03T20:56:43 - `d313f1f3-ca37-4723-8c76-c60137bf4ca0.jsonl`
- `/ll:issue-size-review` - 2026-08-03T18:23:42 - `13ce9106-a2bc-4289-afb9-7b03c8d5dfa8.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- **Files**: `scripts/little_loops/issue_manager.py:1509-1521` (`AutoManager.__init__`), `scripts/little_loops/issue_parser.py:2135-2142` (`find_issues()`'s `skip_blocked` branch — the file is currently at lines 2135-2142, not 2118-2126 as originally cited; see the superseded-line annotation in Files to Modify below)
- **Anchor**: both wrap `gather_all_issue_ids(issues_dir, config=config)` in `try/except Exception`, and both leave `all_known_ids = None` in the except body — `issue_manager.py`'s except body additionally calls `self.logger.debug("Dependency mapping unavailable — skipping")`; `issue_parser.py`'s is a bare `pass` with no logging at all
- **Cause**: `DependencyGraph.from_issues()` (`scripts/little_loops/dependency_graph.py:111,129,143`) guards each of its three edge-kind warning checks with `if all_known_ids is None or <id> not in all_known_ids: warn`. When `all_known_ids is None`, the `or` short-circuits true unconditionally, so every `blocked_by`/`blocks`/`depends_on` reference to an ID outside the graph's own node list is warned on — including references to legitimately existing but excluded issues (e.g. done/cancelled/deferred issues filtered out of the non-terminal node list each caller builds). This is the same spurious-warning failure mode BUG-3024/BUG-3027 fixed on the `sprint.py` path, but here it is only reachable if `gather_all_issue_ids()` itself raises, and it is untested at both sites.
- A third, already-fixed sibling site — `scripts/little_loops/sprint.py:372-379` (`Sprint.resolve_epic`) — falls back to `all_known_ids = active_ids_set` (the already-computed `{info.issue_id for info in all_active}` local, where `all_active = find_issues(self.config, status_filter=_ACTIVE_STATUSES)`) instead of `None`, marked `except Exception:  # pragma: no cover - defensive, mirrors issue_parser`. An analogous local exists at both open sites and could serve the same role: `{info.issue_id for info in all_issues}` at `issue_manager.py` (built before the try block) and `{info.issue_id for info in all_active}` at `issue_parser.py` (also built before the try block).
