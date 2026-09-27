---
id: ENH-3623
type: ENH
title: prepare-issue as a policy dispatch loop
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T01:47:29Z'
parent: EPIC-3565
supersedes:
- ENH-3606
relates_to:
- ENH-3621
- ENH-3618
- BUG-3628
blocked_by:
- ENH-3630
blocks:
- ENH-3600
- ENH-3590
confidence_score: 85
outcome_confidence: 58
score_complexity: 5
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# ENH-3623: prepare-issue as a policy dispatch loop

## Summary

Replace ENH-3606's graph relocation with the design the ENH-3621 spike proved (verdict
PASS on all four criteria; report `thoughts/spikes/preparation-policy-spike.md`, spike
code on branch `spike/preparation-policy` at `a51621302`, not merged). Autodev's
second-pass preparation ladder (the verified 39-state move set plus `size_review_snap`,
`check_broke_down` and `mark_scores_absent_infra`) becomes:

- a pure Python policy `decide(IssueSnapshot, Facts) -> Step` over the issue file,
  config and an append-only per-issue fact log;
- writers kept separate from decisions, behind `ll-issues prep {step,record,apply,explain}`;
- a 15-state dispatch loop that replaces `prepare-issue.yaml` in place.

This issue supersedes ENH-3606. ENH-3606's still-valid decisions carry over (terminal
table, ledger ownership, DECOMPOSED guarantee, queue ownership, accepted behavior
changes, boundary retargets, the three autodev deletions). Its graph-relocation
mechanics are dropped: the ~55-state wrapper, `route_inner_success`,
`detect_ladder_children`, `route_ladder_stop`, the `mark_*` terminals, the 250-step
arithmetic, and the `count_repair_cycle_refine` → `clear_record` entry chain. Each of
those becomes a rule, a precondition or an `apply` outcome.

## Phasing

This is large and touches the most-used loop, and every project on this machine is
`local-editable`, so a half-landed cutover breaks tooling everywhere. Land it as three
phases. **Decided (2026-09-27 review)**: Phase A is its own issue, **ENH-3630**, which
blocks this one; this issue keeps Phases B and C.

1. **Phase A, additive (ENH-3630).** `little_loops.preparation_policy` (policy / facts /
   writers), `ll-issues prep {step,record,apply,explain}`, `decide()` table tests, and the
   promoted parity/differential tests run against the *existing* YAML, with an explicit
   allowance list for the accepted changes (the fixed-on-main semantics, item 6 below, are
   parity there, not allowances, since both sides carry the fixes).
   No loop file changes, so nothing can regress; the dispatch loop lands as a test fixture
   `scripts/tests/fixtures/prepare-issue-policy.yaml` (new). The spike branch is already tagged
   (`spike/preparation-policy-a51621302` at `a51621302`), so the port source cannot be pruned.
2. **Phase B, cutover (atomic).** Replace `prepare-issue.yaml` by moving ENH-3630's
   fixture `scripts/tests/fixtures/prepare-issue-policy.yaml` into its place (`git mv`,
   then repoint `preparation_policy_harness.POLICY_YAML` and the fixture validation test
   at the built-in path), apply the autodev
   retargets / 42 deletions / `dequeue_next` pass-id write / `copy_broke_down` shrink, and
   migrate the affected tests in the same commit.
   - **In-flight runs**: a persisted autodev run whose `current_state` is one of the 42
     removed states cannot resume after the cutover. `PersistentExecutor.resume()`
     restores `current_state` unchecked and `fsm/executor.py` (~:761) indexes
     `self.fsm.states[self.current_state]`, a raw `KeyError`. Autodev uses
     `on_handoff: spawn`, so a detached handoff session can straddle the commit. Phase B
     adds a resume guard: `resume()` fails with a clear "state `<name>` no longer exists
     in `<loop>`; restart the run" error instead of a `KeyError` (generic, so it covers
     any loop edit). Before landing, drain or stop running autodev loops in the
     `local-editable` projects.
3. **Phase C, docs.** CLI/API/LOOPS_REFERENCE/ARCHITECTURE/DEFERRAL_CODES, `ll-adapt`
   mirrors, and the opt-in slow resume matrix.

**Ordering prerequisites**: BUG-3624 (Q1) and ENH-3625 (Q3) landed first (both `done`), on the current
YAML, so the ENH-3618 suite pins the fixed behavior and this issue's "accepted behavior
changes" list stays complete.

## Current Behavior

Autodev owns the second-pass ladder behind its `check_passed` gate: 39 states
(selectors, wire/refine, the shared rescoring chain, reconcile/design remedy,
size-review/atomic remediation, go/no-go, pre-deferral remedy) plus `size_review_snap`,
`check_broke_down` and `mark_scores_absent_infra`. The routing policy lives in graph shape
plus about 15 `run_dir` handshake files (repair-cycle counter, rescore origin and retry
markers, re-entry caps, contradiction/remedy/pending/armed markers, once-per-pass
markers, guard-2 captured stdout). Today a resume re-runs the whole wrapper and
double-counts the repair-cycle counter (ENH-3618 pin
`after_counter_increment_double_counts`). ENH-3606's plan to move the cluster into
`prepare-issue.yaml` as YAML would make resume worse: the executor restores only the
parent's `current_state`, so a mid-ladder resume restarts the `loop:` child from
`initial`.

## Expected Behavior

- `prepare-issue.yaml` is a dispatch loop of exactly 15 states. It asks the policy for
  the next step, runs that one command (inner `refine-to-ready-issue` run or one slash
  command), records a done fact, and repeats. It ends in `apply_outcome`, which writes
  exactly one terminal: `READY`, a ledgered `BLOCKED:*` / `DEFERRED:*` stop,
  `DECOMPOSED`, `CANCELLED` or `RETRYABLE_ERROR:*`.
- Autodev has no second-pass state. It keeps the queue, the ledger bookkeeping and the
  fail-closed proof gate in front of `implement_current`.
- Crash and resume at any point replay at most one command and never double-apply
  bookkeeping.
- Behavior matches the ENH-3618 characterization suite, except for the enumerated
  accepted changes below.

## Proposed Solution

### Policy design (from the ENH-3621 spike)

