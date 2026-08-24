---
id: ENH-3306
title: Add an interactive-resource content type to ll-mcp (HTML with event callbacks)
type: ENH
priority: P2
status: open
discovered_date: '2026-08-23'
parent: EPIC-3127
labels:
- mcp
- artifact
learning_tests_required:
- mcp
confidence_score: 100
outcome_confidence: 74
score_complexity: 16
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 22
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

## Integration Map

### Files to Modify

- `scripts/little_loops/mcp_server/resources.py` — add a new `_interactive_resource_entry(config, tool_name, html)` helper following the existing `_<kind>_entries`/`_<kind>_entry` convention (`_issue_entries` @ :69, `_goals_entry` @ :121, `_docs_entries` @ :136); extend `build_resource_index()` (:167) to merge its results into the flat `uri -> _ResourceEntry` dict; extend `_read_body()`'s `entry.kind` dispatch (:269-274) with a new kind for interactive HTML bodies
- `scripts/little_loops/mcp_server/tools.py` — add `_meta.ui.resourceUri` to whichever tool(s) render through this view; no `types.Tool(...)` call site in this codebase sets a `meta`/`_meta` field today (the only other `_meta` handling, `tasks.py:280`, reads a client-supplied request `_meta`, not a server-declared `Tool._meta`) — this is new ground, not an extension of an existing pattern

### Dependent Files (Callers/Importers)

- `scripts/little_loops/mcp_server/server.py:174` — imports `ResourceIndex`, `make_list_resources_handler`, `make_read_resource_handler` from `resources.py`; wires `resource_index = ResourceIndex(config)` (:194) and registers `on_list_resources=`/`on_read_resource=` handlers (:226-227)

### Conventions in Force

- Resource-entry constructors take only `config: BRConfig`, do their own filesystem/lookup internally, and build a `_ResourceEntry(...)` directly — evidence: `resources.py:69` (`_issue_entries`), `:121` (`_goals_entry`), `:136` (`_docs_entries`)
- `build_resource_index()` merges each helper's output into one flat `uri -> _ResourceEntry` dict keyed by full URI, not by scheme — evidence: `resources.py:167-180`
- `_read_body()` dispatches on `entry.kind` (a short string literal documented inline on the dataclass), never on `mime_type` or on the URI scheme — evidence: `resources.py:269-274`, `resources.py:65`
- Every URI in this file today lives under a single `ll://` scheme; no code parses or switches on a URI scheme anywhere in `resources.py` — adding `ui://` would be this file's first multi-scheme dispatch, with no existing precedent to model it on
- `mcp.resources.*` config knobs default to unset (a no-op) and are read directly off `config.mcp.resources.<key>` inside the relevant `_<kind>_entries` function, not through a shared scoping abstraction — evidence: `config-schema.json:629-650`, `resources.py:84`, `:145`

_Wiring pass added by `/ll:wire-issue`:_
- FYI: the pinned `mcp` SDK (2.0.0) already ships an `EXTENSION_ID` literally named `io.modelcontextprotocol/ui` in `server/apps.py`, reachable via `MCPServer(extensions=[...])` — but `scripts/little_loops/mcp_server/server.py`'s `build_server()` constructs the lowlevel `Server`, which has no `extensions` parameter, so this SDK-native capability-negotiation mechanism is not currently wired up. Out of this issue's scope (capability negotiation is ENH-3307/host territory), but relevant background for whoever implements it next [Agent 2 finding, `.ll/learning-tests/mcp-extension-mechanism.md`]

### Tests

