# ENH-899: `ll-loop status` Show Log File Details

## Overview
Add log file path, last modified time, and last event line to `ll-loop status` output (both text and JSON).

## Changes

### 1. Add `_format_relative_time` helper (`lifecycle.py`)
- Takes seconds as float, returns "3m ago", "1h 23m ago", "2d ago"
- Unit set: s, m, h, d (matches `text_utils.py:173`)

### 2. Update `cmd_status` text output (`lifecycle.py:62-83`)
- Derive `log_file = running_dir / f"{loop_name}.log"` (mirrors PID at line 54)
- If exists: print path, mtime age, last non-empty line
- If not exists: print `Log: (not found)`

### 3. Update `cmd_status` JSON output (`lifecycle.py:57-61`)
- Add `log_file`, `log_updated_ago`, `last_event` keys to dict

### 4. Tests (TDD - write first)
- `test_status_shows_log_file_details` — log exists with content
- `test_status_shows_log_not_found` — no log file
- `test_status_json_includes_log_fields` — JSON output
- `test_format_relative_time` — unit test for the helper

## Success Criteria
- [x] `_format_relative_time` helper added
- [x] Text output includes log path, age, last event
- [x] JSON output includes log fields
- [x] Graceful handling when log file missing
- [x] Tests pass
- [x] Lint/type checks pass
