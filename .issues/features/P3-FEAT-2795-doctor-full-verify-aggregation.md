---
id: FEAT-2795
type: feature
priority: P3
status: done
parent: EPIC-2765
blocked_by: FEAT-2793
relates_to:
- FEAT-2763
decision_needed: false
confidence_score: 96
outcome_confidence: 78
score_complexity: 16
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 20
completed_at: '2026-07-25T15:02:57Z'
---

# FEAT-2795: Add ll-doctor --full aggregation of the ll-verify-* family

## Summary

Add an opt-in `--full` flag that aggregates the existing family of
single-purpose checkers (`ll-verify-docs`, `ll-verify-skills`,
`ll-verify-skill-budget`, `ll-verify-triggers`, `ll-verify-decisions`,
`ll-verify-package-data`, `ll-verify-kinds`, `ll-verify-design-tokens`,
`ll-verify-des-audit`, `ll-check-links`) behind `ll-doctor`, registered
against the check-registry protocol from FEAT-2793. The default (non-`--full`)
run stays fast and unaffected.

## Parent Issue

Decomposed from FEAT-2763: Expand ll-doctor to validate little-loops' own
install surface. This child covers Implementation Step 4.

## Proposed Solution

Import each verifier's pure `_run()` function directly in-process rather than
shelling out — every `ll-verify-*` checker already separates a pure
`_run() -> tuple[int, ...]` from its argparse-owning `main_verify_*()`
wrapper (e.g. `verify_decisions.py:50-78`/`81-124`, `verify_kinds.py:38-47`/
`50-70`), so no verifier requires subprocess overhead or `sys.argv` mutation.
Register each verifier as one check on the FEAT-2793 registry, gated so it
only runs when `--full` is passed.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The FEAT-2793 check-registry protocol is implemented in
  `scripts/little_loops/cli/doctor.py`: `CheckResult` dataclass (32-47),
  `_STATUS_SYMBOLS` (25-29), `_CHECKS: list[Callable[[], list[CheckResult]]]`
  + `register_check()` decorator (55-61), `_run_registered_checks()` (72-77),
  `_exit_code_for()` (80-83). A comment at `doctor.py:50-54` explicitly names
  this list as the extension point for FEAT-2794/FEAT-2795. `main_doctor()`
  (502-565) calls `_run_registered_checks()` at line 563 and folds the result
  into `_exit_code_for()` at 564 — there is no existing flag-gating mechanism
  in `doctor.py`, so `--full` needs a new argparse flag (parallel to
  `-j/--json` at 529-534) that conditionally runs a *separate* list of checks
  rather than appending to `_CHECKS` unconditionally.
