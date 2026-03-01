---
discovered_date: "2026-03-01"
discovered_by: capture-issue
---

# FEAT-518: Add `ll-issues show` command for issue summary cards

## Summary

Add a new `ll-issues show [ISSUE-ID]` sub-command that displays a compact "Summary Card" for a given issue, highlighting key frontmatter fields (especially `confidence_score` and `outcome_confidence`), title, status, priority, and type.

The ISSUE-ID argument supports three input formats:
- **Numeric ID only**: `491` (standard/default)
- **Type + ID**: `ENH-491`
- **Priority + Type + ID**: `P3-ENH-491`

## Current Behavior

There is no way to quickly view a summary of a single issue from the CLI. Users must either `cat` the full issue file or use `ll-issues list` which shows all issues without detail.

## Expected Behavior

Running `ll-issues show 518` (or `FEAT-518` or `P3-FEAT-518`) prints a formatted summary card to stdout using box-drawing characters:

```
┌──────────────────────────────────────────────────────────────┐
│ FEAT-518: Add `ll-issues show` command for summary cards     │
├──────────────────────────────────────────────────────────────┤
│ Priority: P3  │  Status: Open  │  Effort: Small              │
│ Confidence: 85  │  Outcome: 78                               │
├──────────────────────────────────────────────────────────────┤
│ Path: .issues/features/P3-FEAT-518-ll-issues-show-...md      │
└──────────────────────────────────────────────────────────────┘
```

Key frontmatter fields (`confidence_score`, `outcome_confidence`) are displayed when present. Completed issues show `Status: Completed` in the status field. The card is concise and terminal-friendly.

## Motivation

Users and automation tools frequently need to check the status of a specific issue without reading the full markdown. A `show` command enables quick lookups by ID and provides a consistent interface alongside the existing `list`, `sequence`, and `impact-effort` sub-commands.

## Use Case

A developer running `/ll:manage-issue` wants to quickly check an issue's confidence score before starting implementation. They run `ll-issues show 491` and see the summary card with scores, priority, and status at a glance — without opening the file or scrolling through markdown.

## Acceptance Criteria

- [ ] `ll-issues show 491` finds the issue by numeric ID across all active directories
- [ ] `ll-issues show ENH-491` finds by type + numeric ID
- [ ] `ll-issues show P3-ENH-491` finds by full prefix
- [ ] Displays title, type, priority, status, effort, and file path
- [ ] Displays `confidence_score` and `outcome_confidence` from frontmatter when present
- [ ] Prints clear error message when issue ID is not found
- [ ] Works with issues in any active subdirectory (bugs/, features/, enhancements/)
- [ ] Also searches completed/ directory (status field shows "Completed")
- [ ] Uses box-drawing characters for card border (consistent with `impact-effort` sub-command)
- [ ] No `--json` flag in initial scope (plain text card only)

## API/Interface

```python
# New sub-command handler
def cmd_show(config: BRConfig, args: argparse.Namespace) -> int:
    """Display summary card for a single issue."""
    ...

# CLI argument
# ll-issues show <issue_id>
# issue_id: str — accepts "491", "ENH-491", or "P3-ENH-491"
```

## Proposed Solution

1. Add a new `show.py` module in `scripts/little_loops/cli/issues/` following the pattern of existing sub-commands (`list_cmd.py`, `sequence.py`).
2. Implement ID resolution logic (no existing generic resolver exists — `sprint.py:_find_issue_path()` only handles `TYPE-NNN` format):
   - Parse the input to extract numeric ID, optional type, optional priority
   - Glob across all active category dirs + completed dir using `*-{NNN}-*.md` pattern (similar to `sprint.py:307-324`)
   - If type/priority provided, use as additional filter after glob match
3. Parse the matched issue file:
   - Use `parse_frontmatter(content, coerce_types=True)` from `frontmatter.py:13` for `confidence_score`, `outcome_confidence`
   - Extract title via regex `^#\s+[\w-]+:\s*(.+)$` (same pattern as `issue_parser.py:358`)
   - Extract status from `## Status` section (not parsed by existing `IssueInfo` — custom parsing needed)
   - Extract priority/type from filename (same logic as `IssueParser._parse_priority()` at `issue_parser.py:268`)
   - Extract effort from frontmatter `effort` key
4. Format summary card using box-drawing characters (reuse pattern from `impact_effort.py:92-103` in `_render_grid()`).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — register `show` sub-command: add lazy import of `cmd_show`, add `subs.add_parser("show", ...)` with positional `issue_id` arg, add dispatch `if args.command == "show": return cmd_show(config, args)`, update epilog help text
- `scripts/little_loops/cli/issues/show.py` — new file: command implementation

