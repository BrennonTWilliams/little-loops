---
id: ENH-2997
title: Host the pre-patch check on the executor's guarded window
type: ENH
priority: P2
status: open
discovered_date: 2026-08-02
epic: EPIC-2856
parent: ENH-2853
labels:
- rework
- verification
testable: true
size: Large
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 78
score_complexity: 15
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 18
reconcile_attempted: true
---

# ENH-2997: Host the pre-patch check on the executor's guarded window

## Summary

Make ENH-2991's pre-patch check reachable from every green-suite transition in
the `rn-*` loop family by hosting it on the FSM executor's guarded-window
mechanism — the same policy-key-plus-exit-hook shape ENH-2854 established for
`tamper_guard`, minus the entry snapshot, which this check has no use for (see
§ Design Notes → "No entry snapshot is needed") — rather than as a state inside
`oracles/code-run-gate.yaml`.

## Parent Issue

Decomposed from ENH-2853: Deterministic pre-patch test-failure check in
verification loops. Covers Integration Map Layer 2 (executor half) and the
placement Design Notes.

## Current Behavior

ENH-2991 ships `run_prepatch_check()` as a host-agnostic core that nothing calls.
No FSM mechanism invokes it, so no verification transition is gated by it.

## Expected Behavior

A first-class FSM key (settable loop-level and state-level, mirroring
`tamper_guard`) causes the executor to bracket a guarded state's entry and exit,
compute the step diff, resolve the base state, invoke `run_prepatch_check()`, and
record the verdict in `ctx.context` following ENH-2854's `_tamper_guard` record
shape — with the full `PrePatchEvidence` bundle written under
`${context.run_dir}/` per MR-3. When the key is absent (no state override, no
loop default), the guarded window short-circuits to SKIP rather than failing.

## Motivation — why the executor, not an oracle state

The 2026-07-30 placement review on ENH-2853 correctly ruled out `cli/harness.py`
and `/ll:verify-issue-loop` as owners:

- **No orchestrator invokes `ll-harness`.** A repo-wide grep for `ll-harness`
  across `scripts/little_loops/` returns only its own CLI (`cli/harness.py`), the
  shared `runner_spec.py` abstraction, telemetry readers
  (`history_reader.py:2797+`), and a permission string in `init/writers.py:70`.
  Nothing in `ll-auto`, `ll-parallel`, `ll-sprint`, or any `loops/*.yaml` calls it
  — it is a hand-run one-shot tool.
- **`/ll:verify-issue-loop` is a generator.** A check emitted there exists only
  inside per-issue loop YAML someone chose to generate, never in a standing path.

But that review's *positive* prescription — an additive state in
`oracles/code-run-gate.yaml` reached via the token channel — predates ENH-2854
landing on 2026-07-31, which solved the identical reachability problem for the
identical class of gate a different way:

- ENH-2854 shipped `tamper_guard` as a **first-class FSM key**, settable
  loop-level and state-level (`fsm/schema.py:690` and `:1311`), enforced by the
  executor as snapshot-on-entry / compare-on-exit
  (`fsm/executor.py:1295-1384`), with findings accumulated across guarded states
  in `ctx.context["_tamper_guard"]`, plus a dedicated validation lint rule.
- `code-run-gate.yaml:50` already declares `tamper_guard: fail` at loop level —
  the sibling mechanism is already active in the very file the 07-30 review
  proposed adding a state to.
- **Reachability, not input access, is the decisive argument.** An earlier
  revision claimed the executor placement was decisive on the merits because
  "this check's input is the diff of the verification step" and only the
  entry/exit bracket computes it. **That is false and has been corrected** — see
  § Design Notes → "The check's input is the cumulative patch diff, not the
  guarded state's delta." The real input is `git diff <base_ref>`, which any
  host can compute from anywhere. What the executor placement actually buys is
  (a) reachability from every `rn-*` green-suite transition via a one-line
  opt-in, (b) mechanical consistency with `tamper_guard`, the only prior
  entry/exit-bracket guard, and (c) a routing contract (`on_no` / failure
  terminal) that an oracle state would have to reinvent. Those three still
  decide the placement; the input-access argument does not.

