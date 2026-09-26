---
id: ENH-3600
type: ENH
title: Drive autodev ledger from run records and remove preparation handshake files
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T18:51:51Z'
blocked_by:
- ENH-3606
parent: EPIC-3565
relates_to:
- ENH-3577
reconcile_attempted: true
confidence_score: 90
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
missing_artifacts: true
---

# ENH-3600: Drive autodev ledger from run records and remove preparation handshake files

## Summary

Move `finalize_done` into a tested Python module. Add per-issue `prepare-issue` run
records to its inputs so that an issue which crashes during preparation is surfaced
(`record_absent`). Delete the preparation handshake files left over after ENH-3606. This
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

- Read per-issue run records directly from `${context.run_dir}/run-records/prepare-issue/<ID>.json`
  (ENH-3597 layout; the wrapper record is authoritative). No copy step.
- Move `finalize_done`'s logic into a Python function (e.g. `little_loops.autodev_summary`)
  with a thin shell state calling it; unit-test it directly.
- **Missing or malformed record**: a dequeued issue may have no record if it crashed,
  hit `max_steps`, exhausted its rate-limit retries (BUG-3567) or was interrupted by a
  handoff. `build_summary` counts such an issue as `retryable_error` with reason
  `record_absent`. It never drops the issue, and never counts it as passed.
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

- **Source of the prepared-ID set.** Add an append-only `autodev-prepared.txt`. A
  one-line pre-state of `refine_current` appends the in-flight ID before the wrapper
  runs. `init` pre-creates the file, and `dequeue_next` never clears it. `build_summary`
  applies `record_absent` **only** to IDs in this file. Issues skipped at dequeue
  (`skip_already_resolved`, `skip_blocked`, `defer_gated`) never enter preparation, so
  they never produce a `prepare-issue` record and must not be counted as
  `retryable_error`. The set cannot come from enumerating
  `run-records/prepare-issue/*.json`: an issue that crashed before writing a record is
  missing from that directory.
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
  wins. A duplicate line in `autodev-prepared.txt` counts once (`sort -u` semantics).
  Pin both with a test.
- **Exit codes.** `main(argv) -> int` keeps today's routing exactly: `phantom` → exit 1
  → `on_no: failed`, and any exception or unreadable input → exit 2 → `on_error: failed`.
  Every other verdict exits 0. Name them with `EXIT_*` constants (the `fleet_improve.py`
  pattern).
- **Stdout report.** `finalize_done` prints a human-readable report to stdout today: the
  Passed, Skipped, Spike-inconclusive, Proposal-unsound, Unverified, Stopped-early and
  similar lines. The Python version reproduces it line for line, plus the new
  `record_absent` line. The golden fixtures (see Tests) pin this.
- **`max_steps` exit.** Out of scope. The executor's step-cap exit bypasses
  `finalize_done` (`fsm/executor.py`, no `on_max_steps` handler), so no `summary.json`
  is written on that path today. The "every exit" AC below names the exits it covers;
  the step-cap gap stays a known limitation. Document it in `LOOPS_REFERENCE.md`, or
  capture a follow-up if the implementer finds it cheap to close.

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

## Sequencing

Three independent steps. Each can land as its own commit, or as its own issue if the
implementer prefers:

1. **Behavior-identical extraction**: golden fixtures, the `little_loops.autodev_summary`
   module and a thin `finalize_done`. No record reads and no marker changes. This step
   does **not** depend on ENH-3606 and may land before it. Rebase the fixtures only if
   ENH-3606 changes a ledger that `finalize_done` reads.
2. **Record-driven accounting** (after ENH-3606): the `autodev-prepared.txt` ledger,
   `record_absent`, the record-vs-ledger disagreement warning, and the dequeued-twice
   rule.
3. **Marker cleanup and docs** (after ENH-3606): re-derive the Marker disposition table,
   add the table-driven grep gate, remove dead references, update `README.md` /
   `LOOPS_REFERENCE.md` / `ARCHITECTURE.md`, and document the child-ledger exception.

## Integration Map

