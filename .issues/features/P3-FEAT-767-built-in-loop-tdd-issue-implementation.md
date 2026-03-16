---
id: FEAT-767
type: FEAT
priority: P3
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 90
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

## Use Case

**Who**: A developer using the little-loops automation toolchain to implement a backlog issue.

**Context**: They have a specific issue ID (e.g., `FEAT-700`) and want a reproducible, hands-off TDD cycle — write failing tests, implement, fix quality, verify — without manually chaining multiple commands.

**Goal**: Run `ll-loop run tdd-issue-impl --context ISSUE_ID=FEAT-700` and have the loop drive the full red-green-refactor pipeline, retrying on failure, until all tests pass and the issue is marked complete.

**Outcome**: The issue is implemented with a passing test suite, clean linting/types, acceptance criteria verified, and optionally a commit staged — all with a reproducible history in `ll-loop history`.

## Acceptance Criteria

- [ ] `ll-loop validate tdd-issue-impl` exits 0 (valid FSM YAML)
- [ ] `ll-loop list` includes `tdd-issue-impl` in the built-in loop catalogue
- [ ] `ll-loop run tdd-issue-impl --context ISSUE_ID=FEAT-XXX` resolves the issue file, drives the TDD cycle states (`resolve_issue → check_plan → plan → write_tests → implement → run_tests → check_code → verify_issue → done`), and terminates with a clear pass/fail summary
- [ ] `ll-loop run tdd-issue-impl --dry-run` previews the FSM plan without executing any steps
- [ ] `ll-loop simulate tdd-issue-impl` supports interactive walk-through
- [ ] If `ISSUE_ID` is unset or resolves to no file, the `init` state emits a clear error and exits non-zero
- [ ] Test failures route back to `implement`; quality failures route to `fix_quality`; after max iterations the loop exits with a descriptive failure message
- [ ] `docs/guides/LOOPS_GUIDE.md` includes a new entry for `tdd-issue-impl` under the built-in loops catalogue

## Motivation

TDD is the preferred implementation discipline for this project. A dedicated
built-in loop encodes the discipline into the toolchain, reduces manual
orchestration, and produces a reproducible audit trail via `ll-loop history`.

## Proposed Solution

Add a new YAML file at `loops/tdd-issue-impl.yaml` (the project-root `loops/`
directory from which built-in loops are loaded — see `_helpers.py:get_builtin_loops_dir`) with an FSM that encodes:

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

## API/Interface

The public interface is the `ll-loop` CLI invocation contract (no Python API changes):

```bash
# Run TDD cycle for a specific issue
ll-loop run tdd-issue-impl --context ISSUE_ID=FEAT-700

# Preview FSM plan without executing
ll-loop run tdd-issue-impl --dry-run

# Interactive FSM walk-through
ll-loop simulate tdd-issue-impl

# Validate the YAML file structure
ll-loop validate tdd-issue-impl
```

The FSM YAML file (`tdd-issue-impl.yaml`) exposes one context variable:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ISSUE_ID` | string | `""` | Issue ID to implement (e.g., `FEAT-700`, `700`, `P4-FEAT-700`) |

## Integration Map

### Files to Modify
- `loops/tdd-issue-impl.yaml` — new built-in loop file (create; project-root `loops/` is where `get_builtin_loops_dir()` resolves)
- `docs/guides/LOOPS_GUIDE.md` — add entry under built-in loops catalogue

### Dependent Files (Callers/Importers)
- N/A — new file; `ll-loop` CLI discovers built-in loops by scanning the loops directory automatically

### Similar Patterns
- `scripts/little_loops/loops/` — study existing built-in loops (e.g., `issue-refinement`, `fix-quality-and-tests`) for FSM YAML conventions and `action_type: shell` / `action_type: prompt` patterns

### Tests
- TBD — add `ll-loop validate tdd-issue-impl` to the test or CI validation suite; consider a smoke-test scenario

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — new built-in loop catalogue entry

### Configuration
- N/A — no configuration file changes required; invocation uses existing `--context KEY=VALUE` mechanism

## Implementation Steps

1. Place the new loop at `loops/tdd-issue-impl.yaml` — this is the project-root
   `loops/` directory loaded by `get_builtin_loops_dir()` in `scripts/little_loops/cli/loop/_helpers.py:83`.
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

- **Priority**: P3 — useful automation primitive; not blocking active work
- **Effort**: Small — single new YAML file + one doc entry; no Python changes required
- **Risk**: Low — additive only; no changes to existing built-in loops or CLI
- **Breaking Change**: No

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
- `/ll:confidence-check` - 2026-03-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:verify-issues` - 2026-03-16T19:41:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:format-issue` - 2026-03-16T19:37:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:capture-issue` - 2026-03-15T00:00:00Z
