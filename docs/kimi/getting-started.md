# Getting Started with little-loops on Kimi Code CLI

This guide walks through installing and verifying little-loops on a project where you use [Kimi Code CLI](https://www.kimi.com/code/docs/en/).

---

## Prerequisites

1. **Kimi Code CLI** — `kimi` binary on `PATH`, logged in. Verify with `kimi --version` (the adapter is machine-verified on **0.30.0**).
2. **Python 3.11+** — verify with `python --version`.
3. **little-loops Python package** — install once per Python environment:

   ```bash
   pip install little-loops
   ```

   For a local (development) install from the repo:

   ```bash
   pip install -e "./scripts[dev]"
   ```

---

## Install

Run the initializer from inside your project directory:

```bash
ll-init --hosts kimi-code
```

This installs the hook adapter as a **managed, marker-delimited `[[hooks]]` block** in the **user-level** `$KIMI_CODE_HOME/config.toml` (default `~/.kimi-code/config.toml`, honoring the `KIMI_CODE_HOME` env var), with `{{LL_PLUGIN_ROOT}}` substituted to the absolute path of the installed little-loops package. Kimi has no project-local hook file (`.kimi-code/local.toml` only supports `[workspace]`), so user-level config is the only hook install target. `ll-init` never touches config outside the managed block, and stamps the block with the package gen-version so `ll-init --upgrade` can regenerate it. It also writes `.ll/ll-config.json` and appends the little-loops command block to `AGENTS.md` (the cross-tool instructions file kimi reads).

**Auto-detection**: `--hosts kimi-code` is set automatically when the `kimi` binary is on `PATH` or a `.kimi-code/` directory already exists in the project (probed last, so installing the kimi binary never changes resolution for existing users). Preview without touching files:

```bash
ll-init --hosts kimi-code --dry-run
```

Hooks take effect in **new** kimi sessions — there is no trust dialog.

---

## Config file

When `LL_HOOK_HOST=kimi-code` (set by the adapter) or `LL_STATE_DIR=.kimi-code` is in the environment, configuration is probed at `.kimi-code/ll-config.json` **before** the default `.ll/ll-config.json` (ENH-2913). This is the only state path redirected by the kimi host — all other directories (`.issues/`, `.loops/`, etc.) use the project-root defaults regardless of host.

To create a kimi-specific config:

```bash
cp .ll/ll-config.json .kimi-code/ll-config.json
# Edit .kimi-code/ll-config.json as needed
```

---

## Skill and command discovery

Run `ll-adapt --host kimi-code --apply` once after install to bridge all little-loops skills, commands, and agent personas into kimi:

```bash
ll-adapt --host kimi-code --apply
```

This writes:

- **Skills** → `.kimi-code/skills/<name>/SKILL.md` — a native kimi scan dir. The format is near-1:1 (extra frontmatter keys like `allowed-tools` are tolerated); `name:` is injected when absent. Invoke as `/skill:<name>` or the `/<name>` shorthand. Companion files beside SKILL.md (`templates.md`, `reference.md`, ...) are mirrored alongside so relative companion references resolve (BUG-3164).
- **Commands** → `.kimi-code/skills/ll-<stem>/SKILL.md` — kimi has no project-local *commands* surface outside plugin manifests, so commands are bridged as skills and invoked as `/ll-<stem>`.
- **Agents** → `.kimi-code/agents/<name>.md` — kimi natively loads Claude-style agent files (comma-separated `tools`, filename fallback for `name`) and spawns real subagents, so files are written verbatim with no degraded-mode fallback.

Re-run this command after upgrading little-loops or adding new skills/agents to pick up any changes.

### Plugin install (optional)

The repo root carries a `kimi.plugin.json` manifest (plugin id `ll`, FEAT-2917) that registers `skills/`, `commands/`, and the hook shims in one package — including the true `/ll:<name>` slash-command namespace (identical to the Claude plugin). Install it from the kimi TUI:

```
/plugins install https://github.com/BrennonTWilliams/little-loops
```

Plugin installs are **per-user only** (copied to `$KIMI_CODE_HOME/plugins/managed/ll/`); project-scoped installs are not supported. Changes apply after `/reload` or a new session.

---

## Automation

Orchestration CLIs (`ll-auto`, `ll-parallel`, `ll-action`, `ll-harness`, `ll-loop`, `ll-sprint`) route through the host runner abstraction. Select kimi explicitly with:

```bash
LL_HOST_CLI=kimi-code ll-auto
```

or set `orchestration.host_cli: "kimi-code"` in `ll-config.json`. Auto-detection also works when `kimi` is on `PATH`. See [Automation](automation.md) for runner flags, resume/agent conflicts, and current limitations.

---

## First-run verification

1. Start a new kimi session — the managed hooks activate silently (no trust prompt).
2. Run a bridged command, e.g., `/ll-help`, or `/ll:help` if you installed the plugin.
3. Sanity-check the full install surface from the shell:

   ```bash
   ll-doctor --full
   ```

   The host-capability section should report kimi-code with streaming / permission skip / agent selection `full` or `partial`, and the verifier family should print OK lines.
4. To exercise the hook adapter end-to-end from the shell (outside a session):

   ```bash
   LL_HOOK_HOST=kimi-code echo '{"session_id":"test","cwd":"'$(pwd)'","hook_event_name":"SessionStart","source":"startup"}' \
     | bash scripts/little_loops/hooks/adapters/kimi/session-start.sh
   ```

   A zero exit code indicates the adapter and Python dispatcher are both reachable.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Hooks do nothing | Start a **new** kimi session — hooks install user-level and only load at session start |
| `kimi: command not found` during init | Ensure the `kimi` binary is on `PATH`: `which kimi` |
| Adapter scripts not executable | `chmod +x scripts/little_loops/hooks/adapters/kimi/*.sh` |
| `LL_HOOK_HOST=kimi-code` not recognized | Upgrade to the latest little-loops version: `pip install --upgrade little-loops` |
| Stale managed block after a package upgrade | Run `ll-init --upgrade` — it regenerates the managed `[[hooks]]` block and re-stamps the gen-version |
| Skills not appearing in kimi | Re-run `ll-adapt --host kimi-code --apply` |

For more issues see [Troubleshooting](../development/TROUBLESHOOTING.md).

---

## Next steps

- [Hook Events](hook-events.md) — event → intent mapping, payload drift, blockable events
- [Automation](automation.md) — orchestration CLIs under kimi, runner flags, current limitations
- [Host Compatibility Matrix](../reference/HOST_COMPATIBILITY.md) — full per-host feature matrix
- [Getting Started Guide](../guides/GETTING_STARTED.md) — general little-loops orientation (host-agnostic)
