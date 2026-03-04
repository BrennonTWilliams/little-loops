---
discovered_date: 2026-03-03
discovered_by: capture-issue
---

# ENH-560: ll-issues refine-status add normalized column

## Summary

Update `ll-issues refine-status` output to include a `normalized` column, reusing the same normalization check logic from `/ll:normalize-issues` to indicate whether each issue filename conforms to naming conventions.

## Current Behavior

`ll-issues refine-status` renders a table with columns for ID, Priority, Title, per-command session log indicators, Ready score, OutConf score, and Total count. There is no column indicating whether each issue's filename conforms to naming conventions (`^P[0-5]-(BUG|FEAT|ENH)-[0-9]{3,}-[a-z0-9-]+\.md$`). Users must separately run `/ll:normalize-issues` to discover filename violations.

## Expected Behavior

`ll-issues refine-status` includes a `Norm` column (width 4) that shows `✓` for filenames matching the naming convention and `✗` for filenames that do not. The JSON output (`--format json`) includes a `"normalized": true/false` boolean field per record.

## Motivation

The `refine-status` command gives a useful at-a-glance view of issue readiness, but it currently doesn't surface whether filenames are properly normalized. Users must separately run `/ll:normalize-issues` to discover naming issues. Combining both checks in one view saves a step and makes the status output more complete.

## Acceptance Criteria

- [x] `ll-issues refine-status` table includes a `normalized` column
- [x] Column shows a pass/fail indicator (e.g., `✓` / `✗` or `yes` / `no`) for each issue
- [x] Normalization check reuses the same logic/function used by `ll-issues normalize` (no duplication)
- [x] Output remains readable (column fits within typical terminal width or wraps gracefully)
- [x] Existing tests for `refine-status` are updated to cover the new column

## Impact

- **Priority**: P3 - Low-friction improvement; surfaces existing normalization data inline without requiring a separate command
- **Effort**: Small - reuses `is_normalized()` extracted from existing normalize logic; purely additive display change
- **Risk**: Low - additive column in table output; no behavioral change to existing columns; JSON field addition is non-breaking
- **Breaking Change**: No

## Scope Boundaries

- Does **not** auto-rename non-conformant files (that remains `/ll:normalize-issues` responsibility)
- Does **not** change the normalization regex or validation logic — must match `commands/normalize-issues.md` exactly
- Does **not** affect any other `ll-issues` sub-commands (sequence, show, impact-effort, etc.)
- Does **not** add filtering by normalization status (future enhancement if needed)

## Labels

`enhancement`, `cli`, `ll-issues`, `captured`

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — add `_NORMALIZED_RE` module-level regex and public `is_normalized(filename: str) -> bool` helper (alongside existing `slugify()` at ~line 28); this is the canonical shared location so other commands can reuse it
- `scripts/little_loops/cli/issues/refine_status.py` — add `_NORM_WIDTH` constant (line ~22), add it to the `fixed_width` calculation (line ~101), add `normalized` parameter to `_row()` signature and body (line ~111), compute `norm_cell` per-issue in the render loop (line ~139), add `normalized` key to the JSON output dict (line ~82)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py:114` — dispatches to `cmd_refine_status()`; no changes needed
- `commands/normalize-issues.md:351-358` — **source of truth** for the validation regex `^P[0-5]-(BUG|FEAT|ENH)-[0-9]{3,}-[a-z0-9-]+\.md$`; the Python implementation must match this exactly

### Normalization Regex (canonical source)
From `commands/normalize-issues.md:351`:
```
^P[0-5]-(BUG|FEAT|ENH)-[0-9]{3,}-[a-z0-9-]+\.md$
```

### Tests
- `scripts/tests/test_refine_status.py` — update `_make_issue()` to accept non-normalized filenames if needed; add test for `normalized` column header in table, `✓` for conformant filenames, `✗` for non-conformant filenames; add `normalized` field to JSON output test

### Indicator Style
Use `✓` (`\u2713`) for normalized, `✗` (`\u2717`) for non-normalized — distinct from the `✓`/`—` pair used for command-presence columns, making it clear that `✗` signals an actionable problem.

### Documentation
- `docs/reference/CLI.md` — documents `ll-issues refine-status`; update to mention the `normalized` column

## Implementation Steps

1. **Add `is_normalized()` to `issue_parser.py`** — add `_NORMALIZED_RE = re.compile(r'^P[0-5]-(BUG|FEAT|ENH)-[0-9]{3,}-[a-z0-9-]+\.md$')` at module level (alongside `slugify()`, ~line 28), then add `def is_normalized(filename: str) -> bool: return bool(_NORMALIZED_RE.match(filename))`

2. **Add column constant in `refine_status.py`** — add `_NORM_WIDTH = 4` (fits `✓`/`✗` with label "Norm") after the existing `_CMD_WIDTH` constant at line ~22; include it in the `fixed_width` sum (line ~101)

3. **Update `_row()` signature** — add `norm: str` parameter and a matching `_col(norm, _NORM_WIDTH)` entry in the parts list (after the dynamic command cells, before "Ready"), update `header = _row(...)` call with label `"Norm"`

4. **Compute `norm_cell` per-issue** — in the render loop (line ~139), add:
   ```python
   from little_loops.issue_parser import is_normalized
   norm_cell = "\u2713" if is_normalized(issue.path.name) else "\u2717"
   ```
   then pass `norm_cell` to `_row()`

5. **Add `normalized` to JSON output** — in the JSON branch (line ~82), add `"normalized": is_normalized(issue.path.name)` (boolean) to the record dict

6. **Update tests** — in `test_refine_status.py`: assert `"Norm"` appears in header; assert `✓` for a normally-named file (e.g., `P2-BUG-010-refined.md`); create a file with a non-conformant name (e.g., `invalid-filename.md`) and assert `✗`; assert `"normalized": true/false` in JSON output

## Related Key Documentation

- `scripts/little_loops/issue_parser.py` — add `is_normalized()` here (alongside `slugify()`)
- `scripts/little_loops/cli/issues/refine_status.py` — primary implementation target
- `scripts/tests/test_refine_status.py` — test patterns to follow (`_make_issue()` helper, `TestRefineStatusTable`, `TestRefineStatusJson`)
- `commands/normalize-issues.md:347-358` — canonical validation regex used by `/ll:normalize-issues`
- `docs/reference/CLI.md` — documents `ll-issues refine-status`; needs update

## Status

Completed

## Resolution

Implemented in full. Added `is_normalized()` helper to `issue_parser.py` with the canonical regex. Added `Norm` column (`_NORM_WIDTH = 4`) to `refine_status.py` table and `"normalized": bool` to JSON output. Updated tests (4 new test cases). Updated `docs/reference/CLI.md`.

---

## Session Log
- `/ll:capture-issue` - 2026-03-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ff92e7ec-af7a-4ae5-9414-273a2df86684.jsonl`
- `/ll:refine-issue` - 2026-03-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aa91a0eb-a632-4986-985f-bcd42f683157.jsonl`
- `/ll:manage-issue` - 2026-03-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
