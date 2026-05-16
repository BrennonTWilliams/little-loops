---
discovered_date: 2026-03-03T00:00:00Z
discovered_by: capture-issue
---

# FEAT-544: `ll-issues` Refinement Status Table View

## Summary

Add a new `ll-issues refine-status` subcommand (or `ll-issues list --refinement`) that renders all open/active issues in a table where each column represents a refinement command or skill found in the `## Session Log` section. Issues are sorted by refinement depth — the more commands have touched an issue, the higher it appears.

## Current Behavior

`ll-issues` has no `refine-status` subcommand. The only way to assess an issue's refinement state is to open each file individually and read its `## Session Log`. With a growing backlog there is no at-a-glance view showing which issues have been through `/ll:refine-issue`, `/ll:ready-issue`, `/ll:confidence-check`, or other commands.

## Expected Behavior

`ll-issues refine-status` renders a table of all active issues. Each column maps to a distinct `/ll:<name>` command found across Session Log entries (derived dynamically — no hardcoded list). A `Total` column sorts issues descending by refinement depth; `Ready` and `OutConf` columns surface the numeric `confidence_score` and `outcome_confidence` values from frontmatter.

## Motivation

As the issue backlog grows, it becomes hard to see which issues are "implementation-ready" vs. just created. The Session Log already records every command that has touched an issue (`/ll:scan-codebase`, `/ll:refine-issue`, `/ll:tradeoff-review-issues`, `/ll:ready-issue`, `/ll:confidence-check`, etc.), but there is no way to see this at a glance across all issues. A refinement table makes sprint planning and backlog triage instant.

## Use Case

**Who**: Developer or tech lead managing a growing issue backlog.

**Context**: About to start a sprint planning session with 20+ active issues; unsure which have been through the full refinement pipeline.

**Goal**: Identify at a glance which issues are implementation-ready and which still need `/ll:refine-issue`, `/ll:ready-issue`, or `/ll:confidence-check` passes.

**Outcome**: A ranked table sorted by refinement depth makes the decision instant:

```
ID       Pri  Title                          scan  refine  tradeoff  ready  confidence  Ready  OutConf  Total
BUG-525  P2   TOCTOU race condition           ✓     ✓        ✓        ✓        ✓          92     78       5
ENH-534  P2   Fatal error loop stop signals   ✓     ✓        ✓        —        —           —      —       3
FEAT-543 P4   ll-loop history filtering       ✓     —        —        —        —           —      —       1
FEAT-544 P3   ll-issues refine-status table   —     —        —        —        —           —      —       0
```

`Ready` and `OutConf` show the numeric `confidence_score` and `outcome_confidence` values written to frontmatter by `/ll:confidence-check` (0–100).

## Acceptance Criteria

- `ll-issues refine-status` prints a table of all active issues (excludes completed/deferred)
- Columns are dynamically derived from the distinct `/ll:<name>` entries found across all Session Log sections — no hardcoded list
- Each column shows `✓` if that command appears in the issue's Session Log, `—` if not
- Two fixed numeric columns — `Ready` (`confidence_score`) and `OutConf` (`outcome_confidence`) — show the values written to YAML frontmatter by `/ll:confidence-check`; display `—` if absent
- A `Total` column shows the count of distinct commands that have touched the issue
- Issues are sorted descending by `Total`, then by priority as a tiebreaker
- `--type BUG|FEAT|ENH` filter is supported (consistent with `ll-issues list`)
- `--format json` outputs the same data as newline-delimited JSON for scripting
- Table respects terminal width — truncates long titles with `…` rather than wrapping

## API/Interface

```bash
ll-issues refine-status                   # All active issues, sorted by refinement depth
ll-issues refine-status --type BUG        # Only bugs
ll-issues refine-status --format json     # JSON output
```

Example JSON record:
```json
{"id": "BUG-525", "priority": "P2", "title": "TOCTOU race condition", "commands": ["scan-codebase", "refine-issue", "tradeoff-review-issues", "ready-issue", "confidence-check"], "confidence_score": 92, "outcome_confidence": 78, "total": 5}
```

## Implementation Steps

1. **Extract `parse_session_log()` to `session_log.py`** — move the inline logic from `show.py:168-178` to a standalone exported function in `scripts/little_loops/session_log.py`; signature: `parse_session_log(content: str) -> list[str]` returning distinct `/ll:*` command names found in the `## Session Log` section. Regex: `r"^## Session Log\s*\n+(.*?)(?:\n##|\n---|\Z)"` (MULTILINE|DOTALL), then `r"`(/[\w:-]+)`"` to extract commands.
2. **Add `confidence_score` and `outcome_confidence` to `IssueInfo`** — extend `scripts/little_loops/issue_parser.py:131-158` with two new fields (`confidence_score: int | None` and `outcome_confidence: int | None`) and populate them from `parse_frontmatter(content, coerce_types=True)` in `IssueParser.parse_file()` (around line 245). Also add `session_commands: list[str]` field populated by calling `parse_session_log()`.
3. **Implement `scripts/little_loops/cli/issues/refine_status.py`** — `cmd_refine_status(config, args) -> int`:
   - Call `find_issues(config, type_prefixes=...)` for issue list (already sorted by priority)
   - Derive dynamic column set: collect all distinct command names across all issues' `session_commands`, sort consistently
   - Use `shutil.get_terminal_size().columns` to compute max title width; truncate with `…` (U+2026)
   - Render header row + separator + per-issue rows with `✓`/`—` cells
   - For `--format json`: emit one JSON object per line (JSONL) with fields: `id`, `priority`, `title`, `commands`, `confidence_score`, `outcome_confidence`, `total`
