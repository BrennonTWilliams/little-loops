---
id: ENH-1357
type: ENH
priority: P2

confidence_score: 100
outcome_confidence: 61
score_complexity: 0
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
testable: false
completed_at: 2026-05-03T21:16:09Z
parent: ENH-1355
status: done
---

# ENH-1357: Multi-Instance Loop — Docs & Skills Updates

## Summary

Decomposed from ENH-1355. Update all documentation and skill files to reflect multi-instance loop semantics introduced by ENH-1354 and ENH-1356. Covers persistence docstrings, API reference, loops guide, skill files (cleanup-loops, rename-loop, analyze-loop, assess-loop), and CLI/commands reference docs.

**Depends on**: ENH-1356 should be merged first (implementation defines the final semantics being documented).

## Current Behavior

Documentation and skill files reference `{loop_name}.*` file naming for the `.loops/.running/` directory (e.g., `fix-types.state.json`, `fix-types.events.jsonl`, `fix-types.pid`, `fix-types.lock`). Skills (`cleanup-loops`, `rename-loop`, `analyze-loop`, `assess-loop`) use bare-name paths and lack multi-instance disambiguation.

## Expected Behavior

All documentation and skill files reference `{instance_id}.*` naming (e.g., `fix-types-20260503T122306.state.json`), glob-based `.pid`/`.events.jsonl` patterns in cleanup and rename skills, and multi-instance disambiguation via `ll-loop status <loop_name> --json` in analyze/assess skills.

## Parent Issue

Decomposed from ENH-1355: Multi-Instance Loop — Aggregated CLI (status/stop/resume/list) + Docs & Skills

## Implementation Steps

1. Update `scripts/little_loops/fsm/persistence.py` docstrings — module-level docstring (lines 9–18) and `StatePersistence` class docstring (line 193): replace `{loop_name}.*` file references with `{instance_id}.*`.
2. Update `docs/reference/API.md` — `StatePersistence.__init__` and `PersistentExecutor.__init__` signature blocks (add `instance_id: str | None = None`), `LockManager.acquire`/`release` methods table, and `.running/` directory layout diagram under `StatePersistence` section.
3. Update `docs/guides/LOOPS_GUIDE.md` — `.running/` file layout section: reflect `{instance_id}.*` naming and the aggregated status display.
4. Update `skills/cleanup-loops/SKILL.md` — Steps 6 and 7: replace `rm -f ".loops/.running/<loop_name>.pid"` and `tail -20 ".loops/.running/<loop_name>.events.jsonl"` with glob-based paths (`{loop_name}-*.pid`, `{loop_name}-*.events.jsonl`) or delegate to `ll-loop stop`.
5. Update `skills/rename-loop/SKILL.md` — Step 4: replace `test -f ".loops/.running/<old_name>.pid"` guard with glob (`ls .loops/.running/<old_name>*.pid 2>/dev/null | head -1`) to correctly detect running instances.
6. Update `skills/analyze-loop/SKILL.md` and `skills/assess-loop/SKILL.md` — Step 1: handle duplicate `loop_name` entries from `ll-loop list --running --json` by using `instance_id` (or combined `loop_name:instance_id` key) for user selection disambiguation.
7. Update `docs/reference/COMMANDS.md` — `/ll:cleanup-loops` description (~line 661): replace `<loop_name>.pid` references with glob pattern `{loop_name}-*.pid`.
8. Update `docs/reference/CLI.md` — revise `ll-loop status`, `ll-loop stop`, `ll-loop resume`, `ll-loop list` sections to reflect multi-instance semantics and the new `--json` output shape; `stop` now terminates all instances; `resume` now errors with instance list when 2+ match.
9. Update `docs/generalized-fsm-loop.md` — fix bare-name file references in directory layout diagram (lines 1433–1435, 1518, 1537) to show `{instance-id}.*` naming.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 — `persistence.py` exact targets:**
- Module docstring (lines 1–19): directory tree shows `.running/fix-types.state.json` and `.running/fix-types.events.jsonl` — update to `{instance-id}.state.json` / `{instance-id}.events.jsonl`
- `StatePersistence` class docstring (~line 193): says "Files are stored in `.loops/.running/<loop_name>.*`" — update to `<instance_id>.*`

