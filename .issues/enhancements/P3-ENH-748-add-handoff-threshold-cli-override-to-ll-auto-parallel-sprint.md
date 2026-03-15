---
id: ENH-748
priority: P3
type: ENH
status: backlog
discovered_date: 2026-03-14
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 85
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

1. **Add `add_handoff_threshold_arg()` to `cli_args.py`** (after `add_idle_timeout_arg`, ~line 132):
   ```python
   def add_handoff_threshold_arg(parser: argparse.ArgumentParser) -> None:
       parser.add_argument(
           "--handoff-threshold", type=int, default=None,
           help="Override auto-handoff context threshold (1-100, default: from config)"
       )
   ```
   Also add it to `add_common_auto_args()` (lines 232-245) and update `__all__` (lines 265-282).

2. **Wire arg in each CLI entry point** — follow `auto.py:57-58` pattern:
   - `auto.py`: After `args = parser.parse_args()`, add validation and `os.environ["LL_HANDOFF_THRESHOLD"] = str(args.handoff_threshold)` before `AutoManager` construction
   - `parallel.py`: Same pattern in `main_parallel()`, before `config.create_parallel_config()` (line 173)
   - `sprint/__init__.py` + `sprint/run.py`: Set env var in `_cmd_sprint_run()` before `process_issue_inplace()` (line 316) and `ParallelOrchestrator` (line 376)

3. **Add validation** — since `argparse` has no built-in range validation in this codebase (uses `type=int` only), add explicit check after parsing:
   ```python
   if args.handoff_threshold is not None and not (1 <= args.handoff_threshold <= 100):
       parser.error("--handoff-threshold must be between 1 and 100")
   ```

4. **Update `context-monitor.sh` line 26** — change from:
   ```bash
   THRESHOLD=$(ll_config_value "context_monitor.auto_handoff_threshold" "80")
   ```
   to:
   ```bash
   THRESHOLD="${LL_HANDOFF_THRESHOLD:-$(ll_config_value "context_monitor.auto_handoff_threshold" "80")}"
   ```

5. **Add tests**:
   - `test_cli_args.py`: `TestAddHandoffThresholdArg` class following `TestAddIdleTimeoutArg` pattern
   - `test_subprocess_utils.py`: env var propagation using `capture_popen` pattern (lines 244-265)
   - `test_hooks_integration.py`: `TestContextMonitor` class — pass `LL_HANDOFF_THRESHOLD` in `env=` dict

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
- `scripts/little_loops/cli_args.py` — **create `add_handoff_threshold_arg()` function** (lines 232-245 area, after `add_idle_timeout_arg`); also add it to `add_common_auto_args()` bundle; update `__all__` (line 265-282)
- `scripts/little_loops/cli/auto.py` — `add_common_auto_args()` already bundles all common args; no direct change needed if `add_handoff_threshold_arg` is added to the bundle; handle `args.handoff_threshold` after parsing (~line 57-58 pattern)
- `scripts/little_loops/cli/parallel.py` — call `add_handoff_threshold_arg(parser)` alongside existing `add_*_arg` calls (lines 117-133); pass to `create_parallel_config()` at line 173
- `scripts/little_loops/cli/sprint/__init__.py` — call `add_handoff_threshold_arg(run_parser)` in `run` subparser setup (lines 112-130)
- `scripts/little_loops/cli/sprint/run.py` — set `os.environ["LL_HANDOFF_THRESHOLD"]` before `process_issue_inplace()` at line 316 and `ParallelOrchestrator` at line 376
- `hooks/scripts/context-monitor.sh` — change line 26 from `THRESHOLD=$(ll_config_value ...)` to `THRESHOLD="${LL_HANDOFF_THRESHOLD:-$(ll_config_value "context_monitor.auto_handoff_threshold" "80")}"`

### Dependent Files (Callers/Importers)
- N/A — CLI entry points are not imported by other modules

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `cli_args.py:71-132` — `add_max_workers_arg()`, `add_timeout_arg()`, `add_idle_timeout_arg()`: exact template to follow; `add_idle_timeout_arg` (no `default` param, `default=None`, help references config) is the closest precedent
- `cli/auto.py:57-58` — pattern for applying a parsed CLI arg as a config override: `if args.idle_timeout is not None: config.automation.idle_timeout_seconds = args.idle_timeout`
- `hooks/scripts/user-prompt-check.sh:81` — only existing `${VAR:-default}` in hook scripts; confirms the pattern is acceptable in this codebase
- `subprocess_utils.py:92-93` — `env = os.environ.copy()` picks up everything already in the parent process; setting `os.environ["LL_HANDOFF_THRESHOLD"]` in the CLI entry point propagates automatically through this path

### env var propagation note

`subprocess_utils.run_claude_command()` is the single execution path for all Claude CLI invocations (ll-auto via `AutoManager`, ll-sprint single-issue via `process_issue_inplace`, ll-parallel via `_run_claude_base` alias). Setting `os.environ["LL_HANDOFF_THRESHOLD"]` in the CLI entry point before any manager/orchestrator is constructed is sufficient. The `worker_pool.py:613` `os.environ.copy()` site is narrow-scope (model detection only, not normal issue processing) and does not need a separate change.

### Tests
- `scripts/tests/test_cli_args.py` — add `TestAddHandoffThresholdArg` class following `TestAddIdleTimeoutArg` pattern; tests: default is None, accepts integer, rejects non-integer (argparse handles), range validation error
- `scripts/tests/test_subprocess_utils.py:244-265` — add test for `LL_HANDOFF_THRESHOLD` propagation using existing `capture_popen` side-effect pattern
- `scripts/tests/test_hooks_integration.py` — add test in `TestContextMonitor` (lines 14-129) using `env=` dict in `subprocess.run` to verify env var overrides config value

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
- `/ll:refine-issue` - 2026-03-15T17:36:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b847e6a7-cb2f-485f-85b5-ecf0ee74077a.jsonl`
- `/ll:confidence-check` - 2026-03-15T18:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75ab76d5-fcb5-4a04-bb61-499b62742b41.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f844b24a-2a77-4b56-8f27-99f2552bca01.jsonl`
- `/ll:verify-issues` - 2026-03-15T17:27:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/12de81ba-1a5b-40f3-b61a-85f37645e9af.jsonl`
- `/ll:format-issue` - 2026-03-15T16:11:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cc316fcb-f8d1-4845-aab1-5e94c57b6ed3.jsonl`
- `/ll:capture-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55d3be20-340e-4a9d-9286-575d7dc448df.jsonl`
