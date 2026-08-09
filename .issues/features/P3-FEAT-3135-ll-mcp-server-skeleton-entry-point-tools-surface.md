---
id: 3135
title: 'll-mcp: server skeleton, entry point, and tools surface'
type: FEAT
priority: P3
status: deferred
labels:
- multi-host
- mcp
parent: EPIC-3127
learning_tests_required:
- mcp
relates_to:
- FEAT-3132
verify_verdict: VALID
size: Large
reconcile_attempted: true
confidence_score: 95
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 25
deferred_by: automation
deferred_date: '2026-08-09T08:18:43Z'
deferred_reason: low_readiness
---

# FEAT-3135: ll-mcp: server skeleton, entry point, and tools surface

## Summary

The foundational slice of the `ll-mcp` server: the `ll-mcp` console entry
point, a stdio JSON-RPC dispatch loop against the 2026-07-28 MCP spec, and
the five coarse read-only tools (`issues_query`, `issue_get`,
`history_search`, `deps_check`, `capabilities`). This is the part every
other `ll-mcp` surface (resources, prompts) depends on — it establishes the
running server, the module placement, and the permission wiring that makes
`ll-mcp` a recognized `ll-` entry point.

## Parent Issue

Decomposed from FEAT-3132: ll-mcp: core read-only server (tools, resources,
prompts-from-skills). This child covers the server skeleton and the tools
surface; the `ll://` resource surface and prompts-from-skills are split into
sibling issues (FEAT-3136, FEAT-3137) because they build on this server
existing but are independently testable surfaces once it does.

## Spec assumptions (MCP 2026-07-28)

- **Stdio transport unchanged.** This tier ships stdio-only; an HTTP entry
  point is a future addition if needed.
- **Caching metadata is part of the contract.** `tools/list` responses MUST
  include `ttlMs` and `cacheScope` per SEP-2549, and tool ordering is
  guaranteed stable. (`resources/list`/`prompts/list`/`resources/read` are
  out of scope for this child — see FEAT-3136, FEAT-3137.)
- **Explicitly opt out of deprecated primitives.** Do NOT advertise or
  depend on Roots, Sampling, or Logging — all three were deprecated in
  2026-07-28 with a 12-month minimum window.
- **No `initialize` handshake.** Servers handle each request on its own
  merits (protocol version + capabilities arrive in `_meta`). The Python SDK
  v2 implements this; `ll-mcp` must pin the SDK version that ships the new
  behavior.

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
  `("docs/reference/CLI.md", "ll-mcp", "FEAT-3135")`-shaped tuple to
  `DOC_STRINGS_PRESENT`, following the pattern used for prior tools
  (`ll-adapt`, `ll-ctx-stats`)
- A new server module (placement is an open decision — see Program Design →
  Call Path)
- `scripts/little_loops/cli/__init__.py` — **only if** the three-touch
  `cli/` pattern is chosen for the server's module placement (still an open
  decision per the "Conventions in Force" note below): needs an `from
  little_loops.cli.mcp import main_mcp`-shaped import line and a matching
  `__all__` entry, mirroring `main_adapt` (`cli/__init__.py:47`, `__all__`
  entry line 105) and `main_ctx_stats` (`cli/__init__.py:56`, `__all__`
  entry line 117). Not needed if the `mcp_call.py`-style direct wiring path
  is chosen instead.

### Dependent Files (Callers/Importers)
- None yet — this is a new entry point with no existing callers. FEAT-3136
  and FEAT-3137 will import this module's dispatch/registration machinery
  once it exists.

### Conventions in Force
- New console entry points follow a three-touch pattern (implementation
  module exporting `main_<name>(...) -> int`, a re-export in
  `cli/__init__.py`, a `[project.scripts]` entry) — evidence: `main_ctx_stats`
  (`cli/ctx_stats.py:726`), `main_adapt` (`cli/adapt.py:31`). The existing
  `mcp-call` client instead bypasses `cli/` entirely with direct module
  wiring (`mcp-call = "little_loops.mcp_call:main"`, `pyproject.toml:124`) —
  the two precedents disagree on which shape a long-running stdio server
  should follow; this is a decision the implementer needs to make knowingly,
  and it determines where FEAT-3136/FEAT-3137 hang their registration code.
