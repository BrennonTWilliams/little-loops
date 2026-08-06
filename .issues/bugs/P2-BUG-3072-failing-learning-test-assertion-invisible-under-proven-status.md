---
id: BUG-3072
priority: P2
type: BUG
status: open
discovered_commit: 5d0a711f
discovered_branch: main
discovered_date: 2026-08-05
discovered_by: manual-investigation
labels:
- learning-tests
- confidence-check
- registry
testable: true
size: Medium
---

# BUG-3072: A `result: fail` assertion is invisible to every consumer once the record is `proven`

## Summary

`.ll/learning-tests/pytest.md` carries `status: proven` alongside an assertion whose
`result` is `fail`:

> `claim: using an unregistered marker with --strict-markers active causes collection error (exit non-zero)` → `result: fail`

That combination is **correct per spec** — `skills/explore-api/SKILL.md:190-192` defines
`proven` as "at least one assertion is `pass`" and `refuted` as "*all* exercised
assertions are `fail`". So this is not a status-computation bug.

The defect is downstream: once a record is `proven`, its failing claims are unreachable.
Every consumer branches on `record.status` alone, so a registry entry that explicitly
records a contradicted claim is indistinguishable from one where everything held.

## Current Behavior

`status` is author-supplied and never reconciled against `assertions`. Nothing in
`scripts/little_loops/learning_tests/` derives, validates, or re-checks it:

- `LearnTestRecord.from_dict` (`learning_tests/__init__.py:63`) reads `status` straight
  from frontmatter, defaulting to `"proven"` when the key is absent.
- `write_record` (`:90`) serializes whatever the caller set.
- `mark_stale` (`:130`) is the only mutation, and it only writes `"stale"`.

Consumers then use status as the whole truth:

| Consumer | Behavior on a `proven` record with failing assertions |
|---|---|
| `run_release_gate` (`learning_tests/release_gate.py:58`) | filters `status == "refuted" or is_record_stale(...)` → record passes silently |
| `cmd_check --stale-aware` (`cli/learning_tests.py:41`) | `record.status != "proven"` → exit 0, clean |
| `cmd_prove` (`:71`) | `return 0 if record.status == "proven" else 1` → reports success |
| `/ll:confidence-check` rubric (`skills/confidence-check/rubric.md:167`) | `proven` → **0 penalty**; only `refuted`/`missing`/`stale` score against readiness |

So an issue that depends on a claim the registry has already recorded as contradicted
passes the confidence gate with no deduction and no mention.

The one place that does read per-assertion results is
`scripts/little_loops/cli/history_context.py:75-77` (counts pass/fail/untested) — it is a
history-display path, not a gate.

**Secondary finding: `fail` conflates two different things.** The raw output
(`.ll/learning-tests/raw/pytest.txt:3`) for this claim is:

```
[FAIL] claim3_strict_markers_blocks_unregistered: rc=0 has_error=True
```

The probe demanded a non-zero exit code *and* an error marker; it got the error but
`rc=0`, so its compound condition failed. pytest's actual `--strict-markers` behavior is
not in doubt — this is a defective probe, not a contradicted API. Nothing distinguishes
"the API contradicted the claim" from "the proof script was wrong", and nothing ever
revisits it.

## Steps to Reproduce

1. `ll-learning-tests check pytest` → JSON with `status: proven` and one `result: fail`.
2. `ll-learning-tests check pytest --stale-aware` → considers only status; the failing
   assertion has no effect on the exit code (aside from the independent staleness flag).
3. Run `/ll:confidence-check` on an issue naming `pytest` as a learning target → the
   target scores `proven`, 0 penalty, failing claim never surfaced.

## Expected Behavior

A recorded `fail` assertion is visible wherever the record is consumed as evidence:

- `ll-learning-tests check` output makes the failing claims explicit (not merely present
  in the JSON body).
- The confidence-check rubric applies a deduction, or at minimum surfaces the failing
  claim text in the learning-test table, rather than treating `proven` as unqualified.
