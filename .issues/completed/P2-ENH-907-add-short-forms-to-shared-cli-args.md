---
id: ENH-907
type: ENH
priority: P2
status: active
title: "Add short forms to shared CLI arguments in cli_args.py"
discovered_date: 2026-04-01
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 97
---

# ENH-907: Add short forms to shared CLI arguments in cli_args.py

## Summary

Six shared options in `scripts/little_loops/cli_args.py` lack short forms. Since these propagate to `ll-auto`, `ll-parallel`, and `ll-sprint`, adding short forms here has the highest impact-to-effort ratio of all CLI ergonomic improvements.

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

In `scripts/little_loops/cli_args.py`, update each `add_argument` call to include the short form as the first positional argument:

```python
# Before
parser.add_argument("--config", ...)

# After
parser.add_argument("--config", "-C", ...)
```

Note: The codebase convention (from all existing `add_*` functions) is long form **first**, short form **second** — see `add_dry_run_arg` (`cli_args.py:17-22`) and `add_priority_arg` (`cli_args.py:302-310`) as the authoritative pattern.

For `--only` / `-o`: research confirms no conflict. `-o` is used only in `ll-messages` (`messages.py:65`), which never calls `add_only_arg`. `-o` is safe to use.

**Special case — `ll-parallel`**: `parallel.py` does NOT use `add_config_arg` — it adds `--config` manually at `parallel.py:134-139` with no short form. Adding `-C` to `add_config_arg` will not affect `ll-parallel`. The manual definition at `parallel.py:134-139` must also be updated separately to add `-C`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli_args.py` — add short forms to `add_config_arg` (line 35), `add_only_arg` (line 45), `add_skip_arg` (line 55), `add_type_arg` (line 313)
- `scripts/little_loops/cli/parallel.py:134-139` — add `-C` to the manually-defined `--config` argument (does not use `add_config_arg`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/auto.py` — imports shared args via `add_common_auto_args`; adds `-c`/`--category` locally (`auto.py:52-56`)
- `scripts/little_loops/cli/parallel.py` — adds `-w`/`--workers` (line 59), `-p`/`--priority` (line 66), `-c`/`--cleanup` (line 79) locally; `-C` is free
- `scripts/little_loops/cli/sprint/__init__.py` — imports shared args into `create` and `run` subparsers; `-C`, `-T`, `-s`, `-o` are all free on `run` subparser
- `scripts/little_loops/cli/sync.py` — imports `add_config_arg`; `-C` is free on top-level parser
- `scripts/little_loops/cli/issues/__init__.py` — imports `add_config_arg`; `-C` is free
- `scripts/little_loops/cli/history.py` — imports `add_config_arg`; `-C` is free
- `scripts/little_loops/cli/gitignore.py` — imports `add_config_arg`; `-C` is free

### Similar Patterns
- `cli_args.py:17-22` (`add_dry_run_arg`): canonical pattern for adding short forms — long form first, short form second
- `cli_args.py:302-310` (`add_priority_arg`): same pattern with `type=str` and `default=None` — closest match to `add_type_arg` and `add_skip_arg`

### Conflict Analysis (Confirmed Safe)

_Added by `/ll:refine-issue` — based on codebase analysis:_

| Short | Proposed For | Conflicts? | Notes |
|-------|-------------|-----------|-------|
| `-C` | `--config` | No | Unused in all CLI modules |
| `-T` | `--type` | No | Unused in all CLI modules |
| `-s` | `--skip` | No | Used in `ll-loop history --state` (`loop/__init__.py:252`) but that subparser never calls `add_skip_arg` |
| `-o` | `--only` | No | Used in `ll-messages --output` (`messages.py:65`) but `add_only_arg` is never called for `ll-messages` |

### Tests
- `scripts/tests/test_cli_args.py` — primary test file; follow the three-test structure: long form, short form, default (see `TestAddDryRunArg` at line ~212 as the canonical pattern)
- `scripts/tests/test_cli.py:28-36` — inline parser recreation for `ll-auto`; currently includes `--config` without short form; may need updating after this change

### Documentation
- N/A (short forms are self-documenting via `--help`)

