---
id: BUG-2136
title: sprint-refine-and-implement only accepts sprint files, dead-ends on EPIC ids
type: BUG
priority: P2
status: done
captured_at: '2026-06-13T21:55:00Z'
completed_at: '2026-06-13T21:55:00Z'
discovered_date: '2026-06-13'
size: Small
---

# BUG-2136: sprint-refine-and-implement only accepts sprint files, dead-ends on EPIC ids

## Summary

`ll-loop run sprint-refine-and-implement EPIC-1918` terminated after a single
iteration doing no work:

```
[1/500] get_next_issue -> exit: 1  ✗ no  -> done
Loop completed: done (1 iterations, 0.0s)
```

The positional arg `EPIC-1918` was correctly injected into `context.sprint_name`
(via `input_key: sprint_name`), but the `get_next_issue` state resolved it with a
hard-coded shell lookup for a sprint **file** only:

```bash
SPRINT_FILE=".sprints/${context.sprint_name}.yaml"
if [ ! -f "$SPRINT_FILE" ]; then ... exit 1 ; fi
```

`.sprints/EPIC-1918.yaml` does not exist, so the state exited 1 and routed
straight to `done`. The loop never understood EPIC ids — only named sprint files.

## Root Cause

- **File**: `scripts/little_loops/loops/sprint-refine-and-implement.yaml`
- **get_next_issue**: hard-coded `grep '^ *-' .sprints/<name>.yaml | sed ...`
  parse of a sprint file, bypassing the existing dual-shape resolver.
- A resolver that already handles both shapes exists and was simply not used:
  `SprintManager.load_or_resolve(arg)` (`scripts/little_loops/sprint.py:286-361`)
  accepts **either** a sprint name (`.sprints/<name>.yaml`) **or** an `EPIC-NNN`
  id, returning a `Sprint` whose `.issues` is an ordered list of issue-id
  strings. The sibling `goal-cluster` loop already relies on this resolution.

### Non-issue ruled out

The completion-tracking that prevents already-implemented issues from being
re-picked is intact and was left untouched: the `oracles/implement-issue-chain`
sub-loop's `get_passed_issues` state appends passed issue ids to
`${run_dir}/sprint-refine-and-implement-skipped.txt`
(`implement-issue-chain.yaml:35-36`) — the same SKIP_FILE `get_next_issue`
reads. No "mark done" state was needed; this fix is scoped purely to input
resolution.

## Resolution

- **Status**: Done
- **Closed**: 2026-06-13

`get_next_issue` now resolves its input via `SprintManager.load_or_resolve`,
then filters the returned issue list against the SKIP_FILE exactly as before.
The non-obvious detail: the EPIC branch of `load_or_resolve` requires a config —
a bare `SprintManager()` has `config=None` and silently falls back to the file
path, returning `None` for EPIC ids. The resolver is therefore constructed as
`SprintManager(config=BRConfig(Path.cwd()))`. Sprint-name resolution works with
or without config (it reads `.sprints/` directly), so passing config is harmless
for that path and required only for EPICs.

The three failure paths (empty arg, unresolvable input, resolved-but-empty) each
`exit 1` with a distinct stderr message and route to `done`, replacing the
single misleading "Sprint not found" message and making the
EPIC-with-no-active-children case explicit.

State `action_type: shell`, `capture: input`, and the
`on_yes/on_no/on_error` routing were preserved unchanged.

## Files Modified

- `scripts/little_loops/loops/sprint-refine-and-implement.yaml`
  - `get_next_issue.action` — rewritten as a Python heredoc calling
    `SprintManager(config=BRConfig(Path.cwd())).load_or_resolve(arg)`, mirroring
    the `goal-cluster` `load_goals` pattern
  - `description` / `context.sprint_name` comment — now state
    `<sprint-name|EPIC-NNN>`
- `scripts/tests/test_builtin_loops.py`
  - `TestSprintRefineAndImplementLoop` — added
    `test_get_next_issue_resolves_sprint_or_epic` (asserts `load_or_resolve` +
    `EPIC` advertised in the action) and `test_get_next_issue_still_captures_input`

## Verification

- `ll-loop validate sprint-refine-and-implement` — valid.
- `ll-loop run sprint-refine-and-implement EPIC-1918 --max-iterations 1` —
  `get_next_issue` now `exit: 0`, emits `ENH-2130` (first dependency-ordered
  child), routes to `refine_issue` (was: immediate `done`).
- Sprint-name regression: `ll-loop run sprint-refine-and-implement bug-fixes
  --max-iterations 1` resolves and emits `BUG-685` → `refine_issue`.
- Error path: `ll-loop run sprint-refine-and-implement NoSuchSprintXYZ
  --max-iterations 1` exits cleanly to `done` with a distinct error message.
- `pytest scripts/tests/test_builtin_loops.py` — 828 passed.

## Impact

`sprint-refine-and-implement` now accepts both a named sprint and an EPIC id,
matching how `goal-cluster` already resolves the same dual shape. No behavior
change for existing sprint-file callers; the file-based path is preserved.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-14T02:51:34 - `371d5ee2-4b34-466c-84db-32c79663004d.jsonl`
