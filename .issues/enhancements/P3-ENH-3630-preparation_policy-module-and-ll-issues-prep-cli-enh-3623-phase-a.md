---
id: ENH-3630
type: ENH
title: preparation_policy module and ll-issues prep CLI (ENH-3623 Phase A)
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T04:45:18Z'
parent: EPIC-3565
relates_to:
- ENH-3621
blocks:
- ENH-3623
---

# ENH-3630: preparation_policy module and ll-issues prep CLI (ENH-3623 Phase A)

## Summary

Phase A of ENH-3623, split out so it lands on its own. It is additive: port
`little_loops.preparation_policy` (policy / facts / writers) from the ENH-3621 spike
(tag `spike/preparation-policy-a51621302`, report `thoughts/spikes/preparation-policy-spike.md`),
<!-- ll-prose-ok: the prep subcommand group is proposed by this issue, not yet implemented -->
register `ll-issues prep {step,record,apply,explain}`, and add the `decide()` table tests
and the promoted parity/differential tests, run against the *existing* `prepare-issue.yaml`
and `autodev.yaml`. No loop file changes, so nothing that runs today can regress.

ENH-3623 keeps Phase B (the atomic cutover) and Phase C (docs beyond CLI/API) and is
`blocked_by` this issue. The design, terminal table and production additions are specified
in ENH-3623 § Proposed Solution; this issue implements the module/CLI half of it.

## Current Behavior

The second-pass preparation ladder is encoded only as autodev graph shape plus ~15
<!-- ll-prose-ok: the prep subcommand group is proposed by this issue, not yet implemented -->
`run_dir` handshake files. No pure policy, fact log or `ll-issues prep` group exists, so
the ladder's routing cannot be table-tested or replayed.

## Expected Behavior

- `little_loops.preparation_policy` exists, split into a pure policy (`decide`), a fact
  log (`load_facts` / `append_fact`) and writers (`prep step` / `record` / `apply` /
  `explain`), with the production hardening from ENH-3623 § Production additions item 1.
- `ll-issues prep …` is registered in `main_issues()` (parser, dispatch branch, epilog)
  and documented in `docs/reference/CLI.md` and `docs/reference/API.md`.
- No loop YAML changes. The new code is exercised only by tests until ENH-3623 Phase B.

## Motivation

ENH-3623 is large and rewrites the second-pass routing of the most-used loop, and every
project on this machine is `local-editable` against this checkout, so a half-landed change
breaks tooling everywhere. Landing the policy, fact log and writers first, with no loop
file touched, puts about half of ENH-3623's work (and most of its test surface) on `main`
at zero regression risk. The Phase B cutover then only swaps the YAML and migrates the
autodev tests.

## Proposed Solution

Port from the spike, applying ENH-3623's production additions and fixed-on-main
semantics rather than spike parity:

- **Policy**: `StepKind`, frozen `Step`, lazy `IssueSnapshot`, pure
  `decide(IssueSnapshot, Facts) -> Step` following the spike's checkpoint → rule-order
  table; `next_preparation_step(...)`.
  - Q1 (BUG-3624): markers are read from the format-check payload whatever the exit code.
  - Q3 (ENH-3625): the design condition applies in the row after a `RUN_CHILD` done fact.
  - BUG-3620: the design check reads the current check-design verdict; no sticky
    `design_gate_failed` aggregate.
  - BUG-3622: rate-limit rows are live (`prep apply --rate-limited`).
- **Facts**: `run_dir/prep-facts/<ID>.jsonl`, append-only, idempotent by
  `(pass, seq, kind)` (obs also by content); pass id read from `run_dir/prep-pass-<ID>`.
- **Writers**:
  - `prep step`: replay an applied terminal or an open intent; else decide, append obs and
    intent, and run the four idempotent preconditions.
  - `prep record [--guard2]`: classify the child outcome from
    `run-records/refine-to-ready-issue/<ID>.json` (never from `captured.run_child`).
  - `prep apply [--rate-limited]`: sole terminal writer; ledger row keyed `(pass, seq)`
    with check-before-append, then `set-status`, run record and inflight clear, each
    independently idempotent; writes the `refine-terminal-class` sentinel on every
    `failed`-bound terminal; with no open `FINISH`/`STOP` intent writes
    `RETRYABLE_ERROR:infra`.
  - `prep explain`: prints a decision, writes nothing.
- **Shared record helper**: extract the record assembly from `cmd_run_record_write` into
  `run_record.py` and use it from both `ll-issues run-record write` and `prep apply`.
- **Budget arithmetic**: expose the per-pass done-fact cap derived from the ladder budgets,
  and the dispatch-loop `max_steps = 4 × cap + 3` (3 states per command step, 4 per
  `SIZE_REVIEW` step) as a module constant, so Phase B's YAML and structural test both
  read one source.

## Integration Map

### Files to Modify

- `scripts/little_loops/preparation_policy.py` (new), or a `preparation_policy/` package
- `scripts/little_loops/cli/issues/__init__.py`: `prep` parser, dispatch branch, epilog entry
- `scripts/little_loops/cli/issues/run_record.py` and `scripts/little_loops/run_record.py`:
  the shared record-writing helper
<!-- ll-prose-ok: the prep subcommand group is proposed by this issue, not yet implemented -->
- `docs/reference/CLI.md`: `#### \`ll-issues prep\`` section
- `docs/reference/API.md`: `prep` row beside `run-record`, `little_loops.preparation_policy` section

### Tests