- `scripts/tests/test_mcp_server.py` — drives the full server via the SDK `Client` over the wire protocol (`client.list_resources()`, `client.read_resource(uri)`); `test_list_resources_returns_issues_goals_and_docs_with_cache_metadata` (:357-383) and `test_read_resource_outside_enumeration_is_rejected` (:430-447) are the closest existing shape for asserting a new resource kind's list/read/rejection behavior
- `scripts/tests/test_enh_3174_mcp_resources_pagination.py` — pagination-focused resource tests; guarded by `pytest.importorskip("mcp")` since the `mcp` extra is optional
- No existing test exercises a non-text `_ResourceEntry` content type — every `Read...Result` constructed today is `types.TextResourceContents` (`resources.py:362`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_mcp_server.py:372-376` (`test_list_resources_returns_issues_goals_and_docs_with_cache_metadata`) — asserts `uris == {...}` as an **exact set**, not a subset; if `build_resource_index` unconditionally adds a `ui://` entry to every server instance, this test breaks. Must be updated, or the design must conditionally enumerate interactive entries only when a tool declares `_meta.ui.resourceUri` [Agent 2 finding]
- New test: `resources/list` assertion that a `ui://`-scheme entry appears with `mime_type == "text/html;profile=mcp-app"`, following the pattern at `test_mcp_server.py:357-383` [Agent 3 finding]
- New test: `resources/read` assertion that the HTML body round-trips through `TextResourceContents.text` (MCP Apps HTML transports as `text`, not `blob` — no `BlobResourceContents` precedent exists in this codebase), following the pattern at `test_mcp_server.py:416-427` [Agent 3 finding]
- New test: negative-path coverage for an unregistered `ui://` URI, extending the parametrized bad-URI loop in `test_read_resource_outside_enumeration_is_rejected` (`test_mcp_server.py:430-447`) [Agent 3 finding]
- New test: `list_tools` assertion that `_meta.ui.resourceUri` is present on the tool(s) that render through this view — no existing test in `test_feat_3149_mcp_mutation_tools.py` or elsewhere inspects `Tool._meta`/`Tool.meta`, so this is new ground with no in-repo template [Agent 3 finding]

### Documentation

- `docs/guides/MCP_SERVER_GUIDE.md` — describes the resource surface (`ll://` scheme, staleness/refresh, `resources/read` usage); would need a section for the new `ui://` scheme and its capability-negotiation gate

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:103` — the `little_loops.mcp_server` package-index row enumerates the `ll://` resource surface by scheme/kind (`ll://issues/<ID>`, `ll://goals`, `ll://docs/<relative-path>`); needs a `ui://` clause added [Agent 2 finding]
- `docs/reference/CLI.md:4773-4783` — the `ll-mcp` entry's "Also advertises a `resources` capability" paragraph enumerates the same URI/scheme list plus what `resources/read` returns per kind; needs a parallel clause for the `ui://` interactive-HTML kind [Agent 2 finding]

### Configuration

- N/A — no new config knob is implied by this issue's scope; existing `mcp.resources.*` keys (`config-schema.json:629-650`) scope enumeration for the existing kinds only

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_mcp_server.py` — resolve the exact-set assertion in `test_list_resources_returns_issues_goals_and_docs_with_cache_metadata` (:372-376) so it doesn't break when a `ui://` entry is added
- Add tests to `scripts/tests/test_mcp_server.py` — `ui://` list/read/reject coverage per the Tests subsection above
- Update `docs/reference/API.md` (:103) and `docs/reference/CLI.md` (:4773-4783) — add the `ui://` scheme to the existing resource-scheme enumeration

## Status

Open.


## Session Log
- `/ll:confidence-check` - 2026-08-24T01:05:48 - `b39154ec-0980-409b-84ab-ed4ad74fd627.jsonl`
- `/ll:wire-issue` - 2026-08-24T00:58:35 - `4cd71d49-8da8-4dc9-852e-8f17b59fed46.jsonl`
- `/ll:refine-issue` - 2026-08-24T00:51:42 - `9c480c31-6e54-4a77-8e21-d400559417c0.jsonl`
- `/ll:format-issue` - 2026-08-24T00:04:16 - `9d912d1c-def8-4ac1-b2d0-73ed036e9de0.jsonl`
