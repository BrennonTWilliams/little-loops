---
id: ENH-2982
title: autodev finalize_done prints "re-queue to retry" for deterministic NOT_READY
  failures that retrying cannot fix
type: ENH
priority: P3
status: done
discovered_date: '2026-08-01'
discovered_by: audit-loop-run
relates_to:
- BUG-2981
- BUG-2594
labels:
- autodev
- loops
- fsm
decision_needed: false
testable: true
depends_on:
- BUG-2981
---

# ENH-2982: `autodev` `finalize_done` prints "re-queue to retry" for deterministic `NOT_READY` failures that retrying cannot fix

## Summary

`finalize_done`'s Unverified summary line hardcodes one remedy for every
unverified issue:

```
Unverified (N): FEAT-108  (threshold passed; implementation did not close — re-queue to retry)
```

For an issue whose `ll-auto` run failed at Phase 1 with a `ready-issue`
`NOT_READY` verdict, re-queueing is the one thing that will not help — the
verdict is deterministic against the issue's current content, so a rerun
reproduces it. The advice sends the operator into a retry loop instead of at
the issue.

Every other bucket in the same summary block already carries a remedy matched
to its cause (`resolve them, then re-run`, `prove deps with /ll:explore-api`,
`resolve with /ll:decide-issue`). The unverified bucket is the only one that
guesses.

## Current Behavior

`autodev.yaml:2066-2068`:

```bash
if [ "$UNVERIFIED_COUNT" -gt 0 ]; then
  printf 'Unverified   (%d): %s  (threshold passed; implementation did not close — re-queue to retry)\n' "$UNVERIFIED_COUNT" "$UNVERIFIED_LIST"
fi
```

The parenthetical is a constant. It is emitted identically whether the
implementation failed transiently (rate limit, flaky test, interrupted run —
where retry is right) or deterministically (`ready-issue` returned `NOT_READY`,
`CLOSE` without a validated path, a persisted path mismatch — where retry is
wrong).

## Expected Behavior

An issue whose `ll-auto` run ended in a deterministic Phase-1 not-ready verdict
is reported under its own reason stem with a remedy that names the actual next
action — refine or re-ready the issue, not re-queue it. Issues with no such
signal keep the current retry wording.

## Root Cause

The distinction is already on disk and already read by a sibling state, but
`finalize_done` never consults it.

`implement_current` (`autodev.yaml:833`) tees `ll-auto --only` output to
`${context.run_dir}/ll_auto_last.txt` — BUG-2594 introduced this precisely so
downstream states could grep a *file* rather than interpolate captured output
into a shell string. `check_learning_gate` already uses it, via the
`ll_auto_learning_gate_check` fragment (`loops/lib/common.yaml:342-350`):

```bash
if grep -qF 'LEARNING_GATE_BLOCKED' "${context.run_dir}/ll_auto_last.txt" 2>/dev/null; then
```

The not-ready signal is in the same stream. `issue_manager.py:842-854`:

```python
if not parsed["is_ready"]:
    logger.error(
        f"Issue {info.issue_id} is NOT READY for implementation "
        f"(verdict: {parsed['verdict']})"
    )
    return IssueProcessingResult(success=False, ..., failure_reason=f"NOT READY: {parsed['verdict']} - ...")
```

So `ll_auto_last.txt` contains `is NOT READY for implementation (verdict: ...)`
on exactly this path. Nothing reads it.

The structural reason is that `ll_auto_last.txt` is per-issue and overwritten by
the next `implement_current` (`:833` truncates via `tee`), whereas
`finalize_done` runs once at the end over an accumulated list. The reason must
therefore be recorded **when the failure happens**, not reconstructed at
finalize.

## Program Design

Follow the pattern the other buckets already use: record a reason token next to
the ID at failure time, and give `finalize_done` a bucket keyed on it.

**1. Classify at failure time.** The natural site is the state added by
BUG-2981 to clear `autodev-inflight` on `check_impl_auth`'s non-auth legs —
that state already sits exactly where a non-auth, non-gate implementation
failure is known, and it runs per-issue while `ll_auto_last.txt` still holds
that issue's output. It greps for the not-ready signature and, on a hit, writes
`$ID  not_ready` to a new `autodev-not-ready.txt`.

