---
id: FEAT-2267
title: Generic host-parameterized ll-init --upgrade surface refresh
type: feature
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: capture-issue
parent: EPIC-2257
decision_ref: ARCHITECTURE-049
blocked_by: []
decision_needed: false
relates_to: [ENH-2256, FEAT-2260]
labels: [host-compat, portfolio, init, upgrade]
---

# FEAT-2267: Generic host-parameterized ll-init --upgrade surface refresh

## Summary

Generalize `ll-init --upgrade` from a Claude-plugin-only flow into a **single
host-parameterized surface-refresh dispatcher** that keeps *every* active
host's integration surface current after a package upgrade. Per
ARCHITECTURE-049, this is built **once** taking a host argument, not as N
bespoke per-host upgrade paths.

ENH-2256 (`a16d8f7d`) shipped `--upgrade` for the **pip package** plus a
warn/advise path for the **Claude marketplace plugin**, but:

1. The headless `--upgrade` only acts on the package; the Claude plugin update
   is never run, even with `--upgrade`.
2. There is **no surface at all** for non-Claude hosts. Their integration
   surface is **generated adapter files** in the target project
   (`.codex/hooks.json`, codex skill frontmatter / `.codex/agents/*.toml` from
   the `ll-adapt-*` CLIs, opencode/omp adapters) — not a marketplace plugin.
   `fetch_latest_plugin()` correctly returns `None` for these hosts, so they
   currently get **zero** upgrade signal.

## Current Behavior

`ll-init --upgrade` updates only the pip package. No host integration surface is refreshed after a package upgrade:

- **claude-code**: the marketplace plugin is never updated, even with `--upgrade`.
- **Non-Claude hosts** (codex, gemini, omp): no upgrade surface exists; `fetch_latest_plugin()` returns `None` for these hosts.
- Generated adapter files embed absolute `plugin_root` paths that become stale; `install_codex_adapter()` skips existing files without `--force`, so stale adapters persist after an upgrade.

## Expected Behavior

`ll-init --upgrade` dispatches a host-parameterized surface refresh for every active host after the package upgrade:

- **claude-code**: scope-aware plugin update — auto for project-scoped installs, advise-only for user-scoped.
- **Adapter hosts** (codex, gemini, omp): force-regenerate all adapter files against the upgraded `plugin_root`, correcting stale version paths.
- Generated adapters embed a version stamp; `--upgrade` warns when the stamp diverges from the installed package version.
- TUI Screen-1 shows staleness rows for non-Claude hosts, symmetric with existing package/plugin rows.

## Use Case

A developer uses little-loops with both claude-code and codex. After `pip install --upgrade little-loops`, they run `ll-init --upgrade`. Currently, only the pip package advances — codex adapter files still embed the old `plugin_root` path, silently breaking codex integration until the developer manually regenerates adapters. After this change, `ll-init --upgrade` force-regenerates stale adapters for each active non-Claude host and handles the claude-code plugin update in one command.

## Motivation

After a package upgrade, integration adapter files silently become stale — they embed absolute `plugin_root` paths pointing to deleted version directories. Users discover this only when codex/gemini/omp integrations break with path errors. The upgrade surface must be as multi-host-aware as initial installation; without this, every package upgrade requires manual adapter regeneration for each non-Claude host.

## The two surface flavors

| Host | Surface | "Update" means | Staleness signal |
|------|---------|----------------|------------------|
| claude-code | versioned marketplace plugin | `<host> plugin update ll@little-loops` (scope-aware) | marketplace version query |
| codex / gemini / omp | generated adapter files in the project | **regenerate** against the new `plugin_root` | stamped gen-version vs installed package |

## Why non-Claude is more fragile

`install_codex_adapter()` (`writers.py:343-385`) renders the adapter by
substituting `{{LL_PLUGIN_ROOT}}` with an **absolute** `plugin_root` path
(`writers.py:374`). For a Claude plugin install that path is version-stamped
(`…/cache/…/ll/<version>/…`), so a package/plugin upgrade can leave
`.codex/hooks.json` pointing at an **old or deleted** version dir. And the
writer **skips existing files without `--force`** (`writers.py:371`), so a
plain re-run will not refresh a stale adapter.

## Acceptance Criteria

