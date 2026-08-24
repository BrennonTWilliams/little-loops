---
id: ENH-3306
title: Add an interactive-resource content type to ll-mcp (HTML with event callbacks)
type: ENH
priority: P2
status: done
discovered_date: '2026-08-23'
completed_at: '2026-08-24T20:16:11Z'
parent: EPIC-3127
blocked_by:
- ENH-3307
relates_to:
- ENH-3035
labels:
- mcp
- artifact
learning_tests_required:
- mcp
confidence_score: 100
outcome_confidence: 83
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 25
---

## Summary

Add an interactive-resource content type to `ll-mcp`: resources that resolve to interactive HTML with event callbacks, rendered by the host session rather than a browser tab. This is an MCP Apps–compliant content type layered onto `ll-mcp`'s existing resource surface — not a new server or transport.

**Concrete deliverable (first view):** one `ui://issues/view` resource, linked from the existing `issue_get` tool via `_meta.ui.resourceUri`, whose HTML renders the `issue_get` result (frontmatter table + body) and implements the minimal MCP Apps handshake on the view side. The "event callbacks" half is scoped to exactly that handshake — receiving `ui/notifications/tool-result` and emitting level-1 (`ui/message`) interactions per ENH-3307; no level-2/3 re-entry into the FSM is built here.

**Dependency decision:** this issue was `blocked_by: ENH-3307` (the contract had to exist before the view emits anything) — ENH-3307 is now `done` (its output is `docs/reference/ARTIFACT_CONTROL_LEVELS.md`), so that dependency is resolved. ENH-3035 / FEAT-3036 are deliberately excluded from that edge — those build the browser-tab `ll-artifact` template kit, a different render target. If ENH-3035 lands first, the view's page shell/token stamping should adopt the kit; otherwise the template stays a small standalone file (`related:` only).

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

## Design decisions (resolved 2026-08-23 review)

- **Which view / which tool**: `ui://issues/view`, declared on `issue_get` (`tools.py:601`) via `_meta.ui.resourceUri`. One view only; no generic per-tool registry.
- **Where the HTML lives**: package data at `scripts/little_loops/mcp_server/templates/issues-view.html` (mirrors the `scripts/little_loops/templates/` package-data convention in CLAUDE.md; add to `pyproject.toml` package-data if not glob-covered). This keeps `_ResourceEntry.path: Path` (`resources.py:63`) **unchanged** — the new kind reads from disk like every existing kind. Do not widen `path` to `Path | None` or pass inline `html: str`.
- **Enumeration gating**: `resources/list` advertises `ui://` entries **unconditionally**. The spec permits it, clients that did not negotiate `io.modelcontextprotocol/ui` ignore unknown MIME types, and it avoids threading per-request client capabilities into `build_resource_index()`. Capability negotiation is *not* ENH-3307's concern (that is a journey-ownership contract, not protocol negotiation); it is simply out of scope here. `mcp.server.apps._require_ui_scheme` may be reused for URI validation; `client_supports_apps()` is not wired.
- **Staleness/refresh**: the `ui://` entry is static — do not add it to `_watched_paths()`. It must be counted in pagination totals (`test_enh_3174_mcp_resources_pagination.py`) and the exact-set assertion in `test_mcp_server.py:372-376`.
- **View-side messaging**: the template's inline JS must (a) handle `ui/notifications/tool-result` by rendering the payload, (b) emit only `ui/message` (ENH-3307 level 1 — notify), (c) handle `ui/resource-teardown`. No `tools/call` from the view in this issue. It must **ignore unrecognized methods silently** rather than throw — the spec's host→view push set also includes `ui/notifications/tool-input`, `ui/notifications/tool-cancelled`, and `ui/notifications/size-changed`, none of which this view acts on, and a host is free to send them.
- **No resource-level `_meta.ui`; no CSP declaration**: the template is fully self-contained — no external stylesheets, fonts, images, `fetch`/`XHR`, or any other network reference. Because it requests nothing off-origin, the SDK's `ResourceCsp`/`ResourcePermissions` (§ SDK Facts) are left undeclared and the host's default sandbox applies. This is a **deliberate decision, not an oversight**: it is what makes AC "`_ResourceEntry` dataclass fields are unchanged" viable, since the frozen dataclass has no field to carry per-resource `_meta`. If a future view ever needs CSP or iframe permissions, `_ResourceEntry` gains a `meta` field then — not now.
- **Path resolution for package data**: `_ui_entries` cannot build `path` from `config.project_root` the way every other `_<kind>_entries` helper does — the template ships inside the wheel. Resolve it via `importlib.resources`, following the in-package precedent at `server.py:67`. See § Program Design for the exact shape.
- **Missing-template behavior**: always emit the entry; do **not** follow `_goals_entry`'s "return `None` when the file is absent" pattern. A missing `.ll/ll-goals.md` is a legitimately-empty project; a missing package asset is a packaging bug, and it should surface as a read-time `MCPError` naming the URI rather than vanishing from `resources/list`.

