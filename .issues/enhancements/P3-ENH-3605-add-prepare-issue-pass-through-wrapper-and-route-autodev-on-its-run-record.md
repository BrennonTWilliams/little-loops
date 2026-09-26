---
id: ENH-3605
type: ENH
title: Add prepare-issue pass-through wrapper and route autodev on its run record
priority: P3
status: done
discovered_by: issue-size-review
discovered_date: '2026-09-26'
decision_needed: false
blocked_by:
- ENH-3611
- ENH-3602
blocks:
- ENH-3606
- ENH-3600
relates_to:
- ENH-3590
- ENH-3577
- ENH-3607
- ENH-3609
parent: ENH-3601
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
completed_at: '2026-09-26T18:32:04Z'
---

# ENH-3605: Add prepare-issue pass-through wrapper and route autodev on its run record

## Summary

First half of ENH-3601 (Option B), re-cut on 2026-09-26. Add `prepare-issue` as a
pass-through wrapper around `refine-to-ready-issue`, point autodev's `refine_current` at it,
and switch autodev's two run-record routers from `--writer refine-to-ready-issue` to
`--writer prepare-issue`. **No autodev state moves here.** ENH-3606 moves the whole
second-pass cluster in one change. This child proves the three-level passthrough chain,
record forwarding, the infra/rate-limit terminals and the ledger-ownership rule before any
routing moves.

## Why the re-cut

The original split moved wire/refine and reconcile/design remedy here, and size-review,
go/no-go and pre-deferral remedy to ENH-3606. Those states form one strongly connected
cluster: reconcile → size-review → `recheck_after_size_review` → pre-deferral remedy →
reconcile. The moved states route into `check_size_review_ran_this_pass`,
`recheck_after_size_review`, `check_go_no_go_eligible`, `dispatch_pre_deferral_remedy` and
`enqueue_or_skip`. A `loop:` child cannot route into its parent's states, and no
`PreparationOutcome` value means "continue with size-review in autodev". So the original
ENH-3605 could not land alone without dangling edges or a behavior change on `main`, which
is live in every local-editable project. A plumbing-then-move split gives two
behavior-preserving changes that can each land on their own.

## Parent Issue

Decomposed from ENH-3601: Move autodev second-pass preparation routing into a preparation
controller. See the parent for the Option B decision rationale.

## Current Behavior

After ENH-3607 and ENH-3609–3611 land:

- Autodev's `refine_current` is `loop: refine-to-ready-issue` with `context_passthrough: true`.
- `route_refine_success` (entered from `copy_broke_down`) and `route_refine_outcome` (entered
  from `refine_current.on_failure`) read
  `ll-issues run-record read <ID> --run-dir ${context.run_dir} --writer refine-to-ready-issue --format token`.
- `skip_inflight` writes `ID  refine_failed` for `BLOCKED:quality` / `DEFERRED:gate_unmet`
  failure stops; `ledger_child_stop` clears `autodev-inflight` without writing a row.
- `prepare-issue.yaml` does not exist, although `little_loops.run_record` already accepts the
  `prepare-issue` writer.

## Expected Behavior

The call chain is `autodev` → `prepare-issue` → `refine-to-ready-issue`. For every token,
autodev's route and the set of ledger rows it produces match the pre-change behavior. The
only change autodev sees is the writer it reads.

## Scope Boundaries

- **In scope**: the new wrapper YAML, the `refine_current` retarget, the router writer switch,
  the wrapper's forward and terminal states, a `run-record forward` CLI subcommand, the
  ledger-ownership rule, and tests/docs for the new loop.
- **Out of scope**: moving any autodev state (ENH-3606); removing legacy sentinels
  (ENH-3600); changes to `refine-to-ready-issue.yaml` or its other caller
  `recursive-refine.yaml`; widening the go/no-go trigger.

## Proposed Solution

### `prepare-issue.yaml`

1. **`clear_record`** (entry): `ll-issues run-record clear ${context.input:shell} --run-dir
   ${context.run_dir} --writer prepare-issue || true`, then the same `clear` with
   `--writer refine-to-ready-issue`. This uses ENH-3607's `clear` with canonical ID
   resolution, not a raw-ID `rm -f`. Clearing the inner writer too is hardening: autodev
   re-enters `refine_current` for the same ID (the DECISION/PROOF selectors and
   `dispatch_pre_deferral_remedy`), and if the inner loop dies before its own
   `resolve_issue` clear, `forward` would otherwise copy the previous pass's record. Autodev
   reads that stale record directly today, so this is not a regression fix.
