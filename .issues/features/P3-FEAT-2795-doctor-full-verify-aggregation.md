---
id: FEAT-2795
type: feature
priority: P3
status: open
parent: FEAT-2763
blocked_by: FEAT-2793
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

## Acceptance Criteria

- [ ] `ll-doctor --full` runs and reports results for all ten `ll-verify-*`
      checkers listed above, via direct `_run()` import (no shell-out).
- [ ] Default (`ll-doctor` without `--full`) run is unaffected — these checks
      do not execute and do not appear in default output or timing.
- [ ] Each verifier's pass/fail maps onto the `--full` section using the
      existing `_STATUS_SYMBOLS` vocabulary.
- [ ] `--json --full` includes a section per aggregated verifier.
- [ ] New tests exercise `--full` aggregation end-to-end with at least one
      verifier mocked to fail, confirming the failure surfaces in both text
      and `--json` output.

## Files

- `scripts/little_loops/cli/doctor.py` — `--full` flag, verifier aggregation
  registered against the FEAT-2793 registry
- `scripts/little_loops/cli/verify_*.py` (and siblings) — imported, not
  modified
- `scripts/tests/test_cli_doctor_install_checks.py` or a new
  `test_cli_doctor_full.py` — `--full` aggregation coverage

## Execution Pattern

Depends on FEAT-2793 (registry must exist first). Can run in parallel with
FEAT-2794 (fast default checks) — different checks, same file, low conflict
risk since each adds an independent section.

## Session Log
- `/ll:issue-size-review` - 2026-07-25T00:00:00 - `decomposed-from-FEAT-2763`

---

## Status

**Open** | Created: 2026-07-25 | Priority: P3