## Impact

- **Priority**: P2 - additive capability gated on host adoption of the `io.modelcontextprotocol/ui` capability, which is not yet common; not urgent, but cheap to land ahead of demand.
- **Effort**: Medium - layers a new `_ResourceEntry` variant and a `ui://` scheme onto the existing resource index/list/read handlers in `resources.py`; no new server or transport.
- **Risk**: Low - purely additive; clients that have not negotiated the `ui` capability simply never resolve `ui://` resources, so existing resource behavior is unaffected.
- **Breaking Change**: No.

## Integration Map

### Files to Modify

- `scripts/little_loops/mcp_server/resources.py` — add a new `_ui_entries(config)` helper following the existing `_<kind>_entries`/`_<kind>_entry` convention (`_issue_entries` @ :69, `_goals_entry` @ :121, `_docs_entries` @ :136), returning the single `ui://issues/view` entry with `kind="ui"` and `path` pointing at the package-data template; extend `build_resource_index()` (:167) to merge it into the flat `uri -> _ResourceEntry` dict; extend `_read_body()`'s `entry.kind` dispatch (:269-274) with `"ui"` (reads `entry.path`, same as docs); update the `kind` comment on the dataclass (:65)
- `scripts/little_loops/mcp_server/templates/issues-view.html` — **new** package-data file: the view HTML + inline JS handshake
- `scripts/little_loops/mcp_server/tools.py:601` — add `meta={"ui": {"resourceUri": "ui://issues/view"}}` to the `issue_get` tool definition; no `types.Tool(...)` call site in this codebase sets a `meta`/`_meta` field today (the only other `_meta` handling, `tasks.py:280`, reads a client-supplied request `_meta`, not a server-declared `Tool._meta`) — this is new ground, not an extension of an existing pattern. **SDK field name resolved (see § SDK Facts) — use `meta=`, not `_meta=`.**
- `scripts/pyproject.toml` — no change needed; `mcp_server/templates/*.html` is already covered by the existing `include = ["little_loops/**"]` glob (:202) since the new template lives inside the package tree — see § Codebase Research Findings under Integration Map
- `scripts/little_loops/package_data.py` — register the new template in `PACKAGE_DATA_ASSETS` (e.g. `("mcp_server", "templates", "issues-view.html")`) — see § Codebase Research Findings under Integration Map

### Dependent Files (Callers/Importers)

- `scripts/little_loops/mcp_server/server.py:174` — imports `ResourceIndex`, `make_list_resources_handler`, `make_read_resource_handler` from `resources.py`; wires `resource_index = ResourceIndex(config)` (:194) and registers `on_list_resources=`/`on_read_resource=` handlers (:226-227)

### Conventions in Force

- Resource-entry constructors take only `config: BRConfig`, do their own filesystem/lookup internally, and build a `_ResourceEntry(...)` directly — evidence: `resources.py:69` (`_issue_entries`), `:121` (`_goals_entry`), `:136` (`_docs_entries`)
- `build_resource_index()` merges each helper's output into one flat `uri -> _ResourceEntry` dict keyed by full URI, not by scheme — evidence: `resources.py:167-180`
- `_read_body()` dispatches on `entry.kind` (a short string literal documented inline on the dataclass), never on `mime_type` or on the URI scheme — evidence: `resources.py:269-274`, `resources.py:65`
- Every URI in this file today lives under a single `ll://` scheme; no code parses or switches on a URI scheme anywhere in `resources.py` — adding `ui://` would be this file's first multi-scheme dispatch, with no existing precedent to model it on
- `mcp.resources.*` config knobs default to unset (a no-op) and are read directly off `config.mcp.resources.<key>` inside the relevant `_<kind>_entries` function, not through a shared scoping abstraction — evidence: `config-schema.json:629-650`, `resources.py:84`, `:145`

