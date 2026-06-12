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

## Scope

- Delete `scripts/little_loops/loops/greenfield-builder.yaml`
- Remove its row from `scripts/little_loops/loops/README.md`
- Remove its entry from `test_expected_loops_exist` in `scripts/tests/test_builtin_loops.py` (~line 74-86) and any other structural tests referencing it
- Remove the `("greenfield-builder", "required-inputs")` entry from `TestValidatorWarningBudget.ALLOWLIST` (the staleness test will demand this)
- Check `eval-driven-development.yaml`'s description (mentions greenfield-builder as a possible parent) and docs/guides references; update to rn-build
- CHANGELOG entry under the release section per repo convention (no `[Unreleased]`)

## Acceptance Criteria

- [ ] `ll-loop list` no longer shows greenfield-builder; `ll-loop run greenfield-builder` fails with a clear unknown-loop error
- [ ] No dangling references in loops/, docs/, skills/, or tests
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py` passes
