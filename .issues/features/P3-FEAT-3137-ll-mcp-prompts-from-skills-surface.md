---
id: 3137
title: 'll-mcp: prompts-from-skills surface'
type: FEAT
priority: P3
status: done
completed_at: '2026-08-09T19:15:00Z'
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
confidence_score: 90
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-3137: ll-mcp: prompts-from-skills surface

## Summary

The MCP prompts surface for the `ll-mcp` server: every `SKILL.md` served
mechanically as an MCP prompt, with name, description, and args read from
frontmatter. This builds on the running server and dispatch loop from
FEAT-3135 — it adds `prompts/list` handling to the same server, backed by a
new recursive `SKILL.md` discovery walk (the existing
`tool_catalog._skill_entries` glob is non-recursive and cannot be reused
as-is).

## Current Behavior

No MCP prompts surface exists. `ll-mcp` (FEAT-3135, FEAT-3136, both
`status: done`) advertises `tools/list`/`tools/call` and
`resources/list`/`resources/read` only; `prompts/list`/`prompts/get` are
unregistered, so `caps.prompts` reports `None`
(`test_mcp_server.py::test_discover_advertises_tools_and_resources_only`)
and every `SKILL.md` in the plugin is invisible to MCP clients.

## Expected Behavior

Every discovered `SKILL.md` is advertised as an MCP prompt (name,
description, and args read from frontmatter), with `prompts/list`
responses carrying `ttlMs`/`cacheScope` per SEP-2549. A nested `SKILL.md`
registers as its own independent prompt rather than being absorbed as a
parent skill's supporting file. Resource resolution for any per-skill body
fetch is bound at discovery time (enumerated once at startup), never
derived from client-supplied paths at call time.

## Use Case

An external MCP client (a non-Claude-Code host — the EPIC's
"host-agnostic serving layer" goal) wants to browse and invoke
little-loops' skill catalog as MCP prompts without going through the
Claude Code plugin surface.

## Impact

Without this, `ll-mcp` is a read-only tools+resources server only — the
skill catalog, the primary way users invoke little-loops workflows, stays
unreachable from any non-Claude-Code MCP client, undermining the EPIC's
host-agnostic goal. It also blocks FEAT-3134 (`ll-ctx-stats`), which
`depends_on` this issue and consumes the `ttlMs`/`cacheScope` fields this
issue emits on `prompts/list`.

## Status

Open. `blocked_by: FEAT-3135`, which is now `status: done` — no open
blockers remain; ready to implement.

## Parent Issue

Decomposed from FEAT-3132: ll-mcp: core read-only server (tools, resources,
prompts-from-skills). This child covers prompts-from-skills; the server
skeleton, entry point, and tools surface are in FEAT-3135 (must land first —
this child registers its handlers on that server). The `ll://` resource
surface is a separate sibling, FEAT-3136.

## Bind resource resolution at discovery, not at call time

Because this server exposes skill-derived content to arbitrary MCP clients,
`little-loops` is the loader and the trust boundary is external — unlike
host-CLI-owned skill loading elsewhere in the project, where the caller is
already inside the trust boundary.

- **Pre-enumerate supporting files at discovery time.** Walk each skill
  once during startup and record the exact set of readable paths. A prompt-
  related resource request then accepts a skill name, or a
  `skill-name/relative/path` that was enumerated, and is rejected
  otherwise. The server must never perform an arbitrary filesystem read
  derived from client-supplied input at call time — the enumeration, not
  path sanitization, is what makes traversal impossible.
- **Parse frontmatter only when listing.** `prompts/list` needs name,
  description, and args; reading full skill bodies at list time is both a
  context cost and an unnecessary widening of what is loaded. Fetch bodies
  on demand.
- **Treat a nested `SKILL.md` as a separate skill.** When a skill directory
  contains a subdirectory with its own `SKILL.md`, register it as its own
  skill and do not descend into it as supporting files of the parent, so
  one skill can never serve another's contents.

This boundary must carry forward to the future mutation tier, where it
widens.

## Spec assumptions (MCP 2026-07-28)

- **Caching metadata is part of the contract.** `prompts/list` responses
  MUST include `ttlMs` and `cacheScope` per SEP-2549.
- **No `initialize` handshake.** Consistent with the server's existing
  dispatch loop from FEAT-3135 (protocol version + capabilities arrive in
  `_meta`).

