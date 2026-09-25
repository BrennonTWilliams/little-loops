---
id: ENH-3547
type: ENH
title: Wire model hint resolution through loop dispatch and lifecycle
priority: P2
status: open
parent: EPIC-3563
epic: EPIC-3563
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:15Z'
labels:
- multi-host
- loops
blocked_by:
- ENH-3527
relates_to:
- ENH-3533
---

# ENH-3547: Wire model hint resolution through loop dispatch and lifecycle

## Summary

Wire `model_hint` resolution into every loop dispatch path: CLI actions, blocking evaluators, SDK/batch, and CLI downgrade. Preserve requested declarations through sub-loops, detach and resume, and add selection diagnostics to FSM events. This is piece 2 of ENH-3527's delivery split; ENH-3527 keeps piece 1 (declarations, resolver and config) and is the prerequisite.

## Current Behavior

- After ENH-3527, `model_hint` declarations parse and validate, but `FSMExecutor` fails fast with a not-yet-supported error before dispatch.
- CLI actions use `state.model or self.run_model` (`executor.py:2658`); evaluators use `state.model or self.fsm.llm.model` (`executor.py:3174,3221`); SDK/batch use `state.model or self.run_model or self.fsm.llm.model` (`executor.py:3570`).
- Evaluators have no SDK path: `fsm/evaluators.py` always dispatches through `resolve_host().build_blocking_json`, whatever the state's `request_path`.
- `FakeHostRunner.build_streaming` and `build_blocking_json` accept `model` but drop it from argv (`host_runner.py` ~L2095–2130), so no fake-host test can assert a resolved selection today.
- `ll-loop resume` has no `--model`/`--llm-model` flags, and loop persistence saves neither the run-level `--model` nor the `--llm-model` override. Detach forwards both (`cli/loop/runner.py:223-231`). Resume re-reads the loop YAML, so YAML declarations (including hints) survive, but run-level literal overrides are lost. This behavior predates this issue.
- Prompt compression sizes against `model=self.run_model` (`executor.py:2523`), not the state's effective model. This already happens with a literal `state.model`.

## Expected Behavior

Everything below is specified in ENH-3527 (Design → Declaration and precedence, Resolve against the effective backend, Supported artifact/host matrix, Lifecycle and model identity, Call Path). ENH-3527 remains the authoritative design; this issue owns delivering it:

- Resolve after `FSMExecutor._resolve_request_path`. SDK/batch always resolves against `anthropic-api`; a downgrade to CLI re-resolves the original declaration for that runner.
- Evaluator hints are resolved in `FSMExecutor._evaluate` against the CLI host `resolve_host()` returns (never `anthropic-api`, even on an `sdk`/`batch` state) and passed down as `model: str`; no config is threaded into `evaluators.py`.
- `FakeHostRunner` (and `FakeMinimalHostRunner`) append `--model <model>` to argv when `model` is set, so fake-host dispatch tests and the portability proof can assert the resolved sentinel (`fake-coding`, `fake-burst`, …; ENH-3527 built-in mapping). Check that `ll-fake-host` accepts or ignores the flag.
- Each dispatch adds `model_requested`, `model_resolved` and `model_backend` to its event payload and the run header. No DB columns; observed model identity stays in `usage_events.model` (ENH-3528/ENH-3538, done) and is never overwritten with a requested/resolved selection.
- **Resume (decided 2026-09-25).** Hints live only in the loop YAML, because there are no run-level hint flags. Resume re-reads the YAML, so resume preserves hint declarations without new persistence. Losing run-level `--model`/`--llm-model` on resume is older behavior for literals and **out of scope**. One consequence must be visible, not silent: a run started with `--llm-model X`, which cleared a YAML `llm.model_hint`, resumes with that hint active again. The resume header/event must show the new selection.
- **Compression.** Keep `compress_action_text(model=self.run_model)` unchanged here (out of scope, older behavior). Add a code comment that the window is sized against the run model, not the hint-resolved state model.

## Scope Boundaries

- **In scope**: dispatch wiring on every loop path, CLI downgrade re-resolution, lifecycle preservation, event/header diagnostics, portability proof, removing ENH-3527's not-yet-supported guard.
- **Out of scope**: validate warnings and docs (ENH-3548); skill/agent frontmatter (ENH-3533); persisting run-level `--model`/`--llm-model` across resume (older literal behavior); making compression hint-aware.

## Program Design

### Types

- Uses ENH-3527's model declaration and resolved-selection types; no new types.

