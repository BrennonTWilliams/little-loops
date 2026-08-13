---
id: ENH-2998
title: Non-FSM adapter and pre-patch evidence consumers
type: ENH
priority: P2
status: done
discovered_date: 2026-08-02
completed_at: '2026-08-13T02:21:31Z'
epic: EPIC-2856
parent: ENH-2853
blocked_by: []
labels:
- rework
- verification
testable: true
size: Large
verify_verdict: VALID
relates_to:
- ENH-2997
confidence_score: 95
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-2998: Non-FSM adapter and pre-patch evidence consumers

## Summary

Give the pre-patch check coverage on the non-FSM orchestration paths
(`ll-auto`, `ll-parallel`) via an adapter in `work_verification.py`, and make
the evidence readable where humans and hand-run tooling look for it —
`cli/harness.py` and `skills/verify-issue-loop/`.

Both consumers read the persisted bundle; neither re-implements the check. The
adapter adds no check logic either, but it is not a one-liner: it requires a
`verify_work_was_done()` signature change and new `GitLock` plumbing (§ Design
Notes → "The adapter is not thin").

## Parent Issue

Decomposed from ENH-2853: Deterministic pre-patch test-failure check in
verification loops. Covers § Proposed Change step 5 (surfacing) and step 7, and
Integration Map Layer 3 plus the `work_verification.py` half of Layer 2.

## Current Behavior

After ENH-3142 (the core, shipped) and ENH-2997 (the FSM host), the check runs
only inside FSM loops. `ll-auto` and
`ll-parallel` reach verification through `work_verification.verify_work_was_done`,
which has no knowledge of it. `ll-harness` reports only a single-check
`HarnessEvalOutcome`, and `/ll:verify-issue-loop` generates only LLM-judged
states.

## Expected Behavior

`work_verification.py` resolves the base state and calls the same
`run_prepatch_check()` core, mirroring how ENH-2854's tamper guard reaches
`issue_manager.py` and `parallel/worker_pool.py`. `cli/harness.py` surfaces the
persisted `PrePatchEvidence` alongside its existing outcome by *reading* the
bundle. `skills/verify-issue-loop/SKILL.md` and `templates.md` document the
deterministic check and when it applies.

## Motivation

ENH-2853's original scope deferred `ll-auto`/`ll-parallel` coverage to a
follow-up issue, purely because the then-prescribed oracle-state host couldn't
reach those callers. ENH-2997's executor-hosted placement inherits ENH-2854's
non-FSM adapter shape, so the path is now a thin wrapper over the same core
rather than a second implementation — which is why that deferral was reversed.

The consumers matter for a different reason: an evidence bundle nobody reads is
not auditable. Surfacing it in `ll-harness` means the check can be inspected
without re-running it.

## Proposed Change

1. **Non-FSM adapter** — add pre-patch invocation to
   `scripts/little_loops/work_verification.py`, resolving `(base_sha, base_dirty)`
   the same way ENH-2997's FSM host does and calling `run_prepatch_check()`.
   Wire it from `issue_manager.py` and `parallel/worker_pool.py`, mirroring
   ENH-2854's existing wiring in those files. **This is not a one-line
   addition** — see § Design Notes → "The adapter is not thin": the shipped
   core needs a `GitLock`, a `worktree_base`, and a `base_branch` that
   `verify_work_was_done()` does not currently have, and its `-> bool` return
   cannot carry a `PrePatchEvidence` out.
2. **Harness consumer** — `cli/harness.py` reads the persisted bundle and reports
   it alongside `HarnessEvalOutcome` in `_evaluate_and_report()`. It does **not**
   call `run_prepatch_check()` itself. The bundle is an additive key set in
   `_evaluate_and_report()`'s JSON branch; mention it in the `--help` epilog.
   Re-locate all four sites by name at implementation time — the line numbers
   this issue originally cited are stale (see § Design Notes). **It reads the
   `.ll/history.db` row, not the run-dir file**: `ll-harness` is hand-run and
   has no `run_dir`, so the database is the only surface it can discover by
   issue ID. ENH-2997 writes both.
3. **Skill documentation** — `skills/verify-issue-loop/SKILL.md` (~L150-165)
   documents only `llm_structured` verify/probe states today. Add a bullet
   describing when the deterministic pre-patch check applies. The
   state-template example goes in `scripts/little_loops/cli/loop/scaffold_verify.py`
   (the generator), **not** `templates.md` — that file is now a stub redirecting
   to `ll-loop scaffold-verify` per FEAT-2948 and holds no hand-written
   templates to extend. This is additive documentation,
   not editing a prohibition: the "no deterministic state type" boundary text the
   original wiring pass cited at SKILL.md lines 211-219 no longer exists after
   the skill's restructuring (verified 2026-07-29; the skill is now 212 lines with
   no `check_invariants`/`check_stall`/`check_concrete` mention).

## Design Notes

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-08-02):_

- **`cli/harness.py` line citations in this issue are stale.** Current
  positions: `HarnessEvalOutcome` is a 3-field dataclass (`passed`, `verdict`,
  `eval_result`) at `harness.py:295-300`; `_evaluate_and_report()` is
  `harness.py:303-369`; its JSON-print branch is `harness.py:335-346`; `_report()`
  (error/timeout-only path, no evaluation outcome flows through it) is
  `harness.py:372-391`; the `--help` epilog is elsewhere in the file — re-locate
  by name rather than by the line numbers cited above/in Integration Map at
  implementation time.
