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

`ll-init --hosts gemini|kimi-code|qwen` writes hook adapters but never places the mirrored skills/commands/agents where those hosts scan for them (`<project>/.gemini/`, `.kimi-code/`, `.qwen/`); the user is told to run `ll-adapt --host <h> --apply` by hand, which does not help either (see Review Findings: `ll-adapt` writes into the *plugin root*, never the project). Have `_dispatch_host_adapters` in `scripts/little_loops/init/cli.py` **copy the pre-built, git-tracked mirrors** from `plugin_root/.<host>/{skills,commands,agents}` into `project_root/.<host>/` after installing the host's hook adapter, with `--dry-run` parity, and have `_dispatch_host_upgrade` refresh them on `--upgrade`.


## Current Behavior

`ll-init --hosts codex|gemini|kimi-code|qwen` calls `_dispatch_host_adapters` (`scripts/little_loops/init/cli.py:166`), which writes each host's hook adapter file but never mirrors skills, commands, or agents for that host. The user must separately run `ll-adapt --host <h> --apply` by hand; `ll-init` only prints that command in its next-steps footer, so a first-time init leaves adapter hosts with working hooks but no mirrored `/ll:*` skill/command surface until the user notices and runs the follow-up command.

## Expected Behavior

After `_dispatch_host_adapters` installs the hook adapter for gemini, kimi-code, or qwen, `ll-init` copies that host's pre-built mirror tree — `plugin_root/.<host>/skills/`, `plugin_root/.<host>/commands/` (gemini, qwen), and `plugin_root/.<host>/agents/` — into `project_root/.<host>/`, so the host's native project-local scan dir (`<cwd>/.gemini/skills/`, `.kimi-code/skills/`, `.qwen/commands/ll/`, ...) is populated on first init with no manual follow-up. The copy runs unconditionally for those hosts (the FEAT-3372 claude-code auto-install precedent: gated only on host selection and `not dry_run`, no opt-out flag), honours `--dry-run` by printing the planned copy, and is refreshed by `_dispatch_host_upgrade` on `ll-init --upgrade`. It does **not** re-run the `ll-adapt` emitter pipeline: the mirrors are already generated and git-tracked in the plugin root and kept current by the mirror gate. The `ll-adapt --host <h> --apply` next-steps footer line for these hosts is removed (it is a source-repo regeneration command, not a consumer step).

## Scope Boundaries

- **In scope**: copying pre-built mirrors into the project for gemini, kimi-code, and qwen from all four `_dispatch_host_adapters` call sites (`_run_yes`, `_run_apply`, `_dispatch_host_upgrade`, TUI `_apply_config`); `--dry-run` parity; a `--force` overwrite semantics matching the hook-adapter writers; footer + docs updates.
- **Out of scope**: codex (its skills surface is `~/.codex/skills/` user-global and its emitter writes sidecars in place into `skills/`; a project-local copy does not help it — keep the existing footer hint for codex only, or file a separate issue); changing `ll-adapt`'s CLI surface or emitter behavior (e.g. adding an output-root parameter); MCP config; the wizard confirm prompt originally floated (dropped — the TUI already confirms the apply step, and the codebase precedent for follow-up actions is stateless auto-run); making the `pypi` install path work end-to-end (see Review Findings item 4 — needs the wheel to ship `.<host>/` mirrors; track separately).

## Review Findings

_Added by pre-implementation review — 2026-09-05:_

