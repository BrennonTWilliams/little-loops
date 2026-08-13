---
id: ENH-2990
title: Measure the live re-refine skip rate for research-triage
type: ENH
priority: P3
status: open
captured_at: '2026-08-02T05:14:22Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
parent: EPIC-3023
testable: true
relates_to:
- ENH-2971
labels:
- issues
- measurement
- cost
verify_verdict: VALID
---

# ENH-2990: Measure the live re-refine skip rate for `research-triage`

## Summary

ENH-2971's `triage_research_axes()` shipped with its yield measured over the
`.issues/` corpus in each issue's *final* state. That measurement is a poor
proxy for the case the change exists to optimize — `autodev.yaml` re-refining
an issue minutes to hours after a prior pass — and the two numbers differ by
4x. Instrument the real call path (or replay the historical one) to establish
which end of the range production actually sees.

## Current Behavior

The recorded measurement (ENH-2971 § Threshold Validation, 2026-08-02, 2,893
issues / 8,679 axis-spawns):

| Predicate | axis-spawns skipped | locator band spread |
|---|---|---|
| coverage only (`check_staleness=False`) | **33.7%** | 12.4pt |
| coverage + staleness (production default) | **8.6%** | 37.4pt |

Nothing in the corpus sweep observes a real invocation. It scores each issue as
it stands today, against a repo whose files have almost all been committed
since that issue's last recorded `/ll:refine-issue` Session Log entry — so the
Staleness Check invalidates nearly every otherwise-covered axis. The corpus is
also dominated by `done` issues, whose last refine is weeks old.

ENH-2971's own Expected Yield section already names this limitation ("It scores
each issue in its *current* (final) state, not the state it was in at each
historical refine invocation. It is a proxy for the re-refine case, not a replay
of it."). Adding the Staleness Check made the limitation dominant rather than
marginal, which is what this issue exists to resolve.

## Expected Behavior

A measured, defensible figure for the production skip rate, with the
measurement method recorded so it can be re-run after future changes to the
predicate.

## Motivation

The number decides whether the mechanism is worth its complexity, and it is
currently unknown within a 4x band:

- At ~34%, the Staleness Check is nearly free in practice and ENH-2971's
  "~1,700 subagent calls avoided" estimate roughly holds.
- At ~9%, the Staleness Check is eating three quarters of the benefit, and the
  right follow-up is to make it less blunt — it is deliberately file-grained,
  so an unrelated edit anywhere in a large referenced file forces a re-spawn.

There is no way to choose between those responses without the measurement.
`ll-issues research-triage` is on `autodev.yaml`'s critical path, so the data
accumulates on its own once something records it.

## Proposed Solution

**Option A — instrument the live CLI (recommended).** Record each
`ll-issues research-triage` invocation's per-axis verdict, and for uncovered
axes the discriminating reason (`below_threshold` / `no_qualified_refs` /
`missing_symbol` / `stale`). The `analytics.capture.cli_commands` config already
declares `["*"]`, and `.ll/history.db` is the existing sink; check whether the
existing CLI-invocation capture can carry a structured payload before adding a
table. Then read it back after enough autodev cycles have accumulated.

Distinguishing `stale` from the coverage-side reasons is the whole point — that
split is exactly the 33.7%-vs-8.6% gap, measured on real invocations instead of
inferred from a corpus sweep.

**Option B — historical replay.** For each recorded `/ll:refine-issue` Session
Log entry, reconstruct the issue's content and the repo state at that timestamp
(`git show <rev>:<path>`) and score the predicate as it would have run. No
waiting, and it covers the 2,261 recorded invocations — but reconstructing each
issue file's own historical content is the expensive part, and issues are
committed less often than source, so the reconstruction is lossy for
working-tree state that was never committed.

**Option C — bounded live sample.** Wrap the next N autodev runs with a shim
that logs the triage JSON, and stop at a fixed sample size. Cheapest to build,
smallest sample, no permanent instrumentation.

A follow-up worth scoping only after the number is in hand: if `stale`
dominates, consider making the Staleness Check line-grained or scoping it to
the specific paths an axis's evidence resolved against, rather than every
resolved path in the section.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/research_triage.py` — the instrumentation
  point for Option A (`cmd_research_triage` already computes the full verdict)
- `scripts/little_loops/issues/research_triage.py` — `AxisCoverage.evidence` is
  currently free-text prose; a machine-readable reason code would need adding
  for any of the three options to classify verdicts without parsing strings
- `.ll/history.db` — the existing sink; confirm whether CLI-invocation capture
  can carry a structured payload before adding a table

### Tests

- `scripts/tests/test_research_triage.py` — `TestCorpusBaseline` holds the
  existing corpus-sweep measurement and its documented coverage-only reading;
  whatever this issue measures should be recorded alongside it rather than
  replacing it.

## Implementation Steps

1. Decide between A/B/C — the choice is a cost/latency tradeoff, not a
   correctness one.
2. Add a machine-readable reason code to `AxisCoverage` (or a sibling field)
   so `stale` is distinguishable from the coverage-side rejections without
   parsing `evidence` prose.
3. Implement the chosen measurement path.
4. Record the result in ENH-2971's Threshold Validation section next to the
   corpus numbers, so the two are read together.
5. If `stale` dominates, open a follow-up to narrow the Staleness Check.

## Impact

- **Effort**: Small-Medium — instrumentation plus a wait, or a replay harness.
- **Expected benefit**: Resolves a 4x uncertainty in the value of a shipped
  mechanism, and tells us whether the Staleness Check needs narrowing.
- **Risk**: Low — measurement only; no change to the predicate's behavior
  beyond adding a reason code.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: measuring the live/replayed skip rate and its `stale`-vs-
  coverage split; the reason code needed to do so.
- **Out of scope**: changing `COVERAGE_THRESHOLD`, changing the Staleness
  Check's granularity, or acting on the result — those are follow-ups the
  measurement is meant to inform.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/CLI.md` § `ll-issues research-triage` | The predicate's documented contract and axis semantics |
| `.issues/enhancements/P3-ENH-2971-*.md` § Threshold Validation | The corpus measurement this issue exists to supersede for the live case |

## Session Log
- `/ll:verify-issues` - 2026-08-13T03:04:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-10T18:52:52 - `ffa08fd4-dce7-4108-91f7-6bb57e5df4c8.jsonl`
- `/ll:capture-issue` - 2026-08-02T05:15:40 - `3204c464-5212-4b68-a6a3-d963db2a8337.jsonl`

---

## Status

**Open** | Created: 2026-08-02 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's reason-code taxonomy for `AxisCoverage` (distinguishing `stale` from coverage-side rejections) and ENH-3000's new `untracked_by_design` verdict/denominator status both touch coverage/denominator accounting in `scripts/little_loops/issues/research_triage.py`. When implementing, reconcile both into one consistent enum rather than two independently-evolving classification schemes in the same module.
