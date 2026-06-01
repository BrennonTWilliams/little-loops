---
id: FEAT-1855
type: FEAT
priority: P2
status: open
captured_at: '2026-06-01T17:35:32Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
relates_to: [ENH-1727, FEAT-1737]
parent: EPIC-1864
---

# FEAT-1855: EPIC progress aggregation (% done / blocked rollup)

## Summary

Compute and surface child-issue progress aggregates for an EPIC: count by status (`open`/`in_progress`/`blocked`/`done`/`cancelled`/`deferred`), percent complete, percent blocked, oldest stalled child, and total child count. Expose via a new `ll-issues epic-progress EPIC-NNN` CLI subcommand and inline progress badges in `ll-issues list --group-by epic` headers.

## Current Behavior

EPIC files have no roll-up data. To answer "how is EPIC-1773 going?" the user must `ll-issues list --group-by epic` (already shipped via ENH-1727), then visually scan child statuses one row at a time. There is no aggregate %-complete, no blocker count, and no stalled-child detection. EPIC `status:` does not reflect child progress.

## Expected Behavior

```
$ ll-issues epic-progress EPIC-1773
EPIC-1773: Audit & simplify built-in FSM loops, shared fragments, sub-loops, flows
  Progress:     ████████░░░░░░░░  8/12 done (67%)
  Status:       2 in_progress  •  1 blocked  •  1 open  •  8 done
  Oldest open:  ENH-1641 (24 days)
  Blocked:      ENH-1820 → blocked_by BUG-1701
```

`ll-issues list --group-by epic` adds a progress badge to each bucket header:

```
EPIC-1773: Audit & simplify built-in FSM loops (8/12 done · 1 blocked)
  P2  ENH-1820  ... [blocked]
  ...
```

JSON output via `--format json` for programmatic callers (sprint planners, dashboards, scheduled summarizers).

## Motivation

EPICs are first-class tracking containers (FEAT-1389, FEAT-1407) and can now be dispatched as sprints (FEAT-1737, done), but there is no way to *see* aggregate progress without tallying children by hand. This is the single most common question a user asks of an EPIC ("how close is this initiative to done?") and it is currently the most expensive to answer.

Quantified impact: every user with an active EPIC asks this question every time they triage. With 13 active EPICs in this repo today, a 30-second manual tally per EPIC per check ≈ minutes-per-day of friction that compounds against EPIC adoption.

## Proposed Solution

Implement aggregation as a pure function over the already-loaded `IssueFile` list:

```python
# scripts/little_loops/issue_progress.py (new)
@dataclass
class EpicProgress:
    epic_id: str
    epic_title: str
    children: list[IssueFile]
    by_status: dict[str, int]   # canonical status enum -> count
    percent_done: float
    percent_blocked: float
    oldest_open: IssueFile | None
    oldest_open_age_days: int | None

def compute_epic_progress(epic_id: str, all_issues: list[IssueFile]) -> EpicProgress:
    """Union of relates_to: (forward) + parent: (backward), dedup."""
    ...
```

Reuse the resolution path established by `SprintManager.load_or_resolve()` (FEAT-1737) so EPIC→children resolution is identical between sprint execution and progress reporting. Render via a new `cli/issues/epic_progress.py` and bucket-header extension in `cli/issues/list_cmd.py`.

For age computation, prefer `captured_at:` (ISO 8601) → fall back to `discovered_date:` → fall back to git log first-touched timestamp.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_progress.py` — new pure-function module
- `scripts/little_loops/cli/issues/__init__.py` — register `epic-progress` subcommand
- `scripts/little_loops/cli/issues/epic_progress.py` — new subcommand implementation
- `scripts/little_loops/cli/issues/list_cmd.py` — extend `--group-by epic` bucket headers with badge

### Dependent Files (Callers/Importers)
- `scripts/little_loops/sprint.py` — `SprintManager.load_or_resolve()` resolution logic to reuse (FEAT-1737)
- `scripts/little_loops/issue_parser.py` — `find_issues()` / `IssueFile.parent` / `IssueFile.relates_to`

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py` epic-grouping branch (ENH-1727) — same `parent:` scan, same `Unparented` bucket convention
- `scripts/little_loops/cli/issues/clusters.py:_ACTIVE_STATUSES` — canonical active-status frozenset to reuse

