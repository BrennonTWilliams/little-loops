---
id: BUG-2733
title: blocked_by resolution treats a done blocker parked in .issues/completed/
  as unknown, permanently blocking dependents
type: BUG
status: open
priority: P1
parent: BUG-2728
decision_needed: true
discovered_date: '2026-07-21'
discovered_by: issue-size-review
labels:
- issues
- dependency-graph
- regression
relates_to:
- BUG-2403
- ENH-2722
- BUG-2732
---

# BUG-2733: `blocked_by` resolution can't see a `done` blocker parked in `.issues/completed/`, permanently blocking dependents

## Summary

Decomposed from BUG-2728: `ENH-2722` (`status: open`,
`blocked_by: [ENH-2721]`) was never dispatched across three logged
`ll-auto` runs because `ENH-2721`'s file lives in the legacy
`.issues/completed/` directory, and every resolver the `/ll:ready-issue`
gate can reach globs type-scoped directories only. This child covers the
**read/resolution path** — making blocker-status lookups
legacy-dir-aware so a `done` blocker parked anywhere on disk resolves as
satisfied. The companion defect (the write path that keeps parking closed
parents there in the first place) is tracked separately as BUG-2732.

## Parent Issue

Decomposed from BUG-2728: `done` issues in vestigial `.issues/completed/`
are invisible to `blocked_by` resolution, permanently blocking dependents.

## Codebase Research Findings

_Carried over verbatim from BUG-2728's `/ll:refine-issue` pass — this is the
open question this child issue exists to resolve:_

- **The dependency-graph path does NOT keep ENH-2722 stuck — confirmed
  twice.** `IssueManager.__init__` builds the graph from `find_issues(...)`,
  whose status filter (`issue_parser.py:1249-1251`: `if info.status in
  ("done", "cancelled", "deferred"): continue`) drops a `done` blocker as a
  graph *node* by **status alone**, independent of directory. So
  `all_issue_ids` never contains it, `from_issues()` `continue`s at
  `dependency_graph.py:108` without adding an edge,
  `get_blocking_issues(...)` returns `∅`, and `_get_next_issue()`
  (`issue_manager.py:1209-1274` → `get_ready_issues`) **selects the
  dependent as a ready candidate**. It is dispatched, not skipped, on this
  path.
- **The actual skip is the `/ll:ready-issue` LLM gate returning verdict
  `BLOCKED`**, consumed at `issue_manager.py:798-810`
  (`process_issue_inplace()`): `if parsed.get("is_blocked"): ... 
  was_blocked=True` → `IssueProcessingResult(success=False)`, so the issue
  is re-attempted (and re-blocked) every pass. `is_blocked` is set at
  `output_parsing.py:420` (`verdict == "BLOCKED"`). The
  `"blocked by unknown issue ..."` line at `dependency_graph.py:106` fires
  once per graph build regardless of outcome and is **co-occurring log
  noise, not the causal skip**.
