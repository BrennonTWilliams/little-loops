---
id: ENH-1780
title: Add --json flag consistently across all ll-* CLIs
type: enh
status: done
priority: P3
captured_at: '2026-05-29T02:23:45Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
- cli
- agent-composability
- captured
confidence_score: 100
outcome_confidence: 73
score_complexity: 13
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
size: Very Large
---

# ENH-1780: Add --json flag consistently across all ll-* CLIs

## Summary

Add `--json` flag support to every `ll-*` CLI command that doesn't yet have it, making all CLIs reliably composable in agent-driven workflows. Modeled after CLI-Anything's universal `--json` contract.

## Current Behavior

Some CLIs support `--json` for structured machine-readable output (`ll-issues list`, `ll-loop list`, `ll-logs discover`), but many commands and CLIs don't. Agents must parse human-formatted text (tables, colored output), which is brittle and breaks when output formatting changes.

## Expected Behavior

Every `ll-*` CLI command that produces output supports a `--json` flag. When passed, the command emits structured JSON to stdout. Human-readable output (tables, colors) remains the default. The contract is: "if it outputs data, it outputs JSON with `--json`."

## Motivation

Agents composing CLI calls need structured, parseable output. CLI-Anything mandates `--json` on every command for this exact reason — it's what makes the generated CLIs "agent-native." In little-loops, the inconsistency forces agents to either:
- Parse human-formatted text (brittle, breaks on formatting changes)
- Skip CLI composition entirely and read files directly (slower, context-heavy)

Quantified: every `ll-*` command without `--json` is a command an agent can't reliably compose into a pipeline.

## Success Metrics

- All `ll-*` CLI commands that produce data output accept `--json` (target: 0 remaining without support)
- Agent workflows can query structured data from every CLI without text parsing
- Zero agent pipeline failures caused by human-format output parsing

## Scope Boundaries

- **In scope**: Adding `--json` to data-emitting commands across all `ll-*` CLIs; creating shared `add_json_arg()` argparse helper in `cli_args.py`; adding JSON output tests
- **Out of scope**: Changing default output format (human-readable stays default); modifying JSON schema of commands that already support `--json`; adding `--json` to purely imperative commands (e.g., `ll-loop run`) that produce no data output; TUI/interactive commands

## Proposed Solution

1. Audit all `ll-*` CLIs for `--json` support gaps. Priority targets based on agent usage:
   - `ll-sync status/diff` — sync state queries (`sync.py`)
   - `ll-logs discover/tail` — log discovery and streaming (`logs.py`)
   - `ll-session search` — session store FTS queries (`session.py`)
   - `ll-deps validate` — dependency validation reports (`deps.py`)
   - `ll-gitignore` — suggestion data (`gitignore.py`)
   - `ll-verify-skill-budget` — numerical output (`docs.py`)

2. Add `add_json_arg(parser)` shared helper in `scripts/little_loops/cli_args.py`, following the existing pattern of `add_dry_run_arg()`, `add_config_arg()`, etc.:
   ```python
   def add_json_arg(parser: argparse.ArgumentParser, help_text: str = "Output as JSON") -> None:
       parser.add_argument("-j", "--json", action="store_true", help=help_text)
   ```

3. Add JSON output formatters alongside existing human-readable output in each CLI, using the existing `print_json()` from `scripts/little_loops/cli/output.py` (line 114).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Architecture correction**: All `ll-*` CLIs use **argparse** (not Click). The `[project.scripts]` entry points in `scripts/pyproject.toml` map to `main_*()` functions that build `argparse.ArgumentParser` with `RawDescriptionHelpFormatter`. There is no Click usage anywhere in the CLI layer. The shared helper should be a function in `cli_args.py` following the existing pattern of `add_dry_run_arg(parser)`, `add_config_arg(parser)`, `add_resume_arg(parser)`, etc. — not a Click decorator.

**Existing `--json` pattern** (consistent across 15+ subcommands):
- Argument: `parser.add_argument("-j", "--json", action="store_true", help="Output as JSON")`
- Branching: `if getattr(args, "json", False): print_json(data); return 0`
- Output: `print_json()` at `scripts/little_loops/cli/output.py:114` — `print(json.dumps(data, indent=2))`

