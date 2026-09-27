---
id: ENH-3600
type: ENH
title: Drive autodev ledger from run records and remove preparation handshake files
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T18:51:51Z'
blocked_by: []
parent: EPIC-3565
relates_to:
- ENH-3577
reconcile_attempted: true
confidence_score: 90
outcome_confidence: 73
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 18
---

# ENH-3600: Drive autodev ledger from run records and remove preparation handshake files

## Summary

Build on the `little_loops.autodev_summary` module that ENH-3619 extracts from
`finalize_done`. Add per-issue `prepare-issue` run records to its inputs so that an issue
which leaves preparation unaccounted for is surfaced (`record_absent`). Delete the preparation handshake files left over after ENH-3623. This
is the final step (F) of the ENH-3577 decomposition, after the routing migrations
(C, D).

## Current Behavior

`finalize_done` is a large inline shell state that stitches the verdict together from ~50
`${context.run_dir}/autodev-*` files (staged/passed/unverified/skipped/not-started/
gate-blocked/scores-absent/decision-unresolved/spike-inconclusive/proposal-unsound, plus
per-ID `*-attempted-*` / `*-retry-*` markers).

## Expected Behavior

Each issue that enters preparation produces one `prepare-issue` run record plus its
ledger rows. `finalize_done` is a thin call into `little_loops.autodev_summary`. That
module builds `summary.json` and the stdout report from those records and from the
queue, closure and skip ledgers listed in Scope Boundaries. The ledgers stay the count
source for every existing key. Records add the `record_absent` check. Preparation
markers that have no remaining reader or writer go (see Marker disposition).

## Proposed Solution

- **Re-pointed to ENH-3623 (2026-09-26)**: ENH-3606 was cancelled. ENH-3623, the policy
  dispatch loop, supersedes it, so read "ENH-3606" below as ENH-3623. Two effects:
  - Removing the `refine-terminal-class` MISSING fallback is simpler, because every
    wrapper exit goes through `ll-issues prep apply`, the sole terminal writer.
  - Re-derive the Marker disposition table against the policy design. Most per-pass
    `autodev-*` handshake files (repair-cycle count, rescore origin and retry markers,
    re-entry caps, contradiction/remedy/pending markers, size-review-ran-this-pass)
    disappear into the `prep-facts/<ID>.jsonl` fact log.

- Read per-issue run records directly from `${context.run_dir}/run-records/prepare-issue/<ID>.json`
  (ENH-3597 layout; the wrapper record is authoritative). No copy step.
- `finalize_done`'s logic already lives in `little_loops.autodev_summary` behind a thin
  shell state (ENH-3619, which also adds the `finalize_step_capped` `on_max_steps`
  handler). This issue extends that module; it does not re-extract it.
- **Missing or malformed record**: `build_summary` counts a dequeued issue with no
  record, not in flight, and in no closure or skip ledger under the additive
  `record_absent` summary key (there is no `retryable_error` summary key; the name
  refers only to the `PreparationOutcome` an absent record implies). It never drops the
  issue, and never counts it as passed.
  **`record_absent` is an invariant detector** (2026-09-27 review), like
  `record_ledger_mismatch`: every known exit already lands in another bucket, so it is
  expected to be 0 and its tests build the state synthetically.

  | Exit path | Bucket |
  |---|---|
  | Dequeue-time skip (`skip_already_resolved`, `skip_blocked`, `defer_gated`, `skip_cancelled`) | its `autodev-skipped.txt` row |
  | Wrapper terminal through `prep apply` (incl. the wrapper's `on_max_steps: apply_outcome`) | the record plus its ledger row |
  | `refine_current.on_error` | `skip_inflight_infra`'s ledger row |
  | autodev `max_steps` (`finalize_step_capped`) or rate-limit exhaustion (`finalize_rate_limited`) mid-preparation | ID still in `autodev-inflight` → `inflight_unresolved` / `abandoned` |
  | Process crash | resumed; the resumed run lands in one of the rows above |
  | ID leaves `autodev-inflight` with no record and no ledger row | `record_absent` (a bug) |
- Delete preparation markers no longer written after C and D; verify with a grep gate
  test that `autodev.yaml` references none of them.
- **Child-written `autodev-*` markers**: `refine-to-ready-issue.yaml` itself writes
  `autodev-decide-ran`, `autodev-decision-unresolved.txt`, `autodev-proposal-unsound.txt`
  and `autodev-spike-inconclusive.txt`. `auto-refine-and-implement.yaml:1112` reads
  `autodev-decision-unresolved.txt`, and `oracles/resolve-decision.yaml:249` relies on
  `autodev-decide-ran`. Migrate those readers to run records (the
  `writer: refine-to-ready-issue` record) before the child stops writing the markers, or
  keep writing the markers and list them as a documented exception.
  **Decided (2026-09-26)**: keep them as a documented exception (see Marker disposition).
  `refine-to-ready-issue.yaml` keeps writing the three child ledgers, and
  `auto-refine-and-implement.yaml` keeps counting `autodev-decision-unresolved.txt`.
  Migrating those readers is a follow-up, not part of this issue.

### Design decisions (added 2026-09-26 review)

- **Source of the dequeued-ID set** (revised 2026-09-27 review). `build_summary`
  enumerates ENH-3623's `run_dir/prep-pass-<ID>` files, which `dequeue_next` writes for
  every dequeued ID. No new ledger file and no new autodev state. Issues skipped at
  dequeue (`skip_already_resolved`, `skip_blocked`, `defer_gated`, `skip_cancelled`) do
  have a `prep-pass-<ID>` file, but each of those states writes an `autodev-skipped.txt`
  row, so the "in no closure or skip ledger" filter already excludes them. The set
  cannot come from enumerating `run-records/prepare-issue/*.json`: an issue with no
  record is missing from that directory. (Superseded: the earlier append-only
  `autodev-prepared.txt` plus a `refine_current` pre-state.)
- **Where `record_absent` is reported.** Add one additive key, `record_absent` (a
  count), to `summary.json`. It sits beside the 16 FEAT-3573-as-of keys, which are
  otherwise unchanged. Add the IDs to the stdout report as a new line. The key is
  additive and no consumer does an exact key-set match, so this is non-breaking.
  Confirm that claim against `test_auto_refine_closure_accounting.py` and
  `TestAutoRefineAndImplementLoop` before landing.
- **Precedence with the in-flight counts.** An issue listed in `autodev-inflight` when
  finalization runs is already counted as `inflight_unresolved` / `abandoned`. It is
  **not** also counted as `record_absent`. `record_absent` covers only prepared IDs that
  are no longer in flight, have no record, and appear in no closure or skip ledger. Each
  ID is counted in exactly one bucket; a unit test asserts this.
- **Record lifecycle when an ID is dequeued twice.** The wrapper's `clear_record` runs on
  every entry, so when an ID is dequeued more than once in a run, the last pass's record
  wins. The ID has one `prep-pass-<ID>` file whatever its pass count, so it counts once.
  Pin both with a test.
- **Exit codes.** `main(argv) -> int` keeps today's routing exactly: `phantom` → exit 1
  → `on_no: failed`, and any exception or unreadable input → exit 2 → `on_error: failed`.
  Every other verdict exits 0. Name them with `EXIT_*` constants (the `fleet_improve.py`
  pattern).
- **Stdout report.** `finalize_done` prints a human-readable report to stdout today: the
  Passed, Skipped, Spike-inconclusive, Proposal-unsound, Unverified, Stopped-early and
  similar lines. The Python version reproduces it line for line, plus the new
  `record_absent` line. The golden fixtures (see Tests) pin this.
- **`max_steps` exit.** Closed by ENH-3619: autodev's `on_max_steps:
  finalize_step_capped` runs the module with `--stop-reason max_steps`. `build_summary`
  applies the `record_absent` and `record_ledger_mismatch` rules on that path exactly as
  on `finalize_done`.
- **Record/ledger disagreement is counted, not printed as a warning.** When a
  `prepare-issue` record and the ledger row for the same ID disagree, the ledger row
  stays the count source (Scope Boundaries). `build_summary` adds one to an additive
  `record_ledger_mismatch` key in `summary.json` and lists the IDs on a report line. It
  never reclassifies the issue. A counted key is machine-checkable by `ll-loop audit`
  and by tests; a free-text warning line is not.
- **Removing the `refine-terminal-class` MISSING-record fallback is this issue's job.**
  ENH-3623's `prep apply` keeps the sentinel correct on every wrapper `failed` terminal
  and explicitly leaves its removal here. Today autodev's `skip_inflight` (~`autodev.yaml:584-591`)
  reads `${context.run_dir}/refine-terminal-class` to classify an issue whose
  `prepare-issue` record is `MISSING` (a `|| true` record write failed, or the wrapper
  died before writing one). Replace that read with a record-only rule: a `MISSING` /
  malformed record on the failure path is an infra outcome (`refine_failed_infra`), the
  same "absent record is never a quality verdict" rule as `record_absent`. Then delete the
  sentinel writes that exist only to feed the fallback: `prep apply`'s writes and the
  child's ~8 writers in `refine-to-ready-issue.yaml` (see Review Decisions).
  **Mechanism** (third review, 2026-09-27): see "`skip_inflight` record-only rule" under
  Review Decisions (third review).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Python-module delegation precedent (thin shell state → importable module): `python3 -m little_loops.<module> <subcommand> --run-dir ${context.run_dir}` with `main(argv) -> int` + argparse subparsers, routing on exit code — in force in `fleet-loop-improve.yaml` (10 call sites; module `fleet_improve.py`, `build_parser()` :762, `main()` :812) and `oracles/integrate-node.yaml` (3 sites; `rn_synth_queue.py`, `try_pop_ready` :109). These are the only two loops using the shape; `autodev.yaml` has zero `python3 -m` calls today — its dominant shape is `ll-*` CLI + inline heredoc Python (BUG-3339), which is what the extraction replaces.
- JSON writes go through `atomic_write_json` (`scripts/little_loops/file_utils.py:70`; `indent=2`, `allow_nan=False`, defensive re-parse, `os.replace`, parent dirs auto-created) — matches ENH-3597's atomic-write requirement for records and should serve `summary.json` too.
- Grep-gate styles in force (three, pick knowingly): whole-file `read_text()` substring assertion (`test_autodev_loop.py:983-989`, the only form that also catches marker mentions in comments — where most autodev marker references live today); per-state action scan (`test_builtin_loops.py:6732-6738`); parametrized forbidden-pattern class with a shared collector (`test_builtin_loops.py:910-949`).
- Contested convention — malformed-record tolerance: every existing per-ID JSON-directory reader silently skips bad files (`decisions.py:_load_fragments` :55-77 with its docstring naming the rule; `cli/loop/queue.py:39-45`; `cli/harness.py:2205-2210`), i.e. the record disappears from results. This issue's `record_absent` → `retryable_error` semantics are a deliberate departure from the house default — only `cli/verify_decisions.py:66-77` departs from skip (by failing hard). The unit tests must pin the departure explicitly, and the reader cannot reuse `_load_fragments`-style silent-skip semantics unchanged.
- Naming hazard: `write_summary` already exists as inline shell functions inside `rn-refine.yaml`, `rlhf-svg-refine.yaml`, and `rlhf-animated-svg.yaml` (their own unrelated summaries). A Python `little_loops.autodev_summary.write_summary` does not collide at import time, but greps for the name hit both.
- None of `build_summary`, `read_run_record`, `write_summary` (as Python), `scripts/little_loops/autodev_summary.py`, or the `run-records/` layout exists yet (repo-wide search excluding `.issues/`) — they arrive with ENH-3597/ENH-3601 (both open), matching the `blocked_by` edges. `cli/logs.py`'s `_LoopRunRecord` is an unrelated history-DB concept.

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- Conventions for the extraction, with evidence (rules, not templates): (1) a thin shell state is a one-line `python3 -m little_loops.<mod> … --run-dir ${context.run_dir}` routed on the module's exit code — `fleet-loop-improve.yaml` (10 sites) and `oracles/integrate-node.yaml:62,:138`; (2) the positive structural gate asserts the state's action contains the module invocation (`test_builtin_loops.py:21491`) — it is a substring check and does **not** assert inline logic is absent, so absence needs its own assertion; (3) module tests exercise `main(argv)` directly (`test_fleet_improve.py:328`); (4) no Python `summary.json` writer or module-level `summary.json` test exists today — current behavioral coverage runs the shell action under `bash -c` (`_run_finalize_done`, `test_builtin_loops.py` ~:7475; `test_rn_implement.py:418-453`), which stops exercising the logic once it moves.
- Contested convention: directory readers of per-ID JSON either skip bad files silently (`decisions.py:_load_fragments`, `cli/loop/queue.py`, `cli/harness.py`) or return `None` (`run_record.read_run_record`); `build_summary` sits on the `None` side and must turn `None` into a counted `retryable_error`, not a skip.
- `docs/ARCHITECTURE.md` has no loop/FSM section or parent/child contract heading; the only parent/child loop prose is a dense paragraph inside `## Parallel Mode (ll-parallel)` (:452-477). The AC "describes the parent/child contract" therefore means adding new prose (placement is the implementer's call), not editing an existing section; the end-user marker account stays in `LOOPS_REFERENCE.md`.

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **Conventions in force for the new module code** (evidence, not templates):
  - A thin shell state is one `python3 -m little_loops.<mod>` line routed on named `EXIT_*` constants (`autodev_summary.py:main`, `fleet_improve.py:main`, `oracles/integrate-node.yaml:62,:138`). The structural gate is a substring check on the action (`test_builtin_loops.py:20987`) and does not prove inline logic is absent.
  - `summary.json` additive keys are pinned by ordered key-list tests: `AutodevSummary.KEYS` with `test_summary_key_order` (`test_autodev_summary.py:262`, asserts `len == 16`) and the FEAT-3573 tail pin (`test_feat3573_quality_gate.py:683`, last 4 keys). Adding `record_absent` / `record_ledger_mismatch` changes the count those tests assert, and the golden fixtures compare bytes (compact `to_json`), so every fixture's expected summary and stdout is affected.
  - Contested: this issue's earlier finding says serialize via `atomic_write_json` (`indent=2`); the module actually writes compact JSON through `atomic_write(..., shared_mode=True)`. The byte-pinned fixtures govern.
  - Contested: per-ID JSON readers either skip bad files (`decisions.py:_load_fragments`, `cli/loop/queue.py`, `cli/harness.py`) or return `None` (`read_run_record`); `build_summary` must convert `None` into a counted `record_absent`. `record_token(None)` already maps to `MISSING`, never `READY`.
  - No existing gate restricts a marker to named states (the "allowed only in `init`/`dequeue_next` clears" rule); the existing styles are whole-file substring (`test_autodev_loop.py:980-985`, the only one that catches comments), concatenated-action forbidden list (`test_builtin_loops.py:924-956`), per-line state scan (`test_prepare_issue.py:113-118`) and bidirectional set-equality (`TestMr11MarkerSet`, `test_builtin_loops.py` ~:20795). The disposition-table gate is a new shape.

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **Correction to "every failed-bound terminal" (2026-09-27, post-landing analysis)**: `preparation_policy.py`'s `_apply_outcome` (:1162-1291) does NOT write `sentinel()` on literally every failed-bound terminal — one carve-out: the `_DEFER_STOPS` branch where the issue's frontmatter status is already resolved reroutes to the `decomposed` exit (`write(None, broke_down=True, ...)`, no sentinel), because that path isn't failure-bound anymore. Every other failure path (`child_stop` when `rec.legacy_class` is truthy, `rate_limited`, all three `_INFRA_STOPS`, the six normal `_DEFER_STOPS` cases, and the unknown-outcome fallback) does write it.
- **Sequencing convention for this kind of marker retirement** (pattern-finder, 2026-09-27): this codebase ships a marker/state retirement of this shape as two commits on the same issue — commit 1 additive only (new reader/routing lands, old markers keep being written), commit 2 deletes the old writers/states and adds per-state "stays-deleted" absence tests. Evidence: ENH-3611's `f67aa4c15` (step 1; commit body: "Old spike/decision states removed in step 2") and `423ea19b8` (step 2; commit body: "delete the 22 autodev spike/decision states ... add stays-deleted guards"), with the stays-deleted test shape itself at `scripts/tests/test_autodev_loop.py:43-48` (asserts the removed marker strings are absent from one specific state's action, not a whole-file scan). No precedent was found for deleting the old writers in the same commit that lands the new reader.

