---
id: BUG-2899
type: bug
priority: P3
status: done
captured_at: '2026-07-28T22:29:06Z'
completed_at: '2026-07-29T02:22:53Z'
discovered_date: 2026-07-28
discovered_by: capture-issue
relates_to:
- BUG-2897
- BUG-2898
blocked_by:
- BUG-2897
confidence_score: 100
outcome_confidence: 88
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 23
---

# BUG-2899: `ll-issues sequence` cycle fallback isn't priority-ordered and prints stale rationale

## Summary

When `topological_sort()` raises on a dependency cycle, `cmd_sequence()` catches
it and falls back with:

```python
ordered = issues  # fall back to priority order
```

The comment is wrong. `find_issues()` walks category directories in sequence
(`bugs/`, then `features/`, then `enhancements/`, then `epics/`), so `issues` is
grouped by type with priority ordering only *within* each group — not globally
priority-ordered.

Separately, the per-issue rationale continues to print `blocked by:` / `after:`
annotations derived from the cyclic graph. Those annotations describe a
dependency structure that is, by definition, unsatisfiable — yet they render
identically to the valid case, so the fallback output looks like an authoritative
sequence when the order is effectively arbitrary.

## Current Behavior

Reproduced against a scratch project with a `depends_on` cycle
(`BUG-001 → BUG-002 → BUG-001`):

```
$ ll-issues sequence
Warning: dependency cycle detected — Dependency graph contains cycles: BUG-001 -> BUG-002 -> BUG-001
Suggested implementation sequence (4 of 4 issues):

  [P0, no blockers] BUG-003: Gamma
  [P1, after: BUG-002] BUG-001: Alpha     # <-- P1 before P2, but only by directory accident
  [P2, no blockers] FEAT-010: Delta
  [P3, ...] BUG-002: Beta
```

Two problems visible here:

1. The order is directory-walk order, not priority order. It happens to look
   plausible in a small fixture; with a realistic backlog, all `bugs/` sort
   before all `features/` regardless of P-level.
2. `BUG-001` still advertises `after: BUG-002` while `BUG-002` is itself waiting
   on `BUG-001`. The output presents a contradiction without flagging it.

The warning is printed once at the top and is easy to miss above a long list —
particularly since the list below it looks entirely normal.

## Expected Behavior

1. The fallback genuinely sorts by priority, matching its stated intent and the
   tiebreaker used inside `topological_sort()`:

   ```python
   ordered = sorted(issues, key=lambda i: (i.priority_int, i.issue_id))
   ```

2. Cycle-participating issues are visually marked, so a reader can tell which
   entries' ordering is untrustworthy. `detect_cycles()` already returns the
   participating IDs — the exception message embeds them, and the method can be
   called directly for structured access.

   ```
   Warning: dependency cycle detected — BUG-001 -> BUG-002 -> BUG-001
   Ordering below is priority-only; cycle members marked ⚠ and cannot be sequenced.

     [P0, no blockers] BUG-003: Gamma
     [P1, ⚠ in cycle: BUG-001 -> BUG-002 -> BUG-001] BUG-001: Alpha
     [P2, no blockers] FEAT-010: Delta
     [P3, ⚠ in cycle: BUG-001 -> BUG-002 -> BUG-001] BUG-002: Beta
   ```

3. `--json` output surfaces the degraded state — currently the JSON branch shows
   no indication a cycle occurred at all, so a programmatic consumer cannot tell
   a fallback ordering from a valid topological one. Add a `cycle` field (or a
   per-issue `in_cycle` boolean).

## Motivation

The failure mode is a confidently-presented wrong answer. A correct ordering and
a fallback ordering are visually indistinguishable apart from one warning line
that scrolls away, and the stale `after:`/`blocked by:` annotations actively
reinforce the impression that dependency ordering was applied.

The `--json` gap is the sharper half: a consumer parsing `ll-issues sequence
--json` has no field to check, so a cycle degrades ordering silently into
whatever automation reads it. That is a small fix with a real correctness payoff.

