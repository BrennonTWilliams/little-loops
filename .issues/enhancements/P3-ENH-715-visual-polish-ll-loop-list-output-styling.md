---
discovered_date: "2026-03-13"
discovered_by: capture-issue
---

# ENH-715: Visual polish for ll-loop list output styling

## Summary

Enhance the `ll-loop list` output to use ANSI colors and formatting from the existing `cli/output.py` utilities, achieving visual parity with `ll-issues list` which already uses `TYPE_COLOR`, `PRIORITY_COLOR`, and `colorize()` for polished output.

## Current Behavior

`ll-loop list` outputs plain uncolored text:
```
Available loops:
  loop-name  description  [built-in]
```

No colors, no visual hierarchy, no alignment. Contrast with `ll-issues list` which colorizes type headers, issue IDs, and priorities using the shared `colorize()` utility.

## Expected Behavior

`ll-loop list` should use the existing `cli/output.py` styling utilities to produce colorized, well-aligned output:
- Loop names colorized (e.g., bold or a distinct color)
- `[built-in]` tag styled (e.g., dim)
- Group headers styled like `ll-issues list` type headers
- Consistent column alignment
- Running loops mode should also benefit from color (status indicators, elapsed time)

## Motivation

CLI output consistency improves usability. `ll-issues list` already demonstrates the project's styling conventions with `colorize()`, `TYPE_COLOR`, and `PRIORITY_COLOR`. `ll-loop list` is one of the most-used loop commands and should match the visual quality standard set by other CLI commands.

## Proposed Solution

Modify `scripts/little_loops/cli/loop/info.py` (`list_loops` and `list_running` functions) to use imports from `scripts/little_loops/cli/output.py`:

- Import `colorize` from `cli.output`
- Define loop-specific color codes (or reuse existing ones) for loop names, descriptions, tags
- Style `[built-in]` with dim (`"2"`)
- Style loop names with bold or a distinctive color
- Style group headers ("Project loops:", "Built-in loops:") like `ll-issues list` type headers
- For running loops: colorize state names, iteration counts, and elapsed time

Reference implementation: `scripts/little_loops/cli/issues/list_cmd.py` lines 51-76 for the pattern used by `ll-issues list`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `list_loops()` and `list_running()` functions

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/commands.py` — calls `list_loops()` / `list_running()`

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py` — reference implementation for styled list output

### Tests
- `scripts/tests/test_ll_loop_display.py` — may need updates if assertions check exact output strings

### Documentation
- N/A

### Configuration
- `cli.colors` in BRConfig — already supports color customization, no changes needed

## Implementation Steps

1. Add `colorize` import to `loop/info.py` from `cli.output`
2. Define color constants for loop list elements (name, tag, header)
3. Apply colors to `list_loops()` output (names, descriptions, built-in tags, headers)
4. Apply colors to `list_running()` output (state, iteration, elapsed, status)
5. Run existing tests and update any broken string assertions

## Scope Boundaries

- Do NOT change `ll-loop show`, `ll-loop history`, or diagram rendering — those already have their own styling
- Do NOT add new color configuration options — reuse existing `cli.output` infrastructure
- Do NOT change the information content or structure of the output, only its visual presentation

## Impact

- **Priority**: P3 - Visual polish, not functional
- **Effort**: Small - Reuses existing `colorize()` utility and follows established pattern in `list_cmd.py`
- **Risk**: Low - Additive styling only, existing `NO_COLOR` and non-TTY guards in `colorize()` handle graceful degradation
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/48c65a82-961f-4b5a-a5e6-9fe32bc7c8b9.jsonl`

---

## Status

**Open** | Created: 2026-03-13 | Priority: P3