## Review Decisions (2026-09-27)

Resolved from the ENH-3623 / ENH-3600 / ENH-3625 review. These override earlier text in
this file where they conflict.

- **`refine-terminal-class` scope.** The AC is about `autodev.yaml` only: zero references
  there, and `skip_inflight` classifies `MISSING` from the record alone. The child's
  ~8 sentinel writers in `refine-to-ready-issue.yaml` become **dead writes**. They are
  removed in this issue, which makes `refine-to-ready-issue.yaml` **in scope** for this
  one change (sentinel writes, the `resolve_issue` clear, and the comments naming it).
  This supersedes the "needs no change" note in Files to Modify; the three child *ledger*
  writers still stay (documented exception). Rewrite the positive pins
  (`test_on_max_steps_is_classify_terminal` and the other sentinel pins listed in the
  research findings) in the same commit. `prep apply` stops writing the sentinel then too.
- **`record_ledger_mismatch` is an apply-atomicity detector.** After ENH-3623, `prep apply`
  writes the ledger row and the run record in one idempotent step, so a mismatch can only
  come from a crash inside `apply` that resume did not repair. Keep the key, but document
  it as that detector, expect it to be 0 on healthy runs, and do not build fixtures for a
  reachable-mismatch case beyond one crash-injection scenario.
- ~~**`autodev-prepared.txt` stays.**~~ **Reversed (2026-09-27 second review):** drop
  `autodev-prepared.txt` and its `refine_current` pre-state. `prep-pass-<ID>` covering
  dequeue-time skips is harmless, because every such skip writes an
  `autodev-skipped.txt` row and the ledger filter excludes it. "Entered preparation but
  crashed before the first `prep step`" is resumed, not finalized: a resumed run
  restarts at `refine_current`, and an abandoned run never reaches `finalize_done`. See
  the exit-path table under Proposed Solution.
- **`record_absent` is an invariant detector** (2026-09-27 second review). Document it
  like `record_ledger_mismatch`: expected 0 on every healthy run, tests build the state
  synthetically.
- **`missing_artifacts: true`** in the frontmatter predates ENH-3619 landing
  (`autodev_summary.py` now exists). Clear it or justify it at the re-score.
- **`decision_unresolved` count.** The summary key stays ledger-only
  (`autodev-decision-unresolved.txt`, child-written). autodev's own `decision_unresolved`
  stops stay under `skipped`. The Marker disposition row says so; no change to the count.
- **`write_summary` serialization.** It keeps compact JSON through
  `atomic_write(..., shared_mode=True)`, not `atomic_write_json`. The golden fixtures pin
  the bytes.
- **Program Design is "extend", not "create".** `build_summary`, `write_summary`,
  `render_report` and `main` exist from ENH-3619; this issue adds the record reader, the
  `prep-pass-*` enumeration and the two keys.
- **Doc refresh.** After ENH-3623 lands, run `/ll:reconcile-issue` to collapse the layered
  research findings into one current map (state counts, anchors), then re-score
  confidence. The 90/63 scores predate all of this.

## Review Decisions (2026-09-27, third review)

Verified against the current code. These override earlier text where they conflict.

