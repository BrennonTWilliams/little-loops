# Getting Started with little-loops on Codex CLI

This guide walks through installing and verifying little-loops on a project where you use [OpenAI Codex CLI](https://github.com/openai/codex).

---

## Prerequisites

1. **Codex CLI** — `codex` binary on `PATH`. Verify with `codex --version`.
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
/ll:init --hosts codex
```

This writes `.codex/hooks.json` into your project with the `{{LL_PLUGIN_ROOT}}` variable substituted to the absolute path of the installed little-loops plugin. It also writes `.ll/ll-config.json` if one does not already exist.

**Auto-detection**: `--hosts codex` is set automatically when the `codex` binary is on `PATH` or a `.codex/` directory already exists in the project. You can also preview what would be written without touching any files:

```bash
/ll:init --hosts codex --dry-run
```

---

## Trust prompt

The first time you start `codex` after install, it shows a hook-trust dialog for every new hook entry in `.codex/hooks.json`. little-loops registers four hooks: `SessionStart`, `PreCompact`, `UserPromptSubmit`, and `PostToolUse`.

Each hook has one of four statuses:

| Status | Meaning |
| --- | --- |
| `managed` | Reserved for Codex-internal hooks. Always runs. |
| `trusted` | Content hash matches `~/.codex/config.toml`. Runs. |
| `modified` | Hash changed (e.g., path or timeout changed). Codex prompts re-trust on next startup. |
| `untrusted` | No saved hash. Codex **silently skips** the hook and shows a startup dialog. |

**Choose "Trust All and Continue"** to let all four hooks run. If you choose "Continue Without Trusting", hooks will be skipped silently with no error — little-loops features will not activate.

### Trust key format

The trust hash is keyed by command string (not script body), stored in the user-level `~/.codex/config.toml`:

```
file:<project>/.codex/hooks.json:session_start:0:0
file:<project>/.codex/hooks.json:pre_compact:0:0
file:<project>/.codex/hooks.json:user_prompt_submit:0:0
file:<project>/.codex/hooks.json:post_tool_use:0:0
```

Because the hash covers the **command string** in `hooks.json` (not the script body), updates to the Python package that only change `hooks/adapters/codex/*.sh` internals do **not** invalidate your trust. Only changes to `.codex/hooks.json` itself (paths, timeouts, matcher) prompt re-trust.

---

## Config file

Codex resolves configuration by probing `.codex/ll-config.json` **before** the default `.ll/ll-config.json`. This is the only state path redirected by the Codex host — all other directories (`.issues/`, `.loops/`, etc.) use the project-root defaults regardless of host.

To create a Codex-specific config:

```bash
cp .ll/ll-config.json .codex/ll-config.json
# Edit .codex/ll-config.json as needed
```

---

## Skill and command discovery

Run `ll-adapt-skills-for-codex --apply` once after install to bridge all little-loops skills and commands into `~/.codex/skills/`:

```bash
ll-adapt-skills-for-codex --apply
```

After this step, typing `/ll:` in the Codex TUI will show the full list of available commands (e.g., `/ll:manage-issue`, `/ll:scan-codebase`, `/ll:prioritize-issues`).

Re-run this command after upgrading little-loops to pick up any new skills or commands.

To also enable ll subagent personas in the Codex TUI, run the companion command:

```bash
ll-adapt-agents-for-codex --apply
```

This writes `.codex/agents/*.toml` files so you can select ll agents via `--agent <name>` in Codex (e.g., `--agent codebase-analyzer`). Re-run after adding new agents to `agents/`.

---

## First-run verification

Start a Codex session and confirm hooks are active:

1. Open a new session — Codex should show the trust dialog (if not already trusted) or start cleanly.
2. Run any command, e.g., `/ll:help`. You should see the command list.
3. To verify the hook adapter end-to-end from the shell (outside a session):

   ```bash
   LL_HOOK_HOST=codex echo '{"session_id":"test","cwd":"'$(pwd)'","model":"","source":"startup"}' \
     | bash hooks/adapters/codex/session-start.sh
   ```

   A zero exit code indicates the adapter and Python dispatcher are both reachable. The full integration test in `scripts/tests/test_codex_adapter.py` exercises all four adapter scripts and is run by `python -m pytest scripts/tests/test_codex_adapter.py -v`.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Hooks silently do nothing | Open a new session; choose "Trust All and Continue" in the trust dialog |
| `codex: command not found` during init | Ensure the `codex` binary is on `PATH`: `which codex` |
| Adapter scripts not executable | `chmod +x hooks/adapters/codex/*.sh` |
| `LL_HOOK_HOST=codex` not recognized | Upgrade to the latest little-loops version: `pip install --upgrade little-loops` |
| Skills not appearing in Codex TUI | Re-run `ll-adapt-skills-for-codex --apply` |

For more issues see [Troubleshooting](../development/TROUBLESHOOTING.md) and the "Hook Debugging" section.

---

## Next steps

- [Usage](usage.md) — running `ll-auto`/`ll-parallel` under Codex, invoking skills, opt-in `pre_tool_use`, limitations
- [Host Compatibility Matrix](../reference/HOST_COMPATIBILITY.md) — full per-host feature matrix
- [Getting Started Guide](../guides/GETTING_STARTED.md) — general little-loops orientation (host-agnostic)
