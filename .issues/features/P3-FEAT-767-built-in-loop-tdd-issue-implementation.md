---
id: FEAT-767
type: FEAT
priority: P3
discovered_date: 2026-03-15
discovered_by: capture-issue
---

# FEAT-767: Built-in Loop for TDD Issue Implementation

## Summary

Add a `tdd-issue-impl` built-in loop that implements a single issue using a
Test-Driven Development cycle. The loop accepts an optional issue ID positional
argument (formats: `FEAT-700`, `700`, or `P4-FEAT-700`) and drives an
implement → test → fix → verify pipeline until all tests pass and the issue is
marked complete.

## Current Behavior

No built-in loop targets single-issue TDD implementation. Users who want a
red-green-refactor cycle must manually chain `/ll:manage-issue`, `/ll:check-code`,
and `/ll:run-tests` — a repetitive multi-step flow with no automatic retry or
state tracking.

## Expected Behavior

Running `ll-loop tdd-issue-impl FEAT-700` (or `ll-loop run tdd-issue-impl
--context ISSUE_ID=FEAT-700`) should:

1. Resolve the issue file path from the ID argument.
2. Drive `/ll:manage-issue` to produce an implementation plan (or skip if a
   plan already exists).
3. Enter a red-green loop:
   - **red**: write/locate failing tests that cover the acceptance criteria.
   - **green**: implement the minimum code to pass those tests.
   - **refactor**: run lint + types (`/ll:check-code`) and fix violations.
   - **verify**: run the full test suite; if tests pass and issue criteria are
     met, mark complete — otherwise loop back.
4. Terminate with a clear pass/fail summary and optionally stage a commit.

The loop should support `ll-loop run tdd-issue-impl --dry-run` to preview the
FSM plan and `ll-loop simulate tdd-issue-impl` for interactive walk-through.

## Motivation

TDD is the preferred implementation discipline for this project. A dedicated
built-in loop encodes the discipline into the toolchain, reduces manual
orchestration, and produces a reproducible audit trail via `ll-loop history`.

## Proposed Solution

Add a new YAML file at `scripts/little_loops/loops/tdd-issue-impl.yaml` (the
location from which built-in loops are loaded) with an FSM that encodes:

```
init → resolve_issue → check_plan → plan → write_tests → implement →
run_tests → [pass → check_code → [clean → verify_issue → done |
                                  dirty → fix_quality → run_tests] |
             fail → implement]
```

Key states:

| State | action_type | Action |
|-------|-------------|--------|
| `init` | shell | Validate `${context.ISSUE_ID}` is set; resolve path via `ll-issues show`; store to `.loops/tmp/tdd-{id}.txt` |
| `resolve_issue` | shell | `ll-issues show ${context.ISSUE_ID} --json > .loops/tmp/tdd-meta.json` |
| `check_plan` | shell | Check if a plan file already exists for the issue (grep `.thoughts/` or frontmatter `plan_path`) |
| `plan` | prompt | `/ll:manage-issue feature plan ${context.ISSUE_ID}` |
| `write_tests` | prompt | Write failing tests covering acceptance criteria in the issue |
| `implement` | prompt | `/ll:manage-issue feature implement ${context.ISSUE_ID}` |
| `run_tests` | shell | `python -m pytest ... > .loops/tmp/tdd-test-out.txt 2>&1; tail -20 ...` |
| `check_code` | shell | `ruff check scripts/ && python -m mypy scripts/little_loops/ --ignore-missing-imports` |
| `fix_quality` | prompt | `/ll:check-code fix` |
| `verify_issue` | prompt | `/ll:verify-issues ${context.ISSUE_ID} --auto` |
| `done` | shell | `echo "TDD cycle complete for ${context.ISSUE_ID}"` |

Loop config:

```yaml
context:
  ISSUE_ID: ""   # override with --context ISSUE_ID=FEAT-700
max_iterations: 30
timeout: 7200
on_handoff: spawn
```

The optional positional argument accepted by `ll-loop run` via `--context
ISSUE_ID=<value>` means no changes to the `ll-loop` CLI are needed; the
built-in loop documents the convention in its `description` field.

## Integration Map

- **`scripts/little_loops/loops/`** — new `tdd-issue-impl.yaml` built-in loop file
- **`ll-loop` CLI** — no changes; uses existing `--context KEY=VALUE` mechanism
- **`/ll:manage-issue`** — invoked for plan + implement steps
- **`/ll:check-code`** — invoked for quality gate
- **`/ll:verify-issues`** — invoked for final acceptance check
- **`ll-issues show`** — used to resolve issue ID to metadata

## Implementation Steps

1. Identify the directory where built-in loops are stored (likely
   `scripts/little_loops/loops/` — confirm with `ll-loop list --json`).
2. Study an existing multi-state built-in loop (`issue-refinement` or
   `fix-quality-and-tests`) for FSM YAML conventions.
3. Author `tdd-issue-impl.yaml` with the states above; use `action_type:
   shell` for deterministic checks and `action_type: prompt` for Claude
   invocations.
4. Validate: `ll-loop validate tdd-issue-impl`.
5. Smoke-test: `ll-loop simulate tdd-issue-impl --scenario all-pass`.
6. Add a brief entry to `docs/guides/LOOPS_GUIDE.md` under the built-in loops
   catalogue.

## Impact

- **Scope**: single new YAML file + one doc entry; no Python changes required.
- **Risk**: low — no changes to existing built-in loops or CLI.
- **Value**: encodes TDD workflow as a first-class automation primitive.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/guides/LOOPS_GUIDE.md` | FSM YAML schema and authoring guide |
| `docs/reference/CLI.md` | `ll-loop` flags including `--context KEY=VALUE` |
| `docs/reference/COMMANDS.md` | `/ll:manage-issue`, `/ll:check-code`, `/ll:verify-issues` |

## Labels

`loops`, `tdd`, `automation`, `built-in`

## Status

Active

## Session Log
- `/ll:capture-issue` - 2026-03-15T00:00:00Z
