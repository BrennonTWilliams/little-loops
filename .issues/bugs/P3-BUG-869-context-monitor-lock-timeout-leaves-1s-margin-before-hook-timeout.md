---
discovered_date: 2026-03-23
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
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
- `hooks/hooks.json:49` — defines the 5s `PostToolUse` timeout for this hook (`matcher: "*"`, fires on every tool call)
- `hooks/scripts/lib/common.sh:8-38` — defines `acquire_lock()` (flock + mkdir fallback); `common.sh:59-85` defines `atomic_write_json()` used by `write_state()`

### Similar Patterns
- `hooks/scripts/precompact-state.sh:72-79` — PreCompact hook (also 5s timeout) uses `acquire_lock "$STATE_LOCK" 3`; identical pattern, correct 2s margin
- `hooks/scripts/check-duplicate-issue-id.sh:92-99` — PreToolUse hook (also 5s timeout) uses `acquire_lock "$ISSUE_LOCK" 3` with fail-open fallback
- Both sibling scripts already use 3s — the 4s in `context-monitor.sh` is an outlier

### Tests
- `scripts/tests/test_hooks_integration.py:38-92` — `TestContextMonitor.test_concurrent_updates` fires 10 simultaneous invocations via `ThreadPoolExecutor(max_workers=10)` and asserts all 10 state updates are recorded; uses `subprocess.run(..., timeout=6)` (1s above the hook timeout); this is the direct coverage for lock contention
- No test currently simulates slow lock acquisition (e.g., deliberately holding the lock for 3-4s to trigger the tight margin); the existing concurrent test exercises the happy path but not the near-timeout path

### Documentation
- `docs/development/TROUBLESHOOTING.md` — references the 4s lock timeout and PostToolUse debugging; should be updated after fix to reflect 3s

### Configuration
- `hooks/hooks.json:49` — `"timeout": 5` for the PostToolUse `context-monitor.sh` entry; no change needed if lock timeout is reduced

## Implementation Steps

1. In `hooks/scripts/context-monitor.sh:226`, change `acquire_lock "$STATE_LOCK" 4` → `acquire_lock "$STATE_LOCK" 3`
2. Update the comment at `context-monitor.sh:224` from `# Acquire lock for state file read-modify-write (4s timeout, hook timeout is 5s)` to `# Acquire lock for state file read-modify-write (3s timeout, ~2s margin within 5s hook timeout)`
3. Update `docs/development/TROUBLESHOOTING.md` to reflect the new 3s lock timeout (search for "4s" in that file)
4. Run `python -m pytest scripts/tests/test_hooks_integration.py::TestContextMonitor -v` to verify concurrent access tests still pass

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
- `/ll:confidence-check` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/07aaa052-b8a9-4322-8503-8071eb36b3dd.jsonl`
- `/ll:refine-issue` - 2026-03-23T22:58:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/07aaa052-b8a9-4322-8503-8071eb36b3dd.jsonl`
- `/ll:format-issue` - 2026-03-23T22:42:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9850963-0ae2-487e-9014-ade593329bce.jsonl`

- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0e087610-8d6c-49f4-bacd-b3c561cb7252.jsonl`

---

**Open** | Created: 2026-03-23 | Priority: P3
