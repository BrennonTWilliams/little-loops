---
id: ENH-2024
title: Add --parent filter to ll-issues list
type: ENH
priority: P4
status: done
---

## Problem

`ll-issues list` had no way to filter to children of a specific parent issue. To see all open issues under a given epic you had to use `--group-by epic` and scan visually, or pipe `--json` through `jq`. The `parent:` frontmatter field was already tracked and surfaced in JSON output but could not be used as a filter predicate.

## Solution

Added `--parent ISSUE_ID` to `ll-issues list` (alias `l`), following the same exact-match pattern as the existing `--milestone` filter.

**Changed files:**
- `scripts/little_loops/cli/issues/__init__.py` — registered `--parent` / `dest="parent"` argument on the `list` subparser
- `scripts/little_loops/cli/issues/list_cmd.py` — added `parent_filter` variable and an `issue.parent == parent_filter` predicate to the filter comprehension

## Usage

```bash
ll-issues list --parent EPIC-001
ll-issues list --parent EPIC-001 --status all --json
```

Composable with all other filters (`--type`, `--priority`, `--status`, `--label`, `--milestone`, `--sort`, `--limit`, etc.).


## Session Log
- `hook:posttooluse-status-done` - 2026-06-08T20:50:30 - `0c6be1b2-0553-4e28-bb1f-1f06c6ddae23.jsonl`
