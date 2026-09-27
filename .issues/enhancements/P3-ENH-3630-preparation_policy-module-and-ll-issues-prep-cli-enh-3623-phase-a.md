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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/mcp_server/tools.py` — imports `_load_issues_with_status` (~:88; docstring ~:84 also names it); update if promoted
- `scripts/little_loops/cli/loop/next_loop.py` — `from little_loops.cli.issues.search import _load_issues_with_status` (~:136)
- `scripts/little_loops/cli/issues/count_cmd.py` — imports/calls `_load_issues_with_status` (~:24)
- `scripts/little_loops/cli/issues/list_cmd.py` — imports/calls `_load_issues_with_status` (~:33)
- `scripts/little_loops/cli/issues/search.py` — defines `_load_issues_with_status` (~:125) and calls it internally (~:312)
- `_resolve_issue_id` (`cli/issues/show.py`) has ~26 importers under `cli/issues/` plus `cli/loop/_scaffold_core.py`, `cli/learning_tests.py`, `cli/history_context.py` and `mcp_server/tools.py`. Using public `issue_parser.resolve_issue_path` from the policy leaves all of them untouched; do **not** rename `_resolve_issue_id`
- `scripts/little_loops/loops/autodev.yaml` (7 sites), `refine-to-ready-issue.yaml` (12), `prepare-issue.yaml` (1) — shell out to `ll-issues run-record write ... || true`; depend only on flags and exit code, so the helper extraction must not change either (no edits)

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_issues_search.py` — 4 tests (~:1371-1420) do `from little_loops.cli.issues.search import _load_issues_with_status`; will break if the private name is removed. Update the imports, or keep a private alias
- `scripts/tests/test_arm_proposal_revision.py` — patches `"little_loops.cli.issues.show._resolve_issue_id"` by string; breaks on any rename of that symbol (another reason not to rename it)
- `scripts/tests/test_run_record.py` — asserts the `[RUN_RECORD_WRITTEN] <id> <outcome> <path>` stdout line (~:308), the `Error: Issue '<id>' not found.` stderr + exit 2 path, and `ValueError("unknown run-record writer: ...")`; all three must survive the helper extraction. New direct unit tests for the extracted helper belong here
- `scripts/tests/test_builtin_loops.py` — `test_route_tables_cover_every_run_record_token` and the ~:3226 assertion `"run-record write" not in state["action"]`; unaffected while no loop YAML changes
- `scripts/tests/test_set_scores_cli.py` (`TestIssuesCLISetScores`, `TestSetScoresClear`) — must stay green if score-clearing is extracted from `cmd_set_scores`; `scripts/tests/test_feat_3149_mcp_mutation_tools.py` — only coverage of `apply_status_transition`; add in-process failure-path tests for `prep` alongside it
- `scripts/tests/test_cli_surface.py` — scrapes the installed CLI (`cli_surface_accepts(idx, "ll-issues", ...)`); a `prep` flags assertion can go here
- `scripts/tests/test_docs_audience_gate.py` — the new CLI.md / API.md sections must not cite `scripts/tests/…` (fixture path) or "this repo"; describe in reader terms or add `ll-audience-ok:`
- `scripts/tests/test_enh2776_no_loop_helpers_module.py` — not read; confirm the `preparation_policy` name is not caught by its pattern
- `scripts/tests/test_streaming_cache_parity.py` — iterates `fixtures.iterdir()` directories; confirm it does not target `scripts/tests/fixtures/` (the new top-level YAML would be the first there)
- Pattern sources for new tests: `test_prepare_issue.py:86` (`load_and_validate(WRAPPER)`) for the fixture-validation test; `test_autodev_characterization.py` (`pytestmark = pytest.mark.slow`, `@pytest.mark.timeout(300)`) and `test_research_triage.py:646-647` for slow gating; `test_ll_issues_format_check.py::test_fix_apply_is_idempotent` for idempotency; conftest `make_project` / `issues_dir` / `temp_project` fixtures

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

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/CLI.md` — `#### ll-issues run-record` and `#### ll-issues next-obligation` are the section templates for `#### ll-issues prep`
- `docs/reference/API.md` — CLI subcommand table (~:4655-4667, beside the `next-obligation` / `run-record` rows) gets a `prep` row; module table (~:74, beside `little_loops.cli.issues.run_record`) gets a `little_loops.preparation_policy` row; the `little_loops.run_record` section should mention the new shared helper
- `docs/guides/LOOPS_REFERENCE.md` — "Typed run record (ENH-3597)" / "Score dispatch (ENH-3604)" mention `run-record` and `next-obligation`; no edit in Phase A (no loop changes), revisit in ENH-3623 Phase B/C

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

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **`policy_transform` does not exist on `main`.** The harness parameter on `main` is `autodev_transform: Callable[[dict], dict] | None` in `scripts/tests/autodev_harness.py:run_autodev` (alongside `prepare_issue_yaml`), applied to the parsed `autodev.yaml` in `_load_fsm`. `policy_transform`, `Crash.replay_same`, `state#N` fault points and `AutodevResult.inner_calls` are spike-only; `Scenario.faults` and `Crash` exist but with none of those. Porting the harness means extending it, and the spike's transform must be adapted to (or wrapped as) `autodev_transform`.
- **`scripts/little_loops/run_record.py` already exists** (typed `RunRecord`, `write_run_record`, `read_run_record`, `record_token`, `outcome_from_legacy_class`, `WRITERS`, `LEGACY_CLASSES`) and imports only `file_utils`. The shared helper is an *addition to* it, not a new file, and must not pull in `cli/` or `config` imports if the policy is to stay CLI-independent.
- **Record assembly is inline in `cli/issues/run_record.py:cmd_run_record_write`** and depends on: `readiness_status` (`cli/issues/check_readiness.py`), issue resolution, `canonical_record_id`, `derive_child_ids`, `_read_broke_down`, and the `ready` (`thresholds_met`) predicate. The ENH-3625 check-design term is `not design_gate_failed(check_format_gaps(path))` (both in `issue_parser.py`), inline rather than a named helper. The outcome precedence in `outcome_from_legacy_class` (cancelled, decomposed, retryable_error, blocked, deferred, else ready-or-blocked by `thresholds_met`) is the contract both writers must share. `run-record` also has `read`, `clear` and `forward` subcommands that reuse `canonical_record_id`; they must keep working.
- **`cmd_run_record_write` callers** (all pass `--legacy-class` or thresholds): `loops/refine-to-ready-issue.yaml` (~10 states), `loops/autodev.yaml` (`--writer prepare-issue`), `loops/prepare-issue.yaml`. None may change behavior.
- **In-process replacements for the spike's `_ll_issues()`** (spike call sites: `set-scores --clear`, score set, `set-status open`, `set-status deferred`; return code ignored):
  - status: `cli/issues/set_status.py:apply_status_transition(config, path, issue_id, status, *, reason=None, by=None, cascade_to=None)` is non-printing, atomic under `acquire_lock`, and records history rows. It takes a resolved path.
  - scores: **no callable exists**; `cli/issues/set_scores.py:cmd_set_scores(config, Namespace)` writes inline via `update_frontmatter` / `remove_frontmatter_keys(content, SCORE_KEYS)`. Either extract a function or call `cmd_set_scores` with a constructed `Namespace` and check its return code.
  - format-check payload: assembled inline in the JSON branch of `cli/issues/format_check.py:cmd_format_check`; the in-process source for Q1 is `issue_parser.superseded_marker_count(path)`, printed regardless of exit code.
  - check-design: `cmd_check_design` is `check_format_gaps(path)` then `design_gate_failed(gaps)` (exit 0/1/2).