- `--upgrade` runs a **host-parameterized** surface-refresh after the package
  upgrade, dispatching per active host (driven by selected hosts /
  `resolve_host()`), built once — no per-host bespoke branches beyond the
  surface-flavor split.
- **claude-code branch**: scope-aware plugin update — auto-update when the
  install is **project-scoped**; **advise only** (or require explicit opt-in)
  when **user-scoped**, to avoid mutating shared global state from a
  project-scoped command. (Depends on BUG-2266 for scope.)
- **adapter-host branch**: force-regenerate each active host's adapters against
  the upgraded `plugin_root` (re-substitute the path so a dangling version
  stamp is corrected).
- **Staleness stamping**: generated adapters embed the package version they
  were generated from (mirror the existing `.claude/ll-update-docs.watermark`
  pattern). Warn-only mode compares stamp vs installed version and prints a
  concrete hint (`generated against X, package is now Y — re-run --upgrade`).
- All host CLI calls go through `resolve_host()` — never a hardcoded `"claude"`
  (per CLAUDE.md host-abstraction rule); best-effort (`check=False`) so a
  missing/unauthenticated host never aborts the init or config write.
- TUI Screen-1 per-surface checks (`tui.py:175-224`) extended to show
  adapter-staleness rows for non-Claude hosts, symmetric with the existing
  package/plugin rows.

## Open design questions (keep explicit; do not pre-decide)

- User-scoped Claude plugin: auto-update gated on `scope == project` only, vs.
  a separate `--upgrade-global` opt-in, vs. always advise. (Scope philosophy:
  should a project-scoped command ever mutate global state?)
- Where the adapter gen-version stamp lives (inside each adapter file as a
  comment/field, vs. a sidecar watermark per host).

## Reference

- `scripts/little_loops/init/cli.py:159-236` — current package/plugin upgrade block.
- `scripts/little_loops/init/install_check.py:105-146` — `fetch_latest_plugin`.
- `scripts/little_loops/init/writers.py:343-385` — `install_codex_adapter` (skip-without-force + plugin_root substitution).
- `scripts/little_loops/init/cli.py:57-80` — `_dispatch_host_adapters`.
- ENH-2256 — originating work. FEAT-2260 — generic skill/command adapter (sibling shared-infra child).

## Integration Map

### Files to Modify
- `scripts/little_loops/init/cli.py` — extend upgrade block; add `_dispatch_host_upgrade` dispatcher or extend `_dispatch_host_adapters` (`_dispatch_host_adapters` function)
- `scripts/little_loops/init/install_check.py` — `fetch_latest_plugin`; may need scope-awareness extension
- `scripts/little_loops/init/writers.py` — `install_codex_adapter`; add `force=True` pass-through and gen-version stamp on write
- `scripts/little_loops/init/tui.py` — Screen-1 staleness check region; add non-Claude host adapter-staleness rows

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/cli.py` — top-level `ll-init` entrypoint; orchestrates upgrade dispatch
- Any test calling `install_codex_adapter()` directly

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/__init__.py` — re-exports `install_codex_adapter`, `fetch_latest_plugin`, `detect_installation` in `__all__`; if any new public functions are added (e.g., adapter staleness reader, version stamp writer), they must be imported and listed here [Agent 1]

### Similar Patterns
- `.claude/ll-update-docs.watermark` — existing watermark pattern to mirror for gen-version stamping

