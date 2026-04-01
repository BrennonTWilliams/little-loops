---
id: ENH-907
type: ENH
priority: P2
status: active
title: "Add short forms to shared CLI arguments in cli_args.py"
discovered_date: 2026-04-01
discovered_by: capture-issue
---

# ENH-907: Add short forms to shared CLI arguments in cli_args.py

## Summary

Six shared options in `cli_args.py` lack short forms. Since these propagate to `ll-auto`, `ll-parallel`, and `ll-sprint`, adding short forms here has the highest impact-to-effort ratio of all CLI ergonomic improvements.

## Current Behavior

Shared options `--config`, `--type`, `--skip`, `--only`, `--idle-timeout`, `--handoff-threshold`, and `--context-limit` all require the full long-form flag. Users must type e.g. `ll-auto --config custom.json --type BUG --skip ENH-042` every time.

## Expected Behavior

Common shared options have single-character short forms:

| Long Option | Short Form |
|---|---|
| `--config` | `-C` |
| `--type` | `-T` |
| `--skip` | `-s` |
| `--only` | `-o` (where no `--output` conflict exists) |

`--idle-timeout`, `--handoff-threshold`, and `--context-limit` are tuning parameters where long-form-only is acceptable.

## Motivation

These 4 options are used frequently in interactive workflows. The shared module propagates to 3+ CLI tools, so each short form added here immediately benefits multiple commands. This is the single highest-leverage change for CLI ergonomics.

## Proposed Solution

In `scripts/little_loops/shared/cli_args.py`, update each `add_argument` call to include the short form as the first positional argument:

```python
# Before
parser.add_argument("--config", ...)

# After
parser.add_argument("-C", "--config", ...)
```

For `--only` / `-o`: check for conflicts with `--output` in commands that import both. If a conflict exists, skip `-o` for `--only` or use an alternative like `-O`.

## Integration Map

### Files to Modify
- `scripts/little_loops/shared/cli_args.py` — add short forms to `add_config_arg`, `add_type_filter_arg`, `add_skip_arg`, `add_only_arg`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/auto.py` — imports shared args
- `scripts/little_loops/cli/parallel.py` — imports shared args
- `scripts/little_loops/cli/sprint.py` — imports shared args
- `scripts/little_loops/cli/sync_cmd.py` — imports `add_config_arg`
- `scripts/little_loops/cli/issues/` — imports `add_config_arg`, `add_type_filter_arg`
- `scripts/little_loops/cli/deps.py` — imports `add_config_arg`

### Tests
- `scripts/tests/` — test files for CLI argument parsing

### Documentation
- N/A (short forms are self-documenting via `--help`)

### Configuration
- N/A

## Implementation Steps

1. Add short forms to `add_config_arg` (`-C`), `add_type_filter_arg` (`-T`), `add_skip_arg` (`-s`), `add_only_arg` (`-o` or `-O`)
2. Grep for `-C`, `-T`, `-s` conflicts in downstream CLI modules to avoid collisions
3. Run existing tests to verify no regressions
4. Verify `--help` output shows both short and long forms

## Scope Boundaries

- Only the 4 high-frequency shared options listed above
- Do NOT add short forms to `--idle-timeout`, `--handoff-threshold`, `--context-limit` (tuning params, long-form acceptable)
- Do NOT change any option semantics or defaults

## Impact

- **Priority**: P2 - High-leverage ergonomic improvement affecting 3+ CLI tools from a single change
- **Effort**: Small - 4 `add_argument` modifications plus conflict checks
- **Risk**: Low - argparse natively supports short forms; existing long forms remain valid
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | Development guidelines for CLI tools |
| [docs/reference/API.md](../../docs/reference/API.md) | Python module reference including cli_args |

## Labels

`cli`, `ergonomics`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-01 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4505b861-be5c-4195-9079-b2b3bcde3985.jsonl`

---

## Status

**Open** | Created: 2026-04-01 | Priority: P2