Low priority because a cycle is itself an abnormal state that a user must fix
regardless — this improves the diagnostic, it doesn't unblock ordinary work.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**BUG-2897 has landed on `main` (commit `63c4fff0`) — the `blocked_by:
BUG-2897` gate on this issue is now satisfied**, and the wide/narrow split
described below is *already in place*, not a future prerequisite. Current
`scripts/little_loops/cli/issues/sequence.py:47-105` (`cmd_sequence()`):

- **Build wide** (line 67): `graph_issues = find_issues_for_graph(config)` —
  the non-terminal superset (includes `deferred`, no `--type` filter),
  exactly the substrate this issue's Proposed Solution calls "the post-split
  narrow list." The variable name in the current code is `graph_issues`, not
  `display_issues` as this section originally assumed — use `graph_issues`
  when writing the fix.
- **Cycle fallback** (lines 87-89, unchanged from Root Cause section below):
  ```python
  except ValueError as exc:
      print(f"Warning: dependency cycle detected — {exc}")
      ordered = graph_issues  # fall back to priority order
  ```
  Still assigns the *unsorted* wide list to `ordered` — the bug is confirmed
  present in current code.
- **Narrow: display filtering** (lines 91-94) already sits *below* the
  `try`/`except`, applying `_OPEN_STATUSES` and `--type` filtering uniformly
  to both the success and fallback paths — so Implementation Step 2a's
  "verify this landed" check passes; no separate action needed there, only
  confirmation.
- **`detect_cycles()`** (`scripts/little_loops/dependency_graph.py:380-432`)
  returns `list[list[str]]` — one entry per back-edge found across a full DFS
  over the *whole* graph (not just the first cycle encountered), so
  `cycle_ids = {i for cycle in graph.detect_cycles() for i in cycle}` in the
  Proposed Solution snippet below correctly captures all cycle members even
  when multiple independent cycles exist.
- **Sort key confirmed**: `topological_sort()` uses
  `(i.priority_int, i.issue_id)` at both `dependency_graph.py:351` and `:368`
  — matches this section's proposed `sorted(...)` call exactly.
- **Related, not superseding**: `scripts/little_loops/dependency_mapper/formatting.py:252-271`
  (`format_epic_tree()`) has a *third*, distinct cycle-handling shape —
  `topological_sort()`'s `ValueError` is uncaught there, so an EPIC-child
  cycle crashes rather than falling back or degrading gracefully. Not in
  scope for this fix, but worth a one-line note if a follow-up issue is
  filed per the "Similar Patterns" section below.
- **Sprint code does NOT have the same silent-fallback bug.** `scripts/little_loops/cli/sprint/manage.py:99-109`
  and `scripts/little_loops/cli/sprint/run.py:492-501` both pre-check
  `has_cycles()` and hard-fail (`return 1` / log + exit), and
  `scripts/little_loops/cli/sprint/show.py:189-200` threads a `has_cycles`
  boolean through to an explicit `"BLOCKED -- dependency cycles detected"`
  status line and a top-level `"has_cycles"` JSON key — i.e. sprint code
  already does what this issue's Expected Behavior #3 asks `sequence` to do.
  This resolves the "Similar Patterns" section's open question below:
  sprint/wave construction does **not** need an equivalent fix; `sequence.py`
  is the outlier.
- **`--json` per-item flag precedent**: `deferred_blockers` (added for
  BUG-2897, `sequence.py:126-130`) is the idiom to follow for the new
  `in_cycle` field — an always-present, unconditionally-computed per-item
  key (unlike the conditional `type_filter` key added only when `--type` is
  passed). Verified by `test_sequence_json_deferred_blockers_field`
  (`scripts/tests/test_issues_cli.py:1715-1746`) as the pattern to mirror.

In `cmd_sequence()`'s `except ValueError` branch:

```python
except ValueError as exc:
    print(f"Warning: dependency cycle detected — {exc}")
    print("Ordering below is priority-only; cycle members cannot be sequenced.\n")
    cycle_ids = {i for cycle in graph.detect_cycles() for i in cycle}
    ordered = sorted(display_issues, key=lambda i: (i.priority_int, i.issue_id))
