---
id: ENH-3130
status: open
priority: P3
captured_at: "2026-08-09T05:58:12Z"
discovered_date: 2026-08-09
discovered_by: capture-issue
relates_to: [ENH-3129]
---

# ENH-3130: Give the automation timeout kill a SIGTERM finalize grace before SIGKILL

## Summary

When a wall-clock or idle timeout fires, `run_claude_command` sends an
immediate `SIGKILL` to the whole process group. An agent that is seconds from
finalizing gets no chance to land its work. Send `SIGTERM` first, allow a
bounded grace window for the host CLI to wind down, and escalate to `SIGKILL`
only if it does not exit.

## Current Behavior

`_kill_process_group` (`scripts/little_loops/subprocess_utils.py:313-317`) is
unconditionally lethal:

```python
try:
    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
except (ProcessLookupError, PermissionError, AttributeError):
    process.kill()
```

Both timeout paths call it directly (`subprocess_utils.py:475` wall-clock,
`:486` idle) and then `process.wait(timeout=10)`. That 10-second wait is only
*reaping* an already-SIGKILLed process — it is not a grace period, and nothing
can run during it. There is no `SIGTERM` anywhere in the path.

This is inconsistent with the clean-exit path, which already has a generous
wind-down: `post_stream_close_grace_seconds` (default 300,
`subprocess_utils.py:604`) exists specifically so in-flight work can finish
after the streams close (BUG-2718).

Observed consequence (FEAT-3078): the agent committed at `00:35:36`, the
SIGKILL landed at `00:35:51`. It happened to finish first — 15 seconds the
other way and the work would have been lost mid-write.

## Expected Behavior

On timeout:

1. `SIGTERM` the process group.
2. Wait up to a configurable grace window for a clean exit.
3. `SIGKILL` the group only if still alive after the window.
4. `subprocess.TimeoutExpired` is still raised either way, so callers —
   including the BUG-3131 verification in `issue_manager.py`'s handler — are
   unchanged.

## Motivation

The timeout is a blunt instrument applied at an arbitrary instant. Killing
mid-`git commit` or mid-file-write risks a genuinely corrupted working tree,
which is strictly worse than the run simply taking longer. A grace window
converts most timeout kills from "work destroyed" into "work landed, then
stopped" — and it composes with the BUG-3131 handler fix, which can only
detect a *completed* lifecycle. Making completion more likely to happen is the
other half of that fix.

## Proposed Solution

Give `_kill_process_group` an escalation parameter rather than adding a second
kill helper:

```python
def _kill_process_group(process, grace_seconds: float = 0.0) -> None:
    """SIGTERM the group, then SIGKILL after grace_seconds if still alive.

    grace_seconds=0 preserves the historical immediate-SIGKILL behavior for
    callers that need it.
    """
```

Both timeout call sites pass the configured grace; any other caller keeps the
default and is unaffected.

Add `automation.timeout_kill_grace_seconds` to the schema (suggested default
**30** — long enough for a commit and a lifecycle write, short enough not to
meaningfully extend a run), threaded to `run_claude_command` alongside the
existing `post_stream_close_grace_seconds` parameter (`subprocess_utils.py:337`).

**Caveat worth verifying during implementation**: whether the host CLI
(`claude`) actually handles `SIGTERM` gracefully — flushes, finishes the
in-flight tool call, exits — or just dies. If it dies on `SIGTERM` the same
way, the grace window buys nothing and the issue should be closed with that
finding recorded. A spike against the real binary is the cheap first step
(see `/ll:spike`). Note also that `SIGTERM` goes to the whole group, so any
tool subprocess the agent spawned receives it too.

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — `_kill_process_group` and the
  two timeout call sites at `:475` and `:486`
- `scripts/little_loops/config-schema.json` — `automation` block
- `scripts/little_loops/config/automation.py` — dataclass + `from_dict`
- `scripts/little_loops/config/core.py` — `to_dict` serializer

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` — passes automation timeouts through
- `scripts/little_loops/worker_pool.py` — `ll-parallel`/`ll-sprint` share
  `run_claude_command`; confirm they get sane behavior or an explicit default
- any other `_kill_process_group` caller (grep before changing the signature)

### Similar Patterns
- `post_stream_close_grace_seconds` (`subprocess_utils.py:337`, `:604`) — the
  existing grace-window parameter to model naming and threading on

### Tests
- `scripts/tests/test_subprocess_utils.py` — signal-order assertions
- `scripts/tests/test_feat3033_idle_timeout.py` — idle path must escalate too
- `scripts/tests/test_fsm_signal_integration.py` — check for interaction

### Documentation
- `docs/reference/CONFIGURATION.md` — new key
- `docs/development/TROUBLESHOOTING.md` — timeout-kill behavior

### Configuration
- `scripts/little_loops/config-schema.json`

## Implementation Steps

1. Spike first: does `claude` exit cleanly on `SIGTERM`? If not, stop and close
   this issue with the finding.
2. Add the `grace_seconds` parameter to `_kill_process_group`, defaulting to 0
   so existing callers are byte-identical.
3. Thread `automation.timeout_kill_grace_seconds` through schema, dataclass,
   serializer, and `run_claude_command`.
4. Pass it at both timeout call sites.
5. Tests asserting SIGTERM-then-SIGKILL ordering and that the escalation
   actually fires when the child ignores SIGTERM.
6. Docs.

## Impact

- **Risk**: Medium. Touches the kill path shared by every automation driver; a
  bug here means processes that never die. The `grace_seconds=0` default keeps
  the blast radius to the two call sites that opt in.
- **Benefit**: Fewer corrupted working trees; more timeout kills that leave
  committed, verifiable work behind.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/CONFIGURATION.md` | Documents the new `automation.*` grace key |
| `docs/development/TROUBLESHOOTING.md` | Timeout and hung-process guidance |
| `docs/reference/API.md` | `little_loops.subprocess_utils` module reference |

## Status

- **Current**: open
- **Blockers**: None

## Session Log
- `/ll:capture-issue` - 2026-08-09T05:59:57 - `ce451e9a-4952-45a2-828c-106f17467622.jsonl`
