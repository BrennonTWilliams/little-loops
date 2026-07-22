---
id: BUG-2733
title: blocked_by resolution treats a done blocker parked in .issues/completed/ as
  unknown, permanently blocking dependents
type: BUG
status: done
priority: P1
parent: BUG-2728
decision_needed: false
discovered_date: '2026-07-21'
discovered_by: issue-size-review
completed_at: '2026-07-22T00:44:13Z'
labels:
- issues
- dependency-graph
- regression
relates_to:
- BUG-2403
- ENH-2722
- BUG-2732
confidence_score: 100
outcome_confidence: 71
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 0
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

## Current Behavior

`ll-issues path`/`show` (`show.py:_resolve_issue_id`) and `ll-issues list
--status done --json` (`search.py:_load_issues_with_status`) — the two
resolvers `/ll:ready-issue`'s `## Dependency Status` step calls to look up a
blocker's status — glob type-scoped category directories
(`bugs/`, `features/`, `enhancements/`, `epics/`) only. A `blocked_by`
reference to an issue file parked in `.issues/completed/` or
`.issues/deferred/` resolves to "not found," so the LLM gate conservatively
returns verdict `BLOCKED`, and the dependent is re-attempted (and
re-blocked) on every automation pass.

Note (2026-07-22): BUG-2732's fix (flipping
`finalize_decomposed_parent()`'s `move_to_completed` default) already swept
the two files that originally triggered this — BUG-2728 and ENH-2721 — back
out of `.issues/completed/` into their type-based directories, and
`.issues/completed/` is currently empty on `main`. That removes today's
concrete repro instance but does **not** touch `show.py`/`search.py`
themselves: both resolvers are unchanged and still scan type-dirs only, so
any file that lands in a legacy directory by another path (a stale
migration, a manually placed file, or a project that still uses
`completed_dir`/`deferred_dir`) reproduces the same permanent-block failure.

## Expected Behavior

A `blocked_by` reference to a `done` (or `cancelled`) issue resolves as
satisfied regardless of which directory the file physically lives in —
`ll-issues path`/`show`/`list --status done --json` should also scan
`config.issues.completed_dir`/`deferred_dir` when present, following the
`dirs_to_scan`-append pattern already used by
`issue_parser.py:get_next_issue_number()`.

## Steps to Reproduce

1. Create a `done` issue file directly under `.issues/completed/` (or
   `.issues/deferred/`) rather than its type-based directory.
2. Create a second issue with `blocked_by: [<first-issue-id>]` (frontmatter
   and/or a `## Blocked By` body section) in its normal type directory.
3. Run `ll-issues path <first-issue-id>` or
   `ll-issues list --status done --json` — the blocker issue is not
   returned/found.
4. Run `/ll:ready-issue <second-issue-id>` — the gate cannot confirm the
   blocker is `done` and returns verdict `BLOCKED`, permanently, since the
   blocker's file never moves and the gate re-runs the same lookup every
   pass.

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

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — alternatives below are reformatted verbatim
from the `## Open Decision` section above so `/ll:decide-issue` can score
them; no new prose invented._

**Option A**: Make `gather_all_issue_ids()`
(`dependency_mapper/operations.py:261–293`) legacy-dir-aware, following
`get_next_issue_number()`'s `dirs_to_scan`-append pattern
(`issue_parser.py:~453–490` — same module family, already correct) or
`recursive_finalize.py:_find_issue_file()`'s `rglob`-based pattern. This
widens the dependency-graph's `all_known_ids` set but — per the Codebase
Research Findings above — does **not** by itself fix the actual
`/ll:ready-issue` gate skip, since that gate never consults the dependency
graph.

**Option B**:

> **Selected:** Option B — directly fixes the resolvers (`show.py`/`search.py`) that `/ll:ready-issue`'s gate actually calls; Option A alone leaves the reported BLOCKED symptom unfixed.

Make the resolvers the `/ll:ready-issue` gate actually calls —
`ll-issues path`/`show` (`show.py:_resolve_issue_id`) and `ll-issues list
--status done --json` (`search.py:_load_issues_with_status`) —
legacy-dir-aware, so a `done` blocker parked in `completed/`/`deferred/`
resolves as found regardless of directory. This directly fixes the
dispatch-blocking mechanism.

**Recommended**: Option B — the Codebase Research Findings above establish
that the `/ll:ready-issue` gate's `BLOCKED` verdict is driven solely by
`ll-issues path`/`show`/`list`, which never consult the dependency graph
that Option A widens; Option A alone leaves the reported symptom (permanent
`BLOCKED`) unfixed. Option A remains independently valuable for the other
`gather_all_issue_ids()` consumers listed in Integration Map (sprint
ordering, `ll-deps`, duplicate detection) and can be done in addition to
Option B, but does not substitute for it.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-21.

**Selected**: Option B — legacy-dir-aware `ll-issues path`/`show`/`list` resolvers

