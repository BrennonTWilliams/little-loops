---
id: 3135
title: 'll-mcp: server skeleton, entry point, and tools surface'
type: FEAT
priority: P3
status: open
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
---

# FEAT-3135: ll-mcp: server skeleton, entry point, and tools surface

## Summary

The foundational slice of the `ll-mcp` server: the `ll-mcp` console entry
point, a stdio MCP server built on the official `mcp` Python SDK v2 against
the 2026-07-28 spec, and the five coarse read-only tools (`issues_query`,
`issue_get`, `history_search`, `deps_check`, `capabilities`). This is the
part every other `ll-mcp` surface (resources, prompts) depends on — it
establishes the running server, the module placement, and the permission
wiring that makes `ll-mcp` a recognized `ll-` entry point.

**The SDK owns the protocol.** This issue does not hand-roll JSON-RPC
framing, method routing, `ttlMs`/`cacheScope` attachment, or `server/discover`
— all four are SDK-provided (proven in `.ll/learning-tests/mcp.md`). The work
here is: the entry point, the async wiring, five handler functions over
existing library calls, and the permission/doc plumbing.

## Parent Issue

Decomposed from FEAT-3132: ll-mcp: core read-only server (tools, resources,
prompts-from-skills). This child covers the server skeleton and the tools
surface; the `ll://` resource surface and prompts-from-skills are split into
sibling issues (FEAT-3136, FEAT-3137) because they build on this server
existing but are independently testable surfaces once it does.

## Spec assumptions (MCP 2026-07-28)

- **Stdio transport unchanged.** This tier ships stdio-only; an HTTP entry
  point is a future addition if needed. The 2026-07-28 release also formally
  deprecates the HTTP+SSE transport, so a future HTTP tier targets streamable
  HTTP, never HTTP+SSE. The new `Mcp-Method`/`Mcp-Name` routing headers are
  HTTP-transport-only (they exist so gateways can route without parsing the
  JSON body) and have no stdio equivalent — nothing to implement here.
- **Caching metadata is part of the contract, and the SDK supplies it.**
  `tools/list` responses MUST include `ttlMs` and `cacheScope` per SEP-2549,
  and tool ordering is guaranteed stable. The lowlevel `Server` runner
  auto-fills both onto spec-method results a handler leaves unset
  (`mcp.server.caching`; proven in `.ll/learning-tests/mcp.md`), and ordering
  is simply the order of the list the `list_tools` handler returns. Both are
  therefore **assertions to write, not machinery to build**.
  (`resources/list`/`prompts/list`/`resources/read` are out of scope for this
  child — see FEAT-3136, FEAT-3137.)
- **Explicitly opt out of deprecated primitives.** Do NOT advertise or
  depend on Roots, Sampling, or Logging — all three were deprecated in
  2026-07-28 with a 12-month minimum window.
- **No `initialize` handshake.** Servers handle each request on its own
  merits (protocol version + capabilities arrive in `_meta`). The Python SDK
  v2 implements this; `ll-mcp` must pin the SDK version that ships the new
  behavior (2.0.0 specifically — see Confidence Check Notes; the 1.21.0 line
  does not implement it).
- **Statelessness is the design invariant, not just handshake removal.** The
  handshake and the `Mcp-Session-Id` header were retired together so that any
  request can land on any server instance behind a plain round-robin load
  balancer with no shared storage. The operative rule for `ll-mcp`: **no
  request handler may depend on state established by a prior request.** Each
  `tools/call` reads `_meta` for protocol version/client identity/capabilities
  and resolves entirely from the filesystem and SQLite. Stdio makes this
  cheap to satisfy — but it is a hard constraint, not an incidental property,
  and it must survive into any future HTTP tier.
  - This directly settles the `cli_event_context()` tension documented in
    Conventions in Force: a single `cli_events` row held open across the
    process's whole stdin loop *is* exactly the cross-request session state
    the spec is designing away from. The spec-aligned resolution is a
    per-request event row (or none), not a process-lifetime one. Decide it
    on those grounds rather than as a free judgment call.
