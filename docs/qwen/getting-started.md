# Getting Started with little-loops on Qwen Code

This guide walks through installing and verifying little-loops on a project where you use [Qwen Code](https://qwenlm.github.io/qwen-code-docs/).

---

## Prerequisites

1. **Qwen Code** — `qwen` binary on `PATH`, logged in. Verify with `qwen --version` (the adapter is live-verified on **0.21.6**; pin your version — the 0.x upstream moves fast).
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
ll-init --hosts qwen
```

This installs the hook adapter as **managed, `ll:`-prefixed hook entries** merged into the **project's** `.qwen/settings.json` — a structured JSON merge that never touches any other key or third-party hook entries (ARCHITECTURE-046 Option A, first implementation; project scope was live-verified to fire under `qwen -p` headless). Entries are stamped with the package gen-version (`ll-gen:<version>` in their description) so `ll-init --upgrade` can regenerate them. `ll-init` also writes `.ll/ll-config.json` and appends the little-loops command block to `AGENTS.md` (Qwen reads `AGENTS.md` natively).

**Auto-detection**: `--hosts qwen` is set automatically when the `qwen` binary is on `PATH` or a `.qwen/` directory already exists in the project (probed last, so installing the qwen binary never changes resolution for existing users). Preview without touching files:

```bash
ll-init --hosts qwen --dry-run
```

Hooks take effect in **new** qwen sessions — interactive and `qwen -p` headless alike; there is no trust dialog.

---

## Config file

When `LL_HOOK_HOST=qwen` (set by the adapter) or `LL_STATE_DIR=.qwen` is in the environment, configuration is probed at `.qwen/ll-config.json` **before** the default `.ll/ll-config.json` (ENH-3157). This is the only state path redirected by the qwen host — all other directories (`.issues/`, `.loops/`, etc.) use the project-root defaults regardless of host.

To create a qwen-specific config:

```bash
cp .ll/ll-config.json .qwen/ll-config.json
# Edit .qwen/ll-config.json as needed
```

---

## Skill and command discovery

Run `ll-adapt --host qwen --apply` once after install to bridge all little-loops skills, commands, and agent personas into qwen:

```bash
ll-adapt --host qwen --apply
```

This writes:

- **Skills** → `.qwen/skills/<name>/SKILL.md` — Qwen's native skills format, near-1:1 (Claude-only frontmatter keys like `allowed-tools` are tolerated — live-verified); `name:` is injected when absent.
- **Commands** → `.qwen/commands/ll/<stem>.md` — Qwen's subdirectory namespacing maps these to `/ll:<stem>` slash commands (live-verified). True command emission: no skill bridging needed (better than Codex/Kimi). `$ARGUMENTS` is rewritten to Qwen's `{{args}}` placeholder.
- **Agents** → `.qwen/agents/<name>.md` — Qwen documents explicit Claude Code 2.1.168 agent-frontmatter compatibility, and all nine ll agents load verbatim; real subagent spawning, no degraded mode.

Re-run this command after upgrading little-loops or adding new skills/agents to pick up any changes.

### Extension install (optional)

Two packaging routes exist for interactive use (headless automation never depends on either — the managed `.qwen/settings.json` block covers it):

1. **Native extension** (recommended): the repo root carries `qwen-extension.json` (plugin id `ll`) with inline hooks using Qwen-native matchers. For development:

   ```bash
   qwen extensions link .
   ```

2. **Marketplace zero-artifact path**: Qwen Code installs Claude Code marketplace plugins natively:

   ```bash
   qwen extensions install BrennonTWilliams/little-loops:ll
   ```

   ⚠️ Known conversion caveats (FEAT-3155 spike): `hooks/hooks.json` is copied **verbatim** — no matcher translation, so tool-specific guard hooks (Claude tool names `Write|Edit`/`Bash`) never match Qwen runtime ids, and commands flatten to `ll-<stem>` without the `/ll:` colon namespace. `*`-matcher events and agents work. Prefer the native manifest.

---

## Automation

Orchestration CLIs (`ll-auto`, `ll-parallel`, `ll-action`, `ll-harness`, `ll-loop`, `ll-sprint`) route through the host runner abstraction. Select qwen explicitly with:

```bash
LL_HOST_CLI=qwen ll-auto
```

or set `orchestration.host_cli: "qwen"` in `ll-config.json`. Auto-detection also works when `qwen` is on `PATH`. See [Automation](automation.md) for runner flags, structured output, and current limitations.

---

## First-run verification

1. Start a new qwen session — the managed hooks activate silently (no trust prompt).
2. Run an adapted command, e.g. `/ll:help` (requires `ll-adapt --host qwen --apply`).
3. Sanity-check the full install surface from the shell:

   ```bash
   ll-doctor --full
   ```

   The host-capability section should report qwen with streaming / permission skip / json_schema / structured_output `full`, and the verifier family should print OK lines.
4. To exercise the hook adapter end-to-end from the shell (outside a session):

   ```bash
   LL_HOOK_HOST=qwen echo '{"session_id":"test","cwd":"'$(pwd)'","hook_event_name":"SessionStart","source":"startup"}' \
     | bash scripts/little_loops/hooks/adapters/qwen/session-start.sh
   ```

   A zero exit code indicates the adapter and Python dispatcher are both reachable.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Hooks do nothing | Start a **new** qwen session — hooks load at session start |
| `qwen: command not found` during init | Ensure the `qwen` binary is on `PATH`: `which qwen` |
| Adapter scripts not executable | `chmod +x scripts/little_loops/hooks/adapters/qwen/*.sh` |
| `LL_HOOK_HOST=qwen` not recognized | Upgrade to the latest little-loops version: `pip install --upgrade little-loops` |
| Stale managed hooks after a package upgrade | Run `ll-init --upgrade` — it re-merges the managed entries and re-stamps the gen-version |
| Third-party hooks in `.qwen/settings.json` disappeared | They cannot — the writer only removes entries whose names start with `ll:`; report it as a bug if you see otherwise |
| Skills/commands not appearing in qwen | Re-run `ll-adapt --host qwen --apply` |
| SessionEnd cleanup skipped in headless runs | Expected — `SessionEnd` does not fire under `qwen -p`; headless cleanup rides the `Stop` hook (see [Hook Events](hook-events.md)) |

For more issues see [Troubleshooting](../development/TROUBLESHOOTING.md).

---

## Next steps

- [Hook Events](hook-events.md) — event → intent mapping, payload shape, the headless SessionEnd gap
- [Automation](automation.md) — orchestration CLIs under qwen, runner flags, structured output, current limitations
- [Host Compatibility Matrix](../reference/HOST_COMPATIBILITY.md) — full per-host feature matrix
- [Getting Started Guide](../guides/GETTING_STARTED.md) — general little-loops orientation (host-agnostic)
