---
id: ENH-2657
title: Detect an abandoned autodev queue in finalize (silent work loss on timeout)
type: ENH
priority: P2
status: done
discovered_date: 2026-07-16
captured_at: '2026-07-16T00:00:00Z'
discovered_by: capture-issue
completed_at: '2026-07-16T13:53:57Z'
decision_needed: false
labels:
- enhancement
- loops
- autodev
- finalize
- observability
- captured
confidence_score: 100
outcome_confidence: 92
score_complexity: 20
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 22
---

# ENH-2657: Detect an abandoned autodev queue in finalize (silent work loss on timeout)

## Summary

When `auto-refine-and-implement` (via `sprint-refine-and-implement`) delegates a
large issue set to `autodev`, `autodev` drains its unified depth-first queue
(`${run_dir}/autodev-queue.txt`) one issue at a time. If `autodev` hits its
`timeout` (28800s / 8h) or `max_steps` (500) **mid-drain**, it terminates with a
**non-empty queue** — those issues were dispatched but never refined, never
implemented, and never parked with a skip reason. `finalize` in
`auto-refine-and-implement.yaml` never reads `autodev-queue.txt`, so these
abandoned issues appear in **none** of summary.json's counters (`closed`,
`skipped`, `not_closed`, `gate_blocked`, `inflight_unresolved`). The run reads a
clean partial and routes to the green `done` terminal.

`finalize` should read the residual `autodev-queue.txt` at completion, count it
as a distinct `abandoned` signal in summary.json, fold it into `parked_rate`,
and — like `phantom` (BUG-2636) — keep an abandoned-queue run off the green
`done` terminal.

## Motivation

- **Observed silent work loss.** In the `ll-marketing` run
  `sprint-refine-and-implement-20260715T182217` (EPIC-058): 27 issues dispatched,
  3 passed / 1 shipped, 11 parked, and **18 left undrained in
  `autodev-queue.txt`** when the 8h timeout fired (481m39s ≈ 480m = `timeout:
  28800`). Two of the 18 (`ENH-110`, `ENH-111`) were correctly-enqueued
  decomposition children at the front of the queue that simply never got their
  turn. summary.json reported `closed=1` and routed to `done`; the 18 abandoned
  issues were invisible. The operator had to hand-reconstruct the real outcome
  from the queue file.
- **Same class as BUG-2636, but wider.** BUG-2636 added `INFLIGHT_UNRESOLVED` to
  catch the single `autodev-inflight` sentinel left mid-implementation. That
  guard reads exactly one issue; it does not look at the residual queue. An
  entire undrained queue passes straight through the existing accounting.
- **The verdict/terminal is misleading, not just incomplete.** Because
  `CLOSED > 0` yields `partial` → `done` (finalize routing,
  `auto-refine-and-implement.yaml:883-924`), a run that abandoned 18 of 27
  dispatched issues renders green. There is no signal telling the operator to
  re-run to drain the remainder.
- **It reframes the budget conversation.** Knowing "18 abandoned at timeout" (vs
  "1 shipped, looks done") is what tells an operator to either raise the budget,
  shrink the scope, or land the wasted-slot prefilter (tracked separately). The
  counter is the prerequisite for that decision.

## Current Behavior

- `autodev` seeds `${run_dir}/autodev-queue.txt` from `context.input` at `init`
  and pops the head at each `dequeue_next`; it exits to its `done` terminal only
  when the queue is empty (`autodev.yaml:80-83`). On `timeout`/`max_steps` the
  FSM engine terminates with the queue still populated.
- `finalize` (`auto-refine-and-implement.yaml:676-924`) computes `CLOSED`,
  `NOT_CLOSED`, `SKIP`, `ERR`, `GATE_BLOCKED`, `DECISION_UNRESOLVED`,
  `INFLIGHT_UNRESOLVED` — but never reads `autodev-queue.txt`.
- `PARKED_RATE` denominator is the dispatched ledger, but its numerator omits the
  abandoned queue, so the rate understates the true incompletion.
- Verdict routing: `phantom` → `incomplete` (exit 1); everything else with
  `CLOSED > 0` → `done`. An abandoned-queue partial is indistinguishable from a
  clean partial.

## Expected Behavior

- `finalize` reads `${run_dir}/autodev-queue.txt`. Non-blank residual lines
  (excluding any already in the closed-now union, to be safe against a
  late-closing race) are counted as `ABANDONED` and the IDs are written to an
  `auto-refine-and-implement-abandoned.txt` artifact.
