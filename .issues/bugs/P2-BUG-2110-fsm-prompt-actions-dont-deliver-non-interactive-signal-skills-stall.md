---
id: BUG-2110
type: BUG
priority: P2
status: done
captured_at: '2026-06-13T15:27:51Z'
completed_at: '2026-06-13T17:11:14Z'
discovered_date: '2026-06-13'
discovered_by: capture-issue
labels:
- bug
- fsm
- loops
- automation
- host-runner
- captured
confidence_score: 100
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 18
---

# BUG-2110: FSM prompt actions never deliver the non-interactive signal to spawned skills (auto-mode auto-detect is dead code)

## Summary

When a loop runs an interactive skill via `action_type: prompt` (e.g. `ll-loop run prompt-across-issues "/ll:format-issue {issue_id}"`), the skill's automation-context auto-detection never fires. The skill runs in interactive mode, hits `AskUserQuestion`, and silently degrades to analysis-only — producing no file mutations while the loop unconditionally advances. Observed live: a `prompt-across-issues` run formatting 17 issues only mutated 5; the other 12 stalled on unanswered interactive questions (see `audit-prompt-across-issues-2026-06-13.md`).

## Current Behavior

Interactive issue-prep skills auto-detect automation context with this idiom (e.g. `skills/format-issue/SKILL.md:60-65`):

```bash
if [[ "$FLAGS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then
    AUTO_MODE=true
fi
```

Under an FSM `prompt` action **both branches are dead**:

1. `ClaudeCodeRunner.build_streaming` passes `--dangerously-skip-permissions` as a top-level flag to the **`claude` binary** (`scripts/little_loops/host_runner.py:245`), not as an argument to the slash command. Inside the skill, `$FLAGS` / `$ARGUMENTS` contains only the command's own args (the issue ID), so the string-match never hits.
2. **Nothing in the codebase ever sets the `DANGEROUSLY_SKIP_PERMISSIONS` env var.** `grep -rn "DANGEROUSLY"` across `scripts/little_loops/` finds only: the CLI flag in `host_runner.py`, the log string in `issue_manager.py:134`, and two call sites that *strip* the flag (`fsm/handoff_handler.py:118`, `parallel/worker_pool.py:578`). The subprocess env built in `subprocess_utils.py:309-321` only injects `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR`.

Net effect: every loop that drives an interactive skill through `action_type: prompt` silently stalls into analysis-only mode unless the operator remembers to pass `--auto` explicitly in the prompt string.

## Root Cause

The non-interactive signal is never delivered to the spawned skill subprocess. The FSM prompt path is:

`fsm/executor.py:_run_action` → `fsm/runners.py:DefaultActionRunner.run` (slash-command branch, line 125 `run_claude_command`) → `issue_manager.run_claude_command` → `subprocess_utils` (`resolve_host().build_streaming(...)` → `Popen(cmd_args, env=env)` at `subprocess_utils.py:298-321`).

`build_streaming` adds `--dangerously-skip-permissions` to the `claude` argv but does **not** add any non-interactive marker to `invocation.env`. So the merged subprocess env (`env.update(invocation.env)`, `subprocess_utils.py:310`) carries no signal the skill can read. The `${DANGEROUSLY_SKIP_PERMISSIONS:-}` env-var branch that ENH-669 propagated to multiple skills is therefore latent dead code — it was never wired to a producer.

**Anchors:**
- `scripts/little_loops/host_runner.py:245` (flag added to argv), `:262` (env dict — missing the signal)
- `scripts/little_loops/subprocess_utils.py:298-321` (env construction + Popen)
- `skills/format-issue/SKILL.md:60-65` (dead consumer idiom; mirrored in `confidence-check`, `decide-issue`, `go-no-go`, `audit-loop-run`, `debug-loop-run`, `audit-issue-conflicts`)

## Expected Behavior

When a skill is spawned via an FSM `prompt`/`slash_command` action (which always runs with `--dangerously-skip-permissions`), the skill's automation auto-detection should fire so interactive skills run in their non-interactive `--auto` equivalent without an explicit flag. Interactive skills run under loops should never stall on `AskUserQuestion`.

## Steps to Reproduce

1. `ll-loop run prompt-across-issues "/ll:format-issue {issue_id}"` over a set of open issues that have low-confidence (judgment-call) gaps.
2. Observe the run completes cleanly (all `exit_code: 0`, loop advances on every issue).
3. Inspect the issue files: issues whose gaps required judgment received gap analysis only, no section edits — the skill asked `AskUserQuestion` and nobody answered.

