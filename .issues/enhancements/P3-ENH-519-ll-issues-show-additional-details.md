---
discovered_date: "2026-03-01"
discovered_by: capture-issue
---

# ENH-519: Enhance `ll-issues show` with additional detail fields

## Summary

Enhance the `ll-issues show [ISSUE-ID]` summary card to display richer information extracted from the issue file: summary text, integration map file count, effort/risk levels from the Impact section, labels, and session log commands with run counts. Also change the Path field to show a relative path instead of absolute.

## Current Behavior

The `ll-issues show` card currently displays only: title, priority, status, effort (from frontmatter), confidence/outcome scores, and the full absolute file path.

## Expected Behavior

The summary card should display these additional fields when present in the issue:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ FEAT-518: Add `ll-issues show` command for summary cards                 │
├──────────────────────────────────────────────────────────────────────────┤
│ Priority: P3  │  Status: Open  │  Effort: Small  │  Risk: Low           │
│ Confidence: 85  │  Outcome: 78                                          │
├──────────────────────────────────────────────────────────────────────────┤
│ Summary: Add a new sub-command that displays a compact summary card...   │
│ Integration: 5 files  │  Labels: cli, feature                           │
│ History: /ll:capture-issue, /ll:refine-issue (3), /ll:manage-issue      │
├──────────────────────────────────────────────────────────────────────────┤
│ Path: .issues/features/P3-FEAT-518-ll-issues-show-summary-card.md       │
└──────────────────────────────────────────────────────────────────────────┘
```

Specifically:
- **Summary**: First sentence or first 80 characters from the `## Summary` section
- **Integration map file count**: Count of files listed under `## Integration Map` > `### Files to Modify`
- **Effort level**: From `## Impact` section (e.g., "Small", "Medium", "Large")
- **Risk level**: From `## Impact` section (e.g., "Low", "Medium", "High")
- **Labels**: From `## Labels` section
- **Session log commands**: Unique command/skill names from `## Session Log`, with count if run more than once (e.g., `/ll:refine-issue (3)`)
- **Path**: Show relative path from project root instead of absolute path

## Motivation

The current card is useful for a quick glance but lacks context that would help users decide whether to work on an issue without opening the file. Adding summary text, integration complexity (file count), risk assessment, and workflow history makes the card a more complete decision-support tool.

## Acceptance Criteria

- [ ] Summary line shows first sentence (or truncated to ~80 chars with `...`) from `## Summary` section
- [ ] Integration file count parsed from `## Integration Map` > `### Files to Modify` section
- [ ] Effort and Risk levels parsed from `## Impact` section bullet points
- [ ] Labels parsed from `## Labels` section
- [ ] Session log shows unique command names with counts for duplicates
- [ ] Path displays relative to project root (e.g., `.issues/features/...` not `/Users/.../...`)
- [ ] All new fields are gracefully omitted when not present in the issue file
- [ ] Existing tests still pass
- [ ] New tests cover each additional field

## API/Interface

```python
# Updated _parse_card_fields() in scripts/little_loops/cli/issues/show.py
# Returns additional keys:
#   "summary": str | None
#   "integration_files": int | None
#   "risk": str | None
#   "labels": str | None
#   "history": str | None
# Updated "path" to use relative path
```

## Scope Boundaries

- **In scope**: Parsing and displaying new fields (summary, integration file count, risk, labels, session log history, relative path) in the existing `show` card layout; color/formatting improvements if simple to add
- **Out of scope**:
  - New sub-commands or CLI flags beyond existing `show [ISSUE-ID]`
  - New interactive features (e.g., drill-down, navigation)
  - User-configurable field visibility (no config options for which fields to show)
  - Major refactoring of `_render_card()` layout engine

## Proposed Solution

Extend `_parse_card_fields()` in `scripts/little_loops/cli/issues/show.py:82` to extract additional fields from the issue markdown content:

```python
# In _parse_card_fields(), after existing frontmatter extraction (show.py:94):

# 1. Summary: first sentence from ## Summary section
summary_match = re.search(r"^## Summary\n+(.+?)(?:\n|$)", content, re.MULTILINE)
summary_text = summary_match.group(1).strip()[:80] if summary_match else None

# 2. Integration file count: count items under ### Files to Modify only
# Use section-boundary technique from issue_parser.py:380-416
ftm_match = re.search(r"^### Files to Modify\s*$", content, re.MULTILINE)
if ftm_match:
    start = ftm_match.end()
    next_header = re.search(r"^#{2,3}\s+", content[start:], re.MULTILINE)
    section = content[start:start + next_header.start()] if next_header else content[start:]
    integration_files = len(re.findall(r"^- .+", section, re.MULTILINE))

# 3. Risk: extract from ## Impact bullet — follows **Bold**: Value pattern
# from issue_history/parsing.py:122-143
risk_match = re.search(r"\*\*Risk\*\*:\s*(Low|Medium|High)", content, re.IGNORECASE)

# 4. Labels: extract backtick-delimited labels from ## Labels section
# Labels section uses format: `label1`, `label2` on a single line
labels_match = re.search(r"^## Labels\s*\n+(.*?)(?:\n\n|\n##|\Z)", content, re.MULTILINE | re.DOTALL)
if labels_match:
    labels = ", ".join(re.findall(r"`([^`]+)`", labels_match.group(1)))

# 5. Session log: parse ## Session Log for unique /ll:* commands with counts
# Uses COMMAND_PATTERN from workflow_sequence_analyzer.py:52
# Session log entry format (session_log.py:62): "- `/ll:cmd` - ts - `path`"
import re as _re
from collections import Counter
log_match = re.search(r"^## Session Log\s*\n+(.*?)(?:\n##|\n---|\Z)", content, re.MULTILINE | re.DOTALL)
if log_match:
    cmds = re.findall(r"`(/[\w:-]+)`", log_match.group(1))
    counts = Counter(cmds)
    parts = [f"{cmd} ({n})" if n > 1 else cmd for cmd, n in counts.items()]
    history = ", ".join(parts)

# 6. Relative path: inline Path.relative_to() with ValueError fallback
# Follows pattern from issue_manager.py:44-62 but kept inline
try:
    rel_path = str(path.relative_to(config.project_root))
except ValueError:
    rel_path = str(path)
```

Update `_render_card()` at `show.py:138` to add a new bordered content section between the scores line and the path line, rendering: summary (truncated with `...`), integration file count + labels on one row, and history commands on another row. All fields gracefully omitted when `None`. Use the existing `"  │  ".join(parts)` pattern (show.py:169) for multi-value lines.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`_parse_card_fields()` signature**: `show.py:82` — returns `dict[str, str | None]`; new fields should follow the same `str(value) if value is not None else None` coercion pattern used at `show.py:131-133`
- **`_render_card()` structure**: `show.py:138-204` — 3 sections separated by `├─┤` mid-borders; width auto-sized from `max(len(line) for line in content_lines) + 2` at `show.py:186`; new detail section adds a 4th section
- **Relative path needs `config` parameter**: `_parse_card_fields(path)` currently takes only `path`; must add `config: BRConfig` parameter (or `project_root: Path`) to compute relative path via `path.relative_to(config.project_root)` — `config.project_root` is set at `config.py:508`
- **`parse_frontmatter` already imported**: lazy import at `show.py:91` — no new imports needed for frontmatter; `re` already imported at `show.py:6`; `collections.Counter` is the only new import needed
- **`cmd_show` call site**: `__init__.py:93-94` calls `cmd_show(config, args)` — `config` is already available, so passing it through to `_parse_card_fields` is straightforward

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/show.py:82` — `_parse_card_fields()`: add 6 new regex parsers; add `config` parameter for relative path
- `scripts/little_loops/cli/issues/show.py:138` — `_render_card()`: add new detail section (summary, integration+labels, history) between scores and path
- `scripts/little_loops/cli/issues/show.py:207` — `cmd_show()`: pass `config` to `_parse_card_fields(path, config)` (currently only passes `path`)
- `scripts/tests/test_issues_cli.py:460` — `TestIssuesCLIShow`: add tests for each new field (present and absent cases)
- `docs/reference/API.md:2259` — update `ll-issues show` docs to list new displayed fields

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py:93` — calls `cmd_show(config, args)` (no changes needed; `config` already available)

### Similar Patterns
- `scripts/little_loops/issue_parser.py:380-416` — `_parse_section_items()` section-boundary extraction pattern
- `scripts/little_loops/issue_history/parsing.py:122-143` — `**Bold**: Value` regex extraction for `**Risk**`, `**Effort**`
- `scripts/little_loops/session_log.py:62` — session log entry format: `- \`/ll:cmd\` - ts - \`path\``
- `scripts/little_loops/workflow_sequence_analyzer.py:52` — `COMMAND_PATTERN = re.compile(r"/[\w:-]+")`
- `scripts/little_loops/issue_manager.py:44-62` — `_compute_relative_path()` with `Path.relative_to()` + `ValueError` fallback (pattern to follow inline)

### Tests
- `scripts/tests/test_issues_cli.py:460` — `TestIssuesCLIShow` class (8 existing tests); add tests for each new field
- `scripts/tests/conftest.py:125` — `issues_dir` fixture creates 5 sample issues (none have `## Impact`, `## Labels`, `## Integration Map`, or `## Session Log` sections — new test fixtures needed)
- Test pattern: use `patch.object(sys, "argv", [...])` + `capsys.readouterr()` + write custom issue files with target sections

### Documentation
- `docs/reference/API.md:2256-2267` — update `ll-issues show` section; currently says "Displays title, priority, status, effort, confidence scores, and file path" — needs to list all new fields

### Configuration
- N/A

## Implementation Steps

1. **Modify `_parse_card_fields()` signature** (`show.py:82`): Add `config: BRConfig` parameter. Update call site at `show.py:224` to pass `config`.

2. **Add 6 new parsers to `_parse_card_fields()`** (after existing frontmatter extraction at `show.py:94`):
   - Summary: `re.search(r"^## Summary\n+(.+?)(?:\n|$)", content, re.MULTILINE)` → truncate to 80 chars with `...`
   - Integration files: find `### Files to Modify` header, extract section until next `###`/`##`, count `^- ` lines
   - Risk: `re.search(r"\*\*Risk\*\*:\s*(Low|Medium|High)", content, re.IGNORECASE)` — follows `issue_history/parsing.py:122` pattern
   - Labels: find `## Labels` section, `re.findall(r"\`([^\`]+)\`", section_text)`, join with `, `
   - History: find `## Session Log` section, extract `/ll:*` commands with `re.findall(r"\`(/[\w:-]+)\`", ...)`, use `Counter` for dedup with counts
   - Relative path: `path.relative_to(config.project_root)` wrapped in try/except `ValueError`

3. **Update `_render_card()` layout** (`show.py:138`): Add a new bordered section between scores and path containing:
   - Line 1: `Summary: {text}...` (only if summary present)
   - Line 2: `Integration: {n} files  │  Labels: {labels}` (join non-None parts with `"  │  "`)
   - Line 3: `History: {cmd1}, {cmd2} (3), {cmd3}` (only if history present)
   - Add `mid_border` before this section (between scores/metadata and detail)
   - Include new lines in `content_lines` for width calculation at `show.py:186`

4. **Add unit tests** in `scripts/tests/test_issues_cli.py` within `TestIssuesCLIShow`:
   - `test_show_with_summary` — issue with `## Summary` section → assert `Summary:` in output
   - `test_show_with_integration_files` — issue with `## Integration Map` > `### Files to Modify` → assert `Integration: N files` in output
   - `test_show_with_risk` — issue with `## Impact` containing `**Risk**: Low` → assert `Risk: Low` in output
   - `test_show_with_labels` — issue with `## Labels` containing backtick labels → assert `Labels:` in output
   - `test_show_with_session_log` — issue with `## Session Log` entries → assert `History:` in output with deduped counts
   - `test_show_relative_path` — assert path starts with `.issues/` not `/Users/`
   - `test_show_new_fields_absent_gracefully` — issue without any new sections → assert none of the new field labels appear

5. **Run existing tests**: `python -m pytest scripts/tests/test_issues_cli.py -v` to confirm no regressions

6. **Update docs**: Edit `docs/reference/API.md:2267` to list all displayed fields including new ones

## Success Metrics

- All 7 new fields (summary, integration files, risk, labels, history, relative path, effort from Impact) render correctly when present in issue files
- Fields gracefully omit when not present — no errors, no blank lines
- Card remains readable and well-aligned for issues with any combination of fields
- Existing `TestIssuesCLIShow` tests continue to pass without modification

## Impact

- **Priority**: P3 - Quality-of-life improvement
- **Effort**: Small - Parsing additional markdown sections from existing files
- **Risk**: Low - Additive change to existing show command, no behavior change for missing fields
- **Breaking Change**: Path field changes from absolute to relative (minor output change)

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md` | CLI module reference for ll-issues |

## Labels

`cli`, `enhancement`

## Session Log
- `/ll:manage-issue` - 2026-03-01T22:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fc141004-5976-469b-bfe9-9ae45b94033a.jsonl`
- `/ll:capture-issue` - 2026-03-01 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffa88660-2b5b-4a83-a475-9f7a9def1102.jsonl`
- `/ll:format-issue` - 2026-03-01 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4dc2e0a7-02fe-4b8c-8950-4019a0ba41aa.jsonl`
- `/ll:refine-issue` - 2026-03-01T22:48:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bbc30a90-7d39-419b-8360-08a1832adc65.jsonl`

## Resolution

- **Status**: Completed
- **Action**: implement
- **Date**: 2026-03-01

### Changes Made
- Extended `_parse_card_fields()` with `config` parameter and 6 new field parsers (summary, integration files, risk, labels, history, relative path)
- Updated `_render_card()` with new detail section between scores and path; risk added to metadata line
- Updated `cmd_show()` to pass `config` through
- Added 8 new tests covering all new fields plus truncation and graceful absence
- Updated API docs

---

## Status

**Completed** | Created: 2026-03-01 | Completed: 2026-03-01 | Priority: P3