**Step 4 — `skills/cleanup-loops/SKILL.md` exact targets:**
- Step 6 stale-interrupted block: `rm -f ".loops/.running/<loop_name>.pid"` → `rm -f .loops/.running/<loop_name>-*.pid`
- Step 7 tail command: `tail -20 ".loops/.running/<loop_name>.events.jsonl"` → glob last matching file: `f=$(ls .loops/.running/<loop_name>-*.events.jsonl 2>/dev/null | sort | tail -1); [ -n "$f" ] && tail -20 "$f"`
- Step 1 field table: add `instance_id` field row (the per-instance timestamp stem, e.g. `fix-types-20260503T122306`)
- Step 2 `pid` field description: update from `PID from '.loops/.running/<loop_name>.pid'` → `PID from '.loops/.running/<instance_id>.pid'`

**Step 5 — `skills/rename-loop/SKILL.md` exact target:**
- Step 4 guard: `test -f ".loops/.running/<old_name>.pid"` → `ls .loops/.running/<old_name>-*.pid 2>/dev/null | head -1` (non-empty = running)

**Step 6 — `skills/analyze-loop/SKILL.md` and `skills/assess-loop/SKILL.md` exact targets:**
- Both skills' Step 1 LoopState field list: add `instance_id` field noting it's absent from list output
- Disambiguation approach: when 2+ entries share `loop_name`, follow up with `ll-loop status <loop_name> --json` (includes `instance_id`, `pid`, `log_file`, `log_updated_ago` per instance) to build the user selection list

**Step 7 — `docs/reference/COMMANDS.md` exact target:**
- Lines 650–678, "What it does" step 5: "removes orphaned `.pid` files (stale-interrupted)" → clarify glob-based removal: `rm -f .loops/.running/<loop_name>-*.pid`

**Step 8 — `docs/reference/CLI.md` exact targets:**
- `ll-loop status` section: add note that `--json` output is an array when 2+ instances exist (array of LoopState + `instance_id`, `pid`, `log_file` fields); single instance remains a plain object
- `ll-loop stop` section: add note "Stops all running instances of the named loop (no `--instance-id` selector)"
- `ll-loop resume` section: add `--instance-id` flag row to flags table; document that 2+ resumable instances exits with error listing instance IDs and `"Use --instance-id to select one."`
- `ll-loop list --json` flag description: clarify that with `--running`, output is `LoopState` objects (not loop definition fields); note `instance_id` absent from this output

**Step 9 — `docs/generalized-fsm-loop.md` exact targets:**
- Lines 1433–1435: `.running/` directory tree entries → `fix-types-20260503T122306.state.json` and `fix-types-20260503T122306.events.jsonl`
- Line 1518: `// .loops/.running/<name>.state.json` → `// .loops/.running/<instance-id>.state.json`
- Line 1537: `Events stream to '.loops/.running/<name>.events.jsonl'` → `Events stream to '.loops/.running/<instance-id>.events.jsonl'`

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — module + class docstrings only (no logic changes)
- `docs/reference/API.md`
- `docs/guides/LOOPS_GUIDE.md`
- `skills/cleanup-loops/SKILL.md`
- `skills/rename-loop/SKILL.md`
- `skills/analyze-loop/SKILL.md`
- `skills/assess-loop/SKILL.md`
- `docs/reference/COMMANDS.md`
- `docs/reference/CLI.md`
- `docs/generalized-fsm-loop.md`
- `scripts/little_loops/fsm/concurrency.py` — `LockManager` class docstring (line 85) only: replace `<name>.lock` with `<instance_id>.lock`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` — lines 315–318: `ll-loop stop/status/resume <loop-name>` described as single-target commands with no multi-instance note; add brief note that `stop` terminates all instances and `resume` errors when 2+ match

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**All 10 target files confirmed to exist.** Additional context:

- `scripts/little_loops/fsm/concurrency.py` — `LockManager` lives here (not in `persistence.py`); verify signatures here when writing API.md step 2
- `scripts/little_loops/cli/loop/_helpers.py:_make_instance_id` — generates `{loop_name}-YYYYMMDDTHHMMSS` (e.g. `fix-types-20260503T122306`)
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_status`, `cmd_stop`, `cmd_resume` with multi-instance logic
- `scripts/little_loops/cli/loop/info.py` — `cmd_list`

