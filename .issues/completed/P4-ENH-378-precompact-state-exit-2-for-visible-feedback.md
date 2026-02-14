---
discovered_date: 2026-02-12
discovered_by: hooks-reference-audit
---

# ENH-378: precompact-state.sh should use exit 2 for user-visible feedback

## Summary

`hooks/scripts/precompact-state.sh` outputs a state-preservation message to stderr but exits with code 0. Per the hooks reference, PreCompact stderr on exit 0 is only visible in verbose mode. Using exit 2 (which is non-blocking for PreCompact) would make the message visible to the user.

## Location

- **File**: `hooks/scripts/precompact-state.sh`
- **Line(s)**: 82-84
- **Anchor**: `exit 0` after stderr echo at end of script

## Current Behavior

```bash
echo "[ll] Task state preserved before context compaction. Check .claude/ll-precompact-state.json if resuming work." >&2
exit 0  # stderr only visible in verbose mode (Ctrl+O)
```

## Expected Behavior

```bash
echo "[ll] Task state preserved before context compaction. Check .claude/ll-precompact-state.json if resuming work." >&2
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

## Scope Boundaries

- Not changing the stderr message text itself
- Not modifying any other hook scripts' exit codes
- Not adding new PreCompact hook behavior beyond exit code change

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

- **Priority**: P4 — Low priority, cosmetic UX improvement with no functional impact
- **Effort**: Trivial — single exit code change in one file
- **Risk**: None — PreCompact exit 2 is non-blocking per hooks reference; cannot disrupt compaction
- **Breaking Change**: No

## Labels

`enhancement`, `hooks`, `precompact`, `ux`

## Resolution

- **Action**: improve
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `hooks/scripts/precompact-state.sh`: Changed `exit 0` to `exit 2` at line 84 for user-visible stderr feedback
- `scripts/tests/test_hooks_integration.py`: Updated TestPrecompactState assertions to expect exit code 2

### Verification Results
- Tests: PASS (2733 passed)
- Lint: PASS
- Types: PASS
- Integration: PASS

## Session Log
- `/ll:format-issue --all --auto` - 2026-02-13
- `/ll:manage-issue` - 2026-02-13T19:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dcc8e5f2-3df0-4b8a-8723-252e07ec9b1a.jsonl`

---

## Status

**Completed** | Created: 2026-02-12 | Completed: 2026-02-13 | Priority: P4
