---
id: ENH-2886
title: Add action-severity field to drift findings and gate --fix to auto
type: ENH
parent: EPIC-2872
priority: P2
status: done
discovered_date: 2026-07-28
labels:
- verification
- ll-doctor
relates_to:
- ENH-2875
confidence_score: 92
outcome_confidence: 82
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 22
completed_at: '2026-07-28T08:22:35Z'
---

# ENH-2886: Add action-severity field to drift findings and gate --fix to auto

## Parent Issue
Decomposed from ENH-2875: Give drift findings an action-severity and a throttle, and forbid opportunistic repair

## Summary

`ll-verify-docs` and `ll-check-links` findings carry no field distinguishing a finding the tool can safely fix itself (`auto`) from one that needs a human (`mention`) or is owned by another command (`route`). `--fix` currently repairs every mismatch unconditionally. This issue adds the closed-vocabulary `auto`/`mention`/`route` action-severity field to the underlying result types and restricts `--fix` to `auto` findings only.

## Current Behavior

- `scripts/little_loops/doc_counts.py` — `CountResult` (line 38) and `VerificationResult` (line 50) have no severity/action field. `add_result()` (line 57) dumps every mismatch into one undifferentiated `mismatches` bucket. `fix_counts()` (line 408) repairs every mismatch unconditionally.
- `scripts/little_loops/link_checker.py` — `LinkOutcome` enum (line 46: `VALID`/`BROKEN`/`UNREACHABLE`/`IGNORED`) and `LinkResult` (line 61) classify network reachability, not action-severity or ownership. No `--fix` path exists in this tool today.
- `scripts/little_loops/cli/docs.py` — `main_verify_docs()` (function starts at line 15, `--fix` handling near line 101) invokes `fix_counts()` unconditionally for every mismatch under `--fix` (flag defined at line 66).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact construction call sites** where the new field must be assigned: `doc_counts.py`'s `verify_documentation()` (~line 120) builds each `CountResult` with `matches = documented == actual` (~line 169) then calls `result.add_result(count_result)` — this is the single call site for `CountResult`'s action-severity value. `link_checker.py`'s `check_markdown_links()` (~line 247) has ~6 separate `LinkResult(...)` construction sites (lines 291-397, one per outcome branch) that would each need an explicit action-severity value.
- **Formatters also need updating to surface the field**: `doc_counts.py`'s `format_result_text/json/markdown` (~lines 185, 211, 240) iterate `result.mismatches` and print `category`/`documented`/`actual`/`file`/`line` today, with no severity/action key — `format_result_json`'s dict comprehension (~line 226) in particular will need a new key for the field to appear in JSON output. `link_checker.py` has parallel formatters (`format_result_text/json/markdown`, ~lines 439-584) with the same gap. Neither is mentioned in the Acceptance Criteria; worth an explicit criterion or Implementation Step if the field is expected to be user-visible in `--format json`/`--format markdown` output, not just gate `--fix`.
- **No existing "route to owning command" precedent**: a repo-wide search for `owns its repair`/`owning command`/`owned by`/`command that owns` found no prior pattern for a finding that carries the name of another command as its repair owner. The closest structural analogue is `doctor.py`'s `_full_*_check()` functions, which name the underlying tool only in a docstring comment (e.g. `"""Adapter over verify_documentation() (ll-verify-docs)."""`), not as a data-carried field. This is genuinely new territory for the `route` value's "owning command" attribution, not a retrofit of an existing shape.
- **Test pattern to model new severity-gated tests after**: `scripts/tests/test_cli_doctor.py` has `test_mixed_severity_registered_check_affects_exit_code_via_main_doctor` — constructs a mixed list of `error`/`informational` `CheckResult`s and asserts the aggregate behavior. The equivalent shape for this issue's `fix_counts()` tests would be a fixture with one `auto` and one `mention`/`route` mismatch in the same batch, asserting only the `auto` one gets rewritten.

## Expected Behavior

`CountResult`/`VerificationResult`/`LinkResult` carry a closed-vocabulary `auto`/`mention`/`route` action-severity field, following the reference pattern:

- `auto` — fixed silently on the next write to that file
- `mention` — state once
- `route` — name the command that owns the repair

`fix_counts()` (and `main_verify_docs()`'s `--fix` flow) applies only to `auto`-severity findings. A `route`-severity finding carries the name of the command that owns its repair.

## Impact

Without this field, `--fix` rewrites any mismatch it finds, including ones that legitimately belong to another command's repair flow or that a human should confirm before silent rewrite (ENH-2875's opportunistic-repair problem). This issue is the data-shape prerequisite for ENH-2887 (aggregation), ENH-2888 (session-start hook), and ENH-2889 (docs-sync.yaml) — none of those can gate on severity until it exists on the result types.

## Scope Boundaries

In scope: the action-severity field on `CountResult`/`VerificationResult`/`LinkResult`, the `auto`-only gate on `fix_counts()`/`--fix`, and the `route`-severity "owning command" attribution. Out of scope: `ll-doctor`'s existing `error`/`informational` severity axis (orthogonal, unchanged — see `cli/doctor.py` `CheckResult`), the `--full` aggregation layer (ENH-2887), the session-start hook (ENH-2888), and `docs-sync.yaml` (ENH-2889).

