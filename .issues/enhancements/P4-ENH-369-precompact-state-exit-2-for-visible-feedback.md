---
discovered_date: 2026-02-12
discovered_by: hooks-reference-audit
---

# ENH-369: precompact-state.sh should use exit 2 for user-visible feedback

## Summary

`hooks/scripts/precompact-state.sh` outputs a state-preservation message to stderr but exits with code 0. Per the hooks reference, PreCompact stderr on exit 0 is only visible in verbose mode. Using exit 2 (which is non-blocking for PreCompact) would make the message visible to the user.

## Location

- **File**: `hooks/scripts/precompact-state.sh:82-84`

## Current Behavior

```bash
echo "[ll] Task state preserved before context compaction..." >&2
exit 0  # stderr only visible in verbose mode (Ctrl+O)
```

## Expected Behavior

```bash
echo "[ll] Task state preserved before context compaction..." >&2
exit 2  # PreCompact: non-blocking, "Shows stderr to user only"
```

## Reference

- `docs/claude-code/hooks-reference.md` — Exit code 2 behavior table: `PreCompact | No [can't block] | Shows stderr to user only`

PreCompact exit 2 is safe — the event cannot block compaction. Exit 2 simply makes stderr visible to the user.

## Impact

- **Priority**: P4
- **Effort**: Trivial — change exit code
- **Risk**: None — PreCompact cannot block

## Labels

`enhancement`, `hooks`, `precompact`, `ux`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4
