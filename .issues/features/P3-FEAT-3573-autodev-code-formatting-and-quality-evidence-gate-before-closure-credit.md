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
- ENH-3600
blocked_by: []
relates_to:
- ENH-3612
confidence_score: 95
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
`summary.json` cancelled/implemented split is now **ENH-3613** (landed 2026-09-26; its
`closed_implemented`/`closed_cancelled` keys are in `finalize_done`). This issue is only
the autodev quality gate.

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

These close the gaps a pre-implementation review found. They are directive. A second
review the same day (after ENH-3609 landed) added: verdict-from-route, killed-stage
failure, prepatch-check interaction, `quality_gate_infra`, dirty-tree rule, the
`Quality-failed` summary line, parent accounting, `commands.json` quoting, and the
timeout-parameter correction.

- **Format stage is check-only, and it uses a new key.** `format_cmd` changes files and
  carries its own path argument (`ruff format scripts/`), so it cannot be scoped by
  adding files. Add a new, unset-by-default config key `project.format_check_cmd` with a `{files}`
  placeholder, for example `ruff format --check --force-exclude {files}`
  (`--force-exclude` makes ruff honor its excludes for explicitly passed paths). The
  oracle replaces `{files}` with the shell-quoted changed-file list, read directly from
  `changed_files_path` — the file list never goes through `commands.json` (see
  *commands.json quoting* below). When the key is unset, the stage writes
  `SKIP format_check_cmd=null`. `format_cmd` stays unread at runtime.
- **Changed-file set.** `git diff --name-only --diff-filter=d <base>..<head>`, plus
  uncommitted tracked changes (`git diff --name-only --diff-filter=d HEAD`), plus
  untracked files (`git ls-files --others --exclude-standard`; plain `git diff` omits
  them). This drops deleted files. **Subtract the pre-existing dirty set** (see *Base
  revision*): tracked-dirty and untracked paths that existed before `ll-auto` ran are
  the operator's WIP, not the deliverable, and must not be format-checked or mark the
  record dirty. This mirrors BUG-2963's `snapshot_dirty_paths`
  (`git_operations.py`), which exists for exactly this problem on the `ll-auto` close
  path. Known limit, accepted for v1: a file that was already dirty *and* is touched by
  the implementation is excluded from the format stage (it is still covered by lint/test);
  a committed change to it is still included via `<base>..<head>`. Then filter by the unset-by-default
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
  `${context.run_dir}/quality/<ID>.base` before it runs `ll-auto`, and in the same step
  writes the pre-existing dirty set (`git diff --name-only HEAD` plus
  `git ls-files --others --exclude-standard`) to `${context.run_dir}/quality/<ID>.base-dirty`.
  These are lines added to the existing action, not a new state, so the routing into
  `implement_current` does not change. The snapshot must be taken **before** `ll-auto`:
  a later snapshot already contains the deliverable (BUG-2963 anchor warning). `ll-auto` also stamps a dequeue `base_sha` per issue in the history DB
  (`issue_manager.py:780`, read by `read_base_sha` at `history_reader/runs.py:181`);
  the two should agree. `record_quality_evidence` records both when they differ, but the
  `.base` file is authoritative (it needs no DB and survives a missing stamp).
- **Placement.** `verify_impl_closed.on_yes` → `route_quality_gate` → `run_quality_gate`
  (`loop: oracles/code-run-gate`) → per-route marker state → `record_quality_evidence` →
  `dequeue_next`.
  - `route_quality_gate` sends `cancelled` closures straight to `dequeue_next`, because
    nothing was implemented. Every other closure goes to `run_quality_gate`, after the
    state computes the changed-file set.
  - `run_quality_gate` routes `on_success` → `mark_quality_pass`, `on_failure` →
    `mark_quality_fail`, `on_error` → `mark_quality_infra`. Each marker writes its route
    (`pass|fail|infra`) to `${context.run_dir}/quality/<ID>.route` and chains to
    `record_quality_evidence`. **The verdict comes from the sub-loop route, never from
    the oracle's `subloop_outcome_<ID>.txt`.** `resolve_commands` pre-writes `GATE_PASS`
    into that file (`code-run-gate.yaml:196`), and any path that reaches the oracle's
    `failed` terminal without running `aggregate` (see *Prepatch check* below) leaves the
    placeholder in place. (The implementer may fold the three markers into one fragment;
    the contract is "verdict from route".)
  - `verify_impl_closed` has already cleared `autodev-inflight`, so the new states sit
    outside the inflight-clearing chain.
  - `implement_current.on_yes → verify_impl_closed` stays as it is.
- **Oracle parameters from autodev.** Pass `min_pass_rate: 1.0`. This is
  belt-and-braces, not load-bearing: `aggregate` already fails on any non-zero test exit
  (`code-run-gate.yaml:442`), and `pass_rate` only departs from the exit code when a
  `pytest.json` exists in the oracle run dir, which the configured `test_cmd` never
  writes. Pass `test_cmd`, `lint_cmd`, `typecheck_cmd` and `format_check_cmd`, all
  resolved with `ll-config get` (honors `.ll/ll.local.md`; `ll-config get project.type_cmd`
  works today). The oracle's own `resolve_commands` reads only `.ll/ll-config.json`.
  Also pass `issue_id`, `run_dir: ${context.run_dir}/quality/<ID>/` and
  `changed_files_path`.