- summary.json gains an `"abandoned": N` field and the abandoned count is added
  to the `PARKED_RATE` numerator alongside `SKIP + NOT_CLOSED + GATE_BLOCKED +
  DECISION_UNRESOLVED + INFLIGHT_UNRESOLVED`.
- Verdict/terminal: a run with `ABANDONED > 0` must not route to green `done`.
  Preferred: treat a non-empty residual queue the same way `phantom` is treated
  (exit 1 → `incomplete`), OR introduce an `incomplete-abandoned` verdict that
  also routes to the `incomplete` terminal. A run that legitimately drained its
  queue (empty file) is unaffected.
- The `incomplete` terminal message names the abandoned count and points at the
  artifact so a re-run to drain is obvious.

## Proposed Solution

1. In `finalize` (`auto-refine-and-implement.yaml`), after the closed-now union
   is computed, add:
   ```sh
   : > "$RUN_DIR/$P-abandoned.txt"
   if [ -s "$RUN_DIR/autodev-queue.txt" ]; then
     grep '[^[:space:]]' "$RUN_DIR/autodev-queue.txt" | sort -u \
       | comm -23 - "$RUN_DIR/$P-closed-now-union.txt" \
       > "$RUN_DIR/$P-abandoned.txt" 2>/dev/null || true
   fi
   ABANDONED=$(count $P-abandoned.txt)
   ```
2. Add `ABANDONED` to the `PARKED_RATE` numerator.
3. Add `"abandoned":%s` to the summary.json printf and the human-readable echo.
4. Extend the verdict block so `ABANDONED > 0` cannot yield green `done`:
   either fold into the existing `phantom`/exit-1 path or add a dedicated
   `incomplete-abandoned` verdict routed to `incomplete`. Keep `CLOSED > 0` runs
   labeled as partial-progress in the *verdict string* (so real closures are
   still visible), but the *terminal* must be `incomplete` when work was
   abandoned.
5. Update the `incomplete` terminal message to mention the abandoned count.

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current `auto-refine-and-implement.yaml` and `autodev.yaml` (2026-07-16):_

**Verified anchors (line numbers refreshed — the `Sources` refs had drifted):**

- `finalize` state: `auto-refine-and-implement.yaml:676-925`; action shell body
  `689-920`. Local vars: `RUN_DIR="${context.run_dir}"` (`:689`),
  `P=auto-refine-and-implement` (`:690`), and the counter
  `count() { awk 'NF{c++} END{print c+0}' "$RUN_DIR/$1" ...; }` (`:691`) — a
  blank-line-skipping line count, exactly what the abandoned read needs.
- Closed-now union file: `$RUN_DIR/$P-closed-now-union.txt` (built ~`:763`). This
  is the correct file for the `comm -23` subtraction in the Proposed Solution
  (step 1) — it is the full closed set, not just the since-baseline diff
  (`CLOSED` at `:756` uses `$P-closed-union.txt`, a different, narrower file). Use
  `-closed-now-union.txt` for the abandoned subtraction, per the AC's late-close
  guard.
- `PARKED_RATE` numerator (`:849`):
  `$SKIP + $NOT_CLOSED + $GATE_BLOCKED + $DECISION_UNRESOLVED + $INFLIGHT_UNRESOLVED`
  over denominator `$INPUT_SIZE`. Add `$ABANDONED` here.
- summary.json printf: `:899`; human-readable echo: `:905-906`. Both must gain the
  new field.
- Verdict logic: `:883-896` (INFLIGHT_UNRESOLVED already gates `phantom` at
  `:890`, from BUG-2636). Terminal routing: `case "$VERDICT" in phantom) exit 1
  ;; *) exit 0 ;; esac` at `:917-920`; `exit 1`→`on_no: incomplete`, `exit
  0`→`on_yes: done` (`:922-923`). `incomplete` terminal message: `:935`.
- `autodev.yaml` confirmed: queue seeded from `${context.input}` (`:50`),
  `dequeue_next` pops via `head -1`/`tail -n +2` (`:80-85`), empty-queue exit →
  `on_no: done` (`:70,:80-81`), `max_steps: 500` (`:18`), `timeout: 28800`
  (`:19`).

**Precedent to mirror (INFLIGHT_UNRESOLVED / BUG-2636)** — the abandoned counter
is a direct generalization of the single-sentinel guard. Follow its five touch
points verbatim: (1) count computation, (2) `:849` numerator, (3) `:899` printf,
(4) `:905` echo, (5) `:890` verdict gate. This keeps the diff minimal and the
accounting symmetric.

**Verdict-branch decision (Proposed Solution step 4) — recommendation:**

