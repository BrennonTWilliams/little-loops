---
id: BUG-3644
type: BUG
title: orchestration.host_cli config key ignored by ll-loop run and other resolve_host()
  callers
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-28'
captured_at: '2026-09-28T22:31:27Z'
labels:
- multi-host
- host-runner
decision_needed: false
behavior_parity_not_applicable: true
reconcile_attempted: true
verify_verdict: VALID
confidence_score: 95
outcome_confidence: 64
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 0
size: Large
---

# BUG-3644: orchestration.host_cli config key ignored by ll-loop run and other resolve_host() callers

## Summary

`orchestration.host_cli` in `.ll/ll-config.json` is documented as a host-selection override, but only `ll-doctor` honors it. `apply_host_cli_from_config()` (`little_loops.host_runner`) is the sole bridge from the config key into the host env var, and its only production caller is `little_loops.cli.doctor`. `resolve_host()` reads only the host env vars (`LL_HOST_CLI`, `LL_HOOK_HOST`) and the `_PROBE_ORDER` PATH probe.

Found while reviewing ENH-3548 (validate-time model hint warnings).

## Current Behavior

- `ll-loop run`, `ll-auto`, `ll-parallel`, `ll-sprint` and every other `resolve_host()` consumer ignore `orchestration.host_cli`. With `orchestration.host_cli: codex` and no `LL_HOST_CLI` set, a machine that also has `claude` on PATH dispatches to whichever host wins the probe order.
- `FSMExecutor._resolve_model` / `_preflight_model_hints` resolve `model_hint` against `resolve_host().name`, so hint resolution also ignores the config key.
- `ll-doctor` does apply it, so `ll-doctor` and `ll-loop run` can report different hosts on the same machine.

## Expected Behavior

Precedence everywhere a host is resolved: `LL_HOST_CLI` env var > `orchestration.host_cli` config key > binary probe — as `apply_host_cli_from_config()`'s docstring, `config-schema.json` (`orchestration`, `orchestration.host_cli` descriptions), `.claude/CLAUDE.md` (Host CLI Abstraction) and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (~486) already claim.

## Root Cause

- **File**: `scripts/little_loops/host_runner.py`
- **Anchor**: `in function resolve_host()` (and its sibling `apply_host_cli_from_config()`)
- **Cause**: `resolve_host(env)` has no access to config: it snapshots `dict(os.environ)` and computes `explicit = env.get("LL_HOST_CLI") or env.get("LL_HOOK_HOST")`, then falls to the `_PROBE_ORDER` PATH probe. The config value only reaches it if something first runs `apply_host_cli_from_config(config)`, which copies `config.orchestration.host_cli` into `os.environ["LL_HOST_CLI"]` (early-returns when `LL_HOST_CLI` is already truthy). The only production call is `cli/doctor.py:main_doctor` (`apply_host_cli_from_config(cfg)` immediately before `resolve_host()`); no other `main_*` bootstrap calls it, and no shared CLI-startup helper exists to host the call. Comments and docs then assert the bridge exists everywhere (`init/cli.py` comment at "resolve_host() honors LL_HOST_CLI/orchestration.host_cli", `docs/ARCHITECTURE.md` ~919/924, `config-schema.json` `orchestration` description), which is false for every path except `ll-doctor`.

## Proposed Solution

Apply the config key at CLI entry for every automation tool that resolves a host (at minimum `ll-loop run`/`validate`, `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-logs fleet-review`), or fold the config lookup into `resolve_host()` itself behind the env var. Prefer a single choke point over per-CLI calls so new entry points cannot regress. Decide whether in-process `os.environ` mutation (current `apply_host_cli_from_config` approach) is acceptable given it leaks into descendants (compare the `LL_AUTOMATION` descendant-leak incident).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

**Option A**: Per-entry-point `apply_host_cli_from_config(config)` calls in each `main_*` after `BRConfig` construction (`main_loop`, `main_auto`, `main_parallel`, `main_sprint`, plus any other host-resolving entry). Matches the `main_doctor` precedent and the `LL_HANDOFF_THRESHOLD` per-entry writes; carries the env-mutation leak into descendants and gives no structural guard against a new entry point omitting it (needs the enumeration gate).

**Option B**: Fold the config lookup into `resolve_host()` itself, consumer-side and behind the env vars, reading `ll-config.json` without raising (precedent: `session_store/db.py::resolve_history_db`). Single choke point, no env mutation. Constraints: `resolve_host_named()` passes an explicit `env` and must stay config-independent, so the lookup can only apply on the `env is None` path; `host_runner.py` has no top-level `little_loops.config` import (a lazy import or a raw JSON read avoids a cycle); `LL_HOOK_HOST` ordering vs config **RESOLVED** — `LL_HOOK_HOST` stays above config (env-level signals beat config), decided 2026-09-28 by /ll:decide-issue.

> **Selected:** Option B — single choke point reaching ~45 `resolve_host()` callers with no env mutation, consistent with the `resolve_history_db` env > config > default precedent and the FEAT-3060 rejection of env-mutating helpers.

**Option C**: Export `LL_HOST_CLI` from config inside `BRConfig.__init__`, alongside the existing `load_env_fallback` side effect, so every entry that builds a `BRConfig` is covered. Constraints: ~62 files construct `BRConfig` (including `cli/advise.py`, whose test pins `LL_HOST_CLI` unchanged after `main_advise()`); it widens the env-mutation leak the FEAT-3060 decision rejected; `cmd_run` builds a second `BRConfig` at `cli/loop/run.py:269` after `main_loop` already built one.

**Recommended**: Option B — the issue's own stated preference for a single choke point that new entry points cannot regress; final selection belongs to `/ll:decide-issue`.

- Scope note: `ll-logs fleet-review` does not call `host_runner.resolve_host()`. `fleet-review --host` resolves a session-log host through `user_messages._resolve_host` (flag > `LL_HOOK_HOST` > default), unrelated to host-CLI selection. _(Corrected by pre-implementation review 2026-09-28: ENH-3548 has landed, and `cmd_validate` now calls `resolve_host().name` at `cli/loop/config_cmds.py:38`, so `ll-loop validate` is a direct `env is None` caller covered by AC-1.)_
- Related latent inconsistency: `cli/doctor.py:816` hand-rolls env > config for the advisor floor row and then calls `resolve_host_named(name)` or `resolve_host()`; a choke-point fix should let it collapse to one resolution path.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-28.

**Selected**: Option B

**Reasoning**: Folding the config lookup into `resolve_host()` (on the `env is None` path only) fixes every ambient-env caller at once with no `os.environ` mutation, matching the `session_store/db.py::resolve_history_db` precedent (`test_env_wins_over_config`). Options A and C both export `LL_HOST_CLI` into the process, which the FEAT-3060 decision rejected and which leaks to descendants via `project_child_env`; C additionally breaks `test_advisor_host_env_independent_of_orchestration_host_cli` and A leaves ~20 non-enumerated entry points uncovered.

**Implementation cautions for B**: `_config_db_path` reads only base `ll-config.json`; `ll.local.md` frontmatter overrides (deep-merged in `BRConfig`) must also be honored, so reuse the config-merge helper (lazy import, never raise) rather than a raw JSON read. `env=None` tests in other files run from the repo cwd and could pick up the repo's own config — guard with a fixture or an isolated cwd. `LL_HOOK_HOST` keeps precedence over config.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 2/3 | 2/3 | 2/3 | 1/3 | 7/12 |
| Option B | 3/3 | 2/3 | 2/3 | 2/3 | 9/12 |
| Option C | 1/3 | 3/3 | 1/3 | 0/3 | 5/12 |

**Key evidence**:
- Option A: only `main_doctor` calls `apply_host_cli_from_config` (`cli/doctor.py:1668`); `LL_HANDOFF_THRESHOLD` per-entry writes are precedent, but ~20 `resolve_host()` entry points (`cli/action.py`, `cli/harness.py`, `cli/artifact/*`, `mcp_server/tools.py`, …) would each need the call, and it re-creates the FEAT-3060-rejected env leak.
- Option B: `db.py::_resolve_db_path` (l.105-117) is a direct env > config > default template; `host_runner.py` has no top-level config import so a lazy import avoids a cycle; `resolve_host_named` passes explicit `env` and stays independent.
  > **Selected:** Option B — per the Decision Rationale above
- Option C: `BRConfig.__init__` → `load_env_fallback` (`config/core.py:293`) is a wiring point, but ~55 source-file constructions (incl. `cli/advise.py`) would export `LL_HOST_CLI`, failing `test_cli_advise.py:153` and widening the leak.

### Review Decisions (2026-09-28)

_Pre-implementation review. These close the items the Wiring Phase and Confidence Check left as "decide and record"; where they conflict with earlier sections, these win._