- **`server/discover` is the replacement discovery path, and the SDK
  implements it by default — DECIDED, no choice to make.** With `initialize`
  gone, a client that wants server capabilities upfront issues
  `server/discover`. The lowlevel `Server` registers it as a built-in spec
  request (`mcp/server/lowlevel/server.py`, `_spec_requests` table) with a
  default `_handle_discover` that **auto-derives capabilities from whatever
  handlers are actually registered, at call time**. Consequences:
  - We get an affirmative, testable capability surface for free. No custom
    handler is needed (`add_request_handler("server/discover", ...)` could
    replace it wholesale, but there is no reason to).
  - "Advertises no Roots, Sampling, or Logging" is satisfied structurally:
    those capabilities are absent because we never register handlers for
    them. This becomes an assertion against the default discover response.
  - FEAT-3136/FEAT-3137 need no registration point of their own — registering
    their `resources/*` and `prompts/*` handlers makes them appear in
    `server/discover` automatically.

## The SDK is async — this is the main structural constraint

Verified directly against the `mcp==2.0.0` wheel. Nothing in this codebase's
existing CLI surface is async, so this is new ground and the single largest
implementation risk in this issue.

- `mcp.server.stdio.stdio_server()` is an `@asynccontextmanager` yielding
  `(read_stream, write_stream)`; `Server.run(read_stream, write_stream,
  init_options)` is `async def`. The documented shape is
  `anyio.run(run_server)` (module docstring, `mcp/server/stdio.py`).
- The stdlib package is `anyio`, a hard dependency of `mcp`. Use
  `anyio.run(...)` rather than `asyncio.run(...)` to match the SDK's own
  documented entry shape.
- **`main_mcp(argv) -> int` stays a synchronous function** so it matches
  every other `ll-*` entry point and remains directly callable from tests.
  It parses args, then calls `anyio.run()` on an inner async coroutine. The
  async surface must not leak into the entry-point signature.
- **The five tool handlers wrap blocking work.** `history_search` hits SQLite
  FTS5; `issues_query`/`issue_get`/`deps_check` walk and parse `.issues/`
  from disk. Handlers registered with the SDK are `async def`, so this
  blocking work will run on the event loop thread unless explicitly offloaded.
  Decision: **run them inline (do not offload)** for this tier — stdio serves
  exactly one client with no concurrent in-flight requests, so there is no
  responsiveness to protect and `anyio.to_thread.run_sync` would only add a
  thread-safety burden on SQLite connections for no benefit. Record this
  choice in the module docstring so a future HTTP tier (which *would* need
  offloading) revisits it deliberately rather than inheriting it.
- **Test harness follows from this**: the dispatch loop is not ours to test.
  Drive the server over in-memory stream pairs (the SDK's
  `mcp.shared.memory` connected-server-and-client-session helper) rather than
  patching `sys.stdin`. See Tests below — the previously-researched
  `StringIO`-stdin precedents do not apply.

## Anti-goals

- **Do not mirror all ~40 `ll-issues` subcommands as tools.** That is a
  context-budget disaster. The whole surface stays coarse.
- **Do not expose orchestration.** `ll-auto`, `ll-parallel`, `ll-loop`, and
  `ll-action invoke` — anything that spawns an agent or runs for minutes —
  stay off the tool surface.
- **Do not reimplement CLI logic.** The server is a facade over the same
  library functions, never a second implementation. Any behavior divergence
  between a tool and its CLI equivalent is a bug in this tier.
- **Do not use MRTR (multi round-trip requests).** 2026-07-28 adds MRTR as
  the stateless replacement for server-initiated requests over open streams —
  mid-call confirmations, parameter elicitation. Five read-only tools over
  read-only library calls need none of it: every tool resolves from its own
  params in a single round trip. Reaching for MRTR here would be a signal
  that a tool has grown a mutating or interactive dimension it should not
  have.

## Integration Map

### Files to Modify
- `scripts/pyproject.toml` — add `ll-mcp` console entry point under
  `[project.scripts]`, and add the MCP SDK as an **optional extra**, not a
  base dependency (see "Dependency placement" below), with a justification
  comment (pattern: the `anthropic` pin, `scripts/pyproject.toml:46-51`)
- `scripts/little_loops/cli/verify_cli_allowlist.py` — `ll-mcp` is
  `ll-`-prefixed and will NOT get the `mcp-call`-style `_NON_LL_TOOLS`
  exclusion, so it must be added to both permission presets this module
  checks
- `skills/configure/areas.md` — add `ll-mcp` to the "Authorize all
  ll- commands (Recommended)" preset line (`areas.md:849`)
