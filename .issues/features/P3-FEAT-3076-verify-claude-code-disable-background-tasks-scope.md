---
id: FEAT-3076
title: Verify actual scope of CLAUDE_CODE_DISABLE_BACKGROUND_TASKS via a real host
  invocation
type: FEAT
priority: P3
status: done
completed_at: '2026-08-06T06:45:52Z'
testable: true
parent: FEAT-3060
labels:
- automation
- headless
- host-runner
confidence_score: 100
outcome_confidence: 85
score_complexity: 22
score_test_coverage: 15
score_ambiguity: 24
score_change_surface: 24
---

# FEAT-3076: Verify actual scope of CLAUDE_CODE_DISABLE_BACKGROUND_TASKS via a real host invocation

## Summary

Determine, empirically, what `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` actually
disables when set in a real `claude` child process: only the `Bash`
`run_in_background` parameter, or also the synchronous-agent paths
`ll-parallel` relies on (subagent tool backgrounding). The vendored docs
(`docs/claude-code/settings.md:772`) describe the flag as disabling "all
background task functionality, including the `run_in_background` parameter on
Bash and subagent tools, auto-backgrounding" — but no test in this codebase
exercises a real subprocess to confirm this, and every existing test
(`test_fsm*.py`, `test_issue_manager.py`, `test_subprocess_utils.py`) mocks
`Popen`/`resolve_host`.

## Parent Issue

Decomposed from FEAT-3060: Hard-disable background tasks in headless
automation instead of instructing against them. Resolves that issue's
Acceptance Criterion 6 and its "open question worth answering before
implementing."

## Motivation

FEAT-3077 (carve-out decision) and FEAT-3078 (main implementation) both need
this answer before they can proceed correctly:

- If the flag also disables subagent-tool backgrounding, it would break the
  two known carve-outs (`manage-issue` smoke tests, `go-no-go`'s concurrent
  agent launch) more broadly than a Bash-only reading suggests, changing the
  carve-out decision in FEAT-3077.
- The implementation in FEAT-3078 should not ship AC1/AC2 as "done" against a
  reading of the docs alone when a five-minute manual check can confirm it
  directly.

## Current Behavior

`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`'s scope is only known from the vendored
docs (`docs/claude-code/settings.md:772`), which assert it covers both `Bash`
`run_in_background` and subagent-tool backgrounding. No test or manual
verification in this codebase has confirmed that description against a real
`claude` child process — every existing test that touches host invocation
(`test_fsm*.py`, `test_issue_manager.py`, `test_subprocess_utils.py`) mocks
`Popen`/`resolve_host`, so nothing exercises the flag's real effect.

## Expected Behavior

A documented, evidence-backed answer to: does
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` in a `claude` child process's
environment reject only `Bash run_in_background: true` calls, or does it also
prevent the agent from launching background subagents (the mechanism
`ll-parallel` depends on)?

## Impact

FEAT-3077 (carve-out decision) and FEAT-3078 (main implementation) are both
blocked on trusting an unverified docs claim. If the flag's real scope is
broader than a Bash-only reading suggests, the known carve-outs
(`manage-issue`'s smoke tests, `go-no-go`'s concurrent agent launch) would
need to be handled differently in FEAT-3077, and FEAT-3078 risks shipping its
acceptance criteria against an incorrect assumption.

## Status

Open — investigation not yet performed. No blocking code changes exist for
this repo; the flag is not currently set, read, or referenced anywhere in
`scripts/little_loops/`.

## Proposed Solution

Manually invoke the `claude` CLI (or a minimal harness script) with
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` set in its environment, and:

1. Attempt a `Bash` call with `run_in_background: true` — confirm it is
   rejected or behaves differently than without the flag.
2. Attempt to launch a subagent expected to run in the background (mirroring
   how `ll-parallel` invokes concurrent agents) — confirm whether it is also
   rejected or unaffected.
