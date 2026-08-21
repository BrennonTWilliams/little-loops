---
id: BUG-3276
type: BUG
title: "Built-in loops hardcode this-repo-specific project commands \u2014 incremental-refactor\
  \ reverts all work in consuming projects"
priority: P1
status: open
discovered_by: design-review
discovered_date: '2026-08-20'
captured_at: '2026-08-20T00:00:00Z'
relates_to:
- BUG-3269
labels:
- bug
- loops
- config
- test-cmd
confidence_score: 98
outcome_confidence: 80
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 16
score_change_surface: 22
---

# BUG-3276: Built-in loops hardcode this-repo-specific project commands — incremental-refactor reverts all work in consuming projects

## Summary

`incremental-refactor.yaml` declares `test_cmd: "python -m pytest scripts/tests/"` as a
context default (`:12`) and executes it bare as an exit-code-gated state (`:31-36`).
`scripts/tests/` is *this repository's* test directory. In any consuming project that path
does not exist, so pytest exits non-zero on every lap, `on_no: revert` fires, and `revert`
runs `git checkout -- .` (`:57-60`) — discarding **all** uncommitted work in the tree, not
just the failed step. The loop then re-plans and repeats.

This is the same defect class as BUG-3269 (a mis-resolved project command corrupting a
gate) arriving through a different mechanism: not a divergent config *read*, but no config
read at all. BUG-3269's mirror-drift gate scans for inline `.ll/ll-config.json` access
patterns, so it does not and will not cover this site.

Split out of BUG-3269's design review — see that issue's *Similar Patterns* section for the
scope rationale.

## Current Behavior

`scripts/little_loops/loops/incremental-refactor.yaml`:

```yaml
context:
  refactor_goal: ""
  test_cmd: "python -m pytest scripts/tests/"     # :12 — this repo's test path

  verify_tests:                                    # :31
    action: "${context.test_cmd}"
    action_type: shell                             # exit-code gated
    on_yes: commit_step
    on_no: revert
    on_error: revert

  revert:                                          # :57
    action: "git checkout -- ."
    action_type: shell
    next: replan
```

There is no `.ll/ll-config.json` read anywhere in the file, and no fallback: the hardcoded
literal is the only source for the command.

**Failure chain in a consuming project** (any project whose tests are not under
`scripts/tests/`):

1. `execute_step` makes a real, correct refactoring change.
2. `verify_tests` runs `python -m pytest scripts/tests/` → pytest exits 4 (usage error, no
   such directory) or 2 (collection error).
3. Non-zero → `on_no: revert`.
4. `revert` runs `git checkout -- .` — **the step's work is discarded, along with any other
   uncommitted changes in the working tree**.
5. `replan` → `execute_step` → step 2. Every lap destroys work, up to `max_steps: 30` or
   `replan`'s `max_retries: 3` → `failed`.

The loop cannot succeed in any project but this one, and it does not fail cleanly — it
deletes uncommitted work on the way.

**Severity note.** `git checkout -- .` is unscoped. A user with unrelated uncommitted
changes in the tree when the loop runs loses those too. That is why this is P1 rather than
P2 despite the narrow trigger.

## Steps to Reproduce

1. In any project that is not this repository, ensure `scripts/tests/` does not exist.
2. Leave an unrelated uncommitted change in the working tree.
3. Run `incremental-refactor` with any `refactor_goal`.
4. Observe: after the first `execute_step`, `verify_tests` fails and `revert` discards both
   the step's changes and the unrelated uncommitted change.

**Frequency**: deterministic in every project without a `scripts/tests/` directory —
i.e. every consuming project.

## Expected Behavior

- `verify_tests` resolves the test command from project configuration, with the same
  three-way semantics BUG-3269 establishes: key absent → the `ProjectConfig` default; key
  present and `null` → **no test gate**; key present with a value → that value.
- The hardcoded `python -m pytest scripts/tests/` context default is replaced with `""`
  (an override slot), matching `general-task.yaml:23` and `test-coverage-improvement.yaml:23`.
- Under an opt-out (`test_cmd: null`, empty resolution), `verify_tests` must **not** fall
  through to `revert`. Reverting on "no test command configured" destroys work in exchange
  for no signal at all.
- `revert` should scope its checkout to what the step touched rather than the whole tree, or
  the loop should refuse to start with a dirty working tree.

## Motivation

Per `.claude/CLAUDE.md`, all little-loops projects on this machine are `local-editable`
against this checkout, so this ships with no reinstall step. The loop is listed in
`/ll:help` under Code Quality and is directly runnable by any user of any consuming project.
Unlike BUG-3269 — which burns budget on already-completed work — this one destroys work.

