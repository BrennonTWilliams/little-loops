---
id: ENH-2436
type: enhancement
status: open
priority: P3
title: ll-issues next-issue should consider Issue dependencies
labels:
- cli
- ll-issues
- dependency-management
captured_at: 2026-07-02 01:50:54+00:00
discovered_date: 2026-07-02
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 57
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 0
---

# P3-ENH-2436: ll-issues next-issue should consider Issue dependencies

## Summary

`ll-issues next-issue` (singular) and `ll-issues next-issues` (plural) currently
select and rank active issues purely by `outcome_confidence`, `confidence_score`,
and `priority_int`. They never inspect Issue dependency edges (`blocked_by`,
`parent` epic chains, `relates_to` blocking links), so a high-confidence issue
that is waiting on an unresolved blocker can be returned ahead of an unblocked,
lower-confidence one.

## Current Behavior

`cmd_next_issue` in `scripts/little_loops/cli/issues/next_issue.py:13-63` and
`cmd_next_issues` in `scripts/little_loops/cli/issues/next_issues.py:13-67`:

1. Call `find_issues(config)` (`scripts/little_loops/issue_parser.py:845-918`),
   which filters issues **only by status** (skips `done`/`cancelled`/`deferred`)
   and has no awareness of any blocking dependency.
2. Sort via `build_sort_key(config.issues.next_issue)` in
   `scripts/little_loops/cli/issues/search.py:182-227`, whose precomputed
   sort-key tuple contains exactly `(-outcome_confidence, -confidence_score,
   priority_int)` under the default `confidence_first` strategy. No dependency
   field appears anywhere in the key.
3. Return the top entry (or all ranked, for the plural form).

Concretely: a `P0 BUG-123` flagged `blocked_by: [BUG-099]` (where BUG-099 is
still `open`) is returned just as readily as an unblocked `P2 BUG-200`, and
will be picked first whenever its confidence/priority math wins.

## Expected Behavior

`ll-issues next-issue` and `ll-issues next-issues` should skip issues that are
**currently blocked** by an unresolved dependency, treating only "ready" issues
as eligible for the top-of-list slot. After the top ready issue is exhausted
or none exists, behavior should degrade gracefully (e.g., surface a warning
that the backlog is fully blocked, or fall back to the current ranking as a
secondary view — see Proposed Solution for the options).

"Blocked" here is whatever the project's existing dependency model considers
blocking: at minimum `blocked_by` edges pointing to a non-`done`/`cancelled`
target. The `parent:` epic relationship is **not** implicitly blocking (per the
epic-progress non-recursive convention), so it should not block a child from
being picked while its epic is still in flight.

## Motivation

- `ll-auto` and `ll-parallel` already received dependency-aware treatment in
  `.issues/enhancements/P2-ENH-016-dependency-aware-sequencing-ll-auto.md` and
  `.issues/enhancements/P2-ENH-017-dependency-aware-scheduling-ll-parallel.md`
  (both `status: done`). Closing the same gap in `ll-issues next-issue` keeps
  the issue-selection surface internally consistent: a human running the same
  ranking an automation runner uses should not pick a blocked issue first.
- Users who drive `/ll:manage-issue` or any manual workflow off
  `ll-issues next-issue` (e.g., scripts, CI selection, ad-hoc review) currently
  have to pre-filter `blocked` issues themselves, which is fragile and easy
  to skip.
- Consistent semantics with `/ll:map-dependencies` and the documented
  `relates_to`/`blocked_by` data model.

## Proposed Solution

The change has three layers; per-layer options below.

### Layer 1 — Filter blocking at the candidate set

