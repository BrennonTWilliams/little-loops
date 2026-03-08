---
id: BUG-640
type: BUG
priority: P3
title: "is_formatted ignores /ll:format-issue session log entry"
status: completed
---

## Summary

`is_formatted` in `issue_parser.py` only performed a structural section check (all required `##` headings present per type template). It ignored whether `/ll:format-issue` had been run on the issue and recorded in the `## Session Log`. This caused the `fmt` column in `ll-issues refine-status` to show `✗` for issues that had clearly been formatted via `/ll:format-issue`.

## Root Cause

`is_formatted` had a single evaluation path: load the type template, collect required section names, and check whether all were present as `##` headings in the file. There was no check for a `/ll:format-issue` entry in `## Session Log`.

Issues formatted via `/ll:format-issue` may have been formatted correctly but fail the section check due to minor structural differences or template drift, producing false negatives.

## Fix

Updated `is_formatted` (`scripts/little_loops/issue_parser.py`) to use two criteria (OR logic):

1. **Session log check** (checked first): if `/ll:format-issue` appears in the parsed `## Session Log`, return `True` immediately.
2. **Structural check** (fallback): all required sections per the type template are present as `##` headings.

The file is now read once upfront (instead of at the end), shared across both checks.

## Acceptance Criteria

- [x] Issues with `/ll:format-issue` in `## Session Log` show `✓` in the `fmt` column
- [x] Issues lacking `/ll:format-issue` in the session log but with all required sections also show `✓`
- [x] Issues with neither condition show `✗`
- [x] `is_formatted` reads the file once regardless of which criterion is evaluated

## Files Changed

- `scripts/little_loops/issue_parser.py` — `is_formatted` function

## Session Log

- 2026-03-07 `BUG-640` completed inline (no dedicated session file)
