---
id: BUG-2728
title: done issues still land in vestigial .issues/completed/, making blocked_by resolution
  report them as unknown and permanently blocking dependents
type: BUG
status: done
priority: P1
decision_needed: true
size: Very Large
captured_at: '2026-07-21T22:10:00Z'
discovered_date: '2026-07-21'
discovered_by: audit-loop-run
labels:
- issues
- dependency-graph
- regression
relates_to:
- BUG-2403
- ENH-1390
- ENH-2722
- ENH-2721
confidence_score: 96
outcome_confidence: 63
score_complexity: 13
score_test_coverage: 25
score_ambiguity: 15
score_change_surface: 10
completed_at: '2026-07-21T23:54:43Z'
---

# BUG-2728: `done` issues in vestigial `.issues/completed/` are invisible to `blocked_by` resolution, permanently blocking dependents

## Summary

ENH-2721 was closed today (`status: done`) but its file was placed at
`.issues/completed/P2-ENH-2721-usage-events-run-id-live-writer.md` — the legacy
directory that ENH-1390's `ll-migrate` was supposed to retire in favor of
type-based directories. Issue discovery used for dependency resolution does not
scan `completed/`, so `dependency_graph.py:106` logs
`Issue ENH-2722 blocked by unknown issue ENH-2721` and ENH-2722 is skipped on
every `ll-auto` pass — its blocker is satisfied, but the resolver can't see it.

Two component defects:

1. **Something still writes closures into `completed/`** — the closure path that
   filed ENH-2721 there needs to move files to (or leave them in) the type
   directory instead. BUG-2403 (done) fixed only the *closure metric* counting
   this directory; the write path evidently persists.
2. **Dependency resolution treats out-of-scan blockers as unknown, not
   satisfied** — `DependencyGraph.from_issues` only skips-silently when
   `all_known_ids` contains the blocker; a done-but-unscanned blocker leaves the
   dependent effectively stuck (skipped by dispatchers) with only a log warning.

## Evidence

- `ls .issues/completed/ | grep 2721` → `P2-ENH-2721-usage-events-run-id-live-writer.md`
  (`status: done`); `.issues/enhancements/` has no ENH-2721 file.
- `.issues/enhancements/P2-ENH-2722-ctx-stats-waste-view.md` remains
  `status: open`, `blocked_by: [ENH-2721]`, no Session Log entries.
- autodev run `2026-07-21T181435` logged "Issue ENH-2722 blocked by unknown
  issue ENH-2721" repeatedly (18:43, 19:11, 19:54 UTC) and never dispatched it.

## Root Cause

- **File**: `scripts/little_loops/recursive_finalize.py`
- **Anchor**: `finalize_decomposed_parent()` (lines 110–210), move logic at
  lines 167–173
