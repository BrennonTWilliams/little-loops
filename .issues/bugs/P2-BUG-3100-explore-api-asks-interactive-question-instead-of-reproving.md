---
id: BUG-3100
priority: P2
type: BUG
status: open
captured_at: '2026-08-08T04:44:28Z'
discovered_date: '2026-08-08'
discovered_by: capture-issue
discovered_commit: 2371728a
discovered_branch: main
verify_verdict: VALID
labels:
- learning-tests
- skills
- automation
relates_to:
- BUG-3101
- BUG-3102
- ENH-3073
size: Very Large
confidence_score: 96
outcome_confidence: 80
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 22
---

# BUG-3100: `/ll:explore-api` asks an interactive question instead of re-proving an existing record

## Summary

`/ll:explore-api <target>` only performs a real exploration when **no** learning-test record
exists for the target. When a record is already present — in either `proven` or `stale`
status — the skill stops and asks the user which of two paths to take, and returns without
touching the record.

Every automated re-prove path runs `/ll:explore-api` as its remedy step. In automation there
is nobody to answer the question, so **no path can refresh an existing record.**

## Current Behavior

Reproduced twice on `2026-08-08` at `2371728a` against `.ll/learning-tests/ruamelyaml.md`
(`target: ruamel.yaml`, `date: 2026-06-19`, 50 days old).

**Case 1 — record is `proven` and date-stale:**

```
$ ll-loop run ready-to-implement-gate --context "targets=ruamel.yaml"
[1/50] prove (0s) -> ✦ /ll:explore-api ruamel.yaml
       A prior record already exists for `ruamel.yaml` (slug `ruamelyaml`), dated 2026-06-19.
       **Status:** proven (7/7 assertions passed)
       Do you want to reuse this record and stop here, or should I proceed with a fresh
       exploration (which will overwrite the file with new claims)?
       -> done
Loop completed: done (1 iterations, 25.5s)
```

Record unchanged. Loop reported success (see [[BUG-3101]] for why the verdict was `done`).

**Case 2 — record explicitly marked `status: stale`:**

```
$ ll-learning-tests mark-stale "ruamel.yaml"
$ ll-loop run ready-to-implement-gate --context "targets=ruamel.yaml"
       ... it's currently marked **stale** ...
       Since it's stale, do you want me to:
       1. **Re-run** a fresh exploration ... or
       2. **Reuse** the existing claims as-is and just refresh the status back to `proven`?
       -> blocked
Loop completed: blocked (1 iterations, 51.8s)
```

Here the FSM retry path worked correctly (2 invocations, then `on_blocked`) — the skill was
asked twice and asked a question both times. Record still `date: 2026-06-19`.

**Consequence — every re-prove path is a dead end:**