**Gap audit completed**: 29 `ll-*` CLI entry points exist. 11 already have full `--json` support on data-emitting commands. 6 have gaps (listed in Integration Map). 12 are imperative/dev-tool CLIs where `--json` is N/A or low-value. See Integration Map for the prioritized gap list.

**Companion issue**: ENH-1781 covers shared output formatting (colors, tables, progress bars) — complementary but separate from the `--json` flag contract.

## API/Interface

```python
# Shared helper in scripts/little_loops/cli_args.py
def add_json_arg(parser: argparse.ArgumentParser, help_text: str = "Output as JSON") -> None:
    """Add --json/-j argument to a subparser for machine-readable output."""
    parser.add_argument("-j", "--json", action="store_true", help=help_text)
```

Usage in a CLI:
```python
from little_loops.cli_args import add_json_arg
# ...
list_parser = subparsers.add_parser("list", help="List items")
add_json_arg(list_parser)
# ...
args = parser.parse_args()
if args.json:
    print_json(data)
    return 0
```

## Integration Map

### Files to Modify (priority order — data-emitting CLIs lacking `--json`)

**Priority 1 — Agent-composability gaps:**
- `scripts/little_loops/cli/sync.py` — `ll-sync status` and `ll-sync diff` produce structured data with no `--json` flag. `SyncStatus` and `SyncResult` dataclasses already exist in `scripts/little_loops/sync.py`.
- `scripts/little_loops/cli/logs.py` — `ll-logs discover` (line 314, prints paths) and `ll-logs tail` (line 319, streams events) have no `--json`.
- `scripts/little_loops/cli/session.py` — `ll-session search` (line 46) lacks `--json`, unlike `recent` (line 63) which already has it.

**Priority 2 — Secondary data output:**
- `scripts/little_loops/cli/deps.py` — `ll-deps validate` (line 141) produces a text report only. `analyze` already has `--format json`.
- `scripts/little_loops/cli/gitignore.py` — `ll-gitignore` produces suggestion data with no `--json`.

**Priority 3 — Minor/nice-to-have:**
- `scripts/little_loops/cli/docs.py` — `ll-verify-skill-budget` (`main_verify_skill_budget()`, lines 107-201) has numerical output with no `--json`.

**Shared infrastructure (new):**
- `scripts/little_loops/cli_args.py` — Add `add_json_arg(parser)` helper following existing pattern of `add_dry_run_arg()`, `add_config_arg()`, etc.

### Already-complete CLIs (no changes needed)
- `ll-issues` — `--json` on all data-emitting subcommands: list, search, count, sequence, show, path, impact-effort, clusters, refine-status, next-issue, next-issues
- `ll-loop` — `--json` on list, status, show, history, next-loop, audit-meta
- `ll-doctor`, `ll-ctx-stats`, `ll-verify-docs`, `ll-check-links` — top-level `--json`
- `ll-history` — `--json` on summary, `--format json` on analyze
- `ll-sprint` — `--json` on list, show; `--format json` on analyze
- `ll-learning-tests` — check and list always output JSON
- `ll-action` — always-JSON output via `--output json`

### Dependent Files (Callers/Importers)
- Orchestrators (`ll-auto`, `ll-parallel`, `ll-sprint`) use Python APIs directly — they do **not** parse CLI JSON output. Adding `--json` primarily benefits human/ad-hoc scripting and agent-driven CLI composition.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — re-exports all `main_*` functions (no changes needed; verified no new entry points)
- `scripts/little_loops/__init__.py` — re-exports `SyncResult`, `SyncStatus` (no changes needed; dataclasses already serializable)
- `scripts/pyproject.toml` — entry points for all affected CLIs (no changes needed; no new subcommands)
- 22 existing callers of `print_json()` (from `cli/output.py`) — all already have `--json` on data-emitting subcommands; the new `add_json_arg()` helper is additive and backward-compatible

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Test files requiring new `--json` output tests:**