The actual chokepoint for "did these tests prove anything" is
`oracles/code-run-gate.yaml`'s `run_test` state, delegated to by
`rn-refine.yaml:483`, `rn-remediate.yaml:543`, and `rn-implement`'s
`run_code_gate` (`loops/README.md:64`). `code-run-gate.yaml` opts in with a
**single loop-level key line**, exactly as it already does for `tamper_guard`
(`:50`) — **no state is added to it**. See § Design Notes → "Opting
`code-run-gate.yaml` in" for why a key line is required and is not the
placement the 2026-07-30 review rejected.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Token-channel idiom, verified current** (`loops/oracles/code-run-gate.yaml`): `subloop_outcome_<ID>.txt` is a plain-text single-token verdict file, one per issue ID — written by shell `echo VERDICT > "subloop_outcome_${context.issue_id}.txt"` (placeholder at `:184-186`, final verdict from the `aggregate` state at `:449-451`, failure paths at `:538`,`:566`), read by shell `cat`/`grep -qxF` in the parent loop (`rn-implement.yaml:772,1182,1271`) or by Python glob + stem-slicing (`rn-implement.yaml:1575-1577`, `run_dir.glob("subloop_outcome_*.txt")`). It carries only a short enum-like verdict string — any richer evidence bundle (this issue's `PrePatchEvidence`) is a separate artifact under `${context.run_dir}/`, referenced alongside the token file, not inside it.
- **Testing convention confirmed**: this codebase's guard-key tests split into two independently-named test classes, one per layer — an executor-integration tier (`TestTamperGuardExecutorHook`, `scripts/tests/test_fsm_executor.py:11225`, builds a real git repo via `tests.helpers.copy_git_template` and a real `FSMExecutor.run()`, no mocked FSM layer, individually named tests per policy value) and a lint-rule tier (`TestTamperGuardValidation`, `scripts/tests/test_fsm_validation_evaluator_rules.py:1242`, builds `FSMLoop`/`StateConfig` objects directly via a `_fsm()` helper, plus one dedicated YAML-round-trip test — `test_tamper_guard_recognized_as_top_level_key` — that exercises the `KNOWN_TOP_LEVEL_KEYS` registration specifically). A `prepatch_check` key should get one test class per tier, mirroring this exact split rather than one combined test file.

## Proposed Change

1. Add the pre-patch-check key to `fsm/schema.py` at both loop level (near
   `:1323,1325`, alongside `tamper_guard`/`tamper_guard_ok`) and state level
   (near `:698`), following `tamper_guard`'s declaration shape.
2. In `fsm/executor.py`, extend the guarded-window mechanism — mirroring the
   `tamper_guard` resolver (`:1344-1361`) and exit-compare/checker (`:1385-1455`,
   invoked from both call sites `:1534-1538` and `:1587-1591`) — **with a
   resolver and an exit hook only; no entry snapshot is added** (see § Design
   Notes → "No entry snapshot is needed"). The exit hook fires only on the green
   path (see § Design Notes → "The check runs only on the green path"), resolves
   `(base_sha, base_dirty)` via `history_reader.read_base_sha(issue_id)` /
   `history_reader.read_base_dirty(issue_id)`, resolves `base_ref` via the newly
   public `prepatch_check.resolve_base_ref()`, **produces the cumulative patch
   diff via a new `_prepatch_step_diff(repo_root, base_ref) -> str` helper that
   unions tracked changes with untracked non-ignored files** (see § Design Notes
   → "The check's input is the cumulative patch diff" and "`git diff <base_ref>`
   alone drops untracked files"), and calls `run_prepatch_check()` — supplying
   the six further arguments the shipped signature requires (see § Design Notes
   → "Host-supplied arguments"). The call is wrapped in `try/finally` so the
   pre-patch worktree is torn down (see § Design Notes → "Worktree lifetime is
   the host's").
2c. **Promote `resolve_base_ref()` to public in `prepatch_check.py`** and route
   both the core and the host through it, so the ref the diff is computed
   against and the ref the core forks at cannot diverge (see § Design Notes →
   "The host cannot obtain the resolved `base_ref` today").
2a. **Pin the ordering against `tamper_guard` in code, at both exit call
   sites** — the prepatch checker must run before `_check_tamper_guard`, with
   an explicit precedence rule when both want to route (see § Design Notes →
   "Ordering against ENH-2854").
2b. **Persist the bundle to `.ll/history.db`** — a new
   `prepatch_evidence` table plus writer and reader, since none exists today
   (see § Design Notes → "The history.db surface must be built, not reused").
3. Define the key's **policy enum** as `fail | warn | allow` and map the core's
   verdict onto it (see § Design Notes → "Policy values and verdict mapping").
4. Add the one-line loop-level `prepatch_check:` key to
   `oracles/code-run-gate.yaml` — a key line, not a state.
5. Record the verdict in `ctx.context` following ENH-2854's `_tamper_guard`
   record shape, accumulating findings across guarded states.
6. Write the full `PrePatchEvidence` bundle to the **named** path
   `${context.run_dir}/prepatch_evidence_<issue_id>.json` (MR-3) via
   `PrePatchEvidence.to_dict()`, and expose it through the parent↔sub-loop token
   channel (the `subloop_outcome_<ID>.txt` idiom `code-run-gate` already uses) so
   a delegating parent loop can read the result. The filename is a contract
   ENH-2998's consumer depends on — see § Design Notes → "Evidence-bundle
   transport follows the host."
7. Resolve an absent key to SKIP, exactly as `fsm/executor.py:1305` resolves
   `tamper_guard`'s absence to "not guarded". This is a *different* layer from
   ENH-3142's config off-switch, which remains in force underneath it (see
   § Design Notes → "Two skip layers"); neither may resolve to a failure.
8. Add a validation lint rule mirroring ENH-2854's, so misuse is caught by
   `ll-loop validate`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/fsm/fsm-loop-schema.json` — declare
  `prepatch_check`/`prepatch_check_ok` at loop level and `prepatch_check` at
  state level, mirroring the existing `tamper_guard` entries.
- Register the new lint rule in
  `scripts/little_loops/fsm/validation/structural_rules.py` alongside
  `_validate_tamper_guard`'s registration.
- Add `TestPrePatchCheckExecutorHook` (`scripts/tests/test_fsm_executor.py`)
  and `TestPrePatchCheckValidation`
  (`scripts/tests/test_fsm_validation_evaluator_rules.py`), each mirroring its
  tamper-guard sibling class method-for-method.
- Add `KNOWN_TOP_LEVEL_KEYS` membership tests and a schema-round-trip test for
  `prepatch_check`, following `test_feat3033_idle_timeout.py:60-61` and
  `test_fsm_schema.py:4571-4579`.
- Update `docs/guides/LOOPS_GUIDE.md` (new `### Pre-Patch Check` section after
  the "Tamper Guard" section), `docs/reference/CLI.md` (new `ll-loop validate`
  rule bullet), `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (new Design Rules
  table row), and `docs/reference/loops.md` (add the evidence bundle to the
  MR-3 run-dir artifact enumeration).

## Design Notes

- **Skip convention.** Absent key (no state override, no loop default) means "not
  guarded." The knob must short-circuit to a SKIP pass-through, never to a
  failure — a gate that fails closed on an unconfigured loop would break every
  existing loop on upgrade.
- **Opting `code-run-gate.yaml` in (corrects an earlier contradiction).** An
  earlier revision of this issue claimed `code-run-gate.yaml` "inherits this
  check via the loop-level guard key it already carries." It does not: the only
  guard key in that file is `tamper_guard: fail` (`:50`), and guard keys are not
  interchangeable. Combined with the absent-key-means-SKIP rule below, leaving
  the file untouched would mean **the check never runs on the `rn-*` path at
  all**, which cannot coexist with this issue's reachability AC. The resolution
  is a single loop-level `prepatch_check:` key line in `code-run-gate.yaml`,
  alongside the `tamper_guard:` line it already carries. This does not revive the
  placement the 2026-07-30 review rejected — that review rejected adding a
  *state* (an oracle step with its own action and routing); a one-line key
  declaration is the same opt-in `tamper_guard` uses and adds no step to the
  gate's state machine.
- **Prefer state-level placement over blanket loop-level inheritance.** Each
  invocation forks a git worktree and runs pytest up to twice (the initial run,
  then a flake-retry pass over everything that passed — `prepatch_check.py:449-454`)
  inside a `timeout_s` box that defaults to 300s. At loop level every guarded
  state pays that on every iteration. Placing the key on the single verify state
  (`run_test`) rather than at loop level is the cost-appropriate default; if the
  loop-level line is used instead, the per-state cost must be justified.
- **The check's input is the cumulative patch diff, not the guarded state's
  delta (corrects a blocking design error, 2026-08-12).** `run_prepatch_check()`
  requires `step_diff` to be a real unified diff: `_parse_diff`
  (`prepatch_check.py:100-120`) matches `+++ b/` headers and `@@` hunks to
  recover post-patch touched line numbers. **The guarded-window bracket produces
  nothing of the sort** — entry is a `{path: hash}` snapshot and exit is
  `tamper_guard_changed_files()` (`test_tamper_guard.py:175-190`), a *name list*
  from `git diff --name-only HEAD` unioned with untracked files. A repo-wide
  grep for `step_diff` returns hits only inside `prepatch_check.py` itself: **no
  diff-string producer exists anywhere in the codebase**, and no earlier
  revision of this issue named one.

  Compounding it, the cost-preferred placement is state-level on `run_test` — a
  state that *runs pytest and edits nothing*. Its entry→exit delta is empty, so
  `collect_candidates()` returns `[]` and the core returns `verdict="skipped"`,
  `skipped_reason="no candidate tests identified"` (`prepatch_check.py:416-424`)
  on **every** invocation. The reachability AC would pass green over a
  structurally inert gate.

  **Resolution:** the host computes `git diff <base_ref>` — where `base_ref` is
  the `read_base_sha()` value, or the merge-base when unstamped — capturing the
  whole patch under evaluation, including the working tree. Add a
  `_prepatch_step_diff(repo_root: Path, base_ref: str) -> str` helper on the
  executor (a thin `_git(repo_root, "diff", base_ref)` wrapper following
  `_tamper_guard_changed_files`'s delegation shape).
- **`git diff <base_ref>` alone drops untracked files, which re-opens the inert
  gate one layer down (blocking, found 2026-08-12 pre-implementation review).**
  `git diff <ref>` reports tracked modifications only; a brand-new test file is
  untracked until something commits it. Since `_parse_diff`
  (`prepatch_check.py:100-134`) discovers files **exclusively** through `+++ b/`
  headers, an untracked new test never appears in `touched`, never reaches
  `filter_test_files`, and `collect_candidates()` returns `[]` → the core
  short-circuits to `verdict="skipped"` (`prepatch_check.py:416-424`). That is
  the same silently-inert gate the resolution above was written to close, and
  "a newly added test that also passes pre-patch" is precisely the highest-value
  case this whole check exists to catch.

  The sibling guard already solves this and documents why:
  `tamper_guard_changed_files` (`test_tamper_guard.py:175-190`) unions `git diff
  --name-only HEAD` with `git ls-files --others --exclude-standard` explicitly
  "so a newly-added test file is visible to `run_tamper_guard` even though it
  couldn't have been in the entry snapshot."

  **Rule:** `_prepatch_step_diff` returns `git diff <base_ref>` **concatenated
  with**, for each untracked non-ignored path from `git ls-files --others
  --exclude-standard`, a `git diff --no-index -- /dev/null <path>` fragment
  (which emits a well-formed `+++ b/<path>` header plus `@@` hunks, exactly what
  `_parse_diff` consumes). Use `--no-index` rather than `git add -N`: the latter
  mutates the index of the live repository under a shared `GitLock` and would be
  visible to every concurrent worker. The anti-inert-gate AC must exercise an
  **untracked** added test file, not merely a committed one — a committed-file
  test passes without this rule and would leave the hole open.
- **The host cannot obtain the resolved `base_ref` today; a public resolver must
  be promoted (blocking, found 2026-08-12 pre-implementation review).** The host
  needs the resolved ref *before* the call, to compute `step_diff`. The core
  resolves it *internally* (`prepatch_check.py:398-403`) via the private
  `_merge_base` (`:240`) and only surfaces the result on the returned
  `PrePatchEvidence.base_ref` — after the call, too late. `prepatch_check.py`
  declares no `__all__` and every other helper is underscore-private, so an
  implementer's only options are to duplicate `_merge_base`'s logic (the exact
  host/core divergence that would silently mis-scope the diff) or import a
  private name.

  **Rule:** promote a public
  `resolve_base_ref(repo_root: Path, base_sha: str | None, base_branch: str) ->
  tuple[str, str]` (returning `(base_ref, base_source)`) in `prepatch_check.py`,
  and have **both** `run_prepatch_check()` and the executor host call it, so
  host and core agree by construction rather than by parallel maintenance. This
  is the same private→public promotion this repo applied in `3a70ba56`
  (`_test_functions` → `extract_test_functions`) for the same reason: a second
  caller outside the module needed the helper.
- **The check runs only on the green path (found 2026-08-12 pre-implementation
  review).** § Summary scopes this to "every green-suite transition," but no
  earlier revision gated invocation on the guarded state having passed. As
  specced the exit hook fires on red runs too — forking a worktree and running
  pytest up to twice inside a 300s box to produce a verdict that is then
  discarded, because a red suite routes to remediation regardless of what the
  pre-patch check found. Combined with the per-iteration multiplication below,
  that roughly doubles the wasted runtime for zero decisions changed. **Rule:**
  invoke the core only when the guarded state's action succeeded (the `on_yes` /
  zero-exit-code path); otherwise record a skip in `ctx.context` with a
  `skipped_reason` and route nothing. A pre-patch verdict is only meaningful
  about a suite that just went green.
- **No entry snapshot is needed, and one must not be wired.** Unlike
  `tamper_guard`, this check consults no before-state: its entire input is
  `git diff <base_ref>` computed at exit. § Proposed Change and the first
  Acceptance Criterion both enumerate the entry snapshot (`fsm/executor.py:1499-1507`)
  when describing the mechanism to mirror, which reads as an instruction to add
  one; taken literally it would hash every candidate path on every guarded entry
  for no consumer. **Rule:** `prepatch_check` registers a policy resolver and an
  exit hook only. The entry snapshot stays `tamper_guard`-exclusive, and the
  entry-site condition at `:1499-1507` is left keyed on `_tamper_policy` alone.
- **The `.ll/history.db` surface must be built, not reused (new scope,
  2026-08-12).** An AC requires persisting the bundle to `.ll/history.db`, and
  ENH-2998's `run_dir`-less `cli/harness.py` consumer can discover it by no
  other route. But **no such surface exists**: a repo-wide grep finds zero
  `prepatch` references in `history_reader.py` or `session_store/`, there is no
  table and no column, and no earlier revision of this issue listed a file for
  it. ENH-2998 only *reads* the row (`:331`) while elsewhere attributing the
  write to "the adapter" (`:328`) — so both issues assumed the other owned it.
  **ENH-2997 owns it**, since it is the first producer. Scope: a
  `prepatch_evidence` table in `session_store/schema.py` (follow the additive
  migration pattern the `base_sha`/`base_dirty` columns use at `:919-932`),
  keyed by `issue_id` with the `PrePatchEvidence.to_dict()` JSON as its payload;
  a writer in `session_store/writers.py` mirroring
  `record_orchestration_run`'s upsert shape (`:1279-1360`); and a
  `read_prepatch_evidence(issue_id)` reader in `history_reader.py` following
  `read_base_sha`'s never-raises contract. ENH-2998 consumes the reader only.
- **Host-supplied arguments that have no resolution rule yet (2026-08-12).**
  Three of the core's required arguments were left implicit and need explicit
  rules, each with an AC:
  - **`issue_id` is not an executor concept.** `FSMExecutor` has no `issue_id`
    field — the only source is `self.fsm.context.get("issue_id")`.
    `code-run-gate.yaml` declares it as a required parameter, but the guard key
    is generic and any loop may set it. **Rule: degrade, do not skip.** Absent
    `issue_id` means `base_sha=None` / `base_dirty=None`, which the core already
    handles by taking its merge-base fallback (`prepatch_check.py:398-403`). The
    check still runs; the bundle records `base_source="merge-base"`.
  - **`run_dir` may be empty.** The executor already guards this elsewhere
    (`fsm/executor.py:2613-2617` returns an error rather than writing to `""`).
    The bundle-write path needs the same guard: no `run_dir` means skip the
    run-dir file and rely on the `history.db` row, never a crash and never a
    gate failure.
  - **`base_branch` has no source, and the config field is nullable.** It is
    required with no default and drives the merge-base fallback. **Rule:**
    resolve from `parallel.base_branch` in `.ll/ll-config.json` (the same global
    default `issue_parser.py:1698-1700` documents as the fallback for per-issue
    `base_branch:`) — **falling back to `"main"` when unset**, since the config
    field is `base_branch: str | None = None`
    (`config/automation.py:104,142`) while the core's parameter is a required
    `str`. The `or "main"` fallback is already the codebase's own convention for
    this exact field: `self._parallel.base_branch or "main"`
    (`config/core.py:674`, mirrored at `:773`).
- **Evidence-bundle transport follows the host.** With the check hosted by the
  executor rather than `ll-harness`, `PrePatchEvidence` cannot ride a
  harness-local `HarnessEvalOutcome`. It reaches the parent through the existing
  token channel, with the full bundle written to the **named** path
  `${context.run_dir}/prepatch_evidence_<issue_id>.json` and also persisted to
  `.ll/history.db`. Both surfaces are load-bearing and neither is optional:
  ENH-2998's `cli/harness.py` consumer is hand-run and has **no `run_dir`**, so
  the database row is the only surface it can discover by issue ID, while the
  run-dir file is what the delegating parent loop reads. An earlier "and/or"
  phrasing here left the consumer with nothing addressable to read; that
  ambiguity is resolved in favor of writing both.
- **Host-supplied arguments.** The shipped `run_prepatch_check()` is
  keyword-only and requires six arguments beyond `(step_diff, base_sha,
  base_dirty)`. The host must supply: `repo_root`; `worktree_base` — **resolve
  it as `BRConfig(repo_root).get_worktree_base()`** (`config/core.py:568-570`),
  **not** a hardcoded `.worktrees/` and **not** `run_dir`. The directory is a
  configurable setting (`automation.worktree_base`, default `".worktrees"`,
  `config/automation.py:27,45`), the executor already uses this exact accessor
  for its own sub-loop worktrees (`fsm/executor.py:938`), and keeping the fork
  out of `run_dir` is what keeps it outside `tamper_guard_changed_files()`'s
  scan scope per ENH-3141's docstring. Note the earlier "already gitignored at
  `.gitignore:71`" rationale holds **only in this source repo**: `.worktrees/`
  is absent from `ll-init`'s `_GITIGNORE_ENTRIES` (`init/writers.py:59-73`), so
  in a consuming project the fork may be untracked-and-visible — one more reason
  the untracked-file union in `_prepatch_step_diff` must respect
  `--exclude-standard` and the worktree base must come from config, where a
  project can move it. Also: `base_branch` for the merge-base fallback when
  `base_sha` is unstamped; `logger`; and a `GitLock` — **construct both locally
  at the call site as `Logger(verbose=False)` / `GitLock(wt_logger)`.** This is
  no longer an open question: `fsm/executor.py:929-940` already does exactly
  this, in this same file, for the sub-loop worktree path, and `GitLock`'s
  constructor takes an optional logger and nothing else
  (`parallel/git_lock.py:44-48`). `config` is optional and defaults to
  `BRConfig(repo_root)` — pass the host's own instance so `get_worktree_base()`
  and `prepatch_check.enabled` are read from one object.
- **Worktree lifetime is the host's.** `run_prepatch_check()` does not clean up
  after itself: `setup_prepatch_worktree()` creates
  `<repo>/<worktree_base>/prepatch-<timestamp>` plus a same-named branch, and
  tears it down **only when setup itself fails** (`worktree_utils.py:405`). On
  the success path both persist. Executor-hosted, that is one worktree and one
  branch per guarded-state exit per iteration — unbounded growth. The host must
  therefore wrap the call in `try/finally` and call `cleanup_worktree(...,
  delete_branch=True)`. This does not fully close the hole: the reaper cannot
  collect crash leftovers either, because `_is_ll_worktree()` and
  `_is_ll_branch()` (`worktree_utils.py:415-431`) both reject the
  `prepatch-<timestamp>` naming (verified — both return `False`), so
  `/ll:cleanup-worktrees` skips them. Widening those two predicates to accept
  the `prepatch-` naming is in scope here. **Widen with an anchored pattern —
  `^prepatch-\d{8}-\d{6}-\d{6}$`, matching `setup_prepatch_worktree`'s actual
  format string (`worktree_utils.py:381-383`, `"%Y%m%d-%H%M%S-%f"`) — not a bare
  `startswith("prepatch-")`.** `_is_ll_branch` gates *auto-deletion*, and its
  docstring's stated contract is to accept only ll-managed names; a loose prefix
  test would make a hand-created branch called `prepatch-experiment` reapable by
  `/ll:cleanup-worktrees`. The two existing predicates are already anchored
  (`re.match(r"^\d{8}-\d{6}-", name)`), so this follows their shape.
- **Policy values and verdict mapping.** The key's enum is `fail | warn |
  allow` — deliberately *not* `tamper_guard`'s `revert | fail | allow`, since
  `revert` has no meaning for a read-only pre-patch observation. The enum must
  be named explicitly because `fsm-loop-schema.json` needs an `enum` constraint
  and the lint rule validates value validity (per the ENH-2934 precedent in
  § Codebase Research Findings). Mapping onto the core's output
  (`prepatch_check.py:77-97`): `PrePatchEvidence.verdict` is `clean | flagged |
  skipped`, and is `flagged` only when some outcome carries `flag == "hard"`
  (`:493`). Under `fail`, only `verdict == "flagged"` routes to the failure
  target; `soft` flags never route (they are recorded in the bundle and the
  `ctx.context` record only), and `skipped` never routes. Under `warn` and
  `allow`, nothing routes; `warn` additionally logs the flagged outcomes.
- **Two skip layers, and the feature is inert by default.** The host-level
  absent-key SKIP is distinct from ENH-3142's config off-switch, which sits
  underneath it and remains in force. `PrePatchCheckConfig.enabled` defaults to
  **`False`** (`config/features.py:1065`), so a loop that sets the key still
  gets a no-op until `prepatch_check.enabled` is turned on in
  `.ll/ll-config.json` — in that combination the core returns
  `verdict="skipped"` with a `skipped_reason` (`prepatch_check.py:407-414`).
  That is a skip, never a gate failure, and the host must record it as such.
- **The host owns base resolution; the core stays DB-free.**
  `history_reader.read_base_sha(issue_id, *, run_id=None, db=DEFAULT_DB_PATH)`
  (`:1816-1821`) is keyed by issue ID, never raises, returns `None` when
  unstamped, and deliberately does not implement the merge-base fallback (which
  ENH-2991 owns). `run_id` is a process-local uuid4 never exported to env,
  run-dir, or argv, so this out-of-process consumer must omit it and take the
  most-recent-stamped-row path. Note `code-run-gate.yaml` already declares
  `issue_id` as a required parameter, so the identifier is available on that path.
- **Ordering against ENH-2854 — a design decision, not an implementation TODO
  (tightened 2026-08-12).** An earlier revision deferred this ("confirm the
  ordering when wiring both"). It cannot be deferred: `code-run-gate.yaml` will
  carry *both* keys, so both guards are live on the same window in the standing
  `rn-*` path, and `_check_tamper_guard` is invoked from two independent call
  sites (`fsm/executor.py:1534-1538`, `:1587-1591`) that each do
  `if _next is not None: return _next` — an **unconditional early return** from
  `_execute_state`. Whichever checker is called first can therefore prevent the
  other from running at all. Pinned rules:
  1. The prepatch checker is called **before** `_check_tamper_guard` at **both**
     call sites, so it reads the diff before a `revert` policy can rewrite the
     working tree out from under it.
  2. Both checkers always run to completion and record their `ctx.context`
     entry before either routes — the prepatch checker returns its route
     candidate rather than early-returning it, so a prepatch finding never
     suppresses tamper-guard evidence (and vice versa).
  3. **Precedence when both want to route: tamper-guard wins.** A tampered test
     file makes the prepatch verdict untrustworthy — it was computed against a
     diff the guard just flagged as manipulated — so the tamper-guard target is
     the honest destination. The prepatch record still lands in `ctx.context`
     for the evidence trail.
- **Runtime cost is the main non-correctness risk, and it compounds per
  iteration.** Each guarded exit forks a worktree and runs pytest up to twice
  under a 300s box. `run_test` inside `code-run-gate` is reached on *every*
  iteration of the outer `rn-refine`/`rn-remediate` loop, not once per run, so
  the cost is multiplied by iteration count. **In scope:** memoize on the
  **`(step_diff hash, base_ref)` pair** — when both match the previous guarded
  exit in the same run, reuse the prior verdict and record it with a
  `"memoized": true` marker rather than re-forking. The `base_ref` component is
  load-bearing and not optional: a byte-identical diff evaluated against a
  different base is a different check, and `base_ref` legitimately moves within
  one run (an unstamped `issue_id` takes the merge-base path, which tracks
  `HEAD`). Keying on the diff hash alone would serve a stale verdict after a
  rebase or a new commit. This is cheap (a tuple in `ctx.context`) and converts
  the worst case from O(iterations) worktree forks to O(distinct patches).
  Combined with the green-path gate above, red iterations cost nothing at all.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-12 — based on codebase analysis:_

- **Two cosmetic line-range corrections in existing citations (verified 2026-08-12):**
  - `worktree_utils.py:415-431` (cited for `_is_ll_worktree()`/`_is_ll_branch()`) is
    slightly short — `_is_ll_worktree()` starts at line 416 (415 is a blank
    separator) and `_is_ll_branch()`'s body runs through line 435, not 431. The
    functional claim (both reject the `prepatch-<timestamp>` naming) is unaffected.
  - `evaluator_rules.py:368-421` (cited for `_validate_tamper_guard`) spans the
    whole tamper-guard-validation block — the `_TAMPER_GUARD_VALUES` frozenset
    constant at `:368`, the `_effective_tamper_guard()` resolver at `:371-375`,
    and the `_validate_tamper_guard` function itself only starting at `:378`
    (through `:421` as cited). Not a functional error, just a loose span.
- **No shared worktree-lifetime helper exists anywhere in the codebase to reuse
  for the required `try/finally` wrap** (confirmed by pattern search): every
  other worktree-lifetime caller rolls its own — `cli/loop/run.py:449-572` uses
  `atexit.register` instead of `try/finally`; `parallel/worker_pool.py` splits
  setup and teardown across separate methods rather than bracketing them
  together; none of the six `@contextmanager` usages in the codebase
  (`mcp_server/server.py`, `file_utils.py`, `issue_manager.py`,
  `session_store/writers.py`, `cli/issues/format_check.py`,
  `cli/loop/_helpers.py`) touch worktrees. This confirms `cleanup_worktree()` +
  `GitLock` are the only reusable primitives — there is no higher-level
  "worktree session" helper to call into instead of a hand-rolled `try/finally`.
- **`tamper_guard` confirmed as the only prior snapshot-on-entry/compare-on-exit
  bracket** — `session_mode` (`fsm/executor.py:1799`) and `pruning_profile`
  (`fsm/executor.py:1912`) both resolve their value inline at the point the
  executor needs it and consume it immediately; neither takes a "before"
  snapshot or performs a post-action "check" call. No second bracket-shaped
  precedent exists beyond `tamper_guard`.

## Integration Map

### Files to Modify / Create

- `scripts/little_loops/fsm/schema.py` — new first-class key at loop level
  (near `:1323,1325`, alongside `tamper_guard`/`tamper_guard_ok`) and state
  level (near `:698`), following `tamper_guard`.
- `scripts/little_loops/fsm/executor.py` — guarded-window entry/exit hook
  mirroring `tamper_guard`'s current shape (resolver `:1344-1361`, entry
  snapshot `:1499-1507`, exit-compare/checker `:1385-1455`, invoked from both
  call sites `:1534-1538` and `:1587-1591`); base resolution, core invocation,
  `ctx.context` record, run-dir bundle write, token-channel export.
- `scripts/little_loops/fsm/validation/evaluator_rules.py` — lint rule
  mirroring ENH-2854's `_validate_tamper_guard` (`:368-421`), registered in
  `fsm/validation/structural_rules.py:49,1109`.
- `scripts/little_loops/fsm/validation/_base.py` — add the new loop-level key
  (and its `_ok` suppress flag) to `KNOWN_TOP_LEVEL_KEYS` (`:79-134`), or the
  separate unknown-top-level-key check flags the new key itself.
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — **no state added.**
  One loop-level `prepatch_check:` key line (or a state-level key on `run_test`,
  the cost-preferred placement per § Design Notes), alongside the existing
  `tamper_guard: fail` at `:50`. This is the opt-in that makes the reachability
  AC satisfiable; see § Design Notes → "Opting `code-run-gate.yaml` in."
- `scripts/little_loops/worktree_utils.py` — `_is_ll_worktree()` (`:416-422`) /
  `_is_ll_branch()` (`:425-435`) widened with an anchored
  `^prepatch-\d{8}-\d{6}-\d{6}$` so `/ll:cleanup-worktrees` can reap crash
  leftovers without making arbitrary `prepatch-*` branches auto-deletable.

_Added 2026-08-12 — previously-missing files for the `step_diff` producer and
the `history.db` surface (see § Design Notes):_
- `scripts/little_loops/fsm/executor.py` — also gains
  `_prepatch_step_diff(repo_root, base_ref) -> str`, the diff producer the
  core's `step_diff` argument requires. Nothing in the codebase produces one
  today; the guarded-window bracket produces a name list, not a diff. It must
  union `git diff <base_ref>` with per-file `git diff --no-index -- /dev/null
  <path>` fragments for untracked non-ignored paths, or newly added test files
  are invisible to `_parse_diff`.
- `scripts/little_loops/prepatch_check.py` — **promote the private base-ref
  resolution at `:398-403` (which calls the private `_merge_base`, `:240`) into
  a public `resolve_base_ref(repo_root, base_sha, base_branch) -> tuple[str,
  str]`**, called by both `run_prepatch_check()` and the executor host. Without
  it the host has no way to learn the ref the core will fork at before the call
  it must compute `step_diff` for. Follow the `_test_functions` →
  `extract_test_functions` promotion in `3a70ba56`.
- `scripts/little_loops/session_store/schema.py` — new `prepatch_evidence`
  table via the additive-migration pattern the `base_sha`/`base_dirty` columns
  use (`:919-932`).
- `scripts/little_loops/session_store/writers.py` — writer for that table,
  mirroring `record_orchestration_run`'s upsert shape (`:1279-1360`).
- `scripts/little_loops/history_reader.py` — `read_prepatch_evidence(issue_id)`
  following `read_base_sha`'s never-raises / returns-`None` contract
  (`:1816-1869`). This is the reader ENH-2998's harness consumer calls; ENH-2997
  owns it because it is the first producer.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fsm-loop-schema.json` — separate JSON Schema (not
  `fsm/schema.py`) that independently declares `tamper_guard`/`tamper_guard_ok`
  at loop level (`:368-377`, inside `properties` whose `additionalProperties:
  false` closes at `:389`) and `tamper_guard` at state level
  (`definitions.stateConfig.properties`, `:591-595`). An unregistered key here
  fails schema validation independently of the Python-side
  `KNOWN_TOP_LEVEL_KEYS` check — a new `prepatch_check`/`prepatch_check_ok`
  pair needs the same entries or schema-based tooling rejects the key.
- `scripts/little_loops/fsm/validation/structural_rules.py` — registers the new
  lint rule (mirrors `_validate_tamper_guard`'s registration at `:49,1109`,
  confirmed current call site `:1111`).

### Similar Patterns to Follow

- `scripts/little_loops/test_tamper_guard.py` + `fsm/executor.py:1295-1384` +
  `fsm/schema.py:690` / `:1311` (ENH-2854, landed 2026-07-31) — **the primary
  template**: the same class of gate, hosted on the executor's guarded window.
- `oracles/code-run-gate.yaml`'s `subloop_outcome_<ID>.txt` token channel — the
  existing parent↔sub-loop result transport.

### Tests

- A test asserting a guarded loop (`rn-implement` / `rn-remediate` / `rn-refine`,
  transitively via `code-run-gate`) actually runs the check — this is the
  reachability claim the whole issue exists to satisfy, so it must be asserted,
  not assumed.
- A test asserting an absent key short-circuits to SKIP rather than failing.
- A test asserting the bundle lands under `${context.run_dir}/` and the
  `ctx.context` record follows the `_tamper_guard` shape.
- `scripts/tests/test_builtin_loops.py` — `code-run-gate.yaml` must remain valid
  and free of any added *state*; its one added key line is expected.
- A test asserting the pre-patch worktree and its branch do not survive a
  guarded-state exit (success path and exception path both), and that
  `_is_ll_worktree()`/`_is_ll_branch()` accept the `prepatch-` naming.
- A test asserting `verdict: "flagged"` under `policy: fail` routes to the
  failure target while a soft-flag-only bundle does not route.
- A test asserting key-present + `prepatch_check.enabled: false` records a skip
  rather than failing the gate.

_Added 2026-08-12 — coverage for the gaps found in pre-implementation review:_
- **The anti-inert-gate test (highest value in this list).** A guarded run whose
  patch added a test file must produce a non-empty `step_diff` and at least one
  candidate. Without it, every other test here passes green over a gate that
  returns `verdict="skipped"` on every invocation. **The added test file must be
  left untracked** — a committed-file variant passes even with the
  untracked-blind `git diff <base_ref>` producer and would certify an inert gate.
  Pair it with a tracked-modification variant so both discovery paths are covered.

_Added 2026-08-12 — third pre-implementation review pass:_
- A test asserting the live repo's index is unchanged after `_prepatch_step_diff`
  runs (guards the `--no-index` choice against a regression to `git add -N`).
- A test asserting host and core resolve the same `base_ref` — the host's
  `resolve_base_ref()` return equals the invocation's
  `PrePatchEvidence.base_ref`, on both the `dequeue-stamp` and `merge-base` paths.
- A test asserting a guarded state whose action *failed* forks no worktree and
  records a skip (green-path gating).
- A test asserting no entry snapshot is taken for a `prepatch_check`-guarded
  state that does not also set `tamper_guard`.
- Tests for `base_branch` unset → `"main"`, and for a non-default
  `automation.worktree_base` being honored.
- A memo-invalidation test: identical `step_diff` against a changed `base_ref`
  must re-run rather than reuse.
- A reaper-predicate negative test: `prepatch-experiment` is still rejected by
  `_is_ll_worktree()` / `_is_ll_branch()`.
- A test asserting the `prepatch_evidence` row is written and readable by
  `read_prepatch_evidence(issue_id)`, plus the never-raises contract on a
  missing DB / unknown ID.
- Tests for the three degrade-don't-fail rules: absent `issue_id` (falls back to
  merge-base and still runs), absent/empty `run_dir` (skips the file write, still
  writes the row), and `base_branch` resolution from `parallel.base_branch`.