BUG-2981 should land first; this issue's change is additive to the state it
introduces. If they are implemented together, the grep and the `rm -f` belong
in the same action body.

**2. Bucket at finalize.** `finalize_done` reads `autodev-not-ready.txt`,
excludes those IDs from `UNVERIFIED_IDS` (mirroring how ENH-2727/ENH-2868/
ENH-2909 exclude infra-class and pre-flight skips from the generic Skipped
bucket at `:1986-2000`), and emits its own line:

```
Not-ready    (N): FEAT-108  (ready-issue verdict NOT_READY — refine the issue, then re-run; re-queueing reproduces it)
```

**3. Summary JSON.** Add a `not_ready` key alongside the existing bucket keys.
This is the part that makes it an ENH rather than a BUG: the summary JSON is
read by other tooling (`/ll:audit-loop-run`, `ll-loop audit`), so adding a key
and moving IDs out of `unverified` into it is an output-contract change, not a
wording fix.

**Verdict semantics — unchanged.** A not-ready issue must still count against
success the way it does today. It is a real failure to close, not a legitimate
skip like `decomposed` or `gate_blocked`. The verdict predicate at
`autodev.yaml:2076-2082` must treat `NOT_READY_COUNT` exactly as it treats
`UNVERIFIED_COUNT`; only the *reporting* splits. Getting this backwards would
launder a failure into a pass — the failure mode BUG-2908 exists to prevent.

### Grep signature

Match on the `issue_manager.py:843-845` log line, which is stable and
issue-scoped:

```bash
grep -qE 'is NOT READY for implementation' "${context.run_dir}/ll_auto_last.txt"
```

Prefer this over the `failure_reason` string (`NOT READY: ...`), which is a
return value and only reaches stdout indirectly. The pattern is a `logger.error`
format string, so it is coupled to source text — the test below pins it.

### Call Path