2. **`run_refine_to_ready`**: `loop: refine-to-ready-issue`, `context_passthrough: true`, no
   `timeout:` (`TestSubLoopStateTimeoutAudit`), and no `with_rate_limit_handling` /
   `on_rate_limit_exhausted` (inert on `loop:` states, BUG-3390). Routes: `on_yes` →
   `forward_done`, `on_failure` → `forward_stop`, `on_error` → `mark_inner_error`.
3. **`forward_done` / `forward_stop`**: run
   `ll-issues run-record forward <ID> --run-dir ${context.run_dir} --from refine-to-ready-issue --writer prepare-issue`.
   This rewrites the inner record under the wrapper's writer and copies `outcome`,
   `legacy_class`, `child_ids`, `evidence_refs`, `readiness` and `outcome_confidence`
   unchanged. `forward_done` ends in a success terminal and `forward_stop` in a failure
   terminal, so the wrapper mirrors the inner terminal type. Autodev therefore still enters
   `route_refine_success` through `on_yes` and `route_refine_outcome` through `on_failure`.
   When the inner record is missing, `forward` writes nothing and autodev reads `MISSING` →
   `skip_inflight`, as today.
   - **Terminal type must survive a forward error**: `forward_done.on_error` → the success
     terminal and `forward_stop.on_error` → the failure terminal. Otherwise a failed
     `forward` call flips which autodev router runs.
   - **Terminals**: declare the failure terminal with an explicit `failure: true` (the
     `refine-to-ready-issue.yaml` `failed` pattern), because autodev's `on_failure` routing
     depends on it rather than on name inference.
   - **`forward_stop` row write**: `forward_stop` branches on the token `forward` prints
     (see below). For `BLOCKED:quality` and `DEFERRED:gate_unmet` only, it appends
     `ID  refine_failed` to `${context.run_dir}/autodev-skipped.txt`. `ID` is the raw
     `${context.input}`, not the canonical ID: `skip_inflight` writes the raw
     `captured.input.output` today, and `finalize_done` and the `grep -x` marker checks key on
     that exact string.
4. **`mark_inner_error`**: the inner loop died (`terminated_by` of `error`, `no_route` or
   `workdir_vanished`). Write `printf infra > ${context.run_dir}/refine-terminal-class`,
   then write the record with `--legacy-class infra`, and end in the failure terminal.
   Autodev routes `RETRYABLE_ERROR:infra` → `skip_inflight_infra`, which writes the same
   `refine_failed_infra` row that `refine_current.on_error` produces today. (A wrapper
   cannot end with `terminated_by: error` on purpose, so this record is how the error
   reaches autodev.) The sentinel write is required: the record write is `|| true`, and if
   it fails autodev reads `MISSING` → `skip_inflight`, which falls back to
   `refine-terminal-class`. The inner loop's `resolve_issue` deleted that file, so without
   the sentinel the infra crash is ledgered as `refine_failed`. Every inner `mark_*_infra`
   state writes the sentinel the same way.
5. **Rate limits**: this child adds no wrapper slash states, so there is no wrapper-local
   rate-limit terminal. An inner `mark_rate_limit_infra` record carries
   `evidence_refs: [rate_limit_exhausted]`, is forwarded unchanged, and still sends autodev
   to `finalize_rate_limited`.
6. **Mechanics**: declare `scope:` (BUG-3107). Take the ID from `${context.input}`:
   passthrough flattens autodev's `captured.input` into the child's context
   (`FSMExecutor._execute_sub_loop`), so `${captured.input.output}` does not resolve in the
   wrapper. Re-declare no `pruning_profile:` blocks (the wrapper has no slash states yet).
   Run `ll-loop validate` (MR-3/7/9/11/14, capture reachability, `scope:`).
   Two passthrough traps:
   - Do not declare `input` in the wrapper's own `context:` block. The child context is
     `{**parent.context, **flatten(parent.captured), **child.context}`, so the wrapper's own
     literal wins and would hide the issue ID.
   - Wrapper `capture:` names flatten into the inner loop's context. Do not use names that
     collide with inner context keys (`input`, `run_dir`, `readiness_threshold`,
     `outcome_threshold`, `input_hash`).