- `scripts/tests/test_cli_args.py` — new `TestAddJsonArg` class following the `TestAddDryRunArg` pattern (line 225): test `--json`/`-j` flag, default False. Every `add_*_arg` function in `cli_args.py` has a matching test class.
- `scripts/tests/test_cli_sync.py` — JSON output tests for `status`/`push`/`pull` subcommands. Follow Pattern B (capsys + `json.loads()`) from `test_cli.py:2457` (`test_list_json_output`).
- `scripts/tests/test_ll_logs.py` — JSON output tests for `discover`/`extract` subcommands. `TestDiscover` already uses capsys with temp dirs (line 30).
- `scripts/tests/test_ll_session.py` — JSON output test for `search` subcommand (note: `recent` already has `--json` at `session.py:62-64`). `TestMainSession` already uses capsys + temp SQLite DBs (line 45).
- `scripts/tests/test_dependency_mapper.py` — JSON output tests for `validate` subcommand in `TestMainCLI` (line 1299). Verify `--json` on `validate` does not conflict with `--format json` on `analyze`.
- `scripts/tests/test_gitignore_cmd.py` — JSON output tests for dry-run/apply. Follow Pattern B (capsys + `json.loads()`).

**Already listed (kept for reference):**
- `scripts/tests/test_cli.py` — capsys + `json.loads()` pattern (see `test_list_json_output` at line 2457)
- `scripts/tests/test_cli_docs.py` — `test_json_output_flag` pattern (line 38); `ll-verify-docs` and `ll-check-links` already have `--json` — use as reference implementation

**Test verification checklist (per CLI):**
- Verify `--json` flag appears in `--help` output
- Verify short flag `-j` works equivalently
- Verify valid JSON output (parse with `json.loads()`)
- Verify no ANSI escape codes in JSON output
- Verify exit code is 0

**Tests that may break (verification needed):**
- `test_ll_logs.py` — `TestDiscover` asserts on text content via capsys (lines 81-280). Safe since `--json` is opt-in; default text output unchanged.
- `test_ll_session.py` — `test_search_outputs_match`, `test_search_no_match` (lines 52-66). Safe for same reason.
- `test_dependency_mapper.py:1499` — `test_validate_json_output_includes_new_fields` uses `--format json` on `analyze`. Verify `--json` flag doesn't conflict with `--format` choices interaction.

### Documentation

- `docs/reference/API.md` — document the universal `--json` contract

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — add `--json` to flag tables in 6 CLI sections: `ll-sync` (status/diff), `ll-logs` (discover/tail), `ll-session` (search), `ll-deps` (validate), `ll-gitignore`, `ll-verify-skill-budget`. Note: `ll-session recent` already has `--json` in code but is NOT documented in CLI.md (existing gap).
- `commands/help.md` — lists all affected CLIs at lines 47, 168, 253-271. May add a note about the universal `--json` contract.
- `skills/map-dependencies/SKILL.md` — heavily documents `ll-deps validate` invocations (lines 98, 105, 122, 125, 190). Adding `--json` to `validate` creates a pattern inconsistency: `validate` uses `--json` while `analyze` uses `--format json`. The skill doc should note both flags or the team should consider normalizing to `--json` on `analyze` as well.

### Configuration
- N/A (no config-schema.json changes needed; no hooks.json entries reference affected CLIs)

## Implementation Steps

**Phase 1 — Shared infrastructure:**
1. Add `add_json_arg(parser)` to `scripts/little_loops/cli_args.py` — follow existing helpers like `add_dry_run_arg()` (line 15) and `add_config_arg()` (line 35) for the function signature pattern.

**Phase 2 — Priority 1 CLIs (agent-composability):**
2. Add `--json` to `ll-sync status` and `ll-sync diff` in `scripts/little_loops/cli/sync.py` — serialize `SyncStatus` and `SyncResult` dataclasses (already defined in `scripts/little_loops/sync.py`). Pattern: follow `ll-doctor` in `scripts/little_loops/cli/doctor.py:30-38` for inline JSON object construction.
3. Add `--json` to `ll-logs discover` in `scripts/little_loops/cli/logs.py:314` — output discovered log paths as `{"paths": [...]}` JSON array.
4. Add `--json` to `ll-session search` in `scripts/little_loops/cli/session.py:46` — follow the existing `recent --json` pattern at `session.py:108-109` (calls `print_json(list(rows))`).

**Phase 3 — Priority 2 CLIs:**
5. Add `--json` to `ll-deps validate` in `scripts/little_loops/cli/deps.py:141` — output validation results as structured JSON. Follow pattern from `ll-verify-docs` in `docs.py:87-94` (format-function dispatch).
6. Add `--json` to `ll-gitignore` in `scripts/little_loops/cli/gitignore.py` — output suggestion data as JSON.

