---
id: ENH-3307
title: State "host owns the journey" as the contract for any artifact that can re-enter the FSM
type: ENH
parent: EPIC-3127
priority: P2
status: open
discovered_date: 2026-08-23
discovered_by: research-apply
promoted_from: ll-product/ENH-313
promoted_at: 2026-08-23
labels:
- artifact
- fsm
- contract
- journey
research_source: https://www.youtube.com/watch?v=-jY2T2PiJBE
confidence_score: 88
outcome_confidence: 78
score_complexity: 25
score_test_coverage: 35
score_ambiguity: 30
score_change_surface: 20
relates_to:
- ENH-3306
- FEAT-067
- FEAT-068
blocks:
- ENH-3306
goal_alignment: clarify
---

# ENH-3307: State "host owns the journey" as the contract for any artifact that can re-enter the FSM

## Status

**Open** — Spoke file landed as the precondition for implementation.

Promoted from ll-product `ENH-313` on 2026-08-23. The hub manifest at
`ll-product/.ll/promotion-manifest.yaml` recorded the spoke ID but the file
itself never made it into this repo (see BUG-322). This file exists to close
that gap before any code work begins.

---

## Context

The executor owns FSM transitions, but no artifact type can currently route
a user interaction back into the engine. FEAT-067 (local read-only SSE
bridge) and FEAT-068 (queue-backed command execution from live artifacts)
are building the transport for exactly that re-entry, and both are still
open and unpromoted — so the contract can land ahead of the mechanism
instead of being reverse-engineered out of it afterward.

This issue is the contract. Its job is to:

1. Name the three control levels an artifact interaction can occupy:
   - **notify** — the artifact reports state and owns nothing; no re-entry.
   - **ask-to-run-prompt** — the artifact asks the host session to run a
     prompt, releasing responsibility to the host; the FSM is not the one
     acting.
   - **host-owned** — the interaction *is* an event the engine consumes;
     the executor retains ownership of the resulting transition.
2. Make the distinction between level 2 and level 3 the load-bearing one:
   level 2 hands control to the host session, level 3 keeps the executor
   authoritative over the transition. FEAT-068 currently implies level 3
   without saying so; naming it is what stops the queue-backed exec path
   from defining the contract implicitly.
3. Pin the contract at the little-loops layer, not on the wire format. The
   vocabulary is ours, the spec does not provide field-for-field
   semantics for it (see "Spec conformance" below).

---

## MCP Apps spec conformance (checked against ext-apps 2026-01-26 stable)

The notify / ask-to-run-prompt / host-owned taxonomy is little-loops' own
vocabulary, sourced from the talk's framing — it is not terminology defined
in the published MCP Apps extension spec.

Whoever writes the contract should say so explicitly, because the spec
defines an adjacent-but-different, orthogonal axis under similar-sounding
territory: tool **visibility** (`_meta.ui.visibility` = `"model"` | `"app"`
| both), which is access control over who may invoke a tool, NOT a
taxonomy of journey-control levels.

Do not let the two get conflated. Do not expect a protocol field that maps
1:1 onto this three-level model — it needs to be defined and enforced at
little-loops' contract layer, not looked up in the wire format.

The event stream the engine already emits is the substrate. The missing
piece is an artifact whose interaction is an event on it. This issue
defines the vocabulary; FEAT-067/FEAT-068 build the transports; ENH-3306
builds the artifact that opts into the vocabulary.

---

## Proposed Solution

1. Document the contract in `docs/generalized-fsm-loop.md` (or a sibling
   doc under `docs/contracts/` if one exists by the time this lands). The
   doc MUST:
   - Name the three levels (notify / ask-to-run-prompt / host-owned) and
     define each in one paragraph.
   - State the level-2 vs. level-3 distinction explicitly, because that
     is the one that determines who owns the resulting transition.
   - State the contract is protocol- and render-target-agnostic: it holds
     for htmx artifacts over the local SSE bridge, for interactive MCP
     resources (ENH-3306), and for whatever render target follows.
   - State the spec boundary: do not look up 1:1 field mappings in the
     wire format. The vocabulary is defined and enforced at the
     little-loops contract layer.

2. Add a runtime check helper in the event-substrate layer (next to the
   FSM event emission code) that classifies each artifact interaction into
   one of the three levels before the event is enqueued. The classifier is
   config-driven — the artifact author declares which level applies via
   an explicit `journey: notify | ask_to_run_prompt | host_owned` field on
   the artifact's configuration.

3. Add the `journey` field to the loop config schema. The default is
   `notify` (no re-entry, safe). Promoting an artifact to `ask_to_run_prompt`
   or `host_owned` is an opt-in that the author must make visible in the
   loop file.

4. Test coverage:
   - Default-loop behavior is unchanged: an artifact with no `journey`
     field emits a `notify`-class event and the executor logs but does not
     act on it.
   - `journey: ask_to_run_prompt` routes the interaction to the host
     session's prompt queue; the FSM executor receives no event and does
     not transition.
   - `journey: host_owned` produces an event on the engine's stream;
     the executor consumes it and transitions exactly as if a tool had
     emitted the same event.
   - The vocabulary doc explicitly cross-references ENH-3306
     (interactive MCP resources) and FEAT-067 / FEAT-068 (transports).

---

## Dependencies

- **Blocks**: ENH-3306 (interactive resources are unfettered re-entry
  without this contract — see Risk).
- **Related**: FEAT-067 (local SSE bridge), FEAT-068 (queue-backed command
  execution).
- **Pre-existing substrate**: the engine's event stream; no new transport
  required for the contract itself.

---

## Acceptance Criteria

- A normative doc exists under `docs/` (preferable: `docs/contracts/artifact-journey.md`
  or the equivalent location the repo already uses for FSM contract docs)
  that defines the three levels.
- A `journey` field on the relevant config schema accepts one of
  `notify | ask_to_run_prompt | host_owned`, with `notify` as the default.
- Validation rejects unknown values rather than silently defaulting.
- Runtime classification emits a structured log entry identifying the
  journey level for each artifact interaction, so it is auditable after
  the fact.
- The doc explicitly names the level-2 vs. level-3 distinction and the
  spec-boundary disclaimer about `_meta.ui.visibility`.
- Tests cover all three levels plus the default case; the default case is
  the regression-safety test (default behavior unchanged).
- The doc explicitly cross-references ENH-3306 as a downstream consumer
  of this contract.

---

## Out of Scope

- Implementing the transports (FEAT-067, FEAT-068) — those carry the
  contract; this issue defines it.
- Implementing an interactive artifact that uses the contract — that is
  ENH-3306.
- Any per-host adaptation beyond naming the contract. Host-specific
  conformance (does Claude Code honor `host_owned`? does Codex?) is a
  follow-up once at least one host does.

---

## Risk

- **Medium if shipped alone, on its own merit**: low. The contract is a
  doc plus a config field plus a classifier; defaulting to `notify`
  preserves existing behavior.
- **High if shipped AFTER ENH-3306**: an interactive MCP resource with
  no journey contract is unfettered re-entry into the engine. This issue
  MUST land before or alongside ENH-3306.
- **Medium if vocabulary diverges across docs**: pin the terms in
  `docs/contracts/` (or the canonical place) and refuse synonyms in
  validation messages to keep one vocabulary across the codebase.

---

## Source Doc

- `ll-product/docs/research/2026-08-23-mcp-apps-agentic-web.md` (resolved
  via the promotion handoff; mirror to local `docs/research/` if an
  equivalent does not already exist locally before implementation work).

---

**Open** | Created: 2026-08-23 | Promoted from ll-product #ENH-313 | Spoke file landed 2026-08-24