- A `fail` is distinguishable from an untrustworthy probe, so it can be triaged instead
  of silently persisting.

## Root Cause

Two-part:

1. **Status is a lossy summary used as the sole interface.** The record schema carries
   per-claim results, but every gate collapses to the three-valued `status`. `proven`
   means "≥1 claim held", which is a much weaker guarantee than the consumers treat it as.
2. **No reconciliation step exists.** `status` is written once by `/ll:explore-api` and
   never recomputed, so even a later edit to `assertions` cannot change it.

## Proposed Solution

Options, to be decided:

- **A — surface, don't gate** (smallest): make `cmd_check` print failing claims to stderr
  and add a `failing_claims` count to the JSON; add a rubric row so
  `/ll:confidence-check` reports them. Status semantics unchanged.
- **B — derive and validate status**: compute status from assertions on read
  (`from_dict`), and add a fourth state (e.g. `partial`) for "some pass, some fail" so
  gates can branch on it. Larger blast radius: every consumer's status comparison and the
  `Literal` type must be updated, and `skills/explore-api/SKILL.md` re-specified.
- **C — treat any `fail` as gate-relevant**: leave status alone but add
  `has_failing_assertions` to the release gate and `--stale-aware` exit conditions.

A is the minimum that fixes the observed harm; B is the principled fix. Recommend A now,
B behind a separate decision.

Independently: re-run the `pytest` `--strict-markers` probe with a corrected condition and
update that assertion, since the current `fail` is a probe artifact.

## Program Design

**Invariant.** No consumer treats a record as unqualified evidence while that record
contains an assertion with `result: fail`.

### Types

```python
result: Literal["pass", "fail", "untested"]
status: Literal["proven", "refuted", "stale"]
```

### Signatures

```python
def check_learning_test(target: str, *, base_dir: Path | None = None) -> LearnTestRecord | None:
def cmd_check(args: argparse.Namespace) -> int:
def run_release_gate(cwd: Path, *, base_dir: Path | None = None) -> int:
```

### Call Path

- `cmd_check` (`cli/learning_tests.py:13`) → `check_learning_test`
  (`learning_tests/__init__.py:140`) → `read_record` (`:105`) → `LearnTestRecord.from_dict` (`:63`)
- `run_release_gate` (`learning_tests/release_gate.py:36`) → `list_records` (`:117`)
- `skills/confidence-check/rubric.md:130` shells out to `ll-learning-tests check`

## Acceptance Criteria

- [ ] `ll-learning-tests check <target>` on a record containing a `result: fail` assertion
      makes the failing claim(s) explicit in its output.
- [ ] A test asserts that a `proven` record with ≥1 failing assertion is distinguishable
      from a `proven` record with none, at the consumer boundary chosen by the decision.
- [ ] `skills/confidence-check/rubric.md` states how failing assertions affect scoring.
- [ ] The `pytest` record's `claim3` assertion is re-run and its result corrected, or the
      claim reworded to match what the probe actually tests.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Impact

The registry exists so implementation decisions rest on proven API behavior. A claim the
registry has recorded as contradicted still reads as proven evidence to the confidence
gate — the exact failure mode the gate is meant to prevent. Currently one record is
affected, but nothing prevents recurrence, and the same mechanism hides genuine
refutations behind a single passing claim.

## Integration Map

- `scripts/little_loops/learning_tests/__init__.py` — record model / status handling
- `scripts/little_loops/cli/learning_tests.py` — `check`, `prove` exit semantics
- `scripts/little_loops/learning_tests/release_gate.py` — gate filter
- `skills/confidence-check/rubric.md`, `skills/confidence-check/SKILL.md` — scoring
- `skills/explore-api/SKILL.md:187-192` — status determination spec
- `.ll/learning-tests/pytest.md`, `.ll/learning-tests/raw/pytest.txt` — the affected record

## Related Issues

- ENH-2214 — release gate blocking on stale/refuted records
- ENH-3073 — staleness policy for the same registry

## Status

Open. Root cause confirmed; remedy option (A/B/C) undecided.