### Configuration
- N/A

## Implementation Steps

1. In `scripts/little_loops/cli_args.py`, add short forms following the `add_dry_run_arg` pattern (long first, short second):
   - `cli_args.py:35-42` (`add_config_arg`): add `"-C"` after `"--config"`
   - `cli_args.py:45-52` (`add_only_arg`): add `"-o"` after `"--only"`
   - `cli_args.py:55-69` (`add_skip_arg`): add `"-s"` after `"--skip"`
   - `cli_args.py:313-320` (`add_type_arg`): add `"-T"` after `"--type"`
2. In `scripts/little_loops/cli/parallel.py:134-139`, add `"-C"` to the manually-defined `--config` argument (this parser does not use `add_config_arg`)
3. Add short-form tests in `scripts/tests/test_cli_args.py` following the three-test structure: long form, `-X` short form, default — see `TestAddDryRunArg` (line ~212) as the pattern
4. Run `python -m pytest scripts/tests/test_cli_args.py scripts/tests/test_cli.py -v`
5. Verify `ll-auto --help`, `ll-parallel --help`, `ll-sprint run --help` each show both forms

## API/Interface

CLI argument short forms added (backward-compatible — existing long forms remain valid):

| Short | Long | Function | Propagates To |
|-------|------|----------|---------------|
| `-C` | `--config` | `add_config_arg()` | ll-auto, ll-parallel, ll-sprint, ll-sync, ll-issues, ll-deps |
| `-T` | `--type` | `add_type_arg()` | ll-auto, ll-parallel, ll-sprint, ll-issues |
| `-s` | `--skip` | `add_skip_arg()` | ll-auto, ll-parallel, ll-sprint |
| `-o`/`-O` | `--only` | `add_only_arg()` | ll-auto, ll-parallel, ll-sprint (conflict-dependent) |

## Scope Boundaries

- Only the 4 high-frequency shared options listed above
- Do NOT add short forms to `--idle-timeout`, `--handoff-threshold`, `--context-limit` (tuning params, long-form acceptable)
- Do NOT change any option semantics or defaults

## Success Metrics

- `--help` output for `ll-auto`, `ll-parallel`, `ll-sprint` shows both short and long forms for `-C`/`--config`, `-T`/`--type`, `-s`/`--skip`, `-o`/`--only`
- `ll-auto -C custom.json -T BUG -s ENH-042` works identically to the long-form equivalent
- No short-form conflicts with per-command flags (verified by grep across downstream CLIs)
- All existing CLI tests pass

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

## Resolution

**Status**: Completed on 2026-04-01

**Changes made**:
- `scripts/little_loops/cli_args.py`: Added `-C` to `add_config_arg`, `-o` to `add_only_arg`, `-s` to `add_skip_arg`, `-T` to `add_type_arg` — all following long-first, short-second pattern
- `scripts/little_loops/cli/parallel.py:134-139`: Added `-C` to manually-defined `--config` argument
- `scripts/tests/test_cli_args.py`: Added `TestAddOnlyArg` class (3 tests) and `test_short_flag` methods to `TestAddConfigArg`, `TestAddTypeArg`, `TestAddSkipArg`

**Verification**: All 212 tests pass; lint and mypy clean; `ll-auto --help` shows all 4 short forms.

## Session Log
- `/ll:ready-issue` - 2026-04-01T21:56:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f917633e-ae5f-42bc-93e3-c4dbb5873058.jsonl`
- `/ll:refine-issue` - 2026-04-01T21:48:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a5166e6-7937-4565-82dc-5d79146cbc1f.jsonl`
- `/ll:format-issue` - 2026-04-01T21:45:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2d71985-ba62-4c95-940c-27ba0048b64e.jsonl`
- `/ll:capture-issue` - 2026-04-01 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4505b861-be5c-4195-9079-b2b3bcde3985.jsonl`
- `/ll:confidence-check` - 2026-04-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bd663ffc-6e9a-4b4c-897e-5f22c749b3c0.jsonl`
- `/ll:manage-issue` - 2026-04-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---

## Status

**Completed** | Created: 2026-04-01 | Completed: 2026-04-01 | Priority: P2
