---
id: 3132
title: 'll-mcp: core read-only server (tools, resources, prompts-from-skills)'
type: FEAT
priority: P3
status: done
discovered_date: '2026-08-09'
verify_verdict: VALID
labels:
- multi-host
- mcp
parent: EPIC-3127
learning_tests_required:
- mcp
relates_to:
- FEAT-3128
size: Very Large
completed_at: '2026-08-09T07:40:54Z'
---

# FEAT-3132: ll-mcp: core read-only server (tools, resources, prompts-from-skills)

## Summary

The core of the `ll-mcp` server: a new `ll-mcp` console entry point in the
`scripts` package running a read-only stdio MCP server against the 2026-07-28
spec. It imports the same `little_loops` library functions the CLIs use — no
shelling out, no daemon; the host spawns it per session like any stdio server.

Three surfaces, all read-only:

1. **Coarse read-only tools** — `issues_query` (list / search / show /
   next-issue / sequence behind one parameterized tool), `issue_get` (full
   body + sections), `history_search`, `deps_check`, and `capabilities` (the
   existing `CapabilityReport`).
2. **MCP resources** for issue files, `ll-goals.md`, and docs, under an
   `ll://` scheme (`ll://issues/FEAT-042`, `ll://docs/…`).
3. **Prompts from skills** — every `SKILL.md` served mechanically as an MCP
   prompt, with name, description, and args read from frontmatter.