- **Record ↔ ledger correspondence (defines "disagree" for `record_ledger_mismatch`).**
  `build_summary` checks each ID with a `prep-pass-<ID>` file against this table. A
  mismatch is a record whose token requires a row the ledgers don't have, or a row that
  the table says the record's token can never produce. Rows marked "any/none" never
  mismatch.

  | `prepare-issue` record token | Expected ledger evidence |
  |---|---|
  | `BLOCKED:quality` | an `autodev-skipped.txt` `refine_failed` row (`prep apply`'s `child_stop` → `row("refine_failed")`) |
  | `DEFERRED:gate_unmet` | an `autodev-skipped.txt` row: `refine_failed` (child stop) or the `_DEFER_STOPS` reason (`design_gate_failed`, `oversized_atomic`, `readiness_stagnated`, `low_readiness`) |
  | `BLOCKED:decision_unresolved` | the ID in `autodev-decision-unresolved.txt` (child stop) **or** an `autodev-skipped.txt` `decision_unresolved` row (wrapper `_DEFER_STOPS` stop: `decision_unresolved` / `decision_exhausted`) |
  | `DEFERRED:spike_inconclusive` | the ID in `autodev-spike-inconclusive.txt` |
  | `BLOCKED:proposal_unsound` | the ID in `autodev-proposal-unsound.txt` |
  | `RETRYABLE_ERROR:infra` | a `refine_failed_infra` row in `autodev-skipped.txt` (written by autodev's `skip_inflight_infra`, not by `prep apply`) |
  | `RETRYABLE_ERROR:rate_limited` | none required (the run halts through `finalize_rate_limited`; the ID stays in flight → `abandoned`) |
  | `READY` | any or none: a closure row (staged/passed/unverified), a not-started, gate-blocked, gate-infra or proof-gate-infra row, a `refine_failed` row (`check_passed.on_no`), or no row (`clear_inflight_after_impl_failure`, `verify_impl_closed.on_no`) |
  | `DECOMPOSED` | a `decomposed` / `resolved_by_subloop` skipped row, or a `refine_failed` row (`check_parent_resolved.on_no`) |
  | `CANCELLED` | a `cancelled` skipped row |
  | absent / malformed (`MISSING`) | not a mismatch: handled by `record_absent` when no row exists; **row present + record absent** **is** counted as `record_ledger_mismatch` |

  Crash windows inside `prep apply` (`_apply_outcome`, `preparation_policy.py` ~:1162-1291):
  the `_DEFER_STOPS` branch writes the skipped row **before** the record (crash → row, no
  record → last table row); the `child_stop` branch forwards the record **before** the
  row (crash → `BLOCKED:quality` / `DEFERRED:gate_unmet` record, no row → first two
  rows). The single crash-injection scenario in the AC uses the `_DEFER_STOPS` window.
- **`skip_inflight` record-only rule (mechanism).** `skip_inflight` is reached from
  `route_refine_outcome` (tokens `READY`, `BLOCKED`, `DECOMPOSED`, `CANCELLED`, `MISSING`,
  `_`, `_error`), `check_passed.on_no` and `check_parent_resolved.on_no`, so once the
  sentinel is gone it cannot infer the token from the route. The new action:
  1. runs the three child-ledger greps **first** (unchanged; today the sentinel check
     runs before them);
  2. then reads `ll-issues run-record read "$ID" --run-dir … --writer prepare-issue
     --format token`; `MISSING`, or a failed read (`_error`), exits 1 → `on_no:
     skip_inflight_infra` (`refine_failed_infra`);
  3. otherwise ledgers `refine_failed` as today.

  Do **not** route `MISSING: skip_inflight_infra` directly in `route_refine_outcome`: that
  skips the greps and double-counts a crash-in-apply after a child stop (the ID would land
  in both `decision_unresolved` and `refine_failed_infra`). No new state.
  Consequence to pin with a test: the success path's `MISSING` (`route_refine_success` →
  `check_passed` → `on_no` → `skip_inflight`) now ledgers `refine_failed_infra`, not
  `refine_failed`.
- **The child-ledger greps stay.** `route_refine_outcome` does not cover a `MISSING`
  record, and the greps are exactly that fallback. This resolves the Marker disposition
  row's "remove the grep if a test shows…" condition as **keep**. Reword the stale comment
  at `autodev.yaml` ~:575-577 ("ENH-3600 removes them with the markers").
- **Verdict and exit code are unaffected.** `record_absent` and `record_ledger_mismatch`
  never change `verdict` or the exit code (`compute_verdict` and `AutodevSummary.exit_code`
  are untouched). Surfacing them is the report line plus `ll-loop audit` / the
  audit-loop-run skill.
- **Ordering inside `build_summary`.** Compute `record_absent` after
  `record_abandoned_inflight()`. That call folds the in-flight ID into
  `autodev-unverified.txt` as `ID  inflight_at_finalize`, so the "in no closure ledger"
  filter excludes it with no special case. Pin the ordering with the in-flight
  precedence test.
- **Report lines are conditional.** The `record_absent` and `record_ledger_mismatch`
  lines print only when the count is > 0 (the existing `render_report` convention). The
  golden scenarios seed no `prep-pass-*` files, so both counts are 0 there and every
  `expected_stdout.txt` stays byte-identical.
- **Golden-fixture regeneration (resolves the `_generate.py` "pick one").** Keep the
  legacy oracle (`_legacy_finalize_done.sh`) frozen. `_generate.py` post-processes
  `run_legacy`'s summary by appending `,"record_absent":0,"record_ledger_mismatch":0`
  before the closing brace, so regeneration stays idempotent. Record-driven scenarios go
  in unit tests, not in the golden set.
- **Sentinel writer location correction.** `prepare-issue.yaml` has zero
  `refine-terminal-class` references; `mark_inner_error` no longer writes it. The wrapper
  writer is `preparation_policy.py`'s `sentinel()` closure (~:1207-1208), and ENH-3623's
  "temporary sentinel test" is in `test_preparation_policy_writers.py` (~:367, ~:414,
  ~:503-507). The child passes `--legacy-class` explicitly on every record write, so no
  record's `legacy_class` depends on the sentinel file.

## Sequencing

The former step 1 (behavior-identical extraction: golden fixtures, the
`little_loops.autodev_summary` module and a thin `finalize_done`) is now **ENH-3619**
(done). ENH-3619 also closes the `max_steps` summary gap. Two steps remain. Following
the repo's additive-then-delete convention (ENH-3611 `f67aa4c15` / `423ea19b8`), land
them as two commits:

1. **Additive: record-driven accounting.** The `prep-pass-*` dequeued-ID set,
   `record_absent`, the counted `record_ledger_mismatch` key (per the correspondence
   table), the dequeued-twice rule, the `_generate.py` post-process, `SUMMARY_BASE`, key
   pins, `API.md`, and the new `skip_inflight` record-only rule. The sentinel is still
   written but no longer read.
2. **Deletions: sentinel, markers and docs.** Remove the child's ~8 sentinel writers,
   the `resolve_issue` clear and the comments naming it; remove `prep apply`'s
   `sentinel()`; flip the positive sentinel pins to absence assertions; finalize the
   Marker disposition table; add the table-driven grep gate; remove dead references;
   update `README.md` / `LOOPS_REFERENCE.md` / `ARCHITECTURE.md` / `CLI.md` and the
   `--legacy-class` help text; document the child-ledger exception.

## Integration Map

_Line anchors throughout this section and the Codebase Research Findings predate
ENH-3623, which removes 42 autodev states. Treat them as historical. Refresh them,
and collapse the layered findings into one current map, when ENH-3623 lands._

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — **in scope for the sentinel only** (2026-09-27 review): remove the ~8 `refine-terminal-class` writers, the `resolve_issue` clear and the comments naming it. It keeps writing the three child ledgers as a documented exception (see Marker disposition).
- `scripts/little_loops/preparation_policy.py` (ENH-3623) — `prep apply` stops writing `refine-terminal-class`: delete the `sentinel()` closure (~:1207-1208) and its five call sites; flip ENH-3623's temporary sentinel test (`test_preparation_policy_writers.py`).
- `scripts/little_loops/loops/prepare-issue.yaml` needs no sentinel change: it has zero `refine-terminal-class` references (`mark_inner_error` no longer writes it; verified 2026-09-27).
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` needs no change. It keeps reading `autodev-decision-unresolved.txt`, and its counts must stay unchanged.
- `scripts/little_loops/autodev_summary.py` (exists, ENH-3619) — extended with the record reader and the `prep-pass-*` enumeration
- `docs/ARCHITECTURE.md` — add new parent/child contract prose (no loop/FSM section exists; placement is the implementer's call)
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` needs no change: its `autodev-decide-ran` mention (~:249) is a comment only; autodev alone writes/reads that marker (finding: "comments only (verified)")

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md` — `autodev` (:34) and `refine-to-ready-issue` (:31) catalog rows describe the run_dir marker pattern; update as markers go [Agent 1 finding]

### Tests
- **Golden fixtures** come from ENH-3619 (`scripts/tests/fixtures/autodev_summary/`). They
  must keep passing, apart from the additive `record_absent` / `record_ledger_mismatch`
  keys and their report lines.
- New unit tests for summary construction from records
- `summary.json` truthfulness on every exit (EPIC-3565 AC) incl. rate-limit exits (BUG-3567)
- Structural, rewrite: `test_builtin_loops.py` `TestAutodevLoop` (:6411; `finalize_done` behavioral coverage via `_run_finalize_done` :7216-7243 under `bash -c`, which stops exercising the logic once it moves to Python). The thin-shell gate is `test_finalize_states_are_thin_module_calls` (:7182-7200, in the same class) — it, not `test_shell_states_call_helper_module_not_inline_logic` (which is `TestFleetLoopImproveLoop`'s fleet-improve-only gate), asserts `finalize_done`/`finalize_step_capped` are each a single `python3 -m little_loops.autodev_summary` call with zero inline shell. `test_autodev_loop.py` has zero `finalize_done` references (per-iteration markers only); `test_fsm_topology.py` only pins the autodev state count (46 states as of ENH-3623's post-cutover `autodev.yaml`; this issue adds no state)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_autodev_decision_gate.py` — pins `autodev-decide-ran` in `mark_decide_ran_at_dequeue` (:160), `record_decision_unresolved`'s ledger write (:1028), design-remedy attempted markers (:732, :739), and four `on_rate_limit_exhausted == "finalize_rate_limited"` pins (:459, :471, :606, :727) — breaks as markers/routing move [Agent 1 finding]
- `scripts/tests/test_spike_verdict_routing.py` — `test_autodev_routing_table` (:107-108) asserts `autodev-spike-inconclusive.txt` in `skip_inflight` AND `init`; `test_autodev_ledgers_proposal_unsound_stop_not_as_refine_failed` (:229) pins the exact `grep -qxF "$ID" ... autodev-proposal-unsound.txt` line — both break [Agent 1 finding]
- `scripts/tests/test_auto_refine_closure_accounting.py` — seeds `autodev-passed.txt` (:116) against a real mini project (`_make_project` :43); the closest fixture precedent for `build_summary` closure tests [Agent 3 finding]
- `scripts/tests/test_recursive_finalize.py:134` — seeds `autodev-new-children.txt` [Agent 1 finding]
- `scripts/tests/test_builtin_loops.py` — breaking sites beyond `TestAutodevLoop`: `TestRefineToReadyIssueSubLoop.test_proposal_revision_failure_routing` (:3161, `autodev-proposal-unsound.txt` in action), the `autodev-decide-ran` trio (:9378, :9448, :9457), the `skip_inflight` ledger pair (:7949, :7961), `TestAutoRefineAndImplementLoop._run_finalize` harness (:5018) + literal-filename gates (:5634, :5663), the loop-state set pin (:7913), `MR11_MARKER_ALLOWLIST` (:21037, asserted :21249), and the `TestInterpSweepBaseline` bidirectional ratchet (:20974) [Agent 3 finding]
- `scripts/tests/test_fleet_improve.py` — the module-test pattern for `autodev_summary`: `main(argv)` + `EXIT_*` constants, malformed-JSON → `EXIT_ERROR` (`test_cmd_select_bad_sidecar_exit_2` :328); plus `TestFleetLoopImproveLoop.test_shell_states_call_helper_module_not_inline_logic` (:21440 in test_builtin_loops.py) — the thin-shell structural gate to imitate for the rewritten `finalize_done` [Agent 3 finding]
- `scripts/tests/fixtures/autodev_summary/_generate.py` — `generate()` records expected output by running the frozen `_legacy_finalize_done.sh` (`run_legacy`, no `record_absent` / `record_ledger_mismatch`), so re-running it would overwrite the additive-key updates. **Decided (third review)**: keep the legacy oracle frozen and post-process `run_legacy`'s summary to append `,"record_absent":0,"record_ledger_mismatch":0`; `expected_stdout.txt` is unchanged because the new report lines print only when > 0. Record-driven scenarios live in unit tests, not the golden set. `test_fixture_set_is_populated` (:70) requires set equality with `SCENARIOS` [Agent 3 finding]
- `scripts/tests/test_autodev_summary.py` — `test_matches_legacy_shell_action` (:75, byte-compares summary and stdout), `test_summary_key_order` (:262; pins `len == 16` and the last four keys, so append the new keys or change the tail pin) and `list(summary) == list(ads.AutodevSummary.KEYS)` (:92) all change; `test_step_cap_runs_finalize_step_capped_and_writes_summary` (~:278) is the real-FSM probe to extend with a `prep-pass-<ID>` file for an unrecorded, unledgered ID for the `max_steps` AC; no helper yet seeds a `run-records/prepare-issue/<ID>.json` (use `run_record.write_run_record`) [Agent 3+4 finding]
- `scripts/tests/test_preparation_policy_writers.py` (~:367, ~:414, ~:503-507) — ENH-3623's "temporary sentinel test": asserts `prep apply` leaves `refine-terminal-class` on failed-bound terminals (the `mark_inner_error` successor). Flip to absence assertions in commit 2 (third review, 2026-09-27)
- `scripts/tests/autodev_harness.py` (~:133, ~:208, ~:550) — the characterization harness's `refine-terminal-class` handling; update with the sentinel removal so `test_autodev_characterization.py` scenarios keep driving the `MISSING` route through the record, not the sentinel (third review, 2026-09-27)
- New `skip_inflight` tests (third review): greps-before-token ordering (a `MISSING` record plus a child-ledger row → no skipped row); `_error` read → `refine_failed_infra`; success-path `MISSING` (`check_passed.on_no`) → `refine_failed_infra`
- `scripts/tests/test_autodev_characterization.py` — `SUMMARY_BASE` (:150-171) is compared whole, so both new keys must be added there or every scenario fails; `inner_error` (~:773-788, `InnerRun(terminal="error", write_record=False)`) and `inner_rate_limited` (~:790-810, queued `MISSING` record that must not count as `record_absent`) are the harness precedents for the `MISSING` route; `reopen_waived` (~:375-380) has `records={ID: "MISSING"}` on an implemented issue and needs the "in a closure ledger" precedence assertion [Agent 3+4 finding]
- `scripts/tests/test_builtin_loops.py` — `test_skip_inflight_infra_sentinel_routes_to_on_no` (~:6747) is rewritten for the record-only rule; `test_skip_inflight_quality_path_writes_refine_failed` (~:6721) seeds no sentinel and now hits the `MISSING` route, so it must seed a record; `test_on_max_steps_is_classify_terminal` (~:2670) positively pins the sentinel writer in `refine-to-ready-issue` [Agent 3 finding]
- `scripts/tests/test_prepare_issue.py` (:240, :280-287 `test_missing_routes_to_skip_inflight`) and `test_run_record.py` (:866-867) — pin the `MISSING` route to `skip_inflight` [Agent 3 finding]
- ~~`scripts/tests/test_fsm_topology.py:291` — the `refine_current` pre-state adds one state~~ Superseded (2026-09-27 review): no pre-state, so no topology change from this issue [Agent 4 finding]
- `scripts/tests/test_audit_loop_run_skill.py` — `test_skill_step6a_reads_closed_implemented_cancelled_keys` (:168) is the pin pattern for a new key paragraph in the skill [Agent 4 finding]
- `scripts/tests/test_ll_issues_check_gate.py` (:382-392) pins `init` truncation and the proof-gate ledger (the `autodev-prepared.txt` pre-create it would have interacted with is superseded, 2026-09-27 review) [Agent 1 finding]
- Marker-disposition gate has no direct precedent; template is `TestMr11MarkerSet.test_marker_set_matches_enumeration` (`test_builtin_loops.py` ~:20795, bidirectional set-equality) plus a whole-file `read_text()` check for comment-only references (`test_autodev_loop.py:200-203`). Dead-marker rows that would fail today: `autodev-pre-spike-readiness.txt` (~`autodev.yaml:2076`) and `autodev-design-gate-failed` (~:170), both comment-only [Agent 3 finding]
- `scripts/tests/test_run_record.py` `TestTerminalExecution::test_mark_rate_limit_infra` (:661-667, assertion `:665`) and `TestTerminalExecution::test_classify_terminal_quality_is_blocked` (:717-744, assertion `:743`) — both assert the literal `refine-terminal-class` file content via subprocess execution of `refine-to-ready-issue.yaml` states; the issue's existing `test_run_record.py (:570, :579, :657)` citation covers only `test_record_gate_unmet` (a different test in the same `TestTerminalExecution` class) — these two were not previously listed and break when the sentinel write is removed [Agent 3 finding, verified by direct read, 2026-09-27]
- `scripts/tests/test_prepare_issue.py:105-117` (`TestStructure::test_prep_apply_is_the_only_terminal_writer`) — structural gate enumerating which `prepare-issue.yaml` states call `ll-issues prep apply`; distinct from the already-cited `:162`/`:240`/`:280-287` (the `MISSING`-route tests). The call-site set shouldn't change from this issue, but the gate should be checked and kept green [Agent 3 finding, 2026-09-27]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- `finalize_done`'s actual read set is narrower than the Summary's "~50 files": it reads the `autodev-staged/passed/unverified/skipped/gate-blocked/decision-unresolved/not-started/spike-inconclusive/proposal-unsound/spike-no-verdict` ledgers, `autodev-inflight`, `autodev-stop-reason`, and `autodev-queue.txt` (only when stop reason ≠ completed). It never reads `autodev-scores-absent.txt`, `autodev-gate-infra.txt`, or any per-ID `*-attempted-*`/`*-retry-*` marker — those are per-iteration routing state consumed by other states, invisible to the summary.
- Correction to the Proposed Solution bullet: `autodev-decide-ran` is NOT written by `refine-to-ready-issue.yaml`. The child writes its own counter (`refine-to-ready-decide-attempts` in `check_decide_attempts`, whose comment cites autodev's write-once marker as the one-attempt model). `autodev-decide-ran` is written by autodev's `mark_decide_ran_at_dequeue`/`mark_decide_ran`, cleared in `dequeue_next`, and short-circuits `decide_current`.
- `oracles/resolve-decision.yaml`'s `autodev-decide-ran` reference (~:249) is a comment documenting a behavioral dependency (autodev's one-decide-pass-per-dequeue), not a file read of the child's markers. The only genuine external file reader of the child markers is `auto-refine-and-implement.yaml`'s finalize (~:1112, counts `autodev-decision-unresolved.txt` into that loop's own summary). autodev itself reads the three child ledgers in `skip_inflight` (grep-before-`refine_failed`) and truncates them at `init`.
- The child's three autodev-ledger writers are `record_proposal_unsound`, `record_spike_inconclusive`, and `record_decision_unresolved` in `refine-to-ready-issue.yaml` — each also writes `refine-terminal-class` and defers via `ll-issues set-status`.
- Ledger lifecycle facts: `init` pre-creates 12 ledger files (single `printf '' >` each); `autodev-gate-infra.txt` and `autodev-scores-absent.txt` are append-only and NOT pre-created; `autodev-stop-reason` is written only by `finalize_rate_limited`; `autodev-passed.txt` is written only by `finalize_done` (test-enforced).
- Test locations differ from the Tests section: `finalize_done` behavioral coverage lives in `test_builtin_loops.py` `TestAutodevLoop` (:6643; `_run_finalize_done` harness :7475 executes the action under `bash -c`; promotion/phantom/no-op/rate-limit tests :7389-:7574; `test_check_passed_stages_instead_of_passes` :7459). `test_autodev_loop.py` has zero `finalize_done` references (it covers per-iteration markers); `test_fsm_topology.py` only pins the autodev state count (105). `scripts/tests/data/loop_interpolation_baseline.json` carries a `finalize_done` interpolation-baseline entry that must stay valid through the rewrite.
- `summary.json` current key set (single printf at the end of `finalize_done`): `verdict`, `closed`, `not_closed`, `skipped`, `gate_blocked`, `decision_unresolved`, `not_started`, `inflight_unresolved`, `abandoned`, `stop_reason`, `pending`, `proof_gate_infra` (12 keys; BUG-3603 added `proof_gate_infra`; ENH-3613 appends `closed_implemented`/`closed_cancelled` → 14; FEAT-3573 appends `quality_failed`/`quality_gate_infra` → 16); verdict ladder success → partial → phantom → not_started → no-op, with `rate_limit` stop reason overriding to `rate_limited`, and `phantom` exiting 1 to route `on_no: failed`. This is the FEAT-3573-as-of shape the Scope Boundary pins.

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- **Stale premise corrected**: ENH-3597 is `done` and its run-record layer is in the tree — the earlier finding that `read_run_record` / `run-records/` "do not exist yet" no longer holds. `scripts/little_loops/run_record.py`: `RunRecord` (frozen dataclass; `writer, issue_id, outcome, child_ids, evidence_refs, legacy_class, readiness, outcome_confidence`), `read_run_record(run_dir, writer, issue_id) -> RunRecord | None` (`None` on absent/malformed/OSError/non-dict/writer-or-ID mismatch), `write_run_record` (atomic), `record_path`, `RECORD_DIR_NAME = "run-records"`, `PreparationOutcome` (already includes `retryable_error`), `RunRecordWriter` (already includes `prepare-issue`). CLI writer: `scripts/little_loops/cli/issues/run_record.py` (`ll-issues run-record write`). Tests: `scripts/tests/test_run_record.py`.
- **What still does not exist**: `autodev_summary.py`/`build_summary` (zero hits), any producer of `writer=prepare-issue` records (no loop YAML writes them — that arrives with ENH-3601), and any run-record read in `autodev.yaml`. Only `refine-to-ready-issue.yaml` writes records today (`--writer refine-to-ready-issue`, ~:721, :954, :1130, :1217, :1260, :1292, :1320, :1332, :1343, :1366, :1402, :1640; stale-record clear at :184). The three child ledger writers now also emit a record: `record_proposal_unsound` (~:704), `record_spike_inconclusive` (~:1348), `record_decision_unresolved` (~:1371).
- **`finalize_done` current anchor**: `autodev.yaml:3021-3240` (routes in at :86-87, :176-177, :1411, :3018-3019; `finalize_rate_limited` :3009; terminals `failed` :3241, `done` :3244). Summary key set is now **twelve** keys — the earlier list lacks `proof_gate_infra` (printf at ~:3223-3225, fed by `autodev-proof-gate-infra.txt`, which the read-set finding also omits). Verdict ladder at ~:3201-3221; `phantom` is the only exit 1.
- **Dequeued-ID source constraint**: no cumulative "dequeued" ledger exists. `autodev-queue.txt` is head-popped by `dequeue_next` (:96-101), `autodev-inflight` holds only the last ID, `autodev-input.txt` (:56) omits later-enqueued children. `build_summary` must either enumerate `run-records/prepare-issue/*.json` (cannot see a crashed issue with no record) or a dequeue ledger must be introduced — the `record_absent` requirement is unsatisfiable without one of the two, and this is a design decision the implementer must make knowingly.
- **Marker anchors have shifted** (autodev.yaml): `autodev-decision-unresolved` :68, :579, :584 (read in `skip_inflight`), :997 (autodev's own writer), :3080; `autodev-spike-inconclusive` :69, :591, :1786, :3160; `autodev-proposal-unsound` :70, :597, :3164; `autodev-decide-ran` :109, :249, :283, :782, :863. Child writers in `refine-to-ready-issue.yaml`: `autodev-proposal-unsound` :711, `autodev-spike-inconclusive` :1356, `autodev-decision-unresolved` :1389. The `autodev-decide-ran` mentions at `refine-to-ready-issue.yaml:981` and `oracles/resolve-decision.yaml:249` are **comments only** (verified) — no child or oracle writes or reads that marker; only autodev does.
- **Other autodev-side markers outside the issue's "preparation" list** still read/written by `autodev.yaml`: `autodev-spike-no-verdict.txt` (:1807), `autodev-proof-gate-infra.txt` (:1354), `autodev-pre-readiness.txt`, `autodev-pre-spike-readiness.txt`, `autodev-pre-deferral-remedy.txt`, `autodev-repair-cycle-count.txt`, `autodev-contradiction-reconcile-count.txt`, `autodev-pre-ids/post-ids/diff-ids/new-children`. Whether these count as "preparation markers" for the AC grep gate is undecided; the gate's wording must name its scope.
- **Test/doc anchors drifted**: `test_builtin_loops.py` thin-shell gate now `:21491` (was :21440); `autodev-decide-ran` sites `:9261, :9430-9434, :9500-9514`; `autodev-decision-unresolved` `:5133, :5405, :5659-5664, :7986, :7997`; `autodev-proposal-unsound` `:3161`. `LOOPS_REFERENCE.md` marker lines are now `:1035, :1037, :1081, :1083, :1085, :1087`, plus run-record mentions at `:158` and `:1083` the issue does not list. Additional marker-name mentions with no code reader: `CHANGELOG.md`, `.ll/private-refs-baseline.json`, `.ll/decisions.d/daca1e87-…json`.

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **Current-state correction (supersedes the stale anchors above).** ENH-3619 has landed: `scripts/little_loops/autodev_summary.py` exists (`build_summary`, `render_report`, `write_summary`, `finalize`, `main`; `EXIT_OK=0`/`EXIT_PHANTOM=1`/`EXIT_ERROR=2`; `AutodevSummary.KEYS` = 16 keys). `autodev.yaml` `finalize_done` (~:2948) and `finalize_step_capped` (~:2967) are one-line `python3 -m little_loops.autodev_summary` calls routed through `fragment: shell_exit`. Absent everywhere in `scripts/`: `autodev-prepared`, `record_absent`, `record_ledger_mismatch`, `prep-facts`, `prep apply`.
- **Reader contract facts.** `autodev_summary.py` imports nothing from `run_record` and never touches `run-records/`. `read_run_record(run_dir, writer, issue_id) -> RunRecord | None` (`run_record.py:118`) is reached from loop YAML only through `ll-issues run-record read … --format token` (`autodev.yaml` ~:526, ~:691); no Python code enumerates `run-records/prepare-issue/`. `write_summary` uses `atomic_write(..., shared_mode=True)` with compact `to_json()`, not `atomic_write_json`; the golden fixtures compare bytes, so that serialization is pinned.
- **`refine-terminal-class` sentinel — one reader, many writers.** Sole reader: `autodev.yaml` `skip_inflight` (:588-589; comments :501, :576, :599). Writers: `prepare-issue.yaml` `mark_inner_error` (:77) and about eight sites in `refine-to-ready-issue.yaml` (:690, :1143, :1198, :1209, :1220, :1233, :1267, :1513; `resolve_issue` clears it at :181). It is also documented in `run_record.py` (module docstring, `LEGACY_CLASSES` comment) and `cli/issues/run_record.py:59` (`--legacy-class` help). `skip_inflight` also carries three child-ledger greps (:598-618) whose comment (:594-596) names this issue as their remover. Removal must stay consistent with the pins in `test_builtin_loops.py` (:1759, :1941-1946, :2211-2215, :2272, :2658-2671, :2744-2752, :6748-6757), `test_run_record.py` (:570, :579, :657), `test_prepare_issue.py:162` and `autodev_harness.py` (:133, :208, :550) — several are positive pins on the wrapper-side writers.
- **Marker facts against the disposition table.** Dead today: `autodev-pre-spike-readiness.txt` (comment-only mention at `autodev.yaml:2076`, no writer or reader); `autodev-decide-ran` and `autodev-spike-no-verdict` (zero refs in `autodev.yaml`; `autodev-decide-ran` survives as a comment at `refine-to-ready-issue.yaml:907`); `autodev-design-gate-failed` (comment-only at `autodev.yaml:170`, retired by BUG-3620). Write-only: `autodev-scores-absent.txt` (`mark_scores_absent_infra`, :1630) and `autodev-gate-infra.txt` (`mark_gate_infra`, :1615) have no reader in `scripts/little_loops`; `mark_scores_absent_infra` is a state ENH-3623 deletes, but `mark_gate_infra`'s disposition is not covered by the table. `autodev-decision-unresolved.txt` is never written by autodev — `init` truncates it (:77-80) and `skip_inflight` reads it; the child writes it (`refine-to-ready-issue.yaml:692`, :1235, :1269 for the three ledgers). Per-pass markers cleared in `dequeue_next` (~:97-189): `repair-cycle-count`, `pre-readiness`, `contradiction-reconcile-*`, `pre-deferral-remedy*`, `atomic-design-remedy-pending`, `size-review-ran-this-pass`, `rescore-origin/retry`, `reentry-*`, `go-no-go-attempted-<ID>`, `design-remedy-attempted-<ID>`.
- **Where the prepared-ID append lands.** `dequeue_next` → `check_status_at_dequeue` → skip states → gate check (`on_no`/`on_error: refine_current`, ~:452-453); `refine_current` (:478-518) is `loop: prepare-issue` with `on_success: count_repair_cycle_refine`, `on_failure: route_refine_outcome`, `on_error: skip_inflight_infra`. `init` (:56-95) pre-creates 11 ledgers with `printf ''` and does not create `autodev-gate-infra.txt` or `autodev-scores-absent.txt`.
- **ENH-3623 dependency surface.** ENH-3623 is `open`; the `refine-terminal-class` removal, the "wrapper `failed` terminals write the record" premise and the shared per-pass marker rows all assume `ll-issues prep apply` as sole terminal writer, none of which exists yet. Today the MISSING route depends on `mark_inner_error` plus the child's `classify_terminal` sentinel.
- **Current test anchors** (supersede the list above): `test_autodev_summary.py` (module-level tests; fixtures under `scripts/tests/fixtures/autodev_summary/` registered through `_generate.py`, `test_fixture_set_is_populated` requires set equality), `test_builtin_loops.py` `TestAutodevLoop` :6412, `_run_finalize_done` :7233, thin-shell gate :20987, `TestInterpSweepBaseline` :20515, `MR11_MARKER_ALLOWLIST` :20589 (asserted :20802); `test_feat3573_quality_gate.py` :577-603, :683; `test_autodev_decision_gate.py` :666-679, :1261-1265; `test_spike_verdict_routing.py` :130-131, :305-307; `test_autodev_loop.py` :200-203; `test_autodev_characterization.py` :138, :444-445, :642, :679, :798; `loop_interpolation_baseline.json` :708. `auto-refine-and-implement.yaml` counts `autodev-decision-unresolved.txt` at :1135.

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **Anchor refresh (2026-09-27, post-ENH-3623/3630 landing)**: `autodev.yaml` is now 1446 lines / 45 states (down from the 87→105-state counts cited in earlier passes). Current anchors: `dequeue_next:96` (bumps `prep-pass-$CURRENT` at :119-120), `check_status_at_dequeue:167`, `refine_current:454` (`loop: prepare-issue`, `on_error: skip_inflight_infra`), `route_refine_outcome:500`, `ledger_child_stop:534`, `skip_inflight:547` (reads `refine-terminal-class` at :569-571, three child-ledger greps at :575-601), `skip_inflight_infra:610`, `copy_broke_down:628`, `finalize_rate_limited:1392`, `finalize_done:1404` (still a one-line `python3 -m little_loops.autodev_summary` call, unchanged), `finalize_step_capped:1423`.
- `refine-to-ready-issue.yaml`'s 8 `refine-terminal-class` writer sites are now at :742, :1195, :1250, :1261, :1272, :1285, :1319, :1565; the `resolve_issue` clear is at :192. Writer states: `record_proposal_unsound:737`, `record_spike_inconclusive:1279`, `record_decision_unresolved:1302`, `classify_terminal:~1503-1569`.
- `preparation_policy.py` anchors: `_apply_outcome:1162-1291` (`sentinel()` closure :1207-1208), `_DEFER_STOPS:1089-1096`, `_INFRA_STOPS:1097`, `prep_apply:1100-1159`, `prep_record:1039-1084`, `prep_step:1000-1036`, `FACTS_DIR="prep-facts":63`, `PASS_PREFIX="prep-pass-":64`, `facts_path:836-837`, `current_pass:840-846`.
- **Confirmed still-live run-dir handshake artifacts post-ENH-3623** (four kinds, only the first is in this issue's removal scope): (1) `refine-terminal-class` — the sole sentinel this issue removes; (2) `refine-broke-down` — stays; reset by `autodev.yaml`'s `copy_broke_down:628-639`, written by `preparation_policy.py`'s `_apply_outcome.write()`; (3) `run-records/<writer>/<ID>.json` — the ENH-3597/3623/3630 typed replacement (writers: `refine-to-ready-issue`, `prepare-issue`); (4) `prep-pass-<ID>` / `prep-facts/<ID>.jsonl` — the ENH-3623 fact-log layer, unrelated to `autodev_summary`'s reads (confirmed: `autodev_summary.py` references neither `FACTS_DIR`, `PASS_PREFIX`, nor `load_facts`).

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **Post-ENH-3623 anchor refresh, confirmed (2026-09-27, second pass)**: `autodev.yaml` is 1447 lines / 46 states. `dequeue_next:96` (writes `prep-pass-$CURRENT` at :119-120). `skip_inflight:547` still reads `refine-terminal-class` at :569-570, with the three child-ledger fallback greps at :584 (`autodev-decision-unresolved.txt`), :591 (`autodev-spike-inconclusive.txt`), :597 (`autodev-proposal-unsound.txt`). `finalize_rate_limited:1392`, `finalize_done:1404` (action is now `python3 -m little_loops.autodev_summary --run-dir ${context.run_dir} --quality-gate <ref>` — a `--quality-gate` flag not previously recorded in this issue), `finalize_step_capped:1423` (adds `--stop-reason max_steps`).
- **`refine-to-ready-issue.yaml` anchors reconfirmed unchanged** (1578 lines / 61 states): the 8 `refine-terminal-class` writer sites are still exactly `:742, :1195, :1250, :1261, :1272, :1285, :1319, :1565` (no drift since the prior 2026-09-27 pass); `resolve_issue` clear still `:192`. Writer states: `record_proposal_unsound:737` (writes class :742, ledger `autodev-proposal-unsound.txt` :744), `record_spike_inconclusive:1279` (class :1285, ledger :1287), `record_decision_unresolved:1302` (class :1319, ledger :1321).
- **`preparation_policy.py` anchors reconfirmed**: 1391 lines. `FACTS_DIR:63`, `PASS_PREFIX:64`, `facts_path:836-837`, `current_pass:840-846`, `prep_step:1000-1036`, `prep_record:1039-1084`, `_DEFER_STOPS:1089-1096`, `_INFRA_STOPS:1097`, `prep_apply:1100-1159` (docstring: "Sole terminal writer"), `_apply_outcome:1162-1291` with `sentinel()` closure at :1207-1208, called from 5 sites: `:1253` (`child_stop`), `:1258` (`rate_limited`), `:1266` (`_INFRA_STOPS`), `:1285` (`_DEFER_STOPS`), `:1289` (unknown outcome, fail-closed). `callers-of _apply_outcome` (code graph) confirms `prep_apply` (:1143) is its sole caller.
- **Test-anchor ambiguity resolved: the autodev thin-shell gate has a different name than prior anchors claimed.** `TestAutodevLoop.test_finalize_states_are_thin_module_calls` (`test_builtin_loops.py:7182-7200`, class header `:6411`) is the actual structural gate asserting `finalize_done`/`finalize_step_capped` are each a single `python3 -m little_loops.autodev_summary --run-dir ${context.run_dir} --quality-gate <ref>[extra]` call with zero inline shell (`printf`/`grep`/`awk`/`sort`/`for`/`if`/`case`/`echo`/`$(` all asserted absent). Every prior pass's "thin-shell gate" anchor (`:21491`/`:21440`/`:21017`/`:20987`) named `test_shell_states_call_helper_module_not_inline_logic`, which resolves only to `TestFleetLoopImproveLoop` (`:20103`, the fleet-improve loop) — that test was never autodev's gate, and no autodev-scoped test of that exact name exists. `_run_finalize_done` helper is at `:7216-7243`. AC's "ENH-3619's structural gate stays green" claim is accurate; only the anchor citation was wrong.
- **Marker disposition re-derived against post-ENH-3623 `autodev.yaml`, full inventory (analyzer, 2026-09-27).** Confirmed **dead** (zero references anywhere in `scripts/little_loops/`): `autodev-pre-spike-readiness`, `autodev-design-gate-failed`, `autodev-design-remedy-attempted`, `autodev-atomic-design-remedy-pending`, `autodev-contradiction-reconcile`, `autodev-go-no-go-attempted`, `autodev-pre-deferral-remedy`, `autodev-size-review-ran-this-pass`, `autodev-rescore-retry`, `autodev-rescore-origin`, `autodev-reentry`, `autodev-scores-absent.txt`, `autodev-broke-down` (distinct from the still-live `refine-broke-down`). Confirmed **still live**: `autodev-repair-cycle-count` (now a projection per `prep_record` docstring `preparation_policy.py:81`, written `:1083`, reset `autodev.yaml:143`), `autodev-pre-readiness` (written `autodev.yaml:142`, read `preparation_policy.py:935`), `autodev-gate-infra.txt`/`mark_gate_infra` (write-only, `autodev.yaml:1178`/state header `:1170`, still zero readers anywhere — the "drop or keep" question is unresolved, unchanged from before ENH-3623), `autodev-pre-ids`/`-post-ids`/`-diff-ids`/`-new-children` (written `autodev.yaml:158,1266,1270,1286-1380`), `refine-broke-down` (reset `autodev.yaml:122,636`; written `refine-to-ready-issue.yaml:195,1222` and `preparation_policy.py:1076,1214`; read `recursive-refine.yaml:484`).
- **`run_record.py` reconfirmed, and the design decision stands.** `read_run_record(run_dir, writer, issue_id) -> RunRecord | None` signature unchanged (`:119`). No production code anywhere in the repo enumerates `run-records/prepare-issue/*.json` as a directory glob — only `scripts/tests/test_run_record.py` does (test-only `rglob`, :447/:699/:714). This reconfirms the `prep-pass-<ID>`-file dequeued-ID-set decision is still the only viable route; the record directory alone still cannot see a crashed/recordless issue.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/run_record.py:65` — the `--legacy-class` argparse `help=` text names `refine-terminal-class` directly ("The refine-terminal-class token this terminal just wrote... omit on the done paths (no class file is written there)"); once the sentinel file is removed entirely (no path writes a class file anymore), this help string is stale and needs rewording — a source-code touchpoint distinct from its doc mirror at `docs/reference/CLI.md:2426,2432` [Agent 1 finding, 2026-09-27]
- `scripts/little_loops/loops/prepare-issue.yaml:178,188` — real shell call sites invoking `ll-issues prep apply` (`prep_apply`) in production, not previously listed as a caller anywhere in this Integration Map [Agent 1 finding, 2026-09-27]
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `init` deletes the shared run-dir `summary.json` (:95) and `finalize` overwrites it (:1255), so autodev's summary.json is transient on the sprint path; `finalize` reads six ledger files plus `autodev-queue.txt` (`recheck_set` :477 residual fold-back) — any ledger in the removal set orphans its counts, and if the child stops writing `autodev-decision-unresolved.txt`, `DECISION_UNRESOLVED` undercounts child-side unresolved [Agent 2 finding]
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — `read_outcome` cats and `record_crash` overwrites the same shared `summary.json` path (third writer) [Agent 2 finding]
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — writes `decide-options-deposited-<ID>` (:56) and `decide-rate-limited-<ID>` handshake markers autodev reads (`dequeue_next`, `check_decide_rate_limited`); not `autodev-`-prefixed, so the AC's "No `autodev-*` preparation marker" wording does not cover them — they remain the cross-loop run-dir contract after this issue [Agent 2 finding]
- `scripts/little_loops/fsm/executor.py:653` — autodev declares no `on_max_steps` handler today, so the step-cap exit calls `_finish("max_steps")` without passing through `finalize_done` [Agent 2 finding]. Closed by ENH-3619 (`finalize_step_capped`), not a limitation of this issue
- `scripts/little_loops/fsm/persistence.py` (`archive_run`), `scripts/little_loops/cli/loop/audit.py`, `scripts/little_loops/cli/loop/evidence.py`, `scripts/little_loops/hooks/pre_compact_handoff.py` — shape-agnostic summary.json consumers; safe under key-shape preservation [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — autodev section (:1013-1087) documents the marker vocabulary (:1033, :1035, :1079, :1083, :1085) and the parent/child closure-accounting contract (:1007) — prune marker references as they are removed; the end-user account stays here even after the ARCHITECTURE.md contract lands [Agent 1+2 finding]
- `docs/reference/DEFERRAL_CODES.md:30` — names `autodev-scores-absent.txt` / `autodev-gate-infra.txt` by filename [Agent 1 finding]
- `docs/reference/COMMANDS.md:944` — `ll-loop audit` phantom/honest-failure classification keyed on summary.json presence and claimed-success counters [Agent 2 finding]
- `skills/audit-loop-run/SKILL.md:271` — documents autodev's summary keys (`not_started`, `notstarted_*`, `refine_failed_infra`, `oversized_atomic`); update for the FEAT-3573 key split [Agent 2 finding]
- `docs/reference/API.md` — `## little_loops.autodev_summary` enumerates the 16 keys in order ("holds one compact JSON line with the 16 keys of `AutodevSummary.KEYS`", ~:12222-12224) and says `build_summary()` "counts the run-dir ledgers"; add the two new keys, the record reader and the `prep-pass-<ID>` dequeued-ID set. Module table row at :60 [Agent 1+4 finding]
- `docs/reference/CLI.md:2426` — the `ll-issues run-record write` `--legacy-class` row documents the `refine-terminal-class` sentinel [Agent 1+4 finding]
- `docs/guides/LOOPS_REFERENCE.md` — long lines at :172, :1023, :1097, :1101 also match the key/sentinel names and were not enumerated above [Agent 1+4 finding]
- `skills/audit-loop-run/SKILL.md` Step 6a (:271-283) has one additive-key paragraph per ticket; add one for `record_absent` / `record_ledger_mismatch` (edit triggers the `ll-adapt` mirror regeneration) [Agent 4 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Preserve `summary.json`'s key set through the Python rewrite — `test_auto_refine_closure_accounting.py`, `TestAutoRefineAndImplementLoop` key assertions, and MR-13's `"abandoned"`-key emission requirement all depend on it; MR-13's shell-text scan goes vacuously silent when the printf moves to Python, so its enforcement shifts to the new module's unit tests
- Keep autodev's four interpolation-baseline entries valid (`check_blockers_at_dequeue`, `check_reconcile_needed`, `check_spike_needed`, `check_spike_needed_before_skip`); the thin `python3 -m little_loops.autodev_summary --run-dir ${context.run_dir}` call is plain interpolation and needs no new entry
- Migrate `auto-refine-and-implement.yaml`'s `autodev-decision-unresolved.txt` count together with the child's writer, or document the closure-ledger exception — the six ledger reads plus `recheck_set`'s queue read stay by Scope Boundaries
- Decide `decide-options-deposited-<ID>` / `decide-rate-limited-<ID>` (resolve-decision handshake, not `autodev-`-prefixed) — keep or migrate; the AC grep gate's wording must name what it covers
- Thin-shell structural gate for `finalize_done` / `finalize_step_capped` (`TestAutodevLoop.test_finalize_states_are_thin_module_calls`, `test_builtin_loops.py` ~:7182) — landed with ENH-3619; keep it green
- Update `scripts/little_loops/loops/README.md` rows and `docs/guides/LOOPS_REFERENCE.md` marker references as markers are removed
- Correct two stale premises above: MR-13 lives in `fsm/validation/evaluator_rules.py` (`_ABANDONED_KEY_EMIT_RE` :146; there is no `fsm/validation.py`) and its shell scan is already vacuous after ENH-3619 (`test_autodev_summary.py:254` covers the `abandoned` key); the interpolation baseline holds two autodev entries (`check_blockers_at_dequeue`, `check_reconcile_needed`), not four, because ENH-3611 removed `check_spike_needed*`
- ~~Check the `autodev-prepared.txt` pre-state's ID interpolation against MR-11~~ Superseded (2026-09-27 review): no pre-state
- Update `scripts/little_loops/cli/issues/run_record.py:65` — reword the `--legacy-class` help text once no path writes a `refine-terminal-class` file (added by `/ll:wire-issue`, 2026-09-27)
- Flip `scripts/tests/test_run_record.py::TestTerminalExecution::test_mark_rate_limit_infra` (:665) and `::test_classify_terminal_quality_is_blocked` (:743) to absence assertions alongside the already-planned `test_record_gate_unmet` flip (added by `/ll:wire-issue`, 2026-09-27)
- Update the fixtures/`SUMMARY_BASE` key sets and `docs/reference/API.md` in the same commit as the two new keys (no `test_fsm_topology.py` change)
- Sweep `refine-to-ready-issue.yaml`'s `refine-terminal-class` references when the sentinel goes (anchors refreshed 2026-09-27): writers :742, :1195, :1250, :1261, :1272, :1285, :1319, :1565; `resolve_issue` clear :192; comments :146, :222, :1314, :1345, :1537, :1575 (the `failed` terminal's own comment). `autodev.yaml`: comments :479 (`refine_current`), :557, :580, the `refine_current` `on_error` comment's "sentinel path" wording (~:487-496), and the stale "ENH-3600 removes them with the markers" note (~:575-577, reword: the greps stay). `prepare-issue.yaml` has no references
- Nested runs never surface these keys: `auto-refine-and-implement.yaml` (:100, :1277) overwrites `summary.json` with its own printf and reads no `autodev-prepared` file; `sprint-refine-and-implement.yaml` (:45-59) is key-agnostic; document the "standalone autodev runs only" caveat as ENH-3613 did

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Medium - summary builder moved to Python plus marker removal
- **Risk**: Medium - summary.json truthfulness is an EPIC-3565 invariant
- **Breaking Change**: No - summary.json keeps its 16 keys; `record_absent` and `record_ledger_mismatch` are additive (no consumer asserts an exact key set)

## Program Design

### Types

- `AutodevSummary: dataclass` — exists (ENH-3619); this issue appends `record_absent` and `record_ledger_mismatch` to `KEYS`

### Signatures

- `build_summary(run_dir: Path) -> AutodevSummary` — exists (ENH-3619); extended to read `run-records/prepare-issue/<ID>.json` for each ID with a `run_dir/prep-pass-<ID>` file plus the Scope Boundaries files; an absent/malformed record for a prepared, not-in-flight, otherwise-unledgered ID counts as `record_absent`
- `write_summary(run_dir: Path, summary: AutodevSummary) -> Path` — exists (ENH-3619); writes compact `summary.json` via `atomic_write(..., shared_mode=True)`, byte-pinned by the golden fixtures
- `render_report(summary: AutodevSummary) -> str` — the stdout report, line-identical to today's plus the `record_absent` line
- `main(argv: list[str] | None = None) -> int` — `EXIT_OK=0` / `EXIT_PHANTOM=1` / `EXIT_ERROR=2`

### Call Path

`autodev.yaml:finalize_done` -> `main` -> `build_summary` -> `read_run_record` -> `write_summary` / `render_report`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- ENH-3597's proposed reader returns `RunRecord | None` on absent/malformed record (or writer/ID mismatch), so `build_summary`'s `record_absent` bucket maps from a `None` return plus the dequeued-ID list — which must come from the closure/queue files that remain (`autodev-staged.txt`/`autodev-unverified.txt`/`autodev-inflight`), since the queue alone does not retain dequeued IDs.
- ENH-3597 specifies `read_run_record(run_dir, writer, issue_id) -> RunRecord | None`; after ENH-3601 the authoritative writer is `prepare-issue` (the wrapper), not `refine-to-ready-issue` — the audit-conflicts Scope Boundary note already reflects this.
- Serialization conventions for `AutodevSummary`: hand-written `to_dict` on the dataclass is the house style (`state.py:49-86` is the canonical both-directions example with `from_dict`; `queue_store.py:391` emits camelCase keys with `_from_row` :421; `issue_history/models.py` is to_dict-only), sets converted to lists for JSON, writes via `atomic_write_json` (`file_utils.py:70`).

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- Reader contract in force: `read_run_record` returns `None` for absent, malformed, and writer/ID-mismatched records (`test_run_record.py:195-212` pins each), so `build_summary` gets `record_absent` from a `None` return over a dequeued-ID set — the ID set's source was resolved by the 2026-09-26 review: `autodev-prepared.txt` (see Design decisions).
- Exit-code convention for the thin-shell call: `fleet_improve.py` names `EXIT_YES=0 / EXIT_NO=1 / EXIT_ERROR=2` (:75-77) and states route `on_yes/on_no/on_error`; `finalize_done` today already routes `phantom` → exit 1 → `on_no: failed` and any error → `on_error: failed`, which a module `main() -> int` must preserve exactly.
- Decision Rules: N/A — no new decision logic beyond the `record_absent` → `retryable_error` rule already stated in Proposed Solution; the verdict ladder is carried over unchanged.

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **Signature correction (2026-09-27)**: the current `build_summary` signature is `build_summary(run_dir: Path, *, cancelled_ids: list[str], stop_reason: str | None = None) -> AutodevSummary` (`autodev_summary.py:422`) — not the no-kwarg `build_summary(run_dir: Path)` this section previously stated. `cancelled_ids` is a required keyword-only argument the record-reader extension must thread through or default explicitly.
- **`record_absent`/`record_ledger_mismatch` do not currently affect the verdict or exit code**: `AutodevSummary.exit_code` (`autodev_summary.py:179-182`) only checks `verdict == "phantom"`, and `compute_verdict` (:405-419) has no branch for either new key. Whether a nonzero count should change `verdict`/`exit_code` is undecided by the existing Design/Review Decisions and must be resolved explicitly — today it would only be a reported, non-blocking count.
- **`record_token` conflates absent and malformed**: `read_run_record` (`run_record.py:119-138`) returns `None` for a missing file, malformed JSON, a non-dict payload, or a writer/issue-id mismatch alike, and `record_token(None)` (:167-168) always maps to `"MISSING"` — there is no separate token distinguishing "no file" from "file present but unreadable/foreign". `build_summary`'s `record_absent` bucket must either accept this conflation via `record_token()`, or read the `RunRecord | None` return directly if it needs to report *why* a record read as absent.
- **`KEYS` addition blast radius**: unlike the FEAT-3573/ENH-3613 additions (which only tripped a shell `printf`-line tail-slice test, since `AutodevSummary` didn't exist as a Python module yet — confirmed via `git show 0c0d35869` / `e9bba58d7`), adding `record_absent`/`record_ledger_mismatch` to the live `AutodevSummary.KEYS` tuple trips both `test_summary_key_order` (`test_autodev_summary.py:262-264`, full ordered-list assert) and the per-scenario parity assertion `list(summary) == list(AutodevSummary.KEYS)` (`test_autodev_summary.py:92`) across every one of the ~30+ golden fixture scenarios simultaneously — broader than the single dedicated test the issue's earlier research implied.
- **Marker-disposition grep gate confirmed as a new shape** (pattern-finder, 2026-09-27): the two nearest structural cousins are `TestMr11MarkerSet` (`test_builtin_loops.py:19780-20005`, bidirectional set-equality over `(file, path, issue-id)` tuples — enumeration only, no per-row disposition) and the chokepoint reasoned-allowlist pattern (`test_history_store_chokepoint_gate.py:37-126`, `test_usage_selection_chokepoint_gate.py:28-38` — `dict[site, one-line reason]` paired with a companion staleness test asserting each allowlisted site still exists and still needs the exception). Neither combines enumeration + a per-row expected-disposition column + staleness detection the way the proposed Marker disposition gate does; no single existing gate is a direct template.
- **Two more "counted, never dropped, non-blocking" precedents** for the `record_absent`/`record_ledger_mismatch` design (beyond the four already cited): `issue_parser.py`'s `_ADVISORY_GAP_CLASSES` / `orphaned_session_log_entries` (BUG-3424, :505-517 — "report-only by design ... must never fail the exit code on its own"), and `token_provenance.py`'s `counted_entry`/`estimated_entry` `known_count`/`missing_count` fields (:241-242, :294-295, :330-343 — missing observations are folded into the denominator via `coverage`/`availability` classification, never dropped from the aggregate).

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **`build_summary` signature and `AutodevSummary.KEYS` reconfirmed unchanged post-ENH-3623** (analyzer, 2026-09-27, via code-graph `callers-of`/`callees-of`): `build_summary(run_dir: Path, *, cancelled_ids: list[str], stop_reason: str | None = None) -> AutodevSummary` (`autodev_summary.py:422-424`); its body (`:433-507`) still reads no `run-records/` — callees are only local helpers `_ledger`/`_records`/`_read`/`_sorted_unique`/`_nonblank`/`_field`, all within the same module. `AutodevSummary.KEYS` (`:152-169`) is still the same 16 keys in the same order. `write_summary` (`:611-615`) still calls `atomic_write(path, summary.to_json(), shared_mode=True)`; `to_json()` (`:175-177`) is compact `json.dumps(..., separators=(",", ":"))`. Sole caller of `build_summary` is `finalize()` (`:618-628`), confirmed via code-graph `callers-of`.

## Scope Boundaries

- **Queue and closure-accounting files stay.** These are the only non-record inputs
  `build_summary` may read:
  - queue: `autodev-queue.txt`, `autodev-inflight`, `autodev-input.txt`, and ENH-3623's
    `prep-pass-<ID>` files (enumerated by name only; their contents are not read);
  - closure: `autodev-staged.txt`, `autodev-passed.txt`, `autodev-unverified.txt`, and
    `${context.run_dir}/quality/` (the FEAT-3573 evidence);
  - skip/stop ledgers: `autodev-skipped.txt` (its reason column feeds the `already_*`,
    `blocked_by_unmet`, `notstarted_` and `refine_failed_infra` buckets, and
    `auto-refine-and-implement`'s `SKILL_BREAKDOWN`), `autodev-gate-blocked.txt`,
    `autodev-not-started.txt` / `-attempts.txt`, `autodev-proof-gate-infra.txt` and
    `autodev-stop-reason`;
  - child-written ledgers (documented exception; see Marker disposition):
    `autodev-decision-unresolved.txt`, `autodev-spike-inconclusive.txt`,
    `autodev-proposal-unsound.txt`.

  Run records cannot replace the skip reasons: `legacy_class` has six values and
  `gate_unmet` drops the specific reason (`oversized_atomic`, `design_gate_failed`,
  `readiness_stagnated`, ...).
- **Run records add information; they do not replace the ledgers.** Records supply the
  per-issue preparation outcome and the `record_absent` check. The ledger rows written
  next to each record (ENH-3605's ledger-ownership rule) stay the count source for
  every existing key. If a record and a ledger row disagree, the ledger row is used for
  the count, and `build_summary` increments the additive `record_ledger_mismatch` key and
  lists the ID on a report line. It does not reclassify the issue.
- `summary.json` keys keep their shape **as of FEAT-3573**, which builds on ENH-3613's
  cancelled/implemented split (`closed_implemented`/`closed_cancelled`, derived in
  memory in the promotion loop — no ledger file). The additions are the
  `record_absent` and `record_ledger_mismatch` keys (see Design decisions).
- Out of scope: migrating the child-written ledger readers (documented exception); and the `resolve-decision` handshake markers
  `decide-options-deposited-<ID>` / `decide-rate-limited-<ID>`, which stay as the
  cross-loop run-dir contract.

### Marker disposition

The AC grep gate checks against this table, not a bare `autodev-*` prefix. Re-derive the
table from post-ENH-3623 `autodev.yaml` as the first implementation step, because
ENH-3623 removes 42 states and moves their markers into the fact log.

| Class | Files | Disposition |
|---|---|---|
| Queue / closure accounting | listed in Scope Boundaries | stay |
| Shared per-pass state, still live (re-derived 2026-09-27 post-ENH-3623) | `autodev-repair-cycle-count.txt` (projection: `dequeue_next` resets it, ~:143; `prep record` rewrites it, `preparation_policy.py` ~:1083), `autodev-pre-readiness.txt` (written by `dequeue_next` ~:142; read by `preparation_policy.py` ~:935) | stay. In `autodev.yaml`, allowed **only in `dequeue_next`** (writes and resets, not just clears) |
| Shared per-pass state, dead (folded into `run_dir/prep-facts/<ID>.jsonl` by ENH-3623) | `autodev-design-remedy-attempted-<ID>`, `autodev-atomic-design-remedy-pending`, `autodev-contradiction-reconcile-*`, `autodev-go-no-go-attempted-<ID>`, `autodev-pre-deferral-remedy*`, `autodev-size-review-ran-this-pass`, `autodev-rescore-retry-*`, `autodev-rescore-origin-<ID>`, `autodev-reentry-*` | zero references (confirmed zero in `scripts/little_loops/`, 2026-09-27); the gate keeps them at zero |
| Policy state (ENH-3623) | `run_dir/prep-facts/<ID>.jsonl`, `run_dir/prep-pass-<ID>` | stay. `prep-pass-<ID>` is written only by `dequeue_next`; `prep-facts` only by `ll-issues prep` |
| Gate-infra ledger | `autodev-gate-infra.txt` (`mark_gate_infra`) | **Keep** (resolved 2026-09-27; not re-derived). Write-only, no reader in `scripts/little_loops`, but not dead: named in `docs/reference/DEFERRAL_CODES.md:30` as the documented "learning-gate record", positively test-pinned (`test_mark_gate_infra_advances_queue_without_defers`), and one of four sibling infra-deferral-ledger states — BUG-3603 earmarks this exact ledger class as a candidate for a future `summary.json` infra key. Stays a write-only audit trail this issue does not touch (`autodev-scores-absent.txt`, its former table-mate, is separately dead — see below) |
| Decomposition diff | `autodev-pre-ids.txt`, `-post-ids.txt`, `-diff-ids.txt`, `-new-children.txt`, `refine-broke-down` (reset in `dequeue_next` / `copy_broke_down`; written by the child and `prep apply`) | stay (queue-owned child detection). `autodev-broke-down` has zero references and belongs in the Dead row |
| Child-written ledgers (documented exception) | `autodev-decision-unresolved.txt`, `autodev-spike-inconclusive.txt`, `autodev-proposal-unsound.txt` | The child keeps writing them, and `auto-refine-and-implement` keeps reading them. `build_summary` also keeps reading them as closure accounting. The `decision_unresolved` key counts **only** this ledger today; the child's `record_decision_unresolved` writes no `autodev-skipped.txt` row, while autodev's own `decision_unresolved` rows go to `autodev-skipped.txt`. Counting that key from records would pull in the wrapper's `record_reentry_exhausted` stops and change the count. Inside `autodev.yaml`, the only references left are `init` truncation and `skip_inflight`'s grep-before-`refine_failed` (~:584-601). **The greps stay** (third review): `route_refine_outcome` routes present records to `ledger_child_stop`, but the greps are the only guard for a `MISSING` record after a child stop, and they now run before the record-token read |
| Dead | `autodev-scores-absent.txt` (writer deleted by ENH-3623), `autodev-pre-spike-readiness.txt`, `autodev-design-gate-failed-<ID>` (BUG-3620), `autodev-broke-down`, `autodev-decide-ran`, `autodev-spike-no-verdict.txt`, `refine-terminal-class` (this issue), and any other file with no writer after ENH-3623 | delete every reference (the one survivor outside `autodev.yaml` is the `autodev-decide-ran` comment at `refine-to-ready-issue.yaml` ~:959; reword it to cite the policy's per-pass decide budget) |

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **`mark_gate_infra`/`autodev-gate-infra.txt` decision resolved: keep, not drop (2026-09-27).** Unlike the confirmed-dead markers, this one has external evidence of intentional use: (1) `docs/reference/DEFERRAL_CODES.md:30` names `autodev-gate-infra.txt` by filename as "the learning-gate record," documented for operators reading deferral codes; (2) it is the terminal ledger for `check_learning_gate_infra`/`mark_gate_infra` (ENH-3084, "learning-gate lacks infra contention verdict"), one of four sibling states sharing a deliberate "infra-deferral state convention" (`skip_inflight_infra`, `mark_gate_infra`, `mark_scores_absent_infra` [now removed by ENH-3623], `mark_spike_no_verdict_infra`) that append an ID to a per-reason ledger as an infra-failure audit trail, distinct from a quality verdict; (3) it is positively test-pinned (`test_mark_gate_infra_advances_queue_without_defers`, `test_builtin_loops.py:7966`, asserts `"autodev-gate-infra.txt" in action`) — not incidental cruft; (4) BUG-3603's own research explicitly earmarks this class of infra ledger (`autodev-gate-infra.txt`, alongside `autodev-proof-gate-infra.txt`, `autodev-scores-absent.txt`) as a candidate for a *future* `summary.json` infra-deferral key, i.e. planned to eventually gain a reader, not slated for removal. Disposition: **keep**, filed under Queue / closure accounting alongside its sibling `autodev-proof-gate-infra.txt` (already listed there) — not deleted, and not re-derived as an open question.

## Behavior Parity

What the rewrite of `finalize_done` must preserve, and what is allowed to change:

- **Preserved exactly**: all 16 FEAT-3573-as-of `summary.json` keys and their values;
  the verdict ladder (success → partial → phantom → not_started → no-op, with the
  `rate_limit` stop reason overriding to `rate_limited`); the staged → passed/unverified
  promotion and its writes to `autodev-passed.txt` / `autodev-unverified.txt`; the stdout
  report lines; and the exit code per verdict. The golden fixtures enforce all of this.
- **Intentionally changed**: the additive `record_absent` and `record_ledger_mismatch`
  keys and their report lines (printed only when > 0); and a `MISSING` record classified
  from the record alone (no `refine-terminal-class` read) on both the failure path and the
  success path (`check_passed.on_no`), plus a failed record read (`_error`), each now
  ledgered `refine_failed_infra` instead of `refine_failed`. Nothing else in
  `summary.json` changes.
- **Sentinel removal**: `refine-to-ready-issue.yaml` and `prep apply` stop writing
  `refine-terminal-class`. With its only reader gone this has no behavioral effect.
- **Unchanged behavior**: `refine-to-ready-issue.yaml` keeps writing the three child
  ledgers (the documented exception), and `auto-refine-and-implement`'s summary counts
  are identical on the same input.
- **MR-13**: the `abandoned` key requirement moves from the shell-text scan to the
  module's unit tests, because the printf no longer lives in YAML.

## Acceptance Criteria

- [ ] `build_summary` reads only `run-records/prepare-issue/*.json` plus the files listed in Scope Boundaries (unit test with a `run_dir` that also contains a decoy unlisted `autodev-*` file, which must have no effect)
- [ ] `finalize_done` stays the thin ENH-3619 call and ENH-3619's structural gate stays green
- [ ] Golden parity: ENH-3619's fixtures still match, minus the new `record_absent` / `record_ledger_mismatch` keys and report lines
- [ ] Exit codes are unchanged from ENH-3619: `phantom` → 1, error → 2, every other verdict → 0
- [ ] `autodev.yaml` references only markers the Marker disposition table allows, in the positions it allows (grep gate driven by that table; dead markers have zero references, including comments)
- [ ] Every autodev exit (`init`-empty queue, normal drain, `finalize_rate_limited`, and the `max_steps` cap through ENH-3619's `finalize_step_capped`) writes a truthful `summary.json` that includes `record_absent` (unit test for the `--stop-reason max_steps` path)
- [ ] When a `prepare-issue` record and the ledger evidence for the same ID disagree per the record ↔ ledger correspondence table (Review Decisions, third review), the ledger row is the count source, `summary.json`'s additive `record_ledger_mismatch` key counts the ID once, and the report lists it; the issue is not reclassified (unit test per table row that can mismatch)
- [ ] Autodev's `skip_inflight` no longer reads `refine-terminal-class`: it runs the three child-ledger greps first, then reads the `prepare-issue` record token; `MISSING` or a failed read (`_error`) is ledgered `refine_failed_infra` from the record alone, and no wrapper terminal writes the sentinel (structural test that `autodev.yaml` has zero `refine-terminal-class` references; behavioral tests for the failure-path `MISSING` route, the success-path `MISSING` route via `check_passed.on_no`, the `_error` route, and a `MISSING` record plus child-ledger row producing no skipped row)
- [ ] `record_absent` and `record_ledger_mismatch` never change `verdict` or the exit code; their report lines print only when the count is > 0, so every existing golden `expected_stdout.txt` is byte-identical (unit test)
- [ ] `record_absent` is computed after `record_abandoned_inflight()`, so an in-flight ID (folded into `autodev-unverified.txt`) is excluded by the ledger filter (covered by the in-flight precedence test)
- [ ] An ID with a `prep-pass-<ID>` file, no or malformed `prepare-issue` record, not in flight, and in no closure or skip ledger is counted once under `record_absent`, never dropped or passed; dequeue-time skips (which have both a `prep-pass-<ID>` file and a skipped row) are never `record_absent`; an in-flight ID counts as `abandoned`, not `record_absent` (unit tests for each)
- [ ] `record_absent` is 0 on every healthy characterization scenario, and each row of the exit-path table (Proposed Solution) is pinned to its bucket
- [ ] No `autodev-prepared.txt` and no new autodev state: `test_fsm_topology.py`'s autodev count is unchanged by this issue
- [ ] When an ID is dequeued twice, the last record wins and the ID is counted once (unit test)
- [ ] `refine-to-ready-issue.yaml` has zero `refine-terminal-class` references (writers, the `resolve_issue` clear, comments), and `prep apply` no longer writes it; ENH-3623's temporary sentinel test is flipped to assert absence
- [ ] `record_ledger_mismatch` is 0 on every healthy characterization scenario, and a single crash-injection-inside-`prep apply` scenario is the only case that exercises a non-zero value
- [ ] The Marker disposition table is re-derived against post-ENH-3623 `autodev.yaml` (fact-log files, `prep-pass-<ID>`, `mark_gate_infra` all have a row) before the grep gate is written
- [ ] The child-written ledger exception is documented in `LOOPS_REFERENCE.md`; `auto-refine-and-implement`'s counts are unchanged; `oracles/resolve-decision` needs no change (its `autodev-decide-ran` mention is a comment only)
- [ ] `docs/ARCHITECTURE.md` describes the parent/child contract (records vs. ledgers, which is the count source, and the `prep-pass-*` dequeued-ID set)

## Parent Issue

Decomposed from ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Status

**Open** | Created: 2026-09-25 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`, applied 2026-09-25): The ledger reads the wrapper's record (`run-records/prepare-issue/<ID>.json`, ENH-3597 layout), not the child's. The body above reflects this.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-25 (re-scored 2026-09-26, after the design-decision review; 2026-09-27 after the ENH-3623 re-point; and 2026-09-27 after ENH-3623 landed and closed)_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 73/100 → MODERATE

### Concerns
- None open. The `decision_unresolved` count source was resolved as ledger-only (Review Decisions, 2026-09-27); `mark_gate_infra` resolved to **keep**; the `record_ledger_mismatch` definition, the `skip_inflight` mechanism, the child-ledger greps, verdict impact and golden-fixture regeneration were resolved by the third review (2026-09-27). Re-score after these edits.

### Outcome Risk Factors
- Deep per-site complexity remains on the `refine-terminal-class` removal: it is a control-flow change to `skip_inflight`'s `MISSING`-record classification (not a mechanical deletion), touching `autodev.yaml`, ~8 sites in `refine-to-ready-issue.yaml`, and `preparation_policy.py`'s `_apply_outcome`.
- Broad enumeration across confirmed sites: 4 core implementation files plus ~10 test files with specific breaking assertions already pinned in Integration Map → Tests, plus 6 documentation files.

## Resolved Concerns
- [resolved 2026-09-27] `blocked_by: ENH-3623` forced a Dependencies hard override (STOP) — ENH-3623 landed and closed (confirmed `done`); the edge was unlinked via `ll-issues link ENH-3600 --blocked-by ENH-3623 --unlink`.
- [resolved 2026-09-27] `format-check`'s stale-CLI-claim cap on Criterion 4 (`ll-issues prep`, no such subcommand) — `ll-issues prep {step,record,apply,explain}` now exists post-ENH-3623; `format-check`'s `stale_cli_flag`/`stale_symbol_ref` keys came back clean.
- [resolved 2026-09-27] `missing_artifacts: true` — `preparation_policy.py`, `ll-issues prep apply`, and `run_dir/prep-pass-<ID>` all confirmed to exist post-ENH-3623; flag cleared from frontmatter.
- [resolved 2026-09-27 by /ll:reconcile-issue] The layered research findings carried stale anchors (scheduled for the post-ENH-3623 refresh) — a fresh `/ll:refine-issue` pass (2026-09-27, post-ENH-3623-landing) re-verified every `autodev.yaml`/`refine-to-ready-issue.yaml`/`preparation_policy.py`/`autodev_summary.py` anchor and the full marker-liveness inventory via code-graph queries plus grep, resolved the autodev thin-shell gate's test-name ambiguity, and reconcile folded the corrections into the Tests directive section.

## Verification Notes

_Collapsed 2026-09-27 (third review)._ The 2026-09-26 `/ll:verify-issues` pass and the
2026-09-26 manual Review Notes are fully superseded: they predate ENH-3619, ENH-3623 and
ENH-3630 landing (they state that `autodev_summary.py` does not exist, cite `blocked_by`
ENH-3606 and the `autodev-prepared.txt` design, and carry pre-cutover anchors). The
current state is recorded in Review Decisions (both 2026-09-27 blocks), the Marker
disposition table and the Integration Map. Git history holds the original text.

## Session Log
- `/ll:wire-issue` - 2026-09-27T23:34:09 - `bfc7c299-f46e-4b01-958a-fe298468cb8a.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-27T22:55:35 - `a2f463b8-cf83-4388-84d1-2b97de36c16c.jsonl`
- `/ll:confidence-check` - 2026-09-27T22:40:21 - `a2f463b8-cf83-4388-84d1-2b97de36c16c.jsonl`
- `/ll:reconcile-issue` - 2026-09-27T22:36:17 - `a2f463b8-cf83-4388-84d1-2b97de36c16c.jsonl`
- `/ll:refine-issue` - 2026-09-27T22:33:14 - `a2f463b8-cf83-4388-84d1-2b97de36c16c.jsonl`
- `/ll:reconcile-issue` - 2026-09-27T22:16:51 - `a2f463b8-cf83-4388-84d1-2b97de36c16c.jsonl`
- `/ll:refine-issue` - 2026-09-27T22:07:09 - `205029d7-7661-47e0-95f4-129e6134efdf.jsonl`
- `/ll:confidence-check` - 2026-09-27T03:42:24 - `7853641e-1dad-4830-bad1-b40be31584c3.jsonl`
- `/ll:wire-issue` - 2026-09-27T02:33:29 - `951684ed-7b41-4bf8-9307-a4474a28eb29.jsonl`
- `/ll:refine-issue` - 2026-09-27T02:22:06 - `e00c47b1-36f2-4288-9df3-a5c841c33968.jsonl`
- `/ll:format-issue` - 2026-09-27T02:13:31 - `eab069d8-1487-4826-8057-122a54e92dfd.jsonl`
- `/ll:confidence-check` - 2026-09-26T20:41:31 - `b6e9bba8-3f37-46ef-bab4-0e3a573a871f.jsonl`
- `/ll:verify-issues` - 2026-09-26T20:09:35 - `57be1948-59d1-446a-b252-a9b0fec818aa.jsonl`
- `/ll:confidence-check` - 2026-09-26T02:52:27 - `28baa352-2934-411c-bced-7bb0e7406cbf.jsonl`
- `/ll:reconcile-issue` - 2026-09-26T02:50:41 - `1a6e3280-98dc-4084-b164-9f1e529dd9fb.jsonl`
- `/ll:refine-issue` - 2026-09-26T02:45:37 - `972291b5-b9f1-4321-9110-477f6b624b3d.jsonl`
- `/ll:confidence-check` - 2026-09-25T21:32:36 - `672e0da1-840e-4b60-a432-7b20e9ebbd01.jsonl`
- `/ll:wire-issue` - 2026-09-25T20:49:53 - `4a475966-a47c-4657-a3e4-16e6706f4c4d.jsonl`
- `/ll:refine-issue` - 2026-09-25T19:53:36 - `52506a27-e6a0-49d9-99b0-9b89990953d8.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:18 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`

## Characterization findings (ENH-3618, 2026-09-26)

- autodev's own `decision_unresolved` stops (written to `autodev-skipped.txt`) are counted under
  `skipped`, while the `decision_unresolved` summary key stays 0 — it reads only the child-written
  `autodev-decision-unresolved.txt`. `record_ledger_mismatch` / the Marker disposition row should decide
  whether that key counts both sources.
- Scores-absent stops write no skipped row and leave the verdict `no-op` (ENH-3606 accepted change 1).