## Proposed Solution

1. **Replace the hardcoded context default** with `test_cmd: ""` and resolve in
   `verify_tests` using BUG-3269's context-first shape:

   ```bash
   if [ -n "${context.test_cmd}" ]; then
     CMD="${context.test_cmd}"
   else
     CMD=$(ll-config get project.test_cmd)
   fi
   ```

   Do **not** add a `|| { ...; exit N; }` guard: `verify_tests` is exit-code gated, so a
   non-zero exit routes to `on_no: revert`. See BUG-3269 §1f for the executor routing
   analysis.

2. **Decide the empty-`CMD` branch** — this is the safety decision, equivalent to
   BUG-3269 §2b's row for `dead-code-cleanup`. `verify_tests`'s `on_no` edge is destructive,
   so pass-on-empty is not automatically safe either: passing means committing a refactoring
   step with zero verification. Options:
   - **(a)** Route to `commit_step` with a recorded "no test signal" marker — trusts the
     model's step, matches `fix-quality-and-tests`'s pass-on-empty semantic.
   - **(b)** Route to a new terminal `failed` state — refuses to run an unverifiable
     test-gated refactor at all.
   - **(c)** Refuse at loop start: validate that a test command resolves before
     `plan_steps`, failing fast rather than mid-refactor.

   Recommendation: **(c) plus (b)** — a refactor loop whose entire safety model is
   "test-gated commits" should not start without a test gate, and should not silently
   downgrade to untested commits if one disappears mid-run.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/guides/LOOPS_REFERENCE.md:1305` — the "Key context variables" table's `test_cmd` row documents the old hardcoded literal; replace with the resolution/precondition behavior.
- Add `scripts/tests/test_builtin_loops.py` — a `TestConfidenceGateThresholdsNotHardcoded`-style parametrized test asserting `incremental-refactor.yaml`'s `context.test_cmd == ""` (no hardcoded literal).
- Add `scripts/tests/test_builtin_loops.py` — a `test_harness_optimize.py:145-149`-style test (`test_revert_uses_scoped_targets`) asserting `incremental-refactor.yaml`'s `revert` state scopes to a context variable, not bare `git checkout -- .`.
- If option (c) is taken: update `scripts/tests/test_builtin_loops.py:11786-11789` (`test_required_top_level_fields`)'s `data.get("initial") == "plan_steps"` assertion to match the new initial state, and add a `TestPrePatchCheckReachability`-style precondition test.
- Sibling survey (step 4) is closed: no other loop hardcodes an unresolved project-command literal, and no other loop has an unscoped blanket `git checkout`/`reset`/`clean` beyond the four already-scoped precedents — see the new Sibling Loop Survey subsection of the Integration Map.

3. **Scope or guard `revert`.** Either narrow `git checkout -- .` to the paths the step
   touched, or add a clean-tree precondition at `plan_steps`. Independent of (1) and (2),
   and arguably the more important half: even with a correct `test_cmd`, a genuinely failing
   step currently discards unrelated uncommitted work.

4. **Survey for siblings.** `test-coverage-improvement.yaml:54,57` builds
   `COV_CMD="python -m pytest --cov ..."` as a literal. That one is a *coverage* invocation
   rather than the project's test command, and `project.test_cmd` has no coverage variant,
   so it is likely correct as-is — but confirm rather than assume, and record the finding
   here either way.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- **Resolution pattern (Rule 1, matches this issue's proposed context-first shape) is already implemented in two loops that cite BUG-3269 directly**: `scripts/little_loops/loops/general-task.yaml:24,49-58` (`check_baseline_tests` state) and `scripts/little_loops/loops/rl-coding-agent.yaml:17-21,62-63` (`observe` state, no `context.test_cmd` key at all since `ll-config get` always wins). Two other loops resolve the same context-first shape but via inline `python3 -c` reading `.ll/ll-config.json` directly rather than the `ll-config get` CLI: `test-coverage-improvement.yaml:23,38-48` and `dead-code-cleanup.yaml:66-77`; `fix-quality-and-tests.yaml:62-73` uses the same inline-Python shape with an extra branch. The CLI form (Rule 1) is the more recent, BUG-3269-aligned convention; the inline-Python form (Rule 2) predates it.
- **The empty-`CMD` branch (step 2's open decision) has conflicting precedent across existing loops — not a settled convention**:
  - `general-task.yaml` / `rl-coding-agent.yaml` (both post-BUG-3269): present-and-null resolves to an **opt-out**, never guessing a command. `general-task.yaml` writes a `baseline-skip-reason.txt` sentinel and skips; `rl-coding-agent.yaml` scores `0.0` for that dimension. `rl-coding-agent.yaml`'s comment states this explicitly: "never guess `pytest`/`ruff check` against a null config, which previously scored every rollout against a shell `command not found`."
  - `test-coverage-improvement.yaml` / `dead-code-cleanup.yaml`: any falsy `raw` (key absent OR explicitly null) falls back to the guessed literal `'pytest'` — no opt-out branch.
  - `fix-quality-and-tests.yaml`: splits the two falsy cases — key absent → guessed `'pytest'`; key present-and-null → runs `true` (a no-op that always passes), functionally an opt-out but implemented as "run a trivial passing command" rather than skip-with-sentinel.
  - This disagreement bears directly on options (a)/(b)/(c): the two loops that already cite BUG-3269 both chose an opt-out-without-guessing shape, which is closer to (a)/(b) than to the guessed-default loops. No existing loop implements option (c) (refuse at `plan_steps` before running); no loop in this codebase currently checks working-tree cleanliness as a precondition.
- **Revert/destructive-git scoping (step 3) — the codebase already has scoped-revert precedent to reuse, `incremental-refactor.yaml`'s blanket `git checkout -- .` is the outlier**: `dead-code-cleanup.yaml:84-97` (`revert_and_scan`, prompt-driven `git checkout -- <file>` scoped to the single failing file) and `test-coverage-improvement.yaml:188-197` (`revert`, prompt-driven, scoped to "the new test files" only) scope to specific paths; `harness-optimize.yaml:56-57` scopes to a specific ref and path (`git checkout "$BEST" -- ${context.targets}`); `rn-refine.yaml:513-532` (`revert_leaf_failed`) uses `git reset --hard "$BASELINE"` against a per-leaf recorded commit rather than current HEAD. None of the searched loop YAMLs implement a clean-working-tree precondition check (confirmed via grep for `git status --porcelain` / "working tree" / "clean tree" — no matches).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/incremental-refactor.yaml:12` — context default → `""`
- `scripts/little_loops/loops/incremental-refactor.yaml:31-36` — `verify_tests` resolution
  + empty-`CMD` branch
