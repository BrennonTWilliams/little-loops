# Codex CLI Headless Invocation Contract

**Status:** Research note for FEAT-1465 (CodexRunner flag translation)
**Last verified:** 2026-05-15
**Codex version:** Rust-based OpenAI Codex CLI (current GA; not the deprecated Node version)

## Sources

- OpenAI Codex CLI reference: <https://developers.openai.com/codex/cli/reference>
- Non-interactive mode docs: <https://developers.openai.com/codex/noninteractive>
- Source repo: <https://github.com/openai/codex> (`docs/exec.md`, `docs/config.md`, `docs/sandbox.md`)
- Approval policy values surfaced via cross-references in upstream issues and third-party guides; canonical enum: `untrusted | on-failure | on-request | never`.

`codex` binary is not installed on the development host, so `codex exec --help` could not be exercised directly. All flag names below are sourced from upstream docs and the developers.openai.com reference.

## Headless invocation: `codex exec`

```
codex exec [FLAGS] <PROMPT>
codex exec [FLAGS] -          # read prompt from stdin
codex exec resume [--last | SESSION_ID] [FLAGS] [FOLLOWUP_PROMPT]
```

- **Prompt is positional**, not via `-p`. Claude's `-p <prompt>` does not translate verbatim — in Codex `-p` is `--profile`.
- **Output**: by default streams progress to stderr and final agent message to stdout. With `--json`, emits newline-delimited JSON events (Claude `stream-json` equivalent). There is no single-blob JSON mode like Claude's `--output-format json`; callers that want a final blob must consume the last event of the `--json` stream, or use `--output-last-message <path>` to capture the final message to a file.
- **Working directory**: `-C <dir>` / `--cd <dir>`. Sets workspace root before executing.

## Flag translation table

| Claude Code flag | Codex equivalent | Source / notes |
|------------------|------------------|----------------|
| `claude -p <prompt>` | `codex exec <prompt>` (positional) | CLI reference |
| `--output-format stream-json` | `--json` (newline-delimited events) | CLI reference; Codex docs |
| `--output-format json` | `--json` (streams) **or** `--output-last-message <path>` | Codex has no single-blob JSON mode; use `--json` and consume last event |
| `--dangerously-skip-permissions` | `--dangerously-bypass-approvals-and-sandbox` | CLI reference; exact semantic match (skips both approval and sandbox) |
| `--continue` (resume) | `codex exec resume --last` (restructures subcommand) | CLI reference resume subcommand |
| `--agent <name>` | **N/A → CapabilityNotSupported** | Codex has no per-agent selection; profiles are an authentication concept, not an agent persona |
| `--tools <list>` | **N/A → CapabilityNotSupported** | Codex constrains tools via sandbox mode (`-s read-only|workspace-write|danger-full-access`), not an allowlist |
| `--verbose` | (dropped) | Codex stream output is verbose by default; no explicit flag |
| `--model <id>` | `-m <id>` / `--model <id>` | CLI reference |
| `--json-schema <dict>` | `--output-schema <path>` (file, not dict) | Codex supports schema enforcement but only via file path. The `build_blocking_json(json_schema=dict)` Protocol signature gives an inline dict, so emit `CapabilityNotSupported` until a tempfile-write path is added (future enhancement). |
| `--no-session-persistence` | `--ephemeral` | CLI reference |
| `--version` | `codex --version` (top-level, not on `exec`) | Standard CLI |

### Approval-policy enum (`--ask-for-approval`)

For reference (not directly used by CodexRunner since we use the combined bypass flag):

- `untrusted` — only known-safe commands run without prompting
- `on-failure` — deprecated, prefer `on-request` or `never`
- `on-request` — model decides when to ask
- `never` — never ask; failures returned to model immediately

### Sandbox enum (`-s/--sandbox`)

- `read-only` (default)
- `workspace-write`
- `danger-full-access`

`--dangerously-bypass-approvals-and-sandbox` is equivalent to `--ask-for-approval never --sandbox danger-full-access` and is the cleanest 1:1 mapping for Claude's `--dangerously-skip-permissions`.

## Capability map

```python
HostCapabilities(
    streaming=True,          # --json emits NDJSON events
    permission_skip=True,    # --dangerously-bypass-approvals-and-sandbox
    agent_select=False,      # no per-agent flag; profiles are auth, not persona
    tool_allowlist=False,    # tool surface is controlled via sandbox mode
)
```

## Gating recommendation

Per FEAT-1465 AC ("gated behind `LL_HOST_CLI=codex` until manually tested"):

- Register `CodexRunner` in `_HOST_RUNNER_REGISTRY` so explicit `LL_HOST_CLI=codex` resolves it.
- Comment out the `("codex", "codex")` row in `_PROBE_ORDER` so an installed `codex` binary alone does not auto-activate the runner.
- This leaves `LL_HOST_CLI=codex` as the single activation path until a follow-up enables auto-probe.
