---
id: ENH-2100
title: Remove deprecated greenfield-builder loop (superseded by rn-build)
type: ENH
priority: P4
status: open
captured_at: '2026-06-12T14:10:00Z'
discovered_date: '2026-06-12'
discovered_by: fsm-loop-audit
parent: EPIC-1811
---

# ENH-2100: Remove deprecated greenfield-builder loop

## Summary

`scripts/little_loops/loops/greenfield-builder.yaml` is marked DEPRECATED in favor of `rn-build` (header + loops/README.md) but still ships, still appears in `ll-loop list`, and is the one builtin loop with an unfixed `required_inputs` warning (deliberately skipped in the 2026-06-12 audit — don't polish deprecated code). Schedule removal for the next minor release.

## Current Behavior

`greenfield-builder.yaml` ships with the project and appears in `ll-loop list` output despite being deprecated. It carries an unfixed `required_inputs` validation warning that was deliberately left unresolved because polishing deprecated code is wasteful. The loop header and `loops/README.md` both mark it as deprecated, but no removal has been scheduled.

## Expected Behavior

After removal, `ll-loop list` no longer shows `greenfield-builder`. Running `ll-loop run greenfield-builder` fails with a clear unknown-loop error. No dangling references remain in `loops/`, `docs/`, `skills/`, or tests. The `TestValidatorWarningBudget.ALLOWLIST` no longer includes the `("greenfield-builder", "required-inputs")` entry, and all structural tests pass.

## Motivation

- **Dead code elimination**: A deprecated loop with an unfixed warning is dead weight — it bloats `ll-loop list` output and misleads users who discover it there.
- **Maintenance clarity**: Keeping the warning in `TestValidatorWarningBudget.ALLOWLIST` indefinitely forces future maintainers to understand why it exists; removal is the honest signal.
- **Clean audit surface**: The 2026-06-12 builtin-loop audit explicitly deferred this; scheduling it now closes the open audit item.

## Scope Boundaries

- **In scope**:
  - Delete `scripts/little_loops/loops/greenfield-builder.yaml`
  - Remove its row from `scripts/little_loops/loops/README.md`
  - Remove its entry from `test_expected_loops_exist` in `scripts/tests/test_builtin_loops.py` (~line 74-86) and any other structural tests referencing it
  - Remove the `("greenfield-builder", "required-inputs")` entry from `TestValidatorWarningBudget.ALLOWLIST`
  - Update `eval-driven-development.yaml`'s description (mentions greenfield-builder as a possible parent) to reference `rn-build`
  - Update any `docs/guides/` references from greenfield-builder to rn-build
  - CHANGELOG entry under the release section per repo convention (no `[Unreleased]`)
- **Out of scope**: Changes to `rn-build` itself; migration tooling or user-facing warnings

## Acceptance Criteria

- [ ] `ll-loop list` no longer shows greenfield-builder; `ll-loop run greenfield-builder` fails with a clear unknown-loop error
- [ ] No dangling references in loops/, docs/, skills/, or tests
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py` passes

## Implementation Steps

1. Delete `scripts/little_loops/loops/greenfield-builder.yaml`
2. Remove the `greenfield-builder` row from `scripts/little_loops/loops/README.md`
3. Remove test entries: `test_expected_loops_exist` block and `TestValidatorWarningBudget.ALLOWLIST` entry in `test_builtin_loops.py`
4. Update `eval-driven-development.yaml` description and any `docs/guides/` references from greenfield-builder → rn-build
5. Add CHANGELOG entry under the active release section
6. Run `python -m pytest scripts/tests/test_builtin_loops.py` and `ll-loop list` to verify

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/greenfield-builder.yaml` (delete)
- `scripts/little_loops/loops/README.md` (remove row)
- `scripts/tests/test_builtin_loops.py` (remove from `test_expected_loops_exist` ~line 74-86; remove from `TestValidatorWarningBudget.ALLOWLIST`)
- `CHANGELOG.md` (add entry)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/eval-driven-development.yaml` (description mentions greenfield-builder as a possible parent loop)
- TBD — run `grep -r "greenfield-builder" scripts/ docs/ skills/` to find any remaining references

### Similar Patterns
- N/A — no other loops are currently in a deprecated-but-not-removed state

### Tests
- `scripts/tests/test_builtin_loops.py` (primary; structural loop existence + validator warning budget tests)

### Documentation
- `docs/guides/` — grep for greenfield-builder references and redirect to rn-build
- `scripts/little_loops/loops/README.md` — remove table row

### Configuration
- N/A

## Impact

- **Priority**: P4 — Low; purely cleanup with no user-facing urgency
- **Effort**: Small — delete one file, update three others, one test fix
- **Risk**: Low — removing a deprecated artifact with a clear replacement; tests will catch any missed references
- **Breaking Change**: No — greenfield-builder is already marked deprecated; users should have migrated to rn-build

## Labels

`cleanup`, `deprecated-removal`, `loops`

## Status

**Open** | Created: 2026-06-12 | Priority: P4


## Session Log
- `/ll:format-issue` - 2026-06-12T20:24:24 - `a1ec72f5-b2fb-4515-a490-94794292cae6.jsonl`
