---
id: BUG-2897
type: bug
priority: P2
status: open
captured_at: '2026-07-28T22:29:06Z'
discovered_date: 2026-07-28
discovered_by: capture-issue
relates_to:
- BUG-2898
- BUG-2899
supersedes:
- BUG-2898
blocks:
- BUG-2899
decision_needed: false
confidence_score: 98
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 22
---

# BUG-2897: A `deferred` blocker is silently treated as satisfied by the dependency graph

## Summary

`find_issues()`'s default status filter excludes `done`, `cancelled`, **and
`deferred`** (`issue_parser.py`, `_matches_status`). Every caller that builds a
`DependencyGraph` from a default `find_issues()` call therefore never sees a
`deferred` issue as a node — so a `blocked_by`/`depends_on` edge pointing at a
deferred issue is dropped in `DependencyGraph.from_issues()` and the dependent
is reported as unblocked.

The warning that would normally surface a dropped edge is also suppressed,
because `all_known_ids` (gathered from disk, all statuses) contains the deferred
blocker — the `all_known_ids is None or blocker_id not in all_known_ids` guard
in `from_issues()` correctly silences it as "exists on disk", which is true but
misleading here.

This matters disproportionately in this project: `autodev.yaml` and
`rn-implement.yaml` defer issues routinely and automatically
(`low_readiness`, `readiness_stagnated`, `gate_blocked`, `decision_unresolved`,
`blocked_by_unmet`, `oversized_atomic`). Deferred blockers are a normal steady
state, not an edge case.

## Current Behavior

A dependent of a `deferred` blocker is sequenced as if it had no prerequisite,
with no warning.

Reproduced against a scratch project:

```
.issues/bugs/P1-BUG-001-alpha.md   status: deferred
.issues/bugs/P3-BUG-002-beta.md    status: open, blocked_by: [BUG-001]
.issues/bugs/P0-BUG-003-gamma.md   status: open

$ ll-issues sequence
Suggested implementation sequence (2 of 2 issues):

  [P0, no blockers] BUG-003: Gamma
  [P3, no blockers] BUG-002: Beta      # <-- wrong: BUG-001 is deferred, not resolved
```

Flipping BUG-001 to `status: open` produces the correct
`[P3, blocked by: BUG-001]`.

## Expected Behavior

A `deferred` blocker is **not** treated as satisfied. `deferred` is a
non-terminal status — the work is postponed, not completed — so a dependent
should still be reported as blocked, distinguishably from a hard-open blocker.

Suggested rendering:

```
  [P3, blocked by: BUG-001 (deferred)] BUG-002: Beta
```

Only `done` and `cancelled` (the terminal statuses, per
`issue_progress._TERMINAL_STATUSES`) should resolve a dependency edge.

## Motivation

A sequencing tool whose entire purpose is dependency ordering silently reporting
`no blockers` for a genuinely blocked issue is a correctness failure at the
tool's core contract. Downstream, an operator (or `ll-auto`/`ll-sprint`) picks up
an issue whose prerequisite was explicitly postponed, does the work against
missing groundwork, and either wastes the cycle or lands something that must be
redone once the deferred blocker is revisited.

The autodev deferral machinery (ENH-2664/ENH-2666/BUG-2803) deliberately routes
not-ready issues to `deferred` rather than leaving them `open`, precisely so they
stop being re-evaluated every run. That design decision quietly widened this
bug's blast radius: the more the automation defers, the more dependency edges
silently vanish.

## Proposed Solution

The fix has a narrow option and a broad option; the broad one is likely correct
but needs a caller audit.

> **Selected:** Option A (narrow) — reuses the existing `skip_blocked` superset/filter precedent in `issue_parser.py`, low blast radius, high consistency.

### Option A (narrow) — fix at the graph-building call sites

Have `ll-issues sequence` (and peer graph consumers) load the full non-terminal
set explicitly rather than relying on the default filter:

```python
from little_loops.issue_progress import _ALL_STATUSES, _TERMINAL_STATUSES

non_terminal = _ALL_STATUSES - _TERMINAL_STATUSES  # includes deferred
graph_issues = find_issues(config, status_filter=non_terminal)
graph = DependencyGraph.from_issues(graph_issues, all_known_ids=all_known_ids)
# ... then filter the *display* list to the active subset
```

This is the same superset trick `find_issues(skip_blocked=True)` already uses
internally (`issue_parser.py`, the `if skip_blocked:` branch) — that code path
already recognized that graph correctness needs a wider parse than the caller's
own filter. Reuse that reasoning rather than reinventing it.

Note this pairs naturally with BUG-2898, which needs the same
"build graph from the superset, filter only the display list" restructuring.

### Option B (broad) — change the default filter semantics

Make `find_issues()`'s `status_filter=None` default exclude only terminal
statuses (`done`, `cancelled`), and audit every caller that relied on `deferred`
being hidden. Higher blast radius — `deferred` issues would start appearing in
`ll-issues list`, `ll-auto` dequeue, sprint composition, etc., which is almost
certainly *not* wanted for work-selection callers.

**Recommendation**: Option A. Keep `deferred` hidden from work-selection
surfaces; make it visible to graph-construction surfaces. Consider extracting a
small `find_issues_for_graph(config)` helper so the distinction is named once
rather than repeated at each call site.

### Decision Rationale

**Selected: Option A (narrow) — fix at the graph-building call sites.**

Codebase evidence from parallel `codebase-pattern-finder` agents confirms the
narrow fix directly reuses an already-working, already-tested in-repo pattern:
`find_issues(skip_blocked=True)` (`issue_parser.py:1468-1522`) already builds a
`non_terminal = _ALL_STATUSES - _TERMINAL_STATUSES` superset for graph
construction and separately filters the display list — the exact shape Option
A proposes. Each of the five affected call sites (`sequence.py`,
`issue_manager.py`, `link.py`, `next_issue.py`, `next_issues.py`) follows the
same `find_issues()` → `DependencyGraph.from_issues()` two-line shape, so the
fix is a small, copy-paste-consistent patch per site rather than five
different designs.

Option B (broadening the `find_issues()` default) was rejected: an agent
audit found 10+ bare-default production call sites (`next_issues.py`,
`next_issue.py`, `link.py`, `show.py`, `set_status.py`, `next_action.py`,
`format_check.py`, `sweep_stale_refs.py`, `priority_queue.py` feeding
`ll-parallel`, `issue_manager.py`) that would start surfacing `deferred`
issues in work-selection/dequeue paths where hiding them is intentional and
correct — inverting an established convention rather than reusing it, with
existing unit tests (e.g. `test_issue_parser.py:2255`) asserting the current
exclusion.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A (narrow) | 3 | 2 | 3 | 3 | **11/12** |
| B (broad) | 1 | 3 | 1 | 0 | 5/12 |

**Key evidence:**
- `issue_parser.py:1484-1522` — the `skip_blocked` superset/filter precedent Option A reuses verbatim
- 10+ bare `find_issues(config)` call sites across work-selection surfaces would need individual auditing under Option B
- `sprint.py`'s `_ACTIVE_STATUSES` filter is already independent of the default, unaffected either way

### Distinguishing deferred blockers in output

`DependencyGraph` currently has no notion of blocker status. Either:
- have `sequence.py` join against the already-loaded `issue_statuses` dict (it
  builds one for the prose-dep check) when formatting the rationale, or
- add an optional `blocker_status` lookup to the graph.

