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
---

# FEAT-3573: Autodev code formatting and quality evidence gate before closure credit

## Summary

Autodev closes the loop on implementation with `verify_impl_closed`, which checks issue
status (`done|completed|cancelled`). The lifecycle helper is a frontmatter check. Code
quality rests on `/ll:manage-issue` Phase 4's instruction that configured checks must pass.
That is an agent instruction, not a machine-readable result. Specific gaps:

- Phase 4 never runs `project.format_cmd`.
- Phase 4 examples append arguments to `project.test_cmd` (e.g. a trailing `tests/ -v`),
  which is wrong when the configured command is already complete.
- No structured record of which checks ran and passed against the resulting revision.
- `oracles/code-run-gate` exists but is outside autodev's call graph and has no format stage.
- `cancelled` closures are counted as passed alongside implemented ones in `finalize_done`.

## Current Behavior

Autodev credits closure from frontmatter status alone. `manage-issue` runs checks by instruction, never runs `format_cmd`, and appends arguments to configured commands.

## Expected Behavior

Closure credit requires a recorded passing format/lint/type/test result for the resulting revision, with formatting limited to changed files.

## Motivation

A frontmatter flip to `done` is the only closure evidence autodev consumes. Tamper and work
guards help, but nothing establishes that formatting, lint, types and tests passed on the
final change.

## Proposed Solution

After `implement_current`, run a deterministic quality gate (reuse or extend
`oracles/code-run-gate`, or a shared Python runner) that:

1. Runs formatting **scoped to the files changed by the implementation**. A bare
   `ruff format scripts/` in this repo reformats ~30 unrelated files because main carries
   format drift, so an unscoped format stage would pollute every commit.
2. Runs `lint_cmd`, `type_cmd` and `test_cmd` exactly as configured.
3. Records structured results tied to the resulting commit.
4. Gates `finalize_done`'s passed bucket on that result, with bounded repair/retest.

Avoid running the full suite twice (once in manage-issue, once in the gate). Pick one owner.
Split `cancelled` from `closed` in the summary.

**Option A**: `manage-issue` Phase 4 writes a structured result file that autodev reads.

**Option B**: An autodev gate (extended `oracles/code-run-gate`) runs after `implement_current` and is the only place the suite runs.

> **Selected:** Option B — the gate is deterministic, FSM-native, and sits outside the opaque `ll-auto` subprocess.

### Decision Rationale

**Decision point:** Owner of the quality run

**Selected**: Option B — autodev gate (extended `oracles/code-run-gate`)

**Reasoning**: `implement_current` shells out to `ll-auto`, so autodev cannot observe what manage-issue ran; Option A would need a new file contract across the ll-auto boundary and would trust an agent-written result. Option B is a non-LLM evaluator in the FSM, matches the `rn-implement` usage of `oracles/code-run-gate`, and can be tied to the revision recorded before `implement_current`. Under B, manage-issue Phase 4 must not re-run the full suite, and must still use configured commands verbatim.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A | 1 | 1 | 2 | 1 | 5/12 |
| B | 3 | 2 | 3 | 2 | 10/12 |

**Key evidence**: scoring done from direct inspection (`autodev.yaml` `implement_current` → `ll-auto`; `oracles/code-run-gate.yaml`; `skills/manage-issue/SKILL.md` Phase 4), not parallel agent runs.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `implement_current`, `verify_impl_closed`, `finalize_done`
- `scripts/little_loops/loops/oracles/code-run-gate.yaml`
- `skills/manage-issue/SKILL.md` — Phase 4 verification commands