- **commands.json quoting.** `resolve_commands` builds `commands.json` with an unescaped
  heredoc (`code-run-gate.yaml:190-192`). A command containing `"` produces invalid JSON,
  each `run_*` state's `json.load` fails, the command reads as empty, and the stage
  SKIPs silently. Caller overrides are also interpolated into a double-quoted shell
  string (:172-187), so `"`, `$` or backticks in a command break the same way. v1
  keeps the changed-file list out of this path (read from `changed_files_path`), and
  `run_format_check` writes its SKIP/exit sidecar like the others. Rewriting
  `commands.json` via `json.dumps` is recommended in the same change if cheap; otherwise
  document the no-`"` constraint in `CONFIGURATION.md` next to `format_check_cmd`.
- **Killed stage is a failure, not a pass.** Every `run_*` state appends `exit_code=N`
  only after its command returns (e.g. `run_test` :264-281). When the FSM kills a state
  at its `timeout:` (or an xdist controller wedges until the timeout), the sidecar holds
  partial output with no `exit_code=` line, and `aggregate` (:434-464) — which fails
  only on `^exit_code=[1-9]` — returns `GATE_PASS`. Fix in `aggregate`: a sidecar whose
  first line is not `SKIP` and that has no `exit_code=` line sets `ANY_FAIL=true`. This
  changes behavior for existing callers only in the killed-stage case, where the current
  result is a latent false pass; that change is intended. `record_quality_evidence`
  reports such a stage as `killed`. Related hole: `aggregate` skips a missing sidecar
  (`[ -f "$f" ] || continue`), so a stage killed before its `>` redirect creates the
  file is invisible. Also fail when `commands.json` has a non-empty command for a stage
  but its sidecar is absent (`run_format_check` keys off `changed_files_path` instead:
  path passed + `format_check_cmd` set + non-empty filtered set ⇒ sidecar required).
  `record_quality_evidence` reports that stage as `absent`.
- **Prepatch check now fires on the implementation diff.** `run_test` carries
  `prepatch_check: fail`. Because the gate passes `issue_id`, the executor reads
  `ll-auto`'s dequeue `base_sha` stamp, computes the implementation diff, and re-runs new
  or modified tests in a worktree at the base (`executor.py:1960-2003`). If a new test
  also passes on the base (`flagged`), the executor routes the oracle straight to its
  `failed` terminal (`executor.py:2047-2053`), skipping typecheck, lint and `aggregate`.
  Accepted for v1: a closure whose new tests prove nothing does not earn credit. The
  route is `fail`, so it lands as `quality_gate_failed`; `record_quality_evidence`
  reads `quality/<ID>/prepatch_evidence_<ID>.json` when present and records
  `prepatch: flagged|clean|skipped` so the operator can tell this cause from a red suite.
- **Evidence record.** `record_quality_evidence` writes `${context.run_dir}/quality/<ID>.json`
  with these fields: `issue_id`, `base_sha`, `history_base_sha` (only when it differs),
  `head_sha`, `dirty`, `changed_files`, a per-stage outcome (`format_check`, `lint`,
  `typecheck`, `test`, each `pass|fail|skip|killed|absent`), `prepatch`
  (`flagged|clean|skipped|absent`), `route` (`pass|fail|infra`) and `verdict`
  (`GATE_PASS|GATE_FAILED|GATE_SKIP|GATE_INFRA`). The verdict is derived from `route`
  (`fail` → `GATE_FAILED`, `infra` → `GATE_INFRA`; `pass` → `GATE_SKIP` when every stage
  is `skip`, else `GATE_PASS`). Stage outcomes are informational. `head_sha` is recorded
  at gate time. `finalize_done` must not compare against the live HEAD, because later
  queue items move it.
- **Dirty tree.** If tracked or untracked changes remain after `ll-auto`, the gate tested
  the working tree, not `head_sha`. `dirty` is computed on the gate-time dirty set
  **minus** `quality/<ID>.base-dirty`, so pre-existing operator WIP never sets it. v1 rule: a dirty tree does not block credit (the
  uncommitted files are in the changed set and were checked), but the record carries
  `dirty: true` and the summary line appends `(dirty)` for that ID. Uncommitted leftovers
  after manage-issue Phase 5 are a separate defect and must not be hidden.
- **Failure path (no repair in v1).** On `GATE_FAILED`, do not change the issue: it stays
  `done` and committed. Append `ID  quality_gate_failed` to `autodev-unverified.txt`,
  using the reasoned-line idiom from BUG-3390. On `GATE_INFRA` (sub-loop `on_error`:
  oracle crash or context-resolution failure, mirroring `rn-remediate`
  `record_gate_error`), append `ID  quality_gate_infra` instead. Both count in
  `not_closed` and go through the existing verdict ladder (partial or phantom).
  `summary.json` gains `quality_failed` (count of `quality_gate_failed` lines) and
  `quality_gate_infra` (count of `quality_gate_infra` lines). That is the same filter
  idiom as `notstarted_`, built on ENH-3613's key shape (landed). Automatic
  repair/retest is a follow-up, not part of this issue.
- **Summary line and rerun behavior.** A quality-failed issue stays `done`, so a later
  autodev run skips it at pre-flight as `already_done` — rerunning will **not** re-gate
  it. The generic `Unverified` hint ("re-queue to retry", `autodev.yaml:3274`) is wrong
  for these IDs. `finalize_done` excludes `quality_gate_*` lines from the `Unverified`
  display list (they still count in `UNVERIFIED_COUNT` / `not_closed`) and prints
  `Quality-failed (N): ID@<short head_sha>[ (dirty)], ...  (marked done but gate failed —
  review these commits; rerun will not re-gate)` and, when non-zero,
  `Quality-gate-infra [infra] (N): ...  (gate crashed — re-run the oracle manually)`.
