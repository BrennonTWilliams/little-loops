# oh-my-pi (`omp`) Headless CLI Flag Surface

**Status:** Audit complete — `OmpRunner` (FEAT-1850) landed against these
findings; structured-output section added by FEAT-2797.
**Last verified:** 2026-07-25 (structured-output section); original flag
audit 2026-07-03.
**Research issue:** FEAT-1850 (EPIC-2258), `OmpRunner` headless flag
translation; structured-output section by FEAT-2797.
**Package:** `@oh-my-pi/pi-coding-agent` (Bun package). Original audit
sourced from the oh-my-pi README, omp.sh/docs/cli, and DeepWiki mirrors of
`packages/coding-agent/src/cli/args.ts` / `modes/print-mode.ts`.
Structured-output findings verified directly against
`can1357/oh-my-pi@main` via the GitHub contents API (`args.ts`,
`docs/task-agent-discovery.md`, `docs/sdk.md`, `docs/rpc.md`,
`docs/ai-schema-normalize.md`).

## Sources

- oh-my-pi README and `omp.sh/docs/cli` (original audit)
- DeepWiki mirrors of `packages/coding-agent/src/cli/args.ts` and
  `packages/coding-agent/src/modes/print-mode.ts` (original audit)
- `can1357/oh-my-pi@main`, `packages/coding-agent/src/cli/args.ts` (420
  lines, the complete flag surface) — read directly via the GitHub contents
  API for the FEAT-2797 structured-output pass
- `docs/task-agent-discovery.md` (task-agent frontmatter contract and
  runtime schema precedence)
- `docs/sdk.md` (`createAgentSession` signature)
- `docs/rpc.md` (`--mode rpc` JSON-RPC protocol)
- `docs/ai-schema-normalize.md` and `@oh-my-pi/pi-ai/utils/schema`
  (provider-side schema normalization, referenced but not read in full)

## Headless invocation

```
omp -p <prompt>                    # one-shot, print mode
omp --mode json -p <prompt>        # JSONL event stream (no single-blob JSON mode)
omp --mode json --no-session -p <prompt>   # documented CI pattern; keeps
                                            # one-shot queries out of the
                                            # on-disk session store
omp --continue -p <prompt>         # resume most recent session in cwd
```

- **Prompt** is passed via `-p`/`--print` (one-shot, non-interactive).
- **Output**: default is human-readable. `--mode json` emits a **JSONL
  event stream** (session header, then agent events) — there is no
  single-blob JSON mode, so callers must consume the final event, the same
  contract as Codex `--json` (see `thoughts/research/codex-headless-invocation.md`).
- **Resume**: `--continue` — most recent session in the current working
  directory, matching Claude's `--continue` semantics.
- **Model**: `--model <pattern>`.
- **Tools**: `--tools <comma-list>` — a native allowlist flag.
- **Permission bypass**: none exists or is needed — print mode runs without
  an interactive UI context, so tools execute without approval prompts.
- **Agent selection**: no CLI flag. omp subagents are spawned in-session by
  the model (task delegation), not selected at invocation.
- **Config**: `.omp/ll-config.json` project config dir (FEAT-2262).

## Flag translation table

| Capability | omp mechanism | Notes |
|---|---|---|
| Streaming | `--mode json` (JSONL events) | Consume-the-final-event contract, same shape as Codex `--json` |
| Permission skip | implicit (no flag) | Print mode never prompts |
| Agent selection | **N/A → CapabilityNotSupported** | Subagents spawn in-session by the model, no `--agent` flag |
| Tool allowlist | `--tools <comma-list>` | Native allowlist |
| Resume | `--continue` | Most recent session in cwd |
| Model | `--model <pattern>` | |
| `json_schema` / `structured_output` | **N/A at the CLI level** | See "Structured output" below |

## Structured output (FEAT-2797)

**1. No CLI-level schema flag exists.** `packages/coding-agent/src/cli/args.ts`
defines `export type Mode = "text" | "json" | "rpc" | "acp" | "rpc-ui"` —
no schema/response-format flag of any kind. So:

- `json_schema: ✗` — correct, no flag to pass.
- `structured_output: False` — correct, since that flag narrowly means
  "honors the inline `--json-schema` the FSM evaluators append" (ENH-2627).
  Only the Anthropic `claude` CLI (and, since EPIC-3154, `qwen`) does.

**2. omp does have structured output, off the CLI path.** Two mechanisms,
neither reachable by adding a flag to `OmpRunner.build_blocking_json`:

- **Task-agent frontmatter `output:`** — a per-agent output schema, passed
  through as opaque schema data (`docs/task-agent-discovery.md`). Runtime
  precedence: task item's explicit `outputSchema` → agent frontmatter
  `output` → parent session `outputSchema`. A per-item `schemaMode`
  overrides the session mode; default `permissive`.
- **SDK / RPC** — `createAgentSession({outputSchema, requireYieldTool})`
  (`docs/sdk.md`), and `--mode rpc`'s JSON-RPC protocol with a defined
  response schema (`docs/rpc.md`). Provider-side schema normalization is a
  first-class subsystem (`docs/ai-schema-normalize.md`,
  `@oh-my-pi/pi-ai/utils/schema`) with per-provider strict-mode adapters.

This is a file/tool-mediated path analogous to Codex's `--output-schema`
(see `thoughts/research/codex-headless-invocation.md`), and like Codex's, the
FSM evaluators do not use it.

**3. Cross-harness agent dirs are deliberately skipped.** `discoverAgents()`
merges OMP-native + Claude *plugin* roots, but explicitly skips
`.claude/agents`, `.codex/agents`, and `.gemini/agents` — their frontmatter
"is not the OMP task-agent contract"; `TASK_AGENT_CONFIG_SOURCE = ".omp"`
filters both dir lists.

**Decision (FEAT-2797):** stay on prompt-and-parse (Option B) rather than
wire the RPC/`outputSchema` path into `OmpRunner`. The RPC path is a
structurally new mechanism — session-based, not one-shot-argv like every
other `HostRunner`/`HostInvocation` — and would need its own design across
three FSM evaluators. See FEAT-2797's Decision Rationale for the full
scoring.

## Capability map

```python
HostCapabilities(
    streaming=True,           # --mode json emits a JSONL event stream
    permission_skip=True,     # implicit — print mode never prompts
    agent_select=False,       # no --agent flag; subagents spawn in-session
    tool_allowlist=True,      # --tools <comma-list>
    structured_output=False,  # FEAT-2797: no CLI schema/response-format
                               # flag; the agent-frontmatter output:/SDK
                               # outputSchema path exists but is unused —
                               # stays on prompt-and-parse (BUG-2626 tag
                               # fallback)
)
```

## Out of scope here

- Skill/command discovery (`.omp/skills/`, `.omp/commands/`) — covered by
  `thoughts/research/omp-skill-command-surface.md` (FEAT-3103).
- Hook event surfaces — tracked by FEAT-2261/FEAT-2263, not this audit.
