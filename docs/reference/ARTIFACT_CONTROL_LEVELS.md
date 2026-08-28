# Artifact Control Levels

This document is the canonical contract for what a rendered artifact may do when a
user interacts with it, and which layer — the host session or the FSM executor —
owns the resulting state change. It exists so that any render target (a local
SSE bridge, queue-backed command execution, an MCP Apps interactive resource, or
any future mechanism) conforms to one written contract instead of each inventing
its own re-entry path into the FSM. Every other doc that discusses artifact
interactivity links here rather than restating this contract.

> **Related Documentation:**
> - [Architecture Overview](../ARCHITECTURE.md) — see `## Artifact Control Layer` for how this contract sits alongside the Host Runner Layer
> - [Event Schema Reference](EVENT-SCHEMA.md) — see `## Reserved Event Names` for the reserved `artifact_interaction` event
> - [MCP Server Guide](../guides/MCP_SERVER_GUIDE.md) — the first consumer of this contract (ENH-3306's `ui://` resources)

## The three levels

Any artifact that can route a user interaction back toward the FSM engine operates
at exactly one of three levels. This is little-loops' own vocabulary for the
contract — informal framing chosen for clarity, not terminology defined by any MCP
specification.

| Level | Artifact may emit | Host is obligated to | Owner of resulting state change | Existing / planned example |
|---|---|---|---|---|
| 1 notify | Display-only signals (`ui/message`, status text) | Surface it; nothing else | Nobody — no state change | `html-anything.yaml` dashboards; ENH-3306 first view |
| 2 ask-to-run-prompt | A prompt/command request addressed to the host session | Decide whether to run it; if run, run it as its own session action | Host session (human/agent), *not* the executor | `HandoffBehavior.SPAWN` (closest analog) |
| 3 host-owned | An `artifact_interaction` event | Deliver it to the executor's inbound channel unchanged | FSM executor (`FSMExecutor`) | `ll-loop run --serve`'s SSE bridge (ENH-3351) |

### Level 2 vs. level 3

The distinction that matters most is level 2 vs. level 3. Level 2 hands control to
the host session — a human- or agent-mediated step decides whether and how to act,
and any resulting FSM transition happens later, through the host's own normal
session actions. Level 3 keeps the FSM executor authoritative over the transition
with no intermediate hand-off: the interaction *is* the event the engine consumes.
A queue-backed command-execution path that lets a live artifact trigger execution
directly implies level 3 without saying so explicitly — naming the levels here is
what stops that kind of path from defining the contract implicitly, after the fact.

## Prohibitions

In the style of the Host Runner Layer's "MUST go through `resolve_host()`" rule:

1. A render target MUST declare which level(s) it supports (see below) and MUST
   NOT emit above its declared level.
2. No transport may consume a level-3 event itself — it must hand it to the
   FSM executor unchanged.

## Declared levels by render target

This table is canonical — a new render target landing without a row here is a
contract violation reviewers can point at.

| Render target | Declared level(s) |
|---|---|
| `html-anything.yaml` dashboards | 1 (notify) |
| ENH-3306's `ui://` resources | 1 (notify) |
| `ll-loop run --serve`'s dashboard page (ENH-3351) | 3 (host-owned) |

**Binding now:** every render target MUST declare its supported level(s) in
prose, in its own canonical doc, and MUST link back to this document for the
definitions.

**Forward slot, non-binding (not built here):** when a render target first needs
a machine-readable declaration, it belongs on that target's own registration
record — an `ArtifactControlLevel`-valued field on `_ResourceEntry`
(`scripts/little_loops/mcp_server/resources.py`) for `ll-mcp`, and an
artifact-type key for loop-YAML artifact types. This document names these as the
intended sites so two mechanisms do not invent two different ones; adding either
field is out of scope for this issue.

## Reserved event: `artifact_interaction`

The level-3 event name `artifact_interaction` is reserved so that ENH-3306's view
and `ll-loop run --serve`'s SSE bridge converge on one name rather than each
inventing one. `FSMExecutor._drain_inbound()` (ENH-3351) is the first emitter —
see
[EVENT-SCHEMA.md § Reserved Event Names](EVENT-SCHEMA.md#reserved-event-names) for
the full reservation and its schema.

The payload fields compose with the standard event envelope (`event`, `ts`, both
always present; an executor-emitted event additionally carries `state` and
`loop`), not replace it:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `artifact_id` | `str` | yes | Stable identifier of the artifact instance that produced the interaction |
| `level` | `str` | yes | One of the three level identifiers — `"notify"` \| `"ask-to-run-prompt"` \| `"host-owned"`; a string identifier, not an ordinal, matching the `terminated_by` / `reason` precedent elsewhere in `EVENT-SCHEMA.md` |
| `action` | `str` | yes | Render-target-defined name of the interaction the user performed |
| `payload` | `object` | optional | Free-form, render-target-defined interaction data; `additionalProperties: true` |

## Relationship to MCP Apps

The MCP Apps extension (stable release 2026-01-26) defines a different, narrower
axis under similar-sounding territory: tool **visibility**
(`_meta.ui.visibility` = `"model"` \| `"app"` \| both), which is access control
over who may invoke a given tool — not a taxonomy of journey-control levels. Do
not conflate the two, and do not expect a wire-protocol field that maps 1:1 onto
the three-level model above; the three levels are defined and enforced at
little-loops' own contract layer, independent of whatever transport carries the
interaction.

## Scope boundaries

- Out of scope: implementing any transport mechanism (SSE bridge, queue-backed
  command execution, MCP Apps interactive resource) — this document defines the
  contract those mechanisms must follow, not a mechanism itself.
- Out of scope: mapping the three levels onto a specific wire-protocol field.
- Out of scope: retrofitting existing one-way artifacts (dashboards, markdown
  reports) to a specific level — they already satisfy level 1 (notify) by
  construction.
