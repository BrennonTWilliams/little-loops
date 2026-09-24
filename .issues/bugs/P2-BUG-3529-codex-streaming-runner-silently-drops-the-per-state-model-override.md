---
id: BUG-3529
type: BUG
title: Codex streaming runner silently drops the per-state model override
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T00:20:31Z'
labels:
- multi-host
- loops
confidence_score: 95
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

- `scripts/little_loops/host_runner.py` `CodexRunner.build_streaming` builds `codex exec [resume --last] <sandbox> --json --skip-git-repo-check [-C dir] <prompt>` and drops `model`.
- `CodexRunner.build_blocking_json` appends `--model <model>` when supplied.
- Result: loop `prompt` states on Codex ignore `state.model` and run `--model` with no warning (`slash_command` states never forward a model on any host, so they are out of scope); evaluators (blocking path) honor it. The drop was introduced with the original per-state model override (fc2fb7676) and was never re-verified against the CLI.

## Expected Behavior

`build_streaming` forwards a supplied `model` as `--model <model>` for both fresh and `resume --last` invocations, exactly as `build_blocking_json` does. `model=None` leaves argv unchanged. On the resume path, `--model` goes after `resume` (the `codex exec resume` subparser accepts `-m, --model`).

## Integration Map

- `scripts/little_loops/host_runner.py` — `CodexRunner.build_streaming`.
- `scripts/little_loops/fsm/executor.py` — resolves `state.model or self.run_model` for `prompt` actions only (`slash_command` passes `model=None` for every host); `fsm/runners.py` forwards it to `run_claude_command` → `build_streaming`. Dispatch tests must use a `prompt` state.
- Tests: `scripts/tests/test_host_runner.py` (builder argv); FSM/subprocess tests — `test_fsm_runners.py` / `test_subprocess_utils.py` (dispatch regression, with the host resolved to Codex). **Not** `test_host_runner_dispatch.py`: it covers `dispatch_anthropic_request` / `dispatch_batch_request` (Anthropic SDK and batch dispatch) and has no Codex coverage.
- Related: BUG-3536 — the same resume argv places `-C` and `--sandbox` after `resume`, which the installed parser rejects. Coordinate argv placement; the parser-level test there must cover `--model` too.

## Impact

- **Priority**: P2 — silent wrong-model selection, but only when a Codex loop pins a model.
- **Effort**: Small.
- **Risk**: Low — additive argv only when a model is supplied.
- **Unblocks**: ENH-3527's Codex streaming row (hint resolution can then be advertised as supported).

## Acceptance Criteria

- [ ] `CodexRunner.build_streaming(model="X")` argv contains `--model X` for fresh and resume invocations; `model=None` argv is byte-identical to today.
- [ ] Dispatch-level tests in the FSM/subprocess suites (Codex host), asserting on the spawned argv: (a) state `model:` set and run `--model` set → the state model wins; (b) only run `--model` set → it is forwarded; (c) neither set → no `--model` in argv (host default retained).
- [ ] Resume argv with `model` is accepted by the `codex exec resume` grammar (covered by BUG-3536's parser-level test; `--model` present alone is not sufficient evidence).
- [ ] Remove the stale `# codex does not support --model in streaming mode` comment. No runtime capability change is required: `HostCapabilities` / `RuntimeHostEntry` have no model-support field, and `HOST_COMPATIBILITY.md` does not list per-state model as unsupported for Codex streaming (checked 2026-09-23). If a model-support flag is wanted, that is ENH-3527's scope.

## Program Design

### Types

- No new types; `HostInvocation` is unchanged.

### Signatures

- `CodexRunner.build_streaming(self, *, prompt: str, resume: bool = False, model: str | None = None) -> HostInvocation` — (other keyword parameters unchanged) appends `--model <model>` after the sandbox args when `model` is set, for both fresh and `resume --last` argv.

### Call Path

- `FSMExecutor` → `CodexRunner.build_streaming` → `HostInvocation`
- Parity reference: `CodexRunner.build_blocking_json` already forwards `--model`.

## Verification Notes

Verdict: **VALID** (2026-09-23). `CodexRunner.build_streaming` still does `del model` (`host_runner.py:1198`); repro argv lacks `--model`; `build_blocking_json` forwards it (`:1272`). Installed `codex exec` and `codex exec resume` both list `-m, --model`. Resume argv is built at `:1224`. Proposal is additive and sound. `ll-verify-evidence` clean.

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
- `/ll:audit-issue-conflicts` - 2026-09-24T01:05:29 - `af4614fc-00c0-4ee9-995a-e89a43f1523c.jsonl`
- `/ll:confidence-check` - 2026-09-24T00:44:59 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:37:52 - `97f40d76-766f-412a-a4ef-794728276e4c.jsonl`