- **Why the gate says BLOCKED**: the `## Dependency Status` step in
  `commands/ready-issue.md:213-221` has the LLM look up each blocker's
  status via `ll-issues` CLIs. Every resolver it can reach globs type-dirs
  only — `ll-issues path`/`show` (`show.py:_resolve_issue_id`, comment line
  91 "type-scoped dirs only") and `ll-issues list --status done --json`
  (`search.py:_load_issues_with_status`, docstring line 129 "Scans only
  type-scoped directories") — so a blocker parked in `completed/` resolves
  to "not found". The prompt's literal `"...or don't exist: PASS"` branch
  (line 220) *should* pass it, but the gate is an LLM, and it has
  conservatively treated an unresolvable frontmatter `blocked_by` reference
  as a live blocker across all three logged runs. (Note also: a dependent
  with only frontmatter `blocked_by` and no `## Blocked By` body section is
  another reason the deterministic reading is ambiguous and the outcome is
  LLM-judged, not parser-deterministic.)
- **Implication**: making `gather_all_issue_ids()` legacy-dir-aware does
  **not**, by itself, unblock a dependent like ENH-2722 — a `done` blocker
  is excluded from the dependency graph by *status*, not by scan scope, so
  widening that particular scan changes nothing on the dispatch path. The
  fix must make the **blocker-status resolution the `/ll:ready-issue` gate
  depends on** (`ll-issues path`/`show`/`list`) `completed/`-aware, or the
  file must be relocated out of `completed/` (handled separately in
  BUG-2732).
- **Latent instruction bug (out of scope, flag only)**:
  `ready-issue.md:220` tells the LLM to run `ll-issues list --id
  [BLOCKER-ID] --json`, but `ll-issues list`
  (`cli/issues/list_cmd.py:cmd_list`) has **no `--id`** argument.

## Open Decision

This issue is `decision_needed: true`. Two remedies were identified in
BUG-2728's research and neither is committed yet:

1. Make `gather_all_issue_ids()` (`dependency_mapper/operations.py:261–293`)
   legacy-dir-aware, following `get_next_issue_number()`'s
   `dirs_to_scan`-append pattern (`issue_parser.py:~453–490` — same module
   family, already correct) or `recursive_finalize.py:_find_issue_file()`'s
   `rglob`-based pattern. This widens the dependency-graph's `all_known_ids`
   set but — per the Codebase Research Findings above — does **not** by
   itself fix the actual `/ll:ready-issue` gate skip, since that gate never
   consults the dependency graph.
2. Make the resolvers the `/ll:ready-issue` gate actually calls —
   `ll-issues path`/`show` (`show.py:_resolve_issue_id`) and `ll-issues
   list --status done --json` (`search.py:_load_issues_with_status`) —
   legacy-dir-aware, so a `done` blocker parked in `completed/`/`deferred/`
   resolves as found regardless of directory. This directly fixes the
   dispatch-blocking mechanism.

Run `/ll:refine-issue` or `/ll:decide-issue` on this child before
implementation to commit to one (or both) remedies — do not assume (1)
alone satisfies the acceptance criteria below.

## Integration Map

### Files to Modify (candidate — see Open Decision)
- `scripts/little_loops/dependency_mapper/operations.py` —
  `gather_all_issue_ids()` (lines 261–293): currently iterates only
  `config.issue_categories` (`bugs/`, `features/`, `enhancements/`,
  `epics/`); never globs `completed/`/`deferred/`.
- `scripts/little_loops/cli/issues/show.py` — `_resolve_issue_id` (comment
  line 91, "type-scoped dirs only") — the resolver `ll-issues path`/`show`
  use; likely the higher-leverage fix per the Codebase Research Findings.
- `scripts/little_loops/cli/issues/search.py` —
  `_load_issues_with_status()` (docstring line 129, "Scans only
  type-scoped directories") — backs `ll-issues list --status done --json`,
  the other call the `/ll:ready-issue` gate makes.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:1187,1190` — `IssueManager.__init__`
  builds `all_known_ids` via `gather_all_issue_ids()` and constructs
  `self.dep_graph`; this is `ll-auto`'s dependency graph.
- `scripts/little_loops/cli/sprint/show.py:187,190`,
  `cli/sprint/run.py:473,487`, `cli/sprint/manage.py:96,99`,
  `cli/sprint/edit.py:114,117` — same `gather_all_issue_ids()` →
  `DependencyGraph.from_issues(all_known_ids=...)` pairing.
- `scripts/little_loops/dependency_mapper/__init__.py` — re-exports
  `gather_all_issue_ids` (`__all__`); every consumer imports via this
  surface, so the exported name/signature must stay stable.
- `scripts/little_loops/dependency_mapper/analysis.py:481` —
  `validate_dependencies()` and `analyze_dependencies()` union
  `all_known_ids` into `all_known` before `DependencyGraph.from_issues(...)`;
  their docstrings already say `all_known_ids` means "all IDs on disk
  across all categories and completed" — evidence this is a bug fix, not a
  contract change.
- `scripts/little_loops/cli/deps.py` — `ll-deps` calls
  `gather_all_issue_ids()` and feeds it into
  `analyze_dependencies`/`validate_dependencies`/`fix_dependencies` and an
  ad-hoc existence check; widened scan scope → fewer false "unknown
  blocker" reports.
- `scripts/little_loops/sprint.py:367` — `DependencyGraph.from_issues(...,
  all_known_ids=...)` for wave ordering; same behavior shift as
  `issue_manager`.
- `scripts/little_loops/issue_discovery/search.py:_get_all_issue_files()`
  (lines 34–78) — backs `/ll:capture-issue` duplicate/regression matching;
  same type-dir-only scan, so a legacy-parked issue is also invisible to
  duplicate detection.
- `commands/ready-issue.md:213-221` — the `## Dependency Status` step whose
  prompt instructs the LLM to call the resolvers above; also has the
  latent `ll-issues list --id` instruction bug noted in Codebase Research
  Findings (fix or flag separately).

### Similar Patterns
- `scripts/little_loops/issue_parser.py:get_next_issue_number()` (lines
  ~453–490) — the strongest precedent: a *second, independent* "scan all
  issue dirs including legacy `completed`/`deferred`" implementation that
  is already correct. It builds `dirs_to_scan` from `config` categories
  **plus** conditionally-appended `completed`/`deferred` paths, each
  guarded by `.exists()` (lines 479–484). Caveat: it hardcodes the
  `"completed"`/`"deferred"` literals and does *not* honor
  `config.issues.completed_dir`/`deferred_dir`; this fix should read those
  config fields instead of inheriting that gap.
- `scripts/little_loops/recursive_finalize.py:_find_issue_file()` (lines
  39–59) — the only lookup helper already `completed/`-aware
  (`issues_dir.rglob("*.md")`, filtered by `include_completed`); a template
  for the resolver fix.

### Tests
- `scripts/tests/test_dependency_graph.py:test_known_id_not_in_graph_no_warning`
  (lines 101–109), `test_missing_blocker_logged_warning` (92–99),
  `test_truly_unknown_id_still_warns` (111–118),
  `test_all_known_ids_backward_compatible` (120–126),
  `test_completed_blocker_not_added` (128–140) — existing coverage for the
  `completed`/`all_issue_ids`/`all_known_ids` three-tier disposition.
- `scripts/tests/test_dependency_mapper.py:TestGatherAllIssueIds` (lines
  681–769), especially `test_scans_type_dirs_including_done_issues` (lines
  741–769) — currently documents (and asserts) "completed_dir is not
  used"; needs a companion test asserting a legacy-dir `done` issue is
  still discoverable once the fix lands.
- `scripts/tests/test_issue_migration.py` (`_make_project()` fixture, lines
  35+; `TestMigrateCompleted`/`TestMigrateDeferred`) — fixture shape for a
  new "legacy-dir reconciliation" test: a config with
  `completed_dir`/`deferred_dir` keys and issue files placed only under
  those dirs.
- **New tests to write**:
  - `gather_all_issue_ids()` legacy-dir awareness — sibling to
    `TestGatherAllIssueIds`, inverting
    `test_scans_type_dirs_including_done_issues`.
  - **Regression fixture**: a `blocked_by` reference to an ID that exists
    *only* in `.issues/completed/` resolves as satisfied by whichever
    resolver(s) the Open Decision commits to (dependency-graph
    `all_known_ids` consumer and/or `ll-issues path`/`show`/`list`).

### Configuration
- `scripts/little_loops/config-schema.json` (lines ~111–119) — defines
  `completed_dir` (default `"completed"`) and `deferred_dir` (default
  `"deferred"`), both annotated `[DEPRECATED: use IssueInfo.status
  instead]`. A legacy-dir-aware resolver should read these, not hardcode
  literals.
- `scripts/little_loops/config/features.py` — `IssuesConfig.completed_dir`
  / `deferred_dir` fields (the runtime home of those config values).
- `scripts/little_loops/config/core.py` — `BRConfig.issue_categories`
  property (lines ~583–586). **Do NOT** add legacy dirs by mutating this
  property — other consumers rely on it meaning "active type categories."
  Add a separate scan step alongside it, mirroring
  `get_next_issue_number()`'s `dirs_to_scan` append pattern.

### Documentation
- `docs/reference/API.md` — `get_next_issue_number` entry documents the
  correct "scans … any legacy completed/deferred" contract (precedent);
  add/adjust the `gather_all_issue_ids` (and/or resolver) entry to match
  its new scan scope.

## Acceptance Criteria

- [ ] A `blocked_by` reference to a `done` issue parked only in
      `.issues/completed/` (or `.issues/deferred/`) resolves as satisfied,
      not "unknown", via whichever resolver(s) the Open Decision commits to
- [ ] `/ll:ready-issue` no longer returns `BLOCKED` for a dependent whose
      only unresolved blocker is `done` but parked in a legacy directory
- [ ] Regression test: a `done` blocker in a legacy/unscanned directory does
      not leave dependents permanently skipped

## Session Log
- `/ll:issue-size-review` - 2026-07-21T23:52:25 - `35cd122b-5b42-4ccf-8307-837e09286f3f.jsonl`
