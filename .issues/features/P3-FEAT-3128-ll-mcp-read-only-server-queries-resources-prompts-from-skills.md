---
id: 3128
title: 'll-mcp: read-only server (queries, resources, prompts-from-skills)'
type: FEAT
priority: P3
status: done
discovered_date: '2026-08-09'
labels:
- multi-host
- mcp
parent: EPIC-3127
learning_tests_required:
- mcp
verify_verdict: VALID
size: Very Large
completed_at: '2026-08-09T07:00:20Z'
---

## Summary

The first tier of the `ll-mcp` EPIC: a read-only stdio MCP server, shipped as a
new `ll-mcp` console entry point in the `scripts` package. It imports the same
`little_loops` library functions the CLIs use — no shelling out, no daemon; the
host spawns it per session like any stdio server.

Three surfaces:

1. **Coarse read-only tools** — `issues_query` (list / search / show /
   next-issue / sequence behind one parameterized tool), `issue_get` (full body
   + sections), `history_search`, `deps_check`, and `capabilities` (the existing
   `CapabilityReport`).
2. **MCP resources** for issue files, `ll-goals.md`, and docs, under an `ll://`
   scheme (`ll://issues/FEAT-042`, `ll://docs/…`).
3. **Prompts from skills** — every `SKILL.md` served mechanically as an MCP
   prompt, with name, description, and args read from frontmatter.

No write path. Alongside the server, `ll-adapt --host` learns to emit the host's
MCP config snippet (`.mcp.json` for Claude Code, TOML for Codex), and
`ll-ctx-stats` learns to measure the MCP surface's context cost *before* this
ships, so tool granularity is decided on data rather than guesswork.

This tier exists to prove the facade pattern and establish the context-cost
profile. It blocks the mutation tier, which extends this facade, its
output-schema reuse, and its resource surface.

## Spec assumptions (MCP 2026-07-28)

- **Stdio transport unchanged.** This tier ships stdio-only; an HTTP entry point
  is a future addition if needed.
- **Caching metadata is part of the contract.** `tools/list`, `resources/list`,
  `prompts/list`, and `resources/read` responses MUST include `ttlMs` and
  `cacheScope` per SEP-2549, and tool ordering is guaranteed stable. For the
  prompts-from-skills list this directly answers the context-cost open question:
  the host prompt cache can reuse list responses per the declared TTL, and
  `ll-ctx-stats` should consume these protocol-level fields rather than
  re-measuring transport bytes.
- **Explicitly opt out of deprecated primitives.** Do NOT advertise or depend on
  Roots, Sampling, or Logging — all three were deprecated in 2026-07-28 with a
  12-month minimum window. New implementations should not adopt them; this ships
  as a clean-slate consumer.
- **No `initialize` handshake.** Servers handle each request on its own merits
  (protocol version + capabilities arrive in `_meta`). The Python SDK v2
  implements this; `ll-mcp` must pin the SDK version that ships the new
  behavior.

## Bind resource resolution at discovery, not at call time

The design does not yet say how a resource path is resolved. Because this server
exposes skill-derived resources to arbitrary MCP clients, `little-loops` is the
loader and the trust boundary is external — unlike host-CLI-owned skill loading
elsewhere in the project, where the caller is already inside the trust boundary.
Specify the resolution rule before this ships rather than after:

- **Pre-enumerate supporting files at discovery time.** Walk each skill once
  during startup and record the exact set of readable paths. A resource request
  then accepts a skill name, or a `skill-name/relative/path` that was
  enumerated, and is rejected otherwise. The server must never perform an
  arbitrary filesystem read derived from client-supplied input at call time —
  the enumeration, not path sanitization, is what makes traversal impossible.
- **Parse frontmatter only when listing.** `prompts/list` and `resources/list`
  need name, description, and args; reading full skill bodies at list time is
  both a context cost and an unnecessary widening of what is loaded. Fetch
  bodies on demand.
- **Treat a nested `SKILL.md` as a separate skill.** When a skill directory
  contains a subdirectory with its own `SKILL.md`, register it as its own skill
  and do not descend into it as supporting files of the parent, so one skill can
  never serve another's contents.

This applies to the resources surface and the prompts-from-skills surface alike,
and must carry forward to the mutation tier, where the same boundary widens.

## Anti-goals

