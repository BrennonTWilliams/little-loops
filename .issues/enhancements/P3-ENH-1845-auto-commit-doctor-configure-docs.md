---
id: ENH-1845
title: Auto-commit doctor UI, configure areas display, and documentation
type: ENH
priority: P3
status: done
parent: ENH-1717
confidence_score: 95
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 10
implementation_order_risk: true
size: Very Large
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

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Files Modified**
- `scripts/little_loops/cli/doctor.py` — `_print_issues_section()` at line 41; called from `main_doctor()` at line 141 (after `_print_capture_section`)
- `scripts/tests/test_cli_doctor.py` — `test_issues_auto_commit_section_enabled` at line 389, `test_issues_auto_commit_section_disabled` at line 418
- `skills/configure/areas.md` — issues `### Current Values` block (lines 133–140); hooks table `issue-auto-commit.sh` row at line 869
- `docs/reference/CONFIGURATION.md` — `### issues` table rows at lines 279–280
- `docs/ARCHITECTURE.md` — `### Issue Auto-Commit` subsection at lines 1091–1102

**Dependent Files (Callers/Importers)**
- `scripts/little_loops/config/features.py` — `IssuesConfig` dataclass source of `cfg.issues` passed to `_print_issues_section()`
- `hooks/hooks.json` — `issue-auto-commit.sh` registered as two separate PostToolUse entries: lines 88–98 (`Write`) and 99–109 (`Edit`)
- `scripts/little_loops/cli/__init__.py` — re-exports `main_doctor` in `__all__`; no change needed
- `scripts/pyproject.toml` — `ll-doctor = "little_loops.cli:main_doctor"` entry point; no change needed

**Confirmed Pattern Anchors**
- `scripts/little_loops/cli/doctor.py:23` — `_print_capture_section()` — exact model followed for `_print_issues_section()`
- `scripts/tests/test_cli_doctor.py:336` — `test_analytics_capture_section_all_enabled` — test structure model
- `docs/ARCHITECTURE.md:1071` — `### Session Log Auto-Linking` — structural model for new subsection

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `### ll-doctor` section has a verbatim example output block ending after "Analytics Capture"; needs "Issues" section added to match new `_print_issues_section` output [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md` — `## Runnable Capability Check` prose: "also prints an 'Analytics Capture' section…" needs to also mention the new "Issues" section [Agent 2 finding]
- `docs/reference/API.md` — `### IssuesConfig` dataclass code block does not include `auto_commit` or `auto_commit_prefix` fields (added in ENH-1843, undocumented here) [Agent 2 finding]
- `docs/codex/README.md` — paragraph describing `ll-doctor` output omits the Issues section [Agent 2 finding]
- `skills/configure/show-output.md` — `## issues --show` section (lines 23–36) missing `auto_commit` and `auto_commit_prefix` fields in the `configure --show issues` output template [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_doctor.py` — `test_issues_auto_commit_section_enabled` (line 389) and `test_issues_auto_commit_section_disabled` (line 418) already written; follow `_capture_print()` + `_make_runner()` helpers pattern
- `scripts/tests/test_feat1504_doc_wiring.py`, `test_feat1625_doc_wiring.py`, `test_ll_logs_wiring.py`, `test_create_extension_wiring.py` — each asserts `"Authorize all 26"` in `areas.md`; low-risk (count is CLI tools, not config questions) but would break if the authorize-all number changes [Agent 3 finding]
- `scripts/tests/test_enh1845_doc_wiring.py` — **gap**: no wiring test file exists for ENH-1845; should assert `auto_commit` present in `docs/reference/CONFIGURATION.md`, `skills/configure/areas.md`, and `docs/ARCHITECTURE.md`; follow `test_enh1734_doc_wiring.py` pattern [Agent 3 finding]

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-01_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 67/100 → MODERATE

### Outcome Risk Factors
- `docs/reference/CLI.md` ll-doctor example output still shows only "Analytics Capture" section — "Issues" section not reflected in example block; identified by `/ll:wire-issue` but not implemented (issue marked done)
- `docs/reference/HOST_COMPATIBILITY.md` prose says "also prints an 'Analytics Capture' section" — does not mention new "Issues" section
- `docs/reference/API.md` `IssuesConfig` dataclass block missing `auto_commit` and `auto_commit_prefix` fields added in ENH-1843
- `skills/configure/show-output.md` `configure --show issues` output template missing `auto_commit`/`auto_commit_prefix` fields
- `test_enh1845_doc_wiring.py` does not exist — wiring coverage gap; these tests are co-deliverables of the ENH-1845 implementation and assert `auto_commit` presence in CONFIGURATION.md, areas.md, and ARCHITECTURE.md

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8698e6e-9c45-4d67-8054-c621d3104267.jsonl`
- `/ll:wire-issue` - 2026-06-01T09:08:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75b96388-8e1f-45e0-9c33-f5b3c8e964f1.jsonl`
- `/ll:refine-issue` - 2026-06-01T09:02:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/601d045e-eabd-4567-ae43-13dfb443db86.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e2ad9a6-4834-4969-9404-2babd791318d.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d0e9800f-e118-4d24-8ad2-495361bb162e.jsonl`