- **Non-FSM baseline resolution today is git-local, not DB-backed.** Neither
  `issue_manager.py` (`_baseline_sha` at `:1022-1027`, a `git rev-parse HEAD`
  captured before Phase 2) nor `worker_pool.py` (`tamper_baseline_sha` at
  `:591`, `self._get_worktree_head_sha(worktree_path)` at `:1639`) currently
  calls `history_reader.read_base_sha()`. `read_base_sha(issue_id, *, run_id=None,
  db=DEFAULT_DB_PATH) -> str | None` exists at `history_reader.py:1816-1821` and
  never raises. ~~No `base_dirty` reader exists yet alongside it~~ — **stale as
  of 2026-08-12**: `read_base_dirty(issue_id, *, run_id=None, db=DEFAULT_DB_PATH)
  -> bool | None` shipped with ENH-3142 (`history_reader.py:1872-1918`), same
  never-raises contract, int→bool converted. Both readers are ready to use
  as-is; only the *call* from the non-FSM path is new.
- **The established FSM-vs-non-FSM split for this check's sibling (tamper
  guard) is: FSM hosts its own adapter directly; the two non-FSM orchestrators
  share one.** `fsm/executor.py:1336`'s `_check_tamper_guard` calls
  `test_tamper_guard.run_tamper_guard()` directly, bypassing
  `work_verification.py` entirely, while `issue_manager.py` and
  `worker_pool.py` both go through the single shared
  `work_verification.verify_work_was_done()` entry point (never the private
  `_run_non_fsm_tamper_guard()` helper at `work_verification.py:63` directly).
  This confirms the shape ENH-2997 (FSM host) and this issue (shared non-FSM
  adapter) already assume, and gives a concrete file (`work_verification.py:146-199`)
  showing where the `config is not None` gate conditionally invokes the
  adapter — the same conditional-gate shape a prepatch-check call would need.
- **Lazy-import discipline applies to any new `prepatch_check` import.**
  `_run_non_fsm_tamper_guard()` (`work_verification.py:96-104`) and
  `worker_pool.py:604-610` both import `test_tamper_guard` symbols
  function-locally, not at module top level, specifically to avoid a
  `test_tamper_guard -> config.core -> parallel.types -> parallel ->
  worker_pool` circular import (documented inline at `worker_pool.py:604-606`).
  Whether the new `prepatch_check` import needs the same treatment depends on
  its own dependency chain once ENH-2991 lands.
- **`skills/verify-issue-loop/templates.md` no longer holds hand-written
  templates.** Per FEAT-2948, the file is now a stub redirecting to
  `ll-loop scaffold-verify` (`scripts/little_loops/cli/loop/scaffold_verify.py`)
  — its own text states "there is nothing left here for an LLM to fill in or
  chain by hand." The Proposed Change/Integration Map's plan to add "a
  state-template example" to `templates.md` needs to target
  `scaffold_verify.py` instead (or `SKILL.md` only) — the concrete precedent
  for a deterministic-vs-`llm_structured` state pairing already exists in that
  file's generated output: the adversarial mode's `count_probes` state uses
  `EvaluateConfig(type="output_numeric", operator="ge", target=3)` chained
  after three `llm_structured` probe states (`scaffold_verify.py:130-145`).
  `skills/create-loop/loop-types.md:145-151` and `:777-808` are the codebase's
  existing convention for documenting an evaluator-type mapping in prose, if
  `SKILL.md`'s bullet follows that shape.
- **No conditional-JSON-key precedent exists in `cli/harness.py` itself.**
  Its JSON branch (`harness.py:335-346`) builds one fixed-key dict; the nearest
  precedent for an *optional* key in a JSON payload is `fsm/executor.py`'s
  `action_complete` event (`:1879-1917`), which does `if <condition>:
  payload["<key>"] = <value>` per optional field with an inline comment noting
  "additive field — existing consumers ... are unaffected" (ENH-2469 pattern).
- ~~**Off-switch shape for the new check is a contested convention**~~ —
  **settled as of ENH-3142 (2026-08-12).** The check ships a `BRConfig`-layer
  off-switch: `config.prepatch_check.enabled` (`config/features.py:1062-1076`,
  default **`False`**), and the core itself honors it by returning
  `PrePatchEvidence(verdict="skipped", skipped_reason=...)` rather than
  omitting the section (`prepatch_check.py:407-414`). The adapter **must not
  add a second off-switch** — it reuses this one, and the default means the
  non-FSM path is inert until a project opts in.
- **Shared skip-flag precedent orders config-gate before override-flag.** The
  learning-gate pattern this issue's Integration Map cites checks
  `if not <config>.enabled: return` first, then the CLI override flag second,
  in both `worker_pool.py:67-71` and `cli/sprint/run.py:215-220` — the same
  ordering, if a comparable skip flag is added for this check, would be the
  established convention to match.

- **Consumers read, never re-derive.** `cli/harness.py` reading the oracle's
  artifact rather than hosting the check is the whole point of the layering — a
  second implementation would drift from the first and the two would disagree on
  the same diff.