- New third-party dependencies are pinned with an inline justification
  comment naming the originating issue and the reason an existing
  dependency doesn't suffice — evidence: `anthropic` pin
  (`scripts/pyproject.toml:40-46`), `psutil` pin (`scripts/pyproject.toml:52-58`).
- Blocking stdio reads are bounded via `selectors.DefaultSelector` against a
  deadline, and process teardown always follows terminate → bounded
  `wait()` → kill → bounded `wait()` — evidence:
  `mcp_call.py:_send_jsonrpc()` (lines 76-131, BUG-2778 fix) and its
  `finally` block (lines 325-338, BUG-2779 fix). That pattern is
  client-side (reads a spawned subprocess's stdout); this server reads its
  own `sys.stdin` in a persistent loop with no fixed per-call timeout, so
  the selector/deadline shape doesn't transfer directly — the NDJSON
  framing (see Codebase Research Findings below) does.
- CLI tests import CLI module internals directly (not via subprocess) and
  isolate fixtures under `tmp_path` — evidence: `test_cli_ctx_stats.py`,
  `test_mcp_call.py:TestLoadMcpConfig` (lines 43-60).
- Adding a new CLI tool triggers a documented, partially-gated checklist in
  `CONTRIBUTING.md` § "Documentation wiring for new CLI tools" —
  `docs/reference/CLI.md` section, `README.md` count-only bump,
  `pyproject.toml` entry point, and both permission presets.
  `ll-verify-cli-allowlist` gates only the last three; the README/CLI.md
  items are gated separately by `test_readme_structure.py` and
  `test_wiring_cli_registry.py::DOC_STRINGS_PRESENT`.

### Tests
- `scripts/tests/test_cli_ctx_stats.py` — precedent for testing a CLI
  module's internals directly
- `scripts/tests/test_mcp_call.py` — precedent for testing MCP config
  loading/dispatch with `tmp_path`-backed `.mcp.json` fixtures; follow its
  `_MockFileObj` / `_make_ready_selector` / `_patch_selector` /
  terminate→kill→wait pattern (lines 139-280) for this new server's own
  subprocess/teardown tests
- New test file needed for the server module itself — no reusable
  server-side harness exists yet; `test_mcp_call.py` only covers the MCP
  *client* side
- `scripts/tests/test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero`
  — will fail the moment `ll-mcp` is registered in `pyproject.toml
  [project.scripts]` unless `areas.md` and `writers._LL_PERMISSIONS` are
  updated in the same change
- `scripts/tests/test_verify_cli_allowlist.py::TestMainVerifyCliAllowlist::test_clean_state_returns_zero`
  (lines 51-54) — a second, distinct end-to-end test (`main_verify_cli_allowlist()`
  via a patched `sys.argv`) that breaks the same way and for the same reason
  as the `TestRun` variant above; both must stay green, not just one
  [`/ll:wire-issue` finding]

### Wiring pass added by `/ll:wire-issue`

- `scripts/tests/test_wiring_guides_and_meta.py:93` — the parametrized
  `DOC_STRINGS_PRESENT` tuple `("README.md", "47 typed CLI tools",
  "FEAT-1045")` asserts the literal count string in `README.md:180`; this
  test will break the moment the README count line is bumped for `ll-mcp`
  unless the tuple's string is updated in the same change (e.g. to "48
  typed CLI tools")
- `scripts/little_loops/cli/issues/search.py::_load_issues_with_status`
  (line 121) has no unit test isolating it directly — unlike its sibling
  `build_sort_key` (covered by `TestBuildSortKey` in
  `scripts/tests/test_issues_search.py:971-1043`), it's only exercised
  transitively through full `ll-issues search`/`next-issue` CLI-level
  tests. Since `issues_query`'s status-tagging behavior (open/in_progress/
  blocked/deferred/done/cancelled, including legacy-dir handling) depends
  directly on this helper, a new unit test isolating it is needed alongside
  the tool implementation, not just CLI-level coverage
- `scripts/tests/test_show.py` (lines ~205-494) — existing direct coverage
  for `_parse_card_fields` (`cli/issues/show.py:154`), the function
  `issue_get` wraps; confirms low regression risk for that call path, no
  new test file needed for the underlying helper itself