### Tests
- `scripts/tests/test_issue_progress.py` (new) — unit tests for `compute_epic_progress`: empty children, all done, mixed, blocked-with-no-open, age fallback chain
- `scripts/tests/test_issues_cli.py:TestIssuesCLIList` — extend `--group-by epic` tests to assert progress badges
- `scripts/tests/test_issues_cli.py` — new `TestIssuesCLIEpicProgress` class for the new subcommand

### Documentation
- `docs/reference/CLI.md` — `ll-issues epic-progress` flag table + `--group-by epic` badge note
- `docs/guides/EPIC_GUIDE.md` (new or appended) — progress workflow

### Configuration
- N/A

## Implementation Steps

1. **Resolve children** — extract or call into `SprintManager.load_or_resolve()` union path to get an EPIC's child `IssueFile` list. Keep status filter *off* here (progress reports include done/cancelled, unlike sprint execution).
2. **Compute aggregates** — `compute_epic_progress()` returns the dataclass above; pure function, no I/O.
3. **`epic-progress` subcommand** — text renderer (sparkline bar, status counts, oldest stalled), `--format json` path, `--format markdown` for embedding into reports.
4. **List badge** — `cli/issues/list_cmd.py` calls `compute_epic_progress()` per EPIC bucket and appends `(N/M done · K blocked)` to the header.
5. **Tests** — unit + CLI integration; gold-output snapshot for the text renderer.
6. **Docs** — CLI reference + a short guide section.

## Impact

- **Priority**: P2 — Highest-leverage EPIC gap (most-asked question, manually answered today); not blocking but every EPIC user touches this.
- **Effort**: Medium — Pure function + two render surfaces. Resolution logic reused from FEAT-1737.
- **Risk**: Low — Read-only computation; no mutation of any issue file. Existing `--group-by epic` output enriched, not replaced.
- **Breaking Change**: No

## Use Case

A developer reviewing the audit-and-simplify initiative runs `ll-issues epic-progress EPIC-1773` before standup and sees "8/12 done (67%), 1 blocked on BUG-1701, oldest open ENH-1641 at 24 days." Decision: chase BUG-1701 to unblock, defer ENH-1641 if not strategic. Today this decision requires opening 12 files.

## Acceptance Criteria

- [ ] `ll-issues epic-progress EPIC-NNN` renders text report with progress bar, status breakdown, oldest open child, and blocker count.
- [ ] `--format json` emits structured output suitable for piping into scripts.
- [ ] `ll-issues list --group-by epic` headers include `(N/M done · K blocked)` badge.
- [ ] Resolution uses union of `relates_to:` (forward) + `parent:` (backward), deduplicated.
- [ ] Done and cancelled children are *included* in totals (unlike sprint resolution).
- [ ] EPIC with zero children renders a clear "no children" line, exit 0.
- [ ] EPIC ID not found exits non-zero with a clear message.
- [ ] Unit tests cover empty / all-done / mixed / blocked-only / age-fallback cases.
- [ ] `compute_epic_progress` is a pure function with no I/O dependency.

## API/Interface

```python
# scripts/little_loops/issue_progress.py
@dataclass
class EpicProgress:
    epic_id: str
    epic_title: str
    children: list[IssueFile]
    by_status: dict[str, int]
    percent_done: float
    percent_blocked: float
    oldest_open: IssueFile | None
    oldest_open_age_days: int | None

def compute_epic_progress(
    epic_id: str,
    all_issues: list[IssueFile],
) -> EpicProgress | None: ...
```

CLI:

```
ll-issues epic-progress EPIC-NNN [--format {text,json,markdown}]
ll-issues list --group-by epic     # now includes (N/M done · K blocked) badge
```

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `epics`, `cli`, `captured`

## Session Log
- `/ll:format-issue` - 2026-06-01T17:44:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da2e50a4-7590-4ddf-b880-913ecbd374e7.jsonl`
- `/ll:capture-issue` - 2026-06-01T17:35:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/277dd3c5-ffef-46cb-bcc6-124409ce1225.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P2