- Tests for guard ordering: prepatch runs before `_check_tamper_guard` at both
  exit call sites, both records land before either routes, and tamper-guard wins
  the route when both want it.
- A test asserting two consecutive guarded exits with a byte-identical
  `step_diff` create only one worktree, with the second record carrying
  `"memoized": true`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — new `TestPrePatchCheckExecutorHook`
  class (place near `TestTamperGuardExecutorHook`, `:11225`), one test per
  parity target: `test_fail_policy_routes_to_on_no_when_...`,
  `test_allow_policy_proceeds_despite_...`, `test_no_guard_when_key_absent`,
  `test_tdd_mode_does_not_trip_guard_on_separate_verify_state`,
  `test_fail_policy_blocks_convergent_routing`,
  `test_fail_policy_blocks_next_chained_state`,
  `test_evidence_accumulates_across_guarded_states` — adapted for
  `read_base_sha()` / `run_prepatch_check()` / `ctx.context["_prepatch_check"]`
  / `PrePatchEvidence` in place of the tamper-guard equivalents.
- `scripts/tests/test_fsm_validation_evaluator_rules.py` — new
  `TestPrePatchCheckValidation` class (place near `TestTamperGuardValidation`,
  `:1242`), mirroring `test_fires_for_state_with_unrecognized_value`,
  `test_fires_for_unrecognized_loop_level_default`,
  `test_does_not_fire_for_recognized_values`, `test_does_not_fire_when_unset`,
  `test_suppressed_by_..._ok`, `test_wired_into_validate_fsm`, and a
  `prepatch_check` analog of `test_tamper_guard_recognized_as_top_level_key`
  (`:1318`).
