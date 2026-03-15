---
id: ENH-748
priority: P3
type: ENH
status: backlog
discovered_date: 2026-03-14
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 75
---

# ENH-748: Add `--handoff-threshold` CLI Override to ll-auto, ll-parallel, ll-sprint

## Summary

Add a `--handoff-threshold` CLI flag to `ll-auto`, `ll-parallel`, and `ll-sprint` that overrides `context_monitor.auto_handoff_threshold` from `ll-config.json` for a single run, without modifying shared config.

## Motivation

The `context_monitor.auto_handoff_threshold` setting in `ll-config.json` controls when automatic handoff is triggered, but changing it requires modifying a shared project config file. Users often want to run a single command with a lower (or higher) threshold for a specific session without touching the config. A `--handoff-threshold` CLI flag enables per-run overrides without side effects.

## Current Behavior

- Handoff threshold is read exclusively from `ll-config.json` → `context_monitor.auto_handoff_threshold` (default: 80)
- The `context-monitor.sh` hook reads this value at hook invocation time via `ll_config_value "context_monitor.auto_handoff_threshold" "80"`
- `ll-auto`, `ll-parallel`, and `ll-sprint` have no way to pass a one-off threshold override

## Expected Behavior

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

2. **Propagate the override** — when the value is provided, set `os.environ["LL_HANDOFF_THRESHOLD"] = str(value)` in the CLI entry point before any subprocess is spawned. Both `subprocess_utils.py` (line 92) and `parallel/worker_pool.py` (line 613) call `os.environ.copy()` when building subprocess environments, so the env var will propagate automatically to Claude subprocesses and the hook. Do NOT use the config layer (`config.automation.*`) — that approach won't reach `context-monitor.sh`.

3. **Update `context-monitor.sh`** — check for the env var override before falling back to `ll_config_value`:
   ```bash
   THRESHOLD="${LL_HANDOFF_THRESHOLD:-$(ll_config_value "context_monitor.auto_handoff_threshold" "80")}"
   ```

4. **Add validation** — reject values outside 1–100 with a clear error message.

5. **Update help text** for all three commands to document the new flag.

## API/Interface

New CLI flag added to three entry points:

```bash
ll-auto [--handoff-threshold THRESHOLD]
ll-parallel [--handoff-threshold THRESHOLD] [ISSUES...]
ll-sprint run SPRINT [--handoff-threshold THRESHOLD]
```

Environment variable set by the CLI before subprocess spawning:

```bash
LL_HANDOFF_THRESHOLD=<1-100>
```

Updated `context-monitor.sh` resolution order:

```bash
THRESHOLD="${LL_HANDOFF_THRESHOLD:-$(ll_config_value "context_monitor.auto_handoff_threshold" "80")}"
```

## Scope Boundaries

- **In scope**: `ll-auto`, `ll-parallel`, `ll-sprint run` only
- **Out of scope**: `ll-loop` (different lifecycle model — has its own config)
- **Out of scope**: Persisting the override back to `ll-config.json`
- **Out of scope**: Per-issue threshold overrides — the flag applies to the entire run
- **Out of scope**: Changes to `config-schema.json` — this is a CLI flag, not a new config key
- **Out of scope**: Changing the default threshold (remains 80)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/auto.py` — add `--handoff-threshold` arg to argparse
- `scripts/little_loops/cli/parallel.py` — add `--handoff-threshold` arg to argparse
- `scripts/little_loops/cli/sprint/__init__.py` — add `--handoff-threshold` to `run_parser`
- `hooks/scripts/context-monitor.sh` — read `LL_HANDOFF_THRESHOLD` env var before config fallback (line 26)

### Dependent Files (Callers/Importers)
- N/A — CLI entry points are not imported by other modules

### Similar Patterns
- `parallel.py` existing flags (`--max-workers`, `--dry-run`, `--issues`) — follow same `add_argument` pattern
- Other env var overrides in `hooks/scripts/` — follow same `${VAR:-default}` shell pattern

### Tests
- `scripts/tests/test_hooks_integration.py` — add test for `LL_HANDOFF_THRESHOLD` env var override
- New `test_cli_handoff_threshold.py` or inline tests for arg parsing in auto/parallel/sprint
- Note: `test_hooks_integration.py` exists but has no coverage for this env var yet — new tests must be written

### Documentation
- N/A — CLI flags are self-documenting via `--help`

### Configuration
- `config-schema.json` — N/A (no schema change needed)

## Acceptance Criteria

- [ ] `--handoff-threshold <int>` accepted by `ll-auto`, `ll-parallel`, `ll-sprint`
- [ ] Values outside 1–100 produce a validation error
- [ ] The override takes effect for the run without modifying `ll-config.json`
- [ ] Existing behavior unchanged when flag is omitted

## Impact

- **Priority**: P3 — Ergonomic improvement; current workaround (editing `ll-config.json`) works but risks polluting shared config
- **Effort**: Small — Additive flag on 3 existing argparse setups + 1-line shell fallback; no structural changes
- **Risk**: Low — Non-breaking; omitting the flag preserves current behavior exactly
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `context-monitor`, `captured`

## Status

**Open** | Created: 2026-03-14 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-03-15T18:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75ab76d5-fcb5-4a04-bb61-499b62742b41.jsonl`
- `/ll:verify-issues` - 2026-03-15T17:27:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/12de81ba-1a5b-40f3-b61a-85f37645e9af.jsonl`
- `/ll:format-issue` - 2026-03-15T16:11:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cc316fcb-f8d1-4845-aab1-5e94c57b6ed3.jsonl`
- `/ll:capture-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55d3be20-340e-4a9d-9286-575d7dc448df.jsonl`
