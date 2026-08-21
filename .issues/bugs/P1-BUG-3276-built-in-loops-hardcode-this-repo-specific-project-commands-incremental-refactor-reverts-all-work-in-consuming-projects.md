---
id: BUG-3276
type: BUG
title: "Built-in loops hardcode this-repo-specific project commands \u2014 incremental-refactor\
  \ reverts all work in consuming projects"
priority: P1
status: done
discovered_by: design-review
discovered_date: '2026-08-20'
captured_at: '2026-08-20T00:00:00Z'
completed_at: '2026-08-21T13:44:37Z'
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
decision_needed: false
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
   - `git checkout -- .` is also *too narrow* in the other direction: it does not remove
     untracked files. A step that creates a new module leaves that file behind after the
     revert, so `replan` → `execute_step` runs against a partially-reverted tree. The revert
     is simultaneously too broad (tracked, unrelated changes) and incomplete (new files).
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
  the loop should refuse to start with a dirty working tree. Either way, the loop's own
  runtime directory (`.loops/`) must be excluded from both the cleanliness gate and any
  `git clean` — see Proposed Solution step 3.

## Motivation

Per `.claude/CLAUDE.md`, all little-loops projects on this machine are `local-editable`
against this checkout, so this ships with no reinstall step. The loop is listed in
`/ll:help` under Code Quality and is directly runnable by any user of any consuming project.
Unlike BUG-3269 — which burns budget on already-completed work — this one destroys work.

## Proposed Solution

1. **Replace the hardcoded context default** with `test_cmd: ""` and resolve in
   `verify_tests` using BUG-3269's context-first shape. Copy `general-task.yaml:49-58`
   **verbatim, including the `RC` check** — a bare `CMD=$(ll-config get project.test_cmd)`
   silently conflates "`ll-config` is missing/broken" with "the user opted out", and under
   this issue's chosen design an empty `CMD` routes to a *terminal failure*, so that
   conflation is no longer harmless:

   ```bash
   if [ -n "${context.test_cmd}" ]; then
     CMD="${context.test_cmd}"
   else
     CMD=$(ll-config get project.test_cmd)
     RC=$?
     if [ "$RC" != "0" ]; then
       echo "ll-config not found (exit $RC)" > "${context.run_dir}/verify-skip-reason.txt"
       CMD=""
     fi
   fi
   ```

   Do **not** let a resolution failure exit non-zero *unclassified*: `verify_tests` is
   exit-code gated, so an undistinguished non-zero exit routes to `on_no: revert`. See
   BUG-3269 §1f for the executor routing analysis, and step (2) below for the exit-code
   contract that keeps resolution failure off the `revert` edge.

2. **Decide the empty-`CMD` branch** — this is the safety decision, equivalent to
   BUG-3269 §2b's row for `dead-code-cleanup`. `verify_tests`'s `on_no` edge is destructive,
   so pass-on-empty is not automatically safe either: passing means committing a refactoring
   step with zero verification. Options:

**Option A**: Route to `commit_step` with a recorded "no test signal" marker — trusts the
model's step, matches `fix-quality-and-tests`'s pass-on-empty semantic.

**Option B**: Route to a new terminal `failed` state — refuses to run an unverifiable
test-gated refactor at all.

**Option C**: Refuse at loop start: validate that a test command resolves before
`plan_steps`, failing fast rather than mid-refactor.

**Recommended**: Option C plus Option B — a refactor loop whose entire safety model is
"test-gated commits" should not start without a test gate, and should not silently
downgrade to untested commits if one disappears mid-run.

> **Selected:** Option C + Option B — refuse to start when `test_cmd` doesn't resolve
> (`plan_steps` precondition), and route to the existing `failed` terminal as a
> mid-run defense if the resolved command later becomes unresolvable. Option A's
> pass-on-empty semantic has better isolated codebase reuse, but it reintroduces the
> exact class of risk this P1 bug exists to close: an unverified refactoring step
> gets silently committed. See Decision Rationale below.

#### Mechanism for the empty-`CMD` branch (corrects the "new wiring" note in Decision Rationale)

The Decision Rationale's key-evidence line for Option B claims no `action_type: shell` state
can branch "precondition empty" vs. "command failed" to two different targets. **That is
wrong** — `evaluate_exit_code` (`scripts/little_loops/fsm/evaluators.py:238-264`) already
gives shell states a four-way verdict space, and `abstain_on_exit_3` is schema-supported
(ENH-3224, `scripts/little_loops/fsm/schema.py:113,158-159,210`):

| exit code | verdict | edge on `verify_tests` |
|---|---|---|
| `0` | `yes` | `commit_step` |
| `1` | `no` | `revert` |
| `3` | `cannot_judge` — **only** when `abstain_on_exit_3: true` | `on_cannot_judge: failed` |
| anything else | `error` | `on_error` |

