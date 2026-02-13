---
discovered_date: 2026-02-12
discovered_by: hooks-reference-audit
---

# ENH-378: precompact-state.sh should use exit 2 for user-visible feedback

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

## Motivation

This enhancement would:
- Provide user-visible feedback during context compaction so users know their task state was preserved
- Business value: Improved user experience — users see confirmation that state preservation occurred without needing verbose mode
- Technical debt: Aligns exit code usage with hooks reference documentation for correct semantics

## Implementation Steps

1. **Change exit code**: Replace `exit 0` with `exit 2` in `hooks/scripts/precompact-state.sh` at line 84
2. **Verify message visibility**: Confirm the stderr message "[ll] Task state preserved before context compaction..." is shown to the user (not just in verbose mode)
3. **Test compaction flow**: Ensure exit 2 does not block compaction (PreCompact is non-blocking by design)

## Integration Map

- **Files to Modify**: `hooks/scripts/precompact-state.sh`
- **Dependent Files (Callers/Importers)**: `hooks/hooks.json` (PreCompact event triggers this script)
- **Similar Patterns**: Other hook scripts using exit codes (`hooks/scripts/session-start.sh`, `hooks/scripts/postcommit-update.sh`)
- **Tests**: N/A — shell script exit code change; verified by triggering PreCompact hook and observing stderr visibility
- **Documentation**: `docs/claude-code/hooks-reference.md`
- **Configuration**: N/A

## Reference

- `docs/claude-code/hooks-reference.md` — Exit code 2 behavior table: `PreCompact | No [can't block] | Shows stderr to user only`

PreCompact exit 2 is safe — the event cannot block compaction. Exit 2 simply makes stderr visible to the user.

## Impact

- **Priority**: P4
- **Effort**: Trivial — change exit code
- **Risk**: None — PreCompact cannot block

## Labels

`enhancement`, `hooks`, `precompact`, `ux`

## Session Log
- `/ll:format_issue --all --auto` - 2026-02-13

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4