- **Do not mirror all ~40 `ll-issues` subcommands as tools.** That is a
  context-budget disaster, and `ll-ctx-stats` exists to catch exactly this. The
  whole surface stays coarse.
- **Do not expose orchestration.** `ll-auto`, `ll-parallel`, `ll-loop`, and
  `ll-action invoke` — anything that spawns an agent or runs for minutes — stay
  off the tool surface.
- **Do not reimplement CLI logic.** The server is a facade over the same library
  functions, never a second implementation. Any behavior divergence between a
  tool and its CLI equivalent is a bug in this tier.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **Second independent skill-walk site**: `adapters/core.py:process_skills()` (line 279) also globs `*/SKILL.md` (non-recursive, independent of `tool_catalog.py:_skill_entries()`) and applies a `disable-model-invocation` filter via `_is_model_invocation_disabled()` (`core.py:180`). The prompts-from-skills recursive walker should decide whether to honor this same filter — neither existing site's behavior can be assumed by default since they diverge on it today only trivially (both currently apply it), but a new third walk site is exactly the kind of divergence this filter could silently miss.
- **Shared subprocess-teardown helper**: the terminate→wait→kill→wait pattern cited from `mcp_call.py` is backed by a shared helper, `subprocess_utils.py:_kill_process_group()` (line 307) — also used by `subprocess_utils.py:run_claude_command()` (line 320), which is a second precedent for the bounded-selector+deadline pattern applied to a *streaming* subprocess reading two pipes (stdout+stderr) on one selector. Relevant if the new server's own stdin-reading loop needs the same shape for reading from its own stdin rather than a child's stdout — no existing precedent covers a server reading its own stdin in a long-lived loop; `mcp_call.py`/`run_claude_command()` are both client-side patterns reading a child process's output.

