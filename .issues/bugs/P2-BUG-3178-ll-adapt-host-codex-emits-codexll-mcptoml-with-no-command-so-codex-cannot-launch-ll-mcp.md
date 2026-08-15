---
id: BUG-3178
type: BUG
title: ll-adapt --host codex emits .codex/ll-mcp.toml with no command, so Codex cannot
  launch ll-mcp
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T03:25:37Z'
parent: EPIC-3127
labels:
- mcp
- multi-host
relates_to:
- BUG-3177
testable: true
learning_tests_required:
- codex
confidence_score: 80
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 25
---

# BUG-3178: ll-adapt --host codex emits .codex/ll-mcp.toml with no command, so Codex cannot launch ll-mcp

## Summary

`ll-adapt --host codex --apply` writes `.codex/ll-mcp.toml` containing a bare
server-name list and no server definition, so Codex has nothing to launch. The
emitted content is the whole file:

```toml
# <ll-generated marker>
mcp_servers = ["ll-mcp"]
```

(`scripts/little_loops/adapters/codex.py:381`.) Codex registers an MCP server
with a table keyed by name carrying the executable, e.g.
`[mcp_servers.ll-mcp]` / `command = "ll-mcp"`. A top-level `mcp_servers` array
of strings is the *tool-allowlist reference* form used in the per-skill TOMLs
this same emitter writes (see `test_adapters.py:639-649`) — it names a server,
it does not define one. Pointed at a name that is defined nowhere, the
registration is inert.

Compare the Claude Code emitter, which writes a real definition:
`servers["ll-mcp"] = {"command": "ll-mcp"}` merged into `.mcp.json`
(`scripts/little_loops/adapters/claude_code.py:57-58`).

The existing test asserts only that the string `mcp_servers = ["ll-mcp"]`
appears in the file (`scripts/tests/test_adapters.py:679`), so it locks in the
broken shape rather than catching it. Three docs state the file "registers the
`ll-mcp` server": `docs/codex/README.md:32`, `docs/codex/usage.md:50`,
`docs/reference/CLI.md:4185`.

Combined with BUG-3177 (the empty prompt index on a non-editable
install), the practical effect is that the host-agnostic serving claim in
EPIC-3127 has no working end-to-end path outside a Claude Code plugin checkout.


## Steps to Reproduce

1. `ll-adapt --host codex --apply` from a little-loops project.
2. Read the emitted file: `.codex/ll-mcp.toml`.
3. Observe the entire contents are a marker comment plus
   `mcp_servers = ["ll-mcp"]` — a name, and no executable, arguments,
   environment, or working directory anywhere.
4. Start Codex and attempt to use any `ll-mcp` tool.

## Current Behavior

The generated file names a server that is defined nowhere. Nothing tells Codex
what process to spawn, so no `ll-mcp` tools, resources, or prompts become
available. `ll-adapt` reports `APPLY  mcp-config: ll-mcp` and exits 0.

## Expected Behavior

`ll-adapt --host codex --apply` emits a config fragment that actually launches
the server — a `[mcp_servers.ll-mcp]` table carrying at minimum
`command = "ll-mcp"` — placed where Codex will read it, so that `ll-mcp`'s tools
are usable from Codex without hand-editing TOML.

## Root Cause

- **File**: `scripts/little_loops/adapters/codex.py`
- **Anchor**: `in method CodexEmitter.emit_mcp_config()`
- **Cause**: The emitter reuses the *tool-allowlist reference* form for what
  needs to be a *server definition*. The same class writes `mcp_servers = [...]`
  into per-agent TOMLs to declare which already-configured servers an agent may
  reach (`emit_agent`, covered by `test_adapters.py:639-649`, where the value is
  a server name like `"github"`). `emit_mcp_config` copies that array shape, but
  a reference to a name is not a definition of it, so the registration is inert.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

