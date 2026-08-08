---
id: BUG-3102
priority: P3
type: BUG
status: open
captured_at: '2026-08-08T04:44:28Z'
discovered_date: '2026-08-08'
discovered_by: capture-issue
discovered_commit: 2371728a
discovered_branch: main
labels:
- learning-tests
- loops
relates_to:
- BUG-3100
- BUG-3101
- ENH-3073
- FEAT-1813
---

# BUG-3102: `migrate-sdk-version` queues only `status: stale` records, never age-stale ones

## Summary

`migrate-sdk-version` is the bulk re-prove loop (FEAT-1813): it iterates the stale set,
re-proves each target, and classifies the result. Its `list_stale` state selects records with

```python
stale = [r for r in records if r.get("status") == "stale"]
```

But staleness has two independent forms in this system, and that filter sees only one:

| Form | Where it lives | Set by | Seen by `list_stale`? |
|---|---|---|---|
| status staleness | the record's `status:` field | `ll-learning-tests mark-stale` | yes |
| **age staleness** | **computed, never stored** | `is_record_stale(record, days)` vs `date:` | **no** |

The release gate, the `type: learning` FSM state, and `cmd_check` all use age staleness. The
bulk loop built to remediate staleness is the one consumer that ignores it.

## Current Behavior

All 31 records in this repo are `status: proven`; none carries `status: stale`. Verified on
`2371728a`:

```
$ ll-learning-tests list | python3 -c "import json,sys; from collections import Counter; \
    print(Counter(r.get('status') for r in json.load(sys.stdin)))"
Counter({'proven': 31})
```

Seven of those are age-stale and are flagged by the release gate today (`anthropic`, `fcntl`,
`hypothesis`, `phoenix`, `pytest`, `questionary`, `ruamel.yaml` — 31 to 50 days old against
`stale_after_days: 30`).

`ll-loop run migrate-sdk-version` queues **zero** of them, prints `No stale records found.`,
exits 1, and routes `done_empty`.

The workaround — `mark-stale` each target first, converting age staleness into status
staleness — does queue them, but is unsafe in its own right: it flips records to a status that
makes `cmd_check` return 1, blocking `ll-auto`'s learning gate on those targets, and if the
re-prove pass fails partway they stay that way. Reversible only by the re-prove that just
failed. (It also does not currently help, because of [[BUG-3100]].)

## Expected Behavior

`list_stale` selects every record that any other consumer would consider stale — status-stale
**or** age-stale — so the loop's queue matches the set the release gate reports.

Running the bulk loop on a repo with age-stale records queues and processes them, without any
`mark-stale` pre-step and without transiting records through a status that blocks other gates.

## Motivation

This is the gap between what the loop is documented to do and what it does. FEAT-1813 describes
it as the counterpart to `learning-tests-audit`: "After audit marks records stale on dependency
bumps, this loop iterates the stale set." That framing assumes `mark-stale` always runs first —
true for the registry-version-bump path FEAT-1739 automates, false for calendar-driven staleness,
which is the form the release gate actually reports and the form 7 records are in right now.

The practical cost: there is no bulk remediation path for the staleness users are actually shown.
The alternative is N sequential single-target `ll-learning-tests prove` runs — one LLM session
each, seven today.

This surfaced while trying to clear [[ENH-3073]]'s seven flagged records, where the bulk loop was
the recommended path and turned out to queue nothing.

## Root Cause

`scripts/little_loops/loops/migrate-sdk-version.yaml`, `list_stale` state — the record filter
tests the `status` field only. Age staleness is a computed predicate
(`little_loops.learning_tests.gate.is_record_stale`) that is never written back to the record, so
a field-equality filter cannot observe it. The loop's inline `python3` heredoc does not import
the predicate.

## Proposed Solution

Have `list_stale` apply both forms, reusing the canonical predicate rather than re-deriving the
date arithmetic:

```python
from little_loops.config.core import BRConfig
from little_loops.learning_tests import list_records
from little_loops.learning_tests.gate import is_record_stale

lt = BRConfig(Path.cwd()).learning_tests
days = lt.stale_after_days

def _is_stale(r):
    return r.status == "stale" or (
        lt.enabled and r.status == "proven" and is_record_stale(r, days)
    )
```

Reusing `is_record_stale` keeps the loop's definition of stale identical to the release gate's,
which is the property that failed here. Re-implementing the comparison inside the heredoc would
reintroduce the same class of divergence.

Consider also emitting the two forms distinctly in the queue file or the triage report, since
`needs-upgrade` vs `still-valid` classification is more meaningful for a version bump than for a
calendar expiry.

## Impact

- No bulk remediation path exists for age-stale records; N single-target sessions is the only
  option.
- The loop silently reports `No stale records found.` on a repo with 7 stale records — the
  message is accurate to its filter and misleading about the registry.
- Blocks the practical clearing of [[ENH-3073]]'s seven records, though [[BUG-3100]] blocks it
  more fundamentally: fixing this bug alone makes the loop queue seven targets that it then
  cannot re-prove.

## Integration Map

- `scripts/little_loops/loops/migrate-sdk-version.yaml` — `list_stale` state, the filter
- `scripts/little_loops/learning_tests/gate.py` — `is_record_stale`, the predicate to reuse
- `scripts/little_loops/learning_tests/release_gate.py` — the consumer whose definition should match
- `scripts/little_loops/config/features.py` — `stale_after_days`, `enabled`
- `scripts/tests/test_builtin_loops.py` — existing built-in loop coverage

## Acceptance Criteria

- [ ] `list_stale` queues records that are `status: stale` **or** age-stale per
      `is_record_stale`, using the imported predicate rather than inline date arithmetic.
- [ ] A test with a fixture registry containing one age-stale `proven` record and no
      `status: stale` record asserts the queue file is non-empty and the state exits 0.
- [ ] A test asserts an empty registry, and a registry of only fresh `proven` records, still
      route `done_empty`.
- [ ] The `targets` context filter continues to narrow the queue as before.
- [ ] Running the loop in this repo queues the 7 currently age-stale targets.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Issues

- BUG-3100 — `/ll:explore-api` refuses to re-prove existing records; this loop's remedy step
  hits it, so fixing BUG-3102 alone yields a loop that queues work it cannot complete
- BUG-3101 — the learning-state re-check bug; the same remedy path
- FEAT-1813 — introduced this loop with the `status == "stale"` filter
- FEAT-1739 — `learning-tests-audit`, the `mark-stale` producer this filter assumes always ran
- ENH-3073 — the seven age-stale records this loop was expected to clear

## Status

Open. Mechanism confirmed by reading `list_stale` and by observing `Counter({'proven': 31})`
against a release gate reporting 7 stale rows on `2371728a`. Lower priority than BUG-3100 and
BUG-3101: this bug limits the *scale* of remediation, those two prevent remediation entirely.


## Session Log
- `/ll:capture-issue` - 2026-08-08T04:47:04 - `0c442e3b-c3d8-4743-b597-7b3551a75ba6.jsonl`
