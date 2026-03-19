---
id: BUG-817
type: BUG
priority: P2
status: open
discovered_date: 2026-03-19
discovered_by: capture-issue
---

# BUG-817: Cross-project /tmp path conflicts cause silent data corruption

## Summary

Multiple components in the CLI, commands, and skills use bare `/tmp/<name>` paths with no project identifier. When the same tool runs in two different projects simultaneously on one machine, these paths collide, causing silent data corruption, stale stall-detection state, deleted scratch files, and garbled release notes.

## Current Behavior

Nine locations write to unscoped `/tmp/` paths:

1. **`scripts/little_loops/fsm/evaluators.py:421-423`** — `evaluate_diff_stall()` writes `/tmp/ll-diff-stall-{cache_key}.txt` and `.count`. The `cache_key` is hashed from scope (file paths like `["scripts/"]`), **not** from CWD. Two projects with identically-named source dirs share the same key and stomp each other's stall-detection state.
2. **`.claude/CLAUDE.md` scratch pad section** — Instructs Claude to write large outputs to `/tmp/ll-scratch/<name>.txt`. All projects share this global directory.
3. **`hooks/scripts/session-cleanup.sh:17`** — `rm -rf "/tmp/ll-scratch"` deletes *all* projects' scratch files when any project's session ends.
4. **`commands/manage-release.md:337`** — `gh release create ... --notes-file /tmp/ll-release-notes.md` collides when two projects run manage-release simultaneously.
5. **`commands/normalize-issues.md:169,172,174`** — Three references to `/tmp/issue_id_map.txt` for intermediate deduplication work.
6. **`skills/create-loop/loop-types.md:797`** — Loop template example uses `/tmp/harness-items.txt`, so generated loops embed a global path.
7. **`skills/review-loop/SKILL.md:168-171`** + **`reference.md:333-356`** — QC-10/FA-3 warns only about unreset shared state in `/tmp/`, not the cross-project bare path problem.
8. **`scripts/tests/test_fsm_evaluators.py:984-997`** — `clean_state_files` fixture patches paths matching `p.startswith("/tmp/ll-diff-stall-")`, which will break after fix #1.
9. **`scripts/tests/test_builtin_loops.py:222-226`** — `AFFECTED_LOOPS` list is missing `pr-review-cycle` (BUG-744 fixed that loop's YAML but the test never included it).

## Expected Behavior

All intermediate files written during a loop iteration must be project-scoped. The established pattern (from BUG-744, resolved 2026-03-14) is **`.loops/tmp/<name>`** relative to CWD — project-scoped by nature, no hashing needed.

The `review-loop` skill's QC-10/FA-3 check should flag bare `/tmp/<name>` paths (not `.loops/tmp/`) as a cross-project safety Warning.

## Motivation

This is a user-level install model: multiple projects run concurrently on one machine. Silent data corruption is the worst failure mode — the user sees no error but gets wrong stall-detection, wrong release notes, or scratch files deleted mid-session by an unrelated project ending. The fix pattern is already established (BUG-744) and is a mechanical rename with mkdir guards.

## Root Cause

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Anchor**: `in function evaluate_diff_stall()`
- **Cause**: Cache key hashed from `scope` argument (source paths), not from `Path.cwd()`. Two projects whose source dirs share the same names (e.g., both have `["scripts/"]`) generate identical keys and write to the same `/tmp/` file.

Secondary causes in commands/skills/hooks: ad-hoc `/tmp/` usage with no project qualifier, predating the BUG-744 fix pattern.

## Steps to Reproduce

1. Open two terminal sessions pointing to two different projects that both use `evaluate_diff_stall` with `scope=["scripts/"]`.
2. Trigger a diff-stall check in both sessions within the same loop cycle.
3. Observe: one project's stall counter is overwritten by the other; stall detection fires at wrong threshold or resets unexpectedly.

## Proposed Solution

Apply the BUG-744 pattern (`Path.cwd() / ".loops" / "tmp" / name`) consistently:

| Location | Change |
|----------|--------|
| `evaluators.py:evaluate_diff_stall()` | `Path("/tmp/ll-diff-stall-*")` → `Path.cwd() / ".loops/tmp" / f"ll-diff-stall-{cache_key}.txt"` + `mkdir(parents=True, exist_ok=True)` |
| `.claude/CLAUDE.md` scratch pad | `/tmp/ll-scratch/` → `.loops/tmp/scratch/` in both example commands |
| `hooks/scripts/session-cleanup.sh:17` | `rm -rf "/tmp/ll-scratch"` → `rm -rf ".loops/tmp/scratch" 2>/dev/null \|\| true` |
| `commands/manage-release.md:337` | `/tmp/ll-release-notes.md` → `.loops/tmp/ll-release-notes.md`; add `mkdir -p .loops/tmp` on line before |
| `commands/normalize-issues.md:169,172,174` | `/tmp/issue_id_map.txt` → `.loops/tmp/issue_id_map.txt`; add `mkdir -p .loops/tmp` before the `find` pipeline |
| `skills/create-loop/loop-types.md:797` | Template `/tmp/harness-items.txt` → `.loops/tmp/harness-items.txt` |
| `skills/review-loop/SKILL.md` QC-10 | Extend FA-3 to add Warning when action text writes to bare `/tmp/<name>` (not `.loops/tmp/`) |
| `skills/review-loop/reference.md` FA-3 | Update fix template "After" example to show `.loops/tmp/` |
| `test_fsm_evaluators.py:clean_state_files` | Replace path-patching with `monkeypatch.chdir(tmp_path)` + create `.loops/tmp/` under `tmp_path` |
| `test_builtin_loops.py:AFFECTED_LOOPS` | Add `"pr-review-cycle"` to the list |

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — core fix
- `.claude/CLAUDE.md` — scratch pad examples
- `hooks/scripts/session-cleanup.sh` — cleanup hook
- `commands/manage-release.md` — release temp file
- `commands/normalize-issues.md` — dedup temp file
- `skills/create-loop/loop-types.md` — loop template
- `skills/review-loop/SKILL.md` — QC-10/FA-3 check
- `skills/review-loop/reference.md` — FA-3 fix template

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/evaluators.py` is imported by FSM orchestrator; no interface change, only internal paths change

### Similar Patterns
- `.loops/general-task.yaml`, `issue-refinement`, `fix-quality-and-tests`, `dead-code-cleanup` built-in loops already use `.loops/tmp/` (fixed in BUG-744)

### Tests
- `scripts/tests/test_fsm_evaluators.py` — fixture update required (clean_state_files)
- `scripts/tests/test_builtin_loops.py` — add `pr-review-cycle` to AFFECTED_LOOPS

### Documentation
- `skills/review-loop/SKILL.md` — extended QC check
- `skills/review-loop/reference.md` — updated fix example
- `.claude/CLAUDE.md` — scratch pad path examples

### Configuration
- N/A

## Implementation Steps

1. Fix `evaluate_diff_stall()` in `evaluators.py` — change both file paths to `Path.cwd() / ".loops/tmp" / ...` with `mkdir(parents=True, exist_ok=True)`
2. Update `.claude/CLAUDE.md` scratch pad examples and `session-cleanup.sh` atomically
3. Update `commands/manage-release.md` and `commands/normalize-issues.md`
4. Update `skills/create-loop/loop-types.md` template
5. Extend `skills/review-loop/SKILL.md` QC-10/FA-3 and update `reference.md` fix template
6. Fix test fixtures: `clean_state_files` in `test_fsm_evaluators.py` + add `pr-review-cycle` to `test_builtin_loops.py`
7. Verify: run pytest, run loop validator on built-in loops, grep for remaining bare `/tmp/ll-`

## Impact

- **Priority**: P2 — Silent data corruption; no error surfaced to user; affects anyone running two ll-powered projects concurrently
- **Effort**: Small — Mechanical path renames + mkdir guards; fix pattern is established
- **Risk**: Low — Internal paths only; no API/interface changes; test suite catches regressions
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `data-integrity`, `cross-project`, `tmp-paths`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-03-19T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/50a1c997-86c0-49fe-9276-210a71c2c9da.jsonl`

---

**Open** | Created: 2026-03-19 | Priority: P2