1. **The original Program Design could not work.** It proposed calling `resolve_emitter`/`process_skills`/`process_commands` with `project_root` threaded in. The emitters have no output-root parameter for skills or commands: `_emit_mirrored_skill` (`scripts/little_loops/adapters/core.py:381`) derives the output root from `skill_path.parent.parent.parent`, and gemini/kimi/qwen `emit_command` derive it from `cmd_path.parent.parent` (`adapters/gemini.py:109`, `kimi.py:91`, `qwen.py:93`). Output always lands beside the *source* `skills/` and `commands/` dirs, i.e. in the plugin root. Only `process_agents` and `process_mcp_config` take an `output_dir`. Fixing that is an emitter change, which Scope Boundaries exclude.
2. **The mirrors are already git-tracked in this repo.** `git ls-files` shows `.gemini/{agents,commands,skills}`, `.kimi-code/{agents,skills}`, `.qwen/{agents,commands,skills}`, and `.codex/agents` (~250 files), kept fresh by `scripts/tests/test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale`. In a `local-editable` consumer, re-running `ll-adapt` from `ll-init` is a no-op that touches this checkout, not the consumer. In a `pypi` consumer, `_find_plugin_root()` falls back to `site-packages/..`, where `commands/` does not exist, so nothing useful happens either. Neither case populates `<consumer>/.gemini/skills/`, which is where the host scans (`docs/reference/HOST_COMPATIBILITY.md:214`).
3. **Correct model: copy, don't adapt.** ll-init should copy (or link) the pre-built mirror trees from `plugin_root/.<host>/` into `project_root/.<host>/`. That is project-root-scoped by construction and is the same shape as the `install_*_adapter` writers (template in package → file in project).
4. **pypi path is unresolved.** The wheel ships `little_loops/skills/` (hatch_build.py, BUG-3177) but not `commands/`, `agents/`, or any `.<host>/` mirror. For pypi installs the copy source does not exist. Options: ship the `.<host>/` mirrors in the wheel via the same hatch hook, or generate them at init time from the packaged `little_loops/skills` into a temp dir (needs the emitter output-root change). Warn-and-skip when the source dir is absent; track the wheel change as a follow-up.
5. **Codex is different** (user-global `~/.codex/skills/`, in-place sidecars). Dropped from scope; see Scope Boundaries.
6. **`_dispatch_host_upgrade` was missing** from the original touchpoints. It force-regenerates hook adapters after a package upgrade and is the natural place to refresh mirrors too.
7. **Docs currently overstate the manual step.** `docs/kimi/getting-started.md:60-63` and `docs/qwen/getting-started.md:60-63` say "Skills → `.kimi-code/skills/`" as if run from the consumer; today that is only true when run from a little-loops checkout. Correct the wording while updating those pages.
8. `learning_tests_required: questionary` removed — no new prompt is added.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-05 — based on codebase analysis:_

Findings below cover the call sites, existing conventions, and test structure relevant to wiring skill/command mirroring into `_dispatch_host_adapters`.

_Added by `/ll:refine-issue` — 2026-09-05 — based on codebase analysis:_

- `_ADAPTER_MIRROR_HOSTS` (`scripts/little_loops/init/cli.py:542-547`) — existing dict mapping `codex`/`gemini`/`kimi-code`/`qwen` to display labels (e.g. `"Codex CLI"`); consumed today only by `next_steps()` to decide which hosts get the `ll-adapt --host {host} --apply` footer hint. This is the existing host-scoping list for "which hosts need mirroring" and is a natural registry to reuse when gating the new auto-mirror call, rather than re-deriving the host set.
- `next_steps()` (`scripts/little_loops/init/cli.py:550-581`) and `_print_next_steps()` (`:584`) — names the function that currently builds the `ll-adapt --host {host} --apply` hint line (previously only the raw line 578 was cited); shared by both the headless completion footer (`_run_yes`/`_run_apply`) and the wizard footer (`init/tui.py` renders the same hints, per its own docstring).
- Per-host insertion point for a new mirroring call inside `_dispatch_host_adapters` (`scripts/little_loops/init/cli.py:166-309`): codex (186-200), kimi-code (201-222), qwen (223-237), gemini (238-252) each have their own `elif` branch ending in an `elif installed and not dry_run:` success guard — the natural attachment point is inside/after that same guard, per host. `opencode`/`pi`/`omp` (`_ADAPTER_PENDING_HOSTS`, line 74) print an info line only and never call an adapter writer — there is no successful-install signal to attach a mirroring call to for these three. `claude-code` (262-309) is excluded: `HOST_CAPABILITIES["claude-code"]` has `config_dir="."`, `agents=False`, `commands=False` — that host is served natively by the plugin marketplace install flow, not generated skill/command/agent files.
- `scripts/little_loops/init/writers.py:272,276` — docstrings on the Codex skill/agent frontmatter and TOML writers describe their output as "alias for ll-adapt --host codex", an additional (currently unlisted) documentation-adjacent reference to the manual workaround this issue automates.

