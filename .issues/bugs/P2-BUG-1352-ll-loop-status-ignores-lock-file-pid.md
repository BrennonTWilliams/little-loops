---
captured_at: '2026-05-03T18:44:03Z'
completed_at: '2026-05-03T22:29:56Z'
discovered_date: '2026-05-03'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 85
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
status: done
---

# BUG-1352: `ll-loop status` ignores `.lock` file PID, reports `null`

## Summary

`ll-loop status <name> --json` returns `"pid": null` even when a `.lock` file exists with a live PID holding the scope. The command reads only from a `.pid` file (used for background-mode tracking), never from the `.lock` file managed by `LockManager`. This causes `cleanup-loops` to misclassify scope-holding zombie processes as clean interrupted loops, masking the real blocker.

## Current Behavior

Running `ll-loop status autodev --json` on a loop whose state is `interrupted` but whose `.lock` file holds a live orphaned PID (e.g. 58522) returns:

```json
{ "status": "interrupted", "pid": null, ... }
```

The `cleanup-loops` skill reads `pid: null`, skips the stale-interrupted cleanup path (which requires `pid` non-null), and reports the loop as needing no action. Attempting `ll-loop run` on the same scope then fails with `Scope conflict with running loop: autodev`.

## Expected Behavior

`ll-loop status` should check both the `.pid` file **and** the `.lock` file. If a `.lock` file exists and its PID is alive, `pid` should be populated from the lock file. If the lock-file PID is dead, it should be treated as a stale lock (reported as such or cleaned up). The `cleanup-loops` skill can then detect and surface the orphaned lock process.

## Motivation

`cleanup-loops` is the primary diagnostic tool for unblocking stuck loops. Its effectiveness depends on `ll-loop status` accurately surfacing the PID. A loop stuck in scope conflict (blocking all new runs on the same directory) appears clean in the output, requiring manual inspection of `.lock` files to diagnose. This turns a 5-second fix into a multi-minute investigation.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Anchor**: `_status_single()` (line ~47) — called by `cmd_status()` (line ~114)
- **Cause**: `pid = _read_pid_file(pid_file)` reads exclusively from `<stem>.pid`. Foreground runs and queue-acquired locks are written to `<stem>.lock` by `LockManager.acquire()` in `concurrency.py`. `_status_single()` never opens the `.lock` file.

The `.lock` file lives at `.loops/.running/<stem>.lock` and contains `{"pid": <int>, "scope": [...], ...}`. The `.pid` file is only written when `--foreground-internal` is passed (background subprocess mode). Foreground runs hold the scope via `.lock` only — so `pid` is always null for foreground-run loops.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The actual PID reading for status happens in `_status_single()` (lines 47–111), not `cmd_status()` itself. `cmd_status()` delegates to `_status_single()` for single-instance cases and builds inline for multi-instance.
- `_status_single()` computes `stem = instance_id or loop_name` and builds `pid_file = running_dir / f"{stem}.pid"`. The `.lock` file for the same instance is at `running_dir / f"{stem}.lock"` — the proposed solution must use `stem`, not `loop_name`, to match the correct file.
- `.lock` file JSON schema (from `ScopeLock.to_dict()` in `concurrency.py` line ~62): `{"loop_name": str, "scope": [str, ...], "pid": int, "started_at": str}` — `pid` is always an integer (`os.getpid()` at acquire time).
- For foreground runs: both `.pid` and `.lock` are written by `run.py` (`.pid` at line 214, `.lock` via `lock_manager.acquire()` at line 230). Both are removed by atexit/finally on clean exit. In a hard-kill or partial cleanup, the `.lock` may outlive the `.pid`.

## Steps to Reproduce

1. Run `ll-loop run autodev ENH-1341 -v` (foreground, no `--background`)
2. Interrupt or let it complete with status `interrupted`
3. Verify `.loops/.running/autodev.lock` exists and its PID is alive: `kill -0 <pid> && echo alive`
4. Run `ll-loop status autodev --json`
5. Observe `"pid": null` despite the live lock-file PID

## Error Messages

```
# From ll-loop run ENH-1340 after the above:
[13:37:05] Scope conflict with running loop: autodev
[13:37:05]   Conflicting scope: ['/Users/.../little-loops']
[13:37:05]   Use --queue to wait for it to finish
```

## Proposed Solution

In `cmd_status()`, after reading the `.pid` file, fall back to reading the `.lock` file if `pid` is None:

```python
# In lifecycle.py: cmd_status()
running_dir = loops_dir / ".running"
pid_file = running_dir / f"{loop_name}.pid"
pid = _read_pid_file(pid_file)

# Fall back to lock file PID if no .pid file
if pid is None:
    lock_file = running_dir / f"{loop_name}.lock"
    if lock_file.exists():
        try:
            lock_data = json.loads(lock_file.read_text())
            pid = lock_data.get("pid")
        except (OSError, json.JSONDecodeError):
            pass
```