```

**Sort the display list, not `issues`** (revised by
`/ll:audit-issue-conflicts`, conflict C2/C3). This issue is `blocked_by:
BUG-2897`, which restructures `cmd_sequence()` so the loaded `issues` list
becomes a *non-terminal superset* — it deliberately includes `deferred` issues,
and (absorbing BUG-2898) is no longer `--type`-filtered either. Sorting raw
`issues` here would therefore render deferred and out-of-type issues in the
cycle-path output, violating BUG-2897's constraint that "the display filter must
stay narrow."

Use the post-split narrow list (`display_issues`) as the sort source, and place
the shared status/type display filter **below** the `try`/`except` so it covers
*both* the success and the cycle-fallback branches. Placing it only in the
success path is the C3 defect: `--type` would silently list every type whenever
a cycle is present.

Then thread `cycle_ids` into the rationale builder: when
`issue.issue_id in cycle_ids`, emit the cycle marker *instead of* the
`blocked by:` / `after:` parts rather than in addition to them — the structured
edges are what form the cycle, so repeating them adds noise.

For `--json`, add a top-level shape change or a per-item flag. Prefer the
per-item flag (`"in_cycle": true`) to avoid breaking the existing top-level array
contract that `FEAT-701` established; note the array-vs-object decision
explicitly during implementation since consumers may index it directly.

Note `detect_cycles()` is called twice on this path — once inside
`topological_sort()` to build the exception message, once again here. Harmless
at current backlog sizes; worth a comment rather than a refactor.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/sequence.py` — `cmd_sequence()`: fallback
  sort, cycle-member marking, rationale suppression, `--json` flag

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py` — imports `cmd_sequence` (line
  68) and dispatches to it from `main_issues()` (line 871); the only caller.
  **Resolves the "TBD — grep for `sequence --json` consumers" note above: no
  programmatic consumer of `sequence --json` exists anywhere in this repo**
  (confirmed by grep across `scripts/little_loops/` and `commands/`/`skills/`
  markdown) — the `in_cycle` field is safe to add with zero downstream
  breakage. [Agent 1 finding]
- `scripts/little_loops/dependency_graph.py` — `detect_cycles()` is the data
  source; no change expected, **confirmed** (research) it returns all cycle
  members across the whole graph, not just the first cycle — DFS with
  WHITE/GRAY/BLACK coloring restarts from every unvisited node
  (`dependency_graph.py:428-430`) and appends one entry per back-edge found

### Similar Patterns
- `get_execution_waves()` raises the same `ValueError` with the same message
  shape — **resolved by research**: sprint/parallel wave construction does
  *not* share this bug. `cli/sprint/manage.py:99-109` and
  `cli/sprint/run.py:492-501` both pre-check `has_cycles()` and hard-fail
  rather than silently substituting an order; `cli/sprint/show.py:189-200`
  threads `has_cycles` through to an explicit `"BLOCKED -- dependency cycles
  detected"` status line and a `"has_cycles"` JSON key. No consistency fix
  needed there — `sequence.py` is the only silently-degrading fallback.
  A third, distinct shape exists at `dependency_mapper/formatting.py:252-271`
  (`format_epic_tree()`): `topological_sort()`'s `ValueError` is uncaught,
  so an EPIC-child cycle crashes outright — out of scope here, flag as a
  possible follow-up rather than folding into this fix.
- `topological_sort()`'s own `(priority_int, issue_id)` tiebreaker is the
  canonical sort key to reuse — confirmed at `dependency_graph.py:351,368`

### Tests
- `scripts/tests/test_issues_cli.py` — cycle fixture asserting: warning emitted,
  output globally priority-sorted, cycle members marked, non-members unmarked
- `--json` assertion for the cycle indicator — model on
  `test_sequence_json_deferred_blockers_field` (`test_issues_cli.py:1715-1746`),
  which asserts an always-present per-item key the same way `in_cycle` should
  be asserted