## Motivation

Loops that drive interactive skills through `action_type: prompt` are a core automation path (`prompt-across-issues`, and any future loop that fans a skill across a work-set). Today they report success while silently skipping any item whose gaps require judgment — a 29% effective success rate (5/17) in the observed run. Operators get no signal that 70% of items were no-ops, so they either ship incomplete work or burn time re-auditing every run by hand. Fixing the signal propagation makes the entire `prompt`-action automation surface trustworthy in one change rather than per-loop workarounds.

## Proposed Solution

Deliver a stable non-interactive signal through the spawned-subprocess env, then have skills honor it.

**Decided approach (hybrid — produce both vars, standardize consumers on `LL_NON_INTERACTIVE`).** `--dangerously-skip-permissions` answers "is the host allowed to act without permission prompts?" (a Claude-CLI security posture); the signal we actually need answers "should this skill skip `AskUserQuestion` and pick sensible defaults?" (a host-agnostic skill-behavior contract). These coincide today but are different concepts. Reusing `DANGEROUSLY_SKIP_PERMISSIONS=1` alone overloads a scary permission flag as a behavior signal and is hard to decouple later; introducing `LL_NON_INTERACTIVE` alone forces a same-PR edit to all ~15 consumers (including the 6 that already branch on `DANGEROUSLY_SKIP_PERMISSIONS`), and any partial migration reproduces the exact silent-stall symptom this bug is about. The hybrid avoids both:

1. **Producer (primary fix):** In `ClaudeCodeRunner.build_streaming` set **both** `LL_NON_INTERACTIVE: "1"` and `DANGEROUSLY_SKIP_PERMISSIONS: "1"` in the `env` dict that is already merged into the subprocess environment. For host parity, set both on `build_blocking_json` / `build_detached` and the Codex/opencode runner subclasses. Setting both means the 6 consumers that already check `${DANGEROUSLY_SKIP_PERMISSIONS:-}` keep working **immediately with no regression window**, while `LL_NON_INTERACTIVE` becomes the clean long-term signal (it sits naturally beside the existing `LL_*` env family and is host-agnostic).
2. **Consumers:** New and argv-only/prose-only consumers adopt `LL_NON_INTERACTIVE`. The shared consumer idiom during the transition is `[[ -n "${LL_NON_INTERACTIVE:-}" ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]`. Migrate the 6 existing `DANGEROUSLY_SKIP_PERMISSIONS` consumers to the `LL_NON_INTERACTIVE` branch opportunistically; once all ~15 consumers are migrated, the `DANGEROUSLY_SKIP_PERMISSIONS` clause can be dropped as a **cleanup follow-up** (it's a permission concept, not a behavior concept). See the Consumer Skills subsection for the full ~15-file surface.
3. **Defense-in-depth (docs):** Update `prompt-across-issues.yaml`'s description/usage examples to show `--auto` for interactive skills, so the loop is correct even before the signal lands.

**Note:** Do *not* "fix" this by bolting an `llm_structured` gate onto `prompt-across-issues` (as one audit proposed) — that contradicts the loop's explicit no-quality-gate contract (`prompt-across-issues.yaml:7-8`) and an LLM self-grade of "did changes apply?" is the unreliable-evaluator pattern the meta-loop rules warn against. The real fix is signal propagation.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — `ClaudeCodeRunner.build_streaming` (primary producer); for host parity also `build_blocking_json`, `build_detached`, and the env dict at the `:262` anchor.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/handoff_handler.py` — **`_spawn_continuation` (`:119`) does NOT pass `env=` to `subprocess.Popen`** (it merges nothing — the detached process inherits bare `os.environ`). The producer fix to `build_detached` alone will **not** reach the spawned continuation. This call site must be updated to pass `env={**os.environ, **invocation.env}` for the signal to propagate to detached/handoff continuations. [Agent 2 finding — implementation blocker]

_Wiring pass (2nd pass) added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/harness.py` — **`cmd_skill` calls `subprocess.run([inv.binary, *inv.args], ...)` with NO `env=` kwarg** — a SECOND env-propagation gap identical in shape to the `_spawn_continuation` one. Skills invoked via `ll-harness skill` will NOT receive `LL_NON_INTERACTIVE`/`DANGEROUSLY_SKIP_PERMISSIONS` because `inv.env` is never merged into the subprocess environment. Must pass `env={**os.environ, **inv.env}` so the signal reaches skills exercised through `ll-harness`. [Agent 2 finding — implementation blocker]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/subprocess_utils.py` — merges `invocation.env` into the subprocess env (`env.update(invocation.env)`); this is where the signal must survive to reach the skill.
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run` slash-command branch (`run_claude_command`), the FSM path that reaches the producer.
- `scripts/little_loops/issue_manager.py` — `run_claude_command` (intermediate caller in the prompt-action chain).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/worker_pool.py` — **second `invocation.env` reader**: `_detect_worktree_model_via_api` merges env at `:585` (`env.update(invocation.env)`) for a `build_blocking_json` probe, and strips `--dangerously-skip-permissions` from argv at `:578`. After the producer fix, the new env key will appear in this read-only probe's environment even though the flag is stripped from argv — functionally inert for the probe but a behavior change to verify. [Agent 2 finding]
- `scripts/little_loops/fsm/evaluators.py` — calls host runner `build_*` methods for LLM evaluators; another path that will carry the new env key. [Agent 1 finding]
- `scripts/little_loops/cli/harness.py`, `scripts/little_loops/cli/action.py`, `scripts/little_loops/fsm/executor.py` — automation entry points that invoke `build_*`/`run_claude_command`; confirm the signal reaches skills spawned through `ll-harness` and `ll-action`. [Agent 1 finding]
- `scripts/little_loops/cli/generate_skill_descriptions.py` — calls `run_claude_command` directly (one-shot release utility); will also receive the signal — confirm no unintended non-interactive behavior. [Agent 1 finding]

### Similar Patterns
- Host runner subclasses for Codex/opencode in `host_runner.py` — if introducing `LL_NON_INTERACTIVE`, set it there too for cross-host parity.
- Flag-stripping call sites `fsm/handoff_handler.py:118` and `parallel/worker_pool.py:578` — confirm they don't also strip the new env signal.

_Wiring pass (2nd pass) added by `/ll:wire-issue`:_
- **Scope-down on "Codex/opencode runner subclasses":** only `CodexRunner` actually produces an invocation. `OpenCodeRunner` and `PiRunner` `build_streaming`/`build_blocking_json`/`build_detached` all unconditionally `raise HostNotConfigured` and return no env dict — **no producer change is needed there today** (apply the fix if/when they are wired). The real cross-host parity work is `ClaudeCodeRunner` + `CodexRunner` only. [Agent 2 finding — scope correction]
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_llm_structured` (`:789`), `evaluate_blind_comparator` (`:963`), and the contract-schema judge (`:1217`) call `subprocess.run([invocation.binary, *args], ...)` with **no `env=` kwarg** — `invocation.env` is silently dropped. **Functionally inert** for this fix (these are direct LLM-judge calls, not skill invocations, so `LL_NON_INTERACTIVE` has no meaning to them), but worth a one-line confirmation during implementation that no evaluator path needs the signal. [Agent 2 finding — inert, confirm-only]
- `on_handoff` / `CONTEXT_HANDOFF` clarification: only `HandoffBehavior.SPAWN` (→ `_spawn_continuation`) creates a subprocess; `PAUSE` and `TERMINATE` spawn nothing. `_handle_handoff` in `executor.py` needs no change — the env fix is isolated to `_spawn_continuation`. [Agent 2 finding — scope clarification]

### Consumer Skills (honor the signal)
- `skills/format-issue/SKILL.md` (the `${DANGEROUSLY_SKIP_PERMISSIONS:-}` idiom), mirrored in `confidence-check`, `decide-issue`, `go-no-go`, `audit-loop-run`, `debug-loop-run`, `audit-issue-conflicts`.

_Wiring pass added by `/ll:wire-issue` — the consumer surface is materially larger than the 7 skills above (~15 files across `skills/` AND `commands/`). The "Codebase Research Findings" claim that `DANGEROUSLY_SKIP_PERMISSIONS=1` would activate "only format-issue" is wrong — 6 consumers already have the env-var branch._

**Already have the `${DANGEROUSLY_SKIP_PERMISSIONS:-}` env-var branch (fire immediately if producer sets that var):**
- `skills/format-issue/SKILL.md:63` (already listed)
- `commands/commit.md:17` — `... || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]` [Agent 2 finding]
- `commands/refine-issue.md:58` — same env-var branch [Agent 2 finding]
- `commands/normalize-issues.md:54` — same env-var branch [Agent 2 finding]
- `commands/verify-issues.md:40` — same env-var branch [Agent 2 finding]
- `commands/prioritize-issues.md:43` — **env-var branch ONLY, no argv fallback** (fully dead today; only fires via env producer) [Agent 2 finding]

**Argv-only check (`$ARGUMENTS`/`$FLAGS` string match) — need a NEW env-var branch added (these NEVER receive the top-level `claude` flag, per Root Cause #1):**
- `skills/confidence-check/SKILL.md:43`, `skills/decide-issue/SKILL.md:61`, `skills/go-no-go/SKILL.md:57`, `skills/audit-issue-conflicts/SKILL.md:42` (already in the issue's research)
- `skills/wire-issue/SKILL.md:61` — `if ARGUMENTS contains "--dangerously-skip-permissions"` (pseudocode) [Agent 1+2 finding — NEW]
- `skills/map-dependencies/SKILL.md:56` — `[[ "$ARGUMENTS" == *"--dangerously-skip-permissions"* ]]` [Agent 1+2 finding — NEW]
- `skills/issue-size-review/SKILL.md:51` — `[[ "$ARGUMENTS" == *"--dangerously-skip-permissions"* ]]` [Agent 1+2 finding — NEW]

**Prose-only (no bash guard) — need a detection block added if they should honor the signal:**
- `skills/audit-loop-run/SKILL.md:28,297`, `skills/debug-loop-run/SKILL.md:25,325` (already in the issue's research)

**Pseudocode consumer:**
- `skills/configure/areas.md:1137,1144` — branches on `DANGEROUSLY_SKIP_PERMISSIONS` in interactive/non-interactive pseudocode [Agent 2 finding]

_Wiring pass (2nd pass) added by `/ll:wire-issue` — `--auto`-capable skills with NO env-var branch (rely on explicit `--auto` in the prompt string today). They are NOT broken by this bug as long as loops pass `--auto`, but if `LL_NON_INTERACTIVE` is meant as a universal signal, they should honor it for parity. Decide scope: include them in the uniform rollout, or leave them as explicit-`--auto`-only and document that:_
- `skills/scope-epic/SKILL.md` — `Phase 1` AUTO parse (bash-regex on args only); invoked by `rn-build.yaml` via `action_type: prompt` with `--auto` already in the string. [Agent 2 finding]
- `skills/link-epics/SKILL.md` — `Step 1` AUTO parse (string-match only). [Agent 2 finding]
- `skills/simplify-loop/SKILL.md` — `--auto`/`--yes` flags, no env detection. [Agent 2 finding]
- `skills/review-loop/SKILL.md` — `--auto` for Auto-Apply Rules, no env detection. [Agent 2 finding]
- `skills/audit-claude-config/SKILL.md` — uses a **distinct `--non-interactive` flag** (not `--auto`/`DANGEROUSLY_SKIP_PERMISSIONS`); a separate convention the BUG-2110 fix won't unify unless `LL_NON_INTERACTIVE` is explicitly added. [Agent 2 finding]

_Decided approach (hybrid): the producer sets BOTH vars, so the 6 consumers above that already check `${DANGEROUSLY_SKIP_PERMISSIONS:-}` keep working with no regression. The argv-only and prose-only consumers get a new branch using the transition idiom `[[ -n "${LL_NON_INTERACTIVE:-}" ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]`. The 6 existing consumers migrate to `LL_NON_INTERACTIVE` opportunistically; dropping the `DANGEROUSLY_SKIP_PERMISSIONS` clause once all ~15 are migrated is a cleanup follow-up, not part of this fix._

### Tests
- New regression test asserting the non-interactive env var is present in the env passed to the spawned subprocess for prompt actions (target `build_streaming` / `subprocess_utils` env construction).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_host_runner.py` — add producer-level assertions that `build_streaming`, `build_blocking_json`, `build_detached` (and the `CodexRunner` equivalents) include the new env key in `invocation.env`. Existing argv-snapshot tests (`test_claude_runner_matches_legacy_args:119`) assert only on `args`, not `env`, so they will NOT break — but they also won't cover the new key. `test_default_env_and_capabilities:634` asserts `env == {}` on a **hand-constructed** `HostInvocation` (not runner-produced), so it is also safe. [Agent 3 finding]
- `scripts/tests/test_subprocess_utils.py` — integration-level regression test following the `capture_popen` / `captured_env.update(kwargs["env"])` pattern at `:261` (`test_sets_maintain_project_working_dir_env`); the autouse `_patch_resolve_host` fixture (`:71`) already wires a real `ClaudeCodeRunner`, so a new test in `TestRunClaudeCommand` will see the key land in the `Popen` `env` kwarg. This is the regression test the Acceptance Criteria calls for. [Agent 3 finding]
- `scripts/tests/test_wiring_init_and_configure.py:72` — asserts `"DANGEROUSLY_SKIP_PERMISSIONS"` appears as a string in `skills/configure/areas.md`. **Must be updated** if the fix introduces `LL_NON_INTERACTIVE` and updates `areas.md` to reference it. [Agent 2+3 finding]
- `scripts/tests/test_fsm_runners.py` (`TestDefaultActionRunnerSlashPath`) — currently mocks `run_claude_command` entirely, so it neither breaks nor covers env propagation. Optional: add a test that exercises the full `DefaultActionRunner → subprocess_utils → Popen` chain without mocking the env away. [Agent 3 finding]
- Argv-snapshot tests that pin `--dangerously-skip-permissions` but will NOT break from an env-only change (no env assertion): `test_subprocess_utils.py:230,990,2070`, `test_subprocess_mocks.py:103`. [Agent 3 finding]

_Wiring pass (2nd pass) added by `/ll:wire-issue`:_
- `scripts/tests/test_handoff_handler.py` — `test_spawn_behavior` (:55) patches `subprocess.Popen` and asserts `kwargs["start_new_session"]`, `stdout`, `stderr`, `stdin` — but does **NOT** assert on `kwargs.get("env")`. **Update required**: add an env kwarg assertion (`assert "LL_NON_INTERACTIVE" in kwargs.get("env", {})` and same for `DANGEROUSLY_SKIP_PERMISSIONS`) to cover the `_spawn_continuation` env-propagation fix. Without this, the handoff fix has zero test coverage. [Agent 3 finding — HIGH VALUE]
- `scripts/tests/test_cli_loop_background.py` — reference pattern for writing the `_spawn_continuation` env assertion; uses `mock_popen.call_args[1]` to inspect subprocess spawn kwargs (no env inspection today). [Agent 3 finding — reference only]
- `scripts/tests/test_host_runner.py` — `TestCodexRunner.test_codex_runner_flag_translation` (`:214-226`) asserts only `[invocation.binary, *invocation.args]`, NOT `invocation.env`. Add a parallel `TestCodexRunner` env assertion for `build_streaming`/`build_blocking_json`/`build_detached` once `CodexRunner` sets the env keys. [Agent 2 finding — specific anchor]
- `scripts/tests/test_cli_harness.py` — add a test asserting `cmd_skill` passes the merged env (with `LL_NON_INTERACTIVE`) to `subprocess.run`, covering the second propagation gap. [Agent 2 finding]

### Documentation
- `scripts/little_loops/loops/prompt-across-issues.yaml` description/usage examples — show `--auto` for interactive skills as defense-in-depth.

_Wiring pass added by `/ll:wire-issue` — if the fix introduces `LL_NON_INTERACTIVE`, these all describe the current `--dangerously-skip-permissions` automation signal and need updating:_
- `docs/reference/HOST_COMPATIBILITY.md:~207` — "Environment variables" table (lists `LL_HOST_CLI`, `LL_HOOK_HOST`, `LL_STATE_DIR`, `LL_HISTORY_DB`); add `LL_NON_INTERACTIVE` here if introduced. [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md:240,283` — directly describes the BUG-2110 symptom ("Missing `--dangerously-skip-permissions` or permission not granted" causing automation stalls); update to reflect the env-var detection mechanism. [Agent 2 finding]
- `docs/generalized-fsm-loop.md:1498,1503,1608` — "Security Model / Autonomous Execution" section describes `--dangerously-skip-permissions` as the automation signal; reflect the in-skill env-var detection. [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:~662` — references `DANGEROUSLY_SKIP_PERMISSIONS` as the auto-accept signal for design-token scaffolding. [Agent 2 finding]
- `docs/reference/COMMANDS.md:712,795` — `--auto` descriptions say "Also activates when `--dangerously-skip-permissions` is in effect"; update if the canonical signal becomes an env var. [Agent 2 finding]
- `docs/reference/API.md:~6633` — `HostCapabilities.permission_skip` field description mentions the flag; may need a note if `LL_NON_INTERACTIVE` becomes a distinct concept. [Agent 2 finding]
- `CHANGELOG.md` — add an entry for the BUG-2110 fix under a concrete release section (not `[Unreleased]`). [standard release prep]

_Wiring pass (2nd pass) added by `/ll:wire-issue`:_
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — describes `--auto` as the FSM non-interactive mechanism across multiple skills (`/ll:format-issue --auto ← non-interactive`, etc.); if `LL_NON_INTERACTIVE` becomes a documented signal, note it alongside `--auto` here. [Agent 2 finding]
- Upstream Claude Code doc mirrors (`docs/claude-code/cli-reference.md`, `settings.md`, `run-agent-teams.md`) reference `--dangerously-skip-permissions` but are read-only mirrors — **do NOT edit**. [Agent 2 finding — exclusion]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-06-13):_

**Material scope correction — consumer idiom is NOT mirrored across the 7 skills.**
A repo-wide grep shows the env-var branch `${DANGEROUSLY_SKIP_PERMISSIONS:-}` exists in **only one** skill — `skills/format-issue/SKILL.md:63` (plus `skills/configure/areas.md`, which is documentation about the var, not a consumer). The other six skills the issue lists check only the **flag-string** in their args, with no env-var branch:
- `skills/confidence-check/SKILL.md:43` — `[[ "$ARGUMENTS" == *"--dangerously-skip-permissions"* ]]` (bash)
- `skills/decide-issue/SKILL.md:61` — `if ARGUMENTS contains "--dangerously-skip-permissions"` (pseudocode)
- `skills/go-no-go/SKILL.md:57` — same pseudocode idiom
- `skills/audit-issue-conflicts/SKILL.md:42` — same pseudocode idiom
- `skills/audit-loop-run/SKILL.md:297`, `skills/debug-loop-run/SKILL.md:325` — gated inline at the issue-creation step ("Also activates when `--dangerously-skip-permissions` is in effect"), no `AUTO_MODE` bash block.

Consequence for the fix: setting `DANGEROUSLY_SKIP_PERMISSIONS=1` in the producer env would activate **only** `format-issue`. The other six string-match `$ARGUMENTS`/`$FLAGS`, which never carries the top-level `claude` flag (the bug's own Root Cause #1), so the producer fix alone leaves them dead. **The consumer work is "add a new env-var branch to 6 skills," not "confirm they already check it."** This tips the Proposed Solution toward introducing a dedicated `LL_NON_INTERACTIVE=1` and adding the branch uniformly, since 6 of 7 skills need a new branch regardless of which var name is chosen. (Three of the six are prose/pseudocode skills, so the consumer edit there is prose-level, not a bash conditional.)

**Producer anchors confirmed.** `ClaudeCodeRunner.build_streaming` adds `--dangerously-skip-permissions` to argv at `host_runner.py:245`; its env dict is seeded at `:260` (`{"CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1"}`) and returned at `:274` — no non-interactive signal. `build_blocking_json` (`:302`) and `build_detached` (`:323`) both pass `env={}`, confirming the producer fix must touch all three. `CodexRunner.build_streaming` seeds `env` at `:500`; its `build_blocking_json`/`build_detached` also pass `env={}` — cross-host parity work is real.

**Consumer-side delivery path confirmed.** `subprocess_utils.run_claude_command` merges the invocation env at `subprocess_utils.py:310` (`env.update(invocation.env)`) and spawns at `:314` (`subprocess.Popen`). Anything added to the producer's env dict survives to the skill subprocess here — this is the correct delivery seam.

**`DANGEROUSLY_SKIP_PERMISSIONS` (env var) has zero producers.** `grep -rn "DANGEROUSLY_SKIP_PERMISSIONS" scripts/little_loops/` returns nothing — the uppercase env var is never set. Only the lowercase `--dangerously-skip-permissions` CLI flag exists (host_runner argv; `issue_manager.py:134` log string; strip sites `fsm/handoff_handler.py:118`, `parallel/worker_pool.py:578`). This confirms the env-var branch is latent dead code with no wired producer.

## Implementation Steps

1. Add **both** `LL_NON_INTERACTIVE=1` and `DANGEROUSLY_SKIP_PERMISSIONS=1` to the `env` dict in `ClaudeCodeRunner.build_streaming` (decided hybrid — see Proposed Solution). Setting both gives the 6 existing `DANGEROUSLY_SKIP_PERMISSIONS` consumers a zero-regression window while `LL_NON_INTERACTIVE` becomes the clean long-term signal.
2. Propagate the signal to `build_blocking_json` / `build_detached` and the Codex/opencode runner subclasses for host parity.
3. Add the env-var branch to the consumer skills. **Research note:** only `format-issue` currently has an env-var branch; the other 6 (`confidence-check`, `decide-issue`, `go-no-go`, `audit-loop-run`, `debug-loop-run`, `audit-issue-conflicts`) check only the flag-string in their args and need a **new** env-var branch added — see "Codebase Research Findings" above. Prefer introducing `LL_NON_INTERACTIVE=1` and adding the branch uniformly across all 7.
4. Update `prompt-across-issues.yaml` docs/examples to show `--auto` as defense-in-depth.
5. Add a regression test asserting the env var reaches the spawned subprocess, then validate end-to-end with `ll-loop run prompt-across-issues "/ll:format-issue {issue_id}"`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **`fsm/handoff_handler.py:119` env-propagation gap (blocker).** `_spawn_continuation` calls `subprocess.Popen([invocation.binary, *args], ...)` with **no `env=` kwarg** — the detached continuation inherits bare `os.environ` and never sees `invocation.env`. The producer fix to `build_detached` does NOT reach handoff/spawn continuations unless this call site is updated to pass `env={**os.environ, **invocation.env}`. (Compare `subprocess_utils.py:310` and `worker_pool.py:585`, which DO merge it.)
7. **Expanded consumer surface (~15 files, not 7).** Beyond the 7 skills in the issue, add the env-var branch to: `skills/wire-issue` (`:61`), `skills/map-dependencies` (`:56`), `skills/issue-size-review` (`:51`). And account for the 5 `commands/*.md` files that already check `${DANGEROUSLY_SKIP_PERMISSIONS:-}` (`commit:17`, `refine-issue:58`, `normalize-issues:54`, `verify-issues:40`, `prioritize-issues:43` — env-only). If introducing `LL_NON_INTERACTIVE`, ALL ~15 consumers (including the 6 that already have a `DANGEROUSLY_SKIP_PERMISSIONS` branch) need the new branch; if reusing `DANGEROUSLY_SKIP_PERMISSIONS=1`, the 6 fire for free and only the argv-only/prose-only consumers need work.
8. **Verify read-only probe behavior.** `worker_pool.py:_detect_worktree_model_via_api` (`:578` strips the flag, `:585` merges env) will carry the new env key into the model-detection probe — confirm this is inert (the probe only asks for "ok").
9. **Producer regression test** in `test_host_runner.py` asserting all three `build_*` methods (Claude + Codex) include the new key in `invocation.env`; **integration test** in `test_subprocess_utils.py` (capture-Popen-env pattern). Update `test_wiring_init_and_configure.py:72` if `areas.md` is changed to reference `LL_NON_INTERACTIVE`.
10. **Docs sync** for the env-var table (`HOST_COMPATIBILITY.md`) and the troubleshooting/security-model sections if `LL_NON_INTERACTIVE` is introduced (see Documentation subsection).

_Wiring pass (2nd pass) added by `/ll:wire-issue`:_
11. **Update `test_handoff_handler.py:test_spawn_behavior`** — the existing test patches `subprocess.Popen` and checks detachment kwargs but never inspects `kwargs.get("env")`. Add: `assert "LL_NON_INTERACTIVE" in kwargs.get("env", {})` (and `DANGEROUSLY_SKIP_PERMISSIONS`). This is the only test gate on the `_spawn_continuation` env fix. Pattern to follow: `mock_popen.call_args[1]` inspection in `test_cli_loop_background.py`.
12. **Fix the second env gap in `cli/harness.py:cmd_skill`** — pass `env={**os.environ, **inv.env}` to its `subprocess.run` so skills exercised via `ll-harness skill` also receive the signal (same shape as step 6). Cover with a `test_cli_harness.py` env assertion. Without this, `ll-harness`-driven skill runs reproduce the silent-stall symptom even after the producer + handoff fixes land.
13. **Scope the producer fix to `ClaudeCodeRunner` + `CodexRunner` only** — `OpenCodeRunner`/`PiRunner` `build_*` raise `HostNotConfigured` and produce no env dict; do not add the keys there now. Confirm `fsm/evaluators.py`'s three `subprocess.run` judge calls need no env wiring (they are LLM-judge calls, not skill invocations).

## Impact

- **Blast radius:** every loop that invokes an interactive skill via `action_type: prompt` — not just `prompt-across-issues`. Affects ~7 skills that use the dead auto-detect idiom.
- **Severity:** silent partial completion. The loop reports success while doing nothing; operators have no signal that 70% of items were skipped. Observed 29% effective success rate (5/17) in a real run.

## Acceptance Criteria

- [ ] A skill spawned by an FSM `prompt` action can detect non-interactive context with no explicit `--auto` flag in the prompt string.
- [ ] `ll-loop run prompt-across-issues "/ll:format-issue {issue_id}"` mutates every open issue that has resolvable gaps (no `AskUserQuestion` stalls).
- [ ] The signal is delivered via subprocess env (verifiable in `build_streaming` / `subprocess_utils`), not via flag-string matching in `$FLAGS`.
- [ ] Regression test asserts the non-interactive env var is present in the env passed to the spawned subprocess for prompt actions.

## Related

- ENH-669 (done) — added the `--auto`/`--batch` flags and propagated the now-dead auto-detect idiom to issue-prep skills. This bug is the missing producer for that idiom.
- BUG-1416 (done) — `decide-issue --auto` asked interactive questions; same failure *class* (interactive stall) but that fix was skill-internal logic, not signal propagation.
- BUG-743 (done) — `format-issue --auto` flag-flow bug.

## Resolution

**Fix:** Producer-side: added `LL_NON_INTERACTIVE=1` and `DANGEROUSLY_SKIP_PERMISSIONS=1` to the `env` dict in `ClaudeCodeRunner.build_streaming`, `build_blocking_json`, and `build_detached` (and the `CodexRunner` equivalents). This delivers the non-interactive signal through `subprocess_utils.py`'s env merge path to every skill subprocess spawned by an FSM prompt action.

**Env-propagation gaps fixed:** `fsm/handoff_handler.py:_spawn_continuation` now passes `env={**os.environ, **invocation.env}` to Popen; `cli/harness.py:cmd_skill` now passes the same merged env to `subprocess.run`.

**Consumer updates:** Added `|| [[ -n "${LL_NON_INTERACTIVE:-}" ]]` to all ~15 consumer files (skills and commands) that previously checked only `$ARGUMENTS` for the flag string or only `$DANGEROUSLY_SKIP_PERMISSIONS`. Skills using pseudocode received equivalent prose updates.

**Tests:** 9 new regression tests across `test_host_runner.py`, `test_subprocess_utils.py`, `test_handoff_handler.py`, and `test_cli_harness.py` verify the signal is present in all producer and propagation paths.

## Session Log
- `/ll:ready-issue` - 2026-06-13T16:48:43 - `9286e810-de1a-4a38-b3ff-bc5c4788c0f4.jsonl`
- `/ll:confidence-check` - 2026-06-13T18:00:00Z - `2596bd2a-a18b-4b53-a9bb-a3c5dad97f3d.jsonl`
- `/ll:confidence-check` - 2026-06-13T17:00:00Z - `7fb59a12-9644-41c3-a147-bd8353f9ada3.jsonl`
- `/ll:wire-issue` - 2026-06-13T16:10:35 - `fbcdf0f9-fa34-4b38-af88-e6efce67bd84.jsonl`
- `/ll:wire-issue` - 2026-06-13T15:48:20 - `fab41d75-7c0d-4930-8162-57045cf9b2a6.jsonl`
- `/ll:refine-issue` - 2026-06-13T15:37:21 - `eab7ea17-4878-4958-ad7e-d5920532d639.jsonl`
- `/ll:format-issue` - 2026-06-13T15:31:36 - `97651ec7-8ea4-4229-9786-eab568f2e3f6.jsonl`
- `/ll:capture-issue` - 2026-06-13T15:27:51Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0dea2e2-549b-4557-ad9d-8f72fd723a64.jsonl`

---

## Status

**Current Status**: open
