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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/adapt.py` — `main_adapt()`'s reference pipeline resolves output paths via `plugin_root = _find_plugin_root()` (`scripts/little_loops/skill_expander.py:25`, package-checkout-scoped), not `project_root`; a new `_mirror_host_artifacts` helper must NOT reuse `main_adapt`'s path resolution as-is, or a consuming project's `ll-init` run would mirror skills/commands into this little-loops checkout instead of that project. The proposed signature already threads both `project_root` and `plugin_root` as separate params, so this needs explicit handling, not an assumption that `resolve_emitter`/`process_skills`/`process_commands`/`process_agents` default to the right root [Agent 2 finding — critical]
- `scripts/tests/test_init_core.py` — 21 existing direct calls to `_dispatch_host_adapters(...)` (~lines 3688-3971) use today's 5-parameter signature; a signature change (vs. adding a sibling call after it) breaks all of them [Agent 2 finding]
- `scripts/tests/test_init_tui.py` — `_default_plugin_installed` fixture docstring (lines 39-45) documents that `_apply_config()` calls `_dispatch_host_adapters()` with **no `dry_run` kwarg at all**; a new mirror call from that site can't thread dry-run the way the three headless call sites do [Agent 2 finding]

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` (line 468) and its `_host_output_dirs()` helper (line 453) — closest existing precedent for calling `resolve_emitter`/`process_skills`/`process_commands`/`process_agents` directly (mirrors `main_adapt()`'s own path derivation); model a new `_mirror_host_artifacts` unit test on this shape [Agent 3 finding]
- `scripts/tests/test_init_core.py::TestClaudeCodeAutoInstall` (line 3759) — closest precedent for testing a new auto-run branch gated on state; patches `_subprocess.run`/`resolve_host`/`plugin_installed` — a new mirroring test should patch `process_skills`/`process_commands`/`process_agents`/`resolve_emitter` the same way [Agent 3 finding]
- `scripts/tests/test_init_audit_fixes.py::TestHeadlessSettingsFlags` (line 631) / `::TestCodeGraphHeadless` (line 1068) — template for testing a `--no-adapt` opt-out flag via real headless CLI invocation + filesystem-effect assertions [Agent 3 finding]
- `scripts/tests/test_init_tui.py::TestHostSelection::test_kimi_selection_requires_confirm` (line 854) — template for testing a new interactive "run ll-adapt now?" confirm prompt via the shared `_wire_q()` mock-dispatch helper [Agent 3 finding]
- `scripts/tests/test_init_tui.py::TestApplyConfigInstallSource` (line 1352) — the only existing test calling `_apply_config()` directly; template for asserting the new mirroring call fires from that TUI call site [Agent 3 finding]
- `scripts/tests/test_init_audit_fixes.py::test_yes_completion_and_next_steps` (line 823) — only exercises `--hosts claude-code`, a host absent from `_ADAPTER_MIRROR_HOSTS`, so the `ll-adapt --host <h> --apply` footer line never fires in this test and has **no existing verbatim assertion anywhere**; a new test is needed for that line's conditional presence/absence once auto-mirroring lands [Agent 3 finding]

### Documentation

- `docs/reference/CLI.md:78` — next-steps footer description referencing `ll-adapt` for adapter hosts in the `ll-init` wizard step list
- `docs/reference/CLI.md:5079-5106` — full `ll-adapt` flag docs (unaffected unless the CLI surface itself changes, which is out of scope per this issue's Scope Boundaries)

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` / `scripts/README.md` (mirrored pair, lines 77, 79) — instruct running `ll-adapt --host <host> --apply` as a separate manual step for Codex/Kimi Code; edit `README.md` then `cp -f README.md scripts/README.md` to keep the pair in sync [Agent 2 finding]
- `docs/guides/GETTING_STARTED.md` ("What gets created" section, line 87) — silent on skill/command/agent mirror artifacts, lists only hook-adapter files [Agent 2 finding]
- `docs/kimi/getting-started.md` (lines 60-63, 129) and `docs/qwen/getting-started.md` (lines 60-63, 109, 138) — instruct a required manual `ll-adapt --host <host> --apply` step, including a troubleshooting row ("Skills not appearing" → re-run ll-adapt) [Agent 2 finding]
- `docs/codex/getting-started.md` (line 65) and `docs/codex/README.md` (line 57) — same manual-step framing [Agent 2 finding]
- `skills/init/SKILL.md` (§5 "Handle `--upgrade`" ~lines 125-136, §7 "Report" ~lines 154-158) — describes only hook-adapter refresh/reporting today, not mirroring [Agent 2 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Resolve the `plugin_root` vs. `project_root` mismatch before wiring `_mirror_host_artifacts`: `main_adapt()`'s reference pipeline resolves output paths via `_find_plugin_root()` (package-checkout-scoped), while `_dispatch_host_adapters`'s own writes are `project_root`-scoped — a naive reuse mirrors into this checkout instead of the initialized project
- Update `README.md`/`scripts/README.md`, `docs/guides/GETTING_STARTED.md`, `docs/kimi/getting-started.md`, `docs/qwen/getting-started.md`, `docs/codex/getting-started.md`, `docs/codex/README.md`, and `skills/init/SKILL.md` to reflect automatic (or prompted) mirroring instead of a required manual follow-up step
- Add a test asserting the `ll-adapt --host <h> --apply` next-steps footer line's conditional presence/absence — currently unasserted verbatim anywhere

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
- `/ll:wire-issue` - 2026-09-05T04:57:35 - `7ad2c895-8f68-4859-96fb-41e7c667e5b1.jsonl`
- `/ll:refine-issue` - 2026-09-05T04:32:50 - `251307a7-40ea-42f4-beb3-43e6b4de6744.jsonl`
- `/ll:format-issue` - 2026-09-05T04:22:41 - `adb409c3-bb29-46e0-a080-e89ad1cec8e0.jsonl`
