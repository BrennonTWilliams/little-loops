---
id: FEAT-3573
type: FEAT
title: Autodev code formatting and quality evidence gate before closure credit
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:13Z'
parent: EPIC-3565
decision_needed: false
blocks:
- ENH-3577
- ENH-3600
blocked_by:
- ENH-3613
relates_to:
- ENH-3612
confidence_score: 75
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# FEAT-3573: Autodev code formatting and quality evidence gate before closure credit

## Summary

Autodev closes the loop on implementation with `verify_impl_closed`, which checks issue
status (`done|completed|cancelled`). The lifecycle helper is a frontmatter check. Code
quality rests on `/ll:manage-issue` Phase 4's instruction that configured checks must pass.
That is an agent instruction, not a machine-readable result. Specific gaps:

- Phase 4 never runs `project.format_cmd`.
- No structured record of which checks ran and passed against the resulting revision.
- `oracles/code-run-gate` exists but is outside autodev's call graph and has no format stage.

_Split out (2026-09-26):_ the Phase 4 argument-append fix is now **ENH-3612**. The
`summary.json` cancelled/implemented split is now **ENH-3613**, which blocks this issue.
This issue is only the autodev quality gate.

## Current Behavior

Autodev credits closure from frontmatter status alone. `manage-issue` runs checks by instruction and never runs `format_cmd`.

## Expected Behavior

An implemented (`done`/`completed`) closure earns credit only when a passing
format-check/lint/type/test result is recorded for the commit it produced, with the
format check limited to changed files. A gate failure keeps the issue out of
`autodev-passed.txt`, puts it in a `quality_failed` ledger, and appears in `summary.json`.
`cancelled` closures skip the gate.

## Use Case

An operator runs `ll-loop run autodev` over a sprint queue and reads `summary.json` the
next morning. Today, `closed: 5` means only that five issue files say `done`. With the
gate, `closed` counts only issues whose resulting commit passed the configured
format-check, lint, type and test commands. `quality_failed` lists the issues that
flipped to `done` but broke the build, so the operator knows which commits to review
before merging.

## Motivation

A frontmatter flip to `done` is the only closure evidence autodev consumes. Tamper and work
guards help, but nothing establishes that formatting, lint, types and tests passed on the
final change.

## Proposed Solution

After an implemented closure, run a deterministic quality gate (extended
`oracles/code-run-gate`) that:

1. Runs a **check-only** format stage **scoped to the files changed by the
   implementation**. A bare `ruff format scripts/` in this repo reformats ~30 unrelated
   files because main carries format drift. A mutating format stage would also leave
   uncommitted edits behind, because manage-issue Phase 5 has already committed.
2. Runs `lint_cmd`, `type_cmd` and `test_cmd` exactly as configured.
3. Records a structured evidence record tied to the commit the implementation produced.
4. Gates `finalize_done`'s passed bucket on that record. There is no automatic repair in
   v1 (see Design Decisions).

### Design Decisions (review 2026-09-26)

These close the gaps a pre-implementation review found. They are directive.

- **Format stage is check-only, and it uses a new key.** `format_cmd` changes files and
  carries its own path argument (`ruff format scripts/`), so it cannot be scoped by
  adding files. Add a new, unset-by-default config key `project.format_check_cmd` with a `{files}`
  placeholder, for example `ruff format --check {files}`. The oracle replaces `{files}`
  with the shell-quoted changed-file list. When the key is unset, the stage writes
  `SKIP format_check_cmd=null`. `format_cmd` stays unread at runtime.
- **Changed-file set.** `git diff --name-only --diff-filter=d <base>..<head>` plus
  uncommitted changes. This drops deleted files. Then filter by the unset-by-default
  `project.format_check_extensions` (for example `[".py", ".pyi"]`). If the key is unset,
  pass every file. If the filtered set is empty, the format stage is SKIP. A formatter
  given a non-source file explicitly (such as a `.md` file) can fail, so the extension
  filter matters for mixed-language changes.
- **The oracle format stage is opt-in by parameter.** It runs only when the caller passes
  the new `changed_files_path` parameter. Existing callers (`rn-remediate.yaml`
  `run_code_gate`, `rn-refine.yaml` `verify_leaf`, and `rn-implement` transitively) pass
  no path, so they get SKIP even when `format_check_cmd` is configured. Their behavior
  does not change.
