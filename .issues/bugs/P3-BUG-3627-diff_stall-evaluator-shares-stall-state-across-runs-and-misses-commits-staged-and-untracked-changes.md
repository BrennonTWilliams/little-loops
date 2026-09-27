---
id: BUG-3627
type: BUG
title: diff_stall evaluator shares stall state across runs and misses commits, staged,
  and untracked changes
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T03:35:14Z'
completed_at: '2026-09-27T05:29:26Z'
confidence_score: 100
outcome_confidence: 88
score_complexity: 13
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3627: diff_stall evaluator shares stall state across runs and misses commits, staged, and untracked changes

## Summary

`evaluate_diff_stall` (`little_loops.fsm.evaluators`, the evaluator behind the `diff_stall_gate` fragment in `loops/lib/common.yaml`) persists its snapshot and stall counter in a cache that is shared across runs and loops, and compares a signal (`git diff --stat`) that is blind to several kinds of real progress. Result: false stall verdicts, including a stall on the very first check of a fresh run.

## Current Behavior

- **Cross-run / cross-loop cache**: state lives at `.loops/tmp/ll-diff-stall-<md5(scope)>.txt` / `.count`. The key is derived only from `evaluate.scope`; every loop using root scope shares `ll-diff-stall-_root_.*`. Nothing resets it at run start, so a new run inherits the previous run's snapshot and stall count. If the prior run ended stalled (count ≥ max_stall) and the tree still matches its snapshot (e.g. empty diff because everything was committed), the new run's first check increments past the threshold and returns `no` immediately.
- **Commits look like no progress**: `git diff --stat` shows unstaged tracked changes only. A worker that edits and commits each pass produces an empty diff every time → counted as stalled.
- **Staged and untracked changes are invisible**: new files and `git add`-ed edits never change the snapshot.
- **`--stat` is insensitive to same-line-count edits**: replacing content while keeping per-file +/- counts yields an identical snapshot.
- Concurrent runs of different loops in the same project clobber each other's counters.

Affected loops (import `diff_stall_gate` / `type: diff_stall`): `continue-task`, `incremental-refactor`, `generator-evaluator`, `generator-evaluator-flux`, `harness-single-shot`, `harness-multi-item`, `harness-plan-research-implement-report`, `vega-viz`, `generative-art`, `openscad-model-generator`, `canvas-sketch-generator`, `pixi-data-viz`.

## Expected Behavior

- Stall state is scoped per run instance (under `${context.run_dir}`), so a fresh CLI run always starts at count 0 with no prior snapshot.
- The progress fingerprint is a **content** fingerprint of the scoped working state: committed tree content (`git ls-tree -r HEAD`), tracked delta (`git diff HEAD`, full content, not `--stat` — covers staged and unstaged), and untracked file contents — excluding `.loops/` and the resolved `run_dir`. It changes on any real content change, whether or not it was committed, and honors `scope`. `general-task`'s `final_verify_spin_gate` (BUG-3270) implements a similar shape in shell (it diffs against a stored baseline ref instead of `ls-tree`).

## Motivation

The stall gate is the non-LLM progress signal that meta-loop rule (2) requires. A signal that false-positives on commits and leaks state between runs routes productive runs to partial terminals — and the pass-1 stall case makes a run's outcome depend on whatever loop last ran in the project.

## Proposed Solution

- Thread the run dir into `evaluate_diff_stall` and store state there; fall back to the current `.loops/tmp` path only when no run context exists.
  - "Fresh run" holds because `cli/loop/run.py` (~:227-236) always derives `run_dir` from a newly generated `instance_id`. It does **not** hold for `--context run_dir=<fixed path>` or direct `FSMExecutor` use without `run_dir` (the legacy `.loops/tmp` fallback); tests must not expect isolation there. Resume reuses the same `run_dir`, so stall state correctly survives a resume.