- `scripts/little_loops/init/writers.py` — add `"Bash(ll-mcp:*)"` to the
  `_LL_PERMISSIONS` tuple (`writers.py:80-134`)
- `README.md` — bump the `"47 typed CLI tools"` count line (`README.md:182`
  — note: earlier drafts of this issue cited `:180`, which has drifted); do
  NOT add a `### ll-mcp` section — blocked by
  `test_readme_structure.py::TestReadmeIsHeroPage::test_readme_has_no_ll_cli_sections`
- `scripts/tests/test_wiring_cli_registry.py` — add a
  `("docs/reference/CLI.md", "ll-mcp", "FEAT-3135")`-shaped tuple to
  `DOC_STRINGS_PRESENT`, following the pattern used for prior tools
  (`ll-adapt`, `ll-ctx-stats`)
- `scripts/little_loops/mcp_server/` — **new top-level package (DECIDED, see
  "Module placement" below)**. `__init__.py` exports `main_mcp`;
  `pyproject.toml` wires `ll-mcp = "little_loops.mcp_server:main_mcp"`
  directly, following the `mcp-call` precedent
  (`mcp-call = "little_loops.mcp_call:main"`, `pyproject.toml:124`). No
  `cli/__init__.py` touch.

### Dependency placement (DECIDED)

The SDK goes in `[project.optional-dependencies]` as `mcp`, **not** in base
`dependencies`:

```toml
[project.optional-dependencies]
# FEAT-3135: exact pin, not a range. The 1.x line does not implement the
# 2026-07-28 no-`initialize`-handshake behavior `ll-mcp` is built on
# (proven: .ll/learning-tests/mcp.md, installed 1.21.0 rejects it), and
# 2.0.0 is the first and only 2.x release — there is no 2.x track record to
# justify an open upper bound. Optional rather than base because mcp==2.0.0
# pulls 16 mandatory transitive deps including a full HTTP server stack
# (starlette, uvicorn, sse-starlette, httpx2), pyjwt[crypto],
# opentelemetry-api, python-multipart, and jsonschema — none of which a
# stdio-only server uses, and all of which would otherwise land on every
# `pip install little-loops`. Per CLAUDE.md § Code Style (minimize
# third-party dependencies).
mcp = ["mcp==2.0.0"]
```

This settles the bound-strictness disagreement flagged in Codebase Research
Findings (`anthropic` double-bounded vs `psutil` lower-bound-only): neither
precedent applies, because an exact pin is justified here by a proven
incompatibility rather than by risk-hedging.

Requirement that follows: **`import mcp` must be lazy**, inside `main_mcp`,
mirroring how `anthropic` is imported inline at each call site
(`host_runner.py:1883,1960`). Two reasons:
1. `test_cli_doctor_install_checks.py::test_real_pyproject_all_entry_points_resolve`
   imports every `[project.scripts]` target — a module-scope `import mcp`
   makes that test fail on any checkout without the extra installed.
2. A bare `pip install little-loops` user who runs `ll-mcp` should get a
   clear "install `little-loops[mcp]`" message on stderr and a nonzero exit,
   not an `ImportError` traceback.

### Dependent Files (Callers/Importers)
- **`ll-mcp` already has emitters in the tree, written ahead of the binary**
  (commits `b2947a60`, `0dda61ce`): `adapters/claude_code.py:58` writes
  `{"command": "ll-mcp"}` into `.mcp.json`, and `adapters/codex.py:376-382`
  writes `ll-mcp.toml` containing `mcp_servers = ["ll-mcp"]`. Both currently
  point at a command that does not exist; this issue is what makes those
  emitted configs functional. Covered by `test_adapters.py:667-678`.
- FEAT-3136 and FEAT-3137 will register their `resources/*` and `prompts/*`
  handlers on the `Server` instance this module creates.

