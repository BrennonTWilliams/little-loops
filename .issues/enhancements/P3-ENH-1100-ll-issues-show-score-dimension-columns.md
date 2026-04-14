---
discovered_date: 2026-04-13
discovered_by: capture-issue
---

# ENH-1100: ll-issues show add score dimension columns

## Summary

`ll-issues show` displays `Confidence` and `Outcome` scores on the summary card but does not expose the four Outcome Confidence dimension scores (`score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface`) that `ll-issues refine-status` shows as `cmplx`, `tcov`, `ambig`, `chsrf` columns. This enhancement adds those four values to the `show` card so the full scoring breakdown is visible without switching to the table view.

## Motivation

After `/ll:confidence-check` runs on an issue, the summary card shows `Confidence: 85  │  Outcome: 72` but hides which dimension dragged the aggregate down. The refine-status table already exposes all four per-criterion scores; `show` should mirror that visibility for the single-issue workflow. Having the breakdown on the card lets an engineer decide whether to re-refine (e.g. reduce change surface) without opening the issue file.

## Current Behavior

`ll-issues show BUG-1095` renders a summary card with `Confidence: 100  │  Outcome: 93` when those frontmatter fields are present. The four dimension fields (`score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface`) are parsed from frontmatter by `refine-status` but are ignored entirely by `show`.

## Expected Behavior

When dimension scores are present in frontmatter, the card gains a second scores line:

```
┌─────────────────────────────────────────────────────┐
│ BUG-1095: auto-refine-and-implement exits immediately│
├─────────────────────────────────────────────────────┤
│ Priority: P2  │  Status: Open                        │
│ Confidence: 100  │  Outcome: 93                      │
│ Cmplx: 22  │  Tcov: 24  │  Ambig: 25  │  Chsrf: 22  │
├─────────────────────────────────────────────────────┤
│ ...                                                  │
```

When no dimension scores are present (issue not yet confidence-checked), the second line is omitted — backward-compatible.

The `--json` output gains four new fields: `score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface` (integer or `null`).

## Proposed Solution

All changes are isolated to `scripts/little_loops/cli/issues/show.py`.

**`_parse_card_fields()`** (line 147–150 region):

Add four new frontmatter reads after the existing `confidence`/`outcome` reads:

```python
score_complexity = frontmatter.get("score_complexity")
score_test_coverage = frontmatter.get("score_test_coverage")
score_ambiguity = frontmatter.get("score_ambiguity")
score_change_surface = frontmatter.get("score_change_surface")
```

Add them to the returned dict (alongside `"confidence"` / `"outcome"`):

```python
"score_complexity": str(score_complexity) if score_complexity is not None else None,
"score_test_coverage": str(score_test_coverage) if score_test_coverage is not None else None,
"score_ambiguity": str(score_ambiguity) if score_ambiguity is not None else None,
"score_change_surface": str(score_change_surface) if score_change_surface is not None else None,
```

**`_render_card()`** (line 286–293 region):

After building `scores_line`, build a second `dim_scores_line`:

```python
dim_parts: list[str] = []
if fields.get("score_complexity"):
    dim_parts.append(f"Cmplx: {fields['score_complexity']}")
if fields.get("score_test_coverage"):
    dim_parts.append(f"Tcov: {fields['score_test_coverage']}")
if fields.get("score_ambiguity"):
    dim_parts.append(f"Ambig: {fields['score_ambiguity']}")
if fields.get("score_change_surface"):
    dim_parts.append(f"Chsrf: {fields['score_change_surface']}")
dim_scores_line = "  \u2502  ".join(dim_parts) if dim_parts else None
```