_Wiring pass added by `/ll:wire-issue`:_
- `.gemini/skills/manage-issue/SKILL.md`, `.kimi-code/skills/manage-issue/SKILL.md`, `.qwen/skills/manage-issue/SKILL.md` (+ each mirror's `templates.md`) — host mirrors carry the same Phase 4 command-append bug (`{{config.project.test_cmd}}` at :355); `test_wiring_skills_and_commands.py` mirror gates enforce regeneration via `ll-adapt --host <host> --apply` [Agent 1 finding]
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
- `scripts/tests/test_builtin_loops.py:633` — `TestPrePatchCheckReachability.test_code_run_gate_state_set_unchanged` freezes the oracle's state set to exact equality (9 states); adding a format *state* trips it, and per its own comment requires re-reading ENH-2997's Scope Boundaries [Agent 1 finding]
- `scripts/tests/test_builtin_loops.py:15117` — `TestCodeRunGateOracle.test_run_states_chain_forward_and_terminate_at_aggregate` and `test_run_states_converging_routing_not_regressed` (:15428) pin the run_* chain edges pairwise; `aggregate`'s sidecar loop (`for f in build.txt test-results.txt typecheck.txt lint.txt health.txt`) must grow the format sidecar [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:578` — `TestCodeRunGateOptionalParams.test_resolve_commands_interpolates_without_cmd_overrides` is the `:default=` tripwire: every new `format_cmd` guard AND assignment RHS needs `:default=` or the GATE_FAILED_INFRA laundering regression returns [Agent 1 finding]
- `scripts/tests/test_builtin_loops.py:20963` — `TestInterpSweepBaseline` and `MR11_MARKER_ALLOWLIST` (:21037, asserted :21249): a new `context.format_cmd` ref in the oracle needs both a baseline entry and an allowlist tuple [Agent 1 finding]
- `scripts/tests/test_bug3269_test_cmd_resolution_gate.py` — `format_cmd` already in `PROJECT_COMMAND_KEYS` (:47); the oracle is a permanent exemption (:58); assertion 2 requires any `${context.format_cmd}` ref in `autodev.yaml` to resolve against a declared `context:`/`parameters:` key [Agent 1 finding]
- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop` promotion/phantom/no-op/mixed-run tests execute `finalize_done` with no quality-evidence artifacts (fixtures must gain them when promotion is gated); `test_implement_current_routes_to_verify_impl_closed` breaks if a gate state is interposed; `TestAutodevAuthGuard.test_autodev_implement_current_failure_chain_clears_inflight` (:18306) requires new states in that region to clear `autodev-inflight` or route only to clearing states [Agent 3 finding]
- `scripts/tests/test_rn_remediate.py` — `TestRunCodeGate` (:2015) pins the existing call-site contract (`run_code_gate.loop`, `with:` bindings, GATE_PASS/GATE_SKIP routing) that must stay behaviorally unchanged; `scripts/tests/test_rn_refine.py:1648` pins `verify_leaf`'s `oracles/code-run-gate` wiring likewise [Agent 1 finding]
- `scripts/tests/test_manage_issue_changelog_gate.py` — asserts a verbatim `GATE_SNIPPET` inside `skills/manage-issue/SKILL.md`; drift-sensitive to any Phase 4 edit [Agent 1 finding]
- `scripts/tests/test_wiring_skills_and_commands.py` — mirror gates plus BUG-2408 substring pins (`foreground-blocking`, `scheduled wakeup`) and the `SPAWN_SITE_INVENTORY` line pin (`skills/manage-issue/SKILL.md`, line 110) — Phase 4 rewording must preserve these or regenerate mirrors [Agent 1 finding]
- `scripts/tests/test_enh494_skill_companions.py` — 500-line cap; `skills/manage-issue/SKILL.md` sits at the cap, so Phase 4 growth requires companion extraction to `templates.md` [Agent 1 finding]

### Documentation
- `docs/guides/` loop guide for autodev, if it documents closure semantics

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/loops.md:874` — full `oracles/code-run-gate` reference (params table :889, stage flow, direct-call example :927) gains the format stage/param [Agent 1 finding]
- `docs/guides/LOOPS_REFERENCE.md:1007` — `Closure accounting` documents `autodev-passed.txt`/`autodev-skipped.txt` as auto-refine's sources; `:1079` documents `finalize_done`'s bucket list — the cancelled/implemented split edits both [Agent 2 finding]
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md:253` — `GATE_FAILED` outcome-token row enumerates "build / test / typecheck / lint / health"; format joins the enumeration [Agent 2 finding]
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:692` — declares `oracles/code-run-gate.yaml` a permanent exemption for command resolution; the format stage's `format_cmd` resolution follows the same exemption [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:305` — `format_cmd` entry gains its first runtime reader [Agent 2 finding]

### Configuration
- `project.format_cmd`, `lint_cmd`, `type_cmd`, `test_cmd`

### Changed-file scoping

`implement_current` shells out to `ll-auto`, so autodev cannot see which files the
implementation touched. Record the base revision (`git rev-parse HEAD`) into the run dir
**before** `implement_current`, and compute the changed-file set as
`git diff --name-only <base>..HEAD` (plus any uncommitted changes) after it. The format
stage runs only on that set.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- `skills/manage-issue/SKILL.md` Phase 4 confirmed as described: lines 354-372 append `tests/ -v` to `{{config.project.test_cmd}}` and `{{config.project.src_dir}}` to the lint/type commands, run `build_cmd`/`run_cmd` bare, and the skill directory contains zero occurrences of `format_cmd` — formatting is never run by manage-issue. The "Headless-Safe Final Test Run" subsection (:376) mandates the scratch-redirect foreground suite run.
- `oracles/code-run-gate.yaml` current surface: params `run_dir`, `issue_id`, `min_pass_rate` (default 0.95), `health_bound_seconds`, plus optional `build_cmd`/`test_cmd`/`typecheck_cmd`/`lint_cmd`/`run_cmd`/`health_url` overrides (:52-103). Stages `resolve_commands → run_build → run_test → run_typecheck → run_lint → service_health → aggregate`; every stage failure still advances (no MR-4 partial-route dead-end). No format stage or format param exists.
- Command-resolution convention inside the oracle: `resolve_commands` reads `.ll/ll-config.json` `project.*` with alias handling (`typecheck_cmd`/`type_cmd`, `start_cmd`/`run_cmd`, ARCHITECTURE-123) and honors caller overrides via `${context.<cmd>:default=}`; other loops use `ll-config get project.test_cmd`, which also honors `.ll/ll.local.md`.
- Baseline→changed-files precedent exists one level down the call chain: `issue_manager.py:1284-1289` (`process_issue_inplace`) captures `git rev-parse HEAD` immediately before implementation, consumed by `work_verification.py:470` (`_detect_meaningful_changes`) as `git diff --name-only <baseline>..HEAD` plus staged/unstaged diffs (:428, :445). `prepatch_check.py:248` (`resolve_base_ref`) is the public base-ref resolver with merge-base fallback. autodev.yaml contains no `git` invocation today, so the base revision must be recorded loop-side as the Changed-file scoping note plans.
- Load-bearing invariant: `test_builtin_loops.py:7459` (`test_check_passed_stages_instead_of_passes`) asserts `finalize_done` is the only state allowed to populate `autodev-passed.txt` (the `check_passed` state must stage, not pass). Whatever gates closure credit must route promotion through `finalize_done`, or amend that test's contract knowingly.
- `verify_issue_completed` (`issue_lifecycle.py:768`) is not in autodev's call chain — its only production callers are in `issue_manager.py` (:1469, :1560, :2220), i.e. the `ll-auto`/manage-issue path. The Dependent Files entry covers that path only; autodev re-implements the status check in shell.
- Existing closure-state tests and their harness: `test_builtin_loops.py` `TestAutodevLoop` (:6643) — `_run_finalize_done` (:7475) executes the state's action under `bash -c` after `${context.run_dir}` substitution and `$${`→`${` un-escaping; tests pin phantom-on-unclosed (:7485), verified promotion (:7518), no-op (:7544), rate-limit routing through finalize (:7553-:7574), BUG-3390 dedupe (:7886), and `verify_impl_closed` routing (:7827-:7871). The 11-key `summary.json` set (`verdict`, `closed`, `not_closed`, `skipped`, `gate_blocked`, `decision_unresolved`, `not_started`, `inflight_unresolved`, `abandoned`, `stop_reason`, `pending`) is load-bearing for these tests and is the shape the cancelled/implemented split extends.
- No doc under `docs/` documents autodev's closure buckets or `summary.json` keys today; the only adjacent passage is `docs/guides/RECURSIVE_LOOPS_GUIDE.md` §PHASE1_NOT_STARTED (:287-304, `not_started` verdict semantics).

## Open Questions

- **Owner of the quality run** ✅ **RESOLVED** (2026-09-25 by /ll:decide-issue): (b) an
  autodev gate (extended `oracles/code-run-gate`) that runs after `implement_current` and
  is the only place the suite runs. The full suite runs once per issue.

## Implementation Steps

1. ~~Decide the single owner of the post-implementation quality run~~ — decided: autodev gate (Option B)
2. Extend `oracles/code-run-gate` (or a shared runner) with a changed-files format stage, scoped from the base revision recorded before `implement_current`
3. Persist structured results per revision; gate `finalize_done` promotion on them
4. Fix manage-issue Phase 4 to use configured commands verbatim
5. Split cancelled from implemented closures in `summary.json`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `aggregate` in `oracles/code-run-gate.yaml` — add the format sidecar to its file list and keep the `SKIP <cmd>=null` first-line convention so `classify` routing survives
- Handle `TestPrePatchCheckReachability` — a new oracle *state* trips the frozen 9-state exact-set equality; either extend the freeze knowingly (its comment requires re-reading ENH-2997's Scope Boundaries) or add format as a stage of an existing state
- Route gate-failed closures through the parent — `auto-refine-and-implement.yaml` `finalize` must count them (new ledger or summary key) or they vanish from `closed`/`not_closed`
- Add baseline + MR11 allowlist entries for the oracle's new `context.format_cmd` refs; keep `:default=` on both guard and RHS in `resolve_commands`
- Update `docs/reference/loops.md`, `docs/guides/LOOPS_REFERENCE.md` (:1007, :1079), `docs/guides/RECURSIVE_LOOPS_GUIDE.md:253`, and `scripts/little_loops/loops/README.md:194` for the format stage
- Regenerate `skills/manage-issue` mirrors — `ll-adapt --host gemini|kimi-code|qwen --apply` after the Phase 4 fix; keep the BUG-2408 substrings and the `SPAWN_SITE_INVENTORY` line pin; extract to `templates.md` if the 500-line cap is crossed
- Update `test_builtin_loops.py` finalize fixtures with quality-evidence artifacts when promotion is gated, and keep new autodev states inside the `autodev-inflight`-clearing chain (`test_autodev_implement_current_failure_chain_clears_inflight`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Constraint: the gate must remain a non-LLM evaluator in the FSM — `code-run-gate` is all-shell with `exit_code`/`output_numeric`/`classify` evaluators, so extending it keeps the autodev meta-loop MR-2-compliant; a shared Python runner preserves the same property only if the FSM routes on its exit code, not on model output.
- Constraint: the format stage consumes `project.format_cmd`, which today has no runtime reader (`config/core.py:210`; serialized at `:770` only) — there is no existing format-invocation helper to reuse, but the scoping primitives exist (`work_verification.py` diff computations, `filter_excluded_files` :32).
- Constraint: adding states to `autodev.yaml` bumps the state count pinned by `test_fsm_topology.py` `TestAutodevSmoke.test_autodev_topology` (currently 105 states) and must keep the `loop_interpolation_baseline.json` `finalize_done` entry valid.
- Verification surface: `python -m pytest scripts/tests/test_builtin_loops.py -k "finalize or verify_impl"` exercises the closure states today; `ll-loop validate` plus `scripts/tests/test_builtin_loops.py` gate classes `TestCodeRunGateOracle` (:14959) / `TestCodeRunGateOracleWiring` (:18851) / `TestCodeRunGateOptionalParams` (:578) cover the oracle side.

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

- Closure credit: an ID reaches `autodev-passed.txt` only when frontmatter reads `done|completed|cancelled` AND a recorded passing quality result exists for the resulting revision; `cancelled` closures are counted in a separate summary bucket from implemented ones.
- The gate's verdict vocabulary is already fixed by `code-run-gate`'s `aggregate` state — `GATE_PASS`/`GATE_FAILED`/`GATE_SKIP`, routed via a `classify` evaluator (`GATE_SKIP` routes to `done`, not failure, when no commands are configured). A format stage joins that matrix; it does not introduce a new vocabulary.
- `code-run-gate` exposes no format parameter today (`oracles/code-run-gate.yaml:52-103`); any added stage must leave the oracle's existing callers (`rn-remediate.yaml:500`, `rn-refine.yaml:491`, `rn-implement.yaml` transitively, tests) behaviorally unchanged unless they opt in.

## Acceptance Criteria

- [ ] Closure credit requires a recorded passing quality result for the resulting revision
- [ ] Formatting runs only on changed files
- [ ] `manage-issue` uses configured commands verbatim
- [ ] `summary.json` distinguishes cancelled from implemented closures

## Scope Boundaries

- Blocks only ENH-3600, which rewrites the same `finalize_done` / closure accounting. It
  no longer blocks the preparation-routing migrations (ENH-3599, ENH-3601). This issue is
  a closure feature, not a preparation fix, and those migrations do not touch
  `implement_current`, `verify_impl_closed` or `finalize_done`.
- The `summary.json` cancelled/implemented split made here is the shape that ENH-3600
  preserves.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-09-25T20:49:53 - `4a475966-a47c-4657-a3e4-16e6706f4c4d.jsonl`
- `/ll:refine-issue` - 2026-09-25T19:53:36 - `52506a27-e6a0-49d9-99b0-9b89990953d8.jsonl`
- `/ll:decide-issue` - 2026-09-25T19:39:02 - `f72e39ee-7f4f-46b8-b438-d29d8550cab9.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:31 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`