### Conventions in Force
- **Module placement (DECIDED): new top-level package
  `little_loops/mcp_server/`, direct `[project.scripts]` wiring, no
  `cli/__init__.py` re-export.** Two precedents disagreed — the three-touch
  pattern (implementation module exporting `main_<name>(...) -> int`, a
  re-export in `cli/__init__.py`, a `[project.scripts]` entry; evidence
  `main_ctx_stats` `cli/ctx_stats.py:726`, `main_adapt` `cli/adapt.py:31`)
  versus `mcp-call`'s direct wiring bypassing `cli/` entirely
  (`mcp-call = "little_loops.mcp_call:main"`, `pyproject.toml:124`).
  Resolved toward the latter, for three reasons:
  1. `cli/` is one-module-per-tool. This surface is multi-module by design —
     FEAT-3136 adds resources, FEAT-3137 adds prompts — so it wants a
     package, and a package under `cli/` would be the only one of its kind.
  2. It is not a CLI. It parses no meaningful arguments and produces no
     terminal output; it is a protocol server that happens to have an entry
     point. `mcp_call.py` sits outside `cli/` for the same reason.
  3. The `cli/` pattern carries `cli_event_context()` with it, which is
     actively wrong here (see next bullet). Choosing the non-`cli/` path
     resolves that tension structurally rather than by exception.
  Consequence: needs a row in the flat module table at `API.md:60-98`,
  alongside the existing `little_loops.mcp_call` row (line 97).
- **`cli_event_context()` (DECIDED): not used.** `mcp_call.py` already
  diverges from that convention with no wrapper, and the statelessness
  invariant in Spec assumptions forbids the process-lifetime row the naive
  application would produce. Nothing replaces it at per-request granularity
  either — a read-only tool call is not a CLI invocation, and inventing
  per-request `cli_events` rows would flood the table with a new event shape
  no consumer expects. If `ll-mcp` telemetry is wanted later, it is its own
  issue with its own schema decision.
- New third-party dependencies are pinned with an inline justification
  comment naming the originating issue and the reason an existing
  dependency doesn't suffice — evidence: `anthropic` pin
  (`scripts/pyproject.toml:40-46`), `psutil` pin (`scripts/pyproject.toml:52-58`).
- The `selectors.DefaultSelector`-with-deadline read pattern and the
  terminate → bounded `wait()` → kill → bounded `wait()` teardown
  (`mcp_call.py:_send_jsonrpc()` lines 76-131 / `finally` lines 325-338,
  BUG-2778 and BUG-2779) are **client-side only and do not apply here**.
  They exist to bound reads of a *spawned subprocess's* stdout. `ll-mcp`
  owns neither the read loop (the SDK's `stdio_server()` does) nor any child
  process. Listed only to head off a mistaken attempt to mirror them.
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
- New test file for the server module. **Drive the server over the SDK's
  in-memory stream pair** (`mcp.shared.memory`'s connected-server-and-client
  session helper), which pairs a real client session against our `Server`
  instance with no subprocess and no stdio. Tests become ordinary
  `anyio`/`pytest.mark.anyio` async tests calling `list_tools()` /
  `call_tool(name, params)` and asserting on the returned models.
- `scripts/tests/test_mcp_call.py`'s `_MockFileObj` / `_make_ready_selector`
  / `_patch_selector` / `_make_proc_mock` scaffolding (lines 139-280)
  **is not a model for this issue.** It mocks `Popen` + `selectors` to test
  the *client* talking to an external server. We are the server, we spawn
  nothing, and we do not touch `selectors`. Its `tmp_path`-backed fixture
  style is still worth copying; its transport mocking is not.
- Do **not** patch `sys.stdin` with a `StringIO`. Earlier research on this
  issue surveyed `test_fsm_runners.py:183-218`, `main_hooks()`, and
  `hooks/__init__.py` stdin tests as candidate models for a hand-rolled
  `while True: readline → dispatch` loop. That loop no longer exists in the
  design — the SDK owns it — so those precedents are inapplicable and the
  "no in-repo precedent, harness must be built from scratch" risk they
  implied is resolved, not outstanding.
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
  "FEAT-1045")` asserts the literal count string in `README.md:182`; this
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
- `README.md` — bump the `"N CLI tools"` count line (`README.md:182`) only;
  `test_readme_structure.py` blocks a new `### ll-mcp` section
- `CONTRIBUTING.md` § "Documentation wiring for new CLI tools" — check this
  issue's Integration Map against it directly
- `docs/reference/API.md` — the flat module table (`API.md:60-98`) already
  lists `little_loops.mcp_call` (line 97) as a one-line row alongside every
  other top-level module. `little_loops.mcp_server` is package top-level
  (placement decided), so it **does** need an analogous row in this table.

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
- **JSON-RPC framing is newline-delimited — and is the SDK's problem, not
  ours.** Confirmed on both sides: `mcp_call.py` (client) writes
  `json.dumps(request) + "\n"` and reads `readline()` + `json.loads()` per
  line (`mcp_call.py:91-128`), and the SDK's stdio server transport frames
  via a `readline`-style loop and `model_dump_json` rather than LSP-style
  `Content-Length:` headers (proven, `.ll/learning-tests/mcp.md`). Recorded
  for background only — no framing code is written in this issue.
