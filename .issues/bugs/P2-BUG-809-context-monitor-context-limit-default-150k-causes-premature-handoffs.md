---
id: BUG-809
type: BUG
priority: P2
status: active
discovered_date: 2026-03-18
discovered_by: capture-issue
---

# BUG-809: context-monitor.sh default context_limit_estimate (150K) is 6–7x too low for current models

## Summary

`hooks/scripts/context-monitor.sh` defaults `context_limit_estimate` to 150,000 tokens. Current Claude models support 1,000,000 tokens (Sonnet 4.6 / Opus 4.6) and 200,000 (Haiku 4.5). The 150K default means handoff triggers fire at ~60K actual tokens — roughly 6% of the real window — making session handoffs dramatically premature on every modern model.

## Current Behavior

`context_limit_estimate` defaults to 150,000 in `context-monitor.sh`. With the default `auto_handoff_threshold` of 80 (80%), handoff logic fires when estimated usage reaches 120,000 tokens (`150000 * 0.80`). For a Sonnet 4.6 session this is only ~12% of the 1M context window.

## Expected Behavior

The default context limit should reflect actual model context windows:
- Sonnet 4.6 / Opus 4.6: 1,000,000 tokens (1M GA: March 13, 2026)
- Haiku 4.5: 200,000 tokens

Config should allow model-aware overrides so operators can set the correct limit without touching the script.

## Root Cause

- **File**: `hooks/scripts/context-monitor.sh`
- **Anchor**: line 27 — `CONTEXT_LIMIT=$(ll_config_value "context_monitor.context_limit_estimate" "150000")`
- **Cause**: The hardcoded fallback `"150000"` passed to `ll_config_value` pre-dates the March 2026 1M context window GA for Sonnet/Opus. No model detection logic exists anywhere in the hooks directory; the limit is a single static variable.

Additionally, `config-schema.json:466` constrains `context_limit_estimate` to `"maximum": 500000`, which must also be raised — otherwise users cannot set a 1M value via config even with a manual override.

The project's `.claude/ll-config.json` sets only `context_monitor.enabled: true` and has no `context_limit_estimate` override, so the script always resolves to the 150K default on this project.

## Motivation

Premature handoffs interrupt long-running sessions unnecessarily, force users to re-establish context, and reduce the utility of the automation harness. The bug is silent — the monitor appears to work correctly but fires far too early.

## Proposed Solution

1. Update the hardcoded default in `context-monitor.sh:27` from `"150000"` to `"1000000"`.
2. Update `config-schema.json:464` default from `150000` to `1000000`, and `config-schema.json:466` maximum from `500000` to `2000000` (headroom for future models).
3. Update documentation in `docs/guides/SESSION_HANDOFF.md` and `docs/reference/CONFIGURATION.md` recommending users set `context_limit_estimate` to `200000` for Haiku 4.5 deployments.
4. Optionally: add `LL_CONTEXT_LIMIT` env var override path following the `THRESHOLD` pattern at `context-monitor.sh:26` — `CONTEXT_LIMIT="${LL_CONTEXT_LIMIT:-$(ll_config_value "context_monitor.context_limit_estimate" "1000000")}"`. This would pair with a `--context-limit` CLI flag using the `add_handoff_threshold_arg` helper in `cli_args.py:136` as a model.
5. If adding the optional CLI flag, propagate `LL_CONTEXT_LIMIT` via `os.environ` in `auto.py`, `parallel.py`, `sprint/run.py`, and `loop/run.py` — following the pattern at `auto.py:68-71`.

## Integration Map

### Files to Modify
- `hooks/scripts/context-monitor.sh:27` — change hardcoded default from `"150000"` to `"1000000"`; optionally add `LL_CONTEXT_LIMIT` env var layer
- `config-schema.json:461-467` — update `context_monitor.context_limit_estimate` default (150000→1000000) and maximum (500000→2000000)
- `docs/guides/SESSION_HANDOFF.md` — add Haiku 4.5 guidance (200K override), update example values
- `docs/reference/CONFIGURATION.md` — update `context_limit_estimate` documented default and recommended values