### `ll-issues run-record forward` (new)

Add `cmd_run_record_forward` to `little_loops.cli.issues.run_record`. It resolves the
canonical ID like `read` and `clear`, reads the `--from` writer's record, and writes it
under `--writer` with only `writer` changed (`read_run_record` rejects a stored `writer`
that does not match the request, so the field must be rewritten). It exits 0 in every case
and prints the forwarded record's routing token (`record_token`, the same words
`read --format token` prints), or `MISSING` when the `--from` record is absent. Printing
the token lets `forward_stop` branch without a second `read` call. Update the `run-record`
dispatch and parser help.

### Autodev changes

- `refine_current`: `loop: prepare-issue`. Keep `context_passthrough: true` and the BUG-2611
  shape (no `on_no`; `on_failure` → `route_refine_outcome`; `on_error` →
  `skip_inflight_infra`), with no rate-limit fragment. Rewrite its comment block, which
  describes `refine-to-ready-issue`'s terminals directly, to describe the `prepare-issue`
  wrapper.
- `route_refine_success` and `route_refine_outcome` read `--writer prepare-issue`.

### Ledger-ownership rule

State this rule here because ENH-3606 depends on it. After ENH-3606, the wrapper's
second-pass stops keep writing their own `autodev-skipped.txt` rows (`oversized_atomic`,
`design_gate_failed`, `readiness_stagnated`, `low_readiness`, `decision_unresolved`,
`resolved_by_subloop`). They have to, because `finalize_done` and
`auto-refine-and-implement`'s `SKILL_BREAKDOWN` key on those reason strings until ENH-3600.
Their records carry `gate_unmet` or `quality`, and ENH-3609 routes those tokens to
`skip_inflight`, which would add a second `refine_failed` row.

**Rule: the wrapper ledgers every blocked or deferred stop it emits through its failure
terminal. On the failure path, autodev's `route_refine_outcome` routes every suffixed
`BLOCKED:*` and `DEFERRED:*` token it reads from `prepare-issue` to `ledger_child_stop`, which
writes no row.**

The rule is scoped to the failure path. `route_refine_success` keeps sending suffixed tokens
to `skip_inflight`: they cannot occur there, `forward_done` writes no row, and routing them to
`ledger_child_stop` would drop the row instead of failing safe. Unsuffixed `BLOCKED` is not
covered by `BLOCKED:*` and stays on `skip_inflight` in both routers.

In this child that means:

- `forward_stop` writes `ID  refine_failed` for a forwarded `quality` or `gate_unmet` stop
  (the row `skip_inflight` writes today).
- `route_refine_outcome` sends `BLOCKED:quality` and `DEFERRED:gate_unmet` to
  `ledger_child_stop` instead of `skip_inflight`.
- `BLOCKED:decision_unresolved`, `BLOCKED:proposal_unsound` and `DEFERRED:spike_inconclusive`
  already go to `ledger_child_stop`, and the child's marker files remain their ledger.
- `MISSING`, `_` and `_error` still reach `skip_inflight`, which keeps the evidenced exit-143
  and `refine-terminal-class` handling (ENH-2727).
- Net ledger rows are unchanged.

### `next-loop` resolver

No resolver. `prepare-issue` runs only as a sub-loop, so `_scan_history` never sees a
standalone run. A direct `ll-loop run prepare-issue` gets `{}` from the default, which
`test_unknown_loop_returns_empty_dict` already covers. This item is settled.

## Tests

- Registration: `test_builtin_loops.py::test_expected_loops_exist` stem set,
  `test_fsm_fragments.py` `migration_targets`, and
  `TestConfidenceGateThresholdsNotHardcoded.LOOPS`.
- Retarget: `test_refine_current_delegates_to_refine_to_ready_issue` now asserts
  `prepare-issue`, and a new pin asserts that `prepare-issue.run_refine_to_ready` delegates to
  `refine-to-ready-issue`. Also update `test_context_passthrough_on_refine_current` and the
  ENH-3607/3609 router tests to assert `--writer prepare-issue`.