Option B is therefore a two-line change, not new wiring. Its Simplicity score of 1/3 below is
understated; this does not change the C+B selection, only its cost.

**The wrapper must own the exit-code space.** pytest's own codes collide with the table:
`2` (interrupted), `3` (internal error), `4` (usage error — the exact code this bug's failure
chain produces), and `5` (no tests collected) all currently land on `on_error`, which today
points at `revert` alongside `on_no`. Normalize inside the action so only the wrapper can
emit `3`:

```bash
[ -z "$CMD" ] && exit 3        # unresolvable / opt-out -> cannot_judge -> failed
sh -c "$CMD"; rc=$?
[ "$rc" = 0 ] && exit 0        # pass -> commit_step
exit 1                         # every real failure -> on_no: revert, as today
```

with `abstain_on_exit_3: true` and `on_cannot_judge: failed` on the state. This preserves
today's "any test failure reverts" semantic exactly while carving the resolution failure out
of it.

**Reuse the `harness_exit` fragment rather than hand-rolling `evaluate:`.**
`scripts/little_loops/loops/lib/common.yaml:23-36` already defines a fragment for exactly this
`0=pass / 1=fail / 3=abstained` contract (`action_type: shell` + `evaluate: {type: exit_code,
abstain_on_exit_3: true}`), and its own docstring requires the caller to declare
`on_cannot_judge`. `incremental-refactor.yaml:15-17` already imports `lib/common.yaml`, so
`verify_tests` becomes `fragment: harness_exit` plus `action`/`on_yes`/`on_no`/
`on_cannot_judge`/`on_error`. This raises Option B's consistency score and drops its cost
below even the "two-line change" estimate above.

**`on_error` must be repointed to `failed`, not left at `revert`.** Earlier drafts left this
as "an acceptable variant"; it is not optional. Once the wrapper owns the exit-code space,
`on_error` can no longer fire on a test failure — the only remaining triggers are a state
timeout or a signal kill, i.e. cases with *no test signal at all*, which is precisely what the
`3`-carve-out exists to keep off the destructive edge. Leaving `on_error: revert` reintroduces
the "destroy work in exchange for no signal" failure this issue exists to close, through a
narrower door. `on_no: revert` remains the only edge into `revert`.

