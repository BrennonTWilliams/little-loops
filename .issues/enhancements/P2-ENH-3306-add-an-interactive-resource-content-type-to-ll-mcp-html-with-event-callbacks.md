---
id: ENH-3306
title: Add an interactive-resource content type to ll-mcp (HTML with event callbacks)
type: ENH
parent: EPIC-3127
priority: P2
status: open
discovered_date: 2026-08-23
discovered_by: research-apply
promoted_from: ll-product/ENH-312
promoted_at: 2026-08-23
labels:
- mcp
- artifact
- ext-apps
- contract
research_source: https://www.youtube.com/watch?v=-jY2T2PiJBE
confidence_score: 70
outcome_confidence: 55
score_complexity: 50
score_test_coverage: 40
score_ambiguity: 45
score_change_surface: 35
relates_to:
- ENH-3307
- FEAT-067
- FEAT-068
depends_on:
- ENH-3307
goal_alignment: clarify
---

# ENH-3306: Add an interactive-resource content type to ll-mcp (HTML with event callbacks)

## Status

**Open** — Spoke file landed as the precondition for implementation.

Promoted from ll-product `ENH-312` on 2026-08-23. The hub manifest at
`ll-product/.ll/promotion-manifest.yaml` recorded the spoke ID but the file
itself never made it into this repo (see BUG-322). This file exists to close
that gap before any code work begins.

---

## Context

Add a fourth content type to ll-mcp's resource surface: resources that
resolve to **interactive HTML with event callbacks**, rendered by the host
session rather than a browser tab. This lands on the MCP Apps extension
(`io.modelcontextprotocol/ui`, ext-apps spec 2026-01-26 stable), not on the
existing `ll://` URI scheme and not on a new transport — the marginal cost
is one content type layered on the resource surface v1 already ships as a
facade over library functions.

State the bet explicitly before any code is written: the payoff is contingent
on interactive MCP resources reaching real host adoption, which is not yet
true, and the in-chat render sandbox is materially more constrained than the
browser-tab render that FEAT-066/FEAT-067 assume. This is cheap optionality on
existing plumbing, not a commitment to build ahead of host support.

Complements rather than competes with FEAT-067's local SSE bridge, which
serves a different render target with different data-access assumptions. Any
interaction this content type exposes is governed by the artifact-to-FSM
re-entry contract captured as ENH-3307 (host owns the journey) — **ENH-3307
is a hard dependency** for this issue: an interactive resource without the
contract is unfettered re-entry, which violates the host-owns-the-journey
invariant.

---

## MCP Apps spec conformance (checked against ext-apps 2026-01-26 stable)