## Integration Map

### Files to Modify
- The server module registered in FEAT-3135 (exact path depends on the
  module-placement decision made there) — add `prompts/list` handler
  > ⚠ Superseded — path resolved: `scripts/little_loops/mcp_server/server.py`; see § Codebase Research Findings under Integration Map
- New recursive `SKILL.md` discovery walk (not
  `tool_catalog._skill_entries`, which is non-recursive)
- `docs/reference/CLI.md` — extend the `ll-mcp` section added by FEAT-3135
  with the prompts surface

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/mcp_server/prompts.py` (new file) — houses the
  recursive `SKILL.md` discovery walk, a `build_prompt_index()`-style
  discovery-time enumeration, and `make_list_prompts_handler()`/
  `make_get_prompt_handler()` factories closing over that index, mirroring
  `resources.py`'s shape (see Codebase Research Findings under Program
  Design below).
- `docs/reference/API.md:98` — the `little_loops.mcp_server` module-table
  row enumerates the tools+resources surface (FEAT-3135/FEAT-3136) and
  stops short of prompts; needs a parallel clause, mirroring the addition
  already planned for `docs/reference/CLI.md`.

### Dependent Files (Callers/Importers)
- Depends on the server/dispatch-loop scaffolding registered by FEAT-3135;
  no other existing callers.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/help.py:181-209` (`_skill_entries()`) — a THIRD
  independent non-recursive `glob("*/SKILL.md")` skill-walk site not named
  in this issue's "Conventions in Force" (which cites only `tool_catalog.py`
  and `adapters/core.py`). Calls `parse_skill_frontmatter()` and
  `_is_model_invocation_disabled()` with narrower bridge-stub-only filtering
  (see Conventions in Force addition below). Feeds `collect_entries()`
  (`:212`), shared with `cli/action.py::_load_skills()` (`action.py:194-210`,
  which delegates to `collect_entries()` rather than walking independently —
  not itself a fourth site).
- `scripts/little_loops/cli/generate_skill_descriptions.py` — imports
  `parse_skill_frontmatter()` and applies the same skill-walk/filter pattern
  conceptually; aware-of, not modified by this issue.
- `scripts/little_loops/cli/verify_skill_prose.py:33,168` (`scan_prose()`)
  — a FOURTH independent single-level `skills_dir.glob("*/SKILL.md")`
  skill-walk site, with its own inline `disable-model-invocation` check
  (`fm.get("disable-model-invocation", "").lower() in ("true", "yes",
  "1")`) distinct from `_is_model_invocation_disabled()`; aware-of, not
  modified by this issue.

### Conventions in Force
- Skill/command/agent discovery already has one canonical
  frontmatter-parsing utility built explicitly to prevent reimplementation —
  evidence: `scripts/little_loops/tool_catalog.py` docstring (lines 1-9),
  `_skill_entries()` (line 95) walking `skills_dir.glob("*/SKILL.md")` via
  `parse_skill_frontmatter()` (`scripts/little_loops/frontmatter.py:371`).
  This glob is non-recursive and does not descend into nested skill
  directories. The "nested SKILL.md = separate skill" requirement needs new
  recursive-walk logic; `_skill_entries` cannot be reused as-is.
- A second independent skill-walk site exists:
  `adapters/core.py:process_skills()` (line 279) also globs `*/SKILL.md`
  (non-recursive) and applies a `disable-model-invocation` filter via
  `_is_model_invocation_disabled()` (`core.py:180`). Decide whether the new
  prompts-from-skills recursive walker honors this same filter — neither
  existing site's behavior can be assumed by default.
- **`parse_skill_frontmatter(text: str) -> dict[str, str]`**
  (`frontmatter.py:371-413`): returns `{}` if `text` doesn't start with
  `"---"` or has no closing `---`. Primary path is `yaml.safe_load()`,
  flattened to `dict[str, str]` — `None` becomes `""`, `bool`/`int`/`float`
  are stringified, and any list or nested-dict value is silently dropped
  (not present in the returned dict at all). Fallback (only on
  `yaml.YAMLError`) is a line-based scan of top-level `key: value` lines
  only. **`name` is never read from frontmatter** by either existing caller
  (`tool_catalog._skill_entries`, `adapters/core.py`) — both derive it from
  `skill_md.parent.name` (the directory name), not a frontmatter field.