This makes `pid` non-null for foreground-run loops still holding their scope lock, allowing `cleanup-loops` to detect and clean them.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Corrected fix location and stem naming** — the fix belongs in `_status_single()` (line ~47), not `cmd_status()`. The variable `stem = instance_id or loop_name` is already computed there; the lock file path must use `stem`:

```python
# In lifecycle.py: _status_single() — after existing _read_pid_file call
stem = instance_id or loop_name
pid_file = running_dir / f"{stem}.pid"
pid = _read_pid_file(pid_file)

# Fall back to lock file PID if no .pid file
if pid is None:
    lock_file = running_dir / f"{stem}.lock"
    if lock_file.exists():
        try:
            with open(lock_file) as f:
                lock_data = json.load(f)
            pid = lock_data.get("pid")
        except (json.JSONDecodeError, KeyError, OSError):
            pass
```

**Exception tuple**: `concurrency.py` uses `(json.JSONDecodeError, KeyError, FileNotFoundError)` for all `.lock` file reads (lines 189, 218) — `KeyError` is needed because `ScopeLock.from_dict()` accesses keys by name. Use `(json.JSONDecodeError, KeyError, OSError)` to also cover read errors.

**`pid_source` field** (from implementation step 3): after resolving `pid`, set `pid_source = "lock_file"` if it came from the lock file, `"pid_file"` otherwise, and include it in the JSON output dict alongside `pid`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/lifecycle.py` — `_status_single()` (line ~47): add lock-file PID fallback using `stem = instance_id or loop_name` for path; also fix multi-instance branch in `cmd_status()` (lines 134–154) which has the same bare `.pid`-only read

_Wiring pass added by `/ll:wire-issue`:_
- `skills/cleanup-loops/SKILL.md` — Step 3 classification branches on `pid` non-null to run `.pid`-file removal; after fix, `pid` may come from `.lock` file — Step 3 must branch on `pid_source` to remove the correct artifact (`"pid_file"` → `rm .pid`; `"lock_file"` → `rm .lock`) [Agent 2]

### Dependent Files (Callers/Importers)
- `skills/cleanup-loops/SKILL.md` — reads `pid` from `ll-loop status --json`; benefits automatically once fixed
- `scripts/little_loops/fsm/concurrency.py` — `LockManager`: source of truth for `.lock` file format

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/__init__.py` — dispatches `cmd_status(args.loop, loops_dir, logger, args)` as the `status` subcommand handler [Agent 1]
- `skills/analyze-loop/SKILL.md` — reads `pid` from `ll-loop status --json` for display in instance disambiguation; non-breaking, display only [Agent 2]
- `skills/assess-loop/SKILL.md` — reads `pid` from `ll-loop status --json` for display in instance disambiguation; non-breaking, display only [Agent 2]

### Similar Patterns
- `cmd_stop()` in `lifecycle.py` also reads only from `.pid` file — see BUG-1353

### Tests
- `scripts/tests/test_cli_loop_lifecycle.py` — add test: status of foreground-interrupted loop shows lock-file PID
- `scripts/tests/test_ll_loop_commands.py` — add scenario with live lock-file PID and no `.pid` file

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_background.py` — `TestCmdStatusWithPid` exercises `cmd_status` with PID liveness; add lock-file PID variants alongside existing `.pid` file tests [Agent 1, Agent 3]
- Update `TestCmdStatusJson.test_status_json_output` in `test_ll_loop_commands.py` — assert `"pid_source" in data` and verify value [Agent 3]
- Update `TestCmdStatusLogFile.test_status_json_includes_log_fields` in `test_cli_loop_lifecycle.py` — add `pid_source` assertion [Agent 3]

### Documentation
- `skills/cleanup-loops/SKILL.md` — Step 2 field description states `pid` comes from `.pid` file only; Step 3 `stale-interrupted` cleanup action removes `.pid` file — both need updating (see Files to Modify above)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `#### ll-loop status <loop>` section: add `pid_source` to `--json` field list; update `pid` field description to note it may come from `.lock` file [Agent 2]
- `docs/guides/LOOPS_GUIDE.md` — paragraph "The PID is stored in `.loops/.running/<instance-id>.pid`" under `### Monitoring progress` needs updating to mention `.lock` file fallback [Agent 2]
- `docs/reference/COMMANDS.md` — `### /ll:cleanup-loops` Step 5 description states stale-interrupted cleanup removes `.pid` files; needs updating for lock-sourced PIDs [Agent 2]

### Configuration
- N/A

## Implementation Steps

