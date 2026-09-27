---
id: FEAT-3594
type: FEAT
title: 'continue-task loop: run a continuation prompt until done with automatic handoff/resume'
priority: P3
status: done
decision_needed: false
reconcile_attempted: true
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T04:27:08Z'
completed_at: '2026-09-27T04:18:10Z'
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-3594: continue-task loop: run a continuation prompt until done with automatic handoff/resume

## Summary

Add a built-in, general-purpose FSM loop `continue-task` that takes a continuation prompt and keeps working it until done, handling context exhaustion with automatic `/ll:handoff` → spawned `/ll:resume` sessions. Input is optional: with no input, the loop starts from the newest `.ll/ll-continue-prompt.md`.

**Status of scope (review 2026-09-26):** the loop shipped in e4556ec95 (`scripts/little_loops/loops/continue-task.yaml`). Remaining work: (1) a loop-local fingerprint gate for `stall_check` in place of `diff_stall_gate`; (2) clear stale `tests.txt` in `run_tests`; (3) guard `work`'s `/ll:resume` re-entry against foreign handoffs; (4) dedicated tests; (5) the `docs/guides/LOOPS_REFERENCE.md` row. Do NOT re-implement the loop.

## Current Behavior

Continuing a handed-off session is manual: open a new session, run `/ll:resume`, repeat at every handoff. `general-task` automates handoff/resume but only inside its own plan/DoD pipeline and requires an explicit task input.

## Expected Behavior

`ll-loop run continue-task [prompt]` works a continuation prompt (explicit, or the newest non-stale `.ll/ll-continue-prompt.md`) across as many automatic handoffs as needed, stopping when an independent done-check against the pinned starting goal passes, or at the iteration cap with a partial summary.

## Motivation

No built-in loop defaults its input to the handoff prompt. `general-task` is the only loop that reads `.ll/ll-continue-prompt.md`, and only to re-enter a pass mid-step (`do_work`). It is the wrong shape for this job: it always runs `define_done` and `plan`, then the DoD verification / final-tests / step-abandonment machinery. A continuation prompt already carries the plan and current state, so re-planning discards or duplicates it.

## Proposed Solution

### As built (e4556ec95) — keep

Thin loop, decoupled from the Issue system. 8 non-terminal states: `load_prompt` (shell: heredoc input capture per BUG-2622, handoff-file fallback rejected when older than `continuation.prompt_expiry_hours`, pins `goal.md`, resolves test cmd + records baseline exit) → `start_pass` (touches `pass-started.txt`, bumps `pass-count.txt`) → `work` (prompt; `/ll:resume` iff handoff `-nt` `pass-started.txt`; maintains `progress.md`; `/ll:handoff` at threshold) → `stall_check` → `run_tests` (shell; exit 1 only on regression = baseline 0 and now non-zero; pre-existing failure advisory) → `check_done` (prompt; skeptical judge writes one word to `verdict.txt`) → `read_verdict` (shell: `grep -qx 'DONE'`) → `done`, else back to `start_pass`. `summarize_partial` → `partial` on stall or `on_max_steps`. Top level: `on_handoff: spawn`, `max_steps: 150`, no `required_inputs`.

### Changes (review 2026-09-26)

1. **Replace `stall_check`'s `diff_stall_gate`** with a loop-local shell fingerprint gate. `evaluate_diff_stall` keeps its state in `.loops/tmp/ll-diff-stall-_root_.*`, shared across runs and loops and never reset, and snapshots `git diff --stat`, which ignores commits, staged changes, untracked files and same-line-count edits (BUG-3627). Consequences for this loop: a fresh run can stall on pass 1 from a previous run's counter, and a worker that commits each pass is judged stalled. New gate, modeled on `general-task.yaml` `final_verify_spin_gate` (:423):
   - `load_prompt` records `git rev-parse HEAD` to `${context.run_dir}/baseline-ref.txt` (when in a git repo).
   - `stall_check` (shell) hashes `git diff <baseline-ref> -- . ':(exclude).loops/'` plus untracked paths + contents (same `untracked()` helper, explicit `.loops/` exclusion since `ll-init` ships no `.loops/` gitignore) into `${context.run_dir}/stall-fingerprint.txt`; identical fingerprint increments `stall-counter.txt`, a change resets it. Emit the count and gate with `output_numeric lt 3` (keep the existing "3 identical passes" budget). Route `yes → run_tests`, `no → summarize_partial`, `on_error → run_tests`.
   - Non-git fallback: no fingerprint possible — treat every pass as progress (the `max_steps` cap still bounds the run). Say so in a comment.
   - Local shell vars unbraced (`"$FP"`), per the FSM-interpolates-first rule.
