---
id: BUG-1779
type: BUG
status: open
priority: P4
created_date: 2026-05-28
captured_at: "2026-05-29T01:36:37Z"
discovered_date: 2026-05-28
discovered_by: capture-issue
labels:
  - bug
  - cli
  - json
  - captured
---

# BUG-1779: description field missing from ll-loop `list --json` output

## Summary

When running `ll-loop list --json`, the output JSON includes `name`, `path`, `category`, and `labels` but omits `description` — even though `_load_loop_meta()` already extracts it from the loop YAML.

## Current Behavior

`ll-loop list --json` outputs:

```json
[
  {
    "name": "my-loop",
    "path": "/path/to/loops/my-loop.yaml",
    "category": "data",
    "labels": ["example"]
  }
]
```

No `description` field is present.

## Expected Behavior

Each item in the JSON array should include `"description"`:

```json
[
  {
    "name": "my-loop",
    "path": "/path/to/loops/my-loop.yaml",
    "category": "data",
    "labels": ["example"],
    "description": "Runs the data pipeline end to end"
  }
]
```

## Steps to Reproduce

1. Run `ll-loop list --json` in a project with loops that have descriptions
2. Observe that the `description` field is absent from every entry

## Motivation

Consumers of `--json` output (scripts, dashboards, downstream tooling) have no access to the loop's description without re-parsing each YAML file. The data is already loaded; it just isn't wired into the JSON output dict.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Anchor**: `cmd_list()`, lines 183-195
- **Cause**: `_load_loop_meta()` correctly extracts `description` from the YAML and it flows into `all_loops` entries via `**meta`. However, when building the JSON-serializable dict at lines 185-194, the code manually constructs each item and only includes `name`, `path`, `category`, `labels`, and `built_in` — it never copies `description` into the output.

## Proposed Solution

Add `"description": lp["description"]` to the `item` dict in `cmd_list()`:

```python
# scripts/little_loops/cli/loop/info.py, ~line 186
item: dict[str, Any] = {
    "name": lp["name"],
    "path": str(lp["path"]),
    "category": lp["category"],
    "labels": lp["labels"],
    "description": lp["description"],  # add this line
}
```

The `_load_loop_meta` function already returns `""` when a loop has no description, so this is safe — every entry will have at least an empty string.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — add `description` to the JSON output dict in `cmd_list()`

### Dependent Files (Callers/Importers)
- N/A — no callers consume the JSON output format of `ll-loop list`. This is a terminal output format.

### Similar Patterns
- N/A — one-line field addition to existing JSON output dict; no similar patterns to align

### Tests
- `scripts/tests/` — add or update a test that verifies `ll-loop list --json` includes the `description` key

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `"description": lp["description"]` to the `item` dict at line 186 of `scripts/little_loops/cli/loop/info.py`
2. Add or update a test case in `scripts/tests/` to assert `description` is present in `--json` output
3. Run `ll-loop list --json` manually to verify the field appears

## Impact

- **Priority**: P4 — Minor defect. The data is available and loaded; it's simply not included in the JSON output. No crashes or incorrect data.
- **Effort**: Small — One-line fix plus a test assertion.
- **Risk**: Low — Adding a field to JSON output is backwards-compatible; no existing consumers should break.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `cli`, `json`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-29T01:42:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3503f9ee-b935-4a47-a95f-613e88e853a9.jsonl`
- `/ll:capture-issue` - 2026-05-29T01:36:37Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10ec9212-23d4-4181-8984-005063bcc13e.jsonl`

## Status

**Open** | Created: 2026-05-28 | Priority: P4
