---
id: ENH-909
type: ENH
priority: P3
status: completed
title: "Standardize --json and --format short forms across all CLI commands"
discovered_date: 2026-04-01
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# ENH-909: Standardize --json and --format short forms across all CLI commands

## Summary

`--json` has `-j` in only 2 of 7+ commands that offer it. `--format` has `-f` in 6 commands but is missing in 2. This inconsistency means users can't rely on muscle memory across tools.

## Current Behavior

| Option | Has Short Form | Missing Short Form | Done |
|---|---|---|---|
| `--json` / `-j` | ll-verify-docs, ll-check-links | ll-loop (list/status/show/history), ll-sprint (list), ll-history (summary) | ll-issues all subcommands ✓ |
| `--format` / `-f` | ll-history, ll-deps, ll-workflows, ll-verify-docs, ll-check-links, ll-sprint analyze | — | ll-issues search, ll-issues refine-status ✓ |

## Expected Behavior

`-j` and `-f` work consistently everywhere `--json` and `--format` are offered. Users can rely on `-j` always meaning `--json` and `-f` always meaning `--format` regardless of which `ll-*` tool they're using.

## Motivation

`--json` and `--format` are the two most cross-cutting output options. Inconsistent short form availability breaks muscle memory and makes the CLI feel unpolished. These are the two easiest consistency wins.

## Proposed Solution

For each command missing the short form, add it to the `add_argument` call:

```python
# Before
parser.add_argument("--json", action="store_true", ...)

# After
parser.add_argument("-j", "--json", action="store_true", ...)
```

Before adding, verify no existing `-j` or `-f` conflict in that subcommand's argument namespace.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop.py` — add `-j` to `--json` in list, status, show, history subcommands
- `scripts/little_loops/cli/issues/` — add `-j` to `--json` in 6+ subcommands, add `-f` to `--format` in search/refine-status
- `scripts/little_loops/cli/sprint.py` — add `-j` to `--json` in list/show
- `scripts/little_loops/cli/history.py` — add `-j` to `--json` in summary subcommand

### Dependent Files (Callers/Importers)
- N/A — changes are internal to argparse definitions

### Similar Patterns
- `scripts/little_loops/cli/verify_docs.py` — existing `-j`/`-f` short forms; reference implementation
- `scripts/little_loops/cli/check_links.py` — existing `-j`/`-f` short forms; reference implementation

### Tests
- `scripts/tests/` — CLI argument parsing tests

### Documentation
- N/A (self-documenting via `--help`)

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Corrected file paths** (module packages, not flat `.py` files):

| Path in issue | Actual file |
|---|---|
| `scripts/little_loops/cli/loop.py` | `scripts/little_loops/cli/loop/__init__.py` |
| `scripts/little_loops/cli/issues/` | `scripts/little_loops/cli/issues/__init__.py` |
| `scripts/little_loops/cli/sprint.py` | `scripts/little_loops/cli/sprint/__init__.py` |
| `scripts/little_loops/cli/verify_docs.py` | `scripts/little_loops/cli/docs.py` (backs both `ll-verify-docs` and `ll-check-links`) |
| `scripts/little_loops/cli/check_links.py` | `scripts/little_loops/cli/docs.py` |

**Reference implementation** (actual lines): `scripts/little_loops/cli/docs.py:43-56` (`ll-verify-docs` `-j`/`-f`), `docs.py:136-149` (`ll-check-links` `-j`/`-f`)

**Precise change locations:**

| File | Subcommand | Change | Line | Status |
|---|---|---|---|---|
| `cli/loop/__init__.py` | `list` | add `-j` to `--json` | L170 | TODO |
| `cli/loop/__init__.py` | `status` | add `-j` to `--json` | L177 | TODO |
| `cli/loop/__init__.py` | `history` | add `-j` to `--json` | L247 | TODO |
| `cli/loop/__init__.py` | `show` | add `-j` to `--json` | L317 | TODO |
| `cli/sprint/__init__.py` | `list` | add `-j` to `--json` | L142 | TODO |
| `cli/history.py` | `summary` | add `-j` to `--json` | L53 | TODO |
| `cli/issues/__init__.py` | `list` | add `-j` to `--json` | — | DONE (commit d65cd3c6) |
| `cli/issues/__init__.py` | `search` | add `-j` to `--json` | — | DONE (commit d65cd3c6) |
| `cli/issues/__init__.py` | `search` | add `-f` to `--format` | — | DONE (commit d65cd3c6) |
| `cli/issues/__init__.py` | `count` | add `-j` to `--json` | — | DONE (commit d65cd3c6) |
| `cli/issues/__init__.py` | `sequence` | add `-j` to `--json` | — | DONE (commit d65cd3c6) |
| `cli/issues/__init__.py` | `show` | add `-j` to `--json` | — | DONE (commit d65cd3c6) |
| `cli/issues/__init__.py` | `refine-status` | add `-f` to `--format` | — | DONE (commit d65cd3c6) |
| `cli/issues/__init__.py` | `refine-status` | add `-j` to `--json` | — | DONE (commit d65cd3c6) |
| `cli/issues/__init__.py` | `next-issue` | add `-j` to `--json` | — | DONE (commit d65cd3c6) |
| `cli/issues/__init__.py` | `next-issues` | add `-j` to `--json` | — | DONE (commit d65cd3c6) |