- **Critical correction to the Proposed Solution's premise**: only 3 of the
  10 target verifiers actually expose the clean `_run() -> tuple[int, ...]`
  shape the Proposed Solution generalizes from
  (`verify_decisions.py:_run()` (50), `verify_kinds.py:_run()` (38),
  `verify_cli_allowlist.py:_run()` (69)). The other seven do not:
  - `verify_triggers.py` — `_run_validation()` (355) returns
    `tuple[dict[str, SkillTriggerResult], list[dict], dict]`, no exit code;
    pass/fail is computed separately by `_any_failures()` (555), called only
    inline inside `main_verify_triggers()` (577).
  - `verify_des_audit.py` — no `_run()`; logic is inline in
    `main_verify_des_audit()` (97), built on `audit_tree()` from
    `little_loops.observability.audit`, producing an `AuditResult` with
    `.passed`/`.uncovered_event_types`.
  - `verify_package_data.py` — no `_run()`; `run_escape_lint()` (136) and
    `run_manifest_check()` (151) are two separate pure entry points, exit
    code computed inline at `main_verify_package_data()` line 315
    (`1 if (lint_results or missing_assets) else 0`).
  - `verify_design_tokens.py` — no `_run()`; `lint_profile()` (92) /
    `lint_profiles_dir()` (126) feed `main_verify_design_tokens()` (197);
    pass/fail rule is `passed = not results` inside `_format_json_report()`
    (158).
  - `docs.py` (not `verify_docs.py` — one file holds four entry points) —
    `main_verify_docs()` (15) uses `verify_documentation()` from
    `little_loops.doc_counts`, exit via `.all_match` (line 108);
    `main_verify_skill_budget()` (111) uses `check_skill_budget()`, exit via
    `.under_budget`; `main_verify_skills()` (237) uses `check_skill_sizes()`;
    `main_check_links()` (313) uses `check_markdown_links()` from
    `little_loops.link_checker`. None factor out a local `_run()`.
  - `verify_cli_allowlist.py` is not in the issue's original ten-item list
    but does exist and does conform to the `_run()` shape
    (`-> tuple[int, dict[str, list[str]]]`, line 69) — consider whether it
    belongs in scope alongside the listed ten.

  **Option A**: Factor a `_run() -> tuple[int, ...]` out of each of the
  seven non-conforming verifiers (mirroring `verify_decisions.py`/
  `verify_kinds.py`), then aggregate uniformly. Cleaner long-term contract,
  but touches seven files the issue's "Files" section currently marks as
  "imported, not modified."

  **Option B**: Write one small per-verifier adapter function inside
  `doctor.py` (or a new `doctor_full.py`) that calls each verifier's actual
  reusable unit under its native shape — `_run()` where it exists, else the
  underlying helper (`audit_tree()`, `run_escape_lint()` +
  `run_manifest_check()`, `lint_profiles_dir()`, `verify_documentation()` /
  `check_skill_budget()` / `check_skill_sizes()` / `check_markdown_links()`,
  `_run_validation()` + `_any_failures()`) — and normalizes each result to
  `CheckResult` at the adapter boundary. Matches the issue's "imported, not
  modified" file-scope constraint but means ten distinct adapter shapes
  instead of one uniform call convention.

  > **Selected:** Option B — matches doctor.py's existing `_data()`/`_check()`
  > adapter precedent (used five times already: `_loop_validity_check()`,
  > `_decisions_store_check()`, `_history_db_check()`, `_entry_points_check()`,
  > `_skills_commands_check()`) and honors the "imported, not modified"
  > file-scope constraint on the seven non-conforming verifier modules.

  **Recommended**: Option B — it honors the existing "Files" section's
  no-modification constraint on the verifier modules and follows the
  aggregation precedent already in `doctor.py` (`_loop_validity_data()`,
  350-406, imports `load_and_validate` from `little_loops.fsm.validation`
  directly and folds per-file results into one summary dict — the same
  shape a per-verifier adapter would use).
- Test pattern to follow: `scripts/tests/test_cli_doctor_install_checks.py`
  (`TestLoopValidity`, `TestDecisionsStore`, `TestHistoryDb`) patches the
  underlying callable at the `little_loops.cli.doctor` import site via
  `monkeypatch.setattr`, then asserts on the returned data dict's
  `status`/`severity`/`note` — this is the template for the "mock one
  verifier to fail" AC. No existing test in that file exercises `--json`
  end-to-end or `main_doctor()`'s exit code from a mocked failure;
  `scripts/tests/test_cli_doctor.py` (`TestCheckRegistry`, 619-717) is the
  sibling file for CLI-level/`--json` coverage — check there before adding a
  new `test_cli_doctor_full.py`.
- `--json` output today bypasses `CheckResult` entirely: `_print_report()`
  (`doctor.py:456-486`) builds one flat dict keyed by section name, calling
  each `_*_data()` function directly rather than serializing `CheckResult`
  objects. A `--full` section should follow this same pattern (one dict key
  per aggregated verifier) rather than introducing a second JSON shape.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-25.

**Selected**: Option B — per-verifier adapters normalizing to `CheckResult`

**Reasoning**: `doctor.py` already contains this exact adapter shape five times
over (`_loop_validity_data()`/`_loop_validity_check()` at 350-406 being the
closest precedent, importing `load_and_validate` directly rather than
requiring the source module to expose a uniform contract). Option A's
uniform-`_run()` premise only holds for 3 of the 10 target verifiers and
would require refactoring the other 7 — directly contradicting the issue's
own "Files" section, which marks those modules "imported, not modified," and
touching code already covered by each verifier's dedicated test file.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| Option A | 1/3 | 1/3 | 1/3 | 0/3 | 3/12 |
| Option B | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |

**Key evidence**:
- Option A: Only `verify_decisions.py:_run()`, `verify_kinds.py:_run()`, and
  `verify_cli_allowlist.py:_run()` conform to the uniform shape; the other 7
  verifiers have no `_run()` at all, so Option A requires new refactoring in
  files the issue scopes as read-only, each with its own existing test suite.