`ll-mcp` is added to both permission presets checked by
`verify_cli_allowlist.py` in the same change that registers the console
entry point (they gate on the entry point's mere existence).

## Parent Issue

Decomposed from FEAT-3128: ll-mcp: read-only server (queries, resources,
prompts-from-skills from skills). This child covers the server itself; MCP
config emission (`ll-adapt --host`) and context-cost measurement
(`ll-ctx-stats`) are split into sibling issues because they are separately
testable subsystems that consume this server's surface rather than being
part of it.

## Spec assumptions (MCP 2026-07-28)

- **Stdio transport unchanged.** This tier ships stdio-only; an HTTP entry
  point is a future addition if needed.
- **Caching metadata is part of the contract.** `tools/list`,
  `resources/list`, `prompts/list`, and `resources/read` responses MUST
  include `ttlMs` and `cacheScope` per SEP-2549, and tool ordering is
  guaranteed stable.
- **Explicitly opt out of deprecated primitives.** Do NOT advertise or
  depend on Roots, Sampling, or Logging — all three were deprecated in
  2026-07-28 with a 12-month minimum window.
- **No `initialize` handshake.** Servers handle each request on its own
  merits (protocol version + capabilities arrive in `_meta`). The Python SDK
  v2 implements this; `ll-mcp` must pin the SDK version that ships the new
  behavior.

## Bind resource resolution at discovery, not at call time

The design does not yet say how a resource path is resolved. Because this
server exposes skill-derived resources to arbitrary MCP clients,
`little-loops` is the loader and the trust boundary is external — unlike
host-CLI-owned skill loading elsewhere in the project, where the caller is
already inside the trust boundary.

- **Pre-enumerate supporting files at discovery time.** Walk each skill once
  during startup and record the exact set of readable paths. A resource
  request then accepts a skill name, or a `skill-name/relative/path` that
  was enumerated, and is rejected otherwise. The server must never perform
  an arbitrary filesystem read derived from client-supplied input at call
  time — the enumeration, not path sanitization, is what makes traversal
  impossible.
- **Parse frontmatter only when listing.** `prompts/list` and
  `resources/list` need name, description, and args; reading full skill
  bodies at list time is both a context cost and an unnecessary widening of
  what is loaded. Fetch bodies on demand.
- **Treat a nested `SKILL.md` as a separate skill.** When a skill directory
  contains a subdirectory with its own `SKILL.md`, register it as its own
  skill and do not descend into it as supporting files of the parent, so one
  skill can never serve another's contents.

This boundary must carry forward to the future mutation tier, where it
widens.

## Anti-goals

- **Do not mirror all ~40 `ll-issues` subcommands as tools.** That is a
  context-budget disaster. The whole surface stays coarse.
- **Do not expose orchestration.** `ll-auto`, `ll-parallel`, `ll-loop`, and
  `ll-action invoke` — anything that spawns an agent or runs for minutes —
  stay off the tool surface.
- **Do not reimplement CLI logic.** The server is a facade over the same
  library functions, never a second implementation. Any behavior divergence
  between a tool and its CLI equivalent is a bug in this tier.

## Integration Map

### Files to Modify
- `scripts/pyproject.toml` — add `ll-mcp` console entry point under
  `[project.scripts]` and a new pinned MCP SDK dependency with a
  justification comment (pattern: the `anthropic` pin,
  `scripts/pyproject.toml:40-46`)
- `scripts/little_loops/cli/verify_cli_allowlist.py` — `ll-mcp` is
  `ll-`-prefixed and will NOT get the `mcp-call`-style `_NON_LL_TOOLS`
  exclusion, so it must be added to both permission presets this module
  checks
- `skills/configure/areas.md` — add `ll-mcp` to the "Authorize all
  ll- commands (Recommended)" preset line (`areas.md:849`)
- `scripts/little_loops/init/writers.py` — add `"Bash(ll-mcp:*)"` to the
  `_LL_PERMISSIONS` tuple (`writers.py:80-134`)
- `README.md` — bump the `"N CLI tools"` count line (`README.md:180`); do
  NOT add a `### ll-mcp` section — blocked by
  `test_readme_structure.py::TestReadmeIsHeroPage::test_readme_has_no_ll_cli_sections`
- `scripts/tests/test_wiring_cli_registry.py` — add a
  `("docs/reference/CLI.md", "ll-mcp", "FEAT-3132")`-shaped tuple to
  `DOC_STRINGS_PRESENT`, following the pattern used for prior tools
  (`ll-adapt`, `ll-ctx-stats`)
- A new server module (placement is an open decision — see Program Design →
  Call Path)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — **only if** the three-touch `cli/`
  pattern is chosen for the server's module placement (still an open
  decision per this Integration Map's own "Conventions in Force" note):
  needs an `from little_loops.cli.mcp import main_mcp`-shaped import line and
  a matching `__all__` entry, mirroring `main_adapt` (`cli/__init__.py:47`,
  `__all__` entry line 105) and `main_ctx_stats` (`cli/__init__.py:56`,
  `__all__` entry line 117). Not needed if the `mcp_call.py`-style direct
  wiring path is chosen instead. [codebase-locator finding, confirmed via
  `ll-code importers-of`]

### Dependent Files (Callers/Importers)
- None yet — this is a new entry point with no existing callers.

### Conventions in Force
- New console entry points follow a three-touch pattern (implementation
  module exporting `main_<name>(...) -> int`, a re-export in
  `cli/__init__.py`, a `[project.scripts]` entry) — evidence: `main_ctx_stats`
  (`cli/ctx_stats.py:726`), `main_adapt` (`cli/adapt.py:31`). The existing
  `mcp-call` client instead bypasses `cli/` entirely with direct module
  wiring (`mcp-call = "little_loops.mcp_call:main"`, `pyproject.toml:124`) —
  the two precedents disagree on which shape a long-running stdio server
  should follow; this is a decision the implementer needs to make knowingly.
- New third-party dependencies are pinned with an inline justification
  comment naming the originating issue and the reason an existing
  dependency doesn't suffice — evidence: `anthropic` pin
  (`scripts/pyproject.toml:40-46`), `psutil` pin (`scripts/pyproject.toml:52-58`).
- Skill/command/agent discovery already has one canonical
  frontmatter-parsing utility built explicitly to prevent reimplementation —
  evidence: `scripts/little_loops/tool_catalog.py` docstring (lines 1-9),
  `_skill_entries()` (line 95) walking `skills_dir.glob("*/SKILL.md")` via
  `parse_skill_frontmatter()` (`scripts/little_loops/frontmatter.py:371`).
  This glob is non-recursive and does not descend into nested skill
  directories. The issue's "nested SKILL.md = separate skill" requirement
  needs new recursive-walk logic; `_skill_entries` cannot be reused as-is.
- A second independent skill-walk site exists:
  `adapters/core.py:process_skills()` (line 279) also globs `*/SKILL.md`
  (non-recursive) and applies a `disable-model-invocation` filter via
  `_is_model_invocation_disabled()` (`core.py:180`). Decide whether the new
  prompts-from-skills recursive walker honors this same filter — neither
  existing site's behavior can be assumed by default.
- Blocking stdio reads are bounded via `selectors.DefaultSelector` against a
  deadline, and process teardown always follows terminate → bounded
  `wait()` → kill → bounded `wait()` — evidence:
  `mcp_call.py:_send_jsonrpc()` (lines 76-131, BUG-2778 fix, `done`) and its
  `finally` block (lines 325-338, BUG-2779 fix, `done`). The shared helper
  `subprocess_utils.py:_kill_process_group()` (line 307) backs this pattern
  elsewhere too (`subprocess_utils.py:run_claude_command()`, line 320), a
  second precedent for a bounded-selector+deadline pattern applied to a
  streaming subprocess reading two pipes on one selector — relevant if the
  server's own stdin-reading loop needs the same shape, though no existing
  precedent covers a server reading its own stdin in a long-lived loop.
- CLI tests import CLI module internals directly (not via subprocess) and
  isolate fixtures under `tmp_path` — evidence: `test_cli_ctx_stats.py`,
  `test_mcp_call.py:TestLoadMcpConfig` (lines 43-60).
- No existing convention in this codebase pre-enumerates an allowlist at
  discovery time and rejects requests outside it —
  `skill_expander.py:_resolve_content_path()` (lines 38-52) only does
  existence-checking, and `verify_package_data.py`'s escape lint is a
  build-time source lint, not a runtime request-path validator. The
  resource-resolution boundary this issue requires is new territory in this
  codebase, not a pattern to mirror.
- Adding a new CLI tool triggers a documented, partially-gated checklist in
  `CONTRIBUTING.md` § "Documentation wiring for new CLI tools" —
  `docs/reference/CLI.md` section, `README.md` count-only bump,
  `pyproject.toml` entry point, and both permission presets.
  `ll-verify-cli-allowlist` gates only the last three; the README/CLI.md
  items are gated separately by `test_readme_structure.py` and
  `test_wiring_cli_registry.py::DOC_STRINGS_PRESENT`.

_Wiring pass added by `/ll:wire-issue`:_
- `cli_event_context()` (`scripts/little_loops/session_store/writers.py:472-528+`)
  is a context manager built around one short-lived CLI invocation — it
  opens a `cli_events` row on `__enter__` and records `exit_code`/
  `duration_ms` on `__exit__`, with `duration_ms` measured across the whole
  `with` block. If the three-touch `cli/` pattern is followed and this
  wraps the server's entire stdin-read dispatch loop, the row stays open for
  the process's full lifetime (potentially a whole host session, per this
  issue's own framing), not a discrete command — the same tension the
  issue's Codebase Research Findings already flag for why `mcp_call.py`
  diverges from this convention (no `cli_event_context` wrapper, `sys.exit()`
  contract instead). Resolve this explicitly rather than applying the `cli/`
  pattern unmodified. [codebase-analyzer finding]
- `verify_cli_allowlist.py`'s `_all_ll_entry_points()`
  (`cli/verify_cli_allowlist.py:46-54`) reads **installed distribution
  metadata** via `importlib_metadata.distribution("little-loops")`, not live
  `scripts/pyproject.toml` — a local editable install must be re-synced
  (re-run `pip install -e`, or let PEP 660 regenerate `entry_points.txt`)
  before `ll-mcp` becomes visible to this check or to
  `test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero`.
  [codebase-analyzer finding]

### Tests
- `scripts/tests/test_cli_ctx_stats.py` — precedent for testing a CLI
  module's internals directly
- `scripts/tests/test_mcp_call.py` — precedent for testing MCP config
  loading/dispatch with `tmp_path`-backed `.mcp.json` fixtures; follow its
  `_MockFileObj` / `_make_ready_selector` / `_patch_selector` /
  terminate→kill→wait pattern (lines 139-280) for the new server's own
  subprocess/teardown tests
- New test file needed for the server module itself — no reusable
  server-side harness exists yet; `test_mcp_call.py` only covers the MCP
  *client* side
- New tests for recursive `SKILL.md` discovery — no existing fixture for
  nested skill directories anywhere in `scripts/tests/`; author from
  scratch, extending `test_tool_catalog.py`'s flat `skills/<name>/SKILL.md`
  fixture base with a nested-subdirectory case
- `scripts/tests/test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero`
  — will fail the moment `ll-mcp` is registered in `pyproject.toml
  [project.scripts]` unless `areas.md` and `writers._LL_PERMISSIONS` are
  updated in the same change

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_doctor_install_checks.py::test_real_pyproject_all_entry_points_resolve`
  (lines 42-47) — reads the real `[project.scripts]` table and asserts every
  entry point resolves to an importable callable; will break if `ll-mcp`'s
  target module/callable doesn't import cleanly, gating the entry point
  regardless of which module-placement path is chosen [codebase-pattern-finder
  finding]
- `scripts/tests/test_fsm_runners.py:183-218`
  (`TestSimulationActionRunnerPromptResult`) — closest existing template for
  the new server's own stdin-read dispatch loop test: patches `sys.stdin`
  with `StringIO(input_text)`, includes an EOF-handling case
  (`test_eof_returns_success`, lines 200-205). No existing test in this
  codebase drives a `while True: readline(); dispatch` loop reading its own
  stdin (as opposed to `test_mcp_call.py`'s `_MockFileObj`/
  `_make_ready_selector`, which mocks a *spawned child's* stdout) — this is
  the nearest adaptable pattern, not a direct precedent
  [codebase-pattern-finder finding]
- Existing tests for the library functions each tool/resource wraps show the
  exact shapes a new server-side test needs to mock or reuse fixtures from:
  `test_host_runner.py:1277-1401` (`TestCapabilityReport`,
  `TestDescribeCapabilities` — `capabilities` tool), `test_history_reader.py:581-632`
  (`TestSearch` — `history_search` tool), `test_dependency_mapper.py:577-636,777`
  (`TestValidateDependencies`, `TestAnalyzeDependencies` — `deps_check` tool,
  result object has `.has_issues`/`.broken_refs`/`.missing_backlinks`/
  `.cycles`/`.stale_completed_refs`), `test_frontmatter.py:320-366`
  (`TestParseSkillFrontmatter` — prompts-from-skills edge cases: malformed
  YAML fallback, `None`→`""`, bool stringification), `test_tool_catalog.py:64-121`
  (`TestAssembleToolCatalogSkills` — closest structural template for the new
  recursive `SKILL.md` walk's tests, including an unreadable-file-degrades
  pattern at lines 107-121), `test_adapters.py:102-126,202-235`
  (`_is_model_invocation_disabled` truthy-string matrix, `TestProcessSkillsTraversal`
  emitter-call pattern), `test_goals_parser.py:106-183,392`
  (`TestProductGoals` — full error-path matrix for the `ll-goals.md`
  resource: missing/malformed/empty frontmatter, unreadable file)
  [codebase-pattern-finder finding]

### Documentation
- `docs/reference/CLI.md` — new `ll-mcp` section following the
  `ll-adapt`/`ll-ctx-stats` entries
- `README.md` — bump the `"N CLI tools"` count line (`README.md:180`) only;
  `test_readme_structure.py` blocks a new `### ll-mcp` section
- `CONTRIBUTING.md` § "Documentation wiring for new CLI tools" — check this
  issue's Integration Map against it directly

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — the flat module table (`API.md:60-98`) already
  lists `little_loops.mcp_call` (line 97, "Thin CLI wrapper for direct MCP
  tool invocation via JSON-RPC") as a one-line row alongside every other
  top-level module. If the new server module is placed at package top-level
  (e.g. `little_loops.mcp_server`), it needs an analogous row in this same
  table, following the one-line-description convention of the `mcp_call`
  and `advisor` (line 98) rows immediately above it. Not needed if the
  module instead lives under `cli/` (those aren't individually enumerated in
  this table). [codebase-analyzer finding]

### Configuration
- `scripts/pyproject.toml` `[project.scripts]` (lines 67-124) and
  `dependencies` (lines 40-59) — both need new entries

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **`test_mcp_call.py` harness detail** (relevant to the "New test file needed for the server module itself" gap noted above): `_MockFileObj` (`test_mcp_call.py:139-160`) is a `readline()`+`fileno()`-only fake standing in for `proc.stdout` — needed because `_send_jsonrpc()` registers a real selector on it, and a bare `MagicMock()` has no `fileno()` (cites BUG-2778). `_make_ready_selector()` (`:163-193`) is a `MagicMock` selector that always reports registered fds ready, so progress is driven by the fake `readline()`/EOF rather than the selector. `_patch_selector()` (`:196-201`) patches `little_loops.mcp_call.selectors.DefaultSelector` with that fake. `_make_proc_mock(init_response, call_response)` (`:204-213`) assembles a full fake `Popen`-like object. No test in this file spawns a real subprocess — `subprocess.Popen` itself is always patched. This is client-side scaffolding (mocks a spawned server); testing `ll-mcp` as a server reading its own stdin needs an analogous but inverted harness (fake stdin/stdout for the process under test, not a faked child process) that does not exist yet anywhere in `scripts/tests/`.
- **Dependency-pin comment convention, confirmed identical across three instances**: `anthropic` (`pyproject.toml:46-51`), `psutil` (`:52-58`), and `ruff==0.14.10` (`:141-143`, a dev-dependency pin) all follow the same shape — cite the issue ID that justified the addition, state why an existing/stdlib dependency was insufficient, and justify the version-bound choice (upper-bound vs. lower-bound-only) with the concrete failure mode it prevents.
- **Allowlist-enumeration-then-reject pattern confirmed absent codebase-wide**, not just at the two sites the issue already names: a broader search across `scripts/little_loops/` (CLI, hooks, and adapters layers) for `is_relative_to`/`allowed_paths`/similar path-boundary checks found only `cli/verify_cli_allowlist.py` (an allowlist of CLI *command names*, unrelated) and `cli/logs.py`'s `resolve()` calls (`:716`, `:1265`, `:1270`, which scope log capture to a `current_project` cwd comparison — not a pre-enumerated readable-paths allowlist with reject-outside-allowlist semantics). The resource-resolution boundary this issue requires has no precedent anywhere in the codebase to extend.

## Program Design

### Types
- `little_loops.host_runner.CapabilityReport` (`host_runner.py:181`) —
  existing dataclass the `capabilities` tool returns directly; constructed
  today at `host_runner.py:447,746,865,940,1123,1299,1504`. No new type
  needed for that tool.
- `little_loops.goals_parser.ProductGoals` (`.from_file(path: Path) ->
  ProductGoals | None`, `goals_parser.py:92`) — dataclass with `version`,
  `persona`, `priorities`, `raw_content`; `raw_content` is the full
  markdown, usable directly as the body of an `ll://goals` resource. No
  caller in this module resolves the default `.ll/ll-goals.md` path — the
  resource handler must construct it itself.
- `little_loops.history_reader.SearchResult` — return element type of
  `search()` (`history_reader.py:517`), the shape `history_search` marshals.

### Signatures
- `little_loops.history_reader.search(query, *, kind=None, limit=10,
  db=DEFAULT_DB_PATH) -> list[SearchResult]` — `history_reader.py:517`;
  `history_search` wraps this directly, `kind` filters by
  tool/file/issue/loop/correction/message
- `little_loops.dependency_mapper.validate_dependencies(issues,
  completed_ids, all_known_ids)` — `dependency_mapper/analysis.py:416`,
  used at `cli/deps.py:448`; the `deps_check` tool's direct equivalent
  (broken refs, missing backlinks, cycles, stale refs).
  `analyze_dependencies` (`dependency_mapper/analysis.py:518`, used at
  `cli/deps.py:396,624`) is also read-only and available if a richer
  variant is wanted. Both are re-exported at package level
  (`dependency_mapper/__init__.py:42-48,69-94`), so `from
  little_loops.dependency_mapper import validate_dependencies` remains
  valid.
- `little_loops.frontmatter.parse_skill_frontmatter(text) -> dict[str,
  str]` — `frontmatter.py:371`; the canonical frontmatter parser,
  prompts-from-skills should reuse this rather than reimplement parsing
- Unwrapped, single-line restatement of the above for quick reference:
  `parse_skill_frontmatter(text: str) -> dict[str, str]`
- `CapabilityReport` dataclass fields (`host_runner.py:181-192`), the exact
  shape the `capabilities` tool returns verbatim:
  `host: str`
  `binary: str`
  `version: str`
  `capabilities: list[CapabilityEntry]`
- `SearchResult` dataclass fields (`history_reader.py:126-133`), the exact
  shape `history_search` marshals per result:
  `content: str`
  `kind: str`
  `ref: str`
  `anchor: str`
  `ts: str`
  `score: float`

### Call Path
- `issues_query`/`issue_get` tools → existing `ll-issues` list/search/show/
  next-issue/sequence library functions (`cli/issues/list_cmd.py`,
  `search.py`, `show.py`, `next_issue.py`, `sequence.py`, dispatched from
  `cli/issues/__init__.py`), per the anti-goal behind one parameterized
  tool, not five
- `history_search` tool → `little_loops.history_reader.search()` → SQLite
  FTS5 `search_index` query
- `deps_check` tool → `little_loops.dependency_mapper.validate_dependencies()`
  → issue frontmatter graph
- `capabilities` tool → `little_loops.host_runner.CapabilityReport`
  (existing per-host construction sites)
- prompts-from-skills discovery → new recursive `SKILL.md` walk (not
  `tool_catalog._skill_entries`, which is non-recursive) →
  `little_loops.frontmatter.parse_skill_frontmatter()` → MCP `prompts/list`
  entries

### Decision Rules
N/A — no new gap kind, gate, keyword list, or threshold; this issue
composes an existing protocol surface rather than introducing new
classification logic. One open architectural decision surfaced by research
(module placement for the server entry point: three-touch `cli/` pattern
vs `mcp_call.py`-style direct wiring) is an implementation-route decision,
not decision-rule logic in this section's sense.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **Entry-point precedent, confirmed side by side**: `main_adapt` (`cli/adapt.py:31`) and `main_ctx_stats` (`cli/ctx_stats.py:726`) both wrap their body in `with cli_event_context(DEFAULT_DB_PATH, "ll-<name>", sys.argv[1:]):` and end with plain `return 0`/`return 1` — the int return *is* the exit code, no `sys.exit()` call. `mcp_call.py:main()` (`mcp_call.py:341`) instead returns `None` and calls `sys.exit(exit_code)` directly (`mcp_call.py:394`), with a richer documented exit-code contract than the `cli/` pattern's plain 0/1: `0` success, `1` tool_error, `124` timeout, `127` not_found, `2` usage/config error (`mcp_call.py:10-15`). `mcp_call.py` also has no `cli_event_context` wrapper, no `cli/__init__.py` re-export, and no `__all__`/docstring catalog entry — those three are present for every `cli/` pattern entry point.
- **JSON-RPC framing precedent is newline-delimited, not Content-Length-framed**: `mcp_call.py`'s only existing JSON-RPC code (the client side) writes `json.dumps(request) + "\n"` to `proc.stdin` and reads via `proc.stdout.readline()` + `json.loads()` per line (`mcp_call.py:91-128`), not LSP-style `Content-Length:` header framing. The bounded read loop is `selectors.DefaultSelector()` registered on `proc.stdout` against a `deadline = time.monotonic() + timeout` (`mcp_call.py:99-113`, citing BUG-2777 — prevents a live-but-silent server from blocking `readline()` past deadline). This is client-side (reads a spawned subprocess's stdout); a server reading its own `sys.stdin` would need the NDJSON framing but not the subprocess-pipe selector/deadline shape, since a persistent server loop has no fixed per-call timeout.
- **`parse_skill_frontmatter(text: str) -> dict[str, str]`** (`frontmatter.py:371-413`): returns `{}` if `text` doesn't start with `"---"` or has no closing `---`. Primary path is `yaml.safe_load()`, flattened to `dict[str, str]` — `None` becomes `""`, `bool`/`int`/`float` are stringified, and any list or nested-dict value is silently dropped (not present in the returned dict at all). Fallback (only on `yaml.YAMLError`) is a line-based scan of top-level `key: value` lines only. **`name` is never read from frontmatter** by either existing caller (`tool_catalog._skill_entries`, `adapters/core.py`) — both derive it from `skill_md.parent.name` (the directory name), not a frontmatter field.
- **`disable-model-invocation` filter mechanics**: `_is_model_invocation_disabled(fm: dict) -> bool` (`adapters/core.py:180-192`) — `None` → `False`; native `bool` → returned directly; anything else stringified/trimmed/lowercased and checked against `{"true", "yes", "1"}`. Applied by `adapters/core.py:process_skills()` (`:304`) and `process_commands()` (`:376`), and by `cli/help.py:190` when building the skill catalog listing. It is **not applied universally** — `cli/verify_triggers.py`'s loader (`:306-316`) documents the filter as opt-in via a `model_invocable_only: bool` param specifically because other callers (`issue_history.evolution._load_skill_keywords`) need the full unfiltered population.
- **No existing MCP server-side scaffolding anywhere in this codebase** (confirmed via broad search for `jsonrpc`/`tools/list`/`tools/call`/`mcpServers`/`stdio` markers): every MCP-related file found — `mcp_call.py`, `runner_spec.py:_run_mcp` (line 281, calls `call_mcp_tool`), `cli/harness.py:cmd_mcp` — is client-side, spawning and talking to *external* MCP servers declared in a project's `.mcp.json`. `ll-mcp` would be the first server-side implementation in this codebase; there is no in-repo server loop to model the stdin-reading dispatch loop after.

## Implementation Steps

1. The server module's placement is decided and recorded (three-touch
   `cli/` pattern used by `main_adapt`/`main_ctx_stats` vs
   `mcp_call.py`-style direct module wiring bypassing `cli/`) — every other
   step below depends on where `main_mcp` actually lives.