- `scripts/tests/test_feat3033_idle_timeout.py:60-61` —
  `test_default_idle_timeout_is_known_top_level_key` is the membership-check
  template (`assert "default_idle_timeout" in KNOWN_TOP_LEVEL_KEYS`) to mirror
  for `test_prepatch_check_is_known_top_level_key` / `..._ok`; no existing test
  does full set-equality on `KNOWN_TOP_LEVEL_KEYS`, so nothing else breaks.
- `scripts/tests/test_fsm_schema.py:4571-4579` —
  `test_schema_json_declares_state_and_loop_level_tamper_guard` is the
  round-trip template for a parallel assertion (or extension) confirming
  `prepatch_check` is declared in `fsm-loop-schema.json` at both levels.
- Confirmed safe / no change needed: `scripts/tests/test_builtin_loops.py`
  has no byte/hash-level assertion on `code-run-gate.yaml`, `rn-implement.yaml`,
  `rn-remediate.yaml`, or `rn-refine.yaml` — all references parse structural
  fields, not raw content, so leaving those YAMLs unmodified needs no test
  update.

### Related Issues

- `ENH-2991` (blocking) — the gate core this hosts.
- `ENH-2998` (dependent) — non-FSM adapter and the harness consumer that reads
  the bundle this host writes.
- `ENH-2854` (peer) — supplies the guarded-window mechanism; ordering constraint
  documented above.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` § "Tamper Guard" (`:666-704`) — the actual
  user-facing FSM-YAML authoring section for `tamper_guard:` (worked YAML
  example, policy-value table, entry-snapshot-timing note, `ll-loop validate`
  cross-reference). A parallel `### Pre-Patch Check` section belongs
  immediately after it. `docs/ARCHITECTURE.md` and `docs/reference/API.md`
  (cited generically elsewhere in this issue) currently contain zero mentions
  of `tamper_guard` or the guarded-window mechanism — this file, not those, is
  the precise existing anchor to mirror.
