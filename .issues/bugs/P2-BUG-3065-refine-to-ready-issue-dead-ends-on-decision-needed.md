---
id: BUG-3065
title: refine-to-ready-issue dead-ends on decision_needed instead of resolving it
type: BUG
priority: P2
status: open
discovered_by: capture-issue
discovered_date: 2026-08-05
captured_at: '2026-08-05T20:05:24Z'
relates_to:
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
---

# BUG-3065: `refine-to-ready-issue` dead-ends on `decision_needed` instead of resolving it

## Summary

`refine-to-ready-issue.yaml` has three `decision_needed` gates that all route `on_yes: done`. That
routing is a **sub-loop handoff contract** — exit clean, let a parent loop run `/ll:decide-issue`,
then re-enter. The contract no longer has a counterparty: nothing invokes `refine-to-ready-issue`
as a sub-loop today. Run it on an issue whose refine pass sets `decision_needed: true` and it exits
`done` after four states, having silently skipped `/ll:wire-issue`, `/ll:verify-issues`, and
`/ll:confidence-check` — with no signal to the operator that the readiness pipeline never ran.

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
resolve the decision either — its own `check_decision_needed`
(`scripts/little_loops/loops/recursive-refine.yaml:556-568`) **skips the issue entirely**, appending
it to `recursive-refine-skipped-decision.txt`. Only `autodev.yaml` carries `run_decide` machinery.

Net effect: a `decision_needed` issue dead-ends in both loops, and the operator must notice the
truncated run and invoke `/ll:decide-issue` by hand.

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

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — retarget the three `decision_needed`
  gates' `on_yes` from `done` to the decision cluster/sub-loop call.
- `scripts/little_loops/loops/autodev.yaml` — (Option B) replace the inline cluster at lines 529-573,
  610-624, 685-697 with a `loop:` call; keep `record_decision_unresolved` as autodev's own terminal
  routing.