The `ll://` scheme is **not** viable for the interactive resource itself: the
MCP Apps extension spec normatively requires `"URI MUST start with ui://"`.
`ll://issues/<id>` can stay the resource identity for the underlying data,
but the interactive view must be published as a separate `ui://`-scheme
resource, referenced from the originating tool via `_meta.ui.resourceUri`
(the spec's tool→UI linkage field, host-fetched via `resources/read`).
Content must also carry `mimeType: "text/html;profile=mcp-app"` — plain
HTML is not sufficient.

Any implementation plan must also account for host capability negotiation:
a client only renders these if it declared the `io.modelcontextprotocol/ui`
extension at `initialize` with that MIME type listed — this is the concrete
mechanism behind the "not yet true" host-adoption note, not just a vague
maturity gap. MCP Apps is versioned independently of core MCP (stable spec
dated 2026-01-26, separate from the core protocol's 2026-07-28) — track
ext-apps' own spec revisions, not the core protocol's.

---

## Proposed Solution

1. Add a `ContentType.INTERACTIVE_HTML` (or equivalently-named literal) to
   `little_loops/mcp_server/resources.py`, alongside the existing text/markdown
   and JSON content types. The literal must carry a stable name and a
   stable numeric tag.

2. In `make_list_resources_handler` / `make_read_resource_handler` (or their
   successors), branch on the new content type to:
   - Validate the URI scheme is `ui://` (reject `ll://`, return `MCPError`
     with a spec-citing message — not a silent fallback).
   - On read, resolve to a sibling `ui://` resource whose MIME type is
     `text/html;profile=mcp-app`, NOT the underlying `ll://` data — the
     `ll://` resource may still exist but is for data, not rendering.

3. Tool definitions that wish to surface an interactive view attach
   `_meta.ui.resourceUri` (string, `ui://...`) and (when the spec is
   updated) `_meta.ui.visibility` if model/app visibility split is desired.
   Wire a thin helper in `tools.py` so authors do not assemble the meta
   block by hand.

4. Capability negotiation: at server construction, check
   `server.get_client_capabilities().extensions` for
   `io.modelcontextprotocol/ui` with `text/html;profile=mcp-app` listed in
   its declared MIME types. If absent, the `ui://` resource must still be
   readable (so reading does not error), but the server MUST NOT advertise
   it in `resources/list` — that is the host-adoption gate.

5. Test coverage:
   - `resources/list` does not include `ui://` entries when the client did
     not declare the extension at `initialize`.
   - `resources/read` against a `ui://` URI returns content with
     `mimeType: "text/html;profile=mcp-app"`, never `text/html`.
   - `resources/read` against an `ll://` URI that has an interactive
     counterpart still returns the data MIME, not the render MIME.
   - Tool → UI linkage via `_meta.ui.resourceUri` survives a JSON
     round-trip and round-trips back to the same `resources/read` call.

---

## Dependencies

- **Hard blocker**: ENH-3307 (the artifact-to-FSM re-entry contract must
  exist before any interactive view can be wired — otherwise the interaction
  has no defined journey).
- **Related**: FEAT-067 (local SSE bridge — different render target,
  different data assumptions; do not collapse into a single concept).
- **Related**: FEAT-068 (queue-backed command execution from live artifacts;
  one of its two control levels — *host-owned* — is what ENH-3307 names).

---

## Acceptance Criteria

- A `ContentType` (or equivalent) literal exists for interactive HTML,
  distinct from `MARKDOWN` and `JSON`, and is named consistently in the
  resource surface and tool layer.
- `resources/read` for a `ui://...` URI returns content whose MIME type is
  `text/html;profile=mcp-app`; the response never silently downgrades to
  `text/html`.
- `resources/read` for a sibling `ll://...` data resource keeps its data
  MIME type even when the resource advertises an interactive counterpart.
- A tool exposes an interactive view by declaring `_meta.ui.resourceUri`
  pointing at a `ui://` resource; the linkage round-trips through a
  `resources/read` call without a hand-built meta block.
- When the connecting client does NOT declare
  `io.modelcontextprotocol/ui` at `initialize` (or declares it without
  `text/html;profile=mcp-app` in its MIME list), `ui://` resources are
  omitted from `resources/list` — the host-adoption gate is enforced, not
  just documented.
- Tests cap coverage at the boundary: URI-scheme validation, MIME-type
  pinning, capability-gated listing, and `_meta.ui.resourceUri` round-trip.
  Render-correctness (does the HTML actually work?) is **out of scope** —
  that's the host's job, not ours.
- The bet is restated in the implementation PR's first comment: payoff is
  contingent on host adoption that is not yet true; in-chat render sandbox
  is materially more constrained than FEAT-066/FEAT-067's browser-tab
  assumptions.

---

## Out of Scope

- Rendering the HTML in any specific way. The host does that.
- Any host-specific capability beyond what ext-apps 2026-01-26 defines.
- Browser-tab render via FEAT-066/FEAT-067's local SSE bridge. Different
  feature, different issue.
- Interaction semantics. That lives in ENH-3307.

---

## Risk

- **Medium if shipped alone**: an interactive resource with no contract
  is unfettered re-entry. ENH-3307 must land first or in the same release
  train.
- **Low once ENH-3307 lands**: ext-apps spec is stable; conformance
  requirements are mechanical.
- **High if host adoption flattens**: every line of code in this issue
  is optionality, not commit. Revisit if the spec stalls past 2027.

---

## Source Doc

- `ll-product/docs/research/2026-08-23-mcp-apps-agentic-web.md` (resolved
  via the promotion handoff; mirror to local `docs/research/` if an
  equivalent does not already exist locally before implementation work).

---

**Open** | Created: 2026-08-23 | Promoted from ll-product #ENH-312 | Spoke file landed 2026-08-24
