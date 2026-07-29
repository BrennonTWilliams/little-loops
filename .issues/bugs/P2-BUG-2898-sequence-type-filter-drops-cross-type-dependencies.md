---
id: BUG-2898
type: bug
priority: P2
status: cancelled
captured_at: '2026-07-28T22:29:06Z'
discovered_date: 2026-07-28
discovered_by: capture-issue
relates_to:
- BUG-2897
- BUG-2899
closed_reason: superseded
---

# BUG-2898: `ll-issues sequence --type` drops cross-type dependencies instead of respecting them

## Summary

`cmd_sequence()` applies the `--type` filter at *graph construction* time rather
than at *display* time. It passes `type_prefixes={args.type}` to `find_issues()`
and builds the `DependencyGraph` from that already-filtered list, so any
prerequisite outside the requested type never becomes a node — its edge is
dropped in `from_issues()` and the dependent is reported as unblocked.

The result is that `--type` doesn't narrow the view of a correct sequence; it
computes a *different, wrong* sequence. Silently, because `all_known_ids`
suppresses the dropped-edge warning (the out-of-type issue does exist on disk).

## Current Behavior

The same issue's blocker appears or vanishes depending on whether `--type` is
passed. Reproduced against a scratch project:

```
BUG-001  status: open
BUG-002  status: open, blocked_by: [FEAT-010]
BUG-003  status: open
FEAT-010 status: open

$ ll-issues sequence
  [P0, no blockers] BUG-003: Gamma
  [P1, no blockers] BUG-001: Alpha
  [P2, no blockers] FEAT-010: Delta
  [P3, blocked by: FEAT-010] BUG-002: Beta      # correct

$ ll-issues sequence --type BUG
  [P0, no blockers] BUG-003: Gamma
  [P1, no blockers] BUG-001: Alpha
  [P3, no blockers] BUG-002: Beta               # <-- wrong: FEAT-010 blocker erased
```

The `--json` output has the same defect: `blocked_by` and `depends_on` come back
empty for `BUG-002` under `--type BUG`.

## Expected Behavior

`--type` filters *which issues are shown*, not *which dependencies exist*. The
ordering of the shown issues must match their relative order in the unfiltered
sequence, and the rationale must name out-of-type prerequisites honestly:

```
$ ll-issues sequence --type BUG
  [P0, no blockers] BUG-003: Gamma
  [P1, no blockers] BUG-001: Alpha
  [P3, blocked by: FEAT-010] BUG-002: Beta
```

Naming a filtered-out prerequisite is the point — "you asked for bugs only, and
this bug is waiting on a feature" is exactly the information a type-filtered
sequence needs to convey.

## Motivation

`--type` exists (FEAT-833) so a user can focus a sequencing pass on one class of
work — a natural thing to do when triaging bugs or planning a feature push. That
focus is precisely when a cross-type prerequisite matters most: it is the
dependency you would otherwise forget, because it isn't in front of you.

Today the flag actively conceals it and reports a confident `no blockers`. A
user who trusts the filtered output starts work on an issue whose groundwork
doesn't exist yet. The unfiltered command is correct, so the failure is
inconsistent rather than uniformly wrong — which makes it harder to notice and
easier to trust.

## Proposed Solution

Build the graph from all active issues; filter only the list that gets rendered.

```python
# Build the graph from the full active set — dependencies are global.
all_active = find_issues(config)
graph = DependencyGraph.from_issues(all_active, all_known_ids=all_known_ids)

try:
    ordered = graph.topological_sort()
except ValueError as exc:
    ...

# Apply the type filter to the *display* list, preserving topological order.
type_prefix = getattr(args, "type", None)
if type_prefix:
    ordered = [i for i in ordered if i.issue_id.split("-", 1)[0] == type_prefix]

shown = ordered[:limit]
```

Two consequences to handle deliberately:

1. **The `N of M` count.** `Suggested implementation sequence (N of M issues)`
   should report M as the count of *matching* issues, not the whole graph.
   Compute it after filtering.
2. **Empty-result message.** The current early return
   (`if not issues: print("No active issues found.")`) fires before graph
   construction. With this change, "no active issues at all" and "no issues of
   this type" become distinct cases and should read differently.

This restructuring — build wide, display narrow — is the same shape BUG-2897
needs for the deferred-blocker fix. If both are implemented, do the split once
and let both fixes ride on it; implementing them independently risks two
conflicting rewrites of the same function.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/sequence.py` — `cmd_sequence()`: move the
  type filter from `find_issues()` to post-sort display filtering; fix the
  count line and the empty-result branch

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py` — subcommand registration and
  `--type` argument definition (confirm no validation assumptions change)