- `scripts/little_loops/loops/incremental-refactor.yaml:57-60` — `revert` scoping

### Dependent Files (Callers/Importers)
- `scripts/little_loops/config/core.py` — `ProjectConfig.test_cmd` default (`:191`, `:215`);
  read-only here, pinned by BUG-3269's tests
- `scripts/little_loops/cli/config.py` — `ll-config get`, the resolution path

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:1219,1292-1306` — the loop-catalog entry for `incremental-refactor`, whose "Key context variables" table (`:1305`) literally documents `test_cmd | python -m pytest scripts/tests/ | Test command to gate each step`. This row becomes wrong once the context default changes to `""` and must describe the resolution/precondition behavior instead. [Agent for BUG-3276 caller trace / side-effect finding]
- `scripts/little_loops/loops/README.md:52` — one-line loop-catalog description; lower risk, no `test_cmd` mention, but the "rollback and re-plan on failure" phrasing implies scoped/safe revert, worth a pass once revert scoping (step 3) lands.
- `scripts/little_loops/loops/lib/prompt-fragments.yaml:14` — comment noting the `ll_commit` fragment deep-merges "so incremental-refactor.yaml can keep slash_command behaviour" for `commit_step`; unrelated to this fix but a second place that special-cases this loop by name — leave undisturbed, do not let a `commit_step`-adjacent edit break this.
- Confirmed no `commands/*.md`, `skills/*/SKILL.md`, or `/ll:help` entry references `incremental-refactor` — no CLI/command-doc coupling beyond `LOOPS_REFERENCE.md` above.
- Confirmed `scripts/little_loops/fsm/validation/` (MR-1..MR-14, spanning `meta_rules.py`, `shell_safety.py`, `evaluator_rules.py`, `structural_rules.py`) has no rule catching a hardcoded project-command literal in a loop action/context default — this defect class is structurally unguarded by `ll-loop validate` today, consistent with the issue's own framing (BUG-3269's mirror-drift gate won't catch it either).

### Sibling Loop Survey (step 4 of Proposed Solution)

_Wiring pass added by `/ll:wire-issue`:_
- **No additional unscoped `git checkout`/`git reset`/`git clean`/`git stash` sites found.** Grep across `scripts/little_loops/loops/*.yaml` returns only the five files already accounted for: `test-coverage-improvement.yaml:194`, `harness-optimize.yaml:57`, `dead-code-cleanup.yaml:92`, `rn-refine.yaml:523`, and `incremental-refactor.yaml:56` itself. `incremental-refactor.yaml`'s blanket `git checkout -- .` remains the sole outlier requiring scoping.
- **No other loop hardcodes a bare project-command literal without resolving through `test_cmd`/`ll-config get`.** Confirmed already-correct (using the same context-first + `ll-config get` pattern as the fix): `fix-quality-and-tests.yaml:58-75`, `general-task.yaml:120-127`, `rl-coding-agent.yaml:88-96`, `auto-refine-and-implement.yaml:58-67`, `harness-single-shot.yaml`, `harness-multi-item.yaml`, `harness-plan-research-implement-report.yaml`, `loops/lib/common.yaml:225-260` (shared `shell_exit` fragment). One near-miss reviewed and ruled out: `evaluation-quality.yaml:323-324` installs and runs pytest into a per-run venv to test *generated sample code*, not this repo's own `test_cmd` — a different concern, not a sibling instance of this bug.

### Tests
- `scripts/tests/test_builtin_loops.py` — `incremental-refactor` structural assertions; add
  a case asserting `verify_tests` contains no hardcoded `scripts/tests/` literal
- New: `verify_tests` under `test_cmd: null` does not reach `revert`

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — BUG-3269 adds the "resolve project commands
  via `ll-config get`" rule; this issue is the case for extending it to "and never hardcode
  a project command literal in a loop action or context default"

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:1219,1292-1306` — the loop-catalog entry for `incremental-refactor`; its "Key context variables" table (`:1305`) documents `test_cmd | python -m pytest scripts/tests/ | Test command to gate each step` — this row must be rewritten to describe resolution-via-config once the context default changes to `""`.
- `scripts/little_loops/loops/README.md:52` — one-line catalog description; the phrase "rollback and re-plan on failure" implies scoped/safe revert, worth a pass once revert scoping (step 3) lands.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- `scripts/tests/test_general_task_loop.py:1560-1618` (`TestCheckBaselineTestsShellAction`) — closest existing test pattern for the empty-`CMD` branch: runs the extracted shell action script via `subprocess.run(["bash", "-c", script], ...)` against a `tmp_path` fixture with a controlled `.ll/ll-config.json`, asserting on sentinel files (`resolved-test-cmd.txt`, `baseline-exit.txt`). Covers `test_falls_back_to_config_test_cmd`, `test_explicit_null_test_cmd_writes_skip`, `test_unrunnable_command_writes_skip_not_127`, `test_writes_baseline_ref_regardless_of_skip`.
- `scripts/tests/test_builtin_loops.py:10593-10634` (`TestRlCodingAgentObserveTestCmdResolution`) — `test_resolves_config_test_and_lint_cmd`, `test_null_test_cmd_resolves_to_empty_not_a_guessed_default`.
- `scripts/tests/test_builtin_loops.py:11776-11811` (`TestIncrementalRefactorLoop`) — the only existing structural-test class for this loop file today; current assertions (`test_required_top_level_fields`, `test_required_states_exist`, `test_commit_step_uses_ll_commit_fragment`, `test_commit_step_keeps_slash_command_action_type`, `test_done_state_is_terminal`) do not inspect `context.test_cmd`, `verify_tests.action`, or `revert.action` — this is the class the new cases (Tests subsection above) land in.
- No existing test in `test_builtin_loops.py` greps loop YAML source text for a hardcoded command literal (e.g. `"python -m pytest"`) as a structural check across loops; `test_builtin_loops.py:12508`'s `${context.min_pass_rate}`-not-literal assertion is the nearest existing shape but targets a different field/loop (`code-run-gate.yaml`).

_Wiring pass added by `/ll:wire-issue`:_
- **Best "no hardcoded literal" template — better fit than the `${context.min_pass_rate}` one already cited**: `scripts/tests/test_builtin_loops.py:16250-16298` (`TestConfidenceGateThresholdsNotHardcoded`), a `@pytest.mark.parametrize("loop_name", LOOPS)` class asserting a context key is absent/non-literal per loop. The equivalent for this issue: assert `data["context"]["test_cmd"] == ""` in `incremental-refactor.yaml`. New test, no update needed to the cited class itself.
- **Scoped-revert template — direct precedent, copy this**: `scripts/tests/test_harness_optimize.py:145-149` (`test_revert_uses_scoped_targets`) already pins `harness-optimize.yaml`'s `revert_and_log` state scoping via `assert "context.targets" in action`. `incremental-refactor.yaml`'s `revert` state is `action_type: shell` — the same shape as `harness-optimize.yaml`'s — making this the exact template to copy (rename, retarget `incremental-refactor.yaml`'s `revert` state, assert against whatever scoped context var the fix introduces), unlike `dead-code-cleanup.yaml`/`test-coverage-improvement.yaml`'s revert states, which are free-text `action_type: prompt` instructions with no structural pytest coverage to model instead.
- **No existing "refuse to start" / clean-tree precondition test or loop pattern exists** — confirmed via grep for `git status --porcelain`, `clean tree`, `working tree`, `precondition` across `loops/*.yaml` and `scripts/tests/`; only prose/comment hits unrelated to a tree-cleanliness gate. If Proposed Solution option (c) is taken, model the new test on `scripts/tests/test_builtin_loops.py:584` (`TestPrePatchCheckReachability`, a non-LLM shell-evaluated precondition gate with a frozen state-set) or `:10789`/`:10841-10846` (`TestReadyToImplementGateLoop.test_blocked_is_terminal`, template for asserting a new non-happy-path terminal). This is a new test to write, not an existing one to update.
- **Will break, not a gap**: `scripts/tests/test_builtin_loops.py:11786-11789` (`test_required_top_level_fields`) hard-asserts `data.get("initial") == "plan_steps"`. If option (c) prepends a new precondition state ahead of `plan_steps` and changes the FSM's `initial`, this assertion must be updated. `test_required_states_exist` (`:11791-11802`) is a subset check and will NOT break from an added state.
- **Confirmed not a new terminal**: `failed` is already declared `terminal: true`/`failure: true` in `incremental-refactor.yaml` (already reachable from `replan.on_retry_exhausted` and pinned by `TestOnCannotJudgeRoutes.ROUTES:3395` for `check_complete`). Option (b)'s "route to a terminal failed state" is a new *edge* into an existing terminal, not a new terminal — no `NEW_FAILURE_TERMINALS`-style test addition required for the terminal's own `failure: true` declaration.

## Program Design

### Signatures

- `verify_tests(test_cmd: str) -> bool` — gates the refactoring step; returns pass/fail from
  the resolved command's exit code, and must not route an *unresolvable* command to the same
  edge as a *failing* one.
- `revert(paths: list) -> None` — discards step changes; currently unscoped (`git checkout
  -- .`), which is the destructive half of this bug.

### Call Path

- `plan_steps` → `execute_step` → `verify_tests` → `commit_step` (pass) or `revert` (fail)
- `revert` → `replan` → `execute_step` — the destructive cycle
- `verify_tests` → `ll-config get project.test_cmd` — the resolution this issue adds

### Decision Rules

- Resolved command non-empty → run it, gate on exit code as today.
- Resolved command empty (explicit `null`, or unresolvable) → **do not revert**; take the
  branch chosen in Proposed Solution step 2.
- Working tree dirty at `plan_steps` → refuse to start (if option (c) is taken).

## Impact

- **Severity**: P1. Destroys uncommitted work, deterministically, in every project that is
  not this repository. Not merely ineffective.
- **Blast radius**: `incremental-refactor` only. Narrower than BUG-3269, but the failure is
  destructive rather than wasteful.
- **Risk of the fix**: low for steps (1) and (2) — one loop file, mechanically checkable.
  Step (3) changes revert semantics and deserves its own review.
- **Backward compatibility**: in *this* repo the resolved `project.test_cmd`
  (`python -m pytest scripts/tests/`) is byte-identical to the current hardcoded literal, so
  behavior here is unchanged. Every other project changes from "always revert" to "gate on
  the project's real test command".
- **Not fixed by this issue**: BUG-3269's mirror-drift gate scans for config-read patterns
  and will not catch a future hardcoded literal. Whether that gate should additionally flag
  bare `pytest` / `ruff` / `mypy` literals in loop actions is an open question in BUG-3269
  §4; this issue is the second data point arguing yes.

## Related Key Documentation

- BUG-3269 — the sibling defect (divergent config *reads*); its §1f documents why a
  non-zero exit cannot be used to signal a resolution failure at an exit-code-gated state,
  and its §2/§2b document the precedence and empty-`CMD` shapes to reuse here
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — loop design rules

## Status

**Open** | Created: 2026-08-20 | Priority: P1


## Session Log
- `/ll:wire-issue` - 2026-08-21T04:45:06 - `ee8d0c92-9f75-42c4-9e2a-730c3d5d3cb0.jsonl`
- `/ll:refine-issue` - 2026-08-21T04:32:03 - `a85e8b1c-5475-4885-a40b-302d5e096fc6.jsonl`
- `/ll:refine-issue` - 2026-08-21T03:56:04 - `d0214377-90ea-4261-b458-0b3aa6f7a0bc.jsonl`
