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

### Documentation
- The three sites above; `docs/guides/MCP_SERVER_GUIDE.md` if it documents
  Codex registration
- `docs/reference/HOST_COMPATIBILITY.md:214` already flags Codex
  `mcp_servers`/`skills.config` scoping as unresearched — update it with
  whatever step 1 establishes

### Configuration
- Output path may change from `.codex/ll-mcp.toml` to `~/.codex/config.toml`
  depending on step 1.

## Implementation Steps

1. Establish the Codex MCP config format and read path; record a learning test.
2. Rewrite `emit_mcp_config` to that format, preserving marker/idempotency guards.
3. Replace the substring assertion with a `tomllib`-parsing assertion.
4. Correct the docs.
5. Verify end-to-end: run `ll-adapt --host codex --apply`, start Codex, call an
   `ll-mcp` tool. This end-to-end check has never been run and is the real
   acceptance criterion — a passing unit test only proves the file's shape.

## Impact

- **Priority**: P2 — the entire `ll-mcp` surface is unreachable from the primary
  non-Claude-Code host, and three docs claim otherwise.
- **Effort**: Small once step 1 is answered; the emission change is a few lines.
  Step 1 is the real work, and could enlarge the fix to a config merge.
- **Risk**: Low — one emitter, guarded by a marker, with a dry-run path.
- **Breaking Change**: No. The current output is inert, so replacing it cannot
  regress a working setup.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-15 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-15T03:27:53 - `d730c0cc-e383-42c2-b3ab-672713d72ffb.jsonl`
