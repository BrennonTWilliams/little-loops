---
discovered_date: 2026-04-17
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
status: done
completed_at: 2026-04-18T00:00:00Z
---

# BUG-1154: ll-loop --verbose truncates fsm state output

## Summary

When `ll-loop` is run with `--verbose`, FSM loop state output (state transitions, state metadata, per-state progress info) is truncated in the terminal display. Under `--verbose`, state output should be shown in full with proper formatting (preserved newlines, wrapping instead of hard-clipping) rather than cut off.

## Current Behavior

Running `ll-loop run <fsm> --verbose` truncates state-related output (e.g., state enter/exit banners, state payload or transition details) so that only a single clipped row is visible, typically ending in `...`. Longer multi-line state info is collapsed or chopped, defeating the purpose of `--verbose`.

## Expected Behavior

With `--verbose`:
- FSM state output is **never truncated** — the full content is printed.
- Output is **properly formatted**: embedded newlines are preserved, multi-line content renders as multiple rows, and long lines wrap (or are indented) rather than being hard-clipped to terminal width with `...`.
- Non-verbose mode retains today's compact display.

## Motivation

`--verbose` is an inspection/debugging flag. Users invoke it specifically to see the complete picture of what the FSM is doing. Silent truncation of state output forces them to dig into raw event logs (`ll-loop history`, `ll-loop show`) to recover information the UI already had in-hand. This directly undermines the flag's contract.

Related prior fix: BUG-1118 addressed the same class of truncation for LLM assistant responses on the prompt-action path (`subprocess_utils.py`, `_helpers.py:419-424`). The same pattern appears to still affect FSM state-level output.

## Steps to Reproduce

1. Pick a loop whose state output (banner, payload, or transition info) spans multiple lines or exceeds terminal width.
2. Run `ll-loop run <fsm> --verbose`.
3. Observe: state output renders as a single clipped row ending in `...` instead of a fully formatted multi-line block.

## Root Cause

_Codebase research (`/ll:refine-issue`): the bug is not in `state_enter`/`state_exit` per se — there is no `state_exit` or `state_transition` event emitted by the executor, and the `state_enter` branch at `_helpers.py:388-393` never applies `max_line`. The observable "state output" truncation actually originates in the per-state events that surround a state: `action_start` (prompt/shell echo) and `evaluate` (verdict reason & raw preview). BUG-1118 fixed the clip only in `action_output`; the sibling branches were not touched._

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchors** (all still hard-clip under `--verbose`):
  - `_helpers.py:409` — `action_start` prompt path per-line clip: `display = line[:max_line] + "..."` — fires even when `verbose=True`
  - `_helpers.py:416` — `action_start` shell path single-line clip: `action_display = action[:max_line] + "..."` — fires even when `verbose=True`
  - `_helpers.py:504` — `evaluate` `raw_preview` hard 200-char cap: `raw_preview[:200]` — no verbose bypass
  - `_helpers.py:507` — `evaluate` `reason` hard 300-char cap: `reason_display = reason[:300] + "..."` — no verbose bypass
- **Cause**: `max_line = tw - 8 - len(indent)` is computed at `_helpers.py:324-325` and applied unconditionally in the `action_start` branches; the `evaluate` branch additionally uses two hardcoded numeric caps (200 / 300) with no `verbose` guard. BUG-1118's Fix B removed the clip from `action_output` only (`_helpers.py:419-423`), leaving these sibling branches still truncating under `--verbose`.
- **Note on event shape**: `action_start.action` can be a multi-line prompt string; the prompt branch already splits on `splitlines()` at `_helpers.py:400`, but then re-clips each line at line 409. The `evaluate.reason` field (from `fsm/executor.py:729-736`) is free-form LLM rationale that can span multiple sentences/lines but is treated as one string and truncated at 300 chars.

## Proposed Solution

Mirror BUG-1118 Fix B across the remaining branches. Two focused edits in `scripts/little_loops/cli/loop/_helpers.py`:

1. **`action_start` branch (lines 407-417)** — when `verbose`, skip the per-line `[:max_line]` clip and print each line verbatim. Keep the non-verbose path (5-line cap + per-line clip) unchanged.

   ```python
   # around line 407-414 (prompt path)
   show_count = line_count if verbose else min(5, line_count)
   for line in lines[:show_count]:
       if verbose:
           print(f"{indent}       {line}", flush=True)
       else:
           display = line[:max_line] + "..." if len(line) > max_line else line
           print(f"{indent}       {display}", flush=True)

   # around line 415-417 (shell path)
   if verbose:
       action_display = action
   else:
       action_display = action[:max_line] + "..." if len(action) > max_line else action
   ```

