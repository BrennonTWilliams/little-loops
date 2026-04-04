---
id: ENH-944
type: ENH
priority: P3
status: backlog
discovered_date: 2026-04-03
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 72
---

# ENH-944: Loop history saved to per-run timestamped folder

## Summary

Loop history in `.loops/.history/` is currently organized as `<loop_name>/<run_id>/`, creating a two-level nested structure. Each run should instead be stored directly as a top-level folder named `[TIMESTAMP]-[LOOP-NAME]`, making individual runs first-class entries and making the history directory browsable at a glance. The `/ll:analyze-loop` skill's Step 1 resolution should also be updated to derive the target run directly from the flat folder names rather than via `ll-loop history` CLI output.

## Current Behavior

Completed, failed, or terminated loop runs are archived to:

```
.loops/.history/
  general-task/
    2026-04-01T120000/
      state.json
      events.jsonl
  issue-refinement/
    2026-04-02T090000/
      state.json
      events.jsonl
```

The loop name is a directory, and individual runs are subdirectories named by compact timestamp. To see all runs you must traverse two levels.

## Expected Behavior

Each run is archived to a flat top-level folder combining timestamp and loop name:

```
.loops/.history/
  2026-04-01T120000-general-task/
    state.json
    events.jsonl
  2026-04-02T090000-issue-refinement/
    state.json
    events.jsonl
  2026-04-02T143000-general-task/
    state.json
    events.jsonl
```

All runs across all loops are visible at a single level. Sorting by name gives chronological order across loops.

## Motivation

The nested structure obscures the timeline of activity — you have to drill into each loop-name folder to see when things ran. A flat `[TIMESTAMP]-[LOOP-NAME]` structure makes the history directory scannable: `ls .loops/.history/` immediately shows recency and loop identity. It also removes a level of indirection from all history-reading code paths and aligns with how logs and artefacts from other tools (e.g. CI) are typically organized.

## Proposed Solution

Changes are localized to `scripts/little_loops/fsm/persistence.py`.

**`archive_run()` (line ~279):** Change the archive destination from two-level to flat:

```python
# Before
archive_dir = self.loops_dir / HISTORY_DIR / self.loop_name / run_id

# After
run_folder = f"{run_id}-{self.loop_name}"
archive_dir = self.loops_dir / HISTORY_DIR / run_folder
```

**`list_run_history()` (line ~577):** Change glob pattern to find all folders whose name ends with `-<loop_name>`:

```python
# Before
history_loop_dir = base_dir / HISTORY_DIR / loop_name
for state_file in history_loop_dir.glob("*/state.json"):

# After
history_dir = base_dir / HISTORY_DIR
for state_file in history_dir.glob(f"*-{loop_name}/state.json"):
```

**`get_archived_events()` (line ~608):** Update the path construction to match the flat structure:

```python
# Before
events_file = base_dir / HISTORY_DIR / loop_name / run_id / "events.jsonl"

# After
run_folder = f"{run_id}-{loop_name}"
events_file = base_dir / HISTORY_DIR / run_folder / "events.jsonl"
```

**`_list_archived_runs()` (`cli/loop/info.py:353`):** Switch from iterating `history_base` (nested) to filtering the flat history dir:

```python
# Before
history_base = loops_dir / HISTORY_DIR / loop_name
for run_dir in sorted(history_base.iterdir(), ...):
    runs.append((run_dir.name, state))  # run_dir.name was the run_id

# After
history_base = loops_dir / HISTORY_DIR
pattern = re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{6})-(.+)$')
for run_dir in sorted(history_base.iterdir(), ...):
    m = pattern.match(run_dir.name)
    if m and m.group(2) == loop_name:
        run_id = m.group(1)   # "2024-01-15T103000"
        runs.append((run_id, state))
```

**`run_id` parsing — critical detail:** The timestamp `2024-01-15T103000` contains hyphens, so `folder_name.split("-")` is ambiguous (yields `["2024", "01", "15T103000", ...]`). Use a regex or fixed-width slice instead:

```python
import re
_RUN_FOLDER = re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{6})-(.+)$')

def _parse_run_folder(name: str) -> tuple[str, str] | None:
    """Return (run_id, loop_name) from flat folder name, or None if not matching."""
    m = _RUN_FOLDER.match(name)
    return (m.group(1), m.group(2)) if m else None
```

Add this helper near the top of `persistence.py` or as a module-level constant. Both `list_run_history()` and `_list_archived_runs()` will use it.

**Migration:** Use a compatibility shim in `list_run_history()` (preferred over a one-time script — no migration utilities exist in the codebase). After reading `history_dir.glob("*/state.json")` with the flat pattern, also check `history_dir / loop_name` and yield any runs found there with a deprecation warning. This prevents orphaning existing data immediately after the code change. Remove the shim in a follow-up issue once all real `.loops/.history/` folders have been migrated manually.