- **Cause**: This is the closure engine behind `ll-issues finalize-decomposition`
  (wired from `scripts/little_loops/cli/issues/finalize_decomposition.py:cmd_finalize_decomposition()`,
  invoked by `autodev.yaml`'s `enqueue_children`/`enqueue_or_skip` states and
  `rn-decompose.yaml`'s `finalize_parent` state whenever an issue is closed via
  decomposition). It writes `status: done` in place (correct, per ENH-1418),
  but then, `if move_to_completed and "completed" not in parent_path.parts`,
  `git mv`s the file to `<issues_dir>/completed/`. `move_to_completed` defaults
  to `True`; `cmd_finalize_decomposition()` only skips the move via an opt-in
  `--no-move` flag. ENH-2721's file location and its exact `## Resolution`
  body text (`_append_decomposition_note()`, lines 91–107 — "Work for
  {parent_id} is now carried by its child issues; this parent was closed by
  rn-decompose.") confirm this is the write path that produced the bug report.
- **Why it wasn't caught by BUG-2403**: BUG-2403 fixed only `auto-refine-and-implement.yaml`'s
  closure-metric counting of `completed/` and explicitly rejected adding a new
  finalize state that would `git mv` *every* `status: done` issue there
  ("Do NOT reintroduce directory moves (reject audit P3)"). It treated the
  decomposition path's move as a separate, pre-existing, retained behavior to
  route around (via union-counting), not something in its own scope to fix.

## Root Cause — Caveat on the "permanently blocking" mechanism

Codebase research found that `DependencyGraph.from_issues()`
(`scripts/little_loops/dependency_graph.py:96–108`) does **not** add an edge
to `graph.blocked_by[...]` for a blocker missing from `all_issue_ids`,
regardless of whether the `all_known_ids not in` check fires the warning or
not — the `continue` at line 108 runs either way. `get_ready_issues()` →
`get_blocking_issues()` (lines 147–181, 282–288) only consults
`graph.blocked_by`, so on the *dependency-graph* code path alone, a blocker
absent from the graph is treated as **not blocking**, not as a permanent
block — the warning is log noise, not (by itself) the mechanism keeping
ENH-2722 stuck. Before treating "add `completed/` to `all_known_ids`" as a
complete fix, the implementer should trace `ll-auto`'s actual dispatch skip
for ENH-2722 (e.g. `IssueManager._get_next_issue()` in `issue_manager.py`,
or check whether some other code path reads `issue.blocked_by` frontmatter
directly rather than via `dep_graph`) to confirm what specifically kept it
un-dispatched across the three logged runs, rather than assuming the
dependency-graph warning path is the full causal chain.

### Codebase Research Findings

_Added by `/ll:refine-issue` — the open question above is now resolved by tracing
the actual `ll-auto` dispatch path:_

- **The dependency-graph path does NOT keep ENH-2722 stuck — confirmed twice.**
  `IssueManager.__init__` builds the graph from `find_issues(...)`, whose status
  filter (`issue_parser.py:1249-1251`: `if info.status in ("done", "cancelled",
  "deferred"): continue`) drops ENH-2721 as a graph *node* by **status alone**,
  independent of directory. So `all_issue_ids` never contains ENH-2721,
  `from_issues()` `continue`s at `dependency_graph.py:108` without adding an edge,
  `get_blocking_issues("ENH-2722")` returns `∅`, and `_get_next_issue()`
  (`issue_manager.py:1209-1274` → `get_ready_issues`) **selects ENH-2722 as a
  ready candidate**. It is dispatched, not skipped, on this path.
- **The actual skip is the `/ll:ready-issue` LLM gate returning verdict
  `BLOCKED`**, consumed at `issue_manager.py:798-810` (`process_issue_inplace()`):
  `if parsed.get("is_blocked"): ... was_blocked=True` → `IssueProcessingResult(success=False)`,
  so the issue is re-attempted (and re-blocked) every pass. `is_blocked` is set at
  `output_parsing.py:420` (`verdict == "BLOCKED"`). The
  `"blocked by unknown issue ENH-2721"` line in the Evidence section is
  `dependency_graph.py:106` — it fires once per graph build regardless of outcome
  and is **co-occurring log noise, not the causal skip** (grep confirms it's the
  only site emitting that exact string).
- **Why the gate says BLOCKED**: the `## Dependency Status` step in
  `commands/ready-issue.md:213-221` has the LLM look up each blocker's status via
  `ll-issues` CLIs. Every resolver it can reach globs type-dirs only —
  `ll-issues path`/`show` (`show.py:_resolve_issue_id`, comment line 91
  "type-scoped dirs only") and `ll-issues list --status done --json`
  (`search.py:_load_issues_with_status`, docstring line 129 "Scans only
  type-scoped directories") — so ENH-2721 (parked in `completed/`) resolves to
  "not found". The prompt's literal `"...or don't exist: PASS"` branch (line 220)
  *should* pass it, but the gate is an LLM, and across all three logged runs it
  conservatively treated an unresolvable frontmatter `blocked_by` reference as a
  live blocker. (Note also: ENH-2722 has **no `## Blocked By` body section**, only
  frontmatter `blocked_by: [ENH-2721]`, and the step at line 214 is nominally
  gated on that heading — another reason the deterministic reading is ambiguous
  and the outcome is LLM-judged, not parser-deterministic.)
- **Implication for the Proposed Fix / AC #3**: making `gather_all_issue_ids()`
  legacy-dir-aware does **not**, by itself, unblock ENH-2722 — ENH-2721 is
  excluded from the graph by *status*, not by scan scope, so widening the scan
  changes nothing on the dispatch path. To satisfy AC #3 ("a `done` blocker in a
  legacy dir does not leave dependents permanently skipped"), the fix must make
  the **blocker-status resolution the `ready-issue` gate depends on**
  `completed/`-aware — i.e. `ll-issues path`/`show`/`list` must find a `done`
  issue regardless of directory (or the file must be migrated out of `completed/`
  per the Proposed Fix's first bullet). The write-path fix (stop the move) is
  necessary to prevent recurrence but is **not sufficient** to resolve an
  already-parked blocker.
- **Latent instruction bug (out of scope, flag only)**: `ready-issue.md:220`
  tells the LLM to run `ll-issues list --id [BLOCKER-ID] --json`, but
  `ll-issues list` (`cli/issues/list_cmd.py:cmd_list`) has **no `--id`
  argument** — worth capturing separately.

## Integration Map

### Files to Modify
- `scripts/little_loops/recursive_finalize.py` — `finalize_decomposed_parent()`
  (lines 110–210): stop moving closed parents into `completed/`, or gate it
  behind an explicit flag that defaults off, matching ENH-1418's in-place
  convention already used by `issue_lifecycle.py:close_issue()`.
- `scripts/little_loops/dependency_mapper/operations.py` — `gather_all_issue_ids()`
  (lines 261–293): currently iterates only `config.issue_categories`
  (`bugs/`, `features/`, `enhancements/`, `epics/`); never globs
  `completed/`/`deferred/`. Its docstring's invariant ("scanning only type
  dirs finds all known IDs") is what this bug breaks.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/finalize_decomposition.py` —
  `cmd_finalize_decomposition()` calls `finalize_decomposed_parent(...,
  move_to_completed=not args.no_move)` and owns the `--no-move` argparse flag
  (`add_finalize_decomposition_parser()`). If the fix flips the default to
  in-place (no move), the flag's help text and default must be updated here in
  lockstep with `recursive_finalize.py` [Agent 2 finding].
- `scripts/little_loops/cli/issues/__init__.py:48–51,836,912–913` —
  registers `add_finalize_decomposition_parser` / dispatches
  `cmd_finalize_decomposition`; touch only if the flag surface changes
  [Agent 1 finding].

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:1187,1190` — `IssueManager.__init__`
  builds `all_known_ids` via `gather_all_issue_ids()` and constructs
  `self.dep_graph`; this is `ll-auto`'s dependency graph.
- `scripts/little_loops/cli/sprint/show.py:187,190`, `cli/sprint/run.py:473,487`,
  `cli/sprint/manage.py:96,99`, `cli/sprint/edit.py:114,117` — same
  `gather_all_issue_ids()` → `DependencyGraph.from_issues(all_known_ids=...)`
  pairing.
- Callers that build a graph *without* `all_known_ids` (every unresolvable
  blocker there always warns): `scripts/little_loops/issue_parser.py:1276`
  (`find_issues(..., skip_blocked=True)`),
  `scripts/little_loops/cli/issues/next_issues.py:48`,
  `cli/issues/next_issue.py:57`, `cli/issues/sequence.py:34`.
- `scripts/little_loops/issue_discovery/search.py:_get_all_issue_files()`
  (lines 34–78) — backs `/ll:capture-issue` duplicate/regression matching;
  same type-dir-only scan, so ENH-2721 is also invisible to duplicate
  detection while parked in `completed/`.
- `scripts/little_loops/issue_parser.py:find_issues()` (lines 1198–1290) and
  `cli/issues/search.py:_load_issues_with_status()` (lines 121–165) — same
  `config.issue_categories` scan pattern; general-purpose listers used by
  `ll-issues list` and most loop states.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/dependency_mapper/__init__.py` — re-exports
  `gather_all_issue_ids` (`__all__`); every consumer imports via this surface,
  so the exported name/signature must stay stable [Agent 1/2 finding].
- `scripts/little_loops/dependency_mapper/analysis.py:481` —
  `validate_dependencies()` and `analyze_dependencies()` union `all_known_ids`
  into `all_known` before `DependencyGraph.from_issues(...)`; their docstrings
  already say `all_known_ids` means "all IDs on disk across all categories and
  completed" — evidence this is a bug-fix, not a contract change [Agent 2 finding].
- `scripts/little_loops/cli/deps.py` — `ll-deps` calls `gather_all_issue_ids()`
  and feeds it into `analyze_dependencies`/`validate_dependencies`/`fix_dependencies`
  and an ad-hoc existence check; widened scan scope → fewer false "unknown
  blocker" reports [Agent 1/2 finding].
- `scripts/little_loops/sprint.py:367` — `DependencyGraph.from_issues(...,
  all_known_ids=...)` for wave ordering; same behavior shift as issue_manager
  [Agent 1 finding].
- `scripts/little_loops/parallel/orchestrator.py:1072,1491` — parallel-sprint
  `close_issue()` callers; confirm they stay in-place-only (they should already,
  per ENH-1418) so the decomposition path is the only remaining mover
  [Agent 1 finding].

### Similar Patterns
- `scripts/little_loops/recursive_finalize.py:_find_issue_file()` (lines
  39–59) — the only lookup helper in the codebase that is already
  `completed/`-aware (`issues_dir.rglob("*.md")`, filtered by
  `include_completed`); a template for making `gather_all_issue_ids()` (or a
  new shared "resolve blocker status regardless of directory" helper)
  legacy-dir-aware.
- `scripts/little_loops/cli/migrate.py:main_migrate()` (lines 87–215,
  ENH-1390) — the established one-time-migration-CLI convention for
  reconciling files left in `completed_dir`/`deferred_dir` back into
  type-scoped directories; could be re-run or extended rather than writing
  new runtime special-casing.
- `scripts/little_loops/issue_lifecycle.py:close_issue()` (lines 621–717) —
  the in-place, no-move convention (ENH-1418) that `finalize_decomposed_parent()`
  should be brought in line with.

_Wiring pass added by `/ll:wire-issue`:_
- **`scripts/little_loops/issue_parser.py:get_next_issue_number()` (lines
  ~453–490)** — the strongest precedent: a *second, independent* "scan all
  issue dirs including legacy `completed`/`deferred`" implementation that is
  **already correct**. It builds `dirs_to_scan` from `config` categories **plus**
  conditionally-appended `completed`/`deferred` paths, each guarded by
  `.exists()` (lines 479–484). Model `gather_all_issue_ids()`'s legacy-dir glob
  directly on this — same shape, same module family — rather than reinventing.
  Caveat (Agent 2): it hardcodes the `"completed"`/`"deferred"` literals and
  does *not* honor `config.issues.completed_dir`/`deferred_dir`; the fix should
  read those config fields (see Configuration below) to avoid inheriting that
  gap [Agent 1/2 finding].
- `scripts/little_loops/issue_lifecycle.py:complete_issue_lifecycle()` /
  `defer_issue()` / `verify_issue_completed()` — the ENH-1418 in-place family
  whose docstrings state the convention verbatim ("Does not move the file …
  ENH-1418 decoupled status from directory location"); the assertion template
  (path unchanged, only frontmatter differs) to mirror when rewriting the
  `test_recursive_finalize.py` move-asserting tests [Agent 3 finding].

### Tests
- `scripts/tests/test_recursive_finalize.py:test_parent_closed_and_moved`
  (lines 40–56) and `test_idempotent` (lines 78–90) — currently assert the
  parent **is** moved to `completed/`; these encode the behavior this bug
  wants changed and will need updating alongside any fix to
  `finalize_decomposed_parent()`.
- `scripts/tests/test_dependency_graph.py:test_known_id_not_in_graph_no_warning`
  (lines 101–109), `test_missing_blocker_logged_warning` (92–99),
  `test_truly_unknown_id_still_warns` (111–118),
  `test_all_known_ids_backward_compatible` (120–126),
  `test_completed_blocker_not_added` (128–140) — existing coverage for the
  `completed`/`all_issue_ids`/`all_known_ids` three-tier disposition; a
  regression test for "a `done` blocker in a legacy dir does not leave
  dependents permanently skipped" belongs in this file or
  `scripts/tests/test_dependency_mapper.py`.
- `scripts/tests/test_dependency_mapper.py:TestGatherAllIssueIds` (lines
  681–769), especially `test_scans_type_dirs_including_done_issues` (lines
  741–769) — currently documents (and asserts) "completed_dir is not used";
  will need a companion test asserting a legacy-dir `done` issue is still
  discoverable once the fix lands.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_recursive_finalize.py:test_cli_children_file_path`
  (lines 102–130) — a **third** move-asserting test (beyond
  `test_parent_closed_and_moved`/`test_idempotent`): drives
  `cmd_finalize_decomposition()` end-to-end and asserts
  `(issues / "completed" / "P2-ENH-200-parent.md").exists()`. Will break under
  the fix; update alongside the other two [Agent 3 finding].
- `scripts/tests/test_builtin_loops.py:TestRecursiveRefineLoop`
  (lines 5279–5318) — `test_enqueue_children_moves_parent_to_completed` and
  `test_enqueue_or_skip_moves_parent_to_completed_when_children_found` string-assert
  `"completed"`/`"mv"` in the FSM action text. **Reconcile first**: ENH-2615
  (`test_..._calls_finalize_decomposition`, lines 4103–4123) already asserts
  `"git mv" not in action` for the CLI-delegated states, so these older
  raw-`mv` assertions may already be stale/coincidentally-passing — check the
  current `enqueue_children`/`enqueue_or_skip` YAML before editing
  [Agent 3 finding].
- `scripts/tests/test_issue_migration.py` (`_make_project()` fixture, lines 35+;
  `TestMigrateCompleted`/`TestMigrateDeferred`) — the model for a new
  "legacy-dir reconciliation" test: a config with `completed_dir`/`deferred_dir`
  keys and issue files placed *only* under those dirs. Reuse its fixture shape
  for the new `gather_all_issue_ids()` legacy-dir test [Agent 3 finding].
- `scripts/tests/test_issue_lifecycle.py` — the in-place-close assertion
  template (path unchanged, only frontmatter differs) to mirror when inverting
  the move-asserting tests above [Agent 3 finding].
- **New tests to write** (no existing coverage) [Agent 3 finding]:
  - `finalize_decomposed_parent(..., move_to_completed=False)` — assert parent
    stays at its type-dir path, `status: done` written, `result["moved"] is False`.
  - `cmd_finalize_decomposition` with `--no-move` — argparse `Namespace(no_move=True)`
    case asserting no move occurred.
  - `gather_all_issue_ids()` legacy-dir awareness — sibling to
    `TestGatherAllIssueIds`, inverting `test_scans_type_dirs_including_done_issues`.
  - **BUG-2728 regression fixture**: a `blocked_by` reference to an ID that
    exists *only* in `.issues/completed/` resolves as satisfied (not "unknown")
    via the `issue_manager.py:1184–1187` `all_known_ids` consumer.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` (lines ~111–119) — defines
  `completed_dir` (default `"completed"`) and `deferred_dir` (default
  `"deferred"`), both annotated `[DEPRECATED: use IssueInfo.status instead]`.
  A legacy-dir-aware `gather_all_issue_ids()` should read these, not hardcode
  literals [Agent 2 finding].
- `scripts/little_loops/config/features.py` — `IssuesConfig.completed_dir` /
  `deferred_dir` fields (the runtime home of those config values). Prefer
  `config.issues.completed_dir`/`deferred_dir` over `"completed"`/`"deferred"`
  string literals [Agent 2 finding].
- `scripts/little_loops/config/core.py` — `BRConfig.issue_categories` property
  (lines ~583–586). **Do NOT** add legacy dirs by mutating this property —
  other consumers rely on it meaning "active type categories." Add a separate
  scan step alongside it, mirroring `get_next_issue_number()`'s `dirs_to_scan`
  append pattern [Agent 2 finding].

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `ll-issues finalize-decomposition` `--no-move`
  entry (~lines 1341–1359, "Do not move the closed parent into the completed
  directory") and the `ll-migrate` section (~lines 2715–2717) framing
  completed/deferred as legacy; both need reconciling if the move default flips
  [Agent 2 finding].
- `docs/reference/API.md` — `get_next_issue_number` entry documents the correct
  "scans … any legacy completed/deferred" contract (precedent); add/adjust the
  `gather_all_issue_ids` entry to match its new scan scope [Agent 2 finding].
- `docs/ARCHITECTURE.md` — Issue Processing Lifecycle mermaid diagram
  (`Move to completed/`, `Move to .issues/completed/`, `Move to .issues/deferred/`)
  is adjacent stale documentation of the move-based model ENH-1418 deprecated;
  the reviewer's first stop for "is `.issues/completed/` still a thing"
  [Agent 2 finding].
- `scripts/little_loops/loops/autodev.yaml` — inline ENH-2615 comments at the
  `enqueue_children`/`enqueue_or_skip` states (~lines 611–617, 867–871) assert
  "finalize-decomposition … owns the status-done close + completed/ move"; update
  the comments if the owned side effect changes [Agent 2 finding].
- `scripts/little_loops/loops/rn-decompose.yaml` — `finalize_parent` state
  (~lines 218–232) calls `ll-issues finalize-decomposition` with **no**
  `--no-move`, i.e. relies on the current default. If the default flips, this
  call site's behavior changes silently unless it passes an explicit flag
  [Agent 2 finding].

## Proposed Fix

- Move `.issues/completed/P2-ENH-2721-usage-events-run-id-live-writer.md` to
  `.issues/enhancements/` (immediate unblock for ENH-2722).
- Stop `finalize_decomposed_parent()` (`recursive_finalize.py:167–173`) from
  moving newly-closed parents into `completed/` — bring it in line with
  ENH-1418's in-place-only convention already used elsewhere. Add a guard
  (test or `ll-verify-*` gate) asserting no new files appear under
  `.issues/completed/`.
- Consider having blocked-by resolution treat a blocker that resolves to a
  `done` issue anywhere on disk (including legacy dirs) as satisfied — e.g.
  make `gather_all_issue_ids()` legacy-dir-aware, following
  `_find_issue_file()`'s `rglob`-based pattern in the same module as the
  write-site fix.

## Acceptance Criteria

- [ ] ENH-2721's file lives in a type-based directory; ENH-2722 dispatches
      without the "unknown issue" warning
- [ ] The closure write path no longer creates files under `.issues/completed/`
- [ ] Regression test: a `done` blocker in a legacy/unscanned directory does not
      leave dependents permanently skipped

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-21_

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 63/100 → LOW

_Re-assessed after the second `/ll:refine-issue` pass (Codebase Research
Findings) and `/ll:decide-issue`. The prior either/or on the write-path remedy
is now resolved (Proposed Fix commits to "stop the move outright"), and the
prior open question on the permanently-blocking mechanism is now resolved
(traced to the `/ll:ready-issue` LLM gate, not the dependency graph). A new,
more consequential gap replaces them below._

### Outcome Risk Factors
- Unresolved decision: the Proposed Fix's third bullet still targets
  `gather_all_issue_ids()` legacy-dir-awareness as the AC #3 remedy, but the
  Codebase Research Findings section explicitly concludes that fix is
  "necessary [for recurrence] but not sufficient" for AC #3 — the actual gate
  that leaves ENH-2722 stuck is `/ll:ready-issue`'s reliance on
  `ll-issues path`/`show`/`list`, which stay type-dir-only regardless of
  `gather_all_issue_ids()`. The Integration Map's "Files to Modify" list does
  not include `show.py:_resolve_issue_id` or
  `search.py:_load_issues_with_status` as modification targets — only as
  "Dependent Files" context — so the plan as written risks satisfying AC #1/#2
  while leaving AC #3 unmet. Resolve before implementing which resolver(s)
  the fix actually targets.
- Broad change surface: `gather_all_issue_ids()` has roughly 8 direct callers
  across `issue_manager.py`, four `cli/sprint/*.py` files, `cli/deps.py`, and
  `sprint.py` — a legacy-dir-aware change shifts warning/graph behavior for
  all of them, not just BUG-2728's specific case, and is compounded now that
  a second resolver family (`ll-issues path`/`show`/`list`) may also need
  touching to satisfy AC #3.


## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-21
- **Reason**: Issue too large for single session — two independent
  component defects (write path vs. read/resolution path) with a
  significant integration surface and an explicitly unresolved decision on
  which resolver(s) satisfy AC #3.

### Decomposed Into
- BUG-2732: `finalize_decomposed_parent()` still moves closed parents into
  legacy `.issues/completed/` (write path + immediate ENH-2721 relocation)
- BUG-2733: `blocked_by` resolution treats a `done` blocker parked in
  `.issues/completed/` as unknown, permanently blocking dependents (read/
  resolution path; carries forward the Open Decision from the parent's
  Outcome Risk Factors)

## Session Log
- `/ll:issue-size-review` - 2026-07-21T23:52:25 - `35cd122b-5b42-4ccf-8307-837e09286f3f.jsonl`
- `/ll:confidence-check` - 2026-07-21T23:55:00 - `d3f1ac90-d570-43e6-a3c7-26787d047b71.jsonl`
- `/ll:decide-issue` - 2026-07-21T23:48:09 - `12b61af3-cfb4-4d62-bb6a-2707c670a322.jsonl`
- `/ll:refine-issue` - 2026-07-21T23:46:01 - `0822acff-4c20-4899-8d73-cd344c5cc332.jsonl`
- `/ll:confidence-check` - 2026-07-21T23:39:39 - `014d002a-1b0f-40ae-949c-fb29ca84775c.jsonl`
- `/ll:wire-issue` - 2026-07-21T23:35:52 - `08b1cad7-e00a-4aaf-8283-0f31093651af.jsonl`
- `/ll:refine-issue` - 2026-07-21T23:29:01 - `fc23a9e9-dd12-4501-838a-5c5615141175.jsonl`
- `/ll:verify-issues` - 2026-07-21T23:08:29 - `9fc8185c-278a-4573-8071-af3d44765f41.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-07-21
- **Decomposed into**: BUG-2732, BUG-2733

Work for BUG-2728 is now carried by its child issues; this parent was closed by rn-decompose.
