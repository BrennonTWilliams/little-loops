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

- Scope note: `ll-logs fleet-review` and `ll-loop validate` do not call `host_runner.resolve_host()` today. `fleet-review --host` resolves a session-log host through `user_messages._resolve_host` (flag > `LL_HOOK_HOST` > default), unrelated to host-CLI selection, and `cmd_validate` (`cli/loop/config_cmds.py`) has no `resolve_host` call until ENH-3548 adds one. Acceptance Criterion 1 is vacuous for those two until then; they are only affected through ENH-3548's hint warnings.
- Related latent inconsistency: `cli/doctor.py:815` hand-rolls env > config for the advisor floor row and then calls `resolve_host_named(name)` or `resolve_host()`; a choke-point fix should let it collapse to one resolution path.

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
- Option A: only `main_doctor` calls `apply_host_cli_from_config` (`cli/doctor.py:1438`); `LL_HANDOFF_THRESHOLD` per-entry writes are precedent, but ~20 `resolve_host()` entry points (`cli/action.py`, `cli/harness.py`, `cli/artifact/*`, `mcp_server/tools.py`, …) would each need the call, and it re-creates the FEAT-3060-rejected env leak.
- Option B: `db.py::_resolve_db_path` (l.105-117) is a direct env > config > default template; `host_runner.py` has no top-level config import so a lazy import avoids a cycle; `resolve_host_named` passes explicit `env` and stays independent.
  > **Selected:** Option B — per the Decision Rationale above
