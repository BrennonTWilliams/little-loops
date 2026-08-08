---
id: BUG-3100
priority: P2
type: BUG
status: open
captured_at: '2026-08-08T04:44:28Z'
discovered_date: '2026-08-08'
discovered_by: capture-issue
discovered_commit: 2371728a
discovered_branch: main
labels:
- learning-tests
- skills
- automation
relates_to:
- BUG-3101
- BUG-3102
- ENH-3073
---

# BUG-3100: `/ll:explore-api` asks an interactive question instead of re-proving an existing record

## Summary

`/ll:explore-api <target>` only performs a real exploration when **no** learning-test record
exists for the target. When a record is already present — in either `proven` or `stale`
status — the skill stops and asks the user which of two paths to take, and returns without
touching the record.

Every automated re-prove path runs `/ll:explore-api` as its remedy step. In automation there
is nobody to answer the question, so **no path can refresh an existing record.**

## Current Behavior

Reproduced twice on `2026-08-08` at `2371728a` against `.ll/learning-tests/ruamelyaml.md`
(`target: ruamel.yaml`, `date: 2026-06-19`, 50 days old).

**Case 1 — record is `proven` and date-stale:**

```
$ ll-loop run ready-to-implement-gate --context "targets=ruamel.yaml"
[1/50] prove (0s) -> ✦ /ll:explore-api ruamel.yaml
       A prior record already exists for `ruamel.yaml` (slug `ruamelyaml`), dated 2026-06-19.
       **Status:** proven (7/7 assertions passed)
       Do you want to reuse this record and stop here, or should I proceed with a fresh
       exploration (which will overwrite the file with new claims)?
       -> done
Loop completed: done (1 iterations, 25.5s)
```

Record unchanged. Loop reported success (see [[BUG-3101]] for why the verdict was `done`).

**Case 2 — record explicitly marked `status: stale`:**

```
$ ll-learning-tests mark-stale "ruamel.yaml"
$ ll-loop run ready-to-implement-gate --context "targets=ruamel.yaml"
       ... it's currently marked **stale** ...
       Since it's stale, do you want me to:
       1. **Re-run** a fresh exploration ... or
       2. **Reuse** the existing claims as-is and just refresh the status back to `proven`?
       -> blocked
Loop completed: blocked (1 iterations, 51.8s)
```

Here the FSM retry path worked correctly (2 invocations, then `on_blocked`) — the skill was
asked twice and asked a question both times. Record still `date: 2026-06-19`.

**Consequence — every re-prove path is a dead end:**

| Path | Result |
|---|---|
| `ll-learning-tests prove "<target>"` | exit 0, record unchanged (silently — see [[ENH-3073]]'s `cmd_prove` hardening) |
| `ll-loop run ready-to-implement-gate` | explore-api asks → false `done` |
| `ll-loop run migrate-sdk-version` | queues 0 records — separate cause, see [[BUG-3102]] |
| `mark-stale` + either loop | explore-api asks → `blocked` |

## Expected Behavior

When invoked non-interactively, `/ll:explore-api <target>` performs a fresh exploration and
rewrites the record, without prompting. A record that already exists is the **normal** input
to a re-prove, not an ambiguity requiring escalation.

Interactive human use may still offer the reuse-vs-fresh choice; automation must get a
deterministic default.

## Motivation

The learning-test registry's entire value is that a `proven` record means "verified against
the installed API recently." That guarantee decays by design (`stale_after_days: 30`), and
the only mechanism for renewing it does not work. All 31 records in this repo are therefore
on a one-way trip to permanently stale — 7 are already past the threshold.

This is also the root blocker for [[ENH-3073]], whose selected fix is to print
`ll-learning-tests prove "<target>"` beside each stale row. That command cannot clear the row
it would be printed next to, so shipping ENH-3073 as specified would advertise a command that
silently does nothing — worse than the dead-end warning it replaces.

## Root Cause

`skills/explore-api/SKILL.md` — the ingest step checks the registry for an existing record and
branches to a user-facing question rather than proceeding. The skill has no notion of running
under automation, and no parameter by which a caller can demand a fresh run.

The FSM's remedy invocation is `f"/ll:explore-api {target}"`
(`scripts/little_loops/fsm/executor.py`, `_execute_learning_state`), which passes the bare
target and no freshness signal.

## Proposed Solution

Two candidate shapes:

**A — automation-aware default.** Have the skill detect automation context (`LL_AUTOMATION`
is already set for every descendant of a loop run — see the env-leak behavior) and default to
fresh exploration, keeping the interactive prompt for human invocations. No caller changes.

**B — explicit affordance.** Add a `--fresh` argument to `/ll:explore-api` and have
`_execute_learning_state` pass it: `f"/ll:explore-api {target} --fresh"`. More explicit, but
requires the FSM change and leaves the bare invocation still broken for anything else that
calls it.

**Recommended: A**, with B as a follow-on if an explicit override proves useful. A fixes every
existing caller at once; B fixes only the callers that are updated.

Either way the skill must never terminate a non-interactive run by asking a question — the
general failure mode is worth checking for elsewhere in `skills/`.

## Impact

- 7 of 31 learning-test records are past `stale_after_days` today and cannot be refreshed.
- `ready-to-implement-gate` — the gate `ll-auto` runs before implementing any issue with
  `learning_tests_required` — cannot do its job for any target that already has a record.
- [[ENH-3073]] is blocked: its selected option is unimplementable as specified.
- Hand-editing `date:` is the only remaining way to clear a row, and it is a false assertion
  in the registry — explicitly rejected in ENH-3073.

## Integration Map

- `skills/explore-api/SKILL.md` — the branch that asks instead of exploring
- `scripts/little_loops/fsm/executor.py` — `_execute_learning_state`, the remedy invocation
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — `type: learning` gate loop
- `scripts/little_loops/loops/migrate-sdk-version.yaml` — bulk re-prove loop, same remedy
- `scripts/little_loops/cli/learning_tests.py` — `cmd_prove`, shells to the gate loop

## Acceptance Criteria

- [ ] `/ll:explore-api <target>` invoked non-interactively against an existing `proven` record
      performs a fresh exploration and rewrites `date`/`assertions`/`status`.
- [ ] Same for an existing `status: stale` record.
- [ ] `ll-loop run ready-to-implement-gate --context "targets=<t>"` re-dates a date-stale
      record and terminates `done` — with the date actually advanced.
- [ ] No non-interactive invocation of the skill terminates by asking the user a question.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Issues

- BUG-3101 — the re-check bug that turns this no-op into a false `proven` verdict; found in
  the same session and must be fixed alongside, since it masks this one
- BUG-3102 — `migrate-sdk-version` queues only `status: stale` records
- ENH-3073 — blocked by this; its Option A advertises `ll-learning-tests prove`, which cannot
  clear a row until this is fixed

## Status

Open. Mechanism confirmed by direct reproduction on `2371728a`; both cases captured above
verbatim from loop output. Fix shape not yet decided (A vs B).


## Session Log
- `/ll:capture-issue` - 2026-08-08T04:47:03 - `0c442e3b-c3d8-4743-b597-7b3551a75ba6.jsonl`
