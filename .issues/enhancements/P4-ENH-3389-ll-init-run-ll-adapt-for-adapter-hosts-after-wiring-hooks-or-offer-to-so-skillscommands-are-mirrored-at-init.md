---
id: ENH-3389
type: ENH
title: 'll-init: run ll-adapt for adapter hosts after wiring hooks (or offer to) so
  skills/commands are mirrored at init'
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-04'
captured_at: '2026-09-04T21:03:39Z'
---

# ENH-3389: ll-init: run ll-adapt for adapter hosts after wiring hooks (or offer to) so skills/commands are mirrored at init

## Summary

`ll-init --hosts codex|gemini|kimi-code|qwen` writes hook adapters but never mirrors skills/commands/agents; the user must run `ll-adapt --host <h> --apply` by hand (ll-init now prints it in the next-steps footer). Consider running it automatically (or a wizard prompt) after `_dispatch_host_adapters` in `scripts/little_loops/init/cli.py`, with `--dry-run` parity and a `--no-adapt` escape hatch; reuse `little_loops.cli.adapt` rather than shelling out.


## Current Behavior

`ll-init --hosts codex|gemini|kimi-code|qwen` calls `_dispatch_host_adapters` (`scripts/little_loops/init/cli.py:166`), which writes each host's hook adapter file but never mirrors skills, commands, or agents for that host. The user must separately run `ll-adapt --host <h> --apply` by hand; `ll-init` only prints that command in its next-steps footer, so a first-time init leaves adapter hosts with working hooks but no mirrored `/ll:*` skill/command surface until the user notices and runs the follow-up command.

## Expected Behavior

After `_dispatch_host_adapters` installs hook adapters for a host that also needs skill/command mirroring, `ll-init` runs `ll-adapt --host <h> --apply` for that host automatically (or, in interactive/wizard mode, prompts once to confirm) — respecting a `--dry-run` init run by only previewing the adapt plan, and a new `--no-adapt` escape hatch that restores today's manual-follow-up behavior. It reuses `little_loops.cli.adapt`'s emitter pipeline (`process_skills`, `process_commands`, `process_agents`) directly rather than shelling out to the `ll-adapt` binary.

## Scope Boundaries

- **In scope**: auto-invoking (or prompting for) `ll-adapt`-equivalent mirroring for the same adapter hosts `_dispatch_host_adapters` already handles (codex, gemini, kimi-code, qwen); `--dry-run` parity; a `--no-adapt` opt-out.
- **Out of scope**: adding new adapter hosts beyond the four `_dispatch_host_adapters` already supports; changing `ll-adapt`'s own CLI surface or emitter behavior; MCP config mirroring (`process_mcp_config`) beyond whatever `ll-adapt --apply` already does for a host.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-05 — based on codebase analysis:_

Findings below cover the call sites, existing conventions, and test structure relevant to wiring skill/command mirroring into `_dispatch_host_adapters`.

### Files to Modify

- `scripts/little_loops/init/cli.py` — `_dispatch_host_adapters` (line 166) needs a call to a new mirroring helper after each adapter host's hook adapter install; a new `--no-adapt`-style CLI flag needs registering near the existing `--dry-run` (line ~1238) and `--hosts` (line ~1252) arguments
- `scripts/little_loops/init/tui.py` — the wizard's `_apply_config` (line ~1185-1284) is a fourth, structurally separate call site of `_dispatch_host_adapters` with no `dry_run` parameter at all (writes are unconditional; dry-run preview happens earlier in the wizard flow) — any new mirroring call or confirm prompt needs to account for this divergence

### Dependent Files (Callers/Importers)

- `scripts/little_loops/init/cli.py:363` (`_dispatch_host_upgrade`, force-regenerate only, no interactivity), `:920` (`_run_yes`, headless `--yes` flow), `:1159` (`_run_apply`, plan-apply flow) — three call sites of `_dispatch_host_adapters`, all threading the same `force`/`dry_run` flags straight from parsed CLI args
- `scripts/little_loops/init/tui.py:1284` (`_apply_config`) — the fourth call site (see Files to Modify above)

### Conventions in Force

- This codebase has two disagreeing precedents for gating an auto-run follow-up action, and neither uses a bare `--no-X` boolean: (a) a mode-choice flag with a "commands"-only escape hatch (`--code-graph {auto,install,index,commands,skip}`, `init/cli.py:1343`, dispatched via `resolve_code_graph_action()` in `init/codegraph.py:141`), or (b) an unconditional state-check with no flag at all (the `claude-code` plugin auto-install added for FEAT-3372, `init/cli.py:272-282`, gated only on host selection + `not dry_run` + `not plugin_installed(binary)`). The choice between a `--no-adapt` boolean and a `--code-graph`-style mode flag is not settled by existing convention.
- Interactive confirmation has no reusable helper — every wizard site calls `questionary.confirm(...).ask()` directly and treats a `None` return (Ctrl-C) as an abort propagated up the call chain, not as `False` (`init/tui.py:174-182` for the kimi-code user-global-write confirm, `:1002` for the final apply confirm).
- Every existing consumer of `resolve_emitter`/`process_skills`/`process_commands`/`process_agents` (`little_loops/adapters/core.py`) is an in-process import and direct call — `cli/adapt.py` (`main_adapt()`, the full pipeline at lines 87,109,115,132,141), `cli/adapt_skills_for_codex.py`, `cli/adapt_agents_for_codex.py`. No code anywhere shells out to `ll-adapt` as a subprocess; `init/cli.py`'s only existing reference to `ll-adapt` is the printed next-steps string (`init/cli.py:578`).
- `--dry-run` is threaded as a plain keyword uniformly into every writer/dispatcher call (`init/core.py`); each function internally branches on `dry_run` rather than the call site pre-checking it — a new mirroring call should follow this same shape rather than special-casing itself.
- `process_agents` and `process_mcp_config` both need a per-host `output_dir`/`config_dir`, resolved today via `HOST_CAPABILITIES.get(args.host)` (`little_loops/adapters/capabilities.py`, imported in `cli/adapt.py:12`) — a direct-call `_mirror_host_artifacts` helper needs this same resolution, not just `resolve_emitter`/`process_skills`/`process_commands`.