**Reasoning**: Independent codebase-pattern-finder evidence for both options confirmed that `/ll:ready-issue`'s `## Dependency Status` gate (`commands/ready-issue.md:213-221`) resolves blocker status exclusively through `show.py:_resolve_issue_id` and `search.py:_load_issues_with_status` — never through `gather_all_issue_ids()`/`DependencyGraph`. Option A has stronger direct precedent to copy but, applied alone, does not touch the code path producing the reported `BLOCKED` verdict; Option B directly targets that mechanism, following the same `dirs_to_scan`/`rglob` shapes already proven by `get_next_issue_number()` and `_find_issue_file()`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (widen `gather_all_issue_ids()`) | 1/3 | 3/3 | 3/3 | 0/3 | 7/12 |
| Option B (legacy-dir-aware `show.py`/`search.py` resolvers) | 2/3 | 2/3 | 2/3 | 2/3 | 8/12 |

**Key evidence**:
- Option A: Two shipped precedents (`get_next_issue_number`'s `dirs_to_scan` append, `_find_issue_file`'s `rglob`+`path.parts` filter) make it cheap and well-tested to implement, but `test_dependency_mapper.py:741-769`'s `test_scans_type_dirs_including_done_issues` currently asserts "completed_dir is not used" as intentional, and — decisively — a `done` blocker is already excluded from the dependency graph by status alone (`test_completed_blocker_not_added`), so widening the scan changes nothing on the `/ll:ready-issue` dispatch path.
- Option B: `_resolve_issue_id` (9 call sites) and `_load_issues_with_status` (4 call sites) both currently assert type-dir-only scanning as by-design in their docstrings, and neither has existing legacy-dir test coverage — but this is the exact mechanism `/ll:ready-issue` calls, confirmed independently by both evidence agents, making it the fix that actually closes the acceptance criteria. Option A remains additive value (not required) for `gather_all_issue_ids()`'s other consumers (sprint CLIs, `ll-deps`, duplicate detection).

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

## Impact

- **Severity**: High (P1) — a blocked dependent never self-resolves; it is
  re-attempted and re-blocked on every `ll-auto`/`ll-parallel` pass with no
  automatic recovery path.
- **Scope**: `/ll:ready-issue`'s `## Dependency Status` gate (all
  automation that runs it), plus every other consumer of
  `ll-issues path`/`show`/`list --status done --json` — currently latent
  since `.issues/completed/`/`.issues/deferred/` are empty on `main`
  (BUG-2732 swept the only two files that lived there), but live again the
  moment any issue is parked in a legacy directory by any other path.
- **Effort**: Low-Medium — extend two resolvers to also scan
  `config.issues.completed_dir`/`deferred_dir` when present, following the
  proven `dirs_to_scan`-append pattern from `get_next_issue_number()`.
- **Risk**: Low — additive scan-scope widening with an existing precedent
  and no interface/contract changes to `show.py`/`search.py` callers.

## Status

**Open** | Discovered: 2026-07-21 | Priority: P1

## Resolution

- **Status**: Fixed
- **Completed**: 2026-07-21
- **Approach**: Implemented Option B per the Decision Rationale above. Added
  `BRConfig.legacy_issue_dirs()` (`scripts/little_loops/config/core.py`),
  returning the existing `completed_dir`/`deferred_dir` paths (if any),
  reading config fields rather than hardcoding literals. Both resolvers the
  `/ll:ready-issue` gate calls now append it to their scan directories:
  `show.py:_resolve_issue_id` and `search.py:_load_issues_with_status`
  (backing `ll-issues path`/`show` and `ll-issues list --status done --json`
  respectively). Option A (`gather_all_issue_ids()`) was not implemented —
  per the Decision Rationale, it doesn't touch the `/ll:ready-issue`
  dispatch path and remains a separate, optional enhancement.
- **Tests added**: `test_config.py::TestBRConfig::test_legacy_issue_dirs_*`,
  `test_show.py::TestResolveIssueId::test_resolves_done_issue_parked_in_legacy_*`,
  `test_issues_cli.py::TestIssuesCLIList::test_list_status_done_json_finds_issue_in_legacy_completed_dir`.

## Session Log
- `/ll:manage-issue` - 2026-07-22T00:43:32 - `6b6c6f34-55fd-4f56-b1ab-d7ea731fd7af.jsonl`
- `/ll:ready-issue` - 2026-07-22T00:32:56 - `47643fcf-ade9-4510-8494-7b4414dfaa10.jsonl`
- `/ll:confidence-check` - 2026-07-22T00:29:37 - `cb97f015-b9ce-42f6-a5ae-0226536bb2f0.jsonl`
- `/ll:decide-issue` - 2026-07-22T00:27:13 - `41f9f33c-00df-4650-a689-225e1937022c.jsonl`
- `/ll:refine-issue` - 2026-07-22T00:22:53 - `41f9f33c-00df-4650-a689-225e1937022c.jsonl`
- `/ll:issue-size-review` - 2026-07-21T23:52:25 - `35cd122b-5b42-4ccf-8307-837e09286f3f.jsonl`
