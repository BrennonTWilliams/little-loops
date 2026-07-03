---
id: ENH-2454
title: Extend --delay help text to mention host-pressure use case
type: ENH
parent: EPIC-2455
priority: P5
status: open
labels: [docs, cli, captured]
captured_at: "2026-07-03T02:05:57Z"
discovered_date: "2026-07-02"
discovered_by: capture-issue
---

# ENH-2454: Extend --delay help text to mention host-pressure use case

## Summary

Update the `ll-loop run --delay` flag's help text (and the matching per-state `backoff:` field doc) from "useful for recording" to also mention the host-pressure-relief use case. The flag already serves both purposes; the help text undersells it.

## Current Behavior

In `scripts/little_loops/cli/loop/__init__.py:140-146`:

```python
run_parser.add_argument(
    "--delay",
    type=float,
    default=None,
    metavar="SECONDS",
    help="Sleep N seconds between iterations (useful for recording)",
)
```

The flag sets `fsm.backoff`, which the executor honors as an interruptible sleep between iterations (`executor.py:583-589`). The help text mentions only the original use case (demo recording visibility) and not the secondary use case that emerged in practice: as a host-pressure relief valve between subprocess spawns.

## Expected Behavior

Help text reads: `"Sleep N seconds between iterations (useful for recording and to relieve host memory pressure between subprocess spawns)"`. The per-state `backoff:` field doc in `docs/guides/LOOPS_GUIDE.md:439` gets a parallel one-line update.

## Motivation

On 2026-07-02 an interactive Claude session was jetsam-killed during a 12-minute `ll-loop run brainstorm` (13 sequential ~500 MB claude subprocesses). The fix is the broader `fsm.host_guard` design (ENH-2452 + ENH-2453), but in the meantime users can mitigate by running heavy loops with `--delay 1` to space out the spawns. The current help text doesn't tell them that — they'd have to read the executor source. A one-line help text fix surfaces the mitigation.

## Proposed Solution

1. Change `cli/loop/__init__.py:145` help text to `"Sleep N seconds between iterations (useful for recording and to relieve host memory pressure between subprocess spawns)"`.
2. Add a one-line note to `docs/guides/LOOPS_GUIDE.md` `backoff:` field description: `"… Overridden at runtime by --delay. Also useful to space out subprocess spawns in long-running loops."`
3. No code change beyond the help text. No schema change. No new flag.

## Success Metrics

- Users running `ll-loop run --help` see the host-pressure use case in the `--delay` description.
- `docs/guides/LOOPS_GUIDE.md` search for "pressure" or "spawn" surfaces the `backoff:` field as a relevant mitigation.

## Scope Boundaries

- Help text only. The full `fsm.host_guard` (ENH-2452 + ENH-2453) is the structural fix; this issue is the one-line interim mitigation surfacing.
- No new flag. No schema change.

## API/Interface

- One string change in `cli/loop/__init__.py:145`.
- One string change in `docs/guides/LOOPS_GUIDE.md`.
- Public API unchanged.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — change `help=` for `--delay`.
- `docs/guides/LOOPS_GUIDE.md` — extend the `backoff:` field description.

### Dependent Files
- None. The `--delay` flag is also referenced in `cli/loop/next_loop.py:310`, `cli/loop/lifecycle.py:500`, `cli/loop/_helpers.py:1356` — none of these carry user-facing help text.

### Similar Patterns
- N/A — this is a doc fix.

### Tests
- `scripts/tests/test_cli_loop.py` — extend the `--help` output snapshot test to assert the new help string.

### Documentation
- `docs/reference/CLI.md` lines 521, 707 — auto-regenerated from the argparse `help=` if `ll-verify-docs` runs the regen; if not, update manually.
- `docs/guides/LOOPS_GUIDE.md:439` — manual edit.

### Configuration
- N/A

## Implementation Steps

1. Edit the help text in `cli/loop/__init__.py`.
2. Edit the `backoff:` field description in `docs/guides/LOOPS_GUIDE.md`.
3. Update the `--help` snapshot test.
4. Run `ll-verify-docs` to check if `docs/reference/CLI.md` needs manual sync.

## Impact

- **Priority**: P5 — doc-only; zero functional impact. Useful as a stopgap until ENH-2452 lands.
- **Effort**: Small — 2 string changes + 1 test update.
- **Risk**: Low — help text only.
- **Breaking Change**: No.

## Related Key Documentation

- `docs/reference/CLI.md` (`--delay` rows at lines 521, 707)
- `docs/guides/LOOPS_GUIDE.md` (`backoff:` field)

## Related Issues

- **ENH-2452** — the structural fix (adaptive pressure gate). This issue is the interim mitigation surfacing.

## Status

**Open** | Created: 2026-07-02 | Priority: P5

## Session Log

- `/ll:capture-issue` - 2026-07-03T02:05:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ff12421-1849-4d8d-abe4-d955b4becd84.jsonl`
