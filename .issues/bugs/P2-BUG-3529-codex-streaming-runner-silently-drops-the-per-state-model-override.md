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
- Result: loop prompt/slash_command states on Codex ignore `state.model` and run `--model` with no warning; evaluators (blocking path) honor it. The drop was introduced with the original per-state model override (fc2fb7676) and was never re-verified against the CLI.

## Expected Behavior

`build_streaming` forwards a supplied `model` as `--model <model>` for both fresh and `resume --last` invocations, exactly as `build_blocking_json` does. `model=None` leaves argv unchanged.

## Integration Map

- `scripts/little_loops/host_runner.py` — `CodexRunner.build_streaming`.
- Tests: `scripts/tests/test_host_runner.py`, `test_host_runner_dispatch.py`, `conformance/test_host_conformance.py`.

## Impact

- **Priority**: P2 — silent wrong-model selection, but only when a Codex loop pins a model.
- **Effort**: Small.
- **Risk**: Low — additive argv only when a model is supplied.
- **Unblocks**: ENH-3527's Codex streaming row (hint resolution can then be advertised as supported).

## Acceptance Criteria

- [ ] `CodexRunner.build_streaming(model="X")` argv contains `--model X` for fresh and resume invocations; `model=None` argv is byte-identical to today.
- [ ] Runtime capability/conformance data no longer describe Codex streaming as model-unsupported (check `RUNTIME_HOST_CAPABILITIES` and `conformance/test_host_conformance.py`).
- [ ] Dispatch-level test: an FSM prompt state with `model:` under the Codex host reaches the runner argv (not just the builder).
- [ ] `docs/reference/HOST_COMPATIBILITY.md` no longer lists per-state model as unsupported for Codex streaming, if it does today.

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
- Two Acceptance Criteria are conditional ("if it does today"); grep `RUNTIME_HOST_CAPABILITIES` and `HOST_COMPATIBILITY.md` first to see whether they apply.
- `build_streaming` has ~13 call sites; existing argv-equality tests for Codex must keep passing with `model=None`.

## Session Log
- `/ll:confidence-check` - 2026-09-24T00:44:59 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:37:52 - `97f40d76-766f-412a-a4ef-794728276e4c.jsonl`