- **File**: `scripts/little_loops/adapters/codex.py`
- **Anchor**: `CodexEmitter.emit_mcp_config` (lines 375-404)
- **Cause**: `new_content` is built as the literal `f'{_MARKER}\nmcp_servers = ["ll-mcp"]\n'` (line 381) — the exact array-of-server-names syntax `_derive_mcp_servers` (codex.py:166-182) produces for per-agent TOMLs, where it correctly means "this agent may use these already-defined servers." Reused here as the *entire* content of the standalone `.codex/ll-mcp.toml`, it names a server (`"ll-mcp"`) that no `[mcp_servers.ll-mcp]` table anywhere defines. Contrast `ClaudeCodeEmitter.emit_mcp_config` (`scripts/little_loops/adapters/claude_code.py:42-75`), which builds `new_entry = {"command": "ll-mcp"}` (line 58) and merges it into `.mcp.json`'s `mcpServers` map — a real, launchable definition. `meta` passed into both emitters only ever carries `output_dir`, `apply`, `quiet` (`scripts/little_loops/adapters/core.py:641-645`) — no host-specific fields exist to carry a command value even if `codex.py` wanted to use one.

## Location

- **File**: `scripts/little_loops/adapters/codex.py`
- **Line(s)**: 375-404, definition at 381 (at scan commit: `fe176022`)
- **Anchor**: `in method CodexEmitter.emit_mcp_config()`
- **Code**:
```python
new_content = f'{_MARKER}\nmcp_servers = ["ll-mcp"]\n'
out_toml = output_dir / "ll-mcp.toml"
```

Contrast the Claude Code emitter, which writes a real definition
(`scripts/little_loops/adapters/claude_code.py:57-58`):
```python
servers: dict = data.setdefault("mcpServers", {})
new_entry = {"command": "ll-mcp"}
```

## Environment

Any project where `ll-adapt --host codex --apply` has been run. Not
environment-dependent.

## Frequency

Deterministic — the emitted content is a fixed literal.

## Motivation

Codex is the flagship non-Claude-Code host in EPIC-3127's host-agnostic thesis,
and this is the one artefact that would make `ll-mcp` reachable from it. As
shipped, the entire `ll-mcp` surface — ten tools, the `ll://` resources, the
skill prompts, `tasks/get`/`tasks/cancel` — is unreachable from Codex, while
three docs state the file "registers the `ll-mcp` server"
(`docs/codex/README.md:32`, `docs/codex/usage.md:50`,
`docs/reference/CLI.md:4185`).

Together with BUG-3177 (empty prompt index on a non-editable install), the
host-agnostic serving claim has no verified end-to-end path off Claude Code.
Fixing one without the other still leaves Codex with a launchable server that
serves no prompts.

## Proposed Solution

1. **Confirm the target format and read path first.** Two questions, both
   currently unverified in this repo, and the second is the larger risk:
   - What table shape does the pinned Codex version expect
     (`[mcp_servers.ll-mcp]` with `command`/`args`/`env`)?
   - **Does Codex read `.codex/ll-mcp.toml` at all?** Codex's documented config
     is `~/.codex/config.toml`; whether a standalone per-file fragment under a
     project `.codex/` directory is loaded is not established anywhere in this
     repo. If it is not, emitting a correct table into that path is still a
     no-op and the fix is a merge into the real config file (the pattern
     `claude_code.py` already uses for `.mcp.json`), not a content change.

   Record the answer as a learning test under `.ll/learning-tests/`, matching
   how EPIC-3127's other SDK-behavior claims were pinned down.
2. Rewrite `emit_mcp_config` to emit the definition shape, keeping the existing
   marker/idempotency/user-authored-file guards intact.
3. If the read path turns out to be `~/.codex/config.toml`, follow
   `ClaudeCodeEmitter.emit_mcp_config`'s merge-don't-overwrite approach and
   `init/writers.py:merge_settings()`.
4. Fix `test_toml_references_ll_mcp` (`scripts/tests/test_adapters.py:679`),
   which asserts the broken literal and would fail correctly-shaped output.
5. Correct the three docs to describe what the artefact does.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

> **Partially resolved 2026-08-15 — see "Direct evidence from a real Codex install" below.**
> The table shape is now established as fact. The read-path question remains open but the
> evidence points strongly one way.

