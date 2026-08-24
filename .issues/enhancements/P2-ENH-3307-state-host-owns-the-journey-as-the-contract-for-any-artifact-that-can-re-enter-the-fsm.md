---
id: ENH-3307
title: State "host owns the journey" as the contract for any artifact that can re-enter the FSM
type: ENH
priority: P2
status: open
discovered_date: '2026-08-23'
labels:
- artifact
- fsm
program_design_not_applicable: true
---

## Summary

Define "host owns the journey" as the contract for any artifact that can route a user interaction back into the FSM executor. The executor already owns state transitions; no artifact type today can route an interaction back into the engine as an event. This defines the vocabulary and rules before any transport-level mechanism (a local SSE bridge, queue-backed command execution, an MCP Apps interactive resource, or any future render target) locks in a de facto contract by accident.

## Current Behavior

No document or vocabulary defines what an artifact may do when a user acts on it, or who owns the resulting FSM transition. The FSM executor is authoritative over state transitions; artifacts today (dashboards, markdown reports) are one-way — a loop renders an artifact and hands it to a human or another agent, with no path back into the engine. Each new render target (a local SSE bridge, queue-backed command execution, an MCP Apps interactive resource such as ENH-3306) risks locking in a de facto re-entry contract by accident, since nothing written down constrains it.

## Expected Behavior

A written contract — the three-level control taxonomy (notify / ask-to-run-prompt / host-owned) described below — exists as a document/spec artifact that defines, per level, what an artifact may emit, what the host is obligated to do with it, and which layer (host session vs. FSM executor) owns the resulting state change. The contract is protocol- and render-target-agnostic, so it governs htmx-based artifacts over a local bridge, MCP Apps interactive resources (ENH-3306), and any future render target without modification.

## Background / Motivation

The FSM executor is authoritative over transitions; artifacts today (dashboards, markdown reports) are one-way — a loop renders an artifact and hands it to a human or another agent, but the artifact cannot re-enter the engine. The event stream the engine already emits is the substrate an interactive artifact would plug into; the missing piece is defining what an artifact is allowed to do when a user acts on it, and who owns the resulting transition.

## Proposed contract: a three-level control taxonomy

This is little-loops' own vocabulary for the contract — informal framing chosen for clarity, not terminology defined by any MCP specification:

1. **notify** — the artifact reports state and owns nothing; there is no re-entry into the FSM.
2. **ask-to-run-prompt** — the artifact asks the host session to run a prompt, releasing responsibility to the host; the FSM engine is not the one acting.
3. **host-owned** — the interaction *is* an event the engine consumes; the executor retains ownership of the resulting transition.

The distinction that matters most is level 2 vs. level 3: level 2 hands control to the host session (a human- or agent-mediated step), level 3 keeps the executor authoritative over the transition with no intermediate hand-off. A queue-backed command-execution path that lets a live artifact trigger execution implies level 3 without saying so explicitly — naming the levels here is what stops that kind of path from defining the contract implicitly, after the fact.

## Relationship to MCP Apps (checked against the extension spec, stable release 2026-01-26)

The MCP Apps extension defines a different, narrower axis under similar-sounding territory: tool **visibility** (`_meta.ui.visibility` = `"model"` | `"app"` | both), which is access control over who may invoke a given tool — not a taxonomy of journey-control levels. Do not conflate the two, and do not expect a wire-protocol field that maps 1:1 onto the three-level model above; it must be defined and enforced at little-loops' own contract layer, independent of whatever transport carries the interaction (a local bridge, an MCP Apps interactive resource, or any future render target).

## Impact

- **Priority**: P2 - not blocking today's artifact types (which are all level-1 notify), but should land before a transport mechanism (a local SSE bridge, ENH-3306) ships and defines the contract implicitly.
- **Effort**: Small - a document/spec artifact defining vocabulary and rules; no code changes to the FSM executor itself.
- **Risk**: Low - purely additive documentation; does not change existing artifact or executor behavior.
- **Breaking Change**: No.

## Scope Boundaries

- Out of scope: implementing any transport mechanism (SSE bridge, queue-backed command execution, MCP Apps interactive resource) — this issue defines the contract those mechanisms must follow, not a mechanism itself.
- Out of scope: mapping the three levels onto a specific wire-protocol field; the MCP Apps `_meta.ui.visibility` axis is a different, narrower concern (tool access control) and must not be conflated with journey-control levels.
- Out of scope: retrofitting existing one-way artifacts (dashboards, markdown reports) to a specific level — they already satisfy level 1 (notify) by construction.

## Scope

- The contract must be protocol- and render-target-agnostic: it must hold for htmx-based artifacts over a local bridge, for MCP Apps interactive resources, and for whatever render target follows.
- Write the contract as a document/spec artifact defining, per control level, what an artifact may emit, what the host is obligated to do with it, and which layer (host session vs. FSM executor) owns the resulting state change.
- This should land ahead of the transport mechanisms that will need it, not be reverse-engineered out of a shipped mechanism afterward.

## Status

Open.


## Session Log
- `/ll:format-issue` - 2026-08-24T00:04:16 - `9d912d1c-def8-4ac1-b2d0-73ed036e9de0.jsonl`