- **Base revision.** `implement_current` writes `git rev-parse HEAD` to
  `${context.run_dir}/quality/<ID>.base` before it runs `ll-auto`. This is a line added
  to the existing action, not a new state, so the routing into `implement_current` does
  not change.
- **Placement.** `verify_impl_closed.on_yes` → `route_quality_gate` → `run_quality_gate`
  (`loop: oracles/code-run-gate`) → `record_quality_evidence` → `dequeue_next`.
  - `route_quality_gate` sends `cancelled` closures straight to `dequeue_next`, because
    nothing was implemented. Every other closure goes to `run_quality_gate`, after the
    state computes the changed-file set.
  - `verify_impl_closed` has already cleared `autodev-inflight`, so the new states sit
    outside the inflight-clearing chain.
  - `implement_current.on_yes → verify_impl_closed` stays as it is.
- **Oracle parameters from autodev.** Pass `min_pass_rate: 1.0`, because the oracle
  default of 0.95 would credit a run with failing tests. Pass `test_cmd`, `lint_cmd` and
  `typecheck_cmd` resolved with `ll-config get`, which honors `.ll/ll.local.md`. The
  oracle's own `resolve_commands` reads only `.ll/ll-config.json`. Also pass `issue_id`,
  `run_dir: ${context.run_dir}/quality/<ID>/` and `changed_files_path`.
- **Evidence record.** `record_quality_evidence` writes `${context.run_dir}/quality/<ID>.json`
  with these fields: `issue_id`, `base_sha`, `head_sha`, `dirty`, `changed_files`, a
  per-stage outcome (`format_check`, `lint`, `typecheck`, `test`, each
  `pass|fail|skip`), and `verdict` (`GATE_PASS|GATE_FAILED|GATE_SKIP`). `head_sha` is
  recorded at gate time. `finalize_done` must not compare against the live HEAD, because
  later queue items move it.
- **Failure path (no repair in v1).** On `GATE_FAILED`, do not change the issue: it stays
  `done` and committed. Append `ID  quality_gate_failed` to `autodev-unverified.txt`,
  using the reasoned-line idiom from BUG-3390. The ID then counts in `not_closed` and
  goes through the existing verdict ladder (partial or phantom). `summary.json` gains
  `quality_failed`, counted from those reason lines. That is the same filter idiom as
  `notstarted_`, and it requires ENH-3613's key shape to have landed. Automatic repair/retest is a
  follow-up, not part of this issue.
- **Promotion rule.** In `finalize_done`, a `done|completed` ID is promoted only if
  `quality/<ID>.json` exists with verdict `GATE_PASS` or `GATE_SKIP`. A `cancelled` ID is
  promoted on status alone. A `done` ID with no evidence record goes to
  `autodev-unverified.txt` as `quality_evidence_missing`.
- **Escape hatch.** Add an autodev context key `quality_gate`, default `true`. With
  `false`, closure credit falls back to the old status-only check. Use it for repos
  whose base branch is red: in v1 the gate judges absolute pass/fail, so failures that
  already exist on the base fail every issue in the queue. The run summary prints a
  one-line hint when every gated issue fails.
- **Suite ownership.** v1 accepts that the suite runs twice: manage-issue Phase 4 still
  runs it, and the gate runs it again. Phase 4 is the only verification on the
  `ll-auto`, `ll-parallel` and `ll-sprint` paths, and the implementing agent needs test
  feedback, so removing it would regress those paths. An autodev-only opt-out (an env
  flag that tells Phase 4 to run only targeted tests) is a follow-up.
- **Timeouts.** `run_test` has `timeout: 600` and the oracle has `timeout: 1800`. Before
  wiring, measure this repo's `test_cmd` wall-clock, plus the `prepatch_check: fail`
  worktree fork on `run_test`. If it exceeds about 80% of 600s, add a caller-set
  `test_timeout_seconds` oracle parameter instead of raising the default for existing
  callers.

**Option A**: `manage-issue` Phase 4 writes a structured result file that autodev reads.

**Option B**: An autodev gate (extended `oracles/code-run-gate`) runs after `implement_current` and is the only place the suite runs.

> **Selected:** Option B — the gate is deterministic, FSM-native, and sits outside the opaque `ll-auto` subprocess.

### Decision Rationale

**Decision point:** Owner of the quality run

**Selected**: Option B — autodev gate (extended `oracles/code-run-gate`)

