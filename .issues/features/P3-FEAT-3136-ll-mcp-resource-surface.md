---
id: 3136
title: 'll-mcp: ll:// resource surface'
type: FEAT
priority: P3
status: done
labels:
- multi-host
- mcp
parent: EPIC-3127
blocked_by:
- FEAT-3135
learning_tests_required:
- mcp
relates_to:
- FEAT-3132
verify_verdict: VALID
size: Large
reconcile_attempted: true
confidence_score: 95
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
completed_at: '2026-08-09T18:23:49Z'
---

# FEAT-3136: ll-mcp: ll:// resource surface

## Summary

The MCP resources surface for the `ll-mcp` server: issue files,
`ll-goals.md`, and docs, exposed under an `ll://` scheme (e.g.
`ll://issues/FEAT-042`, `ll://docs/…`). This builds on the running server
and dispatch loop from FEAT-3135 — it adds `resources/list` and
`resources/read` handling to the same server, resolved against a
discovery-time enumeration rather than arbitrary filesystem reads.

## Current Behavior

FEAT-3135 landed the `ll-mcp` server skeleton with a working stdio dispatch
loop and five read-only tools, but no `resources` capability: `Server(...)`
in `build_server()` registers only `on_list_tools=`/`on_call_tool=`, so
`resources/list` and `resources/read` are unhandled and `caps.resources` is
`None` (asserted directly by `test_mcp_server.py::test_discover_advertises_tools_only`).
There is no way for an MCP client to enumerate or read issue files,
`ll-goals.md`, or docs through the server.

## Expected Behavior

`ll-mcp` advertises a `resources` capability and serves issue files,
`ll-goals.md`, and docs under an `ll://` scheme (`ll://issues/<ID>`,
`ll://goals`, `ll://docs/...`). `resources/list` returns name/description
metadata (frontmatter-only, no full bodies) plus `ttlMs`/`cacheScope`;
`resources/read` returns a resource's full body plus the same caching
metadata, and rejects any path outside a discovery-time enumeration built
once at server startup — never performing a filesystem read derived
directly from client-supplied input.

## Use Case

An MCP client (e.g. an editor integration or another host CLI) connects to
`ll-mcp` over stdio and wants to pull the full text of `FEAT-042` or the
project's `ll-goals.md` into its own context without shelling out to
`ll-issues show` or reading the filesystem directly — it lists resources
under `ll://`, picks `ll://issues/FEAT-042`, and reads it back as a normal
MCP resource with cache metadata attached.

## Impact

- **Priority**: P3 - Read-only resource surface for the local-first `ll-mcp`
  server; not on a critical path, but blocks the parity FEAT-3137 (prompts)
  and downstream MCP clients need.
- **Effort**: Large - new SDK-kwarg registration, a new
  discovery-time-enumeration primitive (first stateful construct in
  `mcp_server/`, no existing precedent), and a new `docs/` walk, on top of
  reusing existing issue/goals read primitives.
- **Risk**: Medium - the discovery-time-enumeration/rejection boundary is
  new territory (no existing access-control precedent in this codebase per
  the Codebase Research Findings above); getting the allowlist wrong is a
  path-traversal risk since the server is exposed to arbitrary MCP clients.
- **Breaking Change**: No - additive capability on top of the FEAT-3135
  server; existing tools/list behavior is unaffected.

## Parent Issue

Decomposed from FEAT-3132: ll-mcp: core read-only server (tools, resources,
prompts-from-skills). This child covers the `ll://` resource surface; the
server skeleton, entry point, and tools surface are in FEAT-3135 (must land
first — this child registers its handlers on that server). Prompts-from-
skills is a separate sibling, FEAT-3137.

## Bind resource resolution at discovery, not at call time

The design does not yet say how a resource path is resolved. Because this
server exposes resources to arbitrary MCP clients, `little-loops` is the
loader and the trust boundary is external — unlike host-CLI-owned skill
loading elsewhere in the project, where the caller is already inside the
trust boundary.

