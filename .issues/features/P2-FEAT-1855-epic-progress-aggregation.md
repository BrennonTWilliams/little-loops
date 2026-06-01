---
id: FEAT-1855
type: FEAT
priority: P2
status: done
captured_at: '2026-06-01T17:35:32Z'
completed_at: '2026-06-01T19:49:09Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
relates_to:
- ENH-1727
- FEAT-1737
parent: EPIC-1864
confidence_score: 95
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
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

Implement aggregation as a pure function over the already-loaded `IssueInfo` list:

```python
# scripts/little_loops/issue_progress.py (new)
@dataclass
class EpicProgress:
    epic_id: str
    epic_title: str
    children: list[IssueInfo]
    by_status: dict[str, int]   # canonical status enum -> count
    percent_done: float
    percent_blocked: float
    oldest_open: IssueInfo | None
    oldest_open_age_days: int | None

def compute_epic_progress(epic_id: str, all_issues: list[IssueInfo]) -> EpicProgress | None:
    """Union of relates_to: (forward) + parent: (backward), dedup."""
    ...
```

Reuse the resolution path established by `SprintManager.load_or_resolve()` (FEAT-1737) so EPIC→children resolution is identical between sprint execution and progress reporting. Render via a new `cli/issues/epic_progress.py` and bucket-header extension in `cli/issues/list_cmd.py`.

For age computation, prefer `captured_at:` (ISO 8601) → fall back to `discovered_date:` → fall back to git log first-touched timestamp.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Type name correction**: The domain class is `IssueInfo` (from `issue_parser.py`), not `IssueFile`. All references to `IssueFile` in this issue should be read as `IssueInfo`.

**Sprint resolution vs. progress resolution**: `SprintManager.load_or_resolve()` contains the epic resolution logic inline (lines ~304-355). Sprint resolution calls `find_issues(config, status_filter=_ACTIVE_STATUSES)` which excludes `done`/`cancelled`/`deferred`. Progress reporting must include all statuses — call `find_issues(config)` with **no status filter** (or `status_filter=None`) to get the full child set, mirroring how `deps.py:main_deps()` does it for tree display. The forward+backward union pattern is identical:
```python
forward_ids = set(epic_info.relates_to)
backward_ids = {i.issue_id for i in all_issues if i.parent == epic_id}
child_ids = forward_ids | backward_ids   # no active-only intersection for progress
```

**Age computation**: `_parse_discovered_date()` in `scripts/little_loops/cli/issues/search.py` already implements the exact fallback chain: `captured_at` (ISO datetime) → `discovered_date` (date-granular) → file mtime. Note: `captured_at` is **not** a field on `IssueInfo` — it must be read from file content. Consider extracting `_parse_discovered_date()` into a shared utility (e.g., `issue_parser.py` or a new `issue_utils.py`) rather than importing from a CLI module.

**Progress bar rendering**: `cli/output.py:progress(current, total, width=20)` exists and returns `|###  |` ASCII format. The expected output in this issue shows Unicode block characters (`████░░`). The implementer must either (a) use the existing ASCII `progress()` utility and update the expected output, or (b) add a new `sparkline()` function to `cli/output.py` using Unicode block elements. No Unicode sparkline utility currently exists in the codebase.

**`--format` flag convention**: The issue specifies `--format {text,json,markdown}`. Most existing subcommands use a `--json` boolean flag (`--json`/`-j`). The three-choice `--format` pattern exists in `cli/deps.py`. For the `epic-progress` subcommand, use `--format {text,json,markdown}` (consistent with the issue spec and deps.py) since markdown output is required.

**`find_issues()` import**: `from little_loops.issue_parser import find_issues` — defer inside function body per CLI convention.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_progress.py` — new pure-function module; `EpicProgress` dataclass + `compute_epic_progress()`
- `scripts/little_loops/cli/issues/__init__.py` — register `epic-progress` subcommand in `main_issues()` dispatch chain (after `skip` entry, lines ~695-696)
- `scripts/little_loops/cli/issues/epic_progress.py` — new subcommand; `cmd_epic_progress(config, args) -> int`
- `scripts/little_loops/cli/issues/list_cmd.py` — extend `--group-by epic` bucket headers in `cmd_list()` (epic-grouping branch, lines ~135-176); call `compute_epic_progress()` per bucket to append `(N/M done · K blocked)` badge

### Dependent Files (Callers/Importers)
- `scripts/little_loops/sprint.py` — epic resolution inline in `SprintManager.load_or_resolve()` (lines ~304-355) — forward+backward union pattern to replicate (do NOT call directly; copy the two-pass logic and skip the active-only intersection)
- `scripts/little_loops/issue_parser.py` — `find_issues(config)` with no `status_filter` for all-status child loading; `IssueInfo.parent` (`str | None`) and `IssueInfo.relates_to` (`list[str]`) fields
- `scripts/little_loops/cli/issues/search.py` — `_parse_discovered_date(content: str, file_path: Path | None = None)` for age fallback chain (`captured_at` → `discovered_date` → file mtime)
- `scripts/little_loops/cli/output.py` — `progress(current, total, width)` ASCII bar utility; `print_json()` for `--format json`; `colorize()` / `TYPE_COLOR` / `PRIORITY_COLOR` for terminal output

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — imports and re-exports `main_issues` in `__all__` (lines 50, 92); this is the top-level CLI entry point that makes `ll-issues` available as a console script — no changes needed but must be aware that the `add_parser()` call in `cli/issues/__init__.py` is what registers the subcommand visible to users

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py:cmd_list()` — epic-grouping branch (ENH-1727) — `parent_buckets` dict structure, `Unparented` bucket convention, bucket header rendering
- `scripts/little_loops/cli/issues/clusters.py:_ACTIVE_STATUSES` — canonical active-status frozenset (`frozenset({"open", "in_progress", "blocked"})`) to import or replicate
- `scripts/little_loops/cli/deps.py` — `--format {text,json}` multi-format subcommand pattern; `print_json()` usage