Extend `find_issues()` (`scripts/little_loops/issue_parser.py:845`) with an
optional `skip_blocked: bool = False` parameter (default `False` to preserve
existing behavior for callers that don't want it):

- When `True`, exclude any issue whose `Blocked By` edges reference a non-
  terminal (`status: done`/`cancelled`) issue.
- When `False` (default), current behavior is byte-identical.

This keeps the change opt-in for callers that don't want it, while letting
`cmd_next_issue` / `cmd_next_issues` turn it on unconditionally. A pure
addition — no existing caller breaks.

### Layer 2 — Surface "ready vs blocked" in the output

Two viable options, decoupled from Layer 1:

- **Option A — silent skip (simple)**: the command simply picks the top
  ready issue; if none exist, exit 1 with stderr message
  `"No ready issues (all active issues are blocked)"`.
- **Option B — dual-view output**: add a `--include-blocked` flag; default
  stays silent-skip, but `--include-blocked` returns the full ranked list
  with a `blocked: true|false` field, so downstream consumers (sprints,
  scripts) can distinguish. This matches the precedent set by
  `ll-issues list --include-completed` for status filtering.

> **Selected:** Option B — dual-view output — matches the established `--include-completed`/`--include-orphans` pair pattern in `cli/issues/__init__.py:281-287, 415-421` and reuses `cmd_sequence`'s per-row JSON decoration at `cli/issues/sequence.py:54`.

Recommended: **Option B** — it preserves power-user workflows without
breaking the common case, and the flag pattern is already established.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-01.

**Selected**: Option B — dual-view output

**Reasoning**: Option B directly mirrors the codebase's established `--include-completed`/`--include-orphans` argparse pair (`cli/issues/__init__.py:281-287`, `415-421`) and reuses `cmd_sequence`'s per-row `blocked_by` JSON decoration (`cli/issues/sequence.py:54`) for the new `blocked` field. While Option A is simpler on the surface, it would split the `--include-*` pair pattern by introducing a third silent-drop category with no recovery flag — the only such case in the CLI surface. Option B's incremental cost is negligible (the same `find_issues(skip_blocked=...)` plumbing powers both), and the structured `blocked` field benefits downstream consumers (`auto-refine-and-implement.yaml:107`, `refine-to-ready-issue.yaml:28-30`, `lib/cli.yaml:50-57`) in ways a stderr message cannot reach.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — silent skip (simple) | 2/3 | 3/3 | 3/3 | 3/3 | 11/12 |
| Option B — dual-view output | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |

**Key evidence**:
- Option A: matches the stderr+exit-1 convention (30+ sibling subcommands), but splits the established `--include-*` pair pattern — `cmd_list`'s default status filter is explicit and visible, but Option A would silently drop dependency-blocked issues with no `--include-blocked` recovery flag, the first such case in the CLI surface.
- Option B: `--include-completed` and `--include-orphans` provide exact argparse shape precedent (`action="store_true"`, `default=False`, `dest="include_*"`); `cmd_sequence` JSON output at `sequence.py:54` provides per-row dependency field precedent; `test_include_completed` (`test_issues_search.py:372-390`) provides the test harness template; `DependencyGraph.get_ready_issues()` / `is_blocked()` / `get_blocking_issues()` (`dependency_graph.py:147-171, 236-260`) provide all primitives.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Reuse `DependencyGraph` rather than write a parallel `_is_blocked()` helper.**
  The codebase already has a complete dependency module at
  `scripts/little_loops/dependency_graph.py` with three methods that map
  exactly to the problem this issue solves:
  - `DependencyGraph.is_blocked(issue_id, completed)` (lines 236-246)
  - `DependencyGraph.get_blocking_issues(issue_id, completed)` (lines 248-260)
  - `DependencyGraph.get_ready_issues(completed)` (lines 147-171) — returns
    issues with no unresolved blockers, sorted by `(priority_int, issue_id)`.

  The proposed `_is_blocked(info, by_id)` helper in the Implementation Steps
  duplicates this logic. Recommend either:
  (a) build a `DependencyGraph` once inside `find_issues()` and filter via
  `graph.get_ready_issues(completed)` when `skip_blocked=True`, or
  (b) if a lighter-weight inline check is preferred, document explicitly
  why the duplication is justified (e.g., to avoid a graph-build cost on
  large backlogs).

- **In-`ll-issues` precedent for the graph build.** `cmd_sequence` in
  `scripts/little_loops/cli/issues/sequence.py:14-79` already builds a
  `DependencyGraph` from the same `find_issues()` candidate set and emits
  `blocked_by` in its JSON output (line 54). That is the closest sibling
  command and provides a tested shape for the new `blocked` field on
  `next-issue --include-blocked --json`.

- **`AutoManager._get_next_issue` is the canonical dependency-aware
  pattern** at `scripts/little_loops/issue_manager.py:1198-1263` (ENH-016).
  It calls `dep_graph.get_ready_issues(completed)`, applies skip/only/type/
  priority/label filters, and falls back to `_log_blocked_issues(...)`
  (lines 1265-1280) when no candidates are ready — the textual counterpart
  of the stderr exit-1 message proposed here.

### Layer 3 — Optional: parent-epic gating

If desired as a follow-on (out of scope for the first pass, tracked
separately to honor the `parent:` non-recursive convention), expose
`skip_epic_children: bool` to also skip children whose parent epic is not
`done`. Suggest splitting this into a sibling issue rather than coupling it
here, since the convention is documented as non-recursive
(`/ll:scoped automation reference` / `ll-issues epic-progress`).

## Acceptance Criteria

- [ ] `find_issues()` accepts `skip_blocked=False` by default and excludes
      blocked issues only when set.
- [ ] `cmd_next_issue` and `cmd_next_issues` set `skip_blocked=True` so
      blocked issues are filtered out of the candidate set by default.
- [ ] An `--include-blocked` flag (Option B) is added; default omits blocked
      issues; flag re-includes them and stamps a `blocked` field on each
      JSON output row.
- [ ] When no ready issue exists, exit 1 with a stderr message naming the
      blocker count (e.g., `"No ready issues (3 blocked, 0 ready)"`).
- [ ] Existing callers of `find_issues()` are unaffected (byte-identical
      output when `skip_blocked=False`).
- [ ] Unit tests in `scripts/tests/test_next_issue.py` and
      `scripts/tests/test_next_issues.py` cover: unblocked-only selection,
      all-blocked exit, `--include-blocked` JSON shape, and the byte-identical
      no-flag default for backward compatibility.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In scope**: dependency-aware candidate filtering for
  `ll-issues next-issue` / `next-issues`; output field for downstream
  consumers; tests and docs updates.
- **Out of scope**: parent-epic gating (Layer 3 — track separately);
  changing `ll-issues list`/`search` (those are explicit queries and
  should still return everything matching the filter); changing
  `find_issues()`'s default `skip_blocked=False` behavior for any caller
  other than `cmd_next_issue`/`cmd_next_issues`.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — `find_issues()` (~line 845):
  add `skip_blocked: bool = False` parameter; pass an "is blocked by open
  issue?" check using parsed IssueInfo data. Reuses existing frontmatter
  parsing — no new parsers needed.
- `scripts/little_loops/cli/issues/next_issue.py` — `cmd_next_issue` (line
  13): call `find_issues(config, skip_blocked=True)`; add argparse
  `--include-blocked` and a `blocked` field on the JSON output when
  `--include-blocked` is passed.
- `scripts/little_loops/cli/issues/next_issues.py` — `cmd_next_issues` (line
  13): same changes — `skip_blocked=True` by default; `--include-blocked`
  flag; `blocked` field on each JSON row.
- `scripts/little_loops/cli/args/issues.py` (or wherever next-issue/next-issues
  argparse is registered) — wire `--include-blocked`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Argparse location correction.** The plan refers to
  `scripts/little_loops/cli/args/issues.py`, but no such file exists
  (`Glob` confirms only `scripts/little_loops/cli/issues/__init__.py`).
  The actual registration sites for the two subcommands are:
  - `next-issue` (alias `nx`) subparser — `scripts/little_loops/cli/issues/__init__.py:535-544`
  - `next-issues` (alias `nxs`) subparser — `scripts/little_loops/cli/issues/__init__.py:546-562`
  - Dispatch to `cmd_next_issue` / `cmd_next_issues` — `scripts/little_loops/cli/issues/__init__.py:770-773`

  Add the `--include-blocked` argument to both `nx` and `nxs` parser
  definitions in `__init__.py`; the issue's path reference is stale and
  should be updated when the implementation lands.

- **`--include-blocked` flag precedent in the same file.** Two existing
  `--include-*` flags are already wired in `cli/issues/__init__.py` and
  match the proposed flag shape (`action="store_true"`, `dest=...`):
  - `--include-completed` at `cli/issues/__init__.py:281-287`
    (consumed in `cli/issues/search.py:296-302`)
  - `--include-orphans` at `cli/issues/__init__.py:415-421` (clusters subcommand)

  Mirror the `--include-completed` pattern: `add_argument("--include-blocked",
  action="store_true", default=False, dest="include_blocked", help=...)`
  on both `nx` and `nxs` parsers. Consumer: read via
  `getattr(args, "include_blocked", False)` in each `cmd_next_*` body.

- **`next-issue` currently has `--skip` via `add_skip_arg(nx)` from
  `scripts/little_loops/cli_args.py:57-72`.** `next-issues` does **not**
  register `--skip` today (the plural handler ignores it). If symmetry
  matters, register `--skip` on `nxs` in the same edit; otherwise leave as-is.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

The default `skip_blocked=False` keeps every other `find_issues()` caller
byte-identical; the following are listed for awareness and so any future
maintainer can verify the contract without re-deriving it:

- `scripts/little_loops/issue_parser.py:940` — `find_highest_priority_issue()`
  internal wrapper. Does **not** forward `skip_blocked`; protected if the new
  parameter is declared keyword-only (`*, skip_blocked: bool = False`).
- `scripts/little_loops/issue_manager.py:1170` — `AutoManager.__init__` seeds
  its dep graph from `find_issues(self.config, self.category)`. Already builds
  its own `DependencyGraph.from_issues(...)` so semantics are unchanged.
- `scripts/little_loops/parallel/priority_queue.py:244` —
  `IssuePriorityQueue.scan_issues()`. Unaffected.
- `scripts/little_loops/hooks/sweep_stale_refs.py:159, 166` — `done_issues` and
  `open_issues` lookups in the session_end hook. Unaffected.
- `scripts/little_loops/sprint.py:325` — `SprintManager.load_or_resolve`.
- `scripts/little_loops/cli/deps.py:38, 269` — `cmd_deps()` and the local
  `_find_issues` alias used by `tree` rendering.
- `scripts/little_loops/cli/issues/set_status.py:75` — `all_issues` lookup.
- `scripts/little_loops/cli/issues/next_action.py:30` — `cmd_next_action()`.
- `scripts/little_loops/cli/issues/refine_status.py:281` —
  `cmd_refine_status()`.
- `scripts/little_loops/cli/issues/epic_consistency.py:274` —
  `cmd_epic_consistency()`.
- `scripts/little_loops/cli/issues/epic_progress.py:53` —
  `cmd_epic_progress()`.
- `scripts/little_loops/cli/issues/sequence.py:28` — `cmd_sequence()` (issue's
  own graph-building precedent).
- `scripts/little_loops/cli/issues/clusters.py:311` — `cmd_clusters()`.
- `scripts/little_loops/cli/issues/impact_effort.py:188` —
  `cmd_impact_effort()`.
- `scripts/little_loops/cli/issues/list_cmd.py:154` — `cmd_list()` (imported
  as `_find_issues_all`).

**FSM loop shell-out consumers** — observe the new exit-1 contract; the change
is a transparent improvement in all three sites:

- `scripts/little_loops/loops/auto-refine-and-implement.yaml:107` —
  `resolve_set` action shells `ll-issues next-issues`. The existing empty-LIST
  guard at lines 113-116 swallows the new exit-1 path; behavior is identical.
  Add a comment note on line 78 clarifying the dependency-filter semantics.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:28-30` —
  `resolve_issue` action shells `ll-issues next-issue` as the standalone
  fallback. When run standalone against a fully-blocked backlog, the loop now
  routes to `diagnose` instead of selecting the next unblocked issue. No code
  change required (already covered by the issue's Impact section), but worth
  a regression test fixture.
- `scripts/little_loops/loops/lib/cli.yaml:50-57` — `ll_issues_next_issue`
  shared fragment. No callsite currently uses the fragment, but downstream
  loops that build on it will see a new `on_no` trigger for the all-blocked
  case; document the override pattern (`action: "ll-issues next-issue
  --include-blocked"`) in the fragment description.

### Tests

- `scripts/tests/test_next_issue.py` — add cases: blocked issue is skipped
  by default; `--include-blocked` returns it with `blocked: true`; all-
  blocked backlog exits 1 with a stderr message; existing default
  behavior is byte-identical.
- `scripts/tests/test_next_issues.py` — same coverage for the plural form.
- Regression: `scripts/tests/test_issue_parser.py::TestFindIssues` — a new
  case that `find_issues(skip_blocked=False)` produces byte-identical output
  to the current behavior.

_Wiring pass added by `/ll:wire-issue`:_

The following test files exercise `find_issues()` (or mock it) and need
verification that the new `skip_blocked=False` default preserves their
behavior:

- `scripts/tests/test_issue_workflow_integration.py:139, 158, 461, 467` — four
  direct calls to `find_issues(config)` and category-filtered variants. Add
  a regression assertion that no behavior change occurs when `skip_blocked`
  is left at its default.
- `scripts/tests/test_issue_parser_fuzz.py:324` —
  `test_find_issues_handles_mixed_files` Hypothesis fuzz test. Should remain
  green (default is byte-identical); re-run after the change lands.
- `scripts/tests/test_priority_queue.py:649-731` — `TestScanIssues` class
  patches `little_loops.parallel.priority_queue.find_issues`; pattern-based
  mock unaffected but worth re-running to confirm.
- `scripts/tests/test_issue_manager.py` — extensive coverage of
  `AutoManager._get_next_issue` (lines 576, 596, 615, 733, 751, 771, 787,
  844, 860, 877, 893; concurrent paths at 3163, 3177, 3192, 3239-3249) and
  the `dep_graph.get_ready_issues(set())` assertion at line 3366. The graph
  is built directly inside `AutoManager.__init__`, so this code path is
  independent of the new `skip_blocked` parameter — verify post-merge by
  running `python -m pytest scripts/tests/test_issue_manager.py`.

**Helper extension required** (both files):

- `scripts/tests/test_next_issue.py:19-46` — `_make_issue` helper currently
  writes only `confidence_score` / `outcome_confidence` frontmatter and a
  `# Title` + `## Summary` body. Extend with a `blocked_by: list[str] | None
  = None` keyword argument that writes YAML frontmatter `blocked_by:` (the
  `IssueParser.parse_file` path prefers frontmatter per `issue_parser.py:536-562`).
- `scripts/tests/test_next_issues.py:19-46` — twin of the above; identical
  extension required.

**New test classes to add**:

- `scripts/tests/test_next_issue.py::TestNextIssueBlockedFilter` — five cases:
  blocked issue excluded by default; `--include-blocked` re-includes it;
  `--include-blocked --json` row carries `blocked: true`; all-blocked
  backlog exits 1 with stderr `"Error: No ready issues (N blocked, 0 ready)"`;
  `done`/`cancelled` blockers unblock the issue (per
  `_TERMINAL_STATUSES = frozenset({"done", "cancelled"})` at
  `issue_progress.py:14`).
- `scripts/tests/test_next_issues.py::TestNextIssuesBlockedFilter` — same
  five cases adapted for the plural form (ranked output, JSON-array output,
  `--include-blocked` re-includes all, exit 1 with stderr).
- `scripts/tests/test_issue_parser.py::TestFindIssues` — add
  `test_find_issues_skip_blocked_*` cases covering: default includes blocked;
  `True` excludes blocked; `done`/`cancelled` blockers do not block;
  `deferred` blocker does still block (deferred is non-terminal per
  `_TERMINAL_STATUSES`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`_make_issue` test helper needs extension.** The helper at
  `scripts/tests/test_next_issue.py:19-46` (and its twin in
  `scripts/tests/test_next_issues.py`) currently does **not** write
  `blocked_by` to the fixture file. To exercise the new behavior, extend
  the helper to accept a `blocked_by: list[str] | None = None` parameter
  and write the corresponding `Blocked By:` body section. Reference
  implementation: `scripts/tests/test_dependency_graph.py::make_issue`
  (lines 18-39) — already supports `blocked_by`, `blocks`, `depends_on`,
  `relates_to`, `parent`.

- **Body-section parser test precedent.** `scripts/tests/test_issue_parser.py`
  has `test_parse_blocked_by_*` (lines 1331-1658) covering single/multiple/
  empty/`None`/bold-markdown/`to_dict` roundtrip/comma-string-frontmatter/
  YAML-list-frontmatter variants. Re-use these patterns when asserting
  that the new `skip_blocked` parameter correctly reads both frontmatter
  and `## Blocked By` body sources.

- **Closest test-harness template for the new `--include-blocked` flag.**
  `TestNextIssueSkipFlag` (`scripts/tests/test_next_issue.py:369-484`) and
  `TestNextIssueEdgeCases` (`scripts/tests/test_next_issue.py:487-534`) are
  the harness shape to mirror: `patch.object(sys, "argv", [...])`, call
  `main_issues()`, inspect stdout via `capsys.readouterr()`, assert
  `result == 0` (success) or `result == 1` (no candidates). In particular,
  `test_skip_only_issue_returns_exit_1` (lines 410-432) already covers the
  "all candidates excluded → exit 1" shape needed for the all-blocked case.

- **`--include-*` flag test precedent.** `test_include_completed` in
  `scripts/tests/test_issues_search.py:372-390` exercises the
  `--include-completed` flag end-to-end (`patch.object(sys, "argv", [...,
  "search", "--include-completed", ...])`, assert `result == 0`, check
  stdout). Mirror this exactly for `--include-blocked`.

- **Sibling JSON-shape precedent.** `test_sequence_json_includes_blocked_by_and_blocks`
  (`scripts/tests/test_issues_cli.py:1293`) already asserts that
  `ll-issues sequence --json` includes `blocked_by` and `blocks` per issue.
  Use this as the assertion shape for the new `blocked` field on
  `next-issue --include-blocked --json`.

- **Blocked-status fixture precedent.** `test_blocked_child`
  (`scripts/tests/test_issues_cli.py:4828`) uses a fixture with
  `status: blocked` + `parent: EPIC-001` + `blocked_by: [BUG-099]`.
  Reuse this fixture shape when testing that a `blocked_by` edge is what
  the new filter inspects (rather than `status: blocked`).

### Documentation

- `docs/reference/CLI.md` — `ll-issues next-issue` / `next-issues` sections:
  document `--include-blocked` and the new exit-1 stderr message.
- `.claude/CLAUDE.md` — if a `## Commands & Skills` row exists for
  `next-issue` / `next-issues`, note the default skip-blocked behavior.
- `docs/development/TROUBLESHOOTING.md` (only if a common "why is my issue
  not showing up" question appears) — short note on dependency filtering.

_Wiring pass added by `/ll:wire-issue`:_

The following doc updates are required for parity (in addition to the
`docs/reference/CLI.md` entry already listed above):

- `docs/reference/API.md:811-840` — `find_issues` signature block: add the
  new `skip_blocked: bool = False` keyword-only parameter to the documented
  signature, Parameters block, and the byte-identical-default clause.
- `docs/reference/API.md:3417-3497` — both `#### next-issue` (3417-3456)
  and `#### next-issues` (3458-3497) sections: add `--include-blocked` row
  to the flags table; add an example line; update the Exit-codes block to
  document the new all-blocked exit-1 case.
- `docs/reference/CONFIGURATION.md:929-965` — `### issues.next_issue`
  prose at line 931 promises "byte-identical to the legacy hardcoded
  ordering, so existing projects see no change until they opt in". That
  promise now has a caveat: the default mode filters out blocked issues.
  Either tighten the prose or add a "Behaviour changes by release" note.
  No new config key required (CLI-only flag).
- `docs/guides/LOOPS_REFERENCE.md:853, 3187` — `auto-refine-and-implement`
  resolve_set entry (line 853) and the `ll_issues_next_issue` fragment
  table row (line 3187). Add a one-line note that the top-ranked issue
  is now unblocked-only by default and that the fragment can be
  overridden with `--include-blocked` to preserve the legacy behavior.
- `CHANGELOG.md` — per memory rule `feedback_changelog_no_unreleased`,
  do NOT add to the `[Unreleased]` block; add a future `## [X.Y.Z]` entry
  during release prep with `Added` (new `--include-blocked` flag),
  `Changed` (default skip-blocked behavior in `next-issue(s)`), and an
  exit-code contract note for the new all-blocked path.

## Implementation Steps

1. Add `skip_blocked` parameter to `find_issues()` and an `_is_blocked()`
   helper that walks `Blocked By` (the existing frontmatter field) and
   checks each target's terminal status.
2. Wire `cmd_next_issue` and `cmd_next_issues` to call with
   `skip_blocked=True` by default.
3. Add `--include-blocked` argparse flag and propagate it through both
   commands; emit `blocked` per-row in JSON output when set.
4. Update the no-ready-issues exit path to stderr a count summary.
5. Add unit tests for the four cases listed in Acceptance Criteria.
6. Update `docs/reference/CLI.md` and any in-repo command listings.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

7. **Declare `skip_blocked` as keyword-only** (`*, skip_blocked: bool = False`)
   so `find_highest_priority_issue()` at `issue_parser.py:921-941` (which
   calls `find_issues` positionally) does not accidentally receive a
   `skip_blocked` positional argument and stay byte-identical for the 13
   other callers listed in the Dependent Files section.
8. **Import `_TERMINAL_STATUSES` from `little_loops.issue_progress`** at the
   top of `issue_parser.py` rather than redefining the literal
   `("done", "cancelled")` tuple inside `_is_blocked()`. The constant lives
   at `scripts/little_loops/issue_progress.py:14` and is already imported by
   `cli/issues/set_status.py:35`.
9. **Mirror the `--include-completed` flag precedent** at
   `cli/issues/__init__.py:281-287` for the new `--include-blocked` argument
   on both `nx` (line 536) and `nxs` (line 547) subparsers. Consumer code
   reads via `getattr(args, "include_blocked", False)` per the issue's
   existing Codebase Research note.
10. **Update `docs/reference/API.md`** (`find_issues` signature block at
    811-840; `next-issue`/`next-issues` sections at 3417-3497) and
    `docs/reference/CONFIGURATION.md:929-965` for the new flag and
    default-mode filtering caveat. See Documentation section above for the
    full doc-update list.
11. **Extend the `_make_issue` test helpers** at
    `scripts/tests/test_next_issue.py:19` and
    `scripts/tests/test_next_issues.py:19` to accept
    `blocked_by: list[str] | None = None` and write a YAML frontmatter
    `blocked_by:` key. Mirror the `make_issue` helper at
    `scripts/tests/test_dependency_graph.py:18-39`.
12. **Add `TestNextIssueBlockedFilter` and `TestNextIssuesBlockedFilter`**
    test classes (5 cases each) covering: blocked excluded by default;
    `--include-blocked` re-includes; `--include-blocked --json` adds
    `blocked: true`; all-blocked backlog exits 1 with the new stderr
    message; `done`/`cancelled` blockers unblock the issue.
13. **Add `test_find_issues_skip_blocked_*` cases to
    `scripts/tests/test_issue_parser.py::TestFindIssues`** as the
    byte-identical-default regression sentinel (4 cases: default includes,
    `True` excludes, terminal-status whitelist, deferred is non-terminal).
14. **Verify FSM loop transparent behavior post-merge** by running
    `ll-loop run auto-refine-and-implement --context max_issues=5` and
    `ll-loop run refine-to-ready-issue` against a fixture where the
    top-ranked issue is `blocked_by` a still-open issue; both should
    either fall through to the next unblocked candidate or exit cleanly
    to the existing "no work" route. Add a regression test fixture
    (alongside the existing `TestAutoRefineAndImplementLoop` tests at
    `scripts/tests/test_builtin_loops.py:1706+`) if the loop's exit-code
    contract changes observably.

## API/Interface

### CLI changes — `ll-issues next-issue` and `ll-issues next-issues`

New flag (both singular and plural form):

```text
--include-blocked    Include issues with unresolved blockers in the ranked
                     output. By default, blocked issues are filtered out.
                     When set, each JSON output row carries a `blocked`
                     field (true/false).
```

Exit-code contract:

| Condition | Exit | Stderr |
|-----------|------|--------|
| At least one ready issue returned | 0 | _(none)_ |
| `--include-blocked` set, any active issues returned | 0 | _(none)_ |
| No ready issues exist (default mode) | 1 | `No ready issues (N blocked, 0 ready)` |

JSON output shape (per row, when `--include-blocked` is set):

```json
{
  "id": "ENH-2436",
  "title": "...",
  "priority": "P3",
  "confidence_score": 0.0,
  "outcome_confidence": 0.0,
  "blocked": true,
  "blocked_by": ["BUG-0099"]
}
```

### Internal API change — `find_issues()`

Signature delta in `scripts/little_loops/issue_parser.py`:

```python
# Before
def find_issues(config: LLConfig) -> list[IssueInfo]: ...

# After
def find_issues(
    config: LLConfig,
    *,
    skip_blocked: bool = False,
) -> list[IssueInfo]: ...
```

- `skip_blocked=False` (default) → byte-identical to current behavior; no existing
  caller is affected.
- `skip_blocked=True` → exclude any issue whose `Blocked By` references a
  non-terminal (`status: done` or `cancelled`) issue.

Helper added (private to the module):

```python
def _is_blocked(info: IssueInfo, by_id: dict[str, IssueInfo]) -> bool:
    """True if any of info.blocked_by points to a non-terminal issue."""
```

`cmd_next_issue` and `cmd_next_issues` opt in by passing
`skip_blocked=True` unconditionally; this is the only behavior change visible
to end users.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Match the existing stderr message style.** The current
  `cmd_next_issue` already has two exit-1 patterns:
  - `print(f"Error: {e}", file=sys.stderr); return 1` for invalid strategy
    (line 34 of `scripts/little_loops/cli/issues/next_issue.py`)
  - silent `return 1` for the empty-candidate case (line 40)

  The new all-blocked stderr message should follow the line-34 style
  for grep-ability and consistency. Suggested message text:

  ```python
  print(
      f"Error: No ready issues ({blocked_count} blocked, 0 ready)",
      file=sys.stderr,
  )
  return 1
  ```

  The `f"Error: ..."` prefix and `file=sys.stderr` channel match the
  established convention. Apply the same shape to `cmd_next_issues`
  (line 38 of `scripts/little_loops/cli/issues/next_issues.py`).

- **`_is_blocked()` helper vs. `DependencyGraph` — design decision.**
  The proposed `_is_blocked(info, by_id)` signature requires the caller
  to build a `dict[str, IssueInfo]` lookup table; that is exactly the
  data structure `DependencyGraph.from_issues()` already constructs.
  Two viable implementations to choose between at implementation time:

  1. **Lightweight inline (per the plan)**: keep `_is_blocked(info, by_id)`
     as a pure function; build `by_id` once inside `find_issues()` from
     the already-loaded list. Pros: zero new module dependencies; minimal
     blast radius. Cons: duplicates terminal-status detection logic that
     lives in `DependencyGraph.get_blocking_issues` already.

  2. **Reuse `DependencyGraph` (recommended based on existing precedent)**:
     inside `find_issues()`, when `skip_blocked=True`, build
     `DependencyGraph.from_issues(all_issues)` and filter via
     `graph.get_ready_issues(completed)`. Pros: zero duplication, same
     code path as `cmd_sequence` and `AutoManager`. Cons: graph build
     adds O(N) work per call, but `find_issues()` is not on a hot path.

  Either is correct; document the choice in the implementation PR. The
  Acceptance Criterion "byte-identical output when `skip_blocked=False`"
  is satisfied by both.

- **No `IssueStatus` enum.** Terminal-status detection is repeated as
  inline `("done", "cancelled")` tuples across `issue_parser.py:891`,
  `issue_manager.py:196`, `issue_lifecycle.py:465`, `sync.py:277,981`,
  and `parallel/worker_pool.py:841`. The canonical constant is
  `_TERMINAL_STATUSES = frozenset({"done", "cancelled"})` at
  `scripts/little_loops/issue_progress.py:14` (imported by
  `cli/issues/set_status.py:35`). `_is_blocked()` should import and
  reuse this constant rather than redefining the literal tuple.

## Impact

- **Priority**: P3 — quality-of-life improvement; the current behavior is
  surprising, not unsafe (a user who doesn't know about dependencies is no
  worse off than a user who does, but they're also not protected from
  picking blocked work).
- **Effort**: Small — additive `skip_blocked` parameter plus a `--include-
  blocked` flag and a few test cases. Reuses existing frontmatter parsing.
- **Risk**: Low — `find_issues()` defaults are preserved; only
  `cmd_next_issue`/`cmd_next_issues` change behavior. The exit-1 change
  in the all-blocked case is the only user-visible default change and is
  paired with a clear stderr message.
- **Breaking Change**: No for opt-in callers; yes for the all-blocked exit
  code path (was 0 if any issues existed, now 1 if none are ready) —
  document this in the changelog under whatever release ships it.

## Related Key Documentation

- `.issues/enhancements/P2-ENH-016-dependency-aware-sequencing-ll-auto.md` —
  prior art for dependency-aware sequencing, scoped to `ll-auto`. **Done.**
- `.issues/enhancements/P2-ENH-017-dependency-aware-scheduling-ll-parallel.md`
  — prior art for dependency-aware scheduling, scoped to `ll-parallel`.
  **Done.**
- `scripts/little_loops/issue_parser.py` — `find_issues()` definition (line
  845).
- `scripts/little_loops/cli/issues/search.py` — `build_sort_key()` (line 182)
  for the current sort contract.
- `commands/map-dependencies/` — the explicit `/ll:map-dependencies` skill,
  which is the current manual dependency-edge source-of-truth.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`scripts/little_loops/dependency_graph.py`** — `DependencyGraph` dataclass
  (lines 32-53), `from_issues()` (lines 55-145), `get_ready_issues()`
  (lines 147-171), `is_blocked()` (lines 236-246), `get_blocking_issues()`
  (lines 248-260). Reuse this module rather than duplicating its logic —
  see the Proposed Solution enrichment above for the design trade-off.

- **`scripts/little_loops/cli/issues/sequence.py`** (`cmd_sequence()`,
  lines 14-79) — the closest in-family precedent. Already builds a
  `DependencyGraph` from `find_issues()`, runs `topological_sort()`, and
  emits `blocked_by` in its JSON output (line 54). When implementing
  ENH-2436, mirror `cmd_sequence`'s shape for the new `blocked` field
  on `next-issue --include-blocked --json`.

- **`scripts/little_loops/issue_manager.py`** — `AutoManager.__init__`
  (lines 1168-1185) and `AutoManager._get_next_issue` (lines 1198-1263) are
  the canonical dependency-aware selection pattern. The graph is built
  once in `__init__`, and `_get_next_issue` calls
  `dep_graph.get_ready_issues(completed)` then applies skip/only/type/
  priority/label filters. Pair with `_log_blocked_issues()` (lines
  1265-1280) for the textual counterpart of the new stderr exit-1.

- **`scripts/little_loops/issue_progress.py:14`** —
  `_TERMINAL_STATUSES = frozenset({"done", "cancelled"})` is the canonical
  terminal-status constant. Import this in `_is_blocked()` rather than
  redefining the literal tuple.

- **Downstream consumers (loops that call `next-issue` / `next-issues`):**
  these commands are used inside three FSM loops and the behavior change
  may affect them. Verify behavior post-implementation by re-running the
  loops with the change in place:
  - `scripts/little_loops/loops/auto-refine-and-implement.yaml` — line 78
    (comment) and line 107 (`LIST=$(ll-issues next-issues ...`)
  - `scripts/little_loops/loops/refine-to-ready-issue.yaml` — line 29
    (`ll-issues next-issue; }`)
  - `scripts/little_loops/loops/lib/cli.yaml` — lines 50-55
    (`ll_issues_next_issue` step)
  - Test coverage: `scripts/tests/test_builtin_loops.py` — line 1706
    (`get_next_issue` ref), lines 1738-1744 assert `ll-issues next-issues`
    appears in `resolve_set backlog` action.

  None of these consumers appears to depend on the current behavior of
  surfacing blocked issues at the top of the list, so the default-skip
  change should be a transparent improvement. Add a regression test that
  exercises `auto-refine-and-implement.yaml` (or `refine-to-ready-issue.yaml`)
  against a fixture where the top-ranked issue is `blocked_by` a still-open
  issue, asserting the loop falls through to the next unblocked candidate.

## Labels

`enhancement`, `cli`, `ll-issues`, `dependency-management`

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-02_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 57/100 → LOW

### Notes (updated post-Layer-1)

Layer 1 (commit `19d4dd43`) shipped the keyword-only `skip_blocked: bool = False`
parameter on `find_issues()` with four unit tests in `TestFindIssues`. The
remaining work is Layer 2 (CLI surface for `cmd_next_issue` / `cmd_next_issues`)
plus the integration test added in this commit that exercises every kwarg shape
the 13 external callers use, asserting the default is byte-identical.

### Outcome Risk Factors

- **Remaining change surface (Layer 2 only).** The breadth-across-callers risk
  flagged before Layer 1 was retired by the keyword-only default: callers that
  don't pass `skip_blocked` continue to get the pre-change result without
  per-caller verification. The integration test added in this commit is the
  per-implementation-locus breadth sentinel — it walks the 13 callers' kwarg
  shapes and asserts byte-identity, so any future regression in `find_issues()`
  that reorders, deduplicates, or reorders status filtering will surface
  immediately.
- **User-visible behavior shift (Layer 2).** The default change in
  `cmd_next_issue` / `cmd_next_issues` (top of list is now an unblocked issue)
  plus the new exit-1 path for an all-blocked backlog are the only user-visible
  changes. Three FSM loops (`auto-refine-and-implement.yaml`,
  `refine-to-ready-issue.yaml`, `lib/cli.yaml`) consume these commands; their
  existing empty-candidate and exit-1 routes already cover the new behavior,
  so this is a transparent improvement rather than a breaking one.
- **Why outcome confidence is still 57.** The uncertainty sits in the user-
  surface layer, not the implementation: whether `--include-blocked` is the
  right flag name, whether the all-blocked exit-1 is the right exit code, and
  whether downstream workflows will need a migration note. None of these are
  blockers for Layer 2 — they are follow-on calibration questions that
  resolve in the first sprint of real-world use.

## Session Log
- `/ll:confidence-check` - 2026-07-02T20:55:26 - `9d02b2f6-5396-47a3-a74d-144f2283337c.jsonl`
- `/ll:decide-issue` - 2026-07-02T02:36:37 - `64610888-7400-4f39-b171-4825f84a8759.jsonl`
- `/ll:wire-issue` - 2026-07-02T02:23:22 - `bd4904c3-9618-4f6f-883b-d4597ec4eda8.jsonl`
- `/ll:refine-issue` - 2026-07-02T02:09:28 - `ea47d6be-ecee-41c2-9918-0eee9aeca58a.jsonl`
- `/ll:format-issue` - 2026-07-02T01:54:22 - `20fc75fb-9899-40ff-8a4b-e2769c3146f7.jsonl`
- `/ll:capture-issue` - 2026-07-02T01:50:54Z - `da779351-747f-430a-a983-842762d5b619.jsonl`

## Status

**Open** | Created: 2026-07-02 | Priority: P3
