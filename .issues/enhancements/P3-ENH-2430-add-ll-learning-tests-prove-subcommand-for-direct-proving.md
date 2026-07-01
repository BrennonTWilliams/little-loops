---
id: ENH-2430
title: Add `ll-learning-tests prove` subcommand so gates can trigger proving directly
type: ENH
priority: P3
status: open
captured_at: '2026-07-01T19:10:34Z'
discovered_date: '2026-07-01'
discovered_by: capture-issue
relates_to:
- ENH-2406
- ENH-2319
- ENH-2242
- ENH-2431
labels:
- learning-tests
- cli
- automation
- rn-implement
confidence_score: 98
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-2430: Add `ll-learning-tests prove` subcommand so gates can trigger proving directly

## Summary

`ll-learning-tests` exposes only registry read/write-adjacent verbs
(`check`, `list`, `mark-stale`, `orphans`) — there is no verb that *proves* a
target. The one existing proving primitive,
`run_learning_gate_for_issue()` (`scripts/little_loops/learning_tests/gate.py`),
is Python-only, requires an `issue_path` (it shells to
`ll-loop run proof-first-task --context issue_file=<path>`), and is wired into
exactly three call sites: `ll-auto`, `ll-sprint`, `ll-parallel`. Any caller
that is target-addressed rather than issue-addressed — most concretely,
`rn-implement`'s pre-dequeue learning gate — has no CLI verb to invoke and can
only dead-end into a "prove it yourself" message.

## Current Behavior

Observed directly: running `ll-loop run rn-implement FEAT-385` against an
issue declaring `learning_tests_required: [requests]` (no existing
`.ll/learning-tests/requests.md` record) hits `check_learning_ready`
(`scripts/little_loops/loops/rn-implement.yaml:464`), which shells out to
`ll-learning-tests check requests --stale-aware`, finds it unproven, and
routes to `mark_learning_blocked` (`rn-implement.yaml:1063`). That state is
terminal — `next: dequeue_next` with no same-run re-enqueue — so the issue
sits blocked until a human manually runs `/ll:explore-api "requests"` and
re-runs the loop.

This is a real regression in automation coverage versus the ENH-2319
baseline, not a bug in what ENH-2406 shipped: pre-ENH-2406, an unrefined/
unproven issue dequeued by `rn-implement` would proceed into
`run_remediation` → `ll-auto --only`, whose inline learning gate *does* call
`run_learning_gate_for_issue()` and auto-attempts `/ll:explore-api` before
failing. ENH-2406's pre-dequeue gate is explicitly check-only by design (its
Scope Boundaries rule out "auto-running `/ll:explore-api` from inside
rn-implement," deferring to that in-`ll-auto` choke point) — but because
`mark_learning_blocked` is terminal, issues that fail the cheap pre-check now
never reach that choke point at all when driven through `rn-implement`. The
auto-proving capability ENH-2319 built is only reachable via `ll-auto`,
`ll-sprint`, or `ll-parallel` directly, not via `rn-implement`.

Separately, `ENH-2242` gave `ready-issue`/`confidence-check` an equivalent
auto-provision behavior, but via `Skill("explore-api", ...)` prose
instructions inside those two skills specifically — not a reusable primitive
any shell-based FSM state or plain CLI caller can invoke.

## Expected Behavior

`ll-learning-tests` gains a `prove <target>` subcommand, target-addressed
(no issue file required, mirroring `check`), that triggers proving and exits
0/1 on the resulting registry status:

```
ll-learning-tests prove requests
```

- On success (target ends `proven`): print the refreshed JSON record, exit 0.
- On failure (target ends `refuted`/still missing): print the record (or an
  error if still absent), exit 1.

Internally this should be a thin orchestration wrapper — not new proving
logic — shelling to `ll-loop run ready-to-implement-gate --context
targets=<target>` (see Codebase Research Findings below), which already
implements the retry-then-`/ll:explore-api` proving loop this issue needs.
There is only one proving mechanism, so no `--via` selector is needed.