Add `dim_scores_line` to `structural_lines` for width calculation (when not None), and render it in the card body directly after the existing `scores_line` row, following the same `f"{v} {dim_scores_line:<{width - 1}}{v}"` pattern.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/show.py` — `_parse_card_fields()` + `_render_card()` + `cmd_show()` JSON path

### Similar Patterns
- `scripts/little_loops/cli/issues/show.py:147–148` — existing `confidence_score` / `outcome_confidence` reads (exact template)
- `scripts/little_loops/cli/issues/show.py:287–293` — existing `scores_line` build (exact template for `dim_scores_line`)
- `scripts/little_loops/cli/issues/refine_status.py:453–465` — `_cell_value` for the same four fields (shows the frontmatter key names)

### Tests
- `scripts/tests/test_issues_cli.py:TestIssuesCLIShow` — add three tests following the pattern of `test_show_with_frontmatter_scores` (line 1172): (1) `test_show_dim_scores_present` — issue with all four dimension fields in frontmatter → card contains "Cmplx:", "Tcov:", "Ambig:", "Chsrf:"; (2) `test_show_dim_scores_absent` — issue without dimension fields → card does not contain "Cmplx:" (backward-compat); (3) `test_show_json_includes_dim_scores` — `--json` output dict contains all four keys with correct values

  **Note**: There is NO `test_show.py` — all show tests live in `test_issues_cli.py`.

### Related
- `scripts/little_loops/cli/issues/refine_status.py` — already reads and renders these same four fields; serves as the reference implementation
- ENH-1099 — adds the four dimension fields to `refine-status` (and writes them from `confidence-check`); ENH-1100 depends on ENH-1099 having been implemented so the frontmatter fields exist

## Implementation Steps

1. In `_parse_card_fields()` (after line 148), add four `frontmatter.get(...)` reads for the four dimension keys.
2. Add the four keys to the `return` dict (after `"outcome"` entry) as `str(x) if x is not None else None`.
3. In `_render_card()` (after `scores_line` is built at line 293), build `dim_scores_line` from `fields` using the four new keys.
4. Add `dim_scores_line` to `structural_lines` (line 323–326 region, for width calculation) when it is not None.
5. In the card-body rendering block (after line 382 `if scores_line:` block), add `if dim_scores_line: lines.append(f"{v} {dim_scores_line:<{width - 1}}{v}")`.
6. In `cmd_show()` JSON branch (line 417), the `fields` dict returned by `_parse_card_fields` already contains the four new keys — no additional change needed; verify the JSON output includes them.
7. Add three tests to `scripts/tests/test_issues_cli.py` in `TestIssuesCLIShow` (after the existing `test_show_with_frontmatter_scores` test at line 1172), following the same fixture + `write_text` pattern.
8. Run `python -m pytest scripts/tests/test_issues_cli.py::TestIssuesCLIShow -v` to confirm.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Precise line anchors in `show.py`:**
- `confidence`/`outcome` reads: lines 147–148 (confirmed)
- `scores_line` build: lines 287–293 (confirmed)
- `structural_lines` build: line 323, guarded append at 324–326
- Existing `if scores_line:` card render: line 381–382

**Test file correction:** All `show` command tests are in `scripts/tests/test_issues_cli.py:TestIssuesCLIShow` (line 1051). There is no `test_show.py`. The test pattern to follow is `test_show_with_frontmatter_scores` (line 1172–1199) which:
  1. Creates an issue file with frontmatter via `write_text(...)`
  2. Invokes `main_issues()` via `patch.object(sys, "argv", [...])`
  3. Asserts on `capsys.readouterr().out`

**JSON path:** `cmd_show()` calls `print_json(fields)` at line 418 — the `fields` dict flows unchanged from `_parse_card_fields()`, so the four new keys appear automatically with no further changes.

**`IssueInfo` model:** The four dimension fields already exist in `little_loops/issue_parser.py:241–244` and are parsed from frontmatter at lines 373–435. The `show.py` change reads them independently via `frontmatter.get(...)` (same approach as `confidence_score` / `outcome_confidence`).

## Impact

- **Priority**: P3
- **Effort**: Minimal — ~25 lines across one file + tests
- **Risk**: Low — additive only; issues without dimension scores are unchanged
- **Breaking Change**: No — new dict keys in JSON output are additive

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/cli/issues/show.py` | File under change; existing `confidence`/`outcome` pattern to follow |
| `scripts/little_loops/cli/issues/refine_status.py` | Reference for the four frontmatter key names and display labels |

## Labels

`enhancement`, `ll-issues`, `show`, `confidence-check`, `cli`

## Session Log
- `/ll:refine-issue` - 2026-04-14T03:59:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d9e8886a-31c2-46ba-b5b1-6b68e4055cce.jsonl`
- `/ll:capture-issue` - 2026-04-13T21:24:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43909014-7cf5-4dcd-8cb6-2b74700e6f59.jsonl`

---

**Open** | Created: 2026-04-13 | Priority: P3
