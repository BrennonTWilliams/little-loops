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
---

# BUG-3644: orchestration.host_cli config key ignored by ll-loop run and other resolve_host() callers

## Summary

`orchestration.host_cli` in `.ll/ll-config.json` is documented as a host-selection override, but only `ll-doctor` honors it. `apply_host_cli_from_config()` (`little_loops.host_runner`) is the sole bridge from the config key into `LL_HOST_CLI`, and its only production caller is `cli/doctor.py` (`apply_host_cli_from_config(cfg)`, ~line 1438). `resolve_host()` reads only `LL_HOST_CLI`, `LL_HOOK_HOST` and the `_PROBE_ORDER` PATH probe.

Found while reviewing ENH-3548 (validate-time model hint warnings).

## Current Behavior

- `ll-loop run`, `ll-auto`, `ll-parallel`, `ll-sprint` and every other `resolve_host()` consumer ignore `orchestration.host_cli`. With `orchestration.host_cli: codex` and no `LL_HOST_CLI` set, a machine that also has `claude` on PATH dispatches to whichever host wins the probe order.
- `FSMExecutor._resolve_model` / `_preflight_model_hints` resolve `model_hint` against `resolve_host().name`, so hint resolution also ignores the config key.
- `ll-doctor` does apply it, so `ll-doctor` and `ll-loop run` can report different hosts on the same machine.

## Expected Behavior

Precedence everywhere a host is resolved: `LL_HOST_CLI` env var > `orchestration.host_cli` config key > binary probe — as `apply_host_cli_from_config()`'s docstring, `config-schema.json` (`orchestration`, `orchestration.host_cli` descriptions), `.claude/CLAUDE.md` (Host CLI Abstraction) and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (~486) already claim.

## Proposed Solution

Apply the config key at CLI entry for every automation tool that resolves a host (at minimum `ll-loop run`/`validate`, `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-logs fleet-review`), or fold the config lookup into `resolve_host()` itself behind the env var. Prefer a single choke point over per-CLI calls so new entry points cannot regress. Decide whether in-process `os.environ` mutation (current `apply_host_cli_from_config` approach) is acceptable given it leaks into descendants (compare the `LL_AUTOMATION` descendant-leak incident).

## Impact

- **Priority**: P2 — documented config key silently has no effect on the main automation paths.
- **Effort**: Small–Medium (choke-point change plus tests across entry points).
- **Risk**: Medium — changes which host runs for users who set the key and relied on the probe.

## Steps to Reproduce

1. Set `"orchestration": {"host_cli": "codex"}` in `.ll/ll-config.json`, leave `LL_HOST_CLI` unset, have both `claude` and `codex` on PATH.
2. Run `ll-doctor` — reports `codex`.
3. Run any loop with `ll-loop run` — dispatches to the probe winner, not `codex`.

## Related

- ENH-3548 uses `resolve_host()` for validate-time hint warnings so `validate` and `run` agree; it inherits this fix automatically.

## Status

**Open** | Created: 2026-09-28 | Priority: P2