- `docs/reference/CLI.md` — under `#### \`ll-loop validate <loop>\`` (`:786`),
  the validation-rules bullet list has a dedicated tamper-guard bullet
  ("Tamper-guard value validity (WARNING)", `:814`) in a uniform
  severity/suppress-flag/issue-ID format. The new lint rule needs a sibling
  bullet here.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` § "The Design Rules" table — has
  a dedicated `tamper-guard` row (`:111`, severity + suppress flag
  `tamper_guard_ok: true`). `.claude/CLAUDE.md` § Loop Authoring points readers
  here as "the full rule table" — the new lint rule needs a parallel row, not
  just the CLI.md bullet.
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — § "How They Connect" → "1.
  Outcome-token handoff" (`:240-254`) documents the
  `${run_dir}/subloop_outcome_<ID>.txt` sidecar contract this issue's AC
  requires exposing the bundle through; the `summary.json` `per_issue` record
  shape (`:400-405`) is the schema to extend if the bundle needs to surface
  through per-issue aggregation rather than sitting alongside as a separate
  run-dir artifact.
- `docs/reference/loops.md:860` — MR-3's enumerated list of required
  `${context.run_dir}/` artifacts for `code-run-gate.yaml`
  (`commands.json`, `build.txt`, ..., `subloop_outcome_<ID>.txt`). The new
  `PrePatchEvidence` bundle path is a natural addition to this enumeration —
  documentation of the run-dir contract, not a change to the loop file itself
  (which stays unmodified per this issue's Scope Boundaries).
- FYI, no change expected: `skills/audit-loop-run/SKILL.md:341,344` pattern-
  matches on whether a shared next-state's action "contains
  `subloop_outcome_`" for its laundering-mitigation heuristic — a consumer of
  the token channel's presence, not content. Relevant only if the bundle's
  exposure mechanism changes how the token string itself is written, which
  this issue's design (bundle "alongside" the token file) does not do.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Missing file in the Integration Map**: `scripts/little_loops/fsm/validation/_base.py:79-134`
  declares `KNOWN_TOP_LEVEL_KEYS`, the allow-list a loop-level key must join or a
  separate "unknown top-level key" structural check flags the new key itself as
  unrecognized (`"tamper_guard"`/`"tamper_guard_ok"` are already listed at
  `:121-122`). There is no equivalent state-level key allowlist in this codebase
  (a state-level key needs no such registration).
- **The guarded-window bracket is two coordinated call sites, not one wrapper.**
  In `_execute_state`, the entry snapshot is taken once
  (`fsm/executor.py:1450-1458`, gated on `_tamper_policy is not None and
  state.action and self._action_mode(state) != "contract"`), but the exit
  compare (`_check_tamper_guard`) is invoked from *two* independent spots that
  must both be extended: inside the `state.next:`-chained branch
  (`executor.py:1481-1488`, before exit-code routing) and in the non-`next:`
  path after `self._evaluate(...)` (`executor.py:1534-1541`). This split exists
  because an earlier version only guarded one shape (BUG-2962); a state with a
  bare `next:` and no `on_yes`/`on_no` (e.g. `resolve_commands`) only goes
  through the first path.
- **The absent-means-skip resolver is duplicated, not shared, across two
  layers** — `_effective_tamper_guard_policy` in `fsm/executor.py:1295-1312`
  (runtime resolution: `state.tamper_guard or self.fsm.tamper_guard`, any
  unrecognized value silently returns `None`) and a second, independent
  `_effective_tamper_guard` in `fsm/validation/evaluator_rules.py:371-375`
  (lint-time resolution, same precedence, no shared helper function). A new
  key following this template needs both resolvers written, each in its own
  layer.
- **Lint severity convention**: `_validate_tamper_guard`
  (`fsm/validation/evaluator_rules.py:368-421`, registered at
  `fsm/validation/structural_rules.py:49,1109`) emits
  `ValidationSeverity.WARNING`, not `ERROR` — an unrecognized guard value is
  caught but doesn't block load. It checks the loop-level default once and each
  state's own override only (never a state's *inherited* value, which would
  duplicate one bad loop-level default across every non-overriding state).
- **`rn-implement`'s reachability to `code-run-gate` is transitive, not
  direct.** `rn-implement.yaml` has no `run_code_gate` state and does not
  reference `code-run-gate`/`run_code_gate` by name anywhere except one code
  comment (`:993`). It delegates to `rn-remediate` via a `loop: rn-remediate`
  sub-loop state (`~:755`), and `rn-remediate.yaml`'s own `run_code_gate` state
  (`:529-546`) is what delegates to `oracles/code-run-gate.yaml` (`:543`). The
  Motivation section's phrase "`rn-implement`'s `run_code_gate`" should be read
  as this transitive path, not a state literally inside `rn-implement.yaml`.
- **Existing test coverage to extend, beyond `test_tamper_guard.py`**:
  `scripts/tests/test_fsm_executor.py`'s `TestTamperGuardExecutorHook` class
  (`~:10702`) is the executor-integration test tier — it builds a real git repo
  and a real `FSMExecutor.run()` (no mocked FSM layer), with dedicated,
  individually-named tests for the absent-key skip
  (`test_no_guard_when_key_absent`) and for `ctx.context` record-shape
  accumulation (`test_evidence_accumulates_across_guarded_states`, asserting a
  list of length 2 with per-entry `"state"`/`"findings"`/`"passed"` keys).
  `scripts/tests/test_fsm_validation_evaluator_rules.py`'s
  `TestTamperGuardValidation` class (`~:1242`) is the lint-rule test tier,
  including `test_tamper_guard_recognized_as_top_level_key` — a YAML-round-trip
  test asserting the key doesn't trip the `KNOWN_TOP_LEVEL_KEYS` check above. A
  new key should get one test class per tier, mirroring this split.

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Blocking dependency has changed since this issue was last refined (2026-08-02), and has since resolved (2026-08-12).** ENH-2991 (the check this issue hosts) is `status: done`, but its own `## Resolution` records `**Status**: Decomposed` — it shipped no code. The actual work landed in two children, ENH-3141 (`setup_prepatch_worktree()`) and ENH-3142 (`prepatch_check.py` core, `depends_on: [ENH-3141]`) — both are now `status: done` and `run_prepatch_check()` ships in `prepatch_check.py:376-387`. ENH-2997 carries no `blocked_by` frontmatter and is unblocked; see § Scope Boundaries.
- **Stale line numbers (verified 2026-08-10, `fsm/executor.py` changed 2026-08-09 after this issue's last refine):**
  - `_effective_tamper_guard_policy` — now `fsm/executor.py:1344-1361` (was cited as part of `1295-1384`).
  - `_check_tamper_guard` — now `fsm/executor.py:1385-1455`.
  - Entry snapshot call site — now `fsm/executor.py:1499-1507` (was `~1450-1458`).
  - Exit compare call sites — now `fsm/executor.py:1534-1538` (`next:`-chained branch) and `fsm/executor.py:1587-1591` (non-`next:` path after `self._evaluate(...)`) (were `~1481-1488` and `~1534-1541`).
  - `ctx.context["_tamper_guard"]` accumulation — `fsm/executor.py:1433` (`ctx.context.setdefault("_tamper_guard", []).append(tamper_record)`).
  - State-level `tamper_guard` field — now `fsm/schema.py:698` (was cited as `:1311`).
  - Loop-level `tamper_guard`/`tamper_guard_ok` fields — now `fsm/schema.py:1323,1325` (was cited as `:690`).
  - `TestTamperGuardExecutorHook` — now `scripts/tests/test_fsm_executor.py:11225` (was `~:10702`).
  - `TestTamperGuardValidation` — confirmed current at `scripts/tests/test_fsm_validation_evaluator_rules.py:1242`.
- **`_tamper_guard_candidate_paths`/`_tamper_guard_changed_files`** (`fsm/executor.py:1363-1372`, `:1374-1383`) are thin delegators into `little_loops.test_tamper_guard`'s shared `tamper_guard_candidate_paths()`/`tamper_guard_changed_files()` — the diff-computation primitives are already shared between the FSM executor and the non-FSM `work_verification.py` hook (ENH-2998's territory). A new `prepatch_check` key's diff computation should reuse this same shared layer rather than reimplementing it.
- **`work_verification.py`** (`scripts/little_loops/work_verification.py`) is the non-FSM parallel to this issue's executor hook — its own `_effective_tamper_guard_policy(config: BRConfig)` (line 60) and `_run_non_fsm_tamper_guard(...)` (line 76) are architecturally analogous but out of this issue's scope (ENH-2998 owns that host).

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **A third and fourth example of the loop+state+`_ok`+lint-rule shape exist beyond `tamper_guard`** — `session_mode` (`fsm/schema.py:1329,1331`, resolver `_effective_session_mode` at `fsm/validation/_base.py:187-195`, lint rule `_validate_session_mode_evaluator_inheritance` at `fsm/validation/evaluator_rules.py:506-548`, `KNOWN_TOP_LEVEL_KEYS` entries at `fsm/validation/_base.py:124-125`) and `pruning_profile` (`fsm/schema.py:1320`). Both share tamper_guard's loop-level-default/state-level-override/`_ok`-suppression/paired-lint-rule shape, but their executor enforcement is a **value read at read-time** to gate continuity/prompt behavior (`fsm/executor.py:1799,1801,2084,2112`), not a **snapshot-on-entry/compare-on-exit bracket**. `tamper_guard` remains the only prior example of the entry/exit-bracket shape this issue needs — the other two do not suggest a different convention for a check that must diff a guarded state's action.
- **No shared FSM-fixture/`_fsm()` test helper exists across guard-key test suites** — each test class defines its own local `_fsm()` builder scoped to its own construction needs (`TestTamperGuardExecutorHook._fsm`, `test_fsm_executor.py:11295`; `TestSessionModeEvaluatorInheritance._fsm`, `test_fsm_validation_evaluator_rules.py:547`; `TestHostGuardConfig._fsm`, `test_host_guard.py:602`; others at `test_fsm_executor.py:201,295,7069,7253`). A new `prepatch_check` test class should define its own `_fsm()` following this per-class convention, not attempt to reuse or extract a shared one.
- **`KNOWN_TOP_LEVEL_KEYS` membership testing has two co-existing, non-superseding shapes**: (a) a bare `assert "key" in KNOWN_TOP_LEVEL_KEYS` (`test_feat3033_idle_timeout.py:60-61`) — confirmed as the only membership-assert example in the suite, and already the lightest possible form; (b) a fuller pair for `tamper_guard` specifically — a YAML-round-trip test asserting no unknown-key warning fires (`test_tamper_guard_recognized_as_top_level_key`, `test_fsm_validation_evaluator_rules.py:1318-1338`) plus a JSON-schema-dict-membership assertion (`test_schema_json_declares_state_and_loop_level_tamper_guard`, `test_fsm_schema.py:4571-4579`). No test performs full set-equality on `KNOWN_TOP_LEVEL_KEYS`.
- **Spec-only forward reference to `run_prepatch_check()` had no in-repo staging precedent as of 2026-08-10** — at that time a repo-wide grep for `run_prepatch_check` returned zero hits under `scripts/` (issue-file mentions only), and no stub function, `NotImplementedError` placeholder, or feature flag precedent existed for building an executor hook against a not-yet-existing function. That gap is now closed: ENH-3142 landed on 2026-08-12 and `run_prepatch_check()` is a real, callable function at `prepatch_check.py:376-387`. This issue is no longer blocked and this observation is historical context only, not a live constraint.

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Stale line citation, minor**: `KNOWN_TOP_LEVEL_KEYS` entries for `"tamper_guard"`/`"tamper_guard_ok"` are now at `fsm/validation/_base.py:122-123` (verified 2026-08-10), not `:121-122` as an earlier refine pass cited (line 322-327 above). The containing block range `:79-134` cited elsewhere in this issue is still accurate.
- **JSON-schema property requirement is precedented, not just mirrored**: ENH-2934's own decision rationale (`.issues/enhancements/P2-ENH-2934-tamper-guard-fsm-adapter.md:181-244`, "Option A vs Option B") establishes the actual rule this codebase applies for whether a new guard key needs an explicit `fsm-loop-schema.json` property — not every loop-level key gets one. `session_mode` has zero entries in `fsm-loop-schema.json` (confirmed by grep) because its validator only checks inheritance shape; `tamper_guard` and `pruning_profile` both got explicit schema properties (loop + state level, with an `"enum"` constraint) because each pairs with a dedicated enum-validity WARNING validator. Since this issue's Proposed Change item 6 specs a `prepatch_check` lint rule that mirrors `tamper_guard`'s value-validity check (not a `session_mode`-style inheritance-shape check), it falls in the "needs an explicit schema property" bucket — this confirms, rather than changes, the Wiring Phase's existing `fsm-loop-schema.json` requirement.