### Tests
- `scripts/tests/test_init_core.py` — add coverage for `--upgrade` multi-host dispatch and scope-aware claude-code branch
- New: verify force-regeneration for adapter hosts; verify staleness-stamp compare logic

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_install.py` — dedicated `TestFetchLatestPlugin` and `TestDetectInstallation` classes (351 lines); needs new tests for non-Claude host behavior in `fetch_latest_plugin` and for `detect_installation` after fixing hardcoded `"claude"` literals at `install_check.py:60,63` [Agent 1/3]
  - **At risk of breaking**: 6 tests in `TestDetectInstallation` patch `little_loops.init.install_check.shutil.which` as the Claude binary guard; when the hardcoded `"claude"` literal is replaced with `resolve_host()`, the patch target changes — update those 6 tests to patch `resolve_host` instead of `shutil.which` [Agent 2/3]
- `scripts/tests/test_init_tui.py` — `TestHostSelection` class (lines 596–672); needs new tests for Screen-1 adapter-staleness rows for codex host; the `mock_detect_installation` autouse fixture (line 32) forces `install_source=None` for all TUI tests — new staleness tests must override it to return a non-None install source with a known version so the staleness code path is exercised [Agent 3]
  - **At risk of breaking**: all `_wire_q`-based tests will fail if a new `questionary.confirm()` call is added to Screen-1 for the adapter-staleness proceed dialog, because `_wire_q`'s positional `confirm_returns` list will have the wrong count; update `_wire_q` helper and affected tests (`TestCtrlC.test_ctrl_c_on_hosts_returns_130`, `TestDesignTokenProfilePicker.test_profile_warm_paper_written_to_config`, any test with explicit confirm lists) [Agent 3]

### Documentation
- `docs/reference/CLI.md` — update `ll-init --upgrade` flag description for multi-host behavior

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/GETTING_STARTED.md` — `--upgrade` flag table (line 95) currently says "install or upgrade the pip package" only; needs multi-host adapter refresh behavior documented; "Installation Detection" table (lines 117–121) is also pip-centric [Agent 2]
- `docs/codex/getting-started.md` — troubleshooting table (line 132) directs users to `pip install --upgrade little-loops` for stale adapters; after FEAT-2267, `ll-init --upgrade` is the canonical path and should be mentioned here; if sidecar file (`.codex/ll-gen-version`) is introduced, that artifact is not documented anywhere yet [Agent 2]
- `docs/reference/API.md` — `fetch_latest_plugin` entry says "Only meaningful when the `claude-code` host is active"; update after scope fix extends or replaces this behavior [Agent 2]
- `skills/init/SKILL.md` — example comment for `--upgrade` (in Parse Flags section) describes claude-only behavior; update when adapter-host branch is complete [Agent 2]

### Configuration
- N/A — uses existing `orchestration.host_cli` / `LL_HOST_CLI`; no new config keys

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/adapters/codex/hooks.json` (in-package template) — if the JSON-field approach is chosen for the gen-version stamp (`"_ll_gen_version"` key inside the file), the template itself must be modified; this template is verified by `ll-verify-package-data` [Agent 2]
- `scripts/little_loops/init/cli.py` (`_print_dry_run()`) — if a gen-version sidecar file (e.g., `.codex/ll-gen-version`) is introduced as a separate artifact, the dry-run preview block for codex (which currently prints only `[write] .codex/hooks.json`) needs a corresponding `[write] .codex/ll-gen-version` line [Agent 2]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Unblocked**: BUG-2266 is `done` (completed 2026-06-25). `detect_installation()` (`install_check.py:39-87`) already returns `"project-claude-code"` vs `"global-claude-code"` from the `scope` field in `claude plugin list --json`. The `install_source` value is already the scope signal — no new function needed for Step 2.

**Exact upgrade hook point**: `_run_yes` calls `_dispatch_host_adapters(hosts, project_root, plugin_root, force=force)` at `cli.py:339`. The upgrade (pip) runs in the block at `cli.py:200-265`, **before** this call. The `_dispatch_host_upgrade()` dispatcher should be inserted **between** the pip-upgrade block and the normal `_dispatch_host_adapters` call, calling `_dispatch_host_adapters(hosts, project_root, plugin_root, force=True)` when an upgrade was performed (instead of routing through the normal `force` flag).

**`install_codex_adapter` already has `force` param** (`writers.py:383-423`): returns `True|False|None`. Gen-version stamp is not yet written. The rendered output is `.codex/hooks.json` (JSON) — JSON does not support comments, so a `# generated by little-loops v0.9.0`-style comment is invalid. Options for stamp location: (a) a `"_ll_gen_version"` key inside the JSON (codex may reject unknown fields), or (b) a sidecar file (e.g., `.codex/ll-gen-version`) mirroring the `.claude/ll-update-docs.watermark` pattern. **This is one of the open design questions — do not pre-decide.** Document the constraint (no JSON comments) when implementing.

**Watermark format mismatch**: `.claude/ll-update-docs.watermark` stores a **git commit hash**, not a package version string. The gen-version stamp for adapters needs the **package version** (`importlib.metadata.version("little-loops")`), not a commit hash. The watermark "pattern" to mirror is the sidecar-file concept, not the hash format.