- New (none exist on `main` yet; port from the spike branch):
  `test_preparation_policy.py` (`decide()` table tests),
  `test_preparation_policy_parity.py` (19 pinned + 9 differential),
  `test_preparation_policy_resume.py` (subset by default; full matrix behind `slow` plus an
  env-var/`skipif` gate and `@pytest.mark.timeout`), `preparation_policy_harness.py`
- Extended: `scripts/tests/autodev_harness.py` (`"state#N"` fault points,
  `Crash.replay_same`, `inner_calls`)
- `prep` help/epilog test (copy `test_run_record.py::test_subcommand_in_help` and the
  one-class-per-subcommand layout)
- `scripts/tests/test_wiring_reference_docs.py`: `DOC_STRINGS_PRESENT` rows for the new
  CLI.md / API.md sections
- Must stay green: `test_run_record.py` (`test_ready_iff_check_passed_would_pass`,
  `TestOutcomeMapping`, `TestRunRecordForward`)

## Implementation Steps

1. Port the policy (`decide`, `StepKind`, `Step`, lazy `IssueSnapshot`) and the fact log
   from `spike/preparation-policy-a51621302`, applying Q1, Q3, BUG-3620 and BUG-3622
   semantics; add the `decide()` table tests alongside.
2. Extract the shared record-writing helper from `cmd_run_record_write` into
   `run_record.py`; keep `test_run_record.py` green before any `prep` code uses it.
3. Build the writers (`prep step` / `record` / `apply` / `explain`) with the hardening
   from ENH-3623 § Production additions item 1, register `prep` in `main_issues()`, and
   add the help/epilog and `apply` crash-injection tests.
4. Port the spike harness, the parity/differential tests (with the allowance list) and
   the resume subset; gate the full matrix as opt-in.
5. Add the CLI.md / API.md entries and the `test_wiring_reference_docs.py` rows; run the
   full suite, `ruff`, and `mypy`.

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
- `apply_terminal(config: BRConfig, issue_id: str, run_dir: Path, step: Step) -> str` — the sole terminal writer; ledger row (keyed `(pass, seq)`, check-before-append), `set-status`, run record and inflight clear, each idempotent; returns the terminal token
- `record_step(config: BRConfig, issue_id: str, run_dir: Path, *, guard2: bool = False) -> None` — writes the done fact and repair-cycle projection; classifies the child outcome from `run-records/refine-to-ready-issue/<ID>.json`

### Call Path

<!-- ll-prose-ok: the prep subcommand group is proposed by this issue, not yet implemented -->
`ll-issues prep step` -> `next_preparation_step` -> `select_next_obligation` / `load_facts` -> `decide`

## Impact

- **Priority**: P3. First, zero-regression half of ENH-3623.
- **Effort**: Large (~1,300-line module port plus tests), but no runtime behavior changes.
- **Risk**: Low. Nothing in a loop calls the new code until ENH-3623 Phase B.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] `decide()` has table tests covering every row of the checkpoint → rule-order table,
  H1–H4, the budget rules, and the ported shell predicates (contradiction-sourced spike
  exemption, spike-budget-exhausted reconcile fallback, the refine cap on DPDR, the
  selectors' `_error` routes).
- [ ] Parity/differential tests run the policy against the existing YAML. Every
  difference is on an explicit allowance list, and each allowance names its source:
  ENH-3623 accepted changes 1–6, the record-token fixes, BUG-3620 (no sticky design
  marker; `test_design_marker_is_sticky_across_passes_bug3620_parity` rewritten to the
  fixed rule), BUG-3622 (`ladder_rate_limit_is_inert` becomes a halt test), and Q1.
  No vacuous allowances.
- [ ] Fact log: appending the same `(pass, seq, kind)` twice writes one line; a replayed
  `dequeue_next` increment that skips a pass number is harmless (test).
- [ ] Crash injection inside `prep apply`, between each of the ledger row, `set-status`,
  run record and inflight clear writes, followed by a re-run, never double-appends a
  ledger row and ends with one terminal.
- [ ] `prep apply` with no open `FINISH`/`STOP` intent writes `RETRYABLE_ERROR:infra`, and
  writes the `refine-terminal-class` sentinel on every `failed`-bound terminal.
- [ ] `prep record` ignores a seeded stale `failure_terminal` capture and classifies from
  the child's run record; an absent record means the child errored.
- [ ] The contradiction trigger reads `superseded_marker_count` even when format-check
  reports blocking gaps.
- [ ] `ll-issues run-record write` and `prep apply` share one record-writing helper; the
  existing `test_run_record.py` suite stays green.
- [ ] The step-budget constants (`cap`, `max_steps = 4 × cap + 3`) are exported with the
  arithmetic in a comment and a unit test.
<!-- ll-prose-ok: the prep subcommand group is proposed by this issue, not yet implemented -->
- [ ] The `prep` group's `--help` lists all four subcommands; CLI.md / API.md rows exist and
  `test_wiring_reference_docs.py` / `test_cli_claims.py` pass.
- [ ] `git diff --stat` for this issue touches no file under `scripts/little_loops/loops/`.

## Scope Boundaries

- **In scope**: the module, the `prep` group, the shared record helper, the new tests and
  harness extensions, and the CLI.md / API.md entries.
- **Out of scope** (ENH-3623 Phase B/C): any change to `prepare-issue.yaml` or
  `autodev.yaml`, the `dequeue_next` pass-id write, test migration of the autodev
  second-pass cluster, `LOOPS_REFERENCE` / `ARCHITECTURE` / `DEFERRAL_CODES` / skill docs,
  and `ll-adapt` mirrors.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-27T04:48:28 - `92da6ad0-e100-4b8d-bcc9-de840c7a338f.jsonl`