## Program Design

### Call Path

FSM host: executor guarded-window exit hook -> `read_base_sha` -> `run_prepatch_check` -> `collect_candidate_nodeids` -> `filter_test_files`

The host resolves `(base_sha, base_dirty)` and passes them in; the core is
database-free. The host records its verdict in `ctx.context` following ENH-2854's
`_tamper_guard` record shape and writes the full `PrePatchEvidence` bundle under
`${context.run_dir}/` (MR-3).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Failure-routing contract for `_check_prepatch_check` to replicate**: `_check_tamper_guard` (`fsm/executor.py:1447-1455`) does not use a single lookup — it chains three tiers: (1) `state.on_no` if `state.on_no in get_failure_states()` (`fsm/schema.py:1618-1627`, a `{name for name, state in self.states.items() if state.failure}` comprehension); (2) else `sorted(get_failure_states())[0]` — the lexicographically-first failure-flagged state in the whole FSM, not a semantic "closest" one; (3) else bare `state.on_no` (may be `None`). A new prepatch-check checker must replicate all three tiers, not just tier 1, to cover both loops with a per-state `on_no` failure target and loops with only a shared `failure: true` terminal.
- **Return-value contract**: both call sites (`fsm/executor.py:1534-1538`, `:1587-1591`) do `if _tamper_next is not None: return _tamper_next` — an unconditional early `return` from `_execute_state` that skips all subsequent bookkeeping in that function (exit-code branching, `_evaluate`, `prev_result`/stall-detector updates at `:1596-1674` for the non-`next:` path). The returned string flows straight through the run loop (`fsm/executor.py:689,748-763,766-798`) with no membership check against `self.fsm.states` at assignment time — it relies on load-time validation (`fsm/validation/structural_rules.py:970-982`, `get_referenced_states()` includes `on_no`) to guarantee the target exists; a new checker inherits this same guarantee only if it returns exclusively `state.on_no` or a member of `get_failure_states()`, never a hand-constructed string.
- **`_tamper_guard` record shape to mirror** (`fsm/executor.py:1423-1433`): `{"state": str, "policy": Literal["revert","fail","allow"], "passed": bool, "findings": [{"path": str, "kind": str, "is_config": bool}, ...], "reverted": list[str]}`, appended via `ctx.context.setdefault("_tamper_guard", []).append(record)` — one record per guarded-state execution, list never overwritten. A `"_prepatch_check"` accumulator follows the identical `setdefault(KEY, []).append(record)` shape under its own key to coexist without collision.
- ~~**No existing timeout-config surface for this call site**~~ — **obsolete as of ENH-3142 landing (2026-08-12).** This note assumed `run_prepatch_check(..., timeout_s: int)` and worried about introducing a new timeout knob at this call site. The shipped core takes **no `timeout_s` parameter**: the time box is read from `config.prepatch_check.timeout_s` (`config/features.py:1066`, default 300) and applied inside `_run_pytest()`, with the timeout surfacing as `category="timeout"` on the affected outcomes rather than as an exception the host must catch. There is no new host-side timeout surface to design. Retained struck-through because the surrounding notes reference it.

_Added by `/ll:refine-issue` — 2026-08-12 — based on codebase analysis:_

- **Full independent re-verification (2026-08-12) confirms all Types/Signatures/Call Path/Schema Anchors citations in this section are current** against the shipped codebase — `run_prepatch_check()` (`prepatch_check.py:376-387`), `PrePatchEvidence`/`PrePatchTestOutcome`/`PrePatchCandidate` (`prepatch_check.py:42-97`), `history_reader.read_base_sha()`/`read_base_dirty()` (`history_reader.py:1816-1918`), the executor call-site line numbers (`:1344-1361`, `:1385-1455`, `:1499-1507`, `:1534-1538`, `:1587-1591`), the schema anchors (`fsm/schema.py:698`, `:801-802`, `:911`, `:1323,1325`, `:1445-1448`, `:1577-1578`), and `KNOWN_TOP_LEVEL_KEYS` at `fsm/validation/_base.py:122-123`. No functional drift found; see § Design Notes for two cosmetic line-range corrections (`worktree_utils.py`, `evaluator_rules.py`) that don't affect this section's own citations.

### Types

_Updated 2026-08-12 — ENH-3142 has landed; these are the shipped types, not specs._

- `PrePatchEvidence` (`prepatch_check.py:77-97`) — `base_ref: str`,
  `base_source: str` (`"dequeue-stamp" | "merge-base"`), `base_dirty: bool | None`,
  `outcomes: list[PrePatchTestOutcome]`, `verdict: str`
  (`"clean" | "flagged" | "skipped"`), `skipped_reason: str | None`. Ships a
  `to_dict()` following the codebase's nested-list-comprehension convention, so
  the run-dir bundle write and ENH-2998's JSON surfacing need no new serializer.
- `PrePatchTestOutcome` (`prepatch_check.py:52-74`) — per-test record carrying
  `category` (`pass | fail | error | timeout | flaky`) and `flag`
  (`hard | soft | none`) with `flag_reason`. The `hard`/`soft` distinction is
  what the policy mapping in § Design Notes keys off.
- `PrePatchCandidate` (`prepatch_check.py:42-49`) — pre-run identification only;
  the host does not touch it.

### Signatures

_Updated 2026-08-12 — supersedes this issue's earlier 4-argument spec citation._

- `run_prepatch_check(*, step_diff: str, repo_root: Path, worktree_base: str | Path, base_sha: str | None, base_dirty: bool | None, base_branch: str, logger: Logger, git_lock: GitLock, config: BRConfig | None = None) -> PrePatchEvidence`

  Shipped at `prepatch_check.py:376-387` — **keyword-only, nine parameters.** Earlier revisions of this issue cited `(step_diff, base_sha, base_dirty, timeout_s)`, which is not callable against the shipped function: `timeout_s` is not a parameter (it comes from `config.prepatch_check.timeout_s`), and `repo_root`/`worktree_base`/`base_branch`/`logger`/`git_lock` are required with no defaults. See § Design Notes → "Host-supplied arguments" for where each value comes from at the guarded-window call site.
- `resolve_base_ref(repo_root: Path, base_sha: str | None, base_branch: str) -> tuple[str, str]`
  — **to be created by this issue** by promoting the inline resolution at
  `prepatch_check.py:398-403` (`base_sha` → `("<sha>", "dequeue-stamp")`, else
  `(_merge_base(repo_root, base_branch) or base_branch, "merge-base")`). No
  public equivalent exists: `prepatch_check.py` declares no `__all__` and
  `_merge_base` (`:240`) is private, so the host currently has no supported way
  to learn the ref before calling the core. See § Design Notes.
- `setup_prepatch_worktree(repo_path, worktree_base, base_ref, test_files, logger, git_lock, src_dir=None) -> Path` (`worktree_utils.py:329-337`) — called transitively by the core; relevant to the host only because it is what leaks a worktree and branch absent host-side cleanup.
- `history_reader.read_base_dirty(issue_id: str, *, run_id: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> bool | None` (`history_reader.py:1872-1918`) — **now exists** (shipped with ENH-3142); the additive sibling of `read_base_sha` this issue's earlier revisions listed as unimplemented. Same never-raises contract, returns `None` when the DB is missing/unreadable, no row matches, or the column is NULL; converts the stored int to `bool`.
- `history_reader.read_base_sha(issue_id: str, *, run_id: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> str | None` (`scripts/little_loops/history_reader.py:1816-1869`) — current and verified. Never raises (DB-open failure or `sqlite3.Error` both caught, return `None`); returns `None` when unstamped; implements no merge-base fallback (docstring assigns that to the consumer).
- ~~A `base_dirty` reader alongside `read_base_sha` does not exist yet~~ — **stale; it shipped with ENH-3142.** See `read_base_dirty` above.
- `_effective_tamper_guard_policy(self, state: StateConfig) -> Literal["revert", "fail", "allow"] | None` (`fsm/executor.py:1344-1361`) — the resolver shape a new `_effective_prepatch_check_policy()` would mirror: `state.<key> or self.fsm.<key>`, any unrecognized value collapses to `None`.
- `_check_tamper_guard(self, state, ctx, tamper_before, tamper_policy, repo_root) -> str | None` (`fsm/executor.py:1385-1455`) — the compare-on-exit/record/route-on-fail shape a new `_check_prepatch_check()` would mirror.

### Call Path (current, verified 2026-08-10 — supersedes the issue's original stale citations)

`_execute_state` entry (`fsm/executor.py:1499-1507`, resolves `_effective_tamper_guard_policy`, snapshots before action runs) -> action executes -> exit compare from one of two call sites: `next:`-chained branch (`fsm/executor.py:1534-1538`) or non-`next:` path after `self._evaluate(...)` (`fsm/executor.py:1587-1591`) -> `_check_tamper_guard` (`fsm/executor.py:1385-1455`) appends to `ctx.context["_tamper_guard"]` (`:1433`) and, on `policy: fail` with a finding, routes to `state.on_no` or the FSM's failure terminal.