3. Record the findings (which calls are blocked, any error message/behavior
   observed) in this issue's Session Log / a Resolution note, in a form
   FEAT-3077 and FEAT-3078 can cite directly (e.g. "Bash `run_in_background`
   only; subagent launches unaffected" or the reverse).

This is a manual, out-of-suite verification step — no new automated test
harness exists for real subprocess execution, and building one is out of
scope here (this issue is the investigation, not new test infrastructure).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- Recording convention: issues of this shape (proving a real external CLI's behavior, no shipped code) record findings directly in the issue body under a terminal `## Findings` section, one subsection per research question opened with a ✓/✗ verdict — evidence: `.issues/features/P4-FEAT-2179-gemini-cli-research-spike-binary-surface-hooks-plugins.md`.
- Citable-evidence convention: a completed determination is recorded with a bolded verdict line followed by `Key evidence:` file:line-anchored bullets — evidence: this issue's own parent, FEAT-3060, `### Decision Rationale` section.
- `/ll:spike` explicitly routes external-API/CLI-behavior questions like this one away from itself to `/ll:explore-api` + the Learning Test Registry (`skills/spike/SKILL.md`: "Not for: unproven *external* API assumptions"). This issue's manual-check framing (no automated harness) matches that routing rather than the `/ll:spike` pytest-package convention, which is reserved for unproven *internal* mechanisms.

## Use Case

As the implementer of FEAT-3077 (carve-out decision) or FEAT-3078 (config
threading), I need a citable, verified answer for whether
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` blocks subagent-tool backgrounding in
addition to `Bash run_in_background`, so I can scope the carve-out policy and
implementation correctly instead of inferring it from unverified vendored
docs.

## Acceptance Criteria

1. The flag's actual scope is confirmed via a real host invocation (not
   inferred from documentation alone).
2. The finding — which call paths are blocked and which are not — is recorded
   in this issue in a form other issues can cite as evidence.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Files to Modify
- None — this issue is investigation-only. No implementation code changes are in scope (confirmed by analyzer: `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` is not set, read, or referenced anywhere in `scripts/little_loops/` today).

### Relevant Entry Points (for the manual verification invocation)
- `scripts/little_loops/host_runner.py:297-369` — `ClaudeCodeRunner.build_streaming()`, the factory that builds the child `claude` process's env dict (`:345-353`); has no `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` key and no parameter to thread one through yet.
- `scripts/little_loops/subprocess_utils.py:412-413` — the chokepoint where `HostInvocation.env` is merged into `os.environ.copy()` immediately before `subprocess.Popen`; a manual verification script would set the flag here or in the shell environment before invoking `claude` directly.
- `scripts/little_loops/subprocess_utils.py:320` — `run_claude_command()`, the function that actually drives the child process end-to-end; the natural call site to observe tool-call behavior via `--output-format stream-json`.

### Distinct Mechanisms the Verification Must Distinguish
- `Bash`/`Agent`-tool `run_in_background: true` — an in-turn tool-call parameter, used from skill prompt text: `skills/go-no-go/SKILL.md:174` (Agent-tool background launch of adversarial agents), `:274` (wait for completion), `:278` (foreground judge agent, explicitly *not* backgrounded); `skills/manage-issue/SKILL.md:367` (Bash-tool background server-start carve-out) and `:376-400` (prohibits `run_in_background`/trailing `&` for the final blocking test suite).
- `ll-parallel`'s actual concurrency — separate OS-level `claude` subprocesses spawned by Python thread workers, structurally unrelated to any in-turn `Agent`-tool call: `scripts/little_loops/parallel/orchestrator.py:73` (`ParallelOrchestrator`), `:209` (`run()`), `:927/:1002/:1041` (dispatch to pool); `scripts/little_loops/parallel/worker_pool.py:128` (`WorkerPool`), `:177` (`ThreadPoolExecutor`), `:885-924` (`_run_claude_command` → `subprocess_utils.run_claude_command`).
- These are not the same mechanism: `go-no-go`'s carve-out is the `Agent`-tool `run_in_background: true` parameter inside one `claude -p` turn; `ll-parallel`'s parallelism is N independently-spawned `claude -p` processes. Whatever the flag gates inside a single process's tool surface applies (or doesn't) per-process to each `ll-parallel` worker — it has no structural relationship to `WorkerPool`'s own Python-level thread fan-out.

### Conventions in Force
- Investigation-only issues of this shape (proving a real external CLI's behavior, no shipped code) record findings directly in the issue body under a terminal `## Findings` section, one subsection per research question opened with a ✓/✗ verdict — evidence: `.issues/features/P4-FEAT-2179-gemini-cli-research-spike-binary-surface-hooks-plugins.md`.
- The standing convention for empirically proving external-CLI/API behavior with a citable, falsifiable-claim record is the Learning Test Registry (`/ll:explore-api`, `.ll/learning-tests/<slug>.md` + raw capture) — evidence: `skills/explore-api/SKILL.md`, `docs/guides/LEARNING_TESTS_GUIDE.md:296` ("Cite the record... reference the record path in a comment near the call site"). `/ll:spike` explicitly routes external-API/CLI-behavior questions away from itself to this convention — evidence: `skills/spike/SKILL.md` ("Not for: unproven *external* API assumptions... use `/ll:explore-api`").
- A completed determination is recorded with a bolded verdict line followed by `Key evidence:` file:line-anchored bullets — evidence: this issue's own parent, `.issues/features/P3-FEAT-3060-hard-disable-background-tasks-in-headless-automation.md`, `### Decision Rationale` section.

### Tests
- No test exercises this behavior and none is in scope: `scripts/tests/test_host_runner.py`, `test_subprocess_utils.py`, `test_fsm*.py`, `test_issue_manager.py` all mock `Popen`/`resolve_host` (per `conftest.py` fixtures). Building automated coverage is explicitly out of scope per this issue's Proposed Solution.

### Documentation
- `docs/claude-code/settings.md:772` — sole existing (vendored, unverified) description of the flag's scope, asserting it covers both `Bash` and subagent-tool `run_in_background`.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Types
- N/A — this issue produces no new data shape. It is a manual, out-of-suite verification step; no implementation code ships.

### Signatures
- `ClaudeCodeRunner.build_streaming(prompt, automation_profile=None)` — existing factory (`scripts/little_loops/host_runner.py:297`) that returns a `HostInvocation` for a `claude` subprocess; a manual verification script sets `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` in the returned `env` dict, since no parameter exists today to thread the flag through `build_streaming()` itself.
- `run_claude_command(invocation)` — existing driver (`scripts/little_loops/subprocess_utils.py:320`) that merges `invocation.env` into `os.environ` immediately before `subprocess.Popen`; the natural call site for observing the child's tool-call stream (`--output-format stream-json`) during manual verification.

### Call Path
`(manual script)` -> `ClaudeCodeRunner.build_streaming()` [env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] = "1" set manually] -> `run_claude_command()` -> `subprocess.Popen` -> real `claude` child process -> observe: (a) `Bash run_in_background: true` call outcome, (b) `Agent`-tool `run_in_background: true` subagent-launch outcome

### Decision Rules
N/A — no new decision logic. This issue records an empirical finding, not a gate/threshold/keyword rule.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/claude-code/settings.md:772` | The only existing description of the flag's scope |
| `skills/manage-issue/SKILL.md:376-400` | Carve-out that depends on this answer (see FEAT-3077) |
| `skills/go-no-go/SKILL.md:174,274,278` | Second carve-out that depends on this answer (see FEAT-3077) |


## Findings

_Added by `/ll:manage-issue` — 2026-08-06 — verified via real `claude -p` child-process invocations (`claude --version` 2.1.219), comparing behavior with and without `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` in the child's environment. Full raw stream-json transcripts and methodology: `postmortems/feat-3076-verify/README.md`._

### Does the flag disable `Bash` `run_in_background`? ✓ Confirmed

**Bash `run_in_background` is disabled when the flag is set.** With the flag
unset, a `Bash` call with `run_in_background: true` launches asynchronously
and returns immediately ("Command running in background with ID: ..."). With
the flag set, the model's own `thinking` block states intent to pass
`run_in_background: true`, but the emitted tool call omits the parameter
entirely, and the command executes synchronously (blocked for the full
`sleep 3` duration, returning the command's stdout directly). Key evidence:
`postmortems/feat-3076-verify/bash_control.jsonl` vs.
`postmortems/feat-3076-verify/bash_disabled.jsonl`.

### Does the flag also disable subagent-tool (`Agent`) background launches? ✓ Confirmed — yes, broader than Bash-only

**Agent-tool subagent backgrounding is also disabled, not just Bash.** With
the flag unset, an `Agent` call with `run_in_background: true` returns
"Async agent launched successfully... The agent is working in the
background," and the model's own turn text confirms genuine async behavior
(launch now, notified on completion in a later turn). With the flag set, the
same call's `run_in_background` value is coerced to a **string** (`"true"`
vs. boolean `true` in the control — a schema-handling difference under the
flag) and the tool result returns the subagent's full final response and
`agentId` synchronously, in the same turn, with none of the
launched-in-background/notify-on-completion language from the control. The
subagent still runs, but the async launch/notify mechanism is unavailable.
Key evidence: `postmortems/feat-3076-verify/agent_control.jsonl` vs.
`postmortems/feat-3076-verify/agent_disabled.jsonl`.

**Bottom line for FEAT-3077/FEAT-3078**: the vendored docs description
(`docs/claude-code/settings.md:772`) is accurate — the flag's scope covers
both mechanisms. Both known carve-outs (`manage-issue`'s smoke-test
Bash-background step, `go-no-go`'s concurrent `Agent`-tool background launch)
would be affected by enabling this flag, not just Bash-specific steps. This
must factor into FEAT-3077's carve-out policy: a carve-out is needed for both
mechanisms if either is required to stay functional, not just for Bash.

## Session Log
- `/ll:manage-issue` - 2026-08-06T06:45:38 - `5bcd5d84-ac9a-4ec4-b551-41ee4656d380.jsonl`
- `/ll:ready-issue` - 2026-08-06T06:35:24 - `5fdbc0dc-95be-4333-a38d-9c11253fc947.jsonl`
- `/ll:refine-issue` - 2026-08-06T05:41:13 - `5d36237a-64c0-48ea-973e-fbf5147c9f9f.jsonl`
- `/ll:issue-size-review` - 2026-08-06T05:11:26 - `c21cd57e-cb03-41ae-b233-cd39e3e2a29a.jsonl`
