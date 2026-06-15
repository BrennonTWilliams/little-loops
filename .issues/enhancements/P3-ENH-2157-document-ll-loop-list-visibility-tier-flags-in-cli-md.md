---
id: ENH-2157
title: Document ll-loop list visibility tier flags in CLI.md
type: ENH
priority: P3
status: open
created: 2026-06-14
affects:
  - docs/reference/CLI.md
---

## Problem

`docs/reference/CLI.md` section for `ll-loop list` (around line 619) is missing documentation for flags and JSON output fields added with the visibility tier feature (CHANGELOG v1.124.0):

**Missing flags:**
- `--internal` — show only internal sub-loops (hidden from default listing)
- `--examples` — show only example/demo loops (hidden from default listing)

**Missing JSON field:**
- `visibility` field (values: `public` | `internal` | `example`) is now included in every `--json` output entry but is not documented in the flags table or the JSON field description.

## Acceptance Criteria

- [ ] Add `--internal` row to the `ll-loop list` flags table with description
- [ ] Add `--examples` row to the `ll-loop list` flags table with description
- [ ] Extend the `--json` output description to list `"visibility"` as one of the output fields
- [ ] Verify the flags exist in the actual CLI: `ll-loop list --help`

## Notes

The visibility tier was added to control which loops appear in the default listing (users see `public` loops; `internal` and `example` loops are hidden unless requested). This was a v1.124.0 addition per the CHANGELOG.