2. **`run_tests`: clear stale `tests.txt`.** Add `rm -f "$RUN_DIR/tests.txt"` next to the `verdict.txt` removal, so an `on_error` (timeout) route into `check_done` cannot read a previous pass's `PASS`. `check_done`'s prompt already treats a missing `tests.txt` as no test signal only implicitly — add one line: "If tests.txt is missing, the test run did not complete; do not treat tests as passing."
3. **Guard `work`'s re-entry against foreign handoffs.** `.ll/ll-continue-prompt.md` is shared: any other session's `/ll:handoff` (or the PreCompact hook) during a pass makes the `-nt` check fire and `/ll:resume` load unrelated notes. Tighten the check to also require the run dir in the handoff text:
   `[ .ll/ll-continue-prompt.md -nt ${context.run_dir}/pass-started.txt ] && grep -qF '${context.run_dir}' .ll/ll-continue-prompt.md && echo RESUME`
   and tell the worker, in the handoff-chain paragraph, to include the literal run dir path (`${context.run_dir}`) in its handoff notes. Fail-safe: if a handoff omits it, the session works from `goal.md` + `progress.md` + `done-check.md`, which carry the durable state anyway.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

As-built deltas vs this section (implementation landed in e4556ec95; constraints below describe what must stay true):
- Step 4's `check_done (prompt + llm_structured)` shipped as prompt + mechanical verdict file (one-word `verdict.txt` gate in `read_verdict`) — same judge-independence outcome ("You did NOT do this work; judge it skeptically", `continue-task.yaml:216-217`; worker told "Do NOT declare the task finished", :153-154), different mechanism.
- Step 2's `/ll:resume`-on-fresher-handoff re-entry is present: `work` runs `/ll:resume` iff `.ll/ll-continue-prompt.md` is `-nt` `pass-started.txt`; the marker is deliberately NOT refreshed mid-pass so an intra-pass handoff is still detected (`continue-task.yaml:108-111`), mirroring `general-task.yaml:364-368, 516-518`.

**Option A**: Correct the API/Interface example — drop `--context max_passes=20`. Nothing in `continue-task.yaml` reads a `max_passes` context key; the run accepts it as a silent no-op. The real pass budget is `max_steps: 150` plus the `diff_stall_gate` (max_stall 3).

> **Selected:** Option A — `max_steps` + stall gate already bound passes with no distinct failure mode for a second budget; dropping the dead knob restores the declare-then-document convention.

**Option B**: Implement the `max_passes` knob — declare it in the loop's `context:` block and cap passes in the start_pass state against the pass-count.txt counter — so the documented example works as written.

**Recommended**: Option A — `max_steps` and the stall gate already bound runaway passes; a second overlapping budget adds config surface with no distinct failure mode. Option B remains cheap if a per-pass budget is ever wanted.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-25.

**Selected**: Option A