The former is less invasive and keeps the graph status-agnostic.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/sequence.py` — `cmd_sequence()`: widen the
  graph-building `find_issues()` call; annotate deferred blockers in rationale
- `scripts/little_loops/issue_parser.py` — `find_issues()`: possibly add a
  graph-oriented helper / document the filter's graph implications
- `scripts/little_loops/dependency_graph.py` — `from_issues()`: docstring
  currently says "Completed issues are treated as satisfied"; clarify that only
  terminal statuses should be, and that absent-from-graph is the mechanism

### Dependent Files (Callers/Importers)

**Call-site audit completed 2026-07-29.** All 12 `DependencyGraph.from_issues(`
call sites, with the provenance of the issue list each one passes:

| Call site | Line | Issue-list source | Affected? |
|---|---|---|---|
| `cli/issues/sequence.py` | 77 | `find_issues(config, type_prefixes=...)` @ `:62` — **default status filter** | **Yes — the confirmed defect** |
| `issue_parser.py` | 1520 | `all_active` (skip_blocked branch) | Verify — this is the existing non-terminal-superset precedent |
| `issue_manager.py` | 1237 | `all_issues` | Verify |
| `sprint.py` | 367 | `child_infos` | Verify |
| `dependency_mapper/analysis.py` | 481 | `issues` + explicit `completed` arg | Verify |
| `cli/deps.py` | 292 | — | Verify |
| `cli/issues/link.py` | 222 | `issues` (**no `all_known_ids`** — will emit dropped-edge warnings) | Verify |
| `cli/sprint/show.py` | 190 | `issue_infos` | Verify |
| `cli/sprint/run.py` | 490 | `issue_infos` | Verify |
| `cli/sprint/manage.py` | 99 | `issue_infos` | Verify |
| `cli/issues/next_issue.py` | 72 | `raw_issues` | Verify |
| `cli/issues/next_issues.py` | 57 | `raw_issues` | Verify |

Two concrete findings from the audit that shape the fix:

1. **`sequence.py:62` carries both defects on one line.** It passes
   `type_prefixes` *and* relies on the default status filter:
   ```python
   type_prefixes = {args.type} if getattr(args, "type", None) else None
   issues = find_issues(config, type_prefixes=type_prefixes)   # :62
   ```
   This single call is the BUG-2897 half and the absorbed BUG-2898 half
   simultaneously — consistent with merging the two issues.

2. **`sequence.py:90` already does the right thing** for the `all_known_ids`
   argument: `find_issues(config, status_filter=set(_ALL_STATUSES))`. So
   `_ALL_STATUSES` is already imported in this module and the superset-load
   pattern is already present one line away from the defect. The fix is smaller
   than the issue implies.

The `Verify` rows are *not* asserted broken — the audit establishes the call-site
inventory, not each one's correctness. Work through them during implementation;
the ones whose list comes from a bare `find_issues(config)` share the defect, the
ones fed a pre-built list (sprint `issue_infos`, `child_infos`) inherit whatever
their caller did and need one more hop.

- `scripts/little_loops/parallel/` — wave construction consumes the same graph

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis, resolving the 11
`Verify` rows above one hop further to their list source:_

**Exact anchors** (referenced elsewhere in this issue without line numbers):
- `find_issues()` — `scripts/little_loops/issue_parser.py:1425`
- `_matches_status()` — `scripts/little_loops/issue_parser.py:1468`; the
  `status_filter is None` branch (the BUG-2897 defect) is at `:1470`
- `_ALL_STATUSES` — `scripts/little_loops/issue_progress.py:12`
- `_TERMINAL_STATUSES` — `scripts/little_loops/issue_progress.py:14`

**Confirmed affected (bare `find_issues(config)`, `status_filter=None`) — 5 more sites beyond `sequence.py:77`:**
- `issue_manager.py:1237` — fed by `all_issues = find_issues(self.config, self.category)` (`issue_manager.py:1228`)
- `cli/issues/link.py:222` — fed by `issues = find_issues(config)` (`cli/issues/link.py:214`); this site also passes no `all_known_ids`, so it will additionally start emitting dropped-edge warnings once the graph gains the deferred nodes — worth a deliberate check during implementation, not just a silent fix
- `cli/issues/next_issue.py:72` — fed by `raw_issues = find_issues(config)` (`cli/issues/next_issue.py:51`)
- `cli/issues/next_issues.py:57` — fed by `raw_issues = find_issues(config)` (`cli/issues/next_issues.py:44`)
- `cli/deps.py` `analyze`/`validate` command path (reaches `dependency_mapper/analysis.py:481`/`539` via `validate_dependencies`/`analyze_dependencies`) — sourced from `_load_issues()` → `issues = find_issues(config, only_ids=only_ids)` at `cli/deps.py:38`, a bare call. Note this is a **different** call path than the `cli/deps.py:292` row in the audit table, which is the epic-tree path and is NOT affected (see below) — the audit table's single `cli/deps.py` row conflates two distinct call paths in the same file.

**Confirmed NOT affected (explicit non-terminal superset already passed, or no `find_issues()` in the chain):**
- `issue_parser.py:1520` — `all_active` is built from `non_terminal = _ALL_STATUSES - _TERMINAL_STATUSES` (`issue_parser.py:1494`), bypassing `find_issues()`'s default filter entirely — this is the existing precedent, confirmed clean
- `cli/deps.py:292` (epic-tree path) — fed by `all_issues = _find_issues(tree_cfg, status_filter=all_statuses)` (`cli/deps.py:274`) where `all_statuses` explicitly includes `deferred`, `done`, and `cancelled`
- `cli/sprint/show.py:190`, `cli/sprint/run.py:490`, `cli/sprint/manage.py:99` — all three source `issue_infos` from `SprintManager.load_issue_infos()` (`sprint.py:451`), which parses named issue IDs directly via `IssueParser.parse_file()` and never calls `find_issues()` or applies any status filter at all

**Excluded by pre-existing explicit design, not the BUG-2897 default-branch code path (same symptom, different root):**
- `sprint.py:367` — `child_infos` derives from `all_active = find_issues(self.config, status_filter=_ACTIVE_STATUSES)` (`sprint.py:341`), where `_ACTIVE_STATUSES = {"open", "in_progress", "blocked"}` (`sprint.py:15`) intentionally excludes `deferred`. This is a separate, deliberate exclusion for sprint composition (a work-selection surface, where hiding `deferred` is correct per Option A's recommendation) — not a defect to fix under this issue, but worth a cross-reference note if a future change touches sprint dependency display.

**Revised affected count**: 6 confirmed-affected call sites total (`sequence.py:77` plus the 5 above), 6 confirmed-clean, 1 excluded-by-design.

### Similar Patterns
- `find_issues(skip_blocked=True)` already builds a non-terminal superset for
  exactly this reason — the precedent to follow
- `ll-issues deferred-triage` is the intended visibility surface for deferred
  work; cross-check that this fix doesn't duplicate its role

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase-pattern-finder analysis:_

- The `skip_blocked=True` precedent (`issue_parser.py:1484-1522`) is confirmed
  to work exactly as described: `non_terminal = _ALL_STATUSES -
  _TERMINAL_STATUSES` (line ~1494) builds one unfiltered non-terminal parse
  pass over every category regardless of the caller's own filters, builds
  `DependencyGraph.from_issues(all_active, ...)` from that superset, then
  derives the caller's actual `issues` display list from the same in-memory
  pass — single directory walk, not two (`test_find_issues_skip_blocked_single_parse_pass`
  guards this, ENH-2780).
- No `find_issues_for_graph()`-style extracted helper exists anywhere yet
  (grepped `find_issues_for_graph`, `graph.*loader` — no hits). All 12
  `DependencyGraph.from_issues(` call sites currently inline their own
  `find_issues(...)` + `from_issues(...)` pairing. The issue's suggestion to
  "consider extracting a small helper" is confirmed as genuinely new work, not
  something to just call.
- `sequence.py:90`'s second `find_issues()` call (`status_filter=set(_ALL_STATUSES)`)
  builds only an `issue_statuses` dict for prose-dep terminal-status checks —
  it does not feed the graph itself, so it's not a template to copy for the
  graph-building fix, only for the "how do I get a full-status dict" need.

### Tests
- `scripts/tests/test_issues_cli.py` — add a deferred-blocker sequencing case;
  no `deferred`-status test currently exists in the `TestSequence*` class
  block (lines 1410-1791) — existing deferred coverage lives only at the
  `find_issues()` unit level
- `scripts/tests/test_issue_manager.py` — graph construction with deferred nodes
- Regression: assert a `done` blocker still resolves (BUG-2733 behaviour) while
  a `deferred` blocker does not
- Model new tests after the existing paired contrast in `test_issue_parser.py`:
  `test_find_issues_skip_blocked_deferred_blocker_still_blocks` (:1374-1394,
  deferred blocker still blocks) and
  `test_find_issues_skip_blocked_terminal_blocker_unblocks` (:1352-1372, `done`
  blocker unblocks) — same fixture shape, opposite assertion
- `test_find_issues_skip_blocked_false_byte_identical_for_all_caller_shapes`
  (`test_issue_parser.py:1396-1523`) is the existing model for proving no
  caller's *display* behavior regresses while the *graph-building* superset
  changes — it enumerates real call-site kwargs shapes annotated with their
  source line; extend it or write a sibling for this fix

### Documentation
- `.claude/CLAUDE.md` § Issue File Format — note that `deferred` is non-terminal
  for dependency purposes
- `docs/reference/API.md` — `find_issues` / `DependencyGraph` entries

### Configuration
- N/A

## Implementation Steps

1. Add a failing test: dependent of a `deferred` blocker must report blocked.
2. ~~Audit `DependencyGraph.from_issues()` call sites for default-filter reliance.~~
   **Done 2026-07-29** — inventory in Dependent Files. Remaining work is walking
   the 11 `Verify` rows one hop further to their list source and fixing those that
   share the defect.
3. Introduce the non-terminal superset load for graph construction (Option A),
   ideally behind one named helper.
4. Separate graph-membership from display-membership in `cmd_sequence()`.
5. Annotate deferred blockers distinctly in both text and `--json` output.
6. Update `from_issues()` docstring to say "terminal" rather than "completed".
7. Run `python -m pytest scripts/tests/`.

## Impact

- **Severity**: Correctness — silent wrong answer, no warning
- **Scope**: `ll-issues sequence` confirmed broken. 12 `from_issues()` call sites
  inventoried (see Dependent Files); `sequence.py:77` is the one with a
  demonstrated default-filter dependency. The remaining 11 are candidates whose
  list-provenance must be walked one hop further during implementation — they are
  inventoried, not yet cleared.
- **Risk of fix**: Low for Option A; the graph gains nodes it should always have
  had. Watch for deferred issues leaking into *display* lists — the display
  filter must stay narrow.
- **User-visible**: Yes — new `(deferred)` annotations and previously-hidden
  blocked states will appear

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` § Issue File Format | Defines the status enum and the deferral discriminator (`deferred_by`/`deferred_reason`) that autodev stamps |
| `docs/ARCHITECTURE.md` | Orchestration layers that consume the dependency graph |
| `docs/reference/API.md` | `little_loops.dependency_graph` / `issue_parser` reference |

## Steps to Reproduce

1. Create a scratch project with `.ll/ll-config.json` and `.issues/bugs/`.
2. Write `BUG-001` with `status: deferred`.
3. Write `BUG-002` with `status: open` and `blocked_by: [BUG-001]`.
4. Run `ll-issues sequence`.
5. Observe `BUG-002` rendered as `[P3, no blockers]`.
6. Change `BUG-001` to `status: open`, re-run — observe the blocker now appears.

## Root Cause

`scripts/little_loops/issue_parser.py`, `find_issues()` → `_matches_status()`:

```python
if status_filter is None:
    return info.status not in ("done", "cancelled", "deferred")
```

`deferred` is grouped with the terminal statuses for filtering purposes. The
resulting list is handed to `DependencyGraph.from_issues()`, whose
`blocker_id not in all_issue_ids` guard then drops the edge as out-of-graph. The
warning is suppressed by the `all_known_ids` check, which was added by BUG-2802
to silence legitimate `done` references.

## Location

- `scripts/little_loops/issue_parser.py` — `find_issues()` / `_matches_status()`
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph.from_issues()`
- `scripts/little_loops/cli/issues/sequence.py` — `cmd_sequence()`

## Session Log
- `/ll:confidence-check` - 2026-07-28T00:00:00Z - `441ef83e-0cde-42e0-afee-c51c388cc71f.jsonl`
- `/ll:decide-issue` - 2026-07-29T01:40:41 - `e92a4acb-e07e-4abc-a10c-a6fee7eacecf.jsonl`
- `/ll:refine-issue` - 2026-07-29T01:38:23 - `f658c4fd-e051-4ee6-95c7-6f9f287dbf58.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-28T23:17:14 - `139954b3-6523-4f66-ba64-f2917d895a02.jsonl`
- `/ll:capture-issue` - 2026-07-28T22:29:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/73139eea-b48b-4fa0-a6fa-0b390a284d9f.jsonl`

---

## Status

**Status**: open

---

## Scope Addition

**Source**: Merged from BUG-2898 during `/ll:audit-issue-conflicts` conflict resolution.

BUG-2898 (`--type` drops cross-type dependencies) is absorbed here because it
required the *same* "build the graph wide, filter the display narrow"
restructuring of `cmd_sequence()`, on a second axis. Landing them separately
risked two conflicting rewrites of the same function — BUG-2898's proposed
`all_active = find_issues(config)` is the bare default call whose
`status_filter=None` path is precisely the defect this issue fixes.

The merged change is a single restructuring with **two** widening axes and one
narrowing step:

1. **Build wide** — one graph-construction call that widens on both axes:

```python
from little_loops.issue_progress import _ALL_STATUSES, _TERMINAL_STATUSES

non_terminal = _ALL_STATUSES - _TERMINAL_STATUSES  # includes deferred
graph_issues = find_issues(config, status_filter=non_terminal)  # NO type_prefixes
graph = DependencyGraph.from_issues(graph_issues, all_known_ids=all_known_ids)
```

   Note the absence of `type_prefixes` — that is BUG-2898's half. Passing
   `type_prefixes={args.type}` here is what drops cross-type prerequisites.

2. **Display narrow** — apply *both* narrowings to the ordered display list,
   below the `try`/`except` so the cycle-fallback path is covered too:

```python
display = [i for i in ordered if i.status in ACTIVE_STATUSES]   # BUG-2897 half
type_prefix = getattr(args, "type", None)
if type_prefix:                                                  # BUG-2898 half
    display = [i for i in display if i.issue_id.split("-", 1)[0] == type_prefix]
shown = display[:limit]
```

3. **Empty-result message** (from BUG-2898) — the current early return
   (`if not issues: print("No active issues found.")`) fires before graph
   construction. With this change, "no active issues at all" and "no issues of
   the requested type" become distinguishable and should print different
   messages.

Absorbed acceptance criteria from BUG-2898:

- Under `--type BUG`, an issue blocked by a non-BUG prerequisite still reports
  that blocker rather than appearing unblocked.
- `--json` `blocked_by`/`depends_on` are non-empty for a cross-type-blocked
  issue under `--type`.
- The dropped-edge warning is no longer suppressed misleadingly for out-of-type
  prerequisites that exist on disk.
