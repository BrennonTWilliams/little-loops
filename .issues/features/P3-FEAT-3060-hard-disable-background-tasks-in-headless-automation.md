---
id: FEAT-3060
title: Hard-disable background tasks in headless automation instead of instructing
  against them
type: FEAT
priority: P3
status: open
testable: true
discovered_by: capture-issue
discovered_date: 2026-08-05
captured_at: '2026-08-05T16:06:39Z'
relates_to:
- BUG-3058
- BUG-2408
- BUG-3026
- BUG-2729
- BUG-2730
labels:
- automation
- headless
- host-runner
---

# FEAT-3060: Hard-disable background tasks in headless automation instead of instructing against them

## Summary

Every existing defense against "agent backgrounds a task, ends its turn, work is
lost" is an *instruction*. `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` is a hard
lever documented in the vendored settings reference but referenced nowhere in
this codebase. Setting it for automation invocations would make the failure
structurally impossible rather than merely discouraged.

## Motivation

Three independent instruction-based mitigations already exist, and the failure
still recurs:

- `skills/manage-issue/SKILL.md:376-400` forbids backgrounding the final suite.
  BUG-3026 measured the agent violating it in 3 of 10 sprint runs.
- BUG-2730's stay-in-turn contract, now reaching `ll-auto` via BUG-3058.
- BUG-3058's finalize re-drive, which recovers after the fact rather than
  preventing.

Each narrows the window; none closes it. An LLM instructed not to background a
task can still background a task. The env var cannot be disregarded.

## Current Behavior

`grep -rn "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS" scripts/` returns nothing. The
only occurrence in the repo is `docs/claude-code/settings.md:772`, which
describes it as disabling "all background task functionality, including the
`run_in_background` parameter on Bash and subagent tools, auto-backgrounding".

`host_runner.py` builds the child environment and already injects
`LL_AUTOMATION` / `LL_AUTOMATION_PROFILE` when `automation_profile` is set
(`host_runner.py:351-353`), so the injection point exists and is exercised.

## Expected Behavior

Automation invocations that opt into an automation profile also disable
background tasks in the child, unless explicitly overridden. An agent in that
child cannot background its test suite, so it cannot end its turn waiting on one.

## Proposed Solution

Inject `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` alongside the existing
`LL_AUTOMATION` pair in the host runner's env-building blocks, gated on a new
config flag so the behavior can be turned off per project.

**The tradeoff that makes this a FEAT rather than a bug fix**: the same
`manage-issue` skill that forbids backgrounding the final suite explicitly
*permits* backgrounding for smoke tests — `SKILL.md:394-396` carves out "for
long-running processes (servers), start in background, wait briefly for startup,
then terminate." A blanket disable breaks that carve-out. Resolving this
requires deciding which of the two matters more in automation, or finding a
narrower mechanism than the all-or-nothing env var.

Open question worth answering before implementing: does the flag disable the
`Bash` `run_in_background` parameter only, or also the synchronous-agent paths
`ll-parallel` relies on? The documentation says "and subagent tools", which may
be broader than intended here.

## Use Case

An operator runs `ll-auto` overnight across a sprint of eight issues and is not
present to observe it. On issue five, the implement agent hits a slow test suite,
backgrounds it to keep working, and ends its turn narrating that it will wait for
the completion notification. That signal never fires headlessly.

Today the run either recovers by inference (dirty-tree fallback), recovers by
re-drive (BUG-3058), or loses the work outright if anything else vetoes. With
this feature the agent's `run_in_background: true` call is rejected by the host,
so it runs the suite in the foreground and reaches Phase 5 normally. The operator
returns to eight completed issues rather than seven and a forensic exercise.

## Program Design

### Signatures

- `ClaudeCodeRunner.build_streaming(self, prompt: str, ..., automation_profile: str | None = None) -> HostInvocation` — existing, `host_runner.py:297`; env-building block at `:351` gains the new var.
- `resolve_host() -> HostRunner` — existing, `host_runner.py`; unchanged entry point.
- `run_claude_command(command: str, ..., automation_profile: str | None = None) -> subprocess.CompletedProcess[str]` — existing, `subprocess_utils.py:320`; unchanged, forwards to the runner.

### Call Path

`process_issue_inplace` (`issue_manager.py:619`) -> `run_with_continuation` (`issue_manager.py:224`) -> `run_claude_command` (`subprocess_utils.py:320`) -> `resolve_host` -> `ClaudeCodeRunner.build_streaming` (`host_runner.py:297`), whose env block at `host_runner.py:351-353` already injects `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` and is the single insertion point. The FSM path reaches the same block via `fsm/runners.py:191`. Four sibling env blocks exist in `host_runner.py` (`:644`, `:1036`, `:1223`, `:1418`) and must be surveyed for parity before implementing.

## Acceptance Criteria

1. When `automation_profile` is set and the new config flag is enabled, the child
   environment carries `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`.
2. When `automation_profile` is unset, the variable is absent — interactive
   sessions are unaffected.
3. The config flag defaults are decided and documented, with the
   `manage-issue` server-smoke-test carve-out (`SKILL.md:394-396`) explicitly
   addressed in the decision: either the carve-out is retired, or the flag
   defaults off.
4. All env-injection blocks in `host_runner.py` are surveyed and either updated
   for parity or documented as deliberately excluded.
5. A test asserts presence and absence of the variable across both branches.
6. The flag's actual scope is verified against a real host invocation — whether
   it disables only `Bash` `run_in_background` or also the synchronous agent
   paths `ll-parallel` depends on.

## Impact

Closes the last gap in a failure mode that silently discards completed work. The
2026-08-04 `ll-auto --only ENH-3046` run lost 21.6 minutes of correct,
fully-tested work this way, and BUG-3026 shows a 30% recurrence rate in one
sprint.

Cost is loss of legitimate backgrounding in automation contexts. If the
server-smoke-test carve-out turns out to matter, this should be scoped down or
closed in favor of the instruction-based defenses.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/claude-code/settings.md:772` | The only description of the flag's scope |
| `skills/manage-issue/SKILL.md:376-400` | The instruction this would replace, and the carve-out it would break |
| `docs/reference/HOST_COMPATIBILITY.md` | Whether non-Claude hosts have an equivalent |

## Status

**Open**

## Session Log
- `/ll:capture-issue` - 2026-08-05T16:09:36 - `fb7ca535-1f06-49a2-8ac3-7943736f7215.jsonl`

- `/ll:capture-issue` - 2026-08-05 - Captured from the ENH-3046 run forensics
  session; recorded as an explicit decision rather than an unstated omission.