- `scripts/tests/test_cli_doctor_install_checks.py::test_real_pyproject_all_entry_points_resolve`
  — reads the real `[project.scripts]` table and asserts every entry point
  resolves to an importable callable; will break if `ll-mcp`'s target
  module/callable doesn't import cleanly
- `scripts/tests/test_fsm_runners.py:183-218`
  (`TestSimulationActionRunnerPromptResult`) — closest existing template for
  the new server's own stdin-read dispatch loop test: patches `sys.stdin`
  with `StringIO(input_text)`, includes an EOF-handling case
  (`test_eof_returns_success`, lines 200-205). No existing test in this
  codebase drives a `while True: readline(); dispatch` loop reading its own
  stdin — this is the nearest adaptable pattern, not a direct precedent
- Existing tests for the library functions each tool wraps show the exact
  shapes a new server-side test needs to mock or reuse fixtures from:
  `test_host_runner.py:1277-1401` (`TestCapabilityReport`,
  `TestDescribeCapabilities` — `capabilities` tool), `test_history_reader.py:581-632`
  (`TestSearch` — `history_search` tool), `test_dependency_mapper.py:577-636,777`
  (`TestValidateDependencies`, `TestAnalyzeDependencies` — `deps_check` tool,
  result object has `.has_issues`/`.broken_refs`/`.missing_backlinks`/
  `.cycles`/`.stale_completed_refs`)

### Documentation
- `docs/reference/CLI.md` — new `ll-mcp` section following the
  `ll-adapt`/`ll-ctx-stats` entries, covering the entry point and the tools
  surface (FEAT-3136/FEAT-3137 extend this same section)
- `README.md` — bump the `"N CLI tools"` count line (`README.md:180`) only;
  `test_readme_structure.py` blocks a new `### ll-mcp` section
- `CONTRIBUTING.md` § "Documentation wiring for new CLI tools" — check this
  issue's Integration Map against it directly
- `docs/reference/API.md` — the flat module table (`API.md:60-98`) already
  lists `little_loops.mcp_call` (line 97) as a one-line row alongside every
  other top-level module. If the new server module is placed at package
  top-level (e.g. `little_loops.mcp_server`), it needs an analogous row in
  this same table. Not needed if the module instead lives under `cli/`
  (those aren't individually enumerated in this table).

### Configuration
- `scripts/pyproject.toml` `[project.scripts]` (lines 67-124) and
  `dependencies` (lines 40-59) — both need new entries

### Codebase Research Findings

- **`test_mcp_call.py` harness detail**: `_MockFileObj`
  (`test_mcp_call.py:139-160`) is a `readline()`+`fileno()`-only fake
  standing in for `proc.stdout` — needed because `_send_jsonrpc()`
  registers a real selector on it, and a bare `MagicMock()` has no
  `fileno()` (cites BUG-2778). `_make_ready_selector()` (`:163-193`) is a
  `MagicMock` selector that always reports registered fds ready.
  `_patch_selector()` (`:196-201`) patches
  `little_loops.mcp_call.selectors.DefaultSelector` with that fake.
  `_make_proc_mock(init_response, call_response)` (`:204-213`) assembles a
  full fake `Popen`-like object. No test in this file spawns a real
  subprocess. This is client-side scaffolding (mocks a spawned server);
  testing `ll-mcp` as a server reading its own stdin needs an analogous but
  inverted harness (fake stdin/stdout for the process under test) that does
  not exist yet anywhere in `scripts/tests/`.
- **Dependency-pin comment convention, confirmed identical across three
  instances**: `anthropic` (`pyproject.toml:46-51`), `psutil` (`:52-58`),
  and `ruff==0.14.10` (`:141-143`) all follow the same shape — cite the
  issue ID that justified the addition, state why an existing/stdlib
  dependency was insufficient, and justify the version-bound choice with
  the concrete failure mode it prevents.
- **JSON-RPC framing precedent is newline-delimited, not
  Content-Length-framed**: `mcp_call.py`'s only existing JSON-RPC code (the
  client side) writes `json.dumps(request) + "\n"` to `proc.stdin` and
  reads via `proc.stdout.readline()` + `json.loads()` per line
  (`mcp_call.py:91-128`), not LSP-style `Content-Length:` header framing.
  This is client-side; a server reading its own `sys.stdin` needs the
  NDJSON framing but not the subprocess-pipe selector/deadline shape, since
  a persistent server loop has no fixed per-call timeout.