- **`disable-model-invocation` filter mechanics**:
  `_is_model_invocation_disabled(fm: dict) -> bool` (`adapters/core.py:180-192`)
  — `None` → `False`; native `bool` → returned directly; anything else
  stringified/trimmed/lowercased and checked against `{"true", "yes",
  "1"}`. Applied by `adapters/core.py:process_skills()` (`:304`) and
  `process_commands()` (`:376`), and by `cli/help.py:190` when building the
  skill catalog listing. It is **not applied universally** —
  `cli/verify_triggers.py`'s loader (`:306-316`) documents the filter as
  opt-in via a `model_invocable_only: bool` param specifically because
  other callers (`issue_history.evolution._load_skill_keywords`) need the
  full unfiltered population.
- CLI tests import CLI module internals directly (not via subprocess) and
  isolate fixtures under `tmp_path` — evidence: `test_cli_ctx_stats.py`.

_Wiring pass added by `/ll:wire-issue`:_
- `cli/help.py::_skill_entries()` (`:181-209`) applies
  `_is_model_invocation_disabled()` more narrowly than
  `adapters/core.py::process_skills()` — it only skips a disabled skill when
  it also shares a name with an existing command (bridge-stub de-dup,
  comment at `:190-196`); a disabled skill with no command counterpart is
  still listed. This is a THIRD distinct filter behavior alongside
  `adapters/core.py`'s blanket skip and `cli/verify_triggers.py`'s opt-in
  `model_invocable_only` (default unfiltered) — confirms this issue's own
  framing that no single existing site's behavior can be assumed by
  default. For an MCP `prompts/list` surface (external, untrusted client),
  `adapters/core.py::process_skills()`'s blanket-skip is the closest
  behavioral match in intent (a skill author's `disable-model-invocation:
  true` should suppress advertisement to any external auto-invoker), not
  `cli/help.py`'s narrower dedup logic (solves a docs-listing problem
  irrelevant to MCP) or `verify_triggers.py`'s default-unfiltered stance
  (built for internal trigger analysis).
- `.issues/bugs/P4-BUG-1627-two-skill-md-parsers-have-block-scalar-defect.md`
  — prior art documenting that multiple independent `SKILL.md` parse/walk
  sites is a known recurring defect source in this codebase; supports
  reusing `parse_skill_frontmatter()` exactly in the new recursive walker
  rather than reimplementing parsing.

### Tests
- New tests for recursive `SKILL.md` discovery — no existing fixture for
  nested skill directories anywhere in `scripts/tests/`; author from
  scratch, extending `test_tool_catalog.py`'s flat `skills/<name>/SKILL.md`
  fixture base with a nested-subdirectory case.
- `test_frontmatter.py:320-366` (`TestParseSkillFrontmatter`) —
  prompts-from-skills edge cases: malformed YAML fallback, `None`→`""`,
  bool stringification.
- `test_tool_catalog.py:64-121` (`TestAssembleToolCatalogSkills`) — closest
  structural template for the new recursive `SKILL.md` walk's tests,
  including an unreadable-file-degrades pattern at lines 107-121.
- `test_adapters.py:102-126,202-235` (`_is_model_invocation_disabled`
  truthy-string matrix, `TestProcessSkillsTraversal` emitter-call pattern).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_help.py:13-76` (`TestCollectEntries`) — existing
  coverage of `cli/help.py`'s own skill-walk site (see Dependent Files
  above); no nested-`SKILL.md` fixture exists here either, consistent with
  this issue's "no existing nested-skill fixture" note — a second place to
  mirror the new nested-directory fixture, alongside `test_tool_catalog.py`.
- `scripts/tests/test_help.py:142-156`
  (`TestCatalogDriftGate.test_collect_entries_covers_real_plugin_root`) —
  asserts a subset (`<=`), not exact equality, against the real `skills/`
  tree; confirms a recursive walker surfacing new nested skills won't break
  this gate.
