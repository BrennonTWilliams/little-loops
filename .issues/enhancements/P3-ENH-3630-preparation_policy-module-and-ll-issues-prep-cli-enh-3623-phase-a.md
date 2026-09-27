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
and the promoted parity/differential tests, which compare the policy against the *existing*
`prepare-issue.yaml` and `autodev.yaml`. The policy side runs the dispatch loop from a
**test fixture** (`scripts/tests/fixtures/prepare-issue-policy.yaml`) with the harness's
in-memory `policy_transform` applied to `autodev.yaml`. No loop file changes, so nothing
that runs today can regress.

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
  Nothing writes that file until ENH-3623 Phase B (`dequeue_next`), so an absent or
  unparsable file means pass `0` (the spike's default); pin that with a test.
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
  - **In-process writes**: the spike's `_ll_issues()` shells out to `ll-issues` via
    `subprocess` and ignores the return code (preconditions and `apply`'s `set-status`).
    Call the status/score functions in-process and treat a failure as a failure: a
    silently failed `set-status` breaks the "each write independently idempotent"
    guarantee, and the subprocess path depends on `ll-issues` being on `PATH`.
- **Shared record helper**: extract the record assembly from `cmd_run_record_write` into
  `scripts/little_loops/run_record.py` (not the CLI module, so the policy does not depend
  on `cli/`) and use it from both `ll-issues run-record write` and `prep apply`. This is a
  **correctness** requirement, not just de-duplication: the spike's inline `ready`
  predicate in `apply` (`preparation_policy.py` ~:1095 at the tag) omits the check-design
  condition that ENH-3625 added to the run-record `ready` predicate, so a design-failing
  `FINISH` would record `READY` instead of `BLOCKED`.
- **Budget arithmetic**: expose the per-pass done-fact cap derived from the ladder budgets,
  and the dispatch-loop `max_steps = 4 × cap + 3` (3 states per command step, 4 per
  `SIZE_REVIEW` step) as a module constant, so Phase B's YAML and structural test both
  read one source. These replace the spike's hard-coded `MAX_DONE_PER_PASS = 15` and its
  YAML's `max_steps: 80`; the fixture YAML's `max_steps` must equal the constant (test).
- **Dispatch-loop fixture**: port the spike's dispatch-loop YAML (under `loops/` on the tag) to
  `scripts/tests/fixtures/prepare-issue-policy.yaml`, not `loops/`. A new built-in loop
  would appear in every project's `ll-loop list` and trip the loop-count gates.
  `run_autodev(prepare_issue_yaml=…)` copies the file's text into the harness's temp
  `loops_dir`, so any path works. Update it for the fixed-on-main semantics
  (`mark_rate_limited` live per BUG-3622, `max_steps` from the constant), and add a test
  that loads and validates it so it cannot drift before ENH-3623 Phase B moves it into
  `loops/prepare-issue.yaml`.
- **Snapshot imports**: the spike imports private CLI helpers (`_resolve_issue_id` from
  `cli/issues/show.py`, `_load_issues_with_status` from `cli/issues/search.py`). Promote
  them to public names, or keep the import and note the layering in the module docstring.

## Integration Map

### Files to Modify

- `scripts/little_loops/preparation_policy.py` (new), or a `preparation_policy/` package
- `scripts/little_loops/cli/issues/__init__.py`: `prep` parser, dispatch branch, epilog entry
- `scripts/little_loops/run_record.py`: the shared record-writing helper (new home);
  `scripts/little_loops/cli/issues/run_record.py`: `cmd_run_record_write` calls it
- `scripts/tests/fixtures/prepare-issue-policy.yaml` (new): the dispatch loop, test-only
  until ENH-3623 Phase B
<!-- ll-prose-ok: the prep subcommand group is proposed by this issue, not yet implemented -->
- `docs/reference/CLI.md`: `#### \`ll-issues prep\`` section, labelled as internal loop
  plumbing (`prep step` preconditions change issue status; not for manual use)
- `docs/reference/API.md`: `prep` row beside `run-record`, `little_loops.preparation_policy` section
- Once `prep` is registered, remove the `ll-prose-ok` markers in this issue and ENH-3623

### Tests

- New (none exist on `main` yet; port from the spike branch):
  `test_preparation_policy.py` (`decide()` table tests),
  `test_preparation_policy_parity.py` (19 pinned + 9 differential),
  `test_preparation_policy_resume.py` (subset by default; full matrix behind `slow` plus an
  env-var/`skipif` gate and `@pytest.mark.timeout`), `preparation_policy_harness.py`
  (`POLICY_YAML` points at the fixture, not `BUILTIN_LOOPS_DIR`)
- **Rewrite, don't port** — spike tests that pin pre-fix behavior. The spike branched
  before BUG-3624 (`684909afe`), ENH-3625 (`a1cee466a`), BUG-3620 (`9e8af1dd4`) and
  BUG-3622 (`ce86ce662`) landed, so the "today" side of every parity/differential run now
  carries the fixed behavior:
  - `h2_first_gate_skips_design` (differential) and
    `test_h2_first_gate_ignores_design_and_files_no_marker` (table): ENH-3625 Rule A makes
    the first gate design-aware, so both expectations flip.
  - `contradiction_masked_by_format_gaps`: `DIFF_SHAPES` expects `(_S,)`; under Q1 the
    reconcile fires, so it becomes `(_S, _RC, _C)` (and the comment describing the mask goes).
  - `test_design_marker_is_sticky_across_passes_bug3620_parity`: rewrite to the fixed rule
    (current verdict, no sticky `design_gate_failed` obs).
  - The characterization row the spike called `ladder_rate_limit_is_inert` is already
    `ladder_rate_limit_halts` on main; it is plain parity once the fixture's
    `mark_rate_limited` is live.
- **Runtime budget**: parity (19) + differential (9) are ~28 full autodev runs with
  300–600 s timeouts. `slow` is not deselected by default, so they join every
  `python -m pytest scripts/tests/` run. Either gate them like the resume matrix or
  record the measured added wall-clock here; keep each test under the 120 s default where
  possible (a longer shell-out test can orphan its xdist worker and respawn-loop).
- Extended: `scripts/tests/autodev_harness.py` (`"state#N"` fault points,
  `Crash.replay_same`, `inner_calls`)
- `prep` help/epilog test (copy `test_run_record.py::test_subcommand_in_help` and the
  one-class-per-subcommand layout)
- `scripts/tests/test_wiring_reference_docs.py`: `DOC_STRINGS_PRESENT` rows for the new
  CLI.md / API.md sections
- Must stay green: `test_run_record.py` (`test_ready_iff_check_passed_would_pass`,
  `TestOutcomeMapping`, `TestRunRecordForward`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **Record helper boundary**: `cmd_run_record_write` (`cli/issues/run_record.py`) has one caller, `cmd_run_record`. Everything from `parse_frontmatter` through `write_run_record` is already non-printing; only `args.*` access, the unresolved-issue stderr/exit 2, and the `[RUN_RECORD_WRITTEN]` stdout line are CLI-only. A helper in `little_loops/run_record.py` must take `broke_down` as an in-process value (the CLI currently reads it from the `refine-broke-down` file via `_read_broke_down`).
- **Layering constraint**: `little_loops/run_record.py` imports only `file_utils.atomic_write_json` today. The helper's inputs `canonical_record_id`, `derive_child_ids`, `_read_broke_down` (all `cli/issues/run_record.py`), `readiness_status` (`cli/issues/check_readiness.py`) and `_resolve_issue_id` (`cli/issues/show.py`, a thin delegate to `issue_parser.resolve_issue_path`) all live under `cli/`. Either relocate or import them lazily; a module-level `cli/` import would give the policy the `cli/` dependency this issue says to avoid.
- **`ready` predicate on main**: `thresholds_met` = scores present, `meets_readiness`, `meets_outcome_or_waived`, and `not design_gate_failed(check_format_gaps(path))`, evaluated on the file at write time. It only decides the outcome when `legacy_class` is `None`/unrecognised and status is not `cancelled` and broke-down is unset (`outcome_from_legacy_class`, first-match rules). The spike's inline predicate in `_apply_outcome.write()` lacks the design term (confirmed in the worktree copy of the spike).
- **`prep` registration touch points** (`cli/issues/__init__.py`, `main_issues()`): lazy import block, `add_*_parser(subs)` call beside `add_run_record_parser`, one line in the `Sub-commands:` epilog, and an `if args.command == ...` dispatch branch. The group parser uses `set_defaults(command=...)` plus a required nested `add_subparsers(dest=...)`; every leaf takes `add_config_arg`. The spike registered its parser and dispatch but no epilog line, so the epilog entry and help test are new work.
- **In-process writers**: status has a non-printing writer, `apply_status_transition(config, path, issue_id, status, *, reason, by, cascade_to)` in `cli/issues/set_status.py`. It takes the issue lock, stamps `deferred_by`/`deferred_reason`/`closed_reason`/`completed_at` via `status_frontmatter_updates`, and shares a caller with the MCP `_tool_issue_set_status`. It signals failure by raising `OSError` on the main file (only cascade-child errors land in `StatusTransition.failures`), and the caller must resolve `path` first; transition validity is checked in `cmd_set_status`, not here. Scores have **no** shared writer: `cmd_set_scores` inlines `update_frontmatter` / `remove_frontmatter_keys(content, SCORE_KEYS)` with a non-atomic, unlocked `write_text`. In-process score clearing therefore needs either a new function extracted from `cmd_set_scores` or direct use of those `frontmatter` primitives.
- **Spike subprocess sites**: the spike's `_ll_issues` (ignored return code) has four call sites: `set-scores --clear` (`clear_scores`), `set-status deferred --reason oversized_atomic` (`defer_oversized_atomic`), `set-status open` (`reopen`), and the `_DEFER_STOPS` branch of `_apply_outcome`. All four must become checked in-process calls.
- **Spike snapshot shape differs from the issue's wording**: the spike's `IssueSnapshot` is frozen and eagerly built by `snapshot_issue`, not lazy; `Facts` carries a `design_gate_failed_sticky` aggregate (the BUG-3620 field to drop); the spike drops markers when blocking format gaps exist (`0 if blocking else superseded_marker_count(path)`, the Q1 site). `current_pass` already returns `"0"` for an absent or empty pass file; `load_facts` skips torn lines; `append_fact` flushes without `fsync`.
- **Private CLI helpers the snapshot needs**: `_resolve_issue_id(config, user_input) -> Path | None` and `_load_issues_with_status(config, include_open, include_done, include_deferred)`. The latter is already imported by `mcp_server/tools.py`, so a public name has a second consumer to update. `select_next_obligation` exists on main (`cli/issues/next_obligation.py`, raises `ObligationProbeError` on fail-closed probe errors), so the spike's dependency on it resolves.
- **Design-gate semantics on main match the issue**: `design_gate_failed(gaps)` is recomputed from the file every call, with nothing sticky; `check-design` exits 0/1/2 (pass-or-inert / fail / unresolved). Not verified row-by-row against `autodev.yaml`.
- **Verification caveat**: the spike surface above was read from a worktree copy (`.claude/worktrees/agent-a07c1384a19983bfb/`), not `git show` of the tag; confirm it matches `spike/preparation-policy-a51621302` before porting. The tag's dispatch-loop YAML and tests were not inspected.

## Implementation Steps

1. Port the policy (`decide`, `StepKind`, `Step`, lazy `IssueSnapshot`) and the fact log
   from `spike/preparation-policy-a51621302`, applying Q1, Q3, BUG-3620 and BUG-3622
   semantics; add the `decide()` table tests alongside.
2. Extract the shared record-writing helper from `cmd_run_record_write` into
   `run_record.py`; keep `test_run_record.py` green before any `prep` code uses it.
3. Build the writers (`prep step` / `record` / `apply` / `explain`) with the hardening
   from ENH-3623 § Production additions item 1, register `prep` in `main_issues()`, and
   add the help/epilog and `apply` crash-injection tests.
4. Port the dispatch loop as `scripts/tests/fixtures/prepare-issue-policy.yaml` (with its
   validation test), then the spike harness, the parity/differential tests (with the
   allowance list) and the resume subset; rewrite the pre-fix pins listed under Tests;
   gate the full matrix as opt-in and settle the parity/differential runtime budget.
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
- [ ] Parity/differential tests run the policy (fixture dispatch loop + in-memory
  `policy_transform`) against the existing YAML. Every difference is on an explicit
  allowance list, and each allowance names its source: an ENH-3606/ENH-3623 accepted
  change that a scenario actually exercises (today: change 1, scores-absent and
  `on_error` drops → `refine_failed_infra`) or one of the record-token fixes (GO path
  `READY`, size-review / resolved-parent `DECOMPOSED`, rescore-retry `READY`). Q1,
  BUG-3620 and BUG-3622 are **parity, not allowances** (fixed on main, so both sides
  agree). No vacuous allowances (`test_allowed_diffs_are_real_diffs` stays).
- [ ] The dispatch-loop fixture loads and validates, and its `max_steps` equals the
  exported constant.
- [ ] A design-failing `FINISH` records `BLOCKED`, not `READY` (the shared helper carries
  ENH-3625's check-design condition).
- [ ] An absent `prep-pass-<ID>` file reads as pass `0`.
- [ ] A failing `set-status` inside `prep apply` or a precondition is surfaced as an error
  (non-zero exit, no progress mark), and a re-run converges on one terminal.
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

- **In scope**: the module, the `prep` group, the shared record helper, the dispatch-loop
  test fixture, the new tests and harness extensions, and the CLI.md / API.md entries.
- **Out of scope** (ENH-3623 Phase B/C): any change to `prepare-issue.yaml` or
  `autodev.yaml`, the `dequeue_next` pass-id write, test migration of the autodev
  second-pass cluster, `LOOPS_REFERENCE` / `ARCHITECTURE` / `DEFERRAL_CODES` / skill docs,
  and `ll-adapt` mirrors.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-27T05:01:48 - `399ba9ba-cae5-4abc-9ec9-beebb2989847.jsonl`
- `/ll:format-issue` - 2026-09-27T04:48:28 - `92da6ad0-e100-4b8d-bcc9-de840c7a338f.jsonl`