### Signatures

- `resolve_model_hint(hint, *, backend, overrides=None) -> str` — from ENH-3527 (no `operation` parameter, decided 2026-09-24), called at each dispatch seam.
- Evaluator functions keep `model: str`.

### Call Path

- `FSMExecutor._resolve_request_path` → `resolve_model_hint` → `build_anthropic_request` (SDK/batch)
- `FSMExecutor._resolve_request_path` → `resolve_model_hint` → `ClaudeCodeRunner.build_streaming` / `CodexRunner.build_streaming` (CLI actions)
- `FSMExecutor._evaluate` → `resolve_model_hint` (CLI backend only) → `evaluate_llm_structured` → `build_blocking_json`

## Integration Map

- `scripts/little_loops/fsm/{executor,evaluators,runners,persistence}.py`, `subprocess_utils.py`, `cli/loop/{run,lifecycle,runner,header,info}.py`.
- `scripts/little_loops/host_runner.py` — `FakeHostRunner` / `FakeMinimalHostRunner` forward `--model`; `scripts/little_loops/fake_host` if the executable must accept the flag.
- Tests: `test_fsm_executor.py`, `test_fsm_evaluators.py`, `test_fsm_runners.py`, `test_ll_loop_execution.py`, `test_host_runner_dispatch.py`, `test_fake_host.py`.

## Impact

- **Priority**: P2.
- **Effort**: Medium to high — ~10 source files, six test files, and a persistence-format check. If lifecycle proves large, split sub-loop/detach/resume/persistence from dispatch wiring.
- **Risk**: Medium — a precedence or backend mismatch silently selects the wrong model.

## Acceptance Criteria

Carried over from ENH-3527's original criteria (stated inline; ENH-3527's numbering has since changed):

- [ ] Tests cover every precedence row; no-hint behavior and literal CLI argv are unchanged.
- [ ] CLI action, blocking evaluator, SDK and batch paths share declaration semantics; a foreign configured CLI host never supplies an Anthropic request model; downgrade re-resolves.
- [ ] An evaluator hint on a `request_path: sdk` state resolves against the CLI host, not `anthropic-api`.
- [ ] Every advertised host/operation combination has a dispatch-level argv test, including Codex streaming and a config-only `orchestration.model_hints.codex` mapping reaching argv (moved from ENH-3527); opencode/pi and missing/disabled mappings error explicitly.
- [ ] `FakeHostRunner` forwards `--model`; a fake-host dispatch test asserts the resolved sentinel in argv.
- [ ] Sub-loop/detach/resume preserve requested declarations (resume via YAML re-read; run-level literal flags are out of scope); event payloads carry the three selection fields (`model_requested`, `model_resolved`, `model_backend`).
- [ ] Sub-loops follow ENH-3527's decided semantics: run `--model` inherits into children; a parent state's declaration does not propagate; children resolve against their own `llm`.
- [ ] A state with both a prompt action and an LLM evaluator resolves its single declaration separately for each and may yield two different model strings.
- [ ] `--llm-model` replaces the `llm` declaration and clears an inherited hint.
- [ ] Resuming under a changed mapping or host resolves afresh and makes the new selection visible (event/header), including a resume that drops an earlier `--llm-model` override and reactivates a YAML `llm.model_hint`.
- [ ] Portability proof: a fixture loop with `coding`/`burst` states runs unedited under the fake host (argv shows `fake-coding`/`fake-burst`), `claude-code` (argv shows `sonnet`/`haiku`), and `anthropic-api` (mocked SDK client receives `MODEL_ALIASES` IDs).

## Status

**Open** | Created: 2026-09-24 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue covers runtime dispatch, CLI downgrade re-resolution, and lifecycle wiring only; the resolver and config slice is ENH-3527 and validate-time warnings/docs are ENH-3548. ENH-3527 dropped the `operation` parameter (2026-09-24), so there is no `model_operation` event field.

## Verification Notes

Pre-implementation review 2026-09-25 made these changes:

- Added fake-host `--model` forwarding. It is needed for the portability proof and depends on ENH-3527's new `fake`/`fake-minimal` mapping.
- Evaluators resolve against the CLI host only.
- Moved the config-only Codex argv criterion here from ENH-3527.
- Decided resume scope: hint declarations survive through the YAML re-read, and run-level literal flags are out of scope.
- Recorded the compression sizing gap as older, out-of-scope behavior.
- Updated observed-identity wording now that ENH-3528/ENH-3538 are done.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:56 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