- **`_record_harness_event()`** (`harness.py:57-83`) persists a flat single-row
  event, not a multi-test table. The per-test bundle is new structure alongside
  it, not an extension of it.
- **The adapter adds no check logic** — it resolves the base and calls the core.
  Any logic belonging to the check itself belongs in `prepatch_check.py`
  (ENH-3142), where both hosts get it.
- **The adapter is not thin, though (revised 2026-08-12).** Verified against the
  shipped core, `verify_work_was_done()` cannot host this without a signature
  change. Its current shape is `verify_work_was_done(logger, changed_files=None,
  baseline_sha=None, config=None, repo_root=None, pre_step_snapshot=None) ->
  bool` (`work_verification.py:158-165`). Three gaps:
  - **No `GitLock`.** `run_prepatch_check()` requires one (and passes it to
    `setup_prepatch_worktree()`). `git_lock` appears **zero** times in both
    `work_verification.py` and `issue_manager.py` — `worker_pool.py` has one to
    thread through, but the `ll-auto` path would have to construct one. Decide
    and state which: threaded param vs. locally constructed.
  - **No `worktree_base` / `base_branch`.** Both are required by the core with
    no defaults. `worktree_base` must be a gitignored dir (`.worktrees/`);
    `base_branch` drives the merge-base fallback when `base_sha` is unstamped.
  - **The `-> bool` return cannot carry `PrePatchEvidence` out.** The tamper
    guard folds into the bool because its result *is* pass/fail; this check
    produces a bundle that must reach `.ll/history.db` for ENH-2998's own
    harness consumer to find it. Either widen the return type or have the
    adapter persist the bundle itself before returning. State which.
  This is why the Impact section's effort/risk was revised upward below.
- **Worktree teardown is ENH-2997's, and applies here too.** The core does not
  clean up its fork on the success path. ENH-2997 owns the `try/finally` +
  `cleanup_worktree(..., delete_branch=True)` contract and the reaper-predicate
  widening; this adapter must follow the same contract rather than inventing a
  second one, or `ll-auto`/`ll-parallel` runs leak a worktree per verification.
- **`docs/reference/API.md`** — `:88`'s module table entry for
  `little_loops.worktree_utils` names only ll-parallel/ll-sprint/ll-loop as
  consumers and does not mention the FSM executor as a fourth direct caller;
  `:3455-3473` documents `verify_epic_branch_before_merge` /
  `setup_worktree(..., checkout_existing=True)`'s call shape. Cross-reference the
  pre-patch variant here.
- **`docs/reference/CONFIGURATION.md`** — no change needed; the
  `project.test_patterns` row shipped with ENH-2973.
- `scripts/little_loops/parallel/merge_coordinator.py` (~`:1061`) has its own
  private `_cleanup_worktree` wrapper rather than calling
  `little_loops.worktree_utils.cleanup_worktree` directly; confirm during
  implementation whether it needs updating or is genuinely independent.

_Added by `/ll:refine-issue` — 2026-08-13 — based on codebase analysis:_

- **`cli/harness.py` line numbers have drifted again since this issue's own
  2026-08-02 citations** (confirmed via `research-triage`: the file changed
  2026-08-08, after this issue's last refine). Current positions: `HarnessEvalOutcome`
  is now at `harness.py:369-376`; `_evaluate_and_report()` is now `harness.py:378-444`;
  its JSON-print branch is now `harness.py:410-421` (a fixed-key dict:
  `runner`, `exit_code`, `exit_code_check`, `semantic`, `result`, `stdout`,
  `stderr` — still no conditional-key precedent inside this file); `_report()`
  is now `harness.py:447-466`; the `--help` epilog is inside
  `_build_harness_parser()` at `harness.py:192-203`. This supersedes the
  earlier `295-300`/`303-369`/`335-346`/`372-391` numbers above — reinforces
  the existing instruction to locate all sites by name at implementation time,
  not by any line number cited anywhere in this issue.
- **ENH-2997 (now done, completed 2026-08-13) shipped a full reference
  implementation of the `run_prepatch_check()` call and its persistence**,
  which this adapter should mirror rather than design from first principles.
  `fsm/executor.py`'s `_check_prepatch_check()` (`:1574-1709`) resolves
  `base_sha`/`base_dirty` via `read_base_sha`/`read_base_dirty`, resolves
  `base_branch` from `config.parallel.base_branch or "main"`, constructs a
  fresh `GitLock(wt_logger)` locally (`:1630`, not threaded from any caller),
  calls `run_prepatch_check()` with the same nine keyword arguments this
  issue's own Program Design section already lists, wraps the call in
  `try/finally` with `_prepatch_teardown()` for worktree/branch cleanup on
  both the success and exception paths, and persists the resulting
  `PrePatchEvidence` to two independent best-effort sinks: a run-dir JSON
  file (`prepatch_evidence_{issue_id}.json`, guarded by `try/except OSError:
  pass`) and `.ll/history.db` via `session_store.record_prepatch_evidence()`
  (`writers.py:1375-1402`, guarded by a bare `try/except Exception: pass`)
  into a new `prepatch_evidence` table (`schema.py:976-985`) whose own
  in-code comment states the row shape is intentionally what `cli/harness.py`
  is meant to read.
- **The `-> bool` return-widening question is resolved by precedent, not left
  open.** ENH-2997's executor never widens `run_prepatch_check()`'s
  caller-facing return — it persists the bundle to `.ll/history.db`
  internally and lets the guarded state's control flow stay bool/verdict-shaped.
  None of `verify_work_was_done()`'s current callers (`issue_manager.py`,
  `worker_pool.py`) consume anything beyond the bool today, so the "widen
  return type vs. persist internally" choice this issue's Design Notes left
  open has an existing in-repo answer to match if consistency with ENH-2997
  is the goal: persist internally, keep `-> bool`.
