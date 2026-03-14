---
id: ENH-748
priority: P3
type: ENH
status: backlog
discovered_date: 2026-03-14
discovered_by: capture-issue
---

# ENH-748: Add `--handoff-threshold` CLI Override to ll-auto, ll-parallel, ll-sprint

## Motivation

The `context_monitor.auto_handoff_threshold` setting in `ll-config.json` controls when automatic handoff is triggered, but changing it requires modifying a shared project config file. Users often want to run a single command with a lower (or higher) threshold for a specific session without touching the config. A `--handoff-threshold` CLI flag enables per-run overrides without side effects.

## Current Behavior

- Handoff threshold is read exclusively from `ll-config.json` → `context_monitor.auto_handoff_threshold` (default: 80)
- The `context-monitor.sh` hook reads this value at hook invocation time via `ll_config_value "context_monitor.auto_handoff_threshold" "80"`
- `ll-auto`, `ll-parallel`, and `ll-sprint` have no way to pass a one-off threshold override

## Desired Behavior

```bash
# Trigger auto-handoff at 40% context usage for this run only
ll-auto --handoff-threshold 40

ll-parallel --handoff-threshold 60 P2-BUG-123

ll-sprint my-sprint.yaml --handoff-threshold 50
```

The flag value (1–100) overrides `auto_handoff_threshold` for the duration of that CLI invocation without modifying `ll-config.json`.

## Implementation Steps

1. **Add `--handoff-threshold` argument** to the argument parsers in:
   - `scripts/little_loops/cli/auto.py` (or wherever `ll-auto` args are defined)
   - `scripts/little_loops/cli/parallel/` entry point
   - `scripts/little_loops/cli/sprint/` entry point
   - Validate: integer, range 1–100, optional

2. **Propagate the override** — when the value is provided, write it as an environment variable (e.g. `LL_HANDOFF_THRESHOLD=<value>`) before spawning subprocesses, OR pass it as an override to the config layer so `context-monitor.sh` picks it up.

3. **Update `context-monitor.sh`** — check for the env var override before falling back to `ll_config_value`:
   ```bash
   THRESHOLD="${LL_HANDOFF_THRESHOLD:-$(ll_config_value "context_monitor.auto_handoff_threshold" "80")}"
   ```

4. **Add validation** — reject values outside 1–100 with a clear error message.

5. **Update help text** for all three commands to document the new flag.

## Files Likely Affected

- `scripts/little_loops/cli/auto.py` (or equivalent entry point)
- `scripts/little_loops/cli/parallel/__init__.py` / entry point
- `scripts/little_loops/cli/sprint/__init__.py` / entry point
- `hooks/scripts/context-monitor.sh` (env var fallback)
- `config-schema.json` (no schema change needed — this is a CLI flag, not a config key)

## Acceptance Criteria

- [ ] `--handoff-threshold <int>` accepted by `ll-auto`, `ll-parallel`, `ll-sprint`
- [ ] Values outside 1–100 produce a validation error
- [ ] The override takes effect for the run without modifying `ll-config.json`
- [ ] Existing behavior unchanged when flag is omitted

## Session Log
- `/ll:capture-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55d3be20-340e-4a9d-9286-575d7dc448df.jsonl`
