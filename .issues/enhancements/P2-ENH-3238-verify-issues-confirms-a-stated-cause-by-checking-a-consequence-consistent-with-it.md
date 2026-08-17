---
id: ENH-3238
type: ENH
title: verify-issues confirms a stated cause by checking a consequence consistent
  with it
priority: P2
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T18:22:51Z'
---

# ENH-3238: verify-issues confirms a stated cause by checking a consequence consistent with it

## Summary

`/ll:verify-issues` verifies that a claim's *observable consequence* holds and treats that as
confirming the claim's *stated cause*. Necessary-but-not-sufficient evidence is accepted as
sufficient, so a false causal attribution can pass with verdict `VALID` — and confirming the
symptom actively raises confidence in the false explanation.

Discovered by reviewing the `refine-to-ready-issue` run that certified BUG-3236
(run `.loops/.history/2026-08-17T170259-refine-to-ready-issue`; the `verify_issue` transcript is
session `038b6ab4-3b9f-4cfd-a4d6-dac5e7366086`, recorded as `session_jsonl` on that run's third
`action_complete` event in `events.jsonl`).

## Current Behavior

BUG-3236 asserted an identity claim: the live `issue_sessions` view "is the v16 (ENH-2462)
definition." `verify_issue` did run live-state checks — it opened `.ll/history.db` and executed:

```python
print('version:', c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0])
print('cols:', [r[1] for r in c.execute('PRAGMA table_info(issue_sessions)')])
# → version: 41
# → cols: ['issue_id','session_id','jsonl_path','first_message_ts','last_message_ts']
```

It also ran `ll-history sessions ENH-3195` and observed the real `no such column: issue_num`
error, reporting "Reproduction confirmed live — matches the issue exactly."

It then concluded, verbatim: "`issue_sessions` has the **pre-v36 column set** (no `issue_num`)"
— inferring the *identity of a view definition* from the *absence of one column*. Many
definitions satisfy that predicate. The live view was in fact a third variant with no committed
ancestor (a `GROUP BY issue_num` plus a `JOIN issue_events le ON le.issue_id` clause appearing in
zero commits).

The sufficient test was one line from a script it had already written, on a connection it
already held open:

```sql
SELECT sql FROM sqlite_master WHERE name='issue_sessions';
```

It compounded the error by confirming that the issue's *quotation* of the v16 source matched
`schema.py:372,386` (true) without ever diffing source-v16 against the live SQL.

Verdict: `VALID`. Downstream `confidence_check` scored 96/90.

## Expected Behavior

A causal or identity claim in an issue is verified by probing the claimed cause directly.
Observing a consequence that is merely *consistent* with the stated cause does not on its own
earn a `VALID` verdict — where the cause cannot be read directly, the verdict is `NEEDS_UPDATE`
and the unverified claim is named.

## Motivation

The `verify_issue` gate exists to be the one state in `refine-to-ready-issue` that can refute
the issue's own text. When it accepts necessary-but-not-sufficient evidence, a false root cause
is not merely missed — it is *certified*, and every downstream state inherits that certification.
BUG-3236 reached `verify_verdict: VALID`, `confidence_score: 96`, `outcome_confidence: 90` with a
central causal claim that one additional query disproved. Implementation work started from that
false cause would have targeted the wrong fix.

The change is small and well-precedented: one claim-shape rule in a file that already contains an
identically-shaped rule for negative claims.

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

- **Priority**: P2 - The gate is the loop's only refutation state; when it certifies a false
  cause, downstream states inherit the certification and implementation starts from the wrong
  target. Not P1: prevalence is unestablished (n=1) and no released behavior is broken.
- **Effort**: Small - one claim-shape rule added to a markdown command file, mirroring the
  structure of a rule already in the same section.
- **Risk**: Low - additive prompt guidance. The realistic downside is over-triggering, which
  costs verification time and yields `NEEDS_UPDATE` instead of `VALID` on issues whose causes
  cannot be probed directly.
- **Breaking Change**: No

## Root Cause

`commands/verify-issues.md`, section `#### B. Verify Against Codebase` (lines 126-130). Four of
its five checks are artifact existence and location — files exist, line numbers resolve, quoted
snippets match, decisions-log gate. The fifth is `4. **Test claims**: Is the described behavior
accurate?` — a bare instruction with no method attached and no notion of claim *shape*.

