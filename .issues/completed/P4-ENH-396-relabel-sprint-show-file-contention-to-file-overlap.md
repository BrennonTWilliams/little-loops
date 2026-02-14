---
discovered_date: 2026-02-12
discovered_by: capture-issue
---

# ENH-396: Relabel sprint show "File contention" to "File overlap" with new glyph

## Summary

In `ll-sprint show` CLI output, the file contention annotation currently reads `⚠  File contention` with a warning triangle glyph. Relabel the text to "File overlap" and replace the `⚠` glyph with a symbol depicting two overlapping circles (e.g., Venn diagram style, filled at the intersection).

## Current Behavior

The `ll-sprint show` execution plan displays wave headers like:
```
Wave 1 (2 issues, serialized — file contention):
```

The term "contention" implies a conflict or problem requiring user action, while this is actually informational — it indicates files are shared between issues in the same wave and the system has already handled it by serializing into sub-waves.

## Expected Behavior

The output should read something like:
```
Wave 1 (2 issues, serialized — file overlap):
```

The term "file overlap" is more accurate and neutral than "file contention." No glyph change is needed — there is no warning glyph in the current output (the original issue description was inaccurate about a `⚠` glyph being present).

## Motivation

"File contention" with a warning symbol suggests a problem requiring user action. In reality, the sprint system already handles this by splitting into sub-waves — it's informational, not a warning. "File overlap" is more accurate terminology and a non-warning glyph better matches the informational nature.

## Proposed Solution

1. In `scripts/little_loops/cli/sprint.py`, anchor `_render_execution_plan()`, change the display string at line 303:
   ```python
   # Before:
   f"Wave {logical_num} ({group_count} issues, serialized \u2014 file contention):"
   # After:
   f"Wave {logical_num} ({group_count} issues, serialized \u2014 file overlap):"
   ```

2. Update comments in `sprint.py` that reference "file contention" (lines 387, 962) to say "file overlap".

3. Update test assertions in `scripts/tests/test_cli.py` that check for the string `"file contention"` (lines 1110, 1130, 1169) — change to `"file overlap"`.

4. Optionally update docstrings/log messages in `dependency_graph.py` (lines 22, 342, 422) for terminology consistency.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint.py` — line 303: display string in `_render_execution_plan()`
- `scripts/little_loops/cli/sprint.py` — lines 387, 962: comments referencing "file contention"

### Dependent Files (Callers/Importers)
- N/A — this is a display-only change

### Similar Patterns
- `scripts/little_loops/dependency_graph.py` — lines 22, 342, 422: docstrings and log messages reference "file contention" (update for consistency)

### Tests
- `scripts/tests/test_cli.py` — lines 1110, 1130, 1169: string assertions for "file contention"

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Update the display string in `sprint.py:303` from "file contention" to "file overlap"
2. Update comments referencing "file contention" in sprint.py (lines 387, 962)
3. Update test assertions in test_cli.py (lines 1110, 1130, 1169)
4. Optionally update docstrings/log messages in dependency_graph.py for terminology consistency

## Impact

- **Priority**: P4 - Cosmetic/terminology improvement, no functional change
- **Effort**: Small - String replacements in 2-3 files
- **Risk**: Low - Display-only change, no logic changes
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Relabeling the user-facing display text and glyph in `ll-sprint show` output
- **Out of scope**: Renaming internal Python identifiers (`refine_waves_for_contention`, `WaveContentionNote`, `contention_notes`) — these are internal API names and renaming them is a separate, larger refactor

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Sprint system design |

## Labels

`enhancement`, `captured`, `cli`, `cosmetic`

## Session Log
- `/ll:capture-issue` - 2026-02-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d505908-8129-431d-a9c6-108fc6753c82.jsonl`
- /ll:format-issue --all --auto - 2026-02-13

## Verification Notes

- **Verified**: 2026-02-14
- **Verdict**: CORRECTED
- **Previous verification (2026-02-13)**: Correctly identified glyph claim was inaccurate, but incorrectly stated test assertions were not found
- **Current state**: All file paths, line numbers, and code references verified against codebase
- **Display string**: `sprint.py:303` — `f"Wave {logical_num} ({group_count} issues, serialized — file contention):"`
- **Test assertions**: Found at test_cli.py lines 1110, 1130, 1169 (lowercase "file contention")
- **Additional references**: sprint.py lines 387, 962; dependency_graph.py lines 22, 342, 422

---

## Resolution

- **Resolved**: 2026-02-14
- **Action**: improve
- **Changes**:
  - `sprint.py:303`: Display string "file contention" → "file overlap"
  - `sprint.py:491`: Health summary "contention serialized" → "overlap serialized"
  - `sprint.py`: Updated 3 comments for terminology consistency
  - `dependency_graph.py`: Updated docstrings (lines 22, 342) and log message (line 422)
  - `test_cli.py`: Updated 4 test assertions and 1 comment
  - `test_dependency_graph.py`: Updated 1 test docstring
- **Internal identifiers preserved** (out of scope per issue): `refine_waves_for_contention`, `WaveContentionNote`, `contention_notes`

## Status

**Completed** | Created: 2026-02-12 | Resolved: 2026-02-14 | Priority: P4