- TBD — grep for consumers of `ll-issues sequence --json` (skills, loop YAML,
  `commands/*.md`) that may depend on the current `type_filter` echo field

### Similar Patterns
- `find_issues(skip_blocked=True)` in `issue_parser.py` already builds an
  unfiltered superset for the graph and derives the caller's filtered result
  from it in memory — the established precedent for this exact split
- Check whether `ll-issues list --type` / `impact-effort` have the same
  filter-before-graph shape

### Tests
- `scripts/tests/test_issues_cli.py` — add a cross-type dependency case
  asserting `--type BUG` still reports the FEAT blocker; assert relative order
  of shown issues matches the unfiltered run
- `--json` variant of the same assertion

### Documentation
- `docs/reference/API.md` — `ll-issues sequence` entry, if it documents `--type`
- Any skill/command markdown that describes `--type` semantics

### Configuration
- N/A

## Implementation Steps

1. Add a failing test: cross-type blocker must survive `--type` filtering.
2. Coordinate with BUG-2897 — both need graph-wide vs. display-narrow separation;
   land the restructuring once.
3. Move the type filter out of the `find_issues()` call and apply it to
   `ordered` after `topological_sort()`.
4. Fix the `N of M` count to reflect the filtered total.
5. Split the empty-result message into "no active issues" vs. "no issues of type X".
6. Mirror the fix in the `--json` branch.
7. Run `python -m pytest scripts/tests/`.

## Impact

- **Severity**: Correctness — silently wrong dependency reporting under a flag
  whose purpose is narrowing, not altering, the answer
- **Scope**: `ll-issues sequence --type` only (text and `--json`); the unfiltered
  path is correct
- **Risk of fix**: Low-moderate. Filtered runs get slower (full parse instead of
  one type dir) — acceptable; `find_issues` already walks all categories by
  default. Output changes for any filtered issue with a cross-type dependency,
  which is the intended correction.
- **Interaction**: Overlaps structurally with BUG-2897; sequence them together

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` § Issue File Format | Type prefixes (`BUG`/`FEAT`/`ENH`/`EPIC`) that `--type` matches against |
| `docs/reference/API.md` | `ll-issues` CLI surface and `dependency_graph` module reference |
| `docs/ARCHITECTURE.md` | Where dependency ordering feeds orchestration |

## Steps to Reproduce

1. Create a scratch project with `.issues/bugs/` and `.issues/features/`.
2. Write `FEAT-010` (`status: open`) and `BUG-002`
   (`status: open`, `blocked_by: [FEAT-010]`), plus any other open bugs.
3. Run `ll-issues sequence` — `BUG-002` correctly shows `blocked by: FEAT-010`.
4. Run `ll-issues sequence --type BUG` — `BUG-002` now shows `no blockers`.
5. Note no warning is emitted in either run.

## Root Cause

`scripts/little_loops/cli/issues/sequence.py`, `cmd_sequence()`:

```python
type_prefixes = {args.type} if getattr(args, "type", None) else None
issues = find_issues(config, type_prefixes=type_prefixes)
...
graph = DependencyGraph.from_issues(issues, all_known_ids=all_known_ids)
```

The filtered list is the graph's entire node set. In
`DependencyGraph.from_issues()`, `blocker_id not in all_issue_ids` then drops
every cross-type edge, and the `all_known_ids` guard (added by BUG-2802 to
silence `done`-issue references) suppresses the warning because the out-of-type
blocker does exist on disk.

## Location

- `scripts/little_loops/cli/issues/sequence.py` — `cmd_sequence()`
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph.from_issues()`
  (edge-dropping and warning-suppression mechanism)

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-28T23:17:14 - `139954b3-6523-4f66-ba64-f2917d895a02.jsonl`
- `/ll:capture-issue` - 2026-07-28T22:29:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/73139eea-b48b-4fa0-a6fa-0b390a284d9f.jsonl`

---

## Status

**Status**: open

---

## Resolution

- **Completed**: 2026-07-28
- **Reason**: Superseded by BUG-2897 via conflict resolution audit
- **Proposed change**: Merged into BUG-2897. Both issues restructured the same
  `cmd_sequence()` graph-construction into a "build wide / display narrow"
  split, but on different widening axes, and this issue's proposed
  `all_active = find_issues(config)` snippet re-introduced the exact
  `status_filter=None` defect BUG-2897 exists to fix. The `--type`-at-display-time
  fix, the empty-result message split, and this issue's acceptance criteria are
  absorbed into BUG-2897's `## Scope Addition` section as the second widening
  axis of a single change.
