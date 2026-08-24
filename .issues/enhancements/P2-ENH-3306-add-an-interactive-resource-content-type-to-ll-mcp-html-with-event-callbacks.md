---
id: ENH-3306
title: Add an interactive-resource content type to ll-mcp (HTML with event callbacks)
type: ENH
priority: P2
status: open
discovered_date: '2026-08-23'
labels:
- mcp
- artifact
---

## Summary

Add an interactive-resource content type to `ll-mcp`: resources that resolve to interactive HTML with event callbacks, rendered by the host session rather than a browser tab. This is an MCP Apps–compliant content type layered onto `ll-mcp`'s existing resource surface — not a new server or transport.

## Current Behavior

`ll-mcp`'s resource surface (`scripts/little_loops/mcp_server/resources.py`) enumerates `_ResourceEntry` objects with a `mime_type` that is always a plain, non-interactive type (`application/json`, `text/markdown`) served from a fixed set of URI schemes (issue, goals, docs). There is no resource content type that a host can render as an inline interactive view, and no path for a rendered view to post interactions back to the host. Dashboard/artifact UX today is served by separate htmx explorations targeting a browser tab, entirely outside `ll-mcp`.

## Expected Behavior

`ll-mcp` can publish a `ui://`-scheme resource whose `mime_type` is `text/html;profile=mcp-app`, discoverable and readable through the existing `resources/list` / `resources/read` handlers. A tool that wants to render through this view declares it via `_meta.ui.resourceUri`; a client that has negotiated the `io.modelcontextprotocol/ui` capability at `initialize` renders it inline and exchanges JSON-RPC 2.0 messages with it over `postMessage` per the MCP Apps extension spec. Any interaction the view emits back toward the FSM is routed per whatever contract governs artifact-to-host ownership (see ENH-3307) rather than inventing ad hoc semantics here.

## Background / Motivation

`ll-mcp` maps MCP's three core primitives (tools, resources, prompts) onto little-loops' CLI/files/skills trichotomy. That design has no UI surface today — dashboard/artifact UX is served by separate htmx explorations targeting a browser tab, not a chat host. The MCP Apps extension to the Model Context Protocol adds exactly this: a resource content type that a host renders inline as a sandboxed interactive app, where UI-originated interactions post back to the host rather than to the resource's own backend — the host decides what happens next, not the resource.

## Design constraints (checked against the MCP Apps extension spec, stable release 2026-01-26)

- **URI scheme**: the spec normatively requires interactive-UI resource URIs to start with `ui://` ("URI MUST start with `ui://`"). An existing data resource under a different scheme can stay as-is for non-interactive reads; the interactive view itself must be published as its own `ui://`-scheme resource — reusing an existing scheme for this is not spec-conformant.
- **MIME type**: interactive resources must declare `mimeType: "text/html;profile=mcp-app"`. Plain `text/html` is not sufficient for a host to recognize the resource as an MCP Apps view.
- **Linkage**: a tool that wants to render through this view declares it via `_meta.ui.resourceUri` on the tool definition; the host is required to `resources/read` that URI to fetch the view before rendering.
- **Capability negotiation**: a client only renders these resources if it declared the `io.modelcontextprotocol/ui` extension at `initialize`, with the supported `mimeTypes` listed. Real host adoption of this capability is the actual gate on payoff here — most current hosts do not declare it yet.
- **Host↔view messaging** is JSON-RPC 2.0 over `postMessage`: the view can request `tools/call`, `resources/read`, `ui/open-link`, `ui/message`, `ui/request-display-mode`, `ui/update-model-context`; the host pushes `ui/notifications/tool-input`, `ui/notifications/tool-result`, `ui/notifications/tool-cancelled`, `ui/notifications/size-changed`, and a `ui/resource-teardown` cleanup signal.

## Impact

- **Priority**: P2 - additive capability gated on host adoption of the `io.modelcontextprotocol/ui` capability, which is not yet common; not urgent, but cheap to land ahead of demand.
- **Effort**: Medium - layers a new `_ResourceEntry` variant and a `ui://` scheme onto the existing resource index/list/read handlers in `resources.py`; no new server or transport.
- **Risk**: Low - purely additive; clients that have not negotiated the `ui` capability simply never resolve `ui://` resources, so existing resource behavior is unaffected.
- **Breaking Change**: No.

## Program Design

### Types

- `_ResourceEntry.mime_type: str` (existing field; new call sites pass `"text/html;profile=mcp-app"`)

### Signatures

- `_interactive_resource_entry(config: BRConfig, tool_name: str, html: str) -> _ResourceEntry`
- `build_resource_index(config: BRConfig) -> dict[str, _ResourceEntry]` (existing; gains `ui://`-scheme entries)

### Call Path

`build_resource_index` -> `_interactive_resource_entry` -> `make_list_resources_handler` / `_read_body` (existing `resources/list` and `resources/read` handlers, unchanged dispatch)

## Scope Boundaries

- Out of scope: implementing a new transport, server, or browser-tab render target — this is a content type on the existing resource surface only.
- Out of scope: defining host↔view interaction ownership semantics — that contract is ENH-3307's scope, not this issue's.
- Out of scope: building ahead of host support; land the plumbing but do not invest in host-specific rendering workarounds while `io.modelcontextprotocol/ui` adoption remains rare.

## Scope

- One new resource content type on the existing resource surface, not a new server or transport.
- Treat this as cheap optionality on existing plumbing (the current facade over library functions) rather than a commitment to build ahead of host support — payoff is contingent on hosts actually declaring the `io.modelcontextprotocol/ui` capability, which is not yet common.
- Any interaction this content type exposes must be governed by whatever contract defines what an artifact may do when a user acts on it and who owns the resulting FSM transition afterward — do not let this content type invent its own ad hoc interaction semantics.
- Complements, rather than competes with, a planned local read-only SSE bridge for live artifact dashboards in a browser tab — different render target, different data-access assumptions.

## Status

Open.


## Session Log
- `/ll:format-issue` - 2026-08-24T00:04:16 - `9d912d1c-def8-4ac1-b2d0-73ed036e9de0.jsonl`
