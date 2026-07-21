---
id: BUG-2729
title: headless automation sessions that end their turn while awaiting subagents are
  torn down by claude -p shutdown (SIGTERM/exit 143), discarding in-flight work
type: BUG
status: open
priority: P1
captured_at: '2026-07-21T22:40:00Z'
discovered_date: '2026-07-21'
discovered_by: audit-loop-run
labels:
- subprocess
- automation
- headless
- prompt-contract
relates_to:
- BUG-2718
- ENH-2717
- BUG-2726
- ENH-2727
- ENH-2714
---

# BUG-2729: headless sessions that end their turn while awaiting subagents self-terminate with exit 143, discarding in-flight work

## Summary

FSM `slash_command` actions run skills via headless `claude -p` (stream-json).
In interactive Claude Code, a model may spawn subagents, **end its turn**, and be
re-invoked by a `<task-notification>` when they finish. In headless mode that
contract does not exist: the end-of-turn `result` event ends the *session*. The
CLI then shuts down, reaps its still-running subagent children (SIGTERM to the
process group), and exits **143** — silently discarding all in-flight subagent
work. From the FSM's perspective the action just "failed with exit 143".

This is the behavioral successor of [[BUG-2718]]: that fix stopped *little-loops*
from SIGKILLing sessions whose streams closed early (grace 30s → 300s +
result-event break), but it cannot stop *claude itself* from tearing down when
the model voluntarily ends its turn to wait. Whether a given run survives
depends on whether the model chooses to block in-turn on its agents (survives)
or end-turn-and-wait (dies) — which is why this recurs intermittently across
automation runs.

## Evidence (run `2026-07-21T214941-autodev`, refine of ENH-2722)

Inner session transcript
`~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d7556fa3-cf0f-4f60-bc7c-7b6b7c3355dd.jsonl`:

1. The session spawned three subagents in one message (`ll:codebase-locator`,
   `ll:codebase-analyzer`, `ll:codebase-pattern-finder`; `run_in_background`
   unset).
2. Last assistant text: *"I'll pause here and wait for the three background
   research agents (locator, analyzer, pattern-finder) to complete before
   enriching the issue file."* — the turn genuinely ended: the **Stop hook
   fired**, `stop_hook_summary` was written.
3. `{"type": "queue-operation", "operation": "dequeue", "timestamp":
   "2026-07-21T21:52:21.056Z"}` — a `<task-notification>` user message was being
   dequeued to re-invoke the model.
4. The process exited **143** at `21:52:21.997` (< 1s later). The FSM run log
   shows only `(2m 36s)  exit: 143` — none of little-loops' kill-path log lines
   ("Action timed out" / "did not exit within Ns after streams closed, killing"),
   and those paths SIGKILL (returncode -15/-9), not 143.
5. Downstream: `refine-to-ready-issue` routed `on_error → diagnose → failed`;
   autodev ledgered `ENH-2722  refine_failed` ([[ENH-2727]] misattribution) and
   the diagnose session confabulated ([[BUG-2726]]). Both are mitigations of
   consequences; this issue is the root cause.

## Expected Behavior

Automation-invoked sessions never lose work to their own end-of-turn: either the
session stays in-turn until all spawned agents return, or the FSM recognizes the
teardown signature and retries/resumes instead of recording a hard failure.

## Proposed Fix

Primary — **prompt contract for headless runs**: inject an instruction into the
automation prompt path (the static prefix `run_claude_command` /
`skill_expander.py` builds; [[ENH-2714]]'s `automation_profile` is a natural
carrier) stating: *"You are running headlessly. Ending your turn ends the
session. Never end your turn while spawned agents/tasks are still running — wait
for them synchronously within the turn."* Audit the parallel-agent skills
(`refine-issue`, `decide-issue`, `wire-issue`, …) for wording that invites the
wait-for-notification pattern.

Secondary — **retryable teardown signature in the FSM**: treat
`exit_code == 143` + `result_seen` (usage captured) as `infra_retry` rather than
a terminal action failure: retry once via `--resume <session_id>` (the
transcript survives) or re-run the action, and ledger a distinct reason code
(coordinates with [[ENH-2727]]).

## Acceptance Criteria

- [ ] Headless automation prompt prefix carries the stay-in-turn contract
- [ ] Parallel-agent skills contain no end-turn-and-wait phrasing for
      automation mode
- [ ] FSM classifies exit-143-after-result as retryable infra teardown with a
      distinct ledger reason (not `refine_failed`), with at least one retry
- [ ] Regression coverage: a simulated 143-after-result action routes to retry,
      not `on_error` terminal failure