4. **Register `refine-status` subparser in `__init__.py`** — follow `impact_effort.py` pattern (line 22 import, `subs.add_parser("refine-status", ...)`, `add_config_arg()`, dispatch `if args.command == "refine-status"`); add `--type` flag (mirroring `list` subcommand at line 53) and `--format` flag with `choices=["table", "json"]`
5. **Write tests in `scripts/tests/test_refine_status.py`** — follow `test_issues_cli.py:563-583` pattern: write fixture issue files with frontmatter + Session Log entries, patch `sys.argv`, call `main_issues()`, assert `capsys.readouterr()` output; cover: Session Log parsing, dynamic column derivation, sort order (by Total desc then priority), `—` for missing scores, JSONL output format, `--type` filter

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — register `refine-status` subparser (add import at line ~22, `subs.add_parser` call, and dispatch `if args.command == "refine-status"`)
- `scripts/little_loops/issue_parser.py` — add `confidence_score: int | None`, `outcome_confidence: int | None`, and `session_commands: list[str]` fields to `IssueInfo` dataclass (lines 131–158); populate in `IssueParser.parse_file()` (~line 245)
- `scripts/little_loops/session_log.py` — extract `parse_session_log(content: str) -> list[str]` from inline logic in `show.py:168-178` into a new exported function here

### Files to Create
- `scripts/little_loops/cli/issues/refine_status.py` — new subcommand module implementing `cmd_refine_status(config, args) -> int`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/show.py:168-178` — currently contains the inline Session Log parsing to refactor into `session_log.py`; update to call the new shared function after extraction

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py` — `cmd_list()` for issue iteration and `--type` filter pattern (`type_prefixes = {args.type} if args.type else None`)
- `scripts/little_loops/cli/issues/impact_effort.py` — table rendering with `✓`/`…` patterns and `_COL_WIDTH` fixed-column approach (note: filename is `impact_effort.py`, not `impact_effort_cmd.py`)
- `scripts/little_loops/cli/issues/show.py:261-281` — dynamic-width card rendering using `textwrap` (content-width-based)
- `scripts/little_loops/cli/deps.py:107-218` — `--format` argparse + `if args.format == "json"` dispatch pattern
- `scripts/little_loops/user_messages.py:717-726` — JSONL output via `print(json.dumps(obj))` per record

### Tests
- `scripts/tests/test_refine_status.py` — new test file (follow `test_issues_cli.py:563-583` fixture pattern: write issue files, patch `sys.argv`, call `main_issues()`, assert `capsys.readouterr()`)
- `scripts/tests/test_session_log.py` — add tests for new `parse_session_log()` function
- `scripts/tests/test_issue_parser.py` — add tests for new `IssueInfo` fields

### Documentation
- CLI help text auto-generated via argparse `description`
- `docs/reference/API.md` — update `ll-issues` subcommand list (line ~2251)

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Session Log regex** (from `show.py:168-174`): `re.search(r"^## Session Log\s*\n+(.*?)(?:\n##|\n---|\Z)", content, re.MULTILINE | re.DOTALL)` then `re.findall(r"`(/[\w:-]+)`", log_match.group(1))` — works for both `—` (em-dash) and `-` (hyphen) separator variants found in real issue files
- **`show.py:168-178` uses `Counter` for display** — the existing code returns a comma-joined string like `"/ll:refine-issue (2), /ll:ready-issue"` for the card view. `parse_session_log()` must return a distinct list instead: `list(dict.fromkeys(cmds))` preserves insertion order and deduplicates. The display string logic stays in `show.py`.
- **IssueInfo is at `issue_parser.py:131-158`**; `find_issues()` at line 491 returns `list[IssueInfo]` sorted by `(priority_int, issue_id)` ascending — refine-status will need to re-sort descending by `len(session_commands)` then ascending by priority
- **`parse_frontmatter(content, coerce_types=True)`** (from `frontmatter.py:13`) returns `confidence_score` and `outcome_confidence` as Python `int` when present; `IssueParser.parse_file()` currently calls it without `coerce_types` and does **manual** int conversion for `effort`/`impact` at lines 250-251. For consistency, use the same `str(val).isdigit()` guard pattern for `confidence_score`/`outcome_confidence` rather than switching to `coerce_types=True`.
- **`confidence_score`/`outcome_confidence` only in a subset of issues**: 4 issues confirmed (ENH-507, ENH-493, ENH-470, ENH-495); most recent issues (BUG-525+) lack them — `—` display for absent values is necessary
- **No `shutil.get_terminal_size` currently used anywhere** — this is a new pattern for the codebase; `show.py` uses content-width sizing instead. Decision: use `shutil.get_terminal_size().columns` for the title truncation column
- **JSON output decision**: use JSONL (one object per line via `print(json.dumps(record))`) — matches `user_messages.py:717-726` pattern and issue spec; deviates from `deps.py` indented JSON convention
- **`--format` flag in `__init__.py`**: add `refine_s.add_argument("--format", choices=["table", "json"], default="table")` consistent with `ll-deps` / `ll-history` patterns

