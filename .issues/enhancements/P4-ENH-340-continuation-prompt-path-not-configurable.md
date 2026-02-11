---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# ENH-340: Continuation prompt path not configurable

## Summary

`subprocess_utils.py` hardcodes `.claude/ll-continue-prompt.md` as the continuation prompt path with no way to override via config.

## Context

Identified during a config consistency audit. Minor impact since most users won't need to change this path, but it's inconsistent with the pattern used for other paths.

## Affected Files

- `scripts/little_loops/subprocess_utils.py` (line 25): hardcoded `CONTINUATION_PROMPT_PATH`

## Proposed Fix

Either parameterize the function to accept the path, or add a config key under `continuation.prompt_path`.

---

## Status

**Open** | Created: 2026-02-11 | Priority: P4