- `scripts/little_loops/loops/oracles/` — (Option B) new sub-loop YAML for the decision cluster.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:4-23` — the file's own header comment is an
  ASCII "Routing summary" diagram that explicitly shows `check_decision_needed → (on_yes) done`;
  must be updated in the same edit as the state retargeting or it becomes stale documentation
  embedded in the primary file itself.
- `scripts/little_loops/loops/autodev.yaml:1236` (`triage_outcome_failure` state) — a **fifth**
  entry point into the decision cluster, distinct from the four already covered by the Behavior
  Parity table below: it routes directly to `run_decide`, bypassing `check_decision_decidable`
  entirely (predicate is `score_ambiguity ≤ 10 OR decision_needed`, not the deterministic
  `ll-issues check-decidable` gate the other four entry points use). A `loop:` state has exactly one
  `initial:` entry point, so if the new sub-loop's `initial` is `check_decision_decidable` (matching
  the other four callers), `triage_outcome_failure` cannot delegate to it without either being
  retargeted to route through `check_decision_decidable` first (a behavior change) or the sub-loop
  exposing a context-gated skip-to-`run_decide` branch. This must be resolved explicitly during
  extraction, not left implicit — see the added Behavior Parity row below.

### Behavior Parity

Option B delegates `autodev.yaml`'s inline decision cluster to a sub-loop. Every behavior below
must survive the move — each exists because of a named prior bug.

| Behavior (autodev.yaml) | Artifact | Status |
|---|---|---|
| Marker short-circuit skips re-validation once options were deposited (`:539-542`) | sub-loop | Preserved |
| `check-open-questions \|\| check-decidable` probe order (ENH-2446, `:543-544`) | sub-loop | Preserved |
| `deposit_options` bounded single retry via `/ll:refine-issue --auto` (`:550-565`) | sub-loop | Preserved |
| Write-once `autodev-decide-options-deposited` marker (`:567-573`) | sub-loop | Preserved — marker path must move to the sub-loop's `run_dir` (context_passthrough) |
| `run_decide` `/ll:decide-issue --auto` + `decide-issue-auto` pruning profile (`:610-624`) | sub-loop | Preserved |
| `assert_decision_cleared` post-decide flag re-verify (BUG-2595, `:685-697`) | sub-loop | Preserved |
| `check_decision_after_decide_error` short-circuit on still-armed flag (ENH-2717, `:627-640`) | autodev | Preserved — stays caller-side (routes to autodev's own terminal) |
| `mark_decide_ran` → `autodev-decide-ran` marker consumed by `decide_current` (ENH-1415) | autodev | Preserved — autodev-specific queue state, not part of the cluster contract |
| `record_decision_unresolved` defer + `DECISION_UNRESOLVED` ledger (`:700-724`) | autodev | Preserved — caller-side terminal routing; `auto-refine-and-implement.yaml:840` reads this ledger |
| `rerun_confidence_after_decide` re-score after decide (`:679`) | autodev | Preserved — caller-side |
| `fragment: with_rate_limit_handling` / `on_rate_limit_exhausted` on `run_decide` + `deposit_options` | sub-loop | **Changed** — rate-limit handling must be re-expressed at the sub-loop level; verify `on_rate_limit_exhausted: done` semantics still reach the caller |
| `triage_outcome_failure` (`autodev.yaml:1236`) routes directly to `run_decide`, bypassing `check_decision_decidable` — a fifth cluster entry point beyond the four this table otherwise covers | _Wiring pass added by `/ll:wire-issue`:_ unresolved | **Open — must be designed**: either retarget `triage_outcome_failure` through `check_decision_decidable` (behavior change) or give the sub-loop a context-gated skip-to-`run_decide` branch. `docs/guides/LOOPS_REFERENCE.md:1055` already claims (inaccurately, pre-existing) that all four `decision_needed:true` entry points share the same gate — this row is the wiring pass's evidence that claim was already false before this refactor |

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

**`test_autodev_decision_gate.py` (1211 lines) — exact assertions that will break** (issue's own
Codebase Research Findings already flagged the file; this pass pins the specific lines):
- `run_decide` on_error routing (lines 1066-1068)
- `assert_decision_cleared` existence + 5 routing assertions (lines 967-1018)
- `check_decision_after_decide_error` existence + 5 routing assertions (lines 1072-1128)
- `record_decision_unresolved` action-content + defer assertions (lines 1022-1041)
- `check_decision_decidable` referenced only as a target string at lines 143, 360-361 (upstream gates
  `check_decision_at_dequeue`/`check_decision_before_size_review`) — needs retargeting to the new
  single entry-point state name.
- `deposit_options`, `record_options_deposited`, `mark_decide_ran`, `rerun_confidence_after_decide` —
  no direct structural assertions found; only new coverage to add, nothing to break.
- Two independent fixture-FSM classes (`TestCheckDecisionAtDequeueRouting` ~203-280,
  `TestAssertDecisionClearedRouting` ~1138-1211) build their own minimal FSMs and won't break, but
  encode the same target-state names as literals and will drift out of sync with the real topology
  post-extraction.

**A second, separate `test_builtin_loops.py` class covers the same cluster inside `autodev.yaml`
itself — larger surface than `test_autodev_decision_gate.py` alone:**
- `test_required_states_exist` (~4215-4249) — a `required` set literal including `decide_current`,
  `run_decide`, `mark_decide_ran`, `rerun_confidence_after_decide`; **will break** (KeyError-class
  failure) once these states move out of `autodev.yaml`'s own `states:` dict.
- `test_check_decision_at_dequeue_...` (~4337), `test_check_decision_after_refine_...` (~5498),
  `test_check_decision_before_size_review_...` (~6007), `test_triage_outcome_failure_on_yes_routes_to_run_decide`
  (~6046 — asserts the fifth-entry-point bypass edge, see Files to Modify above),
  `test_decide_current_on_yes_routes_to_check_decision_decidable` (~6304),
  `test_check_decision_decidable_state_exists_and_routes` (~6314),
  `test_deposit_options_state_exists_and_routes` (~6324),
  `test_check_open_question_progress_...` (~6341-6360),
  `test_run_decide_uses_with_rate_limit_handling_fragment` /
  `test_run_decide_next_routes_to_mark_decide_ran` /
  `test_run_decide_on_error_routes_to_implement_current` /
  `test_run_decide_on_rate_limit_exhausted_routes_to_done` (~6375-6396),
  `test_mark_decide_ran_state_exists` / `..._next_routes_to_rerun_confidence_after_decide` /
  `..._writes_decide_ran_flag` (~6460-6479),
  `test_record_decision_unresolved_defers_via_set_status` (~5359-5362), and further
  `record_decision_unresolved`-referencing assertions (~5638, ~6767) — **all will break**, need
  rewriting to load and assert against the new `oracles/<name>.yaml` sub-loop file instead.

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
- `docs/guides/LOOPS_REFERENCE.md:1000-1045` — `autodev` FSM-flow ASCII diagram spells out the
  `run_decide → mark_decide_ran → rerun_confidence_after_decide → recheck_after_decide` chain
  literally, multiple times, by exact state name; must be updated once these states move.
- `docs/guides/LOOPS_REFERENCE.md:1047` — "Diagram omissions" paragraph, the densest prose
  description of the cluster's internal wiring by exact state name
  (`check_decision_decidable`, `deposit_options` → `record_options_deposited` →
  `check_open_question_progress`, `assert_decision_cleared`, `check_decision_after_decide_error`,
  `record_decision_unresolved`) — describes internals that no longer live in `autodev.yaml`'s own
  `states:` block post-extraction.
- `docs/guides/LOOPS_REFERENCE.md:1053` — "Outcome failure triage" paragraph documenting
  `triage_outcome_failure`'s direct `run_decide` route (the fifth entry point, see Files to Modify).
- `docs/guides/LOOPS_REFERENCE.md:1055` — "Decidability gate parity" paragraph claims all four
  `decision_needed:true` entry points share `check_decision_decidable` before `run_decide`; already
  inaccurate against `triage_outcome_failure`'s direct route (pre-existing, not caused by this
  refactor) and must be corrected regardless, then re-verified once the states move.
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
decide (caller routes its own recovery).

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
- `with:` param binding (`executor.py:862-891`) interpolates the `with:` dict, applies child `parameters:` defaults for unbound optional params, and merges `child_fsm.context = {**child_fsm.context, **resolved}` — `with:` values win over the child's own `context:` defaults. `run_dir` is separately `setdefault`-injected from the parent's context (`:890-891`) since binding via `with:` does not otherwise inherit parent context — the sub-loop's own marker files (equivalent to `autodev-decide-options-deposited`, `autodev-decide-ran`) will land under the *sub-loop's* `run_dir`, not the parent's, matching the Behavior Parity table's note that the marker path must move to the sub-loop's `run_dir`.

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

## Implementation Steps

1. Resolve the Option A / Option B decision (`/ll:decide-issue BUG-3065`).
2. (Option B) Extract the decision cluster from `autodev.yaml` into a sub-loop under
   `scripts/little_loops/loops/oracles/`, parameterized by issue id via `with:`.
3. (Option B) Convert `autodev.yaml` to call the sub-loop, preserving `record_decision_unresolved`
   routing and the `DECISION_UNRESOLVED` ledger `auto-refine-and-implement.yaml:840` reads.
4. Retarget all three `refine-to-ready-issue` gates to the cluster, ordered before wire/confidence.
5. Verify: `ll-loop validate` on both loops; re-run `ll-loop run refine-to-ready-issue BUG-3063` and
   confirm it proceeds through wire + confidence rather than exiting at 5 states.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Decide how `autodev.yaml:1236`'s `triage_outcome_failure` (the fifth cluster entry point, which
  bypasses `check_decision_decidable` and routes straight to `run_decide`) delegates to the new
  sub-loop — retarget it through `check_decision_decidable` first, or give the sub-loop a
  context-gated skip-to-`run_decide` branch. Resolve explicitly; do not leave it implicit.
- Update `scripts/little_loops/loops/refine-to-ready-issue.yaml:4-23`'s header ASCII routing-summary
  comment to match the new `check_decision_needed` target.
- Update or delete the `test_autodev_decision_gate.py` and `test_builtin_loops.py` assertions listed
  in `### Tests` above that structurally assert on cluster states inside `autodev.yaml`'s own
  `states:` dict — this is a larger rewrite surface than a single test file.