**Reasoning**: The pass budget is already doubly bounded — `max_steps: 150` (~25 passes per the loop's own header comment) plus `diff_stall_gate` max_stall 3 — and a `max_passes` default above ~25 can never fire before `max_steps`, while one below it routes to the same `summarize_partial` terminal: no distinct failure mode, only extra config surface on an already-shipped loop. Every other documented `--context` example in the repo cites a key its loop declares and reads (e.g. `min_pass_rate` → `general-task.yaml:17`, `max_remediation_passes` → `rn-remediate.yaml:48,:866`); repo-wide grep confirms `max_passes` is the sole documented-but-unread exception, hitting only generic test fixtures and this issue. The example keeps `--context test_cmd="..."`, which is real (`continue-task.yaml:48`, consumed at `:89`), so the `--context` capability remains demonstrated.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B | 2/3 | 2/3 | 2/3 | 2/3 | 8/12 |

**Key evidence**:
- For Option A — `max_passes` is read by nothing (repo-wide unfiltered grep: only mechanism-test fixtures — `test_ll_loop_commands.py:5883-5999` etc. — and this issue); a `.issues/` edit hits no gate (`test_docs_audience_gate.py:34-36`, wiring needles, packaging mirror all out of scope); matches the issue's own `**Recommended**` marker.
- For Option B — the counter + `output_numeric lt` cap idiom ships in three loops (mechanize-skills `diagnosis_retry:307-325`, rn-remediate `check_remediation_budget:861-879`, general-task `spin_gate:410-418`) and `start_pass` already maintains `pass-count.txt` — genuinely cheap, but it overlaps the documented `max_steps` budget with no distinct failure mode and re-enters the builtin-loop lint battery (ENH-2825 failure-edge routing, MR-11 markers, `$${}` escaping) for no behavioral gain.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/continue-task.yaml` (exists — implemented in e4556ec95 after this issue was captured; verify against Acceptance Criteria rather than re-implementing)
- `docs/guides/LOOPS_REFERENCE.md` — add the still-missing continue-task row to the General-Purpose table (GAP finding below; now an AC)
- `scripts/tests/test_continue_task_loop.py` (new) — NEW dedicated test file, or a `TestContinueTaskLoop` class in `scripts/tests/test_builtin_loops.py` (shape detailed in Tests below)

### Dependent Files (Callers/Importers)
- N/A — standalone built-in loop, discovered by the loop loader

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/loop_paths.py` (`resolve_loop_path()`, `get_builtin_loops_dir()`), `scripts/little_loops/cli/loop/run.py` (`cmd_run()`, `required_inputs` guard :350-357), `scripts/little_loops/cli/loop/lifecycle.py` (`cmd_resume()`), `scripts/little_loops/cli/loop/config_cmds.py` (`cmd_validate()`, `cmd_install()`) — the generic loader/discovery chain; fully name-parametric (no continue-task branch anywhere in `scripts/little_loops`). No edit needed [Agent 1 finding]
- `commands/resume.md` — reads the same `continuation.prompt_expiry_hours` but only warns (`:48-50`) and additionally checks a user-level `~/.ll/ll-continue-prompt.md` fallback (`:38-40`) that `load_prompt` lacks; the reject-vs-warn strictness difference is a wording choice for the LOOPS_REFERENCE row, not an edit here [Agent 2 finding]
- `scripts/little_loops/loops/lib/common.yaml:183` — `diff_stall_gate` fragment definition (`stall_check` dependency); tested in `scripts/tests/test_fsm_fragments.py::TestDiffStallGate` (:1710-1747). No edit needed [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/loops/general-task.yaml` — handoff wiring, `check_baseline_tests` test-cmd resolution
- `scripts/little_loops/loops/prompt-across-issues.yaml` — quoted-heredoc input capture

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_incremental_refactor_loop.py` — `_load_state_script()` (:18) + `_bash()`, writing a real `.ll/ll-config.json` into tmp_path so `ll-config get` resolves for real — closest analog for `load_prompt`'s expiry / test_cmd fallback tests [Agent 3 finding]
- `scripts/tests/test_spike_verdict_routing.py` — standalone per-loop routing-test model: `_load()` (:17) / `_run()` (:30) with the MR-11 `:shell}` → `}` strip (:36) and a PATH-stubbed CLI — the template for `read_verdict` parametrized cases [Agent 3 finding]

### Tests
- `scripts/tests/test_builtin_loops.py` — expected built-in loop list

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_continue_task_loop.py` (new) — NEW dedicated test file (or a `TestContinueTaskLoop` class in `test_builtin_loops.py`, `TestSpikeGateLoop` at :13503 is the shape): `load_prompt` shell-level cases (explicit input → `goal.md` + `PROMPT_SOURCE: input`; fresh handoff + empty input → `PROMPT_MTIME`/`PROMPT_FIRST_LINE` provenance; stale handoff → exit 1 naming `continuation.prompt_expiry_hours`; neither source → exit 1 usage; whitespace-only input falls through; non-numeric/missing expiry defaults to 24), `required_inputs`-absence (`assert not data.get("required_inputs")`, precedent at :6019), and `read_verdict` gate (DONE / NOT_DONE / missing / whitespace vs `grep -qx`). No existing test asserts any of the loop's strings — these establish the contracts [Agent 3 finding]

_Review 2026-09-26 additions:_
- `run_tests` cases (AC3's mechanism — previously unplanned): baseline `0` + command now fails → exit 1, `TEST_STATUS: REGRESSED`, `done-check.md` overwritten with the output tail; baseline non-zero + fails → exit 0, `FAILING (pre-existing)`; empty `resolved-test-cmd.txt` → exit 0, `SKIP`; passing → `PASS`; `verdict.txt` and `tests.txt` removed at start. Plus `load_prompt` baseline recording: a command exiting 127 leaves `baseline-exit.txt` = `SKIP`.
- New `stall_check` cases: identical tree across passes → counter 1, 2, 3 → exit 0 with `3` on stdout (gate `no`); a pass that only commits, only adds an untracked file, or makes a same-line-count edit resets to 0; changes under `.loops/` do not reset; non-git dir → progress. Use a real `git init` tmp repo.
- `work` re-entry guard: assert the action contains the `grep -qF` run-dir clause (string-level; the prompt itself isn't executed).
- **Harness pitfall — `:shell` refs**: the `_run` helper in `test_spike_verdict_routing.py:36` strips `:shell}` → `}` without quoting. For `CMD=${context.test_cmd:shell}` with `pytest -x`, that yields `CMD=pytest -x` (runs `-x`). Substitute `:shell` refs with `shlex.quote(value)` (and `''` for empty).
- **Harness pitfall — real test suites**: every `load_prompt` test must set `test_cmd` explicitly (`true` / `false` / `exit 127`) or put a stub `ll-config` first on PATH. Otherwise the baseline step resolves `project.test_cmd` and can run a real pytest suite from inside the suite.
- **Portability**: CI runs ubuntu + macOS legs. Assert `PROMPT_MTIME:` is present, never its format (`ls -l` columns differ across GNU/BSD and `TIME_STYLE`). Set stale mtimes with `os.utime`.

### Documentation
- DONE as of e4556ec95: `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, README loop count (108). REMAINING: the `docs/guides/LOOPS_REFERENCE.md` General-Purpose row (wiring block below; now an AC).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — add the continue-task row to the General-Purpose table (`general-task`/`stepwise-task` rows at :78-79; gap re-confirmed by grep). Wording must pass `test_docs_audience_gate.py` (end-user framing) and read consistently with the `required_inputs` contract paragraph at :97 [Agent 1/2 finding]
- `README.md:198`, `README.md:232` — additional "Loops Reference" coverage claims ("Every built-in loop and fragment library") in `Where to go next` / the docs table, alongside the known `:118` claim; the row makes all three true. No edit needed beyond the row itself [Agent 2 finding]