The correct target TOML shape for a real Codex MCP server definition, and whether
Codex reads a standalone `.codex/ll-mcp.toml` file at all (vs. only a single
`~/.codex/config.toml`), are **not established anywhere in this repository** — no
code, test, or doc states or verifies it. `_derive_mcp_servers` /
`_format_agent_toml` (`codex.py:166-225`) only ever produce the array-of-names
allowlist form for per-agent TOMLs; nothing in `codex.py` or elsewhere constructs
a table-with-command definition. The Claude Code emitter's `{"command": "ll-mcp"}`
shape (`claude_code.py:57-58`) is evidence of *this codebase's* convention for
representing a launchable server, not evidence of what Codex itself expects to
parse — Codex's config format is not otherwise referenced in this repo.

Confirming Codex's actual expected shape and read path (e.g. via a learning test
under `.ll/learning-tests/`, per `learning_tests.enabled` in `.ll/ll-config.json`)
is a prerequisite for correcting `emit_mcp_config`'s output — not an assumption
to bake into the fix from the Claude Code pattern alone.

### Direct evidence from a real Codex install (2026-08-15)

Inspected `~/.codex/config.toml` on a developer machine — a Codex-written, not
little-loops-written, config. Paths below are generalized; the structure is verbatim:

```toml
[mcp_servers]

[mcp_servers.RepoPrompt]
command = "<abs-path-to-some-cli-binary>"
args = []
tool_timeout_sec = 10000
enabled = false
```

**Question 1 (table shape) — ANSWERED.** A Codex MCP server definition is
`[mcp_servers.<name>]` carrying `command`, with optional `args`, `tool_timeout_sec`, and
`enabled`. This is now grounded in Codex's own config rather than inferred from
`claude_code.py`'s `{"command": "ll-mcp"}`, which the research note above correctly warned
was evidence of *this codebase's* convention only. The minimum viable emission is:

```toml
[mcp_servers.ll-mcp]
command = "ll-mcp"
args = []
```

**Question 2 (read path) — still open, but the evidence leans hard toward "no."** The same
file also carries per-project configuration *inside the global config*, as sections keyed
by absolute project path:

```toml
[projects."<abs-path-to-a-project-checkout>"]
trust_level = "trusted"
```

That Codex expresses project-scoped settings as `[projects."<abs-path>"]` sections in
`~/.codex/config.toml`, rather than reading a project-local file, is meaningful evidence
against a `.codex/*.toml` fragment read path. **Not conclusive** — this repo's `.codex/`
directory does contain an `agents/` subdirectory that Codex does read, so per-project
`.codex/` is a real read path for *some* artefact types. The learning test must still
settle whether MCP config specifically is among them.

**Planning implication:** treat the "balloon" branch as the likely outcome — merging a
`[mcp_servers.ll-mcp]` table into `~/.codex/config.toml`, with the
`meta["output_dir"]` contract deviation the wiring pass already flagged at
`cli/adapt.py:126-139`. Estimate and sequence the work on that basis rather than on the
content-shape-only branch.

### Blocker: the local Codex install is broken (2026-08-15)

`codex --version` fails with `Error: spawn <npm-global>/lib/node_modules/@openai/codex/
node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/codex ENOENT` — the
platform-specific vendor binary is missing from the npm install.

This blocks both Implementation Step 1's learning test and Step 5's end-to-end
verification — which this issue itself calls "the real acceptance criterion."
**Reinstall Codex before starting implementation**, or the work cannot be verified beyond
unit-test shape assertions.

## Integration Map