- `scripts/tests/test_verify_triggers.py:305-345`
  (`TestLoadSkillDescriptions`) — closest `tmp_path` skill-fixture pattern
  to extend for a nested-`SKILL.md` case; note its three existing fixtures
  never distinguish frontmatter `name:` from the directory name, so
  `verify_triggers.py:350`'s `fm.get("name") or skill_md.parent.name`
  fallback branch is itself untested today — relevant precedent, not itself
  in this issue's scope, when the new walker decides its own
  name-derivation rule.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_mcp_server.py:111`
  (`test_discover_advertises_tools_and_resources_only`) — currently asserts
  `caps.prompts is None`; MUST be updated to assert non-`None` once
  `on_list_prompts`/`on_get_prompt` are registered. This is an existing
  test to update, not just a structural template.
- `scripts/tests/test_verify_skill_prose.py` (`TestScanProse`) — like
  `test_tool_catalog.py` and `test_help.py`, has no nested-`SKILL.md`
  fixture; a third place where the new nested-directory fixture pattern
  could optionally be mirrored, though `verify_skill_prose.py` itself is
  out of scope for this issue.

### Documentation
- `docs/reference/CLI.md` — extend the `ll-mcp` section (added by
  FEAT-3135) with the prompts-from-skills surface.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:98` — the `little_loops.mcp_server` module-table
  row enumerates the tools+resources surface (FEAT-3135/FEAT-3136) and
  needs a parallel prompts-surface clause appended, mirroring the addition
  already planned for `docs/reference/CLI.md`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- Recursive-walk idiom confirmed: every genuinely-recursive discovery site in this codebase uses `sorted(dir.rglob(pattern))` (e.g. `recursive_finalize.py:50`, `session_store/writers.py:2188,2262`, `cli/doctor.py:419`, `cli/verify_package_data.py:139`) — there is no `os.walk` usage anywhere in `scripts/little_loops`. The flat `glob("*/SKILL.md")` used by 13+ skill-catalog call sites is documented in `.issues/enhancements/P4-ENH-1038-ll-verify-docs-should-track-fsm-loop-counts.md:135` as "the unanimously established pattern across 4+ sites," with a prior `rglob` walk in `doc_counts.count_files()` explicitly called out there as the outlier it corrected — switching this new walk to `rglob` diverges from a documented prior decision, not just current majority practice.
