---
id: BUG-3100
priority: P2
type: BUG
status: done
completed_at: '2026-08-08T07:56:35Z'
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

## Steps to Reproduce

1. Ensure a learning-test record already exists for some target, e.g. `ruamel.yaml`
   (`.ll/learning-tests/ruamelyaml.md`), in either `proven` or `status: stale` state.
2. Run `ll-loop run ready-to-implement-gate --context "targets=ruamel.yaml"` (or any other
   caller that invokes `/ll:explore-api <target>` non-interactively — see Consequence table
   above for the full list).
3. Observe: instead of performing a fresh exploration and rewriting the record, the skill
   prints the existing record and asks the user to choose between reusing it or running a
   fresh exploration — a question nobody in an automated run can answer, so the run reports
   `done` (Case 1, record unchanged) or `blocked` (Case 2, record still stale) without ever
   refreshing the record.

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

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **Scope correction (supersedes the executor/host_runner uncertainty above):** since `LL_NON_INTERACTIVE=1` is confirmed already present in the child skill's environment for every FSM-driven `/ll:explore-api {target}` invocation (see Program Design → Codebase Research Findings), Option A is implementable as a **skill-markdown-only** change — add the standard `AUTO_MODE` detection block (checking `LL_NON_INTERACTIVE`/`DANGEROUSLY_SKIP_PERMISSIONS`/`--dangerously-skip-permissions`/`--auto`, matching the existing convention) to `skills/explore-api/SKILL.md`, gate the exit-0 branch (`:112`) on it, and port the same change to `.kimi-code/skills/explore-api/SKILL.md` and `.gemini/skills/explore-api/SKILL.md` (both currently unmodified mirrors, off-by-one at line 111 due to header differences). No `_execute_learning_state`/`_run_action`/`host_runner.py` change is required.
- **Two additional currently-broken call sites found, both headless and equally exposed:** `scripts/little_loops/loops/assumption-firewall.yaml:135` and `scripts/little_loops/loops/migrate-sdk-version.yaml:97` both invoke `subprocess.run(["ll-action", "invoke", "explore-api", "--args", ...])`, which resolves through `cli/action.py:cmd_invoke` (~line 455) → `resolve_host().build_streaming(...)` — the same `ClaudeCodeRunner.build_streaming` path confirmed above to set `LL_NON_INTERACTIVE=1`. These were not previously listed in Integration Map (only `commands/ready-issue.md:253-254` was, from the `/ll:wire-issue` pass); the Option A fix covers them automatically once the skill checks the env var, same as the FSM `type: learning` path — no separate per-caller change needed. Listed as additional evidence that a skill-level fix is the right altitude, not a fix wired into any one caller.
- **AUTO_MODE-citing skill count correction:** re-verified against current code — 9 files use the local variable literally named `AUTO_MODE`: `skills/decide-issue/SKILL.md:67-76`, `skills/wire-issue/SKILL.md:65-72`, `skills/go-no-go/SKILL.md:61-68`, `skills/audit-issue-conflicts/SKILL.md:48-56`, `skills/format-issue/SKILL.md:70`, `skills/spike/SKILL.md:69-76`, `skills/map-dependencies/SKILL.md:56`, `skills/issue-size-review/SKILL.md:46-54`, `skills/confidence-check/SKILL.md:46-57`. Two more (`skills/debug-loop-run/SKILL.md:325`, `skills/audit-loop-run/SKILL.md:388`) implement the identical 4-trigger detection condition under a differently-named local concept ("Non-interactive mode"), not a variable literally called `AUTO_MODE`. So the citable set is 9 (exact `AUTO_MODE` name) to 11 (including the two "Non-interactive mode" variants) — not "10" as previously stated. Not load-bearing for the fix itself, only for precision of the convention citation.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **Correction (post `c5e7303e`, re-verified against current code):** `_execute_learning_state` now spans `scripts/little_loops/fsm/executor.py:1088-1223` (was `1088-1216`); the `_fresh_record` closure (BUG-3101) lives at `:1152-1167`, called at the pre-loop read (`:1170`) and the in-loop re-check (`:1205`). The remedy invocation is now at `:1199-1203` (was `:1193`), still `self._run_action(f"/ll:explore-api {target}", _dc_replace(state, action_type="slash_command"), ctx)` — unconditional and flagless, unchanged in shape. `_execute_state`'s dispatch to `_execute_learning_state` is now at `:1474` (was `:1466-1467`). `_run_action`'s pruning-profile-gated env injection is now at `:1890-1926` (was `:1896-1902`).
- **Major correction — `LL_NON_INTERACTIVE` IS reliably present on this call path, contrary to the "Conventions in Force" note below and the Proposed Solution findings' claim that it "is not set anywhere on this call path."** Traced the full call chain for the `/ll:explore-api {target}` remedy: `_run_action` → `DefaultActionRunner.run()` (`scripts/little_loops/fsm/runners.py:98`), which for `is_slash_command=True` (pinned via `action_type="slash_command"` at the remedy call site) invokes `run_claude_command()` (`scripts/little_loops/subprocess_utils.py:320`) → `resolve_host().build_streaming(...)` (`subprocess_utils.py:402`). `ClaudeCodeRunner.build_streaming` (`scripts/little_loops/host_runner.py:299-370`) unconditionally sets `env["LL_NON_INTERACTIVE"] = "1"` at line 349 — independent of `automation_profile`/pruning-profile gating (that only controls the separate `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` injection via `_apply_automation_env`, line 353). Confirmed the same unconditional `LL_NON_INTERACTIVE: "1"` injection exists in every other *implemented* host's `build_streaming`: `CodexRunner` (`:641`), `GeminiRunner` (`:1031`), `OmpRunner` (`:1216`), `KimiRunner` (`:1409`). `OpenCodeRunner`/`PiRunner` are unimplemented stubs (`raise HostNotConfigured`), not real gaps. **Implication: Option A requires no executor.py/host_runner.py change — the environment signal the 11-12-skill AUTO_MODE convention checks is already present for every FSM-driven `/ll:explore-api` invocation. The fix is confined to `skills/explore-api/SKILL.md` (plus its two host mirrors).**

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

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **New caller sites (not previously listed):** `scripts/little_loops/loops/assumption-firewall.yaml:110-142` (`record_untestable` shell action, `ll-action invoke explore-api ...`) and `scripts/little_loops/loops/migrate-sdk-version.yaml:80-100` (bulk re-prove action, same `ll-action invoke` shape) — both resolve through `scripts/little_loops/cli/action.py:399-462` (`cmd_invoke`) → `resolve_host().build_streaming(...)`, headless with no attached interactive terminal, equally exposed to the exit-0 question branch as the already-documented `commands/ready-issue.md:253-254` site.
- **Anchor precision correction:** the interactive-question branch is a single line, `skills/explore-api/SKILL.md:112` (issue's original `:106-113` citation was the surrounding numbered-list range, not the branch itself — still a reasonable pointer, just less precise). The host mirrors `.kimi-code/skills/explore-api/SKILL.md` and `.gemini/skills/explore-api/SKILL.md` carry the identical branch at line 111 (off-by-one from canonical due to frontmatter/header differences) — both need the same fix applied, or a mirror-regeneration step (`ll-init --hosts kimi-code`/`gemini`) after the canonical skill changes.
- **Citation correction (Tests subsection, added by `/ll:wire-issue`):** the existing "Tests" bullet names the model test class as `TestPhase3bInlineDecisionScan` in `scripts/tests/test_decide_issue_skill.py` — the actual class name in that file is `TestPhase3bInlineProvisionalScan` (added by commit `64d99161`, the BUG-1416 fix this issue cites as precedent). The structural pattern (bound-by-heading assertion on `SKILL_FILE.read_text()`, assert `AUTO_MODE`/`LL_NON_INTERACTIVE` present, assert `AskUserQuestion` absent from the auto-mode branch) is otherwise accurately described — only the class name is wrong.

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
- `scripts/little_loops/loops/assumption-firewall.yaml:135` — a **third headless call site**, `ll-action invoke explore-api ...` (the `record_untestable`-adjacent shell action), resolving through `cli/action.py:cmd_invoke` → `resolve_host().build_streaming(...)` — the same `LL_NON_INTERACTIVE=1`-injecting path as the FSM `type: learning` remedy. This was **named explicitly** in a Program Design → Integration Map codebase-research finding above ("New caller sites (not previously listed)") but never actually landed in this Dependent Files subsection during the prior `/ll:wire-issue` pass — confirmed still present via direct grep in this pass. Covered automatically by the Option A skill-level fix; listed here so post-fix verification checks it alongside `commands/ready-issue.md` and `migrate-sdk-version.yaml`. [Agent 1 finding, re-confirmed via grep]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LEARNING_TESTS_GUIDE.md:67` — Ingest-phase description states the interactive question as unconditional current behavior; needs to describe the AUTO_MODE-vs-human split.
- `docs/guides/LEARNING_TESTS_GUIDE.md:270-272` — Troubleshooting entry titled "`/ll:explore-api` asks to overwrite a record I want to keep" documents the question as expected UX and tells scripted callers to work around it by pre-checking `ll-learning-tests check` themselves first — the exact workaround this fix makes unnecessary for automated callers. Needs rewriting to state that automation now gets a deterministic default and only interactive/human runs see the question.
- `docs/guides/LEARNING_TESTS_GUIDE.md:314-318` — "Using Learning Tests in Issue Lifecycle Gates" section describes `/ll:ready-issue`'s refuted/missing auto-invoke of `/ll:explore-api` as already working; that claim is presently inaccurate for `refuted` (see `commands/ready-issue.md:253` above) and becomes accurate only once this fix lands.
- `.kimi-code/skills/explore-api/SKILL.md` and `.gemini/skills/explore-api/SKILL.md` — auto-generated per-host mirrors of the canonical `skills/explore-api/SKILL.md` (regenerated via `ll-init --hosts kimi-code`/`gemini`). Both exist on disk today and currently lack any AUTO_MODE machinery; they will drift out of sync with the canonical skill once this fix lands there unless regenerated as part of the implementation.
- `docs/reference/COMMANDS.md:16` — the `## Flag Conventions` table's `--auto` row lists every other AUTO_MODE-gated skill's command name (`commit`, `refine-issue`, `format-issue`, `confidence-check`, `spike`, `verify-issues`, `map-dependencies`, `issue-size-review`, `audit-issue-conflicts`, `link-epics`, `audit-loop-run`, `debug-loop-run`) but not `explore-api` — needs `explore-api` appended once the fix lands, for consistency with how every other AUTO_MODE-gated skill is catalogued here. [Agent 2 finding, confirmed]
- `docs/reference/COMMANDS.md:115-134` — the `### /ll:explore-api` section's `**Arguments:**` list only documents `target` and `--assume`, unlike e.g. `### /ll:spike` (line 356: `**Flags:** --auto (non-interactive), --check ...`). Needs an analogous `**Flags:**` line describing the new AUTO_MODE/`--auto` behavior, or it will read as stale once the skill gains automation detection. [Agent 2 finding, confirmed]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_explore_api_skill.py` — does not exist yet; new test file needed. Follow the structural markdown-assertion pattern from `scripts/tests/test_decide_issue_skill.py`'s `TestPhase3bInlineDecisionScan` class (added for BUG-1416's identical fix shape on `skills/decide-issue/SKILL.md`): bound the relevant section of `SKILL_FILE.read_text()` by heading, assert `AUTO_MODE`, `LL_NON_INTERACTIVE`, `DANGEROUSLY_SKIP_PERMISSIONS`, and `--auto` are documented, and assert the AUTO_MODE branch does not route through `AskUserQuestion`.
- `scripts/tests/test_learning_state.py` — existing coverage of `_execute_learning_state`; confirmed **not** to need changes. All assertions on the remedy string (e.g. `TestLearningStateMissingRecord.test_invokes_explore_api_then_advances:159`, `TestLearningStateStaleRecord`) use substring checks (`"/ll:explore-api" in call`), not full-string equality, and Option A does not change the Python-built remedy string at `executor.py:1193` — only the skill markdown gains AUTO_MODE detection. No update needed; listed for confirmation.
- `scripts/tests/test_builtin_loops.py:5747,14565` — asserts `"/ll:explore-api" in action` against literal strings embedded in `autodev.yaml`/`rn-implement.yaml`. Unrelated code path (different action strings, not the executor-built remedy); confirmed unaffected.
- `scripts/tests/test_wiring_skills_and_commands.py:360-365` — `SKILL_MIRRORS_MUST_MATCH_SOURCE` (ENH-2996/FEAT-3077) is the only automated check that a host mirror body matches its canonical `skills/*/SKILL.md` source; it currently enumerates only `wire-issue` and `manage-issue`. `explore-api` is **not enrolled**, so nothing test-enforces that the `.kimi-code/skills/explore-api/SKILL.md` and `.gemini/skills/explore-api/SKILL.md` mirror-porting step (required by this fix, per the Documentation subsection above) was actually done — a missed or partial port would drift silently, same failure shape the comment at `test_wiring_skills_and_commands.py:355-359` calls out for other skills. Add both `("skills/explore-api/SKILL.md", ".gemini/skills/explore-api/SKILL.md")` and `("skills/explore-api/SKILL.md", ".kimi-code/skills/explore-api/SKILL.md")` tuples as part of this fix. [Agent 2 finding, confirmed]
- `scripts/tests/test_wiring_skills_and_commands.py:130-135` — existing `DOC_STRINGS_PRESENT`-style assertions that `description:`, `argument-hint:`, `ll-learning-tests`, and `--assume` remain present somewhere in `skills/explore-api/SKILL.md`. Not touched by the fix, but the AUTO_MODE edit must preserve these substrings verbatim or this test breaks. [Agent 2 finding, confirmed — preservation constraint, not a new test]

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

Done. Mechanism confirmed by direct reproduction on `2371728a`; both cases captured above
verbatim from loop output. Fixed via Option A: `skills/explore-api/SKILL.md` (and its
`.gemini`/`.kimi-code` mirrors) now detects `AUTO_MODE` from `--auto`,
`--dangerously-skip-permissions`, `LL_NON_INTERACTIVE`, or `DANGEROUSLY_SKIP_PERMISSIONS`
and skips the reuse-vs-fresh question under automation, proceeding straight to a fresh
exploration that overwrites the record.


## Session Log
- `/ll:ready-issue` - 2026-08-08T07:39:21 - `967925b2-04f1-477a-90a2-a7ee60a8e1aa.jsonl`
- `/ll:verify-issues` - 2026-08-08T07:35:27 - `4026537a-e0c7-40ff-8d4c-d586bb604cf9.jsonl`
- `/ll:refine-issue` - 2026-08-08T07:33:53 - `ff9a5234-366f-416f-a363-31fe5d67eb34.jsonl`
- `/ll:verify-issues` - 2026-08-08T07:32:26 - `690ff33c-19f7-402c-9526-c2b9691a0ed2.jsonl`
- `/ll:wire-issue` - 2026-08-08T07:31:21 - `78a0de05-70ab-46eb-9193-3d0ae0ba40df.jsonl`
- `/ll:refine-issue` - 2026-08-08T07:23:40 - `ef7c968d-df03-42d2-8a91-d401130a4e7b.jsonl`
- `/ll:confidence-check` - 2026-08-08T05:14:11 - `35849b94-1675-4028-a86c-d7bfb6f2fe94.jsonl`
- `/ll:verify-issues` - 2026-08-08T05:10:09 - `e18a2b37-f311-483e-b2d7-2b0d5c897203.jsonl`
- `/ll:refine-issue` - 2026-08-08T05:08:34 - `d195b08f-3364-4fc0-add5-7b412ca3d18c.jsonl`
- `/ll:wire-issue` - 2026-08-08T05:04:35 - `64ca74d9-79ee-4836-b3f6-ca70ef719b8a.jsonl`
- `/ll:refine-issue` - 2026-08-08T04:56:08 - `24514c46-1862-4026-911e-ec9cd0fb70c7.jsonl`
- `/ll:capture-issue` - 2026-08-08T04:47:03 - `0c442e3b-c3d8-4743-b597-7b3551a75ba6.jsonl`