With `prove` in place, `rn-implement`'s `mark_learning_blocked`
(`rn-implement.yaml:1063`) — or an opt-in flag on `check_learning_ready`
(`rn-implement.yaml:464`) — can call `ll-learning-tests prove <target>`
directly before giving up, closing the gap without routing back through
`run_remediation` (which would partially defeat ENH-2406's budget-saving
intent by spending a remediation pass).

## Motivation

Without this, `rn-implement`'s pre-dequeue gate is strictly less automated
than the pre-ENH-2406 baseline for any issue that fails the cheap check: it
now requires a human round-trip (`/ll:explore-api` + re-run) that the system
was already capable of doing itself via `ll-auto`'s inline gate. A
target-addressed `prove` verb also benefits any future gate or ad-hoc CLI use
that needs to resolve a learning-test target without an issue file in hand —
today that's only possible by hand-rolling an `issue_file=` context or
invoking the `explore-api` skill interactively.

## Proposed Solution

1. Add `cmd_prove(args)` to `scripts/little_loops/cli/learning_tests.py`,
   modeled on `cmd_check` (`learning_tests.py:13-46`) for output shape and
   exit-code contract.
2. Factor a target-addressed variant of `run_learning_gate_for_issue()` in
   `scripts/little_loops/learning_tests/gate.py` (or extend it with an
   `issue_path: Path | None` signature) that, given a bare target string,
   invokes proving without requiring an issue file — e.g. by writing a
   throwaway `issue_file=`-less `proof-first-task` context, or by invoking
   the `explore-api` skill directly via `resolve_host()`
   (`scripts/little_loops/host_runner.py`) per the project's Host CLI
   Abstraction convention.
3. Register the `prove` subparser in `main_learning_tests()`
   (`learning_tests.py:116`), alongside `check`/`list`/`mark-stale`/`orphans`.
4. Wire `rn-implement.yaml`'s `mark_learning_blocked` (or a new opt-in branch
   off `check_learning_ready`) to call `ll-learning-tests prove <target>`
   before falling back to the terminal blocked state.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- A target-addressed proving primitive **already exists**, independent of
  `run_learning_gate_for_issue()`: the `type: learning` FSM state
  (`_execute_learning_state()` in `scripts/little_loops/fsm/executor.py:745-862`),
  used today by the built-in `scripts/little_loops/loops/ready-to-implement-gate.yaml`
  loop's `prove` state. It takes a bare `targets`/`targets_csv` — no
  `issue_file` — and already implements the exact per-target
  retry-then-`/ll:explore-api` proving loop this issue proposes.
  `ll-loop run ready-to-implement-gate --context targets=<target>` is a
  working, zero-code-change instance of target-addressed proving today.
- This means step 2's "throwaway `issue_file=`-less `proof-first-task`
  context" is unnecessary complexity. Confirmed via `check_issue_file` in
  `proof-first-task.yaml:19-23`: passing `targets_csv` with no `issue_file`
  never reaches the gate at all (`on_no: run_impl` bypasses it entirely) —
  `proof-first-task` genuinely requires a real, existing `issue_file` path
  even when `targets_csv` is set. `cmd_prove` should instead shell directly
  to `ll-loop run ready-to-implement-gate --context targets=<target>`,
  mirroring the existing `_run_learning_gate_preflight()` helper in
  `scripts/little_loops/cli/sprint/run.py` (~lines 180-228), which already
  does exactly this for its multi-target preflight check — no throwaway
  file, no `proof-first-task` involvement needed.
- Exit-code interpretation should follow `_run_learning_gate_preflight()`'s
  pattern (`subprocess.run(...).returncode`) rather than
  `run_learning_gate_for_issue()`'s pattern (reading
  `.loops/.running/<loop>.state.json`), since `ready-to-implement-gate.yaml`'s
  terminal states are plain `done`/`blocked` with no intermediate
  `impl_failed` — the state-file read exists only to disambiguate
  `proof-first-task`'s 3-way terminal set, which doesn't apply here.