- Fixture must span multiple category directories to actually catch the
  directory-grouping bug (a bugs-only fixture would pass under the current
  code). No existing fixture combines multi-directory issues with a cycle —
  closest precedents to compose from: `issues_dir_with_cycle`
  (`test_issues_cli.py:5412-5428`, single-directory `blocked_by` cycle) and
  `test_sequence_type_filter_still_reports_cross_type_blocker`
  (`test_issues_cli.py:1748-1783`, cross-directory `bugs/`+`features/` but no
  cycle) — combine both shapes for the new fixture. For a unit-level
  (non-CLI) cycle fixture against `DependencyGraph` directly, the `make_issue()`
  helper (`test_dependency_graph.py:18-39`) and `test_simple_cycle()`
  (`test_dependency_graph.py:518-527`) show the minimal pattern.

_Wiring pass added by `/ll:wire-issue`:_
- No existing test currently exercises `cmd_sequence`'s cycle-fallback branch
  at all — `issues_dir_with_cycle` (`test_issues_cli.py:5413-5428`) is only
  consumed by cluster/tree tests (`test_tree_cycle_terminates`,
  `test_no_color_suppresses_ansi_and_cycle_icon`,
  `test_overview_counts_cycles`), a different command; the new cycle test is
  fully additive, not a modification of a brittle existing assertion. No test
  anywhere asserts the literal strings `"Warning: dependency cycle detected"`
  or `"fall back to priority order"`, so the warning text can be freely
  reworded per Expected Behavior #2. [Agent 3 finding]
