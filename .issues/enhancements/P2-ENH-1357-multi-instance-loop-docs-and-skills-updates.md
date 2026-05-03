---
id: ENH-1357
type: ENH
priority: P2
parent_issue: ENH-1355
---

# ENH-1357: Multi-Instance Loop — Docs & Skills Updates

## Summary

Decomposed from ENH-1355. Update all documentation and skill files to reflect multi-instance loop semantics introduced by ENH-1354 and ENH-1356. Covers persistence docstrings, API reference, loops guide, skill files (cleanup-loops, rename-loop, analyze-loop, assess-loop), and CLI/commands reference docs.

**Depends on**: ENH-1356 should be merged first (implementation defines the final semantics being documented).

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

## Session Log
- `/ll:issue-size-review` - 2026-05-03T21:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/995ae302-a902-4497-a747-428e14fa83da.jsonl`

---

**Open** | Created: 2026-05-03 | Priority: P2
