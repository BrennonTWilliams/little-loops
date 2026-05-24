---
captured_at: '2026-05-24T04:52:29Z'
discovered_date: '2026-05-24'
discovered_by: capture-issue
status: open
depends_on: [BUG-1668]
relates_to: [ENH-1669, ENH-1667]
---

# ENH-1670: Optional log capture for foreground runs (tee to `{instance_id}.log`)

## Summary

Background runs persist child stdout/stderr to `{instance_id}.log` via `run_background()`. Foreground runs write nothing to disk — output goes only to the user's terminal. This means foreground runs are unrecoverable for post-hoc inspection once the terminal is closed. Add an optional path that tees foreground output to `{instance_id}.log` as well, giving operators a recoverable artifact without sacrificing the live-terminal experience.

## Motivation

When investigating loop behavior after the fact, the events file (`{instance_id}.events.jsonl`) shows structured state transitions but lacks the free-form stdout that often contains the real explanation (LLM tool output, error tracebacks, debug prints). Background runs already have this — foreground runs should be able to opt in. BUG-1668 makes the `Log:` line honest about run mode, but the underlying gap (no log file for foreground) remains a real ergonomic loss.

## Current Behavior

- `run_background()` at `scripts/little_loops/cli/loop/_helpers.py:540, 589` redirects child stdout/stderr to `{instance_id}.log` via `subprocess.Popen(..., stdout=log_fh, stderr=log_fh, ...)`.
- `run_foreground()` at `_helpers.py:608+` does not redirect; output streams to the controlling terminal only.
- Once the terminal closes or scrollback rolls off, the run output is gone.

## Expected Behavior

A new flag (e.g. `--log` or `--capture`) or a config option causes `run_foreground()` to additionally tee stdout/stderr to `{instance_id}.log` while still streaming to the terminal. Default off (to preserve current behavior and not surprise users with new disk writes), but easy to enable for diagnostic runs.

## Proposed Solution

In `run_foreground()`, when `--log`/`--capture` is set:

1. Open `{instance_id}.log` for writing in the same way `run_background()` does.
2. Use a tee approach — either spawn a subprocess with stdout/stderr piped through a Python tee reader, or use `subprocess.run(..., stdout=subprocess.PIPE)` with the parent writing each line to both `sys.stdout` and the log file.

The Python-side tee is preferable because the existing `run_foreground()` already drives the child synchronously; adding a line-by-line forwarder is a minimal extension.

Once the file exists, BUG-1668's three-way `Log:` label naturally degrades to the existing `Log: <path>` case for these runs.

### Flag vs config

Two reasonable shapes:

- CLI flag: `ll-loop run <loop> --log` — explicit per-invocation opt-in.
- Config: `.ll/ll-config.json` → `loop.capture_foreground_logs: true` — persistent default.

Recommend both, with the flag overriding the config value when present.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/_helpers.py` — `run_foreground()` (~line 608+); add tee logic guarded by the new flag/config.
- `scripts/little_loops/cli/loop/__init__.py` — register the new `--log`/`--capture` flag on the `run` subcommand.
- `scripts/little_loops/cli/loop/run.py` — propagate the flag from argparse into `run_foreground()`.

### Dependent Files (Callers/Importers)

- BUG-1668's `Log:` label helper — once a foreground run has a `.log`, the label should render as `Log: <path>` (no special case needed; the absence test already handles it).

### Similar Patterns

- `run_background()` at `_helpers.py:540, 589` — direct redirect via `subprocess.Popen(..., stdout=log_fh, stderr=log_fh, ...)`.
- Python `tee`-like helpers in the standard library are rare; the codebase may need a small `_tee_stream(src, *dsts)` helper.

### Tests

- `scripts/tests/test_cli_loop_run.py` (or equivalent foreground-run test file) — assert that `--log` produces a `.log` file with captured content; assert that without the flag, no file is written.
- Verify that terminal output is not suppressed when `--log` is on.

### Documentation

- `docs/reference/CLI.md` — document the new `--log`/`--capture` flag on `ll-loop run`.
- `docs/guides/LOOPS_GUIDE.md` — note the option in the monitoring/debugging section.

### Configuration

- `config-schema.json` — add `loop.capture_foreground_logs` (boolean, default false) if going with the config-knob approach.

## Implementation Steps

1. Add the `--log` flag to the `run` subcommand argparse setup.
2. Thread the flag through to `run_foreground()`.
3. In `run_foreground()`, open the log file (matching `run_background()`'s path/naming) when the flag is set.
4. Replace the direct child-process attach with a line-streaming tee that writes to both `sys.stdout` and the log file (and same for stderr).
5. Add tests.
6. Document the flag.

## Impact

- **Priority**: P4 — useful but a feature, not a bug fix. Most users won't notice; investigators will appreciate it.
- **Effort**: Small-to-medium — tee logic is straightforward but needs care around line buffering, signal handling, and TTY behavior to avoid breaking interactive runs.
- **Risk**: Medium — touching the foreground I/O path risks regressions in terminal interaction (especially around stderr ordering, ANSI escape passthrough, and signal forwarding).
- **Breaking Change**: No (opt-in only).

## Scope Boundaries

- Foreground runs only. Background runs already capture logs.
- No retroactive capture for already-running foreground instances (not technically recoverable).
- No log rotation, compression, or retention policy — those are separate concerns.

## API/Interface

New CLI flag on `ll-loop run`:

```
ll-loop run <loop> [--log | --capture]
```

- `--log` (alias `--capture`): boolean flag, default false. When set, foreground runs tee stdout/stderr to `{instance_id}.log` in addition to streaming to the terminal.

New config key in `.ll/ll-config.json` (`config-schema.json` addition):

```json
{
  "loop": {
    "capture_foreground_logs": false
  }
}
```

Resolution precedence: CLI flag overrides config when present; otherwise config value applies; otherwise default false.

No changes to existing public function signatures. Internally, `run_foreground()` in `scripts/little_loops/cli/loop/_helpers.py` gains an optional `capture_log: bool = False` keyword parameter.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ll-loop`, `cli`, `observability`, `captured`

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-24T06:05:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8cdfeedd-6a9f-4683-a41d-9ff3860ac7e0.jsonl`
- `/ll:format-issue` - 2026-05-24T05:08:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/71b13280-abbe-4af9-a47c-adb27bd0900e.jsonl`
- `/ll:capture-issue` - 2026-05-24T04:52:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f605fdcc-8000-4585-8dc4-835fc0020291.jsonl`

---

## Status

**Open** | Created: 2026-05-24 | Priority: P4

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The artifact path for this issue (`{instance_id}.log`) should be verified against ENH-1667's `.loops/runs/<name>/meta-eval.jsonl` convention — both define per-run observability artifacts; align on directory policy before implementing. Also, ENH-1669 (auto-reconcile orphaned state files) addresses the same foreground-run gap from a different angle (state accuracy vs. log capture); these two issues form a cluster with BUG-1668 and should be sequenced together.
