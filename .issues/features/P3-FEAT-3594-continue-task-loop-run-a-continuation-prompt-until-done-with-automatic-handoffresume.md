---
id: FEAT-3594
type: FEAT
title: 'continue-task loop: run a continuation prompt until done with automatic handoff/resume'
priority: P3
status: open
decision_needed: true
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T04:27:08Z'
---

# FEAT-3594: continue-task loop: run a continuation prompt until done with automatic handoff/resume

## Summary

Add a built-in, general-purpose FSM loop `continue-task` that takes a continuation prompt and keeps working it until done, handling context exhaustion with automatic `/ll:handoff` → spawned `/ll:resume` sessions. Input is optional: with no input, the loop starts from the newest `.ll/ll-continue-prompt.md`.

## Current Behavior

Continuing a handed-off session is manual: open a new session, run `/ll:resume`, repeat at every handoff. `general-task` automates handoff/resume but only inside its own plan/DoD pipeline and requires an explicit task input.

## Expected Behavior

`ll-loop run continue-task [prompt]` works a continuation prompt (explicit, or the newest non-stale `.ll/ll-continue-prompt.md`) across as many automatic handoffs as needed, stopping when an independent done-check against the pinned starting goal passes, or at the iteration cap with a partial summary.

## Motivation

No built-in loop defaults its input to the handoff prompt. `general-task` is the only loop that reads `.ll/ll-continue-prompt.md`, and only to re-enter a pass mid-step (`do_work`). It is the wrong shape for this job: it always runs `define_done` and `plan`, then the DoD verification / final-tests / step-abandonment machinery. A continuation prompt already carries the plan and current state, so re-planning discards or duplicates it.

## Proposed Solution

A thin loop (~5 states), decoupled from the Issue system:

1. `load_prompt` (shell) — write `${context.input}` via quoted heredoc (BUG-2622 pattern from `prompt-across-issues.yaml` `init`). If empty, fall back to `.ll/ll-continue-prompt.md`, rejecting it when older than `continuation.prompt_expiry_hours` (default 24, same key `/ll:resume` reads). Print the source, mtime and first line for provenance. Fail clearly if neither is available. Snapshot the starting prompt to `${context.run_dir}/goal.md` — this pins the goal so repeated handoff summaries cannot drift it.
2. `work` (prompt) — mark the pass start; run `/ll:resume` if the handoff file is newer than the pass marker (general-task's `pass-started.txt` freshness pattern), else work from `goal.md`. Keep `${context.run_dir}/progress.md` current (done / remaining / evidence). On the context-monitor threshold, update progress and run `/ll:handoff`.
3. `run_tests` (shell, non-LLM signal) — run the resolved test command (explicit `context.test_cmd`, else `ll-config get project.test_cmd`); record exit code. Skip cleanly when none is configured.
4. `check_done` (prompt + `llm_structured`) — judge `progress.md` evidence and the test exit code against the pinned `goal.md`, re-verifying claims by reading files / running commands. The worker's own "done" claim is never sufficient. A test *regression* (passed at baseline, fails now) forces NO mechanically in `run_tests`, before the LLM check; a suite already failing at baseline is advisory, so a pre-existing failure cannot pin the loop open.
5. `stall_check` (`diff_stall_gate`, max_stall 3) after `work` — working tree unchanged across 3 passes routes to a partial summary.
6. Terminals `done` / `partial` (summary via `on_max_steps` or stall) / `failed`.

Top level: `on_handoff: spawn`, `max_steps` + `on_max_steps` cap, input NOT in `required_inputs` (otherwise `ll-loop run` rejects the empty-input fallback case before `load_prompt` runs).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

As-built deltas vs this section (implementation landed in e4556ec95; constraints below describe what must stay true):
- Step 4's `check_done (prompt + llm_structured)` shipped as prompt + mechanical verdict file (one-word `verdict.txt` gate in `read_verdict`) — same judge-independence outcome ("You did NOT do this work; judge it skeptically", `continue-task.yaml:216-217`; worker told "Do NOT declare the task finished", :153-154), different mechanism.
- Step 2's `/ll:resume`-on-fresher-handoff re-entry is present: `work` runs `/ll:resume` iff `.ll/ll-continue-prompt.md` is `-nt` `pass-started.txt`; the marker is deliberately NOT refreshed mid-pass so an intra-pass handoff is still detected (`continue-task.yaml:108-111`), mirroring `general-task.yaml:364-368, 516-518`.

**Option A**: Correct the API/Interface example — drop `--context max_passes=20`. Nothing in `continue-task.yaml` reads a `max_passes` context key; the run accepts it as a silent no-op. The real pass budget is `max_steps: 150` plus the `diff_stall_gate` (max_stall 3).

**Option B**: Implement the `max_passes` knob — declare it in the loop's `context:` block and cap passes in `start_pass` against `pass-count.txt` — so the documented example works as written.

**Recommended**: Option A — `max_steps` and the stall gate already bound runaway passes; a second overlapping budget adds config surface with no distinct failure mode. Option B remains cheap if a per-pass budget is ever wanted.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/continue-task.yaml` (exists — implemented in e4556ec95 after this issue was captured; verify against Acceptance Criteria rather than re-implementing)

### Dependent Files (Callers/Importers)
- N/A — standalone built-in loop, discovered by the loop loader

### Similar Patterns
- `scripts/little_loops/loops/general-task.yaml` — handoff wiring, `check_baseline_tests` test-cmd resolution
- `scripts/little_loops/loops/prompt-across-issues.yaml` — quoted-heredoc input capture

### Tests
- `scripts/tests/test_builtin_loops.py` — expected built-in loop list

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `README.md` loop count

### Configuration
- Reads `continuation.prompt_expiry_hours`, `project.test_cmd` (no new keys)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- As-built verification (commit e4556ec95): all 5 Acceptance Criteria satisfied by `scripts/little_loops/loops/continue-task.yaml`. Actual shape is 8 non-terminal states (`load_prompt`, `start_pass`, `work`, `stall_check`, `run_tests`, `check_done`, `read_verdict`, `summarize_partial`) plus terminals `done` / `partial` (deliberately non-failure) / `failed` — not the ~5 states sketched in Proposed Solution.
- Input handling as built: no `required_inputs` key (`FSMLoop.required_inputs` defaults to `[]`, `scripts/little_loops/fsm/schema.py:1428`); `cmd_run` rejects only listed keys (`scripts/little_loops/cli/loop/run.py:350-357`), so empty input reaches `load_prompt` — declared intentional by in-file comment at `continue-task.yaml:37-38`.
- Registration verified complete: expected-set entry `scripts/tests/test_builtin_loops.py:300` (exact set equality asserted by `test_expected_loops_exist` at :204), `scripts/little_loops/loops/README.md:93`, `docs/guides/LOOPS_GUIDE.md:391`, README loop count 108 = 97 top-level + 11 oracles (enforced by `scripts/tests/test_wiring_guides_and_meta.py::test_doc_counts_all_match` -> `scripts/little_loops/doc_counts.py:206-208`).
- GAP — `docs/guides/LOOPS_REFERENCE.md` has no continue-task entry (general-task/stepwise-task rows at :78-79) while root `README.md:118` claims every built-in loop is documented there; no test enforces that coverage, so the miss is silent.
- Handoff chain as built: `work` session runs `/ll:handoff` -> `CONTEXT_HANDOFF:` marker (`commands/handoff.md:194`) -> `SignalDetector` (`scripts/little_loops/fsm/signal_detector.py:74`) -> `_handle_handoff` (`scripts/little_loops/fsm/executor.py:4466`) -> `HandoffHandler.handle` (`scripts/little_loops/fsm/handoff_handler.py:68`) -> `_spawn_continuation` (:96) via `resolve_host().build_detached(...)` with DEVNULL stdio and `start_new_session=True` (:123-131). Run persists `terminated_by="handoff"` -> status `awaiting_continuation` (`scripts/little_loops/fsm/persistence.py:174-175`, in `RESUMABLE_STATUSES` at :55); `ll-loop resume` restores the `work` state directly (`persistence.py:1388`), where the `pass-started.txt -nt` check fires `/ll:resume`.
- Conventions in force for any edit to this loop: (1) built-in registration is exact-set test-enforced (`test_builtin_loops.py:204`) plus auto-applying file gates (`test_all_validate_as_valid_fsm`, the ENH-2825 failure-edge rule, bare-PASS / bare-bash-`${}`/ grep `-c` bans); (2) `scripts/tests/test_builtin_loop_hardcode_gate.py` (ENH-3281) bans this-repo paths in `states[*].action` bodies — loops ship to consuming projects; (3) `scripts/tests/test_builtin_loop_interpolation.py` fails any bare shell `${VAR}` in actions — escape as `$${VAR}`; (4) MR-3 per-run artifact isolation applies to ALL loops, not just meta-loops (`scripts/little_loops/fsm/validation/meta_rules.py:201-231`) — write only under `${context.run_dir}`; (5) MR-5 artifact versioning binds `category: harness` loops regardless of meta status (`meta_rules.py:278-293`) — hence `artifact_versioning_ok: true` at `continue-task.yaml:36`, same declaration as `general-task.yaml:10`; (6) shell-injected context values interpolate with the `:shell` suffix (`${context.test_cmd:shell}`, MR-11; `scripts/little_loops/fsm/interpolation.py:280-316`).

## Program Design

### Types

- `input: str` — continuation prompt; empty string selects the newest `.ll/ll-continue-prompt.md` fallback
- `test_cmd: str` — resolved from `context.test_cmd`, else `ll-config get project.test_cmd`; empty skips `run_tests`
- `max_steps: int` (150) with `on_max_steps: summarize_partial` — iteration cap diverts to a partial summary
- `on_handoff: str` (`spawn`) — detached continuation session via `HandoffHandler`

### Signatures

- `load_prompt(input: str, handoff: Path) -> goal_path: Path`
- `work(goal: Path, progress: Path) -> None`
- `run_tests(test_cmd: str) -> exit_code: int`
- `check_done(goal: str, progress: str, test_exit: int) -> verdict: str`

### Call Path

`ll-loop run` -> `load_prompt` -> `work` -> (`run_tests` -> `check_done`) -> `done` | `summarize_partial`; on context threshold `work` -> `HandoffHandler` spawns a detached `ll-loop resume continue-task`; `stall_check` (via the `diff_stall_gate` fragment from `loops/lib/common.yaml`) -> `summarize_partial`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- As-built verdict mechanism replaces the sketched `llm_structured` evaluator: `check_done` (prompt state) writes exactly one word — `DONE` or `NOT_DONE` — to `${context.run_dir}/verdict.txt`; `read_verdict` (shell) gates on `grep -qx 'DONE' verdict.txt` so free-text output can never be mistaken for a verdict. There is no `evaluate:` block on `check_done`.
- As-built test gating: `run_tests` exits 1 only on a regression (current exit != 0 AND baseline = 0), routing `on_no -> start_pass` and bypassing the LLM check for that pass (it overwrites `done-check.md` with the regression report itself); exit 127 at baseline keeps `baseline-exit.txt` at `SKIP` so command-not-found is never classified REGRESSED; pre-existing failures are recorded `FAILING (pre-existing)` and exit 0 — advisory by design.
- As-built staleness strictness: `load_prompt` REJECTS a stale handoff file (exit 1, naming `continuation.prompt_expiry_hours` and the explicit-prompt remedy), whereas `/ll:resume` only warns on the same key (`commands/resume.md:48-50`) — same key, different strictness.
- The `max_passes` context key shown in the API/Interface example is read by nothing in `continue-task.yaml`; the pass budget is `max_steps: 150` (~25 passes at ~6 steps/pass) plus `diff_stall_gate` max_stall 3 (state-level override of the fragment default 2 via deep-merge, `scripts/little_loops/fsm/fragments.py:142`).

## Implementation Steps

1. Add `scripts/little_loops/loops/continue-task.yaml` (states above).
2. Register it: expected-loop list in `scripts/tests/test_builtin_loops.py`, the table in `scripts/little_loops/loops/README.md`, the General-purpose row in `docs/guides/LOOPS_GUIDE.md`, and the README loop count if it changes.
3. Tests: `ll-loop validate continue-task` passes; `load_prompt` fallback / staleness / missing-both cases (shell-level, tmp project dir); input absent from `required_inputs`.
4. Document that `on_handoff: spawn` is detached (`HandoffHandler._spawn_continuation` in `little_loops.fsm.handoff_handler` discards stdout), so the foreground view ends at the first handoff — follow along with `ll-loop status` / run logs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Steps 1-2 are DONE as of e4556ec95 (file exists; every registration point verified — see Integration Map findings). The LOOPS_REFERENCE.md row found there extends step 2's doc surface.
- Step 3 is PARTIALLY done: `ll-loop validate` coverage exists via `test_all_validate_as_valid_fsm` (`scripts/tests/test_builtin_loops.py:77-80`) and expected-set membership at :300, but the dedicated `load_prompt` shell-level tests and the `required_inputs`-absence test do not exist anywhere in `scripts/tests/` (searched; the only hit is the expected-set entry).
- Precedent for those tests: extract the state's shell action from the YAML, substitute `${context.*}` refs from declared defaults + overrides, run under `bash -c` with cwd = a tmp "project" dir, and assert on stdout markers + returncode + run_dir file contents — the `_load_state_script` / `_setup_run_dir` / `_bash` harness in `scripts/tests/test_general_task_loop.py:509-531, 1058-1059` (e.g. `TestBatchedPasses` at :2740-2784).
- Outcomes the shell-level tests should hold true: explicit input -> `goal.md` written from `input.txt` and `PROMPT_SOURCE: input`; fresh handoff file + empty input -> `goal.md` copied with `PROMPT_MTIME` / `PROMPT_FIRST_LINE` provenance; stale handoff -> exit 1 naming `continuation.prompt_expiry_hours` and the explicit-prompt remedy; neither source -> exit 1 with usage; whitespace-only input falls through to the handoff branch; non-numeric/missing expiry config defaults to 24.
- Step 4 verified accurate as written: `_spawn_continuation` discards stdout/stderr/stdin (DEVNULL) and detaches via `start_new_session=True` (`scripts/little_loops/fsm/handoff_handler.py:123-131`).

## Impact

- **Priority**: P3 - Workflow convenience; manual `/ll:resume` works today
- **Effort**: Small - one thin YAML reusing existing handoff machinery, plus registration
- **Risk**: Low - additive new loop; no changes to executor or existing loops
- **Breaking Change**: No

## Use Case

A developer's interactive session hits the context threshold mid-task and runs `/ll:handoff`. Instead of manually opening a new session and running `/ll:resume` (repeatedly, for a long task), they run `ll-loop run continue-task` with no argument. The loop picks up the handoff prompt, pins its goal, and keeps working across as many handoffs as needed, stopping only when an independent done-check (plus the test command, when one exists) confirms the goal is met, or when the iteration cap is hit.

## API/Interface

```
ll-loop run continue-task                 # resume newest .ll/ll-continue-prompt.md
ll-loop run continue-task "<prompt>"      # explicit continuation prompt / task
ll-loop run continue-task --context test_cmd="pytest -x" --context max_passes=20
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- The `--context max_passes=20` example does not correspond to any knob the loop reads — see the Option A/B decision under Proposed Solution -> Codebase Research Findings.

## Acceptance Criteria

- `ll-loop run continue-task` with no input and a fresh handoff file starts from that file and writes `goal.md`.
- With no input and no (or stale) handoff file, the run fails at `load_prompt` with an actionable message.
- `check_done` cannot pass on the worker's self-report alone; a failing test command forces NO.
- Loop validates cleanly and appears in the built-in loop listings/tests.
- Loop contains no Issue-system coupling.

## Risks

- `.ll/ll-continue-prompt.md` is a single shared file, overwritten by any session's `/ll:handoff` and by the PreCompact hook (`little_loops.hooks.pre_compact_handoff`). Mitigated by the staleness check, provenance printing, and the pinned `goal.md`.

## References

- `general-task.yaml` — `on_handoff: spawn`, `pass-started.txt` freshness check in `select_step` / `do_work`
- `little_loops.fsm.handoff_handler` — spawn = detached `ll-loop resume <loop>`
- `little_loops.issue_manager.run_with_continuation` — Issue-coupled Python equivalent used by ll-auto

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-25T22:27:12 - `bff3e917-f6b3-4423-97e1-f84bce0f9928.jsonl`
- `/ll:format-issue` - 2026-09-25T22:14:32 - `d4531072-4651-4af1-8df5-773eb121a569.jsonl`
- `/ll:capture-issue` - 2026-09-25T04:27:15 - `a8472ba4-4c46-48b4-8f68-409c6b4973fa.jsonl`