Stale anchor corrections (content still present, line numbers have shifted since the last refine pass):
- `docs/codex/getting-started.md` — issue/prior pass cited line 65; the `ll-adapt --host codex --apply` instruction is now at lines 90 and 93, with the troubleshooting row at 129.
- `docs/codex/README.md` — issue/prior pass cited line 57; the `ll-adapt --host codex --apply` sentence is now at line 32 (the `### Skill and command discovery` heading it sits under is at line 30).
- `docs/guides/GETTING_STARTED.md` — the "What gets created" list (silent on skill/command/agent mirroring, listing only hook-adapter files) has moved from ~line 87 to line 75.

_Added by `/ll:refine-issue` — 2026-09-05 — based on codebase analysis:_

Additional conventions-in-force findings (pattern-finder):
- Closest existing precedent for a plain `--no-adapt`-style boolean: `--no-claude-md` (`scripts/little_loops/init/cli.py` ~1333-1341) is a genuine standalone opt-out boolean with no companion mode flag. By contrast, `--no-settings` in this same file is documented as an *alias* for `--settings skip` inside a `mutually_exclusive_group`, not a standalone opt-out — so this codebase has both shapes, and `--no-claude-md` is the nearer match to what this issue proposes.
- No reusable `confirm()`/`ask_confirm()` helper exists anywhere in production code — every interactive confirm in `init/tui.py` calls `questionary.confirm(...).ask()` inline. `None` (Ctrl-C) is checked uniformly (`if x is None:`) immediately after `.ask()`, but the returned value differs by call site: mid-wizard confirms return `False` to abort that step (e.g. `tui.py:541`, `:600-601`), while the final apply-confirm returns exit code `130` directly (`tui.py:1002-1004`).
- `scripts/little_loops/init/core.py` has zero `dry_run` parameters anywhere (repo-wide grep of that file returns no matches) — `dry_run` threading happens only in `cli.py`, `writers.py`, and `codegraph.py`, each function individually branching on its own `dry_run` flag; there is no shared dispatcher-level short-circuit a new mirroring call could hook into generically.
- `scripts/tests/test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` and `::test_gate_detects_present_but_drifted_codex_command_bridge` (lines 466-537) import and call `resolve_emitter`/`process_skills`/`process_commands`/`process_agents` directly, in-process — no test anywhere in the repo invokes the `ll-adapt` CLI via subprocess or `sys.argv` patching. This direct-call shape is the established pattern for exercising adapter machinery in tests.

### Files to Modify

- `scripts/little_loops/init/cli.py` — `_dispatch_host_adapters` (line 166) needs a call to a new mirroring helper after each adapter host's hook adapter install; a new `--no-adapt`-style CLI flag needs registering near the existing `--dry-run` (line ~1238) and `--hosts` (line ~1252) arguments
- `scripts/little_loops/init/tui.py` — the wizard's `_apply_config` (line ~1185-1284) is a fourth, structurally separate call site of `_dispatch_host_adapters` with no `dry_run` parameter at all (writes are unconditional; dry-run preview happens earlier in the wizard flow) — any new mirroring call or confirm prompt needs to account for this divergence

