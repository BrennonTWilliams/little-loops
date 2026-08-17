---
id: ENH-3240
type: ENH
title: action_complete events omit state and iteration alongside session_jsonl so
  transcripts are unlabeled
priority: P4
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T18:23:48Z'
---

# ENH-3240: action_complete events omit state and iteration alongside session_jsonl so transcripts are unlabeled

## Summary

`action_complete` events in a run's `events.jsonl` record `session_jsonl` — the host session
transcript for that action — but omit the `state` and `iteration` fields the same run's
`usage.jsonl` records at identical timestamps. The pointers are therefore present but unlabeled:
recovering "which transcript was `verify_issue`" requires a timestamp join against a second file,
or opening each transcript to identify it.

## Current Behavior

For run `.loops/.history/2026-08-17T170259-refine-to-ready-issue`, every event carrying a
`session_jsonl` looks like this — four fields, none of which name the state:

```
{'event': 'action_complete', 'ts': '2026-08-17T17:09:30.536676+00:00'}
{'event': 'action_complete', 'ts': '2026-08-17T17:15:53.232580+00:00'}
{'event': 'action_complete', 'ts': '2026-08-17T17:17:54.464016+00:00'}
{'event': 'action_complete', 'ts': '2026-08-17T17:19:27.383191+00:00'}
```

(printed filtering to `event`/`type`/`state`/`iteration`/`action`/`ts`; `state`, `iteration` and
`action` are absent, not null-valued)

The pointers themselves are correct — they resolve to the four prompt-state transcripts:

```
0d1d5748-…  (refine_issue)
874f81b5-…  (wire_issue)
038b6ab4-…  (verify_issue)
83adf706-…  (confidence_check)
```

The run's `usage.jsonl` records `state` and `iteration` for those same four moments, at
byte-identical timestamps:

```json
{"iteration": 10, "state": "verify_issue", "action_type": "prompt", ...,
 "timestamp": "2026-08-17T17:17:54.464016+00:00"}
```

So the attribution is fully recoverable — by joining two files on `ts` — but is not directly
readable from the event that names the transcript.

The `events.jsonl` schema does carry `state` on other event types; the observed key set across
the file includes `state`, `iteration`, `from`, `to`, `verdict`, `session_jsonl`, and others. It
is specifically the `session_jsonl`-bearing `action_complete` event that lacks it.

## Expected Behavior

An `action_complete` event that records `session_jsonl` also records the `state` and
`iteration` that produced it, so a run's per-state transcripts can be attributed to their
states by reading `events.jsonl` alone — no timestamp join against `usage.jsonl`, and no
opening each transcript to identify it.

## Motivation

Reconstructing why a loop reached a given verdict is the core diagnostic task behind
`/ll:debug-loop-run` and `/ll:audit-loop-run`, and it starts with reading the right transcript.
The run already records exactly the pointer needed; withholding the state name turns a direct
lookup into a two-file join that a reader has to know about. The fix is additive and touches one
event payload.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

Low severity, purely diagnostic friction. It surfaces when reconstructing why a loop reached a
particular verdict — the exact task ENH-3238's investigation required. Without knowing the
`ts`-join trick, the fallback is grepping every session JSONL in
`~/.claude/projects/<project>/` for the state's slash-command text (~25 files for a single day's
runs) to identify four transcripts the run had already recorded.

No data is lost and no behavior is wrong; the information is one join away.

## Proposed Solution

Add `state` (and `iteration`, for consistency with `usage.jsonl`) to the `action_complete` event
payload at the site where `session_jsonl` is written. Both values are in scope at emission time —
`usage.jsonl` is written from the same point with the same timestamp.

## Scope Boundaries

**In scope**: adding `state` and `iteration` to the `action_complete` event payload that already
carries `session_jsonl`.

**Out of scope**: the split whereby `.loops/runs/<run>/` holds marker files and `usage.jsonl`
while `.loops/.history/<run>/` holds `events.jsonl` and `state.json`. That is existing design;
consolidating the two locations is a separate question and should not be folded in here.

**Out of scope**: any change to what is written to the host session transcripts themselves, or
to their retention.

## Acceptance Criteria

- [ ] `action_complete` events carrying `session_jsonl` also carry `state` and `iteration`.
- [ ] The values match the corresponding `usage.jsonl` record for the same timestamp.
- [ ] Existing `events.jsonl` readers tolerate the added fields (additive change only; no
      existing field renamed or removed).
- [ ] A test asserts that a prompt-state action's `action_complete` event names its state.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Found while investigating ENH-3238; the initial assumption that run artifacts carried *no*
transcript pointer was wrong — `session_jsonl` is recorded, and correctly. This issue is only
about labeling it.

Note that the per-run directory under `.loops/runs/<run>/` holds only marker files and
`usage.jsonl`; the `session_jsonl` pointers live in `.loops/.history/<run>/events.jsonl`. That
split is existing design and not in scope here.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-17 | Priority: P4


## Session Log
- `/ll:capture-issue` - 2026-08-17T18:23:57 - `66dab8b6-e923-43d4-9f0e-eccb97176e0f.jsonl`