### Tests
- `scripts/tests/test_issue_progress.py` (new) — unit tests for `compute_epic_progress`: empty children, all done, mixed, blocked-with-no-open, age fallback chain
- `scripts/tests/test_issues_cli.py:TestIssuesCLIList` — extend `--group-by epic` tests to assert progress badges (follow `test_list_json_output` class structure with `patch.object(sys, "argv", [...])` + `capsys`)
- `scripts/tests/test_issues_cli.py` — new `TestIssuesCLIEpicProgress` class for the new subcommand

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_search.py` — contains 6 test functions + `TestCreatedSortSubDayResolution` class (lines ~1051–1194) that import `_parse_discovered_date` directly from `little_loops.cli.issues.search`; if `_parse_discovered_date` is extracted to a shared location (e.g., `issue_parser.py`) as the issue suggests, all 7 import paths in this file must be updated — this is a required change if extraction happens [Agent 2 finding]
- `scripts/tests/test_cli_output.py` — existing tests for `cli/output.py`; `progress()` has no unit tests anywhere; if `sparkline()` is added to `cli/output.py` for Unicode block rendering, tests for both `progress()` and `sparkline()` should live here [Agent 3 finding]
- Note: `test_list_group_by_epic_parented` (line 741) and `test_list_group_by_epic_unparented` (line 770) in `TestIssuesCLIList` use `in` substring assertions — they will NOT break when badges are appended to EPIC headers; no update required for those specific assertions [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` — `ll-issues epic-progress` flag table + `--group-by epic` badge note
- `docs/guides/EPIC_GUIDE.md` (new or appended) — progress workflow

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — `## Browsing Issues by Epic` section (line ~463) describes `--group-by epic` output format and shows sample output; the prose and example will be stale once progress badges are added to bucket headers — update this section alongside `docs/reference/CLI.md` [Agent 2 finding]
- `.claude/CLAUDE.md` — CLI Tools section, `ll-issues` entry (~line 176) enumerates subcommands in a parenthetical list; `epic-progress` must be added alongside the existing entries [Agent 2 finding]
- `docs/ARCHITECTURE.md` — directory tree listing (~lines 223–235) enumerates `cli/issues/` subcommand files by name; a new `epic_progress.py` entry must be added; the top-level `issue_progress.py` new module also needs an entry in the parent module listing [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. **Resolve children** — replicate the two-pass union from `sprint.py:SprintManager.load_or_resolve()` (lines ~304-355) in `issue_progress.py:compute_epic_progress()`: `forward_ids = set(epic_info.relates_to)` + `backward_ids = {i.issue_id for i in all_issues if i.parent == epic_id}`. Call `find_issues(config)` with **no status filter** so done/cancelled/deferred children are included (unlike sprint execution which uses `status_filter=_ACTIVE_STATUSES`).
2. **Compute aggregates** — `compute_epic_progress()` returns `EpicProgress`; pure function, no I/O. Use `IssueInfo` (not `IssueFile`) as the child type. For age: call `_parse_discovered_date(content: str, file_path: Path | None = None)` from `cli/issues/search.py` or extract it to a shared location first.
3. **Progress bar** — decide: (a) use existing `cli/output.py:progress(current, total)` ASCII `|###  |` bar and update the expected output, OR (b) add `sparkline(current, total, width=16)` to `cli/output.py` using Unicode block characters. Whichever is chosen, document in `docs/reference/CLI.md`.
4. **`epic-progress` subcommand** (`cli/issues/epic_progress.py:cmd_epic_progress()`) — add `--format {text,json,markdown}` following the `cli/deps.py` pattern. Register in `cli/issues/__init__.py` `main_issues()` dispatch chain; import `cmd_epic_progress` at the top of the `with cli_event_context(...)` block.
5. **List badge** — in `cli/issues/list_cmd.py:cmd_list()` epic-grouping branch, call `compute_epic_progress()` per EPIC bucket and append `(N/M done · K blocked)` to the header line. Import `compute_epic_progress` at the top of the function body (deferred import pattern).
6. **Tests** — `test_issue_progress.py`: unit tests for `compute_epic_progress` (empty/all-done/mixed/blocked-only/age-fallback); `test_issues_cli.py:TestIssuesCLIList`: extend with `--group-by epic` badge assertion; `test_issues_cli.py:TestIssuesCLIEpicProgress`: new class following `test_list_json_output` structure with `patch.object(sys, "argv", [...])` + `capsys`.
7. **Docs** — update `docs/reference/CLI.md` with `ll-issues epic-progress` flag table and `--group-by epic` badge note.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — revise the `## Browsing Issues by Epic` section's prose and sample output to reflect the badge format added to `--group-by epic` headers; coordinate with step 7 so both docs show consistent examples
9. Update `.claude/CLAUDE.md` — add `epic-progress` to the `ll-issues` parenthetical subcommand list in the CLI Tools section (~line 176); keep alphabetical/logical order with existing entries
10. Update `docs/ARCHITECTURE.md` — add `epic_progress.py` to the `cli/issues/` directory tree listing (~lines 223–235) and add `issue_progress.py` to the parent `little_loops/` module listing
11. If extracting `_parse_discovered_date` to a shared location: update `scripts/tests/test_issues_search.py` — 6 test functions + `TestCreatedSortSubDayResolution` class (lines ~1051–1194) import from `little_loops.cli.issues.search`; update their import paths to the new shared location; also update `list_cmd.py` line 28 import

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Subcommand registration in `main_issues()` follows a flat `if args.command == "..."` dispatch chain — add an `elif args.command == "epic-progress":` branch and import `cmd_epic_progress` alongside other imports at the top of the `with cli_event_context(...)` block.
- `find_issues()` accepts `status_filter: set[str] | None = None`; passing `None` returns all statuses.
- Test fixtures use `temp_project_dir`, `sample_config`, `issues_dir` from `conftest.py`; EPIC-specific child fixtures are defined inline in the test file (see `issues_dir_with_epic_children` pattern in `test_issues_cli.py`).
- `print_json()` in `output.py` handles JSON serialization — pass a `dict` or `list[dict]` from `EpicProgress.to_dict()`.
- `_parse_discovered_date()` is module-private in `search.py`; if reusing it directly, consider whether to keep the private reference or extract to `issue_parser.py`.

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
from dataclasses import dataclass, field
from little_loops.issue_parser import IssueInfo   # IssueInfo, not IssueFile

@dataclass
class EpicProgress:
    epic_id: str
    epic_title: str
    children: list[IssueInfo]
    by_status: dict[str, int]   # e.g. {"open": 2, "done": 8, "blocked": 1, ...}
    percent_done: float
    percent_blocked: float
    oldest_open: IssueInfo | None
    oldest_open_age_days: int | None

    def to_dict(self) -> dict:
        """For --format json output via print_json()."""
        ...

def compute_epic_progress(
    epic_id: str,
    all_issues: list[IssueInfo],   # loaded with no status_filter — includes done/cancelled
) -> EpicProgress | None: ...
```

CLI:

```
ll-issues epic-progress EPIC-NNN [--format {text,json,markdown}]
ll-issues list --group-by epic     # now includes (N/M done · K blocked) badge
```

## Related Key Documentation

- `docs/reference/CLI.md` — ll-issues CLI reference (add `epic-progress` entry here)
- `docs/reference/API.md` — Python module reference (document `issue_progress.py` here)
- `docs/reference/HOST_COMPATIBILITY.md` — host CLI abstraction reference
- `scripts/little_loops/cli/issues/clusters.py` — `_ACTIVE_STATUSES` frozenset (active status definition)
- `scripts/little_loops/cli/issues/search.py` — `_parse_discovered_date()` for age computation

## Labels

`enhancement`, `epics`, `cli`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-06-01T19:34:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0ab8b4ae-3378-4730-9736-479cb6d5aa6e.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b683bd50-bc7c-486c-b125-062c3399175d.jsonl`
- `/ll:wire-issue` - 2026-06-01T19:26:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d4e1a7d5-5056-4e46-8db9-e529fbf37c68.jsonl`
- `/ll:refine-issue` - 2026-06-01T19:17:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ba071d29-681d-440e-9a8d-833fa01b9c50.jsonl`
- `/ll:format-issue` - 2026-06-01T17:44:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da2e50a4-7590-4ddf-b880-913ecbd374e7.jsonl`
- `/ll:capture-issue` - 2026-06-01T17:35:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/277dd3c5-ffef-46cb-bcc6-124409ce1225.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P2
