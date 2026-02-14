---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-396: Relabel sprint show "File contention" to "File overlap" with new glyph

## Summary

In `ll-sprint show` CLI output, the file contention annotation currently reads `⚠  File contention` with a warning triangle glyph. Relabel the text to "File overlap" and replace the `⚠` glyph with a symbol depicting two overlapping circles (e.g., Venn diagram style, filled at the intersection).

## Current Behavior

The `ll-sprint show` execution plan displays:
```
  ⚠  File contention — sub-wave 1/2
```

The warning triangle (`⚠` / `\u26a0`) implies something is wrong, while this is actually informational — it indicates files are shared between issues in the same wave.

## Expected Behavior

The output should read something like:
```
  ◎  File overlap — sub-wave 1/2
```

Using a glyph that visually conveys "overlap" rather than "warning." Candidate Unicode glyphs to evaluate:
- `◎` (U+25CE) — bullseye / double circle
- `⊚` (U+229A) — circled ring operator
- `⧉` (U+29C9) — two joined squares
- `⬡` or custom — Venn-style overlap if available in common terminal fonts

The chosen glyph must render correctly in common terminal emulators (iTerm2, Terminal.app, Windows Terminal, standard Linux terminals).

## Motivation

"File contention" with a warning symbol suggests a problem requiring user action. In reality, the sprint system already handles this by splitting into sub-waves — it's informational, not a warning. "File overlap" is more accurate terminology and a non-warning glyph better matches the informational nature.

## Proposed Solution

1. In `scripts/little_loops/cli/sprint.py` around line 290, change:
   ```python
   f"  \u26a0  File contention \u2014 sub-wave "
   ```
   to:
   ```python
   f"  [GLYPH]  File overlap \u2014 sub-wave "
   ```

2. Update test assertions in `scripts/tests/test_cli.py` that check for the string `"File contention"` — change to `"File overlap"`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint.py` — line 290: display string

### Dependent Files (Callers/Importers)
- N/A — this is a display-only change

### Similar Patterns
- `scripts/little_loops/dependency_graph.py` — docstrings and log messages reference "file contention" (update for consistency)
- `scripts/little_loops/cli/sprint.py` — comments on lines 285, 389, 743 reference "file contention"

### Tests
- `scripts/tests/test_cli.py` — lines 1066, 1084, 1119: string assertions for "File contention"

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Choose a Unicode glyph that renders well across terminals
2. Update the display string in `sprint.py:290`
3. Update comments and docstrings referencing "File contention" label in sprint.py
4. Update test assertions in test_cli.py
5. Optionally update docstrings/log messages in dependency_graph.py for terminology consistency

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

- **Verified**: 2026-02-13
- **Verdict**: NEEDS_UPDATE
- **Glyph claim inaccurate**: No `⚠` warning glyph found near "file contention" text. Actual format at line 290: `f"Wave {logical_num} ({group_count} issues, serialized — file contention):"` — no warning triangle glyph is used
- **Test assertions not found**: No "File contention" string assertions found in test_cli.py (previously claimed at lines 1066, 1084, 1119)
- **Other references found**: "file contention" appears at sprint.py lines 290, 374, 940
- Core relabeling request ("contention" → "overlap") remains valid, but the issue description of current behavior needs correction

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4
