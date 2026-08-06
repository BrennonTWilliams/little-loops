---
id: BUG-3065
title: refine-to-ready-issue dead-ends on decision_needed instead of resolving it
type: BUG
priority: P3
status: done
discovered_by: capture-issue
discovered_date: 2026-08-05
captured_at: '2026-08-05T20:05:24Z'
completed_at: '2026-08-06T04:38:48Z'
relates_to:
- ENH-3075
- BUG-3063
- BUG-2528
- BUG-1366
- BUG-2595
- BUG-1416
- ENH-2443
- ENH-2446
- FEAT-937
labels:
- loops
- fsm
- decision-gate
testable: true
decision_needed: false
verify_verdict: VALID
size: Large
confidence_score: 100
outcome_confidence: 59
score_complexity: 5
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3065: `refine-to-ready-issue` dead-ends on `decision_needed` instead of resolving it

## Summary

`refine-to-ready-issue.yaml` has three `decision_needed` gates that all route `on_yes: done`. That
routing is a **sub-loop handoff contract** — exit clean, let a parent loop run `/ll:decide-issue`,
then re-enter. The contract holds for exactly one of its four invocation paths; on the other three
the issue silently dead-ends. Run it on an issue whose refine pass sets `decision_needed: true` and
it exits `done` after four states, having silently skipped `/ll:wire-issue`, `/ll:verify-issues`,
and `/ll:confidence-check` — with no signal to the operator that the readiness pipeline never ran.

### Which callers honor the contract

_Corrected 2026-08-05 (pre-implementation review): an earlier revision of this Summary claimed
"nothing invokes `refine-to-ready-issue` as a sub-loop today." That is false — there are three
live `loop:` callers, and one of them does resolve the decision._

| Invocation path | Post-return decision handling | Contract honored? |
|---|---|---|
| `ll-loop run refine-to-ready-issue <ID>` (direct) | none — the run just ends | **No** — the reproduced bug |
| `autodev.yaml:385` (`refine_current`) | `check_decision_after_refine` (`autodev.yaml:~484`) → `check_decision_decidable` → `run_decide` | **Yes** — works end-to-end today |
| `recursive-refine.yaml:231` (`run_refine`) | `check_decision_needed` (`:556-568`) **skips** the issue to `recursive-refine-skipped-decision.txt` | **No** |
| `issue-refinement.yaml:29-33` | none | **No** |

This narrowing matters for the fix, not just the framing: because `autodev` *does* resolve the
decision after the sub-loop returns, moving resolution **into** `refine-to-ready-issue` makes
`autodev`'s `check_decision_after_refine` → cluster path largely dead on the post-refine path
(it degrades to the defense-in-depth role its own comment already claims). That is acceptable, but
it must be a deliberate outcome of the design rather than an accident — see `### Caller interaction
after the fix` below.

## Scope

_Split 2026-08-05 (third pre-implementation review). Prior revisions bundled the `autodev.yaml`
conversion into this issue, giving it size Very Large and `outcome_confidence: 59`._

**In scope here:**

1. Author the new sub-loop at `scripts/little_loops/loops/oracles/resolve-decision.yaml`, extracted
   from `autodev.yaml`'s inline cluster per `### The extraction boundary`.
2. Adopt it in `refine-to-ready-issue.yaml` — three `loop:` call states, a new
   `record_decision_unresolved`, `max_steps` 30 → 40, header-comment update.