**Abstention routes immediately — no hold.** `_abstention_declared()` /
`_route_abstention_hold()` (`scripts/little_loops/fsm/executor.py:2669-2725`) apply the
`_ABSTENTION_HOLD_CAP = 2` re-execution hold only to *undeclared* abstentions. With
`on_cannot_judge: failed` declared, a `3` transitions on the first evaluation; `verify_tests`
does not re-run the resolution twice before failing. The declared route also satisfies
`_validate_abstention_route` (`scripts/little_loops/fsm/validation/structural_rules.py:1483+`),
so no `abstention_route_ok` suppression is needed.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/guides/LOOPS_REFERENCE.md:1305` — the "Key context variables" table's `test_cmd` row documents the old hardcoded literal; replace with the resolution/precondition behavior.
- Add `scripts/tests/test_builtin_loops.py` — a `TestConfidenceGateThresholdsNotHardcoded`-style parametrized test asserting `incremental-refactor.yaml`'s `context.test_cmd == ""` (no hardcoded literal).
- Add `scripts/tests/test_builtin_loops.py` — a `test_harness_optimize.py:145-149`-style test (`test_revert_uses_scoped_targets`) asserting `incremental-refactor.yaml`'s `revert` state scopes to a context variable, not bare `git checkout -- .`.
- If option (c) is taken: update `scripts/tests/test_builtin_loops.py:11944-11947` (`test_required_top_level_fields`)'s `data.get("initial") == "plan_steps"` assertion to match the new initial state, and add a `TestPrePatchCheckReachability`-style precondition test.
- Sibling survey (step 4) is closed: no other loop hardcodes an unresolved project-command literal, and no other loop has an unscoped blanket `git checkout`/`reset`/`clean` beyond the four already-scoped precedents — see the new Sibling Loop Survey subsection of the Integration Map.

3. **Guard `revert` with a clean-tree precondition — not by narrowing the checkout.**
   Earlier drafts framed these as alternatives ("narrow `git checkout -- .` to the paths the
   step touched, *or* add a clean-tree precondition"). Path-narrowing is not implementable as
   written: `execute_step` is `action_type: prompt` (with `fragment: diff_stall_gate`) and
   nothing records touched files into context, so there is no scoped context variable to
   narrow to and none can be produced without adding a further shell state to capture
   `git diff --name-only`.

   The clean-tree precondition is not a weaker substitute — **it is what makes the blanket
   revert correct.** If `git status --porcelain` is empty at loop start, then at every
   `revert` all uncommitted content *is* the failed step's work, because each accepted step
   is committed by `commit_step` and HEAD advances every lap. One precondition state
   therefore serves both step (2) and step (3), and this — not the tie-break in the Decision
   Rationale — is the strongest argument for Option C.

   Given that invariant, `revert` becomes:

   ```bash
   git checkout -- . && git clean -fd -e .loops
   ```

   `git clean -fd` closes the *too-narrow* half of the defect (untracked files created by the
   step survive a bare `git checkout -- .`). It is safe only under the invariant, which is
   why the precondition must reject untracked files too. Do not weaken the gate to
   `--untracked-files=no`.

   **`.loops/` must be excluded from both the gate and the clean — this is a blocker, not a
   refinement.** (Found 2026-08-21 during pre-implementation review.) `ll-init`'s gitignore
   block — `_GITIGNORE_ENTRIES`, `scripts/little_loops/init/writers.py:59-72` — contains **no
   `.loops/` entry at all**; a grep of `scripts/little_loops/init/` for `.loops` returns zero
   hits. This repository's own `.gitignore:81-89` carries those entries, but they are
   hand-maintained here and are not deployed to consuming projects. Consequences:

   - By the time the initial state runs, `.loops/runs/<id>/` and `.loops/.running/` exist and
     are untracked-and-unignored in a consuming project, so a bare `git status --porcelain`
     reports `?? .loops/` and the precondition **refuses to start — deterministically, in
     every consuming project.** That is this bug's own signature failure shape (works in this
     repo, breaks everywhere else) reintroduced by its fix, and it would not reproduce during
     local development here.
   - `git clean -fd` skips ignored paths, so `.loops/` survives in *this* repo but is
     **deleted in a consuming project** — taking the active run directory and the persisted
     FSM state with it, mid-run.

   Exclude at the pathspec level, which is correct regardless of the target project's
   gitignore state (both forms verified against a scratch repo containing `.loops/runs/x/a`
   and an untracked `src.py`):

   ```bash
   git status --porcelain -- ':(exclude).loops'   # precondition gate
   git checkout -- . && git clean -fd -e .loops   # revert
   ```

   Adding `.loops/` to `_GITIGNORE_ENTRIES` is separately worthwhile, but it cannot be the
   primary mechanism: it does nothing for already-initialized projects. Treat it as an
   optional follow-up, not part of this fix's correctness argument.

4. **Survey for siblings.** `test-coverage-improvement.yaml:54,57` builds
   `COV_CMD="python -m pytest --cov ..."` as a literal. That one is a *coverage* invocation
   rather than the project's test command, and `project.test_cmd` has no coverage variant,
   so it is likely correct as-is — but confirm rather than assume, and record the finding
   here either way. **Closed** — see the Sibling Loop Survey subsection of the Integration
   Map; no further sibling instances exist.

5. **Extend the harness design rule — in scope, not an open argument.** Add to
   `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`, alongside BUG-3269's "resolve project
   commands via `ll-config get`": *never hardcode a project command literal in a loop action
   or context default.* Earlier drafts left this phrased as a case to be argued; it is an
   acceptance criterion of this issue. Whether `ll-loop validate` should **enforce** it as a
   new MR rule stays out of scope here (BUG-3269 §4) — this is a documentation change only.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- **Resolution pattern (Rule 1, matches this issue's proposed context-first shape) is already implemented in two loops that cite BUG-3269 directly**: `scripts/little_loops/loops/general-task.yaml:24,49-58` (`check_baseline_tests` state) and `scripts/little_loops/loops/rl-coding-agent.yaml:17-21,62-63` (`observe` state, no `context.test_cmd` key at all since `ll-config get` always wins). Two other loops resolve the same context-first shape but via inline `python3 -c` reading `.ll/ll-config.json` directly rather than the `ll-config get` CLI: `test-coverage-improvement.yaml:23,38-48` and `dead-code-cleanup.yaml:66-77`; `fix-quality-and-tests.yaml:62-73` uses the same inline-Python shape with an extra branch. The CLI form (Rule 1) is the more recent, BUG-3269-aligned convention; the inline-Python form (Rule 2) predates it.
- **The empty-`CMD` branch (step 2's open decision) has conflicting precedent across existing loops — not a settled convention**:
  - `general-task.yaml` / `rl-coding-agent.yaml` (both post-BUG-3269): present-and-null resolves to an **opt-out**, never guessing a command. `general-task.yaml` writes a `baseline-skip-reason.txt` sentinel and skips; `rl-coding-agent.yaml` scores `0.0` for that dimension. `rl-coding-agent.yaml`'s comment states this explicitly: "never guess `pytest`/`ruff check` against a null config, which previously scored every rollout against a shell `command not found`."
  - `test-coverage-improvement.yaml` / `dead-code-cleanup.yaml`: any falsy `raw` (key absent OR explicitly null) falls back to the guessed literal `'pytest'` — no opt-out branch.
  - `fix-quality-and-tests.yaml`: splits the two falsy cases — key absent → guessed `'pytest'`; key present-and-null → runs `true` (a no-op that always passes), functionally an opt-out but implemented as "run a trivial passing command" rather than skip-with-sentinel.
  - This disagreement bears directly on options (a)/(b)/(c): the two loops that already cite BUG-3269 both chose an opt-out-without-guessing shape, which is closer to (a)/(b) than to the guessed-default loops. No existing loop implements option (c) (refuse at `plan_steps` before running); no loop in this codebase currently checks working-tree cleanliness as a precondition.
- **Revert/destructive-git scoping (step 3) — the codebase already has scoped-revert precedent to reuse, `incremental-refactor.yaml`'s blanket `git checkout -- .` is the outlier**: `dead-code-cleanup.yaml:84-97` (`revert_and_scan`, prompt-driven `git checkout -- <file>` scoped to the single failing file) and `test-coverage-improvement.yaml:188-197` (`revert`, prompt-driven, scoped to "the new test files" only) scope to specific paths; `harness-optimize.yaml:56-57` scopes to a specific ref and path (`git checkout "$BEST" -- ${context.targets}`); `rn-refine.yaml:513-532` (`revert_leaf_failed`) uses `git reset --hard "$BASELINE"` against a per-leaf recorded commit rather than current HEAD. None of the searched loop YAMLs implement a clean-working-tree precondition check (confirmed via grep for `git status --porcelain` / "working tree" / "clean tree" — no matches).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-20.

**Selected**: Option C + Option B (refuse to start when `test_cmd` is unresolvable; route to
the existing `failed` terminal as a mid-run defense)

**Reasoning**: Option A (pass-on-empty with a recorded marker) scores highest in isolation on
codebase-pattern reuse — `fix-quality-and-tests.yaml`'s `true`-substitution and
`general-task.yaml`'s `run_final_tests` bare `exit 0` are direct precedent for silent
pass-through, and `general-task.yaml`'s `check_baseline_tests` sentinel is direct precedent
for the marker half. But this is a P1 bug specifically about `incremental-refactor` destroying
uncommitted work; Option A reintroduces the underlying danger in a new shape — committing an
unverified refactoring step — which the issue's own Expected Behavior section rules out
("must not fall through to revert... in exchange for no signal at all" applies equally to
committing with no signal). Option C's `initial: <precondition-state>` shape is directly
reused from `general-task.yaml`/`code-run-gate.yaml`/`spike-gate.yaml`, and Option B's
route-into-an-existing-`failed`-terminal shape is reused from `incremental-refactor.yaml`'s
own `check_complete.on_cannot_judge`/`replan.on_retry_exhausted` edges and the
`TestOnCannotJudgeRoutes` convention (11 existing call sites) — both pieces compose known FSM
shapes even though the specific "empty precondition" trigger is new. `rl-coding-agent.yaml`'s
`observe` state (scoring `0.0` rather than trusting an empty command) is corroborating
evidence that this codebase does not treat "no test signal" as safe-to-pass uniformly.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (pass-on-empty + marker) | 2/3 | 3/3 | 3/3 | 1/3 | 9/12 |
| Option B (route to `failed`) alone | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |
| Option C (refuse at loop start) alone | 2/3 | 1/3 | 2/3 | 3/3 | 8/12 |
| **Option C + Option B (selected)** | 2/3 | 1/3 | 3/3 | 3/3 | **9/12** |

**Key evidence**:
- Option A: `fix-quality-and-tests.yaml:58-77` (`true` substitution), `general-task.yaml:677-685` (`run_final_tests` bare `exit 0`), `general-task.yaml:36-70` (`baseline-skip-reason.txt` marker) — but `rl-coding-agent.yaml:56-70` scores empty `test_cmd` as `0.0`, not a pass, showing the convention is contested.
- Option B: `incremental-refactor.yaml:53` (`check_complete.on_cannot_judge: failed`) and `:64` (`replan.on_retry_exhausted: failed`) are same-file precedent for a new edge into the existing `failed` terminal; `TestOnCannotJudgeRoutes` (`test_builtin_loops.py:3534-3555`) pins 11 such edges codebase-wide. ~~No existing `action_type: shell` state branches "precondition empty" vs. "command failed" to two different targets — new wiring.~~ **Corrected 2026-08-21**: this was wrong, and it is why Option B scores 1/3 on Simplicity below. `evaluate_exit_code` (`evaluators.py:238-264`) already yields four verdicts from a shell exit code, and `abstain_on_exit_3` (`schema.py:113`) is schema-supported. The branch is a two-line change — see *Mechanism for the empty-`CMD` branch* above. The selection is unchanged; only B's cost estimate was inflated.
- Option C: `general-task.yaml:4,36-74` (`check_baseline_tests` as `initial`), `oracles/code-run-gate.yaml:24` (`resolve_commands` as `initial`) establish the `initial: <precondition-state>` shape — but every existing instance of it (including `general-task.yaml`'s identical `test_cmd`-resolution case) resolves an empty value by skipping forward, never by refusing to start; the "refuse" behavior itself has no precedent and is the one genuinely new piece of this decision.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/incremental-refactor.yaml:12` — context default → `""`
- `scripts/little_loops/loops/incremental-refactor.yaml:31-36` — `verify_tests` resolution
  + empty-`CMD` branch