- `test_sequence_json_output` (`test_issues_cli.py:1480-1512`) asserts
  presence of specific JSON keys (`id`, `priority`, `title`, `path`,
  `blocked_by`, `blocks`, `depends_on`) but not an exhaustive key set —
  adding `in_cycle` will not break it. All other non-cycle `TestIssuesCLISequence`
  tests (`test_sequence_basic`, `test_sequence_limit`, `test_sequence_type_filter_*`,
  etc., `test_issues_cli.py:1407-1676`) exercise only `topological_sort()`'s
  success path and are unaffected by changes to the `except ValueError`
  branch. [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — `ll-issues sequence` JSON schema, if documented
  (confirmed by research: only a one-line subcommand-table entry exists here,
  no field-level schema to update)
- `docs/development/TROUBLESHOOTING.md` — a "dependency cycle detected" entry
  pointing at `ll-deps` for resolution would be a natural companion

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — the `ll-issues sequence` / `ll-issues seq` section
  documents the `--json` flag and prose behavior (including the
  `blocked_by`/`depends_on` ordering note added for BUG-2848) and is the only
  place the JSON output shape is documented in prose; needs a note for the new
  `in_cycle` field and the priority-only-fallback warning text, following the
  same pattern as `deferred_blockers`, which was documented here (not in a
  schema file) when added for BUG-2897. [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. Write the multi-directory cycle fixture; assert priority ordering — confirm it
   fails against current code.
2. Replace `ordered = graph_issues` with the explicit priority sort:
   `ordered = sorted(graph_issues, key=lambda i: (i.priority_int, i.issue_id))`
   at `scripts/little_loops/cli/issues/sequence.py:89`. (Research confirms the
   current variable name is `graph_issues`, not `display_issues` as an earlier
   draft of this section assumed.)
2a. **BUG-2897 has landed** (commit `63c4fff0`, status `done`) — confirmed by
   research that the shared status/type display filter already sits below the
   `try`/`except` at `sequence.py:91-94`, covering both the success and
   cycle-fallback branches identically. No action needed here beyond this
   confirmation; the `blocked_by: BUG-2897` gate on this issue is satisfied.
3. Capture `cycle_ids` from `graph.detect_cycles()` in the except branch.
4. Thread `cycle_ids` into rationale construction; suppress stale
   `blocked by:` / `after:` parts for cycle members.
5. Add the `--json` cycle indicator (per-item flag preferred).
6. Add the second warning line clarifying the ordering is priority-only.
7. Update `docs/reference/CLI.md`'s `ll-issues sequence` section to document
   the `in_cycle` field and the priority-only-fallback warning text (added by
   `/ll:wire-issue`).
8. Run `python -m pytest scripts/tests/`.

## Impact

- **Severity**: Low-moderate — misleading output in an already-abnormal state
- **Scope**: `ll-issues sequence` cycle path only; the normal path is untouched
- **Risk of fix**: Very low. Only reachable when a cycle exists, which is already
  a broken state a user must repair.
- **User-visible**: Yes, on the cycle path — different ordering and new markers.
  `--json` gains a field (additive).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md` | `dependency_graph.detect_cycles` / `topological_sort` contracts and `sequence --json` schema |
| `docs/development/TROUBLESHOOTING.md` | Natural home for a cycle-resolution entry |
| `.claude/CLAUDE.md` § Issue File Format | `blocked_by` / `depends_on` semantics that form cycles |

## Steps to Reproduce

1. Create a scratch project with issues spanning `bugs/` and `features/`.
2. Introduce a cycle, e.g. `BUG-001 depends_on: [BUG-002]` and
   `BUG-002 depends_on: [BUG-001]`.
3. Run `ll-issues sequence`.
4. Observe the warning, then note the list below is grouped by category
   directory rather than sorted by priority.
5. Note cycle members still print `after:` annotations naming each other, with
   nothing indicating those entries are unorderable.

## Root Cause

`scripts/little_loops/cli/issues/sequence.py`, `cmd_sequence()`:

```python
try:
    ordered = graph.topological_sort()
except ValueError as exc:
    print(f"Warning: dependency cycle detected — {exc}")
    ordered = issues  # fall back to priority order
```

`issues` comes from `find_issues()`, which accumulates results by iterating
`config.issue_categories` and appending each directory's contents — producing
category-grouped output, not a global priority sort. The comment asserts a
property the code never establishes.

The rationale-building loop further down is unconditional: it reads
`graph.blocked_by` and `graph.get_pending_prerequisites()` with no awareness that
the graph was rejected as non-DAG.

## Location

- `scripts/little_loops/cli/issues/sequence.py` — `cmd_sequence()`, the
  `except ValueError` branch and the subsequent rationale loop
- `scripts/little_loops/issue_parser.py` — `find_issues()` (category-walk
  ordering that the fallback incorrectly assumes is priority-sorted)

## Resolution

Fixed in `scripts/little_loops/cli/issues/sequence.py`'s `cmd_sequence()`:

- Cycle fallback now sorts `graph_issues` by `(priority_int, issue_id)` —
  the same tiebreaker `topological_sort()` uses — instead of assigning the
  unsorted directory-walk list.
- Cycle members (from `graph.detect_cycles()`) print `⚠ in cycle: A -> B -> A`
  in place of stale `blocked by:`/`after:` rationale.
- `--json` gains an always-present per-item `"in_cycle"` boolean; the
  human-readable warning lines are suppressed under `--json` so stdout stays
  a single valid JSON document.
- `docs/reference/CLI.md` updated with the new behavior.

## Session Log
- `/ll:manage-issue` - 2026-07-29T02:22:18Z - `ceb50580-97ce-49cb-9f44-dc343c2f82d3.jsonl`
- `/ll:ready-issue` - 2026-07-29T02:15:12 - `0de86690-7973-45c6-90e9-c985d844345b.jsonl`
- `/ll:confidence-check` - 2026-07-28T00:00:00Z - `06a2ec85-fd32-4624-9408-062df533141a.jsonl`
- `/ll:wire-issue` - 2026-07-29T02:12:29 - `99883733-72e3-4f7d-9736-7fb54e8c4b0f.jsonl`
- `/ll:refine-issue` - 2026-07-29T02:07:41 - `3d118b72-0b1a-46cf-afc1-009f920e0843.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-28T23:18:36 - `139954b3-6523-4f66-ba64-f2917d895a02.jsonl`
- `/ll:capture-issue` - 2026-07-28T22:29:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/73139eea-b48b-4fa0-a6fa-0b390a284d9f.jsonl`

---

## Status

**Status**: open