**Reasoning**: `implement_current` shells out to `ll-auto`, so autodev cannot observe what manage-issue ran; Option A would need a new file contract across the ll-auto boundary and would trust an agent-written result. Option B is a non-LLM evaluator in the FSM, matches the `rn-implement` usage of `oracles/code-run-gate`, and can be tied to the revision recorded before `implement_current`. ~~Under B, manage-issue Phase 4 must not re-run the full suite.~~ _Amended 2026-09-26:_ Phase 4 keeps its suite run in v1 (see Design Decisions → Suite ownership). The verbatim-commands fix moved to ENH-3612.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A | 1 | 1 | 2 | 1 | 5/12 |
| B | 3 | 2 | 3 | 2 | 10/12 |

**Key evidence**: scoring done from direct inspection (`autodev.yaml` `implement_current` → `ll-auto`; `oracles/code-run-gate.yaml`; `skills/manage-issue/SKILL.md` Phase 4), not parallel agent runs.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `implement_current` (:1154, base-rev line), `verify_impl_closed` (:1197, `on_yes` retarget), new `route_quality_gate` / `run_quality_gate` / `record_quality_evidence`, `finalize_done` (:3041, promotion rule + `quality_failed` key), `quality_gate` context default
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — new `format_check_cmd` / `changed_files_path` / (maybe) `test_timeout_seconds` params, new `run_format_check` state, `aggregate` sidecar list
- `scripts/little_loops/config-schema.json` (`project`, near `format_cmd` :45) — add `format_check_cmd` and `format_check_extensions`
- `scripts/little_loops/config/core.py` — `ProjectConfig` (:220 `format_cmd` neighbour), `from_dict` (:244), `to_dict` (:770)
- ~~`skills/manage-issue/SKILL.md` — Phase 4 verification commands~~ → moved to ENH-3612