### Files to Modify
- `scripts/little_loops/adapters/codex.py` — `emit_mcp_config` (375-404)
- `scripts/tests/test_adapters.py` — `TestCodexEmitterEmitMcpConfig` (656-710)
- `docs/codex/README.md`, `docs/codex/usage.md`, `docs/reference/CLI.md:4185`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/adapt.py` — the `--host codex` dispatch
- `scripts/little_loops/adapters/core.py` — the `HostEmitter` protocol, if the
  method signature or return contract changes

### Similar Patterns
- `scripts/little_loops/adapters/claude_code.py:42-75` — the correct shape:
  real definition, merged into existing content, idempotent
- `scripts/little_loops/init/writers.py:merge_settings()` — merge precedent

### Tests
- `scripts/tests/test_adapters.py::TestCodexEmitterEmitMcpConfig` — assert a
  parseable `[mcp_servers.ll-mcp]` table with `command`, via `tomllib.loads`,
  not a substring match on a literal
- Keep the existing marker, dry-run, idempotency, and user-authored-file cases

### Behavior Parity

_Added 2026-08-15 to close the `missing_behavior_parity` gap that capped the confidence
check's Criterion 4 at 10/20._

`test_toml_references_ll_mcp` (`scripts/tests/test_adapters.py:675-679`) is being replaced,
not extended. Parity contract for the replacement:

| Behavior | Before (asserted today) | After (must assert) |
|---|---|---|
| Emitted content | substring `'mcp_servers = ["ll-mcp"]'` present | `tomllib.loads(text)["mcp_servers"]["ll-mcp"]["command"] == "ll-mcp"` |
| Assertion style | substring match on a literal | structural parse, mirroring `TestClaudeCodeEmitterEmitMcpConfig`'s `json.loads` + dict pattern (`test_adapters.py:1681-1733`) |
| Marker gating | `_MARKER` prefix written and honored | unchanged — must still hold |
| Idempotency | second run returns `"skipped"` | unchanged — must still hold |
| User-authored file | no marker → `"skipped"`, file untouched | unchanged — must still hold |
| Dry run | no write, returns `"adapted"` | unchanged — must still hold |
| Return contract | `"adapted"` / `"skipped"` only | unchanged — `core.py:654-659` maps anything else to an error |

The replacement test **must fail against the current implementation**. A test that passes
against both the name-only array and the correct table has not closed the defect. Add
`import tomllib` following `scripts/tests/test_kimi_adapter.py:24,50-56` (`tomllib.loads(text)`
on a string), not the file-handle pattern in `test_cli_doctor_install_checks.py`.

If step 1 resolves to merging into `~/.codex/config.toml`, add merge/overwrite/malformed-input
cases paralleling `test_merges_into_existing_sibling_entry` /
`test_overwrites_stale_ll_mcp_entry` / `test_tolerates_malformed_existing_json`
(`test_adapters.py:1711-1735`) — critically, a merge must preserve unrelated pre-existing
`[mcp_servers.*]` tables and `[projects."..."]` sections in the user's real config.

### Documentation
- The three sites above; `docs/guides/MCP_SERVER_GUIDE.md` if it documents
  Codex registration
- `docs/reference/HOST_COMPATIBILITY.md:214` already flags Codex
  `mcp_servers`/`skills.config` scoping as unresearched — update it with
  whatever step 1 establishes

### Configuration
- Output path may change from `.codex/ll-mcp.toml` to `~/.codex/config.toml`
  depending on step 1.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/adapters/codex.py` — `CodexEmitter.emit_mcp_config` (lines 375-404) must emit a real server definition Codex can launch, not a name-only allowlist array
