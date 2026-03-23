---
discovered_date: 2026-03-23
discovered_by: capture-issue
---

# BUG-869: context-monitor.sh lock timeout leaves only 1s before hook timeout

## Summary

`context-monitor.sh` uses a 4-second lock acquisition timeout, but the hook itself has a 5-second timeout in `hooks.json`. In the worst case, the lock takes ~4s to acquire, leaving only ~1 second for all remaining operations: two `jq` invocations, state reads, estimate calculation, state write, and potentially a JSONL parse. Under disk pressure or contention, the hook times out mid-execution and may leave the state file inconsistent. This hook fires after every single tool call.

## Steps to Reproduce

1. Run a session with heavy parallel tool use or on a slow filesystem
2. Observe `context-monitor.sh` occasionally failing to complete within 5 seconds
3. State file may be partially written (if timeout occurs during `write_state`)

## Current Behavior

`acquire_lock "$STATE_LOCK" 4` waits up to 4 seconds. After acquisition, the remaining operations must complete within ~1 second before the 5-second hook timeout triggers, killing the process mid-execution.

## Expected Behavior

After the lock is acquired, there should be enough time budget remaining (at least 2–3 seconds) for all post-acquisition operations to complete reliably, even under moderate I/O load.

## Root Cause

- **File**: `hooks/scripts/context-monitor.sh`
- **Anchor**: `acquire_lock` call in `main()`
- **Cause**: Lock timeout (4s) and hook timeout (5s) are too close together. The design assumed fast lock acquisition, but the 1s margin is insufficient when lock contention is high or I/O is slow.

## Motivation

`context-monitor.sh` runs after every tool call (matcher `*`). A systematic timeout means context tracking becomes unreliable in longer sessions, defeating the hook's purpose. State file corruption from a mid-write timeout could also cause unexpected behavior on the next invocation.

## Proposed Solution

Reduce the lock timeout to 3 seconds, leaving ~2 seconds for post-acquisition ops:

```bash
# Before:
if ! acquire_lock "$STATE_LOCK" 4; then

# After:
if ! acquire_lock "$STATE_LOCK" 3; then
```

Alternatively, increase the hook timeout in `hooks.json` from 5 to 8 seconds (but this delays every tool call response, so reducing the lock timeout is preferred).

## Integration Map

### Files to Modify
- `hooks/scripts/context-monitor.sh` — reduce `acquire_lock` timeout argument

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — defines the 5s `PostToolUse` timeout for this hook

### Similar Patterns
- N/A — `acquire_lock` pattern is unique to `context-monitor.sh`

### Tests
- TBD — test that hook completes within timeout under simulated lock contention

### Documentation
- N/A

### Configuration
- `hooks/hooks.json` — PostToolUse timeout (5s) is the constraint; no change needed if lock timeout is reduced

## Implementation Steps

1. Change `acquire_lock "$STATE_LOCK" 4` to `acquire_lock "$STATE_LOCK" 3` in `context-monitor.sh`
2. Optionally add a comment noting the intentional margin: `# 3s leave ~2s for post-acquisition ops within 5s hook timeout`
3. Verify in a long session that state file updates consistently

## Impact

- **Priority**: P3 - Affects reliability of context tracking under contention; not a crash but degrades a key monitoring feature
- **Effort**: Small - Single argument change
- **Risk**: Low - Reducing the timeout makes the hook fail faster under contention (vs. timing out after blocking longer); state is always written atomically
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`hooks`, `bug`, `captured`

## Session Log
- `/ll:format-issue` - 2026-03-23T22:42:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9850963-0ae2-487e-9014-ade593329bce.jsonl`

- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0e087610-8d6c-49f4-bacd-b3c561cb7252.jsonl`

---

**Open** | Created: 2026-03-23 | Priority: P3
