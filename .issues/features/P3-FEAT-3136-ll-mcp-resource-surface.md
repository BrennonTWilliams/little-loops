---
id: 3136
title: 'll-mcp: ll:// resource surface'
type: FEAT
priority: P3
status: open
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
---

# FEAT-3136: ll-mcp: ll:// resource surface

## Summary

The MCP resources surface for the `ll-mcp` server: issue files,
`ll-goals.md`, and docs, exposed under an `ll://` scheme (e.g.
`ll://issues/FEAT-042`, `ll://docs/…`). This builds on the running server
and dispatch loop from FEAT-3135 — it adds `resources/list` and
`resources/read` handling to the same server, resolved against a
discovery-time enumeration rather than arbitrary filesystem reads.

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
- The server module registered in FEAT-3135 (exact path depends on the
  module-placement decision made there) — add `resources/list` and
  `resources/read` handlers
- `docs/reference/CLI.md` — extend the `ll-mcp` section added by FEAT-3135
  with the resource surface

### Dependent Files (Callers/Importers)
- Depends on the server/dispatch-loop scaffolding registered by FEAT-3135;
  no other existing callers.

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

### Documentation
- `docs/reference/CLI.md` — extend the `ll-mcp` section (added by
  FEAT-3135) with the resource surface's `ll://` scheme and examples.

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

## Program Design

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

## Implementation Steps

1. The `ll://` resource surface's discovery-time enumeration (issue files,
   `ll-goals.md`, docs) is built once at startup on the server registered
   in FEAT-3135; `resources/read` is verified to reject any path outside
   that enumeration without performing a filesystem read. `resources/list`
   and `resources/read` responses include `ttlMs`/`cacheScope`.
2. `python -m pytest scripts/tests/` passes, including new coverage for the
   resource enumeration/resolution boundary.

## Acceptance criteria

- Issue files, `ll-goals.md`, and docs are listed and readable as MCP
  resources under the `ll://` scheme.
- `resources/read` resolves only against the discovery-time enumeration; a
  request for a path outside it is rejected without a filesystem read.
- `resources/list` and `resources/read` responses include `ttlMs` and
  `cacheScope`.
- `python -m pytest scripts/tests/` passes.

## Session Log
- `/ll:refine-issue` - 2026-08-09T14:35:10 - `1870f2e0-e809-4665-982e-242cc0be4d41.jsonl`
- `/ll:refine-issue` - 2026-08-09T13:51:06 - `f453a70a-3ede-4be0-a10b-493541f0278e.jsonl`
- `/ll:issue-size-review` - 2026-08-09T07:40:09 - `153550d2-faf1-4350-b263-1aaa047c80e3.jsonl`