- **No existing MCP server-side scaffolding anywhere in this codebase**
  (confirmed via broad search for `jsonrpc`/`tools/list`/`tools/call`/
  `mcpServers`/`stdio` markers): every MCP-related file found —
  `mcp_call.py`, `runner_spec.py:_run_mcp` (line 281, calls
  `call_mcp_tool`), `cli/harness.py:cmd_mcp` — is client-side, spawning and
  talking to *external* MCP servers declared in a project's `.mcp.json`.
  `ll-mcp` is the first server-side implementation in this codebase; there
  is no in-repo server loop to model the stdin-reading dispatch loop after.
- **`cli_event_context()` tension**
  (`scripts/little_loops/session_store/writers.py:472-528+`) is a context
  manager built around one short-lived CLI invocation — it opens a
  `cli_events` row on `__enter__` and records `exit_code`/`duration_ms` on
  `__exit__`, with `duration_ms` measured across the whole `with` block. If
  the three-touch `cli/` pattern is followed and this wraps the server's
  entire stdin-read dispatch loop, the row stays open for the process's
  full lifetime (potentially a whole host session), not a discrete command.
  `mcp_call.py` diverges from this convention entirely (no
  `cli_event_context` wrapper, `sys.exit()` contract instead
  (`mcp_call.py:394`), with a richer documented exit-code contract: `0`
  success, `1` tool_error, `124` timeout, `127` not_found, `2` usage/config
  error, `mcp_call.py:10-15`). Resolve this explicitly rather than applying
  the `cli/` pattern unmodified.
- **`verify_cli_allowlist.py`'s `_all_ll_entry_points()`**
  (`cli/verify_cli_allowlist.py:46-54`) reads **installed distribution
  metadata** via `importlib_metadata.distribution("little-loops")`, not
  live `scripts/pyproject.toml` — a local editable install must be
  re-synced (re-run `pip install -e`, or let PEP 660 regenerate
  `entry_points.txt`) before `ll-mcp` becomes visible to this check or to
  `test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero`.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **No stdin server-loop test precedent exists**: confirmed by direct read of the three closest candidates. `mcp_call.py:_send_jsonrpc()` (lines 107-132) is client-side — it reads a *spawned subprocess's* stdout via a `selectors`-bounded `readline()`, not its own stdin, and has no dedicated loop-iteration unit test (exercised only through `call_mcp_tool()` integration behavior). `hooks/__init__.py:main_hooks()` (line 189) and its tests (`test_hook_intents.py:622,655,680,702,724,752,785`) patch `sys.stdin` to a `StringIO` holding exactly one JSON blob per test — single-shot, not a loop. `fsm/runners.py:_prompt_result()` (488-502) and `test_fsm_runners.py:_run_with_stdin()` (183-216) also feed one bounded `StringIO` per test. No test in this codebase feeds a multi-line `StringIO` and asserts multiple stdout writes — `ll-mcp`'s dispatch-loop test needs a new fixture shape, not an adaptation of an existing one.
