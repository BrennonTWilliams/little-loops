---
id: ENH-1701
status: open
priority: P3
type: ENH
captured_at: "2026-05-25T21:57:02Z"
discovered_date: 2026-05-25
discovered_by: capture-issue
parent: EPIC-1744
---

# ENH-1701: Show artifact paths in `ll-loop run` output

## Summary

Add a small artifact-paths section to the `ll-loop run` pinned header, displayed between the `== loop: name ==` line and the FSM diagram. The section shows the resolved loop YAML file path and any context values that look like filesystem paths (e.g. `output_dir: .loops/plans/`), so the user can preview outputs in another terminal while the loop runs.

## Motivation

Loop runs that write plan files, rubric files, research findings, or other outputs give the user no indication of where those files are. For example, `rn-refine` writes to `.loops/plans/<slug>/` but nothing in the output points there. Users must consult the YAML or guess. Surfacing these paths at startup reduces friction and makes loops feel more transparent.

## Current Behavior

The pinned pane header shows only:

```
== loop: rn-refine =========================================
[FSM diagram]
```

No file paths are displayed until the loop completes and the `report` state prints them.

## Expected Behavior

```
== loop: rn-refine =========================================
  loop:       loops/rn-refine.yaml
  output_dir: .loops/plans/
────────────────────────────────────────────────────────────
[FSM diagram]
```

The same section also appears in the non-pinned (no `--show-diagrams`) startup block printed by `run_foreground`.

## Scope Boundaries

- **In scope**: Pinned pane header (`_build_pinned_pane`) and non-pinned startup block in `run_foreground`; path-like context values using the heuristic below; `loop_path` defaulting to `None` so sub-loop callers are unaffected.
- **Out of scope**: Runtime validation or resolution of displayed paths; colorization or styling beyond the existing header format; surfacing context values that are not path-like strings; integration with the `report` state or post-run summaries.

## Implementation Steps

1. **Thread `loop_path: Path` through display functions** — `resolve_loop_path()` is already called at the `run_loop` / `resume_loop` call sites in `_helpers.py`; capture the result and pass it as a new parameter to `_build_pinned_pane` and the non-pinned print block in `run_foreground`.

2. **Add `_artifact_lines(fsm, loop_path)` helper** — extract path-looking values from `fsm.context`: a value qualifies if it is a non-empty string, starts with `.` or `/` or contains `/`, and contains no `${` template expressions. Return a list of `(key, value)` pairs.

3. **Render the section** — in `_build_pinned_pane` (`_helpers.py:314–318`), insert the artifact lines between the `== loop: name ==` header and `parent_diagram`. In `run_foreground` (`_helpers.py:673–675`), print the same lines after the `Max iterations:` line.

4. **Make loop_path optional** — default to `None` so callers that don't have the path (e.g. sub-loop display) are unaffected.

## Heuristic for "looks like a path"

A context value is treated as a path if it:
- Is a non-empty `str`
- Starts with `.`, `/`, or `~`, OR contains at least one `/`
- Does NOT contain `${` (template expression — not yet resolved)

This matches `".loops/plans"`, `"./output"`, `"/tmp/scratch"` and excludes `"ITERATE"`, `"LOW"`, `"${captured.run_dir.output}"`.

## Files

- `scripts/little_loops/cli/loop/_helpers.py` — primary change site
  - `_build_pinned_pane` (~line 314): insert artifact section after header line
  - `run_foreground` (~line 673): print artifact section in startup block

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — `_build_pinned_pane` (~line 314): insert artifact section after header line; `run_foreground` (~line 673): print artifact section after `Max iterations:` line; add new `_artifact_lines(fsm, loop_path)` helper

### Dependent Files (Callers/Importers)
- TBD — grep for callers: `grep -r "run_foreground\|_build_pinned_pane\|run_loop\|resume_loop" scripts/little_loops/cli/loop/`
- `_helpers.py` call sites in `run.py` / `resume.py` must thread `loop_path` through

### Similar Patterns
- TBD — check for existing context-display helpers in `_helpers.py`

### Tests
- TBD — identify test files under `scripts/tests/` for `cli/loop/_helpers.py`

### Documentation
- N/A — display-only change, no CLI or public API changes

### Configuration
- N/A

## Impact

- **Priority**: P3 — UX improvement; loops are fully functional without this, but users must consult the YAML to locate output paths during a run.
- **Effort**: Small — single file change; new `_artifact_lines` helper plus threading `loop_path: Optional[Path]` through two display functions.
- **Risk**: Low — output-only change; `loop_path` defaults to `None` so all existing callers are unaffected with no behavioral changes.
- **Breaking Change**: No

## Labels

`enhancement`, `ux`, `ll-loop`

## Session Log
- `/ll:format-issue` - 2026-05-25T22:02:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/432171fe-0cc8-40cb-a835-f0fb1286db77.jsonl`
- `/ll:capture-issue` - 2026-05-25T21:57:02Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`

---
**Open** | Created: 2026-05-25 | Priority: P3