A `prepatch_check` key follows the identical two-call-site bracket, with its own resolver/checker pair calling into `history_reader.read_base_sha()` / `read_base_dirty()` (both shipped with ENH-3142), producing the cumulative patch diff via `_prepatch_step_diff(repo_root, base_ref)`, then calling `run_prepatch_check()` (`prepatch_check.py:376-387`). Its checker is invoked **before** `_check_tamper_guard` at both sites — see § Design Notes → "Ordering against ENH-2854."

### Schema Anchors (current, verified 2026-08-10 — supersedes the issue's original stale `:690`/`:1311` citations)

- State-level `tamper_guard` field (the template to mirror): `StateConfig.tamper_guard: str | None = None`, `fsm/schema.py:698` (declaration), `:801-802` (`to_dict`), `:911` (`from_dict`).
- Loop-level `tamper_guard` field + suppression companion: `FSMLoop.tamper_guard: str | None = None` and `tamper_guard_ok: bool = False`, `fsm/schema.py:1323,1325` (declaration), `:1445-1448` (`to_dict`), `:1577-1578` (`from_dict`).
- `KNOWN_TOP_LEVEL_KEYS` entries for the loop-level key + its `_ok` companion: `fsm/validation/_base.py:79-134` (currently lists `"tamper_guard"`/`"tamper_guard_ok"`; a new loop-level key needs the same pair added here).

### Decision Rules