- Skill-name derivation is `skill_md.parent.name` at every site except one: `cli/verify_triggers.py:350` tries frontmatter `name` first, directory name as fallback — the sole exception to the "always directory name, never frontmatter" rule already noted in this issue.
- No nested `SKILL.md` exists anywhere under `skills/` today — a glob for `skills/*/*/SKILL.md` returns zero matches across all ~69 skill directories, every one exactly one level deep. The "nested SKILL.md = separate skill" requirement is a forward-looking design constraint with no reproducible fixture in this repo, consistent with this issue's own Tests section noting no existing nested-skill fixture.
- Frontmatter `args` today are free-text strings only — 11 `SKILL.md` files declare a top-level `args:` key (e.g. `skills/ll-refine-issue/SKILL.md:4: args: "ISSUE_ID [--auto] [--dry-run] [--gap-analysis] [--full-rewrite]"`), all untyped display hints, confirmed by `tool_catalog.py`'s own docstring (lines 11-14: "no type information"). Contrast: `fsm/schema.py:265` `ParameterSpec` dataclass (`type`, `required`, `default`, `description`, `values` fields) is the only *typed* parameter precedent in this codebase — used by FSM loop fragments, not skills or commands.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- Actual module locations now landed (FEAT-3135/FEAT-3136 both status `done`): `scripts/little_loops/mcp_server/server.py` (`build_server()`, lines ~29-69) registers all handlers as `Server(...)` constructor kwargs; `scripts/little_loops/mcp_server/tools.py` (stateless tool handlers, FEAT-3135); `scripts/little_loops/mcp_server/resources.py` (FEAT-3136 — `build_resource_index()`, `make_list_resources_handler()`, `make_read_resource_handler()`). The resource surface is the direct structural precedent for prompts and has already landed.
- New module implied by the existing shape: a `scripts/little_loops/mcp_server/prompts.py` parallel to `resources.py` would house the recursive `SKILL.md` discovery walk, a `build_prompt_index()`-style discovery-time enumeration, and `make_list_prompts_handler()`/`make_get_prompt_handler()` factories closing over that index — mirroring `resources.py`'s "build once in `build_server()`, close handlers over it" shape, not `tools.py`'s per-call statelessness.
- Dispatch registration mechanics: handlers are wired purely as `Server(...)` constructor kwargs (`on_list_tools=`, `on_list_resources=`, etc.) — there is no manual JSON-RPC routing table. `prompts/list`/`prompts/get` would add `on_list_prompts=`/`on_get_prompt=` kwargs the same way. `cache_hints={...}` (`server.py:64-68`) is a single server-wide dict keyed by exact JSON-RPC method name string that the SDK uses to auto-fill `ttlMs`/`cacheScope` (SEP-2549) — handlers never set these fields themselves; a `"prompts/list"` entry needs adding to that same dict.
- `docs/reference/CLI.md`'s `ll-mcp` section is now at lines ~4210-4243 (shifted since this issue's last refine pass) and already documents the tools + resources surfaces landed by FEAT-3135/FEAT-3136; the prompts surface still needs to be added there.
- `scripts/tests/test_mcp_server.py:98-116` (`test_discover_advertises_tools_and_resources_only`) currently asserts `caps.prompts is None` (~line 111) — this assertion must flip once `on_list_prompts`/`on_get_prompt` are registered. The file's existing resource tests (`test_list_resources_returns_issues_goals_and_docs_with_cache_metadata`, `test_read_resource_outside_enumeration_is_rejected`, both in `test_mcp_server.py`) are the closest structural templates for new prompts tests, including the in-process `mcp.client.Client(server)` harness (no JSON-RPC framing, no stdin/stdout) and the `_make_project(tmp_path, monkeypatch)` fixture.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- `server.py`'s module docstring (`server.py:1-10`) currently states "No Roots, Sampling, or Logging handlers are registered" and does not mention Prompts at all — it needs a corresponding update once `on_list_prompts`/`on_get_prompt` are added, matching how the docstring already carries per-surface `(FEAT-3135, FEAT-3136)` commentary.
- Imports inside `build_server()` are function-local, not module-top-level (`server.py:37-46` imports `resources.py`'s three symbols this way) — a `from little_loops.mcp_server.prompts import ...` block for the new module should follow the same function-local style, not be hoisted to the top of the file.
- No `"prompts/get"` precedent exists among the three current `cache_hints` entries (`tools/list`, `resources/list`, `resources/read` — all `ttl_ms=300_000, scope="public"`, `server.py:64-68`). The pattern only covers list-type methods plus one read/get method (`resources/read`); whether a `prompts/get` cache-hint entry is expected the same way is not established by existing precedent and is open for the implementer to decide explicitly, not assumed.

## Program Design

### Signatures
- `little_loops.frontmatter.parse_skill_frontmatter(text) -> dict[str,
  str]` — `frontmatter.py:371`; the canonical frontmatter parser,
  prompts-from-skills should reuse this rather than reimplement parsing.

- `_skill_entries(skills_dir: Path) -> list[ToolDefinition]` — `tool_catalog.py:95`; its `glob("*/SKILL.md")` matches exactly one path segment by construction, not an incidental limitation — a recursive replacement needs `rglob("**/SKILL.md")` or an explicit walk with pruning so a found `SKILL.md`'s own subdirectories are never re-descended as if they were plain supporting files
- `_is_model_invocation_disabled(fm: dict) -> bool` — `adapters/core.py:183`; `None` → `False`, native `bool` returned as-is, anything else stringified/trimmed/lowercased and checked against `{"true", "yes", "1"}`; applied by `process_skills()`/`process_commands()`/`cli/help.py:190` but not universally (`cli/verify_triggers.py`'s loader makes it opt-in via a `model_invocable_only` param)

### Call Path
- prompts-from-skills discovery → new recursive `SKILL.md` walk (not
  `tool_catalog._skill_entries`, which is non-recursive) →
  `little_loops.frontmatter.parse_skill_frontmatter()` → MCP `prompts/list`
  entries

### Decision Rules
N/A — no new gap kind, gate, keyword list, or threshold. Whether the
recursive walker honors the `disable-model-invocation` filter (see
Conventions in Force) is an implementation decision to make explicitly, not
existing decision-rule logic.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- `build_server()` (`scripts/little_loops/mcp_server/server.py:29-69`) — builds `resource_index = build_resource_index(config)` once, then returns `Server("ll-mcp", version=_server_version(), on_list_tools=handle_list_tools, on_call_tool=handle_call_tool, on_list_resources=make_list_resources_handler(resource_index), on_read_resource=make_read_resource_handler(resource_index, config), cache_hints={...})`. A prompts surface follows the identical shape: build a `prompt_index` once (a `build_prompt_index(...)`-style call), then pass `on_list_prompts=make_list_prompts_handler(prompt_index)` (and `on_get_prompt=...` if per-skill body fetch is needed) into the same `Server(...)` call, plus a `"prompts/list"` entry in `cache_hints`.
- `make_list_resources_handler(index) -> Callable`, `make_read_resource_handler(index, config) -> Callable` (`resources.py:197,222`) — the factory-closure pattern to mirror: each returns an `async def` handler closing over a precomputed `dict[str, _ResourceEntry]` built once in `build_resource_index()`. `resources/read`'s entire access-control boundary is `index.get(params.uri) is None` -> `MCPError(code=types.INVALID_PARAMS, ...)`; no path sanitization layered on top — the discovery-time enumeration is what makes traversal impossible, matching this issue's own "Bind resource resolution at discovery, not at call time" requirement. Any per-skill body-fetch handler (a `prompts/get`-equivalent) should use the identical dict-membership-only rejection over an index enumerated once at startup.
- Cache-hint convention: `ttlMs`/`cacheScope` are never set by a handler — `server.py`'s `cache_hints` dict (keyed by exact JSON-RPC method string, e.g. `"resources/list"`) is what the SDK (`mcp.server.caching.apply_cache_hint`) uses to fill them per SEP-2549. All three existing entries use `ttl_ms=300_000, scope="public"`; a `"prompts/list"` entry should follow the same value pair unless this issue's implementer has a reason to diverge.

_Wiring pass added by `/ll:wire-issue`:_
- `.issues/features/P3-FEAT-3134-ll-ctx-stats-mcp-context-cost-measurement.md`
  (FEAT-3134, `status: deferred`, `depends_on: [..., FEAT-3137]`) —
  explicitly states it consumes the `ttlMs`/`cacheScope` fields this issue
  emits on `prompts/list`, alongside FEAT-3135's/FEAT-3136's. This makes
  the `ttl_ms=300_000, scope="public"` cache-hint value pair a load-bearing
  input to a downstream issue's measurement design, not just an internal
  convention — diverging from it would propagate into FEAT-3134.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- `resources.py`'s own `_docs_entries()` (`resources.py:112`) already uses `sorted(docs_dir.rglob("*.md"))` for recursive markdown discovery — a genuinely-recursive walk already present in the very file this issue's `prompts.py` is meant to mirror, alongside `issue_history/collisions.py:83` and `observability/audit.py:173` as further `rglob` sites. This sits in direct tension with the flat `glob("*/SKILL.md")` used at the 4 existing skill-catalog sites (`tool_catalog.py:97`, `adapters/core.py:296`, `cli/help.py:183`, `cli/verify_skill_prose.py:163`), which `.issues/enhancements/P4-ENH-1038-ll-verify-docs-should-track-fsm-loop-counts.md:99,135` documents as a deliberate decision made when every skill directory was exactly one level deep — a precondition this issue's own "nested SKILL.md = separate skill" requirement removes.
- `resources.py`'s factory-closure/stateful-index shape is explicitly called out by its own module docstring (`resources.py:11-14`) as "the first stateful construct in `mcp_server/`... a deliberate, scoped departure from `tools.py`'s statelessness invariant." `tools.py` instead uses a stateless `_TOOL_HANDLERS` dispatch table (`tools.py:182-188`) that rebuilds `BRConfig` from `Path.cwd()` on every call (`tools.py:13-16`). A new `prompts.py` mirroring `resources.py`'s build-once/close-over-index shape continues that same scoped departure from `tools.py`'s pattern, not a third convention.
- Unknown-key rejection follows one consistent 3-part shape across every `resources.py` handler: `raise MCPError(code=types.INVALID_PARAMS, message=f"Unknown <thing>: <value>", data={<param>: <value>})` — identical at `_read_issue_body` (`:156-160`), `_read_goals_body` (`:170-174`), `_read_docs_body` (`:182-186`), and `handle_read_resource` (`:235-239`). A `prompts/get` analog for an unknown skill name follows the identical shape: `MCPError(code=types.INVALID_PARAMS, message=f"Unknown prompt: {params.name}", data={"name": params.name})`.

## Implementation Steps

1. Prompts-from-skills discovery walks `SKILL.md` files recursively (not
   the existing non-recursive `tool_catalog._skill_entries` glob) and
   registers a nested `SKILL.md` as its own independent prompt. The walker
   explicitly decides whether to honor the `disable-model-invocation`
   filter used elsewhere. `prompts/list` responses include
   `ttlMs`/`cacheScope`.
2. `python -m pytest scripts/tests/` passes, including new coverage for the
   nested-`SKILL.md`-discovery walk.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Be aware of `cli/help.py::_skill_entries()` (`:181-209`) as a third
  existing non-recursive skill-walk site (not modified by this issue, but
  its narrower `disable-model-invocation` filtering differs from
  `adapters/core.py`'s blanket skip — see Conventions in Force)
- When deciding whether the new recursive walker honors
  `disable-model-invocation`, prefer matching
  `adapters/core.py::process_skills()`'s blanket-skip behavior (closest in
  intent to an external MCP `prompts/list` surface) over `cli/help.py`'s
  bridge-stub-only dedup or `cli/verify_triggers.py`'s default-unfiltered
  stance

_Wiring pass added by `/ll:wire-issue`:_
- Create `scripts/little_loops/mcp_server/prompts.py`, register
  `on_list_prompts=`/`on_get_prompt=` in `build_server()`
  (`server.py:38-69`), and add a `"prompts/list"` entry to the
  `cache_hints` dict at `ttl_ms=300_000, scope="public"` — the same value
  pair as the three existing entries, since FEAT-3134 depends on this
  convention holding for its context-cost measurement.
- Update `scripts/tests/test_mcp_server.py:111` — flip
  `assert caps.prompts is None` to assert non-`None`.
- Update `docs/reference/API.md:98` and `docs/reference/CLI.md`
  (~4210-4243) — both enumerate the tools+resources surface and need a
  parallel prompts clause.
- Be aware of `cli/verify_skill_prose.py::scan_prose()` (`:163`) as a
  fourth existing non-recursive skill-walk site with its own inline
  `disable-model-invocation` filter variant (not modified by this issue).

## Acceptance Criteria

- Every discovered `SKILL.md` is advertised as an MCP prompt with its name,
  description, and args derived from frontmatter; a nested `SKILL.md` is
  registered as its own skill.
- `prompts/list` responses include `ttlMs` and `cacheScope`.
- `python -m pytest scripts/tests/` passes.

## Session Log
- `/ll:manage-issue` - 2026-08-09T19:14:41 - `edf4cad7-1cdc-4e3a-8be5-67cc7abeac0a.jsonl`
- `/ll:ready-issue` - 2026-08-09T18:54:59 - `46bbb811-67c4-4201-b9e3-86df69d95528.jsonl`
- `/ll:confidence-check` - 2026-08-09T18:51:09 - `0baf3c5c-5881-4dc4-a66c-a1f20046c113.jsonl`
- `/ll:verify-issues` - 2026-08-09T18:49:17 - `3d3acf26-c251-4da2-8935-cff39606e6b0.jsonl`
- `/ll:refine-issue` - 2026-08-09T18:46:10 - `94805c22-a326-419c-8d0d-89b4be72813b.jsonl`
- `/ll:verify-issues` - 2026-08-09T18:41:36 - `47044128-d882-4221-b993-8114f8f411bc.jsonl`
- `/ll:wire-issue` - 2026-08-09T18:38:10 - `eb314c74-9017-4c3b-a35e-854b671f5838.jsonl`
- `/ll:refine-issue` - 2026-08-09T18:28:42 - `144a31dc-73bc-40a6-a107-8414be1a2bbe.jsonl`
- `/ll:wire-issue` - 2026-08-09T14:08:49 - `5aa8ca8f-e752-4f8d-9df6-b510a835085e.jsonl`
- `/ll:refine-issue` - 2026-08-09T13:51:06 - `f453a70a-3ede-4be0-a10b-493541f0278e.jsonl`
- `/ll:issue-size-review` - 2026-08-09T07:40:09 - `153550d2-faf1-4350-b263-1aaa047c80e3.jsonl`