- **`history_reader.read_prepatch_evidence(issue_id, *, db=DEFAULT_DB_PATH)
  -> dict | None` already exists** (`history_reader.py:1921-1961`), shipped as
  part of ENH-2997 specifically as the read path this issue's `cli/harness.py`
  consumer is meant to call: `SELECT evidence_json FROM prepatch_evidence
  WHERE issue_id = ? ORDER BY id DESC LIMIT 1`, `json.loads`'d, never raises.
  This is a third reader beyond the `read_base_sha`/`read_base_dirty` pair
  already cited above — the harness-reads-the-DB-row language elsewhere in
  this issue should route through this function rather than a hand-rolled
  query.
- **GitLock sourcing precedent (the open "threaded vs. locally constructed"
  question) has one in-repo data point, not zero.** ENH-2997's executor
  constructs a fresh `GitLock` locally rather than threading a caller-owned
  one, even though `worker_pool.py` already owns `self._git_lock`
  (constructed at `worker_pool.py:176`) that a threaded design could reuse
  instead. Both shapes are legitimate and already present in the codebase's
  two GitLock-consuming call paths — this doesn't resolve the choice, but it
  means "state which" now has a concrete precedent to diverge from or match
  explicitly, not a blank slate.
- **Additive-JSON-key precedent has three concrete worked examples in one
  function, not just the one previously cited.** `fsm/executor.py:2249-2286`
  sets three separate additive keys into an already-built payload dict, each
  gated by `if <condition>: payload["<key>"] = <value>` with an inline
  comment marking the field additive/non-breaking: `stderr_preview`
  (`:2249-2251`), `session_jsonl`/`effort` (`:2259-2270`), and
  `input_tokens`/`output_tokens`/`is_batch` (`:2271-2286`, itself with a
  further-nested conditional). These are the concrete shape `cli/harness.py`'s
  JSON branch should follow for the pre-patch evidence keys.
- **`GitLock` census confirms the "zero occurrences" claim still holds as of
  2026-08-12.** `git_lock` remains absent from `work_verification.py` and
  `issue_manager.py`; its only consumers repo-wide are `fsm/executor.py`,
  `prepatch_check.py`, `worktree_utils.py`, `worker_pool.py`,
  `parallel/orchestrator.py`, `parallel/merge_coordinator.py`,
  `parallel/__init__.py`, and its own module `parallel/git_lock.py`.
- **`worker_pool.py` reaches `verify_work_was_done` via a re-export
  indirection, not a direct import.** `git_operations.py:19-24` re-exports it
  (`# noqa: F401`) from `work_verification`; `worker_pool.py:34` imports it
  from `git_operations`, while `issue_manager.py:42` imports it directly from
  `work_verification`. Neither changes where the adapter's new prepatch call
  would live (still inside `work_verification.py`, reached by both callers
  through their existing import paths) — noted so a future grep for "who
  calls `verify_work_was_done`" checks both import sites.

_Added by `/ll:refine-issue` — 2026-08-13 — based on codebase analysis:_