**`detect_installation` hardcodes `"claude"` literal** (`install_check.py:60, 63`): violates the CLAUDE.md host-abstraction rule. Pre-existing debt; fix opportunistically when modifying this file for FEAT-2267.

**Gemini/OMP adapter writers don't exist yet**: `_dispatch_host_adapters` has no `elif host == "gemini"` or `elif host == "opencode"` branch. FEAT-2260 (sibling) delivers those writers. FEAT-2267's upgrade dispatcher must be designed to call the same writer functions FEAT-2260 introduces — **implement the upgrade dispatcher interface against FEAT-2260's writer contract, not ahead of it**. Consider marking this as `depends_on: [FEAT-2260]` for sequencing.

**TUI Screen-1 staleness pattern** (`tui.py:179-230`): `_pkg_outdated` and `_plugin_outdated` booleans gate the Screen-1 section; adapter staleness rows follow the same boolean pattern. The new per-host staleness boolean would compare the gen-version stamp (read from `.codex/ll-gen-version` or the JSON field) against `installed_version`. The console output follows `console.print("[yellow]...[/yellow] ...")` with a fix hint.

**`_detect_hosts` (cli.py:55-64)** uses `shutil.which("codex")` and `.codex` dir presence — this governs which `hosts` are passed to the upgrade dispatcher. Upgrade dispatches to whichever hosts were selected/detected; `resolve_host()` is invoked inside each host CLI call, not at the detection level.

## Implementation Steps

1. Add `_dispatch_host_upgrade(hosts, plugin_root)` dispatcher in `cli.py` that iterates active hosts and routes to claude-code or adapter branch
2. Implement claude-code branch: query install scope via `resolve_host()`; auto-update if project-scoped, advise-only if user-scoped (blocked on BUG-2266 for scope detection)
3. Implement adapter-host branch: call `install_codex_adapter(force=True)` for each non-Claude host against the upgraded `plugin_root`
4. Add gen-version stamp to adapter files on write; implement warn path comparing stamp vs installed version (mirror `.claude/ll-update-docs.watermark`)
5. Extend TUI Screen-1 to include staleness rows for non-Claude host adapters
6. Wire all host CLI calls through `resolve_host()` — no hardcoded `"claude"` literals
7. Add/update tests in `test_init_core.py`; verify dispatch for each host flavor

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update 6 tests in `TestDetectInstallation` (`test_init_install.py`) — patch target changes from `little_loops.init.install_check.shutil.which` to `resolve_host` when the hardcoded `"claude"` literal at `install_check.py:60,63` is fixed
9. Update `_wire_q` helper and affected `_wire_q`-based tests in `test_init_tui.py` if a new `questionary.confirm()` call is added to Screen-1 (adapter-staleness proceed dialog); positional `confirm_returns` lists will be off by one for all existing host-selection tests
10. Update `scripts/little_loops/init/cli.py::_print_dry_run()` — add `[write] .codex/ll-gen-version` preview line if sidecar-file stamp approach is chosen
11. Update `scripts/little_loops/init/__init__.py` — add any new public functions (staleness reader, version stamp writer) to imports and `__all__`

## Impact

- **Priority**: P4 — non-Claude upgrade path was missing from ENH-2256; affects multi-host users on codex/gemini/omp
- **Effort**: Medium — extends upgrade block and adapter writer; reuses `_dispatch_host_adapters` pattern
- **Risk**: Medium — touches global plugin state (gated on scope) and force-regenerates project files; scope gate mitigates global-state risk
- **Breaking Change**: No (additive behavior; `--upgrade` currently does nothing for non-Claude hosts)

## Status

**Open** | Created: 2026-06-24 | Priority: P4


## Session Log
- `/ll:wire-issue` - 2026-06-25T18:46:15 - `b48daf6e-e26f-40d4-9aab-ea94d716a199.jsonl`
- `/ll:refine-issue` - 2026-06-25T18:36:28 - `70f59565-7e94-410d-bf6c-c34dd59cbf9f.jsonl`
- `/ll:format-issue` - 2026-06-25T18:23:35 - `07bde162-4904-43ac-b97d-3e260fc376b5.jsonl`