1. **Remove `apply_host_cli_from_config` from `main_doctor`; collapse `doctor.py:816`.** `apply_host_cli_from_config` early-returns only on `LL_HOST_CLI` (`host_runner.py:2954`), never on `LL_HOOK_HOST`, so today `ll-doctor` ranks config **above** `LL_HOOK_HOST` — contradicting the decided precedence. The hand-rolled `os.environ.get("LL_HOST_CLI") or cfg.orchestration.host_cli` at `:816` has the same defect. After the fold-in the doctor call is redundant, and keeping it makes `ll-doctor` and `ll-loop run` disagree whenever `LL_HOOK_HOST` is set. So: delete the call at `:1668`; replace `:816` with `resolve_host(project_root=<root doctor built cfg from>).name`; keep `apply_host_cli_from_config` as a **deprecated** public symbol with zero production callers (docstring says so; stays in both `__all__` lists and `API.md` marked deprecated). The ~30 `patch(...apply_host_cli_from_config)` sites become harmless no-ops and need no edit; `TestApplyHostCliFromConfig` stays.
2. **Project root is an explicit seam, not cwd-only.** Signature becomes `resolve_host(env: dict[str, str] | None = None, *, project_root: Path | None = None)`. The config step seeds its upward walk from `project_root` (default `Path.cwd()`), mirroring `session_store/db.py::_config_db_path(root=)` (BUG-3181). `init/cli.py:149` (`default_hosts`) and `mcp_server/tools.py:224` pass their own root — the MCP server's root can come from `LL_MCP_PROJECT_ROOT` (`mcp_server/tools.py:54`), and `ll-init --root` targets a non-cwd directory. `project_root` is ignored when `env` is passed explicitly. _(Amended by Review Decision 13: an explicit `project_root` is read as-is, not used as a walk seed.)_
3. **No caching.** `resolve_host()` already does up to 7 `shutil.which` PATH scans per call and every hot caller then spawns a subprocess; one config read is noise, and when the key is set it short-circuits the probe. A cache would reintroduce `monkeypatch.chdir` leakage (see `cli/doctor.py::_probe_advisor_version`).
4. **AC-4 gate targets real bypasses, not env writes.** Under Option B the bypass risks are (a) hand-rolled `LL_HOST_CLI` / `orchestration.host_cli` reads for host selection outside `host_runner.py` (exactly what `doctor.py:816` is today), and (b) `resolve_host(env=...)` called with a copy of ambient env, which silently skips the config step because only the `env is None` path reads config. The gate asserts: no production call to `apply_host_cli_from_config`; no `resolve_host(` call passing a positional or `env=` argument outside `resolve_host_named` (`project_root=` is allowed); no `LL_HOST_CLI` read or `orchestration.host_cli` read outside `host_runner.py`, except reasoned `_ALLOWLIST` entries (config loading in `config/core.py`/`config/orchestration.py`, `init/cli.py` persistence/`default_hosts`), plus an allowlist-drift test and a `test_gate_detects_a_stray_site` self-test. **Matcher precision** (a naive text or attribute-name match false-positives on current code):
   - *`LL_HOST_CLI` reads* — AST only: a `.get("LL_HOST_CLI")` call, or a `Subscript` with `Load` context whose slice is the constant `"LL_HOST_CLI"`. String mentions in docstrings and error messages (`fsm/evaluators.py:1626`, `session_store/lifecycle.py:176`, `learning_tests/extractor.py:144`) and dict-literal child-override writes (`cli/loop/summary.py:201`, `project_child_env(extra={"LL_HOST_CLI": ...})`) are not reads and must not match.
   - *Config-key reads* — match an `Attribute(attr="host_cli")` only when its `.value` is an `Attribute(attr="orchestration")` (catches `cfg.orchestration.host_cli`; does **not** match `shown.conditions.host_cli` at `cli/harness.py:1595`, the unrelated fingerprint field), **plus** a `["host_cli"]` subscript or `.get("host_cli")` call (catches raw-dict reads such as `init/cli.py`'s `existing_config["orchestration"]["host_cli"]`, which an attribute-only matcher misses). `config/core.py:905` (`"host_cli": self._orchestration.host_cli` in `to_dict`) is a serialization read and is allowlisted with that reason.
5. **`LL_STATE_DIR` also steers the lookup.** `resolve_config_path` reads both `LL_HOOK_HOST` and `LL_STATE_DIR` from `os.environ` (`config/core.py:177-178`). `LL_HOOK_HOST` can never reach the config step (it wins first), but `LL_STATE_DIR=.codex` redirects which `ll-config.json` is read. That is accepted behavior; it must be tested.
6. **Not edit targets.** The CLI `main_*` bootstraps, `cmd_run`, and `BRConfig.__init__` (whose `load_env_fallback` writes `os.environ`) are unmodified — they were the wiring points of the rejected Options A/C. `BRConfig` is never constructed inside `resolve_host()`. _(Amended by Review Decision 12: `config/core.py` gets one behavior-preserving extraction — `BRConfig._load_config`'s body moves to a module function both paths share; `BRConfig.__init__` itself is still unmodified.)_
7. **Worktree children — known limitation, out of scope.** `ll-*` processes launched inside `ll-parallel`/sprint worktrees resolve from the worktree cwd; worktrees copy only `.claude/settings.local.json`, `.env`, `.ll/ll.local.md` (`parallel/types.py:436`). Where `.ll/ll-config.json` is tracked (as here) this is fine; in a consumer project where it is untracked, children miss the key and fall to the probe while the parent honored it. Not fixed here — changing the default copy list is an `ll-parallel` behavior change; capture a follow-up if it bites.
8. **Docs scope trimmed.** Required edits are only docs that describe the **mechanism** ("exported by `apply_host_cli_from_config` before `resolve_host()` runs", "Typically called at startup", detection-order lists missing the config step). Host docs that already state env > config > probe (`docs/{codex,qwen,kimi}/*`, `docs/codex/README.md`, `docs/development/CONFORMANCE.md`, `docs/guides/EVALUATION_GUIDE.md`) become correct by the fix — verify, edit only on a mechanism claim.
9. **Suite-wide test isolation via an autouse stub, not a per-file `chdir` audit.** Add an autouse function-scoped fixture to `scripts/tests/conftest.py` that monkeypatches `little_loops.host_runner._config_host_cli` to return `None`, with an opt-out (a `real_host_config` fixture or `@pytest.mark.host_config` marker) for tests that exercise the config step. Precedent: `_install_no_live_host_cli`. Reason: the repo's own `.ll/ll-config.json:152` sets `host_cli: claude-code`, which is also what the probe picks on a dev machine with `claude` on PATH — so an unisolated test can pass locally for the wrong reason and fail only on GitHub-hosted CI, where `claude` is absent. The stub makes every existing `env is None` test behave exactly as before the fix, replacing the ~20-file cwd-exposure audit and the per-fixture `chdir` edits (`test_model_hints.py::no_host`, `test_init_core.py::TestDetectHosts`), which become unnecessary. New `TestResolveHost` config cases, the `test_fake_host.py` end-to-end test, the `ll-doctor` agreement test and the `default_hosts`/MCP `project_root` tests opt out. **Limit:** the stub is a `monkeypatch`, so it covers in-process calls only — a test that runs an `ll-*` CLI as a subprocess from the repo cwd bypasses it and reads the repo's `host_cli: claude-code`. A spot check found host-sensitive CLI tests (`test_loop_cli_defaults.py`, `test_model_hints.py`, `test_ll_loop_commands.py`) drive `main_*` in-process via `patch.object(sys, "argv", ...)`, so risk is low; any subprocess-based test that fails on GitHub-hosted CI (no `claude` on PATH) after this lands should run with `cwd=tmp_path`.
10. **Error messages name the config source.** (a) When the host name came from the config step and is not in `_HOST_RUNNER_REGISTRY`, `HostNotConfigured` says so: `orchestration.host_cli = 'xyz' in <config path> is not a registered host. Available: [...]` — `_config_host_cli` returns the resolved path alongside the value (or a small private `(value, path)` tuple) so the message can cite it. The `LL_HOST_CLI`/`LL_HOOK_HOST` branch keeps its current message. (b) The four "`<binary>` CLI not found. Install the active host CLI (see LL_HOST_CLI)." messages — `host_runner.py:2840` and `:2844`, `fsm/evaluators.py:1626`, `learning_tests/extractor.py:144`, `session_store/lifecycle.py:176` — change to "(see LL_HOST_CLI / orchestration.host_cli)", since after the fix a config-selected host whose binary is not on PATH is the most likely cause. Check tests that assert the exact old text (`grep -rn "see LL_HOST_CLI" scripts/tests/`) and update them in step.
11. **Pre-merge rollout survey.** Every `ll-init`'d project writes `orchestration.host_cli` (`init/cli.py:555`), and all local projects are `local-editable` against this checkout, so each one switches from the probe to its config the moment this lands. Before merging, list each local little-loops project's effective `orchestration.host_cli` (`.ll/ll-config.json` merged with `.ll/ll.local.md`) and confirm the matching binary is on PATH (`which claude|codex|pi|...`). Fix or clear any mismatched key first. Record the survey result in the Resolution section.
12. **Extract a shared raw-config loader instead of re-composing the merge.** Move `BRConfig._load_config`'s body (`config/core.py:297-326`: `resolve_config_path` → `json.load` → `.ll/ll.local.md` frontmatter `deep_merge`) into a pure module function `load_raw_config(project_root: Path) -> dict[str, Any]` in `config/core.py` — no env reads beyond what `resolve_config_path` already does, no `os.environ` writes, same exceptions as today. `BRConfig._load_config` becomes `return load_raw_config(self.project_root)`. `_config_host_cli` resolves the root (`resolve_ll_dir(start=project_root)`, parent of the `.ll` dir), calls `load_raw_config(root)` via a function-local import inside its never-raise `try`, and reads `orchestration.host_cli`. Reason: re-assembling the same three primitives in `host_runner.py` duplicates non-obvious details (the local override is always read from `<root>/.ll/`, never from a host state dir like `.codex/`) that would drift. Existing `test_config.py::TestBRConfigLocalOverrides` covers the extraction; add one direct `load_raw_config` test.
13. **An explicit `project_root` is used as-is; only the cwd default walks upward.** Amends Decisions 2 and 12. `_config_host_cli(project_root)`: when `project_root` is given, call `load_raw_config(project_root)` directly — no `resolve_ll_dir`/`find_project_root` walk; when omitted, resolve the root with `resolve_ll_dir(start=Path.cwd())` (parent of the returned `.ll`) and return `None` if it resolves nothing. Reasons: (a) `BRConfig(project_root)` reads config at the root it is handed without walking, and the two must agree; (b) `find_project_root` (`paths.py:14`) climbs to an ancestor, so `ll-init --root sub/` inside a larger project whose top has `.ll/` would read the parent's `host_cli` — exactly the fallback case `default_hosts` reaches when the target has no valid config yet; (c) `find_project_root` matches only on an existing `.ll/` dir, so a root whose config lives solely in `.codex/ll-config.json` (no `.ll/`) would resolve `None` and skip a present config. Test: config in `tmp/a/.ll/ll-config.json`, a config-less stray `tmp/a/sub/.ll/`, `resolve_host(project_root=tmp/a/sub)` → does **not** pick up `tmp/a`'s key (falls to probe); `resolve_host(project_root=tmp/a)` with only `tmp/a/.codex/ll-config.json` + `LL_STATE_DIR=.codex` → honors it.
14. **`default_hosts` re-init with an invalid key: accept the shift, update the docstring.** Today an existing `orchestration.host_cli` not in `_KNOWN_HOSTS` falls to step 2 (`resolve_host()` → probe winner). After the fix, `resolve_host(project_root=project_root)` re-reads the same invalid value and raises `HostNotConfigured`, which `init/cli.py:150` catches, so selection drops to step 3 (first detected host with a wired adapter, `_DETECT_ORDER`). Both outcomes pick a detected host; the ordering source differs. Accept it and reword the `default_hosts` docstring (~125-137) step 2 to "`resolve_host(project_root=...)` (`LL_HOST_CLI`/`LL_HOOK_HOST`, then this root's `orchestration.host_cli`, then the probe) — skipped when the configured key is present but unregistered".

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — owns `resolve_host()`, `resolve_host_named()`, `apply_host_cli_from_config()`; `resolve_host()` is the selected choke point (Option B).
- `scripts/little_loops/config/core.py` — one behavior-preserving extraction (Review Decision 12): `BRConfig._load_config`'s body becomes the module function `load_raw_config(project_root)`, which `_load_config` delegates to and the new `_config_host_cli` helper imports function-locally. No other edits (Review Decision 6).
- `scripts/little_loops/fsm/evaluators.py` (~1626), `scripts/little_loops/learning_tests/extractor.py` (~144), `scripts/little_loops/session_store/lifecycle.py` (~176), and `host_runner.py` (~2840/2844) — "CLI not found … (see LL_HOST_CLI)" messages gain `orchestration.host_cli` (Review Decision 10).
- `scripts/tests/conftest.py` — new autouse `_config_host_cli` stub with opt-out (Review Decision 9).
- `scripts/little_loops/init/cli.py` — `default_hosts()` (~149) passes `project_root=project_root` to `resolve_host()` (Review Decision 2); the comment at ~266 claiming `resolve_host()` honors the config key becomes true — reword to name the `project_root` seam.
- `scripts/little_loops/cli/doctor.py` — `apply_host_cli_from_config(cfg)` call at ~1668 and a hand-rolled `os.environ.get("LL_HOST_CLI") or cfg.orchestration.host_cli` at ~816; per Review Decision 1, delete the `:1668` call and collapse `:816` to `resolve_host(project_root=...)`.
- `scripts/little_loops/mcp_server/tools.py` — `_tool_capabilities` (~224, `resolve_host().describe_capabilities()`) passes `project_root=project_root` (Review Decision 2).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/host_runner.py` — `resolve_host()` `env is None` branch (~2661) is the insertion point for the config step (after the `explicit = env.get("LL_HOST_CLI") or env.get("LL_HOOK_HOST")` check at ~2664, before the `_PROBE_ORDER` loop at ~2674); its docstring precedence list (~2642-2647) needs a config step; `_remediation_hint()` already names `orchestration.host_cli` and must keep doing so (`test_raises_when_no_host` pins it). New code must stay inside `resolve_host`/a helper so `resolve_host_named` (`resolve_host({"LL_HOST_CLI": name})`, ~2689-2697) never reaches it [Agent 1 finding]
- `scripts/little_loops/config/orchestration.py` — `OrchestrationConfig` docstring (~96-98) says `apply_host_cli_from_config` exports the key "before `resolve_host()`"; update to the shipped mechanism. It also holds the only existing lazy `config → host_runner` import (`_validate_model_hints`, ~64), so the new `host_runner → config` import must be function-local [Agent 1 finding]
- `scripts/little_loops/init/cli.py` — `default_hosts()` (~144-149) already prefers `existing_config["orchestration"]["host_cli"]` and only falls back to `resolve_host()`; after the fix that fallback reads the **cwd** project's config, not `project_root`'s (`ll-init --root <other>`), and `ll-init` runs before the target has a config. Also `_persist_host_selection` (~555) writes `orchestration.host_cli = hosts[0]`, whose comment relies on `resolve_host()` agreeing [Agent 2 finding]
- `scripts/little_loops/advisor.py` — `consult()` docstring (~237-239) says it is independent of ambient `orchestration.host_cli`/`LL_HOST_CLI` and "Never calls `apply_host_cli_from_config()`"; wording must stay true if `apply_host_cli_from_config` is removed or renamed. Line 286 (`main_host or resolve_host().name`) is an `env is None` caller and is deliberately left config-independent only via `resolve_host_named` at the `--host` seam [Agent 1/2 finding]
- `scripts/little_loops/cli/advise.py` (~100) — mentions `orchestration.host_cli` independence in help/comments; keep consistent [Agent 1 finding]
- `scripts/little_loops/__init__.py` (~121 `__all__`) and `host_runner.py` `__all__` (~73) — export `apply_host_cli_from_config`; if the function is deleted/renamed, both plus `docs/reference/API.md` must change together [Agent 1 finding]

### Dependent Files (Callers/Importers)
- `resolve_host()` callers that read ambient env only today (graph-seeded, grep-confirmed): `subprocess_utils.py:741` (`ll-auto`/`ll-parallel` path), `parallel/worker_pool.py:854`, `fsm/executor.py:3698` (`_resolve_model`) and `:3717` (`_cli_backend_name`), `fsm/evaluators.py:1230/1341/1597`, `fsm/handoff_handler.py:116`, `cli/loop/config_cmds.py:38` (`ll-loop validate`, ENH-3548), `cli/loop/header.py:156`, `cli/loop/summary.py:172`, `runner_spec.py:264/449`, `cli/action.py:343`, `cli/harness.py:1832`, `cli/artifact/discover.py:417`, `cli/artifact/extract.py:167`, `cli/issues/link_epics.py:334`, `cli/issues/decisions.py:912`, `init/cli.py:149/274/363`, `init/install_check.py:87/181`, `advisor.py:286`, `learning_tests/extractor.py:131`, `session_store/lifecycle.py` (3 sites), `mcp_server/tools.py:224`.
- `resolve_host_named()` callers that are **deliberately config-independent**: `advisor.py` (`consult`) and the doctor advisor rows; `test_cli_advise.py::test_advisor_host_env_independent_of_orchestration_host_cli` pins that `LL_HOST_CLI` is unchanged after `main_advise()`.

_Wiring pass added by `/ll:wire-issue`:_
- **Import cycle constraint** — `config/core.py` imports `little_loops.parallel.types` at module level → `parallel/__init__` → `worker_pool` → `host_runner` (`from little_loops.host_runner import resolve_host`), so `config.core` reaches `host_runner` at import time. A top-level `host_runner → config` import closes a cycle; only a function-local import inside `resolve_host` (or a helper it calls) is safe. `little_loops/__init__.py` imports `config` (line 7) before `host_runner` (line 33) [Agent 2 finding]
- **Config-merge helper is not a standalone loader** — merge logic lives in `BRConfig._load_config` (`config/core.py` ~297) using `resolve_config_path` (~158), `parse_local_override_frontmatter` (~64), `deep_merge` (~91), `LOCAL_OVERRIDE_FILENAME` (~61). Constructing `BRConfig` inside `resolve_host` has three hazards the Decision Rationale's "reuse the config-merge helper" must handle: (a) `BRConfig.__init__` runs `load_env_fallback` (`config/core.py` ~293, `env_file.py:65`), an `os.environ` **write** — defeats "no env mutation" and the `resolve_host_named` no-mutation test; (b) `OrchestrationConfig.from_dict` → `_validate_model_hints` can raise `ValueError`, and `json.load` can raise `JSONDecodeError`/`OSError`, so the never-raising wrapper must catch far more than `AttributeError`; (c) `resolve_config_path` (~177) reads `LL_HOOK_HOST` and prepends `.codex/ll-config.json`-style host dirs, so the lookup is itself host-dependent. Preferred shape: a small extracted helper reusing `resolve_config_path` + `parse_local_override_frontmatter` + `deep_merge` that returns only `orchestration.host_cli` (mirror `session_store/db.py::_config_db_path`, ~35-69, which catches `(OSError, JSONDecodeError, ValueError, TypeError, AttributeError)`), plus the `ll.local.md` merge that `_config_db_path` lacks [Agent 1/2 finding]. _(Superseded by Review Decision 12: extract `load_raw_config(project_root)` from `BRConfig._load_config` and call it, rather than re-composing the primitives in `host_runner.py`.)_
- **Alternate target (conditional branch: raw JSON read instead of `BRConfig`)** — touchpoints are `config/core.py` module functions `resolve_config_path`, `deep_merge`, `parse_local_override_frontmatter`, and `paths.find_project_root` (~14, never raises) / `resolve_ll_dir` (~45) [Agent 1 finding]
- **Project-root ambiguity** — `resolve_host()` takes no root argument, so the lookup can only use `Path.cwd()`/`find_project_root()`. Callers that carry an explicit root diverge: `mcp_server/tools.py:224` (`_tool_capabilities(_arguments, *, project_root)`) and `init/cli.py:149` (`default_hosts(project_root, ...)`). Decide whether `resolve_host` gains an optional root/config seam or these accept cwd resolution [Agent 2 finding]
- **Per-call cost** — no caching in `host_runner.py`; hot per-invocation callers: `fsm/evaluators.py:1230/1341/1597` (per LLM eval), `subprocess_utils.py:741` (per host spawn), `parallel/worker_pool.py:854`, `fsm/executor.py:3698/3717` (per prompt state), `cli/harness.py:1832` (`_resolved_host_cli`, 3× per run). A config file read + YAML frontmatter parse on each is new I/O; if cached, key on cwd (see `cli/doctor.py::_probe_advisor_version` `lru_cache` docstring on `monkeypatch.chdir` leakage) [Agent 2 finding]
- **New `HostNotConfigured` raises** — an unregistered config value now raises from `resolve_host()` on every `env is None` path. Callers that do **not** catch it (propagate): `subprocess_utils.run_claude_command` (`test_subprocess_utils.py` asserts propagation), `fsm/evaluators.py` (3 sites), `runner_spec.py:264/449`, `worker_pool.py:854`, `fsm/handoff_handler.py:116`, `cli/action.py:343`, `cli/issues/link_epics.py:334`, `cli/issues/decisions.py:912`, `learning_tests/extractor.py:131`, `cli/artifact/{discover,extract}.py`, `session_store/lifecycle.py` (3 sites), `mcp_server/tools.py:224`, `advisor.consult()` (`resolve_host().name`), and `main_doctor` (`runner = resolve_host()` at ~1669). Callers that catch it: `init/cli.py`, `init/install_check.py`, `cli/loop/header.py:156`, `cli/loop/summary.py:172`, `fsm/executor.py` (`_resolve_model_selection` → `ModelHintError`; `_cli_backend_name` → `None`), `cli/harness.py::_resolved_host_cli` (`except Exception`) [Agent 2 finding]
- `cli/harness.py::_resolved_host_cli` (~1827; used 1867/1890/1901) feeds `conditions.host_cli` into the `harness_events` conditions fingerprint (`conditions_fp`, schema v50), so a configured host now changes baseline-matching fingerprints for users who set the key [Agent 2 finding]
- `scripts/little_loops/user_messages.py:404` (`_resolve_host`), `hooks/__init__.py:224` and `config/core.py:177` read `LL_HOOK_HOST` independently of `host_runner.resolve_host` — a **different** function despite the name; not callers and not to be changed, but scans/greps for `resolve_host` will collide with `_resolve_host` [Agent 1/2 finding]
- No hook handler, `hooks/hooks.json`, `.claude-plugin/plugin.json`, `commands/*.md`, `agents/*.md`, `skills/*/SKILL.md` (bar prose in `skills/explore-api/SKILL.md:89`), or built-in loop YAML references `resolve_host`/`LL_HOST_CLI`/`host_cli` — no manifest registration and no `ll-adapt` mirror regeneration is required [Agent 1/2 finding]

### Conventions in Force
- Host CLI spawns and host selection go through `resolve_host()` — evidence: `.claude/CLAUDE.md` § Host CLI Abstraction; "enumerate every site, keep the chokepoint the only opener" gates at `scripts/tests/test_history_store_chokepoint_gate.py` (AST scan + reasoned `_ALLOWLIST` + allowlist-drift test) and `test_enh3184_spawn_site_guard.py`.
- Explicit env beats config beats default, with config read consumer-side and never raising — evidence: `session_store/db.py::resolve_history_db` (`LL_HISTORY_DB` > `history.db_path` > default), tested by `test_session_store_db.py::test_env_wins_over_config`.
- Construction-time env export where real env wins — evidence: `env_file.py::load_env_fallback` wired into `BRConfig.__init__`; set-but-empty counts as present there, while `apply_host_cli_from_config` treats empty as unset (a divergence).
- Contested: process-wide `os.environ` mutation. `.ll/decisions.d/d17c5448-a58a-49be-a3aa-a66935e50497.json` (FEAT-3060) rejected an `apply_*_from_config()` env helper "mirroring `apply_host_cli_from_config()`" because it leaks into later invocations sharing the process; the `LL_HANDOFF_THRESHOLD`/`LL_CONTEXT_LIMIT` writes in `cli/auto.py`, `cli/parallel.py`, `cli/sprint/run.py`, `cli/loop/run.py` and `apply_host_cli_from_config` itself do mutate env. Any exported `LL_HOST_CLI` is inherited by every descendant (`project_child_env` admits `LL_*` unless credential-shaped).
- Cross-host child spawns override per child via `project_child_env(extra={"LL_HOST_CLI": second_host})` (`cli/loop/summary.py:201`); an exported config value must not defeat that (env-wins early-return preserves it).

### Tests
- `scripts/tests/test_host_runner.py` — `TestResolveHost` (precedence via `env={}`, never touches `os.environ`), `TestApplyHostCliFromConfig`, `TestResolveHostNamed` (asserts no `os.environ` mutation); `test_referenced_env_names_are_covered` regex-scans env-name reads.
- `scripts/tests/test_cli_doctor.py` / `test_cli_doctor_full.py` — patch `apply_host_cli_from_config`; no end-to-end config → host test exists for any entry point (searched: no `host_cli` + `main_loop|main_auto|main_parallel|main_sprint` test).
- `scripts/tests/test_model_hints.py` — dozens of `monkeypatch.setenv("LL_HOST_CLI", ...)`; `no_host` fixture; hint resolution tests must keep passing.
- `scripts/tests/conftest.py` — autouse `_restore_cmd_run_env_vars` scrubs and restores `LL_HOST_CLI`/`LL_HOOK_HOST`, so an in-test env write is undone; `_install_no_live_host_cli` fails tests that spawn a real host CLI.
- AC-4 regression test (Option B): a sole-opener gate modeled on `test_history_store_chokepoint_gate.py` (see the wiring block below); entry-point enumeration (`doc_counts.py::declared_entry_points` used by `test_wiring_cli_registry.py::test_cli_entry_point_coverage`) is not needed under the choke-point mechanism. No existing gate asserts host-config behavior per entry point.

_Wiring pass added by `/ll:wire-issue`:_

_Pre-implementation review 2026-09-28: Review Decision 9's autouse `_config_host_cli` stub neutralizes the exposure below for every test that does not opt out, so the per-test `chdir` fixes listed here are **not required**. The list stays as the inventory of tests that would break if a test opted out, or if the stub were removed._

**Tests that may break — the repo's own `.ll/ll-config.json:152` sets `"orchestration": {"host_cli": "claude-code"}` (tracked via `!/.ll/`), there is no suite-wide cwd isolation (`conftest.py` has no autouse `chdir`; only file-local ones in `test_cli_queue.py`, `test_cli_queue_run.py`, `test_cli_harness.py`), and `_restore_cmd_run_env_vars` scrubs only env, not config. After the fix every `resolve_host()` with `env is None` and no `LL_HOST_CLI`/`LL_HOOK_HOST` resolves `claude-code` from the repo config *before* the probe runs:**
- `scripts/tests/test_model_hints.py` — fixture `no_host` (~357; deletes both env vars, patches `shutil.which` → `None`) now resolves `claude-code` from config instead of raising; breaks `TestPreflight::test_host_not_configured_fails_preflight` (asserts `"no host CLI was found"`) and weakens `test_literal_without_host_runs_and_omits_backend` (~553). Fix: `monkeypatch.chdir(tmp_path)` (config-less) inside `no_host` [Agent 3 finding]
- `scripts/tests/test_init_core.py::TestDetectHosts` — `test_pi_never_primary` (~3641), `test_nothing_detected_defaults_to_claude_code` (~3606), `test_only_pending_hosts_still_listed`, `test_kimi_detected_last`, `test_multiple_hosts_detected` reach `default_hosts()` → `resolve_host()` (`init/cli.py:149`) with `shutil.which` patched; now resolves from repo config (results may coincide by accident). Add `monkeypatch.chdir(tmp_path)` [Agent 3 finding]
- `scripts/tests/test_init_audit_fixes.py::TestHostSelectionPersisted` — review (`default_hosts` patched in one test; `test_existing_host_cli_stays_primary_on_reinit` passes config in) [Agent 3 finding]
- `scripts/tests/test_host_runner.py::TestResolveHost::test_raises_when_no_host` — asserts `"LL_HOST_CLI"` and `"orchestration.host_cli"` in the message; keep `_remediation_hint()` text. Passes `env={}` so unaffected by the env-is-None-only fold-in [Agent 3 finding]
- `scripts/tests/test_host_runner.py::TestApplyHostCliFromConfig` (~2379, 4 tests) and the ~30 `patch("little_loops.host_runner.apply_host_cli_from_config")` sites in `test_cli_doctor.py` plus `test_cli_doctor_full.py:330/352` — break (`AttributeError`) only if `apply_host_cli_from_config` is deleted/renamed; keep the symbol or update all together [Agent 3 finding]
- `scripts/tests/test_cli_doctor_install_checks.py` — `_advisor_data` env > config > fallback tests (`test_independent_main_vs_advisor_resolution_env_first`, `..._config_second`, `..._both_unset_falls_back`, `_FakeBRConfig`/`_FakeOrchestrationConfig`) must stay green or be reshaped if `cli/doctor.py:816` collapses to one resolution path; note the hand-rolled expression ignores `LL_HOOK_HOST` [Agent 3 finding]. **Per Review Decision 1, `:816` does collapse**: `..._config_second` must switch from `_FakeBRConfig` to a tmp `.ll/ll-config.json` + `project_root`, and gain an `LL_HOOK_HOST`-beats-config case.
- `scripts/tests/test_fsm_evaluators.py:1077`, `test_fsm_continuity.py:71` (+ `scripts/tests/spike/fsm_continuity_compaction/test_continuity_pipeline.py:134`), `test_subprocess_utils.py:77/2435/2438/2565`, `test_learning_tests_extractor.py:215/229`, `test_session_store_lifecycle.py:1687`, `test_session_store_schema.py:943` (asserts `row["host"]` populated), `test_cli_harness.py:696`, `test_loop_model_display.py`, `test_handoff_handler.py`, `test_mcp_server.py` — call or depend on real `resolve_host()` with `env is None`; audit each for cwd exposure (agents did not inspect every one) [Agent 1/3 finding]
- `scripts/tests/test_advisor.py` (`resolve_host_named` patches at 171/204/227/244/266/443/624/704), `test_cli_advise.py` (71/147/179/213/243), `test_cli_doctor_install_checks.py` (667-984) — patch `resolve_host_named`; unaffected provided it stays config-independent and never writes `os.environ` [Agent 3 finding]

**New tests to write** (none exist today — searched `scripts/tests` for any test driving `resolve_host()` from config; all 146 `host_cli` hits are parsing/schema/`apply_host_cli_from_config`/mocked):
- `test_host_runner.py::TestResolveHost` — with `env=None`: config beats probe; `LL_HOST_CLI` beats config; `LL_HOOK_HOST` beats config; `ll.local.md` frontmatter overrides `ll-config.json`; malformed/missing config never raises and falls through to probe; unregistered config value raises `HostNotConfigured`; empty-string config treated as unset; `os.environ` unmutated. `resolve_host(env={})` does not consult config; `resolve_host_named` ignores config. Added by review: `project_root=` selects the lookup root (config under `tmp_path/a`, cwd `tmp_path/b` → config honored; `project_root` ignored when `env` is explicit); an explicit `project_root` is not walked upward (Review Decision 13: `project_root=tmp/a/sub` with a stray config-less `tmp/a/sub/.ll/` does not read `tmp/a`'s key; a root with only `.codex/ll-config.json` + `LL_STATE_DIR=.codex` is honored); `LL_STATE_DIR=.codex` selects `<root>/.codex/ll-config.json` over `<root>/.ll/ll-config.json`; a stray config-less `.ll/` dir in a cwd subdirectory shadows the real root → no raise, falls through to probe; `ll-doctor` and `resolve_host()` report the same host with `LL_HOOK_HOST` set and a conflicting config key. Follow `test_session_store_db.py::test_env_wins_over_config` / `test_config_used_when_env_unset` (tmp_path `.ll/ll-config.json` + `monkeypatch.chdir`) and `test_config.py::TestBRConfigLocalOverrides._write_local` [Agent 3 finding]
- End-to-end carrier: `test_fake_host.py::TestRunClaudeCommandEndToEnd::test_default_emission_drives_callbacks` — swap `setenv("LL_HOST_CLI","fake")` for `tmp_path/.ll/ll-config.json` `{"orchestration":{"host_cli":"fake"}}` + `chdir`; `fake` is absent from the schema enum but `OrchestrationConfig.from_dict` does not enforce it. Config-driven `cmd_*` precedent: `test_ll_loop_commands.py` (~341, `request_path` config + `cmd_validate`) [Agent 3 finding]
- AC-4 gate (new file, e.g. `scripts/tests/test_host_resolution_chokepoint_gate.py`) — copy `test_history_store_chokepoint_gate.py`'s structure (`_SRC_ROOT`, `_ALLOWLIST: dict[str,str]` with one-line reasons, AST `ast.walk` scan of `ast.Call` for `resolve_host`, `sorted(_SRC_ROOT.rglob("*.py"))`, allowlist-drift test); use `test_usage_selection_chokepoint_gate.py`'s `(rel, enclosing_function)` key + `test_gate_detects_a_stray_site` self-test if per-function granularity is wanted. `conformance/test_host_composition.py::_RUNNER_BINDING_CALLS`/`_bindings()` is an existing `resolve_host` call recogniser to reuse [Agent 3 finding]. **Superseded by Review Decision 4**: the gate asserts no production `apply_host_cli_from_config` call, no `resolve_host(` with a positional/`env=` argument outside `resolve_host_named`, and no `LL_HOST_CLI` / `.host_cli` read outside `host_runner.py` beyond the reasoned allowlist — not an env-write check and not a per-caller site list.
- Config-side: extend `test_config_schema.py::test_orchestration_host_cli_in_schema` only if the description text changes; `_SCHEMA_DEFAULT_ALLOWLIST` (~1283) already lists `orchestration.host_cli` [Agent 3 finding]

**Gate consumers verified safe** — `test_enh3184_spawn_site_guard.py` pins `host_runner.py` at `(2, 0)` (config read adds no subprocess); `test_host_runner.py::test_referenced_env_names_are_covered` regex-scans `os.environ` literals only (`env.get(...)` on a local dict and `LL_`-prefixed names pass); `conformance/test_host_composition.py::TestExecutorTouchesOnlyAbstractInterface` scans `host_runner.py` for concrete-runner `isinstance`/`.name` literal comparisons — new config code in `resolve_host` must not bind `resolve_host()` results or compare `.binary`/`.name` to literals [Agent 2/3 finding]

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` (~730) — env-var row says `LL_HOST_CLI` "Takes precedence over binary probe and `orchestration.host_cli` config"; the config-vs-probe order is not stated there and must agree with env > config > probe.
- `docs/ARCHITECTURE.md` (~919, ~924), `docs/reference/API.md` (`apply_host_cli_from_config`, `resolve_host`), `docs/reference/CLI.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (~486), `.claude/CLAUDE.md` § Host CLI Abstraction, `scripts/little_loops/config-schema.json` (`orchestration`, `orchestration.host_cli` descriptions) — all assert the precedence; reword the "read by apply_host_cli_from_config() before resolve_host() runs" claims to the selected mechanism (`resolve_host()` reads the config key itself on the ambient-env path, env > `LL_HOOK_HOST` > config > probe).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` host-runner table — `resolve_host()` row ("honors `LL_HOST_CLI` / `orchestration.host_cli` overrides"), `apply_host_cli_from_config()` row ("exports it as `LL_HOST_CLI` before `resolve_host()` runs"), `HostNotConfigured` row [Agent 2 finding]
- `docs/reference/API.md` `little_loops.host_runner` — `### apply_host_cli_from_config` ("Typically called once at startup by orchestration entry points"); `### resolve_host` "Detection order" list has no config step (and already omits kimi/qwen from the probe order — fix together); `HostNotConfigured` entry; advisor entry ~12476 ("Never calls `apply_host_cli_from_config()`"); `detect_installation` ~12359 / `fetch_latest_plugin` ~12393 descriptions. Gate: `test_wiring_reference_docs.py` requires `resolve_host` and `HostNotConfigured` to remain in API.md [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `orchestration.host_cli` row ("Mirrors the `LL_HOST_CLI` environment variable; env var takes precedence if both are set") and `advisor.host` row ("same enum as `orchestration.host_cli`") [Agent 2 finding]
- `docs/reference/CLI.md` — `ll-init` (primary is existing `orchestration.host_cli`, else `resolve_host()`'s pick — now also config-derived), `ll-advise` (~201, "never calls `apply_host_cli_from_config()`"), artifact-extract paragraph (~5647, "never overrides `resolve_host()`'s ambient host selection") [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` `### HostNotConfigured` — Cause names only `LL_HOST_CLI`/`LL_HOOK_HOST` and the probe; add the config key. `test_wiring_guides_and_meta.py` pins `HostNotConfigured`/`FEAT-1462` here [Agent 2 finding]
- `docs/guides/MCP_SERVER_GUIDE.md` (~306, capabilities tool host source), `docs/guides/GETTING_STARTED.md` (~112), `docs/generalized-fsm-loop.md` (~1930, "`resolve_host()` returns the default `ClaudeCodeRunner` when `claude` is on PATH") [Agent 2 finding]
- Host docs with parallel precedence wording: `docs/codex/usage.md` (~19; `test_wiring_guides_and_meta.py` pins `LL_HOST_CLI=codex` here), `docs/qwen/{getting-started,automation}.md`, `docs/kimi/{getting-started,automation}.md`, `docs/codex/README.md`, `docs/development/CONFORMANCE.md`, `docs/guides/EVALUATION_GUIDE.md` [Agent 1/2 finding] — **verify only** (Review Decision 8): edit only where they describe the mechanism, not where they state env > config > probe.
- `AGENTS.md` § Host CLI Abstraction — Codex-flavored copy of the `.claude/CLAUDE.md` block; edit in step if the CLAUDE.md wording changes (`init/writers.py` renders the consumer CLAUDE.md block separately, ~211) [Agent 2 finding]
- Docs edits here trip no `ll-adapt` mirror gate and no skill 500-line cap (`commands/`, `skills/`, `README.md`, `scripts/README.md`, `CONTRIBUTING.md` have no matches); `test_docs_audience_gate.py` forbids `scripts/tests/…` paths in `docs/` [Agent 2 finding]

### Configuration
- `scripts/little_loops/config/orchestration.py` — `OrchestrationConfig.host_cli: str | None`, loaded unvalidated via `data.get("host_cli")`; `.ll/ll.local.md` frontmatter deep-merges over `ll-config.json`, so the value can come from the local override.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` — `orchestration` description (~1806, "read by apply_host_cli_from_config() before resolve_host() runs") and `orchestration.host_cli` (~1808-1811, "Mirrors the LL_HOST_CLI environment variable; env var takes precedence"): reword to env > `LL_HOOK_HOST` > config > probe. No test snapshots the description text, so this is not test-enforced [Agent 2/3 finding]
- `.ll/ll-config.json:152` — this repo's own `"host_cli": "claude-code"` will be picked up by the fold-in for any `env is None` call run from the repo cwd (see Tests) [Agent 1 finding]
- `.claude/CLAUDE.md` § Host CLI Abstraction — already states "(or `orchestration.host_cli`)"; becomes true after the fix, no edit needed unless `apply_host_cli_from_config` is removed [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- `ll-issues format-check` reports three `stale_file_ref` hits that are intentional, not drift: `scripts/tests/test_host_resolution_chokepoint_gate.py` is the not-yet-created AC-4 gate; `.codex/ll-config.json` and `tmp_path/.ll/ll-config.json` are illustrative host-dir / test-fixture paths, not repo files; `.claude/settings.local.json` (Review Decision 7) is a quoted worktree copy-list entry, gitignored by design. All other referenced files and the `host_runner.py` anchors (`resolve_host` `:2637`, `explicit` check `:2664`, `_PROBE_ORDER` loop `:2674`, `apply_host_cli_from_config` `:2937`) and `cli/doctor.py` anchors (`:816`, `:1668`) resolve on disk today.
- `missing_behavior_parity` flags `docs/reference/API.md`, but that file is reworded rather than rewritten, deleted, or delegated away, so no `### Behavior Parity` table applies. `behavior_parity_not_applicable: true` is a human decision; refine does not set it.

## Program Design

### Types
- `OrchestrationConfig.host_cli: str | None` — existing field (`scripts/little_loops/config/orchestration.py`); no new data shape is required by any option.

### Signatures
- `resolve_host(env: dict[str, str] | None = None, *, project_root: Path | None = None) -> HostRunner` — `host_runner.py` (**changed**: new keyword-only `project_root`, Review Decision 2); when `env is None` it snapshots `dict(os.environ)` and, after the env check, reads `orchestration.host_cli` from the config found by walking up from `project_root` (default `Path.cwd()`); an explicit `env` is a testability/independence seam (`resolve_host_named` passes `{"LL_HOST_CLI": name}`) and skips the config step, ignoring `project_root`.
- `_config_host_cli(project_root: Path | None) -> tuple[str, Path] | None` — `host_runner.py` (**new**, private; function-local imports of `load_raw_config` and `resolve_config_path` from `little_loops.config.core` and `resolve_ll_dir` from `little_loops.paths`) — uses an explicit `project_root` as-is, and walks upward from `Path.cwd()` via `resolve_ll_dir` only when `project_root` is `None` (Review Decision 13); returns the merged `orchestration.host_cli` value and the config path it came from (for the Review Decision 10 error message), or `None`; never raises; never writes `os.environ`; empty string → `None`. Stubbed to `None` suite-wide by the autouse fixture (Review Decision 9).
- `load_raw_config(project_root: Path) -> dict[str, Any]` — `config/core.py` (**new**, extracted verbatim from `BRConfig._load_config`, Review Decision 12) — `resolve_config_path` + `json.load` + `<root>/.ll/ll.local.md` frontmatter `deep_merge`; pure apart from the env reads inside `resolve_config_path`; raises what `_load_config` raises today.
- `resolve_host_named(name: str) -> HostRunner` — `host_runner.py`; unchanged; must remain independent of ambient env and config.
- `apply_host_cli_from_config(config: object) -> None` — `host_runner.py`; body unchanged; docstring marked deprecated; zero production callers after the fix (Review Decision 1).

### Call Path

_Post-fix path. Entry points (`ll-loop run`, `ll-auto`, `ll-parallel`, `ll-sprint`) are unmodified; they reach the choke point through these existing callers:_

`FSMExecutor._preflight_model_hints` -> `FSMExecutor._resolve_model` -> `resolve_host` -> `_config_host_cli` -> `load_raw_config` -> `resolve_config_path`

`run_claude_command` -> `resolve_host` -> `_config_host_cli` -> `load_raw_config` -> `parse_local_override_frontmatter`

`default_hosts` -> `resolve_host` (with `project_root`) -> `_config_host_cli` -> `load_raw_config` -> `deep_merge`

`BRConfig._load_config` -> `load_raw_config` (extraction; behavior unchanged)

### Decision Rules
- Precedence: non-empty `LL_HOST_CLI` > `LL_HOOK_HOST` (decided 2026-09-28: stays directly after `LL_HOST_CLI`, above config) > non-empty `orchestration.host_cli` > `_PROBE_ORDER` probe.
- Empty-string values are treated as unset (matches `resolve_host` and `apply_host_cli_from_config`).
- An unregistered config value raises `HostNotConfigured` in `resolve_host` (no fallback to probe), same as an unregistered `LL_HOST_CLI`; its message names `orchestration.host_cli` and the config file path (Review Decision 10).
- `resolve_host_named` and `ll-advise`/`advisor.consult` stay config-independent.
- The config step runs only when `env is None`; it reads config at `project_root` exactly when given (no upward walk), else at the project root resolved upward from `Path.cwd()` (Review Decision 13). Callers with a known root (`init/cli.py:149` `default_hosts`, `mcp_server/tools.py:224`, `cli/doctor.py:816`) pass it.
- Config file selection follows `resolve_config_path`, so `LL_STATE_DIR` (e.g. `.codex`) can redirect the lookup; `LL_HOOK_HOST` cannot, because it wins before the config step.
- No caching; each call re-reads config (Review Decision 3).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- Every Call Path above terminates at `resolve_host()` (`host_runner.py:2637`), which gains the config step on its `env is None` branch (after the `explicit = env.get("LL_HOST_CLI") or env.get("LL_HOOK_HOST")` check at `:2664`, before the `_PROBE_ORDER` loop at `:2674`). _(Updated by pre-implementation review 2026-09-28: the Call Path was rewritten from the pre-fix entry-point reach to the post-fix path; the unmodified entry points and rejected Option A/C wiring points are listed in Review Decision 6.)_

## Implementation Steps

0. Land test isolation first: add the autouse `_config_host_cli` stub with opt-out to `scripts/tests/conftest.py` (Review Decision 9). It can land before the helper exists by patching with `raising=False`, or in the same commit as step 1.
1. Extract `load_raw_config(project_root)` from `BRConfig._load_config` in `config/core.py` and make `_load_config` delegate to it (Review Decision 12); the existing `test_config.py` suite must stay green unchanged. Then fold the config lookup into `resolve_host()` (Option B, selected): add keyword-only `project_root: Path | None = None`; on the `env is None` path only, after the `LL_HOST_CLI`/`LL_HOOK_HOST` check and before the `_PROBE_ORDER` probe, call the new private `_config_host_cli(project_root)` helper (function-local import of `load_raw_config`; never raises; never writes `os.environ`; empty string → unset; no cache). `resolve_host()` reached from `ll-loop run`, `ll-loop validate`, `ll-auto`, `ll-parallel`, `ll-sprint` then returns the configured host when `LL_HOST_CLI`/`LL_HOOK_HOST` are unset — verified by choke-point tests in `test_host_runner.py::TestResolveHost` (opted out of the stub; no per-entry-point tests needed).
1a. Error messages (Review Decision 10): the config-sourced `HostNotConfigured` names `orchestration.host_cli` and the config path; the four "CLI not found … (see LL_HOST_CLI)" messages add `orchestration.host_cli`.
2. Pass the known root at the three root-carrying callers: `init/cli.py:149` (`default_hosts(project_root, ...)`), `mcp_server/tools.py:224` (`project_root`), `cli/doctor.py:816`. Reword the `default_hosts` docstring step 2 per Review Decision 14.
3. `ll-doctor`: delete the `apply_host_cli_from_config(cfg)` call (~1668) and replace the hand-rolled `:816` resolution with `resolve_host(project_root=...)`, so doctor honors `LL_HOOK_HOST` > config like every other path. Mark `apply_host_cli_from_config` deprecated in its docstring (keep it exported).
4. `FSMExecutor._preflight_model_hints`/`_resolve_model` and `initial_model_display` resolve against the configured host — verified in `scripts/tests/test_model_hints.py` by one new opted-out test that writes a tmp `.ll/ll-config.json`; existing tests (including the `no_host` fixture) are protected by the autouse stub and need no `chdir`.
5. A gate test (`test_host_resolution_chokepoint_gate.py`) asserts no production `apply_host_cli_from_config` call, no `resolve_host(` with a positional/`env=` argument outside `resolve_host_named`, and no `LL_HOST_CLI` / `.host_cli` read outside `host_runner.py` beyond a reasoned allowlist; plus allowlist-drift and stray-site self-tests (Review Decision 4).
6. `ll-advise`/`resolve_host_named` remain config-independent (`test_advisor_host_env_independent_of_orchestration_host_cli` still passes) and `ll-loop run`'s cross-host child override (`summary.py:201`) still wins.
7. Comments/docs listed under Integration Map → Documentation agree with the shipped mechanism (mechanism-describing docs only, Review Decision 8); `python -m pytest scripts/tests/` exits 0.
8. Before merging, run the rollout survey (Review Decision 11): list every local little-loops project's effective `orchestration.host_cli`, confirm each binary is on PATH, fix mismatches, and record the result in the Resolution section.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add the config step inside `resolve_host()`'s `env is None` branch in `scripts/little_loops/host_runner.py` via a function-local import (never top-level: `config.core` → `parallel.types` → `worker_pool` → `host_runner` already cycles at import time); the helper must catch `OSError`, `JSONDecodeError`, `ValueError`, `TypeError`, `AttributeError`, never construct the full config object (its env-fallback loader writes `os.environ`; Review Decision 6), honor `.ll/ll.local.md` by calling the extracted `load_raw_config` (Review Decision 12), and treat empty string as unset
- ~~Decide cwd-vs-`project_root` semantics and caching~~ — **decided** (Review Decisions 2, 3): `project_root` keyword seam passed by `mcp_server/tools.py:224` and `init/cli.py:149`; no caching
- ~~Collapse `cli/doctor.py:816` and decide whether `apply_host_cli_from_config` at `:1668` stays~~ — **decided** (Review Decision 1): collapse `:816` to `resolve_host(project_root=...)`, delete the `:1668` call, keep the symbol deprecated (so `__all__`, `TestApplyHostCliFromConfig`, and the ~30 `patch(...)` sites need no edit)
- ~~Update `test_model_hints.py` `no_host` and `test_init_core.py::TestDetectHosts` with `chdir`; audit the other `env is None` tests~~ — **replaced** (Review Decision 9): one autouse `_config_host_cli` stub in `scripts/tests/conftest.py` keeps the repo's `.ll/ll-config.json` (`host_cli: claude-code`) out of every test that does not opt out
- Add `TestResolveHost` config-precedence cases in `scripts/tests/test_host_runner.py`, an end-to-end `fake`-host config test in `scripts/tests/test_fake_host.py`, and the AC-4 site gate (new `scripts/tests/test_host_resolution_chokepoint_gate.py` modeled on `test_history_store_chokepoint_gate.py`)
- Update comments/docstrings: `host_runner.py` `resolve_host`/`apply_host_cli_from_config` docstrings, `config/orchestration.py` `OrchestrationConfig` docstring, `init/cli.py` (~133, ~266), `advisor.py` `consult()` docstring
- Update `config-schema.json` (`orchestration`, `orchestration.host_cli` descriptions) and docs: `docs/ARCHITECTURE.md`, `docs/reference/{API,CONFIGURATION,CLI,HOST_COMPATIBILITY}.md`, `docs/development/TROUBLESHOOTING.md`, `docs/guides/{HARNESS_OPTIMIZATION,MCP_SERVER,GETTING_STARTED}_GUIDE.md`, `docs/generalized-fsm-loop.md`, `AGENTS.md`; verify-only for `docs/{codex,qwen,kimi}/*`, `docs/development/CONFORMANCE.md`, `docs/guides/EVALUATION_GUIDE.md` (Review Decision 8)

## Impact

- **Priority**: P2 — documented config key silently has no effect on the main automation paths.
- **Effort**: Large (matches `size:`). The code change is small (one extracted loader, one helper, one branch in `resolve_host()`, three root-passing callers, the doctor collapse, five error-message strings); the size comes from the new `TestResolveHost` cases, the chokepoint gate, and ~12 mechanism-describing docs. The former ~20-file test cwd audit is replaced by the single autouse stub (Review Decision 9).
- **Risk**: Medium–High. Blast radius is every **initialized** project, not just users who hand-set the key: `_persist_host_selection` (`init/cli.py:555`) writes `orchestration.host_cli` on every `ll-init`, auto-detection included, so after the fix config replaces the probe almost everywhere. Because all local projects on this machine are `local-editable` against this checkout, they switch the moment this lands. Failure mode: a project initialized as `claude-code` whose user now has only `codex` installed will fail on the configured binary instead of falling back to the probe. `cli/harness.py`'s `conditions_fp` fingerprint also shifts for those projects. Worktree children in consumer projects with an untracked `ll-config.json` still fall back to the probe (Review Decision 7, out of scope).

## Steps to Reproduce

1. Set `"orchestration": {"host_cli": "codex"}` in `.ll/ll-config.json`, leave `LL_HOST_CLI` unset, have both `claude` and `codex` on PATH.
2. Run `ll-doctor` — applies the config key before resolving the host.
3. Run any loop with `ll-loop run` — dispatches to the probe winner, not `codex` (unless `codex` happens to win the probe).

## Acceptance Criteria

- [ ] With `LL_HOST_CLI` unset and `orchestration.host_cli` set, `resolve_host()` (ambient-env path) as reached from `ll-loop run`, `ll-loop validate` (`cli/loop/config_cmds.py:38`), `ll-auto`, `ll-parallel` and `ll-sprint` selects the configured host, not the probe winner. (`ll-logs fleet-review` does not call `host_runner.resolve_host()`.)
- [ ] `LL_HOST_CLI` and `LL_HOOK_HOST` still override the config key; with none set, the probe order is unchanged; `resolve_host_named()` and `resolve_host(env={...})` stay config-independent and `os.environ` is never mutated.
- [ ] `FSMExecutor._preflight_model_hints` and ENH-3548's validate-time hint warnings resolve against the configured host.
- [ ] `ll-doctor` and `resolve_host()` report the same host in all precedence cases, including `LL_HOOK_HOST` set alongside a conflicting `orchestration.host_cli`; `ll-doctor` no longer calls `apply_host_cli_from_config`.
- [ ] `resolve_host(project_root=...)` reads config at exactly that root (no upward walk, Review Decision 13) rather than cwd; `ll-init --root <dir>` and the MCP server (`LL_MCP_PROJECT_ROOT`) resolve against their own root, and a `project_root` whose config lives only in a host state dir (`.codex/`, via `LL_STATE_DIR`) is honored.
- [ ] `load_raw_config(project_root)` is extracted from `BRConfig._load_config`, which delegates to it; `test_config.py` passes unchanged and a direct `load_raw_config` test exists (Review Decision 12).
- [ ] `scripts/tests/conftest.py` has an autouse fixture stubbing `host_runner._config_host_cli` to `None`, with an opt-out used by every test that exercises the config step (Review Decision 9).
- [ ] A `HostNotConfigured` raised for an unregistered config value names `orchestration.host_cli` and the config file path; the five "CLI not found … (see LL_HOST_CLI)" messages (`host_runner.py` ×2, `fsm/evaluators.py`, `learning_tests/extractor.py`, `session_store/lifecycle.py`) read "(see LL_HOST_CLI / orchestration.host_cli)", with tests asserting the old text updated (Review Decision 10).
- [ ] `default_hosts` docstring reflects the config-aware step 2 and the invalid-key skip (Review Decision 14).
- [ ] Before merge, the rollout survey (each local little-loops project's effective `orchestration.host_cli` and whether its binary is on PATH) is recorded in the Resolution section, with mismatches fixed (Review Decision 11).
- [ ] A regression gate proves new code cannot bypass the config key: no production `apply_host_cli_from_config` call, no `resolve_host(` with a positional/`env=` argument outside `resolve_host_named`, and no `LL_HOST_CLI` / `.host_cli` read outside `host_runner.py` beyond a reasoned allowlist.

## Related

- ENH-3548 (done) calls `resolve_host()` in `cmd_validate` (`cli/loop/config_cmds.py:38`) for validate-time hint warnings so `validate` and `run` agree; it inherits this fix automatically.

## Verification Notes

Verdict at time of check: **CLAIMS_OUTDATED** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

_`--from-evidence` pass (2026-09-28): re-checked only the claims listed in `verify_evidence`._

- `host_runner.py` anchors in Codebase Research Findings / Program Design shifted +5 lines (uncommitted ENH-3533 `ModelHintUnmappedError` edit): `resolve_host` `:2632` → `:2637`, `explicit` check `:2659` → `:2664`, `_PROBE_ORDER` loop `:2669` → `:2674`, `apply_host_cli_from_config` `:2932` → `:2937`.
- Integration Map wiring pass: `env is None` branch `~2656` → `~2661`, docstring precedence list `~2637-2642` → `~2642-2647`, `resolve_host_named` `~2692` → `~2689-2697`.

### Full-sweep pass (2026-09-29, `--auto`)

Verdict at time of check: **CLAIMS_OUTDATED** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

Graph: provider=`codegraph` freshness=`fresh` (not needed to decide any verdict; all claims were positive, grep-confirmed).

- `cli/doctor.py` anchors had drifted after ENH-3548's doctor edit (626586dc3): the `apply_host_cli_from_config(cfg)` call `:1438` → `:1668` (import `:1616`, `runner = resolve_host()` `:1669`, formerly `~1439`); the hand-rolled `os.environ.get("LL_HOST_CLI") or cfg.orchestration.host_cli` `:815` → `:816`. Rewritten in place everywhere they were cited (Codebase Research Findings, Review Decisions, Integration Map, Program Design, Implementation Steps).
- Confirmed still accurate: `host_runner.py` anchors (`resolve_host` `:2637`, `explicit` `:2664`, `_PROBE_ORDER` loop `:2674`, `resolve_host_named` `:2689-2697`, `apply_host_cli_from_config` `:2937`, its `LL_HOST_CLI` early-return `:2954`); `apply_host_cli_from_config`'s only production caller is `cli/doctor.py` (other hits are docstrings, `__all__`, schema text); every listed `resolve_host()` caller line; `config/core.py:177-178` (`LL_HOOK_HOST`/`LL_STATE_DIR`) and `:293` (`load_env_fallback`); `parallel/types.py:436` copy list; `.ll/ll-config.json:152` (`host_cli: claude-code`, tracked); ENH-3548 `done`.
- Decisions rules: no active required rules. `ll-verify-evidence`: clean.
- Proposal-vs-code check (B6): no new findings beyond those already recorded in Review Decisions.

## Status

**Open** | Created: 2026-09-28 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-28; re-scored after Review Decisions 13–14 and the expanded Acceptance Criteria_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE (1 below `outcome_threshold` 65)

Score movement: Ambiguity 18 → 25 (Decisions 13/14 close the last open semantics — explicit-root walk and `default_hosts` invalid-key behavior; the design is fully specified). Complexity 14 and Change surface 0 are unchanged: they are structural (≈10 code sites + ≈12 docs; ≈45 `resolve_host()` callers), and no further refinement moves them. Splitting the docs sweep out would not raise the score either — code sites alone stay in the 6–15 Breadth band.

### Outcome Risk Factors
- Very wide blast radius: `resolve_host()` has ~45 callers and a new `HostNotConfigured` raise path for unregistered config values reaches many callers that do not catch it. Mitigated by Review Decision 9's autouse stub (existing tests behave as before) and by `default_hosts`'s existing `except HostNotConfigured`.
- Broad enumeration across ~10 source files and ~12 docs; only `_config_host_cli` (explicit-root vs cwd-walk branch, never-raise merge with `ll.local.md`, function-local import) and the `load_raw_config` extraction are deep-ish.
- Behavior change for every initialized project: `_persist_host_selection` writes `orchestration.host_cli` on `ll-init`, so config replaces the probe almost everywhere (and shifts `conditions_fp` in `cli/harness.py`). De-risk by landing the helper + `TestResolveHost` cases first and running the full suite before the doc sweep; gate the merge on the Review Decision 11 rollout survey.

## Session Log
- `/ll:confidence-check` - 2026-09-29T01:27:01 - `fc5cf224-27c3-40f1-8803-a8425dc67494.jsonl`
- `/ll:confidence-check` - 2026-09-29T01:23:09 - `c5893263-4612-4e05-8393-5c50bbf6e762.jsonl`
- `/ll:confidence-check` - 2026-09-29T01:16:27 - `131c2394-4cc5-4b4d-9669-297e9e6feb30.jsonl`
- `/ll:confidence-check` - 2026-09-29T00:50:34 - `9a024917-61ed-49b3-a021-72845a8bcfc2.jsonl`
- `/ll:verify-issues` - 2026-09-29T00:37:37 - `5b5d1874-2832-4b4f-9528-f02ed025e782.jsonl`
- `/ll:confidence-check` - 2026-09-28T23:09:06 - `0cabf8b0-30fa-4125-87cd-02095d27dc98.jsonl`
- `/ll:verify-issues` - 2026-09-28T23:07:11 - `60c95e8d-f486-4f2e-819a-f8c027578985.jsonl`
- `/ll:verify-issues` - 2026-09-28T23:05:22 - `cd8153a1-e80f-45fa-b326-e98f2e9e2120.jsonl`
- `/ll:verify-issues` - 2026-09-28T23:04:03 - `45e76fc6-39f5-4ed4-89bc-374b89f76543.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-28T23:01:54 - `25dca91f-acf1-4079-ba40-cbb10c6ed283.jsonl`
- `/ll:verify-issues` - 2026-09-28T23:00:27 - `b022db67-3202-43f7-b48b-f6b56006bea6.jsonl`
- `/ll:reconcile-issue` - 2026-09-28T22:58:37 - `bd0c73c7-9862-4c60-bd9e-9b392b7afaf8.jsonl`
- `/ll:wire-issue` - 2026-09-28T22:55:33 - `937a6b3a-b00c-40f0-99a6-4ffdf6cec5e8.jsonl`
- `/ll:decide-issue` - 2026-09-28T22:46:35 - `77c339e9-8806-4a53-a734-a18593a275bb.jsonl`
- `/ll:refine-issue` - 2026-09-28T22:43:07 - `29b6f7a1-cbe3-4641-a1f5-b4e98b2d2120.jsonl`