- `scripts/little_loops/issue_manager.py:842-854` — emits the signal (read-only
  here; the pattern's source of truth)
- `scripts/little_loops/loops/autodev.yaml:833` — `implement_current`'s tee to
  `ll_auto_last.txt` (unchanged)
- `scripts/little_loops/loops/autodev.yaml` — BUG-2981's new
  `clear_inflight_after_impl_failure` state: add the classify-and-record grep
- `scripts/little_loops/loops/autodev.yaml:1986-2000` — bucket-exclusion
  pattern to mirror
- `scripts/little_loops/loops/autodev.yaml:2066-2068` — the Unverified printf;
  add the Not-ready printf beside it
- `scripts/little_loops/loops/autodev.yaml:2076-2082` — verdict predicate; fold
  `NOT_READY_COUNT` in with `UNVERIFIED_COUNT`

## Implementation Steps

1. Land BUG-2981 (this builds on the state it adds).
2. Add the not-ready grep + `autodev-not-ready.txt` write to that state.
3. Read the file in `finalize_done`; exclude those IDs from `UNVERIFIED_IDS`;
   add `NOT_READY_COUNT` / `NOT_READY_LIST` and the printf.
4. Add `not_ready` to the summary JSON.
5. Fold `NOT_READY_COUNT` into the verdict predicate on the same footing as
   `UNVERIFIED_COUNT`.
6. `ll-loop validate autodev`; `python -m pytest scripts/tests/test_builtin_loops.py`.

## Test Plan

Same shell-execute-a-state's-action pattern as
`test_builtin_loops.py:4452-4472`:

- **Classification** — write an `ll_auto_last.txt` containing the real
  `issue_manager.py` log line, execute the classifier state's action, assert
  `autodev-not-ready.txt` contains `<ID>  not_ready`.
- **Negative** — an `ll_auto_last.txt` with a generic failure produces no
  not-ready entry, and the issue still lands in the unverified bucket.
- **Summary** — seed `autodev-not-ready.txt`, execute `finalize_done`, assert
  the ID appears in the Not-ready line and **not** in the Unverified line, and
  that the summary JSON carries `not_ready`.
- **Verdict** — a run with only a not-ready issue does not report `success`.
- **Pattern pinning** — assert the grep pattern in the YAML matches the string
  `issue_manager.py` actually logs, so a reword of that `logger.error` fails
  loudly here instead of silently disabling the classification.

## Acceptance Criteria

- [ ] A deterministic `ready-issue` `NOT_READY` failure is reported under its
      own reason stem with a remedy that does not say "re-queue to retry"
- [ ] Issues with no not-ready signal keep the current Unverified wording
- [ ] The summary JSON exposes `not_ready` as its own key
- [ ] A not-ready issue still prevents a `success` verdict
- [ ] The grep pattern is pinned against `issue_manager.py`'s log string by a test
- [ ] `ll-loop validate autodev` passes; `python -m pytest scripts/tests/test_builtin_loops.py` passes

## Impact

**Who is affected:** operators reading an `autodev` run summary after an issue
failed at Phase 1. In a `low_readiness`-prone backlog this is the common
unverified cause, not the rare one.

**What it costs today:** the summary's only actionable sentence points at the
wrong action. Re-queueing a deterministically not-ready issue burns a full
`ll-auto` cycle to reproduce the same verdict. The operator learns nothing from
the second run that the first did not already record in `ll_auto_last.txt` —
which is overwritten by then.

**Why the split earns its keep:** every other bucket in the block already pairs
a cause with its remedy, and those lines are what make the summary usable
without opening the run dir. The unverified bucket is the last one still
guessing, and it guesses on the path where being wrong is most expensive.

**Downstream:** `/ll:audit-loop-run` and `ll-loop audit` read the summary JSON.
Adding a `not_ready` key is additive, but IDs move out of `unverified` into it,
so any consumer counting `unverified` sees a behavior change. That is the reason
this is an ENH and is called out in the AC.

## Scope Boundaries

**In scope:** classifying the not-ready failure at the point it happens;
one new bucket, printf line, and summary-JSON key; folding the new count into
the existing verdict predicate unchanged in meaning.

**Out of scope:**

- Changing what makes an issue not-ready, or acting on it automatically
  (auto-refining, auto-deferring). This issue only reports accurately;
  `low_readiness` / `readiness_stagnated` deferral already owns the acting.
- The other deterministic Phase-1 exits (`CLOSE` without a validated path,
  persisted path mismatch). They share the retry-is-wrong property and would
  fit the same mechanism, but each needs its own verified signature; only
  `NOT_READY` is claimed here.
- The verdict predicate's semantics. `NOT_READY_COUNT` is folded in on exactly
  the same footing as `UNVERIFIED_COUNT` — deliberately not a behavior change.
- BUG-2981's sentinel leak and double-count, which this depends on but does not
  fix.

## Notes

Found by `/ll:audit-loop-run` on an `autodev` run alongside BUG-2981 (inflight
sentinel leak + unverified double-count). Split from it because this one changes
summary output that other tooling reads, while BUG-2981 is a mechanical YAML fix.

## Resolution

_Added by `/ll:verify-issues`:_ Superseded by ENH-2989 (done,
completed_at 2026-08-03), which solved the underlying problem via a
different route than this issue proposed. `check_impl_reached`
(`autodev.yaml:850-861`) now intercepts every Phase-1 rejection —
including `NOT_READY` — via a `PHASE1_NOT_STARTED` marker *before*
`check_learning_gate`/`check_impl_auth` run, diverting it into a new
"Not-started" bucket (`autodev.yaml:2355-2356`, `mark_not_started` at
`:863-925`) with its own reason-scoped ledger (`autodev-not-started.txt`,
including a `not_ready` reason). A deterministic `NOT_READY` issue can no
longer reach the "Unverified" bucket/printf this issue targeted at all —
the scenario described here is now structurally impossible. BUG-2981,
which this issue said should land first, is also already `done`.

## Session Log
- `/ll:verify-issues` - 2026-08-03T04:54:48 - `d03f8e53-9873-4f8d-8cfd-bbc50704a66b.jsonl`

---

## Status

**Done** | Created: 2026-08-01 | Priority: P3