- Reuse `check_learning_test(target)`
  (`scripts/little_loops/learning_tests/__init__.py:140-142`) post-proving
  to build the refreshed JSON record for `cmd_prove`'s stdout, matching
  `cmd_check`'s `print_json(record.to_dict())` shape exactly.

## API/Interface

```
ll-learning-tests prove <target>
```

- `target`: bare learning-test target string (e.g. `requests`), addressed the
  same way as `ll-learning-tests check <target>` — no issue file required.
- No mechanism-selector flag: `ready-to-implement-gate` is the only proving
  path (see Codebase Research Findings above), so there is nothing to select
  between.
- Exit codes: `0` if the target's registry record ends `proven`; `1` if it
  ends `refuted` or remains missing/unproven.
- Output: refreshed JSON record on stdout, mirroring `cmd_check`'s
  `print_json(record.to_dict())` shape (`scripts/little_loops/cli/learning_tests.py:13-46`),
  or a stderr error message plus exit 1 when no record can be produced.

### Codebase Research Findings

_Added by `/ll:refine-issue`:_

- `LearnTestRecord.status` (`scripts/little_loops/learning_tests/__init__.py`)
  is `Literal["proven", "refuted", "stale"]` — there is no `"missing"` status
  value. "Missing" in this spec corresponds to `check_learning_test(target)`
  returning `None` (no `.ll/learning-tests/<slug>.md` file found on disk),
  which `cmd_check` already handles by printing
  `Error: no record found for {target!r}` to stderr and returning 1 —
  `cmd_prove` should follow the same not-found handling after a proving
  attempt still leaves no record.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/learning_tests.py` — add `cmd_prove(args)` and
  register the `prove` subparser in `main_learning_tests()`
- `scripts/little_loops/learning_tests/gate.py` — factor a target-addressed
  proving path (extend or wrap `run_learning_gate_for_issue()`)
- `scripts/little_loops/loops/rn-implement.yaml` — wire
  `mark_learning_blocked` (or an opt-in branch off `check_learning_ready`) to
  call `ll-learning-tests prove <target>`

### Dependent Files (Callers/Importers)
- `rn-implement.yaml:464` (`check_learning_ready`) and `:1063`
  (`mark_learning_blocked`) — the two states gaining the new call path
- `ll-auto`, `ll-sprint`, `ll-parallel` call sites of
  `run_learning_gate_for_issue()` — reference point only, not modified (see
  Scope Boundaries)

### Similar Patterns
- `cmd_check` (`learning_tests.py:13-46`) — output shape and exit-code
  contract to mirror

### Tests
- `scripts/tests/test_cli_learning_tests.py` — add `prove` subcommand tests
  (success/failure/missing-target)
- `scripts/tests/test_learning_tests_gate.py` — add coverage for the new
  target-addressed gate helper
- `scripts/tests/test_rn_implement.py` — add coverage for
  `mark_learning_blocked`'s new call-out to `prove`

### Documentation
- `docs/guides/LEARNING_TESTS_GUIDE.md` — document the new `prove` verb
  alongside `check`/`list`/`mark-stale`/`orphans`

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/loops/ready-to-implement-gate.yaml` (`prove` state,
  `type: learning`) — the existing target-addressed proving loop `cmd_prove`
  should wrap directly (see Proposed Solution findings above), instead of
  the `proof-first-task` path the original plan described.
- `scripts/little_loops/fsm/executor.py:745-862`
  (`_execute_learning_state()`) — the underlying per-target
  retry-then-`/ll:explore-api` mechanism `ready-to-implement-gate` runs;
  useful as a second reference implementation alongside
  `run_learning_gate_for_issue()`.
