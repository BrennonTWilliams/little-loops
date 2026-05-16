---
id: ENH-777
type: ENH
priority: P3
title: "SPRINT_GUIDE audit: accuracy and completeness findings"
status: active
---

## Summary

Audit of `docs/guides/SPRINT_GUIDE.md` found 3 accuracy issues and 6 completeness gaps. One auto-fix was applied directly (A1). The remaining 8 findings are tracked here.

## Current Behavior

`docs/guides/SPRINT_GUIDE.md` contains 2 accuracy issues and 6 completeness gaps:
- Retry logic is documented as applying to all failures, but it only applies to multi-issue parallel waves
- `options.max_iterations` field is missing from the sprint YAML anatomy table
- `ll-sprint delete`, `--only`, `--skip-analysis`, `--quiet`, `--type`, `--handoff-threshold`, `--json` flags are undocumented
- Pre-flight auto-skip of already-completed issues is not documented
- `ll-sprint create --skip` and `--type` flags are not documented

## Expected Behavior

All 8 findings resolved:
- A2: Retry description qualified to clarify it only applies to parallel-wave failures
- A3: `max_iterations` row added to the sprint options table
- C1–C6: All undocumented subcommands and flags documented in relevant sections

## Proposed Solution

Each finding includes its own targeted fix instruction. See **Accuracy Findings** and **Completeness Findings** below for specific file locations and suggested text. No code changes required — documentation updates only.

## Scope Boundaries

- Only `docs/guides/SPRINT_GUIDE.md` and its inline examples
- No code changes (all referenced behaviors are correctly implemented)
- A1 was already auto-fixed and is not tracked here

## Impact

- **Priority**: P3 — Documentation accuracy issue; no user-facing behavior broken
- **Effort**: Small — 8 targeted doc edits, no code changes
- **Risk**: Low — Documentation-only changes
- **Breaking Change**: No

## Labels

`documentation`, `sprint`, `accuracy`, `completeness`

---

## Accuracy Findings

### A2 — Retry logic only applies to multi-issue parallel waves (lines 224–232)

The "Failed Issues" section states:
> "If an issue fails within a wave, the runner: 1. Records the failure, 2. Retries once sequentially (outside the worktree)…"

The sequential retry (`run.py:404–436`, `ParallelOrchestrator` path) only runs for issues that fail during **multi-issue parallel waves**. Issues that fail in **single-issue waves** are immediately marked failed — no retry.

**Fix:** Qualify the retry description to make clear it only applies to parallel-wave failures.

### A3 — `options.max_iterations` missing from sprint YAML anatomy (lines 86–93)

`SprintOptions` (`sprint.py:19–38`) has a third supported field: `max_iterations` (default: `100`). The field table shows only `timeout` and `max_workers`.

**Fix:** Add a row to the field table:
```
| `options.max_iterations` | no | Max Claude iterations per issue (default: 100) |
```

---

## Completeness Findings

### C1 — `ll-sprint delete` subcommand undocumented

`ll-sprint delete <name>` is fully implemented (`manage.py:55–63`) but never mentioned in the guide — not in "Editing a Sprint," "Inspecting Sprints," or any examples.

**Fix:** Add `ll-sprint delete sprint-1` to the "Editing a Sprint" or "Inspecting Sprints" section.

### C2 — `ll-sprint run --only` flag not documented

`--only <ids>` restricts execution to a specific subset of issues in the sprint (allowlist, distinct from `--skip`). Implemented via `add_only_arg` (`__init__.py:129`).

**Fix:** Add to the run examples: `ll-sprint run sprint-name --only BUG-001,FEAT-010`

### C3 — `--skip-analysis` not documented for `run` and `show`

Both `ll-sprint run` and `ll-sprint show` accept `--skip-analysis` to bypass the pre-execution dependency analysis step. Registered at `__init__.py:130, 147`.

**Fix:** Add to run and show example blocks.

### C4 — Pre-flight auto-skip of already-completed issues not documented

Before wave execution, `run.py:143–164` scans for issues already in `completed/` and skips them silently. If all issues are completed, the sprint exits with success. Not mentioned in the "Pre-flight" or "Resume" sections.

**Fix:** Add a note to the "Pre-flight" section explaining this behavior.

### C5 — `ll-sprint create --skip` and `--type` flags not documented

The `create` subcommand supports `--skip <ids>` (exclude specific issues) and `--type <types>` (filter by issue type). Implemented in `create.py:17–36`. The "Direct CLI" examples only show `--issues`, `--description`, `--max-workers`, `--timeout`.

**Fix:** Add examples showing `--skip` and `--type` usage.

### C6 — Minor undocumented flags

| Flag | Subcommand | Description |
|------|-----------|-------------|
| `--json` | `list` | Output as JSON array |
| `--quiet` | `run` | Suppress progress output |
| `--type <types>` | `run` | Filter issues by type at run time |
| `--handoff-threshold <n>` | `run` | Context window handoff threshold (1–100) |

**Fix:** Brief mentions in the relevant CLI example blocks.

---

## Files

- `docs/guides/SPRINT_GUIDE.md` — primary file to update
- `scripts/little_loops/cli/sprint/run.py` — retry logic (A2), pre-completion skip (C4)
- `scripts/little_loops/cli/sprint/__init__.py` — flag registration (C2, C3, C6)
- `scripts/little_loops/cli/sprint/create.py` — create flags (C5)
- `scripts/little_loops/cli/sprint/manage.py` — delete subcommand (C1)
- `scripts/little_loops/sprint.py` — `SprintOptions` (A3)


## Resolution

All 8 findings resolved in `docs/guides/SPRINT_GUIDE.md`:
- **A2**: Retry description qualified — now states retries only apply to multi-issue parallel-wave failures; single-issue wave failures are immediately marked failed
- **A3**: `options.max_iterations` row added to the sprint YAML anatomy table
- **C1**: `ll-sprint delete sprint-1` added to the "Editing a Sprint" examples
- **C2**: `--only BUG-001,FEAT-010` example added to run section
- **C3**: `--skip-analysis` added to both run and show example blocks
- **C4**: Pre-flight auto-skip behavior documented in the "Pre-flight" section
- **C5**: `--skip` and `--type` examples added to the "Direct CLI" create section
- **C6**: `--json` (list), `--quiet` (run), `--type` (run), `--handoff-threshold` (run) all documented in relevant example blocks

## Status

**Completed** | Created: 2026-03-16 | Resolved: 2026-03-16 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-03-16T20:30:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/400f9675-d92a-409d-9e57-9a61a1134490.jsonl`
- `/ll:verify-issues` - 2026-03-16T20:15:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2f8fb9f-5760-41e6-b718-11e29dd2cd54.jsonl`
- `/ll:manage-issue` - 2026-03-16T20:36:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