- **Two disagreeing N-verb dispatch conventions**: (a) dict-registry keyed by name, `.get()` lookup, `sorted(handlers)` for the unknown-name error — `hooks/__init__.py:_dispatch_table()` (134-165) + `main_hooks()` (168-187); (b) argparse subparsers + a long `if/elif args.command == ...` chain — `cli/issues/__init__.py:974+` and `cli/code.py:130-134` (~40-way and smaller N-way respectively). The five-tool `ll-mcp` `tools/call` routing is closer in scale to (a) but (a)'s only existing use has no argument-parsing layer to bypass, unlike an MCP tool call's params dict.
- **Three coexisting, non-interchangeable dataclass→JSON conventions**: generic `dataclasses.asdict()` at the call site for plain dataclasses like `SearchResult` (`cli/history.py:392,410,457`, `cli/session.py:433,453,476,697,729`, `cli/code.py:160`, `cli/help.py:230`); hand-rolled dict construction for `CapabilityReport`/`CapabilityEntry` — no call site uses `asdict()` on these despite them being frozen dataclasses (`cli/action.py:335-366`, `cli/doctor.py:956`); and a dataclass-owned `to_dict()`/`from_dict()` pair for wire-format types that skips `None`-valued optional fields rather than emitting explicit nulls (`hooks/types.py:47-81`, `events.py:45,54`). `history_search`/`capabilities` tool responses need to pick one of these three deliberately, not default to whichever a reference implementation happens to use.
- **No `ttlMs`/`cacheScope` precedent exists anywhere in this codebase** (confirmed by exact-string grep across `scripts/little_loops/`) — the issue's own Program Design section is the first place these terms appear. The closest structural precedent for attaching optional per-entry metadata to a "list of advertised things" response is `tool_catalog.py::to_anthropic_tools()` (158-184): it omits `cache_control` entirely when unset rather than emitting a JSON `null` ("the Anthropic API rejects a literal null cache_control value", comment at 163-165), and its stable ordering comes from `sorted(...)`-glob on filename (lines 97,114,131) rather than an explicit sequence field.
- **Signal-handling precedent for long-running `ll-*` processes** (three existing daemons/watchers, none stdin-driven): `cli/queue.py::_run_watch()` (624) installs `SIGINT`/`SIGTERM` via `signal.signal()` with previous-handler restore in a `finally` (673-675); its handler `_make_signal_handler()` (597) implements two-stage shutdown via `threading.Event`s (first signal = graceful drain, second = force-kill an in-flight child via `_kill_current_loop_proc()`, 610-619). `cli/sprint/run.py::_sprint_signal_handler()` (134) mirrors this with a module-global flag instead of an Event, no handler restore. `issue_manager.py` (~1671) uses a simpler single-stage `self._shutdown_requested` flag. `parallel/orchestrator.py::_setup_signal_handlers()`/`_restore_signal_handlers()` (252, 257) also save/restore prior handlers. None of these treat EOF-on-stdin as a shutdown trigger — that would be new for `ll-mcp`. The "peer closed the pipe" idiom (`if not response_line: break`) exists only client-side, at `mcp_call.py:118`.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **Exact insertion points for the two `verify_cli_allowlist.py` presets** (gap-fill on the already-cited files): `skills/configure/areas.md`'s comma-separated tool list (`areas.md:849`, inside the `"Authorize all"` description line, parsed by `_areas_md_preset_tools()` via `_TOOL_TOKEN_RE`, `verify_cli_allowlist.py:30,62`) — `ll-mcp` inserts alphabetically between `ll-loop` and `ll-messages`. `writers.py`'s `_LL_PERMISSIONS` tuple (parsed by `_writers_preset_tools()` via regex on `Bash(ll-<name>:*)` lines, `verify_cli_allowlist.py:74`) — `ll-mcp` inserts alphabetically between `ll-migrate-status` and `ll-parallel`. The exclusion mechanism that lets `mcp-call` skip both presets is `_NON_LL_TOOLS = frozenset({"mcp-call"})` (`verify_cli_allowlist.py:28`); it matches on the literal name `mcp-call`, not a `mcp-*` prefix, so `ll-mcp` (named `ll-`, not `mcp-`) does not qualify for it regardless.
- **Exact insertion points for the three-touch `cli/__init__.py` pattern**, if chosen: import line `from little_loops.cli.mcp import main_mcp` inserted after `main_migrate_status` (line 79) and before `main_parallel` (line 80) in the import block (lines 46-101, alphabetized by module path); `__all__` entry `"main_mcp"` inserted in the equivalent slot — note the `__all__` list is alphabetized only through roughly line 124, after which it drifts to loosely-grouped historical-addition order, so this second insertion point is looser than the import block's. The module docstring (lines 4-43, one `- ll-<name>: <summary>` bullet per tool) is stylistic convention only — not test-enforced against `_all_ll_entry_points()`.
- **`docs/reference/CLI.md` section template**: every existing tool section follows `### <binary-name>` → one-paragraph description → `**Flags:**` or `**Arguments:**` table → one-line `**Exit codes:**` legend → `**Examples:**` fenced bash block → `---` separator. `### mcp-call` (`CLI.md:4210-4231`) is the closest sibling — positional-arg style (`**Arguments:**`, inline exit-code sentence: `0` success, `1` tool error, `2` usage/config error, `124` timeout, `127` not found) vs. `### ll-init` (`CLI.md:35-79`), the flag-heavy alternative (`**Flags:**` table + separate `**Subcommands:**` table). Both agree on section ordering and a one-line exit-code legend over prose.

## Program Design