### Optional (CLI flag)
- `scripts/little_loops/cli_args.py:136` — add `add_context_limit_arg()` helper following `add_handoff_threshold_arg` pattern
- `scripts/little_loops/cli/auto.py:68-71` — propagate `LL_CONTEXT_LIMIT` to env
- `scripts/little_loops/cli/parallel.py:163` — propagate `LL_CONTEXT_LIMIT` to env
- `scripts/little_loops/cli/sprint/run.py:103` — propagate `LL_CONTEXT_LIMIT` to env
- `scripts/little_loops/cli/loop/run.py:70` — propagate `LL_CONTEXT_LIMIT` to env

### Dependent Files (Read-only context)
- `hooks/scripts/lib/common.sh:217-233` — `ll_config_value` helper; no change needed
- `hooks/scripts/lib/common.sh:184-191` — `ll_resolve_config`; no change needed
- `.claude/ll-config.json` — currently sets only `context_monitor.enabled: true`; no change needed (fix is in script default)
- `docs/development/TROUBLESHOOTING.md` — references context monitor settings; review for stale values

### Tests
- `scripts/tests/test_hooks_integration.py:131-168` — existing env var override test; add parallel test for `LL_CONTEXT_LIMIT` if env var is added
- `scripts/tests/test_cli_loop_lifecycle.py:710-742` — env var propagation tests; add parallel tests if CLI flag is added

## Implementation Steps

1. **`hooks/scripts/context-monitor.sh:27`** — change `"150000"` → `"1000000"` in the `ll_config_value` call; update the surrounding comment to note the 1M GA date (March 13, 2026) and Haiku 4.5 at 200K
2. **`config-schema.json:464,466`** — update `"default": 150000` → `"default": 1000000` and `"maximum": 500000` → `"maximum": 2000000`
3. **`docs/guides/SESSION_HANDOFF.md`** — add a section on model-appropriate values (Sonnet/Opus → 1M, Haiku 4.5 → 200K); update any example values
4. **`docs/reference/CONFIGURATION.md`** — update `context_limit_estimate` default and recommended range in the config reference table
5. **(Optional) `scripts/little_loops/cli_args.py`** — add `add_context_limit_arg()` following `add_handoff_threshold_arg` at line 136; wire into `auto.py`, `parallel.py`, `sprint/run.py`, `loop/run.py` following the `LL_HANDOFF_THRESHOLD` env var pattern at `auto.py:68-71`
6. **`scripts/tests/test_hooks_integration.py:29`** — update the test fixture `"context_limit_estimate": 150000` → `"context_limit_estimate": 1000000` so tests validate the new default; run `python -m pytest scripts/tests/test_hooks_integration.py -v` to confirm no regressions; add `LL_CONTEXT_LIMIT` env var test if step 5 is implemented

## Impact

- **Severity**: High — affects every session using default config on Sonnet/Opus models
- **Users**: Anyone using little-loops with default context monitor config
- **Scope**: Single default value change; backward-compatible (users who set an explicit override are unaffected)

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/SESSION_HANDOFF.md` lines 281, 307 | User-facing docs for context/handoff behavior; contains example values to update |
| `config-schema.json` lines 461–467 | Config schema for context_monitor block; default and maximum need updating |
| `docs/reference/CONFIGURATION.md` lines 114, 330 | Config reference table showing context_limit_estimate default |
| `docs/ARCHITECTURE.md:860` | Architecture config example showing 150000; may need updating |
| `docs/development/TROUBLESHOOTING.md:461` | Troubleshooting config example showing 150000; may need updating |

## Labels

bug, context-monitor, hooks, accuracy

## Session Log
- `/ll:refine-issue` - 2026-03-19T04:09:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/577cb407-2c53-42ff-9cc5-923c88fb7a19.jsonl`
- `/ll:refine-issue` - 2026-03-19T04:09:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/28fae77f-f951-4427-bc31-ccdf8679e0c6.jsonl`
- `/ll:capture-issue` - 2026-03-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/11790a5c-4ad1-498a-9649-93255e24e9c4.jsonl`

---
## Status

Active — not yet implemented.
