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
decision_needed: true
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

**Option B**: Fold the config lookup into `resolve_host()` itself, consumer-side and behind the env vars, reading `ll-config.json` without raising (precedent: `session_store/db.py::resolve_history_db`). Single choke point, no env mutation. Constraints: `resolve_host_named()` passes an explicit `env` and must stay config-independent, so the lookup can only apply on the `env is None` path; `host_runner.py` has no top-level `little_loops.config` import (a lazy import or a raw JSON read avoids a cycle); `LL_HOOK_HOST` ordering vs config must be decided.

**Option C**: Export `LL_HOST_CLI` from config inside `BRConfig.__init__`, alongside the existing `load_env_fallback` side effect, so every entry that builds a `BRConfig` is covered. Constraints: ~62 files construct `BRConfig` (including `cli/advise.py`, whose test pins `LL_HOST_CLI` unchanged after `main_advise()`); it widens the env-mutation leak the FEAT-3060 decision rejected; `cmd_run` builds a second `BRConfig` at `cli/loop/run.py:269` after `main_loop` already built one.

**Recommended**: Option B — the issue's own stated preference for a single choke point that new entry points cannot regress; final selection belongs to `/ll:decide-issue`.

- Scope note: `ll-logs fleet-review` and `ll-loop validate` do not call `host_runner.resolve_host()` today. `fleet-review --host` resolves a session-log host through `user_messages._resolve_host` (flag > `LL_HOOK_HOST` > default), unrelated to host-CLI selection, and `cmd_validate` (`cli/loop/config_cmds.py`) has no `resolve_host` call until ENH-3548 adds one. Acceptance Criterion 1 is vacuous for those two until then; they are only affected through ENH-3548's hint warnings.
- Related latent inconsistency: `cli/doctor.py:815` hand-rolls env > config for the advisor floor row and then calls `resolve_host_named(name)` or `resolve_host()`; a choke-point fix should let it collapse to one resolution path.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — owns `resolve_host()`, `resolve_host_named()`, `apply_host_cli_from_config()`; the choke-point candidate.
- `scripts/little_loops/config/core.py` — `BRConfig.__init__` already runs `load_env_fallback(self.project_root)` before parsing, the only construction-time `os.environ` side effect (alternative choke-point site).
- `scripts/little_loops/cli/loop/__init__.py` (`main_loop`, `BRConfig(Path.cwd())` at ~56), `cli/auto.py` (`main_auto`, ~77), `cli/parallel.py` (`main_parallel`, ~196), `cli/sprint/__init__.py` (`main_sprint`, ~242) — per-CLI sites if the fix is entry-point-scoped.
- `scripts/little_loops/init/cli.py` — comment at ~266 claims `resolve_host()` honors the config key; must be true or corrected after the fix.
- `scripts/little_loops/cli/doctor.py` — `main_doctor` (`apply_host_cli_from_config` at ~1438) and a hand-rolled `os.environ.get("LL_HOST_CLI") or cfg.orchestration.host_cli` at ~815; must stay consistent with whatever becomes canonical.

### Dependent Files (Callers/Importers)
- `resolve_host()` callers that read ambient env only today (graph-seeded, grep-confirmed): `subprocess_utils.py:741` (`ll-auto`/`ll-parallel` path), `parallel/worker_pool.py:854`, `fsm/executor.py:3698` (`_resolve_model`) and `:3717` (`_cli_backend_name`), `fsm/evaluators.py:1230/1341/1597`, `fsm/handoff_handler.py:116`, `cli/loop/header.py:156`, `cli/loop/summary.py:172`, `runner_spec.py:264/449`, `cli/action.py:343`, `cli/harness.py:1832`, `cli/artifact/discover.py:417`, `cli/artifact/extract.py:167`, `cli/issues/link_epics.py:334`, `cli/issues/decisions.py:912`, `init/cli.py:149/274/363`, `init/install_check.py:87/181`, `advisor.py:286`, `learning_tests/extractor.py:131`, `session_store/lifecycle.py` (3 sites), `mcp_server/tools.py:224`.
- `resolve_host_named()` callers that are **deliberately config-independent**: `advisor.py` (`consult`) and the doctor advisor rows; `test_cli_advise.py::test_advisor_host_env_independent_of_orchestration_host_cli` pins that `LL_HOST_CLI` is unchanged after `main_advise()`.

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

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` (~730) — env-var row says `LL_HOST_CLI` "Takes precedence over binary probe and `orchestration.host_cli` config"; the config-vs-probe order is not stated there and must agree with env > config > probe.
- `docs/ARCHITECTURE.md` (~919, ~924), `docs/reference/API.md` (`apply_host_cli_from_config`, `resolve_host`), `docs/reference/CLI.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (~486), `.claude/CLAUDE.md` § Host CLI Abstraction, `scripts/little_loops/config-schema.json` (`orchestration`, `orchestration.host_cli` descriptions) — all assert the precedence; update if the mechanism changes ("read by apply_host_cli_from_config() before resolve_host() runs").

### Configuration
- `scripts/little_loops/config/orchestration.py` — `OrchestrationConfig.host_cli: str | None`, loaded unvalidated via `data.get("host_cli")`; `.ll/ll.local.md` frontmatter deep-merges over `ll-config.json`, so the value can come from the local override.

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
- Precedence: non-empty `LL_HOST_CLI` > non-empty `orchestration.host_cli` > `LL_HOOK_HOST` vs config ordering is **undecided** (the issue's stated order omits `LL_HOOK_HOST`; today `resolve_host` ranks `LL_HOOK_HOST` directly after `LL_HOST_CLI`, above the probe) > `_PROBE_ORDER` probe.
- Empty-string values are treated as unset (matches `resolve_host` and `apply_host_cli_from_config`).
- An unregistered config value raises `HostNotConfigured` in `resolve_host` (no fallback to probe), same as an unregistered `LL_HOST_CLI`.
- `resolve_host_named` and `ll-advise`/`advisor.consult` stay config-independent.

## Implementation Steps

1. `resolve_host()` reached from `ll-loop run`, `ll-auto`, `ll-parallel`, `ll-sprint` returns the configured host when `LL_HOST_CLI` is unset — verified by a test per entry point (or by a single test at the choke point plus the enumeration gate below).
2. `FSMExecutor._preflight_model_hints`/`_resolve_model` and `initial_model_display` resolve against the configured host — verified in `scripts/tests/test_model_hints.py`.
3. A gate test enumerates entry points (precedent: `declared_entry_points`) or the choke point's sole-opener property, with a reasoned allowlist plus drift check, so a new `main_*` cannot bypass the key.
4. `ll-advise`/`resolve_host_named` remain config-independent (`test_advisor_host_env_independent_of_orchestration_host_cli` still passes) and `ll-loop run`'s cross-host child override (`summary.py:201`) still wins.
5. Comments/docs listed under Integration Map → Documentation agree with the shipped mechanism; `python -m pytest scripts/tests/` exits 0.

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
- `/ll:refine-issue` - 2026-09-28T22:43:07 - `29b6f7a1-cbe3-4641-a1f5-b4e98b2d2120.jsonl`