- `scripts/little_loops/loops/incremental-refactor.yaml:57-60` — `revert` scoping

_Optional follow-up, not required for this fix's correctness:_
- `scripts/little_loops/init/writers.py:59-72` — `_GITIGNORE_ENTRIES` has no `.loops/` entry,
  so consuming projects leave the loop runtime dir untracked-and-unignored. Adding one is
  independently worthwhile but does nothing for already-initialized projects; the
  `':(exclude).loops'` pathspec (step 3) is what makes the fix correct. Consider splitting to
  its own issue rather than widening this one.

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
- New (behavioural, model on `TestCheckBaselineTestsShellAction`): extract `verify_tests`'s
  shell action and run it via `subprocess.run(["bash", "-c", script])` against a `tmp_path`
  with a controlled `.ll/ll-config.json`, asserting the **exit-code contract** from step (2):
  empty/unresolvable → `3`; passing command → `0`; failing command → `1`; and that a command
  exiting `4` (pytest usage error — this bug's own failure mode) maps to `1`, not to `3`.
- New: `verify_tests` resolves `abstain_on_exit_3: true` and declares `on_cannot_judge: failed`
  (structural, asserted post-fragment-resolution), so the `3` above cannot silently degrade to
  `on_error`.
- New (structural): `verify_tests.on_error == "failed"`, and `revert` has exactly one inbound
  edge across the whole FSM — `verify_tests.on_no`. Pins AC (3b) against a future edit
  re-pointing `on_error` back at `revert`.
- New (behavioural, `.loops` exclusion — the blocker in step 3): against a `tmp_path` git repo
  containing an untracked `.loops/runs/x/` and nothing else, the precondition state's script
  must exit **pass**, not refuse. Add the mirror case: an untracked `src.py` alongside
  `.loops/` must still refuse. Without the first assertion the loop is unrunnable in every
  consuming project, and no in-repo test would catch it, since this repo gitignores `.loops/`.
- New (behavioural): after `revert` runs in a `tmp_path` repo, an untracked file created by
  the step is gone **and** `.loops/runs/x/` still exists. Pins `-e .loops`.
- New: the clean-tree precondition state rejects a dirty tree **including untracked files**
  — a `??`-only status (outside `.loops`) must refuse to start.
- New: `revert` includes `git clean -fd -e .loops` (untracked-file half of the defect),
  alongside the `test_revert_uses_scoped_targets`-style assertion already noted above.
- New (AC 9, resume): a resumed run does not re-execute the precondition. Model on the
  existing persistence/resume tests; assert `resume()` leaves `current_state` at the persisted
  value rather than `fsm.initial` for this loop.

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — BUG-3269 adds the "resolve project commands
  via `ll-config get`" rule; this issue is the case for extending it to "and never hardcode
  a project command literal in a loop action or context default"

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:1219,1292-1306` — the loop-catalog entry for `incremental-refactor`; its "Key context variables" table (`:1305`) documents `test_cmd | python -m pytest scripts/tests/ | Test command to gate each step` — this row must be rewritten to describe resolution-via-config once the context default changes to `""`.
- `scripts/little_loops/loops/README.md:52` — one-line catalog description; the phrase "rollback and re-plan on failure" implies scoped/safe revert, worth a pass once revert scoping (step 3) lands.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- `scripts/tests/test_general_task_loop.py:1802-1860` (`TestCheckBaselineTestsShellAction`) — closest existing test pattern for the empty-`CMD` branch: runs the extracted shell action script via `subprocess.run(["bash", "-c", script], ...)` against a `tmp_path` fixture with a controlled `.ll/ll-config.json`, asserting on sentinel files (`resolved-test-cmd.txt`, `baseline-exit.txt`). Covers `test_falls_back_to_config_test_cmd`, `test_explicit_null_test_cmd_writes_skip`, `test_unrunnable_command_writes_skip_not_127`, `test_writes_baseline_ref_regardless_of_skip`.
- `scripts/tests/test_builtin_loops.py:10751-10806` (`TestRlCodingAgentObserveTestCmdResolution`) — `test_resolves_config_test_and_lint_cmd`, `test_null_test_cmd_resolves_to_empty_not_a_guessed_default`.
- `scripts/tests/test_builtin_loops.py:11934-11969` (`TestIncrementalRefactorLoop`) — the only existing structural-test class for this loop file today; current assertions (`test_required_top_level_fields`, `test_required_states_exist`, `test_commit_step_uses_ll_commit_fragment`, `test_commit_step_keeps_slash_command_action_type`, `test_done_state_is_terminal`) do not inspect `context.test_cmd`, `verify_tests.action`, or `revert.action` — this is the class the new cases (Tests subsection above) land in.
- No existing test in `test_builtin_loops.py` greps loop YAML source text for a hardcoded command literal (e.g. `"python -m pytest"`) as a structural check across loops; `test_builtin_loops.py:12674`'s `${context.min_pass_rate}`-not-literal assertion is the nearest existing shape but targets a different field/loop (`code-run-gate.yaml`).

_Wiring pass added by `/ll:wire-issue`:_
- **Best "no hardcoded literal" template — better fit than the `${context.min_pass_rate}` one already cited**: `scripts/tests/test_builtin_loops.py:16408-16452` (`TestConfidenceGateThresholdsNotHardcoded`), a `@pytest.mark.parametrize("loop_name", LOOPS)` class asserting a context key is absent/non-literal per loop. The equivalent for this issue: assert `data["context"]["test_cmd"] == ""` in `incremental-refactor.yaml`. New test, no update needed to the cited class itself.
- **Scoped-revert template — direct precedent, copy this**: `scripts/tests/test_harness_optimize.py:145-149` (`test_revert_uses_scoped_targets`) already pins `harness-optimize.yaml`'s `revert_and_log` state scoping via `assert "context.targets" in action`. `incremental-refactor.yaml`'s `revert` state is `action_type: shell` — the same shape as `harness-optimize.yaml`'s — making this the exact template to copy (rename, retarget `incremental-refactor.yaml`'s `revert` state, assert against whatever scoped context var the fix introduces), unlike `dead-code-cleanup.yaml`/`test-coverage-improvement.yaml`'s revert states, which are free-text `action_type: prompt` instructions with no structural pytest coverage to model instead.
- **No existing "refuse to start" / clean-tree precondition test or loop pattern exists** — confirmed via grep for `git status --porcelain`, `clean tree`, `working tree`, `precondition` across `loops/*.yaml` and `scripts/tests/`; only prose/comment hits unrelated to a tree-cleanliness gate. If Proposed Solution option (c) is taken, model the new test on `scripts/tests/test_builtin_loops.py:584` (`TestPrePatchCheckReachability`, a non-LLM shell-evaluated precondition gate with a frozen state-set) or `:10947`/`:10999-11004` (`TestReadyToImplementGateLoop.test_blocked_is_terminal`, template for asserting a new non-happy-path terminal). This is a new test to write, not an existing one to update.
- **Will break, not a gap**: `scripts/tests/test_builtin_loops.py:11944-11947` (`test_required_top_level_fields`) hard-asserts `data.get("initial") == "plan_steps"`. If option (c) prepends a new precondition state ahead of `plan_steps` and changes the FSM's `initial`, this assertion must be updated. `test_required_states_exist` (`:11949-11960`) is a subset check and will NOT break from an added state.
- **Confirmed not a new terminal**: `failed` is already declared `terminal: true`/`failure: true` in `incremental-refactor.yaml` (already reachable from `replan.on_retry_exhausted` and pinned by `TestOnCannotJudgeRoutes.ROUTES:3553` for `check_complete`). Option (b)'s "route to a terminal failed state" is a new *edge* into an existing terminal, not a new terminal — no `NEW_FAILURE_TERMINALS`-style test addition required for the terminal's own `failure: true` declaration.

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

## Acceptance Criteria

_Added 2026-08-21 during pre-implementation review. Steps 1–5 of Proposed Solution are the
design; these are the checkable outcomes._

1. `incremental-refactor.yaml`'s `context.test_cmd` is `""` — no project-command literal
   anywhere in the file (context defaults or state actions).
2. `verify_tests` resolves context-first, then `ll-config get project.test_cmd` **with the
   `RC` check**, matching `general-task.yaml:49-58`.
3. `verify_tests` implements the exit-code contract: `3` = unresolvable/opt-out, `1` = any
   real test failure, `0` = pass; it obtains `abstain_on_exit_3: true` by reusing the
   `harness_exit` fragment (`loops/lib/common.yaml:23-36`) rather than a hand-written
   `evaluate:` block, and declares `on_cannot_judge: failed`. A resolution failure never
   reaches `revert`.
3b. `verify_tests` declares `on_error: failed`. `on_no: revert` is the **only** remaining
   edge into `revert`; no timeout or signal kill can route to a destructive revert.
4. A clean-tree precondition state runs before `plan_steps` and is the FSM's `initial`;
   it refuses to start on any non-empty `git status --porcelain -- ':(exclude).loops'`,
   untracked files included. The `.loops` exclusion is mandatory — without it the gate
   refuses to start in every consuming project (see Proposed Solution step 3). Its failure
   message names both `project.test_cmd` and the clean-tree requirement, and tells the user
   to `git stash` (or commit) outstanding work.
5. `revert` performs `git checkout -- . && git clean -fd -e .loops`, valid under (4)'s
   invariant. The `-e .loops` is mandatory — without it the revert deletes the active run
   directory and persisted FSM state in any consuming project.
6. `ll-loop validate incremental-refactor` passes (MR-1..MR-14), and
   `python -m pytest scripts/tests/` exits 0 — including the updated
   `test_required_top_level_fields` `initial` assertion (`test_builtin_loops.py:11944-11947`).
7. Tests from the Tests subsection above exist and pass.
8. `docs/guides/LOOPS_REFERENCE.md:1305`'s `test_cmd` row and
   `scripts/little_loops/loops/README.md:52` describe the new behavior; the "never hardcode a
   project command literal" rule is added to `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`
   (step 5).
9. Resume re-enters the persisted `current_state`, not the precondition — see Resolved
   Question below. No "first lap only" guard is implemented, and a regression test pins that
   a resumed run does not re-run the precondition.

### Resolved Question (was open; closed 2026-08-21 during pre-implementation review)

This loop sets `on_handoff: spawn`, so a resumed run must re-enter at the persisted
`current_state`, **not** at `initial` — otherwise AC (4)'s precondition fires mid-refactor
against a legitimately dirty tree (uncommitted step work) and refuses to continue, turning a
safety gate into a resume-breaker.

**Confirmed safe.** `LoopRunner.resume()` restores the executor's position directly —
`self._executor.current_state = state.current_state`
(`scripts/little_loops/fsm/persistence.py:1022`, inside the `resume()` body beginning at
`:1006`) — after gating on `RESUMABLE_STATUSES`. The FSM does not re-enter `fsm.initial` on
resume; `executor.py:253` sets `current_state = fsm.initial` only at construction, and
`resume()` overwrites it. **No first-lap guard is needed.** Keep AC (9)'s regression test
anyway, since this invariant is what makes the precondition safe to add at all.

## Impact

- **Severity**: P1. Destroys uncommitted work, deterministically, in every project that is
  not this repository. Not merely ineffective.
- **Blast radius**: `incremental-refactor` only. Narrower than BUG-3269, but the failure is
  destructive rather than wasteful.
- **Risk of the fix**: low for steps (1) and (2) — one loop file, mechanically checkable.
  Step (3) changes revert semantics and deserves its own review; note it is now *coupled* to
  the step (4) precondition rather than independent of it — `git clean -fd` is only safe under
  the clean-tree invariant, so the two must land together or not at all.
- **New failure mode introduced (accepted)**: on a project with no resolvable `test_cmd`, the
  loop now refuses to start instead of running. That is the intended trade — an unverifiable
  test-gated refactor should not run — but it means users of projects without `project.test_cmd`
  configured see a hard stop where they previously saw (destructive) motion. The precondition's
  failure message must name `project.test_cmd` and the clean-tree requirement explicitly, and
  must give the remedy (`git stash` or commit) rather than only stating the requirement — this
  is a stop users will hit routinely, not an edge case.
- **Near-miss worth recording**: as originally specified, the step-(3) precondition would have
  refused to start in *every* consuming project, because `ll-init` never gitignores `.loops/`
  and the run directory is untracked by the time the gate runs. The fix would have reproduced
  this bug's exact signature — correct in this repo, broken everywhere else — and local
  development here could not have surfaced it. The `':(exclude).loops'` pathspec is the
  load-bearing detail; see Proposed Solution step 3.
- **Backward compatibility**: in *this* repo the resolved `project.test_cmd`
  (`python -m pytest scripts/tests/`) is byte-identical to the current hardcoded literal, so
  behavior here is unchanged. Every other project changes from "always revert" to "gate on
  the project's real test command".
- **Not fixed by this issue**: BUG-3269's mirror-drift gate scans for config-read patterns
  and will not catch a future hardcoded literal. Whether that gate should additionally flag
  bare `pytest` / `ruff` / `mypy` literals in loop actions is an open question in BUG-3269
  §4; this issue is the second data point arguing yes.

## Related Key Documentation

- BUG-3269 — the sibling defect (divergent config *reads*), **status `done`** as of
  2026-08-21, so the `ll-config get project.test_cmd` null semantics this issue builds on are
  already landed — no ordering dependency, `relates_to` is the correct edge; its §1f documents why a
  non-zero exit cannot be used to signal a resolution failure at an exit-code-gated state,
  and its §2/§2b document the precedence and empty-`CMD` shapes to reuse here
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — loop design rules

## Resolution

Implemented the selected Option C + Option B design exactly as specified in Proposed
Solution / Acceptance Criteria:

- `context.test_cmd` is now `""`; the hardcoded `python -m pytest scripts/tests/` literal is
  gone from `incremental-refactor.yaml` entirely (context and every state action).
- New `check_preconditions` state is the FSM's `initial`. It resolves `test_cmd`
  context-first / `ll-config get project.test_cmd` (with the `RC` check) and requires a
  clean working tree via `git status --porcelain -- ':(exclude).loops'` (untracked files
  included); refuses to start (routes to `failed`) if either condition fails, with a failure
  message naming both `project.test_cmd` and the clean-tree requirement plus the `git stash`
  remedy.
- `verify_tests` now resolves per step with the same context-first/`ll-config get` shape,
  reuses the `harness_exit` fragment (`abstain_on_exit_3: true`) so it owns the exit-code
  space (`3`=unresolvable → `on_cannot_judge: failed`, `1`=any real failure → `revert`,
  `0`=pass → `commit_step`), and declares `on_error: failed` so no timeout/signal kill can
  reach the destructive edge. `revert` now has exactly one inbound edge (`verify_tests.on_no`).
- `revert` is `git checkout -- . && git clean -fd -e .loops` — correct under
  `check_preconditions`' clean-tree invariant, and `-e .loops` keeps the active run directory
  and persisted FSM state alive in consuming projects (`ll-init` does not gitignore `.loops/`).
- Updated `docs/guides/LOOPS_REFERENCE.md`, `scripts/little_loops/loops/README.md`, and added
  the "never hardcode a project command literal" rule to
  `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`.
- Tests: structural assertions extended in `scripts/tests/test_builtin_loops.py`
  (`TestIncrementalRefactorLoop`, plus a new `TestOnCannotJudgeRoutes.ROUTES` entry);
  behavioural shell-execution coverage added in new
  `scripts/tests/test_incremental_refactor_loop.py` (exit-code contract including the
  exit-4→1 pytest-usage-error mapping, `.loops` exclusion on both the precondition gate and
  revert, untracked-file rejection); a resume regression test added to
  `scripts/tests/test_fsm_persistence.py` confirming a resumed run re-enters the persisted
  `current_state` rather than `check_preconditions`.
- `ll-loop validate incremental-refactor` passes; full suite green except a pre-existing,
  unrelated failure (`test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo`,
  confirmed present on `main` before this change via `git stash`).

## Status

**Open** | Created: 2026-08-20 | Priority: P1


## Session Log
- `/ll:manage-issue` - 2026-08-21T13:43:38 - `c8f7ebbd-0b99-4f71-bbc2-929d36ac69d8.jsonl`
- `/ll:ready-issue` - 2026-08-21T13:24:05 - `1675a156-f682-4482-8218-3bd23d8895a6.jsonl`
- `/ll:confidence-check` - 2026-08-21T13:15:17 - `0d521468-396a-40b1-8135-6a291b58af1a.jsonl`
- `/ll:confidence-check` - 2026-08-21T05:03:13 - `21d9445e-396a-4f1c-8a38-86569c765496.jsonl`
- `/ll:decide-issue` - 2026-08-21T04:57:58 - `89ddbdcc-e3df-48b0-a087-301d49597946.jsonl`
- `/ll:refine-issue` - 2026-08-21T04:51:56 - `f1b83cf4-c090-438e-b615-05796ab30785.jsonl`
- `/ll:wire-issue` - 2026-08-21T04:45:06 - `ee8d0c92-9f75-42c4-9e2a-730c3d5d3cb0.jsonl`
- `/ll:refine-issue` - 2026-08-21T04:32:03 - `a85e8b1c-5475-4885-a40b-302d5e096fc6.jsonl`
- `/ll:refine-issue` - 2026-08-21T03:56:04 - `d0214377-90ea-4261-b458-0b3aa6f7a0bc.jsonl`