_Wiring pass added by `/ll:wire-issue` (round 2, post-redesign):_
- `scripts/little_loops/init/writers.py` — the current Program Design places `install_host_mirrors()` here, beside `install_gemini_adapter`/`install_kimi_adapter`/`install_qwen_adapter`, but this file is not yet listed as a Files to Modify target. Confirmed the file already imports `shutil` (line 7) but not `HOST_CAPABILITIES` (`little_loops.adapters.capabilities`) — that import is new. [Agent 2 finding]

### Dependent Files (Callers/Importers)

- `scripts/little_loops/init/cli.py:363` (`_dispatch_host_upgrade`, force-regenerate only, no interactivity), `:920` (`_run_yes`, headless `--yes` flow), `:1159` (`_run_apply`, plan-apply flow) — three call sites of `_dispatch_host_adapters`, all threading the same `force`/`dry_run` flags straight from parsed CLI args
- `scripts/little_loops/init/tui.py:1284` (`_apply_config`) — the fourth call site (see Files to Modify above)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/adapt.py` — `main_adapt()`'s reference pipeline resolves output paths via `plugin_root = _find_plugin_root()` (`scripts/little_loops/skill_expander.py:25`, package-checkout-scoped), not `project_root`; a new `_mirror_host_artifacts` helper must NOT reuse `main_adapt`'s path resolution as-is, or a consuming project's `ll-init` run would mirror skills/commands into this little-loops checkout instead of that project. The proposed signature already threads both `project_root` and `plugin_root` as separate params, so this needs explicit handling, not an assumption that `resolve_emitter`/`process_skills`/`process_commands`/`process_agents` default to the right root [Agent 2 finding — critical]
- `scripts/tests/test_init_core.py` — 21 existing direct calls to `_dispatch_host_adapters(...)` (~lines 3688-3971) use today's 5-parameter signature; a signature change (vs. adding a sibling call after it) breaks all of them [Agent 2 finding]
- `scripts/tests/test_init_tui.py` — `_default_plugin_installed` fixture docstring (lines 39-45) documents that `_apply_config()` calls `_dispatch_host_adapters()` with **no `dry_run` kwarg at all**; a new mirror call from that site can't thread dry-run the way the three headless call sites do [Agent 2 finding]

_Wiring pass added by `/ll:wire-issue` (round 2, post-redesign):_
- `scripts/little_loops/init/cli.py:363` (`_dispatch_host_upgrade`) — confirmed by direct read: this function's *only* action is `_dispatch_host_adapters(hosts, project_root, plugin_root, force=True)` (line 363), with a comment explaining it deliberately reuses the standard per-host dispatch "so writers introduced by later work ... are picked up for free." Since the Call Path already wires `install_host_mirrors` inside `_dispatch_host_adapters`'s own per-host success branches, `_dispatch_host_upgrade` gets the mirror refresh automatically through that shared call — the Program Design's separate bullet "`_dispatch_host_upgrade(...)` — add a `install_host_mirrors(..., force=True)` call per active mirror host" describes a call site that does not need a distinct edit; implementing it as written would double-call `install_host_mirrors` per host on `--upgrade`. [wire-issue finding, verified against source]
- `scripts/tests/test_kimi_adapter.py` — correction to a prior-pass lead: this file does **not** test `install_kimi_adapter` (confirmed by grep — zero references). It tests only the `hooks/adapters/kimi/` Bash shim and `hooks.toml` sentinels (`TestKimiAdapterSentinels` line 59, `TestKimiAdapterIntegration` line 115), and is skip-gated on `bash` being on `PATH`. `install_kimi_adapter` itself is tested in `test_init_core.py` (~lines 1392-1512), not here — do not place `install_host_mirrors` tests in this file by analogy to gemini/qwen. [Agent 1 + Agent 3 finding]
- `scripts/tests/test_init_core.py::test_hosts_kimi_code_post_install_note` (~line 3612-3623) — asserts `"Kimi: hook adapter installed" in out` and `"user-level" in out` against the full captured stdout of a real `main_init(["--yes", "--hosts", "kimi-code", ...])` run through the same `elif installed and not dry_run:` kimi-code branch (cli.py:218) that the new mirror call is inserted into. Any new `info()`/`warning()` output from `install_host_mirrors` lands in this same `out` — additive-safe only if these two existing substrings are preserved. [Agent 2 finding]

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

_Wiring pass added by `/ll:wire-issue` (round 2, post-redesign):_
- No test in this repo exercises `shutil.copytree(..., dirs_exist_ok=True)` for adapter installs — `install_gemini_adapter`/`install_kimi_adapter`/`install_qwen_adapter` are JSON-merge/TOML-managed-block writers, not directory copies, so their test files (`test_gemini_adapter.py::TestInstallGeminiAdapter` line 290, `test_qwen_adapter.py::TestInstallQwenAdapter` line 357) are a *style* precedent (fresh-install / idempotent / force / dry-run test names) but not a *mechanism* precedent, and both files are skip-gated on `bash` being on `PATH` (unrelated to `install_host_mirrors`, which has no subprocess dependency) — do not add `install_host_mirrors` tests to these files on that basis. The real `dirs_exist_ok=True` precedent in this repo is `scripts/little_loops/worktree_utils.py:403` (production copytree call) with `scripts/tests/test_cli_loop_worktree.py:136-137,354,394` and `scripts/tests/test_worker_pool.py:1007-1010` showing the established test pattern: patch `shutil.copytree`, capture `(src, dst, **kwargs)` via `side_effect`, assert `dirs_exist_ok=True` in the captured kwargs — a lighter-weight alternative to real-filesystem `tmp_path` copies for asserting the merge-vs-replace semantics. Recommend adding `install_host_mirrors` tests as a new class in `scripts/tests/test_init_core.py`, matching where `install_kimi_adapter` itself is tested, not in the three per-host adapter files. [Agent 3 finding]
- `scripts/tests/test_init_audit_fixes.py::test_yes_completion_and_next_steps` (line 823, `TestOutputLayer`) is specifically the test to extend for the footer-line-removal assertion already flagged in Wiring Phase below — it already uses the `_run(["--yes", "--hosts", ..., "--root", str(project)])` + `capsys.readouterr().out` harness; extending its `--hosts` list to include `gemini`/`kimi-code`/`qwen` and asserting the `"mirror skills/commands for"` text's absence is the minimal change. No test anywhere currently references `_ADAPTER_MIRROR_HOSTS` or that literal string. [Agent 3 finding]

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
- Add a test asserting the `ll-adapt --host <h> --apply` next-steps footer line's conditional presence/absence — currently unasserted verbatim anywhere; extend `scripts/tests/test_init_audit_fixes.py::test_yes_completion_and_next_steps` (line 823) — see Tests, round-2 wiring pass
- Add `scripts/little_loops/init/writers.py` to Files to Modify (`install_host_mirrors()` lives here per Program Design; not previously listed)
- Do **not** add a separate `install_host_mirrors(..., force=True)` call inside `_dispatch_host_upgrade` (cli.py:363) — it already delegates entirely to `_dispatch_host_adapters(hosts, project_root, plugin_root, force=True)`, so the mirror call wired into that function's per-host success branches covers the upgrade path for free; a separate call there would double-invoke it
- New test class for `install_host_mirrors` belongs in `scripts/tests/test_init_core.py` (alongside where `install_kimi_adapter` is tested), not in `test_gemini_adapter.py`/`test_qwen_adapter.py`/`test_kimi_adapter.py` (those are bash-shim-gated JSON/TOML-merge tests, a different mechanism)
- Preserve the two stdout substrings (`"Kimi: hook adapter installed"`, `"user-level"`) asserted by `test_init_core.py::test_hosts_kimi_code_post_install_note` when adding new `info()`/`warning()` output from `install_host_mirrors` inside the same kimi-code success branch

## Program Design

### Signatures

- `_dispatch_host_adapters(hosts: list[str], project_root: Path, plugin_root: Path, force: bool = False, dry_run: bool = False) -> None` (`scripts/little_loops/init/cli.py:166`) — call site to extend; signature unchanged (21 direct test calls depend on it)
- new: `install_host_mirrors(project_root: Path, plugin_root: Path, host: str, *, force: bool = False, dry_run: bool = False) -> bool | None` in `scripts/little_loops/init/writers.py`, beside `install_gemini_adapter`/`install_kimi_adapter`/`install_qwen_adapter` — copies `plugin_root/.<host>/<sub>/` for each `sub` in the host's mirror subdirs into `project_root/.<host>/<sub>/`. Returns `None` when the source mirror tree is absent (pypi install, Review Findings 4), `False` when everything is already present and `force` is not set, `True` when written. Mirror subdirs per host: gemini `("skills", "commands", "agents")`, qwen `("skills", "commands", "agents")`, kimi-code `("skills", "agents")` — derive from `HOST_CAPABILITIES[host].commands`/`.agents` plus the kimi bridged-commands exception rather than a new hard-coded table if practical.
- `_ADAPTER_MIRROR_HOSTS` (`init/cli.py:542`) — narrow to gemini/kimi-code/qwen (codex out of scope) and reuse as the gate for calling `install_host_mirrors`
- `_dispatch_host_upgrade(...)` (`init/cli.py:363`) — add a `install_host_mirrors(..., force=True)` call per active mirror host

### Call Path

`_run_yes` / `_run_apply` / `_dispatch_host_upgrade` / `tui._apply_config` -> `_dispatch_host_adapters` -> per-host `elif installed and not dry_run:` success branch -> `install_host_mirrors(project_root, plugin_root, host, force=force, dry_run=dry_run)` -> `shutil.copytree(..., dirs_exist_ok=True)` per subdir

Superseded design (do not implement): `_dispatch_host_adapters -> _mirror_host_artifacts -> resolve_emitter -> process_skills/process_commands/process_agents`. See Review Findings 1–3 for why the emitter pipeline cannot target `project_root`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-05 — based on codebase analysis:_

`_dispatch_host_adapters`'s current per-host body (`scripts/little_loops/init/cli.py:166-282`) confirms it has no call to any of `resolve_emitter`/`process_skills`/`process_commands`/`process_agents` anywhere — its only imports are `error`/`info`/`warning` (`cli/output`), the four `install_*_adapter` writers, `kimi_config_path`, `resolve_host`/`HostNotConfigured`, and `plugin_installed`. `main_adapt()` (`cli/adapt.py:32-149`) is the full reference sequence a new `_mirror_host_artifacts` helper must replicate: `resolve_emitter(host)` (line 87) → `process_skills(emitter, skills_dir, apply, quiet)` if `skills_dir.exists()` (line 109) → `process_commands(emitter, commands_dir, skills_dir, apply, quiet)` unconditionally (line 115, note `skills_dir` doubles as the *output* dir for synthesized command wrappers) → resolve `config_dir` from `HOST_CAPABILITIES.get(host)` (falls back to `.codex`) → `process_agents(emitter, agents_dir, plugin_root/config_dir/"agents", apply, quiet, only)` if `agents_dir.exists()` (line 132) → `process_mcp_config(emitter, plugin_root/config_dir, apply, quiet)` unconditionally (line 141, explicitly out of this issue's scope per Scope Boundaries but still exercised by the reference call sequence). `apply = args.apply and not args.dry_run` (i.e. dry-run wins if both set) is the exact precedence a new call site should mirror.

_Added by `/ll:refine-issue` — 2026-09-05 — based on codebase analysis:_

- `HOST_CAPABILITIES` (`scripts/little_loops/adapters/capabilities.py:68-181`) is importable but currently unused in `init/cli.py`/`init/tui.py`: a targeted grep of `HOST_CAPABILITIES`, `adapters.capabilities`, `adapters.core`, `resolve_emitter`, `process_skills`, `process_commands`, `process_agents`, `process_mcp_config` against `scripts/little_loops/init/cli.py` returns zero matches — a new mirroring call needs a fresh import of these names.
- Plugin-root resolution consistency check: `_find_plugin_root()` (`scripts/little_loops/skill_expander.py:25-35`, `CLAUDE_PLUGIN_ROOT` env var first, else 3 parents up from that file) and `init/cli.py`'s own `_plugin_root()` (`:56-67`, same env var first, else 4 parents up from that file) resolve to the *same* directory as each other when computed from their own module locations — the two resolvers agree. This does **not** resolve the separate plugin_root-vs-project_root concern already flagged above (Integration Map → Dependent Files, Agent 2/wire-issue finding): `main_adapt()`'s skill/command/agent/MCP output dirs (`skills_dir = plugin_root / "skills"`, `agent_output_dir = plugin_root / config_dir / "agents"`, `mcp_output_dir = plugin_root / config_dir`) are all `plugin_root`-relative, never `project_root`-relative, so reusing that output-path logic as-is still risks writing into the plugin/package root instead of the project `_dispatch_host_adapters` is initializing. That wiring concern stands; this finding only confirms the two plugin_root *computations* are consistent with each other, not that plugin_root equals project_root.
- `_apply_config` (`scripts/little_loops/init/tui.py:1185-1299`) confirmed: its signature has no `dry_run` parameter anywhere, and its call to `_dispatch_host_adapters(hosts, project_root, plugin_root, force=force)` at line 1284 passes no `dry_run=` keyword — it relies entirely on that function's own `dry_run: bool = False` default, so TUI wizard writes (including any new mirroring call reached from this path) are always live.
- Full per-host branch ranges inside `_dispatch_host_adapters` (`scripts/little_loops/init/cli.py:166-309`): codex 186-200, kimi-code 201-222, qwen 223-237, gemini 238-252 (each ending in an `elif installed and not dry_run:` success guard), `opencode`/`pi`/`omp` 253-261 (info-only, no adapter writer call), `claude-code` 262-309 (separate `resolve_host()`/`plugin_installed()`/subprocess plugin-marketplace install flow, structurally unrelated to the adapter-file writers).

## Impact

- **Priority**: P4 - quality-of-life gap; note the documented manual workaround (`ll-adapt --host <h> --apply`) does not actually populate a consumer project today (Review Findings 2), so the gap is wider than first captured
- **Effort**: Medium - one new writer (`install_host_mirrors`) plus wiring into four call sites and `_dispatch_host_upgrade`, a footer change with tests, and seven doc pages; pypi source-dir absence must warn-and-skip
- **Risk**: Low - additive copy step gated on host selection and `not dry_run`; `force` semantics mirror the existing hook-adapter writers
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-04 | Priority: P4


## Session Log
- `/ll:wire-issue` - 2026-09-05T17:50:06 - `ed66812c-58df-4f76-9110-35683914fb88.jsonl`
- pre-implementation review (manual) - 2026-09-05 - reframed from "run ll-adapt" to "copy pre-built mirrors"; codex and wizard prompt dropped; re-run `/ll:wire-issue` before `/ll:manage-issue`
- `/ll:refine-issue` - 2026-09-05T17:24:37 - `78d5f5c3-1aa6-45e4-aacc-42e2a861b775.jsonl`
- `/ll:wire-issue` - 2026-09-05T04:57:35 - `7ad2c895-8f68-4859-96fb-41e7c667e5b1.jsonl`
- `/ll:refine-issue` - 2026-09-05T04:32:50 - `251307a7-40ea-42f4-beb3-43e6b4de6744.jsonl`
- `/ll:format-issue` - 2026-09-05T04:22:41 - `adb409c3-bb29-46e0-a080-e89ad1cec8e0.jsonl`