- `scripts/little_loops/cli/sprint/run.py`
  (`_run_learning_gate_preflight()`, ~lines 180-228) — existing precedent
  for a CLI code path that shells to
  `ll-loop run ready-to-implement-gate --context targets=<csv>` and checks
  only `returncode`; the closest existing pattern to model `cmd_prove` on.
- `scripts/little_loops/parallel/worker_pool.py`'s `_run_per_worktree_proof_first_gate()`
  (lines 63-132) independently reimplements
  `run_learning_gate_for_issue()`'s state-file-read logic rather than
  calling the shared function — reference only (out of scope per Scope
  Boundaries), but relevant when choosing which existing pattern to mirror.
- `scripts/tests/test_rn_implement.py::test_state_count_documented_growth`
  (~lines 590-608) enforces `len(states) <= 42` on `rn-implement.yaml`.
  Adding a new state (or branch) to wire `mark_learning_blocked`/
  `check_learning_ready` to `prove` will need that ceiling bumped in the
  same change.
- `docs/guides/LEARNING_TESTS_GUIDE.md` § "Using Learning Tests in Loops"
  (~line 176) already documents the `type: learning` mechanism that
  `ready-to-implement-gate` uses — the new `prove` verb's documentation
  should cross-reference that section rather than duplicate it.

## Success Metrics

- `ll-learning-tests prove <target>` exits 0 and prints a `status: proven`
  JSON record for a target that `check --stale-aware` currently reports as
  unproven/stale.
- `ll-loop run rn-implement <issue>` against an issue with an unproven
  `learning_tests_required` target no longer terminates at
  `mark_learning_blocked` without first attempting `prove` (verified via a
  loop run against a target-addressed test fixture).

## Scope Boundaries

- Out of scope: changing `ll-auto`/`ll-sprint`/`ll-parallel`'s existing
  issue-addressed proving path (`run_learning_gate_for_issue`) — this adds a
  target-addressed sibling, not a replacement.
- Out of scope: making `rn-implement`'s pre-dequeue gate always auto-prove
  by default — whether `mark_learning_blocked` calls `prove` unconditionally
  or behind a flag (e.g. mirroring `skip_learning_gate`'s opt-out shape with
  an opt-in `auto_prove_learning_gate`) is an implementation decision for
  that follow-up wiring, not settled here.
- Out of scope: removing or renaming the "no `write` subcommand" contract in
  `explore-api/SKILL.md` — `prove` orchestrates the existing skill/loop, it
  does not add a second way to hand-write registry records.

## Impact

- **Priority**: P3 — closes a real automation-coverage gap but has a known
  manual workaround (`/ll:explore-api "<target>"` + re-run).
- **Effort**: Small–Medium — one CLI subcommand plus a target-addressed
  proving helper; the underlying subprocess mechanics already exist in
  `run_learning_gate_for_issue()`.
- **Risk**: Low — additive CLI verb; no change to existing `check`/`list`/
  `mark-stale`/`orphans` behavior or to the three existing runner gate paths.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/guides/LEARNING_TESTS_GUIDE.md` | Documents the registry/gate lifecycle this adds a verb to |
| `skills/explore-api/SKILL.md` | Proof lifecycle `prove` would orchestrate; "no write subcommand" principle |

## Labels

`learning-tests`, `cli`, `automation`, `rn-implement`

## Session Log
- `/ll:ready-issue` - 2026-07-01T19:54:13 - `7170efdb-276e-4eec-b79a-2c6959d3b08d.jsonl`
- `/ll:refine-issue` - 2026-07-01T19:27:16 - `825773cc-f3c3-4e72-b818-2f6802981cbb.jsonl`
- `/ll:format-issue` - 2026-07-01T19:16:18 - `9be8c8f3-0586-400c-835a-63136f4a32fd.jsonl`
- `/ll:capture-issue` - 2026-07-01T19:10:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4e438ec0-2ef6-4d50-87d6-3f113b79ec61.jsonl`

## Status

**Open** | Created: 2026-07-01 | Priority: P3