### Types
- `little_loops.host_runner.CapabilityReport` (`host_runner.py:181`) —
  existing dataclass the `capabilities` tool returns directly; constructed
  today at `host_runner.py:447,746,865,940,1123,1299,1504`. No new type
  needed for that tool.
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
  (`dependency_mapper/__init__.py:42-48,69-94`).
- `CapabilityReport` dataclass fields (`host_runner.py:181-192`), the exact
  shape the `capabilities` tool returns verbatim:
  `host: str`, `binary: str`, `version: str`,
  `capabilities: list[CapabilityEntry]`
- `SearchResult` dataclass fields (`history_reader.py:126-133`), the exact
  shape `history_search` marshals per result:
  `content: str`, `kind: str`, `ref: str`, `anchor: str`, `ts: str`,
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

### Decision Rules
N/A — no new gap kind, gate, keyword list, or threshold; this issue
composes an existing protocol surface rather than introducing new
classification logic. The one open architectural decision (module
placement for the server entry point: three-touch `cli/` pattern vs
`mcp_call.py`-style direct wiring) is an implementation-route decision, not
decision-rule logic in this section's sense — and it must be resolved here,
first, since FEAT-3136 and FEAT-3137 build directly on whatever this child
lands.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- The five Call Path targets split on callability, which determines whether `issues_query`/`issue_get` need a synthesized `argparse.Namespace` or a rewrite to call lower-level helpers directly:
  - `little_loops.dependency_mapper.analysis.validate_dependencies(issues, completed_ids=None, all_known_ids=None) -> ValidationResult` (`dependency_mapper/analysis.py:416`) is a pure function with no argparse coupling — directly callable as-is for `deps_check`.
  - `cli/issues/list_cmd.py::cmd_list`, `search.py::cmd_search`, `show.py::cmd_show`, `next_issue.py::cmd_next_issue`, `sequence.py::cmd_sequence` all share the signature `(config: BRConfig, args: argparse.Namespace) -> int`, read filters off `args` via `getattr`, and return nothing structured — output is side-effecting `print`/`print_json` only. None of these five is directly callable from a tool handler without either synthesizing an `argparse.Namespace` or bypassing them.
  - Two reusable non-argparse helpers already exist and are already imported directly by `list_cmd.py` itself, making them the cleaner call surface for `issues_query`: `search.py::_load_issues_with_status(config, include_open, include_done, include_deferred) -> list[tuple[IssueInfo, str]]` (`search.py:121`) and `search.py::build_sort_key(config: NextIssueConfig) -> Callable[[IssueInfo], tuple]` (`search.py:185`).
  - `show.py::_parse_card_fields(path, config) -> dict[str, str | None]` (`show.py:154`) is the equivalent non-argparse surface for `issue_get` — it already returns the full card-field dict that `cmd_show` only forwards to `print_json`/`_render_card`.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **`deps_check` cannot pass raw JSON straight through**: `validate_dependencies(issues, completed_ids=None, all_known_ids=None) -> ValidationResult` (`dependency_mapper/analysis.py:416`) requires `issues: list[IssueInfo]` — objects exposing `.issue_id`, `.blocked_by`, `.blocks`, `.depends_on`, `.relates_to`, `.duplicate_of` (the `little_loops.issue_parser.IssueInfo` dataclass) — not raw dicts or the JSON shape `issues_query`/`issue_get` return. A `deps_check` tool handler must parse issue files into `IssueInfo` objects first; `cli/deps.py::_load_issues()` (lines 15-69) is the existing assembly function doing exactly this (via `find_issues_for_graph(config)` + a second done/cancelled-status pass), and is the callable to reuse or mirror rather than reimplementing the parse. `all_known_ids` is populated in the CLI path by `gather_all_issue_ids()` (`dependency_mapper/operations.py:362`, a filename-regex scan over category dirs, not full parsing) — `cli/deps.py:379-390` wraps that call in a defensive `try/except Exception`, falling back to `{i.issue_id for i in issues}` on failure. `ValidationResult` (`dependency_mapper/models.py:53-83`) returns six `list[tuple[str, str]]`/`list[list[str]]` fields (`broken_refs`, `missing_backlinks`, `cycles`, `stale_completed_refs`, `broken_depends_on_refs`, `broken_relates_to_refs`) plus a `has_issues` bool property ORing all six; `cli/deps.py:450-467` is the precedent JSON-encoding shape (each tuple pair listed via `list(pair)`) a `deps_check` tool's response should mirror.
