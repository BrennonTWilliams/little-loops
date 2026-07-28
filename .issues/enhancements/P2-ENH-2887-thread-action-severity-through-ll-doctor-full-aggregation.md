---
id: ENH-2887
title: Thread action-severity through ll-doctor --full aggregation
type: ENH
parent: ENH-2875
priority: P2
status: open
discovered_date: 2026-07-28
labels:
- verification
- ll-doctor
depends_on:
- ENH-2886
---

# ENH-2887: Thread action-severity through ll-doctor --full aggregation

## Parent Issue
Decomposed from ENH-2875: Give drift findings an action-severity and a throttle, and forbid opportunistic repair

## Summary

`ll-doctor --full` collapses the entire underlying `VerificationResult`/`LinkCheckResult` into a single `CheckResult` note string, discarding per-finding granularity. Once ENH-2886 adds the `auto`/`mention`/`route` action-severity field to those result types, `ll-doctor --full` needs to thread it through instead of collapsing it, so per-finding action-severity survives to the aggregated output.

## Current Behavior

`scripts/little_loops/cli/doctor.py` — `CheckResult` (lines 32-47) already has a two-tier `severity: Literal["error", "informational"]` field, but it only gates `ll-doctor`'s own exit code via `_exit_code_for()` (lines 98-101) — a different axis from action-severity. `_full_docs_check()` (line 486) and `_full_check_links_check()` (line 760) collapse the entire underlying result into a single `CheckResult` note string, discarding per-finding granularity.

## Expected Behavior

`_full_docs_check()` and `_full_check_links_check()` surface each finding's action-severity (added in ENH-2886) in the `--full` output, without conflating it with `CheckResult`'s existing `error`/`informational` exit-code-governing severity field.

## Scope Boundaries

In scope: `_full_docs_check()`/`_full_check_links_check()` aggregation logic and their output shape for action-severity. Out of scope: the action-severity field itself (ENH-2886, a prerequisite), the session-start hook (ENH-2888), `docs-sync.yaml` (ENH-2889).

## Similar Patterns

- `scripts/little_loops/cli/doctor.py` `CheckResult` docstring (~line 36) states it "mirrors `host_runner.CapabilityEntry`'s frozen-dataclass + closed-status shape" — this precedent for the existing severity field's design should inform the aggregation shape for action-severity.

## Acceptance Criteria

- `ll-doctor --full` output distinguishes each finding's action-severity without conflating it with the existing `error`/`informational` exit-code axis.
- `CheckResult`'s existing `error`/`informational` severity axis is untouched.

## Tests

- `scripts/tests/test_cli_doctor.py`, `test_cli_doctor_full.py`, `test_cli_doctor_install_checks.py` — cover `main_doctor()` and `--full` aggregation adapters (`_full_docs_data`, etc.); need new coverage for action-severity surfacing in `--full` output.

## Documentation

- `docs/reference/CLI.md` — update `ll-doctor --full` output documentation for the surfaced action-severity.
- `scripts/little_loops/adapters/capabilities.py` (docstring ~line 20) — the "mirrors `host_runner.CapabilityEntry`'s frozen-dataclass + closed-status shape" comment references `CheckResult`'s shape; verify it doesn't need updating once `--full` output changes.
- `CONTRIBUTING.md` (line ~664) — the release checklist hand-asserts a specific `ll-doctor` output string ("{N} tool(s) discovered"); verify the `--full` output-shape change for action-severity doesn't break this assertion.

## Session Log
- `/ll:issue-size-review` - 2026-07-28T08:00:00 - `f26799df-de87-40c6-90ea-225f55ba976e.jsonl`

## Status

open
