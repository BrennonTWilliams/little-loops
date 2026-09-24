---
id: FEAT-3573
type: FEAT
title: Autodev code formatting and quality evidence gate before closure credit
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:13Z'
parent: EPIC-3565
blocks:
- ENH-3577
---

# FEAT-3573: Autodev code formatting and quality evidence gate before closure credit

## Summary

Autodev closes the loop on implementation with `verify_impl_closed`, which checks issue
status (`done|completed|cancelled`). The lifecycle helper is a frontmatter check. Code
quality rests on `/ll:manage-issue` Phase 4's instruction that configured checks must pass.
That is an agent instruction, not a machine-readable result. Specific gaps:

- Phase 4 never runs `project.format_cmd`.
- Phase 4 examples append arguments to `project.test_cmd` (e.g. a trailing `tests/ -v`),
  which is wrong when the configured command is already complete.
- No structured record of which checks ran and passed against the resulting revision.
- `oracles/code-run-gate` exists but is outside autodev's call graph and has no format stage.
- `cancelled` closures are counted as passed alongside implemented ones in `finalize_done`.

## Current Behavior

Autodev credits closure from frontmatter status alone. `manage-issue` runs checks by instruction, never runs `format_cmd`, and appends arguments to configured commands.

## Expected Behavior

Closure credit requires a recorded passing format/lint/type/test result for the resulting revision, with formatting limited to changed files.

## Motivation

A frontmatter flip to `done` is the only closure evidence autodev consumes. Tamper and work
guards help, but nothing establishes that formatting, lint, types and tests passed on the
final change.

## Proposed Solution

After `implement_current`, run a deterministic quality gate (reuse or extend
`oracles/code-run-gate`, or a shared Python runner) that:

1. Runs formatting **scoped to the files changed by the implementation**. A bare
   `ruff format scripts/` in this repo reformats ~30 unrelated files because main carries
   format drift, so an unscoped format stage would pollute every commit.
2. Runs `lint_cmd`, `type_cmd` and `test_cmd` exactly as configured.
3. Records structured results tied to the resulting commit.
4. Gates `finalize_done`'s passed bucket on that result, with bounded repair/retest.

Avoid running the full suite twice (once in manage-issue, once in the gate). Pick one owner.
Split `cancelled` from `closed` in the summary.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `implement_current`, `verify_impl_closed`, `finalize_done`
- `scripts/little_loops/loops/oracles/code-run-gate.yaml`
- `skills/manage-issue/SKILL.md` — Phase 4 verification commands

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_lifecycle.py` — lifecycle verification
- `scripts/little_loops/issue_manager.py` — ll-auto

### Similar Patterns
- `rn-implement.yaml` usage of `oracles/code-run-gate`

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop` finalize tests

### Documentation
- `docs/guides/` loop guide for autodev, if it documents closure semantics

### Configuration
- `project.format_cmd`, `lint_cmd`, `type_cmd`, `test_cmd`

## Implementation Steps

1. Decide the single owner of the post-implementation quality run (manage-issue vs. an autodev gate)
2. Extend `oracles/code-run-gate` (or a shared runner) with a changed-files format stage
3. Persist structured results per revision; gate `finalize_done` promotion on them
4. Fix manage-issue Phase 4 to use configured commands verbatim
5. Split cancelled from implemented closures in `summary.json`

## Impact

- **Priority**: P3
- **Effort**: Large
- **Risk**: Medium. Adds wall-clock time per issue.

## Acceptance Criteria

- [ ] Closure credit requires a recorded passing quality result for the resulting revision
- [ ] Formatting runs only on changed files
- [ ] `manage-issue` uses configured commands verbatim
- [ ] `summary.json` distinguishes cancelled from implemented closures

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-24T19:42:31 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`