- **`select_next_obligation` lives in `cli/issues/next_obligation.py`** (`select_next_obligation(config, issue_id, *, skip=(), readiness_override=None, outcome_override=None, honor_waiver=False) -> ObligationResult | None`; raises `ObligationProbeError` on fail-closed probes). The policy calling it introduces a `preparation_policy -> cli/` import, the same layering the shared-record-helper bullet avoids; the module docstring note (or a promotion out of `cli/`) must state which.
- **Snapshot imports**: `cli/issues/show.py:_resolve_issue_id` is already a thin wrapper over public `issue_parser.resolve_issue_path(config, user_input)`, so the policy can use the public function directly. `cli/issues/search.py:_load_issues_with_status(config, include_open, include_done, include_deferred)` is the one that still needs promoting or a layering note.
- **Threshold accessors**: `BRConfig` has no `readiness_threshold` / `outcome_threshold` shortcuts. Values live at `config.commands.confidence_gate` (`ConfidenceGateConfig`, defaults 85 / 65, `config/automation.py`), but `check_readiness.py:readiness_status` and `resolve_confidence_thresholds` deliberately read raw `ll-config.json` key by key so absence falls back to caller defaults. `next_preparation_step`'s `readiness_threshold` / `outcome_threshold` parameters must be resolved consistently with that.
- **`prep` registration surface in `cli/issues/__init__.py:main_issues`**: four touch points for `run-record` today (import inside the `cli_event_context` block, epilog line, `add_*_parser(subs)` call beside `add_next_obligation_parser`, `if args.command == ...` dispatch branch). `add_run_record_parser` sets `set_defaults(command=...)` and nested subparsers with `required=True`; the spike's `add_prep_parser` / `cmd_prep` (`preparation_policy.py`) follow the same shape.
- **Doc gates**: `test_wiring_reference_docs.py:DOC_STRINGS_PRESENT` rows are `(doc, needle, issue_id)` tuples (existing `run-record` rows: the CLI.md section heading, the `RUN_RECORD_WRITTEN` marker, the API.md subcommand-table row and the module row). `test_cli_claims.py` only unit-tests the claim extractor (`extract_cli_flag_claims`, `ll-prose-ok` suppression); it does not enumerate subcommands, so the AC's mention of it is really about `ll-prose-ok` markers, not a group-registration check.
- **Spike facts confirmed on the tag** (`scripts/little_loops/preparation_policy.py`, ~1,230 lines): `MAX_DONE_PER_PASS = 15` at line 46; `_ll_issues` at line 876 with call sites in `_run_preconditions` (~893-905) and `_apply_outcome` (~1170); `prep_step` / `prep_record` / `prep_apply` at 908 / 947 / 1000; `_apply_outcome` at 1051. The issue's `~:1095` inline-`ready` reference falls inside `_apply_outcome` and could not be independently confirmed as the exact line. Also `decide()` at 631, `snapshot_issue()` at 654, `current_pass` at 783, `add_prep_parser` / `cmd_prep` at 1186 / 1209. On `main`, `prepare-issue.yaml` has `max_steps: 20`.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/cli/loop/next_loop.py` — lazy-imports `_load_issues_with_status` inside a function; a third consumer beyond `mcp_server/tools.py`, breaks on a rename [Agent 1 finding]
- `scripts/little_loops/cli/issues/list_cmd.py` — top-level import, called in `cmd_list` [Agent 1 finding]
- `scripts/little_loops/cli/issues/count_cmd.py` — lazy import of `_load_issues_with_status` [Agent 1 finding]
- `scripts/little_loops/cli/issues/search.py` — defines it and calls it in `cmd_search`; keep a backward-compatible alias if promoting [Agent 1 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — ~10 `run-record write` states (all `|| true`, `--legacy-class` values incl. `proposal_unsound`, `gate_unmet`, `infra`, `spike_inconclusive`, `decision_unresolved`); behavior must not change under the helper extraction [Agent 2 finding]
- `scripts/little_loops/loops/autodev.yaml` — `run-record write --writer prepare-issue` (~8 sites), `clear`, `read` (~lines 526, 691) [Agent 2 finding]
- `scripts/little_loops/loops/prepare-issue.yaml` — `clear`, `forward` (stdout captured via `TOKEN=$(...)`), `write --legacy-class infra` [Agent 2 finding]
- `cli/issues/run_record.py:cmd_run_record_write` contract to preserve: `[RUN_RECORD_WRITTEN] <canonical_id> <outcome> <path>` on stdout with exit 0; unresolved issue prints `Error: Issue '...' not found.` to stderr with exit 2. `read`/`clear`/`forward` reuse `canonical_record_id`, `derive_child_ids`, `_read_broke_down`, so those must stay importable from `cli/issues/run_record.py` (or be re-exported) [Agent 2 finding]
- Markers to remove once `prep` exists: `ll-prose-ok` also appears in ENH-3600 (not only ENH-3630 and ENH-3623). Readers: `issues/cli_claims.py:_SUPPRESS_RE`, `issues/symbol_claims.py:_SUPPRESS_RE`, `cli/verify_skill_prose.py:_SUPPRESS_RE` [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/API.md` — module table needs a `little_loops.preparation_policy` row beside `little_loops.run_record` / `little_loops.cli.issues.run_record`; the existing `search.py:_load_issues_with_status` cite (for `list --status done --json`) goes stale if the helper is renamed [Agent 2 finding]
- `docs/reference/CLI.md` and `docs/reference/API.md` new text falls under `scripts/tests/test_docs_audience_gate.py`: cite `little_loops.<module>`, never `scripts/little_loops/` or `scripts/tests/` paths [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` ("Typed run record (ENH-3597)") and `scripts/little_loops/loops/README.md` mention `run-record`; neighbours only, ENH-3623 Phase C scope [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/pyproject.toml` `[tool.pytest.ini_options]` — `--strict-markers` is on, `--timeout=120`, `-n logical`, `--dist loadfile`; any new marker for the gated resume matrix must be registered there (registered today: `integration`, `slow`, `conformance`, `no_parallel`, `grader_case`) [Agent 3 finding]
- `scripts/little_loops/config-schema.json` — no change needed; thresholds already live at `commands.confidence_gate.{readiness,outcome}_threshold` (`config/automation.py:ConfidenceGateConfig`) [Agent 1/2 finding]

### Tests (wiring additions)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_issues_search.py` — 4 tests import `_load_issues_with_status` by name (class near line 1377); update or keep an alias if promoted [Agent 1/3 finding]
- `scripts/tests/test_set_scores_cli.py` (`test_clear_removes_all_six_keys_and_is_idempotent`, `test_set_scores_writes_all_fields`, …), `test_set_status_cli.py`, `test_feat_3149_mcp_mutation_tools.py`, `test_bug3150_issue_mutator_atomicity.py` — must stay green if scores writing is extracted from `cmd_set_scores` or status callers change [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` (`run-record write` assertions ~line 3226, router check ~6530, `test_route_tables_cover_every_run_record_token` ~7818), `test_autodev_ladder_run_records.py`, `test_autodev_characterization.py`, `test_prepare_issue.py`, `test_ll_logs.py` — assert the `[RUN_RECORD_WRITTEN]` marker / run-record wiring; must stay green [Agent 2/3 finding]
- `scripts/tests/test_autodev_characterization.py::test_harness_accepts_replacement_prepare_issue_and_autodev_transform` (~:962) — existing pattern for copying a replacement `prepare-issue` YAML into the harness `loops_dir`; model for the fixture parity tests [Agent 3 finding]
- `scripts/tests/test_autodev_characterization.py::test_autodev_resume_characterization` (~:939) — crash/resume pattern (`_with_crash`, `_replayed`, `_assert_hermetic`, `Crash(state, when=…)`) to extend for `state#N` fault points [Agent 3 finding]
- Fixture-validation pattern for the "loads and validates" test: `load_and_validate(path)` (see `test_fsm_schema.py::test_evaluate_unknown_key_sweep_builtin_loops_clean` ~:1943); `scripts/tests/fixtures/` and `conftest.py:fixtures_dir` already exist. No loop-count or enumeration test globs `scripts/tests/fixtures/`, so the fixture does not trip `test_doc_counts.py` or `test_builtin_loops.py` [Agent 3 finding]
- Gating caveat: there is no env-var `skipif` precedent in `scripts/tests`. Do **not** use `no_parallel` for the resume matrix (skipped outright under `-n logical`; runs only in `-n 0` via `test_no_parallel_serial_gate.py`). Use `@pytest.mark.slow` + a module `skipif` on an env var, plus `@pytest.mark.timeout` (precedent: `test_autodev_characterization.py:908`, 300 s) [Agent 3 finding]
- New `prep` help test: copy `test_run_record.py::test_subcommand_in_help` (~:450); no test asserts the `Sub-commands:` epilog text or full subcommand set, so the epilog line is untested unless added [Agent 2/3 finding]

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- If `_load_issues_with_status` is promoted: update `cli/issues/search.py`, `cli/issues/count_cmd.py`, `cli/issues/list_cmd.py`, `cli/loop/next_loop.py`, `mcp_server/tools.py` (import + docstring) and the 4 imports in `test_issues_search.py` in the same change; otherwise keep the private import and record the layering note
- Do not rename `_resolve_issue_id`; use `issue_parser.resolve_issue_path` from the policy (avoids ~30 importers and the `test_arm_proposal_revision.py` string patch)
- Preserve the `cmd_run_record_write` CLI contract when extracting the helper: `[RUN_RECORD_WRITTEN]` stdout line, unresolved-issue stderr + exit 2, `ValueError("unknown run-record writer: ...")`; add direct helper unit tests to `test_run_record.py`
- Add a `prep` flags assertion to `test_cli_surface.py` and keep CLI.md / API.md wording clear of `scripts/tests/…` paths (`test_docs_audience_gate.py`)
- Before adding the fixture and module, check `test_enh2776_no_loop_helpers_module.py` and `test_streaming_cache_parity.py` do not trip on `preparation_policy` or a top-level `scripts/tests/fixtures/*.yaml`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/loop/next_loop.py`, `cli/issues/list_cmd.py`, `cli/issues/count_cmd.py`, `scripts/tests/test_issues_search.py` — if `_load_issues_with_status` is promoted, switch to the public name (or keep an alias in `search.py`)
- Update `docs/reference/API.md` — refresh the `search.py:_load_issues_with_status` cite if renamed
- Register any new pytest marker in `scripts/pyproject.toml` (`--strict-markers`)
- Preserve the `run-record write` stdout marker and exit-2 contract; re-run `test_run_record.py`, `test_builtin_loops.py`, `test_autodev_ladder_run_records.py`, `test_prepare_issue.py` after the helper extraction
- Keep `canonical_record_id`, `derive_child_ids`, `_read_broke_down` importable from `cli/issues/run_record.py` (used by `read`/`clear`/`forward`)
- Remove `ll-prose-ok` markers from ENH-3600 as well as ENH-3630 and ENH-3623 once `prep` is registered

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
- `/ll:wire-issue` - 2026-09-27T05:06:41 - `cf12f410-e7b8-47d0-a1c7-8e4aef01c5e6.jsonl`
- `/ll:wire-issue` - 2026-09-27T05:06:04 - `0fc58fe0-1f4f-488e-b945-c21a1df29f1e.jsonl`
- `/ll:refine-issue` - 2026-09-27T05:03:00 - `b6aefbf4-4b7a-4b60-a3b0-f13fdc7a3e01.jsonl`
- `/ll:refine-issue` - 2026-09-27T05:01:48 - `399ba9ba-cae5-4abc-9ec9-beebb2989847.jsonl`
- `/ll:format-issue` - 2026-09-27T04:48:28 - `92da6ad0-e100-4b8d-bcc9-de840c7a338f.jsonl`
