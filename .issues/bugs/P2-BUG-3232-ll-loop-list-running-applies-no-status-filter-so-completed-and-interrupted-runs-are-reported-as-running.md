---
id: BUG-3232
type: BUG
title: 'll-loop list --running: no status filter is applied, so completed, interrupted
  and user_stopped runs are reported as running'
priority: P2
status: open
discovered_by: little-loops-hermes-audit
discovered_date: '2026-08-17'
labels:
- loops
- cli-json
testable: true
confidence_score: 100
outcome_confidence: 88
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 25
---

# BUG-3232: ll-loop list --running applies no status filter

## Summary

`--running` does not filter by status. It returns every `*.state.json` in
`.loops/.running/`, whatever state those runs ended in.

`list_running_loops` (`scripts/little_loops/fsm/persistence.py:1109`) is
documented on its own next line as *"List all loops with saved state"* — which
is exactly what it does, and is not what `--running` advertises.
`cmd_list` (`scripts/little_loops/cli/loop/info.py:113`) calls it for
`--running` and applies a status filter **only** when the separate `--status`
flag is present (`info.py:114-115`). Meanwhile the flag's own help text
(`scripts/little_loops/cli/loop/__init__.py:365`) reads `Only show running
loops`.

This is not a stale-directory problem that cleanup would fix. Those files are
*meant* to persist: `_reconcile_stale_runs` (`persistence.py:605`) archives
only `{completed, failed, timed_out}` (`persistence.py:622`), deliberately
spares `interrupted` so runs stay resumable, does not list `user_stopped` at
all, and is called at **loop startup** — never from `list`. So on any project
that has ever run a loop, `--running` reports that project's history.

Related to BUG-3231, which concerns what this same command *destroys* on the
empty path. This one concerns what it *returns* on the success path. They are
independent and either can be fixed without the other.

## Current Behavior

Probed live against `little-loops-hermes`, same directory, same process,
seconds apart:

```console
$ ll-loop list --running --json | python -c "import json,sys; [print(s['loop_name'], s['status']) for s in json.load(sys.stdin)]"
general-task user_stopped
general-task interrupted
general-task interrupted
general-task completed

$ ll-loop list --status running
No loops with status: running
```

Four "running" loops, zero running loops. The most recent of the four last
updated 2026-07-26; the oldest, 2026-06-18.

The human-readable path is aware of this and accommodates it rather than
preventing it — `_STATUS_COLORS` in `info.py` assigns colors to `interrupted`,
`user_stopped` and `stopped`, printed under a header that reads
`Running loops:`. So in a terminal the output is merely misleading, and colour
is the only thing distinguishing a live run from a month-old one.

`--json` has no colour. The machine-readable consumer gets four entries and
nothing in the payload marks them as finished unless it inspects `status`
itself — which is the field the flag was supposed to have filtered on.

## Expected Behavior

`ll-loop list --running` returns only dispatches that are actually executing.

## Impact

Any programmatic consumer of `--running --json` that trusts the flag name
over-reports. Found by `little-loops-hermes`, whose portfolio sync fed the
result into a field named `in_flight` and from there into a morning briefing
for the user: the briefing announced four loops in flight for a project with
none. Hermes now filters on `status` itself
(`db/sync.py:_parse_in_flight`) and does not depend on this being fixed.

The narrower consequence is that `--running` is currently unusable as a
liveness check — "is anything running right now" cannot be answered by the
flag named for it, only by `--status running`.

## Proposed Fix

Two directions; the choice is a compatibility call, not a technical one.

1. **Filter in `cmd_list`.** Restrict the `--running` branch to genuinely
   running dispatches. Prefer an allowlist (`running`, `starting`) over a
   denylist of terminal statuses, so a status added later defaults to
   *excluded* rather than silently reappearing as running.

2. **Rename the flag to match the behavior** (`--all`, `--saved`, or fold it
   into `--status`), and correct both the help text and the
   `Running loops:` header.

Whichever is chosen, `list_running_loops`'s name and its docstring should stop
contradicting each other — the function is the source of the confusion and
reads correctly only if you already know the answer.

If (1): `--status` filtering already exists two lines below and can be reused;
`starting` entries are synthesized further down in `list_running_loops` for
loops with a live PID and no state file yet, and must survive the filter.

## Acceptance Criteria

- [ ] `ll-loop list --running --json` on a project whose `.loops/.running/`
      holds only `completed` / `interrupted` / `user_stopped` state files
      returns `[]` (or the flag is renamed and its help corrected).
- [ ] `--running` and `--status running` agree on the same directory.
- [ ] A loop with a live PID and no state file yet (`status="starting"`) is
      still reported.
- [ ] State files are not deleted or archived as a side effect of `list` —
      `interrupted` runs remain resumable.
- [ ] `list_running_loops`'s docstring and the `--running` help text describe
      the same behavior as the code.
