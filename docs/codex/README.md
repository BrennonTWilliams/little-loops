# little-loops on Codex CLI

little-loops integrates with [OpenAI Codex CLI](https://github.com/openai/codex) as a first-class host. Hook intents, orchestration CLIs, and skill/command discovery all work under Codex — with a small set of limitations documented below.

**New to Codex + little-loops?** Start with [Getting Started](getting-started.md).

---

## What works

### Hook intents

| Intent | Status |
| --- | --- |
| `session_start` | ✓ wired (matcher: `startup` only) |
| `pre_compact` | ✓ wired |
| `user_prompt_submit` | ✓ wired |
| `post_tool_use` | ✓ wired (fire-and-forget, ≤5s timeout) |
| `pre_tool_use` | opt-in (see [Usage → Opt-in pre_tool_use](usage.md#opt-in-pre_tool_use)) |
| `stop` | deferred — no current consumer |
| `post_compact` | deferred — no current consumer |
| `permission_request` | deferred — no current consumer |

Hook intents reach the same host-agnostic Python dispatcher (`scripts/little_loops/hooks/`) as Claude Code and OpenCode. The Codex adapter (`hooks/adapters/codex/`) is a thin Bash shim with no logic of its own.

### Orchestration CLIs

`ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`, and `ll-sprint` all route through the host runner abstraction and work with Codex. Set `LL_HOST_CLI=codex` or let the runner auto-detect the `codex` binary on `PATH`. See [Usage → Running orchestration CLIs](usage.md#running-orchestration-clis).

### Skill and command discovery

After running `ll-adapt-skills-for-codex --apply` once, all `ll` skills and commands appear in Codex as `~/.codex/skills/<name>/SKILL.md` entries, making `/ll:*` slash commands discoverable from the Codex TUI.

---

## What is deferred

- **`stop` / `post_compact` / `permission_request`**: Codex fires these events, but little-loops has no current consumer for them. Hooks for these intents are not wired in `.codex/hooks.json` by default.
- **`--agent` (persona selection)**: `CodexRunner` emits `CapabilityNotSupported` and silently drops the flag. See [Usage → Current Limitations](usage.md#current-limitations).
- **`--tools` (sandbox modes)**: Partially supported; only basic sandbox modes pass through.

Run `ll-doctor` (or `ll-doctor --json`) to see exactly which capabilities and hook intents are wired for your active host.

---

## See also

- [Getting Started](getting-started.md) — prerequisites, install, trust prompt, first-run verification
- [Usage](usage.md) — orchestration CLIs, skill invocation, opt-in pre_tool_use, current limitations
- [Host Compatibility Matrix](../reference/HOST_COMPATIBILITY.md) — authoritative per-host feature matrix
- [Troubleshooting](../development/TROUBLESHOOTING.md) — common issues including binary detection and hook trust
