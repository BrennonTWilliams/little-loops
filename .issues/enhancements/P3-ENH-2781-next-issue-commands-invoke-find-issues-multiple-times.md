---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:44+00:00
discovered_by: scan-codebase
completed_at: '2026-07-25T07:13:51Z'
blocked_by:
- ENH-2780
parent: EPIC-2792
confidence_score: 92
outcome_confidence: 85
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 20
status: done
priority: P3
---

<!-- Suggested by scan-codebase: file overlap with issue_parser.py (ENH-2780) -->

# ENH-2781: `next-issue`/`next-issues` invoke `find_issues` 2-4 times per command; parse once and share

## Summary

A single `ll-issues next-issue`/`next-issues` invocation parses the entire
issue directory multiple times: with `--include-blocked`, once to rank issues
and again to build the `DependencyGraph`; without it, the
`skip_blocked=True` call itself does two internal passes (ENH-2780) and the
no-ready-issues fallback path adds another — up to 3-4 full parses.

## Location

- **File**: `scripts/little_loops/cli/issues/next_issues.py`
- **Line(s)**: 13-89 (parses at 44, 56, 74, 77, at scan commit: fb567390)
- **Anchor**: `in function cmd_next_issues()`
- **Code**:
```python
all_issues = [i for i in find_issues(config) if not i.issue_id.startswith("EPIC-")]  # parse 1
...
graph = DependencyGraph.from_issues(find_issues(config), all_known_ids=all_known_ids)  # parse 2
...
issues = [i for i in find_issues(config, skip_blocked=True) ...]  # parse 3 (x2 internally)
if not issues:
    all_active = [i for i in find_issues(config) ...]  # parse 4
```
- Same pattern in `scripts/little_loops/cli/issues/next_issue.py`,
  `cmd_next_issue()`, lines 49, 65, 82, 91.