- Add sub-loop-reference and child-loop-internals tests for the new `oracles/<name>.yaml` file,
  following the `test_confidence_check_delegates_to_verify_confidence_scores_oracle` /
  `test_verify_scores_persisted_on_yes_routes_to_check_readiness` templates.
- Update `docs/guides/LOOPS_REFERENCE.md` at the six locations listed in `### Documentation` above
  (catalog rows, FSM-flow diagram, diagram-omissions prose, outcome-failure-triage prose, the
  pre-existing "four entry points" inaccuracy, and the refine-to-ready-issue gate-chain section).
- Re-verify `scripts/little_loops/loops/scan-and-implement.yaml:77`,
  `scripts/little_loops/loops/recursive-refine.yaml:231`, `scripts/little_loops/loops/autodev.yaml:385`
  (`refine_current`), and `scripts/little_loops/loops/issue-refinement.yaml:29-33` still route
  correctly after their sub-loop calls now do more work (resolve decisions) before returning.

## Impact

- **Priority**: P2 — silent under-delivery on two loops' core contract, with a success terminal
  masking it. Not P1: a workaround exists (run `/ll:decide-issue` manually) once the operator knows.
- **Effort**: Medium — Option A is small; Option B adds a sub-loop extraction plus an `autodev`
  conversion touching a heavily-guarded routing path.
- **Risk**: Medium — `autodev`'s decision cluster encodes five distinct prior bug fixes; the
  refactor must preserve every guard and the `DECISION_UNRESOLVED` ledger contract.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | § Loop Authoring — meta-loop rules and `ll-loop validate` enforcement |
| `docs/ARCHITECTURE.md` | FSM loop execution and sub-loop invocation model |

## Session Log
- `/ll:verify-issues` - 2026-08-05T20:56:37 - `90de83e8-7a69-4aa6-8be3-d90dc6c55111.jsonl`
- `/ll:wire-issue` - 2026-08-05T20:54:29 - `0df8843f-ffca-4359-aefe-620278c0685a.jsonl`
- `/ll:refine-issue` - 2026-08-05T20:46:11 - `3f972b4c-34df-4653-a340-b40cbdbe18b4.jsonl`
- `/ll:decide-issue` - 2026-08-05T20:38:36 - `e519a35e-42e1-44db-b9f7-ccbf4a7b1a4e.jsonl`
- `/ll:capture-issue` - 2026-08-05T20:06:47 - `69895b45-2950-4e3c-a99c-2ecfbf7e5e1f.jsonl`

## Status

- [ ] Not started
