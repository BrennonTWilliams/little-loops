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
blocks:
- ENH-3600
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
<!-- ll-prose-ok: the prep subcommand group is proposed by this issue, not yet implemented -->
- writers kept separate from decisions, behind `ll-issues prep {step,record,apply,explain}`;
- a ~15-state dispatch loop that replaces `prepare-issue.yaml` in place.

This issue supersedes ENH-3606. ENH-3606's still-valid decisions carry over (terminal
table, ledger ownership, DECOMPOSED guarantee, queue ownership, accepted behavior
changes, boundary retargets, the three autodev deletions). Its graph-relocation
mechanics are dropped: the ~55-state wrapper, `route_inner_success`,
`detect_ladder_children`, `route_ladder_stop`, the `mark_*` terminals, the 250-step
arithmetic, and the `count_repair_cycle_refine` → `clear_record` entry chain. Each of
those becomes a rule, a precondition or an `apply` outcome.

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

- `prepare-issue.yaml` is a dispatch loop of at most ~15 states. It asks the policy for
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
    `superseded_marker_count` and `IssueParser.session_command_counts`.
- **Fact log** `run_dir/prep-facts/<ID>.jsonl`, with lines `{pass, seq, kind:
  intent|done|obs, step, payload}`. It is append-only and idempotent by
  `(pass, seq, kind)` (obs lines also by content). It replaces the handshake files; the
  mapping is the spike's aggregates table. The repair-cycle count is derived from done
  facts; the file stays only as a projection.
- **Pass id**: autodev's `dequeue_next` increments `run_dir/prep-pass-<ID>`. That is the
  only new autodev write.
<!-- ll-prose-ok: the prep subcommand group is proposed by this issue, not yet implemented -->
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
    `check_passed` is the only writer of `autodev-staged.txt`).

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
    `failed`.
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
  5. a wrapper step-cap cutoff ledgers `refine_failed_infra`.

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
     remedies), and set `max_steps ≈ 3 × cap + 3`. The spike's fixed 15 is below the
     legal worst case.
   - Make `apply`'s row append and its `apply_progress` obs one atomic write, or key the
     rows by `(pass, seq)`, so a crash inside `apply` cannot double-append a row.
2. **CLI and docs.**
   <!-- ll-prose-ok: the prep subcommand group is proposed by this issue, not yet implemented -->
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
   - Update the `test_fsm_topology.py` autodev count with a delta comment.
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
5. **Decisions to take in this issue, or before it:**
   - **Q1**: the format-check exit code masks the contradiction trigger. Captured as its
     own BUG. The port must use the fixed semantics: markers are read from the payload
     whatever the exit code.
   - **Q3**: the first-gate Program Design rule. Captured as its own ENH. Implement
     whichever rule it decides.
   - **Run-terminal capture for `record_step`**: the executor merges child captures into
     `captured.run_child` only when the child captured something, so a stale
     `failure_terminal` can survive. Get a stable executor-provided capture, or spend 2
     of the ~15 states on three record states.
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
- `scripts/little_loops/loops/prepare-issue.yaml`: replaced in place by the dispatch loop
- `scripts/little_loops/loops/autodev.yaml`: retargets, 42 deletions, the `dequeue_next`
  pass-id write, and the `copy_broke_down` shrink
- `scripts/little_loops/run_record.py`: the shared record-writing helper

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/auto-refine-and-implement.yaml` and
  `scan-and-implement.yaml` call `loop: autodev`. Their counts must not change beyond
  the accepted changes.
- `little_loops.autodev_summary` (ENH-3619) reads the ledgers the policy writes.
- `little_loops.cli.issues` `next-obligation`, `check-design`, `check-gate`,
  `check-readiness` and `format-check`: the snapshot reuses their helpers.

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

### Documentation

- `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/guides/LOOPS_REFERENCE.md`,
  `docs/ARCHITECTURE.md`, `docs/reference/DEFERRAL_CODES.md`, plus the ENH-3606 § Docs
  list

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

### Call Path

`prepare-issue.yaml:clear_record` (replaced by `select_step`) -> `next_preparation_step` -> `select_next_obligation` / `load_facts` -> `decide`

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

- **In scope**: `little_loops.preparation_policy` and the `prep` subcommand group; the dispatch
  loop replacing `prepare-issue.yaml`; the autodev retargets, deletions and pass-id
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
  allowances).
- [ ] No autodev state is in the removed set (39 moved + 3 deleted); a parametrized
  absence test is built from the verified 39-state list. No autodev edge targets a
  removed state, and no autodev event enters a policy-owned step.
- [ ] Crash/resume subset: at each covered crash point (before/after every runner call
  of the wrapper and inner action states), `PersistentExecutor.resume()` yields
  artifacts and counters identical to an uncrashed run, with ≤ 1 replayed command. The
  full matrix passes when opted in.
- [ ] `decide()` has table tests covering every row of the checkpoint → rule-order table,
  H1–H4, the budget rules and the ported shell predicates.
- [ ] The dispatch loop has ≤ ~15 states, contains no `rm`, never appends to
  `autodev-staged.txt`, and `prep apply` is the only writer of ledger rows, status and
  run records inside it.
- [ ] `ll-loop validate prepare-issue` and `ll-loop validate autodev` pass (autodev
  without `capture_reachability_ok`).
- [ ] Rate-limit exhaustion in any wrapper slash-command state halts autodev through
  `mark_rate_limited` → `finalize_rate_limited`, with a real-FSM test per step kind.
- [ ] The design rule reads the current check-design verdict: a fixed design is never
  deferred `design_gate_failed` (BUG-3620 regression test).
- [ ] The contradiction trigger reads `superseded_marker_count` even when format-check
  exits 1 (Q1 semantics).
- [ ] `max_steps` and the per-pass cap are derived from the ladder budgets, with the
  arithmetic in a comment and a structural test.

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-27T02:13:30 - `eab069d8-1487-4826-8057-122a54e92dfd.jsonl`