- **`verify_work_was_done()` call-site census — five sites total, four in `issue_manager.py`, one in `worker_pool.py`.** `issue_manager.py` calls it at `:1398-1403` (gates plan-approval vs. completed-but-unfinalized), `:1508-1513` (gates whether `complete_issue_lifecycle(...)` runs), `:1537-1539` (BUG-2954 diagnostic, deliberately passes `config=None` to bypass the tamper guard — and would bypass this new check the same way), and `:2076` (inside a `TimeoutExpired` handler, `config=None`, only picks a log-message wording). `worker_pool.py` calls it once, inside `WorkerPool._verify_work_was_done()` at `:1339-1346`, itself called once from `_process_issue()` at `:669-676`; that call's `(bool, str)` tuple feeds a return-early failure block at `:694-707` — the bool is load-bearing for the worker's pass/fail result there, not just logging, unlike three of the four `issue_manager.py` sites.
- **`GitLock` availability differs by file, confirmed by direct inspection, not inferred from the earlier "zero occurrences" grep.** `worker_pool.py` already has `self._git_lock` as a reachable instance attribute (constructed once in `__init__` at `:176`) at both `_verify_work_was_done()` (`:1297-1360`) and its caller `_process_issue()` (`:669`) — no new construction needed there. `issue_manager.py` has no `GitLock` import or instance anywhere in the file (confirmed absent from the file); an adapter reached from any of its four call sites would need to construct one fresh, mirroring `fsm/executor.py:1630`'s local `GitLock(wt_logger)` rather than reusing an ambient one.
- **`worktree_base` availability differs by file the same way.** `worker_pool.py` already derives it via `self.repo_path / self.parallel_config.worktree_base`, an expression already used twice in the file (`:205`, `:350-353`) — trivially available, not stored as a local at the call site itself but requires no new resolution logic. `issue_manager.py` has no `worktree_base`-shaped variable or config access anywhere (its two `Path.cwd()`-fallback locals at `:777` and `:1286` resolve the repo root, not a worktree base); an adapter here would need `config.get_worktree_base()` (the `BRConfig` method `fsm/executor.py:1631` uses), since `issue_manager.py` already receives a `BRConfig`-typed `config` parameter to call it on.
- **The tamper-guard adapter this issue mirrors has a structural difference worth naming explicitly: it never forks a worktree.** `_run_non_fsm_tamper_guard()` (`work_verification.py:76-155`) takes `(logger, repo_root, config, baseline_sha, pre_step_snapshot=None)` — no `git_lock`, no `worktree_base` param at all, because it operates on the working tree in place via `snapshot_test_paths_at_ref`/`tamper_guard_changed_files`. Its lazy imports (`:109-117`, from `little_loops.test_tamper_guard`) are function-local for the same circular-import reason already noted for `worker_pool.py:604-610`. It is invoked from `verify_work_was_done()`'s body at `:200-211`: `_detect_meaningful_changes(...)` must return `True` first, then `if config is None: return True` (the exploit point `issue_manager.py:1538`/`:2076` use to skip it), then the guard call itself gates the final `False`. A prepatch-check gate slotted into this same body needs its own worktree/GitLock dependency the sibling never had — the two adapters are not structurally symmetric despite sharing an entry point.
- **Signature-growth convention on `verify_work_was_done()` itself, confirmed from its own docstrings (ENH-2933/2935/2958 precedent).** Every param added to date is keyword-only with a `None` default at the end of the signature, and its docstring states explicitly that `None` preserves prior behavior byte-for-byte, with the new code path gated on that param being non-`None` — e.g. "The guard only runs when a config is supplied... a caller with no config in scope... gets the pre-ENH-2935 behavior unchanged." This is the established shape a new `git_lock`/`worktree_base` param (if the signature is widened rather than persisting internally) would need to match: trailing keyword-only, `None` default, docstring stating pre-change behavior is preserved when omitted.
- **Dual-sink best-effort persistence has no shared helper anywhere in the codebase — every site hand-rolls its own pair of try/except blocks.** A repo-wide search for `def best_effort`/`def safe_write` found nothing. The two sinks this issue's harness consumer depends on (`fsm/executor.py:1670-1689`, run-dir JSON + `.ll/history.db`) swallow silently (`except OSError: pass`, `except Exception: pass`, no logging) — but this is not the only style in the codebase: `session_store/writers.py:1948-1957`'s `SQLiteTransport` and `history_reader.read_prepatch_evidence()` itself both `logger.warning(..., exc_info=True)` before falling back. If this adapter adds its own best-effort write, "silent pass" vs. "warn-and-continue" is a live, contested choice in this codebase, not a settled one.

## Integration Map

### Files to Modify / Create

- `scripts/little_loops/work_verification.py` — the non-FSM adapter over
  ENH-2991's core, mirroring how ENH-2854 reaches `issue_manager.py` and
  `parallel/worker_pool.py`. This is what gives `ll-auto` / `ll-parallel`
  coverage.
- `scripts/little_loops/issue_manager.py`, `scripts/little_loops/parallel/worker_pool.py`
  — call sites for the adapter, following ENH-2854's existing wiring in the same
  files.
- `scripts/little_loops/cli/harness.py` — surface the pre-patch evidence
  alongside `HarnessEvalOutcome` / `_evaluate_and_report()` by reading the
  persisted `.ll/history.db` row; additive JSON keys in the JSON-print branch;
  `--help` epilog. **Locate all sites by name, not by line number** — every
  numeric citation this issue originally carried for this file is stale (see
  § Design Notes).
- `skills/verify-issue-loop/SKILL.md` (~L150-165) — document the deterministic
  check.
- `scripts/little_loops/cli/loop/scaffold_verify.py` — the state-template
  example, since `templates.md` is a redirect stub (FEAT-2948). The existing
  deterministic-alongside-`llm_structured` precedent to mirror is the
  adversarial mode's `count_probes` state (`scaffold_verify.py:130-145`).
- `docs/reference/API.md` (`:88`, `:3455-3473`) — cross-reference the pre-patch
  worktree variant and the FSM executor as a `worktree_utils` consumer.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:2589-2691` — a second, distinct anchor within the
  same file already listed above: the `## little_loops.work_verification`
  module section. It reproduces `verify_work_was_done()`'s exact current
  signature in a fenced code block (`:2628-2635`) and a runnable example
  (`:2684-2691`, `if not verify_work_was_done(logger): ...`). If the adapter
  changes the signature (new params for `GitLock`/`worktree_base`/
  `base_branch`), this block goes stale unless updated alongside the
  `:88`/`:3455-3473` worktree_utils citations already planned.
- `docs/reference/CLI.md:178-243` (`### ll-harness` section) — not previously
  listed. This section prose-duplicates the `--help` epilog text this issue's
  AC already requires updating in `cli/harness.py`
  (`_build_harness_parser()`, `:192-203`); it documents `--output json`
  (`:199`) but no exact JSON key set. Optional/discoverability-only, not a
  breaking dependency, but the natural human-facing mirror of the epilog
  change.

