---
id: BUG-2377
type: BUG
title: '`ll-logs` diagnostic logs pollute stdout, corrupting `discover`/`-j` output'
priority: P2
status: open
captured_at: '2026-06-28T20:50:00Z'
discovered_date: 2026-06-28
discovered_by: user-report
labels:
- cli
- ll-logs
- logging
- automation-blocker
relates_to:
- ENH-2378
- FEAT-2379
decision_needed: false
confidence_score: 95
---

# BUG-2377: `ll-logs` diagnostic logs pollute stdout, corrupting `discover`/`-j` output

## Summary

`ll-logs discover` and `ll-logs scan-failures` emit diagnostic log lines such as

```
[13:43:47] Decoded path does not exist: /Users/.../worktrees/worker/enh/1002/...
```

to **stdout**, intermixed with the command's real output. This:

- Breaks `discover`'s documented contract ("List all Claude projects with ll activity,
  **one path per line, sorted**") — 143 of 162 stdout lines from a real run were noise.
- Corrupts `scan-failures -j` / `discover -j`: the JSON document is preceded by dozens of
  non-JSON log lines, so `json.load(stdin)` fails (`PARSE_FAILED` reproduced this session).
- Survives `2>/dev/null`, because the noise is on stdout, not stderr — so the standard
  "silence diagnostics" idiom does not work, and any scheduled/scripted consumer chokes.

This is the prerequisite blocker for automating cross-project loop review (FEAT-2379):
a harvester cannot reliably parse `ll-logs` output while diagnostics share the data channel.

## Root cause

`little_loops.logger.Logger` routes almost every level to stdout. Only `error` goes to
stderr:

- `scripts/little_loops/logger.py:79` — `info()` → `print(...)` (stdout)
- `scripts/little_loops/logger.py:84` — `debug()` → `print(...)` (stdout)
- `scripts/little_loops/logger.py:89` — `success()` → `print(...)` (stdout)
- `scripts/little_loops/logger.py:94` — `warning()` → `print(...)` (stdout)
- `scripts/little_loops/logger.py:104` — `timing()` → `print(...)` (stdout)
- `scripts/little_loops/logger.py:99` — `error()` → `print(..., file=sys.stderr)` (stderr) ✓

The specific offending call is `scripts/little_loops/cli/logs.py:182`:

```python
logger.debug(f"Decoded path does not exist: {decoded_path}")
```

Because `debug()` prints to stdout, every stale/deleted worktree path the decoder walks past
is dumped into the data stream. The discover corpus on this machine contains dozens of stale
worktree paths, so the noise dominates.

## Reproduction

```bash
ll-logs discover >/tmp/out.txt 2>/tmp/err.txt
wc -l /tmp/out.txt /tmp/err.txt          # 162 stdout, 0 stderr
grep -c "Decoded path" /tmp/out.txt      # 143
ll-logs scan-failures --all -j | python3 -c "import sys,json; json.load(sys.stdin)"  # raises
```

## Proposed fix

Two layers, smallest-blast-radius first:

1. **Route diagnostics off the data channel.** Diagnostic levels (`debug`, `warning`, and
   arguably `info`/`timing`) should write to `sys.stderr`, leaving stdout for command data.
   The cleanest fix is in `logger.py` so the separation holds for every CLI, but the blast
   radius is wide (all `ll-*` tools share `Logger`); gate behind a review of which consumers
   depend on info-on-stdout (e.g. `header()` banners). A conservative first cut: move
   `debug()` and `warning()` to stderr; leave `info()`/`success()` as-is.

2. **Stop walking dead paths so loudly.** In `logs.py`, demote the per-path
   "Decoded path does not exist" message so it only appears under an explicit verbose/debug
   flag, and add `discover --existing-only` to filter the output to live project roots
   (the common case for any downstream harvester).

## Acceptance criteria

- `ll-logs discover` prints only project paths to stdout; diagnostics (if any) go to stderr.
- `ll-logs scan-failures --all -j` produces a stdout stream that `json.load` parses with no
  preprocessing.
- `ll-logs discover --existing-only` exists and emits only paths that currently exist on disk.
- A regression test asserts stdout from `discover` contains no `[HH:MM:SS]`-prefixed lines.

## Notes

The `[HH:MM:SS]` prefix comes from `Logger._format` (`logger.py:65-74`); it is a strong
fingerprint for "a diagnostic leaked onto stdout" and can anchor the regression assertion.