- **Pre-enumerate supporting files at discovery time.** Walk the resource
  set once during startup and record the exact set of readable paths. A
  resource request then accepts a path that was enumerated, and is rejected
  otherwise. The server must never perform an arbitrary filesystem read
  derived from client-supplied input at call time — the enumeration, not
  path sanitization, is what makes traversal impossible.
- **Parse frontmatter only when listing.** `resources/list` needs name and
  description; reading full resource bodies at list time is both a context
  cost and an unnecessary widening of what is loaded. Fetch bodies on
  demand in `resources/read`.

This boundary must carry forward to the future mutation tier, where it
widens.

## Spec assumptions (MCP 2026-07-28)

- **Caching metadata is part of the contract.** `resources/list` and
  `resources/read` responses MUST include `ttlMs` and `cacheScope` per
  SEP-2549.
- **No `initialize` handshake.** Consistent with the server's existing
  dispatch loop from FEAT-3135 (protocol version + capabilities arrive in
  `_meta`).

## Integration Map

### Files to Modify
- `scripts/little_loops/mcp_server/server.py::build_server()` — add
  `on_list_resources=`/`on_read_resources=` kwargs to the existing
  `Server(...)` construction, plus `"resources/list"`/`"resources/read"`
  entries to `cache_hints`, parallel to the existing `"tools/list"` entry
- `scripts/little_loops/mcp_server/tools.py` (or a new sibling module) —
  add the resource handlers and their dict/list registry, mirroring the
  `_TOOL_HANDLERS`/`_TOOLS` shape and `handle_call_tool`'s
  exception-to-`is_error`-result convention
- `docs/reference/CLI.md` — extend the `ll-mcp` section added by FEAT-3135
  with the resource surface

### Dependent Files (Callers/Importers)
- FEAT-3135 landed (`status: Completed`, 2026-08-09): the server/dispatch-loop
  scaffolding it registered is `scripts/little_loops/mcp_server/server.py`
  (`build_server()`, `run_stdio()`) and `scripts/little_loops/mcp_server/tools.py`
  (`_TOOL_HANDLERS`, `_TOOLS`, `handle_list_tools`, `handle_call_tool`). No
  other existing callers.

### Conventions in Force
- **No existing convention in this codebase pre-enumerates an allowlist at
  discovery time and rejects requests outside it** —
  `skill_expander.py:_resolve_content_path()` (lines 38-52) only does
  existence-checking, and `verify_package_data.py`'s escape lint is a
  build-time source lint, not a runtime request-path validator. The
  resource-resolution boundary this issue requires is new territory in this
  codebase, not a pattern to mirror.
- CLI tests import CLI module internals directly (not via subprocess) and
  isolate fixtures under `tmp_path` — evidence: `test_cli_ctx_stats.py`,
  `test_mcp_call.py:TestLoadMcpConfig` (lines 43-60).

### Tests
- New tests for the resource enumeration/resolution boundary: verify a
  request for a path outside the discovery-time enumeration is rejected
  without a filesystem read, and that `resources/list`/`resources/read`
  include `ttlMs`/`cacheScope`.
- `test_goals_parser.py:106-183,392` (`TestProductGoals`) — full error-path
  matrix for the `ll-goals.md` resource: missing/malformed/empty
  frontmatter, unreadable file. Reuse these fixtures for the resource
  handler's own tests rather than re-deriving them.

_Wiring pass added by `/ll:wire-issue`:_
- `test_mcp_server.py::test_discover_advertises_tools_only` (lines 97-114)
  — existing test that asserts `caps.resources is None` (line 108) and a
  docstring framing "no Roots/Sampling/Logging appear" (lines 98-99); once
  `on_list_resources=`/`on_read_resources=` are registered on `Server(...)`,
  the SDK auto-derives a non-`None` `caps.resources`, so this assertion and
  docstring will break and must be updated as part of this issue, not
  discovered later as a test failure. [Agent 3 finding]
- `test_goals_parser_fuzz.py` — hypothesis-based fuzz tests already call
  `ProductGoals.from_content()`/`.from_file()` (confirmed via
  `ll-code callers-of`); reuse as an existing correctness backstop for the
  `ll://goals` resource body, no new fixture needed. [Agent 1 finding]

