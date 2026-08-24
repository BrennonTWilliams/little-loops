---
id: 3306
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

## Background / Motivation

`ll-mcp` maps MCP's three core primitives (tools, resources, prompts) onto little-loops' CLI/files/skills trichotomy. That design has no UI surface today — dashboard/artifact UX is served by separate htmx explorations targeting a browser tab, not a chat host. The MCP Apps extension to the Model Context Protocol adds exactly this: a resource content type that a host renders inline as a sandboxed interactive app, where UI-originated interactions post back to the host rather than to the resource's own backend — the host decides what happens next, not the resource.

## Design constraints (checked against the MCP Apps extension spec, stable release 2026-01-26)

- **URI scheme**: the spec normatively requires interactive-UI resource URIs to start with `ui://` ("URI MUST start with `ui://`"). An existing data resource under a different scheme can stay as-is for non-interactive reads; the interactive view itself must be published as its own `ui://`-scheme resource — reusing an existing scheme for this is not spec-conformant.
- **MIME type**: interactive resources must declare `mimeType: "text/html;profile=mcp-app"`. Plain `text/html` is not sufficient for a host to recognize the resource as an MCP Apps view.
- **Linkage**: a tool that wants to render through this view declares it via `_meta.ui.resourceUri` on the tool definition; the host is required to `resources/read` that URI to fetch the view before rendering.
- **Capability negotiation**: a client only renders these resources if it declared the `io.modelcontextprotocol/ui` extension at `initialize`, with the supported `mimeTypes` listed. Real host adoption of this capability is the actual gate on payoff here — most current hosts do not declare it yet.
- **Host↔view messaging** is JSON-RPC 2.0 over `postMessage`: the view can request `tools/call`, `resources/read`, `ui/open-link`, `ui/message`, `ui/request-display-mode`, `ui/update-model-context`; the host pushes `ui/notifications/tool-input`, `ui/notifications/tool-result`, `ui/notifications/tool-cancelled`, `ui/notifications/size-changed`, and a `ui/resource-teardown` cleanup signal.

## Scope

- One new resource content type on the existing resource surface, not a new server or transport.
- Treat this as cheap optionality on existing plumbing (the current facade over library functions) rather than a commitment to build ahead of host support — payoff is contingent on hosts actually declaring the `io.modelcontextprotocol/ui` capability, which is not yet common.
- Any interaction this content type exposes must be governed by whatever contract defines what an artifact may do when a user acts on it and who owns the resulting FSM transition afterward — do not let this content type invent its own ad hoc interaction semantics.
- Complements, rather than competes with, a planned local read-only SSE bridge for live artifact dashboards in a browser tab — different render target, different data-access assumptions.

## Status

Open.