2. `ll-mcp` is registered as a console entry point in
   `scripts/pyproject.toml` and starts a stdio server against the
   2026-07-28 spec, with a new pinned MCP SDK dependency carrying a
   justification comment matching the `anthropic`/`psutil` precedent.
3. Each of the five read-only tools (`issues_query`, `issue_get`,
   `history_search`, `deps_check`, `capabilities`) resolves to the library
   call named in Program Design → Call Path, with no subprocess invocation
   of any CLI. Responses for `tools/list` include `ttlMs`/`cacheScope` and
   stable ordering.
4. The `ll://` resource surface's discovery-time enumeration (issue files,
   `ll-goals.md`, docs, and per-skill supporting files) is built once at
   startup; `resources/read` is verified to reject any path outside that
   enumeration without performing a filesystem read. `resources/list` and
   `resources/read` responses include `ttlMs`/`cacheScope`.
5. Prompts-from-skills discovery walks `SKILL.md` files recursively (not
   the existing non-recursive `tool_catalog._skill_entries` glob) and
   registers a nested `SKILL.md` as its own independent prompt.
   `prompts/list` responses include `ttlMs`/`cacheScope`.
6. `ll-mcp` is added to both permission presets
   `scripts/little_loops/cli/verify_cli_allowlist.py` checks, since it will
   not get the `mcp-call`-style `_NON_LL_TOOLS` exclusion.