### Similar Patterns to Follow

- `scripts/little_loops/work_verification.py` as wired by ENH-2854 (landed
  2026-07-31) — the exact adapter shape and the `issue_manager.py` /
  `worker_pool.py` call-site pattern to mirror.
- The learning-test gate's shared-skip-flag pattern (`cli_args.py:214` →
  `issue_manager.py:880`, `worker_pool.py:64`, `cli/sprint/run.py:222`) — the
  precedent for one flag controlling a gate across multiple orchestrators.
- `scripts/little_loops/issue_history/models.py`'s `Gap`/`GapAnalysis`
  (`:259-302`) — the `to_dict()` convention the bundle already follows, for
  serializing into harness JSON output.

### Tests

- `scripts/tests/test_cli_harness.py` — extend for the new evidence bundle;
  assert `cli/harness.py` does **not** call `run_prepatch_check()` directly, and
  that its output is unchanged when no row exists for the issue.
- `scripts/tests/test_verify_issue_loop.py` — extend for the documented check.
- Non-FSM adapter coverage from `issue_manager.py` and `worker_pool.py`,
  following ENH-2854's existing tests for the same call sites.
- A test asserting the adapter reuses `config.prepatch_check.enabled` and adds
  no second off-switch, and that with the default `enabled: false` the non-FSM
  path is a recorded skip rather than a failure.
- A test asserting the adapter leaves no pre-patch worktree or branch behind.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_work_verification.py` — the adapter's primary unit-test
  home. `verify_work_was_done` has zero non-test callers outside
  `issue_manager.py`/`worker_pool.py` (confirmed via `ll-code callers-of`); this
  834-line file already hosts `TestVerifyWorkWasDoneTamperGuard`
  (`:568-664`), ENH-2854's sibling adapter test using a real git repo +
  `mock_logger` rather than mocked subprocess (the guard reconstructs state
  from real git history). The new prepatch-check adapter test class belongs
  here, immediately adjacent, mirroring that fixture shape plus the
  `run_prepatch_check` monkeypatch pattern from
  `test_fsm_executor.py::TestPrePatchCheckExecutorHook._patch_run_prepatch_check`
  (`:11672-11681`).
- `scripts/tests/test_ll_loop_scaffold_verify.py` — the existing test file for
  `scaffold_verify.py` (FEAT-2948), not previously listed. Extend it for the
  new state-template example, following the existing `count_probes` assertion
  pattern (`test_ll_loop_scaffold_verify.py:173`, `assert "count_probes" in
  result.yaml_text`).

### Tests (wiring additions)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_manager.py:3174-3179`
  (`test_baseline_sha_passed_to_verify_work_was_done`) — a strict
  `assert_called_once_with(mock_logger, baseline_sha=..., config=...,
  pre_step_snapshot={})` against the `issue_manager.py` call site. If the
  adapter threads new kwargs (e.g. `worktree_base`, `base_branch`) through
  that call site, this assertion breaks and needs updating to match the new
  kwarg set — flagged so it isn't discovered only by a failing test run.
- `scripts/tests/test_fsm_executor.py::TestPrePatchCheckExecutorHook` (from
  `:11580`) — not a file to modify, but the reference test suite for
  ENH-2997's sibling implementation; its teardown-contract test
  (`test_worktree_and_branch_torn_down_after_guarded_exit`, `:12310-12353`)
  and exception-safety fork-diffing pattern (`:12209-12250`) are the concrete
  precedent the new adapter's "leaves no pre-patch worktree or branch behind"
  test (already listed above) should mirror.

### Related Issues

- `ENH-3142` (done) — the gate core this adapter calls; supersedes ENH-2991,
  which was decomposed and shipped no code.
- `ENH-3141` (done) — `setup_prepatch_worktree()`, called transitively.
- `ENH-2997` (done, 2026-08-13) — writes the bundle `cli/harness.py` reads, and
  owns the worktree-teardown contract this adapter follows. Was `blocked_by`;
  now `relates_to` since the blocker is resolved (§ Design Notes has its
  shipped reference implementation).
- `ENH-2854` (peer) — the adapter shape and call sites this mirrors.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-13 — based on codebase analysis:_

- `scripts/little_loops/cli/harness.py` — updated 2026-08-12 anchors (superseding
  the earlier `harness.py:295-369`-range citations above): `HarnessEvalOutcome`
  at `:369-376`, `_evaluate_and_report()` at `:378-444`, JSON-print branch at
  `:410-421`, `_report()` at `:447-466`, `--help` epilog inside
  `_build_harness_parser()` at `:192-203`. Read the bundle via
  `history_reader.read_prepatch_evidence(issue_id, db=...)`
  (`history_reader.py:1921-1961`), shipped by ENH-2997 specifically for this
  read path — do not hand-roll the `.ll/history.db` query.
- `scripts/little_loops/git_operations.py:19-24` — re-exports
  `verify_work_was_done` from `work_verification` (`# noqa: F401`);
  `worker_pool.py` imports it from here, `issue_manager.py` imports it
  directly from `work_verification`. Both import paths reach the same
  function the adapter modifies.

_Added by `/ll:refine-issue` — 2026-08-13 — based on codebase analysis:_