- `scripts/tests/test_adapters.py` — `TestCodexEmitterEmitMcpConfig::test_toml_references_ll_mcp` (lines 675-679) asserts the literal buggy substring `'mcp_servers = ["ll-mcp"]'` and locks in the defect; it must be replaced with a structural assertion (parse the TOML, check the table), not a stronger substring match
- `docs/codex/README.md:32`, `docs/codex/usage.md:50`, `docs/reference/CLI.md:4185` — all three state the file "registers the `ll-mcp` server"; accurate only once the emitted content is a real definition, and only if Codex actually reads this standalone file (see Proposed Solution — this is still an open question, not confirmed by any code/doc in this repo)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/adapters/core.py:622-659` (`process_mcp_config`) — sole production caller of `emit_mcp_config`; wraps the call in `try/except AdapterError` and maps `"adapted"`/`"skipped"`/other to `(1,0,0)`/`(0,1,0)`/`(0,0,1)` (lines 654-659)
- `scripts/little_loops/cli/adapt_skills_for_codex.py`, `scripts/little_loops/cli/adapt_agents_for_codex.py` — import `codex.py` but do not call `emit_mcp_config` directly

### Conventions in Force
- Two live `emit_mcp_config` shapes disagree today: Codex's name-only array (`codex.py:381`) vs. Claude Code's full command-definition object merged non-destructively into existing content (`claude_code.py:57-58`) — there is no shared "MCP server definition" format across hosts; Gemini/Kimi/Omp/Qwen's `emit_mcp_config` are all unconditional `return "skipped"` stubs (`gemini.py:140-142`, `kimi.py:144-146`, `omp.py:131-133`, similarly qwen.py)
- Idempotent marker-gated writes: `_MARKER`/`_LL_GENERATED_MARKERS` (`codex.py:22-30`), checked via `existing.startswith(m)`, is reused identically by `emit_agent` (`codex.py:353-362`) and `emit_mcp_config` (`codex.py:384-393`) — this is one of three different "already up to date" conventions coexisting across `adapters/` (marker-gated in `codex.py`; plain byte-equality in `gemini.py` and the other stub hosts; dict-equality-on-parsed-entry in `claude_code.py:60`). Unifying these is out of scope for this bug — the fix should keep whichever convention `codex.py` already uses.
- No TOML-writing library is used anywhere in `adapters/`; `codex.py` hand-builds TOML via f-strings with manual quote-escaping (`codex.py:185-225`, `:375-404`). `tomllib` (stdlib) is used elsewhere for *reading* only (`scripts/little_loops/host_runner.py:606-608`), outside `adapters/`.
- The `ll-mcp` launchable command comes from the console-script entry point `ll-mcp = "little_loops.mcp_server:main_mcp"` (`scripts/pyproject.toml:119`) — the only place in the repo tying the string `"ll-mcp"` to an executable. `claude_code.py` references this value via `{"command": "ll-mcp"}`; `codex.py` does not reference it anywhere.

### Tests
- `scripts/tests/test_adapters.py::TestCodexEmitterEmitMcpConfig` (lines 656-710) — covers write/dry-run/skip/idempotency mechanics correctly; only `test_toml_references_ll_mcp` (675-679) asserts content shape, and does so via substring match
- `scripts/tests/test_adapters.py::TestClaudeCodeEmitterEmitMcpConfig` (lines 1681-1733) — reference pattern for structural assertions (`json.loads` + dict equality) including merge/overwrite/malformed-input coverage (`test_merges_into_existing_sibling_entry`, `test_overwrites_stale_ll_mcp_entry`, `test_tolerates_malformed_existing_json`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_adapters.py` does not currently import `tomllib`; rewriting `test_toml_references_ll_mcp` to a structural assertion needs that import added. Follow `scripts/tests/test_kimi_adapter.py:24,50-56` (`tomllib.loads(text)` on a string, the closer fit for this file's in-memory content) rather than `scripts/tests/test_cli_doctor_install_checks.py:53-56` (`tomllib.load(f)` on an open binary file handle). [Agent 3 finding]
- `scripts/tests/test_adapt_golden_corpus.py` (imports `CodexEmitter`) and `scripts/tests/test_adapt_agents_for_codex.py` / `scripts/tests/test_adapt_skills_for_codex.py` (import CLI modules that import `codex.py`) were checked and confirmed **not** to exercise `emit_mcp_config` or `.codex/ll-mcp.toml` content — no change needed. [Agent 1 + Agent 3 finding, ruling out false positives from graph-discovery]
- If Proposed Solution step 1 concludes the fix must merge into existing `~/.codex/config.toml` content (rather than whole-file marker-gated overwrite), `CodexEmitter` will need new merge/overwrite/malformed-input test coverage paralleling `TestClaudeCodeEmitterEmitMcpConfig::test_merges_into_existing_sibling_entry` / `test_overwrites_stale_ll_mcp_entry` / `test_tolerates_malformed_existing_json` (`test_adapters.py:1711-1735`) — conditional on that outcome, not required if the fix stays a content-shape-only change to the existing whole-file-replace scheme. [Agent 3 finding]

### Documentation
- `docs/codex/README.md:32`, `docs/codex/usage.md:50` — claim the file "registers the `ll-mcp` server"
- `docs/reference/CLI.md:4185` — "Codex additionally emits a TOML MCP config snippet (`.codex/ll-mcp.toml`) registering the `ll-mcp` server (FEAT-3138)"
- `docs/reference/HOST_COMPATIBILITY.md:211-217` — a footnote flags a *different* open question (per-agent `mcp_servers` allowlist scoping) as "unresearched"; it does not address whether Codex reads a standalone `.codex/ll-mcp.toml` at all

_Wiring pass added by `/ll:wire-issue`:_
- `docs/codex/getting-started.md:94` — "...and `.codex/ll-mcp.toml` registering the `ll-mcp` server" [Agent 2 finding]
- `docs/guides/MCP_SERVER_GUIDE.md:118-122` — shows the literal buggy TOML block (```mcp_servers = ["ll-mcp"]```) as the documented output shape [Agent 3 finding]
- `docs/reference/API.md:9895` — `resolve_emitter` docstring table row: `` `CodexEmitter` ... `emit_mcp_config` writes `ll-mcp.toml` (`mcp_servers = ["ll-mcp"]`) `` [Agent 2 finding]
- `docs/reference/CLI.md:4275` (`### ll-mcp` section, distinct from the `### ll-adapt` mention at :4185 already listed above) — names `ll-mcp.toml` as one of the config files a host emits; update if the filename/path changes [Agent 2 finding]

### Configuration
N/A

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/adapt.py:126-127,139` — computes `mcp_output_dir = plugin_root / config_dir` (project-relative, via `HOST_CAPABILITIES[args.host].config_dir` in `scripts/little_loops/adapters/capabilities.py:69-71`) and passes it as `meta["output_dir"]` into every emitter uniformly. If Proposed Solution step 1 resolves to `~/.codex/config.toml`, `CodexEmitter.emit_mcp_config` becomes the only emitter that must override/ignore the passed `output_dir` rather than write under it — a real interface-contract deviation from `HostEmitter` (`core.py:44`), not just a content-shape change. [Agent 2 finding]

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

### Types
N/A — no new data shape is introduced. The existing `meta: dict` passed into every host emitter's `emit_mcp_config` (keys: `output_dir: Path`, `apply: bool`, `quiet: bool`, per `scripts/little_loops/adapters/core.py:641-645`) is unchanged by this fix.

### Signatures
- `CodexEmitter.emit_mcp_config(self, meta: dict) -> str` — unchanged signature at `scripts/little_loops/adapters/codex.py:375`; return value must remain `"adapted"` or `"skipped"` per `process_mcp_config`'s mapping (`core.py:654-659`), which treats any other string as an error `(0,0,1)`.

### Call Path
`process_mcp_config` (`scripts/little_loops/adapters/core.py:622-659`) -> `CodexEmitter.emit_mcp_config` (`scripts/little_loops/adapters/codex.py:375`) -> writes `<output_dir>/ll-mcp.toml`

### Decision Rules
N/A — no new gap kind, gate, or threshold. This is a content-shape correction to existing emission logic, not new decision logic.

## Implementation Steps

1. Establish the Codex MCP config format and read path; record a learning test.
2. Rewrite `emit_mcp_config` to that format, preserving marker/idempotency guards.
3. Replace the substring assertion with a `tomllib`-parsing assertion.
4. Correct the docs.
5. Verify end-to-end: run `ll-adapt --host codex --apply`, start Codex, call an
   `ll-mcp` tool. This end-to-end check has never been run and is the real
   acceptance criterion — a passing unit test only proves the file's shape.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

1. Codex's expected MCP server-definition shape and whether it reads a standalone `.codex/ll-mcp.toml` at all are confirmed against Codex's real config-loading behavior — not assumed from Claude Code's `{"command": "ll-mcp"}` shape, since nothing in this repo currently establishes Codex's own contract.
2. `CodexEmitter.emit_mcp_config` (`scripts/little_loops/adapters/codex.py:375-404`) emits a definition Codex can actually launch, using the `ll-mcp` console-script entry point (`scripts/pyproject.toml:119`) as the command value, while preserving the existing marker-gated idempotency behavior (`_MARKER`/`_LL_GENERATED_MARKERS`, `codex.py:22-30`).
3. `TestCodexEmitterEmitMcpConfig::test_toml_references_ll_mcp` (`scripts/tests/test_adapters.py:675-679`) is replaced with a structural assertion (parse the TOML, check the resulting table/keys) so it can no longer pass against a name-only array — `TestClaudeCodeEmitterEmitMcpConfig` (`test_adapters.py:1681-1733`) shows this codebase's structural-assertion pattern (`json.loads` + dict equality) to mirror in TOML form.
4. `docs/codex/README.md:32`, `docs/codex/usage.md:50`, and `docs/reference/CLI.md:4185` describe what the file now actually contains.
5. `python -m pytest scripts/tests/test_adapters.py -k Codex` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/codex/getting-started.md:94`, `docs/guides/MCP_SERVER_GUIDE.md:118-122`, `docs/reference/API.md:9895`, and `docs/reference/CLI.md:4275` — four additional doc sites beyond the three already listed in Proposed Solution, all describing or showing the current buggy shape/filename.
- If step 1 resolves the write target to `~/.codex/config.toml`: update `scripts/little_loops/cli/adapt.py:126-139` and account for `CodexEmitter.emit_mcp_config` overriding the passed `meta["output_dir"]` — a deviation from every other `HostEmitter` implementation, which write exactly under the passed `output_dir`.
- Add `import tomllib` to `scripts/tests/test_adapters.py` when rewriting `test_toml_references_ll_mcp`; follow the `tomllib.loads(text)` pattern in `scripts/tests/test_kimi_adapter.py:24,50-56`, not the file-handle pattern in `test_cli_doctor_install_checks.py`.
- Confirmed no-op, no action needed: `scripts/tests/test_adapt_golden_corpus.py`, `test_adapt_agents_for_codex.py`, `test_adapt_skills_for_codex.py` do not exercise `emit_mcp_config` and need no changes.

## Impact

- **Priority**: P2 — the entire `ll-mcp` surface is unreachable from the primary
  non-Claude-Code host, and three docs claim otherwise.
- **Effort**: Small once step 1 is answered; the emission change is a few lines.
  Step 1 is the real work, and could enlarge the fix to a config merge. **Revised
  2026-08-15**: half of step 1 is now answered (the table shape is confirmed), and the
  remaining half leans toward the config-merge branch — plan for Medium, not Small.
- **Risk**: Low — one emitter, guarded by a marker, with a dry-run path. **Revised
  2026-08-15**: Low→Medium *if* the fix merges into `~/.codex/config.toml`, since that
  writes to a real user-global file holding unrelated servers and `[projects."..."]`
  sections. A destructive merge there is a materially worse failure than today's inert
  file. Covered by the Behavior Parity contract above.
- **Breaking Change**: No. The current output is inert, so replacing it cannot
  regress a working setup.
- **Sequencing**: implement after BUG-3177. This issue's Step 5 (start Codex, call an
  `ll-mcp` tool) is only meaningful once the prompt surface works — a launchable Codex
  server that serves zero prompts verifies nothing. Also requires reinstalling Codex
  locally; see the blocker note under Proposed Solution.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-15 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-14_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 67/100 → MODERATE