7. `python -m pytest scripts/tests/` passes, including new coverage for the
   server module and the nested-`SKILL.md`-discovery walk.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- If the three-touch `cli/` pattern is chosen for module placement: add
  `main_mcp` import + `__all__` entry to `scripts/little_loops/cli/__init__.py`.
- Resolve the `cli_event_context()` long-lived-process tension explicitly
  (see Conventions in Force) rather than wrapping the entire stdin loop in
  it unmodified — decide and document the chosen shape.
- If the module lives at package top-level (not under `cli/`): add a row to
  `docs/reference/API.md`'s module table (`API.md:60-98`).
- After registering `ll-mcp` in `pyproject.toml`, re-sync the local editable
  install so `_all_ll_entry_points()` (which reads installed distribution
  metadata, not live `pyproject.toml`) and
  `test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero`
  pick it up.
- Write the stdio dispatch loop test adapting `test_fsm_runners.py:183-218`'s
  `StringIO`-as-`sys.stdin` pattern (no existing test drives a
  read-own-stdin dispatch loop).
- `scripts/tests/test_cli_doctor_install_checks.py::test_real_pyproject_all_entry_points_resolve`
  will gate the new entry point automatically — no edit needed, but the
  target module/callable must import cleanly.

## Acceptance criteria

- `ll-mcp` is registered as a console entry point in the `scripts` package
  and runs as a stdio MCP server against the 2026-07-28 spec.