The section therefore has no rule distinguishing:
- **consequence claims** ("reader X throws `no such column`") — directly observable, and
  correctly verified here; from
- **identity / causal claims** ("the live view IS the v16 definition", "this is caused by Y") —
  where observing a consistent consequence does not establish the attribution.

The file already contains exactly the right pattern for the missing rule. Lines 113-116 define a
claim-shape-triggered method for **negative claims**, including the sufficiency reasoning that is
absent for causal claims:

> **Negative claims**: for issue text asserting "X is never called" ... run `ll-code
> callers-of`/`references` on the named symbol before falling back to Grep-only reasoning. A hit
> refutes the claim outright; a miss is a lead that the normal exploratory pass must still confirm.

## Proposed Solution

Add an identity/causal-claim rule to `commands/verify-issues.md` §2B, mirroring the
negative-claims rule's structure (claim shape → required probe → sufficiency note):

1. **Detect the shape.** Issue text attributing observed state to a specific named cause,
   origin, or version — "is the vN definition", "caused by", "because", "the result of",
   "introduced by", "this is the pre-X form".
2. **Probe the cause directly, not a consequence.** Where the artifact can be read in its own
   terms, read it: stored DDL (`SELECT sql FROM sqlite_master`) over inferred shape
   (`PRAGMA table_info`); the actual file/commit content over a symptom consistent with it.
3. **State the sufficiency test explicitly.** Confirming a consequence consistent with the
   stated cause does not confirm the cause; it only fails to refute it. If the cause cannot be
   read directly, the verdict is `NEEDS_UPDATE`, not `VALID`.
4. Consider a distinct verdict or a Verification Notes annotation recording which claims were
   directly verified vs. only corroborated, so a later reader can tell them apart — the same
   motivation as the existing provider/freshness recording requirement at lines 118-124.

## Acceptance Criteria

- [ ] `commands/verify-issues.md` §2B contains a causal/identity-claim rule naming the claim
      shape, the required direct probe, and the necessary-vs-sufficient distinction.
- [ ] The rule states that a consequence consistent with a stated cause does not on its own
      support a `VALID` verdict.
- [ ] Re-running `/ll:verify-issues BUG-3236 --check` against the pre-correction text of the
      issue would surface the root-cause claim as unverified rather than `VALID`. (The corrected
      issue now states the true cause, so this must be exercised against the prior revision —
      see git history for the file.)
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

Two adjacent things are deliberately **not** part of this issue:

- **`confidence_check` is not the fix site.** Its transcript
  (`83adf706-3c34-48ba-adbd-2ccf3898278d.jsonl`) shows zero live queries: document, source, and
  `ll-issues format-check` only, scoring complexity / test-coverage / ambiguity / change-scope.
  96 was correctly computed against what it measures. It is structurally incapable of catching
  this and should not be taught to.
- **Do not widen meta-loop detection.** `refine-to-ready-issue` is correctly *not* a meta-loop:
  `_is_meta_loop` (`scripts/little_loops/fsm/validation/meta_rules.py:48-70`) keys on actions
  touching `loops/*.yaml`, `skills/`, `agents/`, `commands/`, `.claude/`, and this loop writes
  `.issues/`. Capturing it would also impose the diagnose-first shape and benchmark
  requirements, which do not fit an issue-refinement loop. The MR-1/MR-2 *principle* (pair an
  LLM judgment with a measurable external signal) is what transfers here; the classification is not.

## Notes

A third candidate mitigation was considered and **refuted by the evidence**: a hard gate refusing
`ready` while a Steps to Reproduce block has no recorded execution output. The reproduction *was*
executed in this run, so that gate would have passed BUG-3236 unchanged.

Prevalence is unestablished, deliberately: BUG-3236 is the only `open` issue among 106 carrying
`verify_verdict: VALID`; the other 24 verified BUGs are all completed, so their claims cannot be
re-tested without confounding. A grep across them for post-hoc root-cause corrections returned one
hit (BUG-3102) whose "turned out" is narrative, not a correction. **n=1** — the fix is justified by
the mechanism being clear and the change being small, not by a demonstrated pattern.

Follows ENH-3031, which added the `verify_issue` gate to this loop; this refines the gate's method
rather than its placement.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-17 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-17T18:23:56 - `66dab8b6-e923-43d4-9f0e-eccb97176e0f.jsonl`
