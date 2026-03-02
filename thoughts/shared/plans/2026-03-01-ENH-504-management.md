# ENH-504: Format Highest-Priority Issue When No Args Provided

## Plan Summary

Add default no-arg behavior to `/ll:format-issue` so it auto-selects the highest-priority active issue when invoked without an issue ID or `--all` flag, matching the pattern used by `/ll:manage-issue`.

## Research Findings

- The manage-issue skill uses a simple priority loop (P0→P5) with `ls`/`sort`/`head` at `skills/manage-issue/SKILL.md:77-83`
- The format-issue skill currently errors at lines 81-85 when no issue_id is provided
- Format-issue already iterates across all active category directories at lines 88-99 when searching for a specific issue, excluding `completed/` and `deferred/`
- The adaptation must search ALL categories (not just one `$SEARCH_DIR`) at each priority level

## Changes

### File: `skills/format-issue/SKILL.md`

#### Change 1: Replace error block (lines 81-85) with priority selection

**Before:**
```bash
if [[ -z "$ISSUE_ID" ]]; then
    echo "Error: issue_id is required when not using --all flag"
    echo "Usage: /ll:format-issue [ISSUE_ID] [--auto]"
    exit 1
fi
```

**After:**
```bash
if [[ -z "$ISSUE_ID" ]]; then
    # No issue_id provided — select highest-priority active issue
    for P in P0 P1 P2 P3 P4 P5; do
        for dir in {{config.issues.base_dir}}/*/; do
            if [ "$(basename "$dir")" = "{{config.issues.completed_dir}}" ] || [ "$(basename "$dir")" = "{{config.issues.deferred_dir}}" ]; then continue; fi
            FOUND=$(ls "$dir"/$P-*.md 2>/dev/null | sort | head -1)
            if [ -n "$FOUND" ]; then FILE="$FOUND"; break 2; fi
        done
    done
    if [ -z "$FILE" ]; then
        echo "No active issues found."
        exit 0
    fi
    echo "Selected highest-priority issue: $(basename "$FILE")"
fi
```

#### Change 2: Update Arguments section (line 35)

**Before:**
```
  - If omitted without `--all`, shows error
```

**After:**
```
  - If omitted without `--all`, selects highest-priority active issue
```

## Success Criteria

- [x] When no args provided, selects highest priority active issue across all categories
- [x] Excludes completed/ and deferred/ directories from search
- [x] Prints selected issue filename before formatting begins
- [x] Existing behavior unchanged when issue_id or --all is provided
- [x] Arguments documentation updated