**No `-j` conflicts** confirmed in all remaining subcommands. **Not needed** (already have short forms or lack the flag): `ll-sprint show`, `ll-sprint analyze` (`-f` present), `ll-history analyze` (`-f` present), `ll-history export` (`-f` present).

**Remaining work**: 6 changes across 3 files (loop, sprint, history). The 10 `cli/issues/__init__.py` changes were completed by commit `d65cd3c6`.

**Specific test files:**
- `scripts/tests/test_issues_cli.py` — issues CLI tests
- `scripts/tests/test_ll_loop_parsing.py` — loop argument parsing tests
- `scripts/tests/test_issue_history_cli.py` — history CLI tests
- `scripts/tests/test_cli_docs.py` — reference pattern for testing short flags (see `test_json_output_flag`)

## Implementation Steps

1. Grep for `"--json"` and `"--format"` across all CLI modules to find every definition
2. For each missing short form, check for letter conflicts in the same subcommand
3. Add `-j` / `-f` where missing
4. Run tests to verify no regressions

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete steps with file:line references:_

1. **`scripts/little_loops/cli/loop/__init__.py`** — add `"-j"` as first positional arg at L170, L177, L247, L317 (4 changes)
2. **`scripts/little_loops/cli/sprint/__init__.py`** — add `"-j"` at L142 (`list` only; `show` has no `--json`, `analyze` already has `-f`)
3. **`scripts/little_loops/cli/history.py`** — add `"-j"` at L53 (`summary` only; `analyze`/`export` already have `-f`)
4. ~~**`scripts/little_loops/cli/issues/__init__.py`**~~ — DONE (commit d65cd3c6, 2026-04-01)
5. Run: `python -m pytest scripts/tests/test_ll_loop_parsing.py scripts/tests/test_issue_history_cli.py -v`

**Remaining: 6 `add "-j"` across 3 files. (10 issues/__init__.py changes completed by commit d65cd3c6.)**

## Scope Boundaries

- Only `--json` → `-j` and `--format` → `-f` standardization
- Do NOT add these options to commands that don't currently have them
- Do NOT change output format behavior

## Impact

- **Priority**: P3 - Cross-cutting consistency improvement
- **Effort**: Small - Straightforward argparse additions, no logic changes
- **Risk**: Low - Only adds new short aliases for existing options
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| [docs/reference/API.md](../../docs/reference/API.md) | CLI module reference |

## Labels

`cli`, `consistency`, `ergonomics`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-04-01T22:07:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5150c9c4-7c61-4179-a619-17b9efe065b3.jsonl`
- `/ll:confidence-check` - 2026-04-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:refine-issue` - 2026-04-01T21:44:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2d71985-ba62-4c95-940c-27ba0048b64e.jsonl`
- `/ll:format-issue` - 2026-04-01T21:39:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c8f9b06-8a34-48b3-ae2b-5e9fcf341116.jsonl`
- `/ll:capture-issue` - 2026-04-01 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4505b861-be5c-4195-9079-b2b3bcde3985.jsonl`

---

## Resolution

**Completed** — All 6 remaining `--json` / `-j` short forms added across 3 files:

- `scripts/little_loops/cli/loop/__init__.py`: `list`, `status`, `history`, `show` subcommands
- `scripts/little_loops/cli/sprint/__init__.py`: `list` subcommand
- `scripts/little_loops/cli/history.py`: `summary` subcommand

6 new tests written (TDD) and passing. No regressions introduced.

## Status

**Completed** | Created: 2026-04-01 | Resolved: 2026-04-01 | Priority: P3