> **Selected:** Option B — dedicated `incomplete-abandoned` verdict; the only
> shape that surfaces abandonment on a `CLOSED > 0` run, matching the
> codebase's own most recent compound-verdict precedent (`partial-with-errors`,
> ENH-2376).

**Option A**: Fold `ABANDONED > 0` into the existing `phantom`/exit-1 path (add
`ABANDONED` to the `:890` no-closure disjunction). Minimal diff, reuses the
proven exit-1→`incomplete` route; but a run with `CLOSED > 0` *and* an abandoned
queue would still be labeled `partial`, not `phantom`, so the verdict string
alone wouldn't flag abandonment.

**Option B**: Add a dedicated `incomplete-abandoned` verdict that also exits 1 →
`incomplete`, set whenever `ABANDONED > 0` regardless of `CLOSED`. Slightly more
code, but the verdict string itself names the abandonment (better operator
signal, matches the "not just incomplete, misleading" motivation).

**Recommended**: Option B — the whole point of the ENH is that a green/partial
label on an 18-of-27-abandoned run is misleading. A distinct verdict string that
survives `CLOSED > 0` is what makes the abandonment visible without reading the
artifact. Both routes satisfy the AC (`_is_success` name check on `incomplete`);
B additionally satisfies the "verdict/terminal is misleading" motivation.

**Test model** — extend `scripts/tests/test_builtin_loops.py`. The closest
existing pattern is `test_finalize_stale_inflight_counts_as_unresolved`
(`:2616-2628`, BUG-2636), which drives the `_run_finalize` helper
(`:2225-2243`). That helper seeds ledger files (`autodev-passed.txt`,
`autodev-skipped.txt`, `autodev-gate-blocked.txt`,
`autodev-decision-unresolved.txt`) and the `autodev-inflight` sentinel, runs the
finalize shell in a temp dir, and returns parsed summary.json. Add a sibling
seeding a non-empty `autodev-queue.txt` (residual IDs) and assert
`summary["abandoned"] == N`, `summary["parked_rate"] > 0`, and the
verdict/terminal is non-green (`incomplete`). Add companion cases for the
empty-queue (unaffected, `abandoned: 0`) and late-close-race
(residual-all-closed → `abandoned: 0`) ACs — the `_run_finalize` `closed=`/
`passed=` params already support seeding those.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-16.

**Selected**: Option B — dedicated `incomplete-abandoned` verdict

**Reasoning**: Both options reuse identical infrastructure (the `count()`
helper, `PARKED_RATE` numerator, summary.json printf/echo, and the
`_run_finalize` test harness) — the choice is purely about which verdict
branch carries the signal. Option A is structurally inert for the issue's own
motivating scenario: the `elif` chain at `:883-897` checks `CLOSED > 0`
branches (`success`/`partial-with-errors`/`partial`) before the `phantom`
branch is ever reached, so a run that closed 1 issue and abandoned 18 (the
exact case in the Motivation section) would still render `partial`, not
`phantom`, no matter what's OR'd into the `:890` disjunction. The codebase's
own most recent precedent for a compound "closed-something + secondary-signal"
verdict — `partial-with-errors` (ENH-2376) — was implemented as a new,
distinct verdict string rather than folded into an existing bucket, and
neither option's downstream consumers (`ll-loop`'s terminal-name-only
`_is_success` check, `sprint-refine-and-implement.yaml`'s pass-through
`read_outcome`) branch on the verdict string's literal value, so Option B adds
no new consumer-side infrastructure either.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| Option A (fold into `phantom`) | 2/3 | 3/3 | 2/3 | 2/3 | 9/12 |
| Option B (dedicated `incomplete-abandoned`) | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- Option A: verbatim repeat of the BUG-2636 `INFLIGHT_UNRESOLVED` disjunction
  pattern with zero new infrastructure, but semantically inert for any
  `CLOSED > 0` abandoned run — the exact scenario the issue was captured from.