### Tests

- `scripts/tests/test_init_core.py::TestHostDispatch` (line 3575) and `::TestClaudeCodeAutoInstall` (line 3759, docstring "FEAT-3372: claude-code auto-installs ll@little-loops when absent") — existing per-host/per-branch test structure to extend with a new auto-adapt test class; `TestClaudeCodeAutoInstall` patches three seams (`_subprocess.run`, `resolve_host`, `plugin_installed`) as the closest structural precedent for testing a new auto-run branch
- `scripts/tests/test_init_audit_fixes.py::test_yes_completion_and_next_steps` (line 823), `::test_existing_index_summary_and_next_steps` (line 1116) — assert the `next_steps()` footer's exact content including the `ll-adapt --host <h> --apply` line; would need updating if that line's presence becomes conditional
- `scripts/tests/test_init_tui.py:42` — comment documenting today's fact that `_apply_config()` calls `_dispatch_host_adapters()` with no `dry_run` kwarg

### Documentation

- `docs/reference/CLI.md:78` — next-steps footer description referencing `ll-adapt` for adapter hosts in the `ll-init` wizard step list
- `docs/reference/CLI.md:5079-5106` — full `ll-adapt` flag docs (unaffected unless the CLI surface itself changes, which is out of scope per this issue's Scope Boundaries)

## Program Design

### Signatures

- `_dispatch_host_adapters(hosts: list[str], project_root: Path, plugin_root: Path, force: bool = False, dry_run: bool = False) -> None` (`scripts/little_loops/init/cli.py:166`) — call site to extend
- `resolve_emitter(host: str)`, `process_skills(...)`, `process_commands(...)`, `process_agents(...)` (`little_loops.adapters.core`, imported in `scripts/little_loops/cli/adapt.py:13-20`) — reused directly instead of invoking `main_adapt()`/shelling out
- new: `_mirror_host_artifacts(host: str, project_root: Path, plugin_root: Path, *, apply: bool) -> None` in `scripts/little_loops/init/cli.py`, called from `_dispatch_host_adapters` after a host's hook adapter is installed

### Call Path

`_dispatch_host_adapters` -> `_mirror_host_artifacts` -> `resolve_emitter(host)` -> `process_skills` / `process_commands` / `process_agents`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-05 — based on codebase analysis:_

`_dispatch_host_adapters`'s current per-host body (`scripts/little_loops/init/cli.py:166-282`) confirms it has no call to any of `resolve_emitter`/`process_skills`/`process_commands`/`process_agents` anywhere — its only imports are `error`/`info`/`warning` (`cli/output`), the four `install_*_adapter` writers, `kimi_config_path`, `resolve_host`/`HostNotConfigured`, and `plugin_installed`. `main_adapt()` (`cli/adapt.py:32-149`) is the full reference sequence a new `_mirror_host_artifacts` helper must replicate: `resolve_emitter(host)` (line 87) → `process_skills(emitter, skills_dir, apply, quiet)` if `skills_dir.exists()` (line 109) → `process_commands(emitter, commands_dir, skills_dir, apply, quiet)` unconditionally (line 115, note `skills_dir` doubles as the *output* dir for synthesized command wrappers) → resolve `config_dir` from `HOST_CAPABILITIES.get(host)` (falls back to `.codex`) → `process_agents(emitter, agents_dir, plugin_root/config_dir/"agents", apply, quiet, only)` if `agents_dir.exists()` (line 132) → `process_mcp_config(emitter, plugin_root/config_dir, apply, quiet)` unconditionally (line 141, explicitly out of this issue's scope per Scope Boundaries but still exercised by the reference call sequence). `apply = args.apply and not args.dry_run` (i.e. dry-run wins if both set) is the exact precedence a new call site should mirror.

## Impact

- **Priority**: P4 - quality-of-life gap with a documented manual workaround (`ll-adapt --host <h> --apply`, already printed in the next-steps footer); no functional breakage
- **Effort**: Small - one new call site reusing `little_loops.adapters.core`'s existing emitter functions; no new adapter logic
- **Risk**: Low - additive to `_dispatch_host_adapters`; `--no-adapt` preserves current behavior for anyone who wants to defer mirroring
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-04 | Priority: P4


## Session Log
- `/ll:refine-issue` - 2026-09-05T04:32:50 - `251307a7-40ea-42f4-beb3-43e6b4de6744.jsonl`
- `/ll:format-issue` - 2026-09-05T04:22:41 - `adb409c3-bb29-46e0-a080-e89ad1cec8e0.jsonl`
