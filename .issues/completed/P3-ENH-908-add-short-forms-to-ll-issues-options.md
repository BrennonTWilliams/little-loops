---
id: ENH-908
type: ENH
priority: P3
status: active
title: "Add short forms to ll-issues command options"
discovered_date: 2026-04-01
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
---

# ENH-908: Add short forms to ll-issues command options

## Summary

`ll-issues` is the worst offender for missing short forms: **zero** short options exist across all 10 subcommands (list, search, count, sequence, show, impact-effort, refine-status, next-action, next-issue, next-issues), totaling 35+ long-only options.

## Current Behavior

Every option in `ll-issues` requires the full long form. For example:
```bash
ll-issues list --type BUG --priority P2 --status active --json
ll-issues search --type ENH --priority P3 --format table --limit 10 --sort priority --desc
```

No subcommand offers any `-x` short forms.

## Expected Behavior

High-frequency options have short forms consistent with other `ll-*` commands:

| Long Option | Short Form | Used In |
|---|---|---|
| `--json` | `-j` | list, search, count, show, sequence, refine-status, next-issue, next-issues |
| `--type` | `-T` | list, search, count, sequence, impact-effort, refine-status |
| `--format` | `-f` | search, refine-status |
| `--sort` | `-s` | list, search |
| `--limit` | `-n` | search, sequence |
| `--priority` | `-p` | list, search, count |
| `--status` | `-S` | list, search, count |
| `--config` | `-C` | all subcommands (via shared arg) |

Example after:
```bash
ll-issues list -T BUG -p P2 -S active -j
ll-issues search -T ENH -p P3 -f table -n 10 -s priority --desc
```

## Motivation

`ll-issues` is the most frequently used CLI tool for issue triage and inspection. The complete absence of short forms makes interactive use unnecessarily verbose, especially for search/list/count which are the most common subcommands.

## Success Metrics

- Short form coverage: 0 → 8 high-frequency options have short forms across all applicable subcommands
- No letter conflicts within any subcommand (verified by conflict audit in Implementation Step 2)
- All existing long-form options remain valid (no regressions)
- `ll-issues <subcommand> --help` shows both short and long forms for each added option

## Proposed Solution

Add short forms to the argparse definitions in the `ll-issues` CLI modules. The short forms should match conventions already established in other `ll-*` commands (e.g., `-j` for `--json`, `-f` for `--format`).