2. **`evaluate` branch (lines 502-508)** — when `verbose`, emit the full `reason` and full `raw_preview`, splitting multi-line content on `splitlines()` so each real line renders as its own indented row. Keep the 200/300 caps only in non-verbose mode.

   ```python
   if raw_preview and verdict == "error":
       if verbose:
           for sub in raw_preview.splitlines() or [""]:
               print(f"{indent}         raw: {sub}", flush=True)
       else:
           print(f"{indent}         raw: {raw_preview[:200]}", flush=True)
   if reason and not (error and verdict == "error"):
       if verbose:
           for sub in reason.splitlines() or [""]:
               print(f"{indent}         {sub}", flush=True)
       else:
           reason_display = reason[:300] + "..." if len(reason) > 300 else reason
           print(f"{indent}         {reason_display}", flush=True)
   ```

Non-verbose output is unchanged. No persisted-event shape changes. `ll-loop history` / `ll-loop show` are unaffected because they read from the events log, not `display_progress`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — edits confined to two branches inside the `display_progress` closure:
  - `action_start` branch (lines 395-417): gate `[:max_line]` clips on `not verbose`
  - `evaluate` branch (lines 469-508): gate 200/300-char caps on `not verbose`; add `splitlines()` iteration under verbose
- `scripts/little_loops/subprocess_utils.py` — **not required**. BUG-1118's Fix A already splits assistant text into per-line `stream_callback` calls (`subprocess_utils.py:198-212`); state/evaluate paths don't route through this stream.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py:319` — `display_progress` closure (the only call-site for the changed branches)
- `scripts/little_loops/cli/loop/_helpers.py:516-520` — `display_progress` registration on `executor.event_bus` / `executor._on_event`
- `scripts/little_loops/fsm/executor.py:555` — emits `action_start` events consumed by the changed branch
- `scripts/little_loops/fsm/executor.py:729-736, 770-778` — emits `evaluate` events (`reason`, `raw_preview`, `verdict` fields) consumed by the changed branch
- No external importers of `display_progress` — it's a closure local to `run_foreground`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py:231` — sole production caller of `run_foreground`; no edit needed (fix is internal to the closure), but confirms the call-site for integration testing

### Similar Patterns
- **Direct template** — BUG-1118 Fix B at `_helpers.py:419-423` (`action_output` branch): removed `line[:max_line] + "..."` under `verbose`. Apply the same shape to `action_start` and `evaluate`.
- **BUG-1118 Fix A** at `subprocess_utils.py:198-212` (already merged) — `.splitlines()` iteration before per-line dispatch; mirror this loop for multi-line `reason` / `raw_preview` under verbose.
- **Correctly-guarded precedent** — `action_complete` at `_helpers.py:447-467` already guards its preview clip with `and not verbose`; the fix makes `action_start` and `evaluate` consistent with this existing pattern.
- **BUG-566** (shell output truncation, completed) — same class of fix; confirms the established resolution shape.

### Tests
- `scripts/tests/test_ll_loop_display.py:1584-1597` — `test_verbose_action_output_not_clipped` is the direct template. Add parallel tests:
  - `test_verbose_action_start_prompt_not_clipped` — emit `action_start` with `is_prompt=True` and a 200-char line, assert full line present and no `"..."` trailer.
  - `test_verbose_action_start_shell_not_clipped` — emit `action_start` with `is_prompt=False` and a 200-char command, same assertions.
  - `test_verbose_evaluate_reason_not_clipped` — emit `evaluate` with a 500-char `reason`, assert full reason present and no `"..."` trailer.
  - `test_verbose_evaluate_reason_multiline_preserved` — emit `evaluate` with `\n`-separated reason, assert each line renders on its own row.
  - `test_verbose_evaluate_raw_preview_not_clipped` — emit `evaluate` with `verdict="error"` and a 400-char `raw_preview`, assert full preview present.
  - `test_nonverbose_action_start_still_clips` — negative test confirming non-verbose path retains today's clip + 5-line cap.
  - `test_nonverbose_evaluate_reason_still_caps_at_300` — negative test confirming non-verbose path retains the 300-char cap.
- Reuse `MockExecutor` (`test_ll_loop_display.py:34-52`) and `_make_args`/`_make_fsm` helpers (around `test_ll_loop_display.py:1494-1503, 2192`). Patch `little_loops.cli.loop._helpers.terminal_width` to 80 per the existing pattern.

### Documentation
- `docs/reference/CLI.md:316-317` — `--verbose` / `--full` contract on `ll-loop run`. Verify description still accurate after fix (current text "Show action output preview and LLM call details" is consistent with full-width output).
- `docs/guides/LOOPS_GUIDE.md:1757-1771` — `--verbose` streaming contract. No wording change needed if "streams full output" language is already present; otherwise a short clarification that multi-line `evaluate.reason` is preserved.
- `docs/reference/OUTPUT_STYLING.md` — cross-check if verbose rendering rules are documented there.

### Configuration
- N/A — no config keys gate this behavior; it is driven entirely by the `--verbose` CLI flag.