- Option B: `doctor.py:350-406`'s `_loop_validity_data()` is a working example
  of the exact pattern — import a module's underlying helper directly, fold
  heterogeneous output into a dict, wrap in `CheckResult` via
  `@register_check`. `TestCheckRegistry` (`test_cli_doctor.py:619-717`) and
  the string-path `monkeypatch.setattr` convention in
  `test_cli_doctor_install_checks.py` directly cover this adapter shape.

## Acceptance Criteria

- [x] `ll-doctor --full` runs and reports results for all ten `ll-verify-*`
      checkers listed above, via direct `_run()` import (no shell-out).
- [x] Default (`ll-doctor` without `--full`) run is unaffected — these checks
      do not execute and do not appear in default output or timing.
- [x] Each verifier's pass/fail maps onto the `--full` section using the
      existing `_STATUS_SYMBOLS` vocabulary.
- [x] `--json --full` includes a section per aggregated verifier.
- [x] New tests exercise `--full` aggregation end-to-end with at least one
      verifier mocked to fail, confirming the failure surfaces in both text
      and `--json` output.

## Resolution

Added a `--full` flag to `ll-doctor` gating a second registry (`_FULL_CHECKS`/
`register_full_check`) of ten adapter functions — one per target verifier
(`ll-verify-docs`, `ll-verify-skill-budget`, `ll-verify-skills`,
`ll-verify-triggers`, `ll-verify-decisions`, `ll-verify-package-data`,
`ll-verify-kinds`, `ll-verify-design-tokens`, `ll-verify-des-audit`,
`ll-check-links`) — following Option B's per-verifier adapter shape. Each
adapter imports the verifier's underlying reusable callable directly
(`_run()` where it exists, else its native helper) and normalizes the result
to a dict with `status`/`note`/`severity`, then wraps it in a `CheckResult`.
`--full` adds a "Full Verification" text section and a `full` key to
`--json` output (one sub-key per verifier); the default (non-`--full`) run
is unaffected since these checks live in a separate list from `_CHECKS` and
`_run_full_checks()` is only invoked when `args.full` is set.

## Files

- `scripts/little_loops/cli/doctor.py` — `--full` flag, verifier aggregation
  registered against the FEAT-2793 registry (`CheckResult` 32-47, `_CHECKS`/
  `register_check` 55-61, `main_doctor` 502-565)
- `scripts/little_loops/cli/verify_decisions.py`,
  `verify_kinds.py`, `verify_cli_allowlist.py` — imported via their existing
  `_run()` functions, not modified
- `scripts/little_loops/cli/verify_triggers.py`, `verify_des_audit.py`,
  `verify_package_data.py`, `verify_design_tokens.py`, `docs.py` — imported
  via their existing helper functions (no uniform `_run()`; see Codebase
  Research Findings above), not modified
- `scripts/tests/test_cli_doctor.py` (`TestCheckRegistry`, 619-717) or a new
  `test_cli_doctor_full.py` — `--full` aggregation coverage

### Codebase Research Findings

_Added by `/ll:refine-issue`:_ the original Files list cited a single
`scripts/little_loops/cli/verify_*.py (and siblings)` glob and
`test_cli_doctor_install_checks.py`; the above splits it into the actual
three conforming modules vs. the five non-conforming ones (see the
Proposed Solution research findings), and corrects the test-file reference
to `test_cli_doctor.py`'s `TestCheckRegistry`, the existing home for
CLI-level `--json`/exit-code coverage.

## Execution Pattern

Depends on FEAT-2793 (registry must exist first). Can run in parallel with
FEAT-2794 (fast default checks) — different checks, same file, low conflict
risk since each adds an independent section.

## Session Log
- `/ll:manage-issue` - 2026-07-25T15:02:16 - `f5a3c0e4-074e-4e25-9ad0-d2bf4695b3c3.jsonl`
- `/ll:ready-issue` - 2026-07-25T14:49:38 - `79ea45e1-5fcc-4bb6-82aa-19d302e393ec.jsonl`
- `/ll:confidence-check` - 2026-07-25T00:00:00 - `4fdd9106-fd28-47b7-b3a4-67e20458f734.jsonl`
- `/ll:decide-issue` - 2026-07-25T14:46:57 - `286e9c58-f46e-4732-8411-3aaa71c803f5.jsonl`
- `/ll:refine-issue` - 2026-07-25T14:42:52 - `214b6a2c-06bc-40b7-ba1e-48ac03a807ad.jsonl`
- `/ll:issue-size-review` - 2026-07-25T00:00:00 - `decomposed-from-FEAT-2763`

---

## Status

**Open** | Created: 2026-07-25 | Priority: P3
