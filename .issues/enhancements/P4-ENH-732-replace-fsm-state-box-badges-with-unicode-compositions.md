---
id: ENH-732
priority: P4
type: ENH
status: active
discovered_date: 2026-03-13
discovered_by: capture-issue
---

# ENH-732: Replace FSM State Box Badges with Unicode Compositions

## Summary

Replace the plain-text `[action_type]` badge labels rendered inside FSM box diagram state boxes with compact, visually distinctive multi-character unicode compositions.

## Motivation

The current badges (`[prompt]`, `[slash_command]`, `[shell]`, `[mcp]`) are verbose and consume horizontal space inside fixed-width state boxes, causing more name truncation. Replacing them with compact unicode glyphs reduces badge width while improving visual clarity and making different action types immediately recognizable at a glance.

## Proposed Behavior

Replace each action type badge with the following composition:

| Action Type     | Current Badge    | New Badge |
|----------------|-----------------|-----------|
| `prompt`        | `[prompt]`       | `✦`       |
| `slash_command` | `[slash_command]`| `/━►`     |
| `shell`         | `[shell]`        | `❯_`      |
| `mcp`           | `[mcp]`          | `⚡`       |

The `mcp` action type is not yet implemented (tracked in FEAT-729), but the badge mapping should be added in anticipation of that feature.

## Implementation Steps

1. Add a `_ACTION_TYPE_BADGES` dict in `scripts/little_loops/cli/loop/layout.py` mapping action type strings to their unicode compositions.
2. Replace all three badge-construction sites in `layout.py` (lines ~85, ~466, ~1334) that currently do `badge = f"[{state.action_type}]"` (and the `[shell]` fallback) with lookups into `_ACTION_TYPE_BADGES`, falling back to `f"[{action_type}]"` for unknown types.
3. Verify width calculations remain correct — the new badges have different `len()` values than the old bracket strings (e.g., `[slash_command]` is 15 chars; `/━►` is 3 chars, but note `━` and `►` may have terminal display widths > 1).
4. Consider using `wcwidth` or a simple override table for display-width calculation if terminal rendering is a concern.
5. Update any snapshot/golden-file tests in `scripts/tests/` that assert on rendered diagram output containing the old badge strings.

## Files to Change

- `scripts/little_loops/cli/loop/layout.py` — primary badge rendering logic (3 sites)
- `scripts/tests/` — any tests with hardcoded `[prompt]`, `[shell]`, etc. in expected output

## Related Issues

- FEAT-729: Dedicated `mcp_tool` action type (adds the `mcp` state this badge will serve)
- BUG-730: Transition lines occlude state boxes in FSM box diagram (sibling diagram visual issue)
- ENH-731: Rename FSM transition labels success/fail → yes/no (related diagram label cleanup)

---
## Status

Active — not yet started.

## Session Log
- `/ll:capture-issue` - 2026-03-13T22:51:23Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