- **No `_meta`-based capability negotiation exists in this codebase to verify the "no `initialize` handshake" spec assumption against.** Searches for `initialize`, `_meta`, `capabilities`, `protocolVersion` outside `mcp_call.py` found no hits. The only existing MCP-JSON-RPC code, `mcp_call.py` (client-side), performs the **old-style** `initialize` request + `notifications/initialized` handshake (`mcp_call.py:230-252,265-268`, `MCP_PROTOCOL_VERSION = "2024-11-05"` constant at line 32) — a live counter-example to the 2026-07-28 server-side simplification this issue assumes, though not a contradiction since it's a client speaking to arbitrary (possibly older-spec) servers. No `mcp` (official MCP Python SDK) package appears anywhere in `pyproject.toml` or as an import in `scripts/little_loops/` — the SDK dependency this issue's Implementation Steps calls for pinning is entirely absent from the repo today, so its `_meta`-negotiation behavior rests entirely on the SDK's own (currently unverified-against-this-codebase) implementation.
- **Three coexisting, non-interchangeable conventions for a stable ordered "list of things" response** (relevant to `tools/list`'s required stable ordering): (a) `tool_catalog.py`'s `_skill_entries`/`_command_entries`/`_agent_entries` (lines 95-142) derive order via `sorted(dir.glob(...))` over a directory walk, tolerating a missing directory as zero entries; (b) `host_runner.py`'s per-host `CapabilityReport.capabilities` builders (e.g. lines 452-487, 751-794, 1128-1157) hand-write an ordered literal `list[CapabilityEntry(...)]` in source order; (c) `hooks/__init__.py`'s `_dispatch_table()` (line 134) is a `dict[str, Callable]` registry paired with a hand-maintained, not-test-enforced `_USAGE` string (lines 111-116) that must independently stay in sync with the dict's keys. All three guarantee deterministic, code-defined order; none relies on incidental filesystem/dict iteration order — but they disagree on mechanism, so `tools/list`'s five-tool ordering needs one deliberately chosen, not inherited from whichever precedent is read first.
- **SDK/dependency pin convention has an unresolved disagreement to account for**: the two existing justification-commented pins disagree on whether an upper bound is required — `anthropic>=0.104,<1.0` (`pyproject.toml:46-51`) pins both bounds, `psutil>=5.9` (`pyproject.toml:52-58`) pins only a lower bound. Neither precedent wraps or re-exports the third-party SDK's own types/exceptions in a dedicated module; `anthropic` is imported lazily inline at each call site (`host_runner.py:1883,1960`, explicitly to dodge a circular import, not as an SDK-wrapping policy) and its exceptions are caught by SDK class name at the call site (`except anthropic.APIError as exc:`, `host_runner.py:1965`) and converted into the codebase's own result dataclass rather than re-raised. A new MCP SDK pin should resolve the bound-strictness question explicitly rather than defaulting to whichever precedent is copied.
- **No test precedent exists for a real, spawned-subprocess, multi-turn server-loop test** — confirmed by search for `Popen([sys.executable, "-m" ...])` / multi-turn `communicate(input=...)` patterns in `scripts/tests/` (only unrelated git-subprocess tests matched). The nearest precedent, `test_mcp_call.py`, tests the *client* side entirely via `MagicMock`-based `Popen`/`selectors` patching (`_make_proc_mock()`, `_MockFileObj`, `_patch_selector()`, lines 204,139,196) with no real subprocess spawned. The only tested pattern available to model `ll-mcp`'s own dispatch-loop test against is unit-level stdin/stdout mocking (patch stdin, feed N lines, assert N responses) — there is no "spawn the real binary, drive it over a live pipe" precedent anywhere in this codebase.

## Implementation Steps

1. The server module's placement is decided and recorded (three-touch
   `cli/` pattern used by `main_adapt`/`main_ctx_stats` vs
   `mcp_call.py`-style direct module wiring bypassing `cli/`) — FEAT-3136
   and FEAT-3137 both depend on where `main_mcp` actually lives.