- **No existing MCP server-side scaffolding anywhere in this codebase**
  (confirmed via broad search for `jsonrpc`/`tools/list`/`tools/call`/
  `mcpServers`/`stdio` markers): every MCP-related file found —
  `mcp_call.py`, `runner_spec.py:_run_mcp` (line 281, calls
  `call_mcp_tool`), `cli/harness.py:cmd_mcp` — is client-side, spawning and
  talking to *external* MCP servers declared in a project's `.mcp.json`.
  `ll-mcp` is the first server-side implementation in this codebase; there
  is no in-repo server loop to model the stdin-reading dispatch loop after.
- **`cli_event_context()` tension — RESOLVED, see Conventions in Force.**
  Background: `session_store/writers.py:472-528+` opens a `cli_events` row
  on `__enter__` and records `exit_code`/`duration_ms` on `__exit__`,
  measured across the whole `with` block — which for a persistent server
  would span the entire process lifetime. `mcp_call.py` already diverges
  from the convention (no wrapper; `sys.exit()` contract at
  `mcp_call.py:394` with a documented exit-code table at `mcp_call.py:10-15`:
  `0` success, `1` tool_error, `124` timeout, `127` not_found, `2`
  usage/config error). `ll-mcp` follows `mcp_call.py`: no
  `cli_event_context`, and a simple documented exit-code contract of its own
  (`0` clean EOF/shutdown, `2` missing `[mcp]` extra or usage error).
- **`verify_cli_allowlist.py`'s `_all_ll_entry_points()`**
  (`cli/verify_cli_allowlist.py:46-54`) reads **installed distribution
  metadata** via `importlib_metadata.distribution("little-loops")`, not
  live `scripts/pyproject.toml` — a local editable install must be
  re-synced (re-run `pip install -e`, or let PEP 660 regenerate
  `entry_points.txt`) before `ll-mcp` becomes visible to this check or to
  `test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero`.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **OBSOLETE (superseded by the SDK decision), retained so the same research is not redone:** four findings from this pass assumed a hand-rolled protocol layer and no longer bear on implementation.
  - *Stdin server-loop test precedent* — surveyed `mcp_call.py:_send_jsonrpc()` (107-132), `hooks/__init__.py:main_hooks()` (189) + `test_hook_intents.py`, and `fsm/runners.py:_prompt_result()` (488-502) + `test_fsm_runners.py:_run_with_stdin()` (183-216); all single-shot `StringIO` patches, none a multi-turn loop. Moot: we do not write a stdin loop. Use in-memory SDK streams (see Tests).
  - *Two disagreeing N-verb dispatch conventions* — `hooks/__init__.py:_dispatch_table()` (134-165) dict registry vs argparse `if/elif` chains (`cli/issues/__init__.py:974+`, `cli/code.py:130-134`). Moot: `tools/call` routing is SDK handler registration, not ours to design.
  - *No `ttlMs`/`cacheScope` precedent in this codebase* — true, and irrelevant: the SDK auto-fills both.
  - *Three conventions for stable ordering of an advertised list* — `tool_catalog.py` `sorted(glob)` (95-142) vs `host_runner.py` ordered source literals (452-487 et al.) vs `hooks/__init__.py:_dispatch_table()` (134). Moot: ordering is the order of the list our `list_tools` handler returns; a source-order literal (the `host_runner.py` shape) is the natural fit.