### Configuration
- Reads `continuation.prompt_expiry_hours`, `project.test_cmd` (no new keys)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` — `continuation.prompt_expiry_hours` is bounded min 1 / max 168 / default 24 (`:903-909`); `fsm-loop-schema.json` `context` block is free-form. No schema change under either Option A or B [Agent 1/2 finding]

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

1. DONE as of e4556ec95 — `scripts/little_loops/loops/continue-task.yaml` exists; as built it has 8 non-terminal states and a `verdict.txt` / `read_verdict` gate instead of `llm_structured` (see findings). Do not re-implement.
2. Registration DONE as of e4556ec95 (expected-set entry `scripts/tests/test_builtin_loops.py:300`, `scripts/little_loops/loops/README.md:93`, `docs/guides/LOOPS_GUIDE.md:391`, README loop count 108).
3. TDD: write the dedicated tests first (`scripts/tests/test_continue_task_loop.py` (new)) — `load_prompt` six cases + baseline-127, `run_tests` cases, new `stall_check` cases, `read_verdict` gate, `required_inputs`-absence, re-entry guard string (Integration Map → Tests). The `stall_check`, `tests.txt` and guard tests fail until step 4.
4. Apply Proposed Solution → Changes 1–3 to `continue-task.yaml`: fingerprint `stall_check` (+ `baseline-ref.txt` in `load_prompt`), `rm -f tests.txt` + missing-tests line in `check_done`, run-dir-gated re-entry + handoff instruction in `work`. Update the header comment's step count if `stall_check` changes it (it stays 1 step/pass). Run `ll-loop validate continue-task`.
5. Add the `docs/guides/LOOPS_REFERENCE.md` General-Purpose row (after `stepwise-task`, :79). End-user framing. Cover: input optional (newest `.ll/ll-continue-prompt.md`, rejected when older than `continuation.prompt_expiry_hours` — stricter than `/ll:resume`, which only warns); pinned goal; independent done-check; the spawned continuation is detached, so the foreground view ends at the first handoff — follow with `ll-loop status continue-task`. This closes the former step 4 (detached-spawn documentation); the YAML description already states it.
6. Run the gates: `python -m pytest scripts/tests/test_continue_task_loop.py scripts/tests/test_builtin_loops.py scripts/tests/test_builtin_loop_interpolation.py scripts/tests/test_builtin_loop_hardcode_gate.py scripts/tests/test_docs_audience_gate.py`, then the full suite.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Steps 1-2 are DONE as of e4556ec95 (file exists; every registration point verified — see Integration Map findings). The LOOPS_REFERENCE.md row found there extends step 2's doc surface.
- Step 3 is PARTIALLY done: `ll-loop validate` coverage exists via `test_all_validate_as_valid_fsm` (`scripts/tests/test_builtin_loops.py:77-80`) and expected-set membership at :300, but the dedicated `load_prompt` shell-level tests and the `required_inputs`-absence test do not exist anywhere in `scripts/tests/` (searched; the only hit is the expected-set entry).
- Precedent for those tests: extract the state's shell action from the YAML, substitute `${context.*}` refs from declared defaults + overrides, run under `bash -c` with cwd = a tmp "project" dir, and assert on stdout markers + returncode + run_dir file contents — the `_load_state_script` / `_setup_run_dir` / `_bash` harness in `scripts/tests/test_general_task_loop.py:509-531, 1058-1059` (e.g. `TestBatchedPasses` at :2740-2784).
- Outcomes the shell-level tests should hold true: explicit input -> `goal.md` written from `input.txt` and `PROMPT_SOURCE: input`; fresh handoff file + empty input -> `goal.md` copied with `PROMPT_MTIME` / `PROMPT_FIRST_LINE` provenance; stale handoff -> exit 1 naming `continuation.prompt_expiry_hours` and the explicit-prompt remedy; neither source -> exit 1 with usage; whitespace-only input falls through to the handoff branch; non-numeric/missing expiry config defaults to 24.
- Step 4 verified accurate as written: `_spawn_continuation` discards stdout/stderr/stdin (DEVNULL) and detaches via `start_new_session=True` (`scripts/little_loops/fsm/handoff_handler.py:123-131`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add the `docs/guides/LOOPS_REFERENCE.md` continue-task row (General-Purpose table) — end-user framing for the audience gate, consistent with the `required_inputs` paragraph at `:97`
- Create the dedicated continue-task tests — `load_prompt` six cases + `required_inputs`-absence + `read_verdict` gate, following the `test_incremental_refactor_loop.py` / `test_spike_verdict_routing.py` harness patterns
- Resolve Option A/B via `/ll:decide-issue` before `/ll:ready-issue` — `decision_needed: true` gates the decision oracles (`refine-to-ready`, `autodev`, `rn-remediate`); the `max_passes` example appears nowhere outside this issue, so Option A edits only this file
- Gates in force, none needing edits: `test_docs_audience_gate.py` (row wording), `test_wiring_guides_and_meta.py::test_string_present_in_doc` needles (additive edits safe), `test_doc_counts_all_match` (loop already counted), `test_packaging_duplicate_files.py` mirror (trips only if `README.md` itself is edited)

## Impact

- **Priority**: P3 - Workflow convenience; manual `/ll:resume` works today
- **Effort**: Small - three targeted edits to the shipped YAML, one test file, one doc row
- **Risk**: Low - changes confined to `continue-task.yaml`; no executor or other-loop changes (the shared evaluator fix is BUG-3627)
- **Breaking Change**: No

## Use Case

A developer's interactive session hits the context threshold mid-task and runs `/ll:handoff`. Instead of manually opening a new session and running `/ll:resume` (repeatedly, for a long task), they run `ll-loop run continue-task` with no argument. The loop picks up the handoff prompt, pins its goal, and keeps working across as many handoffs as needed, stopping only when an independent done-check (plus the test command, when one exists) confirms the goal is met, or when the iteration cap is hit.

## API/Interface

```
ll-loop run continue-task                 # resume newest .ll/ll-continue-prompt.md
ll-loop run continue-task "<prompt>"      # explicit continuation prompt / task
ll-loop run continue-task --context test_cmd="pytest -x"
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- The `--context max_passes=20` example does not correspond to any knob the loop reads — see the Option A/B decision under Proposed Solution -> Codebase Research Findings.