### Documentation
- `docs/reference/CLI.md` — extend the `ll-mcp` section (added by
  FEAT-3135) with the resource surface's `ll://` scheme and examples.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (line 98) — the `little_loops.mcp_server` module
  table row currently reads "...`main_mcp` entry point plus the five
  read-only tools (...)"; this becomes stale prose once resources exist and
  should be extended to mention the `ll://` resource surface alongside the
  tools. [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- No MCP server-side code exists yet anywhere in the repo — the only MCP protocol code is the client-side `mcp_call.py` (NDJSON framing, old-style `initialize` handshake), used by `runner_spec.py:_run_mcp` and `cli/harness.py:cmd_mcp`. There is nothing server-side to extend beyond what FEAT-3135 (currently `status: deferred`, not yet implemented) would add.
- FEAT-3135's own Program Design leaves module placement and handler-registration mechanism as an explicitly open, unresolved decision (two disagreeing precedents cited: the three-touch `cli/` pattern vs. `mcp_call.py`-style direct entry-point wiring) — FEAT-3136 cannot cite a concrete registration call site until that decision lands.
- `docs/` (170+ files across subdirs, no frontmatter convention) has no existing enumeration/walk helper anywhere in `scripts/little_loops/` — `tool_catalog.py` walks `skills/`/`commands/`/`agents/` but not `docs/`. The `ll://docs/...` discovery-time enumeration must be built from scratch, unlike the issues/goals resources which have reusable read primitives.
- Metadata-field precedent for `ttlMs`/`cacheScope`: `hooks/types.py:LLHookEvent.to_dict()` (line 47-64) and `tool_catalog.py:to_anthropic_tools()` (line 158-183) both omit unset fields entirely from the serialized dict rather than emitting `null` — the closest structural precedent in this codebase for how `resources/list` entries should attach caching metadata. No `ttlMs`/`cacheScope`-named field exists anywhere in the codebase today.
- Reusable per-issue read primitive for `ll://issues/<ID>`: `cli/issues/show.py::_parse_card_fields(path: Path, config: BRConfig) -> dict[str, str | None]` (lines 154-194) already separates "resolve one path → parse its full content" — FEAT-3135's own Program Design already flags this same function as the reusable non-argparse surface for its sibling `issue_get` tool.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- `_resolve_issue_id()` -> `_parse_card_fields()` is the existing two-call sequence `cmd_show` runs (`cli/issues/show.py:869,875`) that a `ll://issues/<ID>` resource handler should mirror; but `_parse_card_fields()` calls `path.read_text()` with no try/except (`show.py:166`) — a handler chaining these two functions inherits an unguarded `OSError` window if the file is deleted/permission-denied between resolution and read, and needs its own guard to return a clean MCP error instead of an uncaught exception.
- `gather_all_issue_ids()` (`dependency_mapper/operations.py:362-394`) returns only a `set[str]` of IDs, discarding the `Path` it globbed (`operations.py:390-393`) — reusing it for a discovery-time `(id, path)` enumeration needs either a per-ID `_resolve_issue_id()` call or a reimplemented walk that retains the path. It also excludes `config.legacy_issue_dirs()` (the BUG-2733 completed/deferred dirs), unlike `_resolve_issue_id()`, so it under-covers relative to what `ll://issues/<ID>` must resolve.
- Closest existing precedent for the discovery-time enumeration mechanics: `tool_catalog.py::assemble_tool_catalog()` (145-155) and its `_skill_entries`/`_command_entries`/`_agent_entries` helpers (95-142) — a plain `Path.glob()` walk executed at call time, tolerant of missing dirs, with no caching layer and no import-time/startup build anywhere in this codebase. This issue's "build once at startup" framing has no existing precedent to model — new territory in the walk mechanics, not only in the allowlist-rejection mechanics already on file.
- No `<scheme>://` URI parsing/construction precedent exists anywhere in `scripts/little_loops/` — a grep for `://` turns up only ordinary URLs; the only place `ll://` appears today is prose inside issue files. The nearest analog, `mcp_call.py`'s spec parser (`main()`, 365-373), splits `server/tool-name` on `/` — a different, non-scheme delimiter convention with no reusable parsing logic for `ll://issues/<ID>` vs `ll://docs/...` vs `ll://goals`.
- Boundary/rejection precedent for "reject a path outside an allowed set": `verify_private_refs.py::scan_paths()` (393-400) and `cli/loop/_helpers.py::_display_loop_path()`/`_relativize_to_cwd()` (1218-1253) both use `Path.resolve().relative_to(base)` wrapped in `try/except (ValueError[, OSError])`, never string-prefix comparison — but both uses are for *display formatting*, not *access control*. `verify_package_data.py::run_escape_lint()` (~136) is the only existing allowlist-of-known-good-entries concept in the repo, and it's a build-time source lint, not a runtime request validator. FEAT-3136's runtime allowlist rejection has no existing access-control precedent, only display-formatting code sharing the same underlying `relative_to` primitive.
- Test-naming convention for the new rejection tests: class-per-function-under-test with `test_<condition>_<outcome>` methods — evidence: `test_mcp_call.py::TestLoadMcpConfig` (`test_loads_valid_file`, `test_missing_file_raises`, `test_invalid_json_raises`), `test_cli_surface.py` (`test_rejects_unknown_flag`, `test_rejects_unknown_subcommand`).
- Two-phase "list metadata cheaply, fetch body on demand" precedent: `tool_catalog.py`'s `_skill_entries()`/etc. read full file text but extract only `description`/`args` via `parse_skill_frontmatter()` for list-shaped output, deferring body content to a separate step. Two frontmatter parsers already coexist by design in `frontmatter.py`: `parse_skill_frontmatter()` (YAML-first with permissive line-scan fallback, the canonical SKILL.md parser, line 371) vs. the general `parse_frontmatter()` (line 255) — `resources/list`'s frontmatter-only pass and `resources/read`'s full-body pass can draw on this existing split rather than inventing a new one.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **Concrete registration call site (FEAT-3135 landed 2026-08-09):** `scripts/little_loops/mcp_server/server.py::build_server()` constructs the SDK's lowlevel `Server` via kwargs, not decorators — `Server("ll-mcp", version=..., on_list_tools=handle_list_tools, on_call_tool=handle_call_tool, cache_hints={"tools/list": CacheHint(ttl_ms=300_000, scope="public")})`. `server.py`'s own module docstring/comments already anticipate this issue: FEAT-3136 (resources) and FEAT-3137 (prompts) register their own handlers onto the same `Server(...)` call by adding `on_list_resources=`/`on_read_resources=`-shaped kwargs and new `cache_hints` entries (`"resources/list"`, `"resources/read"`), parallel to the existing `"tools/list"` entry.
- **Intra-server dispatch pattern to mirror:** `scripts/little_loops/mcp_server/tools.py` holds a plain `dict` registry (`_TOOL_HANDLERS`, line 182) and a source-order literal list (`_TOOLS`, line 190) for the five tools; `handle_call_tool` (line 294) looks up the dict and converts any exception into a `CallToolResult(is_error=True)` rather than letting it reach the SDK dispatch loop. A resources capability has no existing `handle_list_resources`/`handle_read_resources` yet — this is new code, but the same three-piece shape (dict/list registry + async handler functions) is the established convention to extend.
- **`ll://issues/<ID>` pattern already implemented once:** `_tool_issue_get` (`tools.py:92-107`) already chains `_resolve_issue_id(config, issue_id)` → `_parse_card_fields(path, config)` with a `None`-check `ValueError` guard — this is the concrete call site to mirror for the issues resource, not just the abstract functions cited in Program Design.
- `docs/reference/CLI.md`'s `### ll-mcp` section (line 4210) currently documents only the five tools; it does not yet mention resources — confirms this subsection still needs the resource-surface addition this issue proposes.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- Test-naming convention nuance: `test_mcp_server.py` — the file this issue's new resource tests extend — itself uses flat `test_<subject>_<behavior>` function names throughout (no class grouping), which is in tension with the class-per-function-under-test convention (`test_mcp_call.py::TestLoadMcpConfig`, `test_cli_surface.py`) already cited elsewhere in this issue's findings for the new rejection tests. Both conventions coexist in the test suite; this file's own existing style is the flat one.

## Program Design

### Deviations

- 2026-08-09: The design and Implementation Steps say `on_list_resources=`/
  `on_read_resources=` kwargs. The actual installed SDK's `Server.__init__`
  takes `on_list_resources=` (plural, matches) but `on_read_resource=`
  (**singular** — there is exactly one resource per `resources/read` request,
  unlike `resources/list`'s plural result). Implemented against the real
  kwarg name, `on_read_resource=`.

### Types
- `little_loops.goals_parser.ProductGoals` (`.from_file(path: Path) ->
  ProductGoals | None`, `goals_parser.py:92`) — dataclass with `version`,
  `persona`, `priorities`, `raw_content`; `raw_content` is the full
  markdown, usable directly as the body of an `ll://goals` resource. No
  caller in this module resolves the default `.ll/ll-goals.md` path — the
  resource handler must construct it itself.

### Signatures
- `ProductGoals.from_file(path: Path) -> ProductGoals | None` — `goals_parser.py:92`; every existing call site is a test (`test_goals_parser.py`), no production caller constructs the default `.ll/ll-goals.md` path today
- `ProductGoals.from_content(content: str) -> ProductGoals | None` — `goals_parser.py:111`; both classmethods return `None` on every malformed-input case (missing file, unreadable, absent/empty/malformed frontmatter) rather than raising
- `_resolve_issue_id(config, user_input: str) -> Path | None` — `cli/issues/show.py:40`; already resolves `"518"`/`"FEAT-518"`/`"P3-FEAT-518"` shapes against category dirs, the reusable primitive for `ll://issues/<ID>`
- `gather_all_issue_ids(issues_dir: Path, config: BRConfig | None = None) -> set[str]` — `dependency_mapper/operations.py:362`; filename-only scan across category dirs, the closest existing "build a set once, check membership" analog in this codebase, though invoked per-CLI-call rather than at a long-lived server's startup

### Call Path
- `ll://goals` resource → `little_loops.goals_parser.ProductGoals.from_file()`
- `ll://issues/<ID>` resource → issue file read, resolved against the
  discovery-time enumeration of `.issues/` files
- `ll://docs/...` resource → docs file read, resolved against the
  discovery-time enumeration of `docs/` files

### Decision Rules
N/A — no new gap kind, gate, keyword list, or threshold.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- `_resolve_issue_id(config, user_input) -> Path | None` (`cli/issues/show.py:40-151`) never raises: unparseable input, zero candidates, or an unreadable candidate during disambiguation (its nested `_frontmatter_id()` closure swallows `OSError` per-candidate, `show.py:113-121`) all collapse to `None`, safe to branch on directly. `_parse_card_fields(path, config) -> dict[str, str | None]` (`show.py:154-289+`) is the one seam without that guarantee — its `path.read_text()` (`show.py:166`) has no surrounding try/except, so a resource handler chaining `_resolve_issue_id -> _parse_card_fields` must add its own guard at that seam to avoid an unhandled exception reaching the MCP dispatch loop.
- `ProductGoals.from_file`/`from_content` (`goals_parser.py:92-160`) are fully null-safe end to end (missing file, unreadable/undecodable file, missing/malformed frontmatter delimiters, invalid YAML, non-dict YAML root all return `None`) — no exception path exists there to guard against, unlike the `_parse_card_fields` seam above.
- `gather_all_issue_ids(issues_dir, config) -> set[str]` (`dependency_mapper/operations.py:362-394`) is IDs-only, not path-bearing, and excludes `config.legacy_issue_dirs()` — its one production caller, `cmd_next_issue` (`cli/issues/next_issue.py:69-74`), uses it only as graph-construction input inside a defensive `try/except Exception: pass`, not as a listing/display surface. It is not a drop-in enumerator for `resources/list`; the discovery-time enumeration needs its own walk that retains `(id, path)` pairs and includes the legacy dirs `_resolve_issue_id` searches.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **Registration mechanism confirmed at the actual call site (FEAT-3135 landed):** `mcp.server.lowlevel.Server` is driven by constructor kwargs (`on_list_tools=`, `on_call_tool=`), not `@server.list_resources()`-style decorators — no decorator-based registration appears anywhere in this codebase's usage of the SDK. The resource handlers must be added as `on_list_resources=`/`on_read_resources=`-shaped kwargs to the same `Server(...)` call in `build_server()` (`server.py`), alongside new `cache_hints` entries for `"resources/list"`/`"resources/read"` parallel to the existing `"tools/list"` entry — this is the SDK-level half of the registration; a Python-level dict/list registry analogous to `_TOOL_HANDLERS`/`_TOOLS` (`tools.py:182,190`) is the intra-server half.
- **Error-handling contract the resource handlers must fit into:** `handle_call_tool` (`tools.py:294-323`) never lets an exception reach the SDK dispatch loop — unknown name and any handler exception both convert to `CallToolResult(is_error=True)`. No `handle_read_resources` exists yet to copy, but this is the established convention a new resource handler (or its own dispatch wrapper) must replicate, which also directly addresses the flagged unguarded `_parse_card_fields()` `read_text()` call.
- **Test harness to extend, not invent:** `scripts/tests/test_mcp_server.py` uses `pytest.importorskip("mcp")` at module top, an in-memory `Client(server)` (no subprocess/stdio), fixture helpers `_make_project(tmp_path, monkeypatch)` and `_write_issue(...)`, and asserts cache metadata via `result.ttl_ms`/`result.cache_scope` on the client-side result object. One existing test, `test_discover_advertises_tools_only` (lines 97-114), asserts `caps.resources is None` — this assertion needs updating once resources are registered, since it currently encodes "no resources capability yet."
- Test-naming convention for the new rejection tests: class-per-function-under-test with `test_<condition>_<outcome>` methods, per `test_mcp_call.py::TestLoadMcpConfig` and `test_cli_surface.py`.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **Statelessness invariant tension:** `tools.py`'s module docstring (lines 5-16) documents "the 2026-07-28 statelessness invariant" — every existing tool handler resolves entirely from its own `arguments` dict plus a fresh `BRConfig` built from `Path.cwd()` on every call; nothing is cached at module- or server-construction time. This issue's discovery-time enumeration (built once at startup, reused across requests) is the first departure from that invariant anywhere in `mcp_server/`. No existing code in this module builds state once and reuses it across calls — the enumeration's storage/lifetime (module-level global vs. object built once in `build_server()` and closed over by the resource handlers) has no precedent to follow and needs its own design decision.
- **`ttlMs`/`cacheScope` are server-wide per-method hints today, not per-entry:** the only existing usage, `cache_hints={"tools/list": CacheHint(ttl_ms=300_000, scope="public")}` in `build_server()` (`server.py:44`), is keyed by MCP method name and applied by the SDK to the whole `ListToolsResult`, not set by hand on individual entries — `handle_list_tools` (`tools.py:282-291`) itself never touches `ttlMs`/`cacheScope`. No precedent exists anywhere in this codebase for per-entry (as opposed to per-method) cache metadata. Satisfying this issue's `ttlMs`/`cacheScope` acceptance criterion for `resources/list`/`resources/read` most plausibly extends the same `cache_hints` dict with `"resources/list"`/`"resources/read"` entries, mirroring the existing `"tools/list"` entry — a per-resource-entry hint would be new, unprecedented SDK usage.

## Implementation Steps

1. In `server.py::build_server()`, add `on_list_resources=`/
   `on_read_resources=` kwargs to the existing `Server(...)` call, and
   `"resources/list"`/`"resources/read"` entries to `cache_hints`,
   parallel to the existing `"tools/list"` entry.
2. Build the discovery-time enumeration once (issue files as `(id, path)`
   pairs covering `config.legacy_issue_dirs()`, `ll-goals.md`, and
   `docs/`) and store it for reuse across requests — this is the first
   stateful construct in `mcp_server/`, a deliberate departure from the
   module's statelessness invariant; decide its storage/lifetime (e.g. an
   object built once in `build_server()` and closed over by the handlers).
3. Add `handle_list_resources`/`handle_read_resources` plus a dict/list
   registry, mirroring the `_TOOL_HANDLERS`/`_TOOLS` shape in `tools.py`
   and `handle_call_tool`'s convention of converting every exception to an
   `is_error` result rather than letting it reach the SDK dispatch loop.
4. For `ll://issues/<ID>`, mirror `_tool_issue_get`'s
   `_resolve_issue_id(config, issue_id)` → `_parse_card_fields(path,
   config)` chain, adding a guard around `_parse_card_fields()`'s
   unguarded `path.read_text()` (`show.py:166`) so a deleted or
   permission-denied file returns a clean error instead of an uncaught
   `OSError`.
5. For `ll://goals`, use `ProductGoals.from_file()` directly (already
   null-safe end to end; no additional guard needed).
6. For `ll://docs/...`, add a new enumeration walk — no existing helper
   covers `docs/`.
7. `resources/read` rejects any path outside the discovery-time
   enumeration without performing a filesystem read; `resources/list`
   parses frontmatter only (not full bodies) for name/description, and
   both include `ttlMs`/`cacheScope`.
8. `python -m pytest scripts/tests/` passes, including the updated
   `test_discover_advertises_tools_only` (`caps.resources` no longer
   `None`) and new coverage for the resource enumeration/resolution
   boundary.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `test_mcp_server.py::test_discover_advertises_tools_only` — change
  `assert caps.resources is None` to expect the SDK-derived non-`None`
  value once resource handlers are registered, and update its docstring
  accordingly.
- Update `docs/reference/API.md` (line 98, `little_loops.mcp_server` module
  table row) to mention the `ll://` resource surface alongside the five
  tools.

## Acceptance Criteria

- Issue files, `ll-goals.md`, and docs are listed and readable as MCP
  resources under the `ll://` scheme.
- `resources/read` resolves only against the discovery-time enumeration; a
  request for a path outside it is rejected without a filesystem read.
- `resources/list` and `resources/read` responses include `ttlMs` and
  `cacheScope`.
- `python -m pytest scripts/tests/` passes.

## Status

**Open** | Created: 2026-08-09 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-08-09T18:23:32 - `057c5422-6603-41e8-81d6-1ee028d98358.jsonl`
- `/ll:ready-issue` - 2026-08-09T17:48:02 - `8490c55e-637b-4850-8531-fb88db97fb23.jsonl`
- `/ll:confidence-check` - 2026-08-09T17:45:06 - `9571793e-3521-4319-bafc-0428a14d71e8.jsonl`
- `/ll:reconcile-issue` - 2026-08-09T17:42:47 - `b12572b9-66c1-4127-9915-114b2706e299.jsonl`
- `/ll:verify-issues` - 2026-08-09T17:39:00 - `0d0610d9-8d6c-4767-9b81-2235ebaadcd8.jsonl`
- `/ll:refine-issue` - 2026-08-09T17:36:27 - `83eb51e1-97e4-4c4d-ab0a-2b0d2e86a1a9.jsonl`
- `/ll:verify-issues` - 2026-08-09T17:31:24 - `73cbd7ad-1087-48e0-a6b2-91d51d5067ac.jsonl`
- `/ll:wire-issue` - 2026-08-09T17:28:55 - `d6173141-08a3-48c2-bc9c-28a6e268656b.jsonl`
- `/ll:refine-issue` - 2026-08-09T17:22:19 - `7c5bf03d-e586-44e2-a181-c2075e09cb9f.jsonl`
- `/ll:refine-issue` - 2026-08-09T14:35:10 - `1870f2e0-e809-4665-982e-242cc0be4d41.jsonl`
- `/ll:refine-issue` - 2026-08-09T13:51:06 - `f453a70a-3ede-4be0-a10b-493541f0278e.jsonl`
- `/ll:issue-size-review` - 2026-08-09T07:40:09 - `153550d2-faf1-4350-b263-1aaa047c80e3.jsonl`