**Deferred to [ENH-3075](../enhancements/P3-ENH-3075-convert-autodev-to-shared-decision-cluster-sub-loop.md):**
converting `autodev.yaml` to call the sub-loop and deleting its inline copy — plus the ~25 broken
assertions across `test_autodev_decision_gate.py` and `test_builtin_loops.py`, the marker rename
sweep, the `autodev` sections of `LOOPS_REFERENCE.md`, and two design questions that only bite on the
autodev path (rate-limit propagation out of a `loop:` state, and the `assert_decision_cleared`
reorder losing `recheck_after_decide`'s `snap_and_size_review` escape).

**Why this split.** The reported bug is fixed entirely by (1) + (2); `autodev` already honors the
handoff contract today (Summary caller table), so it gains nothing from the conversion beyond
drift prevention. Splitting gets a P3 user-visible dead-end fixed behind a small diff whose test
surface is `TestRefineToReadyIssueSubLoop` plus new oracle tests, and isolates the risky rewiring of
autodev's five-bug-fix-deep decision path — which has no end-to-end coverage — into its own change.

**Accepted cost.** Between this issue landing and ENH-3075, the cluster exists in **two** copies
(`autodev.yaml` inline + the new sub-loop), which is the duplication Option B exists to eliminate.
This is transitional and time-boxed by ENH-3075, not the end state. Note the copies do not interfere:
`autodev` keeps writing its flat `autodev-decide-options-deposited` marker while the sub-loop writes
the per-issue `decide-options-deposited-<ID>` form (`### Marker semantics`), so neither short-circuits
the other even when nested (`autodev` → `refine-to-ready-issue` → sub-loop) under a shared `run_dir`.
ENH-3075 unifies the name.

## Steps to Reproduce

1. Pick an issue whose `/ll:refine-issue --auto` pass deposits competing options and sets
   `decision_needed: true` (observed on BUG-3063).
2. `ll-loop run refine-to-ready-issue BUG-3063`
3. Observe the run reports `Loop completed: done` — a success terminal.
4. `ll-issues show 3063` — `History:` lists only `/ll:refine-issue, /ll:capture-issue`; no wire, no
   confidence scores.

Observed trace (`.loops/.history/2026-08-05T193536-refine-to-ready-issue/events.jsonl`):

```
resolve_issue → check_epic_id (no) → check_lifetime_limit (yes)
  → refine_issue → check_decision_mid_refine (yes) → done
```

## Current Behavior

Three gates exit via `done` on `decision_needed: true`:

| State | Location | Introduced by |
|-------|----------|---------------|
| `check_decision_mid_refine` | `scripts/little_loops/loops/refine-to-ready-issue.yaml:171-181` | BUG-2528 |
| `check_decision_mid_wire` | `scripts/little_loops/loops/refine-to-ready-issue.yaml:211-221` | BUG-2528 |
| `check_decision_needed` | `scripts/little_loops/loops/refine-to-ready-issue.yaml:369-378` | BUG-1366 |

Each was correct when `auto-refine-and-implement` invoked `refine-to-ready-issue` as a sub-loop.
That caller switched to `recursive-refine` (CHANGELOG.md:2697), and `recursive-refine` does not
resolve the decision — its own `check_decision_needed`
(`scripts/little_loops/loops/recursive-refine.yaml:556-568`) **skips the issue entirely**, appending
it to `recursive-refine-skipped-decision.txt`. Of the three `loop:` callers, only `autodev.yaml`
carries `run_decide` machinery on the post-return path.

Net effect: a `decision_needed` issue dead-ends on three of four invocation paths — direct run,
`recursive-refine`, and `issue-refinement` — and the operator must notice the truncated run and
invoke `/ll:decide-issue` by hand. Only the `autodev` path recovers (Summary caller table).

## Expected Behavior

`refine-to-ready-issue` resolves the decision inline and continues to wire + confidence, so a single
`ll-loop run refine-to-ready-issue <ID>` drives the issue to ready without operator intervention.

`/ll:decide-issue --auto` is fully autonomous — `skills/decide-issue/SKILL.md` documents `--auto` as
"Non-interactive mode: write decision without prompting" — and `rn-remediate.yaml:635` already calls
it inline as a plain `slash_command` state. There is precedent; nothing about the decision requires
a human.

Ordering must match `autodev`: decide **before** wire/confidence, so the confidence score is computed
against the resolved decision rather than the ambiguity the decision removes (`autodev` routes
`run_decide` → `rerun_confidence_after_decide`, `autodev.yaml:679`).

## Motivation

Two loops silently under-deliver on their stated contract. `refine-to-ready-issue`'s own description
is "Drives a single issue from backlog to ready-state" — it reports `done` having done roughly a
third of that. The failure is invisible: a success terminal, no warning, no skip ledger. The cost is
paid by the operator every time, and only if they happen to check `ll-issues show` afterward.

## Proposed Solution

### The naive fix is wrong

`check_decision_mid_refine.on_yes: run_decide` → `check_wire_done` reintroduces regressions this
repo has already paid for:

- **BUG-1416 / BUG-2595** — `decide-issue` silently no-ops when `## Proposed Solution` holds no
  enumerable options, leaving `decision_needed` armed. The issue then scores confidence against
  unresolved ambiguity, or reaches `/ll:manage-issue` Phase 2.3 and halts there with its failure
  misclassified.
- **ENH-2443** — which is precisely why `autodev` guards `run_decide` on *both* sides.

### The correct cluster (~5 states)

> **Superseded by `### The extraction boundary`** (added 2026-08-05, pre-implementation review).
> The sketch below undercounts: `record_options_deposited` routes through
> `check_open_question_progress` before returning to the probe, and an entry demultiplexer is
> needed for the fifth entry point. The authoritative state list is the 6-state + 2-terminal table
> in `### The extraction boundary`. Kept here for the per-state rationale.

Liftable near-verbatim from `autodev.yaml`:

| # | State | Source | Role |
|---|-------|--------|------|
| 1 | `check_decision_decidable` | `autodev.yaml:529-548` | Marker short-circuit, then `ll-issues check-open-questions \|\| ll-issues check-decidable` — deterministic non-LLM decidability probe. ENH-2446 chains open-questions first to catch the mixed case (resolved options + free-form open questions). |
| 2 | `deposit_options` | `autodev.yaml:550-565` | Bounded single retry via `/ll:refine-issue --auto` to deposit Option A/B/C blocks. |
| 3 | `record_options_deposited` | `autodev.yaml:567-573` | Write-once marker preventing infinite deposit↔decide cycles. |
| 4 | `run_decide` | `autodev.yaml:610-624` | `/ll:decide-issue --auto`, `pruning_profile: decide-issue-auto`. |
| 5 | `assert_decision_cleared` | `autodev.yaml:685-697` (BUG-2595) | Re-verify the flag *after* decide; still-armed means decide no-opped. |

All three `refine-to-ready-issue` gates retarget their `on_yes` to the cluster entry.

Step budget is fine: `max_steps: 30` (refine-to-ready-issue.yaml:31) against a ~12-state happy path.

### Decision needed: how to share the cluster

FSM fragments **cannot** express this. `scripts/little_loops/fsm/fragments.py` merges a named partial
state definition into exactly one state (module docstring lines 1-29; `_deep_merge` at line 43) — a
5-state cluster has no fragment representation. So:

**Option A — duplicate the cluster into `refine-to-ready-issue`.**
Smaller, self-contained, no `autodev` changes. Cost: two copies of a guard cluster whose every state
exists because of a distinct prior bug (BUG-1416, BUG-2595, ENH-2443, ENH-2446) — exactly the kind of
logic that must not drift. FEAT-937 (shared fragment libraries for cross-loop state reuse) exists
because this class of duplication is already recognized as a problem.

**Option B — extract as a sub-loop, and convert `autodev` to call it.**

> **Selected:** Option B — extract as a sub-loop — matches the proven `oracles/` sub-loop precedent (`verify-confidence-scores`) and eliminates the drift risk that duplication (Option A) has already caused once (BUG-1416/BUG-2595).

Invoke via a `loop:` state — the shape `confidence_check` already uses at
`refine-to-ready-issue.yaml:277-289` (`loop: oracles/verify-confidence-scores` with `with:` params).
Both loops call one implementation; drift is structurally impossible.

The seam is clean because the cluster core (probe → deposit → decide → assert) is caller-agnostic;
only **terminal routing** differs:

- `autodev` on failure → `record_decision_unresolved` (`autodev.yaml:700-724`), which defers the
  issue via `ll-issues set-status ... --reason decision_unresolved` and dequeues the next one.
- `refine-to-ready-issue` on failure → exit via `done`.

So the sub-loop should return success/failure and let each caller own its terminal routing. The
differing capture names (`autodev`'s `${captured.input.output}` vs `refine-to-ready-issue`'s
`${captured.issue_id.output}`) are already handled by sub-loop `with:` params.

**Recommendation: Option B.** The `autodev` conversion is the point, not incidental overhead — it is
what prevents a second copy of five bug-fix-derived guards from drifting out of sync.

### Decision Rationale

**Selected: Option B — extract as a sub-loop, and convert `autodev` to call it.**

Codebase evidence from two parallel `ll:codebase-pattern-finder` passes:

- **Option A (duplicate)** is mechanically consistent with the codebase's *current* de facto
  pattern — the same cluster is already duplicated between `autodev.yaml` and
  `rn-remediate.yaml`, with manual "parity" cross-reference comments. But that existing 2-copy
  duplication is the documented cause of a real shipped bug (BUG-1416, surfaced via BUG-2595) and
  two dedicated remediation issues (ENH-2443, ENH-2446). A third copy in
  `refine-to-ready-issue.yaml` extends a pattern the codebase has already had to patch around, not
  one it treats as safe.
- **Option B (sub-loop)**'s mechanism — `with:` params, `done`/`failed` terminal contract,
  `oracles/<name>` path resolution, caller-side `on_success`/`on_failure` routing — is not
  speculative; it is the exact pattern already running in production for `confidence_check` in
  `refine-to-ready-issue.yaml` (`loop: oracles/verify-confidence-scores`). `fsm/executor.py`'s
  `_execute_sub_loop` (~line 820) confirms full support for this contract. `fsm/fragments.py` was
  independently confirmed to have no construct for importing a multi-state cluster, ruling out a
  lighter-weight fragment-based alternative for either option.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — duplicate cluster | 1 | 2 | 2 | 1 | 6/12 |
| B — extract sub-loop | 3 | 2 | 1 | 1 | 7/12 |

Option B scores higher on Consistency — the deciding dimension per the tiebreaker rule — because
its sub-loop mechanics are a proven, already-precedented pattern, whereas Option A's duplication
is a pattern the codebase has already been burned by. Option B's lower Testability score reflects
real near-term cost: `scripts/tests/test_autodev_decision_gate.py` (1211 lines) asserts exact
inline state names and ordering for the cluster inside `autodev.yaml`, and extracting the cluster
into a sub-loop will require rewriting those assertions — a cost the issue's own "Behavior Parity"
table already scopes for, and one paid once rather than compounding with every future drift the
duplicated copy would risk.

_Amended 2026-08-05 (third review): Option B remains the selected end state, but it is now reached in
two steps — this issue authors the sub-loop and adopts it in `refine-to-ready-issue`; ENH-3075
converts `autodev` and pays the test-rewrite cost priced in above. Between the two, the cluster is
briefly duplicated — the very thing Option B rejects. That is a deliberate, time-boxed transition
(`## Scope`), not a reversal to Option A: Option A's duplication is permanent and unowned, whereas
this one has a filed owner and a defined end._

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — **new**; the extracted decision
  cluster.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — retarget the three `decision_needed`
  gates' `on_yes` from `done` to three new `loop:` call states; add `record_decision_unresolved`;
  raise `max_steps`.
- ~~`scripts/little_loops/loops/autodev.yaml`~~ — **deferred to ENH-3075** (`## Scope`). Untouched by
  this issue; it keeps its inline cluster until then.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:4-23` — the file's own header comment is an
  ASCII "Routing summary" diagram that explicitly shows `check_decision_needed → (on_yes) done`;
  must be updated in the same edit as the state retargeting or it becomes stale documentation
  embedded in the primary file itself.
- `scripts/little_loops/loops/autodev.yaml:1236` (`triage_outcome_failure` state) — _the binding is
  ENH-3075's work; the sub-loop must still be **authored** to accommodate it here, since retrofitting
  an entry demultiplexer later would change the sub-loop's `initial:` state._ A **fifth**
  entry point into the decision cluster, distinct from the four already covered by the Behavior
  Parity table below: it routes directly to `run_decide`, bypassing `check_decision_decidable`
  entirely (predicate is `score_ambiguity ≤ 10 OR decision_needed`, not the deterministic
  `ll-issues check-decidable` gate the other four entry points use). A `loop:` state has exactly one
  `initial:` entry point, so if the new sub-loop's `initial` is `check_decision_decidable` (matching
  the other four callers), `triage_outcome_failure` cannot delegate to it without either being
  retargeted to route through `check_decision_decidable` first (a behavior change) or the sub-loop
  exposing a context-gated skip-to-`run_decide` branch. This must be resolved explicitly during
  extraction, not left implicit. **Resolved 2026-08-05 (pre-implementation review)** — see
  `### Fifth entry point (resolved)`: a `route_entry` demultiplexer plus a `skip_probe` parameter,
  no behavior change at any of the five sites.

### The extraction boundary

_Added 2026-08-05 (pre-implementation review). The prior Behavior Parity table assigned
`assert_decision_cleared` to the sub-loop while leaving `rerun_confidence_after_decide` and
`recheck_after_decide` caller-side. That split is **topologically impossible**: the actual chain in
`autodev.yaml` is_

```
run_decide → mark_decide_ran → rerun_confidence_after_decide → recheck_after_decide → assert_decision_cleared
```

_`assert_decision_cleared` (`:685`) is reachable only **through** the two states the table left
caller-side. The boundary below resolves this before implementation rather than during it._

**Sub-loop body (6 states + 2 terminals):**

| # | State | Source | Note |
|---|---|---|---|
| 0 | `route_entry` | new | Entry demultiplexer — see `### Fifth entry point` below |
| 1 | `check_decision_decidable` | `autodev.yaml:529-548` | Marker short-circuit → `check-open-questions \|\| check-decidable` |
| 2 | `deposit_options` | `autodev.yaml:550-565` | Bounded single retry via `/ll:refine-issue --auto`. Carries `on_partial: record_options_deposited` (`:564`) alongside `on_yes`/`on_no`/`on_error` — carry all four; `on_partial` is easy to drop in a hand-move and nothing else re-creates it. |
| 3 | `record_options_deposited` | `autodev.yaml:567-573` | Write-once marker (per-issue name — see `### Marker semantics`) |
| 4 | `check_open_question_progress` | `autodev.yaml:579-608` | `fragment: open_question_stall_gate` |
| 5 | `run_decide` | `autodev.yaml:610-624` | `/ll:decide-issue --auto`, `pruning_profile: decide-issue-auto` |
| 6 | `assert_decision_cleared` | `autodev.yaml:685-697` (BUG-2595) | Moved to sit **directly after** `run_decide` |
| T | `done` / `failed` | new | `done` = flag cleared; `failed` = still armed |

**Stays caller-side (autodev):** `mark_decide_ran`, `rerun_confidence_after_decide`,
`recheck_after_decide`, `record_decision_unresolved`, and the four/five entry gates.

**The sub-loop must declare `import: - lib/common.yaml`.** _(Added 2026-08-05, second
pre-implementation review.)_ Every moved state uses a fragment defined there — `shell_exit`
(`lib/common.yaml:15`), `with_rate_limit_handling` (`:74`), `open_question_stall_gate` (`:196`) —
but the structural template this issue names, `oracles/verify-confidence-scores.yaml`, uses **no
fragments and therefore has no `import:` block**. Following it verbatim produces a loop that fails
to load with `Fragment library not found`. Resolution from `loops/oracles/` does work:
`fsm/fragments.py:95-104` tries `loop_dir / import_path` first (i.e. a `lib/common.yaml` *inside*
the `oracles/` dir — which does not exist, so it misses) and falls back to
`_BUILTIN_LOOPS_DIR / import_path` (a hit), so the plain
`import: - lib/common.yaml` form is correct — no `../` prefix. Precedent for `import:` inside
`oracles/`: `enumerate-and-prove.yaml:28`, `generator-evaluator.yaml:45`,
`research-coverage.yaml:34`, `plan-node-refine.yaml:50`.

**Rewrite every `${captured.input.output}` to `${context.issue_id}`.** All six moved states read the
issue ID from `autodev`'s capture, which does not exist in the child. This includes the one inside a
shell body — `check_open_question_progress`'s `ID="${captured.input.output}"` (`autodev.yaml:~584`) —
easy to miss because it reads like shell rather than a routing field. The oracle convention is that
internal state bodies read `${context.issue_id}` and never `${captured...}`
(`verify-confidence-scores.yaml`).

**Declare `max_steps` and `timeout` on the sub-loop.** Nothing is inherited from the parent — an
undeclared `max_steps` takes the schema default of 50 (`fsm/schema.py:1279`). The cluster's worst
case is one deposit↔decide detour (~8 state visits), so an explicit `max_steps: 20` plus a `timeout:`
sized for two slash-command states is ample and documents the bound. No `scope:` or `singleton:` is
needed — the child runs inside the parent's lock.

**Deliberate reorder:** today `assert_decision_cleared` fires *after* re-scoring
(`rerun_confidence_after_decide` → `recheck_after_decide`); post-extraction it fires immediately
after `run_decide`. On the score-passing branch this is a **tightening** — BUG-2595 exists to catch
`decide-issue` silently no-opping, and checking the flag closer to the decide call detects that
strictly sooner. The re-score states remain caller-side and still run, just after the assert.

_Corrected 2026-08-05 (third pre-implementation review): the reorder is **not** purely a tightening._
`recheck_after_decide.on_no: snap_and_size_review` (`autodev.yaml:684`) **bypasses
`assert_decision_cleared` entirely**, so today an issue with a still-armed flag *and* failing scores
goes to size review — ENH-1415's "on failure, route to snap_and_size_review rather than dropping the
issue." Post-extraction the assert fires first and that case returns `failed` → deferred, never
reaching `snap_and_size_review`.

This only bites on the `autodev` path — `refine-to-ready-issue` has no `snap_and_size_review`
equivalent downstream of a decide, so nothing is lost here. **Deferred to ENH-3075**, which must
either record it in the Behavior Parity table as accepted or add a caller-side branch off
`on_failure` that routes to `snap_and_size_review` when scores are below threshold.

**`check_decision_after_decide_error` collapses into `assert_decision_cleared`.** ENH-2717's
short-circuit (`run_decide.on_error` → check flag → still armed → `record_decision_unresolved`) is
behaviorally identical to routing `run_decide.on_error → assert_decision_cleared` inside the
sub-loop, since `assert_decision_cleared` performs the same `ll-issues check-flag` and its `on_yes`
now reaches the `failed` terminal (which the caller routes to `record_decision_unresolved`). One
difference must be accepted explicitly: today `check_decision_after_decide_error.on_no` skips
`mark_decide_ran` and jumps to `recheck_after_decide`; post-extraction a decide that errored but
*did* clear the flag returns `done` and the caller runs `mark_decide_ran` normally. That is
arguably more correct (decide did run), and the `autodev-decide-ran` marker's only consumer
(`decide_current`'s short-circuit) is safe either way. The caller-side
`check_decision_after_decide_error` state is **deleted**, and its tests with it.

### Behavior Parity

Every behavior below must survive the move — each exists because of a named prior bug.

_Scope note (2026-08-05, third review): rows marked `autodev` describe states that **stay where they
are** for this issue — `autodev.yaml` is untouched here (`## Scope`). They are listed so the sub-loop
is authored to the right boundary; ENH-3075 is what actually moves the `autodev` side._

| Behavior (autodev.yaml) | Artifact | Status |
|---|---|---|
| Marker short-circuit skips re-validation once options were deposited (`:539-542`) | sub-loop | Preserved |
| `check-open-questions \|\| check-decidable` probe order (ENH-2446, `:543-544`) | sub-loop | Preserved |
| `deposit_options` bounded single retry via `/ll:refine-issue --auto` (`:550-565`) | sub-loop | Preserved |
| Write-once options-deposited marker (`:567-573`) | sub-loop | **Changed** — marker stays in the inherited parent `run_dir` but gets a **per-issue name**; see `### Marker semantics` |
| `check_open_question_progress` stall gate (ENH-2446, `:579-608`) | sub-loop | **Corrected** — only the *write* path is per-issue; the evaluator reads a different file and the gate is inert today. See `### Open-question stall gate is inert (pre-existing)` |
| `run_decide` `/ll:decide-issue --auto` + `decide-issue-auto` pruning profile (`:610-624`) | sub-loop | Preserved |
| `assert_decision_cleared` post-decide flag re-verify (BUG-2595, `:685-697`) | sub-loop | **Reordered** — now directly after `run_decide`; see `### The extraction boundary` |
| `check_decision_after_decide_error` short-circuit on still-armed flag (ENH-2717, `:627-640`) | — | **Deleted** — collapses into `assert_decision_cleared`; documented equivalence + one accepted difference above |
| `mark_decide_ran` → `autodev-decide-ran` marker consumed by `decide_current` (ENH-1415) | autodev | Preserved — autodev-specific queue state, not part of the cluster contract |
| `record_decision_unresolved` defer + `DECISION_UNRESOLVED` ledger (`:700-724`) | autodev | Preserved — caller-side routing off the sub-loop's `failed` terminal; `auto-refine-and-implement.yaml:840` reads this ledger |
| `rerun_confidence_after_decide` re-score after decide (`:650-667`) | autodev | Preserved — caller-side, now downstream of the assert |
| `recheck_after_decide` threshold re-check + `autodev-staged.txt` (`:669-685`) | autodev | Preserved — caller-side; irreducibly autodev-specific (reads `${context.readiness_threshold}`, routes `on_no: snap_and_size_review`) |
| `deposit_options`'s `on_partial: record_options_deposited` (`:564`) | sub-loop | Preserved — carry all four routes, not just `on_yes`/`on_no`/`on_error` |
| `fragment: with_rate_limit_handling` / `on_rate_limit_exhausted` on `run_decide` + `deposit_options` | sub-loop | **Changed** — routes to `failed`, and cannot propagate to the caller at all; see `### Rate-limit exhaustion` |
| `triage_outcome_failure` (`autodev.yaml:1236`) bypasses `check_decision_decidable` | sub-loop | **Resolved** — `route_entry` + `skip_probe` param exist in the sub-loop; the `autodev` binding lands with ENH-3075. See `### Fifth entry point` |
| `recheck_after_decide.on_no → snap_and_size_review` bypasses the flag check (`:684`, ENH-1415) | autodev | **Changes under ENH-3075** — the assert reorder removes this escape; see `### The extraction boundary` |

### Marker semantics (corrected)

_Added 2026-08-05 (pre-implementation review). The prior text stated twice that the marker "must
move to the sub-loop's `run_dir`". **That is backwards.**_ `executor.py:890-891` explicitly
re-injects the parent's `run_dir` into the child on the `with:` binding path:

```python
if "run_dir" in self.fsm.context:
    child_fsm.context.setdefault("run_dir", self.fsm.context["run_dir"])
```

The child therefore **inherits the parent's `run_dir`**, which is load-bearing for a different reason
than the prior text gave. `autodev.yaml`'s `dequeue_next` clears `autodev-decide-ran` and
`autodev-decide-options-deposited` **by exact name** (`:104-105`).

_Corrected 2026-08-05 (third pre-implementation review): the prior text said a differently-named
marker would "silently disable ENH-2443's write-once bound." **That is inverted.** The write-once
bound comes from the marker's **presence** — `check_decision_decidable`'s `[ -f ... ] && exit 0`
short-circuit. `dequeue_next`'s `rm -f` is what **releases** the bound so a **re-dequeued** issue can
retry `deposit_options` in the same run. A marker the clear misses is over-bound (deposit never
retries), not unbounded._

The inverse hazard is real and is why the marker name must change:
`recursive-refine.yaml:231` calls with `context_passthrough: true`, sharing one `run_dir` across a
**multi-issue queue**, with nothing clearing the marker between issues. A single flat marker name
would make issue #2 onward find the marker already set and skip `deposit_options` entirely.

**Requirement:** keep `${context.run_dir}` (inherited — do not create a sub-loop-local dir), and
make the marker name per-issue, e.g. `${context.run_dir}/decide-options-deposited-${context.issue_id}`,
following `check_open_question_progress`'s existing `.open_questions_${ID}.history` write path
(but see `### Open-question stall gate is inert` — that precedent is only half-implemented).

**Rename sweep — deferred to ENH-3075.** The marker name `autodev-decide-options-deposited` appears
at three functional sites in `autodev.yaml` (`check_decision_decidable`'s read `:540`,
`record_options_deposited`'s write `:573`, `dequeue_next`'s clear `:105`), plus stale non-functional
references in `rn-remediate.yaml`, both test files, and `LOOPS_REFERENCE.md`. Because this issue
leaves `autodev.yaml` untouched (`## Scope`), none of that moves here — `autodev` keeps its flat
marker, the new sub-loop writes the per-issue one, and the two do not collide.

ENH-3075 owns the unification, including a `dequeue_next` trap worth knowing about now: at the point
of the `rm -f`, `capture: input` has not yet been written, so `${captured.input.output}` still holds
the **previous** iteration's ID. The only correct ID in scope is the shell-local `$CURRENT`
(`autodev.yaml:94`), escaped `$${CURRENT}`.

### Open-question stall gate is inert (pre-existing)

_Added 2026-08-05 (second pre-implementation review). This corrects the Behavior Parity row above._

`check_open_question_progress` (`autodev.yaml:579-608`) writes its count history to
`$${RUN_DIR}/.open_questions_$${ID}.history` — per-issue — but declares **no
`evaluate.history_file`**. The evaluator therefore falls back to its default,
`${context.run_dir}/.open_questions_history` (`fsm/evaluators.py:1958`), a flat path **nothing
writes**. `evaluate_open_question_stall` on a missing/empty file takes the `len(counts) < 2`
branch and returns `yes` with `rounds: 0` (`fsm/evaluators.py:800-828`).

Consequence: ENH-2446's stall gate **never fires**. It unconditionally routes
`on_yes: check_decision_decidable`, and the only thing bounding the deposit↔decide detour is the
options-deposited marker's `exit 0` short-circuit. This is a pre-existing defect, not one this
refactor introduces — but the extraction copies the state verbatim and the parity table above
previously asserted the behavior was preserved, so it must be handled deliberately.

**Requirement:** the sub-loop's `check_open_question_progress` declares the read path explicitly and
per-issue, matching its write path:

```yaml
    fragment: open_question_stall_gate
    evaluate:
      history_file: "${context.run_dir}/.open_questions_${context.issue_id}.history"
```

(`evaluate:` keys merge over the fragment's `evaluate.type` / `max_stall`.) Fixing it during
extraction is preferred — it is a two-line change that makes the gate actually work and closes the
same cross-issue leakage hazard `### Marker semantics` closes for the marker. If instead the
decision is to preserve today's inert behavior bit-for-bit, say so explicitly in the sub-loop's
comment and file a follow-up; do not leave it ambiguous.

### Rate-limit exhaustion (must not exit `done`)

_Added 2026-08-05 (pre-implementation review); **corrected 2026-08-05, third review** — the original
resolution named a propagation mechanism that does not exist._

`deposit_options` (`:565`) and `run_decide` (`:624`) both carry `on_rate_limit_exhausted: done`.
Inside `autodev` today that terminates the **entire** autodev run. Post-extraction it would terminate
only the child, on a **success terminal** — so the caller reads `on_success` and proceeds with
`decision_needed` still armed, hitting exactly the `/ll:manage-issue` Phase 2.3 halt that BUG-2595
exists to prevent.

**Requirement (unchanged):** inside the sub-loop, `on_rate_limit_exhausted` must route to the
`failed` terminal (or a distinct terminal whose name is in `FAILURE_TERMINAL_NAMES` / sets
`failure: true`), never `done`.

**Corrected:** the prior text then said "each caller re-expresses rate-limit escalation on its own
`loop:` state via `on_rate_limit_exhausted` / `fragment: with_rate_limit_handling` — the shape
`autodev.yaml:385` and `recursive-refine.yaml:231` already use." **That mechanism cannot fire on a
`loop:` state:**

- `_execute_sub_loop` (`scripts/little_loops/fsm/executor.py:1058-1086`) returns a routing target
  directly from `child_result.terminated_by`; it never produces an `ActionResult`.
- The 429 interception at `executor.py:1673-1685` is gated on `action_result is not None` **and**
  `exit_code != 0`, so a `loop:` state is never classified as rate-limited.
- The child's exit is also indistinguishable after the fact: `captured.<state>.terminated_by` is
  `"terminal"` for every terminal exit, and `captured.<state>.failure_terminal` is a **bool**
  (`fsm/types.py:60`, set at `executor.py:3206`) — **not** the terminal's name — so declaring a
  distinct `rate_limited` failure terminal in the child buys the parent nothing.

(`recursive-refine.yaml:236`'s existing `on_rate_limit_exhausted: dequeue_next` on its
`refine-to-ready-issue` `loop:` state is dead config for the same reason. Pre-existing, out of scope,
worth a comment where noticed.)

**Consequence for this issue:** a 429 that exhausts the budget inside the sub-loop returns `failed`,
which `refine-to-ready-issue` routes to its new `record_decision_unresolved` → the issue is deferred
with `--reason decision_unresolved`. That is a *misattribution* — the decision was never attempted,
not attempted-and-unresolved — but it is safe: the issue is deferred rather than advanced with an
armed flag, and the deferral is visible in the ledger.

**Requirement:** accept that misattribution for now and say so in `record_decision_unresolved`'s
comment. Do **not** add an `on_rate_limit_exhausted` route to the `loop:` call states — it would read
as working and silently never fire.

The full fix (a `${context.run_dir}/decide-rate-limited-${issue_id}` marker written by the sub-loop
before it exits `failed`, which callers check on `on_failure`) belongs with ENH-3075, because it only
changes an outcome on the `autodev` path — there, today's `on_rate_limit_exhausted: done` gracefully
ends the whole run, and losing that would walk the entire queue into deferral one 429 at a time.
`refine-to-ready-issue` has no equivalent behavior to lose.

### Fifth entry point (resolved)

_Added 2026-08-05 (pre-implementation review); previously "Open — must be designed"._
`triage_outcome_failure` (`autodev.yaml:1236`) routes straight to `run_decide`, bypassing the
decidability probe, because its predicate is `score_ambiguity ≤ 10 OR decision_needed` — it may
fire on an issue whose `decision_needed` is false, where `check-decidable` is not the right gate.
An FSM `loop:` state has exactly one `initial:` entry, so:

**Resolution:** the sub-loop declares an optional `skip_probe` parameter and an entry
demultiplexer as its `initial:` state.

```yaml
parameters:
  issue_id: {type: string, required: true}
  skip_probe: {type: string, required: false, default: "false"}
initial: route_entry
```

`route_entry` is a `fragment: shell_exit` state on `[ "${context.skip_probe}" = "true" ]` →
`on_yes: run_decide`, `on_no: check_decision_decidable`. The four probe-first entry points bind
nothing extra; `triage_outcome_failure` binds `with: {issue_id: ..., skip_probe: "true"}`. No
behavior change at any of the five sites.

Note `_validate_with_bindings` (`fsm/validation/structural_rules.py:~258`) is ERROR-severity, so
`skip_probe` **must** be declared in `parameters:` for the `triage_outcome_failure` binding to load.

### Three gates need three call states (resolved)

_Added 2026-08-05 (second pre-implementation review); previously stated as "retarget all three gates'
`on_yes` to **the** sub-loop call state" — singular, which is topologically impossible._

An FSM `loop:` state has exactly one `on_success` / `on_failure` pair, but the three gates resume at
three different points in the chain:

| Gate | Line | `on_no` (unchanged) | Post-decide `on_success` must be |
|---|---|---|---|
| `check_decision_mid_refine` | `:171-181` | `check_wire_done` | `check_wire_done` — resume the chain |
| `check_decision_mid_wire` | `:211-221` | `verify_issue` | `verify_issue` — resume the chain |
| `check_decision_needed` | `:369-378` | `check_missing_artifacts` | **`confidence_check`** — re-score, *not* the `on_no` target |

**Resolution:** add **three** `loop:` states (e.g. `resolve_decision_mid_refine`,
`resolve_decision_mid_wire`, `resolve_decision_pre_breakdown`), each binding
`with: {issue_id: "${captured.issue_id.output}"}` and each routing `on_failure` to the shared
`record_decision_unresolved` (see the `failed`-terminal section below). Only their `on_success`
targets differ. Three near-identical call states is the cost of the engine's one-entry/one-exit
sub-loop contract; the *body* is still shared, which is the point of Option B.

**Why gate 3 is not symmetric.** `check_decision_needed` sits on the **outcome-failure** path
(`check_outcome.on_no → check_decision_needed`), where the low score is caused by the very ambiguity
the decision removes. Routing its `on_success` to `check_missing_artifacts` would carry the stale
pre-decision score into size-review — exactly the failure `autodev` avoids with
`run_decide → rerun_confidence_after_decide` (`autodev.yaml:650-667`), and exactly what
`## Expected Behavior`'s "decide **before** wire/confidence" ordering requires. It must route back to
`confidence_check`.

**The resulting cycle is bounded, but tighten the budget.** Gate 3's re-entry closes a loop:
`confidence_check → check_readiness → check_outcome → check_decision_needed →
resolve_decision_pre_breakdown → confidence_check`. It cannot spin, because the second pass through
`check_decision_needed` sees `decision_needed: false` (the sub-loop's `done` terminal asserts exactly
that via `assert_decision_cleared`) and falls through `on_no` to `check_missing_artifacts`; a decide
that failed to clear the flag returns `failed`, not `done`, and exits via
`record_decision_unresolved`. One extra traversal costs ~6 steps against `max_steps: 30`
(`refine-to-ready-issue.yaml:31`), whose ENH-3031 note already budgets ~22 worst case — that leaves
almost no headroom. **Raise `max_steps` to 40 as part of this change** and update the ENH-3031
rationale comment to account for the decide-then-rescore traversal.

### Caller interaction after the fix

_Added 2026-08-05 (pre-implementation review)._ Because `refine-to-ready-issue` will now resolve
decisions inline, and `autodev.yaml:385` (`refine_current`) calls `refine-to-ready-issue`, autodev
gains a second, nested route into the decision cluster. Consequences to design for:

- `autodev`'s `check_decision_after_refine` (`:~484`) becomes largely dead on the post-refine path —
  the child already cleared the flag. Keep it (its own comment already frames it as defense in
  depth), but do not treat it as the primary resolution path any more.
- `mark_decide_ran` is caller-side, so a decide performed **inside** the child does not set
  `autodev-decide-ran`. If `recheck_after_size_review` later routes back to `decide_current`, its
  ENH-1415 short-circuit will not fire and decide could run a second time. The
  `assert_decision_cleared`/`check-decidable` guards make a second run a no-op rather than a
  correctness bug, but confirm this during implementation — or have the sub-loop write the
  `autodev-decide-ran` marker itself (inherited `run_dir` makes this possible).
- No infinite nesting risk: `refine-to-ready-issue` → decision sub-loop is a leaf; the decision
  sub-loop never calls back into `refine-to-ready-issue`. There is no depth cap in `executor.py`
  (`_depth` at `:409` is used only for event forwarding), so this must be verified by inspection,
  not relied on as an engine guarantee.

### `refine-to-ready-issue`'s handling of the `failed` terminal (resolved)

_Added 2026-08-05 (pre-implementation review); previously unspecified._ Routing the sub-loop's
`failed` terminal to `done` would reproduce exactly the silent-success bug this issue exists to fix.

**Resolution:** `refine-to-ready-issue` routes the sub-loop's `on_failure` to a new
`record_decision_unresolved` state that mirrors `autodev.yaml:700-724` — writes the
`DECISION_UNRESOLVED` ledger entry and defers the issue via
`ll-issues set-status ... --reason decision_unresolved` — then exits via its **existing `failed`
terminal** (`refine-to-ready-issue.yaml:638`), not `done`.

This deliberately flips the outcome its callers observe:

| Caller | `on_failure` target | Effect |
|---|---|---|
| `autodev.yaml:385` | `skip_inflight` | Issue skipped as an inflight failure — but the ledger entry is already written, so `auto-refine-and-implement.yaml:840` still sees it |
| `recursive-refine.yaml:231` | `gate_recursion` | Replaces today's silent `check_decision_needed` skip with an explicit deferral + ledger entry |
| `issue-refinement.yaml:29-33` | (verify it declares one) | Must be checked — an undeclared `on_failure` falls through per `schema.py`'s `on_no = on_no or on_failure` |

Writing the ledger inside `refine-to-ready-issue` rather than relying on each caller is what keeps
`auto-refine-and-implement.yaml:840`'s `DECISION_UNRESOLVED` contract intact across all four
invocation paths.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — consumes autodev's
  `DECISION_UNRESOLVED` ledger (line 840); must keep working after the autodev refactor.
- `scripts/little_loops/loops/rn-remediate.yaml:635` — independent inline `/ll:decide-issue` call;
  a candidate future consumer, out of scope here.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/scan-and-implement.yaml:77` — calls `loop: autodev` with
  `with: {input: "${captured.input.output}"}`; the sub-loop terminal contract change inside
  `autodev.yaml` must not alter what this call site observes as `on_success`/`on_failure`.
- `scripts/little_loops/loops/recursive-refine.yaml:231` — calls `loop: refine-to-ready-issue` with
  `context_passthrough: true`; today this call effectively dead-ends the same way BUG-3065 describes
  (see `## Similar Patterns` below) — once `refine-to-ready-issue` resolves the decision inline,
  issues reaching `recursive-refine` via this path will progress further than before, so its
  post-sub-loop routing needs re-verifying, not just `refine-to-ready-issue`'s own routing.
- `scripts/little_loops/loops/autodev.yaml:385` (`refine_current` state) — also calls
  `loop: refine-to-ready-issue`. Because `autodev.yaml` will *also* own the new decision-cluster
  sub-loop, this is a same-file self-reference risk: confirm `refine_current`'s call into
  `refine-to-ready-issue` (which now itself calls the decision-cluster sub-loop) cannot re-enter
  `autodev`'s own decision-cluster invocation and cycle.
- `scripts/little_loops/loops/issue-refinement.yaml:29-33` — calls `loop: refine-to-ready-issue` with
  `context_passthrough: true`; same downstream-behavior-change consideration as `recursive-refine.yaml`
  above.
- `scripts/little_loops/loops/rn-remediate.yaml` (lines ~275-370, ~633-741, ~784-955) — a **third**,
  independent inline copy of the same decision-resolution state shape
  (`check_decision_decidable`, `deposit_options`, `record_options_deposited`,
  `check_open_question_progress`, `decide`), cross-referenced by a "parity insertion mirroring
  rn-remediate" comment in `autodev.yaml`'s `check_decision_decidable` docstring. Confirms the
  Decision Rationale's drift concern is not hypothetical — a second live duplicate already exists
  beyond the one being extracted. Still out of scope for this issue (per the existing entry above),
  but the Option B sub-loop is now a candidate future consumer for two callers, not one.

### Similar Patterns

- `scripts/little_loops/loops/recursive-refine.yaml:556-568` — same dead-end, skips instead of
  resolving. **Follow-up, not a requirement of this issue.**

### Tests

- TBD — identify the loop-validation/topology tests covering `refine-to-ready-issue` and `autodev`
  routing; `ll-loop validate` must pass for both after the change.

_Wiring pass added by `/ll:wire-issue`:_

**Existing coverage on `refine-to-ready-issue.yaml` (contrary to "no test exists" — one does):**
- `scripts/tests/test_builtin_loops.py:1242` `class TestRefineToReadyIssueSubLoop` — loads
  `refine-to-ready-issue.yaml` directly and asserts on all three `decision_needed` gates:
  - `test_check_decision_mid_refine_on_yes_routes_to_done` (line 2053) — asserts `on_yes == "done"`,
    **will break**, update to assert the new sub-loop/cluster target.
  - `test_check_decision_mid_wire_on_yes_routes_to_done` (line 2102) — same, **will break**.
  - `check_decision_needed.on_yes` — **no existing assertion** (only `on_no`, line 1958-1965) — new
    coverage to add, not a break.

**Nothing in `test_autodev_decision_gate.py` or the `autodev` classes in `test_builtin_loops.py`
breaks under this issue** — `autodev.yaml` is untouched, so every assertion on its inline cluster
state names still holds. _(Re-scoped 2026-08-05, third review; the ~25 assertions that break under
the `autodev` conversion are enumerated in ENH-3075's `### Tests`.)_ This is the bulk of what the
split buys: the test surface here is `TestRefineToReadyIssueSubLoop` plus new oracle-internals tests.

**Regression guard that auto-covers the new wiring with no new test needed:**
- `scripts/tests/test_builtin_loops.py:12944-12979` `class TestBuiltinLoopReferencesResolve` —
  `test_all_static_loop_references_resolve` (~12963) iterates every runnable builtin loop and fails
  if any `loop:` target doesn't resolve; docstring explicitly cites this exact failure class (a bare
  `verify-confidence-scores` reference missing its `oracles/` prefix). Will automatically exercise
  the new `loop: oracles/<name>` references in both `autodev.yaml` and `refine-to-ready-issue.yaml`.
- `test_builtin_loops.py:29-38` `class TestBuiltinLoopFiles` (recursive `rglob("*.yaml")`, so it
  picks up the new `oracles/` file automatically) — `test_all_parse_as_yaml`,
  `test_all_validate_as_valid_fsm`, `test_no_failure_edge_routes_to_a_success_terminal` all cover the
  new sub-loop file with zero new test code required, satisfying "`ll-loop validate` must pass" above.

**New coverage required by the 2026-08-05 pre-implementation review** (none of this exists today):
- `route_entry` demultiplexer: assert `skip_probe: "true"` routes to `run_decide` and the default
  routes to `check_decision_decidable`. _(The companion assertion — that `triage_outcome_failure`
  binds `skip_probe: "true"` and the other four entry points do not — belongs to ENH-3075, which
  adds those bindings.)_
- Rate-limit terminal: assert neither `deposit_options` nor `run_decide` in the sub-loop declares
  `on_rate_limit_exhausted: done` — the regression guard for the false-success hazard. Assert too
  that no `loop:` call state in `refine-to-ready-issue.yaml` declares `on_rate_limit_exhausted`,
  since it can never fire there and would read as working (`### Rate-limit exhaustion`).
- `deposit_options` carries `on_partial: record_options_deposited` — the guard against dropping the
  fourth route in a hand-move.
- Marker name: assert the sub-loop's options-deposited marker path interpolates
  `${context.issue_id}`. This is the only automated defense against the `recursive-refine`
  cross-issue leakage described in `### Marker semantics`. _(The matching `autodev` `dequeue_next`
  assertion lands with ENH-3075.)_
- `refine-to-ready-issue`'s new `record_decision_unresolved` → `failed` routing, and that none of
  the three gates' `on_yes` still equals `"done"`.

**Further new coverage required by the 2026-08-05 second pre-implementation review:**
- Three-call-state fan-out: assert each gate's `on_yes` resolves to a distinct `loop:` state, that
  all three carry `loop: oracles/<name>`, and — the load-bearing one — that
  `check_decision_needed`'s call state has `on_success: confidence_check` (not
  `check_missing_artifacts`). That single assertion is the regression guard for the
  "decide before confidence" ordering `## Expected Behavior` requires; nothing else enforces it.
- Sub-loop fragment resolution: the existing `TestBuiltinLoopFiles.test_all_validate_as_valid_fsm`
  already fails loudly on a missing `import: - lib/common.yaml`, so no new test is needed — but
  confirm it actually runs against `oracles/` (it does; the class uses recursive `rglob`).
- No `${captured.` substring anywhere in the new sub-loop file — a cheap, exact guard against the
  `check_open_question_progress` shell-heredoc miss described in `### The extraction boundary`.
- `check_open_question_progress` declares an `evaluate.history_file` interpolating
  `${context.issue_id}` — guards both the inert-gate fix and cross-issue leakage
  (`### Open-question stall gate is inert`).
- `refine-to-ready-issue.yaml`'s `max_steps` is ≥ 40 (the gate-3 rescore traversal no longer fits in
  30).

**Templates to follow for new/rewritten tests** (both already used together in `test_builtin_loops.py`):
- Sub-loop-reference assertion template: `test_confidence_check_delegates_to_verify_confidence_scores_oracle`
  (lines 1252-1264) — asserts `confidence_check.get("loop") == "oracles/verify-confidence-scores"` and
  `on_success`/`on_error` targets. Use for asserting the new decision-cluster entry state's `loop:`
  reference in both callers.
- Child-loop-internals template: `test_verify_scores_persisted_on_yes_routes_to_check_readiness` /
  `..._on_no_routes_to_retry_confidence_check` (lines 1289-1308) — loads the oracle file directly via
  `yaml.safe_load((BUILTIN_LOOPS_DIR / "oracles" / "<name>.yaml").read_text())` and asserts internal
  routing. Use for the 9 moved states' internal topology.

**No end-to-end coverage exists or is expected**: no test in the suite runs `ll-loop run
refine-to-ready-issue` or `ll-loop run autodev` live (grepped, no hits) — all coverage above is
structural/static (YAML-load + dict-lookup on `on_yes`/`on_no`/`on_error`/`action`/`fragment`), so
the Implementation Steps' step 5 manual re-run (`ll-loop run refine-to-ready-issue BUG-3063`) remains
the only behavioral verification and cannot be replaced by an existing automated test.

### Documentation

- `CHANGELOG.md`
- TBD — check whether `docs/` documents the decision-gate handoff contract.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:79-80` — catalog-table rows for `refine-to-ready-issue` and
  `oracles/verify-confidence-scores`; add a parallel row for the new decision-cluster sub-loop
  following the existing convention.
_The four `autodev`-describing entries below are **deferred to ENH-3075** — `autodev.yaml` is
unchanged here, so its diagrams and prose stay accurate. Listed for traceability:_
`LOOPS_REFERENCE.md:1000-1045` (FSM-flow diagram), `:1047` ("Diagram omissions"), `:1053`
("Outcome failure triage"), `:1055` ("Decidability gate parity" — already inaccurate against
`triage_outcome_failure`'s direct route, pre-existing).
- `docs/guides/LOOPS_REFERENCE.md:140` — `refine-to-ready-issue` "Claim-verification gate chain"
  section documents the three decision gates' current `on_yes: done` exit; update once retargeted.
- `docs/reference/CLI.md` and `docs/reference/API.md` — both matched a grep for `run_decide`/
  `check-decidable`/`decide-issue` CLI surfaces the cluster's actions invoke; not confirmed
  line-by-line, worth a pass to check for anchor prose naming `autodev.yaml`'s `run_decide` state
  specifically (would go stale if so).

### Configuration

- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- `scripts/tests/test_autodev_decision_gate.py` (1211 lines, loads `autodev.yaml` directly via `_load_autodev_yaml()`, line 31-33) makes real `data["states"][...]` structural assertions against only 6 of the 12 inline cluster states: `check_decision_at_dequeue`, `check_decision_before_size_review`, `assert_decision_cleared`, `check_decision_after_decide_error`, plus `on_yes`/`on_error` target-string assertions on `check_decision_decidable`, `run_decide`, and `recheck_after_decide`. The other 6 inline states — `deposit_options`, `record_options_deposited`, `check_open_question_progress`, `mark_decide_ran`, `rerun_confidence_after_decide`, `snap_and_size_review` — appear only in comments/docstrings, with no structural assertion on their existence, action, or routing. Two routing-behavior test classes (`TestCheckDecisionAtDequeueRouting` ~203-280, `TestAssertDecisionClearedRouting` ~1138-1211) build their own minimal fixture FSMs rather than loading `autodev.yaml`, so they assert on `visited` state-name lists independent of the real file and would need updating regardless of extraction approach.

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- The `autodev.yaml` decision cluster is larger than the Proposed Solution's 5-state table: `record_options_deposited`'s `next` routes through `check_open_question_progress` (`autodev.yaml:580-608`, `fragment: open_question_stall_gate`, writes `.open_questions_${ID}.history` under `${context.run_dir}`) before returning to `check_decision_decidable` or falling through to `run_decide`; and `run_decide`'s success path passes through `mark_decide_ran` (`:639-648`) → `rerun_confidence_after_decide` (`:650-667`) → `recheck_after_decide` (`:669-685`) before reaching `assert_decision_cleared`. These 5 additional states are structurally load-bearing for the cluster's control flow though unnamed in the 5-state table — extraction scope is closer to 10 states than 5.
- `run_decide`'s `on_error` routes to a distinct state, `check_decision_after_decide_error` (`autodev.yaml:627-637`, ENH-2717) — separate from `assert_decision_cleared`'s success-path gate. Both check `decision_needed` and both route `on_yes: record_decision_unresolved`, but they are two separate states in the current file, not one shared gate.

## Program Design

The deliverable is loop YAML, not Python — no new modules, types, or functions. What the design
must pin down is which *existing* engine path the change rides on, and the sub-loop's terminal
contract.

### Types

- `StateConfig.loop: str` — sub-loop reference, already carried on the state (the field
  `confidence_check` sets at `refine-to-ready-issue.yaml:278`)
- `StateConfig.with_: dict[str, str]` — sub-loop params, how `issue_id` crosses the boundary
  regardless of each caller's local capture name

### Signatures

- `_execute_sub_loop(self, state: StateConfig, ctx: InterpolationContext) -> str | None`
  (`scripts/little_loops/fsm/executor.py:820`) — the existing engine entry point Option B uses;
  unchanged by this issue, listed because its capture shape constrains the contract
- `resolve_loop_path(name_or_path: str, loops_dir: Path) -> Path`
  (`scripts/little_loops/fsm/loop_paths.py:19`) — resolves `oracles/<decision-cluster>`

Sub-loop terminal contract: `done` = `decision_needed` cleared; `failed` = still armed after
decide, **or** decide was never reached (error / rate-limit exhaustion). Caller routes its own
recovery off `failed`. This binary contract is only coherent because `assert_decision_cleared`
sits inside the sub-loop directly after `run_decide` and every non-success exit — including
`on_rate_limit_exhausted` — is routed to `failed` rather than `done`; see
`### The extraction boundary` and `### Rate-limit exhaustion`.

Sub-loop parameter block (both `_validate_with_bindings` ERROR-severity requirements):

```yaml
parameters:
  issue_id:   {type: string, required: true}
  skip_probe: {type: string, required: false, default: "false"}
```

### Call Path

`_execute_sub_loop` → `resolve_loop_path` → the decision-cluster loop

At the YAML layer, both callers enter that engine path from their existing gates:
`refine-to-ready-issue.check_decision_mid_refine` and `autodev.check_decision_after_refine` →
sub-loop → `check_wire_done` / (`rerun_confidence_after_decide` | `record_decision_unresolved`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- Sub-loop return contract (`_execute_sub_loop`, `scripts/little_loops/fsm/executor.py:820`, routing at `:1058-1086`) is binary by construction, not multi-way: `terminated_by == "terminal"` and not `failure_terminal` → caller's `on_yes`/`on_success`; `terminated_by == "terminal"` and `failure_terminal` → `on_no`/`on_failure`; `terminated_by == "error"` → `on_error` (else `on_no`); `timeout`/`max_steps`/`max_iterations_reached` → `on_timeout` if declared (else `on_no`); anything else (`interrupted`, `cycle_detected`, `stall_detected`, `handoff`, etc.) → `on_no`. The extracted sub-loop's `done`/`failed` terminals therefore can only signal *decision resolved* vs. *decision still unresolved/errored* to the caller in one step — `autodev`'s finer-grained caller-side routing (`implement_current` vs. `run_size_review` vs. `dequeue_next`) must be re-derived by the caller re-checking `decision_needed`/readiness after the sub-loop returns, not read off the sub-loop's own terminal.
- A sub-loop terminal state is treated as a failure terminal only if `terminal: true` and the state name is in `FAILURE_TERMINAL_NAMES = frozenset({"failed", "error", "aborted", "finalize_aborted"})` (`scripts/little_loops/fsm/schema.py:33-35`, applied in `StateConfig.from_dict` at `:873`), or if the state sets `failure: true` explicitly. The existing `oracles/verify-confidence-scores.yaml` `failed:` terminal relies on the name-based default and sets no explicit `failure:` flag — the new decision-cluster sub-loop must name its failure terminal from that set (e.g. `failed`) or set `failure: true` explicitly, or its `record_decision_unresolved` path will silently route through `on_yes`/`on_success` instead of `on_no`/`on_failure`.
- `resolve_loop_path` (`scripts/little_loops/fsm/loop_paths.py:19-40`) treats `oracles/` as an ordinary path segment, not a namespace: `loop: oracles/<name>` resolves to `<loops_dir>/oracles/<name>.yaml` (or `.fsm.yaml`), falling back to the builtin loops dir. The new sub-loop file must be placed at `scripts/little_loops/loops/oracles/<decision-cluster-name>.yaml`, matching `oracles/verify-confidence-scores.yaml`'s placement, for `loop: oracles/<decision-cluster-name>` to resolve from either caller.
- `with:` param binding (`executor.py:862-891`) interpolates the `with:` dict, applies child `parameters:` defaults for unbound optional params, and merges `child_fsm.context = {**child_fsm.context, **resolved}` — `with:` values win over the child's own `context:` defaults. `run_dir` is separately `setdefault`-injected from the parent's context (`:890-891`) since binding via `with:` does not otherwise inherit parent context.

  _Corrected 2026-08-05 (pre-implementation review):_ this finding originally concluded that marker files "will land under the *sub-loop's* `run_dir`, not the parent's." **The opposite is true** — the `setdefault` injects the *parent's* `run_dir` into the child, so the child writes into the parent's run directory. That is required for `autodev.yaml:104-105`'s `dequeue_next` clear to keep working, and it creates a cross-issue leakage hazard under `recursive-refine`'s shared-`run_dir` multi-issue queue. See `### Marker semantics (corrected)` for the resulting per-issue-marker-name requirement.

_Wiring pass added by `/ll:wire-issue`:_
- `_validate_with_bindings` (`scripts/little_loops/fsm/validation/structural_rules.py:~258`) is a
  **load-time ERROR-severity** check, not just convention: for any state with `loop:` + `with:`, it
  resolves the child FSM's top-level `parameters:` block and fails `ll-loop validate` if a `with:`
  key isn't declared in the child's `parameters:`, or a child `required: true` parameter isn't bound.
  The new sub-loop must declare `parameters: {issue_id: {type: string, required: true}}` (matching
  `oracles/verify-confidence-scores.yaml`'s shape) or both callers' `with:` blocks fail validation.
- `_validate_loop_references` (`scripts/little_loops/fsm/validation/reachability.py:~64`) is
  **ERROR-severity** (promoted from WARNING after a prior `refine-to-ready-issue.confidence_check`
  path-miss burned compute, per its own docstring) — a typo'd or missing `oracles/` prefix on the new
  sub-loop's path in either caller fails loop loading outright.
- Visibility convention: `scripts/little_loops/fsm/validation/structural_rules.py` `VALID_VISIBILITY`
  check (~line 1606) — the new sub-loop should set `visibility: internal` per
  `oracles/verify-confidence-scores.yaml`'s convention, which excludes internal sub-loops from
  `loop-router`'s catalog (`docs/guides/LOOPS_REFERENCE.md:38`).
- No `oracles/`-specific schema exists beyond the generic checks above — `name`, `initial`, `states`,
  `parameters`/`context` are the only enforced keys; `description:` prose starting "Extracted from
  ..." is precedent-only (from `verify-confidence-scores.yaml`), not machine-enforced.

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- All three `refine-to-ready-issue.yaml` gates (`check_decision_mid_refine:171-181`, `check_decision_mid_wire:211-221`, `check_decision_needed:369-378`) and the `autodev.yaml` cluster's flag-check states use `fragment: shell_exit` (`lib/common.yaml:15-21`) with action `ll-issues check-flag <id> decision_needed`; each gate's `on_no`/`on_error` already targets its own pre-existing continuation state (`check_wire_done`, `verify_issue`, `check_missing_artifacts` respectively) — the retargeting edit changes only `on_yes`, leaving `on_no`/`on_error` untouched. _Amended
2026-08-05 (second pre-implementation review): each gate's `on_yes` points at its **own** new `loop:`
call state, not a single shared one, because the three post-decide continuations differ — see
`### Three gates need three call states`._
- `oracles/verify-confidence-scores.yaml` confirmed as the structural template for the new sub-loop: `parameters: {issue_id: {type: string, required: true}}`, `context: {issue_id: ""}`, every internal state body reads `${context.issue_id}` (never `${captured...}`), terminals are bare `done: {terminal: true}` / `failed: {terminal: true}` with no `on_success`/`on_failure` fields — those live only on the caller's `loop:` state (matching `refine-to-ready-issue.yaml:277-289`'s `confidence_check` call shape).
- Each caller's existing capture flows into the sub-loop unchanged via `with:`: `autodev.yaml` → `with: {issue_id: "${captured.input.output}"}` (capture set at `dequeue_next`, `:156`); `refine-to-ready-issue.yaml` → `with: {issue_id: "${captured.issue_id.output}"}` (capture set at `resolve_issue`, `:66`). No caller-side capture-name changes are needed.
- `record_decision_unresolved`'s `deferred`-status side effect (`autodev.yaml:701-724`) and the plain `implement_current` success exit are caller-specific post-cluster routing, not part of the sub-loop body — `refine-to-ready-issue.yaml` today has no equivalent of `record_decision_unresolved` (its three gates only ever route to `done` on `decision_needed: true`), so this caller must newly decide its own handling of the sub-loop's `failed` terminal when adopting it. **Resolved 2026-08-05** — see `### refine-to-ready-issue's handling of the failed terminal (resolved)`: it gets its own `record_decision_unresolved` writing the `DECISION_UNRESOLVED` ledger, then exits via `failed`.

## Implementation Steps

_Revised 2026-08-05 (pre-implementation review). Step 1 was stale — Option B is already selected
(`decision_needed: false`). The remaining steps are ordered so every design question is closed
before any YAML moves._

_Re-scoped 2026-08-05 (third review): the `autodev.yaml` conversion (was step 2) moved to ENH-3075.
Steps renumbered; the sub-loop is **copied from** `autodev.yaml`, not cut out of it._

1. Author the new sub-loop at `scripts/little_loops/loops/oracles/resolve-decision.yaml` per
   `### The extraction boundary`: `route_entry` → `check_decision_decidable` → `deposit_options` →
   `record_options_deposited` → `check_open_question_progress` → `run_decide` →
   `assert_decision_cleared`, terminals `done`/`failed`, `visibility: internal`,
   `parameters: {issue_id (required), skip_probe (optional, default "false")}`.
   Apply on the way in: `import: - lib/common.yaml` (all three fragments come from it — see
   `### The extraction boundary`), the `${captured.input.output}` → `${context.issue_id}` rewrite
   across all six bodies including the shell heredoc, explicit `max_steps`/`timeout`, the per-issue
   marker name (`### Marker semantics`), the explicit per-issue
   `evaluate.history_file` on `check_open_question_progress` (`### Open-question stall gate is
   inert`), `failed`-side `on_rate_limit_exhausted` (`### Rate-limit exhaustion`), and the
   `check_decision_after_decide_error` collapse.
2. ~~Convert `autodev.yaml`.~~ **Deferred to ENH-3075** (`## Scope`). `autodev.yaml` is not edited by
   this issue; it keeps its inline cluster and its flat marker name, which do not collide with the
   sub-loop's per-issue marker even under nesting.
3. Add **three** `loop:` call states to `refine-to-ready-issue.yaml` — one per gate, since a `loop:`
   state has a single `on_success` and the three gates resume at three different points — and point
   each gate's `on_yes` at its own call state (leaving every `on_no`/`on_error` untouched).
   Success targets: `check_wire_done`, `verify_issue`, and **`confidence_check`** for
   `check_decision_needed` (re-score after decide, not its `on_no` target). All three route
   `on_failure` to a new shared `record_decision_unresolved` → `failed`. Raise `max_steps` 30 → 40
   and update the ENH-3031 rationale comment. See `### Three gates need three call states`.
4. ~~Verify `issue-refinement.yaml:29-33` declares an `on_failure`.~~ **Pre-verified 2026-08-05
   (third review):** it declares `on_failure: failed` and `on_error: failed` at
   `issue-refinement.yaml:25-27` (ENH-2825). No work. Note the downstream effect, though: once
   `refine-to-ready-issue` exits `failed` on an unresolved decision, `issue-refinement` surfaces
   exit 2 where it previously reported `done` — that is the intended fix, not a regression.
5. Confirm by inspection that `refine-to-ready-issue` → decision sub-loop is a leaf and cannot
   re-enter `autodev`'s own invocation (`### Caller interaction after the fix`); there is no
   engine-level depth cap to rely on.
6. _(was step 3)_ Preserve the `DECISION_UNRESOLVED` ledger contract that
   `auto-refine-and-implement.yaml:840` reads — now written from **two** places (autodev's
   caller-side `record_decision_unresolved` and `refine-to-ready-issue`'s new one).
7. Verify: `ll-loop validate` on `refine-to-ready-issue` and the new sub-loop (and on `autodev`,
   which should be unaffected — a change there means scope leaked); re-run
   `ll-loop run refine-to-ready-issue BUG-3063` and confirm it proceeds through wire + confidence
   rather than exiting at 5 states.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- ~~Decide how `autodev.yaml:1236`'s `triage_outcome_failure` delegates to the new sub-loop.~~
  **Resolved 2026-08-05** — `route_entry` demultiplexer + `skip_probe` parameter; see
  `### Fifth entry point (resolved)`. The sub-loop must be **authored** with both here (retrofitting
  an entry demultiplexer later would change its `initial:`); the `with:` binding at that call site is
  ENH-3075's work.
- Update `scripts/little_loops/loops/refine-to-ready-issue.yaml:4-23`'s header ASCII routing-summary
  comment to match the new `check_decision_needed` target.
- ~~Update or delete the `test_autodev_decision_gate.py` and `test_builtin_loops.py` assertions on
  `autodev.yaml`'s inline cluster.~~ **Deferred to ENH-3075** — none of them break here.
- Add sub-loop-reference and child-loop-internals tests for the new `oracles/resolve-decision.yaml`,
  following the `test_confidence_check_delegates_to_verify_confidence_scores_oracle` /
  `test_verify_scores_persisted_on_yes_routes_to_check_readiness` templates.
- Update `docs/guides/LOOPS_REFERENCE.md` at the two locations still in scope per
  `### Documentation` (the catalog row for the new sub-loop, and the `refine-to-ready-issue`
  gate-chain section at `:140`). The four `autodev`-describing locations move to ENH-3075.
- Re-verify `scripts/little_loops/loops/recursive-refine.yaml:231`,
  `scripts/little_loops/loops/autodev.yaml:385` (`refine_current`), and
  `scripts/little_loops/loops/issue-refinement.yaml:29-33` still route correctly now that their
  `refine-to-ready-issue` call resolves decisions before returning — and can newly return `failed`
  where it previously returned `done`. (`scan-and-implement.yaml:77` calls `autodev`, which this
  issue does not change; it moves to ENH-3075.)

## Impact

- **Priority**: P3 — silent under-delivery on two loops' core contract, with a success terminal
  masking it. Downgraded from P2 (2026-08-05): `autodev` is the main implementation path and
  already honors the contract (Summary caller table); the three broken paths (`direct run`,
  `recursive-refine`, `issue-refinement`) are secondary. A workaround exists (run
  `/ll:decide-issue` manually) once the operator knows.
- **Effort**: Medium — _revised down from Large 2026-08-05 after the ENH-3075 split (`## Scope`)._
  Authoring the sub-loop plus three call states in `refine-to-ready-issue.yaml`; no `autodev.yaml`
  edits and no rewrite of its ~25 cluster assertions.
- **Risk**: Medium — the sub-loop must reproduce five distinct prior bug fixes (BUG-1416, BUG-2595,
  ENH-2443, ENH-2446, ENH-2717) faithfully enough that ENH-3075 can later delete `autodev`'s copy in
  favor of it. Lower than pre-split: `autodev`, the main implementation path, is not touched, so a
  defect in the new sub-loop can only affect the three paths that are broken today anyway.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | § Loop Authoring — meta-loop rules and `ll-loop validate` enforcement |
| `docs/ARCHITECTURE.md` | FSM loop execution and sub-loop invocation model |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-05_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 59/100 → LOW

### Outcome Risk Factors
- Deep per-site complexity: the change is architectural control-flow rewiring (extracting a ~10-state cluster from `autodev.yaml` into a new `oracles/` sub-loop and retargeting two callers' terminal contracts), not a mechanical edit — Complexity/Depth scored 0/13.
- Large test-rewrite surface: `test_autodev_decision_gate.py` (1211 lines) and multiple `test_builtin_loops.py` classes assert on exact inline state names/routing inside `autodev.yaml` that this refactor moves; no end-to-end/live-run coverage exists to backstop the structural rewrite, so regressions in the moved control flow may go undetected until manual re-run.
- Moderate blast radius: 4-5 dependent call sites (`autodev.yaml` self-reference, `recursive-refine.yaml:231`, `issue-refinement.yaml:29-33`, `scan-and-implement.yaml:77`, plus `rn-remediate.yaml`'s out-of-scope duplicate cluster) must be re-verified to still route correctly once their sub-loop calls resolve decisions inline.

_(Gaps to Address omitted — readiness score is 100, above the 70 threshold.)_

**Verified this pass**: the 2026-08-05 pre-implementation review's resolutions for the fifth entry point (`route_entry` + `skip_probe`), marker semantics (per-issue name, inherited `run_dir`), rate-limit exhaustion (`failed` terminal), and the extraction boundary all check out against the current codebase — `_execute_sub_loop` (`executor.py:820`), `FAILURE_TERMINAL_NAMES` (`schema.py:33`), `resolve_loop_path` (`loop_paths.py:19`), and all named autodev/refine-to-ready-issue state locations were spot-checked and resolve (line numbers have drifted slightly since the review, as expected from ongoing edits, but every named state and mechanism exists as described). `format-check --format json` returns no `stale_symbol_ref`/`stale_cli_flag`/`missing_behavior_parity` findings — the prior run's `VALID_VISIBILITY` advisory has since cleared. Ambiguity scoring moved from 10→18 to reflect that the pre-implementation review closed out what were previously open design questions (fifth entry point, marker semantics, rate-limit exhaustion, extraction boundary) rather than leaving them as implementation-time judgment calls.

## Second Pre-Implementation Review — 2026-08-05

Verified the issue's mechanism claims against the engine and both loop files. `_execute_sub_loop`'s
`run_dir` `setdefault` (`executor.py:889-891`), `FAILURE_TERMINAL_NAMES` (`schema.py:33`),
`resolve_loop_path` (`loop_paths.py:19`), and `_validate_with_bindings`' ERROR severity all hold as
described. Five corrections were folded into the sections above:

| # | Finding | Where fixed |
|---|---|---|
| 1 | Three gates cannot share one `loop:` call state; gate 3's success target must be `confidence_check`, and `max_steps: 30` no longer fits | `### Three gates need three call states` |
| 2 | Sub-loop must declare `import: - lib/common.yaml`; the named template has none | `### The extraction boundary` |
| 3 | `check_open_question_progress`'s stall gate is inert — evaluator reads a file nothing writes | `### Open-question stall gate is inert` |
| 4 | Marker rename has three live sites, not one | `### Marker semantics` |
| 5 | `${captured.input.output}` → `${context.issue_id}` rewrite (incl. a shell heredoc); declare `max_steps`/`timeout` | `### The extraction boundary`, step 1 |

Findings 1 and 2 were load-bearing enough to block a first implementation attempt. Finding 3 is a
pre-existing defect this refactor would otherwise have copied forward under a "Preserved" label.

## Third Pre-Implementation Review — 2026-08-05

Re-verified the engine claims and split the issue. Confirmed still-accurate: the stall-gate
inertness finding (`autodev.yaml:585` writes `.open_questions_${ID}.history`; no
`evaluate.history_file` is declared, so `evaluators.py:1958` falls back to a path nothing writes),
`_execute_sub_loop`'s parent-`run_dir` `setdefault` (`executor.py:889-891`), `FAILURE_TERMINAL_NAMES`
(`schema.py:33`), and `max_edge_revisits: 100` (`schema.py:1281`) — which is what makes gate 3's
re-entry cycle safe well beyond the `max_steps: 40` bound.

| # | Finding | Where fixed |
|---|---|---|
| 1 | `on_rate_limit_exhausted` **cannot fire on a `loop:` state** — `_execute_sub_loop` returns a route directly and produces no `ActionResult`, and `failure_terminal` is a bool, not a name. The prior resolution prescribed a mechanism that would read as working and silently never fire. | `### Rate-limit exhaustion` |
| 2 | The `assert_decision_cleared` reorder is not purely a tightening — `recheck_after_decide.on_no: snap_and_size_review` (`autodev.yaml:684`) bypasses the flag check today, so still-armed + failing-score issues lose ENH-1415's size-review escape. | `### The extraction boundary`, Behavior Parity |
| 3 | `### Marker semantics`' rationale was inverted (the clear *releases* the write-once bound, it does not enforce it), and `dequeue_next` cannot use `${captured.input.output}` — `capture: input` is written by that same state, so only the shell-local `$${CURRENT}` is correct. | `### Marker semantics`, ENH-3075 |
| 4 | `deposit_options`'s `on_partial` route (`:564`) was absent from the parity table; `issue-refinement.yaml` already declares `on_failure` (step 4 was already satisfied). | `### The extraction boundary`, step 4 |
| 5 | Scope split — the `autodev` conversion, its ~25 broken assertions, the marker rename, and findings 2–3 moved to ENH-3075. | `## Scope` |

Finding 1 was load-bearing: implemented as previously written, a 429 storm would have deferred issues
under a misleading reason with no route ever taken.

## Session Log
- `/ll:manage-issue` - 2026-08-06T04:38:22 - `be4424fb-bd22-4a4d-8f91-9e0d0eb44d1c.jsonl`
- `/ll:ready-issue` - 2026-08-06T04:21:07 - `90ac5a00-ccc9-4464-ba1a-550d9d9d19e7.jsonl`
- `/ll:confidence-check` - 2026-08-06T04:18:58 - `d0756c3a-5f12-4d7f-a29e-55bed7835840.jsonl`
- `/ll:confidence-check` - 2026-08-05T21:40:43 - `5b36b1a8-f955-4387-b628-060e5d47565a.jsonl`
- `/ll:confidence-check` - 2026-08-05T21:26:23 - `df4641bf-83a3-4970-9d63-8766a6c28feb.jsonl`
- `/ll:confidence-check` - 2026-08-05T21:06:35 - `1280ced4-9fda-4c58-a33f-cf524332bd3e.jsonl`
- `/ll:verify-issues` - 2026-08-05T21:02:01 - `d1ec8a23-5bcc-4a5c-abec-47eb0e38a04f.jsonl`
- `/ll:refine-issue` - 2026-08-05T20:59:56 - `64674ad1-3e2c-4736-8982-c9aa28bd3e87.jsonl`
- `/ll:verify-issues` - 2026-08-05T20:56:37 - `90de83e8-7a69-4aa6-8be3-d90dc6c55111.jsonl`
- `/ll:wire-issue` - 2026-08-05T20:54:29 - `0df8843f-ffca-4359-aefe-620278c0685a.jsonl`
- `/ll:refine-issue` - 2026-08-05T20:46:11 - `3f972b4c-34df-4653-a340-b40cbdbe18b4.jsonl`
- `/ll:decide-issue` - 2026-08-05T20:38:36 - `e519a35e-42e1-44db-b9f7-ccbf4a7b1a4e.jsonl`
- `/ll:capture-issue` - 2026-08-05T20:06:47 - `69895b45-2950-4e3c-a99c-2ecfbf7e5e1f.jsonl`

## Status

- [ ] Not started


## Skip Log

- **Date**: 2026-08-05T16:35:00Z
- **Reason**: reconcile filename with frontmatter priority
