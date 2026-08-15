# MCP Server Guide

> **When to use this**: You want to query a little-loops project's state — issues,
> dependency health, session history — from an MCP-capable client such as Claude Code,
> Codex, or Claude Desktop. This guide covers installing, registering, verifying, and
> troubleshooting the `ll-mcp` stdio server. For the authoritative tool parameter and
> response schemas, see [CLI Reference § `ll-mcp`](../reference/CLI.md#ll-mcp) — this guide
> deliberately does not restate them.

## Contents

- [What `ll-mcp` Is](#what-ll-mcp-is)
- [Install](#install)
- [The Working-Directory Requirement](#the-working-directory-requirement)
- [Registering the Server](#registering-the-server)
- [Verifying with `mcp-call`](#verifying-with-mcp-call)
- [Resources and Prompts in Practice](#resources-and-prompts-in-practice)
- [The Mutation Surface and Its Guards](#the-mutation-surface-and-its-guards)
- [Polling and Stopping a Run: `tasks/*`](#polling-and-stopping-a-run-tasks)
- [Troubleshooting](#troubleshooting)
- [See Also](#see-also)

---

## What `ll-mcp` Is

`ll-mcp` is an MCP server (stdio by default, streamable HTTP with `--http`) that exposes
a little-loops project over the Model Context Protocol. It advertises three surfaces:

| Surface | What it gives a client |
|---------|------------------------|
| **Tools (read)** | `issues_query`, `issue_get`, `history_search`, `deps_check`, `capabilities` |
| **Tools (write)** | `issue_capture`, `issue_set_status`, `issue_link`, `issue_append_log` — dry-run by default, see [below](#the-mutation-surface-and-its-guards) |
| **Resources** | Issue files, `.ll/ll-goals.md`, and `docs/**/*.md` under an `ll://` scheme |
| **Prompts** | Every discovered `SKILL.md`, listed as an invocable MCP prompt |
| **Tasks** | `tasks/get` / `tasks/cancel` — poll or stop an in-flight `ll-loop` run, see [below](#polling-and-stopping-a-run-tasks) |

It is launched *by a host*, never by hand — it speaks JSON-RPC on stdin/stdout and prints
nothing useful to a terminal. Each tool wraps a `little_loops` library call directly: no
subprocess, no `ll-*` CLI shelling out, no orchestration.

---

## Install

The MCP server lives behind an optional extra, because the `mcp` SDK is a heavyweight
dependency that most little-loops users never need:

```bash
pip install "little-loops[mcp]"
```

Without the extra, `ll-mcp` exits `2` with `ll-mcp requires the `mcp` extra` rather than
an `ImportError` traceback. Because hosts usually swallow a server's stderr, this failure
typically surfaces only as "server failed to start" in the client — run `ll-mcp` directly
in a terminal to see the real message (it will hang waiting for JSON-RPC input if the
extra *is* installed; `Ctrl-D` to exit).

---

## The Working-Directory Requirement

**`ll-mcp` resolves the project root as the process's current working directory.** There
is no `--project-root` flag, no config key, and no upward search for a `.ll/` marker.

This matters because MCP hosts vary in what cwd they spawn a server with. A client that
launches its servers from `$HOME` will start `ll-mcp` against `$HOME`, and every tool will
answer truthfully about a project that does not exist there — `issues_query` returns `[]`,
`deps_check` reports a clean graph, `resources/list` is empty. Nothing errors. This is the
single most common cause of a "working but useless" `ll-mcp`.

Two ways to pin it:

1. **A client that supports a `cwd` field** in its server config — set it to the project
   root (see the Claude Desktop snippet below).
2. **A client that does not** — wrap the command in a shell:

   ```json
   {
     "command": "sh",
     "args": ["-c", "cd /abs/path/to/project && exec ll-mcp"]
   }
   ```

Claude Code and Codex both launch project-scoped servers from the project root, so the
`ll-adapt`-generated configs below need no `cwd`.

---

## Registering the Server

### Claude Code

```bash
ll-adapt --host claude-code --apply
```

This merges an `ll-mcp` entry into `.mcp.json` at the project root, preserving any
existing `mcpServers` content:

```json
{
  "mcpServers": {
    "ll-mcp": {
      "command": "ll-mcp"
    }
  }
}
```

### Codex

```bash
ll-adapt --host codex --apply
```

The same run that bridges skills, commands, and agent personas into Codex also writes
`.codex/ll-mcp.toml`:

```toml
mcp_servers = ["ll-mcp"]
```

### Claude Desktop and other MCP clients

No emitter exists for these yet — `ll-adapt --host <other>` skips the MCP artefact — so
write the config by hand. Claude Desktop reads
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS:

```json
{
  "mcpServers": {
    "ll-mcp": {
      "command": "/abs/path/to/venv/bin/ll-mcp",
      "cwd": "/abs/path/to/project"
    }
  }
}
```

Use an **absolute path to the `ll-mcp` executable**. A GUI-launched client does not
inherit your shell's `PATH`, so a bare `"ll-mcp"` that works from a terminal will fail
there with a spawn error. `which ll-mcp` gives you the path to paste.

One entry per project: the server is scoped to a single working directory, so a second
project means a second `mcpServers` key (`ll-mcp-otherproject`) with its own `cwd`.

---

## Verifying with `mcp-call`

`mcp-call` is a thin JSON-RPC client that ships with little-loops. It reads `.mcp.json`
from the current directory, spawns the named server, performs the handshake, calls one
tool, and prints the response envelope — the fastest way to confirm the server works
before blaming the host.

```bash
mcp-call ll-mcp/capabilities '{}'
```

Its exit code tells you which layer failed: `0` success, `1` tool error, `124` timeout,
`127` server or tool not found, `2` config/usage error.

### The five tools, end to end

```bash
# Open issues, filtered and sorted by priority
mcp-call ll-mcp/issues_query '{"issue_type": "EPIC", "limit": 2}'
```

```json
[
  {
    "id": "EPIC-2790",
    "priority": "P1",
    "type": "EPIC",
    "title": "Subprocess and MCP Robustness",
    "path": "/abs/path/.issues/epics/P1-EPIC-2790-subprocess-and-mcp-robustness.md",
    "status": "open",
    "parent": null,
    "labels": []
  }
]
```

```bash
# One issue's full summary card — accepts 3122, FEAT-3122, or P3-FEAT-3122
mcp-call ll-mcp/issue_get '{"issue_id": "3122"}'
```

```json
{
  "issue_id": "FEAT-3122",
  "title": "ll-doctor advisor-reachability check",
  "priority": "P3",
  "status": "Open",
  "raw_status": "open",
  "confidence": "50",
  "outcome": "58",
  "path": ".issues/features/P3-FEAT-3122-advisor-ll-doctor-reachability-check.md"
}
```

Note the two status fields: `status` is display-cased for rendering, `raw_status` is the
frontmatter value. Match on `raw_status` in any automation.

```bash
# FTS5 search over .ll/history.db
mcp-call ll-mcp/history_search '{"query": "handoff", "limit": 1}'
```

```json
[
  {
    "content": "**/.handoff*",
    "kind": "file",
    "ref": "**/.handoff*",
    "anchor": "Glob",
    "ts": "2026-06-04T06:48:07Z",
    "score": -9.998166573997038
  }
]
```

`score` is FTS5 BM25: **more negative is a better match**. An empty result is normal on a
young project — `.ll/history.db` only fills as sessions accumulate.

```bash
# Cross-issue dependency graph health
mcp-call ll-mcp/deps_check '{}'
```

```json
{
  "has_issues": true,
  "broken_refs": [],
  "missing_backlinks": [["ENH-2997", "ENH-2991"]],
  "cycles": [],
  "stale_completed_refs": [["FEAT-2102", "FEAT-1932"]],
  "broken_depends_on_refs": [],
  "broken_relates_to_refs": []
}
```

`has_issues` means "this project has issue files", not "problems were found" — read the
individual lists for that.

```bash
# Resolved host CLI and its capability surface
mcp-call ll-mcp/capabilities '{}'
```

```json
{
  "host": "claude-code",
  "binary": "claude",
  "version": "",
  "capabilities": [
    {"name": "streaming", "status": "full", "note": ""},
    {"name": "claude_md_suppression", "status": "unsupported", "note": "the claude CLI has no flag to skip CLAUDE.md"}
  ]
}
```

This reports the host **little-loops itself would drive** for automation (per
`LL_HOST_CLI` / `orchestration.host_cli`), not the MCP client you are calling from.

---

## Resources and Prompts in Practice

Both surfaces are enumerated **once, when the server starts**. The tools are not — they
re-resolve the project root and re-read the filesystem on every call. That difference
produces the single behaviour that surprises people:

> A newly created issue is immediately visible to `issues_query` and `issue_get`, but does
> not appear as an `ll://issues/<ID>` resource until the server restarts.

Restarting the server means restarting it from the host (reconnect the MCP server, or
restart the client). The same applies to a newly added skill and the prompts list.

Two more practical notes:

- **The resource list is large.** On a mature project it is one entry per issue plus one
  per file under `docs/` — this repository enumerates over 3,000. Clients that eagerly
  fetch every resource will be slow; prefer `issues_query` to *find* an issue and
  `resources/read` (or `issue_get`) to fetch the one you want.
- **Prompts come from the plugin checkout, not the pip package.** The skills directory is
  resolved from `$CLAUDE_PLUGIN_ROOT` if set, otherwise from the installed package's
  parent directory. A pip-only install with no plugin checkout therefore lists zero
  prompts; set `CLAUDE_PLUGIN_ROOT` in the server's `env` block to point at a checkout if
  you want them.

Resource and prompt listings carry `ttlMs`/`cacheScope` cache hints (5 minutes, public),
so a well-behaved client will not re-enumerate on every request.

---

## The Mutation Surface and Its Guards

Four tools write: `issue_capture`, `issue_set_status`, `issue_link`, and
`issue_append_log`. Each wraps the same library function the equivalent `ll-issues`
subcommand calls, so a tool call and a CLI invocation produce the same file state.

`ll-auto`, `ll-parallel`, and `ll-action invoke` are still off the surface entirely. `ll-loop`
is the one exception: `loop_start` (below, alongside `tasks/*`) starts a detached run.
Everything else about the boundary is unchanged — `tasks/cancel` is a control operation over
a run that is already going, signalling an existing PID, never spawning one.

Two guards sit in front of the four.

### Guard 1 — dry-run by default

Every mutating tool takes an `apply` parameter that defaults to `false`. Called without
it, the tool returns the change it *would* make and writes nothing:

```jsonc
// tools/call issue_set_status {"issue_id": "FEAT-3149", "status": "deferred"}
{
  "applied": false,
  "tool": "issue_set_status",
  "target": { "issue_id": "FEAT-3149", "path": ".issues/features/P3-FEAT-3149-….md" },
  "changes": [ { "field": "status", "from": "open", "to": "deferred" } ]
}
```

Re-call with `"apply": true` to perform it. The default is a **refusal to mutate**, not an
opt-out flag: a host that omits the parameter entirely does not write, and the check is
fail-closed — only the literal boolean `true` opts in. `"true"`, `1`, and `null` are all
dry-runs.

One shape differs. A dry-run `issue_capture` returns **no issue ID**, not even a predicted
one — it reports the type, priority, slug, target directory, and rendered body instead.
The ID is allocated inside `create_issue`'s lock hold at write time, so any ID named
before apply is a guess that is wrong precisely when it matters: when something else
allocated concurrently. The apply response carries the real one.

### Guard 2 — per-transport policy

Whether the mutating tools may run at all is a deployment choice, set per transport in
`.ll/ll-config.json`:

```json
{
  "mcp": {
    "transport_policy": {
      "http":  { "allow_mutations": false },
      "stdio": { "allow_mutations": true }
    }
  }
}
```

Those are the defaults. HTTP denies mutations because that transport ships without
authentication, so the posture for a transport a remote host can reach is read-only until
someone opts in; stdio is a same-machine, same-user channel and defaults open. One server
build serves both.

A denied call is refused at the transport layer, before the JSON-RPC body is parsed —
ASGI middleware reads the SEP-2243 `Mcp-Method` / `Mcp-Name` routing headers off the raw
request and answers with a JSON-RPC error and HTTP 403. Reads on the same server are
unaffected:

```
$ # with http.allow_mutations = false
$ mcp-call ll-mcp tools/call issue_set_status '{"issue_id":"FEAT-1","status":"done"}'
{"jsonrpc":"2.0","id":null,"error":{"code":-32001,"message":"policy denied tools/call/issue_set_status: …"}}

$ mcp-call ll-mcp tools/call issues_query '{}'
[ … works fine … ]
```

This is sound against a spoofed header even though the middleware never sees the body: the
SDK independently rejects any request whose `Mcp-Method`/`Mcp-Name` disagree with its body
(`HEADER_MISMATCH`, `-32020`), and both headers are mandatory for `tools/call`. A request
cannot reach a mutating handler while hiding its identity from the guard.

### Distinguishing the two groups from a client

The four mutating tools carry a `readOnlyHint: false` annotation in `tools/list`; the five
read-only tools carry no annotations at all. A host can key presentation — a confirmation
prompt, a different icon — off that.

---

## Starting, Polling, and Stopping a Run

`loop_start` starts a detached `ll-loop` run; `tasks/get` and `tasks/cancel` poll or stop
it (or a run started by other means, e.g. `ll-loop run` on the workstation). All three
share one grant (`allow_tasks`, below) and one identifier space (`instance_id`), so a host
can start a run from a phone-side session and poll/stop it from a workstation session
without SSH-ing anywhere. `ll-queue` is out of scope: only `ll-loop` runs are reachable
this way.

### Starting a run: `loop_start`

```
$ mcp-call ll-mcp tools/call loop_start '{"loop": "rn-refine", "context": ["ISSUE_ID=FEAT-3151"]}'
{"instance_id": "rn-refine-20260814T160000-a1b2", "loop": "rn-refine"}
```

`loop_start` always performs the identical detached spawn — the same one `ll-loop run
--background` does — regardless of caller. What differs is the **response shape**, per
SEP-2663 (the MCP "tasks" extension): a client that declared the tasks extension in its
per-request capabilities *and* asked for task-augmented execution on that call gets back a
task-shaped result instead:

```
$ # client declares the tasks extension and sets params.task on this call
{"resultType": "task", "taskId": "rn-refine-20260814T160000-a1b2", "status": "working"}
```

Any other client — one that never declared the extension, declared it but did not set
`params.task` on this call, or is on a pre-2026-07-28 protocol version — gets the ordinary
shape above, `instance_id` and all. Either way the run started; only the envelope changes.
The task id is the run's `instance_id` verbatim (minted with a short entropy suffix, not
`ll-loop`'s own one-second-resolution id, to stay unique under agent-paced calls) and is
what `tasks/get`/`tasks/cancel` accept below.

If the run cannot be spawned — a scope conflict, an unloadable loop — the call returns an
ordinary tool error (`isError: true`) carrying the reason. It never returns a task id or an
`instance_id` for a run that does not exist.

`loop_start` is **not** one of the four mutating tools above: a dry-run "start" has no
coherent meaning, so it takes no `apply` parameter and is gated by `allow_tasks` (below)
instead of `allow_mutations`.

### Polling and stopping: `tasks/*`

These are not tools — they are custom JSON-RPC methods registered directly on the server,
shaped to track the (not-yet-shipped) `io.modelcontextprotocol/tasks` extension so a
future swap to the official mechanism is a registration change, not a client-visible one.
`initialize`'s capabilities never advertise the extension itself — the server does not
claim a capability it only implements privately.

`taskId` is the `ll-loop` `instance_id` verbatim — the same string `ll-loop status`
already prints — not a handle minted by the server:

```
$ mcp-call ll-mcp tasks/get '{"taskId": "rn-refine-20260811T140000"}'
{"taskId": "rn-refine-20260811T140000", "status": "working", "runStatus": "running"}
```

The `status` field reconciles PID liveness before ever reporting `"working"` — a run whose
process died (OOM, kernel kill) without updating its state file is reported not-running,
not left `"working"` forever. Once the run is terminal, the result also carries the
`ExecutionResult` fields (`final_state`, `iterations`, `terminated_by`, `duration_ms`,
`captured`):

```
$ mcp-call ll-mcp tasks/get '{"taskId": "rn-refine-20260811T140000"}'
{"taskId": "…", "status": "completed", "runStatus": "completed", "final_state": "done", "iterations": 12, "terminated_by": "completed", "duration_ms": 483000, "captured": { … }}
```

An unknown `taskId` is a distinct JSON-RPC error, never a default `"working"` shape:

```
$ mcp-call ll-mcp tasks/get '{"taskId": "no-such-run"}'
{"jsonrpc":"2.0","id":null,"error":{"code":-32002,"message":"no run found for taskId 'no-such-run'"}}
```

`tasks/cancel` stops a running instance the same way `ll-loop stop` does — `SIGTERM`, then
`SIGKILL` after a 10s grace period. Neither backend has a genuinely terminal "cancelled"
status, so the result never reports `"cancelled"` bare: `resumable` and the backend's raw
status ride alongside, so a host cannot mistake a resumable stop for an irreversible one:

```
$ mcp-call ll-mcp tasks/cancel '{"taskId": "rn-refine-20260811T140000"}'
{"taskId": "…", "status": "cancelled", "resumable": true, "runStatus": "user_stopped"}
```

`tasks/*` and `loop_start` get the same deny-by-default-on-HTTP treatment as the mutating
tools (Guard 2 above), but as their own grant — `allow_tasks`, not `allow_mutations`.
Consenting to issue-file writes over HTTP does not imply consenting to starting or
stopping a running agent; starting one is the same class of authority as stopping it, so
both sit behind one grant:

```json
{
  "mcp": {
    "transport_policy": {
      "http":  { "allow_mutations": false, "allow_tasks": false },
      "stdio": { "allow_mutations": true,  "allow_tasks": true }
    }
  }
}
```

Those are the defaults — both closed on HTTP, both open on stdio. A denied `tasks/get`
reports itself as a `tasks/get` denial (not a `tools/call` one), and a denied `loop_start`
reports itself as a `tools/call/loop_start` denial, since the underlying guard is shared
with Guard 2 but every method/tool is gated independently.

Enforcement is uniform across both transports: the `tools/call` and `tasks/*` handlers
themselves consult the policy (in addition to the HTTP transport's ASGI middleware, which
still denies before the JSON-RPC body is parsed on that transport), so a denied call over
stdio returns the same `-32001` JSON-RPC error the HTTP path returns.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Client reports the server failed to start | `mcp` extra not installed | `pip install "little-loops[mcp]"`; run `ll-mcp` in a terminal to see the real stderr |
| Spawn error / command not found, but `ll-mcp` works in your shell | GUI client does not inherit shell `PATH` | Use the absolute path from `which ll-mcp` in the config |
| Every tool succeeds but returns empty results | Server spawned with the wrong cwd | Set `cwd`, or wrap in `sh -c 'cd /path && exec ll-mcp'` — see [above](#the-working-directory-requirement) |
| A new issue is missing from `resources/list` but `issue_get` finds it | Resources are enumerated at startup | Restart/reconnect the server |
| `prompts/list` is empty | No plugin checkout resolvable from the installed package | Set `CLAUDE_PLUGIN_ROOT` to a checkout in the server's `env` |
| `history_search` always returns `[]` | `.ll/history.db` absent or empty | Confirm the file exists; history accrues over sessions |
| `mcp-call` exits `127` | `.mcp.json` missing from cwd, or no `ll-mcp` key in it | Run `mcp-call` from the project root; `ll-adapt --host claude-code --apply` |
| `mcp-call` exits `124` | Server started but never answered | Check for a stale install: `pip show little-loops`, then re-run `ll-adapt` |

For anything protocol-level, run the server by hand and speak to it directly — three lines
of JSON on stdin is a complete session:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"debug","version":"1"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | ll-mcp
```

---

## See Also

- [CLI Reference § `ll-mcp`](../reference/CLI.md#ll-mcp) — authoritative tool parameters,
  response shapes, and the resource/prompt surface contract
- [CLI Reference § `ll-adapt`](../reference/CLI.md#ll-adapt) — the host adapter that emits
  MCP config
- [API Reference § `little_loops.mcp_server`](../reference/API.md) — module-level internals
- [Host Compatibility](../reference/HOST_COMPATIBILITY.md) — which hosts support what
- [Issue Management Guide](ISSUE_MANAGEMENT_GUIDE.md) — the write path the MCP surface
  deliberately omits