### Corrections from Second Refinement Pass

_Added by `/ll:refine-issue` — verified against codebase:_

- **`session_log.py` already exists** at `scripts/little_loops/session_log.py` — it exposes `get_current_session_jsonl()` (line 15) and `append_session_log_entry()` (line 38). Implementation Step 1 should ADD `parse_session_log()` to this existing file, NOT create a new one. The "Files to Modify" list is correct; the "Files to Create" list should NOT include `session_log.py`.
- **`__init__.py` imports are deferred inside `main_issues()`** — all five command imports are at lines 17–21 INSIDE the function body, not at module level. The new `from little_loops.cli.issues.refine_status import cmd_refine_status` import goes inside `main_issues()` alongside the others, not at "line ~22" of the module.
- **`impact_effort.py` does NOT use `✓`/`—` cells** — it uses fixed-width quadrant box rendering with `ljust(_COL_WIDTH)` (`impact_effort.py:52-60`). The `✓`/`—` cell pattern described in this issue does not exist anywhere in the codebase and must be implemented fresh in `refine_status.py`. Reference `list_cmd.py` for row-by-row issue iteration; the cell rendering logic is novel.
- **Test fixture reference correction** — `test_issues_cli.py:563-583` contains `test_show_with_frontmatter_scores` (a test method), not a fixture definition. The shared pytest fixture block is at line 60+. Both are valid references: line 60+ for fixture setup pattern, lines 563-583 for the `patch.object(sys, "argv", [...]) + main_issues() + capsys.readouterr()` invocation pattern.

## Impact

- **Priority**: P3 — Valuable for sprint planning and backlog triage but not blocking any workflow
- **Effort**: Large — Non-trivial: dynamic column derivation, terminal-width-aware rendering, Session Log parsing, dual output formats (table + JSON)
- **Risk**: Medium — Session Log format variations across issues could produce unexpected column names; frontmatter parsing must handle missing fields gracefully
- **Breaking Change**: No — fully additive new subcommand

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/cli/issues/list_cmd.py` | Pattern to follow for issue listing |
| `scripts/little_loops/cli/issues/__init__.py` | Where to register new subparser |
| `scripts/little_loops/issue_parser.py` | Issue parsing utilities to extend |

## Resolution

Implemented 2026-03-03. All acceptance criteria met:

- `ll-issues refine-status` prints table of all active issues
- Columns dynamically derived from distinct `/ll:*` entries across all Session Log sections
- `✓` / `—` cells for command presence/absence per issue
- `Ready` and `OutConf` numeric columns from frontmatter; `Total` column
- Issues sorted descending by total, ascending priority as tiebreaker
- `--type BUG|FEAT|ENH` filter and `--format json` (JSONL) supported
- Terminal-width-aware title truncation with `…`

### Files Changed

- `scripts/little_loops/session_log.py` — added `parse_session_log()`
- `scripts/little_loops/issue_parser.py` — added `confidence_score`, `outcome_confidence`, `session_commands` to `IssueInfo`
- `scripts/little_loops/cli/issues/show.py` — refactored to use `parse_session_log()`
- `scripts/little_loops/cli/issues/refine_status.py` — new subcommand
- `scripts/little_loops/cli/issues/__init__.py` — registered `refine-status` subparser

## Session Log

- `/ll:manage-issue` — 2026-03-03T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:refine-issue` — 2026-03-03T09:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2a1b4efd-c8d7-4a60-8c4d-2fe9383c1af1.jsonl`
- `/ll:refine-issue` — 2026-03-03T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a9be526-ccb3-43a0-b119-5acbc3fba8f2.jsonl`
- `/ll:capture-issue` — 2026-03-03T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ace9385-297c-4f88-9e68-d349c8dea381.jsonl`
- `/ll:format-issue` — 2026-03-03T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/26ee613e-e461-449f-abe5-936627dc59aa.jsonl`

---

**Completed** | Created: 2026-03-03 | Resolved: 2026-03-03 | Priority: P3
`feat`, `ll-issues`, `refinement`, `table-view`, `capture-issue`