- **Adapter-wrapping-a-core test precedent confirmed with no exceptions found**: every test in `TestVerifyWorkWasDoneTamperGuard` (`test_work_verification.py:568-576`) and its sibling `TestVerifyWorkWasDonePostImplementBracket` (`:667-759`) uses a real git repo fixture (`_repo_with_committed_test` / `copy_git_template`) plus a `MagicMock()` logger — a grep across the whole file for `patch(...run_tamper_guard...)` or a monkeypatch on the wrapped core function found zero matches. The class docstring states the reason: the guard reconstructs its "before" state from real git history, which a blanket `subprocess.run` mock can't represent faithfully. The same reasoning applies to `run_prepatch_check()`, whose core also does git-based worktree forking.
- **`--help` epilog convention for naming a specific additive JSON key has exactly one precedent in `cli/*.py`, not a general pattern**: `cli/ctx_stats.py:51-60` appends a parenthetical directly onto the existing `--json`/`--output json` example line — `%(prog)s --json  # Output as JSON (includes skill_health array)` — rather than a separate paragraph. A broader grep across all `epilog=` blocks in `cli/` found many `--json` example lines but only this one names a specific key by name; `cli/harness.py`'s current epilog (`:186-204`) has no per-key JSON annotations yet.

## Program Design

### Signatures

- `verify_work_was_done(logger: Logger, changed_files: list[str] | None = None, baseline_sha: str | None = None, config: BRConfig | None = None, repo_root: Path | None = None, pre_step_snapshot: TamperSnapshot | None = None) -> bool` — `work_verification.py:158-165`, unchanged today; the adapter either extends this signature or persists internally and keeps it as-is (see § Design Notes).
- `run_prepatch_check(step_diff, repo_root, worktree_base, base_sha, base_dirty, base_branch, logger, git_lock, config) -> PrePatchEvidence` — the shipped core (ENH-3142) the adapter calls, mirroring `fsm/executor.py:_check_prepatch_check()`'s (`:1639-1656`) argument construction.
- `read_prepatch_evidence(issue_id: str, *, db: Path = DEFAULT_DB_PATH) -> dict | None` — `history_reader.py:1921-1961`; the read path `cli/harness.py`'s consumer calls.

### Call Path

Non-FSM host: `work_verification.verify_work_was_done` -> `read_base_sha` /
`read_base_dirty` -> `run_prepatch_check` -> `collect_candidates` ->
`setup_prepatch_worktree` -> pytest (x2, initial + flake retry)

The adapter resolves `(base_sha, base_dirty)` and passes them in; the core is
database-free. It must also supply `repo_root`, a gitignored `worktree_base`,
`base_branch`, `logger`, and a `GitLock` — the shipped signature is keyword-only
with nine parameters and takes no `timeout_s` (the box comes from
`config.prepatch_check.timeout_s`). `_evaluate_and_report()` in `cli/harness.py`
reads the persisted bundle from `.ll/history.db` and surfaces it alongside the
existing `HarnessEvalOutcome` — it does not call `run_prepatch_check()` itself.

`PrePatchEvidence.to_dict()` (`prepatch_check.py:88-97`) already exists and
follows this codebase's nested-list-comprehension convention, so the harness
JSON surfacing needs no new serializer.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-13 — based on codebase analysis:_

- **Concrete reference implementation of this exact call shape now exists**:
  `fsm/executor.py:_check_prepatch_check()` (`:1574-1709`), landed by ENH-2997
  (done 2026-08-13). It resolves `base_sha`/`base_dirty` via
  `read_base_sha`/`read_base_dirty`, `base_branch` from
  `config.parallel.base_branch or "main"`, constructs `GitLock(wt_logger)`
  locally, calls `run_prepatch_check()` with the nine keyword arguments above,
  and persists the resulting bundle to `.ll/history.db` via
  `session_store.record_prepatch_evidence()` inside a `try/finally` that also
  runs `_prepatch_teardown()`. The non-FSM adapter's call into
  `run_prepatch_check()` can mirror this shape directly rather than
  re-deriving the argument list from the core's signature alone.

## Scope Boundaries

- **Not this issue**: the check itself (ENH-2991) or the FSM executor host
  (ENH-2997).
- **Not this issue**: making `ll-harness` an owner of the check. It was demoted
  to a consumer at the 2026-07-30 placement review because no orchestrator
  invokes it — a repo-wide grep for `ll-harness` across `scripts/little_loops/`
  returns only its own CLI, `runner_spec.py`, telemetry readers
  (`history_reader.py:2797+`), and a permission string in `init/writers.py:70`.
- **Not this issue**: making `/ll:verify-issue-loop` an owner. It is a generator;
  a check emitted there exists only inside per-issue YAML someone chose to
  generate, never in a standing path. It documents a delegation, not a check.
- **Not this issue**: replacing or removing the existing LLM-judged semantic
  criteria in verification loops.

## Acceptance Criteria