One new mapping, specified in full in § Design Notes → "Policy values and
verdict mapping": policy `fail | warn | allow` × core verdict `clean | flagged |
skipped` → route / don't route, where only (`fail`, `flagged`) routes and
`flagged` itself requires at least one `hard`-flagged outcome. No new gap kind,
keyword list, or threshold — the thresholds live in the ENH-3142 core.

## Scope Boundaries

- **Not this issue**: the check itself — `prepatch_check.py`'s core is
  ENH-3142, `setup_prepatch_worktree()` is ENH-3141, and the `base_dirty`
  reader shipped with ENH-3142 (ENH-2991 shipped no code; it was decomposed
  into these two children). **All three are now `done`; this issue is
  unblocked.**
- **In scope despite belonging to the core's blast radius**: tearing down the
  pre-patch worktree/branch, and widening `_is_ll_worktree()`/`_is_ll_branch()`
  to reap them. The core does not clean up after itself on the success path and
  no other issue owns this; leaving it unowned means executor-hosted invocations
  leak a worktree per guarded-state exit.
- **Adding one loop-level or state-level `prepatch_check:` key line to
  `code-run-gate.yaml` is in scope** — see the rejected-placement boundary
  below, which concerns states, not keys.
- **Not this issue**: the non-FSM `work_verification.py` adapter, `cli/harness.py`
  evidence surfacing, or `skills/verify-issue-loop/` documentation — all ENH-2998.
- **Not this issue**: adding a *state* to `oracles/code-run-gate.yaml`. The
  superseded 2026-07-30 oracle-state placement is explicitly rejected. That
  rejection covers states with their own action and routing — it does not cover
  the one-line guard-key declaration this issue adds, which is the same opt-in
  shape `tamper_guard: fail` already uses at `:50`.
- **Not this issue**: replacing or removing the existing LLM-judged semantic
  criteria in verification loops.

## Acceptance Criteria

- [ ] The check is hosted on the executor's guarded-window mechanism (the shape ENH-2854 established in `fsm/executor.py`: resolver `:1344-1361`, exit-compare/checker `:1385-1455`, invoked from call sites `:1534-1538` and `:1587-1591`), not as a state inside `oracles/code-run-gate.yaml` and not inside `cli/harness.py`. **A resolver and an exit hook only — no entry snapshot is added for `prepatch_check`**; the entry site (`:1499-1507`) stays keyed on `_tamper_policy` alone, and a test asserts a guarded `prepatch_check` state takes no entry snapshot.
- [ ] The exit hook invokes the core **only on the green path** (the guarded state's action succeeded / routes to `on_yes`); on a failed action it records a skip and routes nothing. A test asserts a red guarded state forks no worktree.
- [ ] `prepatch_check.resolve_base_ref(repo_root, base_sha, base_branch)` is public, and **both** `run_prepatch_check()` and the executor host resolve `base_ref` through it; a test asserts the ref the host computes `step_diff` against equals `PrePatchEvidence.base_ref` returned by the same invocation, on both the `dequeue-stamp` and `merge-base` paths.
- [ ] No *state* is added to `oracles/code-run-gate.yaml`; a test asserts its state set is unchanged. The file gains exactly one `prepatch_check:` key line (loop level, or state level on `run_test`).
- [ ] A first-class FSM key is settable at loop level and state level, mirroring `tamper_guard`'s declaration in `fsm/schema.py`, with the enum `fail | warn | allow` declared in `fsm-loop-schema.json`.
- [ ] The check is reachable from the `rn-*` family's green-suite transitions; a test asserts a guarded loop (`rn-implement` / `rn-remediate` / `rn-refine`, transitively via `code-run-gate`) actually runs the check.
- [ ] `verdict == "flagged"` under `policy: fail` routes to the failure target; a bundle whose outcomes carry only `soft` flags does not route, and neither does `verdict == "skipped"`. Tests cover all three.
- [ ] The host records its verdict in `ctx.context` following ENH-2854's `_tamper_guard` record shape, accumulating findings across guarded states.
- [ ] The full `PrePatchEvidence` bundle is written to `${context.run_dir}/prepatch_evidence_<issue_id>.json` (MR-3) **and** persisted to `.ll/history.db` — the latter is the only surface ENH-2998's `run_dir`-less `cli/harness.py` consumer can discover — and is exposed through the existing parent↔sub-loop token channel.
- [ ] The `step_diff` passed to `run_prepatch_check()` is the cumulative patch diff (`git diff <base_ref>`), not the guarded state's entry→exit delta; a test asserts that for a run whose patch added a test file, the diff reaching the core is non-empty and `collect_candidates()` returns at least one candidate. (Guards against the inert-gate failure mode in § Design Notes.)
- [ ] `step_diff` includes **untracked** non-ignored files (`git ls-files --others --exclude-standard`, emitted as `git diff --no-index -- /dev/null <path>` fragments), so a newly added, not-yet-committed test file becomes a candidate. **The anti-inert-gate test above must use an untracked added test file** — a committed-file variant passes without this rule and leaves the hole open. A second test asserts the live repository's index is unmodified by diff production (no `git add -N`).
- [ ] A `prepatch_evidence` table, its writer, and `history_reader.read_prepatch_evidence(issue_id)` exist; a test asserts a guarded-state exit writes a readable row, and that the reader returns `None` (never raises) on a missing DB or unknown issue ID.
- [ ] When `issue_id` is absent from the FSM context, the check still runs against the merge-base fallback (`base_source == "merge-base"`) rather than skipping; a test covers it.
- [ ] When `run_dir` is absent or empty, the run-dir bundle write is skipped without crashing and without failing the gate — the `history.db` row is still written; a test covers it.
- [ ] `base_branch` is resolved from `parallel.base_branch` in `.ll/ll-config.json`, **falling back to `"main"` when the field is null/unset** (matching `config/core.py:674`); tests cover both the configured and the unset case, asserting the resolved value reaches the core.
- [ ] `worktree_base` is resolved via `BRConfig.get_worktree_base()` rather than a hardcoded `.worktrees/`; a test asserts a non-default `automation.worktree_base` is honored and that the fork lands outside `run_dir`.
- [ ] The prepatch checker runs before `_check_tamper_guard` at **both** exit call sites, both checkers record their `ctx.context` entry before either routes, and when both want to route the tamper-guard target wins; tests cover the ordering and the precedence rule.
- [ ] Repeated guarded exits within one run whose **`(step_diff hash, base_ref)` pair** is identical reuse the prior verdict (recorded with `"memoized": true`) instead of re-forking a worktree; a test asserts only one worktree is created across two identical-diff exits, and a second test asserts an identical diff against a *changed* `base_ref` does **not** hit the memo.
- [ ] The pre-patch worktree and its branch are torn down on both the success and exception paths (`try/finally` + `cleanup_worktree(..., delete_branch=True)`); a test asserts neither survives a guarded-state exit.
- [ ] `_is_ll_worktree()` / `_is_ll_branch()` accept the `prepatch-<timestamp>` naming via an **anchored** `^prepatch-\d{8}-\d{6}-\d{6}$` so `/ll:cleanup-worktrees` reaps crash leftovers; tests assert both accept a real `setup_prepatch_worktree()` name and both still **reject** a hand-made `prepatch-experiment`.
- [ ] When the check's key is absent (no state override, no loop default), the guarded window short-circuits to SKIP rather than failing the gate; a test covers it.
- [ ] When the key is present but `prepatch_check.enabled` is `false` (the config default), the run is recorded as a skip with the core's `skipped_reason` and never fails the gate; a test covers it.
- [ ] The host resolves the base via `history_reader.read_base_sha(issue_id)` / `read_base_dirty(issue_id)` and passes both in as arguments, along with `repo_root`, the config-resolved `worktree_base`, `base_branch`, a locally constructed `Logger(verbose=False)`, and a locally constructed `GitLock` (per `fsm/executor.py:929-940`); a test asserts every one of the core's nine keyword-only parameters is supplied explicitly by the host — i.e. the core is never left to discover `base_sha`/`base_dirty` itself. (Replaces an earlier, untestable "the core performs no database access" phrasing; the core's DB-free property is ENH-3142's to guarantee, not this issue's to re-assert.)
- [ ] A `ll-loop validate` lint rule mirroring ENH-2854's catches misuse of the new key.
- [ ] ENH-2854's tamper-guard `revert` policy runs after this check has read the step's diff when both are active on the same window.

## Impact

- **Priority**: P2 — without this, ENH-2991's core is unreachable from any
  production verification path and the hole stays open.
- **Effort**: Large — matching `size: Large` in frontmatter (an earlier
  "Medium" here contradicted it). Revised upward twice on 2026-08-12: first for
  worktree teardown and the reaper-predicate widening, then again for the two
  gaps found in the pre-implementation review — the `step_diff` producer (no
  diff-string producer exists anywhere in the codebase) and the entire
  `.ll/history.db` persistence surface (table + writer + reader, none of which
  exists and neither sibling issue owned).
- **Risk**: Medium — touches the FSM executor's guarded-window path, which
  `tamper_guard` shares. The SKIP-when-absent convention plus the `enabled:
  false` config default are what keep existing loops unaffected. Two non-obvious
  risks: (a) **a silently inert gate**, which has *two* distinct causes — if
  `step_diff` is sourced from the guarded state's own delta rather than the
  cumulative patch diff, **or** if it is sourced from a bare `git diff
  <base_ref>` that cannot see untracked new test files — either way every
  invocation returns `verdict="skipped"` while all reachability tests pass
  green; (b) **runtime cost** — each invocation forks a worktree and runs pytest
  up to twice under a 300s box, multiplied by outer-loop iteration count, which
  the `(step_diff hash, base_ref)` memo and the green-path gate are jointly
  scoped to contain.
- **Scope note (2026-08-12, third review pass)**: this issue grew again. The
  `.ll/history.db` persistence surface (table + writer + reader) is the cleanest
  severable piece — it has no dependency on the guarded-window work and ENH-2998
  is its only other stakeholder — and splitting it into a separate issue that
  both ENH-2997 and ENH-2998 depend on would return this one to a reviewable
  size. Not yet decided; recorded here so the option isn't lost.
- **Breaking Change**: No — new optional key, absent means unguarded.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-10; superseded by a manual review pass on 2026-08-12._

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (dependency hard override)
**Outcome Confidence**: 71/100 → MODERATE

### Gaps to Address
- ~~Blocking dependency `ENH-3142` is still `status: open`~~ — **resolved 2026-08-12.** ENH-3141 and ENH-3142 are both `done`; `prepatch_check.py` and `history_reader.read_base_dirty()` exist. The dependency hard override no longer applies.

### Outcome Risk Factors
- Moderate cross-module depth: the guarded-window extension touches `fsm/executor.py`'s two independent exit-compare call sites plus `fsm/schema.py`, `fsm/validation/_base.py`, and `fsm-loop-schema.json` in lockstep — a multi-file, shared-state change even though each site individually mirrors an existing `tamper_guard` template.
- ~~The `PrePatchEvidence` type and `run_prepatch_check()` signature this issue calls are spec-only~~ — **resolved 2026-08-12**; both verified against shipped code, and this issue's § Types / § Signatures have been rewritten to match. The shipped signature is materially wider than the spec this issue was written against (nine keyword-only params, no `timeout_s`), which is the source of most of the corrections in the 2026-08-12 review pass.

### 2026-08-12 Review Pass — resolved before implementation
- **Reachability contradiction (was blocking):** "`code-run-gate.yaml` inherits this check via the loop-level guard key it already carries" was false — it carries `tamper_guard`, not this key. With absent-key-means-SKIP, the file-left-unmodified constraint made the reachability AC unsatisfiable. Resolved by adding one key line (not a state).
- **Worktree leak (was unowned):** the core never cleans up its fork on the success path, and the reaper's name predicates reject `prepatch-*`. Both now in scope here.
- **Policy enum (was undefined):** now `fail | warn | allow` with an explicit verdict/flag mapping, required because the JSON schema needs an `enum` and the lint rule validates value validity.
- **Config default (was unstated):** `prepatch_check.enabled` defaults to `false`, so the key alone is inert; covered by a new AC.

### 2026-08-12 Second Review Pass — two blocking gaps, resolved in-place
Verified against shipped code; both were unowned by any issue.
- **`step_diff` had no producer, and the chosen host cannot be one (blocking).**
  The core needs a unified diff with `+++ b/` headers and `@@` hunks
  (`_parse_diff`, `prepatch_check.py:100-120`); the guarded-window bracket
  yields a *name list* (`tamper_guard_changed_files`,
  `test_tamper_guard.py:175-190`), and a repo-wide grep for `step_diff` hits
  only `prepatch_check.py` itself. On the cost-preferred `run_test` placement —
  a state that edits nothing — the delta is empty and the core short-circuits to
  `verdict="skipped"` every time, so the reachability AC would have passed green
  over an inert gate. Resolved: the host computes `git diff <base_ref>` via a new
  `_prepatch_step_diff()` helper, with a dedicated non-empty-diff AC.
  Consequence: § Motivation's "decisive on the merits" claim was false and has
  been rewritten — the placement now rests on reachability, guard-key
  consistency, and the routing contract.
- **`.ll/history.db` persistence was an AC with no implementation and no owner
  (blocking).** Zero `prepatch` references exist in `history_reader.py` or
  `session_store/`; no table, no column, no writer, and no Integration Map
  entry. ENH-2998 only read the row (`:331`) while elsewhere attributing the
  write to "the adapter" (`:328`) — each issue assumed the other. Resolved:
  ENH-2997 owns it as the first producer (table + writer + reader now in the
  Integration Map); **ENH-2998 should be updated to consume the reader rather
  than imply it owns the write.**
### 2026-08-12 Third Review Pass — three blocking gaps, resolved in-place
All three verified against shipped code before being written up.
- **`git diff <base_ref>` cannot see untracked files (blocking).** The second
  pass fixed the *scope* of `step_diff` (cumulative patch, not step delta) but
  left the *producer* untracked-blind. `_parse_diff` discovers files only via
  `+++ b/` headers (`prepatch_check.py:100-134`), so a newly added, not-yet-
  committed test file — the single highest-value input to a pre-patch check —
  yields no candidate and the core returns `verdict="skipped"`. This re-opens
  the exact inert-gate failure mode the second pass closed, one layer down, and
  the second pass's own anti-inert-gate AC would have certified it green if
  written with a committed file. `tamper_guard_changed_files` already unions
  `git ls-files --others --exclude-standard` for this documented reason
  (`test_tamper_guard.py:175-190`). Resolved: the producer unions untracked
  non-ignored paths as `git diff --no-index` fragments (never `git add -N`,
  which would mutate a shared index), with the AC tightened to require an
  untracked file.
- **No public base-ref resolver exists, making the second pass's own rule
  unimplementable (blocking).** That pass required the diff helper to "take the
  resolved ref, not re-derive it independently," but nothing exposes one: the
  core resolves internally (`prepatch_check.py:398-403`) via the private
  `_merge_base` (`:240`), there is no `__all__`, and the resolved value appears
  only on the returned `PrePatchEvidence.base_ref` — after the call the host
  needs it for. Resolved: promote a public `resolve_base_ref()` used by both
  sides, following the `3a70ba56` promotion precedent.
- **Invocation was never gated on the green path (blocking on cost).** § Summary
  scopes the check to "green-suite transitions," but no AC restricted it, so the
  exit hook would fire on red runs too — a worktree fork plus up to two pytest
  runs whose verdict is discarded, since a red suite routes to remediation
  regardless. Resolved: green-path-only invocation, with an AC and a
  no-worktree-on-red test.
- Also tightened, non-blocking (third pass): `worktree_base` now resolves via
  `BRConfig.get_worktree_base()` rather than a hardcoded `.worktrees/` (it is
  configurable, and is *not* in `ll-init`'s `_GITIGNORE_ENTRIES`, so the
  "already gitignored" rationale was source-repo-only); `base_branch` gains the
  `or "main"` fallback the nullable config field requires; the `GitLock`
  open question is closed by the construct-locally precedent at
  `fsm/executor.py:929-940`; an explicit "no entry snapshot" rule prevents
  wiring a consumerless entry hook; the memo key becomes `(diff hash, base_ref)`;
  the reaper predicates are anchored so `prepatch-experiment` stays unreapable;
  and the untestable "core performs no database access" AC is reframed as
  host-supplies-all-arguments.
- Also tightened, non-blocking: `issue_id` / `run_dir` / `base_branch` now have
  explicit degrade-don't-fail rules with ACs; tamper-guard ordering is pinned in
  code at both exit call sites with a stated precedence rule instead of deferred
  to implementation; a `step_diff`-hash memo is scoped to contain per-iteration
  worktree cost; Effort corrected Medium → Large to match `size: Large`.

## Status

**Open** | Created: 2026-08-02 | Priority: P2

## Session Log
- `/ll:confidence-check` - 2026-08-12T22:08:52 - `3304c67f-cf7c-43ee-ba8b-38fc793be3db.jsonl`
- `/ll:refine-issue` - 2026-08-12T21:55:05 - `66afad60-66e8-4e0f-983b-a602e0661547.jsonl`
- `/ll:refine-issue` - 2026-08-10T20:11:46 - `023c1f3c-d026-451b-8c6a-4b2383d7380c.jsonl`
- `/ll:confidence-check` - 2026-08-10T09:57:39 - `40b2e08b-9835-4e53-8675-e53c294cbfce.jsonl`
- `/ll:reconcile-issue` - 2026-08-10T09:55:49 - `b5382982-7500-4b49-9d05-5f4f4a33c4aa.jsonl`
- `/ll:confidence-check` - 2026-08-10T09:51:48 - `de80fea3-8c54-460f-b1ea-12e8ab77b5be.jsonl`
- `/ll:refine-issue` - 2026-08-10T09:47:54 - `3b2bc154-0af6-4e2e-9a39-37d002e7241d.jsonl`
- `/ll:confidence-check` - 2026-08-10T09:41:22 - `300fd485-89f6-4889-8737-0a649a723a68.jsonl`
- `/ll:verify-issues` - 2026-08-10T09:38:57 - `0b97f898-84d2-461d-8674-160d8b6584bc.jsonl`
- `/ll:wire-issue` - 2026-08-10T09:35:20 - `25755245-dbb7-4d56-9480-5e59248a3c94.jsonl`
- `/ll:refine-issue` - 2026-08-10T09:25:37 - `ac54a579-51fd-4f94-9e74-9f64d18f429b.jsonl`
- `/ll:refine-issue` - 2026-08-02T15:22:31 - `1a6be5be-a3c2-4f65-a811-ac343eeaa258.jsonl`
- `/ll:issue-size-review` - 2026-08-02T13:48:44 - `14957793-c5a3-42c3-8c4e-e15ef7fbe208.jsonl`

## Related Key Documentation

- `docs/ARCHITECTURE.md` — describes the FSM loop engine at a high level; this issue extends the executor's guarded-window mechanism, a core piece of that engine.
- `docs/reference/API.md` — documents `fsm/executor`, `fsm/schema`, and `fsm/validation` directly; this issue's new first-class guard key and lint rule are additions to those exact modules.

## Documentation

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-12 — based on codebase analysis:_

- **`docs/reference/API.md` gained a `little_loops.prepatch_check` module-doc entry on 2026-08-12** (`:101`, plus a full `## little_loops.prepatch_check` reference section at `:8507+` documenting `run_prepatch_check()`, `collect_candidates()`, and flag-policy semantics) — this landed with ENH-3142's core module, not with this issue's own work, and documents the *module* (what the core does), not the *guarded-window hosting* this issue adds. It does not change this section's existing claim: `docs/ARCHITECTURE.md` and `docs/reference/API.md` still contain zero mentions of `tamper_guard` or the guarded-window mechanism (confirmed by grep, 2026-08-12) — `docs/guides/LOOPS_GUIDE.md` remains the correct, and only, existing anchor to mirror for the new `### Pre-Patch Check` section.
