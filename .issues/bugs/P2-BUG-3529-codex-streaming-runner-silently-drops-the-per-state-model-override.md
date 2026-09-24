---
id: BUG-3529
type: BUG
title: Codex streaming runner silently drops the per-state model override
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T00:20:31Z'
completed_at: '2026-09-24T02:40:57Z'
labels:
- multi-host
- loops
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
relates_to:
- BUG-3536
depends_on:
- BUG-3536
---

# BUG-3529: Codex streaming runner silently drops the per-state model override

## Summary

`CodexRunner.build_streaming` discards its `model` argument (`del model  # codex does not support --model in streaming mode`), so a per-state `model:` or a run `--model` on a loop running under the Codex host is silently ignored and the host default model runs instead. The premise is stale: the installed `codex exec` and `codex exec resume` (codex-cli 0.152.1) both accept `-m, --model <MODEL>`, and the same runner's `build_blocking_json` already forwards `--model`.

## Steps to Reproduce

1. `python -c "from little_loops.host_runner import CodexRunner; print(CodexRunner().build_streaming(prompt='p', model='x').args)"`
2. Observe the argv contains no `--model x` (compare `build_blocking_json(prompt='p', model='x')`, which does).
3. End to end: with `LL_HOST_CLI=codex`, run a loop whose prompt state declares `model: <id>`; the Codex session runs its default model.

## Current Behavior

- `scripts/little_loops/host_runner.py` `CodexRunner.build_streaming` drops `model` on both fresh and resume paths. BUG-3536 is done: resume now places parent `--sandbox` and `-C` options before `resume --last`.
- `CodexRunner.build_blocking_json` appends `--model <model>` when supplied.
- Result: loop states dispatched in prompt mode on Codex ignore `state.model` and run `--model` with no warning; the blocking builder honors it. `FSMExecutor._action_mode` maps both explicit `prompt` and `slash_command` states, plus inferred slash-prefixed actions, to prompt mode, so all are affected. The drop was introduced with the original per-state model override (fc2fb7676).

## Expected Behavior

`build_streaming` forwards a non-empty `model` as `--model <model>` for both fresh and `resume --last` invocations, exactly as `build_blocking_json` does. `model=None` or `model=""` leaves argv unchanged relative to the post-BUG-3536 baseline. On the resume path, `--model` goes after `resume` (the `codex exec resume` subparser accepts `-m, --model`).

## Proposed Solution

Remove `del model` and its stale comment from `CodexRunner.build_streaming`. After emitting the common streaming flags, append `["--model", model]` when `model` is truthy, before the final prompt argument. Preserve BUG-3536's parent-option placement, environment construction, persona injection, and sandbox selection. Forward the model string unchanged; model-hint resolution belongs to ENH-3527.

## Integration Map

- `scripts/little_loops/host_runner.py` — `CodexRunner.build_streaming`.
- `scripts/little_loops/fsm/executor.py` — `_action_mode` normalizes `prompt`, `slash_command`, and inferred slash-prefixed actions to prompt mode; `_run_action` then resolves `state.model or self.run_model`. `ActionRunner.run` in `fsm/runners.py` forwards it to `subprocess_utils.run_claude_command` → `build_streaming`. No production changes are needed in these callers.
- Tests: `scripts/tests/test_host_runner.py` (builder argv); `scripts/tests/test_ll_loop_execution.py` already contains `test_state_model_overrides_run_model` and `test_run_model_used_as_fallback_for_host_action`, but these stop at a capturing action runner. Extend coverage through the real `ActionRunner` and Codex builder to mocked `Popen`. `scripts/tests/test_fsm_runners.py` and `scripts/tests/test_subprocess_utils.py` provide forwarding/spawn mock patterns. Explicitly override the subprocess suite's autouse `_patch_resolve_host` fixture, which selects Claude. **Not** `test_host_runner_dispatch.py`: it tests Anthropic SDK/batch dispatch.
- Related prerequisite: BUG-3536 is `done` and landed on `main` in commit `9b16bb1c5`. Its builder matrix and subprocess resume test exist, but its Resolution explicitly says the parser test was omitted. This issue owns model-bearing parser coverage; do not assume that coverage already exists.
- Parser test location: `scripts/tests/conformance/test_host_conformance.py`, using the existing `live_conformance` fixture with `@pytest.mark.conformance` and `LL_HOST_CONFORMANCE_LIVE=1`. Ordinary unit tests prohibit real host CLI spawns. Keep unconditional argv tests in `test_host_runner.py`; do not weaken the suite-wide spawn guard.
- Documentation/configuration: no public interface or configuration changes required.

## Impact

- **Priority**: P2 — silent wrong-model selection, but only when a Codex loop pins a model.
- **Effort**: Small.
- **Risk**: Low — additive argv only when a model is supplied.
- **Unblocks**: ENH-3527's Codex streaming row (hint resolution can then be advertised as supported).