- **dataclass→JSON convention (DECIDED)**: three coexist — generic `dataclasses.asdict()` for plain dataclasses (`cli/history.py:392,410,457`, `cli/session.py:433,453,476,697,729`, `cli/code.py:160`, `cli/help.py:230`); hand-rolled dict construction for `CapabilityReport`/`CapabilityEntry`, which no call site passes to `asdict()` despite them being frozen dataclasses (`cli/action.py:335-366`, `cli/doctor.py:956`); and dataclass-owned `to_dict()`/`from_dict()` for wire types that omit `None` fields rather than emitting nulls (`hooks/types.py:47-81`, `events.py:45,54`). **Follow existing per-type precedent rather than unifying**: `asdict()` for `SearchResult` in `history_search`, hand-rolled dict for `CapabilityReport` in `capabilities`, and `cli/deps.py:450-467`'s tuple-to-`list(pair)` shape for `deps_check`. This keeps each tool's payload byte-identical to its CLI equivalent, which the "no behavior divergence" anti-goal requires; inventing a fourth unified convention would itself create divergence.
- **Signal handling (mostly not ours)**: existing long-running `ll-*` processes install `SIGINT`/`SIGTERM` handlers — `cli/queue.py::_run_watch()` (624) with previous-handler restore in a `finally` (673-675) and two-stage `threading.Event` shutdown (`_make_signal_handler()`, 597); `cli/sprint/run.py::_sprint_signal_handler()` (134); `issue_manager.py` (~1671); `parallel/orchestrator.py` (252, 257). None applies directly: `ll-mcp` has no in-flight child to kill and no queue to drain, and EOF-on-stdin (the normal MCP shutdown signal) is handled inside the SDK's transport, which exits the `async with` block cleanly. Default `SIGINT`/`SIGTERM` behavior is correct here — install no handlers, and let `anyio.run()` unwind. Recorded to prevent copying the queue/sprint pattern in reflexively.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **Exact insertion points for the two `verify_cli_allowlist.py` presets** (gap-fill on the already-cited files): `skills/configure/areas.md`'s comma-separated tool list (`areas.md:849`, inside the `"Authorize all"` description line, parsed by `_areas_md_preset_tools()` via `_TOOL_TOKEN_RE`, `verify_cli_allowlist.py:30,62`) — `ll-mcp` inserts alphabetically between `ll-loop` and `ll-messages`. `writers.py`'s `_LL_PERMISSIONS` tuple (parsed by `_writers_preset_tools()` via regex on `Bash(ll-<name>:*)` lines, `verify_cli_allowlist.py:74`) — `ll-mcp` inserts alphabetically between `ll-migrate-status` and `ll-parallel`. The exclusion mechanism that lets `mcp-call` skip both presets is `_NON_LL_TOOLS = frozenset({"mcp-call"})` (`verify_cli_allowlist.py:28`); it matches on the literal name `mcp-call`, not a `mcp-*` prefix, so `ll-mcp` (named `ll-`, not `mcp-`) does not qualify for it regardless.
- **OBSOLETE (the three-touch `cli/` pattern was not chosen — see Conventions in Force). Retained only so the research is not repeated.** Exact insertion points had it been chosen: import line `from little_loops.cli.mcp import main_mcp` inserted after `main_migrate_status` (line 79) and before `main_parallel` (line 80) in the import block (lines 46-101, alphabetized by module path); `__all__` entry `"main_mcp"` inserted in the equivalent slot — note the `__all__` list is alphabetized only through roughly line 124, after which it drifts to loosely-grouped historical-addition order, so this second insertion point is looser than the import block's. The module docstring (lines 4-43, one `- ll-<name>: <summary>` bullet per tool) is stylistic convention only — not test-enforced against `_all_ll_entry_points()`.
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
classification logic. The implementation-route decisions this issue once
left open (module placement, `cli_event_context()`, `server/discover` shape,
dataclass→JSON convention, SDK pin strictness) are not decision-rule logic
in this section's sense and have all been resolved inline above — see
Integration Map → Conventions in Force and Codebase Research Findings.
FEAT-3136 and FEAT-3137 build on `little_loops/mcp_server/`.

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
- **SDK pin bound-strictness — RESOLVED as an exact pin** (`mcp==2.0.0`, in an optional extra; see Integration Map → Dependency placement). The two existing justification-commented pins disagreed — `anthropic>=0.104,<1.0` (`pyproject.toml:46-51`) double-bounded, `psutil>=5.9` (`:52-58`) lower-bound only — but neither model fits: both are hedges against *unknown* future breakage, whereas here the incompatibility with the 1.x line is *proven* and 2.0.0 is the only 2.x release in existence. Useful precedent that does carry over: neither existing pin wraps or re-exports the third-party SDK's types/exceptions in a dedicated module. `anthropic` is imported lazily inline at each call site (`host_runner.py:1883,1960`) with its exceptions caught by SDK class name (`except anthropic.APIError as exc:`, `host_runner.py:1965`) and converted into a local result dataclass rather than re-raised. `ll-mcp` should likewise use SDK types directly at the boundary rather than building a wrapper layer over them.
- **No real-subprocess server test precedent — and none is needed.** Confirmed by search for `Popen([sys.executable, "-m" ...])` / multi-turn `communicate(input=...)` in `scripts/tests/` (only unrelated git-subprocess tests matched); `test_mcp_call.py` mocks `Popen`/`selectors` entirely. The SDK's in-memory client/server session pairing removes the need for either a real subprocess or transport mocking — the server is exercised as a Python object over memory streams. A single smoke test that the `ll-mcp` console script imports and exposes `main_mcp` (already covered generically by `test_cli_doctor_install_checks.py::test_real_pyproject_all_entry_points_resolve`) is sufficient for the binary itself.

