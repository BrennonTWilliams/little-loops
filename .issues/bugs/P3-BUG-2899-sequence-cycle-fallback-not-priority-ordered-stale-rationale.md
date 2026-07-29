---
id: BUG-2899
type: bug
priority: P3
status: open
captured_at: '2026-07-28T22:29:06Z'
discovered_date: 2026-07-28
discovered_by: capture-issue
relates_to:
- BUG-2897
- BUG-2898
blocked_by:
- BUG-2897
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
- TBD — grep for `sequence --json` consumers before changing the JSON shape;
  a per-item field is additive and safe, a top-level restructure is not
- `scripts/little_loops/dependency_graph.py` — `detect_cycles()` is the data
  source; no change expected, verify it returns all cycle members not just the
  first cycle

### Similar Patterns
- `get_execution_waves()` raises the same `ValueError` with the same message
  shape — check whether sprint/parallel wave construction has an equivalent
  silently-degrading fallback worth fixing consistently
- `topological_sort()`'s own `(priority_int, issue_id)` tiebreaker is the
  canonical sort key to reuse

### Tests
- `scripts/tests/test_issues_cli.py` — cycle fixture asserting: warning emitted,
  output globally priority-sorted, cycle members marked, non-members unmarked
- `--json` assertion for the cycle indicator
- Fixture must span multiple category directories to actually catch the
  directory-grouping bug (a bugs-only fixture would pass under the current code)

### Documentation
- `docs/reference/API.md` — `ll-issues sequence` JSON schema, if documented
- `docs/development/TROUBLESHOOTING.md` — a "dependency cycle detected" entry
  pointing at `ll-deps` for resolution would be a natural companion

### Configuration
- N/A

## Implementation Steps

1. Write the multi-directory cycle fixture; assert priority ordering — confirm it
   fails against current code.
2. Replace `ordered = issues` with the explicit priority sort over the *display*
   list (`display_issues`), not the raw loaded list — see the Proposed Solution
   note. Requires BUG-2897 to have landed the build-wide/display-narrow split.
2a. Move the status/type display filter below the `try`/`except` so the
   cycle-fallback branch is filtered identically to the success branch.
3. Capture `cycle_ids` from `graph.detect_cycles()` in the except branch.
4. Thread `cycle_ids` into rationale construction; suppress stale
   `blocked by:` / `after:` parts for cycle members.
5. Add the `--json` cycle indicator (per-item flag preferred).
6. Add the second warning line clarifying the ordering is priority-only.
7. Run `python -m pytest scripts/tests/`.

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

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-28T23:18:36 - `139954b3-6523-4f66-ba64-f2917d895a02.jsonl`
- `/ll:capture-issue` - 2026-07-28T22:29:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/73139eea-b48b-4fa0-a6fa-0b390a284d9f.jsonl`

---

## Status

**Status**: open