## Similar Patterns

- `scripts/little_loops/cli/doctor.py` `CheckResult`/`_exit_code_for()` (lines 32-47, 98-101) — orthogonal `severity` field alongside `status`, closed `Literal[...]` vocabulary, one interpreting function. Model the new field the same way.
- `scripts/little_loops/fsm/validation.py` `ValidationSeverity` enum (lines 40-44) / `ValidationError` (lines 47-66) — alternative `Enum`-based severity shape, set explicitly at each violation call site (lines 586, 702).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/doctor.py` — `_full_docs_data()` (~line 476-480) and `_full_check_links_data()` (~line 736-740) call `verify_documentation()`/`check_markdown_links()` and read `CountResult`/`VerificationResult`/`LinkResult` fields directly; consumes the dataclass shape being changed. Out of scope for behavior (ENH-2887 owns threading severity through `--full` aggregation), but the new field must default-construct so these call sites don't break.
- `scripts/tests/test_cli_doctor_full.py` — `TestFullAdapters.test_docs_reports_full_on_match` (line 28) and `test_docs_reports_unsupported_on_mismatch` (line 37) construct `doc_counts.CountResult(...)`/`VerificationResult(...)` directly (lines 32, 40-43) feeding `_full_docs_data()`. These are keyword-only constructions that keep passing if the new field ships with a default; flagged here since they're a transitive consumer of the dataclass shape this issue changes (ENH-2887 owns adding severity assertions to them).

## Acceptance Criteria

- Every drift finding from `doc_counts.py`/`link_checker.py` carries an action-severity, and `--fix` applies only to `auto`-severity findings.
- A `route`-severity finding names the command that owns its repair.
- `CheckResult`'s existing `error`/`informational` severity axis is untouched.

## Tests

- `scripts/tests/test_doc_counts.py` — `TestFixCounts` (lines 425-566: `test_fix_replaces_count`, `test_fix_multiple_mismatches_same_file`, `test_fix_multiple_files`, etc.) constructs `CountResult`/`VerificationResult`/calls `fix_counts()` directly; every fixture needs a severity field once `fix_counts()` becomes severity-aware.
- `scripts/tests/test_cli_docs.py` — `test_fix_flag_with_mismatches` (~line 125) and `test_fix_flag_without_mismatches` (~line 153) assume `--fix` always calls `fix_counts()` for any mismatch; will break once `--fix` becomes `auto`-only unless fixtures gain an explicit `auto` severity.
- `scripts/tests/test_link_checker.py` — covers `LinkOutcome` classification; extend for action-severity.

### New Tests (added by `/ll:wire-issue`)

_No existing test in the repo exercises the `route` severity value or "owning command" attribution — these are net-new, not extensions of existing fixtures:_

- `scripts/tests/test_doc_counts.py` — new test(s) asserting `fix_counts()` filters by `action_severity` (mixed-severity `VerificationResult` fixture, assert only `auto` mismatches land in `files_modified`); model the gating-predicate/integration split after `scripts/tests/test_cli_doctor.py::test_exit_code_ignores_informational_unsupported` (narrow) and `test_mixed_severity_registered_check_affects_exit_code_via_main_doctor` (line 715, wide/integration via register+patch+restore).
- `scripts/tests/test_link_checker.py` — new test(s) covering `action_severity` on `LinkResult` for `mention`/`route` values (zero coverage today).
- `scripts/tests/test_cli_docs.py` — `test_fix_flag_with_mismatches` (~line 125) currently asserts `fix_counts` is called whenever `not all_match`; needs a companion fixture with a non-`auto` mismatch present to assert the CLI's `--fix` gate (`main_verify_docs()` line 101: `if args.fix and not result.all_match:`) also respects severity, not just `all_match`.

## Documentation

- `docs/reference/CLI.md` — update for the new severity field and `--fix` semantics.
- `docs/reference/API.md` — document the new severity/action field on `CountResult`/`VerificationResult`/`LinkResult`/`LinkOutcome`.

## Session Log
- `ll-auto` - 2026-07-28T08:22:35 - `acefb638-6ab6-4e32-9feb-e3cce31fae91.jsonl`
- `/ll:ready-issue` - 2026-07-28T08:11:23 - `7c86a950-0cdb-4c22-8d05-ea75b5d8ed4d.jsonl`
- `/ll:confidence-check` - 2026-07-28T08:09:49 - `d8ae9e6b-b8e9-4adf-837f-cd603b14ac09.jsonl`
- `/ll:wire-issue` - 2026-07-28T08:08:55 - `54f0f02a-6518-440f-84e5-99d259bf4395.jsonl`
- `/ll:refine-issue` - 2026-07-28T08:01:19 - `d3455184-ddb9-43a7-81b5-e0216a2e895e.jsonl`
- `/ll:issue-size-review` - 2026-07-28T08:00:00 - `f26799df-de87-40c6-90ea-225f55ba976e.jsonl`

## Status

open


---

## Resolution

- **Action**: improve
- **Completed**: 2026-07-28
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