### Dependent Files (Callers/Importers)
- `scripts/pyproject.toml` — no change needed (entry point `ll-issues = "little_loops.cli:main_issues"` at line 59 already covers all sub-commands)
- `scripts/little_loops/cli/__init__.py` — no change needed (`main_issues` already exported at line 20)

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py` — follow same module structure: `from __future__ import annotations`, TYPE_CHECKING import of BRConfig, `cmd_list(config, args) -> int` signature
- `scripts/little_loops/cli/issues/impact_effort.py:92-103` — box-drawing character definitions in `_render_grid()` to reuse for card border
- `scripts/little_loops/sprint.py:307-324` — `_find_issue_path()` pattern for globbing `*-{issue_id}-*.md` across category dirs

### Reusable Utilities
- `scripts/little_loops/frontmatter.py:13` — `parse_frontmatter(content, coerce_types=True)` for reading `confidence_score`, `outcome_confidence`
- `scripts/little_loops/issue_parser.py:358-378` — title extraction regex pattern `^#\s+[\w-]+:\s*(.+)$`
- `scripts/little_loops/issue_parser.py:268` — `_parse_priority()` pattern for extracting priority from filename
- `scripts/little_loops/issue_parser.py:294` — `_parse_type_and_id()` pattern for extracting TYPE-NNN from filename
- `scripts/little_loops/cli_args.py:34-41` — `add_config_arg()` for adding `--config` to sub-parser

### Tests
- `scripts/tests/test_issues_cli.py` — add `TestIssuesCLIShow` class following class-per-subcommand pattern
- `scripts/tests/conftest.py:55-157` — reuse `temp_project_dir`, `sample_config`, `issues_dir` fixtures

### Documentation
- `docs/reference/API.md` — add `show` sub-command reference

### Configuration
- N/A

## Implementation Steps

1. **Create `show.py` module** (`scripts/little_loops/cli/issues/show.py`):
   - Follow `list_cmd.py` structure: `from __future__ import annotations`, TYPE_CHECKING BRConfig import, `cmd_show(config: BRConfig, args: argparse.Namespace) -> int` signature
   - Implement `_resolve_issue_id(config, user_input)` — parse input into optional priority/type/numeric components, glob `*-{NNN}-*.md` across `config.issue_categories` dirs + `config.get_completed_dir()`, filter by type/priority if provided
   - Implement `_parse_card_fields(path)` — read file content, call `parse_frontmatter(content, coerce_types=True)` for `confidence_score`/`outcome_confidence`/`effort`, extract title via regex (pattern from `issue_parser.py:358`), extract status by matching `## Status` section, derive priority/type from filename
   - Implement `_render_card(fields)` — build `lines: list[str]` using box-drawing characters (pattern from `impact_effort.py:92-103`), return `"\n".join(lines)` and `print()` at call site
2. **Register sub-command** in `scripts/little_loops/cli/issues/__init__.py`:
   - Add `from little_loops.cli.issues.show import cmd_show` in lazy imports block (after line 20)
   - Add `show_p = subs.add_parser("show", help="Show summary card for an issue")` with `show_p.add_argument("issue_id", help="Issue ID (e.g., 518, FEAT-518, P3-FEAT-518)")` and `add_config_arg(show_p)`
   - Add `if args.command == "show": return cmd_show(config, args)` in dispatch chain
   - Update epilog string to include `show` sub-command description
3. **Add tests** in `scripts/tests/test_issues_cli.py`:
   - `TestIssuesCLIShow` class using `temp_project_dir`, `sample_config`, `issues_dir` fixtures
   - Test cases: numeric-only ID lookup, TYPE-NNN lookup, P-TYPE-NNN lookup, issue not found (returns 1 + error message), completed issue shows "Completed" status, missing frontmatter fields gracefully omitted
4. **Update docs** — add `show` to `docs/reference/API.md` ll-issues section

## Impact

- **Priority**: P3 - Quality-of-life improvement for issue workflow; not blocking anything
- **Effort**: Small - Single new sub-command following established patterns
- **Risk**: Low - Additive change, no modifications to existing commands
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md` | CLI module reference for ll-issues |
| `docs/ARCHITECTURE.md` | System design for CLI tools |

## Labels

`cli`, `feature`, `captured`

## Resolution

**Implemented** on 2026-03-01.

### Changes Made
- Created `scripts/little_loops/cli/issues/show.py` — new sub-command module with ID resolution, field parsing, and box-drawing card rendering
- Updated `scripts/little_loops/cli/issues/__init__.py` — registered `show` sub-command (import, parser, dispatch)
- Added 8 tests in `scripts/tests/test_issues_cli.py` — `TestIssuesCLIShow` class covering all acceptance criteria
- Updated `docs/reference/API.md` — added `main_issues` entry point docs with `show` sub-command reference

## Session Log
- `/ll:capture-issue` - 2026-03-01 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d737e1db-50ee-48ff-886b-222a160828e5.jsonl`
- `/ll:refine-issue` - 2026-03-01 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c22941ef-25a0-440c-bd48-be6906f3d122.jsonl`
- `/ll:manage-issue` - 2026-03-01 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffa88660-2b5b-4a83-a475-9f7a9def1102.jsonl`

---

## Status

**Completed** | Created: 2026-03-01 | Completed: 2026-03-01 | Priority: P3