## Implementation Steps

Design decisions previously deferred here (module placement,
`cli_event_context()`, `server/discover` shape, dataclass→JSON convention,
pin strictness) are all resolved above. What remains is execution.

1. Add `mcp==2.0.0` under `[project.optional-dependencies].mcp` in
   `scripts/pyproject.toml` with the justification comment, and register
   `ll-mcp = "little_loops.mcp_server:main_mcp"` under `[project.scripts]`.
   Re-run `pip install -e "./scripts[dev,mcp]"` so the editable install's
   `entry_points.txt` regenerates — `verify_cli_allowlist.py`'s
   `_all_ll_entry_points()` reads installed distribution metadata, not
   `pyproject.toml`, so `ll-mcp` is invisible to its gate until this happens.
2. Create `little_loops/mcp_server/` exporting a synchronous
   `main_mcp(argv=None) -> int` that lazily imports `mcp`, emits a clear
   "install `little-loops[mcp]`" message and returns `2` if absent, and
   otherwise `anyio.run()`s an inner coroutine that opens `stdio_server()`
   and awaits `Server.run(...)`.
3. Register the five read-only tools (`issues_query`, `issue_get`,
   `history_search`, `deps_check`, `capabilities`) via the SDK's
   `list_tools`/`call_tool` handlers. `list_tools` returns a source-order
   literal (stable ordering follows from this). Each tool resolves to the
   library call named in Program Design → Call Path, with no subprocess
   invocation of any CLI, and marshals its result per the per-type JSON
   convention decided in Codebase Research Findings.
4. Run blocking library calls inline in the async handlers, and record that
   choice (and its stdio-only justification) in the module docstring.
5. No request handler reads or writes state established by a prior request —
   every tool resolves from its own params plus the filesystem/SQLite. No
   `cli_event_context`, no module-level caches keyed across requests.
6. `ll-mcp` is added to both permission presets
   `scripts/little_loops/cli/verify_cli_allowlist.py` checks, since it does
   not qualify for the `mcp-call`-style `_NON_LL_TOOLS` exclusion (that
   frozenset matches the literal name `mcp-call`, not an `mcp-*` prefix).
7. Register no Roots, Sampling, or Logging handlers, and issue/handle no MRTR
   request shape. Both are then structurally true and assertable against the
   SDK's default `server/discover` response.