## Acceptance Criteria

- `ll-loop run continue-task` with no input and a fresh handoff file starts from that file and writes `goal.md`.
- With no input and no (or stale) handoff file, the run fails at `load_prompt` with an actionable message.
- The run reaches `done` only via `read_verdict` finding exactly `DONE` in `verdict.txt` (written by the separate `check_done` session); `run_tests` exits 1 (skipping `check_done`) only when the test command passed at baseline and fails now — a failure already present at baseline is reported as `FAILING (pre-existing)` and exits 0.
- `stall_check` stall state lives only under `${context.run_dir}`: a fresh run never inherits another run's stall count, and a pass that only commits, only adds untracked files, or makes a same-line-count edit counts as progress. Three consecutive passes with an identical fingerprint route to `summarize_partial`.
- `run_tests` removes `tests.txt` before running, so a timed-out test run cannot leave a previous pass's status for `check_done`.
- `work` runs `/ll:resume` only when the handoff file is newer than `pass-started.txt` AND mentions this run's run dir.
- `scripts/tests/test_continue_task_loop.py` (new) covers the `load_prompt`, `run_tests`, `stall_check` and `read_verdict` cases listed under Integration Map → Tests, and passes on both GNU and BSD userlands.
- Loop validates cleanly and appears in the built-in loop listings/tests.
- Loop contains no Issue-system coupling.
- `continue-task` has a row in `docs/guides/LOOPS_REFERENCE.md`'s General-Purpose table.