- The tool surface is exactly the five read-only tools listed above; no
  mutating tool is advertised.
- Every tool calls into `little_loops` library functions directly — no
  subprocess invocation of the CLIs.
- Issue files, `ll-goals.md`, and docs are listed and readable as MCP
  resources under the `ll://` scheme.
- Every discovered `SKILL.md` is advertised as an MCP prompt with its name,
  description, and args derived from frontmatter; a nested `SKILL.md` is
  registered as its own skill.
- `resources/read` resolves only against the discovery-time enumeration; a
  request for a path outside it is rejected without a filesystem read.
- `tools/list`, `resources/list`, `prompts/list`, and `resources/read`
  responses include `ttlMs` and `cacheScope`, and tool ordering is stable
  across calls.
- The server advertises no Roots, Sampling, or Logging capability.
- `ll-mcp` is present in both permission presets `verify_cli_allowlist.py`
  checks.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-08-09
- **Reason**: Issue too large for single session (score 8/11, Very Large).
  The issue's own Implementation Steps note that step 1 (module placement)
  blocks every other step, and the three MCP surfaces it names (tools,
  resources, prompts-from-skills) are independently testable once the
  server skeleton exists — a partially-ordered decomposition with real
  parallelism benefit after the first child lands.

### Decomposed Into
- FEAT-3135: ll-mcp: server skeleton, entry point, and tools surface
- FEAT-3136: ll-mcp: ll:// resource surface
- FEAT-3137: ll-mcp: prompts-from-skills surface

