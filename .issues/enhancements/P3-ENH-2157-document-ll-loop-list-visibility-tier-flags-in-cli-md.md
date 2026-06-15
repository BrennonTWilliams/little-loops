---
id: ENH-2157
title: Document ll-loop list visibility tier flags in CLI.md
type: ENH
priority: P3
status: done
created: 2026-06-14
affects:
- docs/reference/CLI.md
confidence_score: 98
outcome_confidence: 90
score_complexity: 25
score_test_coverage: 15
score_ambiguity: 25
score_change_surface: 25
completed_at: '2026-06-15T14:52:25Z'
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

## Integration Map

### Files to Modify
- `docs/reference/CLI.md` — add three flag rows to the `ll-loop list` table (lines 625–631) and update the `--json` field list

### Dependent Files (Reference Only — no changes needed)
- `scripts/little_loops/cli/loop/__init__.py:297–311` — argparse definitions for `--all`/`-a`, `--internal`, `--examples` (source of truth for flag descriptions)
- `scripts/little_loops/cli/loop/info.py:53–55` — visibility enum validation (`"public"`, `"internal"`, `"example"`) and default value
- `scripts/little_loops/cli/loop/info.py:217–231` — JSON serialization block; confirms `visibility` is always present

### Tests
- `scripts/tests/test_ll_loop_commands.py:713` — `TestVisibilityTierFilter` class with `test_internal_flag_shows_only_internal()`, `test_examples_flag_shows_only_examples()`, `test_all_flag_shows_all_visibility_tiers()`, `test_json_includes_visibility_field()`

### Documentation Context
- `CHANGELOG.md:23` — v1.124.0 entry: "Visibility tier in `ll-loop list`"
- `scripts/little_loops/loops/README.md:7–12` — already documents visibility tiers; CLI.md is the gap

## Implementation Steps

1. Open `docs/reference/CLI.md` and locate the `ll-loop list` flags table (lines 625–631)
2. Insert three new rows after the `--label` row and before `--json`:
   - `| \`--all\` / \`-a\` | \`-a\` | Show all loops including internal sub-loops and examples (hidden by default) |`
   - `| \`--internal\` | | Show only internal (delegated-only) sub-loops |`
   - `| \`--examples\` | | Show only example/template loops |`
3. In the `--json` row description, add `"visibility"` to the field list after `"labels"` (before `"description"`) — full non-running field set: `name`, `path`, `category`, `labels`, `visibility`, `description`, `built_in`
4. Verify: `ll-loop list --help` confirms `--internal`, `--examples`, and `--all`/`-a` appear in the output

## Notes

The visibility tier was added to control which loops appear in the default listing (users see `public` loops; `internal` and `example` loops are hidden unless requested). This was a v1.124.0 addition per the CHANGELOG.

In default view, `ll-loop list` (human-readable) prints a footer hint like `Hidden: N internal (--internal), M example (--examples) · all with --all` when non-public loops exist. The `--json` path includes `visibility` on every entry unconditionally (defaults to `"public"` if the YAML field is missing or invalid).

## Session Log
- `/ll:ready-issue` - 2026-06-15T14:52:05 - `a0aa48aa-ce96-46bd-abe3-d9c5731fc458.jsonl`
- `/ll:refine-issue` - 2026-06-15T14:46:17 - `b41a9adb-f0b8-4ea8-b7ee-6db0339bee2a.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/95c9dfbd-edfb-4ae6-9edf-17daa31fceee.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `faceb11e-e2d7-4c0d-a89f-0bc95671d1c2.jsonl`


---

## Resolution

- **Status**: Closed - Already Fixed
- **Closed**: 2026-06-15
- **Reason**: already_fixed
- **Closure**: Automated (ready-issue validation)

### Closure Notes
Issue was automatically closed during validation.
The issue was determined to be invalid, already resolved, or not actionable.
