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

## Reference

- `docs/claude-code/hooks-reference.md` — SessionStart: "stdout is added as context that Claude can see and act on"

## Impact

- **Priority**: P4
- **Effort**: Trivial
- **Risk**: Low — more context for Claude when config is large

## Labels

`enhancement`, `hooks`, `session-start`, `consistency`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4