_Wiring pass added by `/ll:wire-issue`:_
- ~~`.gemini/` / `.kimi-code/` / `.qwen/` `skills/manage-issue/SKILL.md` mirrors~~ → moved to ENH-3612
- `scripts/little_loops/loops/README.md` — package-data catalog row for `oracles/code-run-gate` (:194) documents the six-command matrix; a format stage joins it [Agent 1 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_lifecycle.py` — lifecycle verification
- `scripts/little_loops/issue_manager.py` — ll-auto

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `finalize` derives `NOT_CLOSED`/`SKIPPED`/`GATE_BLOCKED`/`DECISION_UNRESOLVED` from `autodev-passed.txt`/`autodev-skipped.txt`/`autodev-gate-blocked.txt`/`autodev-decision-unresolved.txt`/`autodev-inflight`/`autodev-queue.txt` in the shared run_dir (reads :1058-:1112); under the new gate, a frontmatter-closed issue that fails quality evidence stays out of `autodev-passed.txt` and silently disappears from the parent's `closed`/`not_closed` accounting unless a new ledger or summary key is read there [Agent 1+2 finding]
- `scripts/little_loops/parallel/worker_pool.py` — imports `verify_work_was_done` in `_verify_work_was_done` (:43, :1380); the ll-parallel/ll-sprint quality-evidence consumer — consistency overlap, no autodev-path edit [Agent 1 finding]
- `scripts/little_loops/fsm/persistence.py` (`archive_run` copies `run_dir/summary.json`, :660), `scripts/little_loops/cli/loop/audit.py` (:194), `scripts/little_loops/cli/loop/evidence.py` (:214, :314), `scripts/little_loops/hooks/pre_compact_handoff.py` (:126-:130) — shape-agnostic summary.json consumers (copy/hash/passthrough, no key reads); additive cancelled/implemented keys are safe for all four [Agent 1 finding]

### Similar Patterns
- `rn-implement.yaml` usage of `oracles/code-run-gate`

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop` finalize tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:661` — `TestPrePatchCheckReachability.test_code_run_gate_state_set_unchanged` freezes the oracle's state set to exact equality (9 states); adding a format *state* trips it, and per its own comment requires re-reading ENH-2997's Scope Boundaries [Agent 1 finding]
- `scripts/tests/test_builtin_loops.py:15174` — `TestCodeRunGateOracle.test_run_states_chain_forward_and_terminate_at_aggregate` and `test_run_states_converging_routing_not_regressed` (:15485) pin the run_* chain edges pairwise; `aggregate`'s sidecar loop (`for f in build.txt test-results.txt typecheck.txt lint.txt health.txt`) must grow the format sidecar [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:598` — `TestCodeRunGateOptionalParams.test_resolve_commands_interpolates_without_cmd_overrides` is the `:default=` tripwire: every new `format_cmd` guard AND assignment RHS needs `:default=` or the GATE_FAILED_INFRA laundering regression returns [Agent 1 finding]
- `scripts/tests/test_builtin_loops.py:21020` — `TestInterpSweepBaseline` and `MR11_MARKER_ALLOWLIST` (asserted :21313): a new `context.format_cmd` ref in the oracle needs both a baseline entry and an allowlist tuple [Agent 1 finding]
- `scripts/tests/test_bug3269_test_cmd_resolution_gate.py` — `format_cmd` already in `PROJECT_COMMAND_KEYS` (:47); the oracle is a permanent exemption (:58); assertion 2 requires any `${context.format_cmd}` ref in `autodev.yaml` to resolve against a declared `context:`/`parameters:` key [Agent 1 finding]
- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop` promotion/phantom/no-op/mixed-run tests execute `finalize_done` with no quality-evidence artifacts (fixtures must gain them when promotion is gated); `test_implement_current_routes_to_verify_impl_closed` breaks if a gate state is interposed; `TestAutodevAuthGuard.test_autodev_implement_current_failure_chain_clears_inflight` (:18363) requires new states in that region to clear `autodev-inflight` or route only to clearing states [Agent 3 finding]
- `scripts/tests/test_rn_remediate.py` — `TestRunCodeGate` (:2019) pins the existing call-site contract (`run_code_gate.loop`, `with:` bindings, GATE_PASS/GATE_SKIP routing) that must stay behaviorally unchanged; `scripts/tests/test_rn_refine.py:1648` pins `verify_leaf`'s `oracles/code-run-gate` wiring likewise [Agent 1 finding]
- ~~`test_manage_issue_changelog_gate.py`, `test_wiring_skills_and_commands.py`, `test_enh494_skill_companions.py`~~ → manage-issue Phase 4 work moved to ENH-3612
- `scripts/tests/test_builtin_loops.py:15047` — `TestCodeRunGateOracle` parameter test pins "run_dir, issue_id + the six command fields"; new params extend it
- `scripts/tests/test_bug3269_test_cmd_resolution_gate.py:47` — `PROJECT_COMMAND_KEYS` gains `format_check_cmd` if autodev resolves it via `ll-config get`
- `scripts/tests/test_fsm_topology.py` `TestAutodevSmoke.test_autodev_topology` — pinned state count (autodev has 107 states as of 2026-09-26; +3 new states)
- New tests: oracle format stage SKIPs without `changed_files_path` (existing-caller invariance); `{files}` substitution quotes paths and drops deleted/filtered files; `finalize_done` promotion requires evidence for `done` but not `cancelled`; `quality_gate_failed` / `quality_evidence_missing` reason lines feed `not_closed` and `quality_failed`; `quality_gate: false` restores status-only credit

### Documentation
- `docs/guides/` loop guide for autodev, if it documents closure semantics

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/loops.md:874` — full `oracles/code-run-gate` reference (params table :889, stage flow, direct-call example :927) gains the format stage/param [Agent 1 finding]
- `docs/guides/LOOPS_REFERENCE.md:1007` — `Closure accounting` documents `autodev-passed.txt`/`autodev-skipped.txt` as auto-refine's sources; `:1079` documents `finalize_done`'s bucket list — the cancelled/implemented split edits both [Agent 2 finding]
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md:253` — `GATE_FAILED` outcome-token row enumerates "build / test / typecheck / lint / health"; format joins the enumeration [Agent 2 finding]
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:692` — declares `oracles/code-run-gate.yaml` a permanent exemption for command resolution; the format stage's `format_cmd` resolution follows the same exemption [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:305` — add `format_check_cmd` (`{files}` placeholder, check-only) and `format_check_extensions` rows beside `format_cmd`; `format_cmd` stays without a runtime reader (amended 2026-09-26)
- `docs/guides/LOOPS_REFERENCE.md` — autodev `quality_gate` context key and the `quality_failed` summary key

### Configuration
- `project.format_check_cmd` (new), `project.format_check_extensions` (new), `lint_cmd`, `type_cmd`, `test_cmd`
- autodev context `quality_gate` (new, default `true`)

### Changed-file scoping

`implement_current` shells out to `ll-auto`, so autodev cannot see which files the
implementation touched. Record the base revision (`git rev-parse HEAD`) into the run dir
**before** `implement_current`, and compute the changed-file set as
`git diff --name-only --diff-filter=d <base>..HEAD` (plus any uncommitted changes) after it.
The format stage runs only on that set (see Design Decisions for extension filtering).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- _Line numbers below are as of 2026-09-25; on 2026-09-26 autodev `implement_current` is :1154, `verify_impl_closed` :1197, `finalize_done` :3041, `ProjectConfig.format_cmd` :220, and `summary.json` has 12 keys (BUG-3603 added `proof_gate_infra`)._
- `skills/manage-issue/SKILL.md` Phase 4 confirmed as described (now ENH-3612's scope): lines 354-372 append `tests/ -v` to `{{config.project.test_cmd}}` and `{{config.project.src_dir}}` to the lint/type commands, run `build_cmd`/`run_cmd` bare, and the skill directory contains zero occurrences of `format_cmd` — formatting is never run by manage-issue. The "Headless-Safe Final Test Run" subsection (:376) mandates the scratch-redirect foreground suite run.
- `oracles/code-run-gate.yaml` current surface: params `run_dir`, `issue_id`, `min_pass_rate` (default 0.95), `health_bound_seconds`, plus optional `build_cmd`/`test_cmd`/`typecheck_cmd`/`lint_cmd`/`run_cmd`/`health_url` overrides (:52-103). Stages `resolve_commands → run_build → run_test → run_typecheck → run_lint → service_health → aggregate`; every stage failure still advances (no MR-4 partial-route dead-end). No format stage or format param exists.
- Command-resolution convention inside the oracle: `resolve_commands` reads `.ll/ll-config.json` `project.*` with alias handling (`typecheck_cmd`/`type_cmd`, `start_cmd`/`run_cmd`, ARCHITECTURE-123) and honors caller overrides via `${context.<cmd>:default=}`; other loops use `ll-config get project.test_cmd`, which also honors `.ll/ll.local.md`.
- Baseline→changed-files precedent exists one level down the call chain: `issue_manager.py:1284-1289` (`process_issue_inplace`) captures `git rev-parse HEAD` immediately before implementation, consumed by `work_verification.py:470` (`_detect_meaningful_changes`) as `git diff --name-only <baseline>..HEAD` plus staged/unstaged diffs (:428, :445). `prepatch_check.py:248` (`resolve_base_ref`) is the public base-ref resolver with merge-base fallback. autodev.yaml contains no `git` invocation today, so the base revision must be recorded loop-side as the Changed-file scoping note plans.
- Load-bearing invariant: `test_builtin_loops.py:7465` (`test_check_passed_stages_instead_of_passes`) asserts `finalize_done` is the only state allowed to populate `autodev-passed.txt` (the `check_passed` state must stage, not pass). Whatever gates closure credit must route promotion through `finalize_done`, or amend that test's contract knowingly.
- `verify_issue_completed` (`issue_lifecycle.py:768`) is not in autodev's call chain — its only production callers are in `issue_manager.py` (:1469, :1560, :2220), i.e. the `ll-auto`/manage-issue path. The Dependent Files entry covers that path only; autodev re-implements the status check in shell.
- Existing closure-state tests and their harness: `test_builtin_loops.py` `TestAutodevLoop` (:6643) — `_run_finalize_done` (:7481) executes the state's action under `bash -c` after `${context.run_dir}` substitution and `$${`→`${` un-escaping; tests pin phantom-on-unclosed (:7485), verified promotion (:7518), no-op (:7544), rate-limit routing through finalize (:7553-:7574), BUG-3390 dedupe (:7886), and `verify_impl_closed` routing (:7827-:7871). The 11-key `summary.json` set (`verdict`, `closed`, `not_closed`, `skipped`, `gate_blocked`, `decision_unresolved`, `not_started`, `inflight_unresolved`, `abandoned`, `stop_reason`, `pending`) is load-bearing for these tests and is the shape the cancelled/implemented split extends.
- No doc under `docs/` documents autodev's closure buckets or `summary.json` keys today; the only adjacent passage is `docs/guides/RECURSIVE_LOOPS_GUIDE.md` §PHASE1_NOT_STARTED (:287-304, `not_started` verdict semantics).

## Open Questions

- **Owner of the quality run** ✅ **RESOLVED** (2026-09-25 by /ll:decide-issue): (b) an
  autodev gate (extended `oracles/code-run-gate`) that runs after `implement_current` and
  is the only place the suite runs. The full suite runs once per issue.

## Implementation Steps

1. ~~Decide the single owner of the post-implementation quality run~~ — decided: autodev gate (Option B)
2. Measure this repo's `test_cmd` wall-clock under the oracle's `run_test` (with `prepatch_check`); add `test_timeout_seconds` only if needed
3. Add `project.format_check_cmd` / `format_check_extensions` to schema, `ProjectConfig`, and `CONFIGURATION.md`
4. Extend `oracles/code-run-gate`: `changed_files_path` + `format_check_cmd` params, `run_format_check` state (opt-in, SKIP without a path), `aggregate` sidecar list; update the state-set freeze, baseline and MR11 allowlist
5. autodev: base-rev line in `implement_current`; `route_quality_gate` → `run_quality_gate` → `record_quality_evidence` after `verify_impl_closed.on_yes`; `quality_gate` context default
6. `finalize_done`: evidence-gated promotion for `done|completed`, `quality_gate_failed` / `quality_evidence_missing` reason lines, `quality_failed` key (requires ENH-3613's shape)
7. `auto-refine-and-implement.yaml` `finalize`: confirm quality-failed IDs land in its `not_closed` accounting
8. Docs and tests per Integration Map
9. ~~Fix manage-issue Phase 4 to use configured commands verbatim~~ → ENH-3612
10. ~~Split cancelled from implemented closures in `summary.json`~~ → ENH-3613 (blocks this issue)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `aggregate` in `oracles/code-run-gate.yaml` — add the format sidecar to its file list and keep the `SKIP <cmd>=null` first-line convention so `classify` routing survives
- Handle `TestPrePatchCheckReachability` — a new oracle *state* trips the frozen 9-state exact-set equality; either extend the freeze knowingly (its comment requires re-reading ENH-2997's Scope Boundaries) or add format as a stage of an existing state
- Route gate-failed closures through the parent — `auto-refine-and-implement.yaml` `finalize` must count them (new ledger or summary key) or they vanish from `closed`/`not_closed`
- Add baseline + MR11 allowlist entries for the oracle's new `context.format_cmd` refs; keep `:default=` on both guard and RHS in `resolve_commands`
- Update `docs/reference/loops.md`, `docs/guides/LOOPS_REFERENCE.md` (:1007, :1079), `docs/guides/RECURSIVE_LOOPS_GUIDE.md:253`, and `scripts/little_loops/loops/README.md:194` for the format stage
- ~~Regenerate `skills/manage-issue` mirrors~~ → ENH-3612
- Update `test_builtin_loops.py` finalize fixtures with quality-evidence artifacts when promotion is gated, and keep new autodev states inside the `autodev-inflight`-clearing chain (`test_autodev_implement_current_failure_chain_clears_inflight`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Constraint: the gate must remain a non-LLM evaluator in the FSM — `code-run-gate` is all-shell with `exit_code`/`output_numeric`/`classify` evaluators, so extending it keeps the autodev meta-loop MR-2-compliant; a shared Python runner preserves the same property only if the FSM routes on its exit code, not on model output.
- Constraint: the format stage consumes `project.format_cmd`, which today has no runtime reader (`config/core.py:210`; serialized at `:770` only) — there is no existing format-invocation helper to reuse, but the scoping primitives exist (`work_verification.py` diff computations, `filter_excluded_files` :32).
- Constraint: adding states to `autodev.yaml` bumps the state count pinned by `test_fsm_topology.py` `TestAutodevSmoke.test_autodev_topology` (currently 105 states) and must keep the `loop_interpolation_baseline.json` `finalize_done` entry valid.
- Verification surface: `python -m pytest scripts/tests/test_builtin_loops.py -k "finalize or verify_impl"` exercises the closure states today; `ll-loop validate` plus `scripts/tests/test_builtin_loops.py` gate classes `TestCodeRunGateOracle` (:14959) / `TestCodeRunGateOracleWiring` (:18851) / `TestCodeRunGateOptionalParams` (:598) cover the oracle side.

## Impact

- **Priority**: P3
- **Effort**: Large
- **Risk**: Medium. Adds wall-clock time per issue.

## Program Design

### Types

- New per-revision quality-evidence record (name open) — the structured "which configured checks ran and passed, against which revision" payload this issue requires. Constraint on the shape, not a prescription: it must carry the revision it attests to, the changed-file set the format stage was scoped to, and per-command outcomes; it is the only evidence `finalize_done` may credit closure on beyond issue status.

### Signatures

- `verify_issue_completed(info: IssueInfo, config: BRConfig, logger: Logger) -> bool` — `scripts/little_loops/issue_lifecycle.py:768`; pure frontmatter check (`done`/`cancelled` → True; missing file → True back-compat). Called only from `issue_manager.py` (:1469, :1560, :2220) — autodev's shell states re-implement the status check via `ll-issues show --json` rather than calling it.
- `resolve_base_ref(repo_root: Path, base_sha: str | None, base_branch: str) -> tuple[str, str]` — `scripts/little_loops/prepatch_check.py:248`; returns the ref plus a provenance tag (`dequeue-stamp` or `merge-base`).
- `_detect_meaningful_changes(logger: Logger, changed_files: list[str] | None, baseline_sha: str | None) -> bool` — `scripts/little_loops/work_verification.py:401`; computes `git diff --name-only <baseline>..HEAD` at :470 — the existing baseline→changed-files precedent this issue's scoping parallels.
- `ProjectConfig.format_cmd: str | None` — `scripts/little_loops/config/core.py:210`; read today only by the `to_dict` serializer (`config/core.py:770`). No runtime consumer exists anywhere.

### Call Path

Today: `autodev.yaml:implement_current` (:1106, shells `ll-auto --only`) → `verify_impl_closed` (:1149, `ll-issues show --json` status read) → `dequeue_next` → … → `finalize_done` (:2971, sole writer of `autodev-passed.txt`). The gate chain this issue extends is NOT on that path today: `rn-remediate.yaml:run_code_gate` (:500, `loop: oracles/code-run-gate` with `issue_id`/`run_dir`/`min_pass_rate`) → `resolve_commands → run_build → run_test → run_typecheck → run_lint → service_health → aggregate` → `subloop_outcome_<ID>.txt` (`GATE_PASS`/`GATE_FAILED`/`GATE_SKIP`). Baseline-capture precedent one level down: `issue_manager.py:1284-1289` records `git rev-parse HEAD` inside `process_issue_inplace` immediately before implementation; autodev.yaml itself contains no `git` invocation.

### Decision Rules

- Closure credit: a `done|completed` ID reaches `autodev-passed.txt` only when `quality/<ID>.json` records `GATE_PASS` or `GATE_SKIP` for the `head_sha` captured at gate time; a `cancelled` ID is promoted on status alone (no gate run); with `quality_gate: false` all closed IDs are promoted on status alone. The cancelled/implemented summary split is ENH-3613's.
- Gate failure never mutates the issue file; it is recorded as `ID  quality_gate_failed` in `autodev-unverified.txt` and counted in both `not_closed` and `quality_failed`.
- The oracle's format stage runs only when `changed_files_path` is passed; it is check-only and never writes to the working tree.
- The gate's verdict vocabulary is already fixed by `code-run-gate`'s `aggregate` state — `GATE_PASS`/`GATE_FAILED`/`GATE_SKIP`, routed via a `classify` evaluator (`GATE_SKIP` routes to `done`, not failure, when no commands are configured). A format stage joins that matrix; it does not introduce a new vocabulary.
- `code-run-gate` exposes no format parameter today (`oracles/code-run-gate.yaml:52-103`); any added stage must leave the oracle's existing callers (`rn-remediate.yaml:500`, `rn-refine.yaml:480`, `rn-implement.yaml` transitively, tests) behaviorally unchanged unless they opt in.

## Acceptance Criteria

- [ ] The autodev gate (extended `oracles/code-run-gate`) is the owner of the post-implement quality verdict
- [ ] Closure credit for `done|completed` requires a recorded `GATE_PASS`/`GATE_SKIP` evidence record for the commit the implementation produced; `cancelled` closures skip the gate
- [ ] The format stage is check-only and runs only on the changed files (deleted files dropped, extension filter applied)
- [ ] The gate passes `min_pass_rate: 1.0`
- [ ] Gate failure lands in `not_closed` and a `quality_failed` summary key; the issue file is not modified
- [ ] Existing `code-run-gate` callers (`rn-remediate`, `rn-refine`, `rn-implement`) are unchanged (format stage SKIPs without `changed_files_path`)
- [ ] `quality_gate: false` restores status-only closure credit

_Moved out 2026-09-26:_ the verbatim-commands criterion is now ENH-3612's; the cancelled/implemented summary split is now ENH-3613's.

## Scope Boundaries

- Blocks only ENH-3600, which rewrites the same `finalize_done` / closure accounting. It
  no longer blocks the preparation-routing migrations (ENH-3599, ENH-3601). This issue is
  a closure feature, not a preparation fix, and those migrations do not touch
  `implement_current`, `verify_impl_closed` or `finalize_done`.
- The `summary.json` cancelled/implemented split moved to ENH-3613 (blocks this issue and
  ENH-3600). This issue adds only `quality_failed` to that shape.
- Out of scope (follow-ups): automatic repair/retest after `GATE_FAILED`; an autodev-only
  opt-out so manage-issue Phase 4 skips the full suite when the gate owns it; baseline
  (pre-existing failure) comparison instead of absolute pass/fail.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-26_

**Readiness Score**: 75/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 71/100 → MODERATE

### Gaps to Address
- Unresolved `blocked_by`: ENH-3613 (open). Its `summary.json` key shape is required by Step 6 (`quality_failed` reason-line filter). Land ENH-3613 first, or remove the dependency if no longer applicable. Without the override the aggregate would be PROCEED WITH CAUTION; all other gates (Program Design, parity, claims, decision, structure, learning tests) are clean.

### Outcome Risk Factors
- broad enumeration across ~8 source/config sites plus ~6 docs and frozen test sets (9-state oracle freeze, MR11 allowlist, interpolation baseline, autodev state-count pin); all need same-commit updates.
- moderate per-site complexity: `finalize_done` promotion rule, new gate states, and oracle opt-in parameter touch shared closure accounting.
- open measurement: `test_cmd` wall-clock vs the `run_test` 600s timeout must be measured before wiring (Step 2).

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-26_

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Substantive claims verified: autodev anchors (`implement_current` :1154, `verify_impl_closed` :1197, `finalize_done` :3041), 107 autodev states, `format_cmd` in schema :45 / `ProjectConfig` :220/:244/:770, no `format_check_*` keys or quality-gate states exist yet, ENH-3612/ENH-3613 open, `resolve_base_ref` / `verify_issue_completed` / `_detect_meaningful_changes` signatures and lines.
- Test line anchors had drifted and were corrected: state-set freeze :633→:661, oracle chain tests :15117→:15174 / :15428→:15485, `:default=` tripwire :578→:598, `TestInterpSweepBaseline` :20963→:21020 (allowlist assert :21313), inflight-clearing test :18306→:18363, `TestRunCodeGate` :2015→:2019, `check_passed` test :7459→:7465, `_run_finalize_done` :7475→:7481, `rn-refine` `verify_leaf` :491→:480.
- Advisory: Program Design cites `implement_current` :1106 / `verify_impl_closed` :1149 / `finalize_done` :2971 and `ProjectConfig.format_cmd` :210 (pre-drift); current values are :1154 / :1197 / :3041 / :220 (see Integration Map).
- `ll-verify-evidence`: clean. Decisions log: no required rules. Graph: provider=`codegraph` freshness=`fresh` (not needed for any verdict).

## Session Log
- `/ll:confidence-check` - 2026-09-26T05:49:01 - `5966980a-c2ea-49c8-a21f-97ae3fab2cc8.jsonl`
- `/ll:verify-issues` - 2026-09-26T05:13:24 - `d2d5d28e-c902-43ff-bf33-1a7825d2f036.jsonl`
- `/ll:confidence-check` - 2026-09-25T21:32:36 - `672e0da1-840e-4b60-a432-7b20e9ebbd01.jsonl`
- `/ll:wire-issue` - 2026-09-25T20:49:53 - `4a475966-a47c-4657-a3e4-16e6706f4c4d.jsonl`
- `/ll:refine-issue` - 2026-09-25T19:53:36 - `52506a27-e6a0-49d9-99b0-9b89990953d8.jsonl`
- `/ll:decide-issue` - 2026-09-25T19:39:02 - `f72e39ee-7f4f-46b8-b438-d29d8550cab9.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:31 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`
