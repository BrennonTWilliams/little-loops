---
discovered_date: 2026-04-12
discovered_by: /ll:capture-issue
confidence_score: 100
outcome_confidence: 86
---

# ENH-1088: Add missing fields to ll-issues show output

## Summary

The `ll-issues show <ID>` card view is missing three fields that `ll-issues refine-status` displays as columns: `source` (discovered_by), `norm` (normalized filename check), and `fmt` (formatted/has all required sections check). Adding these makes the single-issue card consistent with the table view.

## Current Behavior

`ll-issues show` renders a card with: ID, title, priority, status, effort, risk, confidence scores, integration file count, labels, session history, and path. It does not show:
- **source**: which command/workflow originated the issue (frontmatter `discovered_by`)
- **norm**: whether the filename follows `P[0-5]-TYPE-NNN-desc.md` convention (`is_normalized`)
- **fmt**: whether the issue file has all required template sections (`is_formatted`)

## Expected Behavior

`ll-issues show` card includes `source`, `norm`, and `fmt` values, giving the same signal the table view provides. For example, the meta or detail line might read:

```
Source: capture  │  Norm: ✓  │  Fmt: ✗
```

## Motivation

When drilling into a specific issue, a user currently needs to cross-reference `refine-status` output to see its normalization/format state. Surfacing these in `show` eliminates that round-trip and keeps the two views consistent.

## Proposed Solution

1. In `_parse_card_fields` (`show.py`), extract `discovered_by` from frontmatter and call `is_normalized(path.name)` / `is_formatted(path)` from `little_loops.issue_parser`.
2. Add the three new keys (`"source"`, `"norm"`, `"fmt"`) to the returned dict.
3. In `_render_card`, add a new detail line (or extend the existing detail block) showing these values with the same display conventions used in `refine-status` (✓/✗ for norm/fmt, `_source_label` logic for source).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/show.py` — `_parse_card_fields` (add source/norm/fmt extraction) and `_render_card` (display new fields)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py` — exports `is_normalized`, `is_formatted` (already used by `refine_status.py`)
- `scripts/little_loops/cli/issues/refine_status.py` — reference for `_source_label` display logic and `is_normalized`/`is_formatted` usage

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py:29,429` — imports `cmd_show` and dispatches to it; no code change needed (dispatcher only)
- `scripts/little_loops/loops/recursive-refine.yaml:122,233` — subprocess calls `ll-issues show --json`; reads `confidence`/`outcome` fields only — new fields are additive, no update needed
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:134,166,219` — same JSON consumption pattern; reads `d.get('confidence')` and `d.get('outcome')` only — additive safe
- `skills/create-eval-from-issues/SKILL.md:24,60,64,66` — references `ll-issues show --json`; depends on `path` field only — additive safe

### Similar Patterns
- `refine_status.py:108` — `_source_label(discovered_by)` implementation
- `refine_status.py:388` — `_cell_value` — `is_normalized`/`is_formatted` checks, ✓/✗ display
- `refine_status.py:244` — import pattern: `from little_loops.issue_parser import find_issues, is_formatted, is_normalized`
- `show.py:270-279` — existing `detail_lines` accumulation pattern to follow for the new meta line
- `show.py:215-218` — `_ljust()` helper for ANSI-safe width padding (use for the new detail line)

### Tests
- `scripts/tests/test_issues_cli.py:906` — `TestIssuesCLIShow` class; add new tests here following the `test_show_with_frontmatter_scores` (line 1027) pattern
- Fixture pattern: create file inline with `"---\ndiscovered_by: /ll:capture-issue\n---\n# ENH-NNN: Title\n"` using a properly-normalized filename (e.g., `P3-ENH-400-source-test.md`) in an `enhancements/` subdirectory so `is_normalized()` returns `True`. Follow the `issues_dir_with_enh` fixture pattern at `test_issues_cli.py:60`.
- Need: `test_show_with_source_norm_fmt` — assert `Source: capture` / `Norm: ✓` / `Fmt: ✗` appear
- Need: `test_show_json_includes_source_norm_fmt` — assert `"source"`, `"norm"`, `"fmt"` keys present in JSON dict
- Update: `test_show_new_fields_absent_gracefully` (line 1348) — add `assert "Source:" not in captured.out`

### Documentation
- `docs/reference/CLI.md:426` — `ll-issues show` entry; update to mention source/norm/fmt fields
- `docs/reference/OUTPUT_STYLING.md:88` — Issue Card section; update to reflect new detail line
- `docs/reference/API.md:2943` — show sub-command docs; update field list

### Configuration
- None required

## Implementation Steps

1. **Add `_source_label` helper to `show.py`** — do NOT import from `refine_status.py` (private function, sibling module coupling). Inline the logic (< 10 lines) with the same `_CMD_ALIASES` dict restricted to the four source commands:
   ```python
   _SHOW_CMD_ALIASES = {"/ll:capture-issue": "capture", "/ll:scan-codebase": "scan",
                        "/ll:audit-architecture": "audit", "/ll:format-issue": "format"}
   def _source_label(discovered_by: str | None) -> str:
       if not discovered_by:
           return "\u2014"
       return _SHOW_CMD_ALIASES.get(discovered_by, discovered_by[:7])
   ```