## Session Log
- `/ll:issue-size-review` - 2026-08-09T07:40:09 - `153550d2-faf1-4350-b263-1aaa047c80e3.jsonl`
- `/ll:verify-issues` - 2026-08-09T07:35:01 - `770ee1e8-7f64-474e-a38f-e378b4aada4d.jsonl`
- `/ll:refine-issue` - 2026-08-09T07:29:28 - `3cc75e68-cf3c-4c89-9671-fbeabb2b51e6.jsonl`
- `/ll:verify-issues` - 2026-08-09T07:23:00 - `cd816e6e-e503-4f3f-b022-5a09389a0df2.jsonl`
- `/ll:wire-issue` - 2026-08-09T07:15:39 - `5aa2a345-280c-4a3b-bcb7-33aa4d1b89fe.jsonl`
- `/ll:refine-issue` - 2026-08-09T07:05:43 - `8a23a2c9-69f2-40c0-846f-169e3e919094.jsonl`
- `/ll:issue-size-review` - 2026-08-09T06:59:29 - `1a2b4d88-27a6-4756-bc3a-7bce0e10a356.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-08-09
- **Decomposed into**: FEAT-3135, FEAT-3136, FEAT-3137

Work for FEAT-3132 is now carried by its child issues; this parent was closed by rn-decompose.