- **Key includes loop name and state name** (review 2026-09-27): child loops `setdefault` the parent's `run_dir`, so a parent and child both using root-scope `diff_stall` would share `ll-diff-stall-_root_.*` inside one run dir. The state name alone is not enough: nearly every user names the state `check_stall` (`harness-multi-item`, `vega-viz`, `generative-art`, `harness-single-shot`, `harness-plan-research-implement-report`, `openscad-model-generator`, `canvas-sketch-generator`, `pixi-data-viz`, `oracles/generator-evaluator`). Key files as `<loop_name>-<state_name>-<md5(scope)[:12]>`, reading `context.loop_name` and `context.state_name` (both already on `InterpolationContext`, `fsm/interpolation.py` ~:127-129) in the `evaluate()` branch. This also separates two same-scope diff_stall states in one run.
- Replace `git diff --stat` with a **content fingerprint** (decision, review 2026-09-27 — no `HEAD` sha): hash of
  1. `git ls-tree -r HEAD -- <scope or .>` (committed content in scope), with `.loops/` and run-dir entries **filtered out in Python**,
  2. `git diff --no-ext-diff --no-textconv HEAD -- <pathspec>` (staged + unstaged delta, full content),
  3. sorted untracked paths + their blob hashes,

  where `<pathspec>` = `scope` (or `.`) plus `':(exclude).loops/'` and an exclude for the resolved `run_dir` when it lies outside `.loops/` (`--context run_dir=` override).
  - **`ls-tree` cannot take the exclude pathspec** (verified 2026-09-27: `git ls-tree -r HEAD -- . ':(exclude).loops/'` → `fatal: :(exclude).loops/: pathspec magic not supported by this command: 'exclude'`). Pass `ls-tree` only the plain scope paths and drop lines whose path starts with `.loops/` or the run-dir prefix in Python. `git diff` and `git ls-files` accept `:(exclude)` and keep it.
  - **Run-dir exclude only when inside the repo**: an `:(exclude)` pathspec that resolves outside the repository makes both `git diff` and `git ls-files` exit 128 (verified: `fatal: Invalid path '/private/tmp/elsewhere'`). Add the run-dir exclude only when the resolved `run_dir` lies under `git rev-parse --show-toplevel`; a run dir outside the repo cannot appear in the fingerprint anyway.
  - **Neutralize user diff config**: `diff.external` makes `git diff HEAD` exit 128 (verified), and textconv drivers change the output. Always pass `--no-ext-diff --no-textconv`.
  - **Binary files need no special handling**: the `index <old>..<new>` header in `git diff HEAD` carries the working-tree blob hash, so repeated edits to the same binary file change the fingerprint even though the body is only `Binary files … differ` (verified). Pin this with a regression test, since the generator loops (`generative-art`, `canvas-sketch-generator`, `openscad-model-generator`) emit binary output.
  - **Untracked symlinks and vanished files**: `git hash-object --stdin-paths` aborts the whole call on a dangling symlink (verified: `fatal: could not open 'dl' for reading`) and on a file deleted between listing and hashing. Decision: split the untracked list in Python, fingerprint symlinks by `os.readlink()` target (no `hash-object`), and pass only regular files to `hash-object --stdin-paths`. A file that vanishes mid-hash (concurrent worker) returns `error` with the git stderr. The loop's `on_error` handles it, and the next check re-fingerprints.
  - **Why not the `HEAD` sha**: a sha component changes on any commit anywhere, so a scoped gate would count unrelated commits as progress, and a loop that makes trivial commits every pass could never stall. The content fingerprint honors `scope` and still catches edit-then-commit passes. Tradeoff: a pass that *only* commits already-present changes (no content change) is a stall tick — acceptable, and harmless at the fragment's `max_stall: 2`.
  - **No-commit repos**: if `HEAD` does not resolve (`git rev-parse --verify HEAD` fails), skip the `ls-tree` component and use `git diff --cached` (compares against the empty tree) + `git diff` instead of `git diff HEAD`, rather than returning `error` (fresh-repo generator loops such as `generative-art`, `canvas-sketch-generator` are the likely case). Non-git dir still returns `error` with the existing `"git diff failed"` string.
  - **Untracked hashing is bounded**: enumerate with `git ls-files -o --exclude-standard -z -- <pathspec>` (respects gitignore) and hash in one call via `git hash-object --stdin-paths` rather than reading contents into Python or spawning one process per file.