## Verification Notes

_Verified by `/ll:verify-issues --auto` — 2026-09-25:_

Verdict at time of check: **DIRECTIVE_DRIFT** (one check-B6 finding below; every claim about current code verified accurate — see the per-claim log — so this is a directive-level gap only, not a claim failure)

**Verified accurate** (all at working tree, `main` @ 98c033121 + unstaged edits):
- `scripts/little_loops/loops/continue-task.yaml` exists; every cited line anchor holds: `:36` (`artifact_versioning_ok: true`), `:37-38` (input-not-in-`required_inputs` comment), `:48`/`:89` (`test_cmd` declared/consumed), `:108-111` (pass-marker not refreshed mid-pass), `:129` (`-nt` resume check), `:153-154` ("Do NOT declare the task finished"), `:216-217` ("You did NOT do this work; judge it skeptically"), `:244` (`grep -qx 'DONE'`). State inventory (8 non-terminal + `done`/`partial`/`failed`), `max_steps: 150`, `diff_stall_gate` max_stall 3, `on_handoff: spawn` all as documented.
- e4556ec95 is the implementation commit (confirmed via `git show`).
- Cross-file anchors all hold: `general-task.yaml:17/:364-368/:410-418/:516-518`, `rn-remediate.yaml:48/:861-879`, `schema.py:1428` (`required_inputs` defaults `[]`), `run.py:350-357` guard, `handoff_handler.py:68/:96/:123-131` (DEVNULL + `start_new_session=True`), `persistence.py:55/:174-175/:1388`, `signal_detector.py:74`, `executor.py:4466`, `commands/handoff.md:194`, `commands/resume.md:38-40/:48-50` (warn-only strictness difference confirmed), `config-schema.json:903-909`, `fragments.py:142`, `common.yaml:183`, `meta_rules.py:201-231/:278-293`, `interpolation.py:280-316`, `test_builtin_loops.py:77-80/:204/:300/:6019/:13503`, `test_fsm_fragments.py:1710-1747`, `test_spike_verdict_routing.py:17/:30/:36`, `test_incremental_refactor_loop.py:18`, `test_docs_audience_gate.py:34-36`, `mechanize-skills.yaml` `diagnosis_retry` at `:304-305`.
- GAP claims still true as of this check: `docs/guides/LOOPS_REFERENCE.md` has **no** continue-task row (general-task/stepwise-task at `:78-79`, `required_inputs` paragraph at `:97`), while `README.md:118/:198/:232` claim full coverage; `scripts/tests/test_continue_task_loop.py` (new) / `TestContinueTaskLoop` do not exist, no `load_prompt` tests anywhere — step 3 remains PARTIALLY done exactly as the research findings state.
- Option A decision verified: repo-wide grep confirms `max_passes` appears only in generic mechanism-test fixtures (`test_ll_loop_commands.py:5883-5999`) and this issue — no loop reads it; the API/Interface example already drops it (decision applied).
- Evidence-quote check (`ll-verify-evidence`): clean, 0 findings. Decisions log: no active required rules. No dependency declarations to check.