**Actual API signatures (for `docs/reference/API.md` step 2):**
- `StatePersistence.__init__(self, loop_name: str, loops_dir: Path | None = None, instance_id: str | None = None) -> None`
- `LockManager.acquire(self, loop_name: str, scope: list[str], instance_id: str | None = None) -> bool`
- `LockManager.release(self, loop_name: str, instance_id: str | None = None) -> None`
- File stem logic in `StatePersistence`: `stem = instance_id or loop_name` → files become `{stem}.state.json`, `{stem}.events.jsonl`

**Critical: `ll-loop list --running --json` does NOT include `instance_id`** — output is raw `LoopState.to_dict()` with fields: `loop_name`, `current_state`, `iteration`, `status`, `accumulated_ms`, `started_at`, `updated_at`, etc. When multiple instances of the same `loop_name` are running, entries are indistinguishable by loop_name alone. For step 6 disambiguation, skills should follow up with `ll-loop status <loop_name> --json` (which includes `instance_id` per instance) to build the selection list.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `scripts/little_loops/fsm/concurrency.py` — `LockManager` class docstring (line 85): replace `"Lock files are stored in .loops/.running/<name>.lock"` with `"Lock files are stored in .loops/.running/<instance_id>.lock"` (stem is `instance_id or loop_name`)
11. Update `README.md` — lines 315–318: add brief multi-instance notes: `stop` terminates all instances, `resume` errors when 2+ match, `status` aggregates across instances

## Success Metrics

- All doc references to `{loop_name}.*` in `.running/` context are updated to `{instance_id}.*`.
- `skills/cleanup-loops/SKILL.md` uses glob-based paths for `.pid` and `.events.jsonl`.
- `skills/rename-loop/SKILL.md` uses glob to detect running instances.
- `docs/reference/CLI.md` describes multi-instance semantics for status, stop, resume, and list.
- `ll-check-links` reports no broken links after update.

## Scope Boundaries

- Does NOT modify any runtime logic — purely documentation and skill prose.
- Does NOT modify test files (those are in ENH-1356).
- Does NOT add `--select-instance` flag docs (future work).

## Impact

- **Priority**: P2
- **Effort**: Small — 9 doc/skill files, no code logic changes
- **Risk**: None — documentation-only changes
- **Breaking Change**: No

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-03_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 61/100 → MODERATE

### Outcome Risk Factors
- File count (12 targets across docs/, skills/, scripts/ docstrings, README) tips the complexity rubric to 0/25 — while every change is a prose replacement, the breadth increases the risk of missing a target or introducing an inconsistency across related files.
- No dedicated `test_enh1357_doc_wiring.py` exists yet; verification of doc correctness requires manual review or a new doc wiring test after implementation.
- Skill `.md` files have no unit test coverage — prose changes in cleanup-loops, rename-loop, analyze-loop, and assess-loop can only be validated by manual inspection.

## Labels

`enhancement`, `documentation`, `multi-instance`

## Resolution

Updated all 12 target files to reflect multi-instance loop semantics:
- `{loop_name}.*` → `{instance_id}.*` naming in all `.running/` directory references
- Glob-based PID/events patterns in cleanup-loops and rename-loop skills
- `instance_id` disambiguation via `ll-loop status --json` in analyze-loop and assess-loop
- Multi-instance semantics documented in CLI.md (status/stop/resume/list) and README.md

## Session Log
- `/ll:ready-issue` - 2026-05-03T21:09:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8dbc6f71-d2ca-405b-a38f-6deda185bda0.jsonl`
- `/ll:confidence-check` - 2026-05-03T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/93264a5c-207d-4729-8595-d35da63c07c0.jsonl`
- `/ll:wire-issue` - 2026-05-03T21:03:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/26eb2167-6e61-42dd-b600-23b39b69d0c2.jsonl`
- `/ll:refine-issue` - 2026-05-03T20:57:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2b372827-7847-4180-862d-16c925ec06b3.jsonl`
- `/ll:issue-size-review` - 2026-05-03T21:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/995ae302-a902-4497-a747-428e14fa83da.jsonl`
- `/ll:manage-issue` - 2026-05-03T21:16:09Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

---

**Completed** | Created: 2026-05-03 | Completed: 2026-05-03 | Priority: P2