### Changelog

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — add a `Fixed` entry under the next release section; mirror the BUG-1118 entry format at `CHANGELOG.md:25` (e.g., "**`ll-loop run --verbose` Truncated action_start and evaluate Output** — Prompts, shell commands, evaluate reason, and raw_preview now display in full under `--verbose`; non-verbose compact display unchanged (BUG-1154)")

## Implementation Steps

1. **Reproduce** — run any loop whose `action_start` prompt or `evaluate.reason` exceeds terminal width (e.g., a state with a multi-sentence LLM verdict rationale) under `ll-loop run <fsm> --verbose`. Confirm the `...` trailer appears in the prompt echo and/or the `reason:` line.
2. **Edit `action_start` branches in `scripts/little_loops/cli/loop/_helpers.py`:**
   - Line 407-414 (prompt path): guard `line[:max_line] + "..."` on `not verbose`; under `verbose`, print each `line` verbatim.
   - Line 415-417 (shell path): guard `action[:max_line] + "..."` on `not verbose`; under `verbose`, print full `action`.
3. **Edit `evaluate` branch in `scripts/little_loops/cli/loop/_helpers.py` (lines 502-508):**
   - Guard the `raw_preview[:200]` cap at line 504 on `not verbose`; under `verbose`, iterate `raw_preview.splitlines()` and print each line.
   - Guard the `reason[:300] + "..."` cap at line 507 on `not verbose`; under `verbose`, iterate `reason.splitlines()` and print each line.
4. **Add regression tests in `scripts/tests/test_ll_loop_display.py`** modeled after `test_verbose_action_output_not_clipped` (line 1584). Cover: `action_start` prompt, `action_start` shell, `evaluate.reason` (single & multi-line), `evaluate.raw_preview` with `verdict="error"`. Include negative tests to pin the non-verbose clip behavior. Patch `little_loops.cli.loop._helpers.terminal_width` to 80.
5. **Verify** — run `python -m pytest scripts/tests/test_ll_loop_display.py -v`; run `python -m pytest scripts/tests/` for full regression; execute a real `ll-loop run <fsm> --verbose` on a loop with long reason strings to confirm visual output.
6. **Confirm non-impact** — `ll-loop history` and `ll-loop show` are untouched because they read persisted events, not `display_progress` output. No change to event payload shapes.

## Impact

- **Priority**: P3 — UX/debuggability issue on an inspection flag; not blocking, but visibly broken for power users.
- **Effort**: Small — likely a localized change in the verbose rendering helpers, analogous to BUG-1118.
- **Risk**: Low — scoped to `--verbose` display path; no change to persisted events or non-verbose output expected.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Category | Relevance |
|----------|----------|-----------|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | architecture | FSM loop system design and event flow |
| [docs/reference/API.md](../../docs/reference/API.md) | architecture | CLI and module reference for `ll-loop` |

## Labels

`bug`, `captured`, `ll-loop`, `verbose`, `display`

## Resolution

Fixed by mirroring BUG-1118 Fix B in the two remaining `display_progress` branches in `scripts/little_loops/cli/loop/_helpers.py`:

- **`action_start` branch** — under `verbose`, prompt lines and shell commands are printed verbatim without the `[:max_line]` clip. Non-verbose path unchanged (keeps 5-line cap + per-line clip).
- **`evaluate` branch** — under `verbose`, `reason` and `raw_preview` are split on `splitlines()` and printed as full multi-row output. Non-verbose path retains the 200/300-char caps.

Added regression tests in `scripts/tests/test_ll_loop_display.py`:
- `test_verbose_action_start_prompt_not_clipped`
- `test_verbose_action_start_shell_not_clipped`
- `test_verbose_evaluate_reason_not_clipped`
- `test_verbose_evaluate_reason_multiline_preserved`
- `test_verbose_evaluate_raw_preview_not_clipped`
- `test_nonverbose_action_start_still_clips`
- `test_nonverbose_evaluate_reason_still_caps_at_300`

All 4956 tests pass. No changes to persisted event shapes; `ll-loop history` / `ll-loop show` unaffected.

## Session Log
- `/ll:manage-issue` - 2026-04-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1f3fa003-a377-4486-9734-6ee2f5acca1f.jsonl`
- `/ll:ready-issue` - 2026-04-18T18:05:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b59b8421-bd86-4e4a-a3dd-2dfb9f29800f.jsonl`
- `/ll:confidence-check` - 2026-04-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/30b9263f-a97f-427e-a6e7-e47caf4667a9.jsonl`
- `/ll:wire-issue` - 2026-04-18T18:03:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/694a46f6-7043-48a8-82f3-07ab5276f421.jsonl`
- `/ll:refine-issue` - 2026-04-18T17:57:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0affc59b-ae07-4860-8e7a-6a5cd61312a2.jsonl`

- `/ll:capture-issue` - 2026-04-17 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00032768-5efc-466a-aad1-02f0fb698fb3.jsonl`

---

**Completed** | Created: 2026-04-17 | Completed: 2026-04-18 | Priority: P3
