---
id: ENH-878
type: ENH
priority: P4
title: "Add loop-name header bar above top-level FSM diagram when --show-diagrams is used"
discovered_date: 2026-03-24
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
---

# ENH-878: Add loop-name header bar above top-level FSM diagram when --show-diagrams is used

## Summary

When running `ll-loop run ... --show-diagrams`, sub-loops already display a header bar (e.g., `── sub-loop: issue-refinement ──...`). The top-level loop has no equivalent header, making it harder to visually distinguish the top-level FSM diagram from sub-loop diagrams in the output. This enhancement adds a matching header bar above the top-level loop diagram.

## Current Behavior

When `--show-diagrams` is passed, sub-loop FSM diagrams are preceded by a header line:

```
── sub-loop: issue-refinement ────────...
```

The top-level FSM diagram has no header — it appears without any label.

## Expected Behavior

The top-level FSM diagram should be preceded by a similarly styled header:

```
== loop: loop-name ========...
```

The `==` prefix visually distinguishes the top-level loop header from sub-loop headers (`──`), creating a clear visual hierarchy in the terminal output.

## Motivation

When a loop contains sub-loops and `--show-diagrams` is active, the output can be difficult to navigate. Without a header for the top-level loop, users can't easily identify where the top-level diagram begins. The sub-loop header convention is already established — applying it consistently to the top level improves readability with minimal effort.

## Proposed Solution

In the diagram rendering path (likely `scripts/little_loops/layout.py` or wherever `--show-diagrams` output is generated), identify where the top-level FSM diagram is printed and prepend a header line using `==` characters and the loop name:

```
== loop: <loop-name> ========...
```

The line should be padded to a consistent terminal width (matching the existing sub-loop header width convention).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py:347-357` — **primary change site**: the `show_diagrams` branch inside the `display_progress` closure in `run_foreground`. Add a header line immediately before `print(diagram, flush=True)` for the top-level FSM diagram.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:128-132, 204-208` — registers `--show-diagrams` flag on `run` and `resume` subparsers; no change needed
- `scripts/little_loops/cli/loop/run.py` — `cmd_run` passes `args` (including `show_diagrams`) to `run_foreground`; no change needed
- `scripts/little_loops/cli/output.py:16-18` — `terminal_width()` already imported in `_helpers.py:14`; reuse directly

### Similar Patterns
- **Sub-loop separator** at `_helpers.py:358-362` — exact model to follow:
  ```python
  child_name = current_child_fsm[0].name
  separator_text = f"\u2500\u2500 sub-loop: {child_name} "
  separator = separator_text + "\u2500" * max(0, tw - len(separator_text))
  print(separator, flush=True)
  ```
  Mirror this with `=` characters and `fsm.name` for the top-level header:
  ```python
  header_text = f"== loop: {fsm.name} "
  header = header_text + "=" * max(0, tw - len(header_text))
  print(header, flush=True)
  ```
- **`terminal_width()` usage** at `_helpers.py:321` — `tw` is already computed at the top of `display_progress`; use it directly
- **Sprint `=`-banner** at `sprint/_helpers.py:56-61` — confirms `=` characters with `terminal_width()` is an established pattern

### Tests
- `scripts/tests/test_ll_loop_display.py` — primary test file; add new test in the existing `TestShowDiagrams` class. Model after:
  - `test_sub_loop_child_diagram_rendered_during_sub_loop_execution` (line 1785) — checks `"sub-loop: child-loop"` in stdout (line 1841)
  - `test_terminal_width_no_overflow` (line 1440) — patches `output_mod.terminal_width` to return 80

### Documentation
- `docs/reference/CLI.md` — documents `--show-diagrams`; may want to mention the new header format
- `docs/guides/LOOPS_GUIDE.md` — references `--show-diagrams` usage; update example output if any

### Configuration
- N/A

## Implementation Steps

1. Open `scripts/little_loops/cli/loop/_helpers.py` and locate the `show_diagrams` branch at ~line 347 inside `display_progress`
2. Before `print(diagram, flush=True)` (the top-level diagram print), add:
   ```python
   header_text = f"== loop: {fsm.name} "
   header = header_text + "=" * max(0, tw - len(header_text))
   print(header, flush=True)
   ```
   (`tw` is already in scope from `tw = terminal_width()` at line 321)
3. Add a test in `test_ll_loop_display.py::TestShowDiagrams` asserting `"== loop: <name>"` appears in stdout when `show_diagrams=True`, modeled after the sub-loop check at line 1841
4. Verify output manually or via test with a loop that has at least one sub-loop (confirms `==` header appears above top-level diagram, `──` header above sub-loop diagram)

## Impact

- **Priority**: P4 - Minor UX polish; no functional impact
- **Effort**: Small - Likely a single-location change modeled after existing sub-loop header code
- **Risk**: Low - Display-only change
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `show-diagrams`, `fsm`, `captured`

## Resolution

**Implemented** on 2026-03-24.

Added a `== loop: <name> ====...` header line immediately before the top-level FSM diagram print in `run_foreground` (`scripts/little_loops/cli/loop/_helpers.py`). The header mirrors the existing sub-loop separator pattern (`──`) but uses `=` characters to visually distinguish top-level from sub-loop diagrams. Added a corresponding test in `TestDisplayProgressEvents` to verify the header appears in output when `show_diagrams=True`.

**Files changed**:
- `scripts/little_loops/cli/loop/_helpers.py` — added 2-line header before top-level diagram print
- `scripts/tests/test_ll_loop_display.py` — added `test_top_level_loop_header_shown_when_show_diagrams`

## Session Log
- `/ll:ready-issue` - 2026-03-24T23:52:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0fe85a4a-ea95-46b5-ae1e-190049f24d79.jsonl`
- `/ll:confidence-check` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/03039c01-35af-49e7-adee-63a6509207db.jsonl`
- `/ll:refine-issue` - 2026-03-24T23:48:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/934c3a74-13fd-4d71-9690-19cbd8eda466.jsonl`
- `/ll:capture-issue` - 2026-03-24T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a7eabad2-b585-45d8-8e92-63f37037ac5f.jsonl`
- `/ll:manage-issue` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

## Status

**Completed** | Created: 2026-03-24 | Resolved: 2026-03-24 | Priority: P4