- **Re-entered child loops (known limitation, decision 2026-09-27: accept)**: the `<loop_name>-<state_name>` key separates parent from child, but the *same* child loop invoked twice in one parent run (a retry edge back to the `loop:` state, or two parent states calling the same child) shares `run_dir` and key, so the second invocation inherits the first's snapshot and count. Its first check can return `no` when nothing changed between invocations. This is accepted: a per-invocation key would need persisting to keep stall state across resume, and the effect is only a shorter stall budget for a child that already stalled on unchanged content. Document it in the evaluator docstring; do not claim "fresh first check" for sub-loop re-entry.
- **`ll-loop simulate` (decision 2026-09-27: accept)**: `cmd_simulate` uses a fixed `runs/<loop>-simulate/` dir, so stall state carries across successive simulate runs of one loop. This is the same class as a fixed `--context run_dir=` and is excluded from the fresh-run guarantee. Note it in the `cmd_simulate` docstring. BUG-3629 takes the same decision.
- **Shared helper with BUG-3629**: introduce one module-private helper in `fsm/evaluators.py`, e.g. `_stall_state_paths(kind, state_dir, loop_name, state_name, key_parts) -> tuple[Path, Path]`. It returns `ll-<kind>-stall-<loop>-<state>-<md5(key_parts)[:12]>.{txt,count}` under `state_dir`, or under the legacy `.loops/tmp` path with the legacy scope-only name when `state_dir` is `None`. Sanitize loop and state names (`[^A-Za-z0-9_.-]` → `_`, since loop names such as `oracles/generator-evaluator` contain `/`), and `mkdir(parents=True, exist_ok=True)` the directory. BUG-3629 reuses it.
- **Working directory**: today the git commands run with no `cwd=`, so a diff_stall state inside a `worktree:` child (`executor.py` ~:1232, `child_working_dir`) fingerprints the main tree instead of the worktree. Out of scope for this fix — file a follow-up issue (the evaluator needs the executor's working dir threaded through `evaluate()`); do not leave it unrecorded.
- Legacy `.loops/tmp/ll-diff-stall-*` files left by earlier runs need no cleanup; the new keys never read them.
- Update the fragment description in `loops/lib/common.yaml`; behavior tests go in `TestDiffStallEvaluator` (`scripts/tests/test_fsm_evaluators.py`), not `TestDiffStallGateFragment`, which only checks fragment resolution.
- Follow-up for `evaluate_action_stall` (same shared `.loops/tmp` cache defect) is tracked as BUG-3629.

## Program Design

### Deviations

- 2026-09-27, `/ll:manage-issue`: the design's three-component fingerprint (`git
  ls-tree -r HEAD` + `git diff --no-ext-diff --no-textconv HEAD` + untracked
  hashes, with a no-HEAD `--cached`/plain-diff fallback) was implemented instead
  as a single `git ls-files -c -o --exclude-standard -z <pathspec>` listing (all
  tracked + untracked non-ignored paths in scope) hashed via one
  `git hash-object --stdin-paths` call for regular files and `os.readlink()` for
  symlinks. This fingerprints working-tree content directly rather than
  reconstructing it from a committed-tree/diff split, so it needs no `HEAD`
  presence check, no `ls-tree`/`:(exclude)` workaround, and no separate no-commit
  branch — `ls-files` and `hash-object` behave identically with or without
  commits. All Acceptance Criteria still hold under this shape (verified by the
  added tests): edit-then-commit and commit-only-no-change still resolve
  correctly because content, not diff-against-HEAD, drives the hash; `scope`,
  `.loops/`/run-dir exclusion (via `:(exclude)`/`:(top,exclude)` pathspec magic,
  same as the design), binary files, dangling symlinks, and no-commit repos are
  all covered. The `state_dir`/`state_key` shape and `_stall_state_paths` helper
  match the design as specified.

### Types

- `scope: list[str] | None` — optional pathspecs limiting the fingerprint (unchanged)
- `max_stall: int` — consecutive identical fingerprints before a `no` verdict (unchanged)
- `state_dir: Path | None` — NEW: per-run directory for snapshot/count files; `None` keeps the legacy `.loops/tmp` location
- `state_key: str` — NEW: `<loop_name>-<state_name>` prefix for the state files; `""` keeps the legacy scope-only key

### Signatures

- `evaluate_diff_stall(scope: list[str] | None = None, max_stall: int = 1, state_dir: Path | None = None, state_key: str = "") -> EvaluationResult` — fingerprint = hash of `git ls-tree -r HEAD -- <scope>` (`.loops/` and run-dir lines filtered in Python, since `ls-tree` rejects `:(exclude)`) + `git diff --no-ext-diff --no-textconv HEAD -- <pathspec>` (or `--cached` + plain `git diff`, no `ls-tree`, when there are no commits) + sorted untracked paths with `git hash-object --stdin-paths` digests for regular files and `os.readlink()` targets for symlinks; `<pathspec>` excludes `.loops/` and the run dir only when the run dir is inside the repo; state files come from the shared `_stall_state_paths("diff", ...)` helper, `ll-diff-stall-<loop>-<state>-<md5(scope)[:12]>`
- `_stall_state_paths(kind: str, state_dir: Path | None, loop_name: str, state_name: str, key_parts: list[str]) -> tuple[Path, Path]` — NEW module-private helper shared with BUG-3629 (see Proposed Solution)

### Call Path

FSM executor `_evaluate` -> `evaluate(config, output, exit_code, context)` `diff_stall` branch derives `state_dir` from `context.context["run_dir"]` (absent/empty -> `None`) and `state_key` from `context.loop_name` + `context.state_name` -> `evaluate_diff_stall(scope, max_stall, state_dir=..., state_key=...)` -> `EvaluationResult` verdict `yes` / `no` / `error` -> state routing

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_diff_stall()` (cache path, fingerprint); no `executor.py` change — `evaluate()` already receives `context`
- `scripts/little_loops/loops/lib/common.yaml` — `diff_stall_gate` fragment description

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/evaluators.py` — `evaluate()` branch `elif eval_type == "diff_stall"` (~:2012) is the only production call site; derive `state_dir` from `context.context["run_dir"]` here (same pattern as the `score_stall`/`open_question_stall` branches, which resolve `${context.run_dir}` from `context`). Also update the `evaluate_diff_stall` docstring ("State is persisted in /tmp" is already wrong) and the module docstring ("git diff comparison") [Agent 1/2 finding]
- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig` docstring (~:81-82) says "Paths to limit git diff to"; no new field needed if `state_dir` derives from `context` [Agent 2 finding]
- `scripts/little_loops/fsm/fsm-loop-schema.json` (~:829) — `scope` description "Paths to limit git diff to"; reword if fingerprint semantics change [Agent 2 finding]
- `scripts/little_loops/loops/README.md:211` — lists `diff_stall_gate` in the `lib/common.yaml` fragment table; keep description consistent [Agent 1 finding]
- `scripts/little_loops/loops/harness-single-shot.yaml` (`check_stall` comment, ~:46) — "diff_stall compares the git diff between iterations"; reword [Agent 2 finding]

### Dependent Files (Callers/Importers)
- The 12 loops listed under Current Behavior (behavior change only; no YAML edits expected)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/testing.py` — `cmd_test` (~:114-124) is a second `evaluate()` caller and passes a bare `InterpolationContext()` with no `run_dir`; `state_dir` derivation must fall back to the legacy `.loops/tmp` path (or a temp dir) and not raise [Agent 2 finding]
- `scripts/little_loops/cli/loop/audit.py` — `AuditStats.diff_stall_present` reads only evaluate-event `type`/`verdict` (not `details`); unaffected while those are preserved [Agent 2 finding]
- `skills/audit-loop-run/SKILL.md` (~:214-237) — consumes `diff_stall_present` as "shallow-iteration" corroboration; meaning shifts slightly once commits count as progress [Agent 1/2 finding]
- `scripts/little_loops/fsm/validation/structural_rules.py` (`evaluate.type == "diff_stall"` block ~:160) — validates only `max_stall >= 1`; no change unless a new field is added [Agent 1/2 finding]
- Loops not listed above that also use the gate: `scripts/little_loops/loops/oracles/generator-evaluator.yaml` (`check_diff_stall`, ~:281-287, header comments ~:15-17, ~:268-271), inherited by `oracles/generator-evaluator-flux.yaml`; `harness-multi-item.yaml` (~:81) [Agent 1/2 finding]
- Behavior interplay: child loops `setdefault` the parent's `run_dir` (`executor.py` ~:1151-1152), so a sub-loop's diff_stall and the parent's share a state dir; `md5(scope)` alone does not separate them, and two diff_stall states with the same scope in one run still collide (resolved: key includes loop name + state name, see Proposed Solution). Loops that write progress only under `.loops/` (excluded by the fingerprint) will no longer register as progress [Agent 2 finding]
- `scripts/little_loops/fsm/evaluators.py` `evaluate_action_stall` (~:837) — same shared `.loops/tmp` cache pattern; out of scope, follow-up [Agent 2 finding]

### Similar Patterns
- `scripts/little_loops/loops/general-task.yaml` — `final_verify_spin_gate` content fingerprint scoped away from `${context.run_dir}`

### Tests
- `scripts/tests/test_fsm_evaluators.py::TestDiffStallEvaluator` — behavior tests (see wiring notes below)
- `scripts/tests/test_fsm_fragments.py::TestDiffStallGateFragment` — structural only (fragment resolution); should stay green

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_evaluators.py::TestDiffStallEvaluator` — the `mock_git` fixture returns the same stdout for every `subprocess.run`, so a multi-command fingerprint breaks: `test_first_iteration_returns_success`, `test_different_diff_returns_success`, `test_identical_diff_at_threshold_returns_failure`, `test_identical_diff_below_threshold_returns_success`, `test_stall_then_progress_resets_counter`, `test_dispatch_diff_stall`, `test_dispatch_diff_stall_with_options`, `test_first_call_resets_stale_count_file` (hardcodes `md5("_root_")[:12]` and `.loops/tmp/ll-diff-stall-<key>.count`). Re-model `mock_git` with an argv-routed `side_effect` or switch to real-git tests [Agent 2/3 finding]
- `test_scope_passed_to_git` — asserts `mock_run.call_args[0][0]` (last call only); breaks unless the scope-bearing command is last [Agent 3 finding]
- `test_git_failure_returns_error` / `test_git_timeout_returns_error` — assert `"git diff failed"` / `"timed out"` in `details["error"]`; keep those strings [Agent 2/3 finding]
- `clean_state_files` autouse fixture + dispatch tests (`test_dispatch_diff_stall*`, `evaluate(config, "", 0, InterpolationContext())`) — no `run_dir`; `run_dir` must stay optional [Agent 3 finding]
- `scripts/tests/test_grader_coverage.py` (`EXEMPT_GRADERS`, `"evaluate_diff_stall"` ~:48) — `test_all_evaluate_functions_classified` fails if the function is renamed/split into a new `evaluate_*` symbol [Agent 1/3 finding]
- New tests (real git repo; copy the `git_repo` fixture / `_commit_file` from `scripts/tests/test_prepatch_check.py` and `_init_repo(repo, *, gitignore_loops)` from `test_builtin_loops.py::TestGeneralTaskFinalVerifySpinGateShellAction`; `monkeypatch.chdir(repo)`): same-line-count content edit, edit-then-commit, commit-only with no content change (stall tick), staged-only, untracked add/edit, `.loops/` state excluded from untracked hashing, `scope` limiting tracked+untracked, commit outside `scope` is not progress, two `run_dir`s isolated / fresh `run_dir` first check `yes` with `stall_count` 0, parent+child `check_stall` states sharing a `run_dir` isolated, `run_dir` absent fallback, git errors (no-commit repo, non-git dir, later-command timeout) [Agent 3 finding]
- `scripts/tests/test_fsm_evaluators.py::TestScoreStallEvaluator.test_dispatch_defaults_to_run_dir_history` (~:2100) — template for passing `InterpolationContext(context={"run_dir": ...})` through `evaluate()` [Agent 3 finding]
- Structural-only, should stay green unless the `common.yaml` fragment shape changes (`evaluate.type`, `max_stall: 2`, description): `test_fsm_fragments.py::TestDiffStallGateFragment` (~:1711-1760), `test_builtin_loops.py::test_check_stall_uses_diff_stall_gate_fragment` (~:3957), `test_flux_image_generator.py` (~:84-97), `test_audit_loop_run_skill.py::test_shallow_iteration_has_diff_stall_evaluator` (~:466), `test_create_loop.py` (~:274), `test_cli_loop_audit.py::test_diff_stall_detected` [Agent 1/3 finding]

### Documentation
- `docs/guides/LOOPS_GUIDE.md` / `docs/reference/` entries describing `diff_stall` semantics (grep `diff_stall`)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md` — `#### diff_stall` section (~:745-764): "comparing `git diff --stat`", `scope` comment, verdict table rows [Agent 2 finding]
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (~:450-463) — `scope` row "Paths to limit `git diff --stat` to" [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` (~:418, ~:1032-1038, ~:1352) and `docs/guides/LOOPS_REFERENCE.md` (~:3520-3521 fragment description; "No file changes detected" prose ~:2132, ~:2199, ~:2262, ~:2346, ~:2418) [Agent 2 finding]
- `docs/reference/loops.md` (~:590-602, ~:687, ~:753-757) and `docs/reference/API.md` (~:6084-6110, `EvaluateConfig.scope`/`max_stall` "git diff" wording) [Agent 1/2 finding]
- `docs/test-quality-audit.md` (~:23, ~:67) — "stale count file not reset on first call" entry describes the `.count` behavior [Agent 2 finding]
- `skills/create-loop/loop-types.md` (~:973 "comparing `git diff --stat`") and `skills/create-loop/reference.md` (~:406, ~:1350) — after editing, regenerate the mirrors `.gemini/`, `.kimi-code/`, `.qwen/skills/create-loop/` with `ll-adapt --host <gemini|kimi-code|qwen> --apply` or the mirror gates trip [Agent 2 finding]
- `CHANGELOG.md` — historical mentions only; no edit (no `[Unreleased]` entries)

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation/structural_rules.py:365` — `RUNNER_INJECTED` already includes `run_dir`; no schema/config-key addition needed [Agent 2 finding]
- `scripts/little_loops/fsm/validation/meta_rules.py` (`_SHARED_TMP_PATH_RE`, ~:39-41, ~:186-206) — scans loop action text, not evaluator internals; will not flag the evaluator's own `.loops/tmp` write [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Current shape: `evaluate_diff_stall(scope, max_stall)` (`fsm/evaluators.py`) runs `git diff --stat [-- scope]` with no `cwd=`, keys state by `md5("|".join(sorted(scope)) or "_root_")[:12]` under `Path.cwd()/.loops/tmp/ll-diff-stall-<key>.{txt,count}`, and nothing in the repo ever deletes those files (no run-start reset, no cleanup). First call (no snapshot) writes count `0` and returns `yes`; equal snapshot increments and returns `no` at `stall_count >= max_stall`; differing snapshot resets to `0`. Git failure/timeout return `error`; file writes are uncaught.
- Run context gap: the only production caller is the `evaluate()` dispatcher branch `elif eval_type == "diff_stall"`, which passes only `scope=config.scope, max_stall=config.max_stall`. `evaluate()` already receives `context: InterpolationContext`, and `ctx.context["run_dir"]` is populated for CLI runs (`cli/loop/run.py` ~:236, `runs/<instance_id or loop_name>/`; `cli/loop/testing.py` ~:217 for simulate). `InterpolationContext` has no run-id field; the instance id is reachable only through the `run_dir` path. `run_dir` may be absent (direct executor use, older tests), so the no-context path must remain valid.
- Schema surface: `EvaluateConfig.scope`/`max_stall` (`fsm/schema.py` ~:134-135, parsed ~:249); validation covers only `max_stall >= 1` (`fsm/validation/structural_rules.py`); `scope` is neither validated nor interpolated. `fsm/fsm-loop-schema.json` (~:829) describes `scope` as "Paths to limit git diff to" — update if fingerprint semantics change.
- Reference fingerprint (`loops/general-task.yaml` `final_verify_spin_gate`): hashes `git diff "$BASELINE_REF" -- . ':(exclude).loops/'` plus sorted untracked paths (`git ls-files -o --exclude-standard -z`) plus `git hash-object` of each untracked file, via `git hash-object --stdin`. It excludes the whole `.loops/` tree, not just the run dir, because `ll-init` ships no `.loops/` gitignore entry to consuming projects; it diffs against a stored baseline ref rather than `HEAD`, and has a looser no-git fallback. Its tests run the real action in a temp git repo (`TestGeneralTaskFinalVerifySpinGateShellAction`, `test_builtin_loops.py`).
- Constraints from git semantics: `git diff HEAD` errors on a repo with no commits and outside a git repo (today's `--stat` path reports git failure as `error`); a `HEAD`-sha component makes committed progress visible but also means a revert-to-same-content after commits changes the fingerprint (superseded 2026-09-27: no `HEAD` sha; `git ls-tree -r HEAD` content is used instead — see Proposed Solution); untracked-file hashing must not read the run dir or other `.loops/` state or the fingerprint changes on every evaluation.
- Affected users: all `fragment: diff_stall_gate` loops (fragment sets `max_stall: 2`; `continue-task` overrides `max_stall: 3`, `on_error: run_tests`) and `oracles/generator-evaluator.yaml` `check_diff_stall`, inherited by `generator-evaluator-flux.yaml`. None of the loops sampled (`continue-task`, `harness-single-shot`, `incremental-refactor`) sets `scope`; the remaining users were not opened.
- Tests: `TestDiffStallEvaluator` in `scripts/tests/test_fsm_evaluators.py` patches `little_loops.fsm.evaluators.subprocess.run` (`mock_git`) and `chdir`s to `tmp_path`; every test assumes a single `git diff --stat` call and `test_first_call_resets_stale_count_file` hardcodes the `ll-diff-stall-<md5("_root_")[:12]>.count` path, so a multi-command fingerprint or relocated state invalidates that fixture shape. `TestDiffStallGateFragment` (`test_fsm_fragments.py`) — the issue's `TestDiffStallGate` — only checks fragment resolution (`max_stall == 2`, description present) and never exercises the evaluator, so it is not where behavior tests belong. Other references that must keep passing: `test_grader_coverage.py` (lists `evaluate_diff_stall`), `test_fsm_schema_fuzz.py`, `test_cli_loop_audit.py::test_diff_stall_detected`, `test_builtin_loops.py` (`check_stall`, ~:3957).
- Event consumers keyed on the `diff_stall` evaluate event: `cli/loop/audit.py` (`diff_stall_present` when verdict in `stall`/`no`), `cli/loop/info.py`. The `details` keys (`stall_count`, `max_stall`, `diff_changed`) are part of that surface.
- Sibling evaluator: `evaluate_action_stall` (`evaluators.py` ~:898) uses the same shared `.loops/tmp` cache directory and likely shares the cross-run defect; out of scope for this issue but worth a follow-up check.

## Implementation Steps

1. Add the shared `_stall_state_paths` helper; pass run context into `evaluate_diff_stall`; store snapshot/count under the run dir, keyed `<loop_name>-<state_name>-<md5(scope)[:12]>` (names sanitized).
2. Replace the `--stat` snapshot with the content fingerprint (`git ls-tree -r HEAD` filtered in Python + `git diff --no-ext-diff --no-textconv HEAD` + untracked regular-file blob hashes via `git hash-object --stdin-paths` and symlink targets via `os.readlink`), honoring `scope` and excluding `.loops/` and the resolved run dir (run-dir exclude only when inside the repo).
3. Add tests for each Acceptance Criterion; update fragment docs.
4. File the follow-up issue for the worktree `cwd` gap (see Proposed Solution → Working directory).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/fsm/evaluators.py` `evaluate()` `diff_stall` branch — resolve `state_dir` from `context.context["run_dir"]` (no `executor.py` change needed); tolerate missing/empty `run_dir` (`cli/loop/testing.py::cmd_test` passes a bare `InterpolationContext()`)
- Update `scripts/tests/test_fsm_evaluators.py::TestDiffStallEvaluator` — re-model `mock_git` (multi-command fingerprint), fix hardcoded count path in `test_first_call_resets_stale_count_file`, fix `test_scope_passed_to_git` argv assertion, keep error strings; add real-git tests for each Acceptance Criterion
- Update `scripts/tests/test_grader_coverage.py` only if a new `evaluate_*` symbol is introduced
- Update docs listed under Documentation (`docs/generalized-fsm-loop.md`, `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`, `LOOPS_GUIDE.md`, `LOOPS_REFERENCE.md`, `docs/reference/loops.md`, `API.md`, `docs/test-quality-audit.md`), `fsm-loop-schema.json` / `schema.py` `scope` wording, and `skills/create-loop/{loop-types,reference}.md`
- Regenerate host skill mirrors (`ll-adapt --host <gemini|kimi-code|qwen> --apply`) after the `skills/` edit; run `ruff format` scoped to changed files only
- Per-run key collisions: decided — include loop name + state name in the key (see Proposed Solution); add tests with two same-scope diff_stall states in one `run_dir`, and with parent and child loops that both name the state `check_stall`
- Sample the loops the research did not open (`vega-viz`, `pixi-data-viz`, `generative-art`, `openscad-model-generator`, `canvas-sketch-generator`, `harness-plan-research-implement-report`, `harness-multi-item`, `oracles/generator-evaluator`) and confirm each writes progress outside `.loops/` (now excluded); note any that do not
- Follow-up BUG-3629 (`evaluate_action_stall`) already filed; share a state-dir/key helper with it
- Docs checklist (do all, in one pass): `docs/generalized-fsm-loop.md`, `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md`, `docs/reference/loops.md`, `docs/reference/API.md`, `docs/test-quality-audit.md`, `skills/create-loop/{loop-types,reference}.md` + `ll-adapt` mirrors

## Impact

- **Priority**: P3 — false `partial`/stall terminals waste runs; no data loss.
- **Effort**: Small–Medium — one evaluator plus tests.
- **Risk**: Medium — 12 built-in loops change stall sensitivity, in both directions:
  - Edit-then-commit passes now count as progress (stalls trip less often for committing workers). A pass that only commits with no content change is still a stall tick, and trivial commits cannot keep a gate alive (no `HEAD` sha in the fingerprint).
  - Loops whose only progress is written under `.loops/` (now excluded) will stall where they previously did not.
  - Commits outside `scope` no longer register as progress for a scoped gate.
- **Breaking Change**: No

## Steps to Reproduce

1. Run any root-scoped `diff_stall_gate` loop to a stall terminal (counter file reaches max_stall).
2. Commit or discard the working-tree changes so `git diff --stat` matches the stored snapshot (e.g. both empty).
3. Start a new run of any root-scoped diff_stall loop; its first stall check returns `no`.

## Acceptance Criteria

- Two sequential CLI runs of the same loop do not share stall state; a fresh run's first check always returns `yes` (not required for a fixed `--context run_dir=` or the no-`run_dir` fallback).
- A pass that edits then commits, only stages, or only adds untracked files counts as progress. A pass that only commits already-present changes (no content change) is a stall tick.
- A same-line-count content edit counts as progress.
- With `scope` set, changes and commits outside `scope` do not count as progress.
- A parent and child loop sharing a `run_dir` (including both naming the state `check_stall`), or two same-scope diff_stall states in one run, do not share stall state.
- Without a `run_dir` in context (e.g. `cmd_test`'s bare `InterpolationContext()`), the evaluator falls back to the legacy `.loops/tmp` path and does not raise.
- A repo with no commits does not return `error`; it fingerprints from `git diff --cached` + `git diff` + untracked files.
- Untracked regular files are hashed in one `git hash-object --stdin-paths` call (no full-content reads in Python); untracked symlinks, including dangling ones, are fingerprinted by link target and do not return `error`; `.loops/` and the resolved run dir are excluded.
- The committed-content component (`ls-tree`) excludes `.loops/` without passing `:(exclude)` to `git ls-tree`: a test with a committed file under `.loops/` changing between checks is a stall tick, not progress.
- A `--context run_dir=` outside the repository does not return `error` (no out-of-repo exclude pathspec).
- A repo with `diff.external` configured still fingerprints (test sets `-c`/repo-local `diff.external=false`).
- Repeated edits to the same tracked binary file count as progress.
- The evaluator docstring states the accepted limitations: a re-entered child loop and `ll-loop simulate` (fixed run dir) can inherit stall state.
- Follow-up issue filed for the worktree `cwd` gap.
- Existing diff_stall tests updated (`TestDiffStallEvaluator`); new tests cover each case above.
- Follow-up issue filed for `evaluate_action_stall` (BUG-3629).

## Related

- FEAT-3594 (`continue-task`) — discovered during its review; that loop replaces its stall gate with a loop-local fingerprint independently.
- BUG-3270 — `general-task` `final_verify_spin_gate` fingerprint pattern.
- BUG-3629 — `evaluate_action_stall` follow-up (same shared `.loops/tmp` cache defect).
- BUG-3634 — follow-up filed for the worktree `cwd` gap (out of scope here; see Proposed Solution → Working directory).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-27_

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Code claims verified against HEAD: `evaluate_diff_stall` (`evaluators.py:577`) runs bare `git diff --stat`, keys state by `md5(scope)` under `Path.cwd()/.loops/tmp`, and a carried-over count ≥ `max_stall` yields `no` on a new run's first check; `evaluate()` `diff_stall` branch (`:2012`) passes only `scope`/`max_stall`; `InterpolationContext.state_name`/`loop_name` exist; `run_dir` is injected at `cli/loop/run.py:236`; child `run_dir` `setdefault` at `executor.py:1152`; all 12 listed loops use `diff_stall`. `ll-verify-evidence`: clean. No decisions-log rules apply.
- Fixed: stale `evaluate_action_stall` line (`~:849` → `~:837`).
- Fixed (proposal-consequence check, AC gap): the Integration Map lists `cmd_test`'s bare-context fallback but no Acceptance Criterion covered it; added one.

## Resolution

Implemented per Acceptance Criteria (with a documented deviation — see Program
Design → Deviations). `evaluate_diff_stall` now takes `state_dir`/`state_key`,
keys stall state under `<loop_name>-<state_name>-<md5(scope)[:12]>` inside the
run's `run_dir` (falling back to the legacy `.loops/tmp` path when absent), and
fingerprints working-tree content (`git ls-files -c -o --exclude-standard` +
`git hash-object --stdin-paths` for regular files, `os.readlink()` for
symlinks) instead of `git diff --stat`, scoped and excluding `.loops/`/the run
dir. `evaluate()`'s `diff_stall` branch derives `state_dir`/`state_key` from
`context`. `TestDiffStallEvaluator` rewritten against a real git repo covering
every Acceptance Criterion (fresh-run isolation, edit/commit/stage/untracked
progress, commit-only stall tick, scope, parent/child key isolation, no-`run_dir`
fallback, no-commit repo, `diff.external`, binary files, dangling symlinks,
out-of-repo run dir). Docs/schema/skill-mirror wording updated
(`common.yaml`, `fsm-loop-schema.json`, `schema.py`,
`docs/generalized-fsm-loop.md`, `AUTOMATIC_HARNESSING_GUIDE.md`,
`skills/create-loop/loop-types.md` + `.gemini`/`.kimi-code`/`.qwen` mirrors).
Follow-up BUG-3634 filed for the worktree `cwd` gap (BUG-3629 already covers
`evaluate_action_stall`). Full suite: 26580 passed, 60 skipped; 2 pre-existing
failures unrelated to this change (issue-corpus/evidence gates tripped by other
pending `.issues/` edits already present before this session) and one flaky
process test that passes in isolation. `ruff check`/`mypy` clean on touched
files.

## Session Log
- `/ll:manage-issue` - 2026-09-27T05:29:26 - `2bf90db8-8241-42d1-a2f3-16851c36676b.jsonl`
- `/ll:ready-issue` - 2026-09-27T05:18:10 - `09cdddd4-4608-4727-809d-efaaa771aaf2.jsonl`
- `/ll:verify-issues` - 2026-09-27T05:07:18 - `8dd98d25-9e0a-42d3-8b1b-63a8171e5519.jsonl`
- `/ll:confidence-check` - 2026-09-27T04:51:22 - `7d0784ac-24a4-4b7a-af8c-3b3e14cec5c4.jsonl`
- `/ll:wire-issue` - 2026-09-27T04:02:38 - `b9726386-58c1-4c65-8485-76e226017a2f.jsonl`
- `/ll:refine-issue` - 2026-09-27T03:56:26 - `d2d94801-a3bb-4af7-800e-2bfc0ccec8d4.jsonl`
