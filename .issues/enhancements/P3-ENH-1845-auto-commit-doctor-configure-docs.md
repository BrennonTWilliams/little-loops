---
id: ENH-1845
title: "Auto-commit doctor UI, configure areas display, and documentation"
type: ENH
priority: P3
status: done
parent: ENH-1717
---

# ENH-1845: Auto-commit doctor UI, configure areas display, and documentation

## Summary

Expose the `auto_commit` feature flag in `ll-doctor` output, update the `configure` skill's areas display, and document the new config fields in `docs/reference/CONFIGURATION.md`, `CONTRIBUTING.md`, and `docs/ARCHITECTURE.md`.

## Parent Issue

Decomposed from ENH-1717: Auto-commit hooks on Issue file CRUD operations

## Prerequisites

Requires ENH-1843 (config layer) to land first so `issues_cfg.auto_commit` resolves correctly in doctor.

## Proposed Solution

### scripts/little_loops/cli/doctor.py

Add `_print_issues_section(issues_cfg)` function following the `_print_capture_section()` pattern at line 23. Call it from `main_doctor()` after `_print_capture_section()` at line 128. Report `auto_commit` enabled/disabled using `_STATUS_SYMBOLS["full"]` / `_STATUS_SYMBOLS["unsupported"]`.

### skills/configure/areas.md

Two locations:
1. `## Area: hooks` section — add `issue-auto-commit.sh` row to the hardcoded PostToolUse hooks table (rows for `context-monitor.sh`, `issue-completion-log.sh`, `check-duplicate-issue-id-post.sh`)
2. `## Area: issues` Current Values display block — add `auto_commit` and `auto_commit_prefix` so users running `/ll:configure issues` see the new flags

### docs/reference/CONFIGURATION.md

Document `issues.auto_commit` (bool, default false) and `issues.auto_commit_prefix` (string) in both:
- The `### \`issues\`` table (around line 25)
- The "Full Configuration Example" block

### CONTRIBUTING.md

Mention `auto_commit` in the workflow section.

### docs/ARCHITECTURE.md

Add subsection documenting `issue-auto-commit.sh` as a PostToolUse hook on `Write` events (parallel to existing `### Session Log Auto-Linking`). Also correct existing `issue-completion-log.sh` entry which incorrectly states matcher `Bash` (it actually uses `Write`).

## Implementation Steps

1. Add `_print_issues_section()` to `scripts/little_loops/cli/doctor.py`
2. Call it from `main_doctor()` at line 128
3. Update `skills/configure/areas.md` — hooks table and issues display block
4. Update `docs/reference/CONFIGURATION.md` — table and example
5. Update `CONTRIBUTING.md` — workflow section
6. Update `docs/ARCHITECTURE.md` — new subsection + fix matcher label

## Acceptance Criteria

- [ ] `ll-doctor` output includes `auto_commit` status line with enabled/disabled symbol
- [ ] `/ll:configure issues` shows `auto_commit` and `auto_commit_prefix` current values
- [ ] `/ll:configure hooks` shows `issue-auto-commit.sh` in the PostToolUse table
- [ ] `docs/reference/CONFIGURATION.md` documents both new fields
- [ ] `test_cli_doctor.py` — auto_commit enabled/disabled both appear correctly in output

## Tests

- `scripts/tests/test_cli_doctor.py` — add test in `TestMainDoctor` setting `mock_config.issues.auto_commit = True/False` and asserting `auto_commit` label appears in output; follow `test_analytics_capture_section_all_enabled` pattern with `_capture_print()` + `_make_runner()` helpers

## Similar Patterns

- `scripts/little_loops/cli/doctor.py` — `_print_capture_section()` at line 23 — section print pattern
- `scripts/tests/test_cli_doctor.py` — `test_analytics_capture_section_all_enabled` — test pattern

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e2ad9a6-4834-4969-9404-2babd791318d.jsonl`
