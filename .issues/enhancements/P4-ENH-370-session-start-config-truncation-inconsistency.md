---
discovered_date: 2026-02-12
discovered_by: hooks-reference-audit
---

# ENH-370: session-start.sh truncates config at 50 lines without local overrides

## Summary

`hooks/scripts/session-start.sh` has two config output paths: the Python merge path outputs the full config, but the non-merge path truncates at 50 lines via `head -50`. This means Claude sees different amounts of configuration depending on whether `.claude/ll.local.md` exists.

## Location

- **File**: `hooks/scripts/session-start.sh:153`

## Current Behavior

```bash
# Non-merge path (no local overrides)
head -50 "$CONFIG_FILE"   # truncated at 50 lines

# Merge path (local overrides present)
print(config_text)         # full output via Python
```

## Expected Behavior

Output the full config in both paths:

```bash
cat "$CONFIG_FILE"
```

Or consistently truncate in both paths if size is a concern (the Python path already warns at >5000 chars but doesn't truncate).

## Motivation

This enhancement would:
- Ensure consistent config visibility for Claude across both code paths (merge vs non-merge)
- Business value: Claude receives full configuration context regardless of whether local overrides exist, preventing silent truncation that could affect behavior
- Technical debt: Eliminates an asymmetry between two code paths that should produce equivalent output

## Proposed Solution

Replace `head -50` with `cat` in the non-merge path to match the Python merge path's full output behavior, as shown in Expected Behavior.

## Implementation Steps

1. **Replace truncation command**: Change `head -50 "$CONFIG_FILE"` to `cat "$CONFIG_FILE"` in the non-merge path at `hooks/scripts/session-start.sh:153`
2. **Verify both paths**: Confirm both the merge path (Python) and non-merge path (cat) output the full config content
3. **Test with large configs**: Ensure no adverse effects when config exceeds 50 lines

## Integration Map

- **Files to Modify**: `hooks/scripts/session-start.sh`
- **Dependent Files (Callers/Importers)**: `hooks/hooks.json` (SessionStart event triggers this script)
- **Similar Patterns**: N/A
- **Tests**: N/A — shell script change; verified by triggering SessionStart hook with and without local overrides
- **Documentation**: `docs/claude-code/hooks-reference.md`
- **Configuration**: `.claude/ll-config.json`, `.claude/ll.local.md`

## Scope Boundaries

- Only modify the non-merge path output command
- Do not change the Python merge path behavior
- Do not add truncation to the Python path for "consistency" — full output is the desired behavior

## Reference

- `docs/claude-code/hooks-reference.md` — SessionStart: "stdout is added as context that Claude can see and act on"

## Impact

- **Priority**: P4
- **Effort**: Trivial
- **Risk**: Low — more context for Claude when config is large

## Labels

`enhancement`, `hooks`, `session-start`, `consistency`

## Session Log
- `/ll:format_issue --all --auto` - 2026-02-13

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4
