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
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
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
**test fixture** (`scripts/tests/fixtures/loops/prepare-issue-policy.yaml`) with the spike
harness's `policy_transform` passed as the autodev harness's `autodev_transform=`. No loop
file changes, so nothing that runs today can regress.

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

- **Layering (decided)**: only the pure layer (`StepKind`, `Step`, `Facts`,
  `IssueSnapshot`, `decide`) is `cli/`-free, enforced by an import-boundary test. The
  writers and `next_preparation_step` may import from `little_loops.cli.*`, lazily
  (inside the function), because every input they need lives there:
  `apply_status_transition`, `select_next_obligation`, `readiness_status`,
  `canonical_record_id`, `derive_child_ids`, `_read_broke_down` and
  `_load_issues_with_status`. Nothing is relocated or renamed; the module docstring
  records the rule.
- **Policy**: `StepKind`, frozen `Step`, `IssueSnapshot`, pure
  `decide(IssueSnapshot, Facts) -> Step` following the spike's checkpoint → rule-order
  table; `next_preparation_step(...)`.
  - The snapshot is **lazy** (ENH-3623 § Production additions item 1: scan children only
    in DETECT / POST_SIZE_REVIEW). This is new work: the spike's `snapshot_issue` builds a
    frozen snapshot eagerly.
  - Q1 (BUG-3624): markers are read from the format-check payload whatever the exit code.
  - Q3 (ENH-3625): the design condition applies in the row after a `RUN_CHILD` done fact.
  - BUG-3620: the design check reads the current check-design verdict; no sticky
    `design_gate_failed` aggregate (drop the spike's `Facts.design_gate_failed_sticky`).
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
    independently idempotent, each followed by its progress mark (the spike's
    `mark(part)` handshake in `prep_apply`); writes the `refine-terminal-class` sentinel on
    every `failed`-bound terminal; with no open `FINISH`/`STOP` intent writes
    `RETRYABLE_ERROR:infra`.
  - `prep explain`: prints a decision, writes nothing.
  - **In-process writes**: the spike's `_ll_issues()` shells out to `ll-issues` via
    `subprocess` and ignores the return code. Replace all four call sites with checked
    in-process calls and treat a failure as a failure: a silently failed `set-status`
    breaks the "each write independently idempotent" guarantee, and the subprocess path
    depends on `ll-issues` being on `PATH`. The sites (tag line numbers):
    - `set-scores <ID> --clear` (`_run_preconditions`, ~893) → `clear_scores(path)` (below)
    - `set-status deferred --reason oversized_atomic` (`_run_preconditions`, ~895) and
      `set-status deferred --reason <reason>` (`_apply_outcome`'s `_DEFER_STOPS` branch,
      ~1170) → `apply_status_transition`
    - `set-status open` (`_run_preconditions`, ~905) → `apply_status_transition`
  - **Reason validation**: `apply_status_transition` assumes a valid transition; the
    `--reason`-vs-status check (deferral codes only on `deferred`, closure codes only on
    `done`/`cancelled`) lives inline in `cmd_set_status`. Extract it into a function in
    `cli/issues/set_status.py` that `cmd_set_status` keeps calling (same error text and
    exit code), and call it before every in-process `apply_status_transition` in the
    policy.
- **Score clearing (decided)**: extract `clear_scores(path) -> bool` into
  `cli/issues/set_scores.py`. It removes `SCORE_KEYS` under `acquire_lock` with an atomic
  write (matching `apply_status_transition`) and returns whether anything changed.
  `set-scores --clear` calls it, so it gains the lock and atomic write it lacks today.
- **Shared record helper (decided)**: extract the record assembly from
  `cmd_run_record_write` into a public, non-printing function in
  `cli/issues/run_record.py`, next to the helpers it uses, and call it from both
  `ll-issues run-record write` and `prep apply`. This is a **correctness** requirement,
  not just de-duplication: the spike's inline `ready` predicate in `_apply_outcome.write()`
  (~1094 at the tag) omits the check-design condition that ENH-3625 added to the run-record
  `ready` predicate, so a design-failing `FINISH` would record `READY` instead of
  `BLOCKED`. The helper takes `broke_down` as an in-process value (the CLI keeps reading
  it from the `refine-broke-down` file via `_read_broke_down`).
- **Budget arithmetic**: expose the per-pass done-fact cap derived from the ladder budgets,
  and the dispatch-loop `max_steps = 4 × cap + 3` as a module constant, so Phase B's YAML
  and structural test both read one source. The spike's YAML costs 3 states per command
  step (`select_step → run_* → record_step`) and 4 per `SIZE_REVIEW` step
  (`select_step → run_size_review → classify_guard2 → record_*`), plus 3 for the final
  select, `apply_outcome` and the terminal. `4 × cap + 3` is therefore an upper bound. The
  spike report's `≈ 3 × cap + 3` ignores the extra `SIZE_REVIEW` state and is superseded
  deliberately. These replace the spike's hard-coded `MAX_DONE_PER_PASS = 15` and its
  YAML's `max_steps: 80`; the fixture YAML's `max_steps` must equal the constant (test).
- **Dispatch-loop fixture**: port the spike's `loops/prepare-issue-policy.yaml` to
  `scripts/tests/fixtures/loops/prepare-issue-policy.yaml` (the existing loop-fixture dir,
  precedent `caller-suitability-gate-fixture.yaml`), not `loops/`. A new built-in loop
  would appear in every project's `ll-loop list` and trip the loop-count gates.
  `run_autodev(prepare_issue_yaml=…)` copies the file's text into the harness's temp
  `loops_dir`, so any path works. Update it for the fixed-on-main semantics
  (`mark_rate_limited` live per BUG-3622, `max_steps` from the constant), and add a test
  that loads and validates it so it cannot drift before ENH-3623 Phase B moves it into
  `loops/prepare-issue.yaml`.
- **Snapshot imports**: resolve issues with public `issue_parser.resolve_issue_path` (the
  function `cli/issues/show.py:_resolve_issue_id` wraps); do not rename
  `_resolve_issue_id`. Keep the private `_load_issues_with_status` import from
  `cli/issues/search.py` under the layering rule above; do not promote it.

## Integration Map

### Files to Modify

- `scripts/little_loops/preparation_policy.py` (new), or a `preparation_policy/` package
- `scripts/little_loops/cli/issues/__init__.py`: `prep` parser, dispatch branch, epilog entry
- `scripts/little_loops/cli/issues/run_record.py`: new public record-writing helper;
  `cmd_run_record_write` becomes a thin wrapper (args, stderr/exit 2, stdout marker)
- `scripts/little_loops/cli/issues/set_scores.py`: new `clear_scores(path)`; `--clear`
  calls it
- `scripts/little_loops/cli/issues/set_status.py`: extract the reason-vs-status check from
  `cmd_set_status` into a function
- `scripts/tests/fixtures/loops/prepare-issue-policy.yaml` (new): the dispatch loop,
  test-only until ENH-3623 Phase B
<!-- ll-prose-ok: the prep subcommand group is proposed by this issue, not yet implemented -->
- `docs/reference/CLI.md`: `#### \`ll-issues prep\`` section, labelled as internal loop
  plumbing (`prep step` preconditions change issue status; not for manual use)
- `docs/reference/API.md`: `prep` row beside `run-record`, `little_loops.preparation_policy` section
- Once `prep` is registered, remove the `ll-prose-ok` markers in this issue, ENH-3623 and
  ENH-3600

### Dependent Files (Callers/Importers)

_Consolidated from the `/ll:wire-issue` passes._

- `scripts/little_loops/loops/autodev.yaml` (`run-record write --writer prepare-issue`,
  `clear`, `read`), `refine-to-ready-issue.yaml` (~10–12 `run-record write` states, all
  `|| true`, `--legacy-class` values incl. `proposal_unsound`, `gate_unmet`, `infra`,
  `spike_inconclusive`, `decision_unresolved`), `prepare-issue.yaml` (`clear`, `forward`
  captured via `TOKEN=$(...)`, `write --legacy-class infra`). They depend only on flags,
  stdout and exit code, so the helper extraction must not change any of them (no edits).
- `cmd_run_record_write` contract to preserve: `[RUN_RECORD_WRITTEN] <canonical_id>
  <outcome> <path>` on stdout with exit 0; unresolved issue prints
  `Error: Issue '...' not found.` to stderr with exit 2; `ValueError("unknown run-record
  writer: ...")`. `read`/`clear`/`forward` reuse `canonical_record_id`,
  `derive_child_ids` and `_read_broke_down`, which stay in `cli/issues/run_record.py`.
- `set-scores --clear` callers and `cmd_set_status` behavior (error text, exit codes)
  must be unchanged by the `clear_scores` and reason-check extractions.
- Unchanged by decision: `_load_issues_with_status` (importers `search.py`,
  `count_cmd.py`, `list_cmd.py`, `cli/loop/next_loop.py`, `mcp_server/tools.py`,
  `test_issues_search.py`) and `_resolve_issue_id` (~30 importers, and a string patch in
  `test_arm_proposal_revision.py`).
- `ll-prose-ok` readers (for the marker removal): `issues/cli_claims.py:_SUPPRESS_RE`,
  `issues/symbol_claims.py:_SUPPRESS_RE`, `cli/verify_skill_prose.py:_SUPPRESS_RE`.

### Tests

- New (none exist on `main` yet; port from the spike branch):
  `test_preparation_policy.py` (`decide()` table tests),
  `test_preparation_policy_parity.py` (19 pinned + 9 differential),
  `test_preparation_policy_resume.py` (subset by default; full matrix behind `slow` plus an
  env-var `skipif` gate and `@pytest.mark.timeout`), `preparation_policy_harness.py`
  (`POLICY_YAML` points at the fixture, not `BUILTIN_LOOPS_DIR`)
- **Import-boundary test**: importing the pure layer does not import any
  `little_loops.cli` module (fresh interpreter / `sys.modules` check).
- **Rewrite, don't port** — spike tests that pin pre-fix behavior. The spike branched
  (merge base `9f7c5dc27`) before BUG-3624 (`684909afe`), ENH-3625 (`a1cee466a`),
  BUG-3620 (`9e8af1dd4`) and BUG-3622 (`ce86ce662`) landed, so the "today" side of every
  parity/differential run now carries the fixed behavior:
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
- **Runtime budget (decided rule)**: parity (19) + differential (9) are ~28 in-process
  autodev runs (spike timeouts 300/600 s), and `slow` is not deselected by default. In
  step 4, measure the added wall-clock of both files under the default
  `python -m pytest scripts/tests/` (`-n logical`) and record it here. If they add more
  than 60 s, put the 9 differential tests behind the same env-var `skipif` as the full
  resume matrix; the 19 pinned parity tests stay in the default run. Keep each test under
  the 120 s default timeout where possible.
- Harness: the spike's `policy_transform` is already passed as `autodev_transform=`, so it
  ports as is. Extensions needed in `scripts/tests/autodev_harness.py`: `"state#N"` fault
  points, `Crash.replay_same`, `AutodevResult.inner_calls`. Models:
  `test_autodev_characterization.py::test_harness_accepts_replacement_prepare_issue_and_autodev_transform`
  (~:962) and `::test_autodev_resume_characterization` (~:939, `_with_crash`,
  `_replayed`, `_assert_hermetic`, `Crash(state, when=…)`).
- `prep` help/epilog test (copy `test_run_record.py::test_subcommand_in_help` ~:450 and the
  one-class-per-subcommand layout); no existing test asserts the `Sub-commands:` epilog,
  so the epilog line is untested unless added. A `prep` flags assertion goes in
  `test_cli_surface.py` (`cli_surface_accepts(idx, "ll-issues", ...)`).
- `test_run_record.py`: direct unit tests for the extracted helper; must stay green
  (`test_ready_iff_check_passed_would_pass`, `TestOutcomeMapping`, `TestRunRecordForward`,
  the `[RUN_RECORD_WRITTEN]` line ~:308, the exit-2 path, the unknown-writer `ValueError`).
- `test_set_scores_cli.py` (`TestIssuesCLISetScores`, `TestSetScoresClear`,
  `test_clear_removes_all_six_keys_and_is_idempotent`): stay green; add `clear_scores`
  unit tests. `test_set_status_cli.py`, `test_feat_3149_mcp_mutation_tools.py`,
  `test_bug3150_issue_mutator_atomicity.py`: stay green; add a test that every
  `(status, reason)` pair the policy emits passes the extracted reason check, and
  in-process failure-path tests for `prep`.
- Must stay green (run-record wiring): `test_builtin_loops.py` (~3226, ~6530,
  `test_route_tables_cover_every_run_record_token` ~7818), `test_autodev_ladder_run_records.py`,
  `test_autodev_characterization.py`, `test_prepare_issue.py`, `test_ll_logs.py`.
- `test_wiring_reference_docs.py`: `DOC_STRINGS_PRESENT` `(doc, needle, issue_id)` rows
  for the new CLI.md / API.md sections.
- `test_docs_audience_gate.py`: the new CLI.md / API.md text must not cite
  `scripts/tests/…` (the fixture path) or `scripts/little_loops/…`; cite
  `little_loops.<module>`.
- Checked, no impact: `test_enh2776_no_loop_helpers_module.py` only guards the
  `cli.loop._helpers` path; `test_streaming_cache_parity.py` only reads
  `fixtures/streaming_parity/`; no loop-count test globs `scripts/tests/fixtures/`.
- Pattern sources: `test_prepare_issue.py:86` (`load_and_validate(WRAPPER)`) for the
  fixture-validation test; `test_ll_issues_format_check.py::test_fix_apply_is_idempotent`
  for idempotency; conftest `make_project` / `issues_dir` / `temp_project` fixtures.

### Documentation

- `docs/reference/CLI.md` — `#### ll-issues run-record` and `#### ll-issues next-obligation`
  are the section templates for `#### ll-issues prep`
- `docs/reference/API.md` — CLI subcommand table (~:4655-4667, beside the
  `next-obligation` / `run-record` rows) gets a `prep` row; module table (~:74, beside
  `little_loops.cli.issues.run_record`) gets a `little_loops.preparation_policy` row; the
  `little_loops.cli.issues.run_record` entry mentions the new shared helper
- `docs/guides/LOOPS_REFERENCE.md` ("Typed run record (ENH-3597)", "Score dispatch
  (ENH-3604)") and `scripts/little_loops/loops/README.md`: no edit in Phase A (no loop
  changes); ENH-3623 Phase B/C scope

### Configuration

- `scripts/pyproject.toml` `[tool.pytest.ini_options]` — `--strict-markers`, `--timeout=120`,
  `-n logical`, `--dist loadfile`. The opt-in gates use `slow` plus an env-var `skipif`, so
  no new marker is needed; register one there if added. Do **not** use `no_parallel` for
  the resume matrix (skipped outright under `-n logical`).
- `scripts/little_loops/config-schema.json` — no change; thresholds live at
  `commands.confidence_gate.{readiness,outcome}_threshold`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27; consolidated after review._

- **Record helper boundary**: `cmd_run_record_write` has one caller, `cmd_run_record`.
  Everything from `parse_frontmatter` through `write_run_record` is already non-printing;
  only `args.*` access, the unresolved-issue stderr/exit 2, and the `[RUN_RECORD_WRITTEN]`
  stdout line are CLI-only.
- **`ready` predicate on main**: `thresholds_met` = scores present, `meets_readiness`,
  `meets_outcome_or_waived`, and `not design_gate_failed(check_format_gaps(path))`,
  evaluated on the file at write time. It only decides the outcome when `legacy_class` is
  `None`/unrecognised, status is not `cancelled` and broke-down is unset
  (`outcome_from_legacy_class` first-match order: cancelled, decomposed, retryable_error,
  blocked, deferred, else ready-or-blocked by `thresholds_met`). Both writers share this
  contract through the helper.
- **Status writer**: `apply_status_transition(config, path, issue_id, status, *,
  reason=None, by=None, cascade_to=None)` takes the issue lock, stamps
  `deferred_by`/`deferred_reason`/`closed_reason`/`completed_at`, records history rows,
  and raises `OSError` on the main file (only cascade-child errors land in
  `StatusTransition.failures`). The caller resolves `path` first.
- **Score writer**: `cmd_set_scores` inlines `update_frontmatter` /
  `remove_frontmatter_keys(content, SCORE_KEYS)` with an unlocked, non-atomic
  `write_text`; hence the `clear_scores` extraction.
- **Format-check / check-design sources**: the Q1 source is
  `issue_parser.superseded_marker_count(path)`, printed regardless of exit code; the spike
  drops markers when blocking gaps exist (`0 if blocking else superseded_marker_count(path)`,
  the Q1 site to fix). `cmd_check_design` is `check_format_gaps(path)` then
  `design_gate_failed(gaps)` (exit 0/1/2), recomputed every call, nothing sticky.
- **`select_next_obligation`** (`cli/issues/next_obligation.py`,
  `select_next_obligation(config, issue_id, *, skip=(), readiness_override=None,
  outcome_override=None, honor_waiver=False) -> ObligationResult | None`) raises
  `ObligationProbeError` on fail-closed probes.
- **Threshold accessors**: `BRConfig` has no `readiness_threshold` / `outcome_threshold`
  shortcuts. `check_readiness.py:readiness_status` and `resolve_confidence_thresholds`
  read raw `ll-config.json` key by key so absence falls back to caller defaults (85 / 65);
  `next_preparation_step` must resolve its thresholds the same way.
- **`prep` registration surface in `main_issues`**: lazy import in the
  `cli_event_context` block, epilog line, `add_prep_parser(subs)` beside
  `add_next_obligation_parser`, and an `if args.command == ...` dispatch branch. Group
  parser: `set_defaults(command=...)` plus nested `add_subparsers(dest=..., required=True)`;
  every leaf takes `add_config_arg`. The spike registered parser and dispatch but no
  epilog line.
- **Spike facts, confirmed on the tag** (`scripts/little_loops/preparation_policy.py`,
  ~1,230 lines): `MAX_DONE_PER_PASS = 15` (46), `decide()` (631), `snapshot_issue()` (654),
  `current_pass` (783; returns `"0"` for an absent or empty pass file), `_ll_issues` (876;
  call sites 893, 895, 905, 1170), `prep_step` / `prep_record` / `prep_apply`
  (908 / 947 / 1000), `_apply_outcome` (1051), `add_prep_parser` / `cmd_prep`
  (1186 / 1209). `load_facts` skips torn lines; `append_fact` flushes without `fsync`.
  Harness: `POLICY_YAML` (18), `policy_transform` (99), `run_policy` passes
  `prepare_issue_yaml=POLICY_YAML, autodev_transform=policy_transform` (123–129). Spike
  YAML: `max_steps: 80`, `on_max_steps: apply_outcome`, `mark_rate_limited` wired on the
  command states. On `main`, `prepare-issue.yaml` has `max_steps: 20`.

## Implementation Steps

Steps 2 and 3 are standalone refactors with their own tests; commit each separately
before any `prep` code, so a bisect isolates any `run-record write` / `set-scores` /
`set-status` behavior shift.

1. Port the pure layer (`decide`, `StepKind`, `Step`, lazy `IssueSnapshot`, `Facts`) and
   the fact log from `spike/preparation-policy-a51621302`, applying Q1, Q3, BUG-3620 and
   BUG-3622 semantics; add the `decide()` table tests and the import-boundary test.
2. Extract the shared record-writing helper inside `cli/issues/run_record.py`; keep
   `test_run_record.py` green and add direct helper tests. (Own commit.)
3. Extract `clear_scores(path)` into `cli/issues/set_scores.py` and the reason-vs-status
   check out of `cmd_set_status`; keep their suites green and add unit tests. (Own commit.)
4. Build the writers (`prep step` / `record` / `apply` / `explain`) with the hardening
   from ENH-3623 § Production additions item 1 and checked in-process writes, register
   `prep` in `main_issues()`, and add the help/epilog, CLI-surface, failure-path and
   `apply` crash-injection tests.
5. Port the dispatch loop as `scripts/tests/fixtures/loops/prepare-issue-policy.yaml`
   (with its validation test), then the harness extensions, the parity/differential tests
   (with the allowance list) and the resume subset; rewrite the pre-fix pins listed under
   Tests; gate the full resume matrix as opt-in; measure and record the parity/differential
   wall-clock and apply the 60 s rule.
6. Add the CLI.md / API.md entries and the `test_wiring_reference_docs.py` rows; remove
   the `ll-prose-ok` markers from ENH-3630, ENH-3623 and ENH-3600; run the full suite,
   `ruff`, and `mypy`.

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
- `clear_scores(path: Path) -> bool` — removes `SCORE_KEYS` under the issue lock with an atomic write; returns whether anything changed

### Call Path

<!-- ll-prose-ok: the prep subcommand group is proposed by this issue, not yet implemented -->
`ll-issues prep step` -> `next_preparation_step` -> `select_next_obligation` / `load_facts` -> `decide`

## Impact

- **Priority**: P3. First, zero-regression half of ENH-3623.
- **Effort**: Large (~1,300-line module port plus tests), but no runtime behavior changes.
- **Risk**: Low. Nothing in a loop calls the new code until ENH-3623 Phase B. The three
  extractions (record helper, `clear_scores`, reason check) touch live `ll-issues`
  subcommands and are covered by their existing suites.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] `decide()` has table tests covering every row of the checkpoint → rule-order table,
  H1–H4, the budget rules, and the ported shell predicates (contradiction-sourced spike
  exemption, spike-budget-exhausted reconcile fallback, the refine cap on DPDR, the
  selectors' `_error` routes).
- [ ] Importing the pure layer (`decide`, `Step`, `StepKind`, `Facts`, `IssueSnapshot`)
  imports no `little_loops.cli` module (test).
- [ ] Parity/differential tests run the policy (fixture dispatch loop + `policy_transform`
  as `autodev_transform`) against the existing YAML. Every difference is on an explicit
  allowance list, and each allowance names its source: an ENH-3606/ENH-3623 accepted
  change that a scenario actually exercises (today: change 1, scores-absent and
  `on_error` drops → `refine_failed_infra`) or one of the record-token fixes (GO path
  `READY`, size-review / resolved-parent `DECOMPOSED`, rescore-retry `READY`). Q1,
  BUG-3620 and BUG-3622 are **parity, not allowances** (fixed on main, so both sides
  agree). No vacuous allowances (`test_allowed_diffs_are_real_diffs` stays).
- [ ] The measured parity/differential wall-clock is recorded in this issue, and the
  differential set is env-gated if it exceeds 60 s.
- [ ] The dispatch-loop fixture loads and validates, and its `max_steps` equals the
  exported constant.
- [ ] A design-failing `FINISH` records `BLOCKED`, not `READY` (the shared helper carries
  ENH-3625's check-design condition).
- [ ] An absent `prep-pass-<ID>` file reads as pass `0`.
- [ ] A failing `set-status` or `clear_scores` inside `prep apply` or a precondition is
  surfaced as an error (non-zero exit, and the `mark(part)` progress mark for that write is
  not written), and a re-run converges on one terminal.
- [ ] Every `(status, reason)` pair the policy passes to `apply_status_transition` passes
  the extracted reason-vs-status check (test).
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
- [ ] `set-scores --clear` uses `clear_scores` (locked, atomic); `test_set_scores_cli.py`
  and `test_set_status_cli.py` stay green.
- [ ] The step-budget constants (`cap`, `max_steps = 4 × cap + 3`) are exported with the
  arithmetic in a comment and a unit test.
<!-- ll-prose-ok: the prep subcommand group is proposed by this issue, not yet implemented -->
- [ ] The `prep` group's `--help` lists all four subcommands and the `Sub-commands:`
  epilog names `prep`; CLI.md / API.md rows exist and `test_wiring_reference_docs.py`
  passes.
- [ ] The `ll-prose-ok` markers are removed from ENH-3630, ENH-3623 and ENH-3600, and the
  prose/claim gates (`issues/cli_claims.py`, `issues/symbol_claims.py`,
  `ll-verify-skill-prose`) pass without them.
- [ ] `git diff --stat` for this issue touches no file under `scripts/little_loops/loops/`.

## Scope Boundaries

- **In scope**: the module, the `prep` group, the shared record helper, the `clear_scores`
  and reason-check extractions, the dispatch-loop test fixture, the new tests and harness
  extensions, and the CLI.md / API.md entries.
- **Out of scope** (ENH-3623 Phase B/C): any change to `prepare-issue.yaml` or
  `autodev.yaml`, the `dequeue_next` pass-id write, test migration of the autodev
  second-pass cluster, `LOOPS_REFERENCE` / `ARCHITECTURE` / `DEFERRAL_CODES` / skill docs,
  and `ll-adapt` mirrors.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-27T06:11:39 - `6b15b3a1-a94e-4eb9-affa-df6227ccba80.jsonl`
- review (layering, score writer, reason check, runtime rule decided; sections consolidated) - 2026-09-27
- `/ll:wire-issue` - 2026-09-27T05:06:41 - `cf12f410-e7b8-47d0-a1c7-8e4aef01c5e6.jsonl`
- `/ll:wire-issue` - 2026-09-27T05:06:04 - `0fc58fe0-1f4f-488e-b945-c21a1df29f1e.jsonl`
- `/ll:refine-issue` - 2026-09-27T05:03:00 - `b6aefbf4-4b7a-4b60-a3b0-f13fdc7a3e01.jsonl`
- `/ll:refine-issue` - 2026-09-27T05:01:48 - `399ba9ba-cae5-4abc-9ec9-beebb2989847.jsonl`
- `/ll:format-issue` - 2026-09-27T04:48:28 - `92da6ad0-e100-4b8d-bcc9-de840c7a338f.jsonl`