- [x] A non-FSM adapter in `work_verification.py` reaches ENH-3142's core from `ll-auto` / `ll-parallel`, mirroring ENH-2854's `issue_manager.py` / `worker_pool.py` wiring.
- [x] The adapter resolves `(base_sha, base_dirty)` via `read_base_sha` / `read_base_dirty` and supplies the core's six further required arguments (`repo_root`, gitignored `worktree_base`, `base_branch`, `logger`, `GitLock`, `config`); it does not duplicate any check logic that belongs in `prepatch_check.py`.
- [x] The `GitLock` sourcing decision (threaded from the caller vs. constructed in the adapter) is made explicitly and applied consistently at both the `issue_manager.py` and `worker_pool.py` call sites.
- [x] The `PrePatchEvidence` bundle escapes `verify_work_was_done()`'s `-> bool` return — either via a widened return type or by the adapter persisting to `.ll/history.db` before returning — so ENH-2998's own harness consumer can find it.
- [x] The adapter reuses `config.prepatch_check.enabled` as its only off-switch; with the `false` default the non-FSM path is a recorded skip, not a failure. A test asserts no second off-switch was added.
- [x] The adapter leaves no pre-patch worktree or branch behind, following ENH-2997's teardown contract; a test asserts it.
- [x] `cli/harness.py` surfaces the pre-patch evidence by reading the persisted `.ll/history.db` row; a test asserts it does not call `run_prepatch_check()` and does not re-implement the check.
- [x] The evidence appears as an additive key set in `_evaluate_and_report()`'s JSON output, and the `--help` epilog mentions it.
- [x] `skills/verify-issue-loop/SKILL.md` documents when the deterministic pre-patch check applies, and `scaffold_verify.py` gains a state-template example showing the guard key. (`templates.md` is a redirect stub and is **not** modified.)
- [x] `docs/reference/API.md` cross-references the pre-patch worktree variant and lists the FSM executor as a `worktree_utils` consumer.
- [x] Existing `ll-harness` behavior is unchanged when no bundle is present (the evidence section is simply absent, not an error) — including the common case where `prepatch_check.enabled` was never turned on.

## Impact

- **Priority**: P2 — extends coverage to the non-FSM orchestrators and makes the
  evidence auditable without re-running the check.
- **Effort**: Medium-Large — revised upward 2026-08-12. The harness surfacing and
  documentation halves are genuinely small, but the adapter half requires a
  `verify_work_was_done()` signature change plus new `GitLock` plumbing at both
  orchestrator call sites (see § Design Notes → "The adapter is not thin").
- **Risk**: Medium — revised upward 2026-08-12. The harness half is additive and
  low-risk, but `verify_work_was_done()` is a shared entry point for both
  `ll-auto` and `ll-parallel`, so its signature change touches both
  orchestrators' verification path. The `enabled: false` default is what keeps
  the change inert for existing projects.
- **Breaking Change**: No.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-12_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- Deep per-site complexity: the `verify_work_was_done()` signature change touches 5 call sites across two files (`issue_manager.py` x4, `worker_pool.py` x1) with cross-module shared state, not a mechanical substitution.
- The `GitLock` sourcing decision (threaded from caller vs. constructed locally) is an explicit "state which" open choice with two diverging in-repo precedents (`worker_pool.py` already owns `self._git_lock`; `issue_manager.py` has none) — expect a real design call during implementation.
- `issue_manager.py` has neither `GitLock` nor `worktree_base` resolution today while `worker_pool.py` already has both — the two call sites need asymmetric amounts of new plumbing, raising the odds one site gets less careful treatment than the other.

## Status

**Open** | Created: 2026-08-02 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-08-13T02:20:55 - `1b358ce4-3909-4d0a-a1de-c1b364dfe1e9.jsonl`
- `/ll:ready-issue` - 2026-08-13T01:57:11 - `84f91b41-a179-482d-963a-a04e9845a1c6.jsonl`
- `/ll:confidence-check` - 2026-08-13T01:54:47 - `60f275e1-787d-42d4-a543-b4e923c1b80a.jsonl`
- `/ll:verify-issues` - 2026-08-13T01:52:43 - `77e10247-c09b-4f0b-be83-135286e1455f.jsonl`
- `/ll:refine-issue` - 2026-08-13T01:49:29 - `3d3d9d65-d81f-49e2-8855-f3369b112ad5.jsonl`
- `/ll:verify-issues` - 2026-08-13T01:42:57 - `18286908-2ae3-4567-bd06-a842d8a5d783.jsonl`
- `/ll:wire-issue` - 2026-08-13T01:39:54 - `af05a048-8842-4db2-9eb1-386c07437144.jsonl`
- `/ll:refine-issue` - 2026-08-13T01:28:38 - `21c3c18a-7288-4fe2-87be-6847108486fe.jsonl`
- `/ll:refine-issue` - 2026-08-02T15:27:49 - `4acf820d-02a8-4f47-a175-f1a0616e7195.jsonl`
- `/ll:issue-size-review` - 2026-08-02T13:48:44 - `14957793-c5a3-42c3-8c4e-e15ef7fbe208.jsonl`

## Related Key Documentation

- `docs/reference/API.md` — documents `work_verification`, `cli/harness.py`'s module surface, and `worktree_utils`; this issue's non-FSM adapter and harness evidence-surfacing are additive changes to exactly those documented modules (and the issue itself calls out a needed API.md cross-reference update).
- `.claude/CLAUDE.md` — `ll-harness` is listed in the § CLI Tools catalog; this issue extends what it reports without changing its invocation surface.