- **Parent accounting (`auto-refine-and-implement.yaml` `finalize`).** The parent builds
  `CLOSED` from on-disk status diffs (:1027-1029) and `NOT_CLOSED` as
  `autodev-passed − closed-now-union` (:1088-1095). A quality-failed issue is `done` on
  disk and absent from `autodev-passed.txt`, so today it would count as **CLOSED** and
  the parent could report success. Required edit: read `ID  quality_gate_(failed|infra)`
  lines from `$RUN_DIR/autodev-unverified.txt`, remove those IDs from
  `$P-closed-union.txt` before counting `CLOSED`, add them to `NOT_CLOSED`, and emit a
  `quality_failed` key in the parent `summary.json`. The parent verdict then follows its
  existing `NOT_CLOSED > 0` branch (:1245).
- **Promotion rule.** In `finalize_done`, a `done|completed` ID is promoted only if
  `quality/<ID>.json` exists with verdict `GATE_PASS` or `GATE_SKIP`. A `cancelled` ID is
  promoted on status alone. A `done` ID with no evidence record goes to
  `autodev-unverified.txt` as `quality_evidence_missing`.
- **Escape hatch.** Add an autodev context key `quality_gate`, default `true`. With
  `false`, closure credit falls back to the old status-only check. Use it for repos
  whose base branch is red: in v1 the gate judges absolute pass/fail, so failures that
  already exist on the base fail every issue in the queue. The run summary prints a
  one-line hint when every gated issue fails. This is a live risk in this repo: recent
  full-suite runs on `main` show 1 and 12 failures (`.loops/tmp/scratch/` logs,
  2026-09-26), so with the gate on, a single red or flaky test fails every issue in the
  run. v1 keeps absolute pass/fail; baseline comparison stays a follow-up (Scope
  Boundaries), and the hint must name `quality_gate: false` as the workaround.
  **Parent forwarding:** `auto-refine-and-implement.yaml`'s `delegate` state forwards only
  `input` and `skip_learning_gate` to autodev via `with:`, so without a change the
  escape hatch is unreachable under the parent. Add a parent `quality_gate` context key
  (default `true`) and forward it in the same `with:` block, following the
  `skip_learning_gate` precedent (parent `context:` declaration + `with:` binding).
  **Default-on reach:** every local-editable consumer picks up `quality_gate: true` on
  its next autodev run with no reinstall, gaining a full-suite run per issue; call this
  out in the release CHANGELOG entry together with the `quality_gate: false` workaround.
- **No-diff closures.** An issue that `ll-auto`'s Phase 1 closes as already implemented
  (status `done`, no source change beyond `.issues/`) still goes through
  `verify_impl_closed.on_yes` and runs the full gate. v1 applies the absolute rule
  unchanged: on a red base it lands as `quality_gate_failed`. The changed set is then
  `.issues/` files only, so the format stage SKIPs under an extension filter.
- **Worktree runs (EPIC scope).** For EPIC scope, the parent runs autodev in a scratch
  worktree (`delegate`'s `worktree:`). Under an editable install (this repo, and every
  local-editable consumer), `python -m pytest` in that worktree imports the main
  checkout's package, so the branch's new tests run against main's code: every issue
  that adds source + tests fails the gate (or a regression passes). The oracle must
  prepend the worktree's `project.src_dir` to `PYTHONPATH` for `run_test` /
  `run_typecheck` when its cwd is not the main worktree, reusing the rule in
  `verify_epic_branch_before_merge` (`worktree_utils.py`, BUG-2629) rather than a new
  one. Gate the injection on a new optional caller parameter (e.g. `src_dir`, which
  autodev passes from `ll-config get project.src_dir`) so existing callers are
  unchanged.
- **Suite ownership.** v1 accepts that the suite runs twice: manage-issue Phase 4 still
  runs it, and the gate runs it again. Phase 4 is the only verification on the
  `ll-auto`, `ll-parallel` and `ll-sprint` paths, and the implementing agent needs test
  feedback, so removing it would regress those paths. An autodev-only opt-out (an env
  flag that tells Phase 4 to run only targeted tests) is a follow-up.
- **Timeouts.** `run_test` has `timeout: 600` and the oracle has `timeout: 1800`.
  Measured 2026-09-26: this repo's full suite takes 250–355s (42–59% of 600s), under the
  80% threshold, so no timeout change in v1. Still measure the `prepatch_check` worktree
  fork on a real run. A caller-set `test_timeout_seconds` parameter is **not possible**:
  state `timeout:` is `int | None` (`fsm/schema.py:718`) and is not interpolated. If the
  budget is ever exceeded, raise `run_test`'s literal timeout (harmless for existing
  callers whose suites finish sooner) or add an in-action timeout (no GNU `timeout` on
  macOS; use a `python3 -c` subprocess wrapper). The *Killed stage* rule above makes a
  timeout fail rather than pass either way.
  **Oracle budget:** the stage timeouts already sum to 1650s (resolve 60 + build 300 +
  test 600 + typecheck 300 + lint 300 + health 60 + aggregate 30) against the oracle's
  1800s loop timeout. A new stage at the usual 300s would make 1950s, so the loop
  timeout could fire before any stage timeout. Give `run_format_check` a literal
  `timeout: 120` (a check-only format pass over the changed files is seconds) and keep
  the sum under 1800s.
  **Oracle-level timeout / signal routing:** a `loop:` state whose child ends with
  `terminated_by` = `timeout` / `signal` / `interrupted` / `max_steps` routes
  `on_failure` (compiled `on_no → on_failure` fallback, see the BUG-2611 note in
  `auto-refine-and-implement.yaml` `delegate`), so it would land as `quality_gate_failed`.
  That misreports infra as a quality verdict. `mark_quality_fail` must read
  `${captured.run_quality_gate.terminated_by}` (the ENH-3366 `delegate_failed`
  precedent, which reads `${captured.delegate.terminated_by}`) and write route `infra`
  for those classes; only `terminated_by == "terminal"` (the oracle reached its own
  `failed` terminal) is route `fail`.