- Option C: `BRConfig.__init__` → `load_env_fallback` (`config/core.py:293`) is a wiring point, but ~55 source-file constructions (incl. `cli/advise.py`) would export `LL_HOST_CLI`, failing `test_cli_advise.py:153` and widening the leak.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — owns `resolve_host()`, `resolve_host_named()`, `apply_host_cli_from_config()`; the choke-point candidate.
- `scripts/little_loops/config/core.py` — `BRConfig.__init__` already runs `load_env_fallback(self.project_root)` before parsing, the only construction-time `os.environ` side effect (Option C site — not selected; see Decision Rationale).
- `scripts/little_loops/cli/loop/__init__.py` (`main_loop`, `BRConfig(Path.cwd())` at ~56), `cli/auto.py` (`main_auto`, ~77), `cli/parallel.py` (`main_parallel`, ~196), `cli/sprint/__init__.py` (`main_sprint`, ~242) — per-CLI sites (Option A — not selected; no edits required under Option B).
- `scripts/little_loops/init/cli.py` — comment at ~266 claims `resolve_host()` honors the config key; must be true or corrected after the fix.
- `scripts/little_loops/cli/doctor.py` — `main_doctor` (`apply_host_cli_from_config` at ~1438) and a hand-rolled `os.environ.get("LL_HOST_CLI") or cfg.orchestration.host_cli` at ~815; must stay consistent with whatever becomes canonical.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/host_runner.py` — `resolve_host()` `env is None` branch (~2656) is the insertion point for the config step (after the `explicit = env.get("LL_HOST_CLI") or env.get("LL_HOOK_HOST")` check at ~2659, before the `_PROBE_ORDER` loop at ~2669); its docstring precedence list (~2637-2642) needs a config step; `_remediation_hint()` already names `orchestration.host_cli` and must keep doing so (`test_raises_when_no_host` pins it). New code must stay inside `resolve_host`/a helper so `resolve_host_named` (`resolve_host({"LL_HOST_CLI": name})`, ~2692) never reaches it [Agent 1 finding]
- `scripts/little_loops/config/orchestration.py` — `OrchestrationConfig` docstring (~96-98) says `apply_host_cli_from_config` exports the key "before `resolve_host()`"; update to the shipped mechanism. It also holds the only existing lazy `config → host_runner` import (`_validate_model_hints`, ~64), so the new `host_runner → config` import must be function-local [Agent 1 finding]
- `scripts/little_loops/init/cli.py` — `default_hosts()` (~144-149) already prefers `existing_config["orchestration"]["host_cli"]` and only falls back to `resolve_host()`; after the fix that fallback reads the **cwd** project's config, not `project_root`'s (`ll-init --root <other>`), and `ll-init` runs before the target has a config. Also `_persist_host_selection` (~555) writes `orchestration.host_cli = hosts[0]`, whose comment relies on `resolve_host()` agreeing [Agent 2 finding]
- `scripts/little_loops/advisor.py` — `consult()` docstring (~237-239) says it is independent of ambient `orchestration.host_cli`/`LL_HOST_CLI` and "Never calls `apply_host_cli_from_config()`"; wording must stay true if `apply_host_cli_from_config` is removed or renamed. Line 286 (`main_host or resolve_host().name`) is an `env is None` caller and is deliberately left config-independent only via `resolve_host_named` at the `--host` seam [Agent 1/2 finding]
- `scripts/little_loops/cli/advise.py` (~100) — mentions `orchestration.host_cli` independence in help/comments; keep consistent [Agent 1 finding]
- `scripts/little_loops/__init__.py` (~121 `__all__`) and `host_runner.py` `__all__` (~73) — export `apply_host_cli_from_config`; if the function is deleted/renamed, both plus `docs/reference/API.md` must change together [Agent 1 finding]

### Dependent Files (Callers/Importers)
- `resolve_host()` callers that read ambient env only today (graph-seeded, grep-confirmed): `subprocess_utils.py:741` (`ll-auto`/`ll-parallel` path), `parallel/worker_pool.py:854`, `fsm/executor.py:3698` (`_resolve_model`) and `:3717` (`_cli_backend_name`), `fsm/evaluators.py:1230/1341/1597`, `fsm/handoff_handler.py:116`, `cli/loop/header.py:156`, `cli/loop/summary.py:172`, `runner_spec.py:264/449`, `cli/action.py:343`, `cli/harness.py:1832`, `cli/artifact/discover.py:417`, `cli/artifact/extract.py:167`, `cli/issues/link_epics.py:334`, `cli/issues/decisions.py:912`, `init/cli.py:149/274/363`, `init/install_check.py:87/181`, `advisor.py:286`, `learning_tests/extractor.py:131`, `session_store/lifecycle.py` (3 sites), `mcp_server/tools.py:224`.
- `resolve_host_named()` callers that are **deliberately config-independent**: `advisor.py` (`consult`) and the doctor advisor rows; `test_cli_advise.py::test_advisor_host_env_independent_of_orchestration_host_cli` pins that `LL_HOST_CLI` is unchanged after `main_advise()`.

_Wiring pass added by `/ll:wire-issue`:_
- **Import cycle constraint** — `config/core.py` imports `little_loops.parallel.types` at module level → `parallel/__init__` → `worker_pool` → `host_runner` (`from little_loops.host_runner import resolve_host`), so `config.core` reaches `host_runner` at import time. A top-level `host_runner → config` import closes a cycle; only a function-local import inside `resolve_host` (or a helper it calls) is safe. `little_loops/__init__.py` imports `config` (line 7) before `host_runner` (line 33) [Agent 2 finding]
- **Config-merge helper is not a standalone loader** — merge logic lives in `BRConfig._load_config` (`config/core.py` ~297) using `resolve_config_path` (~158), `parse_local_override_frontmatter` (~64), `deep_merge` (~91), `LOCAL_OVERRIDE_FILENAME` (~61). Constructing `BRConfig` inside `resolve_host` has three hazards the Decision Rationale's "reuse the config-merge helper" must handle: (a) `BRConfig.__init__` runs `load_env_fallback` (`config/core.py` ~293, `env_file.py:65`), an `os.environ` **write** — defeats "no env mutation" and the `resolve_host_named` no-mutation test; (b) `OrchestrationConfig.from_dict` → `_validate_model_hints` can raise `ValueError`, and `json.load` can raise `JSONDecodeError`/`OSError`, so the never-raising wrapper must catch far more than `AttributeError`; (c) `resolve_config_path` (~177) reads `LL_HOOK_HOST` and prepends `.codex/ll-config.json`-style host dirs, so the lookup is itself host-dependent. Preferred shape: a small extracted helper reusing `resolve_config_path` + `parse_local_override_frontmatter` + `deep_merge` that returns only `orchestration.host_cli` (mirror `session_store/db.py::_config_db_path`, ~35-69, which catches `(OSError, JSONDecodeError, ValueError, TypeError, AttributeError)`), plus the `ll.local.md` merge that `_config_db_path` lacks [Agent 1/2 finding]
- **Alternate target (conditional branch: raw JSON read instead of `BRConfig`)** — touchpoints are `config/core.py` module functions `resolve_config_path`, `deep_merge`, `parse_local_override_frontmatter`, and `paths.find_project_root` (~14, never raises) / `resolve_ll_dir` (~45) [Agent 1 finding]
- **Project-root ambiguity** — `resolve_host()` takes no root argument, so the lookup can only use `Path.cwd()`/`find_project_root()`. Callers that carry an explicit root diverge: `mcp_server/tools.py:224` (`_tool_capabilities(_arguments, *, project_root)`) and `init/cli.py:149` (`default_hosts(project_root, ...)`). Decide whether `resolve_host` gains an optional root/config seam or these accept cwd resolution [Agent 2 finding]
- **Per-call cost** — no caching in `host_runner.py`; hot per-invocation callers: `fsm/evaluators.py:1230/1341/1597` (per LLM eval), `subprocess_utils.py:741` (per host spawn), `parallel/worker_pool.py:854`, `fsm/executor.py:3698/3717` (per prompt state), `cli/harness.py:1832` (`_resolved_host_cli`, 3× per run). A config file read + YAML frontmatter parse on each is new I/O; if cached, key on cwd (see `cli/doctor.py::_probe_advisor_version` `lru_cache` docstring on `monkeypatch.chdir` leakage) [Agent 2 finding]
- **New `HostNotConfigured` raises** — an unregistered config value now raises from `resolve_host()` on every `env is None` path. Callers that do **not** catch it (propagate): `subprocess_utils.run_claude_command` (`test_subprocess_utils.py` asserts propagation), `fsm/evaluators.py` (3 sites), `runner_spec.py:264/449`, `worker_pool.py:854`, `fsm/handoff_handler.py:116`, `cli/action.py:343`, `cli/issues/link_epics.py:334`, `cli/issues/decisions.py:912`, `learning_tests/extractor.py:131`, `cli/artifact/{discover,extract}.py`, `session_store/lifecycle.py` (3 sites), `mcp_server/tools.py:224`, `advisor.consult()` (`resolve_host().name`), and `main_doctor` (`runner = resolve_host()` at ~1439). Callers that catch it: `init/cli.py`, `init/install_check.py`, `cli/loop/header.py:156`, `cli/loop/summary.py:172`, `fsm/executor.py` (`_resolve_model_selection` → `ModelHintError`; `_cli_backend_name` → `None`), `cli/harness.py::_resolved_host_cli` (`except Exception`) [Agent 2 finding]
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
- Entry-point enumeration precedent for the AC-4 regression test: `doc_counts.py::declared_entry_points` (tomllib over `scripts/pyproject.toml`) used by `test_wiring_cli_registry.py::test_cli_entry_point_coverage`. No existing gate asserts host-config behavior per entry point.

_Wiring pass added by `/ll:wire-issue`:_

**Tests that may break — the repo's own `.ll/ll-config.json:152` sets `"orchestration": {"host_cli": "claude-code"}` (tracked via `!/.ll/`), there is no suite-wide cwd isolation (`conftest.py` has no autouse `chdir`; only file-local ones in `test_cli_queue.py`, `test_cli_queue_run.py`, `test_cli_harness.py`), and `_restore_cmd_run_env_vars` scrubs only env, not config. After the fix every `resolve_host()` with `env is None` and no `LL_HOST_CLI`/`LL_HOOK_HOST` resolves `claude-code` from the repo config *before* the probe runs:**
- `scripts/tests/test_model_hints.py` — fixture `no_host` (~357; deletes both env vars, patches `shutil.which` → `None`) now resolves `claude-code` from config instead of raising; breaks `TestPreflight::test_host_not_configured_fails_preflight` (asserts `"no host CLI was found"`) and weakens `test_literal_without_host_runs_and_omits_backend` (~553). Fix: `monkeypatch.chdir(tmp_path)` (config-less) inside `no_host` [Agent 3 finding]
- `scripts/tests/test_init_core.py::TestDetectHosts` — `test_pi_never_primary` (~3641), `test_nothing_detected_defaults_to_claude_code` (~3606), `test_only_pending_hosts_still_listed`, `test_kimi_detected_last`, `test_multiple_hosts_detected` reach `default_hosts()` → `resolve_host()` (`init/cli.py:149`) with `shutil.which` patched; now resolves from repo config (results may coincide by accident). Add `monkeypatch.chdir(tmp_path)` [Agent 3 finding]
- `scripts/tests/test_init_audit_fixes.py::TestHostSelectionPersisted` — review (`default_hosts` patched in one test; `test_existing_host_cli_stays_primary_on_reinit` passes config in) [Agent 3 finding]
- `scripts/tests/test_host_runner.py::TestResolveHost::test_raises_when_no_host` — asserts `"LL_HOST_CLI"` and `"orchestration.host_cli"` in the message; keep `_remediation_hint()` text. Passes `env={}` so unaffected by the env-is-None-only fold-in [Agent 3 finding]
- `scripts/tests/test_host_runner.py::TestApplyHostCliFromConfig` (~2379, 4 tests) and the ~30 `patch("little_loops.host_runner.apply_host_cli_from_config")` sites in `test_cli_doctor.py` plus `test_cli_doctor_full.py:330/352` — break (`AttributeError`) only if `apply_host_cli_from_config` is deleted/renamed; keep the symbol or update all together [Agent 3 finding]
- `scripts/tests/test_cli_doctor_install_checks.py` — `_advisor_data` env > config > fallback tests (`test_independent_main_vs_advisor_resolution_env_first`, `..._config_second`, `..._both_unset_falls_back`, `_FakeBRConfig`/`_FakeOrchestrationConfig`) must stay green or be reshaped if `cli/doctor.py:815` collapses to one resolution path; note the hand-rolled expression ignores `LL_HOOK_HOST` [Agent 3 finding]
- `scripts/tests/test_fsm_evaluators.py:1077`, `test_fsm_continuity.py:71` (+ `scripts/tests/spike/fsm_continuity_compaction/test_continuity_pipeline.py:134`), `test_subprocess_utils.py:77/2435/2438/2565`, `test_learning_tests_extractor.py:215/229`, `test_session_store_lifecycle.py:1687`, `test_session_store_schema.py:943` (asserts `row["host"]` populated), `test_cli_harness.py:696`, `test_loop_model_display.py`, `test_handoff_handler.py`, `test_mcp_server.py` — call or depend on real `resolve_host()` with `env is None`; audit each for cwd exposure (agents did not inspect every one) [Agent 1/3 finding]
- `scripts/tests/test_advisor.py` (`resolve_host_named` patches at 171/204/227/244/266/443/624/704), `test_cli_advise.py` (71/147/179/213/243), `test_cli_doctor_install_checks.py` (667-984) — patch `resolve_host_named`; unaffected provided it stays config-independent and never writes `os.environ` [Agent 3 finding]

**New tests to write** (none exist today — searched `scripts/tests` for any test driving `resolve_host()` from config; all 146 `host_cli` hits are parsing/schema/`apply_host_cli_from_config`/mocked):
- `test_host_runner.py::TestResolveHost` — with `env=None`: config beats probe; `LL_HOST_CLI` beats config; `LL_HOOK_HOST` beats config; `ll.local.md` frontmatter overrides `ll-config.json`; malformed/missing config never raises and falls through to probe; unregistered config value raises `HostNotConfigured`; empty-string config treated as unset; `os.environ` unmutated. `resolve_host(env={})` does not consult config; `resolve_host_named` ignores config. Follow `test_session_store_db.py::test_env_wins_over_config` / `test_config_used_when_env_unset` (tmp_path `.ll/ll-config.json` + `monkeypatch.chdir`) and `test_config.py::TestBRConfigLocalOverrides._write_local` [Agent 3 finding]
- End-to-end carrier: `test_fake_host.py::TestRunClaudeCommandEndToEnd::test_default_emission_drives_callbacks` — swap `setenv("LL_HOST_CLI","fake")` for `tmp_path/.ll/ll-config.json` `{"orchestration":{"host_cli":"fake"}}` + `chdir`; `fake` is absent from the schema enum but `OrchestrationConfig.from_dict` does not enforce it. Config-driven `cmd_*` precedent: `test_ll_loop_commands.py` (~341, `request_path` config + `cmd_validate`) [Agent 3 finding]
- AC-4 gate (new file, e.g. `scripts/tests/test_host_resolution_chokepoint_gate.py`) — copy `test_history_store_chokepoint_gate.py`'s structure (`_SRC_ROOT`, `_ALLOWLIST: dict[str,str]` with one-line reasons, AST `ast.walk` scan of `ast.Call` for `resolve_host`, `sorted(_SRC_ROOT.rglob("*.py"))`, allowlist-drift test); use `test_usage_selection_chokepoint_gate.py`'s `(rel, enclosing_function)` key + `test_gate_detects_a_stray_site` self-test if per-function granularity is wanted. Seed the site list from the Dependent Files enumeration. `conformance/test_host_composition.py::_RUNNER_BINDING_CALLS`/`_bindings()` is an existing `resolve_host` call recogniser to reuse, not a site gate. Under Option B the gate can instead assert that no production `os.environ["LL_HOST_CLI"]` write exists outside `apply_host_cli_from_config` [Agent 3 finding]
- Config-side: extend `test_config_schema.py::test_orchestration_host_cli_in_schema` only if the description text changes; `_SCHEMA_DEFAULT_ALLOWLIST` (~1283) already lists `orchestration.host_cli` [Agent 3 finding]

**Gate consumers verified safe** — `test_enh3184_spawn_site_guard.py` pins `host_runner.py` at `(2, 0)` (config read adds no subprocess); `test_host_runner.py::test_referenced_env_names_are_covered` regex-scans `os.environ` literals only (`env.get(...)` on a local dict and `LL_`-prefixed names pass); `conformance/test_host_composition.py::TestExecutorTouchesOnlyAbstractInterface` scans `host_runner.py` for concrete-runner `isinstance`/`.name` literal comparisons — new config code in `resolve_host` must not bind `resolve_host()` results or compare `.binary`/`.name` to literals [Agent 2/3 finding]

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` (~730) — env-var row says `LL_HOST_CLI` "Takes precedence over binary probe and `orchestration.host_cli` config"; the config-vs-probe order is not stated there and must agree with env > config > probe.
- `docs/ARCHITECTURE.md` (~919, ~924), `docs/reference/API.md` (`apply_host_cli_from_config`, `resolve_host`), `docs/reference/CLI.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (~486), `.claude/CLAUDE.md` § Host CLI Abstraction, `scripts/little_loops/config-schema.json` (`orchestration`, `orchestration.host_cli` descriptions) — all assert the precedence; update if the mechanism changes ("read by apply_host_cli_from_config() before resolve_host() runs").

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` host-runner table — `resolve_host()` row ("honors `LL_HOST_CLI` / `orchestration.host_cli` overrides"), `apply_host_cli_from_config()` row ("exports it as `LL_HOST_CLI` before `resolve_host()` runs"), `HostNotConfigured` row [Agent 2 finding]
- `docs/reference/API.md` `little_loops.host_runner` — `### apply_host_cli_from_config` ("Typically called once at startup by orchestration entry points"); `### resolve_host` "Detection order" list has no config step (and already omits kimi/qwen from the probe order — fix together); `HostNotConfigured` entry; advisor entry ~12476 ("Never calls `apply_host_cli_from_config()`"); `detect_installation` ~12359 / `fetch_latest_plugin` ~12393 descriptions. Gate: `test_wiring_reference_docs.py` requires `resolve_host` and `HostNotConfigured` to remain in API.md [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `orchestration.host_cli` row ("Mirrors the `LL_HOST_CLI` environment variable; env var takes precedence if both are set") and `advisor.host` row ("same enum as `orchestration.host_cli`") [Agent 2 finding]
- `docs/reference/CLI.md` — `ll-init` (primary is existing `orchestration.host_cli`, else `resolve_host()`'s pick — now also config-derived), `ll-advise` (~201, "never calls `apply_host_cli_from_config()`"), artifact-extract paragraph (~5647, "never overrides `resolve_host()`'s ambient host selection") [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` `### HostNotConfigured` — Cause names only `LL_HOST_CLI`/`LL_HOOK_HOST` and the probe; add the config key. `test_wiring_guides_and_meta.py` pins `HostNotConfigured`/`FEAT-1462` here [Agent 2 finding]
- `docs/guides/MCP_SERVER_GUIDE.md` (~306, capabilities tool host source), `docs/guides/GETTING_STARTED.md` (~112), `docs/generalized-fsm-loop.md` (~1930, "`resolve_host()` returns the default `ClaudeCodeRunner` when `claude` is on PATH") [Agent 2 finding]
- Host docs with parallel precedence wording: `docs/codex/usage.md` (~19; `test_wiring_guides_and_meta.py` pins `LL_HOST_CLI=codex` here), `docs/qwen/{getting-started,automation}.md`, `docs/kimi/{getting-started,automation}.md`, `docs/codex/README.md`, `docs/development/CONFORMANCE.md`, `docs/guides/EVALUATION_GUIDE.md` [Agent 1/2 finding]
- `AGENTS.md` § Host CLI Abstraction — Codex-flavored copy of the `.claude/CLAUDE.md` block; edit in step if the CLAUDE.md wording changes (`init/writers.py` renders the consumer CLAUDE.md block separately, ~211) [Agent 2 finding]
- Docs edits here trip no `ll-adapt` mirror gate and no skill 500-line cap (`commands/`, `skills/`, `README.md`, `scripts/README.md`, `CONTRIBUTING.md` have no matches); `test_docs_audience_gate.py` forbids `scripts/tests/…` paths in `docs/` [Agent 2 finding]

### Configuration
- `scripts/little_loops/config/orchestration.py` — `OrchestrationConfig.host_cli: str | None`, loaded unvalidated via `data.get("host_cli")`; `.ll/ll.local.md` frontmatter deep-merges over `ll-config.json`, so the value can come from the local override.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` — `orchestration` description (~1806, "read by apply_host_cli_from_config() before resolve_host() runs") and `orchestration.host_cli` (~1808-1811, "Mirrors the LL_HOST_CLI environment variable; env var takes precedence"): reword to env > `LL_HOOK_HOST` > config > probe. No test snapshots the description text, so this is not test-enforced [Agent 2/3 finding]
- `.ll/ll-config.json:152` — this repo's own `"host_cli": "claude-code"` will be picked up by the fold-in for any `env is None` call run from the repo cwd (see Tests) [Agent 1 finding]
- `.claude/CLAUDE.md` § Host CLI Abstraction — already states "(or `orchestration.host_cli`)"; becomes true after the fix, no edit needed unless `apply_host_cli_from_config` is removed [Agent 2 finding]

## Program Design

### Types
- `OrchestrationConfig.host_cli: str | None` — existing field (`scripts/little_loops/config/orchestration.py`); no new data shape is required by any option.

### Signatures
- `resolve_host(env: dict[str, str] | None = None) -> HostRunner` — `host_runner.py`; when `env is None` it snapshots `dict(os.environ)`; an explicit `env` is a testability/independence seam (`resolve_host_named` passes `{"LL_HOST_CLI": name}`).
- `resolve_host_named(name: str) -> HostRunner` — `host_runner.py`; must remain independent of ambient env and config.
- `apply_host_cli_from_config(config: object) -> None` — `host_runner.py`; copies `config.orchestration.host_cli` to `os.environ["LL_HOST_CLI"]` unless already set.
- `BRConfig.__init__(project_root)` — `config/core.py`; calls `load_env_fallback` before `_load_config`.

### Call Path
`main_loop` -> `BRConfig` -> `cmd_run` -> `PersistentExecutor` -> `FSMExecutor.run` -> `FSMExecutor._preflight_model_hints` -> `FSMExecutor._resolve_model` -> `resolve_host`

`main_auto` -> `AutoManager` -> `run_claude_command` -> `resolve_host`

`main_parallel` -> `WorkerPool` -> `resolve_host`

### Decision Rules
- Precedence: non-empty `LL_HOST_CLI` > `LL_HOOK_HOST` (decided 2026-09-28: stays directly after `LL_HOST_CLI`, above config) > non-empty `orchestration.host_cli` > `_PROBE_ORDER` probe.
- Empty-string values are treated as unset (matches `resolve_host` and `apply_host_cli_from_config`).
- An unregistered config value raises `HostNotConfigured` in `resolve_host` (no fallback to probe), same as an unregistered `LL_HOST_CLI`.
- `resolve_host_named` and `ll-advise`/`advisor.consult` stay config-independent.

## Implementation Steps

1. `resolve_host()` reached from `ll-loop run`, `ll-auto`, `ll-parallel`, `ll-sprint` returns the configured host when `LL_HOST_CLI` is unset — verified by a test per entry point (or by a single test at the choke point plus the enumeration gate below).
2. `FSMExecutor._preflight_model_hints`/`_resolve_model` and `initial_model_display` resolve against the configured host — verified in `scripts/tests/test_model_hints.py`.
3. A gate test enumerates entry points (precedent: `declared_entry_points`) or the choke point's sole-opener property, with a reasoned allowlist plus drift check, so a new `main_*` cannot bypass the key.
4. `ll-advise`/`resolve_host_named` remain config-independent (`test_advisor_host_env_independent_of_orchestration_host_cli` still passes) and `ll-loop run`'s cross-host child override (`summary.py:201`) still wins.
5. Comments/docs listed under Integration Map → Documentation agree with the shipped mechanism; `python -m pytest scripts/tests/` exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add the config step inside `resolve_host()`'s `env is None` branch in `scripts/little_loops/host_runner.py` via a function-local import (never top-level: `config.core` → `parallel.types` → `worker_pool` → `host_runner` already cycles at import time); the helper must catch `OSError`, `JSONDecodeError`, `ValueError`, `TypeError`, `AttributeError`, avoid `BRConfig.__init__`'s `load_env_fallback` `os.environ` write, honor `.ll/ll.local.md` via `resolve_config_path` + `parse_local_override_frontmatter` + `deep_merge`, and treat empty string as unset
- Decide and record cwd-vs-`project_root` semantics for `mcp_server/tools.py:224` and `init/cli.py:149`, and whether to cache the lookup (key on cwd) given per-call hot paths in `fsm/evaluators.py`, `subprocess_utils.py:741`, `worker_pool.py:854`
- Collapse `cli/doctor.py:815` (`os.environ.get("LL_HOST_CLI") or cfg.orchestration.host_cli`, which ignores `LL_HOOK_HOST`) and decide whether `apply_host_cli_from_config` at `:1438` stays; if it is removed, also update `host_runner.py`/`little_loops/__init__.py` `__all__`, `TestApplyHostCliFromConfig`, and the ~30 `patch(...apply_host_cli_from_config)` sites in `test_cli_doctor.py` / `test_cli_doctor_full.py`
- Update `scripts/tests/test_model_hints.py` (`no_host` fixture → add `monkeypatch.chdir(tmp_path)`) and `scripts/tests/test_init_core.py::TestDetectHosts` (add `chdir`) so the repo's `.ll/ll-config.json` (`host_cli: claude-code`) does not leak in; audit the other `env is None` tests listed under Tests
- Add `TestResolveHost` config-precedence cases in `scripts/tests/test_host_runner.py`, an end-to-end `fake`-host config test in `scripts/tests/test_fake_host.py`, and the AC-4 site gate (new `scripts/tests/test_host_resolution_chokepoint_gate.py` modeled on `test_history_store_chokepoint_gate.py`)
- Update comments/docstrings: `host_runner.py` `resolve_host`/`apply_host_cli_from_config` docstrings, `config/orchestration.py` `OrchestrationConfig` docstring, `init/cli.py` (~133, ~266), `advisor.py` `consult()` docstring
- Update `config-schema.json` (`orchestration`, `orchestration.host_cli` descriptions) and docs: `docs/ARCHITECTURE.md`, `docs/reference/{API,CONFIGURATION,CLI,HOST_COMPATIBILITY}.md`, `docs/development/TROUBLESHOOTING.md`, `docs/guides/{HARNESS_OPTIMIZATION,MCP_SERVER,GETTING_STARTED}_GUIDE.md`, `docs/generalized-fsm-loop.md`, `docs/{codex,qwen,kimi}/*`, `AGENTS.md`

## Impact

- **Priority**: P2 — documented config key silently has no effect on the main automation paths.
- **Effort**: Small–Medium (choke-point change plus tests across entry points).
- **Risk**: Medium — changes which host runs for users who set the key and relied on the probe.

## Steps to Reproduce

1. Set `"orchestration": {"host_cli": "codex"}` in `.ll/ll-config.json`, leave `LL_HOST_CLI` unset, have both `claude` and `codex` on PATH.
2. Run `ll-doctor` — applies the config key before resolving the host.
3. Run any loop with `ll-loop run` — dispatches to the probe winner, not `codex` (unless `codex` happens to win the probe).

## Acceptance Criteria

- [ ] With `LL_HOST_CLI` unset and `orchestration.host_cli` set, `resolve_host()` as reached from `ll-loop run`, `ll-loop validate`, `ll-auto`, `ll-parallel`, `ll-sprint` and `ll-logs fleet-review` selects the configured host, not the probe winner.
- [ ] `LL_HOST_CLI` still overrides the config key; with neither set, the probe order is unchanged.
- [ ] `FSMExecutor._preflight_model_hints` and ENH-3548's validate-time hint warnings resolve against the configured host.
- [ ] A regression test proves a new CLI entry point cannot bypass the config key (single choke point, or a test enumerating entry points).

## Related

- ENH-3548 uses `resolve_host()` for validate-time hint warnings so `validate` and `run` agree; it inherits this fix automatically.

## Status

**Open** | Created: 2026-09-28 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-09-28T22:55:33 - `937a6b3a-b00c-40f0-99a6-4ffdf6cec5e8.jsonl`
- `/ll:decide-issue` - 2026-09-28T22:46:35 - `77c339e9-8806-4a53-a734-a18593a275bb.jsonl`
- `/ll:refine-issue` - 2026-09-28T22:43:07 - `29b6f7a1-cbe3-4641-a1f5-b4e98b2d2120.jsonl`