| Path | Result |
|---|---|
| `ll-learning-tests prove "<target>"` | exit 0, record unchanged (silently — see [[ENH-3073]]'s `cmd_prove` hardening) |
| `ll-loop run ready-to-implement-gate` | explore-api asks → false `done` |
| `ll-loop run migrate-sdk-version` | queues 0 records — separate cause, see [[BUG-3102]] |
| `mark-stale` + either loop | explore-api asks → `blocked` |

## Expected Behavior

When invoked non-interactively, `/ll:explore-api <target>` performs a fresh exploration and
rewrites the record, without prompting. A record that already exists is the **normal** input
to a re-prove, not an ambiguity requiring escalation.

Interactive human use may still offer the reuse-vs-fresh choice; automation must get a
deterministic default.

## Motivation

The learning-test registry's entire value is that a `proven` record means "verified against
the installed API recently." That guarantee decays by design (`stale_after_days: 30`), and
the only mechanism for renewing it does not work. All 31 records in this repo are therefore
on a one-way trip to permanently stale — 7 are already past the threshold.

This is also the root blocker for [[ENH-3073]], whose selected fix is to print
`ll-learning-tests prove "<target>"` beside each stale row. That command cannot clear the row
it would be printed next to, so shipping ENH-3073 as specified would advertise a command that
silently does nothing — worse than the dead-end warning it replaces.

## Root Cause

`skills/explore-api/SKILL.md` — the ingest step checks the registry for an existing record and
branches to a user-facing question rather than proceeding. The skill has no notion of running
under automation, and no parameter by which a caller can demand a fresh run.

The FSM's remedy invocation is `f"/ll:explore-api {target}"`
(`scripts/little_loops/fsm/executor.py`, `_execute_learning_state`), which passes the bare
target and no freshness signal.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- The question-asking branch is an imperative LLM instruction, not code: `skills/explore-api/SKILL.md:106-113` — "Exit 0 (record exists): print the existing JSON record and ask whether to short-circuit and reuse it, or proceed with a fresh exploration... Exit 1 (no record): proceed." The skill infers "record exists" purely from `ll-learning-tests check "$TARGET"`'s exit code and never itself branches on `status: proven` vs `status: stale` — both produce the same "exit 0, ask" outcome; the differently-worded questions in the two reproduction cases come from the LLM's own free-form elaboration of this one instruction, not two coded branches.
- The remedy invocation is confirmed literal and flagless: `scripts/little_loops/fsm/executor.py:1193` — `f"/ll:explore-api {target}"`, called from `_execute_learning_state` (`executor.py:1088-1216`), itself dispatched from `_execute_state` at `executor.py:1466-1467`.
- `LL_AUTOMATION` is not reliably present on this call path: `_run_action`'s env injection (`executor.py:1896-1902`) only sets `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` when `state.pruning_profile or self.fsm.pruning_profile` is set and `.enabled` — neither `scripts/little_loops/loops/ready-to-implement-gate.yaml` nor `scripts/little_loops/loops/migrate-sdk-version.yaml` declares a `pruning_profile:` block. Any `LL_AUTOMATION` seen in practice during these loops is ambient inheritance from an enclosing session (see BUG-3082, ENH-3081), not something this call site sets.
- `skills/explore-api/SKILL.md` frontmatter (`:1-27`) and its argument parser (`:44-75`) accept only `target` (required) and repeatable `--assume "<claim>"` — no `--fresh`/`--auto`/`--force`/non-interactive flag exists today.
- `ll-learning-tests prove <target>` confirmed to shell to the gate loop: `cmd_prove` (`scripts/little_loops/cli/learning_tests.py:59-85`) runs `subprocess.run(["ll-loop", "run", "ready-to-implement-gate", "--context", f"targets={args.target}"], capture_output=True, text=True)` and discards the subprocess output, then re-reads the registry via `check_learning_test()` to compute its own exit code.
- Status-check helpers: `check_learning_test()` (`scripts/little_loops/learning_tests/__init__.py:149`) returns `None`/a `LearnTestRecord`; date-based staleness (distinct from the `status: stale` field) is `is_record_stale()` (`scripts/little_loops/learning_tests/gate.py:45`), used by `_execute_learning_state` (`executor.py:1157-1163`) and `cmd_check --stale-aware` (`learning_tests.py:35-56`).

## Proposed Solution

Two candidate shapes:

**A — automation-aware default.** Have the skill detect automation context (`LL_AUTOMATION`
is already set for every descendant of a loop run — see the env-leak behavior) and default to
fresh exploration, keeping the interactive prompt for human invocations. No caller changes.

**B — explicit affordance.** Add a `--fresh` argument to `/ll:explore-api` and have
`_execute_learning_state` pass it: `f"/ll:explore-api {target} --fresh"`. More explicit, but
requires the FSM change and leaves the bare invocation still broken for anything else that
calls it.

**Recommended: A**, with B as a follow-on if an explicit override proves useful. A fixes every
existing caller at once; B fixes only the callers that are updated.

Either way the skill must never terminate a non-interactive run by asking a question — the
general failure mode is worth checking for elsewhere in `skills/`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **Option A's env-var claim needs correction.** `LL_AUTOMATION` is not reliably set on the `/ll:explore-api {target}` remedy's own call path: `_run_action`'s env injection (`scripts/little_loops/fsm/executor.py:1896-1902`) only sets `LL_AUTOMATION` when `state.pruning_profile or self.fsm.pruning_profile` is configured and enabled, and neither `ready-to-implement-gate.yaml` nor `migrate-sdk-version.yaml` declares one. Any `LL_AUTOMATION` observed in practice is ambient inheritance from an enclosing session (see BUG-3082, ENH-3081) — not a guarantee this fix could rely on.
- **The repo's actual convention checks `LL_NON_INTERACTIVE`, not `LL_AUTOMATION`.** The identical "auto-enable in automation contexts" bash snippet appears in 10 other `skills/*/SKILL.md` files (e.g. `skills/spike/SKILL.md:69-76`, `skills/decide-issue/SKILL.md:72-76`) and checks `LL_NON_INTERACTIVE` + `DANGEROUSLY_SKIP_PERMISSIONS`/`--dangerously-skip-permissions`, plus an explicit `--auto` flag override. `LL_AUTOMATION` is documented (`host_runner.py:1547-1562`) as a Python-layer signal read by `hooks/session_start.py`/`cli/history_context.py`, not something any skill markdown file checks. `scripts/little_loops/loops/prompt-across-issues.yaml:24-27` states this explicitly for loop authors: "Skills auto-detect automation context via the `LL_NON_INTERACTIVE` env var that the FSM runner injects."
- **A near-identical failure was already fixed once.** BUG-1416 (`decide-issue --auto` asked an interactive question instead of resolving a provisional decision) added an `AUTO_MODE` guard that skips `AskUserQuestion` and either auto-resolves or records "unresolvable, no interactive questions" (`skills/decide-issue/SKILL.md` Phase 3b). `skills/issue-size-review/SKILL.md:162-174`'s "Auto Mode Behavior" section follows the same shape. Both are closer structural precedent for this fix than inventing a new `LL_AUTOMATION`-keyed check.
- **Recommendation, if Option A is selected**: key the detection on `LL_NON_INTERACTIVE` (+ `DANGEROUSLY_SKIP_PERMISSIONS`/`--dangerously-skip-permissions`), matching all 10 other skills, not `LL_AUTOMATION` as currently written — `LL_AUTOMATION` would make `/ll:explore-api` the only skill keyed off a signal that is neither guaranteed on its own call path nor checked by any other skill.
- **Closest `--force`-style precedent** (relevant if Option B is preferred instead): `skills/spike/SKILL.md:69-104` and `skills/init/SKILL.md` use `--force` as the name for "ignore existing state, redo"; `skills/manage-issue/SKILL.md` uses the compound `--force-implement`. No `--fresh` flag exists anywhere in `skills/` today — Option B's proposed name would be a new convention, not a reuse of an existing one.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Types
N/A — no new data types; the fix operates on existing `LearnTestRecord`/registry status values (`proven`, `stale`) and process env/args, not a new schema.

### Signatures
- `cmd_prove(args: argparse.Namespace) -> int` — shells to `ll-loop run ready-to-implement-gate`, at `scripts/little_loops/cli/learning_tests.py:59-85`; unaffected by the fix directly but is the entry point that ultimately triggers the remedy
- `check_learning_test(target: str) -> LearnTestRecord | None` — existing registry lookup at `scripts/little_loops/learning_tests/__init__.py:149`, wrapped by the skill's `ll-learning-tests check` call
- `is_record_stale(record: LearnTestRecord, stale_after_days: int) -> bool` — existing date-window staleness helper at `scripts/little_loops/learning_tests/gate.py:45`, distinct from the on-disk `status: stale` field
- Skill branch to change: `skills/explore-api/SKILL.md:106-113` (imperative LLM instruction, not a Python signature)
- Remedy call to change: `_execute_learning_state` builds `f"/ll:explore-api {target}"` at `scripts/little_loops/fsm/executor.py:1193`, currently with no flag

### Call Path
`ll-learning-tests prove <target>` (`cmd_prove`, `learning_tests.py:59`) → `subprocess.run(["ll-loop", "run", "ready-to-implement-gate", ...])` → FSM `type: learning` state → `_execute_learning_state` (`executor.py:1088`) → `_run_action(f"/ll:explore-api {target}")` (`executor.py:1193`) → `skills/explore-api/SKILL.md` Phase 1 step 1 (`:106-113`) → asks reuse-vs-fresh question instead of proceeding.

### Decision Rules
- New decision logic this issue introduces: which signal makes `/ll:explore-api` treat an invocation as non-interactive/automated, and what it defaults to when that signal is present.
- Per codebase-pattern-finder research, the established convention identically implemented in 10 other `skills/*/SKILL.md` files (e.g. `skills/spike/SKILL.md:69-76`, `skills/decide-issue/SKILL.md:72-76`, `skills/format-issue/SKILL.md:70`, `skills/wire-issue/SKILL.md:69`, `skills/go-no-go/SKILL.md:64`) is: `AUTO_MODE=true` when ANY of — `"$ARGUMENTS"` contains `--dangerously-skip-permissions`, env `LL_NON_INTERACTIVE` is set (non-empty), env `DANGEROUSLY_SKIP_PERMISSIONS` is set, OR `"$ARGUMENTS"` contains an explicit `--auto` flag.
- This conflicts with Proposed Solution Option A below, which names `LL_AUTOMATION` as the detection signal — see the Codebase Research Findings appended under Proposed Solution for why `LL_NON_INTERACTIVE` is both the convention-matching and call-path-reliable choice.
- Escape hatch: when none of the above signals are present, the skill must retain today's interactive reuse-vs-fresh question for a human operator — the fix adds an automation branch, it does not remove the human path.

## Impact

- 7 of 31 learning-test records are past `stale_after_days` today and cannot be refreshed.
- `ready-to-implement-gate` — the gate `ll-auto` runs before implementing any issue with
  `learning_tests_required` — cannot do its job for any target that already has a record.
- [[ENH-3073]] is blocked: its selected option is unimplementable as specified.
- Hand-editing `date:` is the only remaining way to clear a row, and it is a false assertion
  in the registry — explicitly rejected in ENH-3073.

## Integration Map

- `skills/explore-api/SKILL.md` — the branch that asks instead of exploring
- `scripts/little_loops/fsm/executor.py` — `_execute_learning_state`, the remedy invocation
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — `type: learning` gate loop
- `scripts/little_loops/loops/migrate-sdk-version.yaml` — bulk re-prove loop, same remedy
- `scripts/little_loops/cli/learning_tests.py` — `cmd_prove`, shells to the gate loop

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Additional Files (from research)
- `scripts/little_loops/host_runner.py:1547-1562` — `_apply_automation_env`, canonical `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` setter; a `None` profile explicitly neutralizes to `""`. Documented readers are Python-layer only (`hooks/session_start.py`, `cli/history_context.py`), not skill markdown.
- `scripts/little_loops/learning_tests/__init__.py:149` — `check_learning_test()`, the registry lookup the skill's `ll-learning-tests check` call wraps.
- `scripts/little_loops/learning_tests/gate.py:45` — `is_record_stale()`, date-window staleness check distinct from the on-disk `status: stale` field.
- `scripts/little_loops/loops/prompt-across-issues.yaml:24-27` — loop-author-facing doc comment naming `LL_NON_INTERACTIVE` as the signal skills auto-detect (contradicts Option A's `LL_AUTOMATION` claim — see Proposed Solution findings).

### Conventions in Force
- Skills detect non-interactive/automation context by checking `LL_NON_INTERACTIVE` (env, non-empty) OR `DANGEROUSLY_SKIP_PERMISSIONS` (env) OR `--dangerously-skip-permissions`/`--auto` in the raw argument string, setting a local `AUTO_MODE` flag — identically implemented in 10 `skills/*/SKILL.md` files (e.g. `skills/spike/SKILL.md:69-76`, `skills/decide-issue/SKILL.md:72-76`, `skills/format-issue/SKILL.md:70`, `skills/wire-issue/SKILL.md:69`, `skills/go-no-go/SKILL.md:64`, `skills/audit-issue-conflicts/SKILL.md:53`, `skills/map-dependencies/SKILL.md:56`, `skills/issue-size-review/SKILL.md:51`). `skills/explore-api/SKILL.md` has none of this machinery.
- When `AUTO_MODE` is true, the established pattern is to skip `AskUserQuestion`/interactive branches and substitute a deterministic default or a recorded "unresolvable" outcome, never a blocking question — evidenced by `skills/issue-size-review/SKILL.md:162-174` ("Auto Mode Behavior") and `skills/decide-issue/SKILL.md` Phase 3b (added by BUG-1416 for the same failure shape: `decide-issue --auto` asking instead of resolving).
- No repo-wide doc states the "never end a non-interactive run with a question" rule once, centrally — it is independently re-implemented per skill and re-discovered per bug (BUG-1416, now BUG-3100); the issue's own "worth checking for elsewhere in `skills/`" note is accurate — other skills beyond the 10 found here have not been confirmed compliant.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `commands/ready-issue.md:253` — a **second call site sharing the identical root-cause defect**: for `status: refuted` targets (exit 0 from `ll-learning-tests check`, same as `proven`/`stale`), it says "**Auto-invoke** `Skill('explore-api', '<target>')` to re-explore the assumption" — but the skill's exit-0 branch asks a question instead of re-exploring, so this auto-invoke currently also dead-ends. Not in the issue's original Integration Map. The Option A fix (env-based `LL_NON_INTERACTIVE` detection) covers this call site automatically without editing this file, but it's worth verifying post-fix since it's a second currently-broken caller of the same defect. `commands/ready-issue.md:254` has the same auto-invoke pattern for the "record not found" branch (unaffected by this bug, but same call shape).

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LEARNING_TESTS_GUIDE.md:67` — Ingest-phase description states the interactive question as unconditional current behavior; needs to describe the AUTO_MODE-vs-human split.
- `docs/guides/LEARNING_TESTS_GUIDE.md:270-272` — Troubleshooting entry titled "`/ll:explore-api` asks to overwrite a record I want to keep" documents the question as expected UX and tells scripted callers to work around it by pre-checking `ll-learning-tests check` themselves first — the exact workaround this fix makes unnecessary for automated callers. Needs rewriting to state that automation now gets a deterministic default and only interactive/human runs see the question.
- `docs/guides/LEARNING_TESTS_GUIDE.md:314-318` — "Using Learning Tests in Issue Lifecycle Gates" section describes `/ll:ready-issue`'s refuted/missing auto-invoke of `/ll:explore-api` as already working; that claim is presently inaccurate for `refuted` (see `commands/ready-issue.md:253` above) and becomes accurate only once this fix lands.
- `.kimi-code/skills/explore-api/SKILL.md` and `.gemini/skills/explore-api/SKILL.md` — auto-generated per-host mirrors of the canonical `skills/explore-api/SKILL.md` (regenerated via `ll-init --hosts kimi-code`/`gemini`). Both exist on disk today and currently lack any AUTO_MODE machinery; they will drift out of sync with the canonical skill once this fix lands there unless regenerated as part of the implementation.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_explore_api_skill.py` — does not exist yet; new test file needed. Follow the structural markdown-assertion pattern from `scripts/tests/test_decide_issue_skill.py`'s `TestPhase3bInlineDecisionScan` class (added for BUG-1416's identical fix shape on `skills/decide-issue/SKILL.md`): bound the relevant section of `SKILL_FILE.read_text()` by heading, assert `AUTO_MODE`, `LL_NON_INTERACTIVE`, `DANGEROUSLY_SKIP_PERMISSIONS`, and `--auto` are documented, and assert the AUTO_MODE branch does not route through `AskUserQuestion`.
- `scripts/tests/test_learning_state.py` — existing coverage of `_execute_learning_state`; confirmed **not** to need changes. All assertions on the remedy string (e.g. `TestLearningStateMissingRecord.test_invokes_explore_api_then_advances:159`, `TestLearningStateStaleRecord`) use substring checks (`"/ll:explore-api" in call`), not full-string equality, and Option A does not change the Python-built remedy string at `executor.py:1193` — only the skill markdown gains AUTO_MODE detection. No update needed; listed for confirmation.
- `scripts/tests/test_builtin_loops.py:5747,14565` — asserts `"/ll:explore-api" in action` against literal strings embedded in `autodev.yaml`/`rn-implement.yaml`. Unrelated code path (different action strings, not the executor-built remedy); confirmed unaffected.

## Acceptance Criteria

- [ ] `/ll:explore-api <target>` invoked non-interactively against an existing `proven` record
      performs a fresh exploration and rewrites `date`/`assertions`/`status`.
- [ ] Same for an existing `status: stale` record.
- [ ] `ll-loop run ready-to-implement-gate --context "targets=<t>"` re-dates a date-stale
      record and terminates `done` — with the date actually advanced.
- [ ] No non-interactive invocation of the skill terminates by asking the user a question.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Issues

- BUG-3101 — the re-check bug that turns this no-op into a false `proven` verdict; found in
  the same session and must be fixed alongside, since it masks this one
- BUG-3102 — `migrate-sdk-version` queues only `status: stale` records
- ENH-3073 — blocked by this; its Option A advertises `ll-learning-tests prove`, which cannot
  clear a row until this is fixed

## Status

Open. Mechanism confirmed by direct reproduction on `2371728a`; both cases captured above
verbatim from loop output. Fix shape not yet decided (A vs B).


## Session Log
- `/ll:confidence-check` - 2026-08-08T05:14:11 - `35849b94-1675-4028-a86c-d7bfb6f2fe94.jsonl`
- `/ll:verify-issues` - 2026-08-08T05:10:09 - `e18a2b37-f311-483e-b2d7-2b0d5c897203.jsonl`
- `/ll:refine-issue` - 2026-08-08T05:08:34 - `d195b08f-3364-4fc0-add5-7b412ca3d18c.jsonl`
- `/ll:wire-issue` - 2026-08-08T05:04:35 - `64ca74d9-79ee-4836-b3f6-ca70ef719b8a.jsonl`
- `/ll:refine-issue` - 2026-08-08T04:56:08 - `24514c46-1862-4026-911e-ec9cd0fb70c7.jsonl`
- `/ll:capture-issue` - 2026-08-08T04:47:03 - `0c442e3b-c3d8-4743-b597-7b3551a75ba6.jsonl`