> ⚠ As of ENH-2780 (done), `skip_blocked=True` (parse 3 above) is a single
> internal pass, not "x2 internally" — see Codebase Research Findings above
> for current line numbers and the narrowed remaining fix surface (the
> `--include-blocked` branch's parse-1/parse-2 duplicate only).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/next_issues.py:44,56` — `--include-blocked`
  branch: reuse the line-44 parse for the graph instead of re-parsing at
  line 56.
- `scripts/little_loops/cli/issues/next_issue.py:49,65` — same duplicate in
  the `--include-blocked` branch.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py:61-62,888-890` — imports and
  registers `cmd_next_issue`/`cmd_next_issues` as the `next-issue`/`next-issues`
  argparse subcommands (aliases `nx`/`nxs`); no change needed, just the wiring
  point that dispatches into the two files being fixed. [Agent 1 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:46` — shells out to
  `ll-issues next-issue` (`resolve_issue` state); latency win is transparent,
  no change needed. [Agent 1 finding]
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:141` — shells out
  to `ll-issues next-issues` (`resolve_set` state); no change needed.
  [Agent 1 finding]
- `scripts/little_loops/loops/lib/cli.yaml:55` — `ll_issues_next_issue`
  reusable FSM fragment shells out to `ll-issues next-issue`; no change
  needed. [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:1273-1308,1426-1431` — documents `next-issue`/
  `next-issues` `--include-blocked`/`--skip` behavior and JSON output shape
  (`blocked`, `blocked_by`, `pending_prerequisites`); only needs updating if
  the `--skip`/graph-population risk below is left unaddressed and changes
  observable behavior. [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md:937,962,3333` — documents overriding
  `resolve_set`/`ll_issues_next_issue` to `--include-blocked` to preserve
  legacy dependency-resolution behavior; depends on `blocked_by`/
  `pending_prerequisites` correctness from the code path being changed.
  [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_next_issue.py` — covers `cmd_next_issue`'s
  `--include-blocked` branch (`TestNextIssueBlockedFilter` etc.); no existing
  test asserts `find_issues` call count, so nothing currently breaks from the
  refactor itself, but **no existing test combines `--skip` with
  `--include-blocked` where the skipped issue is itself a blocker of another
  candidate** — the exact scenario the caveat below describes. Add a
  regression test for that combination. [Agent 2 + Agent 3 findings]
- `scripts/tests/test_next_issues.py` — same shape for `cmd_next_issues`
  (`TestNextIssuesBlockedFilter` etc.); add a `find_issues`-call-count
  regression test. [Agent 3 finding]
- Call-count spy pattern to follow: `test_issue_parser.py`'s
  `test_find_issues_skip_blocked_single_parse_pass` (ENH-2780's sibling test)
  patches `IssueParser.parse_file` via `unittest.mock.patch.object(...,
  autospec=True, side_effect=...)`. For this issue, since `find_issues` is
  imported **locally inside** `cmd_next_issue`/`cmd_next_issues` (not at
  module scope), the spy must patch the source —
  `patch("little_loops.issue_parser.find_issues", ...)` — patching
  `next_issue_mod.find_issues`/`next_issues_mod.find_issues` will NOT
  intercept it. [Agent 3 finding]

## Current Behavior

Each command run re-walks and re-parses `.issues/` up to 4 times.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

`blocked_by: [ENH-2780]` is now `done` (completed 2026-07-25T06:58:31Z), and
its fix changes the parse count claimed above. `find_issues(config,
skip_blocked=True)` (`scripts/little_loops/issue_parser.py:1275-1313`) is now
a **single** unfiltered-superset parse pass internally (it no longer calls
itself recursively) — the "x2 internally" note in the Location section is
stale. Re-verified against current line numbers in both call sites:

- `next_issues.py` (`cmd_next_issues`) — non-`--include-blocked` path
  (lines 73-83): 1 parse (`skip_blocked=True`), +1 conditional parse only on
  the empty-fallback branch (line 77) — not a per-call duplicate.
  `--include-blocked` path (lines 44-56): **2 unconditional full parses per
  call** — `find_issues(config)` at line 44 to build `all_issues`, then
  `find_issues(config)` again at line 56 solely to build the
  `DependencyGraph`. This is the one remaining unconditional duplicate.
- `next_issue.py` (`cmd_next_issue`) — same shape: non-`--include-blocked`
  path (lines 80-92) is 1 parse + conditional fallback parse (line 91,
  empty-branch only); `--include-blocked` path (lines 49, 65) has the same
  unconditional 2-parse duplicate as `next_issues.py`.

So the remaining fix surface is narrower than originally scoped: only the
`--include-blocked` branch in both files does a genuine unconditional
double-parse. The non-`--include-blocked` branches were already fixed by
ENH-2780 (single internal pass) and their fallback parse is conditional
(only fires when zero ready issues exist), not part of the steady-state cost.

`DependencyGraph.from_issues()` (`scripts/little_loops/dependency_graph.py:56-61`)
takes a plain `list[IssueInfo]` — it has no coupling to how that list was
produced, so the already-parsed `all_issues`-equivalent superset (parsed at
line 44/49, before EPIC filtering) can be passed directly instead of
re-parsing.

## Expected Behavior

One parsed `IssueInfo` list is reused: rank from it, build
`DependencyGraph.from_issues(...)` from it, and derive the ready subset by
filtering it against `graph.get_ready_issues()`.

## Proposed Solution

In the `--include-blocked` branch of both `next_issues.py:cmd_next_issues`
and `next_issue.py:cmd_next_issue`, parse once via `find_issues(config, ...)`
into a `raw_issues` list, derive `all_issues`/`ranked` by filtering out
`EPIC-` entries from `raw_issues` in memory, and pass `raw_issues` (the
unfiltered superset, so EPICs and out-of-slice blockers are still graph
nodes) directly into `DependencyGraph.from_issues(...)` instead of calling
`find_issues(config)` a second time. The non-`--include-blocked` branches
already parse once (post-ENH-2780) and only need their existing conditional
fallback parse left as-is, since it's error-path-only, not steady-state.

> ⚠ **Wiring-pass caveat (`/ll:wire-issue`, Agent 2 finding) — the two files
> are NOT symmetric refactors.** `next_issues.py`'s two calls are both bare
> `find_issues(config)` (no `skip_ids`), so collapsing to a single shared
> `raw_issues` is contract-preserving as described above. `next_issue.py`'s
> two calls are asymmetric: the first (line ~49) is
> `find_issues(config, skip_ids=skip_ids or None)`, but the second (line ~65)
> is deliberately unfiltered `find_issues(config)` — per the existing inline
> comment, "Build the dep graph from every active issue so blocking edges
> outside the requested slice are still correctly recognized." If the fix
> naively shares the `skip_ids`-filtered list as `raw_issues` for
> `next_issue.py`, any `--skip`ped issue that is itself a blocker of another
> candidate would silently vanish from the graph's node set, and
> `blocked`/`blocked_by`/`pending_prerequisites` would incorrectly report
> false/empty for issues genuinely still blocked by it — a behavior
> regression, not just a performance fix. For `next_issue.py`, parse once via
> a single **unfiltered** `find_issues(config)` call, then derive the
> `skip_ids`-filtered ranking candidates from it in memory (instead of
> passing `skip_ids` to the parse itself), and pass the unfiltered list to
> `DependencyGraph.from_issues(...)`.

## Scope Boundaries

Out of scope: the non-`--include-blocked` branches' conditional fallback
parse (error-path-only, not steady-state) and any change to
`find_issues`/`skip_blocked` internals themselves (already fixed by
ENH-2780). This issue only collapses the `--include-blocked` branch's
unconditional double-parse in `next_issues.py` and `next_issue.py`.

## Impact

- **Effort**: Medium
- Cuts `next-issue(s)` latency by 2-4x on large backlogs; these commands run
  on every autodev/ll-auto dequeue cycle.

## Resolution

Collapsed the `--include-blocked` branch's unconditional double-parse in both
`next_issues.py:cmd_next_issues` and `next_issue.py:cmd_next_issue` to a single
`find_issues(config)` call, reused for both the ranking candidates and
`DependencyGraph.from_issues(...)`.

`next_issue.py` required the asymmetric treatment called out by the wiring
caveat: the single parse is unfiltered (no `skip_ids` passed to
`find_issues`), and the `--skip`-filtered ranking candidates are derived from
it in memory, so a skipped issue that blocks another candidate still appears
as a graph node and correctly reports `blocked`/`blocked_by`.

Added regression tests: a `find_issues` call-count spy for both commands'
`--include-blocked` path, and a `--skip` + `--include-blocked` blocker
scenario for `next_issue.py` verifying the skipped blocker still surfaces in
`blocked_by`.

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:manage-issue` - 2026-07-25T07:13:51 - `6e61fb39-0658-49e6-a994-239355cb929b.jsonl`
- `/ll:ready-issue` - 2026-07-25T07:08:57 - `0fedf05c-8168-419a-beb1-207e2a96cfce.jsonl`
- `/ll:confidence-check` - 2026-07-25T00:00:00Z - `cd1b9bb8-0da0-4325-a7ce-aa57b97ea3a2.jsonl`
- `/ll:wire-issue` - 2026-07-25T07:05:54 - `98b80699-ec02-4fc3-b1a3-32ecaa413617.jsonl`
- `/ll:refine-issue` - 2026-07-25T07:00:56 - `52c9c6ca-6b23-4557-b2a5-15db6aaaa4c5.jsonl`
- `/ll:scan-codebase` - 2026-07-24T22:41:56 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