_Wiring pass added by `/ll:wire-issue`:_
- FYI: the pinned `mcp` SDK (2.0.0) already ships an `EXTENSION_ID` literally named `io.modelcontextprotocol/ui` in `mcp.server.apps`, reachable via `MCPServer(extensions=[...])` — but `scripts/little_loops/mcp_server/server.py`'s `build_server()` constructs the lowlevel `Server`, which has no `extensions` parameter, so this SDK-native capability-negotiation mechanism is not currently wired up. Out of this issue's scope (capability negotiation is ENH-3307/host territory), but relevant background for whoever implements it next [Agent 2 finding, `.ll/learning-tests/mcp-extension-mechanism.md`]

### Tests

- `scripts/tests/test_mcp_server.py` — drives the full server via the SDK `Client` over the wire protocol (`client.list_resources()`, `client.read_resource(uri)`); `test_list_resources_returns_issues_goals_and_docs_with_cache_metadata` (:357-383) and `test_read_resource_outside_enumeration_is_rejected` (:430-447) are the closest existing shape for asserting a new resource kind's list/read/rejection behavior
- `scripts/tests/test_enh_3174_mcp_resources_pagination.py` — pagination-focused resource tests; guarded by `pytest.importorskip("mcp")` since the `mcp` extra is optional
- No existing test exercises a non-text `_ResourceEntry` content type — every `Read...Result` constructed today is `types.TextResourceContents` (`resources.py:362`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_mcp_server.py:369-374` (`test_list_resources_returns_issues_goals_and_docs_with_cache_metadata`) — asserts `uris == {...}` as an **exact set**, not a subset. Since `build_resource_index` unconditionally adds the `ui://` entry to every server instance (§ Design decisions), this test **must** be updated to include `"ui://issues/view"` in the expected set. (An earlier wiring pass offered "or conditionally enumerate interactive entries only when a tool declares `_meta.ui.resourceUri`" as an alternative — that is settled: enumeration is unconditional, so updating the test is the only path.) [Agent 2 finding]
- **Pinned counts that will break** — `scripts/tests/test_enh_3174_mcp_resources_pagination.py:87` (`assert len(seen) == 5`) and `:107` (`assert len(result.resources) == 5`) both hardcode the index size and become `6`. Both fixtures build a 5-entry index; the `ui://` entry makes 6.
- New test: `resources/list` assertion that a `ui://`-scheme entry appears with `mime_type == "text/html;profile=mcp-app"`, following the pattern at `test_mcp_server.py:357-383` [Agent 3 finding]
- New test: `resources/read` assertion that the HTML body round-trips through `TextResourceContents.text` (MCP Apps HTML transports as `text`, not `blob` — no `BlobResourceContents` precedent exists in this codebase), following the pattern at `test_mcp_server.py:416-427` [Agent 3 finding]
- New test: negative-path coverage for an unregistered `ui://` URI, extending the parametrized bad-URI loop in `test_read_resource_outside_enumeration_is_rejected` (`test_mcp_server.py:430-447`) [Agent 3 finding]
- New test: `list_tools` assertion that `_meta.ui.resourceUri == "ui://issues/view"` is present on `issue_get` — no existing test in `test_feat_3149_mcp_mutation_tools.py` or elsewhere inspects `Tool._meta`/`Tool.meta`, so this is new ground with no in-repo template [Agent 3 finding]
- New test: the served HTML contains the handshake markers — string assertions for `ui/notifications/tool-result`, `ui/message`, and `ui/resource-teardown` in the `resources/read` body — so the view-side contract is enforced without a browser
- New test: `ui://issues/view` is **not** in `_watched_paths()` and pagination totals include it (extend `test_enh_3174_mcp_resources_pagination.py`)
- New test: the served HTML is self-contained — assert the body contains no `http://`/`https://` references and no `fetch(`/`XMLHttpRequest`, so the no-network/no-CSP decision can't silently regress
- New test: the served HTML references `structuredContent` (the primary payload path) — cheap guard that the template didn't get written against `content[0].text` alone
- New test: `_ui_entries` resolves its path under `importlib.resources.files("little_loops")`, not under the project root — assert the entry's `path` is not relative to the tmp-path project root, so a future refactor can't quietly reintroduce a project-relative lookup
- New test: a missing template yields an `MCPError` from `resources/read` (monkeypatch the path) while the entry still appears in `resources/list`
- New test: `pytest.importorskip("mcp")` guard on all of the above, matching the existing pattern

### Documentation

- `docs/guides/MCP_SERVER_GUIDE.md` — describes the resource surface (`ll://` scheme, staleness/refresh, `resources/read` usage); needs a section for the new `ui://` scheme, the unconditional-advertise decision, and a cross-link to ENH-3307's contract doc (`docs/reference/ARTIFACT_CONTROL_LEVELS.md`) stating the view operates at level 1

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:103` — the `little_loops.mcp_server` package-index row enumerates the `ll://` resource surface by scheme/kind (`ll://issues/<ID>`, `ll://goals`, `ll://docs/<relative-path>`); needs a `ui://` clause added [Agent 2 finding]
- `docs/reference/CLI.md` — the `ll-mcp` entry's "Also advertises a `resources` capability" paragraph (locate by string; the line number has drifted across passes) enumerates the same URI/scheme list plus what `resources/read` returns per kind; needs a parallel clause for the `ui://` interactive-HTML kind [Agent 2 finding]

### Configuration

- N/A — no new config knob is implied by this issue's scope; existing `mcp.resources.*` keys (`config-schema.json:629-650`) scope enumeration for the existing kinds only

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- Package-data mechanism: `scripts/little_loops/mcp_server/templates/` sits inside `little_loops/` (the package root), so it is already covered by the plain `include = ["little_loops/**"]` glob (`pyproject.toml:202`) — **no `hatch_build.py` hook is needed.** That hook (`hatch_build.py`'s `SkillsForceIncludeHook`) exists solely for `skills/`, which lives *outside* the package tree at the repo root (`hatch_build.py` docstring, `pyproject.toml:204-219`); it does not apply here. Existing precedent: `scripts/little_loops/templates/policy-router-builder.html.tmpl` and `policy_builder_core.mjs` already ship this way today, with no build hook. (An earlier refine pass asserted the opposite — that a `hatch_build.py` hook was required because Hatchling's `force-include` hard-fails on a not-yet-existing path. That finding was wrong for this case and has been removed; do not re-add a build hook for this template.)
- New gap: the new `issues-view.html` template must be registered in `scripts/little_loops/package_data.py`'s `PACKAGE_DATA_ASSETS` manifest (e.g. `("mcp_server", "templates", "issues-view.html")`) — every runtime-read package asset must appear there or `test_package_data_manifest.py`'s completeness check gives a false-green result for it (the manifest's own docstring: "Omitting an entry gives a false-green completeness result"). `scripts/little_loops/package_data.py` is not currently listed under Files to Modify and should be added.
- Doc citation resolved: `docs/reference/CLI.md`'s "Also advertises a `resources` capability" paragraph (FEAT-3136/ENH-3172/ENH-3174) has drifted repeatedly (cited as 4773-4783, then 4799-4809, then 4800-4808 across passes). **Do not trust any line number for it** — locate the paragraph by its "Also advertises a `resources` capability" opening string. Line-number citations for this paragraph have been stripped from the Acceptance Criteria for the same reason.
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md` now exists (landed via ENH-3307) and already cross-references ENH-3306 at lines 6, 14, 57, and 90-104; `docs/guides/MCP_SERVER_GUIDE.md` already links back to it at lines 618-620. The cross-link this issue's Documentation section calls for is largely already in place on both sides — verify rather than re-add.
- Resource-kind convention confirmed: `_ResourceEntry.kind` is a closed string-literal set documented in a comment at `resources.py:65` (`# "issue" | "goals" | "docs"`) — adding a `"ui"` kind means extending that comment. `build_resource_index()` (`resources.py:167`) merges each kind's helper output into one dict keyed by `entry.uri` with no collision detection (relies on each kind owning a disjoint URI prefix). Each existing `_read_<kind>_body()` raises `MCPError(code=types.INVALID_PARAMS, message=..., data={"uri": entry.uri})` on failure — the identical shape repeated verbatim three times (`resources.py:236-240`, `250-254`, `262-266`); a new `_read_ui_body()` follows this same shape for consistency with existing kinds.
- No precedent exists anywhere in `tools.py` for setting a `meta`/`_meta` field on a declared `types.Tool` — all ten `types.Tool(...)` call sites checked (`tools.py:567, 600, 615, 640, 648, 658, 704, 748, 797, 834`); none passes `meta`/`_meta`. `tasks.py:280` reads the *incoming request's* `_meta` (`ctx.meta`), a different thing from a server-declared `Tool._meta`. Confirms this issue's `_meta.ui.resourceUri` addition to `issue_get` (`tools.py:601`) is new ground with no in-repo template to model against.

### SDK Facts (verified against the pinned `mcp==2.0.0`, 2026-08-24)

These were previously deferred to the learning test. They are resolved; the learning test now only needs to pin them against future SDK bumps.

- **`Tool` meta field**: the field is `meta`, declared with `alias="_meta"`. Both `types.Tool(meta={...})` and `types.Tool(_meta={...})` construct successfully; `model_dump(by_alias=True)` emits `"_meta"` either way. **Use `meta=`** — plain field name, consistent with every other snake_case kwarg at the existing `types.Tool(...)` call sites (`input_schema=`, not `inputSchema=`).
- **URI fields are plain `str`, not `AnyUrl`**: both `types.Resource.uri` and `types.ReadResourceRequestParams.uri` annotate as `str` in 2.0.0. This is why a `ui://` scheme round-trips without normalization or rejection, and why `index.entries.get(params.uri)` (`resources.py:277`) works as a plain dict lookup. **This is the single most likely way this feature silently breaks on an SDK upgrade** — if either field ever becomes `AnyUrl`, a `ui://` authority may be normalized (trailing-slash) or rejected outright. The learning test should assert both annotations.
- **Reuse SDK constants**: `mcp.server.apps` exports `APP_MIME_TYPE = "text/html;profile=mcp-app"` and `EXTENSION_ID = "io.modelcontextprotocol/ui"`. `resources.py` already imports `mcp` at module scope (the module is only importable when the `mcp` extra is installed), so import `APP_MIME_TYPE` rather than hardcoding the MIME string — self-documenting and it tracks the SDK.
- **The SDK models more `_meta.ui` than this issue uses**: `mcp.server.apps` defines `ResourceCsp` (`connectDomains`/`resourceDomains`/`frameDomains`/`baseUriDomains`), `ResourcePermissions` (camera/microphone/geolocation/clipboardWrite), and `Visibility` (`"model" | "app"`). This issue declares **only** `resourceUri` on the tool and **no** resource-level `_meta.ui` at all — see the CSP decision under § Design decisions.
- Test precedent: `scripts/tests/test_mcp_server.py:357-448` is the resource-surface test family (list/read/reject scaffold via `_make_project` + `build_server` + SDK `Client`); the reject test (`:430-447`) folds path-traversal and unknown-scheme cases into one parametrized test rather than splitting them. `scripts/tests/test_package_data_manifest.py` backs the completeness check the new template's manifest entry must satisfy; `scripts/tests/test_wheel_smoke.py::TestWheelSmoke::test_skills_force_include_accessible` is the closest real-wheel-build precedent but is specific to the force-include (skills/) case, not the plain-glob case this template falls under.

## Program Design

### Types

- `_ResourceEntry` — unchanged shape; new call site passes `mime_type=APP_MIME_TYPE` (imported from `mcp.server.apps`), `kind="ui"`, `path=<package template path>`

### Signatures

- `_ui_entries(config: BRConfig) -> list[_ResourceEntry]`
- `_read_ui_body(entry: _ResourceEntry) -> str`
- `build_resource_index(config: BRConfig) -> dict[str, _ResourceEntry]` (existing; gains the `ui://issues/view` entry)

`_ui_entries` takes `config` for signature consistency with the other `_<kind>_entries` helpers but does not read it — the template path is package-relative, not project-relative:

```python
path = (
    Path(str(importlib.resources.files("little_loops")))
    / "mcp_server" / "templates" / "issues-view.html"
)
```

This is the first `_ResourceEntry.path` that does not live under `config.project_root`. Access control is unaffected: the entire `resources/read` boundary is the `index.entries.get(params.uri)` dict lookup (`resources.py:277`), and no filesystem read happens before or instead of it.

`_read_ui_body` mirrors `_read_docs_body` verbatim — `entry.path.read_text()` wrapped in `try/except OSError`, re-raised as `MCPError(code=types.INVALID_PARAMS, message=f"UI resource unreadable: {exc}", data={"uri": entry.uri})`.

**Insert the `"ui"` branch above the fallthrough.** `_read_body` (`resources.py:270-274`) dispatches with two `if`s and a bare `return _read_docs_body(entry)` default. A `"ui"` kind that falls through happens to *work* (both are `read_text()`), but reports "Docs resource unreadable" on failure — a misleading error for a packaging bug.

### View-side payload shape

The `ui/notifications/tool-result` payload for `issue_get` is determined by `make_call_tool_handler` (`tools.py:963-967`): `_tool_issue_get` returns a **dict** (`_parse_card_fields`), so the result carries **both** `structuredContent` (the dict, since the dict-only guard passes) and `content[0].text` (`json.dumps(payload)`). The template should read `structuredContent` first and fall back to `JSON.parse(content[0].text)`.

### Open question — view-side readiness handshake

How the view signals it is mounted before the host pushes `ui/notifications/tool-result` is not pinned here. Resolve it against the MCP Apps extension spec (stable 2026-01-26) at implementation time; the pinned SDK's `mcp.server.apps` encodes the message names and is the first place to check.

### Call Path

`build_resource_index` -> `_ui_entries` -> `make_list_resources_handler` / `_read_body` -> `_read_ui_body` (existing `resources/list` and `resources/read` handlers, one new `kind` branch)

## Acceptance Criteria

- [ ] `resources/list` includes `ui://issues/view` with `mimeType == "text/html;profile=mcp-app"`, unconditionally (no capability gating).
- [ ] `resources/read` on `ui://issues/view` returns the template as `TextResourceContents.text`; any other `ui://` URI is rejected like other unregistered URIs.
- [ ] `list_tools` shows `issue_get` with `_meta.ui.resourceUri == "ui://issues/view"` on the wire (declared as `meta=`, serialized under the `_meta` alias); no other tool carries `_meta.ui`.
- [ ] The template's inline JS handles `ui/notifications/tool-result` and `ui/resource-teardown`, and emits only `ui/message` (ENH-3307 level 1). Unrecognized methods (`tool-input`, `tool-cancelled`, `size-changed`, anything else) are ignored silently, not thrown on.
- [ ] The template is fully self-contained: no external stylesheets, fonts, images, `fetch`/`XHR`, or other off-origin references. No resource-level `_meta.ui` (CSP/permissions) is declared.
- [ ] The template reads the tool result from `structuredContent`, falling back to `JSON.parse(content[0].text)`.
- [ ] `_ResourceEntry` dataclass fields are unchanged; `ui://` is not in `_watched_paths()`.
- [ ] The template path resolves via `importlib.resources`, not `config.project_root`; a missing template surfaces as an `MCPError` naming the URI on `resources/read`, and the entry still appears in `resources/list`.
- [ ] Existing tests updated and green: `test_mcp_server.py:369-374` exact-set, and the hardcoded `== 5` counts at `test_enh_3174_mcp_resources_pagination.py:87` and `:107`. New tests per the Tests subsection.
- [ ] `MCP_SERVER_GUIDE.md`, `docs/reference/API.md:103`, and `docs/reference/CLI.md`'s "Also advertises a `resources` capability" paragraph (locate by string — its line number has drifted repeatedly) updated; guide cross-links `docs/reference/ARTIFACT_CONTROL_LEVELS.md`.
- [ ] Template file ships in the wheel (package-data check) and is registered in `PACKAGE_DATA_ASSETS`.
- [ ] Learning test pins the § SDK Facts assertions — `Tool` field `meta`/alias `_meta`, and `Resource.uri` / `ReadResourceRequestParams.uri` annotating as `str`.

## Scope Boundaries

- Out of scope: implementing a new transport, server, or browser-tab render target — this is a content type on the existing resource surface only.
- Out of scope: defining host↔view interaction ownership semantics — that contract is ENH-3307's scope, not this issue's.
- Out of scope: building ahead of host support; land the plumbing but do not invest in host-specific rendering workarounds while `io.modelcontextprotocol/ui` adoption remains rare.
- Out of scope: client capability negotiation (`client_supports_apps()` / `MCPServer(extensions=[...])`) — entries are advertised unconditionally; negotiation is a follow-up if a real host needs it.
- Out of scope: level-2/level-3 interactions (`tools/call` from the view, FSM re-entry) — the first view is level-1 notify only.
- Out of scope: taking on the `ll-artifact` template kit (ENH-3035) or the artifact-templates design (FEAT-3036) as a prerequisite; adopt the kit opportunistically if it lands first.

## Scope

- One new resource content type on the existing resource surface, not a new server or transport.
- Treat this as cheap optionality on existing plumbing (the current facade over library functions) rather than a commitment to build ahead of host support — payoff is contingent on hosts actually declaring the `io.modelcontextprotocol/ui` capability, which is not yet common.
- Any interaction this content type exposes must be governed by whatever contract defines what an artifact may do when a user acts on it and who owns the resulting FSM transition afterward — do not let this content type invent its own ad hoc interaction semantics.
- Complements, rather than competes with, a planned local read-only SSE bridge for live artifact dashboards in a browser tab — different render target, different data-access assumptions.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_mcp_server.py` — resolve the exact-set assertion in `test_list_resources_returns_issues_goals_and_docs_with_cache_metadata` (:372-376) so it doesn't break when a `ui://` entry is added
- Add tests to `scripts/tests/test_mcp_server.py` — `ui://` list/read/reject coverage per the Tests subsection above
- Update `docs/reference/API.md` (:103) and `docs/reference/CLI.md` ("Also advertises a `resources` capability" paragraph — locate by string, not line number) — add the `ui://` scheme to the existing resource-scheme enumeration

## Status

Open — no longer blocked; ENH-3307 is `done` and its contract doc (`docs/reference/ARTIFACT_CONTROL_LEVELS.md`) exists.


## Session Log
- `/ll:manage-issue` - 2026-08-24T20:15:56 - `7f5298a9-684e-4e01-a282-d2112e18f747.jsonl`
- `/ll:confidence-check` - 2026-08-24T19:31:59 - `e1cc4296-ee28-47c9-bc20-a4dc3f372a09.jsonl`
- `/ll:confidence-check` - 2026-08-24T19:20:04 - `848282c0-0b6c-443d-872b-4aeef5e9eeab.jsonl`
- `/ll:refine-issue` - 2026-08-24T19:01:36 - `d2894239-e4a9-46b6-b02b-e19d64169f3a.jsonl`
- `/ll:refine-issue` - 2026-08-24T18:20:18 - `bf2ea761-d864-4b19-8078-67d47afee296.jsonl`
- `/ll:confidence-check` - 2026-08-24T01:05:48 - `b39154ec-0980-409b-84ab-ed4ad74fd627.jsonl`
- `/ll:wire-issue` - 2026-08-24T00:58:35 - `4cd71d49-8da8-4dc9-852e-8f17b59fed46.jsonl`
- `/ll:refine-issue` - 2026-08-24T00:51:42 - `9c480c31-6e54-4a77-8e21-d400559417c0.jsonl`
- `/ll:format-issue` - 2026-08-24T00:04:16 - `9d912d1c-def8-4ac1-b2d0-73ed036e9de0.jsonl`