**`/ll:analyze-loop` skill — Step 1 resolution:** With the flat structure, the skill can resolve the target run folder directly from `.loops/.history/` rather than calling `ll-loop history <loop_name> --json`:

```bash
# No argument — most recent run across all loops
ls -d .loops/.history/*/  | sort | tail -1
# → e.g. ".loops/.history/2026-04-03T120000-general-task/"

# Loop name provided — most recent run for that loop
ls -d .loops/.history/*-<loop_name>/  | sort | tail -1
# → e.g. ".loops/.history/2026-04-02T090000-issue-refinement/"
```

The skill extracts the `run_id` (timestamp portion) and `loop_name` from the folder name by splitting on the first `-` that precedes the loop name. Once the folder is resolved the rest of the analysis steps are unchanged.

- **No argument**: list all `[TIMESTAMP]-[LOOP-NAME]` folders, sort lexicographically (ISO timestamps sort chronologically), select the last entry, parse `loop_name` and `run_id` from it.
- **Loop name provided**: glob `*-<loop_name>` folders, sort, select last entry. If none found, report "No archived runs found for `<loop_name>`." and stop.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — `archive_run()` (line 279), `list_run_history()` (line 562), `get_archived_events()` (line 608)
- `scripts/little_loops/cli/loop/info.py` — `_list_archived_runs()` (line 353) hardcodes `loops_dir / HISTORY_DIR / loop_name`; must switch to scanning the flat dir filtered by `*-{loop_name}`
- `skills/analyze-loop/SKILL.md` — Step 1 calls `ll-loop history <loop_name> --json`; update to scan `.loops/.history/` folder names directly

### Dependent / Caller Files
- `scripts/little_loops/cli/loop/__init__.py:355` — dispatches `cmd_history(args.loop, ...)` which calls `_list_archived_runs` and `get_archived_events`
- `scripts/little_loops/fsm/persistence.py:291` — `clear_all()` calls `archive_run()` (no path logic; unaffected)

### Tests That Will Break
- `scripts/tests/test_fsm_persistence.py:370-371` — asserts `archive_path.parent.name == "test-loop"` and `archive_path.parent.parent.name == ".history"` — both flip with flat structure
- `scripts/tests/test_fsm_persistence.py:384` — asserts `archive_path.name == "2024-01-15T103000"` — becomes `"2024-01-15T103000-test-loop"`
- `scripts/tests/test_ll_loop_commands.py:524` — manually builds `tmp_path / ".loops" / ".history" / "test-loop" / "test-run-id"`; all similar fixtures in that file (~8 occurrences) need the flat path

### Configuration / Docs
- `.loops/.history/` — existing nested folders need migration
- `docs/ARCHITECTURE.md` — module docstring in `persistence.py:1-20` shows the directory layout diagram; update both
- `docs/guides/LOOPS_GUIDE.md:1153` — describes old two-level layout (`.loops/.history/<loop-name>/<timestamp>/`); update to flat layout
- `docs/reference/CLI.md:301` — documents `ll-loop history`; verify no path shape examples need updating
- `scripts/little_loops/fsm/persistence.py:255-258` — `archive_run()` docstring shows nested layout; update alongside function body

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `get_loop_history()` at `persistence.py:625` reads from the `.running/` state file via `StatePersistence.read_events()` — not history-dir-related; no change needed
- `_list_archived_runs` at `info.py:359` accesses `history_base = loops_dir / HISTORY_DIR / loop_name` and calls `history_base.iterdir()` — this is the non-obvious second caller that must also switch to the flat layout
- `cmd_history` at `info.py:433` delegates to `_list_archived_runs` (no-run_id path) and `get_archived_events` (with-run_id path) — both legs need the flat path
- `cmd_history` error message at `info.py:458` uses `f"No events found for run: {loop_name}/{run_id}"` — still accurate post-change (run_id is still a timestamp), but the `/` separator is cosmetically tied to the old nested path; update to `f"No events found for run {run_id} of loop {loop_name}"` for clarity
- `archive_run()` docstring at `persistence.py:255-258` also shows the old nested layout diagram; update alongside the function body
- `test_fsm_persistence.py:445,459,477` — three additional tests construct `tmp_loops_dir / ".history" / "test-loop"` (in `test_clear_all_archives_before_clearing`, `test_clear_all_no_archive_for_fresh_run`, `test_multiple_archive_runs_coexist`) — missed in original issue; all must change to `tmp_loops_dir / ".history"` with run folder filtering
- `docs/guides/LOOPS_GUIDE.md:1153` — describes the old two-level layout `.loops/.history/<loop-name>/<timestamp>/`; must be updated to show the flat layout
- `docs/reference/CLI.md:301` — documents `ll-loop history` command; scan for any path examples that need updating

## Implementation Steps

