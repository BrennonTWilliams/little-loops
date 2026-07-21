---
id: ENH-2714
type: ENH
title: Automation-context static-prefix pruning for FSM invocations
priority: P2
status: open
captured_at: "2026-07-21T02:03:13Z"
discovered_date: "2026-07-21"
discovered_by: capture-issue
parent: EPIC-2456
labels: [token-cost, fsm, orchestration]
relates_to: [EPIC-2456, FEAT-2672, FEAT-2711, ENH-2486]
---

# ENH-2714: Automation-context static-prefix pruning for FSM invocations

## Summary

Every fresh FSM state invocation re-sends a large static prefix the state usually
doesn't need: the full skill/command catalog, the SessionStart hook's dump of the
resolved `ll-config.json` + `project_context` block, memory/session-digest
injection, and CLAUDE.md. Broaden the original catalog-only scope of this issue
to a general **automation-context static-prefix diet**: for a tight, controlled
FSM state whose prompt fully specifies the task, prune every prefix component we
control and suppress the rest where the host CLI allows it. Default remains the
full prefix; pruning is opt-in per loop/state.

This supersedes the session-resume approach (FEAT-2711) as EPIC-2456's default
per-invocation token lever: pruning makes every invocation strictly cheaper with
zero cross-state coupling, whereas resume amortizes the prefix but re-reads a
growing transcript each turn and has to un-break FSM state isolation
(fresh-on-retry/handoff, evaluator-independence guards) to stay correct.

## Motivation

`ll-verify-skill-budget` polices the catalog's total footprint, but every loop
state still pays for the whole listing — plus hook output and CLAUDE.md — on
every iteration. Most of that prefix is under our own control:

- **SessionStart hook output** (config JSON + project_context) is our code —
  trivially gated on an automation signal.
- **Skill/command catalog** narrows via existing host flags (the original scope
  of this issue; CLI-path analogue of FEAT-2672's SDK-path deferred loading).
- **Memory / session digest / historical context** injection is ours to gate.
- **CLAUDE.md** is host-controlled; suppression needs a per-host capability
  check, but for mechanical shell/verdict states project conventions add nothing.

Savings compound per state per iteration and require no semantic changes to loop
execution. CLAUDE.md is likely the dominant component in this repo — the
measurement AC should break the delta down per component.

## Current Behavior

`fsm/runners.py` → `build_streaming()` invocations inherit the full skill/command
catalog, full SessionStart hook output, memory injection, and CLAUDE.md; only
bare tool names flow through `--tools` CSV and no state narrows anything.

## Expected Behavior

A loop (or state, state overrides loop) may declare a prefix-pruning profile;
the host invocation is built with narrowing flags and an automation env signal
so gated components emit nothing. Default behavior unchanged.

## Proposed Solution

1. **Automation signal**: FSM runner sets `LL_AUTOMATION=1` (and
   `LL_AUTOMATION_PROFILE=<profile>`) in the child environment for pruned
   invocations.
2. **Hook gating**: SessionStart (and other injection hooks: memory recall,
   session digest, historical context) check the signal and emit nothing (or a
   minimal stub) under an automation profile. This is pure hook-side change —
   works on every host that runs our hooks.
3. **Catalog narrowing** (original scope): loop-YAML `tools:` / `skills:`
   allowlist at loop and state level, mapped to each host's narrowing flags via
   `resolve_host()` (Claude `--tools`/`--disallowedTools`-family; confirm
   per-host capability via `ll-doctor` before mirroring — defer-until-confirmed
   posture).
4. **CLAUDE.md suppression**: where the host exposes a flag/env to skip project
   instructions, map it behind the same `ll-doctor` capability check; no-op
   cleanly where unsupported.
5. **Presets**: ship conservative pruning presets for builtin loops' mechanical
   states (shell/verdict states) rather than auditing every loop up front.
6. **Validation**: ERROR if a state's action references a skill excluded by its
   own allowlist; WARN if a state that invokes `/ll:*` skills runs under a
   profile that suppresses the catalog.

## Acceptance Criteria

- [ ] Per-state allowlist reaches the host invocation; unlisted states unchanged.
- [ ] SessionStart/memory/digest injection emits nothing under the automation
      profile; interactive sessions unchanged.
- [ ] Validation catches self-contradictory allowlists and
      catalog-suppressed-but-skill-invoking states.
- [ ] Cross-host: narrowing/suppression applied only on hosts whose capability
      is confirmed via `ll-doctor`; others no-op cleanly.
- [ ] Measured per-invocation input-token delta on a locked trace, broken down
      per prefix component (catalog / hook output / CLAUDE.md), recorded before
      close.

## Impact

- **Priority**: P2 — promoted from P3; now the epic's default per-invocation
  lever, lower risk than session resume with comparable or better savings.
- **Effort**: Medium (~120–180 LOC + tests): schema + host-flag mapping +
  hook gating + presets.
- **Risk**: Low-Medium — an over-tight profile can break a state; validation,
  opt-in defaults, and conservative presets mitigate.

## Session Log
- `/ll:capture-issue` - 2026-07-21T02:03:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79ab3d38-0b67-42aa-9ad2-b6f2af55d225.jsonl`
- Re-scoped 2026-07-20: broadened from catalog-only pruning to full
  static-prefix pruning; promoted P3→P2; supersedes FEAT-2711 as the epic's
  default per-invocation savings lever (FEAT-2711 re-scoped to
  continuity-of-reasoning chains).

---

## Status

**Open** | Created: 2026-07-21 | Priority: P2