**Phase 4 — Tests (expanded by `/ll:wire-issue`):**
7. Add `TestAddJsonArg` class to `scripts/tests/test_cli_args.py` — follow `TestAddDryRunArg` pattern (line 225): test `--json` long flag, `-j` short flag, default `False`.
8. Add JSON output tests to `scripts/tests/test_cli_sync.py` — test `status --json`, `push --json`, `pull --json`. Follow Pattern B (capsys + `json.loads()`) from `test_cli.py:2457`.
9. Add JSON output tests to `scripts/tests/test_ll_logs.py` — test `discover --json` outputs `{"paths": [...]}`, `extract --json` outputs structured data. Use existing temp dir + capsys patterns in `TestDiscover` (line 30).
10. Add JSON output test to `scripts/tests/test_ll_session.py` — test `search --json --fts "query"`. Follow existing `recent --json` pattern at `session.py:108-109`.
11. Add JSON output tests to `scripts/tests/test_dependency_mapper.py` — test `validate --json` in `TestMainCLI` (line 1299). Verify no conflict with `analyze --format json`.
12. Add JSON output tests to `scripts/tests/test_gitignore_cmd.py` — test dry-run and apply with `--json`. Follow Pattern B.
13. For each CLI: verify `--json` in `--help` output, `-j` short flag, valid parseable JSON, no ANSI codes, exit code 0.

**Phase 5 — Documentation (expanded by `/ll:wire-issue`):**
14. Update `docs/reference/API.md` — document the universal `--json` contract.
15. Update `docs/reference/CLI.md` — add `--json \| -j` rows to flag tables in 6 sections: `ll-sync` (status/diff), `ll-logs` (discover/tail), `ll-session` (search), `ll-deps` (validate), `ll-gitignore`, `ll-verify-skill-budget`.
16. Update `skills/map-dependencies/SKILL.md` — note `--json` on `validate` vs `--format json` on `analyze` pattern. Consider normalizing `analyze` to also accept `--json` (or document the inconsistency).

## Impact

- **Priority**: P3 — Not blocking, but reduces agent brittleness across all workflows
- **Effort**: Medium — Many CLIs to touch, but each change is mechanical (add flag + branch on output format)
- **Risk**: Low — Additive change, existing output unchanged, no breaking API surface
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `agent-composability`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-28_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 73/100 → MODERATE

### Outcome Risk Factors
- Criterion A (Complexity 13/25): Wide-shallow sweep across 17 total sites (7 source + 6 test + 4 doc files). Per-site changes are purely mechanical (add `--json` flag + if/else branch), but the enumeration is broad and spans multiple CLI subsystems.
- Criterion D (Change Surface 10/25): Broad implementation surface across 7 CLI entry points. Sites are enumerated in the Integration Map with line numbers, but no unified verification command (e.g., a grep proving all data-emitting subcommands now accept `--json`) is provided. Consider adding a `grep -rL '"--json"' scripts/little_loops/cli/` pre-check to the implementation steps.

## Session Log
- `/ll:wire-issue` - 2026-05-29T03:37:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4763d9ab-78f7-4cbc-a7ba-c9f1f9d72728.jsonl`
- `/ll:refine-issue` - 2026-05-29T03:30:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c7ef651a-ae75-4505-b006-bd8a014cbbac.jsonl`
- `/ll:format-issue` - 2026-05-29T02:28:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9e23d1bf-3385-43d7-80c9-602fafbaf867.jsonl`
- `/ll:capture-issue` - 2026-05-29T02:23:45Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8b24cba6-684e-4420-9519-de98c8b4822b.jsonl`
- `/ll:confidence-check` - 2026-05-28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f9d06869-63f1-4278-ad79-ae92c48ce1b9.jsonl`
- `/ll:issue-size-review` - 2026-05-28T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc1fcf00-8ef7-4a3a-94b4-7099b5095eec.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-28
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- ENH-1783: Add shared add_json_arg() helper to cli_args.py
- ENH-1784: Add --json to Priority 1 CLIs (sync, logs, session)
- ENH-1785: Add --json to Priority 2 CLIs (deps, gitignore)
- ENH-1786: Cross-cutting docs and add --json to ll-verify-skill-budget

---

**Done** | Created: 2026-05-29 | Priority: P3