**DIRECTIVE_DRIFT finding (check B6 — AC-coverage gap)**: the Integration Map's Documentation section and the Wiring Phase both require the `docs/guides/LOOPS_REFERENCE.md` continue-task row, but no Acceptance Criterion covers it — the closest AC ("appears in the built-in loop listings/tests") covers `loops/README.md` / `LOOPS_GUIDE.md` / the expected-set test, not LOOPS_REFERENCE. Since eval harnesses (`/ll:create-eval-from-issues`) and readiness gates consume ACs, an implementer working to the ACs could ship without the doc row and pass every criterion.

Remaining:
- Add an AC covering the LOOPS_REFERENCE.md row (e.g. "continue-task documented in the LOOPS_REFERENCE General-Purpose table"), or run `/ll:reconcile-issue FEAT-3594` — this is `DIRECTIVE_DRIFT`'s designated remedy; not applied here (auto-mode scope is verification notes only).
- Implement the Wiring Phase items (doc row + dedicated tests) — still open, accurately tracked by this issue.

_Re-verified by `/ll:verify-issues --auto` — 2026-09-26 (after the 2026-09-26 review rewrite):_

Verdict at time of check: **VALID** (no corrections needed; the 2026-09-25 `DIRECTIVE_DRIFT` finding above is resolved — the LOOPS_REFERENCE.md row is now an Acceptance Criterion, and its "Remaining" AC item is closed).