## Acceptance Criteria

- [x] `CodexRunner.build_streaming(model="X")` emits exactly one `--model X` pair before the final unchanged prompt for fresh and resume invocations, and after `resume` when present. Cover the existing directory/sandbox matrix with a model supplied; parent `-C`/`--sandbox` placement remains correct. `model=None` and `model=""` preserve the post-BUG-3536 argv and invocation environment.
- [x] Dispatch-level tests use the real executor → action runner → subprocess helper → Codex builder and mock only process launch/stream plumbing, asserting on spawned argv: (a) state and run models set → state wins; (b) only state model set → forwarded; (c) only run model set → forwarded; (d) neither set → no `--model` (host default retained even if `fsm.llm.model` is populated). Exercise explicit `prompt`, explicit `slash_command`, and inferred slash-prefixed actions. Force Codex host selection; a capturing action runner alone is insufficient.
- [x] Add a focused opt-in conformance parser test for complete generated fresh/resume argv with a supplied model, including a directory containing spaces and explicit sandbox mode. Invoke `HostInvocation.binary` + `.args` + trailing `--help`, capture output, bound the timeout, and report the CLI version on failure. Use `live_conformance`; skip when opt-in is disabled or the CLI is absent. This proves parser acceptance without launching a model session, not successful model availability or session selection. BUG-3536 did not add this test.
- [x] Remove the stale `# codex does not support --model in streaming mode` comment. No runtime capability change is required: `HostCapabilities` / `RuntimeHostEntry` have no model-support field, and `HOST_COMPATIBILITY.md` does not list per-state model as unsupported for Codex streaming (checked 2026-09-23). If a model-support flag is wanted, that is ENH-3527's scope.

## Program Design

### Types

- No new types; `HostInvocation` is unchanged.

### Signatures

- `CodexRunner.build_streaming(self, *, prompt: str, resume: bool = False, model: str | None = None) -> HostInvocation` — (other keyword parameters unchanged) appends `--model <model>` among the common streaming options when `model` is truthy, after `resume` when present and before the prompt.

### Call Path

- `FSMExecutor._action_mode` → `FSMExecutor._run_action` → `ActionRunner.run` → `subprocess_utils.run_claude_command` → `resolve_host().build_streaming` (`CodexRunner`) → `HostInvocation` → `subprocess.Popen`
- Parity reference: `CodexRunner.build_blocking_json` already forwards `--model`.

## Verification Notes

Reviewed on `main` at `9b16bb1c5` in the little-loops repository (2026-09-23 local date), with installed `codex-cli 0.152.1`. `CodexRunner.build_streaming` still discards `model`; fresh and resume builder repros omit the flag, while `build_blocking_json` includes it. BUG-3536 is done, so the structured dependency is satisfied.

Manually inserted the proposed `--model test-model` pair before the prompt in generated argv and appended `--help`: all 20 combinations of fresh/resume × five sandbox settings × absent/spaced working directory exited 0. No model session was launched, and this is parser evidence only. Corrected the previous false exclusion of `slash_command` states using `FSMExecutor._action_mode`, and replaced reliance on a nonexistent BUG-3536 parser test with an explicit conformance test plan. No active required decision rules were found.

## Resolution

Fixed 2026-09-23: `CodexRunner.build_streaming` now forwards a truthy `model` as `--model <model>` (fresh and `resume --last`), removing the stale `del model`. Added builder matrix tests (`test_host_runner.py`), executor→runner→Codex-builder dispatch tests (`test_codex_model_dispatch.py`), and an opt-in parser conformance test.

## Status

**Open** | Created: 2026-09-24 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-23_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- ~~Two Acceptance Criteria are conditional ("if it does today")~~ — resolved 2026-09-23: neither the runtime registry nor `HOST_COMPATIBILITY.md` records Codex streaming model support; replaced with concrete criteria.
- `build_streaming` has ~13 call sites; existing argv-equality tests for Codex must keep passing with `model=None`.

## Session Log
- `/ll:manage-issue` - 2026-09-24T02:40:57 - `6b600827-2d1e-4489-ba3c-1ae1bea5658f.jsonl`
- `/ll:ready-issue` - 2026-09-24T02:30:23 - `b0b0087c-8154-4a9a-a6dd-f91b33923334.jsonl`
- `/ll:confidence-check` - 2026-09-24T02:26:22 - `c2618a05-1e63-43c7-a628-77cbaa4fb454.jsonl`
- `/ll:ready-issue` - 2026-09-24T02:24:53 - `81ea4c5e-a825-4566-9e56-fd0ad97eab82.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T01:05:29 - `af4614fc-00c0-4ee9-995a-e89a43f1523c.jsonl`
- `/ll:confidence-check` - 2026-09-24T00:44:59 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:37:52 - `97f40d76-766f-412a-a4ef-794728276e4c.jsonl`
