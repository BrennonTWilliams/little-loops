---
discovered_date: 2026-02-24
discovered_by: capture-issue
confidence_score: 80
outcome_confidence: 75
---

# ENH-504: Format Highest-Priority Issue When No Args Provided

## Summary

When `/ll:format-issue` is run without any arguments, it should automatically select and format the highest-priority active issue, matching the pattern used by `/ll:manage-issue` when invoked without an argument.

## Current Behavior

Running `/ll:format-issue` without any arguments results in an error or shows usage without taking action. Users must always specify an issue ID or `--all` flag explicitly, even when they just want to format the next highest-priority issue.

## Expected Behavior

When invoked with no arguments (no issue ID and no `--all` flag), `/ll:format-issue` automatically selects the highest-priority active issue (P0 first, descending through P5; ties broken by issue number ascending) and formats it. The skill prints the selected issue ID before starting so the user knows what is being formatted.

## Motivation

Currently, running `/ll:format-issue` without arguments has undefined or unproductive behavior. The `/ll:manage-issue` skill already implements a sensible default — selecting the highest-priority issue from the active backlog — and `/ll:format-issue` should follow the same convention for consistency and usability. This reduces friction when running format passes over the backlog without needing to specify issue IDs manually.

## Scope Boundaries

- **In scope**: Default no-argument selection logic in the format-issue skill's argument parsing phase; documentation update for the Arguments section
- **Out of scope**: Changing behavior when an explicit issue ID is provided; changing `--all` behavior; modifying manage-issue logic

## Implementation Steps

1. Locate the format-issue skill definition (`skills/format-issue/SKILL.md` or similar)
2. Review how `/ll:manage-issue` selects the highest-priority issue when no argument is given
3. Add equivalent default-selection logic to the format-issue skill's argument parsing phase
4. Update the skill's "Arguments" documentation to describe the no-arg behavior
5. Verify the selected issue is printed to the user before formatting begins

## Integration Map

### Files to Modify
- `skills/format-issue/SKILL.md` — Replace lines 81-85 (the error-exit block) with the priority selection loop

### Dependent Files (Callers/Importers)
- N/A — skill-level change only

### Similar Patterns
- `skills/manage-issue/SKILL.md:54-83` — exact priority selection loop to mirror

### Codebase Research Findings

_Added by `/ll:refine-issue` — Exact insertion point and pattern:_

**Exact location to modify** (`skills/format-issue/SKILL.md:81-85`):
```bash
# Current block to REPLACE:
if [[ -z "$ISSUE_ID" ]]; then
    echo "Error: issue_id is required when not using --all flag"
    echo "Usage: /ll:format-issue [ISSUE_ID] [--auto]"
    exit 1
fi
```

**Pattern to follow from `manage-issue/SKILL.md:62-70`:**
```bash
# Find highest priority (P0 > P1 > P2 > ...)
for P in P0 P1 P2 P3 P4 P5; do
    ISSUE_FILE=$(ls "$SEARCH_DIR"/$P-*.md 2>/dev/null | sort | head -1)
    if [ -n "$ISSUE_FILE" ]; then
        break
    fi
done
```

**Adaptation needed for format-issue:** Unlike `manage-issue`, `format-issue` searches across all active category directories (`bugs/`, `features/`, `enhancements/`) in its existing loop at lines 87-99. The no-arg selection logic must iterate over all three categories at each priority level, not just a single `$SEARCH_DIR`. Suggested pattern:
```bash
if [[ -z "$ISSUE_ID" ]] && [[ "$ALL_MODE" == false ]]; then
    for P in P0 P1 P2 P3 P4 P5; do
        for dir in {{config.issues.base_dir}}/*/; do
            if [ "$(basename "$dir")" = "{{config.issues.completed_dir}}" ]; then continue; fi
            FOUND=$(ls "$dir"/$P-*.md 2>/dev/null | sort | head -1)
            if [ -n "$FOUND" ]; then FILE="$FOUND"; break 2; fi
        done
    done
    if [ -z "$FILE" ]; then echo "No active issues found."; exit 0; fi
    echo "Selected highest-priority issue: $(basename $FILE)"
fi
```

**Arguments section** (`skills/format-issue/SKILL.md:9-15`): Update `issue_id` description from current to: "Specific issue ID (e.g., BUG-004). If empty and --all is not set, selects highest-priority active issue."

### Tests
- N/A — skill-level testing is manual

### Documentation
- N/A — Arguments section updated within the skill itself

### Configuration
- N/A

## Impact

- **Priority**: P3 — Usability improvement; reduces friction for interactive format passes
- **Effort**: Small — Logic addition in skill argument parsing phase only
- **Risk**: Low — Additive; no change when explicit issue ID or `--all` flag is provided
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/manage-issue/SKILL.md` | Reference implementation for highest-priority issue selection |
| `skills/format-issue/SKILL.md` | The skill being enhanced |

## Labels

`enhancement`, `ux`, `format-issue`

## Session Log
- `/ll:capture-issue` - 2026-02-24T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc790b97-8457-4261-96c9-b25c3abc9efc.jsonl`
- `/ll:format-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a32a1e4-137e-4580-a6db-a31be30ec313.jsonl`
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Identified exact insertion point (format-issue/SKILL.md:81-85) and priority loop pattern from manage-issue/SKILL.md:62-70

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3

## Blocked By

- FEAT-441
