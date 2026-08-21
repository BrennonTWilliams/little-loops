---
id: BUG-3276
type: BUG
title: Built-in loops hardcode this-repo-specific project commands — incremental-refactor
  reverts all work in consuming projects
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

3. **Scope or guard `revert`.** Either narrow `git checkout -- .` to the paths the step
   touched, or add a clean-tree precondition at `plan_steps`. Independent of (1) and (2),
   and arguably the more important half: even with a correct `test_cmd`, a genuinely failing
   step currently discards unrelated uncommitted work.

4. **Survey for siblings.** `test-coverage-improvement.yaml:54,57` builds
   `COV_CMD="python -m pytest --cov ..."` as a literal. That one is a *coverage* invocation
   rather than the project's test command, and `project.test_cmd` has no coverage variant,
   so it is likely correct as-is — but confirm rather than assume, and record the finding
   here either way.

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

### Tests
- `scripts/tests/test_builtin_loops.py` — `incremental-refactor` structural assertions; add
  a case asserting `verify_tests` contains no hardcoded `scripts/tests/` literal
- New: `verify_tests` under `test_cmd: null` does not reach `revert`

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — BUG-3269 adds the "resolve project commands
  via `ll-config get`" rule; this issue is the case for extending it to "and never hardcode
  a project command literal in a loop action or context default"

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