- `continue-task.yaml` still matches every claim about current state: `stall_check` uses `diff_stall_gate` with `max_stall: 3` (:160-171); `run_tests` removes only `verdict.txt` (:181), so the stale-`tests.txt` gap (Change 2) is real; `work`'s re-entry check is the bare `-nt` test (:129), so the foreign-handoff gap (Change 3) is real; `load_prompt` records no `baseline-ref.txt` (Change 1 prerequisite); `check_done` has no missing-`tests.txt` line.
- Change 1's premise holds: `evaluate_diff_stall` keeps state in `.loops/tmp/ll-diff-stall-<cache_key>.txt/.count` (`fsm/evaluators.py:629-630`) and snapshots `git diff --stat` (:581). Model anchor `general-task.yaml` `final_verify_spin_gate` (:423) and its `untracked()` helper (:470) exist as described.
- BUG-3627 exists (open). `scripts/tests/test_continue_task_loop.py` and the LOOPS_REFERENCE row are still absent — accurately tracked as remaining work.
- Proposal-vs-code check (B6): no exception-handler, fixture, or AC-coverage gaps found; every Change maps to an AC and every Integration Map file is covered.
- Evidence-quote check (`ll-verify-evidence`): clean, 0 findings. Decisions log: no active required rules. Graph: codegraph, fresh (not needed for the verdict).

## Risks

- `.ll/ll-continue-prompt.md` is a single shared file, overwritten by any session's `/ll:handoff` and by the PreCompact hook (`little_loops.hooks.pre_compact_handoff`). Mitigated by the staleness check, provenance printing, and the pinned `goal.md`.
- The same shared file drives `work`'s mid-pass `/ll:resume` re-entry: an unrelated session's handoff written during a pass would otherwise be resumed into this run. Mitigated by Change 3 (resume only when the handoff mentions this run dir); fail-safe is working from `goal.md` / `progress.md`.
- The loop previously used `diff_stall_gate`, whose cross-run cache and `--stat` signal produce false stalls (BUG-3627). Change 1 removes that dependency here; BUG-3627 fixes the evaluator for the other 11 loops.

## References

- `general-task.yaml` — `on_handoff: spawn`, `pass-started.txt` freshness check in `select_step` / `do_work`
- `little_loops.fsm.handoff_handler` — spawn = detached `ll-loop resume <loop>`
- `little_loops.issue_manager.run_with_continuation` — Issue-coupled Python equivalent used by ll-auto

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Resolution

Implemented 2026-09-27: loop-local fingerprint `stall_check` (+ `baseline-ref.txt`), stale `tests.txt` cleared in `run_tests`, run-dir-guarded `/ll:resume` re-entry, `scripts/tests/test_continue_task_loop.py` (30 tests), LOOPS_REFERENCE row.

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-09-27T04:18:10 - `90d0b0d8-6a56-424d-9ab1-1657abf73790.jsonl`
- `/ll:ready-issue` - 2026-09-27T04:11:13 - `eaddcf85-90ff-4c37-836f-a664fa4ec1d1.jsonl`
- `/ll:confidence-check` - 2026-09-27T03:50:11 - `c4c15e75-d4e1-4ac8-b300-d2fe135d2325.jsonl`
- `/ll:verify-issues` - 2026-09-27T03:43:20 - `957314ff-4b9b-42e1-b372-a938199f022f.jsonl`
- `/ll:confidence-check` - 2026-09-25T23:38:00 - `45d43ec4-b840-43ef-b61e-afb3edaab08c.jsonl`
- `/ll:reconcile-issue` - 2026-09-25T23:26:13 - `8a0a45f1-b52b-4c03-a859-99ea828324c5.jsonl`
- `/ll:verify-issues` - 2026-09-25T23:12:36 - `95f633b7-5064-467a-9466-762178a1aff0.jsonl`
- `/ll:decide-issue` - 2026-09-25T22:57:17 - `5830abf4-70be-40d6-a44c-678fd54b71da.jsonl`
- `/ll:wire-issue` - 2026-09-25T22:45:30 - `4ad816e2-21f5-4785-88cc-12616ff52711.jsonl`
- `/ll:refine-issue` - 2026-09-25T22:27:12 - `bff3e917-f6b3-4423-97e1-f84bce0f9928.jsonl`
- `/ll:format-issue` - 2026-09-25T22:14:32 - `d4531072-4651-4af1-8df5-773eb121a569.jsonl`
- `/ll:capture-issue` - 2026-09-25T04:27:15 - `a8472ba4-4c46-48b4-8f68-409c6b4973fa.jsonl`