1. Add `_parse_run_folder(name: str) -> tuple[str, str] | None` helper regex to `persistence.py` (module level).
2. Update `archive_run()` (`persistence.py:279`) — change archive path from `HISTORY_DIR / self.loop_name / run_id` to `HISTORY_DIR / f"{run_id}-{self.loop_name}"`.
3. Update `list_run_history()` (`persistence.py:577`) — replace `history_loop_dir.glob("*/state.json")` with flat dir glob `history_dir.glob("*/state.json")` filtered by `_parse_run_folder`.
4. Update `get_archived_events()` (`persistence.py:608`) — change path from `HISTORY_DIR / loop_name / run_id / "events.jsonl"` to `HISTORY_DIR / f"{run_id}-{loop_name}" / "events.jsonl"`.
5. Update `_list_archived_runs()` (`cli/loop/info.py:353`) — change `history_base = loops_dir / HISTORY_DIR / loop_name` to scan flat `loops_dir / HISTORY_DIR`, filtering entries whose name matches `*-{loop_name}` via `_parse_run_folder`.
6. Add migration: iterate existing `<loop_name>/` subdirs in `.loops/.history/` and move nested runs to flat top-level `<run_id>-<loop_name>/` folders.
7. Fix tests in `scripts/tests/test_fsm_persistence.py` — update `TestArchiveRun` assertions at lines 370-371 (parent structure) and 384 (folder name `"2024-01-15T103000"` → `"2024-01-15T103000-test-loop"`); also update path constructions at lines 445, 459, and 477 (in `test_clear_all_archives_before_clearing`, `test_clear_all_no_archive_for_fresh_run`, and `test_multiple_archive_runs_coexist`) from `tmp_loops_dir / ".history" / "test-loop"` to `tmp_loops_dir / ".history"` with flat-folder assertions.
8. Fix tests in `scripts/tests/test_ll_loop_commands.py` — update all ~8 fixtures that build `tmp_path / ".loops" / ".history" / "test-loop" / "test-run-id"` to use flat `tmp_path / ".loops" / ".history" / "<run_id>-test-loop"`.
9. Update `skills/analyze-loop/SKILL.md` Step 1 to resolve the run folder by scanning `.loops/.history/` folder names directly (no-arg → most recent by timestamp; loop-name → most recent matching `*-<loop_name>`).
10. Verify `ll-loop history <loop-name>` and `ll-loop history <loop-name> <run-id>` work with the new layout.

## Impact

- **Scope**: Isolated to `persistence.py` and the `.loops/.history/` directory layout.
- **Backwards compatibility**: Existing history folders use the old layout; a migration step is required to avoid orphaned data. Code can include a fallback read for the old path during a transition, then remove it in a follow-up.
- **No API changes** to `LoopState` or `StatePersistence` public interface — only file paths change.

## Success Metrics

- `ls .loops/.history/` shows all runs as top-level entries named `[TIMESTAMP]-[LOOP-NAME]`.
- `ll-loop history <loop-name>` returns the same runs as before.
- All history-related tests pass.

## Scope Boundaries

- Does not change the contents of `state.json` or `events.jsonl` within each run folder.
- Does not change `.loops/.running/` layout.
- Does not change the `run_id` format — only the containing directory name changes.

## API/Interface

```python
# archive_run() returns path — same return type, new path value
Path(".loops/.history/2026-04-03T120000-general-task/")

# list_run_history() signature unchanged
def list_run_history(loop_name: str, loops_dir: Path | None = None) -> list[LoopState]: ...

# get_archived_events() — run_id arg still the compact timestamp, loop_name used to construct path
def get_archived_events(loop_name: str, run_id: str, loops_dir: Path | None = None) -> list[dict]: ...
```

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | FSM loop persistence design |
| `docs/reference/API.md` | `StatePersistence` and history function signatures |

## Labels

`loops` `persistence` `history` `filesystem`

## Status

**Current**: backlog
**Reason**: Enhancement to loop history storage layout.

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-03_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Concerns
- Migration approach is underspecified — two options offered ("one-time script" vs. "compatibility shim") without committing to one. Decide before implementing step 6.
- `test_ll_loop_commands.py` has 9 fixture instances using the old nested path; mechanical but error-prone if done manually.

### Outcome Risk Factors
- Existing `.loops/.history/` nested folders in real projects will be orphaned immediately after the code change if migration is skipped. A compatibility read-fallback in `list_run_history()` is the lowest-risk approach for step 6.

## Session Log
- `/ll:refine-issue` - 2026-04-04T03:19:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5732e705-6919-4555-ae9d-5c904b677c29.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/822c0254-1b23-4911-b834-f9fb8a3a70da.jsonl`
- `/ll:refine-issue` - 2026-04-04T03:14:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c71751b5-4e08-4ee8-8ca6-6632b7bb4d7d.jsonl`
- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
