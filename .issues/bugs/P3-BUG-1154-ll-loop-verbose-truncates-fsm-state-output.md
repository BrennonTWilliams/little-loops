---
discovered_date: 2026-04-17
discovered_by: capture-issue
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

TBD — requires investigation. Likely candidates:

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchor**: verbose event handlers (`action_output` and neighboring `state_enter` / `state_exit` / state-info branches around the `max_line = tw - 8 - len(indent)` clip path near line 325 / 419-424)
- **Cause**: hard-clip-to-terminal-width logic is applied uniformly to state-related events even under `--verbose`, and/or state output arrives as a single logical "line" without newline-preserving split (mirrors BUG-1118 pattern).

## Proposed Solution

TBD - requires investigation.

Likely direction (mirror BUG-1118 fix):
- In verbose mode, skip the hard-clip for state-output event types and print full content.
- Split multi-line content on `\n` / `splitlines()` before dispatch so each real line renders as its own row and wrapping is natural.
- Apply consistently across `state_enter`, `state_exit`, and any state-payload/transition events — not just `action_output`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` (verbose event rendering)
- Possibly `scripts/little_loops/subprocess_utils.py` if state output flows through the same stream path as BUG-1118

### Dependent Files (Callers/Importers)
- TBD — use grep to find callers of the verbose display helpers

### Similar Patterns
- BUG-1118 (LLM response truncation) and BUG-566 (shell command output truncation) solved the same class of problem; reuse their approach

### Tests
- TBD — identify or add tests under `scripts/tests/` exercising `--verbose` rendering for multi-line state output

### Documentation
- `docs/reference/API.md` if verbose rendering contract is documented there

### Configuration
- N/A

## Implementation Steps

1. Reproduce the truncation with a loop whose state output spans multiple lines.
2. Trace the event pipeline for FSM state events through `_helpers.py` verbose handlers and confirm which branch hard-clips.
3. Apply BUG-1118-style fix (split on newlines, skip width clip under `--verbose`) to the state-output branches.
4. Add regression tests covering `--verbose` rendering of multi-line state output.
5. Verify `ll-loop history` / `ll-loop show` still render correctly with the new event shape.

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

## Session Log

- `/ll:capture-issue` - 2026-04-17 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00032768-5efc-466a-aad1-02f0fb698fb3.jsonl`

---

**Open** | Created: 2026-04-17 | Priority: P3