2. **Extend `_parse_card_fields`** (`show.py:191-205`) — after the existing frontmatter reads at line 132, add:
   ```python
   from little_loops.issue_parser import is_formatted, is_normalized
   discovered_by = frontmatter.get("discovered_by")
   source = _source_label(discovered_by)
   norm = "\u2713" if is_normalized(path.name) else "\u2717"
   fmt = "\u2713" if is_formatted(path) else "\u2717"
   ```
   Add `"source": source`, `"norm": norm`, `"fmt": fmt` to the return dict.

3. **Extend `_render_card`** (`show.py:269-279`) — add a new detail line in the `detail_lines` block following the existing pattern. Place it as the first detail line for visual prominence:
   ```python
   source_parts: list[str] = []
   if fields.get("source"):
       source_parts.append(f"Source: {fields['source']}")
   if fields.get("norm"):
       source_parts.append(f"Norm: {fields['norm']}")
   if fields.get("fmt"):
       source_parts.append(f"Fmt: {fields['fmt']}")
   if source_parts:
       detail_lines.append("  \u2502  ".join(source_parts))
   ```
   **Width note**: `detail_lines` is already included in `structural_lines.extend(detail_lines)` at `show.py:288` — the card width will expand correctly.
   **ANSI safety note**: if coloring ✓/✗, use `_ljust()` (the ANSI-safe helper at `show.py:215`) for the rendered line instead of the plain `f"{dl:<{width - 1}}"` format used for other detail lines at `show.py:352`. Simpler option: skip color in the card (color only appears in refine-status table, not card).

4. **`--json` output** — no change needed; `cmd_show` at `show.py:379` calls `print_json(fields)` directly, so the three new keys appear automatically.

5. **Tests** — add to `TestIssuesCLIShow` in `scripts/tests/test_issues_cli.py:906`:
   - `test_show_with_source_norm_fmt` — create a file with `discovered_by: /ll:capture-issue` in frontmatter (properly named `P3-ENH-NNN-*.md` for norm=✓), assert `"Source: capture"` in output
   - `test_show_json_includes_source_norm_fmt` — assert `"source"`, `"norm"`, `"fmt"` present in JSON dict
   - Update `test_show_new_fields_absent_gracefully` (line 1348) — add `assert "Source:" not in captured.out`; note that `Norm:` and `Fmt:` **will** appear even for the minimal fixture (no frontmatter) because `is_normalized("P1-BUG-300-minimal.md")` returns `True` and `is_formatted` returns `False` — so `Norm: ✓  │  Fmt: ✗` will be in the output. Only `Source:` tests the "gracefully absent" path. The test update should assert `"Source:" not in captured.out` but NOT assert `"Norm:" not in captured.out`.

6. **Documentation updates** — `docs/reference/CLI.md:426`, `docs/reference/OUTPUT_STYLING.md:88`, `docs/reference/API.md:2943`.

## Impact

- **Priority**: P3 - consistency improvement, no urgency
- **Effort**: Small - all data is already available; just wiring and display
- **Risk**: Low - read-only display change; no data written
- **Breaking Change**: No

## Labels

`cli`, `ll-issues`, `show`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-04-13T01:10:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3eb5963e-38bb-46a0-86b5-f4effd434cb7.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8ff2181d-6ede-47a8-9549-e752a280945a.jsonl`
- `/ll:wire-issue` - 2026-04-13T01:00:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/90984138-30d2-411d-a35b-e7b980602eb0.jsonl`
- `/ll:refine-issue` - 2026-04-13T00:54:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f0b40f01-0f45-4840-a5cb-6aa6c3c11276.jsonl`
- `/ll:capture-issue` - 2026-04-12T19:44:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5dd91ad2-03f5-4e33-9759-d4e7dc16b21f.jsonl`

---

## Resolution

**Status**: Completed | **Resolved**: 2026-04-12

### Changes Made
- `scripts/little_loops/cli/issues/show.py`: Added `_SHOW_CMD_ALIASES` dict and `_source_label()` helper; extended `_parse_card_fields()` to extract `source`, `norm`, `fmt`; updated `_render_card()` to display `Source: <label>  │  Norm: ✓/✗  │  Fmt: ✓/✗` as first detail line
- `scripts/tests/test_issues_cli.py`: Added `test_show_with_source_norm_fmt`, `test_show_json_includes_source_norm_fmt`; updated `test_show_new_fields_absent_gracefully`
- `docs/reference/CLI.md`, `docs/reference/OUTPUT_STYLING.md`, `docs/reference/API.md`: Updated show documentation

### Verification
- All 94 `test_issues_cli.py` tests pass

## Status
**Completed** | Created: 2026-04-12 | Priority: P3