- **Module** `little_loops.preparation_policy`, split into three parts (see "Production
  additions"):
  - `StepKind` = `RUN_CHILD`, `WIRE`, `REFINE_GAP`, `RESCORE`, `RECONCILE`,
    `SIZE_REVIEW`, `GO_NO_GO`, `FINISH`, `STOP`. `Step` is a frozen dataclass
    `(kind, seq, payload, reason, evidence, observations)`.
  - `decide(IssueSnapshot, Facts) -> Step` is pure. It follows the spike's checkpoint →
    rule-order table (report § "Checkpoint → rule-order table"): the checkpoint is the
    last `done` fact of the current pass, plus its `role` / `origin` / `attempt`
    payload. Every chain of today's shell/classify states between two commands collapses
    into one `decide()` call.
  - `next_preparation_step(config, issue_id, run_dir, *, readiness_threshold,
    outcome_threshold) = decide(snapshot_issue(...), load_facts(...))`. The snapshot
    reuses `select_next_obligation` (tier-1 skipped), `resolve_gate_verdict`, the
    check-design / format-gap helpers, `readiness_status` semantics,
    `superseded_marker_count` and the `session_command_counts` field of the parsed issue
    (populated by `count_session_commands`).
- **Fact log** `run_dir/prep-facts/<ID>.jsonl`, with lines `{pass, seq, kind:
  intent|done|obs, step, payload}`. It is append-only and idempotent by
  `(pass, seq, kind)` (obs lines also by content). It replaces the handshake files; the
  mapping is the spike's aggregates table. The repair-cycle count is derived from done
  facts; the file stays only as a projection.
- **Pass id**: autodev's `dequeue_next` increments `run_dir/prep-pass-<ID>`. That is the
  only new autodev write. It is also ENH-3600's dequeued-ID set (`glob prep-pass-*`), so
  ENH-3600 needs no separate prepared-ID ledger. A crash inside `dequeue_next` after the
  increment replays it and skips a pass number; that is harmless (the skipped pass has
  no facts) and needs no idempotency guard, but pin it with a test.
- **Writers** (`ll-issues prep …`, registered in `little_loops.cli.issues` so the harness
  fork server serves them):
  - `prep step`: if an applied terminal exists, replay it. If an intent is open,
    re-run its idempotent preconditions and replay it. Otherwise decide, append obs,
    append intent, run preconditions, and print the kind. There are four preconditions:
    clear records (`RUN_CHILD`), clear scores (first `RESCORE`), defer
    `oversized_atomic` (`GO_NO_GO`), and reopen (the step after a GO).
  - `prep record [--guard2]`: writes the done fact and the repair-cycle projection.
  - `prep apply`: the **sole terminal writer**. It writes, in order, the ledger row,
    `set-status`, the run record, and the inflight clear. It is idempotent through its
    own done fact and an `apply_progress` obs.
  - `prep explain`: prints a decision without writing anything.
- **Dispatch loop**: `prepare-issue.yaml` is replaced in place by the spike's
  `prepare-issue-policy.yaml` shape:
  - `select_step` → { `run_child` (`loop: refine-to-ready-issue`), `run_wire`,
    `run_refine_gap`, `run_rescore`, `run_reconcile`, `run_size_review` →
    `classify_guard2` → `record_guard2`, `run_go_no_go` } → `record_step` →
    `select_step`;
  - FINISH / STOP → `apply_outcome` → `done` / `failed`;
  - `mark_rate_limited`, with `on_max_steps: apply_outcome`;
  - no `rm` anywhere in the wrapper, and the wrapper never stages (autodev's
    `check_passed` is the only writer of `autodev-staged.txt`);
  - the wrapper keeps `capture_reachability_ok: true` (as in the spike):
    `classify_guard2` reads `captured.size_review_output`, which only `run_size_review`
    writes, and the policy reaches `classify_guard2` only from there. Only autodev drops
    the key.

### Carried over from ENH-3606 (still valid)

- **Terminal table** (ENH-3606 § Terminal table). Every terminal writes a
  `writer: prepare-issue` record. Ledger rows keep today's reason strings.
  - `oversized_atomic`, `design_gate_failed`, `readiness_stagnated` and `low_readiness`
    record `deferred` / `gate_unmet`.
  - Both `decision_unresolved` sources record `blocked` / `decision_unresolved`.
  - Atomic-remediation failure records `blocked` / `quality`.
  - A resolved parent or a size-review decomposition records `decomposed`.
  - Rate-limit exhaustion records `retryable_error` / `infra` with `--evidence-refs
    rate_limit_exhausted`, and autodev routes it to `finalize_rate_limited`.
  - Scores absent, `on_error` drops and the step cap record `retryable_error` / `infra`,
    and autodev routes them to `skip_inflight_infra`.
  - A completed ladder records `ready`, and autodev routes it to `check_passed` →
    `check_proof_defer_or_implement`.
  - `ready`, `decomposed` and `cancelled` end in the wrapper's `done`. Every stop ends in
    `failed`, except the step cap (below).
  - **No-terminal-intent fallback**: `apply_outcome` is also the `on_max_steps` handler
    and the `select_step` `_error` / `_` target. When `prep apply` finds no open
    `FINISH` / `STOP` intent for the current pass, it writes `RETRYABLE_ERROR:infra`
    (ENH-3606 `mark_ladder_error`). If the cap fires with a `FINISH` / `STOP` intent
    already open, `apply` applies that terminal normally.
  - **Step-cap exit shape**: the executor runs the `on_max_steps` handler once and then
    finishes with `terminated_by=max_steps` without taking `apply_outcome`'s
    `done`/`failed` transition. Autodev's `refine_current` routes that `on_no` →
    `on_failure` → `route_refine_outcome`, which reads the infra record and goes to
    `skip_inflight_infra`. Pin this with a real-FSM test.
- **Ledger ownership**: the wrapper writes its own stop rows (only in `apply`), and
  autodev routes every `BLOCKED:*` / `DEFERRED:*` to `ledger_child_stop` (no second
  row). `recover_subloop_children` is the only writer of `resolved_by_subloop` rows, and
  `enqueue_children` is the only writer of `decomposed` rows. Keep the `deferred_reason`
  frontmatter writes as today.
- **DECOMPOSED guarantee**: the wrapper emits `decomposed` only when `child_ids` is
  non-empty or the parent is resolved. A resolved issue at any deferral stop ends
  DECOMPOSED, and `recover_subloop_children` owns the row. The size-review baseline
  refresh (`size_review_snap`) is not needed under provenance filtering (spike report).
- **Queue ownership**: the wrapper never writes `autodev-queue.txt` and never runs
  `finalize-decomposition`. Autodev's `DECOMPOSED` → `detect_children` →
  `enqueue_children` path does the enqueue.
- **Accepted behavior changes**, each pinned by its own test and documented in
  `docs/guides/LOOPS_REFERENCE.md`:
  1. scores-absent stops and `on_error` drops produce one `refine_failed_infra` row
     (this also fixes the pinned `phantom` verdict);
  2. a parent that the ladder finds `cancelled` records `CANCELLED`;
  3. a waived `oversized_atomic` issue whose readiness is below threshold is deferred
     `low_readiness`;
  4. an error in autodev's `check_passed` or `check_parent_resolved` ledgers
     `refine_failed_infra`;
  5. a wrapper step-cap cutoff ledgers `refine_failed_infra`;
  6. autodev's `max_steps: 500` stays, but the 42 moved states' steps now count against
     the wrapper's own cap, not autodev's, so one run reaches more issues before
     `finalize_step_capped`. **Decided**: keep 500 (the wrapper cap now bounds each
     issue's ladder) and document it; re-pin any ENH-3618 step-cap scenario whose issue
     count changes.

  The spike also measured these record-token fixes of BUG-LIKE pins:
  - `READY` on the go/no-go GO → implement path (was `MISSING`);
  - `DECOMPOSED` after a size-review decomposition and on the resolved-parent branch
    (was a stale forwarded `BLOCKED`);
  - `READY` on an implemented issue after a rescore retry (was a forwarded `BLOCKED`).
- **Boundary retargets in autodev** (ENH-3606 § Boundary edge retargets):
  - `refine_current.on_success` → `copy_broke_down`;
  - `check_passed.on_yes` → `check_proof_defer_or_implement`, `on_no` /
    `on_cannot_judge` → `skip_inflight`, `on_error` → `skip_inflight_infra`;
  - `detect_children.on_no` / `on_error` → `check_parent_resolved`;
  - `check_parent_resolved.on_no` → `skip_inflight`, `on_error` → `skip_inflight_infra`.
- **Three autodev deletions**: `size_review_snap`, `check_broke_down` and
  `mark_scores_absent_infra`. Shrink `copy_broke_down` to its `refine-broke-down` reset.
  Drop `capture_reachability_ok` from autodev; its only reason moves out with
  `check_guard2_verdict`. Confirm that `ll-loop validate autodev` passes without it.

### Production additions (spike report § "Recommendation vs ENH-3606")

1. **Module split and hardening.** Split the module into policy (pure), facts and
   writers.
   - Share one record-writing helper with `ll-issues run-record write`. The spike
     duplicates `outcome_from_legacy_class` + `readiness_status` inside `apply`.
   - Make the snapshot lazy: scan children only in DETECT / POST_SIZE_REVIEW.
   - Derive the per-pass done-fact cap from the ladder budgets (≤ 4 inner epochs, each
     with its wire/rescore/size-review/reconcile legs, plus the atomic and design
     remedies), and set `max_steps = 4 × cap + 3` (or itemize: 3 states per command
     step, 4 per `SIZE_REVIEW` step, plus the `select_step → apply_outcome → done`
     tail). A command step visits `select_step → run_* → record_step` (3 states), but a
     size-review step visits `select_step → run_size_review → classify_guard2 →
     record_guard2|record_step` (4 states), so `3 × cap + 3` undercounts and would cut a
     legal worst-case ladder off as a false `refine_failed_infra`. The spike's fixed 15
     is below the legal worst case.
   - Make `apply` crash-safe by keying ledger rows by `(pass, seq)` with a
     check-before-append (the row and the `apply_progress` obs live in two files, so one
     atomic write is not available). Each of the four writes (ledger row, `set-status`,
     run record, inflight clear) must be independently idempotent, so replaying `apply`
     from any crash point converges on one terminal. This is an acceptance criterion with a
     crash-injection test (see Acceptance Criteria).
   - `apply` owns the `refine-terminal-class` sentinel writes that `mark_inner_error` does
     today, until ENH-3600 removes the reader. Pin it with a test.
2. **CLI and docs.**
   - `ll-issues prep {step,record,apply,explain}` goes in `docs/reference/CLI.md`, and
     the module goes in `docs/reference/API.md`.
   - `docs/guides/LOOPS_REFERENCE.md`: the autodev tree, the prepare-issue section and
     the accepted behavior changes.
   - `docs/ARCHITECTURE.md`: the fact log.
   - ENH-3606 § Docs lists the rest: `DEFERRAL_CODES.md` sources, `COMMANDS.md`,
     `ISSUE_TEMPLATE.md`, `commands/reconcile-issue.md`, `commands/refine-issue.md`,
     `skills/go-no-go`, `skills/audit-loop-run`, then `ll-adapt`.
3. **Loops.**
   - `prepare-issue.yaml` is replaced in place by the dispatch loop.
   - Autodev gets the boundary retargets, the 42 deletions, the `dequeue_next` pass-id
     write and the `copy_broke_down` shrink.
   - Update the `test_fsm_topology.py` autodev count with a delta comment. Expected
     target: 87 states minus the 42 deletions (`size_review_snap`, `check_broke_down`,
     `mark_scores_absent_infra` and the 39 moved), i.e. 45, plus any new autodev state.
     Record the exact number in the delta comment.
4. **Test migration.**
   - ENH-3606's "Relocate or rewrite" inventory becomes `decide()` table tests plus
     wrapper-structure tests. That inventory is the `TestAutodevLoop` second-pass
     cluster, `test_autodev_decision_gate.py`, `test_autodev_loop.py`,
     `test_autodev_scores_freshness.py`, `test_spike_verdict_routing.py`, the
     interpolation baseline and the topology pins.
   - Port the relevant shell-level predicate tests to table tests before deleting the
     YAML: the contradiction-sourced spike exemption, the spike-budget-exhausted
     reconcile fallback, the refine cap on DPDR, and the selectors' `_error` routes.
   - Promote the spike's parity tests (19 pinned) and differential tests (9), plus a
     representative subset of the resume matrix. The full ~240-point matrix (~35 min at
     `-n 4`) stays opt-in (slow marker).
5. **Settled decisions:**
   - **Q1** (BUG-3624, `done`): the format-check exit code masked the contradiction
     trigger. The port must use the fixed semantics: markers are read from the payload
     whatever the exit code.
   - **Q3** (ENH-3625, `done`): the first-gate Program Design rule. **Rule A**: the first
     gate runs check-design too, so `check_passed` hard-ANDs `ll-issues check-design "$ID"`
     after `check-readiness`, and the run-record `ready` predicate carries the same design
     condition (a design-failing child `done` records `BLOCKED`). Two of the three places
     that must agree after the cutover already carry it on main: autodev's `check_passed`
     (`autodev.yaml` ~:745) and the run-record `ready` predicate (`run_record.py` ~:29).
     **Keep** both through the cutover, and **encode** it in the one new place: the
     `decide()` row after a `RUN_CHILD` done fact.
   - **Run-terminal capture for `record_step`**: the executor merges child captures into
     `captured.run_child` only when the child captured something, and writes
     `failure_terminal` only when it is truthy (`fsm/executor.py:1338`), so a stale
     `failure_terminal` can survive. **Decided (2026-09-27 review)**: `prep record` does
     not read the capture. It reads the child's
     `run-records/refine-to-ready-issue/<ID>.json`, which the `RUN_CHILD` precondition
     clears, so an absent record after `run_child` means the child errored. This keeps
     the loop at 15 states (`select_step`, 7 `run_*`, `classify_guard2`,
     `record_guard2`, `record_step`, `apply_outcome`, `done`, `failed`,
     `mark_rate_limited`) without an executor change. The executor's conditional write is
     still a latent bug for any loop that re-enters a `loop:` state; it is captured as
     BUG-3628 and not fixed here.
6. **Fixed on main since the spike; implement the fixed behavior, not parity:**
   - **BUG-3620** (fixed on main): the design branches read the current check-design verdict,
     and no sticky `autodev-design-gate-failed-<ID>` marker exists. In the policy, the
     design check reads the current verdict (`_Decider.design_marker()`). Drop the
     `obs design_gate_failed` sticky aggregate, and rewrite
     `test_design_marker_is_sticky_across_passes_bug3620_parity` to pin the fixed rule.
   - **BUG-3622** (done, `ce86ce662`): the executor applies 429 handling to `next:`
     states, and rate-limit retries do not count toward the throttle. The rate-limit
     rows are reachable, so `mark_rate_limited` must be live. Every slash-command state
     keeps `with_rate_limit_handling` and `on_rate_limit_exhausted: mark_rate_limited`.
     The parity row `ladder_rate_limit_is_inert` becomes a halt test.
7. **Re-point dependents**: ENH-3600 and ENH-3590 are `blocked_by` this issue.
   ENH-3600's `refine-terminal-class` MISSING-fallback removal gets simpler, because
   every wrapper exit goes through `prep apply`.

## Integration Map

### Files to Modify

- `scripts/little_loops/preparation_policy.py` (new), or a `preparation_policy/` package
  (port from branch `spike/preparation-policy`)
- `scripts/little_loops/cli/issues/__init__.py`: register `prep`
- `scripts/little_loops/loops/prepare-issue.yaml`: replaced in place by the dispatch loop,
  moved from ENH-3630's test fixture `scripts/tests/fixtures/prepare-issue-policy.yaml`
- `scripts/little_loops/loops/autodev.yaml`: retargets, 42 deletions, the `dequeue_next`
  pass-id write, and the `copy_broke_down` shrink
- `scripts/little_loops/run_record.py`: the shared record-writing helper
  (the module, `prep` registration and shared helper land in ENH-3630)
- `scripts/little_loops/fsm/persistence.py` (`PersistentExecutor.resume()`): the
  removed-state resume guard

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/auto-refine-and-implement.yaml` and
  `scan-and-implement.yaml` call `loop: autodev`. Their counts must not change beyond
  the accepted changes.
- `little_loops.autodev_summary` (ENH-3619) reads the ledgers the policy writes.
- `little_loops.cli.issues` `next-obligation`, `check-design`, `check-gate`,
  `check-readiness` and `format-check`: the snapshot reuses their helpers.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml` is the only `loop: prepare-issue` caller (`refine_current`, ~:503). Its `--writer prepare-issue` record reads (~:527, ~:692), the ladder-stop ledger writes (`--writer prepare-issue --legacy-class`, ~:995, :2360, :2366, :2710, :2732, :2739, :2834) and a `run-record clear` (~:2481) all move into `prep apply` or the `RUN_CHILD` precondition [Agent 1 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `resolve_issue` `rm -f`s `refine-terminal-class` (:181) on every child entry, overlapping the `RUN_CHILD` "clear records" precondition; the file's comments naming autodev states (:1057, :1485, :1523) go stale [Agent 1+2 finding]
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — comments naming autodev states (:4, :53, :72, :145, :190) and the `autodev-reentry-DECISION-<ID>` / `decide-options-deposited` markers (:92, :253); the markers stay (ENH-3600 scope), the comments go stale [Agent 1+2 finding]
- `scripts/little_loops/loops/recursive-refine.yaml` has its own same-named `size_review_snap` / `check_broke_down` states (:213, :356, :391-392, :461-474): out of scope, but any state-name absence test must be scoped to `autodev.yaml` [Agent 2 finding]
- `scripts/little_loops/fsm/validation/_base.py:133`, `fsm/schema.py` (:1496, :1645, :1769) and `fsm/validation/reachability.py:431-435` — `capture_reachability_ok` is a schema-accepted key suppressing the reachability warning; it stays in the schema (`goal-cluster.yaml:24`, `examples-miner.yaml:25` use it), only autodev drops it [Agent 2 finding]
- `scripts/little_loops/cli/issues/__init__.py` `main_issues()` — the epilog list (`next-obligation` :158, `check-gate` :166, `run-record` :189) and the dispatch chain (`check-gate` :1101, `next-obligation` :1109, `run-record` :1119) both need a `prep` entry [Agent 2 finding]
- `scripts/little_loops/cli/issues/run_record.py` — `cmd_run_record_forward` loses its only production callers (`forward_done` / `forward_stop`); keep or retire it deliberately [Agent 2 finding]
- `scripts/little_loops/cli/issues/check_gate.py:10` and `issue_parser.py` (:655, :2181) — docstrings/comments citing `select_obligation_pre_implement` and `check_reconcile_needed`; refresh [Agent 2 finding]

### Similar Patterns

- `little_loops.fleet_improve` (thin shell → module)

### Tests

- New:
  - `scripts/tests/test_preparation_policy.py` (new): `decide()` table tests
  - `test_preparation_policy_parity.py` (pinned + differential)
  - `test_preparation_policy_resume.py` (subset by default; full matrix opt-in/slow)
  - `preparation_policy_harness.py`
- Extended:
  - `scripts/tests/autodev_harness.py`: the `"state#N"` fault points,
    `Crash.replay_same` and `inner_calls` from the spike
- Rewritten or relocated:
  - `test_prepare_issue.py`, `test_builtin_loops.py::TestAutodevLoop` (second-pass
    cluster), `test_autodev_decision_gate.py`, `test_autodev_loop.py`,
    `test_autodev_scores_freshness.py`, `test_spike_verdict_routing.py`,
    `test_autodev_ladder_run_records.py`, `test_autodev_proof_reentry.py`,
    `test_fsm_topology.py`, `test_run_record.py`, and the interpolation baseline JSON
- Must pass unchanged except for the accepted changes:
  - `test_autodev_characterization.py` (ENH-3618)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_autodev_characterization.py` — "unchanged" does not hold for the wrapper-shape pins: `test_autodev_resume_characterization` (~:897) parametrizes `wrapper_path` tuples such as `("clear_record", "run_refine_to_ready", *WRAPPER_DONE)`, and `test_harness_accepts_replacement_prepare_issue_and_autodev_transform` (~:920) pins the `prepare-issue.yaml` path. Define a `wrapper_path` mapping onto dispatch-loop states; the file is `slow`-marked (:39) [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — beyond the `TestAutodevLoop` cluster [Agent 2+3 finding]:
  - `TestBuiltinLoopFiles` exemption dict (:102-107) `("prepare-issue.yaml", "forward_done", "on_error"): "ENH-3605"` goes stale when `forward_done` is deleted
  - `test_prepare_issue_loop_state_declares_no_rate_limit_handling` (~:7740) must stay scoped to `run_child`, since the slash-command states gain rate-limit handling
  - `TestConfidenceGateThresholdsNotHardcoded` (~:20821, `LOOPS` includes `prepare-issue`) requires no threshold literals in `context:`; pass thresholds through `seed_confidence_thresholds`
  - `TestInterpSweepBaseline.test_completeness_guard` (~:20515) fails both ways as states are deleted and added
  - `TestBuiltinLoopReferencesResolve` (~:17062) must resolve `loop: refine-to-ready-issue`; `TestAutodevAuthGuard` (~:17712), `TestLearningGateConsistency` (~:18019) and `TestAutodevRnImplementDeferralParity` (~:9234) load `autodev.yaml` and may name removed states
- `scripts/tests/test_prepare_issue.py` — `test_every_write_uses_prepare_issue_writer` (:113) conflicts with `prep apply` as sole writer; `mark_inner_error` sentinel pin (:162) requires `prep apply` to keep writing `refine-terminal-class` [Agent 2+3 finding]
- `scripts/tests/test_fsm_topology.py:291` — `test_autodev_topology` pins `len(topo["states"]) == 87`; add the delta comment near :239-290 and extend the edge-endpoint check (:297-302) with removed-target assertions [Agent 2+3 finding]
- `scripts/tests/test_fsm_fragments.py` (~:998-1013) — `test_builtin_loops_load_after_migration` lists `prepare-issue.yaml`; the new YAML must still validate with fragment shell exits [Agent 1+3 finding]
- `scripts/tests/test_fsm_validation_reachability.py` — 12 `capture_reachability_ok` hits; add a case for autodev without it [Agent 2 finding]
- `scripts/tests/test_feat3573_quality_gate.py` (:24) and `test_ll_issues_check_gate.py` (:22, :168-192, :382-391) — load real autodev state actions; they break if they name a moved state [Agent 1+3 finding]
- `scripts/tests/test_run_record.py` — `test_ready_iff_check_passed_would_pass` (:456-467) and `TestOutcomeMapping` (:238) pin `outcome_from_legacy_class`; keep green through the shared-helper refactor. `TestRunRecordForward` (:871+) stays valid unless `forward` is retired [Agent 2+3 finding]
- `scripts/tests/autodev_harness.py` — `PREPARE_ISSUE_YAML` (:77), the `mark_inner_error` comment (:121), fixture `rm -f refine-terminal-class` (:133), `wrapper_path` detection from `loop == "prepare-issue"` (:895-896, :968) and `_read_token` (:1022-1024); `_CLI_SERVER` (:599-603) serves a `prep` group registered in `main_issues` automatically [Agent 1+2+3 finding]
- `scripts/tests/test_wiring_reference_docs.py` — `DOC_STRINGS_PRESENT` (:256-264) needs rows for a `#### \`ll-issues prep\`` heading and API.md `| \`prep\` |` / `little_loops.preparation_policy` rows (`run-record` ENH-3597 rows are the precedent) [Agent 3 finding]
- `scripts/tests/test_cli_claims.py` / `test_cli_surface.py` (:158) — prose claims about `ll-issues prep …` are checked against the scraped real `--help`; register the group before docs cite it (the `ll-prose-ok` markers cover the interim) [Agent 2+3 finding]
- New tests to add: `prep` help/epilog test (copy `test_run_record.py::test_subcommand_in_help` :450 and the one-class-per-subcommand layout, `TestCmdRunRecordWrite` :296); `decide()` table tests (nearest precedent `test_ll_issues_next_obligation.py` parametrized classes; no pure `decide(snapshot, facts)` test exists); parametrized removed-state absence test (`TestConfidenceGateThresholdsNotHardcoded` shape); "no `rm`" / "never appends `autodev-staged.txt`" wrapper scans (`test_builtin_loops.py` ~:3226 `not in state["action"]` style); `capture_reachability_ok` absence test; `max_steps` arithmetic structural test
- Resume-matrix opt-in: `slow` is not deselected by default (`scripts/pyproject.toml` ~:296-302; `addopts` has `--timeout=120 -n logical --dist loadfile`), so "opt-in" needs `slow` plus an env-var or `skipif` gate and `@pytest.mark.timeout` as in `test_autodev_characterization.py:919`; a single >120 s shell-out test orphans its xdist worker [Agent 3 finding]

### Documentation

- `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/guides/LOOPS_REFERENCE.md`,
  `docs/ARCHITECTURE.md`, `docs/reference/DEFERRAL_CODES.md`, plus the ENH-3606 § Docs
  list

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `ll-issues prep` section, plus stale state names in the `next-obligation` (~:2271) and `check-readiness` (~:2922) sections and the `run-record write` `--legacy-class` row (~:2426) [Agent 2 finding]
- `docs/reference/API.md` — `prep` row beside `run-record` (~:4667), `little_loops.preparation_policy` section, and the `run_record` module row (~:74) [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — two copies of the autodev tree (~:1070, ~:1198), `Score gate` prose (~:1148) naming `check_broke_down`, and the `prepare-issue` row (:82) describing the old forwarding behavior [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:458` — lists `prepare-issue` among the loops using the confidence-gate thresholds [Agent 1 finding]
- `scripts/little_loops/loops/README.md` — `prepare-issue` (:31) and `autodev` (:35) catalog rows [Agent 1+2 finding]
- `skills/audit-loop-run/SKILL.md` (:271, :277) and `skills/go-no-go/SKILL.md` (:154, :402) — name `check_go_no_go_eligible`, `run_go_no_go`, `check_go_no_go_waiver`, `recheck_set`; `commands/reconcile-issue.md` (:83, :145-146, :197, :368) cites the `check_reconcile_needed` one-shot guard, which becomes a fact-log rule; regenerate host mirrors with `ll-adapt` after skill edits [Agent 2 finding]

### Configuration

- N/A. No schema or config change; `run_record.py` already accepts the `prepare-issue`
  writer.

### Behavior Parity

`prepare-issue.yaml` is replaced in place, so its current behaviors are enumerated here.

| Artifact | Behavior | Disposition |
|---|---|---|
| `scripts/little_loops/loops/prepare-issue.yaml` | `clear_record` clears stale `prepare-issue` and `refine-to-ready-issue` records on every entry | changed: becomes the `RUN_CHILD` precondition in `prep step` |
| `scripts/little_loops/loops/prepare-issue.yaml` | `run_refine_to_ready` runs `refine-to-ready-issue` as a `loop:` child with `context_passthrough` | preserved: the `run_child` state |
| `scripts/little_loops/loops/prepare-issue.yaml` | `forward_done` forwards the child's typed record under the `prepare-issue` writer | changed: `prep apply` writes the terminal record |
| `scripts/little_loops/loops/prepare-issue.yaml` | `forward_stop` forwards the record and ledgers `refine_failed` for `BLOCKED:quality` / `DEFERRED:gate_unmet` | changed: `prep apply` writes the ledger row per the terminal table |
| `scripts/little_loops/loops/prepare-issue.yaml` | `mark_inner_error` writes an infra record plus the `refine-terminal-class` sentinel | changed: `RETRYABLE_ERROR:infra` through `prep apply`; the sentinel stays until ENH-3600 removes its reader |
| `scripts/little_loops/loops/prepare-issue.yaml` | `max_steps: 20`, `on_handoff: spawn`, `scope`, `shared_state_ok: false` | changed: `max_steps` derived from the ladder budgets; the rest preserved |
| `scripts/little_loops/loops/prepare-issue.yaml` | no rate-limit handling on the `loop:` state (BUG-3390) | preserved for `run_child`; dropped for slash-command states, which gain `mark_rate_limited` (BUG-3622) |

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **Current-state facts for the port** (verified against the tree; `autodev.yaml` has 87 states, pinned by `test_fsm_topology.py`):
  - `prepare-issue.yaml` has 6 states (`clear_record`, `run_refine_to_ready`, `forward_done`, `forward_stop`, `mark_inner_error`, `done`/`failed`), no `context:` block (the ID arrives through `context_passthrough` as `${context.input}`), no `on_max_steps`, and `max_steps: 20`. `run_refine_to_ready` deliberately has no `on_no` (BUG-2611) and no timeout. `cmd_run_record_forward` (`cli/issues/run_record.py`) rewrites the source record with `replace(record, writer=args.writer)` and prints `MISSING` without writing when the source is absent.
  - `autodev.yaml` today: `check_passed` uses `fragment: harness_exit` with `on_yes: select_obligation_pre_implement`, `on_no`/`on_cannot_judge: select_obligation_post_refine`, `on_error: detect_children`; `refine_current` is `loop: prepare-issue` (`on_success: count_repair_cycle_refine`, `on_failure: route_refine_outcome`, `on_error: skip_inflight_infra`); `route_refine_success` routes `DECOMPOSED` → `detect_children` and `READY`/`BLOCKED`/`MISSING` → `check_passed`. `check_proof_defer_or_implement`, `size_review_snap`, `check_broke_down`, `check_parent_resolved`, `recover_subloop_children`, `enqueue_children`, `mark_scores_absent_infra`, `skip_inflight`, `skip_inflight_infra`, `ledger_child_stop`, `skip_cancelled` and `finalize_rate_limited` all exist. `capture_reachability_ok: true` is a top-level setting (no state references it) and its comment names `check_guard2_verdict` via `check_broke_down`. `dequeue_next` (`fragment: queue_pop`) already resets the per-issue markers the spike's aggregates table maps to facts; it has no `prep-pass-<ID>` write yet.
  - **`ll-issues` registration**: subcommand groups register in `cli/issues/__init__.py:main_issues()` via `add_<x>_parser(subs)` plus an `if args.command == …` dispatch chain and an epilog list; `run-record` is the precedent for a group with sub-subcommands (`subsubs = p.add_subparsers(dest="run_record_command", required=True)`). The test harness's fork server (`scripts/tests/autodev_harness.py:_CLI_SERVER`) keys only on `main_issues`/`main_config`, so a group registered in `main_issues` is served without a separate registry.
  - **Record-writing logic is not yet shared**: assembly (path resolution, frontmatter parse, `readiness_status`, `thresholds_met`, `derive_child_ids`, `_read_broke_down`, `RunRecord` build) lives inline in `cmd_run_record_write`; reusable pieces are `derive_child_ids`, `canonical_record_id`, `outcome_from_legacy_class(legacy_class, broke_down, thresholds_met, status)` and `write_run_record`. `run_record.py` `WRITERS` already includes `prepare-issue`.
  - **Snapshot helpers and their real locations**: `select_next_obligation(config, issue_id, *, skip=(), readiness_override=None, outcome_override=None, honor_waiver=False) -> ObligationResult | None` (`cli/issues/next_obligation.py`; raises `ObligationProbeError` fail-closed); `resolve_gate_verdict(frontmatter, text, spike_proven)` (`cli/issues/check_gate.py`); `readiness_status(config, issue_id, *, …) -> ReadinessStatus | None` (`cli/issues/check_readiness.py`); `superseded_marker_count(issue_path)`, `check_format_gaps` and `design_gate_failed(gaps)` (`issue_parser.py`; `cmd_check_design` composes the last two); Program Design grading in `issues/program_design.py`. `session_command_counts` is a **field on the parsed issue dataclass** populated by `count_session_commands(content)` (`session_log.py`), not an `IssueParser` method.
  - **Spike artifacts**: `thoughts/spikes/preparation-policy-spike.md` exists; branch `spike/preparation-policy` exists at `a5162130240f244ad79ae4354470e903e01769b2` (also checked out in a worktree under `.git/worktrees/`). `little_loops.preparation_policy`, the `prep` group, `test_preparation_policy*.py` and `preparation_policy_harness.py` do not exist; `autodev_harness.py` has no `state#N`, `replay_same` or `inner_calls`.
  - **Executor constraints bearing on `record_step` and the dispatch loop** (`fsm/executor.py`): a `loop:` child's captures overwrite `captured[<state>]` only when the child captured something and `context_passthrough`/`with_` is set; `terminated_by` is always set and `failure_terminal` only when the child produced one, so a stale `failure_terminal` from an earlier pass can survive a later child that captured nothing. `on_max_steps` runs exactly one handler state (`_summary_state_executed`), flushing one pending non-loop state first. Since BUG-3622, `next:` states go through `_intercept_transient_failure` (429 retries refund `_throttle_counts`; exhaustion routes `on_rate_limit_exhausted` else `on_error`), but the `loop:` delegate path does not — consistent with the BUG-3390 comments in both YAMLs, so `run_child` stays without rate-limit handling.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Register `prep` in `cli/issues/__init__.py`: parser, dispatch branch and epilog entry
- Decide whether `ll-issues run-record forward` survives once `forward_done` / `forward_stop` are gone
- Make `prep apply` (or the `RUN_CHILD` precondition) own the `refine-terminal-class` sentinel writes that `mark_inner_error` does today, until ENH-3600 removes the reader
- Update the `test_fsm_topology.py` count, the `TestBuiltinLoopFiles` exemption dict, `loop_interpolation_baseline.json` and `MR11_MARKER_ALLOWLIST` together
- Rework the characterization suite's `wrapper_path` fields for the dispatch-loop state names
- Add `test_wiring_reference_docs.py` rows for the new CLI.md / API.md sections
- Refresh comments naming removed autodev states in `refine-to-ready-issue.yaml`, `oracles/resolve-decision.yaml`, `check_gate.py`, `issue_parser.py`
- Run `ll-adapt --host <gemini|kimi-code|qwen> --apply` after the skill edits

## Program Design

### Types

- `StepKind: enum` — `RUN_CHILD`, `WIRE`, `REFINE_GAP`, `RESCORE`, `RECONCILE`, `SIZE_REVIEW`, `GO_NO_GO`, `FINISH`, `STOP`
- `Step: dataclass` — frozen; `(kind, seq, payload, reason, evidence, observations)`, the next action `decide()` returns
- `IssueSnapshot: dataclass` — read-only view of the issue file, config and gate verdicts, built lazily
- `Facts: dataclass` — parsed `run_dir/prep-facts/<ID>.jsonl` (intent / done / obs lines, keyed by `(pass, seq, kind)`)

### Signatures

- `decide(snapshot: IssueSnapshot, facts: Facts) -> Step` — pure; checkpoint → rule-order table, no I/O
- `next_preparation_step(config: BRConfig, issue_id: str, run_dir: Path, *, readiness_threshold: int, outcome_threshold: int) -> Step` — snapshots the issue, loads the facts, calls `decide`
- `load_facts(run_dir: Path, issue_id: str) -> Facts` — reads the append-only fact log, deduplicating by `(pass, seq, kind)`
- `append_fact(run_dir: Path, issue_id: str, fact: Fact) -> bool` — appends one JSONL line unless `(pass, seq, kind)` (obs: content too) already exists; returns whether it wrote
- `apply_terminal(config: BRConfig, issue_id: str, run_dir: Path, step: Step) -> str` — the sole terminal writer; runs the ledger row (keyed `(pass, seq)`, check-before-append), `set-status`, run record and inflight clear in order, each idempotent, and returns the terminal token
- `record_step(config: BRConfig, issue_id: str, run_dir: Path, *, guard2: bool = False) -> None` — writes the done fact and repair-cycle projection; classifies the child outcome from `run-records/refine-to-ready-issue/<ID>.json`, never from `captured.run_child`

### Call Path

`prepare-issue.yaml:select_step` -> `ll-issues prep step` -> `next_preparation_step` -> `select_next_obligation` / `load_facts` -> `decide`

## Impact

- **Priority**: P3. Completes the second-pass consolidation under EPIC-3565, fixes
  resume for the preparation ladder, and unblocks ENH-3600 and ENH-3590.
- **Effort**: Large. A ~1,300-line module port with hardening, a 15-state loop, 42
  autodev deletions, and a large test/doc migration. It is smaller in risk than
  ENH-3606's graph move, because the spike already proved parity and resume.
- **Risk**: Medium. It rewrites the second-pass routing of the most-used loop. Mitigated
  by the ENH-3618 characterization suite, the promoted parity/differential/resume tests
  and the table-tested `decide()`. The spike's parity is coverage-bounded (about 25
  inline predicates re-implemented), so port the shell-level tests before deleting the
  YAML.
- **Breaking Change**: No public interface change. The accepted behavior changes add or
  reclassify ledger rows and record tokens only.

## Scope Boundaries

- **In scope**: consuming ENH-3630's `little_loops.preparation_policy` and `prep`
  subcommand group (built there, not here); the resume guard for removed states; the
  dispatch loop replacing `prepare-issue.yaml`; the autodev retargets, deletions and pass-id
  write; test migration; docs; the Q1/Q3/run-terminal-capture decisions insofar as the
  port depends on them.
- **Out of scope**:
  - widening the go/no-go trigger (it stays the deterministic `oversized_atomic`
    predicate);
  - removing ledgers, queue/closure accounting files or the child-written markers
    (ENH-3600);
  - new `PreparationOutcome` values or run-record tokens;
  - changes to `refine-to-ready-issue.yaml`;
  - `recursive-refine.yaml`'s same-named states;
  - unifying preparation across `recursive-refine` and the `rn-*` loops;
  - the advise consult (ENH-3590).

## Acceptance Criteria

- [ ] Parity with the ENH-3618 characterization suite on every pinned scenario, compared
  on these fields: skipped rows (order), queue, staged/passed/unverified, dequeue order,
  record tokens, status / `deferred_reason`, `summary.json`, slash-command sequence,
  repair-cycle counter, `ll-auto` calls and ledgers. The only differences allowed are
  the enumerated accepted changes above, and each one has its own test (no vacuous
  allowances). The wrapper-shape pins (`wrapper_path` tuples in
  `test_autodev_resume_characterization`, the `prepare-issue.yaml` path pin) are
  remapped onto dispatch-loop state names; that remapping is not a behavior difference.
- [ ] No autodev state is in the removed set (39 moved + 3 deleted); a parametrized
  absence test is built from the verified 39-state list. No autodev edge targets a
  removed state, and no autodev event enters a policy-owned step.
- [ ] Crash/resume subset: at each covered crash point (before/after every runner call
  of the wrapper and inner action states), `PersistentExecutor.resume()` yields
  artifacts and counters identical to an uncrashed run, with ≤ 1 replayed command. The
  full matrix passes when opted in.
- [ ] `decide()` has table tests covering every row of the checkpoint → rule-order table,
  H1–H4, the budget rules and the ported shell predicates.
- [ ] The dispatch loop has exactly 15 states (stated in the YAML comment and pinned by a
  structural test), contains no `rm`, never appends to
  `autodev-staged.txt`, and `prep apply` is the only writer of ledger rows, status and
  run records inside it.
- [ ] `ll-loop validate prepare-issue` and `ll-loop validate autodev` pass (autodev
  without `capture_reachability_ok`).
- [ ] Rate-limit exhaustion in any wrapper slash-command state halts autodev through
  `mark_rate_limited` → `finalize_rate_limited`, with a real-FSM test per step kind.
- [ ] The design rule reads the current check-design verdict: a fixed design is never
  deferred `design_gate_failed` (BUG-3620 regression test).
- [ ] The contradiction trigger reads `superseded_marker_count` even when format-check
  exits 1 (Q1 semantics, BUG-3624): `snapshot_issue` reads markers from the payload
  whatever `has_blocking_gaps` is, not `markers = 0 if has_blocking_gaps`.
- [ ] `max_steps` and the per-pass cap are derived from the ladder budgets
  (`max_steps = 4 × cap + 3`, counting 4 states per `SIZE_REVIEW` step), with the
  arithmetic in a comment and a structural test that reads the constant ENH-3630 exports.
- [ ] A step-cap cutoff (`terminated_by=max_steps` after the `apply_outcome` handler)
  records `RETRYABLE_ERROR:infra` and reaches autodev's `skip_inflight_infra` through
  `route_refine_outcome` (real-FSM test).
- [ ] Resuming a persisted run whose `current_state` no longer exists in the loop fails
  with a clear error, not a `KeyError` (test).
- [ ] Crash injection inside `prep apply` (between each of the ledger row, `set-status`,
  run record and inflight clear writes) followed by resume never double-appends a ledger
  row and ends with one terminal.
- [ ] `apply` writes the `refine-terminal-class` sentinel on every `failed`-bound
  terminal until ENH-3600 removes its reader (test).
- [ ] The first-gate Program Design rule chosen by ENH-3625 is encoded in the `decide()`
  row after a `RUN_CHILD` done fact, in autodev's surviving `check_passed`, and in the
  run-record `ready` predicate; ENH-3625's parity test stays green across the cutover.
- [ ] `prep record` classifies the child outcome from
  `run-records/refine-to-ready-issue/<ID>.json`, not from `captured.run_child`; a test
  seeds a stale `failure_terminal` capture and shows it is ignored.
- [ ] Autodev keeps `max_steps: 500`; accepted change 6 is documented in
  `LOOPS_REFERENCE.md`.
- [ ] The autodev topology count in `test_fsm_topology.py` equals the number recorded in
  the delta comment.

## Status

**Open** | Created: 2026-09-27 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-27; re-scored 2026-09-27T04:31Z (Dependencies override cleared). Superseded in part by the 2026-09-27 review: Phase A split into ENH-3630 (`blocked_by`), so re-score after that lands._

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 58/100 → LOW

### Concerns
- `format-check` flags `ll-issues prep (no such subcommand)` as a stale CLI claim (caps Criterion 4 at 10). It is forward-looking (this issue proposes the group) and already carries `ll-prose-ok` markers at three sites; the flag clears once `prep` is registered. Advisory only.
- Phase A/B/C phasing is stated, but only Phase A is safe to start alone; the atomic cutover (Phase B) is where the risk sits.

### Gaps to Address
- None blocking. The prior Dependencies override is cleared: no `blocked_by` remains, and BUG-3624, ENH-3625, ENH-3621, BUG-3620 and BUG-3622 are all `done` (BUG-3628 is `open` but only `relates_to`).

### Outcome Risk Factors
- Deep per-site complexity: replaces the second-pass routing of the most-used loop (`prepare-issue.yaml` in place, 42 autodev deletions), with all projects on this machine `local-editable`, so a half-landed cutover breaks tooling everywhere.
- Broad enumeration across 16+ sites (new module, `cli/issues`, two loop YAMLs, `run_record.py`, ~15 test files, ~8 docs, skill mirrors) and 11+ dependents, with a spike-parity that is coverage-bounded (~25 inline predicates re-implemented).

## Session Log
- `/ll:confidence-check` - 2026-09-27T04:31:27 - `783ea3bb-f6c1-4581-a4e3-94421a4eb0f1.jsonl`
- `/ll:ready-issue` - 2026-09-27T04:16:14 - `cc063681-f3cf-42c2-b056-46a3321df1ee.jsonl`
- `/ll:confidence-check` - 2026-09-27T03:42:23 - `7853641e-1dad-4830-bad1-b40be31584c3.jsonl`
- `/ll:wire-issue` - 2026-09-27T02:33:29 - `951684ed-7b41-4bf8-9307-a4474a28eb29.jsonl`
- `/ll:refine-issue` - 2026-09-27T02:22:39 - `e00c47b1-36f2-4288-9df3-a5c841c33968.jsonl`
- `/ll:format-issue` - 2026-09-27T02:13:30 - `eab069d8-1487-4826-8057-122a54e92dfd.jsonl`