1. ~~Read lock-file format from `LockManager.acquire()` in `concurrency.py` to confirm JSON shape~~ — confirmed: `{"loop_name": str, "scope": [str], "pid": int, "started_at": str}` from `ScopeLock.to_dict()` at `concurrency.py` line ~62
2. Add lock-file PID fallback in `_status_single()` (line ~47, not `cmd_status()`) using `stem` for the path; catch `(json.JSONDecodeError, KeyError, OSError)`
3. Add a `pid_source` field to the JSON output dict (`"pid_file"` or `"lock_file"`) so callers can distinguish; emit only when `args.json` is true (lines 76–83 of `_status_single()`)
4. Add tests in `scripts/tests/test_cli_loop_lifecycle.py` — follow `TestCmdStatusLogFile.test_status_shows_log_file_details` pattern: `running_dir = tmp_path / ".running"; running_dir.mkdir(parents=True)`, write `(running_dir / "test-loop.lock").write_text(json.dumps({"loop_name": "test-loop", "scope": ["/tmp"], "pid": 12345, "started_at": "..."}))`, patch `_find_instances` with `(None, mock_state)`, call with `args = argparse.Namespace(json=True)`, assert `json.loads(capsys.readouterr().out)["pid"] == 12345`
5. Verify `cleanup-loops` skill correctly classifies the loop after the fix

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Fix multi-instance branch in `lifecycle.py` `cmd_status()` (lines 134–154) — apply the same `.lock` fallback and `pid_source` field to the inline dict-building path used when multiple instances are found; otherwise single-instance and multi-instance JSON output diverge
7. Update `skills/cleanup-loops/SKILL.md` Step 3 — branch on `pid_source`: `"pid_file"` → `rm .loops/.running/<loop>.pid`; `"lock_file"` → `rm .loops/.running/<loop>.lock`; prevents cleanup silently doing nothing when PID came from lock file
8. Update `docs/reference/CLI.md` — add `pid_source` to the `--json` field table under `#### ll-loop status <loop>`; note `pid` may come from either `.pid` or `.lock` file
9. Update `docs/guides/LOOPS_GUIDE.md` — correct the paragraph stating PID is stored only in the `.pid` file
10. Add `pid_source` assertions to `TestCmdStatusJson.test_status_json_output` and `TestCmdStatusLogFile.test_status_json_includes_log_fields`

## Impact

- **Priority**: P2 — blocks new loop runs silently; `cleanup-loops` gives false "no action needed"
- **Effort**: Small — surgical addition of ~10 lines in `cmd_status()`; lock-file format already defined
- **Risk**: Low — read-only change to status output; no state mutation
- **Breaking Change**: No (adds `pid` data where it was previously null)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `ll-loop`, `concurrency`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-05-03T22:24:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2cf85333-8644-4f07-91ec-82f34aa1df7b.jsonl`
- `/ll:confidence-check` - 2026-05-03T23:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8cc408e7-c90c-40dd-af56-67e3959ef6e8.jsonl`
- `/ll:wire-issue` - 2026-05-03T22:20:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/59b21eda-ece5-4df3-a5a3-d7d8032c40d7.jsonl`
- `/ll:refine-issue` - 2026-05-03T22:15:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9f73a849-e051-4a90-8a64-60e7f615bdca.jsonl`
- `/ll:format-issue` - 2026-05-03T21:54:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c0105a40-4f11-453e-842b-a9855e8ac301.jsonl`

- `/ll:capture-issue` - 2026-05-03T18:44:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d6eb746-1937-4f45-bb7f-14d33480c49e.jsonl`

---

## Resolution

**Status**: Fixed

**Changes**:
- `scripts/little_loops/cli/loop/lifecycle.py` — `_status_single()`: added lock-file PID fallback after `.pid` read; added `pid_source` field (`"pid_file"`, `"lock_file"`, or `null`) to JSON output. Multi-instance JSON and human-readable branches updated with same fallback.
- `scripts/tests/test_cli_loop_lifecycle.py` — added `TestCmdStatusLockFilePid` class with 6 tests covering lock-file PID, pid_source values, malformed lock, human-readable output, and multi-instance JSON. Updated `test_status_json_includes_log_fields` to assert `pid_source` in output.
- `scripts/tests/test_ll_loop_commands.py` — updated `TestCmdStatusJson.test_status_json_output` to assert `pid_source` in JSON output.
- `skills/cleanup-loops/SKILL.md` — Step 2 field table updated with `pid_source`; Step 3/6 stale-interrupted cleanup now branches on `pid_source` to remove `.pid` or `.lock` file accordingly.
- `docs/reference/CLI.md` — `--json` flag description updated with `pid_source` field.
- `docs/guides/LOOPS_GUIDE.md` — corrected paragraph about PID storage to mention both `.pid` and `.lock` fallback.
- `docs/reference/COMMANDS.md` — cleanup-loops Step 5 description updated.

**Closed**: 2026-05-03T22:29:56Z

- `/ll:manage-issue` - 2026-05-03T22:29:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/acb1b5bd-8908-467d-b149-60c63c6ffb36.jsonl`

**Resolved** | Created: 2026-05-03 | Priority: P2