8. `python -m pytest scripts/tests/` passes, including new coverage for the
   five tools driven over in-memory SDK streams.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_wiring_guides_and_meta.py:93` — bump the
  `DOC_STRINGS_PRESENT` tuple's `"47 typed CLI tools"` literal to match the
  new count in the same change as the `README.md:182` bump
- Add a unit test isolating `cli/issues/search.py::_load_issues_with_status`
  (currently only covered transitively) alongside the `issues_query` tool
  implementation
- Confirm both `test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero`
  and `::TestMainVerifyCliAllowlist::test_clean_state_returns_zero` pass —
  not just one of the two end-to-end variants

## Acceptance criteria

- `ll-mcp` is registered as a console entry point in the `scripts` package
  and runs as a stdio MCP server against the 2026-07-28 spec.
- The MCP SDK is an optional extra (`little-loops[mcp]`), not a base
  dependency, and `import mcp` happens lazily inside `main_mcp` — a
  checkout without the extra installed still passes
  `test_cli_doctor_install_checks.py::test_real_pyproject_all_entry_points_resolve`,
  and running `ll-mcp` without it exits `2` with an actionable message
  rather than an `ImportError` traceback.
- `main_mcp` is a synchronous `(argv=None) -> int` callable; the async
  surface does not leak into the entry point.
- `.mcp.json` emitted by `ll-adapt --host claude-code --apply` names a
  command that now actually starts (closes the loop on `adapters/`
  emitters written ahead of this binary).
- The tool surface is exactly the five read-only tools listed above; no
  mutating tool is advertised.
- Every tool calls into `little_loops` library functions directly — no
  subprocess invocation of the CLIs.
- `tools/list` responses include `ttlMs` and `cacheScope`, and tool
  ordering is stable across calls.
- No handler depends on state from a prior request: a test that issues the
  same `tools/call` twice, and one that issues calls in a shuffled order,
  both produce identical responses. No `Mcp-Session-Id`-equivalent, no
  handshake-established state, no process-lifetime `cli_events` row.
- The SDK's default `server/discover` response names the tools capability
  only — no custom discover handler is registered.
- The server advertises no Roots, Sampling, or Logging capability, asserted
  against that `server/discover` response.
- No MRTR request shape is issued or handled.
- `ll-mcp` is present in both permission presets `verify_cli_allowlist.py`
  checks.
- `python -m pytest scripts/tests/` passes.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-09_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors

_Revised 2026-08-09 after verifying the `mcp==2.0.0` wheel directly. The two
risk factors below replace three earlier ones that assumed a hand-rolled
protocol layer._

- **`ll-mcp` is the first async code in this codebase.** The SDK is
  anyio-based (`stdio_server()` is an `@asynccontextmanager`, `Server.run()`
  is `async def`), so this introduces an event loop, `pytest.mark.anyio`
  async tests, and async handler signatures into a codebase that has none of
  these today. No in-repo precedent exists for any of it, and the blocking
  SQLite/filesystem calls inside async handlers are a live (if
  low-consequence at stdio scale) design hazard.
- **`mcp==2.0.0` is a brand-new major with no track record**, exactly pinned,
  carrying 16 mandatory transitive dependencies including pydantic>=2.12 and
  a full HTTP stack. Risk is contained by making it an optional extra with a
  lazy import — a base-dependency placement would put a resolver conflict on
  the critical path of every `pip install little-loops`.
- **RESOLVED, no longer risks**: the "no stdin server-loop test precedent"
  concern (we write no such loop; the SDK's in-memory stream pairing is the
  harness), and the four open implementation-route decisions (module
  placement, `cli_event_context()`, pin strictness, dataclass→JSON
  convention — all decided in the body above).
- Confirmed via learning-test proof (`.ll/learning-tests/mcp.md`) and direct
  wheel inspection: the installed system SDK is 1.21.0, which does *not*
  implement the no-`initialize`-handshake behavior this issue assumes — only
  2.0.0 does. `server/discover` is a built-in SDK spec request with a default
  auto-deriving handler, and the lowlevel runner auto-fills
  `ttlMs`/`cacheScope`.

## Session Log
- `/ll:confidence-check` - 2026-08-09T16:15:33 - `3f9246b7-015e-4acf-9b7b-68090c38b52c.jsonl`
- `/ll:reconcile-issue` - 2026-08-09T16:04:28 - `8e9641aa-06e4-4fab-8c0d-99d66c829c87.jsonl`
- `/ll:confidence-check` - 2026-08-09T15:12:44 - `ebf47ba1-366c-4c95-8300-0a2317f943ab.jsonl`
- `/ll:confidence-check` - 2026-08-09T08:17:58 - `042e13ad-a334-4923-8e46-6474a3ddf3dd.jsonl`
- `/ll:reconcile-issue` - 2026-08-09T08:12:41 - `a43d576b-311c-4dc4-9503-e85cef5e3d8c.jsonl`
- `/ll:verify-issues` - 2026-08-09T08:09:14 - `f730fd5c-232d-4c9a-9c1a-183dc938f25c.jsonl`
- `/ll:refine-issue` - 2026-08-09T08:04:25 - `24e59e6a-4438-4d10-8783-fdb2abc8380a.jsonl`
- `/ll:wire-issue` - 2026-08-09T07:54:44 - `03413e2d-017e-4cb9-8625-9740c56c1512.jsonl`
- `/ll:refine-issue` - 2026-08-09T07:46:49 - `fc612f00-613e-4252-b9ba-f6cc15f65c73.jsonl`
- `/ll:issue-size-review` - 2026-08-09T07:40:08 - `153550d2-faf1-4350-b263-1aaa047c80e3.jsonl`