Focus on the 8 highest-frequency options listed above. Lower-frequency options like `--include-completed`, `--date-field`, `--no-key`, `--refine-cap` can remain long-form only.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/` — all subcommand modules that define argparse options

### Dependent Files (Callers/Importers)
- N/A — changes are internal to argparse definitions

### Similar Patterns
- Other `ll-*` CLI tools with existing short forms: `ll-auto`, `ll-parallel`, `ll-sprint` — use same conventions (`-j` for `--json`, `-f` for `--format`, `-C` for `--config`)
- `scripts/little_loops/cli/` — audit all modules to ensure no letter conflicts with conventions from sibling tools

### Tests
- `scripts/tests/` — CLI argument parsing tests for ll-issues

### Documentation
- N/A (short forms are self-documenting via `--help`)

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Architecture clarification**: All 12 subcommand parsers (`list`, `search`, `count`, `sequence`, `show`, `impact-effort`, `refine-status`, `append-log`, `next-action`, `next-issue`, `next-issues`, `next-id`) are defined in a **single file**: `scripts/little_loops/cli/issues/__init__.py`. The handler modules (`list_cmd.py`, `search.py`, etc.) only contain `cmd_*` functions — they do not define parsers.

**Files to Modify (concrete)**:
- `scripts/little_loops/cli/issues/__init__.py` — all `add_argument` calls for the 8 target options
- `scripts/little_loops/cli_args.py:35–42` — `add_config_arg()` function; add `-C` here to cover all 12 ll-issues subcommands at once (note: this helper is also used by `ll-auto`, `ll-sprint`; verify no cross-tool conflict before adding `-C` there)

**Correction — not zero existing short forms**: one short form already exists in ll-issues: `-n` for `--limit` on `list` only (`__init__.py:107–113`). The `search` and `sequence` subcommands also have `--limit` (lines 212 and 237–239) but lack `-n`.

**Exact `add_argument` line numbers in `scripts/little_loops/cli/issues/__init__.py`**:

| Option | Subcommand | Line |
|--------|-----------|------|
| `--json` | list | 105 |
| `--json` | search | 205 |
| `--json` | count | 229 |
| `--json` | sequence | 240 |
| `--json` | show | 246 |
| `--json` | refine-status | 273 |
| `--json` | next-issue | 336 |
| `--json` | next-issues | 354 |
| `--type` | list | 88 |
| `--type` | search | 142 |
| `--type` | count | 217 |
| `--type` | sequence | 236 |
| `--type` | impact-effort | 251 |
| `--type` | refine-status | 260 |
| `--format` | search | 206 |
| `--format` | refine-status | 261 |
| `--sort` | list | 114 |
| `--sort` | search | 186 |
| `--limit` | list | 107 (already has `-n`) |
| `--limit` | search | 212 (needs `-n`) |
| `--limit` | sequence | 237 (needs `-n`) |
| `--priority` | list | 89 |
| `--priority` | search | 150 |
| `--priority` | count | 218 |
| `--status` | list | 94 |
| `--status` | search | 157 |
| `--status` | count | 223 |
| `--config` | all subcommands | via `add_config_arg()` in `cli_args.py:35` |

**Conflict audit result**: `-j`, `-T`, `-f`, `-s`, `-S`, `-C` are **not used** in any ll-issues subcommand. No conflicts. `-n` is already claimed by `list --limit` (line 108) — consistent extension to `search` and `sequence` is safe within ll-issues (argparse enforces short-form uniqueness per-subparser, not globally).

**Argument ordering convention**: dominant pattern in this codebase is long-form first (`"--long", "-s"`), used in `cli_args.py` and `cli/loop/__init__.py`. Short-first exists in `cli/history.py` and `cli/deps.py`. For consistency with `ll-issues` existing style (line 107 uses `"--limit", "-n"`), use **long-form first**.

**Similar pattern — `add_config_arg` in sibling tools**: `ll-sprint` calls `add_config_arg()` at `cli/sprint/__init__.py:121,148,175,196`. `ll-parallel` defines `--config` manually without using `add_config_arg` (`cli/parallel.py:134`). Adding `-C` to `add_config_arg()` would NOT affect `ll-parallel` but WOULD affect any tool that calls the helper.

**Test files**:
- `scripts/tests/test_issues_cli.py` — primary integration tests for ll-issues; use `patch.object(sys, "argv", [...])` pattern
- `scripts/tests/test_issues_search.py` — search subcommand tests
- `scripts/tests/test_next_issues.py` — next-issues subcommand tests
- `scripts/tests/test_cli_args.py` — pattern for testing shared helper short forms (see `test_short_flag` at line 479)
- `scripts/tests/test_cli.py:62–65` — pattern: one test method per short form, named `test_<flag>_short`

## Implementation Steps

1. Identify all argparse `add_argument` calls across `ll-issues` subcommand modules
2. Add short forms for the 8 priority options, checking for per-subcommand letter conflicts
3. Run existing tests to verify no regressions
4. Verify `--help` output for each subcommand

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete steps with file:line references:_

1. ~~**Modify `scripts/little_loops/cli_args.py:35–42`**: Add `"-C"` to `add_config_arg()`~~ — **Already done by ENH-907** (commit `821be7d0`). `add_config_arg()` already defines `"--config", "-C"` at `cli_args.py:37–39`. Skip this step.

2. **Modify `scripts/little_loops/cli/issues/__init__.py`** — add short forms inline, using **long-form first** convention (matching existing `-n` at line 108):
   - Lines 88, 142, 217, 236, 251, 260: add `"-T"` to each `--type` call
   - Lines 89, 150, 218: add `"-p"` to each `--priority` call
   - Lines 94, 157, 223: add `"-S"` to each `--status` call
   - Lines 105, 205, 229, 240, 246, 273, 336, 354: add `"-j"` to each `--json` call
   - Lines 206, 261: add `"-f"` to each `--format` call
   - Lines 114, 186: add `"-s"` to each `--sort` call
   - Lines 212, 237: add `"-n"` to remaining `--limit` calls (list already has it at line 107)

3. **Add test coverage in `scripts/tests/test_issues_cli.py`**: Follow pattern from `scripts/tests/test_cli.py:62–65` — one test per short form per subcommand. Priority: test `-j`/`-T`/`-p`/`-S` on `list` and `search` (highest-frequency subcommands).

4. **Verify `--help` output**: Run `ll-issues list --help`, `ll-issues search --help`, `ll-issues count --help` — confirm short forms appear next to their long equivalents.

5. **Run full test suite**: `python -m pytest scripts/tests/test_issues_cli.py scripts/tests/test_issues_search.py scripts/tests/test_next_issues.py -v`

## API/Interface

New short-form CLI options (additive — existing long forms preserved):

| Long Option | Short Form | Subcommands |
|---|---|---|
| `--json` | `-j` | list, search, count, show, sequence, refine-status, next-issue, next-issues |
| `--type` | `-T` | list, search, count, sequence, impact-effort, refine-status |
| `--format` | `-f` | search, refine-status |
| `--sort` | `-s` | list, search |
| `--limit` | `-n` | search, sequence |
| `--priority` | `-p` | list, search, count |
| `--status` | `-S` | list, search, count |
| `--config` | `-C` | all subcommands (shared arg) |

## Scope Boundaries

- Only the 8 high-frequency options listed in Expected Behavior
- Do NOT add short forms to rarely-used options (`--include-completed`, `--date-field`, `--no-key`, etc.)
- Do NOT change option semantics or defaults
- `--asc`/`--desc` are flags that don't need short forms

## Impact

- **Priority**: P3 - Significant ergonomic improvement for the most-used inspection tool
- **Effort**: Medium - 10 subcommand files to audit, ~8 options each needing conflict checks
- **Risk**: Low - argparse natively supports short forms; existing long forms remain valid
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| [docs/reference/API.md](../../docs/reference/API.md) | Python module reference for ll-issues CLI |

## Labels

`cli`, `ergonomics`, `ll-issues`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-04-01T22:01:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c509a9e3-f1f9-4a0d-aea8-18ad4562dea2.jsonl`
- `/ll:refine-issue` - 2026-04-01T21:43:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b4eae71-f640-463f-b8dc-e190ea206a9d.jsonl`
- `/ll:format-issue` - 2026-04-01T21:39:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/674284e2-26fb-4e5f-8988-b52f3854ef01.jsonl`
- `/ll:capture-issue` - 2026-04-01 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4505b861-be5c-4195-9079-b2b3bcde3985.jsonl`
- `/ll:confidence-check` - 2026-04-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/99a98fe8-6dc1-4507-bb32-fba2edc2d681.jsonl`

---

## Resolution

**Implemented** in `scripts/little_loops/cli/issues/__init__.py`. Added short forms for all 8 high-frequency options across all applicable subcommands:
- `-T` (`--type`): list, search, count, sequence, impact-effort, refine-status
- `-p` (`--priority`): list, search, count
- `-S` (`--status`): list, search, count
- `-j` (`--json`): list, search, count, sequence, show, refine-status, next-issue, next-issues
- `-s` (`--sort`): list, search
- `-f` (`--format`): search, refine-status
- `-n` (`--limit`): search, sequence (list already had it)
- `-C` (`--config`): already done by ENH-907 via `add_config_arg()`

Added 10 short-form tests in `scripts/tests/test_issues_cli.py` (`TestIssuesCLIShortForms`). All 125 tests pass.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-01T22:05:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fc7893d1-dd13-4e96-94d9-4598fb9fa5b5.jsonl`
- `/ll:manage-issue` - 2026-04-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c509a9e3-f1f9-4a0d-aea8-18ad4562dea2.jsonl`

## Status

**Completed** | Created: 2026-04-01 | Priority: P3
