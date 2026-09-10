---
id: BUG-3439
type: BUG
title: FSM shell actions pass the whole rendered script via argv; E2BIG on Linux above
  128 KiB
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
parent: EPIC-3436
---

# BUG-3439: FSM shell actions pass the whole rendered script via argv; E2BIG on Linux above 128 KiB

## Summary

DefaultActionRunner spawns every shell action as ["bash", "-c", action] (fsm/runners.py:348), so any :shell-interpolated capture exceeding Linux MAX_ARG_STRLEN (131072 B) raises OSError Errno 7 in every loop, not just loop-router. Reproduced by test_write_sub_loop_output_survives_oversized_stream (rendered 264085 B). Fix at the runner: feed the script on stdin (bash -s) or via a temp file, mirror in the executor _run_subprocess shell path, keep the loop-router test as the regression pin and make its docstring platform-honest (A4 / BUG-3334 AC14).

## Current Behavior

`DefaultActionRunner.run`'s shell branch builds `cmd = ["bash", "-c", action]` (fsm/runners.py:348) and passes the fully-rendered script as a single argv element to `subprocess.Popen`. Linux caps any single argv/env string at `MAX_ARG_STRLEN` (131072 B, `include/uapi/linux/binfmts.h`), so a rendered action above that raises `OSError: [Errno 7] Argument list too long` at spawn — before the process ever runs, and regardless of the state's `on_error` handling since the failure happens inside the runner call.

The same argv pattern exists in `_run_cmd` (runner_spec.py:323, `["bash", "-c", spec.target]`), giving loop-spec `cmd:` runners the identical exposure.

Correction to the Summary's claim about the executor: `_run_subprocess` (fsm/executor.py:2966) has **no shell path** — it is called only for `mcp-call` commands (executor.py:2480). Executor shell states delegate to `DefaultActionRunner`, so fixing the runner fixes the executor path transitively.

## Steps to Reproduce

1. Render any shell action whose interpolated body exceeds 131072 B — e.g. loop-router's `write_sub_loop_output` with a `sub_loop_output` capture of ~216000 B raw (shlex.quote expansion renders it to 264085 B, as in `test_write_sub_loop_output_survives_oversized_stream`, scripts/tests/test_loop_router.py:234).
2. Run the loop on Linux (macOS's per-argv limit is far larger, so the same action passes on darwin — the existing test is not platform-honest about this).
3. `subprocess.Popen(["bash", "-c", action])` raises `OSError: [Errno 7] Argument list too long` at exec time.

## Expected Behavior

A shell action of any renderable size spawns successfully: the runner passes the script body out-of-band (stdin or temp file) rather than as an argv element, so the OS per-argument limit never applies to loop scripts. Streamed captures written to `${context.run_dir}/` survive intact (BUG-3334 AC14), and the regression test states its platform boundary honestly instead of relying on darwin's larger argv limit.

## Proposed Solution

Two viable mechanics (Summary offers both):

1. **Temp file (recommended)** — write the rendered action to a `tempfile.mkstemp(suffix=".sh")` file in the existing try/finally scope, spawn `["bash", str(path)]`, unlink in `finally`. Deadlock-free regardless of size; no pipe-buffer interaction with the selector loop.
2. **stdin (`bash -s`)** — spawn `["bash", "-s"]` and feed `action` via `process.stdin` from a writer thread. Avoids temp files, but a naive inline `stdin.write(action)` deadlocks once the script exceeds the 64 KiB pipe buffer (bash must buffer the whole command line before executing), so it requires the thread.

Either way, mirror the substitution in `_run_cmd` (runner_spec.py:323). Keep `test_write_sub_loop_output_survives_oversized_stream` as the regression pin and reword its docstring: it currently claims the payload is "sized well under the real OS ARG_MAX", which is true for total ARG_MAX but false for Linux's per-argument `MAX_ARG_STRLEN` — the very limit this bug hits (A4 / BUG-3334 AC14).

## Program Design

### Types

- `_SHELL_SCRIPT_SUFFIX = ".sh"` (module constant, shared by both spawn sites if extracted; otherwise inline)

### Signatures

- `DefaultActionRunner.run(self, action: str, ...) -> ActionResult` — shell branch: `cmd = ["bash", str(script_path)]` where `script_path: Path` comes from `tempfile.mkstemp(suffix=".sh")`; write action, spawn with `stdin=subprocess.DEVNULL`, `os.unlink(script_path)` in the existing `finally`
- `_run_cmd(spec: ActionSpec, *, run_id: str | None = None) -> RunnerResult` (runner_spec.py) — same temp-file substitution for `spec.target`
- Optional direct pin: `test_shell_action_survives_oversized_rendered_script` in scripts/tests/ — drives `DefaultActionRunner.run` with a >131072 B rendered action, asserting `exit_code == 0` and written output equality (the loop-router test pins the end-to-end path; this pins the runner in isolation)

### Call Path

`FSMExecutor._run_action_or_route` → `DefaultActionRunner.run` (shell branch, fsm/runners.py:348) → `subprocess.Popen(["bash", script_path], ...)`; sibling: `runner_spec._run_cmd` → `subprocess.Popen(["bash", script_path], ...)`

## Impact

- **Priority**: P1 - Every FSM loop's shell states fail unconditionally on Linux once any interpolated capture exceeds 128 KiB; Linux is a primary deployment target for automation hosts.
- **Effort**: Small - Two spawn-site substitutions plus a docstring rewrite; no interpolation, routing, or selector-loop changes.
- **Risk**: Low - Spawn mechanics only; script text, env_allow, cwd, and process-group semantics are unchanged. `$0` inside the script changes from `bash` to the temp path — acceptable for loop scripts, which don't reference `$0`.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-10 | Priority: P1

## Session Log
- `/ll:format-issue` - 2026-09-10T22:00:28 - `bfcda7a0-6b47-49e9-8ffb-70e8847bdc09.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:17 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