### Files to Modify
- `scripts/pyproject.toml` — add `ll-mcp` console entry point under `[project.scripts]` and a new pinned MCP SDK dependency with a justification comment (pattern: the `anthropic` pin, `scripts/pyproject.toml:40-46`)
- `scripts/little_loops/cli/adapt.py` — `main_adapt()` (line 31) needs new host-config emission wired in for the MCP snippet work
- `scripts/little_loops/adapters/core.py` — `HostEmitter` Protocol (line 28) and `_EMITTER_MAP` (line 44) need extension for MCP config emission; no Claude Code emitter exists in `_EMITTER_MAP` today (only `codex`, `gemini`, `omp`, `kimi-code`), so `.mcp.json` emission may need a new host key registered, not just a new method
- `scripts/little_loops/adapters/codex.py` — needs a TOML-emission method if `HostEmitter` gains one; `emit_skill` (`codex.py:242`) is the closest TOML-output template
- `scripts/little_loops/adapters/capabilities.py` — `HOST_CAPABILITIES`/`config_dir` may need an MCP-config-path field per host
- `scripts/little_loops/cli/ctx_stats.py` — `_aggregate_mcp_health()` (line 169) currently derives MCP health from `tool_events` byte/latency columns via `history_reader.mcp_server_usage()`, not protocol `ttlMs`/`cacheScope`; no `ttl_ms`/`cache_scope` columns exist in that schema yet — a parallel aggregation path is needed
- A new server module (placement is an open decision — see Program Design → Call Path)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/configure/areas.md` — add `ll-mcp` to the "Authorize all ll- commands (Recommended)" preset line (`areas.md:849`) [Agent 1/3 finding]
- `scripts/little_loops/init/writers.py` — add `"Bash(ll-mcp:*)"` to the `_LL_PERMISSIONS` tuple (`writers.py:80-134`) [Agent 1/3 finding]
- `README.md` — bump the `"N CLI tools"` count line (`README.md:180`); do NOT add a `### ll-mcp` section — blocked by `test_readme_structure.py::TestReadmeIsHeroPage::test_readme_has_no_ll_cli_sections` [Agent 2 finding]
- `scripts/tests/test_wiring_cli_registry.py` — add a `("docs/reference/CLI.md", "ll-mcp", "FEAT-3128")`-shaped tuple to `DOC_STRINGS_PRESENT`, following the pattern used for prior tools (`ll-adapt`, `ll-ctx-stats`) [Agent 2 finding]
- `docs/ARCHITECTURE.md` — add a new schema-migration table row (following the v25 `tool_events.mcp_server`/`mcp_tool`/`mcp_outcome`/`latency_ms` row pattern) if `cli/ctx_stats.py`'s ttlMs/cacheScope aggregation path requires new `tool_events` columns [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py:47` — imports `main_adapt`
- `scripts/little_loops/cli/__init__.py:56` — imports `main_ctx_stats`
- `scripts/tests/test_cli_ctx_stats.py:13` — imports `main_ctx_stats` directly for testing
- `scripts/little_loops/cli/verify_cli_allowlist.py:28` — `_NON_LL_TOOLS = frozenset({"mcp-call"})` excludes the existing MCP *client* from permission-preset parity checks; `ll-mcp` is `ll-`-prefixed and will NOT get that exclusion, so it must be added to both permission presets `verify_cli_allowlist.py` checks (`skills/configure/areas.md` preset, `little_loops.init.writers._LL_PERMISSIONS`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/adapters/gemini.py`, `adapters/omp.py`, `adapters/kimi.py` — existing `HostEmitter` implementations; `HostEmitter` is a `@runtime_checkable` structural `Protocol` (not an ABC, `adapters/core.py:28-42`) and `resolve_emitter()` does no `isinstance` gate at registration time, so adding a new emit method to the Protocol does NOT force these three to implement it — a missing method only surfaces as `AttributeError` at call time for whichever host is actually exercised [Agent 1/2 finding]
- `scripts/little_loops/adapters/__init__.py:2` — re-exports `resolve_emitter`, `HostEmitter`, `AdapterError` [Agent 1 finding]
- `scripts/little_loops/cli/verify_cli_allowlist.py::_all_ll_entry_points()` — derives its canonical set from installed distribution metadata (`importlib_metadata.distribution("little-loops")`), not static `pyproject.toml` parsing — the parity check only sees `ll-mcp` after an editable reinstall picks up the new entry point [Agent 2 finding]

### Conventions in Force
- New console entry points follow a three-touch pattern (implementation module exporting `main_<name>(...) -> int`, a re-export in `cli/__init__.py`, a `[project.scripts]` entry) — evidence: `main_ctx_stats` (`cli/ctx_stats.py:726`), `main_adapt` (`cli/adapt.py:31`). The existing `mcp-call` client instead bypasses `cli/` entirely with direct module wiring (`mcp-call = "little_loops.mcp_call:main"`, `pyproject.toml:124`) — the two precedents disagree on which shape a long-running stdio server should follow; this is a decision the implementer needs to make knowingly.
- New third-party dependencies are pinned with an inline justification comment naming the originating issue and the reason an existing dependency doesn't suffice — evidence: `anthropic` pin (`scripts/pyproject.toml:40-46`), `psutil` pin (`scripts/pyproject.toml:52-58`).
- Skill/command/agent discovery already has one canonical frontmatter-parsing utility built explicitly to prevent reimplementation — evidence: `scripts/little_loops/tool_catalog.py` docstring (lines 1-9), `_skill_entries()` (line 95) walking `skills_dir.glob("*/SKILL.md")` via `parse_skill_frontmatter()` (`scripts/little_loops/frontmatter.py:371`). This glob is non-recursive and does not descend into nested skill directories — it neither discovers nor mis-attributes a nested `SKILL.md` today. The issue's "nested SKILL.md = separate skill" requirement needs new recursive-walk logic; `_skill_entries` cannot be reused as-is for it.
- `ll-adapt` host registration uses a lazy-import dict (`_EMITTER_MAP`, `adapters/core.py:44`) resolved via `resolve_emitter()` (`core.py:56`) against a `@runtime_checkable` `HostEmitter` Protocol (`core.py:28`) — no decorator-based registration pattern exists anywhere in this codebase.
- Blocking stdio reads are bounded via `selectors.DefaultSelector` against a deadline, and process teardown always follows terminate → bounded `wait()` → kill → bounded `wait()` — evidence: `mcp_call.py:_send_jsonrpc()` (lines 76-131, BUG-2778 fix, `done`) and its `finally` block (lines 325-338, BUG-2779 fix, `done`). Any blocking I/O the new server performs should follow this same bounded pattern.
- CLI tests import CLI module internals directly (not via subprocess) and isolate fixtures under `tmp_path` — evidence: `test_cli_ctx_stats.py`, `test_mcp_call.py:TestLoadMcpConfig` (lines 43-60).
- No existing convention in this codebase pre-enumerates an allowlist at discovery time and rejects requests outside it — `skill_expander.py:_resolve_content_path()` (lines 38-52) only does existence-checking, and `verify_package_data.py`'s escape lint is a build-time source lint, not a runtime request-path validator. The resource-resolution boundary this issue requires (§ "Bind resource resolution at discovery, not at call time") is new territory in this codebase, not a pattern to mirror.
- _Wiring pass added by `/ll:wire-issue`:_ Adding a new CLI tool triggers a documented, partially-gated checklist in `CONTRIBUTING.md` § "Documentation wiring for new CLI tools" — `docs/reference/CLI.md` section, `README.md` count-only bump, `pyproject.toml` entry point, and both permission presets. `ll-verify-cli-allowlist` gates only the last three; the README/CLI.md items are gated separately by `test_readme_structure.py` and `test_wiring_cli_registry.py::DOC_STRINGS_PRESENT` [Agent 2 finding].

### Tests
- `scripts/tests/test_cli_ctx_stats.py` — precedent for testing a CLI module's internals directly
- `scripts/tests/test_mcp_call.py` — precedent for testing MCP config loading/dispatch with `tmp_path`-backed `.mcp.json` fixtures
- No test file yet exists for a prospective `ll-mcp`/server module
- `scripts/tests/test_adapt_golden_corpus.py`, `scripts/tests/test_adapters.py` — precedent location for `--host` MCP-config-emission tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero` — will fail the moment `ll-mcp` is registered in `pyproject.toml [project.scripts]` unless `areas.md` and `writers._LL_PERMISSIONS` are updated in the same change [Agent 1/3 finding]
- `scripts/tests/test_verify_host_map.py::TestHostCapabilities::test_keys_match_emitter_map` — asserts `set(HOST_CAPABILITIES) == set(_EMITTER_MAP)`; only at risk if the plan registers a new `"claude-code"` host key for `.mcp.json` emission — both maps must gain the key together [Agent 3 finding]
- `scripts/tests/test_enh_2511_mcp_telemetry.py` — existing coverage of `mcp_server_usage()`'s current byte/latency-only shape (`mcp_server, invocations, completions, successes, avg_latency_ms`); a new ttlMs/cacheScope aggregation path must coexist with this shape unchanged, not replace it [Agent 3 finding]
- `scripts/tests/test_readme_structure.py::TestReadmeIsHeroPage::test_readme_has_no_ll_cli_sections` — guards that README never gains a `### ll-mcp` section; only the CLI-tool count line may change [Agent 2 finding]
- New test file needed for the server module itself — no reusable server-side harness exists yet; `test_mcp_call.py` only covers the MCP *client* side. Follow its `_MockFileObj` / `_make_ready_selector` / `_patch_selector` / terminate→kill→wait pattern (`test_mcp_call.py:139-280`) for the new server's own subprocess/teardown tests [Agent 3 finding]
- New tests for recursive `SKILL.md` discovery — no existing fixture for nested skill directories anywhere in `scripts/tests/`; author from scratch, extending `test_tool_catalog.py`'s flat `skills/<name>/SKILL.md` fixture base with a nested-subdirectory case [Agent 3 finding]
- New `test_capabilities.py`, or an extension of `test_adapters.py` / `test_verify_host_map.py`, if `HostCapabilityEntry` gains a new field for an MCP-config path [Agent 3 finding]

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — referenced by `adapters/capabilities.py` docstring as the authoritative host parity matrix
- `docs/reference/API.md`, `docs/reference/CLI.md` — would need new `ll-mcp` sections following the `ll-adapt`/`ll-ctx-stats` entries

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` — bump the `"N CLI tools"` count line (`README.md:180`) only; `test_readme_structure.py` blocks a new `### ll-mcp` section [Agent 2 finding]
- `CONTRIBUTING.md` § "Documentation wiring for new CLI tools" — the mandatory, already-enforced checklist for any new `ll-` CLI tool; this issue's Integration Map should be checked against it directly [Agent 2 finding]
- `docs/ARCHITECTURE.md` — schema-migration table needs a new row (following the v25 row pattern) if new `ttl_ms`/`cache_scope` columns are added to `tool_events` [Agent 2 finding]

### Configuration
- `scripts/pyproject.toml` `[project.scripts]` (lines 67-124) and `dependencies` (lines 40-59) — both need new entries

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **Verification correction resolved**: `little_loops.dependency_mapper.validate_dependencies` and `analyze_dependencies` resolve to `scripts/little_loops/dependency_mapper/analysis.py:416` and `:518` respectively. Confirmed the package's `__init__.py` (lines 42-48, 69-94) re-exports both at package level, so `from little_loops.dependency_mapper import validate_dependencies` (the form `cli/deps.py:83-90` already uses) remains valid — the dotted-path citations at Program Design → Signatures/Call Path do not need to change, only gain these anchors.
- `issues_query`/`issue_get`'s "existing ll-issues list/search/show/next-issue/sequence library functions" (Call Path) are backed by `scripts/little_loops/cli/issues/list_cmd.py`, `search.py`, `show.py`, `next_issue.py`, `sequence.py`, dispatched from `cli/issues/__init__.py` — these are call targets for the new tool, not files the server itself modifies.
- `adapters/core.py` line citations have drifted slightly since this issue's last refine pass: `_EMITTER_MAP` is now at lines 51-56 (was cited as line 44) and `resolve_emitter()` at lines 59-76 (was cited as line 56); both still resolve, contents unchanged (still 4 keys: `codex`, `gemini`, `omp`, `kimi-code`; still no `isinstance` gate).

### Types
- `little_loops.host_runner.CapabilityReport` (`host_runner.py:181`) — existing dataclass the `capabilities` tool returns directly; constructed today at `host_runner.py:447,746,865,940,1123,1299,1504`. No new type needed for that tool.
- `little_loops.goals_parser.ProductGoals` (`.from_file(path: Path) -> ProductGoals | None`, `goals_parser.py:92`) — dataclass with `version`, `persona`, `priorities`, `raw_content`; `raw_content` is the full markdown, usable directly as the body of an `ll://goals` resource. No caller in this module resolves the default `.ll/ll-goals.md` path — the resource handler must construct it itself.
- `little_loops.history_reader.SearchResult` — return element type of `search()` (`history_reader.py:517`), the shape `history_search` marshals.

### Signatures
- `little_loops.history_reader.search(query, *, kind=None, limit=10, db=DEFAULT_DB_PATH) -> list[SearchResult]` — `history_reader.py:517`; `history_search` wraps this directly, `kind` filters by tool/file/issue/loop/correction/message
- `little_loops.dependency_mapper.validate_dependencies(issues, completed_ids, all_known_ids)` — used at `cli/deps.py:448`; the `deps_check` tool's direct equivalent (broken refs, missing backlinks, cycles, stale refs). `analyze_dependencies` (used at `cli/deps.py:396,624`) is also read-only and available if a richer variant is wanted
- `little_loops.frontmatter.parse_skill_frontmatter(text) -> dict[str, str]` — `frontmatter.py:371`; the canonical frontmatter parser, prompts-from-skills should reuse this rather than reimplement parsing
- `little_loops.adapters.core.resolve_emitter(host: str) -> HostEmitter` — `core.py:56`; the `HostEmitter` Protocol (`core.py:28`) currently defines only `emit_skill`/`emit_command`/`emit_agent`, no MCP-config method exists — this is the extension point for `ll-adapt --host` MCP config emission
- `main_adapt() -> int` — `cli/adapt.py:31`; dispatches per-host processing today for skills/commands/agents (lines 106-134), a new `process_mcp_config()`-shaped call would join that dispatch

### Call Path
- `issues_query`/`issue_get` tools → existing `ll-issues` list/search/show/next-issue/sequence library functions (per the issue's anti-goal, behind one parameterized tool, not five)
- `history_search` tool → `little_loops.history_reader.search()` → SQLite FTS5 `search_index` query
- `deps_check` tool → `little_loops.dependency_mapper.validate_dependencies()` → issue frontmatter graph
- `capabilities` tool → `little_loops.host_runner.CapabilityReport` (existing per-host construction sites)
- prompts-from-skills discovery → new recursive `SKILL.md` walk (not `tool_catalog._skill_entries`, which is non-recursive) → `little_loops.frontmatter.parse_skill_frontmatter()` → MCP `prompts/list` entries
- `ll-adapt --host <x>` → `main_adapt()` (`cli/adapt.py:31`) → `resolve_emitter(host)` (`adapters/core.py:56`) → an `HostEmitter` method not yet present on the Protocol → `.mcp.json` (Claude Code) / TOML (Codex, via `codex.py`'s `emit_skill` at line 242 as the TOML-output template)
- `ll-ctx-stats` MCP-cost measurement → currently `_aggregate_mcp_health()` (`cli/ctx_stats.py:169`) wraps `history_reader.mcp_server_usage()`, sourced from `tool_events` byte/latency columns (no `ttl_ms`/`cache_scope` columns exist in that schema yet) → a parallel aggregation path is needed once the server surface emits those protocol fields

### Decision Rules
N/A — no new gap kind, gate, keyword list, or threshold; this issue composes an existing protocol surface rather than introducing new classification logic. Two open architectural decisions surfaced by research (module placement for the server entry point: three-touch `cli/` pattern vs `mcp_call.py`-style direct wiring; which host key registers `.mcp.json` emission, since none exists in `_EMITTER_MAP` today) are implementation-route decisions, not decision-rule logic in this section's sense.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

1. The server module's placement is decided and recorded (three-touch `cli/` pattern used by `main_adapt`/`main_ctx_stats` vs `mcp_call.py`-style direct module wiring bypassing `cli/`) — the two existing precedents disagree, and every other step below depends on where `main_mcp` actually lives.
2. `ll-mcp` is registered as a console entry point in `scripts/pyproject.toml` and starts a stdio server against the 2026-07-28 spec, with a new pinned MCP SDK dependency carrying a justification comment matching the `anthropic`/`psutil` precedent.
3. Each of the five read-only tools (`issues_query`, `issue_get`, `history_search`, `deps_check`, `capabilities`) resolves to the library call named in Program Design → Call Path, with no subprocess invocation of any CLI.
4. The `ll://` resource surface's discovery-time enumeration (issue files, `ll-goals.md`, docs, and per-skill supporting files) is built once at startup; `resources/read` is verified to reject any path outside that enumeration without performing a filesystem read.
5. Prompts-from-skills discovery walks `SKILL.md` files recursively (not the existing non-recursive `tool_catalog._skill_entries` glob) and registers a nested `SKILL.md` as its own independent prompt.
6. `ll-adapt --host <x>` emits a working MCP config snippet, verified against both `.mcp.json` (Claude Code) and TOML (Codex) output.
7. `ll-ctx-stats` reports the MCP surface's context cost from `ttlMs`/`cacheScope`, verified as a change from `cli/ctx_stats.py:_aggregate_mcp_health()`'s current byte/latency-only measurement.
8. `ll-mcp` is added to both permission presets `scripts/little_loops/cli/verify_cli_allowlist.py` checks, since it will not get the `mcp-call`-style `_NON_LL_TOOLS` exclusion.
9. `python -m pytest scripts/tests/` passes, including new coverage for the server module and the `ll-adapt`/`ll-ctx-stats` extensions.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `ll-mcp` to `skills/configure/areas.md`'s "Authorize all ll- commands" preset line and to `_LL_PERMISSIONS` in `scripts/little_loops/init/writers.py`, in the same change that adds the `[project.scripts]` entry — otherwise `test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero` fails.
- Bump the `"N CLI tools"` count in `README.md` (do not add a `### ll-mcp` section — blocked by `test_readme_structure.py`).
- Add a `("docs/reference/CLI.md", "ll-mcp", "FEAT-3128")`-shaped tuple to `DOC_STRINGS_PRESENT` in `scripts/tests/test_wiring_cli_registry.py`.
- Decide whether any `HostEmitter` implementation beyond `codex.py` needs a body for the new emit method — `HostEmitter` is a structural `Protocol`, so `gemini.py`/`omp.py`/`kimi.py` are not forced to implement it; only add stubs there if those hosts are part of the acceptance-tested path.
- If a `"claude-code"` host key is registered in `_EMITTER_MAP` for `.mcp.json` emission, add the matching key to `HOST_CAPABILITIES` in the same change — `test_verify_host_map.py::test_keys_match_emitter_map` asserts the two sets stay equal.
- If `cli/ctx_stats.py` gains new `tool_events` columns for `ttl_ms`/`cache_scope`, add the corresponding row to the schema-migration table in `docs/ARCHITECTURE.md` and keep `mcp_server_usage()`'s existing byte/latency-only shape unchanged so `test_enh_2511_mcp_telemetry.py` keeps passing.
- Write server-module tests following `test_mcp_call.py`'s `_MockFileObj` / `_make_ready_selector` / `_patch_selector` / terminate→kill→wait pattern, and new recursive-`SKILL.md`-discovery tests (no existing nested-skill fixture to extend).

## Acceptance criteria

- `ll-mcp` is registered as a console entry point in the `scripts` package and
  runs as a stdio MCP server against the 2026-07-28 spec.
- The tool surface is exactly the five read-only tools listed above; no
  mutating tool is advertised.
- Every tool calls into `little_loops` library functions directly — no
  subprocess invocation of the CLIs.
- Issue files, `ll-goals.md`, and docs are listed and readable as MCP resources
  under the `ll://` scheme.
- Every discovered `SKILL.md` is advertised as an MCP prompt with its name,
  description, and args derived from frontmatter; a nested `SKILL.md` is
  registered as its own skill.
- `resources/read` resolves only against the discovery-time enumeration; a
  request for a path outside it is rejected without a filesystem read.
- `tools/list`, `resources/list`, `prompts/list`, and `resources/read` responses
  include `ttlMs` and `cacheScope`, and tool ordering is stable across calls.
- The server advertises no Roots, Sampling, or Logging capability.
- `ll-adapt --host <x>` emits a working MCP config snippet for that host.
- `ll-ctx-stats` reports the MCP surface's context cost, consuming the
  protocol's `ttlMs` / `cacheScope` fields rather than measuring transport bytes.


## Verification Notes

_Added by `/ll:verify-issues` — 2026-08-09:_

Spot-checked ~23 file:line/symbol citations across Integration Map and Program
Design against current HEAD. All referenced symbols/functions/tests exist;
most line numbers have drifted by single digits to ~30 lines (normal churn
since 2026-08-09 research), which doesn't change the guidance. One reference
needs correction:

- **`little_loops.dependency_mapper` is now a package, not a module.**
  `validate_dependencies()` and `analyze_dependencies()` cited at
  `dependency_mapper.py` now live in `dependency_mapper/analysis.py`
  (`validate_dependencies` line 416, `analyze_dependencies` line 518). Their
  usage sites in `cli/deps.py:396,448,624` are unchanged. Update the Program
  Design → Signatures citation before implementation starts.

No other content changed; verdict is `NEEDS_UPDATE` (persisted as
`verify_verdict: NON_VALID` in frontmatter) solely for this one path
correction — the issue's design and acceptance criteria remain accurate.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-08-09
- **Reason**: Issue too large for single session (size score 11/11, Very Large)

### Decomposed Into
- FEAT-3132: ll-mcp: core read-only server (tools, resources, prompts-from-skills)
- FEAT-3133: ll-adapt --host: emit MCP config snippet for ll-mcp
- FEAT-3134: ll-ctx-stats: measure ll-mcp context cost via ttlMs/cacheScope

## Session Log
- `/ll:issue-size-review` - 2026-08-09T06:59:30 - `1a2b4d88-27a6-4756-bc3a-7bce0e10a356.jsonl`
- `/ll:verify-issues` - 2026-08-09T06:56:02 - `c26239ca-f733-4d60-9004-ce6550196434.jsonl`
- `/ll:refine-issue` - 2026-08-09T06:53:17 - `757d2cdd-af5e-485b-bf99-f6ad061ccc95.jsonl`
- `/ll:verify-issues` - 2026-08-09T06:46:49 - `95668616-0b8f-412d-9070-be2e21517f4d.jsonl`
- `/ll:wire-issue` - 2026-08-09T06:43:47 - `05b7a69a-11f5-4fab-8b55-a85bcf173e3a.jsonl`
- `/ll:refine-issue` - 2026-08-09T06:32:34 - `a7ddde54-4fcd-4f63-9248-672e1f4f0d53.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-08-09
- **Decomposed into**: FEAT-3132, FEAT-3133, FEAT-3134

Work for FEAT-3128 is now carried by its child issues; this parent was closed by rn-decompose.