- Option B: matches ENH-2376's `partial-with-errors` precedent for compound
  verdicts; requires two explicit touch points (the `case "$VERDICT"`
  terminal-routing statement at `:917-920` and the `_run_finalize` test
  helper's `expected_rc` check) beyond the shared five-point ledger pattern.

## Acceptance Criteria

- [x] `finalize` reads `autodev-queue.txt`; a non-empty residual queue produces
      `abandoned > 0` in summary.json and an
      `auto-refine-and-implement-abandoned.txt` artifact listing the IDs.
- [x] The abandoned count is included in the `parked_rate` numerator.
- [x] A run that abandoned ≥1 dispatched issue does NOT route to the green `done`
      terminal (renders as `incomplete` per `ll-loop`'s `_is_success` name check).
- [x] A run that fully drained its queue (empty `autodev-queue.txt`) is
      unaffected: same verdict/terminal as today, `abandoned: 0`.
- [x] A run where the residual queue entries all actually closed (late-close
      race) reports `abandoned: 0` (the closed-now-union subtraction holds).
- [x] Test coverage in `scripts/tests/test_builtin_loops.py` (or a finalize-
      focused test) simulating a non-empty `autodev-queue.txt` at finalize and
      asserting the verdict/terminal + summary.json field.

## Sources

- Run artifacts:
  `<ll-marketing>/.loops/runs/sprint-refine-and-implement-20260715T182217/`
  (`autodev-queue.txt` = 18 undrained; `autodev-passed.txt`,
  `autodev-skipped.txt`, `auto-refine-and-implement-dispatched.txt`).
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:676-937` (finalize
  + incomplete terminal).
- `scripts/little_loops/loops/autodev.yaml:17-83` (queue seed/drain, max_steps
  500, timeout 28800).
- BUG-2636 (`INFLIGHT_UNRESOLVED`) — the single-sentinel precedent this
  generalizes.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — verdict/terminal signal honesty.
- `.claude/CLAUDE.md` § Loop Authoring (MR-1 non-LLM evaluator; this is a
  non-LLM ledger check).

## Status

done — implemented 2026-07-16 (Option B).

## Resolution

Implemented in `auto-refine-and-implement.yaml` finalize (Option B, per the
decide-issue selection). Five shared touch points mirror the BUG-2636
`INFLIGHT_UNRESOLVED` precedent, plus the two Option-B-specific points:

1. `ABANDONED` reads residual `autodev-queue.txt`, subtracts the closed-now union
   (`comm -23`) to hold against a late-close race, and writes the residual IDs to
   `auto-refine-and-implement-abandoned.txt`.
2. `ABANDONED` folded into the `PARKED_RATE` numerator.
3. `"abandoned":%s` added to the summary.json printf and the human-readable echo.
4. New `incomplete-abandoned` verdict — set whenever `ABANDONED > 0`, taking
   precedence over every `CLOSED > 0` bucket so an 18-of-27-abandoned run no
   longer renders as green `partial`.
5. `incomplete-abandoned` joins `phantom` on the `exit 1 → incomplete` terminal
   route; the `incomplete` terminal message names the abandoned count and points
   at the artifact.

Tests: `test_finalize_abandoned_queue_counts_and_diverts_terminal`,
`test_finalize_empty_queue_is_unaffected`,
`test_finalize_abandoned_zero_when_residual_all_closed` in
`scripts/tests/test_builtin_loops.py` (TDD red→green). Full suite green
(15096 passed); `ll-loop validate auto-refine-and-implement` passes.

## Impact

- **Affected:** `auto-refine-and-implement.yaml` finalize, and by delegation
  every `sprint-refine-and-implement` / EPIC-scope autodev run that exceeds its
  budget mid-drain. No change to loops that drain fully.
- **Severity:** P2 — silent work loss. Dispatched issues vanish from the run
  summary with no counter and no non-green signal, so operators cannot tell a
  fully-drained partial from one that abandoned most of its set.
- **Risk of change:** low — additive ledger read + one summary field + a verdict
  branch; the empty-queue path (normal completion) is unchanged.

## Scope Boundaries

- **In scope:** finalize reading the residual queue, the `abandoned` counter,
  `parked_rate` inclusion, and keeping abandoned-queue runs off green `done`.
- **Out of scope:** the pre-dispatch readiness/dependency prefilter that would
  reduce wasted slots (separate ENH), raising or making the 8h `timeout`
  configurable, and any change to `autodev`'s own drain/step budget.

## Session Log
- `/ll:manage-issue` - 2026-07-16T13:53:05 - implemented Option B (finalize abandoned-queue signal + incomplete-abandoned verdict)
- `/ll:decide-issue` - 2026-07-16T13:45:09 - `2bcf269c-0ef8-46e0-8318-65e28e8e6867.jsonl`
- `/ll:refine-issue` - 2026-07-16T13:41:52 - `e8d423c5-f164-4257-9937-91797e1531ab.jsonl`

- 2026-07-16: Captured from forensic analysis of `ll-marketing` run
  `sprint-refine-and-implement-20260715T182217`. Confirmed 18 issues left in
  `autodev-queue.txt` at the 8h timeout, invisible to summary.json, run routed
  to green `done`.