**Option A**: `manage-issue` Phase 4 writes a structured result file that autodev reads.

**Option B**: An autodev gate (extended `oracles/code-run-gate`) runs after `implement_current` and is the only source of the closure-credit verdict. (manage-issue Phase 4 still runs the suite in v1; see Suite ownership.)

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
_Autodev states are cited by name only; their line numbers drift with every autodev edit (BUG-3614's uncommitted change adds ~26 lines above `implement_current`)._

- `scripts/little_loops/loops/autodev.yaml` — `implement_current` (base-rev + base-dirty snapshot lines), `verify_impl_closed` (`on_yes` retarget), new `route_quality_gate` / `run_quality_gate` / `mark_quality_pass|fail|infra` (`mark_quality_fail` reads `terminated_by`) / `record_quality_evidence`, `finalize_done` (promotion rule, `quality_failed` + `quality_gate_infra` keys, `Quality-failed` summary line, `Unverified` display exclusion), `quality_gate` context default (context today holds only `skip_learning_gate`)
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — new `format_check_cmd` / `changed_files_path` / `src_dir` params, new `run_format_check` state (`timeout: 120`), `PYTHONPATH` prepend in `run_test` / `run_typecheck` when `src_dir` is passed and cwd is a linked worktree, `aggregate` sidecar list + killed-stage (missing `exit_code=`) and configured-but-absent-sidecar → fail rules; optionally `commands.json` via `json.dumps`
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `finalize` (:1027-1095): subtract `quality_gate_*` IDs from `CLOSED`, add to `NOT_CLOSED`, emit `quality_failed` (see Design Decisions → Parent accounting); `context:` gains `quality_gate` and `delegate`'s `with:` forwards it (see Design Decisions → Escape hatch)
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
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `finalize` derives `NOT_CLOSED`/`SKIPPED`/`GATE_BLOCKED`/`DECISION_UNRESOLVED` from `autodev-passed.txt`/`autodev-skipped.txt`/`autodev-gate-blocked.txt`/`autodev-decision-unresolved.txt`/`autodev-inflight`/`autodev-queue.txt` in the shared run_dir (reads :1058-:1112); under the new gate, a frontmatter-closed issue that fails quality evidence stays out of `autodev-passed.txt`. _Corrected 2026-09-26:_ it does not disappear — `CLOSED` comes from on-disk status diffs (:1027-1029), so it is counted as **closed**. Now a Files to Modify entry [Agent 1+2 finding]
- `scripts/little_loops/parallel/worker_pool.py` — imports `verify_work_was_done` in `_verify_work_was_done` (:43, :1380); the ll-parallel/ll-sprint quality-evidence consumer — consistency overlap, no autodev-path edit [Agent 1 finding]
- `scripts/little_loops/fsm/persistence.py` (`archive_run` copies the run dir's `summary.json`, :660), `scripts/little_loops/cli/loop/audit.py` (:194), `scripts/little_loops/cli/loop/evidence.py` (:214, :314), `scripts/little_loops/hooks/pre_compact_handoff.py` (:126-:130) — shape-agnostic summary.json consumers (copy/hash/passthrough, no key reads); additive cancelled/implemented keys are safe for all four [Agent 1 finding]

### Similar Patterns
- `rn-implement.yaml` usage of `oracles/code-run-gate`

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop` finalize tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:661` — `TestPrePatchCheckReachability.test_code_run_gate_state_set_unchanged` freezes the oracle's state set to exact equality (9 states); adding a format *state* trips it, and per its own comment requires re-reading ENH-2997's Scope Boundaries [Agent 1 finding]
- `scripts/tests/test_builtin_loops.py:15174` — `TestCodeRunGateOracle.test_run_states_chain_forward_and_terminate_at_aggregate` and `test_run_states_converging_routing_not_regressed` (:15485) pin the run_* chain edges pairwise; `aggregate`'s sidecar loop (`for f in build.txt test-results.txt typecheck.txt lint.txt health.txt`) must grow the format sidecar [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:598` — `TestCodeRunGateOptionalParams.test_resolve_commands_interpolates_without_cmd_overrides` is the `:default=` tripwire: every new `format_check_cmd` / `changed_files_path` guard AND assignment RHS needs `:default=` or the GATE_FAILED_INFRA laundering regression returns [Agent 1 finding]
- `scripts/tests/test_builtin_loops.py:21020` — `TestInterpSweepBaseline` and `MR11_MARKER_ALLOWLIST` (asserted :21313): new `context.format_check_cmd` / `context.changed_files_path` refs in the oracle, and new `captured.input.output` refs in the autodev gate states, need baseline entries and allowlist tuples (or `ll-lint: mr11-ok(...)` markers per the existing ENH-3358 idiom) [Agent 1 finding]
- `scripts/tests/test_bug3269_test_cmd_resolution_gate.py` — `format_cmd` already in `PROJECT_COMMAND_KEYS` (:47); the oracle is a permanent exemption (:58); assertion 2 requires any `${context.format_check_cmd}` ref in `autodev.yaml` to resolve against a declared `context:`/`parameters:` key [Agent 1 finding]
- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop` promotion/phantom/no-op/mixed-run tests execute `finalize_done` with no quality-evidence artifacts (fixtures must gain them when promotion is gated); `test_implement_current_routes_to_verify_impl_closed` breaks if a gate state is interposed; `TestAutodevAuthGuard.test_autodev_implement_current_failure_chain_clears_inflight` (:18363) requires new states in that region to clear `autodev-inflight` or route only to clearing states [Agent 3 finding]
- `scripts/tests/test_rn_remediate.py` — `TestRunCodeGate` (:2019) pins the existing call-site contract (`run_code_gate.loop`, `with:` bindings, GATE_PASS/GATE_SKIP routing) that must stay behaviorally unchanged; `scripts/tests/test_rn_refine.py:1648` pins `verify_leaf`'s `oracles/code-run-gate` wiring likewise [Agent 1 finding]
- ~~`test_manage_issue_changelog_gate.py`, `test_wiring_skills_and_commands.py`, `test_enh494_skill_companions.py`~~ → manage-issue Phase 4 work moved to ENH-3612
- `scripts/tests/test_builtin_loops.py:15047` — `TestCodeRunGateOracle` parameter test pins "run_dir, issue_id + the six command fields"; new params extend it
- `scripts/tests/test_bug3269_test_cmd_resolution_gate.py:47` — `PROJECT_COMMAND_KEYS` gains `format_check_cmd` (autodev resolves it via `ll-config get`)
- `scripts/tests/test_fsm_topology.py` `TestAutodevSmoke.test_autodev_topology` — pinned state count (autodev has **110** states after ENH-3609 landed 2026-09-26; +6 new states if the three markers stay separate, +4 if folded)
- `auto-refine-and-implement` `finalize` tests pinning its `summary.json` key set — gain `quality_failed`
- `scripts/tests/test_builtin_loops.py` — parent `delegate` `with:` binding tests gain `quality_gate`
- New tests (added 2026-09-26 review): a file dirty or untracked before `implement_current` is excluded from the changed set and does not set `dirty`; a child `terminated_by` of `timeout`/`signal` routes `mark_quality_fail` to route `infra`; `aggregate` fails when `commands.json` names a command but its sidecar is absent; `run_test` prepends `src_dir` to `PYTHONPATH` only when `src_dir` is passed and cwd is a linked worktree; stage timeouts sum to < the oracle's 1800s
- New tests: oracle format stage SKIPs without `changed_files_path` (existing-caller invariance); `{files}` substitution quotes paths and drops deleted/filtered files and includes untracked files; `aggregate` returns `GATE_FAILED` for a non-SKIP sidecar with no `exit_code=` line (killed stage); `record_quality_evidence` takes the verdict from the route, not `subloop_outcome_<ID>.txt` (fixture: token file says `GATE_PASS`, route is `fail` → `GATE_FAILED`); `on_error` → `quality_gate_infra`; `finalize_done` promotion requires evidence for `done` but not `cancelled`; `quality_gate_failed` / `quality_gate_infra` / `quality_evidence_missing` reason lines feed `not_closed`, the new keys, and are excluded from the `Unverified` display line; parent `finalize` counts a quality-failed `done` ID as not-closed; `quality_gate: false` restores status-only credit

### Documentation
- `docs/guides/` loop guide for autodev, if it documents closure semantics

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/loops.md:874` — full `oracles/code-run-gate` reference (params table :889, stage flow, direct-call example :927) gains the format stage/param [Agent 1 finding]
- `docs/guides/LOOPS_REFERENCE.md:1007` — `Closure accounting` documents `autodev-passed.txt`/`autodev-skipped.txt` as auto-refine's sources; `:1079` documents `finalize_done`'s bucket list — the cancelled/implemented split edits both [Agent 2 finding]
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md:253` — `GATE_FAILED` outcome-token row enumerates "build / test / typecheck / lint / health"; format joins the enumeration [Agent 2 finding]
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:692` — declares `oracles/code-run-gate.yaml` a permanent exemption for command resolution; the format stage's `format_check_cmd` resolution follows the same exemption [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:305` — add `format_check_cmd` (`{files}` placeholder, check-only) and `format_check_extensions` rows beside `format_cmd`; `format_cmd` stays without a runtime reader (amended 2026-09-26)
- `docs/guides/LOOPS_REFERENCE.md` — autodev `quality_gate` context key and the `quality_failed` summary key; `auto-refine-and-implement` forwarding of `quality_gate`
- `CHANGELOG.md` — release entry calling out the default-on gate (full-suite run per issue) and the `quality_gate: false` workaround

### Configuration
- `project.format_check_cmd` (new), `project.format_check_extensions` (new), `lint_cmd`, `type_cmd`, `test_cmd`, `src_dir` (worktree `PYTHONPATH` prepend)
- autodev context `quality_gate` (new, default `true`); `auto-refine-and-implement` context `quality_gate` (new, forwarded)

### Changed-file scoping

`implement_current` shells out to `ll-auto`, so autodev cannot see which files the
implementation touched. Record the base revision (`git rev-parse HEAD`) into the run dir
**before** `implement_current`, together with the pre-existing dirty set, and compute the
changed-file set as `git diff --name-only --diff-filter=d <base>..HEAD` (plus uncommitted
and untracked changes, minus the pre-existing dirty set) after it.
The format stage runs only on that set (see Design Decisions for extension filtering).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- _Line numbers below are as of 2026-09-25 and have since drifted; locate autodev states by name. As of 2026-09-26: autodev has 110 states, `ProjectConfig.format_cmd` is :220, and `summary.json` has 14 keys (BUG-3603 added `proof_gate_infra`; ENH-3613 added `closed_implemented`/`closed_cancelled`)._
- `skills/manage-issue/SKILL.md` Phase 4 confirmed as described (now ENH-3612's scope): lines 354-372 append `tests/ -v` to `{{config.project.test_cmd}}` and `{{config.project.src_dir}}` to the lint/type commands, run `build_cmd`/`run_cmd` bare, and the skill directory contains zero occurrences of `format_cmd` — formatting is never run by manage-issue. The "Headless-Safe Final Test Run" subsection (:376) mandates the scratch-redirect foreground suite run.
- `oracles/code-run-gate.yaml` current surface: params `run_dir`, `issue_id`, `min_pass_rate` (default 0.95), `health_bound_seconds`, plus optional `build_cmd`/`test_cmd`/`typecheck_cmd`/`lint_cmd`/`run_cmd`/`health_url` overrides (:52-103). Stages `resolve_commands → run_build → run_test → run_typecheck → run_lint → service_health → aggregate`; every stage failure still advances (no MR-4 partial-route dead-end). No format stage or format param exists.
- Command-resolution convention inside the oracle: `resolve_commands` reads `.ll/ll-config.json` `project.*` with alias handling (`typecheck_cmd`/`type_cmd`, `start_cmd`/`run_cmd`, ARCHITECTURE-123) and honors caller overrides via `${context.<cmd>:default=}`; other loops use `ll-config get project.test_cmd`, which also honors `.ll/ll.local.md`.
- Baseline→changed-files precedent exists one level down the call chain: `issue_manager.py:1284-1289` (`process_issue_inplace`) captures `git rev-parse HEAD` immediately before implementation, consumed by `work_verification.py:470` (`_detect_meaningful_changes`) as `git diff --name-only <baseline>..HEAD` plus staged/unstaged diffs (:428, :445). `prepatch_check.py:248` (`resolve_base_ref`) is the public base-ref resolver with merge-base fallback. autodev.yaml contains no `git` invocation today, so the base revision must be recorded loop-side as the Changed-file scoping note plans.
- Load-bearing invariant: `test_builtin_loops.py:7465` (`test_check_passed_stages_instead_of_passes`) asserts `finalize_done` is the only state allowed to populate `autodev-passed.txt` (the `check_passed` state must stage, not pass). Whatever gates closure credit must route promotion through `finalize_done`, or amend that test's contract knowingly.
- `verify_issue_completed` (`issue_lifecycle.py:768`) is not in autodev's call chain — its only production callers are in `issue_manager.py` (:1469, :1560, :2220), i.e. the `ll-auto`/manage-issue path. The Dependent Files entry covers that path only; autodev re-implements the status check in shell.
- Existing closure-state tests and their harness: `test_builtin_loops.py` `TestAutodevLoop` (:6643) — `_run_finalize_done` (:7481) executes the state's action under `bash -c` after `${context.run_dir}` substitution and `$${`→`${` un-escaping; tests pin phantom-on-unclosed (:7485), verified promotion (:7518), no-op (:7544), rate-limit routing through finalize (:7553-:7574), BUG-3390 dedupe (:7886), and `verify_impl_closed` routing (:7827-:7871). The `summary.json` key set (`verdict`, `closed`, `not_closed`, `skipped`, `gate_blocked`, `decision_unresolved`, `not_started`, `inflight_unresolved`, `abandoned`, `stop_reason`, `pending`, `proof_gate_infra` — 12 keys after BUG-3603) is load-bearing for these tests; ENH-3613 appended `closed_implemented`/`closed_cancelled` (14), and this issue's keys go after those.
- No doc under `docs/` documents autodev's closure buckets or `summary.json` keys today; the only adjacent passage is `docs/guides/RECURSIVE_LOOPS_GUIDE.md` §PHASE1_NOT_STARTED (:287-304, `not_started` verdict semantics).

## Open Questions

- **Owner of the quality run** ✅ **RESOLVED** (2026-09-25 by /ll:decide-issue): (b) an
  autodev gate (extended `oracles/code-run-gate`) that runs after `implement_current` and
  is the only source of the closure-credit verdict. _Amended 2026-09-26:_ the suite runs
  twice per issue in v1 (Phase 4 + gate); see Design Decisions → Suite ownership.

## Implementation Steps

1. ~~Decide the single owner of the post-implementation quality run~~ — decided: autodev gate (Option B)
2. ~~Measure this repo's `test_cmd` wall-clock~~ — measured 250–355s (under 80% of 600s); still time the `prepatch_check` fork on the first real run. No `test_timeout_seconds` param (state `timeout:` cannot be interpolated)
3. Add `project.format_check_cmd` / `format_check_extensions` to schema, `ProjectConfig`, and `CONFIGURATION.md` (note the no-`"` command constraint unless `commands.json` moves to `json.dumps`)
4. Extend `oracles/code-run-gate`: `changed_files_path` + `format_check_cmd` + `src_dir` params, `run_format_check` state (opt-in, SKIP without a path, file list read from `changed_files_path`, `timeout: 120`), worktree `PYTHONPATH` prepend in `run_test`/`run_typecheck`, `aggregate` sidecar list, **killed-stage (no `exit_code=`) and configured-but-absent-sidecar → fail rules**; keep stage timeouts summing under 1800s; update the state-set freeze, baseline and MR11 allowlist
5. autodev: base-rev + base-dirty snapshot lines in `implement_current` (before `ll-auto`); `route_quality_gate` (changed set minus base-dirty) → `run_quality_gate` → `mark_quality_pass|fail|infra` → `record_quality_evidence` after `verify_impl_closed.on_yes`; verdict from the route, never the token file; `mark_quality_fail` maps `terminated_by` timeout/signal/interrupted/max_steps to route `infra`; `quality_gate` context default
6. `finalize_done`: evidence-gated promotion for `done|completed`, `quality_gate_failed` / `quality_gate_infra` / `quality_evidence_missing` reason lines, `quality_failed` + `quality_gate_infra` keys (on ENH-3613's landed shape), `Quality-failed` summary line with short `head_sha`, exclusion from the `Unverified` display line, all-failed hint naming `quality_gate: false`
7. `auto-refine-and-implement.yaml` `finalize`: subtract `quality_gate_*` IDs from `CLOSED`, add them to `NOT_CLOSED`, emit `quality_failed` (today they would count as closed); declare a `quality_gate` context key and forward it in `delegate`'s `with:`
8. Docs, CHANGELOG callout, and tests per Integration Map
9. ~~Fix manage-issue Phase 4 to use configured commands verbatim~~ → ENH-3612
10. ~~Split cancelled from implemented closures in `summary.json`~~ → ENH-3613 (landed 2026-09-26)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `aggregate` in `oracles/code-run-gate.yaml` — add the format sidecar to its file list and keep the `SKIP <cmd>=null` first-line convention so `classify` routing survives
- Handle `TestPrePatchCheckReachability` — a new oracle *state* trips the frozen 9-state exact-set equality; either extend the freeze knowingly (its comment requires re-reading ENH-2997's Scope Boundaries) or add format as a stage of an existing state
- Route gate-failed closures through the parent — `auto-refine-and-implement.yaml` `finalize` must subtract them from `CLOSED` (status-diff based) and add them to `NOT_CLOSED`; otherwise they count as closed
- Add baseline + MR11 allowlist entries for the oracle's new `context.format_check_cmd` / `context.changed_files_path` refs; keep `:default=` on both guard and RHS in `resolve_commands`
- Update `docs/reference/loops.md`, `docs/guides/LOOPS_REFERENCE.md` (:1007, :1079), `docs/guides/RECURSIVE_LOOPS_GUIDE.md:253`, and `scripts/little_loops/loops/README.md:194` for the format stage
- ~~Regenerate `skills/manage-issue` mirrors~~ → ENH-3612
- Update `test_builtin_loops.py` finalize fixtures with quality-evidence artifacts when promotion is gated, and keep new autodev states inside the `autodev-inflight`-clearing chain (`test_autodev_implement_current_failure_chain_clears_inflight`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Constraint: the gate must remain a non-LLM evaluator in the FSM — `code-run-gate` is all-shell with `exit_code`/`output_numeric`/`classify` evaluators, so extending it keeps the autodev meta-loop MR-2-compliant; a shared Python runner preserves the same property only if the FSM routes on its exit code, not on model output.
- _Superseded 2026-09-26: the format stage consumes the new `project.format_check_cmd`, not `format_cmd`._ Constraint: the format stage consumes `project.format_cmd`, which today has no runtime reader (`config/core.py:210`; serialized at `:770` only) — there is no existing format-invocation helper to reuse, but the scoping primitives exist (`work_verification.py` diff computations, `filter_excluded_files` :32).
- Constraint: adding states to `autodev.yaml` bumps the state count pinned by `test_fsm_topology.py` `TestAutodevSmoke.test_autodev_topology` (110 states as of 2026-09-26, post-ENH-3609) and must keep the `loop_interpolation_baseline.json` `finalize_done` entry valid.
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
- `read_base_sha(issue_id: str, *, run_id: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> str | None` — `scripts/little_loops/history_reader/runs.py:181`; the dequeue-time base stamp `ll-auto` writes per issue. `run_test`'s `prepatch_check` reads it through the oracle's `issue_id`, so the gate's prepatch check runs on the implementation diff.
- `ProjectConfig.format_cmd: str | None` — `scripts/little_loops/config/core.py:220`; read today only by the `to_dict` serializer (`config/core.py:770`). No runtime consumer exists anywhere.

### Call Path

Today: `autodev.yaml:implement_current` (shells `ll-auto --only`) → `verify_impl_closed` (`ll-issues show --json` status read) → `dequeue_next` → … → `finalize_done` (sole writer of `autodev-passed.txt`). The gate chain this issue extends is NOT on that path today: `rn-remediate.yaml:run_code_gate` (:501, `loop: oracles/code-run-gate` with `issue_id`/`run_dir`/`min_pass_rate`) → `resolve_commands → run_build → run_test → run_typecheck → run_lint → service_health → aggregate` → `subloop_outcome_<ID>.txt` (`GATE_PASS`/`GATE_FAILED`/`GATE_SKIP`). Baseline-capture precedent one level down: `issue_manager.py:1284-1289` records `git rev-parse HEAD` inside `process_issue_inplace` immediately before implementation; autodev.yaml itself contains no `git` invocation.

### Decision Rules

- Closure credit: a `done|completed` ID reaches `autodev-passed.txt` only when `quality/<ID>.json` records `GATE_PASS` or `GATE_SKIP` for the `head_sha` captured at gate time; a `cancelled` ID is promoted on status alone (no gate run); with `quality_gate: false` all closed IDs are promoted on status alone. The cancelled/implemented summary split is ENH-3613's.
- Gate failure never mutates the issue file; it is recorded as `ID  quality_gate_failed` in `autodev-unverified.txt` and counted in both `not_closed` and `quality_failed`. A sub-loop `on_error` is `ID  quality_gate_infra`, counted in `not_closed` and `quality_gate_infra`.
- The credited verdict comes from `run_quality_gate`'s route (`on_success`/`on_failure`/`on_error`), never from the oracle's `subloop_outcome_<ID>.txt`, which `resolve_commands` pre-seeds with `GATE_PASS`.
- A non-SKIP stage sidecar with no `exit_code=` line (stage killed at timeout) is a failure in `aggregate`.
- A `prepatch_check` `flagged` verdict on `run_test` (new test passes on the base) fails the gate; the evidence records `prepatch: flagged`.
- The oracle's format stage runs only when `changed_files_path` is passed; it is check-only and never writes to the working tree.
- The gate's verdict vocabulary is already fixed by `code-run-gate`'s `aggregate` state — `GATE_PASS`/`GATE_FAILED`/`GATE_SKIP`, routed via a `classify` evaluator (`GATE_SKIP` routes to `done`, not failure, when no commands are configured). A format stage joins that matrix; it does not introduce a new vocabulary.
- `code-run-gate` exposes no format parameter today (`oracles/code-run-gate.yaml:52-103`); any added stage must leave the oracle's existing callers (`rn-remediate.yaml:500`, `rn-refine.yaml:480`, `rn-implement.yaml` transitively, tests) behaviorally unchanged unless they opt in.

## Acceptance Criteria

- [ ] The autodev gate (extended `oracles/code-run-gate`) is the owner of the post-implement quality verdict
- [ ] Closure credit for `done|completed` requires a recorded `GATE_PASS`/`GATE_SKIP` evidence record for the commit the implementation produced; `cancelled` closures skip the gate
- [ ] The format stage is check-only and runs only on the changed files (deleted files dropped, extension filter applied)
- [ ] The gate passes `min_pass_rate: 1.0`
- [ ] Gate failure lands in `not_closed` and a `quality_failed` summary key; the issue file is not modified
- [ ] Gate `on_error` lands in `not_closed` and a `quality_gate_infra` summary key, distinct from `quality_failed`
- [ ] The credited verdict is taken from the sub-loop route; a test with `subloop_outcome_<ID>.txt` = `GATE_PASS` and route `fail` records `GATE_FAILED`
- [ ] `aggregate` returns `GATE_FAILED` when a non-SKIP stage sidecar has no `exit_code=` line (killed stage)
- [ ] Quality-failed IDs print on their own `Quality-failed` summary line with short `head_sha`, not under the `Unverified` "re-queue to retry" line
- [ ] `auto-refine-and-implement` counts a quality-failed `done` issue as not-closed (not closed) and reports `quality_failed`
- [ ] Existing `code-run-gate` callers (`rn-remediate`, `rn-refine`, `rn-implement`) are unchanged (format stage SKIPs without `changed_files_path`), except that a killed stage now fails instead of passing
- [ ] `quality_gate: false` restores status-only closure credit, and is reachable from `auto-refine-and-implement` via its forwarded `quality_gate` context key
- [ ] Files dirty or untracked before `implement_current` are excluded from the changed-file set and do not set `dirty`
- [ ] An oracle that ends by timeout, signal, interrupt, or step budget lands as `quality_gate_infra`, not `quality_gate_failed`
- [ ] In an EPIC-scope worktree run, the gate's test and typecheck stages import the worktree's package, not the main checkout's

_ENH-3613 landed (status `done`, verified 2026-09-26); `blocked_by` cleared. Line anchors for autodev states refreshed by `/ll:ready-issue`._

_Moved out 2026-09-26:_ the verbatim-commands criterion is now ENH-3612's; the cancelled/implemented summary split is now ENH-3613's.

## Scope Boundaries

- Blocks only ENH-3600, which rewrites the same `finalize_done` / closure accounting. It
  no longer blocks the preparation-routing migrations (ENH-3599, ENH-3601). This issue is
  a closure feature, not a preparation fix, and those migrations do not touch
  `implement_current`, `verify_impl_closed` or `finalize_done`.
- The `summary.json` cancelled/implemented split moved to ENH-3613 (landed 2026-09-26).
  This issue adds only `quality_failed` and `quality_gate_infra` to that shape.
- Out of scope (follow-ups): automatic repair/retest after `GATE_FAILED`; an autodev-only
  opt-out so manage-issue Phase 4 skips the full suite when the gate owns it; baseline
  (pre-existing failure) comparison instead of absolute pass/fail (highest-value
  follow-up: this repo's `main` is intermittently red, see Escape hatch); a way to
  re-gate an already-`done` issue on a later run.
- In scope although it touches existing callers: the `aggregate` killed-stage fix. It
  corrects a latent false `GATE_PASS` for every `code-run-gate` caller.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-26 (re-scored after ENH-3613 landed and the second design review)_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

All hard-override gates clear (no `blocked_by`, Program Design, parity, claims, decision, structure, learning tests). Readiness deductions: partial precedent exists (`oracles/code-run-gate` extended, not duplicated).

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
- `/ll:confidence-check` - 2026-09-26T07:29:51 - `47ac16a0-9fcf-4e6d-8f88-4ec1ae6c246a.jsonl`
- `/ll:ready-issue` - 2026-09-26T07:17:31 - `8bfc06b1-1f9e-46db-8503-f6893c9021c7.jsonl`
- `/ll:confidence-check` - 2026-09-26T05:49:01 - `5966980a-c2ea-49c8-a21f-97ae3fab2cc8.jsonl`
- `/ll:verify-issues` - 2026-09-26T05:13:24 - `d2d5d28e-c902-43ff-bf33-1a7825d2f036.jsonl`
- `/ll:confidence-check` - 2026-09-25T21:32:36 - `672e0da1-840e-4b60-a432-7b20e9ebbd01.jsonl`
- `/ll:wire-issue` - 2026-09-25T20:49:53 - `4a475966-a47c-4657-a3e4-16e6706f4c4d.jsonl`
- `/ll:refine-issue` - 2026-09-25T19:53:36 - `52506a27-e6a0-49d9-99b0-9b89990953d8.jsonl`
- `/ll:decide-issue` - 2026-09-25T19:39:02 - `f72e39ee-7f4f-46b8-b438-d29d8550cab9.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:31 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`