2. `ll-mcp` is registered as a console entry point in
   `scripts/pyproject.toml` and starts a stdio server against the
   2026-07-28 spec (NDJSON framing, no `initialize` handshake), with a new
   pinned MCP SDK dependency carrying a justification comment matching the
   `anthropic`/`psutil` precedent. The `cli_event_context()` long-lived-
   process tension is resolved explicitly (see Conventions in Force) rather
   than wrapping the entire stdin loop in it unmodified.
3. Each of the five read-only tools (`issues_query`, `issue_get`,
   `history_search`, `deps_check`, `capabilities`) resolves to the library
   call named in Program Design → Call Path, with no subprocess invocation
   of any CLI. `tools/list` responses include `ttlMs`/`cacheScope` and
   stable ordering.
4. `ll-mcp` is added to both permission presets
   `scripts/little_loops/cli/verify_cli_allowlist.py` checks, since it will
   not get the `mcp-call`-style `_NON_LL_TOOLS` exclusion.
5. The server advertises no Roots, Sampling, or Logging capability.
6. `python -m pytest scripts/tests/` passes, including new coverage for the
   server module's dispatch loop and the five tools.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_wiring_guides_and_meta.py:93` — bump the
  `DOC_STRINGS_PRESENT` tuple's `"47 typed CLI tools"` literal to match the
  new count in the same change as the `README.md:180` bump
- Add a unit test isolating `cli/issues/search.py::_load_issues_with_status`
  (currently only covered transitively) alongside the `issues_query` tool
  implementation
- Confirm both `test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero`
  and `::TestMainVerifyCliAllowlist::test_clean_state_returns_zero` pass —
  not just one of the two end-to-end variants

## Acceptance criteria

- `ll-mcp` is registered as a console entry point in the `scripts` package
  and runs as a stdio MCP server against the 2026-07-28 spec.
- The tool surface is exactly the five read-only tools listed above; no
  mutating tool is advertised.
- Every tool calls into `little_loops` library functions directly — no
  subprocess invocation of the CLIs.
- `tools/list` responses include `ttlMs` and `cacheScope`, and tool
  ordering is stable across calls.
- The server advertises no Roots, Sampling, or Logging capability.
- `ll-mcp` is present in both permission presets `verify_cli_allowlist.py`
  checks.
- `python -m pytest scripts/tests/` passes.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-09_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- No in-repo precedent for a persistent `while True: readline → dispatch` stdin server loop — nearest analogues (`test_fsm_runners.py`, `main_hooks()`) are single-shot `StringIO` tests, so the new dispatch-loop test harness has to be built from scratch, not adapted.
- Several implementation-route decisions remain genuinely open at write time even though the issue documents each option well: server module placement (three-touch `cli/` vs `mcp_call.py`-style direct wiring), the `cli_event_context()` long-lived-process tension, the SDK version-pin bound strictness, and which of three coexisting dataclass→JSON conventions the tool responses should follow — each requires a judgment call during implementation.
- Confirmed via a scratch `mcp==2.0.0` learning-test proof (`.ll/learning-tests/mcp.md`): the installed system SDK is 1.21.0, which does *not* implement the no-`initialize`-handshake behavior this issue assumes — only 2.0.0 does. The pin must target 2.0.0 specifically, not "whatever `pip install mcp` resolves to" in an unpinned environment.

## Session Log
- `/ll:confidence-check` - 2026-08-09T08:17:58 - `042e13ad-a334-4923-8e46-6474a3ddf3dd.jsonl`
- `/ll:reconcile-issue` - 2026-08-09T08:12:41 - `a43d576b-311c-4dc4-9503-e85cef5e3d8c.jsonl`
- `/ll:verify-issues` - 2026-08-09T08:09:14 - `f730fd5c-232d-4c9a-9c1a-183dc938f25c.jsonl`
- `/ll:refine-issue` - 2026-08-09T08:04:25 - `24e59e6a-4438-4d10-8783-fdb2abc8380a.jsonl`
- `/ll:wire-issue` - 2026-08-09T07:54:44 - `03413e2d-017e-4cb9-8625-9740c56c1512.jsonl`
- `/ll:refine-issue` - 2026-08-09T07:46:49 - `fc612f00-613e-4252-b9ba-f6cc15f65c73.jsonl`
- `/ll:issue-size-review` - 2026-08-09T07:40:08 - `153550d2-faf1-4350-b263-1aaa047c80e3.jsonl`