_Line anchors throughout this section and the Codebase Research Findings predate
ENH-3606, which moves about 40 autodev states. Treat them as historical. Refresh them,
and collapse the layered findings into one current map, when ENH-3606 lands._

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`
- ⚠ Superseded (2026-09-26 review): `scripts/little_loops/loops/refine-to-ready-issue.yaml` needs no change. It keeps writing the three child ledgers as a documented exception (see Marker disposition); only its header comments that cite autodev states may need touching.
- ⚠ Superseded (2026-09-26 review): `scripts/little_loops/loops/auto-refine-and-implement.yaml` needs no change. It keeps reading `autodev-decision-unresolved.txt`, and its counts must stay unchanged.
- `scripts/little_loops/loops/autodev.yaml` — new one-line pre-state before `refine_current` that appends to `autodev-prepared.txt`; `init` pre-creates that file
- new `scripts/little_loops/autodev_summary.py` (or equivalent)
- `docs/ARCHITECTURE.md` — add new parent/child contract prose (no loop/FSM section exists; placement is the implementer's call)
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` needs no change: its `autodev-decide-ran` mention (~:249) is a comment only; autodev alone writes/reads that marker (finding: "comments only (verified)")

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md` — `autodev` (:34) and `refine-to-ready-issue` (:31) catalog rows describe the run_dir marker pattern; update as markers go [Agent 1 finding]

### Tests
- **Golden fixtures first (step 1, before touching `finalize_done`)**: run each existing
  `_run_finalize_done` scenario (promotion, phantom, no-op, rate-limit, quality split,
  cancelled split, abandoned in-flight) against the current shell action. Commit the
  resulting `summary.json` and stdout as fixtures under `scripts/tests/fixtures/`. The
  Python module must reproduce them exactly, apart from the additive `record_absent` key
  and report line. This replaces the `bash -c` harness as the behavioral net.
- New unit tests for summary construction from records
- `summary.json` truthfulness on every exit (EPIC-3565 AC) incl. rate-limit exits (BUG-3567)
- Structural, rewrite: `test_builtin_loops.py` `TestAutodevLoop` (:6643; `finalize_done` behavioral coverage via `_run_finalize_done` under `bash -c`, which stops exercising the logic once it moves to Python). `test_autodev_loop.py` has zero `finalize_done` references (per-iteration markers only); `test_fsm_topology.py` only pins the autodev state count (105)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_autodev_decision_gate.py` — pins `autodev-decide-ran` in `mark_decide_ran_at_dequeue` (:160), `record_decision_unresolved`'s ledger write (:1028), design-remedy attempted markers (:732, :739), and four `on_rate_limit_exhausted == "finalize_rate_limited"` pins (:459, :471, :606, :727) — breaks as markers/routing move [Agent 1 finding]
- `scripts/tests/test_spike_verdict_routing.py` — `test_autodev_routing_table` (:107-108) asserts `autodev-spike-inconclusive.txt` in `skip_inflight` AND `init`; `test_autodev_ledgers_proposal_unsound_stop_not_as_refine_failed` (:229) pins the exact `grep -qxF "$ID" ... autodev-proposal-unsound.txt` line — both break [Agent 1 finding]
- `scripts/tests/test_auto_refine_closure_accounting.py` — seeds `autodev-passed.txt` (:116) against a real mini project (`_make_project` :43); the closest fixture precedent for `build_summary` closure tests [Agent 3 finding]
- `scripts/tests/test_recursive_finalize.py:134` — seeds `autodev-new-children.txt` [Agent 1 finding]
- `scripts/tests/test_builtin_loops.py` — breaking sites beyond `TestAutodevLoop`: `TestRefineToReadyIssueSubLoop.test_proposal_revision_failure_routing` (:3161, `autodev-proposal-unsound.txt` in action), the `autodev-decide-ran` trio (:9378, :9448, :9457), the `skip_inflight` ledger pair (:7949, :7961), `TestAutoRefineAndImplementLoop._run_finalize` harness (:5018) + literal-filename gates (:5634, :5663), the loop-state set pin (:7913), `MR11_MARKER_ALLOWLIST` (:21037, asserted :21249), and the `TestInterpSweepBaseline` bidirectional ratchet (:20974) [Agent 3 finding]
- `scripts/tests/test_fleet_improve.py` — the module-test pattern for `autodev_summary`: `main(argv)` + `EXIT_*` constants, malformed-JSON → `EXIT_ERROR` (`test_cmd_select_bad_sidecar_exit_2` :328); plus `TestFleetLoopImproveLoop.test_shell_states_call_helper_module_not_inline_logic` (:21440 in test_builtin_loops.py) — the thin-shell structural gate to imitate for the rewritten `finalize_done` [Agent 3 finding]

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `init` deletes the shared `run_dir/summary.json` (:95) and `finalize` overwrites it (:1255), so autodev's summary.json is transient on the sprint path; `finalize` reads six ledger files plus `autodev-queue.txt` (`recheck_set` :477 residual fold-back) — any ledger in the removal set orphans its counts, and if the child stops writing `autodev-decision-unresolved.txt`, `DECISION_UNRESOLVED` undercounts child-side unresolved [Agent 2 finding]
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — `read_outcome` cats and `record_crash` overwrites the same shared `summary.json` path (third writer) [Agent 2 finding]
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — writes `decide-options-deposited-<ID>` (:56) and `decide-rate-limited-<ID>` handshake markers autodev reads (`dequeue_next`, `check_decide_rate_limited`); not `autodev-`-prefixed, so the AC's "No `autodev-*` preparation marker" wording does not cover them — they remain the cross-loop run-dir contract after this issue [Agent 2 finding]
- `scripts/little_loops/fsm/executor.py:653` — no `on_max_steps` handler exists, so the step-cap exit calls `_finish("max_steps")` without passing through `finalize_done`: no summary.json on that path today (the parent compensates on the sprint path only) — the every-exit AC's known gap [Agent 2 finding]
- `scripts/little_loops/fsm/persistence.py` (`archive_run`), `scripts/little_loops/cli/loop/audit.py`, `scripts/little_loops/cli/loop/evidence.py`, `scripts/little_loops/hooks/pre_compact_handoff.py` — shape-agnostic summary.json consumers; safe under key-shape preservation [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — autodev section (:1013-1087) documents the marker vocabulary (:1033, :1035, :1079, :1083, :1085) and the parent/child closure-accounting contract (:1007) — prune marker references as they are removed; the end-user account stays here even after the ARCHITECTURE.md contract lands [Agent 1+2 finding]
- `docs/reference/DEFERRAL_CODES.md:30` — names `autodev-scores-absent.txt` / `autodev-gate-infra.txt` by filename [Agent 1 finding]
- `docs/reference/COMMANDS.md:944` — `ll-loop audit` phantom/honest-failure classification keyed on summary.json presence and claimed-success counters [Agent 2 finding]
- `skills/audit-loop-run/SKILL.md:271` — documents autodev's summary keys (`not_started`, `notstarted_*`, `refine_failed_infra`, `oversized_atomic`); update for the FEAT-3573 key split [Agent 2 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Preserve `summary.json`'s key set through the Python rewrite — `test_auto_refine_closure_accounting.py`, `TestAutoRefineAndImplementLoop` key assertions, and MR-13's `"abandoned"`-key emission requirement all depend on it; MR-13's shell-text scan goes vacuously silent when the printf moves to Python, so its enforcement shifts to the new module's unit tests
- Keep autodev's four interpolation-baseline entries valid (`check_blockers_at_dequeue`, `check_reconcile_needed`, `check_spike_needed`, `check_spike_needed_before_skip`); the thin `python3 -m little_loops.autodev_summary --run-dir ${context.run_dir}` call is plain interpolation and needs no new entry
- Migrate `auto-refine-and-implement.yaml`'s `autodev-decision-unresolved.txt` count together with the child's writer, or document the closure-ledger exception — the six ledger reads plus `recheck_set`'s queue read stay by Scope Boundaries
- Decide `decide-options-deposited-<ID>` / `decide-rate-limited-<ID>` (resolve-decision handshake, not `autodev-`-prefixed) — keep or migrate; the AC grep gate's wording must name what it covers
- Add the thin-shell structural gate (`test_shell_states_call_helper_module_not_inline_logic` pattern, :21440) for the rewritten `finalize_done`
- Update `scripts/little_loops/loops/README.md` rows and `docs/guides/LOOPS_REFERENCE.md` marker references as markers are removed

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Medium - summary builder moved to Python plus marker removal
- **Risk**: Medium - summary.json truthfulness is an EPIC-3565 invariant
- **Breaking Change**: No - summary.json keeps its 16 keys; `record_absent` is additive (no consumer asserts an exact key set)

## Program Design

### Types

- `AutodevSummary: dataclass` — the `summary.json` payload built from run records and closure accounting

### Signatures

- `build_summary(run_dir: Path) -> AutodevSummary` — reads `run-records/prepare-issue/<ID>.json` for each ID in `autodev-prepared.txt` plus the Scope Boundaries files; an absent/malformed record for a prepared, not-in-flight, otherwise-unledgered ID counts as `record_absent`
- `write_summary(run_dir: Path, summary: AutodevSummary) -> Path` — writes `summary.json` via `atomic_write_json`
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

## Scope Boundaries

- **Queue and closure-accounting files stay.** These are the only non-record inputs
  `build_summary` may read:
  - queue: `autodev-queue.txt`, `autodev-inflight`, `autodev-input.txt`, and the new
    `autodev-prepared.txt`;
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
  the count, and `build_summary` emits a warning line naming the ID. It does not
  reclassify the issue.
- `summary.json` keys keep their shape **as of FEAT-3573**, which builds on ENH-3613's
  cancelled/implemented split (`closed_implemented`/`closed_cancelled`, derived in
  memory in the promotion loop — no ledger file). The one addition is the
  `record_absent` key (see Design decisions).
- Out of scope: the `max_steps` exit gap; migrating the child-written ledger readers
  (documented exception); and the `resolve-decision` handshake markers
  `decide-options-deposited-<ID>` / `decide-rate-limited-<ID>`, which stay as the
  cross-loop run-dir contract.

### Marker disposition

The AC grep gate checks against this table, not a bare `autodev-*` prefix. Re-derive the
table from post-ENH-3606 `autodev.yaml` as the first implementation step, because
ENH-3606 moves and renames states.

| Class | Files | Disposition |
|---|---|---|
| Queue / closure accounting | listed in Scope Boundaries | stay |
| Shared per-pass state (ENH-3606 keeps the names; the wrapper writes them, and autodev's `dequeue_next` is their only cleaner) | `autodev-repair-cycle-count.txt`, `autodev-pre-readiness.txt`, `autodev-design-gate-failed-<ID>`, `autodev-design-remedy-attempted-<ID>`, `autodev-atomic-design-remedy-pending`, `autodev-contradiction-reconcile-*`, `autodev-go-no-go-attempted-<ID>`, `autodev-pre-deferral-remedy*`, `autodev-size-review-ran-this-pass`, `autodev-rescore-retry-*`, `autodev-rescore-origin-<ID>`, `autodev-reentry-*` | stay. `autodev.yaml` may reference them **only** in `init` / `dequeue_next` clears |
| Decomposition diff | `autodev-pre-ids.txt`, `-post-ids.txt`, `-diff-ids.txt`, `-new-children.txt`, `autodev-broke-down` | stay (queue-owned child detection) |
| Child-written ledgers (documented exception) | `autodev-decision-unresolved.txt`, `autodev-spike-inconclusive.txt`, `autodev-proposal-unsound.txt` | The child keeps writing them, and `auto-refine-and-implement` keeps reading them. `build_summary` also keeps reading them as closure accounting. The `decision_unresolved` key counts **only** this ledger today; the child's `record_decision_unresolved` writes no `autodev-skipped.txt` row, while autodev's own `decision_unresolved` rows go to `autodev-skipped.txt`. Counting that key from records would pull in the wrapper's `record_reentry_exhausted` stops and change the count. Inside `autodev.yaml`, the only references left are `init` truncation and `skip_inflight`'s grep-before-`refine_failed` (~:597). Remove the grep if a test shows `route_refine_outcome`'s record-token routing already covers it (`BLOCKED:decision_unresolved` → `ledger_child_stop`, ~:532) |
| Dead | `autodev-scores-absent.txt` (writer deleted by ENH-3606), `autodev-pre-spike-readiness.txt`, and any other file with no writer after ENH-3606 | delete every reference |

## Behavior Parity

What the rewrite of `finalize_done` must preserve, and what is allowed to change:

- **Preserved exactly**: all 16 FEAT-3573-as-of `summary.json` keys and their values;
  the verdict ladder (success → partial → phantom → not_started → no-op, with the
  `rate_limit` stop reason overriding to `rate_limited`); the staged → passed/unverified
  promotion and its writes to `autodev-passed.txt` / `autodev-unverified.txt`; the stdout
  report lines; and the exit code per verdict. The golden fixtures enforce all of this.
- **Intentionally changed**: the additive `record_absent` key and its report line; the
  new `autodev-prepared.txt` ledger; and a warning line when a record and a ledger row
  disagree. Nothing else in `summary.json` changes.
- **Unchanged files**: `refine-to-ready-issue.yaml` and
  `auto-refine-and-implement.yaml` behave the same (the child-ledger exception), and
  `auto-refine-and-implement`'s summary counts are identical on the same input.
- **MR-13**: the `abandoned` key requirement moves from the shell-text scan to the
  module's unit tests, because the printf no longer lives in YAML.

## Acceptance Criteria

- [ ] `build_summary` reads only `run-records/prepare-issue/*.json` plus the files listed in Scope Boundaries (unit test with a `run_dir` that also contains a decoy unlisted `autodev-*` file, which must have no effect)
- [ ] `finalize_done` is a thin shell state calling `python3 -m little_loops.autodev_summary … --run-dir ${context.run_dir}`, with no inline summary logic (structural gate modelled on `test_shell_states_call_helper_module_not_inline_logic`, plus an explicit absence assertion)
- [ ] Golden parity: for every existing `_run_finalize_done` scenario, the Python module's `summary.json` (minus the new `record_absent` key) and stdout report match fixtures captured from the pre-change shell `finalize_done`
- [ ] Exit codes are unchanged: `phantom` → 1, error → 2, every other verdict → 0 (unit test per verdict)
- [ ] `autodev.yaml` references only markers the Marker disposition table allows, in the positions it allows (grep gate driven by that table; dead markers have zero references, including comments)
- [ ] The `finalize_done` path (`init`-empty queue, normal drain, `finalize_rate_limited`) writes a truthful `summary.json`; the `max_steps` gap is documented as a known limitation
- [ ] An ID in `autodev-prepared.txt` with no or malformed `prepare-issue` record, not in flight, and in no closure or skip ledger is counted once under `record_absent`, never dropped or passed; dequeue-time skips are never `record_absent`; an in-flight ID counts as `abandoned`, not `record_absent` (unit tests for each)
- [ ] When an ID is dequeued twice, the last record wins and the ID is counted once (unit test)
- [ ] The child-written ledger exception is documented in `LOOPS_REFERENCE.md`; `auto-refine-and-implement`'s counts are unchanged; `oracles/resolve-decision` needs no change (its `autodev-decide-ran` mention is a comment only)
- [ ] `docs/ARCHITECTURE.md` describes the parent/child contract (records vs. ledgers, which is the count source, and the prepared-ID set)

## Parent Issue

Decomposed from ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Status

**Open** | Created: 2026-09-25 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`, applied 2026-09-25): The ledger reads the wrapper's record (`run-records/prepare-issue/<ID>.json`, ENH-3597 layout), not the child's. The body above reflects this.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-25 (re-scored 2026-09-26, again after the design-decision review)_

**Readiness Score**: 90/100 → STOP — ADDRESS GAPS (Dependencies hard override; raw sum is PROCEED)
**Outcome Confidence**: 63/100 → MODERATE

### Concerns
- ✅ RESOLVED (2026-09-26 review): Grep-gate scope — now scoped by the Marker disposition table.
- ✅ RESOLVED (2026-09-26 review): `decide-options-deposited-<ID>` / `decide-rate-limited-<ID>` handshake markers — kept as the cross-loop contract (out of scope).

### Gaps to Address
- `blocked_by: ENH-3606` is `open`, so the dependency gate forces STOP. Sequencing step 1 (golden fixtures, `autodev_summary` module, thin `finalize_done`) does not depend on ENH-3606. Either land ENH-3606 first, or drop/relax `blocked_by` and implement only step 1 now (steps 2–3 need ENH-3606).
- ✅ RESOLVED (2026-09-26 review): Dequeued-ID source — `autodev-prepared.txt` (Design decisions).

### Outcome Risk Factors
- Deep per-site complexity: `finalize_done` (~300 lines of inline shell) rewritten into Python while preserving the 16-key `summary.json` shape, verdict ladder and exit-code routing exactly.
- Broad enumeration across ~15+ sites (loop YAML, new module, 5+ test files, README, LOOPS_REFERENCE, ARCHITECTURE), with several existing tests that break as markers move; ENH-3606 will shift the line anchors and the Marker disposition table must be re-derived first.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-26_

Verdict at time of check: **NEEDS_UPDATE** (corrections below are recorded here rather than rewritten into the sections above; the body's older anchors and "still open" statements should be read through them — this section is the current-state record, not an outstanding code defect)

Graph: provider=`codegraph` freshness=`stale` (not used to originate any verdict; findings confirmed by Grep/Read). `ll-verify-evidence`: clean.

- **All `blocked_by` edges are resolved**: ENH-3611, ENH-3601, FEAT-3573, ENH-3613 are all `done`, as are ENH-3597, ENH-3599 and ENH-3577. The Confidence Check Notes' "(all open)" gap and its ENH-3599 blocker mention are stale; the frontmatter `blocked_by` list can be dropped on the next refine. Confidence scores predate this and should be re-scored.
- **`writer=prepare-issue` producer now exists**: `loops/prepare-issue.yaml` (ENH-3605) forwards the record, and `autodev.yaml` already reads it (`ll-issues run-record read … --writer prepare-issue --format token` at :520, :678). The "no producer / no run-record read in autodev.yaml" finding no longer holds.
- **`finalize_done` moved**: now `autodev.yaml:2985-3286` (`finalize_rate_limited` :2973, `failed` :3287, `done` :3290); the loop has 90 states (not 105 — ENH-3611 removed the spike/decision states). The `summary.json` printf now emits **sixteen** keys (adds `closed_implemented`, `closed_cancelled`, `quality_failed`, `quality_gate_infra`), so the "twelve keys" finding is superseded by the Scope Boundaries' FEAT-3573-as-of shape.
- **Markers already gone from autodev.yaml**: `autodev-decide-ran` (0 refs) and `autodev-spike-no-verdict.txt` (0 refs) — ENH-3611 removed their writers/readers. Still present: `autodev-decision-unresolved` (4), `autodev-spike-inconclusive` (3), `autodev-proposal-unsound` (3), `autodev-proof-gate-infra` (4), plus `pre-readiness`, `repair-cycle-count`, `contradiction-reconcile-count`, `new-children` — the grep-gate scope question remains open.
- **Child writers** in `refine-to-ready-issue.yaml` are now at :692 (`proposal-unsound`), :1235 (`spike-inconclusive`), :1269 (`decision-unresolved`); the `autodev-decide-ran` mention at :907 is a comment only. `auto-refine-and-implement.yaml`'s reader is now :1135 (`DECISION_UNRESOLVED=$(count autodev-decision-unresolved.txt)`), not :1112.
- **Test anchors drifted**: `TestAutodevLoop` :6409, `_run_finalize_done` :7209, thin-shell gate `test_shell_states_call_helper_module_not_inline_logic` :21017 (earlier :6643/:7475/:21491).
- **Still accurate**: `autodev_summary.py` / `build_summary` / `record_absent` do not exist; `run_record.py` and `read_run_record` exist; `autodev.yaml` has zero `python3 -m little_loops` calls; the dequeued-ID-source design question is still open (no cumulative dequeue ledger).
- **B6 (proposal-vs-code)**: no unsound mechanism found; the `record_absent` requirement remains unsatisfiable by enumerating `run-records/prepare-issue/*.json` alone (already flagged).

Remaining: none applied to body sections in this pass (auto mode; anchors left as historical research findings).

## Review Notes

_Added by manual review — 2026-09-26_

- `blocked_by` now points at ENH-3606, which declares `blocks: [ENH-3600]` and leaves
  ledger and sentinel removal to this issue. The four previous blockers are all `done`.
- Resolved the open design questions that held readiness down: the prepared-ID source
  (`autodev-prepared.txt`), where `record_absent` is reported and how it ranks against
  the in-flight counts, the grep-gate scope (Marker disposition table), the child-marker
  handling (documented exception), `max_steps` (out of scope), and records vs. ledgers
  as the count source (ledgers).
- Added golden-fixture parity, exit-code and stdout-report criteria, plus a three-step
  sequencing plan in which step 1 can land before ENH-3606.
- The confidence scores (75/55) predate these changes. Re-score after ENH-3606 lands.

## Session Log
- `/ll:confidence-check` - 2026-09-26T20:41:31 - `b6e9bba8-3f37-46ef-bab4-0e3a573a871f.jsonl`
- `/ll:verify-issues` - 2026-09-26T20:09:35 - `57be1948-59d1-446a-b252-a9b0fec818aa.jsonl`
- `/ll:confidence-check` - 2026-09-26T02:52:27 - `28baa352-2934-411c-bced-7bb0e7406cbf.jsonl`
- `/ll:reconcile-issue` - 2026-09-26T02:50:41 - `1a6e3280-98dc-4084-b164-9f1e529dd9fb.jsonl`
- `/ll:refine-issue` - 2026-09-26T02:45:37 - `972291b5-b9f1-4321-9110-477f6b624b3d.jsonl`
- `/ll:confidence-check` - 2026-09-25T21:32:36 - `672e0da1-840e-4b60-a432-7b20e9ebbd01.jsonl`
- `/ll:wire-issue` - 2026-09-25T20:49:53 - `4a475966-a47c-4657-a3e4-16e6706f4c4d.jsonl`
- `/ll:refine-issue` - 2026-09-25T19:53:36 - `52506a27-e6a0-49d9-99b0-9b89990953d8.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:18 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`