### Concerns
- Criterion 4 (Issue Well-Specified) is capped at 10/20 by the format-check
  `missing_behavior_parity` gap on `scripts/tests/test_adapters.py` — the
  issue doesn't yet spell out a `### Behavior Parity` subsection for the
  rewritten test.
- The issue's own Proposed Solution step 1 flags the real open question:
  whether Codex reads a standalone `.codex/ll-mcp.toml` at all, and what
  table shape it expects. That's unconfirmed by any code/doc/learning-test in
  this repo today (no `codex` entry under `.ll/learning-tests/`), so the fix
  could stay a content-shape change to `emit_mcp_config` or balloon into a
  merge into `~/.codex/config.toml` with an `output_dir` contract deviation —
  drives the Ambiguity score (10/25) and the Complexity/Depth estimate.

## Session Log
- `/ll:confidence-check` - 2026-08-15T03:45:12 - `5315999c-c138-48bb-9d4c-374df2bedd62.jsonl`
- `/ll:wire-issue` - 2026-08-15T03:41:53 - `1e28525c-e109-4f5d-a52c-4b13341a9a3f.jsonl`
- `/ll:refine-issue` - 2026-08-15T03:32:38 - `853934e0-e1b5-4fb1-be76-8bcdf8e57dcb.jsonl`
- `/ll:refine-issue` - 2026-08-15T03:32:30 - `d730c0cc-e383-42c2-b3ab-672713d72ffb.jsonl`
- `/ll:capture-issue` - 2026-08-15T03:27:53 - `d730c0cc-e383-42c2-b3ab-672713d72ffb.jsonl`