- `scripts/tests/test_prepare_issue.py` (new), modeled on `test_rn_decompose.py` plus the
  `test_run_record.py` two-layer pattern:
  - structural: states, `scope:`, no `timeout:` or rate-limit keys on the `loop:` state,
    terminals, and `--writer prepare-issue` on every write;
  - execution: `forward` preserves `outcome`, `legacy_class`, `child_ids` and
    `evidence_refs`, including `rate_limit_exhausted`;
  - an inner success reaches the success terminal and an inner failure the failure terminal;
  - a `forward` error keeps the terminal type (`forward_done` error → success terminal,
    `forward_stop` error → failure terminal), and the failure terminal declares
    `failure: true`;
  - an inner error writes an `infra` record and `refine-terminal-class=infra`;
  - a missing inner record writes no wrapper record;
  - entry clears a stale wrapper record and a stale inner record;
  - `forward_stop` writes the raw-ID `refine_failed` row for `BLOCKED:quality` and
    `DEFERRED:gate_unmet` only.
- `test_run_record.py`: CLI tests for `run-record forward` (prints the forwarded token,
  MISSING, writer override, canonical ID, and a forwarded record that `read --writer
  prepare-issue` accepts).
- Real-FSM end to end (autodev → `prepare-issue` → stub refine child), one case per token
  class. **Write these first (TDD), against the pre-change autodev on `main`,** pinning the
  expected route and ledger rows per token; they must pass unchanged after the retarget.
  That is the proof of "matches the pre-change behavior".
  - `READY`;
  - `DECOMPOSED`;
  - `CANCELLED`;
  - `BLOCKED:decision_unresolved` (ledgered once);
  - `BLOCKED:quality` (exactly one `refine_failed` row);
  - `DEFERRED:gate_unmet` (exactly one `refine_failed` row);
  - `RETRYABLE_ERROR:rate_limited` → `finalize_rate_limited`;
  - `RETRYABLE_ERROR:infra` → one `refine_failed_infra` row;
  - `MISSING` → `skip_inflight`;
  - `MISSING` with `refine-terminal-class=infra` → one `refine_failed_infra` row (the
    ENH-2727 fallback that `mark_inner_error`'s sentinel write protects).
- Rate-limit pin twin: add `prepare-issue.yaml` to
  `test_no_loop_call_state_declares_on_rate_limit_exhausted` (`test_builtin_loops.py:2892` for refine-to-ready-issue, `:7745` for autodev).
- The BUG-3603 invariant still holds: `TestProofGateFailClosed` asserts
  `implement_current`'s only predecessor is `check_proof_defer_or_implement`.
- `test_fsm_topology.py::test_autodev_topology`: the autodev state count is unchanged.
- Global gates run on the new file automatically: `TestBuiltinLoopFiles`,
  `TestBuiltinLoopReferencesResolve`, `TestMr11MarkerSet`, `TestSubLoopStateTimeoutAudit`,
  `TestHostRunnerEnvSweep`, the scope-lock tests in `test_concurrency.py`, and
  `TestInterpSweepBaseline` (add baseline entries for any unbaselined wrapper site in the
  same commit).

## Docs

- `scripts/little_loops/loops/README.md`; root `README.md` loop count (+1) mirrored with
  `command cp -f README.md scripts/README.md`.
- `docs/ARCHITECTURE.md` loop section; `docs/guides/LOOPS_REFERENCE.md`: new
  `### prepare-issue` section, and the autodev tree shows `refine_current` → `prepare-issue` →
  `refine-to-ready-issue`. Keep the heading "Typed run record (ENH-3597)", which
  `test_wiring_reference_docs.py:260` pins.
- `docs/reference/CLI.md`: the run-record section (`forward`; `prepare-issue` writer now live)
  and `:1359` (`next-loop` has an autodev-only resolver).
- `docs/reference/CONFIGURATION.md:458`: add `prepare-issue` to the loops that must not pin
  confidence thresholds.
- `docs/guides/LOOPS_GUIDE.md` (`:88`, `:395`) and
  `docs/guides/RECURSIVE_LOOPS_GUIDE.md:271-302`: add a wrapper row.
- `skills/audit-loop-run/SKILL.md:119`: `ll-loop show autodev --resolved` now expands
  `prepare-issue`, one level. Then run `ll-adapt --host <gemini|kimi-code|qwen> --apply`.

## Acceptance Criteria

- [ ] `prepare-issue.yaml` exists, wraps `refine-to-ready-issue` with `context_passthrough: true`, and passes `ll-loop validate`
- [ ] Autodev's `refine_current` is `loop: prepare-issue`; both routers read `--writer prepare-issue`; no other autodev state is added or removed
- [ ] Every wrapper terminal writes a `writer: prepare-issue` record that forwards `outcome`, `legacy_class`, `child_ids` and `evidence_refs` unchanged, with two exceptions: a missing inner record deliberately leaves no wrapper record so autodev reads `MISSING`, and `mark_inner_error` writes a new `--legacy-class infra` record plus `refine-terminal-class=infra`
- [ ] A `forward` error keeps the wrapper's terminal type, and the failure terminal declares `failure: true`
- [ ] An inner rate-limit exhaustion still halts autodev through `finalize_rate_limited` (real-FSM test)
- [ ] For each token class, autodev's route and ledger rows match the pre-change behavior, and no stop is ledgered twice (real-FSM tests)
- [ ] `route_refine_outcome` routes every suffixed `BLOCKED:*` / `DEFERRED:*` token read from `prepare-issue` to `ledger_child_stop`, and the wrapper writes the raw-ID row for `quality` / `gate_unmet` stops; `route_refine_success` and unsuffixed `BLOCKED` keep their current `skip_inflight` routes
- [ ] Stale `prepare-issue` and `refine-to-ready-issue` records are cleared on entry through `run-record clear`
- [ ] `refine-to-ready-issue.yaml` and `recursive-refine.yaml` are untouched

## Impact

- **Priority**: P3 - plumbing that unblocks ENH-3606 and ENH-3600; no user-facing defect
- **Effort**: Medium - one small YAML, one CLI subcommand, a router retarget and tests
- **Risk**: Low-Medium - autodev is live in every local-editable project; mitigated by per-token real-FSM parity tests and no state moves
- **Breaking Change**: No

## Integration Map

_Research below was re-scoped on 2026-09-26 for the plumbing-only cut. Findings about the
moved states now live in ENH-3606. Line anchors predate ENH-3607 and ENH-3609–3611._

### Codebase Research Findings

- **Already in place (do not re-create)**: `run_record.py` registers `prepare-issue` in
  `RunRecordWriter` / `WRITERS`, and `test_run_record.py` exercises that writer.
- **Routing on `loop:` states**: `FSMExecutor._execute_sub_loop` maps only the child's
  terminal type and `terminated_by` to `on_yes`, `on_no` (→ `on_failure`), `on_error` and
  timeout routes; it never reads a run record. ENH-3607/3609's routers do the record read, so
  the wrapper must mirror the inner terminal type for autodev to enter the right router.
- **Passthrough binding**: under `context_passthrough`, the child context is
  `{**parent.context, **flatten(parent.captured), **child.context}`. `captured.X` becomes
  `context.X` as a plain string, and each level re-flattens.
- **Rate-limit constraint**: `with_rate_limit_handling` and `on_rate_limit_exhausted` are
  inert on `loop:` states (BUG-3390; pinned by
  `test_no_loop_call_state_declares_on_rate_limit_exhausted`, `test_builtin_loops.py:2892`/`:7745`).
  `outcome_from_legacy_class` yields `retryable_error` only for `--legacy-class infra`;
  ENH-3607's token adds `:rate_limited` when `evidence_refs` contains `rate_limit_exhausted`.
- **`ready` path / BUG-3603**: `ready` reaches implementation only through the fail-closed
  `check_proof_defer_or_implement`. `LEARNING_GATE_BLOCKED` is emitted by `issue_manager.py`
  (~:1216) after `implement_current`. The wrapper cannot bypass the proof gate, because it
  lives in a separate file and emits only records.
- `select_next_obligation` (`cli/issues/next_obligation.py`): the wrapper uses no selector in
  this child (ENH-3606 moves ENH-3610/3611's selectors).

### Conventions in Force

- New top-level loop YAMLs are registered in an exact-set assertion
  (`test_builtin_loops.py::test_expected_loops_exist`, ~:204-305).
- `TestInterpSweepBaseline::test_completeness_guard` (~`test_builtin_loops.py:20505`) fails in
  both directions against `scripts/tests/data/loop_interpolation_baseline.json`.
- Terminal convention in `refine-to-ready-issue.yaml`: each terminal writes the legacy
  sentinel, then
  `ll-issues run-record write <ID> --run-dir ${context.run_dir} --writer <loop> [--legacy-class X] || true`
  in a shell state.
- README loop count lives at `README.md:185`; `doc_counts.py` counts top-level
  `loops/*.yaml`.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/auto-refine-and-implement.yaml`: `loop: autodev` (~:386); reads
  autodev's shared-`run_dir` ledgers. The ledger rows must stay identical.
  `scan-and-implement.yaml:79` also calls `loop: autodev`.
- `scripts/little_loops/loops/recursive-refine.yaml`: second `refine-to-ready-issue` caller
  (`run_refine` ~:237); untouched.
- `scripts/little_loops/cli/issues/run_record.py`: add `forward`; `_read_broke_down` reads the
  shared `<run_dir>/refine-broke-down`, which the inner child still writes.
- `scripts/little_loops/fsm/validation/reachability.py` (`_validate_loop_references`):
  `autodev.refine_current` → `prepare-issue` is a load ERROR until `prepare-issue.yaml`
  exists, so land the YAML and the autodev edit in one commit.
- `scripts/little_loops/fsm/executor.py` (`_execute_sub_loop`): with a three-level
  passthrough chain, autodev's `captured.refine_current` nests one level deeper. No YAML or
  Python reads `captured.refine_current` today.

### Configuration

- `scripts/little_loops/cli/loop/next_loop.py`: no resolver added (see above).
- No change: `pyproject.toml` (`include = ["little_loops/**"]`), `.claude-plugin/*.json`,
  `hooks/`, `config-schema.json`, `fsm/`.

## Implementation Steps

1. Write the real-FSM per-token parity tests against the pre-change autodev on `main` and
   confirm they pass there (they pin the expected route and ledger rows per token).
2. Add `run-record forward` (prints the forwarded token) with CLI tests.
3. Write `prepare-issue.yaml` and `test_prepare_issue.py`.
4. In the same commit: retarget `refine_current` (and rewrite its comment block), switch
   both routers to `--writer prepare-issue`, route `BLOCKED:quality` /
   `DEFERRED:gate_unmet` to `ledger_child_stop` in `route_refine_outcome` only, and move the
   `refine_failed` row write into `forward_stop`. Point the parity tests' stub at the
   three-level chain; they must pass unchanged.
5. Update the registration, retarget and pin tests.
6. Update the docs, README count and mirror; run `ll-adapt` for the skill edit.

**Scope note**: moving the `refine_failed` write into `forward_stop` is the only
behavior-bearing change in this otherwise mechanical child. It stays here because ENH-3606
needs the ledger-ownership rule proven first, and the step-1 parity tests guard it. If it
has to move, it moves to ENH-3606 together with the ledger-ownership rule.

## Program Design

### Types

- `PreparationOutcome`: six-value Literal in `little_loops.run_record` (reused, not extended)
- `RunRecordWriter`: already includes `prepare-issue`

### Signatures

- `cmd_run_record_forward(config: BRConfig, args: argparse.Namespace) -> int` — new; copies the `--from` writer's record under `--writer`
- `read_run_record(run_dir: Path, writer: str, issue_id: str) -> RunRecord | None` — existing (ENH-3597)
- `write_run_record(run_dir: Path, record: RunRecord) -> Path` — existing (ENH-3597)

### Call Path

`autodev.yaml:refine_current` -> `prepare-issue.yaml:run_refine_to_ready` -> `refine-to-ready-issue.yaml`

`prepare-issue.yaml:forward_stop` -> `cmd_run_record_forward` -> `write_run_record` -> `autodev.yaml:route_refine_outcome` -> `cmd_run_record_read`

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of
what was wrong and fixed, not an outstanding action item)

Verified 2026-09-26 against `main` (graph provider `codegraph`, freshness `stale`; graph
results not used). Blockers ENH-3611/ENH-3602 and ENH-3607/3609/3610 are done;
`prepare-issue.yaml` and `run-record forward` do not exist yet; `prepare-issue` is already in
`RunRecordWriter`/`WRITERS`; `refine_current` and both routers match the described pre-change
state. `ll-verify-evidence` clean.

- Fixed stale anchors: rate-limit pin test is at `test_builtin_loops.py:2892` and `:7745`
  (was ~:3335); `TestInterpSweepBaseline` is ~:20505 (was ~:21014); `CONFIGURATION.md`
  confidence-threshold list is :458 (was :456); `auto-refine-and-implement.yaml` `loop: autodev`
  is ~:386 (was ~:381).
- Clarification (not a defect): autodev's success path is `refine_current.on_success` →
  `count_repair_cycle_refine` → `copy_broke_down` → `route_refine_success`; the counter state is
  unchanged by this child.
- Implementation note (superseded by the 2026-09-26 review below): `forward` now prints the
  forwarded token itself, so `forward_stop` branches on its output without a second `read`.

### Review (2026-09-26)

Applied to Proposed Solution, Tests, Acceptance Criteria and Implementation Steps:

- `mark_inner_error` also writes `refine-terminal-class=infra`. Without it, a failed `|| true`
  record write sends autodev to `MISSING` → `skip_inflight`, which finds no sentinel (the
  inner `resolve_issue` deleted it) and ledgers the infra crash as `refine_failed`.
- A `forward` error keeps the wrapper's terminal type, and the failure terminal declares
  `failure: true`.
- The ledger-ownership rule is scoped to `route_refine_outcome` and suffixed tokens.
  `route_refine_success` and unsuffixed `BLOCKED` keep `skip_inflight`.
- AC 3 lists `mark_inner_error` as a second exception to "forwards unchanged".
- `forward` prints the forwarded token. The `refine_failed` row uses the raw
  `${context.input}` ID to match `skip_inflight`.
- Passthrough traps documented: no `input` in the wrapper's `context:` block, and no capture
  names that collide with inner context keys.
- `clear_record` also clears the inner writer's record, because autodev re-enters
  `refine_current` for the same ID. The stale-record read already happens today, so this
  is hardening, not a regression fix.
- Parity tests are written first against `main`; `CANCELLED`, `DEFERRED:gate_unmet` and the
  `MISSING`+infra-sentinel fallback were added.

## Resolution

Implemented 2026-09-26: `prepare-issue.yaml` wrapper, `ll-issues run-record forward`, autodev `refine_current` retarget, both routers on `--writer prepare-issue`, and `BLOCKED:quality` / `DEFERRED:gate_unmet` routed to `ledger_child_stop` in `route_refine_outcome` (the wrapper's `forward_stop` writes the row). Parity is proven at the router/ledger level (executing the wrapper states and autodev router actions per token) rather than by a full autodev real-FSM run with a stub child. `skills/audit-loop-run/SKILL.md:119` was not edited (no `--resolved` wording to change), so no `ll-adapt` run.

## Status

**Done** | Created: 2026-09-26 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-09-26T18:32:04 - `9a9aae39-54ac-4f95-a7cc-b1334b5443d6.jsonl`
- `/ll:ready-issue` - 2026-09-26T18:19:31 - `f3bc5ab2-2f9d-4322-ad38-6b659ac426b0.jsonl`
- `/ll:confidence-check` - 2026-09-26T18:17:23 - `660a1ff7-079b-4927-8755-da62d2de860b.jsonl`
- `/ll:confidence-check` - 2026-09-26T17:56:17 - `d8dc6ef7-0e36-4417-8999-282f048f8e13.jsonl`
- `/ll:verify-issues` - 2026-09-26T17:51:03 - `88c2d513-b5ef-46f0-9f72-8998adaef5bb.jsonl`
- `/ll:wire-issue` - 2026-09-26T03:36:28 - `e6ad8ea2-14d6-441f-a607-435314c2d056.jsonl`
- `/ll:refine-issue` - 2026-09-26T03:22:24 - `7612ef86-47f8-4d5d-aa01-e50211538dc3.jsonl`
- `/ll:format-issue` - 2026-09-26T03:07:12 - `34887897-5e19-4ee2-b656-5f0a00c15f02.jsonl`
